"""Tests for scripts/next_bead.py (the R1 /next-bead engine, bd polyglot-pdf-h2r.1).

Imports both next_bead and its bd_safe dependency as modules (repo precedent:
test_bd_safe.py) and monkeypatches bd_safe._run so no bd/gh/git subprocess is
spawned. The behaviors under test: ready candidates are classified AVAILABLE vs
BLOCKED by change-surface overlap against ACTIVE claims, and the script never
claims/edits/merges.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
import types

import pytest


SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

# bd_safe first (next_bead imports it).
_bs_spec = importlib.util.spec_from_file_location("bd_safe", SCRIPTS / "bd_safe.py")
bs = importlib.util.module_from_spec(_bs_spec)
sys.modules["bd_safe"] = bs
_bs_spec.loader.exec_module(bs)

_nb_spec = importlib.util.spec_from_file_location("next_bead", SCRIPTS / "next_bead.py")
nb = importlib.util.module_from_spec(_nb_spec)
sys.modules["next_bead"] = nb
_nb_spec.loader.exec_module(nb)


def _proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _bead_json(surfaces):
    return json.dumps([{"id": "x", "metadata": {"surfaces": surfaces}}])


def _make_fake(ready, in_progress, surfaces_by_id, live_ids):
    """Build a bd_safe._run replacement.

    ready: list of candidate dicts for `bd ready --json`.
    in_progress: list of dicts for `bd list --status in_progress --json`.
    surfaces_by_id: {bead_id: [surfaces]} for `bd show <id> --json`.
    live_ids: set of ids that have an open PR (counted as live/active).
    """
    def fake(cmd, *, check=True):
        if cmd[:2] == ["bd", "dolt"]:
            return _proc()
        if cmd[:2] == ["bd", "ready"]:
            return _proc(stdout=json.dumps(ready))
        if cmd[:2] == ["bd", "list"]:
            return _proc(stdout=json.dumps(in_progress))
        if cmd[:2] == ["bd", "show"]:
            bead_id = cmd[2]
            return _proc(stdout=_bead_json(surfaces_by_id.get(bead_id, [])))
        if cmd[:3] == ["gh", "pr", "list"]:
            joined = " ".join(cmd)
            for lid in live_ids:
                if lid in joined:
                    return _proc(stdout=json.dumps(
                        [{"number": 1, "title": "x (bd {})".format(lid)}]))
            return _proc(stdout="[]")
        if cmd[:3] == ["git", "branch", "-a"]:
            return _proc(stdout="* dev")
        if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return _proc(stdout="dev")
        return _proc()
    return fake


def _run_next(monkeypatch, fake, quiet=True):
    monkeypatch.setattr(bs, "_run", fake)
    args = types.SimpleNamespace(no_pull=False, quiet=quiet, func=nb.cmd_next)
    rc = nb.cmd_next(args)
    return rc


def test_candidate_blocked_by_overlapping_active_claim(monkeypatch, capsys):
    fake = _make_fake(
        ready=[
            {"id": "p-aaa1", "title": "scripts work", "priority": 2},
            {"id": "p-ccc3", "title": "docs work", "priority": 3},
        ],
        in_progress=[{"id": "p-bbb2", "status": "in_progress"}],
        surfaces_by_id={
            "p-aaa1": ["scripts/"],
            "p-ccc3": ["docs/x.md"],
            "p-bbb2": ["scripts/foo.py"],   # overlaps aaa1, not ccc3
        },
        live_ids={"p-bbb2"},
    )
    rc = _run_next(monkeypatch, fake)
    assert rc == nb.EXIT_OK
    out = json.loads(capsys.readouterr().out)
    avail = {r["id"] for r in out["available"]}
    blocked = {r["id"] for r in out["blocked"]}
    assert avail == {"p-ccc3"}
    assert blocked == {"p-aaa1"}
    assert out["active_claims"] == ["p-bbb2"]
    # The blocking claim is recorded on the blocked row.
    aaa1 = next(r for r in out["blocked"] if r["id"] == "p-aaa1")
    assert aaa1["blocked_by"][0]["claim"] == "p-bbb2"


def test_stale_in_progress_claim_does_not_block(monkeypatch, capsys):
    # p-bbb2 is in_progress but has NO open PR and NO branch -> not active,
    # so it must NOT block the overlapping candidate.
    fake = _make_fake(
        ready=[{"id": "p-aaa1", "title": "scripts", "priority": 2}],
        in_progress=[{"id": "p-bbb2", "status": "in_progress"}],
        surfaces_by_id={"p-aaa1": ["scripts/"], "p-bbb2": ["scripts/foo.py"]},
        live_ids=set(),   # nothing live
    )
    rc = _run_next(monkeypatch, fake)
    assert rc == nb.EXIT_OK
    out = json.loads(capsys.readouterr().out)
    assert {r["id"] for r in out["available"]} == {"p-aaa1"}
    assert out["blocked"] == []
    assert out["active_claims"] == []


def test_undeclared_surfaces_candidate_not_blocked(monkeypatch, capsys):
    # bd polyglot-pdf-6hr: a candidate with NO declared surfaces is UNKNOWN, and
    # an empty surface set no longer collides -- so it is AVAILABLE, not blocked.
    # (Pre-6hr this was conservatively blocked by any active claim.) This is the
    # core fix: one undeclared in-progress bead must not freeze the whole board.
    fake = _make_fake(
        ready=[{"id": "p-aaa1", "title": "mystery", "priority": 2}],
        in_progress=[{"id": "p-bbb2", "status": "in_progress"}],
        surfaces_by_id={"p-aaa1": [], "p-bbb2": ["docs/only.md"]},
        live_ids={"p-bbb2"},
    )
    _run_next(monkeypatch, fake)
    out = json.loads(capsys.readouterr().out)
    assert {r["id"] for r in out["available"]} == {"p-aaa1"}
    assert out["blocked"] == []


def test_undeclared_active_claim_does_not_block_others(monkeypatch, capsys):
    # The akn case (bd polyglot-pdf-6hr): an ACTIVE claim with no declared
    # surfaces (and no derivable PR) must not block declared candidates.
    fake = _make_fake(
        ready=[
            {"id": "p-aaa1", "title": "frontend", "priority": 1},
            {"id": "p-ccc3", "title": "docs", "priority": 2},
        ],
        in_progress=[{"id": "p-bbb2", "status": "in_progress"}],
        surfaces_by_id={
            "p-aaa1": ["frontend/x.ts"],
            "p-ccc3": ["docs/y.md"],
            "p-bbb2": [],   # undeclared, no PR -> UNKNOWN, must not block
        },
        live_ids={"p-bbb2"},
    )
    _run_next(monkeypatch, fake)
    out = json.loads(capsys.readouterr().out)
    assert {r["id"] for r in out["available"]} == {"p-aaa1", "p-ccc3"}
    assert out["blocked"] == []


def test_no_active_claims_all_available(monkeypatch, capsys):
    fake = _make_fake(
        ready=[
            {"id": "p-aaa1", "title": "a", "priority": 1},
            {"id": "p-bbb2", "title": "b", "priority": 2},
        ],
        in_progress=[],
        surfaces_by_id={"p-aaa1": ["scripts/"], "p-bbb2": ["docs/"]},
        live_ids=set(),
    )
    _run_next(monkeypatch, fake)
    out = json.loads(capsys.readouterr().out)
    assert {r["id"] for r in out["available"]} == {"p-aaa1", "p-bbb2"}
    assert out["blocked"] == []


def test_next_bead_never_claims_or_writes(monkeypatch):
    calls = []
    base = _make_fake(
        ready=[{"id": "p-aaa1", "title": "a", "priority": 1}],
        in_progress=[],
        surfaces_by_id={"p-aaa1": ["scripts/"]},
        live_ids=set(),
    )
    def tracking(cmd, *, check=True):
        calls.append(list(cmd))
        return base(cmd, check=check)
    monkeypatch.setattr(bs, "_run", tracking)
    nb.cmd_next(types.SimpleNamespace(no_pull=False, quiet=True))
    # selection-only: never claims, never closes, never pushes, never merges.
    assert not any("--claim" in c for c in calls)
    assert not any(c[:2] == ["bd", "close"] for c in calls)
    assert not any("merge" in " ".join(c) for c in calls)
    assert not any(c[:2] == ["bd", "dolt"] and "push" in c for c in calls)


def test_no_pull_flag_skips_pull(monkeypatch):
    calls = []
    base = _make_fake(
        ready=[], in_progress=[], surfaces_by_id={}, live_ids=set()
    )
    def tracking(cmd, *, check=True):
        calls.append(list(cmd))
        return base(cmd, check=check)
    monkeypatch.setattr(bs, "_run", tracking)
    nb.cmd_next(types.SimpleNamespace(no_pull=True, quiet=True))
    assert not any(c[:2] == ["bd", "dolt"] and "pull" in c for c in calls)


def test_ready_failure_returns_fail(monkeypatch, capsys):
    def fake(cmd, *, check=True):
        if cmd[:2] == ["bd", "dolt"]:
            return _proc()
        if cmd[:2] == ["bd", "ready"]:
            return _proc(returncode=1, stderr="boom")
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    rc = nb.main(["--quiet"])
    assert rc == nb.EXIT_FAIL
    assert "ERROR" in capsys.readouterr().out
