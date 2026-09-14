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
import math
import subprocess
import sys
import time
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


def _git_stdin(args: list[str], stdin_text: str,
               cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a git command feeding it stdin -- for the --batch forms.

    Separate from _git so one process can answer N queries: spawning per query
    is what made the rewind check cost ~30s on a wide branch.
    """
    return subprocess.run(
        ["git", *args],
        input=stdin_text,
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


def _rewound_paths(WT: Path, base: str, path: str) -> list[str]:
    """[path] if HEAD's version of `path` is an OLDER blob from base history.

    The discriminator between "I reverted their work" and "I edited this file".
    A rewound file is byte-identical to some earlier commit's version; an edited
    file is identical to none. Blob identity is used because it SURVIVES the bad
    reset -- commit topology does not, since afterwards the merge-base is the
    base tip, which is why four topology-based signals all failed here.

    The base tip's own version is skipped: matching THAT just means the branch
    holds current content, which is the normal case rather than a revert.

    Any git failure yields [] -- the caller has already fail-closed on the
    enumerating diff, and a per-file hiccup must not manufacture a false alarm.
    """
    cur = _git(["rev-parse", "HEAD:{}".format(path)], cwd=str(WT))
    if cur.returncode != 0:
        return []
    cur_blob = cur.stdout.strip()

    # THE BASE's history of this path, deliberately -- not HEAD's. The question
    # is "did this branch rewind to something the BASE once held", so the
    # branch's own past versions are not candidates, and walking HEAD would also
    # shift commits[0] and defeat the base-tip skip below.
    #
    # DO NOT "simplify" this to HEAD. An earlier comment here called the two
    # interchangeable; a reviewer constructed a case where they are not (a
    # branch that self-reverts an experiment, plus the mirror case where the
    # match is pruned by history simplification). I could not reproduce either
    # divergence in three attempts, and the accompanying test does not catch the
    # mutation -- so the disagreement is UNRESOLVED and the argument for `base`
    # is the semantic one above, not a measurement. Treat this line as
    # load-bearing until someone settles it.
    history = _git(["rev-list", base, "--", path], cwd=str(WT))
    if history.returncode != 0:
        return []
    commits = [c for c in history.stdout.split("\n") if c.strip()]
    if len(commits) < 2:
        # Only the base tip's own version exists, and matching THAT is the normal
        # case (the branch holds current content), not a revert. Provably inert
        # to mutate -- with one commit, commits[1:] is empty, the batch gets
        # empty stdin, and the comparison below can never match a 40-hex blob --
        # so no test pins it, which would pin shape rather than behaviour.
        return []

    # ONE cat-file --batch-check for the whole history, not a rev-parse spawn
    # per revision. Measured on this repo: backend/config.py has 129 revisions;
    # spawning per revision costs ~0.8s for just 20 of them, while the batched
    # form resolves all 129 in ~0.14s. At 20-odd modified files the spawn-per-
    # revision shape added ~30s to every closeout, on a script that already has
    # a documented 2-minute timeout problem.
    revs = "\n".join("{}:{}".format(c, path) for c in commits[1:])
    batch = _git_stdin(["cat-file", "--batch-check=%(objectname)"], revs,
                       cwd=str(WT))
    if batch.returncode != 0:
        return []
    for line in batch.stdout.split("\n"):
        if line.strip() == cur_blob:
            return [path]
    return []


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

    # WHOLESALE DELETIONS are the signature of a stale-base squash. `git reset
    # --soft <branch>` moves the branch pointer FORWARD while keeping the OLD
    # tree as the content, so every commit that landed on the base in between
    # becomes a deletion -- silently reverting other people's merged work, with
    # no error, a clean `git status`, and a green suite (the deleted work's
    # tests go with it). Caught once by eye on bd polyglot-pdf-06u5o (a 4-file
    # change reporting "11 files changed, 261 deletions"); this makes it
    # mechanical. Deleting a file on purpose is legitimate, so it is ATTENTION
    # rather than FAIL -- the orchestrator confirms or fixes.
    # THE ANCESTRY GATE IS LOAD-BEARING -- for a reason my first comment here
    # got wrong. It is NOT about diff noise (the three-dot range already
    # handles that). It separates "this branch REVERTED their work" from "this
    # branch is simply BEHIND the base": a behind branch legitimately holds an
    # older version of a file it also touches, and without the gate that
    # false-positives -- measured on 2 of this repo's live worktrees. Only
    # `reset --soft <branch-name>` makes a branch CLAIM to contain the base
    # while its tree does not, so that claim is the discriminator.
    contains = _git(["merge-base", "--is-ancestor", base, "HEAD"], cwd=str(WT))
    reverted_files = []
    if contains.returncode == 0:
        # TWO SHAPES, both real. A file the base ADDED comes back as a deletion;
        # a file the base EDITED comes back as an older blob. The second is the
        # commoner shape of merged work and needs blob identity to see, because
        # the reset destroys commit topology -- afterwards the merge-base IS the
        # base tip. Content survives it: a REWOUND file is byte-identical to an
        # older version in the base's history, an EDITED one to none of them.
        # (An earlier --diff-filter=DM attempt lacked that distinction and fired
        # on this very commit's own three intentional edits; a guard that fires
        # on every branch is one the orchestrator learns to skip.)
        # --no-renames: git's rename detection collapses a rewound RENAME into
        # an R entry, which neither the D nor the M filter selects -- so the
        # trap reported OK on a base that had renamed a file (measured).
        # -z: without it git QUOTES paths with spaces or non-ASCII bytes, and
        # `rev-parse HEAD:"quoted name"` then fails, silently returning no
        # rewind for exactly the paths hardest to notice.
        deleted = _git(["diff", "--diff-filter=D", "--name-only", "-z",
                        "--no-renames", "{}...HEAD".format(base)], cwd=str(WT))
        changed = _git(["diff", "--diff-filter=M", "--name-only", "-z",
                        "--no-renames", "{}...HEAD".format(base)], cwd=str(WT))
        if deleted.returncode != 0 or changed.returncode != 0:
            # FAIL CLOSED. Reading a broken diff as "nothing reverted" would
            # make the detector report the same thing as a safe branch --
            # silence, the exact failure this check exists to eliminate.
            problems.append(
                "could not check for reverted work against {} -- treat as "
                "UNVERIFIED, not clean; re-check `git diff {}...HEAD --stat` "
                "by hand".format(base, base))
        else:
            # -z output is NUL-separated, not newline-separated.
            reverted_files = [f for f in deleted.stdout.split("\0") if f.strip()]
            for path in [f for f in changed.stdout.split("\0") if f.strip()]:
                reverted_files.extend(_rewound_paths(WT, base, path))
    if reverted_files:
        problems.append(
            "branch REVERTS {} file(s) to an older state than {} has -- if that "
            "was not deliberate, this is the squash-to-a-branch-name trap "
            "(CLAUDE.md scar #3); re-check `git diff {}...HEAD --stat`".format(
                len(reverted_files), base, base))

    if problems:
        detail = ""
        if dirty:
            detail += "Uncommitted changes:\n{}\n".format(dirty)
        if reverted_files:
            detail += "\nFiles this branch REVERTS to an older state than {}:\n{}\n".format(
                base, "\n".join("  " + f for f in reverted_files[:20]))
            if len(reverted_files) > 20:
                detail += "  ... and {} more\n".format(len(reverted_files) - 20)
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


# Wall-clock ceiling for the full-suite run, and the margin the gate expects to
# keep over it.
#
# DO NOT defend this ceiling with a hardcoded "measured runtime" literal. That
# was the original shape and it rotted within days: the comment here cited 706s
# for 4494 tests (2026-09-03), and nine days later the suite collected 6017 --
# 6127 by 2026-09-14. Two guards asserted the ceiling against that frozen
# number, so both kept passing while the real run crept toward the timeout they
# existed to prevent (bd polyglot-pdf-f3svv). A literal cannot observe growth;
# only the run itself can.
#
# So the ceiling is defended by MEASUREMENT: check_tests times its own suite run
# and reports the margin, warning once the run consumes more than
# _TESTS_MARGIN_WARN_FRACTION of the ceiling. That signal tracks the suite
# automatically -- a slower machine or a few hundred new tests move it, where a
# literal stays put. The ceiling stays generous because an exceeded ceiling
# yields NO verdict at all (bd polyglot-pdf-u98r1), which is strictly worse than
# a slow run.
_TESTS_TIMEOUT_S = 1800

# Warn when an observed run eats more than this fraction of the ceiling. At 0.5
# the gate speaks up while there is still 2x headroom -- early enough to raise
# the ceiling deliberately rather than discover it mid-closeout with no verdict.
_TESTS_MARGIN_WARN_FRACTION = 0.5


def _timeout_margin_note(elapsed_s: float) -> str:
    """Report how much of the ceiling this run consumed -- "" when comfortable.

    This is the part that RESPONDS to suite growth. The ceiling was previously
    defended by asserting it against a hardcoded "measured runtime" literal,
    which went stale in nine days (706s/4494 tests -> 6127 tests) while every
    guard built on it kept passing, because neither side of that comparison
    observes anything (bd polyglot-pdf-f3svv). An observed duration does.

    Returns a suffix appended to the check's summary, so the signal rides the
    line the orchestrator already reads rather than a new field every consumer
    would have to learn.
    """
    budget_s = _TESTS_TIMEOUT_S * _TESTS_MARGIN_WARN_FRACTION
    if elapsed_s <= budget_s:
        return ""
    # Report the run's OWN fraction, not the threshold that tripped the warning.
    # Quoting the threshold makes a 51%-of-ceiling run and a 99%-one -- a second
    # from being killed with no verdict -- read identically, so the text never
    # intensifies as the situation worsens. Since advance warning of that cliff
    # is the entire purpose here, the number has to move with the run.
    # Round the percentage UP, and carry a decimal. Plain {:.0%} rounds to
    # NEAREST, so a run just over the budget (900.5s of a 1800s ceiling) printed
    # "50%" -- the warning contradicting itself at the very moment it first
    # fires, reading as "not actually over" to anyone skimming; the whole band
    # 900-909s rendered "50%". Rounding up guarantees the displayed figure is
    # never <= the warn threshold once the warning has fired, so the text and
    # the decision to warn can never disagree.
    used_fraction = math.ceil(elapsed_s / float(_TESTS_TIMEOUT_S) * 1000.0) / 1000.0
    return (
        " -- NOTE: the run took {:.0f}s, {:.1%} of the {}s ceiling; raise"
        " _TESTS_TIMEOUT_S deliberately now, because a run that EXCEEDS the"
        " ceiling is killed and yields no verdict at all".format(
            elapsed_s, used_fraction, _TESTS_TIMEOUT_S))


def check_tests(py: Path, WT: Path) -> dict:
    """Step 4: run EVERY collected suite from the worktree, minus flaky externals.

    Deliberately passes NO suite paths: with cwd at the worktree root, a bare
    pytest collects every root in the worktree's own pytest.ini `testpaths`, so
    a NEW top-level suite is gated by closeout the day it is added rather than
    the day someone remembers to edit this function. Hardcoding
    `WT/backend/tests` here made the pre-PR gate blind to `admin_backend/tests`
    the moment that package landed (bd polyglot-pdf-pnoik), which is the same
    shape as the CI miss journaled in bd polyglot-pdf-3ave.

    PYTHONPATH and cwd point at the WORKTREE so this branch's code is what runs
    (the `-m "not external"` matches the project's flaky live-Gemini
    exclusion). A non-zero pytest exit is ATTENTION (the orchestrator must fix a
    red suite before a PR); a launch failure is FAIL.

    THE TIMEOUT IS REPORTED SEPARATELY, AND ITS MARGIN IS MEASURED.
    A timeout here is NOT a red suite and must never read as one:
    subprocess.TimeoutExpired subclasses SubprocessError, so an `except
    SubprocessError` that lumps it in with a launch failure renders every
    closeout as "a check could not run" -- a tooling error the orchestrator
    reads past -- and the suite gate then verifies nothing while looking like
    it ran (bd polyglot-pdf-u98r1). So it is caught FIRST and named.

    The ceiling itself is defended by MEASUREMENT rather than by a frozen
    "measured runtime" literal: this function times its own run and appends the
    observed margin to the summary, warning once a run consumes more than
    _TESTS_MARGIN_WARN_FRACTION of the ceiling. The literal it replaced went
    stale in nine days while the guards built on it kept passing, which is the
    one failure mode a static number cannot report (bd polyglot-pdf-f3svv).
    Note the margin is observable ONLY on a run that finished -- a run killed at
    the ceiling reports no duration at all, which is why the warning has to fire
    well before the ceiling to be worth anything.
    """
    # Sanity-check that WT really is a checkout before shelling out -- a bare
    # pytest in an empty dir "passes" with zero tests, which would render this
    # gate a silent no-op.
    tests_dir = WT / "backend" / "tests"
    if not tests_dir.exists():
        return _result("tests", STATUS_FAIL, "backend/tests/ not found")
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [str(py), "-m", "pytest", "-q", "-m", "not external"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(WT),
            env=_pytest_env(WT),
            timeout=_TESTS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        # Ordered BEFORE the SubprocessError arm below, which would otherwise
        # swallow this (TimeoutExpired subclasses it) and mislabel a suite that
        # merely ran long as a check that could not run at all.
        return _result("tests", STATUS_ATTENTION,
                       "test suite exceeded {}s and was killed -- no verdict; "
                       "re-run it by hand".format(_TESTS_TIMEOUT_S))
    except (OSError, subprocess.SubprocessError) as exc:
        return _result("tests", STATUS_FAIL, "could not run pytest: {}".format(exc))
    elapsed_s = time.monotonic() - started
    out = (proc.stdout or "").strip()
    # Keep the last few lines (the summary line: "N passed, M skipped ...").
    tail = "\n".join(out.splitlines()[-8:])
    margin = _timeout_margin_note(elapsed_s)
    if proc.returncode == 0:
        summary = _summary_line(out) or "suite passed"
        return _result("tests", STATUS_OK, summary + margin, tail)
    return _result("tests", STATUS_ATTENTION,
                   "test suite FAILED (exit {}) -- fix before PR{}".format(
                       proc.returncode, margin),
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
