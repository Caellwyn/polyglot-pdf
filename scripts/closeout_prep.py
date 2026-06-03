"""Closeout preconditions in ONE deterministic run -> a single structured TODO.

What this is
------------
A **zero-model-token** aggregator (plan §Supporting #4, bd polyglot-pdf-hrn.2).
The /closeout skill's Steps 0, 1, 2, and 4 are four separate deterministic
checks that each cost a skill-load echo and an orchestrator turn to read:

  - **Step 0 -- preconditions:** working tree clean + at least one commit ahead
    of the integration branch.
  - **Step 1 -- beads housekeeping:** ``closeout_housekeeping.py`` (pull +
    orphans + stale + push).
  - **Step 2 -- doc freshness:** ``check_doc_freshness.py`` (run from the
    worktree so it audits THIS branch's docs).
  - **Step 4 -- tests:** the pytest suite.

This script runs all four in sequence and prints ONE structured TODO (plus a
``--json`` form for machine reads), so the orchestrator spends a single turn
reading a single verdict instead of four. It makes **no write decisions** -- it
only reports; closing orphans, fixing stale docs, and fixing test failures stay
the orchestrator's judgment (the only beads/code writer). It is the
Step-0/1/2/4 analogue of the way ``closeout_housekeeping.py`` already collapses
the two beads audits into one run.

What it does NOT do
-------------------
It does not run the *reviews* (fresh-eyes / Copilot), open the PR, or write the
journal -- those are judgment/generative steps (closeout Steps 3, 6, 7) that a
script can't collapse. It also does not auto-fix anything: a STALE doc or a red
test is surfaced, not repaired.

Worktree safety
---------------
Like the skill's hand-run steps, this resolves two roots:
  - ``$R`` (git-common-dir parent) -- the MAIN repo, home of the only venv
    (``backend/.venv``) and of repo-content-agnostic helpers.
  - ``$WT`` (``git rev-parse --show-toplevel``) -- THIS worktree, whose own
    copies of ``check_doc_freshness.py`` and ``backend/tests/`` must be the ones
    that run, so the gate checks the branch under review and not the main
    checkout (the `bd polyglot-pdf-9pe` lesson). ``closeout_housekeeping.py`` is
    content-agnostic (it only talks to ``bd``), so either copy is fine; we use
    the worktree's for consistency.
The Python interpreter always comes from ``$R``'s venv; the doc/test targets
always come from ``$WT``. The check subprocesses run with cwd = ``$WT``.

Exit codes
----------
  0  ALL checks clean -- ready to proceed to the journal/PR steps.
  3  at least one check wants ATTENTION (dirty tree, no commits ahead, a beads
     slip, a stale doc, or a failing/empty test run). Distinct from 1 so the
     caller can branch "there's triage to do" vs "the prep script itself broke."
     This mirrors ``closeout_housekeeping.py``'s advisory SLIP-FOUND code.
  1  the prep run itself failed (couldn't resolve a root, a check subprocess
     could not be launched, etc.) -- a tooling failure, not a closeout verdict.

Usage
-----
  python scripts/closeout_prep.py
  python scripts/closeout_prep.py --base origin/dev --json
  python scripts/closeout_prep.py --skip-tests        # preconditions+beads+docs only
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# render_todo embeds bd orphans/stale output, which carries non-cp1252 glyphs
# (checkmark U+2713, alarm-clock U+23F0). A cp1252 Windows console -- e.g. when
# this runs inside a subshell that didn't inherit UTF-8 -- would crash on
# print(), so reconfigure to UTF-8 with errors="replace" (Python 3.7+). Same
# idiom as journal_scaffold.py and closeout_finish.py.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Status vocabulary for each check. "ok" = nothing to do; "attention" = the
# orchestrator must triage something (not a script failure); "fail" = the check
# itself could not run.
STATUS_OK = "ok"
STATUS_ATTENTION = "attention"
STATUS_FAIL = "fail"

EXIT_OK = 0
EXIT_ATTENTION = 3
EXIT_FAIL = 1


# --------------------------------------------------------------------------- #
# Root resolution (worktree-safe)
# --------------------------------------------------------------------------- #
def _git(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a git command, capturing text output. Raises on launch failure only."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        timeout=60,
    )


def resolve_roots() -> tuple[Path, Path]:
    """Return (R, WT): the main-repo root and this worktree's root.

    R   = parent of the git common dir (the MAIN checkout, home of the venv).
    WT  = the worktree's top level (the branch under review).
    Raises RuntimeError if either cannot be resolved -- a hard tooling failure.
    """
    common = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"])
    if common.returncode != 0:
        raise RuntimeError(
            "could not resolve --git-common-dir: {}".format(common.stderr.strip())
        )
    R = Path(common.stdout.strip()).parent

    top = _git(["rev-parse", "--show-toplevel"])
    if top.returncode != 0:
        raise RuntimeError(
            "could not resolve --show-toplevel: {}".format(top.stderr.strip())
        )
    WT = Path(top.stdout.strip())
    return R, WT


def venv_python(R: Path) -> Path:
    """Return the backend venv interpreter under the MAIN repo (R)."""
    # Windows layout first, then POSIX -- matches the skill's dual form.
    win = R / "backend" / ".venv" / "Scripts" / "python.exe"
    posix = R / "backend" / ".venv" / "bin" / "python"
    return win if win.exists() else posix


# --------------------------------------------------------------------------- #
# Individual checks -> a (status, summary, detail) result dict
# --------------------------------------------------------------------------- #
def _result(check: str, status: str, summary: str, detail: str = "") -> dict:
    return {"check": check, "status": status, "summary": summary, "detail": detail.strip()}


def check_preconditions(WT: Path, base: str) -> dict:
    """Step 0: working tree clean AND at least one commit ahead of `base`.

    Both are required to open a PR: a dirty tree means uncommitted work, and an
    empty `base..HEAD` means there's nothing to close out. Either failing is an
    ATTENTION (the orchestrator must commit / stop), not a tooling FAIL.
    """
    status = _git(["status", "--short"], cwd=str(WT))
    if status.returncode != 0:
        return _result("preconditions", STATUS_FAIL,
                       "git status failed", status.stderr)
    dirty = status.stdout.strip()

    ahead = _git(["log", "--oneline", "{}..HEAD".format(base)], cwd=str(WT))
    if ahead.returncode != 0:
        # A bad base ref is a real blocker the orchestrator must fix, but it is
        # an input error, not the prep script breaking -> ATTENTION with the
        # git message so the cause is visible.
        return _result("preconditions", STATUS_ATTENTION,
                       "could not diff against base '{}' (bad ref?)".format(base),
                       ahead.stderr)
    commits = ahead.stdout.strip()

    problems = []
    if dirty:
        problems.append("working tree is DIRTY (commit or stash before closeout)")
    if not commits:
        problems.append("no commits ahead of {} (nothing to close out)".format(base))

    if problems:
        detail = ""
        if dirty:
            detail += "Uncommitted changes:\n{}\n".format(dirty)
        if commits:
            detail += "\nCommits ahead:\n{}".format(commits)
        elif not dirty:
            # No commits AND a clean tree: explain why the section is otherwise
            # empty. (When also dirty, the "no commits ahead" problem is already
            # in the summary; spell it out here too so the detail isn't just the
            # uncommitted-file list with no mention of the second problem.)
            detail += "No commits ahead of {}.".format(base)
        else:
            detail += "\n(No commits ahead of {} either.)".format(base)
        return _result("preconditions", STATUS_ATTENTION,
                       "; ".join(problems), detail)
    return _result("preconditions", STATUS_OK,
                   "clean tree, {} commit(s) ahead of {}".format(
                       len(commits.splitlines()), base),
                   commits)


def _run_check_script(py: Path, script: Path, cwd: Path,
                      extra: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run one check script with the venv interpreter at cwd=worktree."""
    return subprocess.run(
        [str(py), str(script), *(extra or [])],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
        timeout=600,
    )


def check_beads(py: Path, WT: Path) -> dict:
    """Step 1: closeout_housekeeping.py. Exit 0=clean, 3=slip, 1=tooling fail."""
    script = WT / "scripts" / "closeout_housekeeping.py"
    if not script.exists():
        return _result("beads", STATUS_FAIL, "closeout_housekeeping.py not found")
    try:
        proc = _run_check_script(py, script, WT)
    except (OSError, subprocess.SubprocessError) as exc:
        return _result("beads", STATUS_FAIL, "could not run housekeeping: {}".format(exc))
    out = (proc.stdout or "").strip()
    if proc.returncode == 0:
        return _result("beads", STATUS_OK, "no lifecycle slips", out)
    if proc.returncode == 3:
        return _result("beads", STATUS_ATTENTION,
                       "beads SLIP-FOUND -- triage orphans/stale", out)
    return _result("beads", STATUS_FAIL,
                   "housekeeping exited {} (tooling error)".format(proc.returncode),
                   out + ("\n" + proc.stderr.strip() if proc.stderr.strip() else ""))


def check_docs(py: Path, WT: Path) -> dict:
    """Step 2: check_doc_freshness.py from the WORKTREE (so it audits this branch).

    The freshness checker always exits 0 and is warn-only, so we parse its
    output for a STALE marker rather than relying on the exit code. A stale doc
    that tracks a file THIS branch changed is the orchestrator's to fix; one
    that tracks untouched files was already stale -- the script surfaces the
    text and lets the orchestrator make that call.
    """
    script = WT / "scripts" / "check_doc_freshness.py"
    if not script.exists():
        return _result("docs", STATUS_FAIL, "check_doc_freshness.py not found")
    try:
        proc = _run_check_script(py, script, WT)
    except (OSError, subprocess.SubprocessError) as exc:
        return _result("docs", STATUS_FAIL, "could not run freshness check: {}".format(exc))
    out = (proc.stdout or "").strip()
    # check_doc_freshness.py is documented to ALWAYS exit 0; a non-zero code
    # therefore means it CRASHED (unhandled exception, bad import), in which
    # case stdout is empty/partial and the "STALE" scan below would falsely read
    # CLEAN -> a false READY that lets stale docs through. Treat a non-zero exit
    # as a tooling FAIL, not OK (fresh-eyes PR #54). The beads/test checks
    # already key on the exit code; this brings docs in line.
    if proc.returncode != 0:
        detail = out + ("\n" + proc.stderr.strip() if proc.stderr.strip() else "")
        return _result("docs", STATUS_FAIL,
                       "doc-freshness check exited {} (crashed; verdict unreliable)".format(
                           proc.returncode),
                       detail)
    # The checker prints "STALE" per stale doc and an all-clear line otherwise.
    # Case-sensitive on the literal marker it emits.
    if "STALE" in out:
        return _result("docs", STATUS_ATTENTION,
                       "doc-freshness flagged STALE doc(s) -- review vs this branch's changes",
                       out)
    return _result("docs", STATUS_OK, "all tracked docs fresh", out)


def check_tests(py: Path, WT: Path) -> dict:
    """Step 4: pytest backend/tests/ from the worktree, excluding flaky externals.

    PYTHONPATH and the test path point at the WORKTREE so this branch's code is
    what runs (the `-m "not external"` matches the project's flaky live-Gemini
    exclusion). A non-zero pytest exit is ATTENTION (the orchestrator must fix a
    red suite before a PR); a launch failure is FAIL.
    """
    tests_dir = WT / "backend" / "tests"
    if not tests_dir.exists():
        return _result("tests", STATUS_FAIL, "backend/tests/ not found")
    try:
        proc = subprocess.run(
            [str(py), "-m", "pytest", str(tests_dir), "-q", "-m", "not external"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(WT),
            env=_pytest_env(WT),
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _result("tests", STATUS_FAIL, "could not run pytest: {}".format(exc))
    out = (proc.stdout or "").strip()
    # Keep the last few lines (the summary line: "N passed, M skipped ...").
    tail = "\n".join(out.splitlines()[-8:])
    if proc.returncode == 0:
        return _result("tests", STATUS_OK, _summary_line(out) or "suite passed", tail)
    return _result("tests", STATUS_ATTENTION,
                   "test suite FAILED (exit {}) -- fix before PR".format(proc.returncode),
                   tail + ("\n" + proc.stderr.strip() if proc.stderr.strip() else ""))


def _pytest_env(WT: Path) -> dict:
    """Return an environment with PYTHONPATH set to the worktree root."""
    import os
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(WT) + (os.pathsep + existing if existing else "")
    return env


def _summary_line(pytest_output: str) -> str:
    """Pull pytest's terminal summary line (the one with 'passed'/'failed')."""
    for line in reversed(pytest_output.splitlines()):
        low = line.lower()
        if "passed" in low or "failed" in low or "error" in low:
            return line.strip().strip("=").strip()
    return ""


# --------------------------------------------------------------------------- #
# Aggregation + reporting
# --------------------------------------------------------------------------- #
def overall_status(results: list[dict]) -> str:
    """Roll the per-check statuses up to one verdict.

    Any FAIL -> fail (tooling broke); else any ATTENTION -> attention; else ok.
    FAIL outranks ATTENTION because a check that couldn't run is a stronger
    signal than one that ran and found work.
    """
    statuses = {r["status"] for r in results}
    if STATUS_FAIL in statuses:
        return STATUS_FAIL
    if STATUS_ATTENTION in statuses:
        return STATUS_ATTENTION
    return STATUS_OK


_EXIT_FOR_STATUS = {STATUS_OK: EXIT_OK, STATUS_ATTENTION: EXIT_ATTENTION, STATUS_FAIL: EXIT_FAIL}
_MARK = {STATUS_OK: "[OK]", STATUS_ATTENTION: "[!!]", STATUS_FAIL: "[XX]"}


def render_todo(results: list[dict], status: str) -> str:
    """Render the human-readable structured TODO."""
    lines = ["=== closeout prep ==="]
    for r in results:
        lines.append("{} {:<14} {}".format(_MARK.get(r["status"], "[??]"),
                                            r["check"], r["summary"]))
    lines.append("")
    if status == STATUS_OK:
        lines.append("RESULT: READY -- all Step 0/1/2/4 checks clean. "
                     "Proceed to the journal entry (Step 3) and PR (Step 6).")
    elif status == STATUS_ATTENTION:
        todo = [r for r in results if r["status"] == STATUS_ATTENTION]
        lines.append("RESULT: ATTENTION -- triage before opening the PR:")
        for r in todo:
            lines.append("  - {}: {}".format(r["check"], r["summary"]))
        # Show the detail blocks for the items needing attention so the
        # orchestrator has what it needs without re-running each check.
        for r in todo:
            if r["detail"]:
                lines.append("\n--- {} detail ---\n{}".format(r["check"], r["detail"]))
    else:
        broken = [r for r in results if r["status"] == STATUS_FAIL]
        lines.append("RESULT: PREP-ERROR -- a check could not run (not a closeout "
                     "verdict); investigate:")
        for r in broken:
            lines.append("  - {}: {}".format(r["check"], r["summary"]))
            if r["detail"]:
                lines.append("    {}".format(r["detail"].replace("\n", "\n    ")))
        # A FAIL outranks any co-occurring ATTENTION in the verdict, but the
        # orchestrator still has to act on BOTH -- a dirty tree doesn't go away
        # because the docs check also crashed. Surface the attention items (with
        # their detail) too, so a mixed FAIL+ATTENTION run doesn't cost a second
        # round-trip to discover the dirty tree (fresh-eyes PR #54).
        attention = [r for r in results if r["status"] == STATUS_ATTENTION]
        if attention:
            lines.append("\nAlso needs triage (non-blocking on the prep error):")
            for r in attention:
                lines.append("  - {}: {}".format(r["check"], r["summary"]))
            for r in attention:
                if r["detail"]:
                    lines.append("\n--- {} detail ---\n{}".format(r["check"], r["detail"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--base", default="origin/dev",
                   help="Integration branch for the preconditions diff (default: origin/dev).")
    p.add_argument("--skip-tests", action="store_true",
                   help="Skip Step 4 (pytest). Useful for a quick pre-commit prep.")
    p.add_argument("--json", action="store_true",
                   help="Emit the structured result as JSON instead of the human TODO.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        R, WT = resolve_roots()
    except RuntimeError as exc:
        sys.stderr.write("closeout_prep.py: {}\n".format(exc))
        return EXIT_FAIL

    py = venv_python(R)
    if not py.exists():
        sys.stderr.write(
            "closeout_prep.py: venv interpreter not found at {} -- the backend "
            "venv lives only in the main repo.\n".format(py)
        )
        return EXIT_FAIL

    results = [
        check_preconditions(WT, args.base),
        check_beads(py, WT),
        check_docs(py, WT),
    ]
    if not args.skip_tests:
        results.append(check_tests(py, WT))

    status = overall_status(results)

    if args.json:
        print(json.dumps(
            {"status": status, "base": args.base, "checks": results},
            indent=2, ensure_ascii=False,
        ))
    else:
        print(render_todo(results, status))

    return _EXIT_FOR_STATUS[status]


if __name__ == "__main__":
    sys.exit(main())
