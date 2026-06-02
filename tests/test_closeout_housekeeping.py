"""Tests for scripts/closeout_housekeeping.py.

Module-import + monkeypatched `_run` (repo precedent: test_pr_review_watcher.py).
Verifies the pull/push bracketing and the clean-vs-slip classification of the
two audits, with no real bd subprocess.
"""

import importlib.util
import pathlib
import subprocess
import sys

import pytest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts" / "closeout_housekeeping.py"
)
spec = importlib.util.spec_from_file_location("closeout_housekeeping", SCRIPT_PATH)
ch = importlib.util.module_from_spec(spec)
sys.modules["closeout_housekeeping"] = ch
spec.loader.exec_module(ch)


def _proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _Recorder:
    def __init__(self, orphans_out, stale_out):
        self.orphans_out = orphans_out
        self.stale_out = stale_out
        self.calls = []

    def __call__(self, cmd, *, check=True):
        self.calls.append(list(cmd))
        if cmd[:2] == ["bd", "orphans"]:
            return _proc(stdout=self.orphans_out)
        if cmd[:2] == ["bd", "stale"]:
            return _proc(stdout=self.stale_out)
        return _proc()  # dolt pull/push

    def ran(self, *tokens):
        return any(all(t in call for t in tokens) for call in self.calls)


# --- clean-marker classification ---

@pytest.mark.parametrize(
    "text,clean",
    [
        ("No orphaned issues found", True),
        ("No stale issues found (all active)", True),
        ("myproject-ab12 still open but closed in commits", False),
        ("", False),
        # A stale-bead row whose TITLE contains a clean-marker substring must
        # still classify as NOT clean -- the bead id on the row is the tell.
        ("myproject-cd34  Fix: no stale-date handling  in_progress", False),
        ("myproject-ef56  Ensure all active sessions expire", False),
        # A single-token-prefix id (my-project-gh78 also works) -- both match.
        ("my-project-gh78  all active sessions audit", False),
    ],
)
def test_audit_is_clean(text, clean):
    assert ch._audit_is_clean(text) is clean


# --- pull/push bracketing + exit-code contract ---

def test_clean_audits_exit_ok_and_bracket(monkeypatch, capsys):
    rec = _Recorder(
        orphans_out="No orphaned issues found",
        stale_out="No stale issues found (all active)",
    )
    monkeypatch.setattr(ch, "_run", rec)
    rc = ch.main([])
    assert rc == ch.EXIT_OK
    assert rec.ran("dolt", "pull")
    assert rec.ran("dolt", "push")
    assert rec.ran("bd", "orphans")
    assert rec.ran("bd", "stale", "in_progress")
    assert "CLEAN" in capsys.readouterr().out


def test_slip_found_exits_3(monkeypatch, capsys):
    rec = _Recorder(
        orphans_out="yourturn-group-abc closed-in-commit but OPEN",
        stale_out="No stale issues found (all active)",
    )
    monkeypatch.setattr(ch, "_run", rec)
    rc = ch.main([])
    assert rc == ch.EXIT_SLIP_FOUND
    assert "SLIP-FOUND" in capsys.readouterr().out


def test_pull_failure_exits_fail(monkeypatch):
    def boom(cmd, *, check=True):
        if cmd[:3] == ["bd", "dolt", "pull"]:
            raise RuntimeError("dolt remote unreachable")
        return _proc()
    monkeypatch.setattr(ch, "_run", boom)
    assert ch.main([]) == ch.EXIT_FAIL


def test_stale_days_threaded_through(monkeypatch):
    rec = _Recorder("No orphaned issues", "No stale issues (all active)")
    monkeypatch.setattr(ch, "_run", rec)
    ch.main(["--stale-days", "3"])
    assert rec.ran("bd", "stale", "-d", "3")


def test_push_failure_preserves_audit_output(monkeypatch, capsys):
    # A failing final `bd dolt push` must NOT discard the already-captured
    # audit output, and must not flip the verdict.
    def run(cmd, *, check=True):
        if cmd[:2] == ["bd", "orphans"]:
            return _proc(stdout="No orphaned issues found")
        if cmd[:2] == ["bd", "stale"]:
            return _proc(stdout="No stale issues found (all active)")
        if cmd[:3] == ["bd", "dolt", "push"]:
            raise RuntimeError("dolt remote unreachable")
        return _proc()  # pull
    monkeypatch.setattr(ch, "_run", run)
    rc = ch.main([])
    out = capsys.readouterr().out
    assert "No orphaned issues found" in out  # audit printed despite push fail
    assert "WARNING" in out and "push" in out
    assert rc == ch.EXIT_OK  # verdict still CLEAN; push is not part of it
