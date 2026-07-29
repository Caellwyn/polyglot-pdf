"""Tests for scripts/closeout_finish.py (bd polyglot-pdf-hrn.13).

Pins the safety-critical contract of the closeout glue script. Review is entirely
Claude-based and runs BEFORE this script (2026-07-08 flow change: both review
layers clear on the local branch, then this script opens the PR AND closes the
bead(s) in one run), so there is no review-worthiness gate, no watch command, and
no external-reviewer trigger to pin here.
  - --dry-run performs ZERO mutating subprocess calls (the highest-value test --
    it pins the "preview has no side effects" promise);
  - worktree safety: every git call is `git -C <WT>`; no `git add` ever;
  - a normal run opens the PR and closes the bead(s); it emits NO watch command and
    makes NO gh-api / reviewer-API / bot-trigger call;
  - a rebase conflict aborts the rebase and exits REBASE-CONFLICT (4);
  - --close-only closes the bead(s) ONLY (recovery tool).

All git/gh/bd calls go through closeout_finish._run, so the tests stub
that single seam rather than spawning real processes (the bd_safe._run idiom).
The live end-to-end run is the closeout's own --dry-run demo + first dogfood.

Run with the backend venv (the worktree has no venv of its own):
  PYTHONPATH=. backend/.venv/Scripts/python.exe -m pytest tests/test_closeout_finish.py
"""
import argparse
import importlib.util
import pathlib
import subprocess
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

# closeout_finish imports `from closeout_prep import ...`; its own sys.path.insert
# makes that resolve, but pre-loading closeout_prep keeps the module identity
# stable across tests (same idiom as test_closeout_prep).
for _name in ("swarm_config", "closeout_prep"):
    _spec = importlib.util.spec_from_file_location(_name, SCRIPTS / "{}.py".format(_name))
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _mod
    _spec.loader.exec_module(_mod)

spec = importlib.util.spec_from_file_location("closeout_finish", SCRIPTS / "closeout_finish.py")
cf = importlib.util.module_from_spec(spec)
sys.modules["closeout_finish"] = cf
spec.loader.exec_module(cf)


# --------------------------------------------------------------------------- #
# A recording stub for the single subprocess seam
# --------------------------------------------------------------------------- #
class RunRecorder:
    """Records every _run(cmd) and returns scripted CompletedProcess results.

    `responses` maps a substring-of-the-joined-cmd -> (returncode, stdout,
    stderr); the first matching key wins, default success-empty.
    """
    def __init__(self, responses=None):
        self.calls: list[list[str]] = []
        self.responses = responses or {}

    def __call__(self, cmd, *, cwd=None, check=True):
        self.calls.append(list(cmd))
        joined = " ".join(cmd)
        rc, out, err = 0, "", ""
        for needle, resp in self.responses.items():
            if needle in joined:
                rc, out, err = resp
                break
        if check and rc != 0:
            raise cf.CloseoutError("stubbed failure ({}): {}".format(rc, joined))
        return subprocess.CompletedProcess(args=cmd, returncode=rc, stdout=out, stderr=err)

    def joined(self) -> list[str]:
        return [" ".join(c) for c in self.calls]


FAKE_R = pathlib.Path("/fake/main")
FAKE_WT = pathlib.Path("/fake/main/.wt/branch")
FAKE_PY = FAKE_R / "backend" / ".venv" / "Scripts" / "python.exe"


def _args(**over):
    """Build a Namespace with sensible defaults; override per test."""
    base = dict(
        bead=["proj-aa11"], branch="feat/x", base="origin/dev",
        pr_title="docs(x): y (bd proj-aa11)", pr_body_file="/tmp/body.md",
        commit_message=None,
        arm="A", cost_category="production", copilot_rounds=0,
        maintainer_touchpoints=0, deferred_nits=0, haiku_escalations=0,
        errors_shipped=0, close_beads=True, close_only=False, dry_run=False,
    )
    base.update(over)
    return argparse.Namespace(**base)


def _job(recorder, **over):
    """A Closeout wired to the recorder seam and fake roots."""
    cf._run = recorder  # monkeypatch the single seam
    return cf.Closeout(_args(**over), FAKE_R, FAKE_WT, FAKE_PY, "owner/repo")


@pytest.fixture(autouse=True)
def _restore_run():
    orig = cf._run
    yield
    cf._run = orig


# --------------------------------------------------------------------------- #
# CLI contract
# --------------------------------------------------------------------------- #
class TestCLIContract:
    def test_pr_run_requires_pr_flags(self, monkeypatch):
        # A PR-opening run (not --close-only) missing a PR flag must fail the
        # precondition check in main() (the flags are argparse-optional only so
        # --close-only can omit them).
        rec = RunRecorder()
        monkeypatch.setattr(cf, "_run", rec)
        monkeypatch.setattr(cf, "resolve_roots", lambda: (FAKE_R, FAKE_WT))
        monkeypatch.setattr(cf, "venv_python", lambda R: FAKE_PY)
        monkeypatch.setattr(cf.Path, "exists", lambda self: True)
        # missing --pr-title / --pr-body-file
        rc = cf.main(["--bead", "x", "--branch", "b"])
        assert rc == cf.EXIT_PRECONDITION

    def test_no_review_gate_flags(self):
        # The retired external-reviewer gate flags no longer exist.
        with pytest.raises(SystemExit):
            cf.build_parser().parse_args(
                ["--bead", "x", "--branch", "b", "--pr-title", "t",
                 "--pr-body-file", "f", "--skip-review"])

    def test_bead_repeatable(self):
        ns = cf.build_parser().parse_args(
            ["--bead", "x", "--bead", "y", "--branch", "b", "--pr-title", "t",
             "--pr-body-file", "f"])
        assert ns.bead == ["x", "y"]


# --------------------------------------------------------------------------- #
# --dry-run: ZERO mutating calls (the headline safety property)
# --------------------------------------------------------------------------- #
class TestDryRun:
    def test_no_mutating_calls(self, capsys):
        rec = RunRecorder()
        job = _job(rec, dry_run=True, commit_message="c")
        assert job.run() == cf.EXIT_OK
        # --dry-run now makes ZERO subprocess calls: the only one it ever made
        # was the telemetry ledger's own --dry-run preview, and the ledger is
        # gone (bd polyglot-pdf-40r4). The plan is printed from in-memory labels.
        assert rec.calls == [], rec.joined()
        out = capsys.readouterr().out
        assert "DRY RUN" in out and "RESULT: DRY-RUN" in out


# --------------------------------------------------------------------------- #
# Worktree safety
# --------------------------------------------------------------------------- #
class TestWorktreeSafety:
    def test_all_git_calls_use_C_worktree(self):
        rec = RunRecorder(responses={"pr create": (0, "https://github.com/o/r/pull/9", "")})
        job = _job(rec, commit_message="c")
        job.run()
        for cmd in rec.calls:
            if cmd and cmd[0] == "git":
                assert cmd[1] == "-C" and cmd[2] == str(FAKE_WT), cmd

    def test_never_git_add(self):
        rec = RunRecorder(responses={"pr create": (0, "https://github.com/o/r/pull/9", "")})
        job = _job(rec, commit_message="c")
        job.run()
        assert not any("add" in " ".join(c) for c in rec.calls if c and c[0] == "git")


# --------------------------------------------------------------------------- #
# Open-PR-and-close (the unified normal run; review already cleared pre-PR)
# --------------------------------------------------------------------------- #
class TestOpenAndClose:
    def test_opens_pr_closes_beads_no_bot_trigger(self):
        # A normal run opens the PR and closes the bead(s) in ONE run. It emits NO
        # watch command and makes NO gh-api / reviewer-API / bot-trigger call --
        # review is entirely Claude-based and already cleared before this ran.
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/42", ""),
        })
        job = _job(rec)
        assert job.run() == cf.EXIT_OK
        assert job.out["PR"] == "42"
        # No leftover watch/floor keys in the output.
        assert "WATCH_CMD" not in job.out
        assert "TS" not in job.out
        # NO gh api call, NEVER the reviewer API, no bot mention.
        assert not any("gh api" in j for j in rec.joined())
        assert not any("requested_reviewers" in j for j in rec.joined())
        assert not any("@copilot" in j for j in rec.joined())
        assert not any("@codex" in j for j in rec.joined())
        assert not any("pr_review_watcher" in j for j in rec.joined())
        # The bead(s) were closed in this same run.
        assert any("bd_safe.py" in j and "close" in j for j in rec.joined())
        assert job.out["beads_closed"] == "proj-aa11"
        assert job.out["RESULT"] == "OPENED-CLOSED"

    def test_no_retired_reviewer_symbols(self):
        # Regression guard: the retired external-reviewer machinery is gone.
        assert not hasattr(cf, "CODEX_REVIEW_TRIGGER")
        assert not hasattr(cf.Closeout, "request_review")

    def test_pr_create_uses_bare_base_name(self):
        # gh pr create --base wants the branch NAME ('dev'), not 'origin/dev'.
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/42", ""),
        })
        job = _job(rec, base="origin/dev")
        job.run()
        create = [c for c in rec.calls if "create" in c][0]
        i = create.index("--base")
        assert create[i + 1] == "dev", create


# --------------------------------------------------------------------------- #
# Rebase conflict
# --------------------------------------------------------------------------- #
class TestRebaseConflict:
    def test_aborts_and_signals(self):
        rec = RunRecorder(responses={
            "pull --rebase": (1, "CONFLICT (content): journal.md", ""),
        })
        job = _job(rec)
        with pytest.raises(cf.RebaseConflict):
            job.run()
        # it aborted the rebase, leaving the branch clean
        assert any("rebase --abort" in j for j in rec.joined())

    def test_main_maps_to_exit_4(self, monkeypatch):
        rec = RunRecorder(responses={
            "rev-parse --abbrev-ref": (0, "feat/x", ""),
            "pull --rebase": (1, "CONFLICT", ""),
        })
        monkeypatch.setattr(cf, "_run", rec)
        monkeypatch.setattr(cf, "resolve_roots", lambda: (FAKE_R, FAKE_WT))
        monkeypatch.setattr(cf, "venv_python", lambda R: FAKE_PY)
        monkeypatch.setattr(cf.swarm_config, "repo", lambda: "owner/repo")
        # venv_python(.exists) is checked unless dry-run; fake a real path check
        monkeypatch.setattr(cf.Path, "exists", lambda self: True)
        rc = cf.main(["--bead", "proj-aa11", "--branch", "feat/x",
                      "--pr-title", "t", "--pr-body-file", "f"])
        assert rc == cf.EXIT_REBASE_CONFLICT


# --------------------------------------------------------------------------- #
class TestCloseBeadsGated:
    def test_main_forces_close_on_normal_run(self, monkeypatch):
        # A normal CLI run always closes the bead(s): main() sets close_beads=True
        # (review already cleared pre-PR), so the PR-open run and the close are one.
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/7", ""),
            "rev-parse --abbrev-ref": (0, "feat/x", ""),
        })
        monkeypatch.setattr(cf, "_run", rec)
        monkeypatch.setattr(cf, "resolve_roots", lambda: (FAKE_R, FAKE_WT))
        monkeypatch.setattr(cf, "venv_python", lambda R: FAKE_PY)
        monkeypatch.setattr(cf.swarm_config, "repo", lambda: "owner/repo")
        monkeypatch.setattr(cf.Path, "exists", lambda self: True)
        rc = cf.main(["--bead", "proj-aa11", "--branch", "feat/x",
                      "--pr-title", "t", "--pr-body-file", "f"])
        assert rc == cf.EXIT_OK
        assert any("bd_safe" in j and "close" in j for j in rec.joined())

    def test_closes_each_bead_when_flagged(self):
        rec = RunRecorder(responses={"pr create": (0, "https://github.com/o/r/pull/7", "")})
        job = _job(rec, close_beads=True,
                   bead=["proj-aa11", "proj-bb22"])
        job.run()
        closes = [j for j in rec.joined() if "bd_safe" in j and "close" in j]
        assert len(closes) == 2
        assert any("proj-aa11" in j for j in closes)
        assert any("proj-bb22" in j for j in closes)
        assert job.out["beads_closed"] == "proj-aa11,proj-bb22"


# --------------------------------------------------------------------------- #
# --close-only (recovery tool) -- closes the bead and nothing else
# --------------------------------------------------------------------------- #
class TestCloseOnly:
    def test_closes_bead_and_does_nothing_else(self):
        # --close-only is a pure recovery tool: it closes the bead and performs
        # NO other side effect (no PR / commit / push / rebase).
        rec = RunRecorder()
        job = _job(rec, close_only=True, close_beads=True, bead=["proj-aa11"])
        assert job.run() == cf.EXIT_OK
        joined = rec.joined()
        # bead WAS closed
        assert any("bd_safe" in j and "close" in j for j in joined)
        # and no PR/commit/push/rebase happened
        assert not any("pr create" in j or "commit" in j or "push" in j
                       or "pull --rebase" in j for j in joined)
        assert job.out["RESULT"] == "CLOSED-ONLY"

    def test_close_only_dry_run_makes_no_calls(self, capsys):
        # --close-only --dry-run must make ZERO subprocess calls (fresh-eyes
        # Finding 4 -- guards against a future regression adding one).
        rec = RunRecorder()
        job = _job(rec, close_only=True, close_beads=True, dry_run=True)
        assert job.run() == cf.EXIT_OK
        assert len(rec.calls) == 0, rec.joined()
        out = capsys.readouterr().out
        assert "close-only" in out and "RESULT: DRY-RUN" in out

    def test_close_only_closes_even_without_close_beads_flag(self):
        # Defensive: a programmatic caller setting close_only but NOT close_beads
        # must still close (not silently no-op) -- fresh-eyes Finding 2.
        rec = RunRecorder()
        job = _job(rec, close_only=True, close_beads=False, bead=["proj-aa11"])
        assert job.run() == cf.EXIT_OK
        assert any("bd_safe" in j and "close" in j for j in rec.joined())
        assert job.out["beads_closed"] == "proj-aa11"

    def test_main_close_only_needs_no_pr_flags(self, monkeypatch):
        # --close-only must parse + run WITHOUT --branch/--pr-title/--pr-body-file
        # or a review gate (they're only required for a PR-opening run).
        rec = RunRecorder()
        monkeypatch.setattr(cf, "_run", rec)
        monkeypatch.setattr(cf, "resolve_roots", lambda: (FAKE_R, FAKE_WT))
        monkeypatch.setattr(cf, "venv_python", lambda R: FAKE_PY)
        monkeypatch.setattr(cf.Path, "exists", lambda self: True)
        rc = cf.main(["--bead", "proj-aa11", "--close-only"])
        assert rc == cf.EXIT_OK
        assert any("bd_safe" in j and "close" in j for j in rec.joined())

    def test_main_pr_run_still_requires_flags(self, monkeypatch):
        # A NON-close-only run with the PR flags omitted must fail precondition.
        rec = RunRecorder()
        monkeypatch.setattr(cf, "_run", rec)
        monkeypatch.setattr(cf, "resolve_roots", lambda: (FAKE_R, FAKE_WT))
        monkeypatch.setattr(cf, "venv_python", lambda R: FAKE_PY)
        monkeypatch.setattr(cf.Path, "exists", lambda self: True)
        rc = cf.main(["--bead", "proj-aa11"])  # no --branch etc.
        assert rc == cf.EXIT_PRECONDITION


# --------------------------------------------------------------------------- #
# main(): branch-mismatch precondition
# --------------------------------------------------------------------------- #
class TestBranchMismatch:
    def test_branch_arg_must_match_checkout(self, monkeypatch):
        rec = RunRecorder(responses={"rev-parse --abbrev-ref": (0, "other-branch", "")})
        monkeypatch.setattr(cf, "_run", rec)
        monkeypatch.setattr(cf, "resolve_roots", lambda: (FAKE_R, FAKE_WT))
        monkeypatch.setattr(cf, "venv_python", lambda R: FAKE_PY)
        monkeypatch.setattr(cf.Path, "exists", lambda self: True)
        rc = cf.main(["--bead", "proj-aa11", "--branch", "feat/x",
                      "--pr-title", "t", "--pr-body-file", "f"])
        assert rc == cf.EXIT_PRECONDITION

    def test_fails_closed_when_branch_unreadable(self, monkeypatch):
        # If `git rev-parse` yields no branch, FAIL (don't silently skip the
        # guard and push blindly) -- fresh-eyes Finding 4.
        rec = RunRecorder(responses={"rev-parse --abbrev-ref": (0, "", "")})
        monkeypatch.setattr(cf, "_run", rec)
        monkeypatch.setattr(cf, "resolve_roots", lambda: (FAKE_R, FAKE_WT))
        monkeypatch.setattr(cf, "venv_python", lambda R: FAKE_PY)
        monkeypatch.setattr(cf.Path, "exists", lambda self: True)
        rc = cf.main(["--bead", "proj-aa11", "--branch", "feat/x",
                      "--pr-title", "t", "--pr-body-file", "f"])
        assert rc == cf.EXIT_PRECONDITION

    def test_dry_run_skips_branch_guard(self, monkeypatch):
        # --dry-run is a rehearsal: a branch mismatch must NOT block the preview
        # (fresh-eyes Finding 5). It should print the plan and exit 0.
        rec = RunRecorder(responses={"rev-parse --abbrev-ref": (0, "other", ""),
                                     "--dry-run": (0, "{}", "")})
        monkeypatch.setattr(cf, "_run", rec)
        monkeypatch.setattr(cf, "resolve_roots", lambda: (FAKE_R, FAKE_WT))
        monkeypatch.setattr(cf, "venv_python", lambda R: FAKE_PY)
        monkeypatch.setattr(cf.Path, "exists", lambda self: True)
        rc = cf.main(["--bead", "proj-aa11", "--branch", "feat/x",
                      "--pr-title", "t", "--pr-body-file", "f",
                      "--dry-run"])
        assert rc == cf.EXIT_OK
        # the branch guard's rev-parse must NOT have run under dry-run
        assert not any("rev-parse --abbrev-ref" in j for j in rec.joined())
