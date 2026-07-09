"""One-shot deterministic GLUE for the mechanical tail of /closeout.

What this is
------------
The /closeout skill's Steps 5-8.5 are a string of orchestrator Bash turns that
each re-derive the ``$R``/``$WT``/``$PY`` worktree roots and run one git/gh/bd
command: commit the staged closeout work, pre-push rebase, push, open the PR,
record the telemetry row, **commit + push that telemetry row**, and close the
bead(s). Every one of those is **deterministic mechanics** -- no judgment -- so
this script collapses the mechanical subset into ONE process where the path traps
are solved once, internally (bd polyglot-pdf-hrn.13).

Review happens BEFORE this script runs (2026-07-08 flow change). Both review
layers -- the Sonnet/Haiku fresh-eyes inner loop and the Opus-4.8 outer loop --
run on the LOCAL branch and clear to their terminal signals (inner ``NO-GAPS``,
outer two-independent-``NO-GAPS``) before the PR is ever opened. There is NO
external reviewer and NO post-PR review watch (the maintainer's Codex subscription
ended 2026-07-08; the ``pr_review_watcher.py`` bot-watch path is retired). So by
the time this script runs the review is already CLEAN: it opens the PR AND closes
the bead(s) in the SAME run -- there is no review-worthiness gate here and no
two-call watcher pattern.

The telemetry row is written AFTER the closeout commit + push, so a dedicated
``commit_push_telemetry`` step commits + pushes the tool-owned row file by
EXPLICIT PATH -- otherwise the row sits uncommitted in the working tree and is
lost when the worktree is archived (bd polyglot-pdf-3yf). Each row is its own
file under ``docs/journal/telemetry/`` (one per closeout), so parallel PRs never
touch the same path and GitHub merges them without conflict (no custom merge
driver needed). The experiment counter (``.beads/experiment_state.json``) is NOT
committed: it is a gitignored cache derived from all row files (bd
polyglot-pdf-8o4). This is the ONE place the script commits its own files; it
still never ``git add``s the orchestrator's content. WARN-ONLY, like the
telemetry write itself.

It is the Steps-5-7 analogue of how ``closeout_prep.py`` collapses Steps
0/1/2/4. The orchestrator (or a cheap ``closeout-runner`` subagent it delegates
to) runs this AFTER it has made every judgment call and BOTH reviews have cleared
on the local branch: the journal prose, the staged file set, the telemetry
counters. This script executes those decisions; it never makes them.

What it does NOT do (the judgment boundary)
-------------------------------------------
- run the review loop or triage fresh-eyes / outer-review findings (both reviews
  already cleared BEFORE this script runs -- SKILL Steps 5.5 + 5.6);
- resolve a merge conflict (it aborts the rebase and exits REBASE-CONFLICT so
  the orchestrator decides mechanical-vs-structural -- SKILL Step 7);
- write journal prose, or ``git add`` (staging is the orchestrator's content
  decision);
- ``gh pr merge`` (not this script's job -- the merge decision is an orchestrator
  judgment call at closeout Step 8: auto-merge a routine low-risk clean PR, else
  ping the maintainer).

Bead close
----------
Because both reviews already cleared before this script runs, a normal run opens
the PR AND closes the bead(s) in the SAME call -- ``--close-beads`` is the default.
``--close-only`` remains as a standalone recovery tool: it closes the bead(s) and
does NOTHING else (no commit/rebase/push/PR/telemetry), for the rare case where a
PR was opened but its bead close failed or was deferred.

Worktree safety
---------------
Resolves two roots internally (reusing ``closeout_prep``'s helpers so there is
one source of truth):
  - ``R`` (git-common-dir parent) -- the MAIN repo, home of the only venv.
  - ``WT`` (``git rev-parse --show-toplevel``) -- THIS worktree.
Every git command runs as ``git -C "$WT"``; the venv interpreter and the
``$PY``-run scripts come from ``R``'s venv but the script TARGETS come from
``WT`` (``harness_ledger.py``/``bd_safe.py`` run via ``$PY`` against the worktree
copy). Neither the orchestrator nor a cheap subagent ever re-types this path
math again.

Exit codes
----------
  0  all requested steps succeeded (or ``--dry-run`` printed the plan).
  1  a hard tooling failure (push failed, ``gh pr create`` failed, dirty tree
     after the commit, root resolution failed).
  2  a precondition the script can mechanically check is unmet (a missing PR-open
     arg; the branch arg doesn't match the checked-out branch).
  4  REBASE-CONFLICT -- the pre-push rebase hit a conflict; the script aborted it
     (branch left clean) and hands the conflict back to the orchestrator
     (resolution is judgment).

Telemetry is WARN-ONLY: a non-zero ``harness_ledger.py`` exit becomes a
``telemetry: GAP`` line in the output and never changes this script's exit code.

Usage
-----
  python scripts/closeout_finish.py --bead <id> --branch <feat> \\
      --pr-title "..." --pr-body-file body.md \\
      --commit-message "..." --arm A --cost-category production \\
      --copilot-rounds 0 --maintainer-touchpoints 0 --deferred-nits 0 \\
      --haiku-escalations 0 --errors-shipped 0

  python scripts/closeout_finish.py ... --dry-run
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make this script's dir importable so sibling-script imports work under both
# direct execution and importlib-based test loading (same idiom as bd_safe.py /
# journal_scaffold.py importing swarm_config).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarm_config  # noqa: E402
# Reuse the EXACT root/venv resolution closeout_prep uses -- one source of truth
# for the worktree-path traps (bd polyglot-pdf-9pe).
from closeout_prep import resolve_roots, venv_python  # noqa: E402

# bd / gh emit UTF-8; reconfigure so a non-cp1252 glyph in a title/body doesn't
# crash a Windows console (Python 3.7+).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_PRECONDITION = 2
EXIT_REBASE_CONFLICT = 4

SUBPROCESS_TIMEOUT_SEC = 600

# Review is entirely Claude-based and runs BEFORE this script (SKILL Steps 5.5 +
# 5.6): a Sonnet/Haiku fresh-eyes inner loop and an Opus-4.8 outer loop, both on
# the local branch, cleared to their terminal signals before the PR opens. There
# is NO external reviewer and NO post-PR watch -- this script neither triggers a
# bot nor emits a watch command (the maintainer's Codex subscription ended
# 2026-07-08; the pr_review_watcher.py path is retired).


class CloseoutError(Exception):
    """A hard tooling failure -> EXIT_FAIL, with a human message."""


class RebaseConflict(Exception):
    """The pre-push rebase hit a conflict -> EXIT_REBASE_CONFLICT."""


# --------------------------------------------------------------------------- #
# The single subprocess seam. ALL git/gh/bd/ledger calls go through here so the
# unit tests can monkeypatch one function (the bd_safe._run idiom).
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], *, cwd: str | None = None,
         check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, capturing text output. Raises CloseoutError on failure
    when ``check`` (the default)."""
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        timeout=SUBPROCESS_TIMEOUT_SEC,
        # Suppress the dozens of git.exe console windows a bd dolt push/pull
        # conjoin spawns on Windows (bd polyglot-pdf-5k32).
        creationflags=swarm_config.windowless_creationflags(),
    )
    if check and proc.returncode != 0:
        raise CloseoutError(
            "command failed ({}): {}\n{}".format(
                proc.returncode, " ".join(cmd),
                (proc.stderr or proc.stdout or "").strip(),
            )
        )
    return proc


def _utcnow() -> str:
    """UTC stamp in the explicit portable form (not %F/%T -- GNU-only)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base_branch_name(base: str) -> str:
    """'origin/dev' -> 'dev' for the `git pull --rebase origin <name>` form."""
    return base.split("/", 1)[1] if "/" in base else base


# --------------------------------------------------------------------------- #
# Plan: a list of (label, callable) steps. --dry-run prints the labels; a real
# run executes the callables. Each callable returns a dict merged into `out`.
# --------------------------------------------------------------------------- #
class Closeout:
    def __init__(self, args: argparse.Namespace, R: Path, WT: Path, PY: Path,
                 repo: str):
        self.args = args
        self.R = R
        self.WT = WT
        self.PY = PY
        self.repo = repo
        self.wt = str(WT)
        # Accumulated machine-readable output.
        self.out: dict[str, str] = {
            "RESULT": "-", "PR": "-", "telemetry": "-", "beads_closed": "-",
        }

    # -- individual mechanical steps ---------------------------------------- #
    def commit(self) -> None:
        """Commit ALREADY-STAGED closeout work; never `git add`."""
        if not self.args.commit_message:
            return
        _run(["git", "-C", self.wt, "commit", "-m", self.args.commit_message])
        status = _run(["git", "-C", self.wt, "status", "--short"], check=False)
        if status.stdout.strip():
            raise CloseoutError(
                "working tree not clean after commit:\n{}".format(status.stdout.strip())
            )

    def rebase(self) -> None:
        """Pre-push rebase on the integration branch; abort+signal on conflict."""
        _run(["git", "-C", self.wt, "fetch", "origin"])
        name = _base_branch_name(self.args.base)
        proc = _run(["git", "-C", self.wt, "pull", "--rebase", "origin", name],
                    check=False)
        if proc.returncode != 0:
            # Leave the branch clean for the orchestrator to resolve by hand.
            _run(["git", "-C", self.wt, "rebase", "--abort"], check=False)
            raise RebaseConflict(
                "rebase onto {} conflicted; aborted and left the branch clean. "
                "Resolve per SKILL Step 7 (mechanical inline / structural "
                "escalate).\n{}".format(name, (proc.stdout or proc.stderr or "").strip())
            )

    def push(self) -> None:
        _run(["git", "-C", self.wt, "push", "-u", "origin", self.args.branch])

    def open_pr(self) -> None:
        # Review already cleared locally before this script ran (SKILL Steps 5.5 +
        # 5.6), so opening the PR triggers nothing and needs no watch floor.
        # gh wants the bare branch NAME for --base ('dev'), not the remote-
        # qualified ref ('origin/dev') the rebase step uses.
        proc = _run([
            "gh", "pr", "create", "--base", _base_branch_name(self.args.base),
            "--title", self.args.pr_title,
            "--body-file", self.args.pr_body_file,
        ])
        # `gh pr create` prints the PR URL (.../pull/<n>); pick the line that looks
        # like one rather than blindly taking the last line (gh may print a
        # trailing notice). Fall back to the last non-empty line.
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        url = next((ln for ln in lines if "/pull/" in ln), lines[-1] if lines else "")
        num = url.rstrip("/").rsplit("/", 1)[-1]
        if not num.isdigit():
            raise CloseoutError("could not parse PR number from: {!r}".format(url))
        self.out["PR"] = num

    def telemetry(self) -> None:
        """Write the telemetry row file. WARN-ONLY: never raises / changes exit code.

        harness_ledger.py writes one JSON file per row under
        docs/journal/telemetry/ and prints the relative path on a
        ``TELEMETRY_FILE: <path>`` line so commit_push_telemetry can stage it
        by exact path (no glob, no git add -A).
        """
        ledger = self.WT / "scripts" / "harness_ledger.py"
        cmd = [str(self.PY), str(ledger), "--recorded-at", _utcnow()]
        for b in self.args.bead:
            cmd += ["--bead", b]
        if self.args.arm:
            cmd += ["--arm", self.args.arm]
        if self.args.cost_category:
            cmd += ["--cost-category", self.args.cost_category]
        for flag, val in (
            ("--copilot-rounds", self.args.copilot_rounds),
            ("--maintainer-touchpoints", self.args.maintainer_touchpoints),
            ("--deferred-nits", self.args.deferred_nits),
            ("--haiku-escalations", self.args.haiku_escalations),
            ("--errors-shipped", self.args.errors_shipped),
        ):
            if val is not None:
                cmd += [flag, str(val)]
        proc = _run(cmd, check=False)
        # Parse TELEMETRY_FILE: from stdout before checking exit code. The
        # harness_ledger.py prints the path BEFORE the cache-refresh step, so a
        # cache-write failure (non-zero exit) can still leave a valid row file
        # that we should commit. Preserving the path here is what makes that case
        # recoverable rather than silently orphaning the row.
        written = None
        for line in (proc.stdout or "").splitlines():
            if line.startswith("TELEMETRY_FILE: "):
                written = line[len("TELEMETRY_FILE: "):].strip()
                break
        if proc.returncode == 0:
            self.out["telemetry"] = "OK"
            self._telemetry_file = written
        else:
            self.out["telemetry"] = "GAP: ledger exit {} ({})".format(
                proc.returncode,
                (proc.stderr or proc.stdout or "no output").strip().splitlines()[-1]
                if (proc.stderr or proc.stdout).strip() else "no output",
            )
            # Still commit the file if harness_ledger.py did write it (non-zero may
            # be a cache-refresh failure, not a file-write failure).
            self._telemetry_file = written

    # _telemetry_file is set by telemetry() to the repo-relative path of the
    # just-written row file (e.g. "docs/journal/telemetry/2026-06-10T...json").
    # commit_push_telemetry reads it to stage exactly that one file.
    _telemetry_file: "str | None" = None

    def commit_push_telemetry(self) -> None:
        """Commit + push the telemetry row file this run just wrote.

        The ``telemetry`` step writes the file AFTER the closeout commit + push,
        so without this step the file sits uncommitted and is lost when the
        worktree is archived. Staging is by EXACT PATH captured from
        harness_ledger.py stdout -- never ``git add -A``. WARN-ONLY.
        """
        telemetry_file = self._telemetry_file
        if not telemetry_file:
            # Nothing was written (GAP / --dry-run) -- nothing to commit.
            return
        status = _run(["git", "-C", self.wt, "status", "--porcelain", "--",
                       telemetry_file], check=False)
        if status.returncode != 0:
            # The guard itself failed. Surface it rather than silently skipping
            # (that would re-orphan the row). (fresh-eyes PR #70 F1)
            self.out["telemetry"] += " | STATUS-CHECK-FAILED: {}".format(
                (status.stderr or status.stdout or "").strip().splitlines()[-1]
                if (status.stderr or status.stdout).strip() else "no output")
            return
        if not status.stdout.strip():
            return  # clean (e.g. --dry-run, or a ledger GAP) -- nothing to commit
        # Stage the file before committing -- git commit -- <path> does not add
        # untracked files, and each new telemetry row is untracked on first write.
        add = _run(["git", "-C", self.wt, "add", "--", telemetry_file], check=False)
        if add.returncode != 0:
            self.out["telemetry"] += " | ADD-FAILED: {}".format(
                (add.stderr or add.stdout or "").strip().splitlines()[-1]
                if (add.stderr or add.stdout).strip() else "no output")
            return
        pr = self.out["PR"]
        msg = ("chore(harness): PR #{} telemetry row (recorded by closeout_finish.py)"
               .format(pr) if pr != "-"
               else "chore(harness): telemetry row (recorded by closeout_finish.py)")
        commit = _run(["git", "-C", self.wt, "commit", "-m", msg, "--",
                       telemetry_file], check=False)
        if commit.returncode != 0:
            self.out["telemetry"] += " | COMMIT-FAILED: {}".format(
                (commit.stderr or commit.stdout or "").strip().splitlines()[-1]
                if (commit.stderr or commit.stdout).strip() else "no output")
            # Unstage the row so it does not bleed into the next closeout commit.
            _run(["git", "-C", self.wt, "reset", "HEAD", "--", telemetry_file],
                 check=False)
            return
        push = _run(["git", "-C", self.wt, "push", "origin", self.args.branch],
                    check=False)
        if push.returncode != 0:
            self.out["telemetry"] += " | PUSH-FAILED: {}".format(
                (push.stderr or push.stdout or "").strip().splitlines()[-1]
                if (push.stderr or push.stdout).strip() else "no output")
        else:
            self.out["telemetry"] += " (committed+pushed)"

    def close_beads(self) -> None:
        # A normal run always closes the bead(s) now (review already cleared before
        # this script ran), and --close-only exists solely to close. Both paths
        # append close_beads to the plan; the only time it must NOT close is a bare
        # invocation that somehow reached here with neither -- guard defensively.
        if not self.args.close_beads and not self.args.close_only:
            return
        bd_safe = self.WT / "scripts" / "bd_safe.py"
        closed = []
        for b in self.args.bead:
            pr = self.out["PR"]
            reason = ("Closed at /closeout for PR #{} (bd {})".format(pr, b)
                      if pr != "-" else "Closed at /closeout (bd {})".format(b))
            _run([str(self.PY), str(bd_safe), "close", b, "--reason", reason])
            closed.append(b)
        self.out["beads_closed"] = ",".join(closed) if closed else "-"

    # -- orchestration ------------------------------------------------------ #
    def steps(self) -> list[tuple[str, object]]:
        """The ordered (label, callable) plan. Labels drive --dry-run output."""
        plan: list[tuple[str, object]] = []
        # --close-only is a standalone recovery tool: the PR was already opened
        # (and its telemetry row already written) elsewhere, so here we ONLY close
        # the bead(s) -- no commit/rebase/push/PR/telemetry (which also avoids a
        # duplicate ledger row).
        if self.args.close_only:
            plan.append((
                '"{}" "{}/scripts/bd_safe.py" close {} --reason "..."'.format(
                    self.PY, self.wt, " ".join(self.args.bead)),
                self.close_beads))
            return plan
        if self.args.commit_message:
            plan.append((
                'git -C "{}" commit -m "{}"'.format(self.wt, self.args.commit_message),
                self.commit))
        name = _base_branch_name(self.args.base)
        plan.append((
            'git -C "{}" fetch origin && git -C "{}" pull --rebase origin {}'.format(
                self.wt, self.wt, name), self.rebase))
        plan.append(('git -C "{}" push -u origin {}'.format(self.wt, self.args.branch),
                     self.push))
        # Both review layers already cleared locally (SKILL Steps 5.5 + 5.6), so
        # opening the PR triggers no bot and needs no watch -- the PR opens and the
        # bead(s) close in this same run.
        plan.append((
            'gh pr create --base {} --title "{}" --body-file {}'.format(
                name, self.args.pr_title, self.args.pr_body_file),
            self.open_pr))
        plan.append((
            '"{}" "{}/scripts/harness_ledger.py" --bead {} --arm {} ... '
            "(warn-only)".format(self.PY, self.wt, ",".join(self.args.bead),
                                 self.args.arm or "-"),
            self.telemetry))
        plan.append((
            'git -C "{}" commit -m "chore(harness): PR #<PR> telemetry row" -- '
            "docs/journal/telemetry/<row>.json && git push (warn-only; bd 3yf)".format(
                self.wt),
            self.commit_push_telemetry))
        plan.append((
            '"{}" "{}/scripts/bd_safe.py" close {} --reason "..."'.format(
                self.PY, self.wt, " ".join(self.args.bead)),
            self.close_beads))
        return plan

    def run(self) -> int:
        plan = self.steps()
        if self.args.dry_run:
            print("=== closeout_finish DRY RUN (no mutating side effects) ===")
            print("R  = {}".format(self.R))
            print("WT = {}".format(self.WT))
            print("PY = {}".format(self.PY))
            print("repo = {}".format(self.repo))
            if self.args.close_only:
                print("mode = close-only (no PR / no telemetry)")
            else:
                print("mode = open-pr + close-beads (review already cleared "
                      "pre-PR)")
            print("--- plan ---")
            for i, (label, _fn) in enumerate(plan, 1):
                print("  {}. {}".format(i, label))
            # Exercise the ledger's own preview so even that is path-checked --
            # but close-only writes NO ledger row, so there's nothing to preview.
            if not self.args.close_only:
                ledger = self.WT / "scripts" / "harness_ledger.py"
                print("--- ledger --dry-run preview ---")
                prev = _run([str(self.PY), str(ledger), "--dry-run",
                             *sum((["--bead", b] for b in self.args.bead), []),
                             *(["--arm", self.args.arm] if self.args.arm else [])],
                            check=False)
                print((prev.stdout or prev.stderr or "(no ledger preview)").strip())
            print("RESULT: DRY-RUN")
            return EXIT_OK

        for _label, fn in plan:
            fn()  # type: ignore[operator]
        if self.args.close_only:
            self.out["RESULT"] = "CLOSED-ONLY"
        else:
            self.out["RESULT"] = "OPENED-CLOSED"
        self._emit()
        return EXIT_OK

    def _emit(self) -> None:
        print("=== closeout_finish RESULT ===")
        for key in ("RESULT", "PR", "telemetry", "beads_closed"):
            print("{}: {}".format(key, self.out[key])
                  if key != "PR"
                  else "{}={}".format(key, self.out[key]))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--bead", action="append", default=[], required=True,
                   help="Full bead id; repeat for a bundled PR.")
    # --branch / --pr-title / --pr-body-file are required for a normal open-the-PR
    # run but NOT for --close-only (which closes a bead on an already-open PR);
    # main() enforces them conditionally.
    p.add_argument("--branch", default=None, help="The feature branch to push.")
    p.add_argument("--base", default="origin/dev",
                   help="Integration branch (default: origin/dev).")
    p.add_argument("--pr-title", default=None)
    p.add_argument("--pr-body-file", default=None,
                   help="Path to the PR body (a file, to avoid shell-quoting a "
                        "multi-line body).")
    p.add_argument("--commit-message", default=None,
                   help="Commit the ALREADY-STAGED closeout work (no git add).")
    p.add_argument("--arm", choices=["A", "B", "C", "BC"], default=None)
    p.add_argument("--cost-category", choices=["production", "audit"], default=None)
    p.add_argument("--copilot-rounds", type=int, default=None)
    p.add_argument("--maintainer-touchpoints", type=int, default=None)
    p.add_argument("--deferred-nits", type=int, default=None)
    p.add_argument("--haiku-escalations", type=int, default=None)
    p.add_argument("--errors-shipped", type=int, default=None)
    # A normal run always closes the bead(s) (review already cleared pre-PR), so
    # main() sets this on. --close-beads is retained as an explicit no-op for
    # backward compatibility with callers that still pass it.
    p.add_argument("--close-beads", action="store_true",
                   help="Close the bead(s). Default ON for a normal run; retained "
                        "as an explicit flag for backward compatibility.")
    p.add_argument("--close-only", action="store_true",
                   help="Recovery tool: close the bead(s) ONLY -- no commit/rebase/"
                        "push/PR/telemetry (for a PR opened elsewhere whose bead "
                        "close failed or was deferred). Implies --close-beads.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the fully-resolved plan; perform ZERO MUTATING side "
                        "effects (read-only git root-resolution still runs).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # --close-only implies --close-beads (it exists to close, nothing else).
    if args.close_only:
        args.close_beads = True
    else:
        # Normal open-the-PR run: the PR flags are required here (they're
        # argparse-optional only so --close-only can omit them). Review already
        # cleared pre-PR, so this run always closes the bead(s).
        args.close_beads = True
        missing = [f for f, v in (("--branch", args.branch),
                                  ("--pr-title", args.pr_title),
                                  ("--pr-body-file", args.pr_body_file)) if not v]
        if missing:
            sys.stderr.write(
                "closeout_finish.py: missing required arg(s) for a PR-opening run: "
                "{}\n".format(", ".join(missing)))
            return EXIT_PRECONDITION

    try:
        R, WT = resolve_roots()
    except RuntimeError as exc:
        sys.stderr.write("closeout_finish.py: {}\n".format(exc))
        return EXIT_FAIL
    PY = venv_python(R)
    if not PY.exists() and not args.dry_run:
        sys.stderr.write(
            "closeout_finish.py: venv interpreter not found at {}\n".format(PY))
        return EXIT_FAIL

    # Branch sanity: the --branch arg must match the checked-out branch, else a
    # push/rebase would operate on the wrong branch. Skip under --dry-run (no side
    # effects) and under --close-only (no push/rebase happens). FAIL CLOSED: if we
    # cannot read the current branch at all, that's a precondition failure, not a
    # reason to skip the guard and push blindly.
    if not args.dry_run and not args.close_only:
        cur = _run(["git", "-C", str(WT), "rev-parse", "--abbrev-ref", "HEAD"],
                   check=False)
        current = (cur.stdout or "").strip()
        if not current:
            sys.stderr.write(
                "closeout_finish.py: could not determine the current branch "
                "(git rev-parse failed); refusing to push blindly.\n")
            return EXIT_PRECONDITION
        if current != args.branch:
            sys.stderr.write(
                "closeout_finish.py: --branch {!r} != checked-out branch {!r}\n".format(
                    args.branch, current))
            return EXIT_PRECONDITION

    repo = swarm_config.repo()
    job = Closeout(args, R, WT, PY, repo)
    try:
        return job.run()
    except RebaseConflict as exc:
        sys.stderr.write("closeout_finish.py: REBASE-CONFLICT: {}\n".format(exc))
        return EXIT_REBASE_CONFLICT
    except CloseoutError as exc:
        sys.stderr.write("closeout_finish.py: {}\n".format(exc))
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
