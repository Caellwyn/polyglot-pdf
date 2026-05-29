"""Safe beads (bd) write wrapper: pull/push bracketing + collision checks.

Background
----------
CLAUDE.md mandates a strict cadence around every beads write:

  - Pull before any write (`bd dolt pull`), push after (`bd dolt push`) --
    the local Dolt DB is a cache; the remote at refs/dolt/data is truth.
    Skipping the pull is the "bd 50c" parallel-claim bug class (two workers
    claim the same bead because neither saw the other's claim).
  - Before claiming a bead, run TWO collision checks so a bead another
    worker is mid-flight on is not re-claimed:
      1. gh pr list --search "<full-id>" --state all   (PR titles carry the
         full bead ID per CLAUDE.md rule R4)
      2. git branch -a | grep "<id-suffix>"            (branches carry the
         suffix only, e.g. "ab12")
  - Dependency direction is easy to invert (scar tissue rule 13): the FIRST
    arg to `bd dep add` is what gets BLOCKED, the SECOND unblocks it. The
    epic trap: an epic is BLOCKED BY its children, so the epic is the first
    arg. This script exposes `--epic`/`--child` so the direction cannot be
    typed backwards.

Doing all of this by hand every write is exactly the deterministic toil the
agent swarm (bd 32qp) pushes out of the model. This script is the mechanism
the /closeout skill and the orchestrator wrap; it spends zero model tokens.

Subcommands
-----------
    python scripts/bd_safe.py claim <id>
        Pull -> two collision checks (ABORT if either matches) -> claim ->
        push. The collision checks are the whole point of claim; if a PR or
        branch already carries this bead, another worker owns it.

    python scripts/bd_safe.py close <id> [--reason "..."]
        Pull -> close -> push.

    python scripts/bd_safe.py dep-add --epic <epic-id> --child <child-id>
        Pull -> `bd dep add <epic> <child>` (epic BLOCKED BY child) -> push.
        Semantic flags make the direction un-invertible.

    python scripts/bd_safe.py dep-add --blocked <id> --prereq <id>
        Pull -> `bd dep add <blocked> <prereq>` -> push. The general
        (non-epic) form, still named so the blocked/prereq roles are explicit.

Exit codes: 0 success; 1 a bd/git/gh command failed or a precondition was not
met; 2 a claim was ABORTED by a collision (distinct so a caller can tell
"someone else owns this" from "the tooling broke").
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# Ensure this script's own directory is importable so `import swarm_config`
# works whether the script is run directly (`python scripts/bd_safe.py`, which
# already puts scripts/ on sys.path) OR imported via importlib by the test
# harness (which does NOT).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarm_config  # noqa: E402

# bd/gh/git emit UTF-8 (bead titles, branch names, a U+2713 in some bd output).
# Printing that to a cp1252 Windows console crashes with UnicodeEncodeError, so
# reconfigure stdout/stderr to UTF-8 with errors="replace" -- the same decode
# robustness _run already applies to captured output. (Python 3.7+.)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# The repo bd commands target, from swarm.config.json / SWARM_REPO env (see
# swarm_config.py). PR-title searches use the FULL bead id; branch greps use
# the SUFFIX only (e.g. "ab12" for myproject-ab12) -- branches are
# <type>/<id-suffix>-<slug>.
DEFAULT_REPO = swarm_config.repo()

# Exit codes. ABORT_COLLISION is distinct from the generic failure so a shell
# (or the orchestrator) can branch: "switch to their branch" vs "the tooling
# itself broke and needs investigating."
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_ABORT_COLLISION = 2

# Per-subprocess wall-clock cap. A hung `bd dolt push` (network) or `gh`
# (auth refresh) must become a reported failure, not a silent stall -- the
# swarm's generalized hang discipline (plan constraint 4) applies to scripts
# too. Pull/push can be slow on a cold Dolt remote, so the cap is generous.
SUBPROCESS_TIMEOUT_SEC = 120


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, streaming nothing, capturing text output.

    encoding="utf-8"/errors="replace": bd and gh emit UTF-8 (bead titles,
    review bodies); the Windows platform default (cp1252) would crash the
    reader on a stray non-cp1252 byte. timeout converts a hang into a
    reported failure rather than a stall. On a non-zero exit (when check)
    the stderr is surfaced so the caller sees WHY.
    """
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "command timed out after {}s: {}".format(
                SUBPROCESS_TIMEOUT_SEC, " ".join(cmd)
            )
        )
    except OSError as exc:
        raise RuntimeError("could not run {}: {}".format(cmd[0], exc))
    if check and proc.returncode != 0:
        raise RuntimeError(
            "command failed (exit {}): {}\n{}".format(
                proc.returncode,
                " ".join(cmd),
                (proc.stderr or proc.stdout or "").strip() or "no output",
            )
        )
    return proc


def _dolt_pull() -> None:
    _run(["bd", "dolt", "pull"])


def _dolt_push() -> None:
    _run(["bd", "dolt", "push"])


def _id_suffix(bead_id: str) -> str:
    """The branch-grep token: the bead id with the project prefix stripped.

    Branches carry only the suffix (e.g. "ab12" for myproject-ab12). The
    suffix is the segment after the LAST hyphen, which is correct whether the
    project prefix is a single token (myproject-) or itself hyphenated
    (my-project-). Punctuation in the suffix (the "." in compound ids like
    ab12.2) is dropped to match branch naming (ab122).
    """
    suffix = bead_id.rsplit("-", 1)[-1]
    return suffix.replace(".", "").replace("_", "")


def _pr_collision(bead_id: str, repo: str) -> str | None:
    """Return non-empty PR-list output if a PR already carries this bead id.

    Searches by the FULL bead id (PR titles carry it, per rule R4). A match
    means another worker is mid-flight; the caller must NOT re-claim.
    """
    proc = _run(
        ["gh", "pr", "list", "--search", bead_id, "--state", "all",
         "--repo", repo],
        check=False,
    )
    # `gh pr list` exits 0 with empty stdout when nothing matches. A non-zero
    # exit here is a real tooling failure (auth, network) -- surface it rather
    # than treating "the check could not run" as "no collision".
    if proc.returncode != 0:
        raise RuntimeError(
            "gh pr list collision check failed: {}".format(
                (proc.stderr or "").strip() or "no stderr"
            )
        )
    out = proc.stdout.strip()
    return out or None


def _current_branch() -> str | None:
    """The branch checked out in THIS worktree, or None (detached/error).

    The claim is run from inside the worktree the agent already created for
    this bead, so the bead's own feature branch is normally already checked
    out here. That branch is MINE, not another worker's -- excluding it from
    the collision match is what removes the self-collision false positive.
    """
    proc = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False)
    if proc.returncode != 0:
        return None
    name = proc.stdout.strip()
    # "HEAD" means detached -- no current branch to exclude.
    return name if name and name != "HEAD" else None


def _branch_collision(bead_id: str, *, current_branch: str | None = None) -> str | None:
    """Return matching branch lines if ANOTHER branch carries the suffix.

    The branch checked out in this worktree (`current_branch`) is excluded:
    an agent claims a bead from inside the worktree it just created for that
    bead, so the bead's own feature branch is already checked out and is NOT
    a foreign-worker collision. Without this exclusion, every claim run from
    the correct worktree would self-abort. A foreign worker's branch (any
    other ref carrying the suffix) still trips the check.
    """
    suffix = _id_suffix(bead_id)
    proc = _run(["git", "branch", "-a"], check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "git branch -a collision check failed: {}".format(
                (proc.stderr or "").strip() or "no stderr"
            )
        )
    # Match the suffix only at a token boundary, not as a bare substring: a
    # plain `"c1" in line` would false-positive on "feature/calendar-ical-fix"
    # for a short suffix and ABORT a legitimate claim. Branches are
    # <type>/<suffix>-<slug>, so the suffix is flanked by a non-alphanumeric
    # delimiter (/, -) or a string edge. \b alone is insufficient because a
    # numeric suffix like "3go1" abutting a digit would still match; anchor on
    # an explicit non-[a-z0-9] (or edge) on each side.
    pattern = re.compile(
        r"(?<![a-z0-9]){}(?![a-z0-9])".format(re.escape(suffix.lower()))
    )
    matches = []
    for line in proc.stdout.splitlines():
        if not pattern.search(line.lower()):
            continue
        if _is_own_current_branch(line, current_branch):
            continue
        matches.append(line)
    return "\n".join(matches) if matches else None


def _is_own_current_branch(branch_line: str, current_branch: str | None) -> bool:
    """True if a `git branch -a` line refers to THIS worktree's checked-out branch.

    `git branch -a` prefixes the current branch with "* " and (from another
    worktree) other-worktree branches with "+ ". We strip the marker and any
    leading "remotes/origin/" so a local "* feature/x" and its tracking
    "remotes/origin/feature/x" both compare equal to current_branch == "feature/x".
    The `remotes/origin/<branch>` tracking ref of the SAME branch is also
    treated as "mine" -- it's the push of the branch I'm on, not a foreign
    worker.
    """
    if not current_branch:
        return False
    name = branch_line.strip().lstrip("*+ ").strip()
    # Drop a trailing "-> origin/..." that symbolic refs (HEAD) can carry.
    name = name.split(" ->", 1)[0].strip()
    # `git branch -a` always emits remote refs as "remotes/<remote>/<branch>";
    # stripping "remotes/" leaves "<remote>/<branch>", which is NOT equal to a
    # local current_branch -- so a remote tracking ref of a DIFFERENT remote
    # won't be falsely excluded, while origin's tracking ref of the current
    # branch is handled by the "remotes/origin/" case.
    for prefix in ("remotes/origin/", "remotes/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name == current_branch


def cmd_claim(args: argparse.Namespace) -> int:
    """Pull -> two collision checks -> claim -> push.

    The collision checks gate the claim: if EITHER a PR or a branch already
    carries this bead, abort with EXIT_ABORT_COLLISION so the caller switches
    to that worker's branch instead of double-claiming.
    """
    _dolt_pull()

    pr_hit = _pr_collision(args.id, args.repo)
    branch_hit = _branch_collision(args.id, current_branch=_current_branch())
    if pr_hit or branch_hit:
        print("ABORT: {} appears to be mid-flight already.".format(args.id))
        if pr_hit:
            print("  matching PR(s):\n{}".format(pr_hit))
        if branch_hit:
            print("  matching branch(es):\n{}".format(branch_hit))
        print(
            "Switch to that worker's branch/PR instead of re-claiming "
            "(CLAUDE.md collision rule)."
        )
        return EXIT_ABORT_COLLISION

    _run(["bd", "update", args.id, "--claim"])
    _dolt_push()
    print("CLAIMED: {}".format(args.id))
    return EXIT_OK


def cmd_close(args: argparse.Namespace) -> int:
    """Pull -> close (with optional reason) -> push."""
    _dolt_pull()
    cmd = ["bd", "close", args.id]
    if args.reason:
        cmd += ["--reason", args.reason]
    _run(cmd)
    _dolt_push()
    print("CLOSED: {}".format(args.id))
    return EXIT_OK


def cmd_dep_add(args: argparse.Namespace) -> int:
    """Pull -> `bd dep add <blocked> <prereq>` -> push, direction-safe.

    Resolves the semantic flags to the (blocked, prereq) pair so the
    direction cannot be inverted:
      --epic X --child Y     -> blocked=X (the epic), prereq=Y (the child)
      --blocked X --prereq Y -> blocked=X, prereq=Y

    `bd dep add <blocked> <prereq>` makes <blocked> BLOCKED BY <prereq>
    (scar rule 13). An epic is blocked by its children, so the epic is the
    first arg -- enforced here by mapping --epic to `blocked`.
    """
    epic_pair = args.epic is not None or args.child is not None
    generic_pair = args.blocked is not None or args.prereq is not None
    # Mixing the two flag pairs is ambiguous -- reject rather than silently
    # preferring one. A script whose whole job is making direction
    # un-invertible must not quietly drop half its inputs.
    if epic_pair and generic_pair:
        print("ERROR: pass EITHER --epic/--child OR --blocked/--prereq, not both.")
        return EXIT_FAIL
    if epic_pair:
        if args.epic is None or args.child is None:
            print("ERROR: --epic and --child must be given together.")
            return EXIT_FAIL
        blocked, prereq = args.epic, args.child
    else:
        if args.blocked is None or args.prereq is None:
            print("ERROR: pass either --epic/--child or --blocked/--prereq.")
            return EXIT_FAIL
        blocked, prereq = args.blocked, args.prereq

    _dolt_pull()
    _run(["bd", "dep", "add", blocked, prereq])
    _dolt_push()
    print(
        "DEP-ADD: {} is now BLOCKED BY {} "
        "(verify with `bd show {}`).".format(blocked, prereq, blocked)
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe bd writes: pull/push bracketing + collision checks."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_claim = sub.add_parser("claim", help="Collision-checked claim of a bead.")
    p_claim.add_argument("id", help="Full bead id, e.g. {}".format(swarm_config.example_bead_id()))
    p_claim.add_argument("--repo", default=DEFAULT_REPO, help="OWNER/REPO")
    p_claim.set_defaults(func=cmd_claim)

    p_close = sub.add_parser("close", help="Pull/push-bracketed close.")
    p_close.add_argument("id", help="Full bead id")
    p_close.add_argument("--reason", default=None, help="Close reason")
    p_close.set_defaults(func=cmd_close)

    p_dep = sub.add_parser(
        "dep-add",
        help="Direction-safe dependency edge (epic BLOCKED BY child).",
    )
    p_dep.add_argument("--epic", default=None, help="Epic id (gets blocked)")
    p_dep.add_argument("--child", default=None, help="Child id (unblocks epic)")
    p_dep.add_argument("--blocked", default=None, help="Generic: id that is blocked")
    p_dep.add_argument("--prereq", default=None, help="Generic: id that unblocks it")
    p_dep.set_defaults(func=cmd_dep_add)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print("ERROR: {}".format(exc))
        return EXIT_FAIL
    except KeyboardInterrupt:
        print("ERROR: interrupted.")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
