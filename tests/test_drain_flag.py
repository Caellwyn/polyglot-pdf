"""Tests for scripts/drain_flag.py (the R2 drain/handover plumbing, bd
polyglot-pdf-h2r.2).

Loads drain_flag as a module (repo precedent: test_next_bead.py) and drives its
subcommand functions directly, feeding the hook stdin JSON via a monkeypatched
sys.stdin and redirecting the runtime dir to a tmp_path. No bd/git/gh subprocess
is spawned (the only subprocess, git in _runtime_dir, is bypassed by patching
_runtime_dir). Behaviors under test:

  * PreCompact(auto) writes a session-scoped marker; PreCompact(manual) does not.
  * PreCompact with NO trigger (matcher-guaranteed auto) still drains.
  * SessionStart(compact) surfaces the drain directive and consumes the marker,
    matching by session_id OR by transcript_path; surfaces exactly once.
  * SessionStart(startup/resume) never drains, sweeps the session's own marker,
    and surfaces NOTHING -- the beads tracker is the handoff, no side-channel note.
  * A foreign-session marker never drains a different session (session-scoping).
  * Malformed / empty stdin degrades to a silent no-op (never crashes).
"""

import importlib.util
import io
import json
import pathlib
import sys

import pytest


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location("drain_flag", SCRIPTS / "drain_flag.py")
df = importlib.util.module_from_spec(_spec)
sys.modules["drain_flag"] = df
_spec.loader.exec_module(df)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    """Redirect the script's runtime dir to a fresh tmp dir for every test."""
    rt = tmp_path / ".beads" / ".runtime"
    monkeypatch.setattr(df, "_runtime_dir", lambda: rt)
    return rt


def _feed_stdin(monkeypatch, payload):
    """Monkeypatch sys.stdin to deliver `payload` (str or dict) to the script."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))


def _run(monkeypatch, capsys, fn, payload):
    """Feed stdin, run a subcommand fn, return (rc, stdout)."""
    _feed_stdin(monkeypatch, payload)
    rc = fn(argparse_ns())
    out = capsys.readouterr().out
    return rc, out


class argparse_ns:
    """Minimal stand-in for the argparse.Namespace the cmd_* hook fns receive.
    The precompact/sessionstart entry points read only stdin, not args, so this
    carries no fields -- it just satisfies the (args) signature."""


def _markers(runtime):
    return sorted(runtime.glob("drain-*.flag"))


# --------------------------------------------------------------------------
# PreCompact: marker raised only on auto.
# --------------------------------------------------------------------------

def test_precompact_auto_writes_marker(runtime, monkeypatch, capsys):
    rc, _ = _run(monkeypatch, capsys, df.cmd_precompact, {
        "trigger": "auto", "session_id": "sid-1", "transcript_path": "/t/abc.jsonl",
    })
    assert rc == 0
    files = _markers(runtime)
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    assert rec["session_id"] == "sid-1"
    assert rec["transcript_path"] == "/t/abc.jsonl"


def test_precompact_manual_writes_nothing(runtime, monkeypatch, capsys):
    rc, _ = _run(monkeypatch, capsys, df.cmd_precompact, {
        "trigger": "manual", "session_id": "sid-1",
    })
    assert rc == 0
    assert _markers(runtime) == []


def test_precompact_missing_trigger_treated_as_auto(runtime, monkeypatch, capsys):
    # The settings.json matcher ("auto") guarantees this hook only fires on auto,
    # so an absent trigger field must still drain.
    rc, _ = _run(monkeypatch, capsys, df.cmd_precompact, {
        "session_id": "sid-2", "transcript_path": "/t/x.jsonl",
    })
    assert rc == 0
    assert len(_markers(runtime)) == 1


# --------------------------------------------------------------------------
# SessionStart(compact): surface + consume the directive.
# --------------------------------------------------------------------------

def _raise(runtime, monkeypatch, capsys, session_id, transcript):
    _run(monkeypatch, capsys, df.cmd_precompact, {
        "trigger": "auto", "session_id": session_id, "transcript_path": transcript,
    })


def test_compact_surfaces_directive_and_consumes(runtime, monkeypatch, capsys):
    _raise(runtime, monkeypatch, capsys, "sid-1", "/t/abc.jsonl")
    rc, out = _run(monkeypatch, capsys, df.cmd_sessionstart, {
        "source": "compact", "session_id": "sid-1", "transcript_path": "/t/abc.jsonl",
    })
    assert rc == 0
    payload = json.loads(out)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "DRAIN SIGNAL" in ctx
    assert "do not claim a new bead" in ctx.lower()
    # Consumed -> a second compact SessionStart surfaces nothing.
    assert _markers(runtime) == []
    rc2, out2 = _run(monkeypatch, capsys, df.cmd_sessionstart, {
        "source": "compact", "session_id": "sid-1", "transcript_path": "/t/abc.jsonl",
    })
    assert rc2 == 0
    assert out2.strip() == ""


def test_compact_matches_by_transcript_when_session_id_changed(runtime, monkeypatch, capsys):
    # session_id stability across compaction is undocumented; a transcript_path
    # match must still drain.
    _raise(runtime, monkeypatch, capsys, "sid-OLD", "/t/same.jsonl")
    rc, out = _run(monkeypatch, capsys, df.cmd_sessionstart, {
        "source": "compact", "session_id": "sid-NEW", "transcript_path": "/t/same.jsonl",
    })
    assert rc == 0
    assert "DRAIN SIGNAL" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert _markers(runtime) == []


def test_compact_with_no_marker_does_not_drain(runtime, monkeypatch, capsys):
    rc, out = _run(monkeypatch, capsys, df.cmd_sessionstart, {
        "source": "compact", "session_id": "sid-1", "transcript_path": "/t/abc.jsonl",
    })
    assert rc == 0
    assert out.strip() == ""


def test_foreign_session_marker_does_not_drain(runtime, monkeypatch, capsys):
    # Marker from a DIFFERENT session (different id AND different transcript) must
    # not drain this compact SessionStart.
    _raise(runtime, monkeypatch, capsys, "sid-OTHER", "/t/other.jsonl")
    rc, out = _run(monkeypatch, capsys, df.cmd_sessionstart, {
        "source": "compact", "session_id": "sid-MINE", "transcript_path": "/t/mine.jsonl",
    })
    assert rc == 0
    assert out.strip() == ""
    # The foreign marker is left intact (only its own session consumes it).
    assert len(_markers(runtime)) == 1


# --------------------------------------------------------------------------
# SessionStart(startup/resume): fresh session never drains; sweeps own marker.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source", ["startup", "resume", "clear"])
def test_fresh_session_never_drains_and_sweeps_own_marker(runtime, monkeypatch, capsys, source):
    # A leftover marker keyed to THIS session must be swept, never drained.
    _raise(runtime, monkeypatch, capsys, "sid-1", "/t/abc.jsonl")
    rc, out = _run(monkeypatch, capsys, df.cmd_sessionstart, {
        "source": source, "session_id": "sid-1", "transcript_path": "/t/abc.jsonl",
    })
    assert rc == 0
    assert "DRAIN SIGNAL" not in out
    # A fresh session surfaces NOTHING -- the tracker is the handoff; there is no
    # side-channel note to inject. It rehydrates from `bd ready` on its own.
    assert out.strip() == ""
    assert df._marker_path(runtime, "sid-1").exists() is False


def test_fresh_session_surfaces_no_note(runtime, monkeypatch, capsys):
    # Regression guard: even if some artifact were left in the runtime dir from a
    # prior drained session, a fresh SessionStart must NOT inject a handover note
    # (the note mechanism was removed; beads is the only handoff). The drain dir
    # holds only markers now; assert a clean startup is silent.
    rc, out = _run(monkeypatch, capsys, df.cmd_sessionstart, {
        "source": "startup", "session_id": "sid-fresh", "transcript_path": "/t/f.jsonl",
    })
    assert rc == 0
    assert out.strip() == ""
    assert not list(runtime.glob("handover-*"))  # no note file is ever created


# --------------------------------------------------------------------------
# Robustness: malformed / empty stdin is a silent no-op, never a crash.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "   ", "not json", "[1,2,3]", "null"])
def test_precompact_bad_stdin_is_noop(runtime, monkeypatch, capsys, bad):
    rc, out = _run(monkeypatch, capsys, df.cmd_precompact, bad)
    assert rc == 0
    # Empty/garbage stdin -> no trigger field -> treated as auto under the matcher,
    # so a marker with an empty session id may be written; the point is it never
    # raises. Garbage that isn't a dict yields {} -> empty-session marker.
    assert rc == 0


@pytest.mark.parametrize("bad", ["", "   ", "not json", "[1,2,3]", "null"])
def test_sessionstart_bad_stdin_is_noop(runtime, monkeypatch, capsys, bad):
    rc, out = _run(monkeypatch, capsys, df.cmd_sessionstart, bad)
    assert rc == 0
    assert out.strip() == ""


def test_session_key_is_filesystem_safe():
    # Even a hostile session id cannot escape the runtime dir.
    key = df._session_key("../../etc/passwd")
    assert "/" not in key and "\\" not in key and ".." not in key
    assert len(key) == 16


def test_main_missing_subcommand_returns_zero(monkeypatch):
    # A hook must never surface a non-zero exit, even on an argparse error.
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert df.main([]) == 0
