"""Tests for scripts/closeout_finish.py (bd polyglot-pdf-hrn.13).

Pins the safety-critical contract of the closeout glue script:
  - the CLI gate: exactly one of --review-worthy/--skip-review (argparse
    mutually-exclusive + required);
  - --dry-run performs ZERO mutating subprocess calls (the highest-value test --
    it pins the "preview has no side effects" promise);
  - worktree safety: every git call is `git -C <WT>`; no `git add` ever;
  - review-worthy opens the PR, posts the trigger as a COMMENT (never the body),
    captures TS, and prints the watch command; skip-review does none of that;
  - a rebase conflict aborts the rebase and exits REBASE-CONFLICT (4);
  - telemetry is warn-only (a ledger failure does not change the exit code);
  - --close-beads gates the bd close calls (0 without, N with).

All git/gh/bd/ledger calls go through closeout_finish._run, so the tests stub
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
        review_worthy=False, skip_review=True, commit_message=None,
        arm="A", cost_category="production", copilot_rounds=0,
        maintainer_touchpoints=0, deferred_nits=0, haiku_escalations=0,
        errors_shipped=0, close_beads=False, close_only=False, dry_run=False,
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
    def test_requires_a_review_flag(self, monkeypatch):
        # A PR-opening run (not --close-only) with neither review flag must fail
        # the precondition check in main() (the gate moved from argparse to main()
        # so --close-only can omit it).
        rec = RunRecorder()
        monkeypatch.setattr(cf, "_run", rec)
        monkeypatch.setattr(cf, "resolve_roots", lambda: (FAKE_R, FAKE_WT))
        monkeypatch.setattr(cf, "venv_python", lambda R: FAKE_PY)
        monkeypatch.setattr(cf.Path, "exists", lambda self: True)
        rc = cf.main(["--bead", "x", "--branch", "b", "--pr-title", "t",
                      "--pr-body-file", "f"])
        assert rc == cf.EXIT_PRECONDITION

    def test_review_flags_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            cf.build_parser().parse_args(
                ["--bead", "x", "--branch", "b", "--pr-title", "t",
                 "--pr-body-file", "f", "--review-worthy", "--skip-review"])

    def test_skip_review_parses(self):
        ns = cf.build_parser().parse_args(
            ["--bead", "x", "--branch", "b", "--pr-title", "t",
             "--pr-body-file", "f", "--skip-review"])
        assert ns.skip_review and not ns.review_worthy

    def test_bead_repeatable(self):
        ns = cf.build_parser().parse_args(
            ["--bead", "x", "--bead", "y", "--branch", "b", "--pr-title", "t",
             "--pr-body-file", "f", "--skip-review"])
        assert ns.bead == ["x", "y"]


# --------------------------------------------------------------------------- #
# --dry-run: ZERO mutating calls (the headline safety property)
# --------------------------------------------------------------------------- #
class TestDryRun:
    def test_no_mutating_calls(self, capsys):
        rec = RunRecorder()
        job = _job(rec, dry_run=True, review_worthy=True, skip_review=False,
                   commit_message="c")
        assert job.run() == cf.EXIT_OK
        # The ledger preview MUST have run (else the test passes vacuously with
        # zero calls -- the Finding-7 gap).
        assert len(rec.calls) >= 1, "dry-run made no subprocess call at all"
        # The ONLY allowed subprocess in dry-run is the ledger's own --dry-run.
        assert all("--dry-run" in j for j in rec.joined()), rec.joined()
        for joined in rec.joined():
            assert "commit" not in joined and "push" not in joined
            assert "pr create" not in joined and "gh api" not in joined
            assert "bd_safe" not in joined
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
# Review-worthy vs skip-review
# --------------------------------------------------------------------------- #
class TestReviewWorthy:
    def test_opens_triggers_and_captures_ts(self, capsys):
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/42", ""),
            "gh api": (0, "2026-06-02T12:00:00Z", ""),
        })
        job = _job(rec, review_worthy=True, skip_review=False)
        assert job.run() == cf.EXIT_OK
        assert job.out["PR"] == "42"
        assert job.out["TS"] == "2026-06-02T12:00:00Z"
        # trigger posted as a COMMENT via gh api, with the literal trigger body
        api = [j for j in rec.joined() if "gh api" in j]
        assert api and "issues/42/comments" in api[0]
        assert cf.COPILOT_TRIGGER in api[0]
        # watch command printed (in the output block), referencing the PR + since
        assert "pr_review_watcher.py" in job.out["WATCH_CMD"]
        assert "--since" in job.out["WATCH_CMD"] and "42" in job.out["WATCH_CMD"]
        assert job.out["RESULT"] == "OPENED-REVIEW"

    def test_trigger_never_in_pr_body(self):
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/42", ""),
            "gh api": (0, "2026-06-02T12:00:00Z", ""),
        })
        job = _job(rec, review_worthy=True, skip_review=False)
        job.run()
        # the create call uses --body-file (a path), never an inline body carrying
        # the trigger string.
        create = [j for j in rec.joined() if "pr create" in j][0]
        assert "--body-file" in create
        assert cf.COPILOT_TRIGGER not in create

    def test_pr_create_uses_bare_base_name(self):
        # gh pr create --base wants the branch NAME ('dev'), not 'origin/dev'.
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/42", ""),
            "gh api": (0, "2026-06-02T12:00:00Z", ""),
        })
        job = _job(rec, review_worthy=True, skip_review=False, base="origin/dev")
        job.run()
        create = [c for c in rec.calls if "create" in c][0]
        i = create.index("--base")
        assert create[i + 1] == "dev", create


class TestSkipReview:
    def test_no_trigger_no_watch(self):
        rec = RunRecorder(responses={"pr create": (0, "https://github.com/o/r/pull/7", "")})
        job = _job(rec, skip_review=True, review_worthy=False)
        assert job.run() == cf.EXIT_OK
        assert not any("gh api" in j for j in rec.joined())
        assert job.out["WATCH_CMD"] == "-"
        assert job.out["TS"] == "-"
        assert job.out["RESULT"] == "OPENED-NOREVIEW"


# --------------------------------------------------------------------------- #
# Rebase conflict
# --------------------------------------------------------------------------- #
class TestRebaseConflict:
    def test_aborts_and_signals(self):
        rec = RunRecorder(responses={
            "pull --rebase": (1, "CONFLICT (content): journal.md", ""),
        })
        job = _job(rec, skip_review=True, review_worthy=False)
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
                      "--pr-title", "t", "--pr-body-file", "f", "--skip-review"])
        assert rc == cf.EXIT_REBASE_CONFLICT


# --------------------------------------------------------------------------- #
# Telemetry warn-only
# --------------------------------------------------------------------------- #
class TestTelemetryWarnOnly:
    def test_ledger_failure_does_not_fail_run(self):
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/7", ""),
            "harness_ledger.py": (1, "", "could not find transcript"),
        })
        job = _job(rec, skip_review=True, review_worthy=False)
        assert job.run() == cf.EXIT_OK
        assert job.out["telemetry"].startswith("GAP")


# --------------------------------------------------------------------------- #
# Telemetry commit+push (bd polyglot-pdf-3yf): the ledger row is written AFTER
# the closeout commit+push, so a dedicated step must commit+push the two
# tool-owned files or the row is orphaned in the working tree.
# --------------------------------------------------------------------------- #
class TestTelemetryCommitPush:
    # The two files harness_ledger.py owns -- the status guard reports them dirty.
    _DIRTY_STATUS = (0, " M docs/journal/harness_ledger.jsonl\n M .beads/experiment_state.json", "")

    def test_commits_and_pushes_dirty_telemetry_files(self):
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/7", ""),
            "status --porcelain": self._DIRTY_STATUS,
        })
        job = _job(rec, skip_review=True, review_worthy=False)
        assert job.run() == cf.EXIT_OK
        # A commit naming BOTH telemetry files (by explicit path) happened.
        commits = [j for j in rec.joined() if "commit" in j and "harness_ledger.jsonl" in j]
        assert len(commits) == 1, rec.joined()
        assert ".beads/experiment_state.json" in commits[0]
        # The PR number is in the commit message.
        assert "PR #7" in commits[0]
        # A push followed it.
        assert any("push" in j and "feat/x" in j for j in rec.joined())
        assert "committed+pushed" in job.out["telemetry"]

    def test_noop_when_telemetry_clean(self):
        # If the ledger wrote nothing (GAP) / nothing is dirty, no commit/push.
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/7", ""),
            # status returns empty (recorder default) -> clean -> nothing to do
        })
        job = _job(rec, skip_review=True, review_worthy=False)
        job.run()
        # No telemetry-file commit happened.
        assert not any("commit" in j and "harness_ledger.jsonl" in j
                       for j in rec.joined())

    def test_uses_git_C_worktree_and_no_git_add(self):
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/7", ""),
            "status --porcelain": self._DIRTY_STATUS,
        })
        job = _job(rec, skip_review=True, review_worthy=False)
        job.run()
        # Every git call (incl. the new commit+push) is `git -C <WT>` and none use add.
        for cmd in rec.calls:
            if cmd and cmd[0] == "git":
                assert cmd[1] == "-C" and cmd[2] == str(FAKE_WT), cmd
                assert "add" not in " ".join(cmd), cmd

    def test_push_failure_is_warn_only(self):
        # A failed telemetry push must NOT fail the run (the PR is already open).
        rec = RunRecorder(responses={
            "pr create": (0, "https://github.com/o/r/pull/7", ""),
            "status --porcelain": self._DIRTY_STATUS,
            "push origin feat/x": (1, "", "remote rejected"),
        })
        job = _job(rec, skip_review=True, review_worthy=False)
        assert job.run() == cf.EXIT_OK
        assert "PUSH-FAILED" in job.out["telemetry"]

    def test_close_only_never_commits_telemetry(self):
        # --close-only returns before the telemetry steps -> no status/commit/push.
        rec = RunRecorder()
        job = _job(rec, close_only=True, close_beads=True, review_worthy=False,
                   skip_review=False, bead=["proj-aa11"])
        job.run()
        assert not any("status --porcelain" in j or "harness_ledger.jsonl" in j
                       for j in rec.joined())


# --------------------------------------------------------------------------- #
# Bead-close gating
# --------------------------------------------------------------------------- #
class TestCloseBeadsGated:
    def test_no_close_by_default(self):
        rec = RunRecorder(responses={"pr create": (0, "https://github.com/o/r/pull/7", "")})
        job = _job(rec, skip_review=True, review_worthy=False, close_beads=False)
        job.run()
        assert not any("bd_safe" in j and "close" in j for j in rec.joined())
        assert job.out["beads_closed"] == "-"

    def test_closes_each_bead_when_flagged(self):
        rec = RunRecorder(responses={"pr create": (0, "https://github.com/o/r/pull/7", "")})
        job = _job(rec, skip_review=True, review_worthy=False, close_beads=True,
                   bead=["proj-aa11", "proj-bb22"])
        job.run()
        closes = [j for j in rec.joined() if "bd_safe" in j and "close" in j]
        assert len(closes) == 2
        assert any("proj-aa11" in j for j in closes)
        assert any("proj-bb22" in j for j in closes)
        assert job.out["beads_closed"] == "proj-aa11,proj-bb22"


# --------------------------------------------------------------------------- #
# --close-only (the two-call second call) — must NOT write a telemetry row
# --------------------------------------------------------------------------- #
class TestCloseOnly:
    def test_closes_bead_and_writes_no_telemetry_row(self):
        # The whole point of hrn.15: --close-only closes the bead but does NOT
        # append a ledger row (the first call already did), so no double-count.
        rec = RunRecorder()
        job = _job(rec, close_only=True, close_beads=True, review_worthy=False,
                   skip_review=False, bead=["proj-aa11"])
        assert job.run() == cf.EXIT_OK
        joined = rec.joined()
        # bead WAS closed
        assert any("bd_safe" in j and "close" in j for j in joined)
        # but the ledger was NOT invoked (no duplicate telemetry row)
        assert not any("harness_ledger.py" in j for j in joined)
        # and no PR/commit/push/rebase happened
        assert not any("pr create" in j or "commit" in j or "push" in j
                       or "pull --rebase" in j for j in joined)
        assert job.out["RESULT"] == "CLOSED-ONLY"

    def test_close_only_dry_run_makes_no_calls(self, capsys):
        # --close-only --dry-run skips the ledger preview entirely (close-only
        # writes no row), so it must make ZERO subprocess calls (fresh-eyes
        # Finding 4 -- guards against a future regression adding one).
        rec = RunRecorder()
        job = _job(rec, close_only=True, close_beads=True, review_worthy=False,
                   skip_review=False, dry_run=True)
        assert job.run() == cf.EXIT_OK
        assert len(rec.calls) == 0, rec.joined()
        out = capsys.readouterr().out
        assert "close-only" in out and "RESULT: DRY-RUN" in out

    def test_close_only_closes_even_without_close_beads_flag(self):
        # Defensive: a programmatic caller setting close_only but NOT close_beads
        # must still close (not silently no-op) -- fresh-eyes Finding 2.
        rec = RunRecorder()
        job = _job(rec, close_only=True, close_beads=False, review_worthy=False,
                   skip_review=False, bead=["proj-aa11"])
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
        rc = cf.main(["--bead", "proj-aa11", "--skip-review"])  # no --branch etc.
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
                      "--pr-title", "t", "--pr-body-file", "f", "--skip-review"])
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
                      "--pr-title", "t", "--pr-body-file", "f", "--skip-review"])
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
                      "--pr-title", "t", "--pr-body-file", "f", "--skip-review",
                      "--dry-run"])
        assert rc == cf.EXIT_OK
        # the branch guard's rev-parse must NOT have run under dry-run
        assert not any("rev-parse --abbrev-ref" in j for j in rec.joined())
