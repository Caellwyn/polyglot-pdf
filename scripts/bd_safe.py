"""Safe beads (bd) write wrapper: pull/push bracketing + collision checks.

Background
----------
CLAUDE.md mandates a strict cadence around every beads write:

  - Pull before any write (`bd dolt pull`), push after (`bd dolt push`) --
    the local Dolt DB is a cache; the remote at refs/dolt/data is truth.
    Skipping the pull is the "bd 50c" parallel-claim bug class (two workers
    claim the same bead because neither saw the other's claim).
  - Before claiming a bead, run THREE collision checks so a bead another
    worker is mid-flight on is not re-claimed:
      1. gh pr list --search "<full-id>" --state OPEN, then confirm the id is
         in the PR TITLE (PR titles carry the full bead ID per CLAUDE.md rule
         R4). Open-only + title-match avoids two false positives: a merged PR
         blocking the bead forever, and a PR whose BODY merely mentions the
         bead as a deferred/related finding (bd polyglot-pdf-9pe).
      2. git branch -a | grep "<id-suffix>"            (branches carry the
         suffix only, e.g. "ab12")
      3. change-surface overlap (bd polyglot-pdf-h2r.1): the bead's declared
         `metadata.surfaces` (files it will MODIFY) vs the surfaces of every
         ACTIVE claim (in_progress AND backed by a live branch/PR). A
         prefix-aware overlap is a HARD block -- two workers writing the same
         file conflict regardless of intent. Checks 1+2 catch a collision only
         AFTER a branch/PR exists; check 3 catches it at claim time. Skippable
         with --no-surface-check for a deliberate maintainer re-claim.
  - Dependency direction is easy to invert (scar tissue rule 13): the FIRST
    arg to `bd dep add` is what gets BLOCKED, the SECOND unblocks it. Epic
    wiring is a different edge type entirely: bd rejects a task-blocks-epic
    blocks edge ("epics can only block other epics"), so epic-child uses
    `bd dep add <child> <epic> -t parent-child` (bd polyglot-pdf-vj3x).
    This script exposes `--epic`/`--child` so neither the direction nor the
    edge type can be typed wrong.

Doing all of this by hand every write is exactly the deterministic toil the
agent swarm (bd 32qp) pushes out of the model. This script is the mechanism
the /closeout skill and the orchestrator wrap; it spends zero model tokens.

Subcommands
-----------
    python scripts/bd_safe.py claim <id> [--no-surface-check]
        Pull -> three collision checks (ABORT if any matches) -> claim ->
        push. The collision checks are the whole point of claim; if a PR,
        branch, or an active claim's change-surfaces already cover this bead,
        another worker owns it. --no-surface-check drops only the surface guard.

    python scripts/bd_safe.py close <id> [--reason "..."]
        Pull -> close -> push.

    python scripts/bd_safe.py dep-add --epic <epic-id> --child <child-id>
        Pull -> `bd dep add <child> <epic> -t parent-child` (child gains
        PARENT = epic) -> push. Semantic flags make the edge un-invertible.

    python scripts/bd_safe.py dep-add --blocked <id> --prereq <id>
        Pull -> `bd dep add <blocked> <prereq>` -> push. The general
        (non-epic) form, still named so the blocked/prereq roles are explicit.

Exit codes: 0 success; 1 a bd/git/gh command failed or a precondition was not
met; 2 a claim was ABORTED by a collision (distinct so a caller can tell
"someone else owns this" from "the tooling broke").
"""

from __future__ import annotations

import argparse
import json
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
            # Suppress the dozens of git.exe console windows a bd dolt
            # push/pull conjoin spawns on Windows (bd polyglot-pdf-5k32).
            creationflags=swarm_config.windowless_creationflags(),
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
    """Return a one-line PR description if an OPEN PR's TITLE carries this bead id.

    A collision means another worker is actively mid-flight; the caller must NOT
    re-claim. Two scoping rules keep this precise (bd polyglot-pdf-9pe):

      - **OPEN PRs only** (`--state open`). A merged/closed PR is finished work,
        not a live claim -- `--state all` made a long-dead PR block the bead
        forever.
      - **Title match, not full-text.** `gh pr list --search` is GitHub
        full-text and matches the id ANYWHERE, including a PR body that merely
        *mentions* the bead as a deferred/related finding (which is exactly how
        9pe got false-blocked by the merged PR that filed it). PR titles carry
        the id by convention (rule R4: `... (bd <full-id>)`), so we confirm the
        id is in the TITLE before calling it a collision. The `--search` term is
        QUOTED so GitHub treats the hyphenated id as one phrase rather than
        OR-ing its hyphen-split tokens; it only narrows the server-side fetch,
        so a loose match there is harmless -- the title check below is the
        authoritative filter.

    The title match requires an id BOUNDARY (the id is not immediately followed
    by another id char: alnum / `.` / `_` / `-`), so a shorter id is not a false
    positive for a longer one that has it as a prefix -- e.g. `...-ab1` must not
    match a title carrying `...-ab12` (fresh-eyes finding on PR #47).
    """
    proc = _run(
        ["gh", "pr", "list", "--search", '"{}"'.format(bead_id), "--state",
         "open", "--json", "number,title", "--repo", repo],
        check=False,
    )
    # `gh pr list` exits 0 with `[]` when nothing matches. A non-zero exit here
    # is a real tooling failure (auth, network) -- surface it rather than
    # treating "the check could not run" as "no collision".
    if proc.returncode != 0:
        raise RuntimeError(
            "gh pr list collision check failed: {}".format(
                (proc.stderr or "").strip() or "no stderr"
            )
        )
    try:
        prs = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "gh pr list returned unparseable JSON: {}".format(exc)
        )
    # Authoritative filter: the bead id must appear in the PR TITLE as a whole
    # id, not as a prefix of a longer id. `(?!...)` rejects a trailing id char
    # so `polyglot-pdf-ab1` does not match a title carrying `polyglot-pdf-ab12`.
    needle = re.compile(re.escape(bead_id) + r"(?![0-9A-Za-z._-])", re.IGNORECASE)
    hits = [pr for pr in prs if needle.search(pr.get("title") or "")]
    if not hits:
        return None
    return "; ".join(
        "#{}\t{}".format(pr.get("number"), pr.get("title")) for pr in hits
    )


def _pr_numbers_for_bead(bead_id: str, repo: str):
    """Numbers of OPEN PRs whose TITLE carries this bead id, or None if UNKNOWN.

    Same scoping as `_pr_collision` (open-only, title boundary match) but returns
    the PR numbers so a caller can fetch each PR's changed files. Used to DERIVE a
    claim's real change-surfaces when the bead declared none (bd polyglot-pdf-8y7).

    Returns a list (possibly empty -- a confident "no open PR carries this id") on
    a clean read, or **None** when the lookup itself failed (gh error / unparseable
    JSON): the difference matters, because "no PR" is a real signal that lets the
    caller fall through to UNKNOWN, whereas "lookup failed" must NOT be mistaken
    for "no PR" and silently narrow the footprint -- it stays UNKNOWN too.
    """
    # Two anti-truncation measures (Codex review): (1) scope the server-side
    # search to the TITLE (`in:title`), so only the handful of PRs that actually
    # carry the id in their title match -- not every PR whose BODY mentions it as a
    # deferred/related finding; this collapses the result set to ~1 in practice.
    # (2) raise --limit well above gh's default of 30 so even a pathological number
    # of title matches is not silently paged off. The local title-boundary regex
    # below stays the authoritative filter regardless.
    proc = _run(
        ["gh", "pr", "list", "--search", '"{}" in:title'.format(bead_id),
         "--state", "open", "--limit", "200", "--json", "number,title",
         "--repo", repo],
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        prs = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    needle = re.compile(re.escape(bead_id) + r"(?![0-9A-Za-z._-])", re.IGNORECASE)
    return [
        pr.get("number")
        for pr in prs
        if needle.search(pr.get("title") or "") and pr.get("number") is not None
    ]


# `gh pr view --json files` is capped at 100 files by the gh CLI's GraphQL query
# (files(first: 100), no auto-pagination). A PR at or above this count may be
# TRUNCATED, so its derived footprint would be incomplete -- and an incomplete
# footprint can hide a real collision. We therefore treat a >= cap result as
# UNKNOWN rather than trusting a partial list (bd polyglot-pdf-8y7, Codex review).
_PR_FILE_CAP = 100


def _pr_changed_files(pr_number, repo: str):
    """Files an OPEN PR changes, via `gh pr view --json files`, or None if UNKNOWN.

    Returns a list of repo-relative POSIX paths (the surface format the overlap
    math expects) on a confident read, or **None** when the footprint cannot be
    trusted -- a gh failure, unparseable JSON, a possibly-truncated list at the
    100-file gh cap, or a RENAMED entry (see below). A None must be propagated as
    UNKNOWN by the caller (block conservatively), NOT coerced to an empty list
    (bd polyglot-pdf-8y7).

    Renames are a hole in this API (Codex review): `gh pr view --json files`
    exposes only `path`/`changeType`/counts -- the GraphQL PullRequestChangedFile
    schema carries NO previous filename. A rename writes BOTH the new and the old
    path, but we can only see the new one, so a candidate editing the OLD path
    would be wrongly judged disjoint. Rather than fetch a second API for the old
    name, we treat any PR containing a RENAMED entry as UNKNOWN (None) -- the same
    conservative-on-uncertainty rule the rest of this path follows.
    """
    proc = _run(
        ["gh", "pr", "view", str(pr_number), "--json", "files", "--repo", repo],
        check=False,
    )
    if proc.returncode != 0:
        return None  # tooling failure -> UNKNOWN, not "no files"
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    files = (data or {}).get("files") or []
    # A list at/above the gh cap may be truncated -> cannot trust it as complete.
    if len(files) >= _PR_FILE_CAP:
        return None
    out = []
    for f in files:
        if not isinstance(f, dict):
            continue
        # We rely on changeType to detect a rename (whose old path is invisible to
        # this API). RENAMED -> UNKNOWN; a MISSING/empty changeType -> also UNKNOWN
        # (Codex review), because we cannot confirm it is NOT a rename and must not
        # trust a footprint that might be hiding an old path. ADDED/MODIFIED/DELETED
        # are confident single-path entries.
        change_type = str(f.get("changeType") or "").upper()
        if change_type in ("", "RENAMED"):
            return None
        path = f.get("path")
        if isinstance(path, str) and path:
            out.append(path)
    return out


def _derive_surfaces_from_prs(bead_id: str, repo: str):
    """Change-surfaces for a bead derived from its open PR(s), or None if UNKNOWN.

    Returns the de-duplicated union of changed files across every open PR whose
    title carries the id. The caller uses this ONLY when the bead declared no
    surfaces (bd polyglot-pdf-8y7).

    Conservative on EVERY uncertainty (Codex review): if the PR-list lookup failed,
    or ANY single PR's file lookup failed / was truncated, the union would be a
    PARTIAL footprint that could hide a real collision -- so we return **None**
    (UNKNOWN, propagated by the caller into a conservative block) rather than a
    narrowed list. A confident empty union (no open PR carries the id) returns []
    so the caller can fall through to its own UNKNOWN handling.
    """
    numbers = _pr_numbers_for_bead(bead_id, repo)
    if numbers is None:
        return None  # could not even list PRs -> UNKNOWN
    seen, out = set(), []
    for num in numbers:
        files = _pr_changed_files(num, repo)
        if files is None:
            # One PR's footprint is unknowable -> the union is incomplete ->
            # refuse to trust a partial footprint.
            return None
        for path in files:
            if path not in seen:
                seen.add(path)
                out.append(path)
    return out


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


# --- change-surface overlap (the R1 collision guard, bd polyglot-pdf-h2r.1) ---
#
# The PR/branch checks above catch a collision only AFTER the other worker has
# pushed a branch or opened a PR. The surface guard catches it EARLIER, at
# selection/claim time, by comparing the files each bead declares it will
# MODIFY. A bead's `metadata.surfaces` is a structured list of paths (files or
# directory prefixes ending in "/"); two beads collide if any surface of one is
# the same as, or nested under, a surface of the other. Reads don't collide --
# only declared writes do. A bead with no DECLARED surfaces is not immediately
# UNKNOWN: _bead_surfaces first tries to DERIVE its real footprint from its open
# PR's changed files (bd polyglot-pdf-8y7); a bead with neither a declaration nor
# an open PR is UNKNOWN ([]). Post-6hr an UNKNOWN set is PERMISSIVE -- it has no
# concrete surface to collide on and does NOT block (see _surfaces_overlap); only
# two positively-stated, overlapping surfaces block.


def _normalize_surface(surface: str) -> str:
    """Canonicalize a surface path for prefix comparison.

    Forward-slashes (bd metadata + this repo's convention are POSIX-style even
    on Windows), no leading "./", collapse repeated slashes. A trailing slash is
    PRESERVED -- it is the signal that the surface is a directory prefix that
    should match anything nested under it.
    """
    s = surface.strip().replace("\\", "/")
    raw = s  # post-strip, post-backslash: distinguishes "" from "./" / "/"
    while s.startswith("./"):
        s = s[2:]
    # Collapse duplicate slashes but keep a single trailing slash if present.
    had_trailing = s.endswith("/")
    parts = [p for p in s.split("/") if p != ""]
    s = "/".join(parts)
    if had_trailing and s:
        s += "/"
    # A non-empty input that collapses to nothing -- "./", "/", ".//" -- is the
    # REPO ROOT, i.e. "everything." Returning "" here would make it overlap
    # nothing (a false negative: a bead claiming the whole repo would silently
    # opt out of the guard). Canonicalize it to the root dir prefix "/" so the
    # prefix logic in _one_surface_overlaps treats it as containing every path.
    # A genuinely empty input ("") stays "" (handled as no-surface by callers).
    if not s and raw:
        return "/"
    return s


def _one_surface_overlaps(a: str, b: str) -> bool:
    """True if surfaces `a` and `b` refer to overlapping write targets.

    Prefix-aware (the R1 design, h2r.1): a directory surface collides with any
    file or directory nested under it.
      - identical paths overlap;
      - a dir prefix `x/` overlaps any path equal to `x` or starting with `x/`;
      - two files overlap only if identical.
    Comparison is on normalized, slash-delimited path SEGMENTS so that `scripts/`
    matches `scripts/foo.py` but NOT a sibling like `scripts-extra/foo.py`
    (a raw startswith would false-match the latter).
    """
    a = _normalize_surface(a)
    b = _normalize_surface(b)
    if not a or not b:
        return False
    # "/" is the repo-root prefix (from a "./"-style surface): it contains every
    # path, so it overlaps any non-empty surface.
    if a == "/" or b == "/":
        return True
    if a == b:
        return True
    # Treat each as a dir prefix and test containment of the other. A dir prefix
    # "x/" contains "y" iff y == x or y starts with "x/". Strip the trailing
    # slash to get the bare dir path, then require a segment boundary.
    a_dir = a[:-1] if a.endswith("/") else a
    b_dir = b[:-1] if b.endswith("/") else b
    if a.endswith("/") and (b == a_dir or b.startswith(a_dir + "/")):
        return True
    if b.endswith("/") and (a == b_dir or a.startswith(b_dir + "/")):
        return True
    return False


def _surfaces_overlap(surfaces_a, surfaces_b) -> bool:
    """True if any POSITIVELY-STATED surface in A overlaps any in B.

    Empty-surface policy (permissive, bd polyglot-pdf-6hr): if EITHER side has no
    surfaces, there is no concrete file pair to collide on, so we report NO
    overlap. An empty set -- whether the bead was simply never annotated (the
    common case) or a tooling failure left it UNKNOWN -- never blocks. Only two
    concretely-declared, actually-overlapping surfaces block.

    This reverses the earlier conservative "empty collides with everything"
    policy, which froze the whole next-bead board behind any one undeclared
    in-progress bead (e.g. a backend-only fix blocking every frontend bead). The
    maintainer's call: it should be the RARE bead that legitimately blocks
    everything, so the default is permissive, not fail-closed. The trade-off is
    that a transient gh/bd failure that empties one side can let a real overlap
    through; surfaces are advisory scheduling hints, and the same-bead PR/branch
    guards remain the hard backstop against two workers on one bead.
    """
    if not surfaces_a or not surfaces_b:
        return False
    return any(
        _one_surface_overlaps(sa, sb) for sa in surfaces_a for sb in surfaces_b
    )


def _bead_surfaces(bead_id: str, *, derive_from_prs: bool = True,
                   repo: str = DEFAULT_REPO) -> list:
    """Return a bead's change-surfaces.

    Source order (bd polyglot-pdf-8y7):
      1. The bead's DECLARED `metadata.surfaces` -- authoritative when present.
      2. If it declared none AND `derive_from_prs`, the files its open PR(s)
         actually change (the real mid-flight footprint). This gives the guard a
         CONCRETE footprint to match an under-declared active claim on, so a
         genuine overlap is still caught even when the bead never annotated.
      3. [] -- UNKNOWN. Post-6hr an UNKNOWN set is PERMISSIVE in _surfaces_overlap
         (no concrete surface to collide on -> does not block); it is no longer a
         collide-with-everything fallback. This covers the genuinely-unknown case
         (no declaration AND no open PR) AND every UNCERTAINTY: a `bd show`
         failure (we could NOT read the declaration, so we must not trust a
         narrower PR diff over an unreadable authoritative list), or a PR lookup
         that failed / was truncated (Codex review). Uncertainty always collapses
         to UNKNOWN, never to a partial footprint -- the value now is avoiding a
         WRONG partial overlap, not forcing a block.

    Set `derive_from_prs=False` for a pure read of the DECLARED surfaces with no
    network/gh lookup (e.g. unit tests of the declaration path, or callers that
    must not hit the GitHub API).
    """
    proc = _run(["bd", "show", bead_id, "--json"], check=False)
    if proc.returncode != 0:
        # Could NOT read the declaration -> UNKNOWN. Do NOT fall through to PR
        # derivation: a bead that actually declares surfaces would otherwise have
        # an authoritative-but-unreadable list silently replaced by a narrower PR
        # diff, letting a real collision through (Codex review).
        return []
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []  # unreadable declaration -> UNKNOWN, same reasoning
    # `bd show --json` returns a list; the bead is the first element.
    bead = data[0] if isinstance(data, list) and data else data
    meta = (bead or {}).get("metadata") or {}
    surfaces = meta.get("surfaces")
    declared = []
    if isinstance(surfaces, list):
        # Keep only string entries -- a malformed bead (a null/number/nested list
        # in surfaces) must not crash the overlap math with an AttributeError deep
        # in _normalize_surface. Non-string junk is dropped, not coerced.
        declared = [s for s in surfaces if isinstance(s, str)]
    if declared:
        return declared
    if derive_from_prs:
        # None (any PR lookup failed/truncated) -> UNKNOWN -> []. Only a confident
        # derived footprint (or confident empty) is trusted.
        derived = _derive_surfaces_from_prs(bead_id, repo)
        return derived if derived is not None else []
    return []


def _active_claim_ids(exclude_id: str) -> list:
    """Ids of beads that are an ACTIVE claim: in_progress AND backed by a live
    branch or open PR (so a stale/abandoned in_progress bead does not block
    forever -- the h2r.1 "active claim" definition). `exclude_id` (the bead being
    claimed/selected) is never counted against itself.
    """
    proc = _run(
        ["bd", "list", "--status", "in_progress", "--json"], check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "bd list (active-claims) failed: {}".format(
                (proc.stderr or "").strip() or "no stderr"
            )
        )
    try:
        beads = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("bd list returned unparseable JSON: {}".format(exc))
    current = _current_branch()
    active = []
    for bead in beads:
        bead_id = bead.get("id")
        if not bead_id or bead_id == exclude_id:
            continue
        # "live work" = a PR title OR a branch (other than this worktree's own)
        # carries the id. Reuses the same checks the same-bead guard uses.
        # Per-bead error isolation: a transient gh/git failure for ONE
        # in-progress bead must not abort the whole enumeration (the surface
        # check makes many of these calls). On failure, conservatively COUNT the
        # bead as active -- a spurious block is safer than silently missing a
        # real active claim.
        try:
            is_live = bool(
                _pr_collision(bead_id, DEFAULT_REPO)
                or _branch_collision(bead_id, current_branch=current)
            )
        except RuntimeError:
            is_live = True
        if is_live:
            active.append(bead_id)
    return active


def _surface_collision(bead_id: str) -> str | None:
    """Return a description of the FIRST active claim whose change-surfaces
    overlap `bead_id`'s, or None if no active claim collides.

    This is the R1 write-overlap guard. It is a HARD block with no override
    (h2r.1): two workers writing the same concretely-declared file is a conflict
    regardless of intent. A claim with no declared (or derivable) surfaces does
    NOT block -- the permissive empty-surface policy in _surfaces_overlap (bd
    polyglot-pdf-6hr); only a positively-stated overlapping pair blocks. Active
    claims still get PR-derivation (bd polyglot-pdf-8y7) so a mid-flight claim
    that under-declared is matched on its real PR footprint, not nothing.
    """
    # The bead BEING CLAIMED is at claim time -- it has no open PR of its own yet,
    # so derivation would be a wasted gh call; read only its declared surfaces.
    # The ACTIVE claims on the other side DO get derivation (the default), since a
    # mid-flight claim that under-declared is exactly the footprint we want real.
    mine = _bead_surfaces(bead_id, derive_from_prs=False)
    for active_id in _active_claim_ids(exclude_id=bead_id):
        theirs = _bead_surfaces(active_id)
        if not _surfaces_overlap(mine, theirs):
            continue
        # Reaching here means _surfaces_overlap was True, which (post-6hr) implies
        # BOTH sides are non-empty with a concrete overlapping pair -- so there is
        # always a pair to name; no UNKNOWN-surface branch is possible anymore.
        shared = sorted(
            "{} ~ {}".format(sa, sb)
            for sa in mine for sb in theirs
            if _one_surface_overlaps(sa, sb)
        )
        detail = "overlapping surfaces: {}".format("; ".join(shared))
        return "{} ({})".format(active_id, detail)
    return None


def cmd_claim(args: argparse.Namespace) -> int:
    """Pull -> three collision checks -> claim -> push.

    The collision checks gate the claim: if a PR, a branch, OR an active claim's
    change-surfaces overlap this bead, abort with EXIT_ABORT_COLLISION so the
    caller switches to that worker's branch / picks a non-overlapping bead
    instead of double-claiming. The surface check is the R1 backstop
    (bd polyglot-pdf-h2r.1) for selection paths that did not go through
    /next-bead; pass --no-surface-check to skip it (e.g. a deliberate
    maintainer re-claim).
    """
    _dolt_pull()

    pr_hit = _pr_collision(args.id, args.repo)
    branch_hit = _branch_collision(args.id, current_branch=_current_branch())
    surface_hit = None
    if not getattr(args, "no_surface_check", False):
        surface_hit = _surface_collision(args.id)
    if pr_hit or branch_hit or surface_hit:
        print("ABORT: {} appears to be mid-flight already.".format(args.id))
        if pr_hit:
            print("  matching PR(s):\n{}".format(pr_hit))
        if branch_hit:
            print("  matching branch(es):\n{}".format(branch_hit))
        if surface_hit:
            print("  write-surface overlap with active claim:\n  {}".format(
                surface_hit))
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
    """Pull -> `bd dep add ...` -> push, direction-safe.

    Resolves the semantic flags to the right bd edge so the direction
    cannot be inverted:
      --epic X --child Y     -> `bd dep add Y X -t parent-child`
                                (child Y gains PARENT = epic X)
      --blocked X --prereq Y -> `bd dep add X Y` (X BLOCKED BY Y)

    The epic/child form uses a parent-child edge, NOT a blocks edge: the
    installed bd rejects a task-blocks-epic edge ("epics can only block
    other epics"), so epic wiring is `bd dep add <child> <epic>
    -t parent-child` (bd polyglot-pdf-vj3x). For blocks edges (scar rule
    13), the FIRST arg is what gets BLOCKED -- enforced here by mapping
    --blocked to the first position.
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
        dep_cmd = ["bd", "dep", "add", args.child, args.epic, "-t", "parent-child"]
        done_msg = (
            "DEP-ADD: {child} now has PARENT {epic} "
            "(verify with `bd show {child}`).".format(
                child=args.child, epic=args.epic
            )
        )
    else:
        if args.blocked is None or args.prereq is None:
            print("ERROR: pass either --epic/--child or --blocked/--prereq.")
            return EXIT_FAIL
        dep_cmd = ["bd", "dep", "add", args.blocked, args.prereq]
        done_msg = (
            "DEP-ADD: {} is now BLOCKED BY {} "
            "(verify with `bd show {}`).".format(
                args.blocked, args.prereq, args.blocked
            )
        )

    _dolt_pull()
    _run(dep_cmd)
    _dolt_push()
    print(done_msg)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe bd writes: pull/push bracketing + collision checks."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_claim = sub.add_parser("claim", help="Collision-checked claim of a bead.")
    p_claim.add_argument("id", help="Full bead id, e.g. {}".format(swarm_config.example_bead_id()))
    p_claim.add_argument("--repo", default=DEFAULT_REPO, help="OWNER/REPO")
    p_claim.add_argument(
        "--no-surface-check",
        action="store_true",
        help="Skip the change-surface overlap guard (PR/branch checks still run).",
    )
    p_claim.set_defaults(func=cmd_claim)

    p_close = sub.add_parser("close", help="Pull/push-bracketed close.")
    p_close.add_argument("id", help="Full bead id")
    p_close.add_argument("--reason", default=None, help="Close reason")
    p_close.set_defaults(func=cmd_close)

    p_dep = sub.add_parser(
        "dep-add",
        help="Direction-safe dependency edge (epic/child = parent-child).",
    )
    p_dep.add_argument("--epic", default=None, help="Epic id (becomes the parent)")
    p_dep.add_argument("--child", default=None, help="Child id (gains PARENT = epic)")
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
