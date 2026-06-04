"""Tests for scripts/harness_ledger.py (bd polyglot-pdf-hrn.1).

These pin the parts the plan's verification section calls out:
  - parsed token totals, split orchestrator-vs-subagent (the isSidechain flag)
    and by model;
  - cost_category bucketing carried onto the row;
  - provenance tagging (the arm A/B/C/BC on the row + counter bump);
  - experiment-counter transitions A -> B/C -> BC -> report and the matching
    phase directive at each threshold;
  - transcript discovery from a sanitized cwd, and graceful failure when no
    transcript exists.

Run with the backend venv (the worktree has no venv of its own):
  PYTHONPATH=. backend/.venv/Scripts/python.exe -m pytest tests/test_harness_ledger.py
"""
import importlib.util
import json
import pathlib
import sys

import pytest


# Load the script as a module without running its CLI main() -- same pattern
# as tests/test_doc_freshness.py.
SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "harness_ledger.py"
)
spec = importlib.util.spec_from_file_location("harness_ledger", SCRIPT_PATH)
ledger = importlib.util.module_from_spec(spec)
sys.modules["harness_ledger"] = ledger
spec.loader.exec_module(ledger)


def _assistant(usage, *, model="claude-opus-4-8", sidechain=False, ts="2026-06-01T00:00:00Z"):
    """Build one assistant transcript record with the given usage."""
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "sessionId": "sess-fixture",
        "timestamp": ts,
        "message": {"model": model, "usage": usage},
    }


def _usage(inp=0, out=0, cr=0, cc=0):
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": cr,
        "cache_creation_input_tokens": cc,
    }


def _write_transcript(tmp_path, records):
    p = tmp_path / "session.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


# --------------------------------------------------------------------------- #
# Transcript parsing
# --------------------------------------------------------------------------- #
class TestParseTranscript:
    def test_actor_split_orchestrator_vs_subagent(self, tmp_path):
        """isSidechain routes tokens to the subagent bucket; absent/false -> orchestrator."""
        records = [
            _assistant(_usage(inp=100, out=10), sidechain=False, ts="2026-06-01T00:00:01Z"),
            _assistant(_usage(inp=200, out=20), sidechain=True, model="claude-haiku-4-5", ts="2026-06-01T00:00:02Z"),
            # A record with no isSidechain key at all counts as orchestrator.
            {"type": "assistant", "sessionId": "sess-fixture", "timestamp": "2026-06-01T00:00:03Z",
             "message": {"model": "claude-opus-4-8", "usage": _usage(inp=50, out=5)}},
        ]
        t = _write_transcript(tmp_path, records)
        parsed = ledger.parse_transcript(t)

        assert parsed["session_id"] == "sess-fixture"
        assert parsed["tokens"]["orchestrator"]["input_tokens"] == 150
        assert parsed["tokens"]["orchestrator"]["output_tokens"] == 15
        assert parsed["tokens"]["subagent"]["input_tokens"] == 200
        assert parsed["tokens"]["subagent"]["output_tokens"] == 20
        assert parsed["tokens"]["total"]["input_tokens"] == 350
        assert parsed["tokens"]["total"]["output_tokens"] == 35  # 10 + 20 + 5
        assert parsed["assistant_turns"] == {"orchestrator": 2, "subagent": 1}

    def test_per_model_breakdown_and_subagent_models(self, tmp_path):
        """The subagent model list is the arm-B / Haiku-escalation signal."""
        records = [
            _assistant(_usage(inp=10), sidechain=True, model="claude-haiku-4-5"),
            _assistant(_usage(inp=20), sidechain=True, model="claude-sonnet-4-6"),
            _assistant(_usage(inp=30), sidechain=False, model="claude-opus-4-8"),
        ]
        t = _write_transcript(tmp_path, records)
        parsed = ledger.parse_transcript(t)

        assert ledger.subagent_models(parsed) == ["claude-haiku-4-5", "claude-sonnet-4-6"]
        assert parsed["models"]["subagent"]["claude-haiku-4-5"]["input_tokens"] == 10
        assert parsed["models"]["orchestrator"]["claude-opus-4-8"]["input_tokens"] == 30

    def test_wall_clock_span(self, tmp_path):
        records = [
            {"type": "user", "sessionId": "sess-fixture", "timestamp": "2026-06-01T00:00:00Z"},
            _assistant(_usage(inp=1), ts="2026-06-01T00:05:00Z"),
            {"type": "user", "sessionId": "sess-fixture", "timestamp": "2026-06-01T00:10:00Z"},
        ]
        t = _write_transcript(tmp_path, records)
        parsed = ledger.parse_transcript(t)
        assert parsed["first_ts"] == "2026-06-01T00:00:00Z"
        assert parsed["last_ts"] == "2026-06-01T00:10:00Z"

    def test_cache_tokens_tracked_separately(self, tmp_path):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1, cr=999, cc=888))])
        parsed = ledger.parse_transcript(t)
        assert parsed["tokens"]["total"]["cache_read_input_tokens"] == 999
        assert parsed["tokens"]["total"]["cache_creation_input_tokens"] == 888

    def test_malformed_and_usageless_lines_skipped(self, tmp_path):
        p = tmp_path / "session.jsonl"
        with p.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_assistant(_usage(inp=5))) + "\n")
            f.write("{not valid json\n")  # malformed -- skipped, not fatal
            f.write(json.dumps({"type": "assistant", "message": {"model": "x"}}) + "\n")  # no usage
            f.write("\n")  # blank
        parsed = ledger.parse_transcript(p)
        assert parsed["tokens"]["total"]["input_tokens"] == 5
        assert parsed["assistant_turns"]["orchestrator"] == 1


# --------------------------------------------------------------------------- #
# Transcript discovery
# --------------------------------------------------------------------------- #
class TestDiscovery:
    def test_sanitize_cwd_matches_claude_rule(self):
        # Non-alphanumerics -> '-'. Verified against this repo's real dir name.
        assert ledger.sanitize_cwd(r"C:\Users\me\proj") == "C--Users-me-proj"
        assert ledger.sanitize_cwd("/home/me/a.b") == "-home-me-a-b"

    def test_discover_picks_newest_jsonl(self, tmp_path, monkeypatch):
        cwd = "/fake/work/dir"
        project_dir = tmp_path / "projects" / ledger.sanitize_cwd(cwd)
        project_dir.mkdir(parents=True)
        old = project_dir / "old.jsonl"
        new = project_dir / "new.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        new.write_text("{}\n", encoding="utf-8")
        # Force a clear mtime ordering (old < new).
        import os
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))
        monkeypatch.setattr(ledger, "claude_projects_dir", lambda: tmp_path / "projects")
        found = ledger.discover_transcript(cwd=cwd)
        assert found == new

    def test_discover_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ledger, "claude_projects_dir", lambda: tmp_path / "projects")
        assert ledger.discover_transcript(cwd="/no/such/dir") is None


# --------------------------------------------------------------------------- #
# Row assembly (provenance + cost_category)
# --------------------------------------------------------------------------- #
class TestBuildRow:
    def test_row_carries_provenance_and_cost_category(self, tmp_path):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1, out=1))])
        parsed = ledger.parse_transcript(t)
        args = ledger.build_parser().parse_args([
            "--bead", "polyglot-pdf-hrn.1", "--bead", "polyglot-pdf-hrn.2",
            "--arm", "BC", "--cost-category", "audit",
            "--copilot-rounds", "2", "--deferred-nits", "3",
        ])
        row = ledger.build_row(parsed, args, recorded_at="2026-06-01T00:00:00Z")
        assert row["beads"] == ["polyglot-pdf-hrn.1", "polyglot-pdf-hrn.2"]
        assert row["arm"] == "BC"
        assert row["cost_category"] == "audit"
        assert row["copilot_rounds"] == 2
        assert row["deferred_nits"] == 3
        assert row["recorded_at"] == "2026-06-01T00:00:00Z"

    def test_cost_category_defaults_to_production(self, tmp_path):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        parsed = ledger.parse_transcript(t)
        args = ledger.build_parser().parse_args([])
        row = ledger.build_row(parsed, args, recorded_at="x")
        assert row["cost_category"] == "production"

    def test_phase_tokens_parsed_from_json(self, tmp_path):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        parsed = ledger.parse_transcript(t)
        args = ledger.build_parser().parse_args(["--phase-tokens", '{"review": {"input_tokens": 9}}'])
        row = ledger.build_row(parsed, args, recorded_at="x")
        assert row["phase_tokens"] == {"review": {"input_tokens": 9}}

    def test_phase_tokens_bad_json_raises(self, tmp_path):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        parsed = ledger.parse_transcript(t)
        args = ledger.build_parser().parse_args(["--phase-tokens", "{not json"])
        with pytest.raises(SystemExit):
            ledger.build_row(parsed, args, recorded_at="x")


# --------------------------------------------------------------------------- #
# Append
# --------------------------------------------------------------------------- #
class TestAppendRow:
    def test_append_creates_and_appends(self, tmp_path):
        ledger_path = tmp_path / "nested" / "harness_ledger.jsonl"
        ledger.append_row({"a": 1}, ledger_path)
        ledger.append_row({"b": 2}, ledger_path)
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        assert [json.loads(l) for l in lines] == [{"a": 1}, {"b": 2}]


# --------------------------------------------------------------------------- #
# Experiment counter + directives
# --------------------------------------------------------------------------- #
def _write_ledger(path, arms):
    """Write a ledger JSONL with one row per entry in `arms` (each an arm value
    or None). Only the `arm` field matters for derive_experiment_state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for a in arms:
            f.write(json.dumps({"arm": a}) + "\n")


class TestExperimentState:
    def test_load_default_when_absent(self, tmp_path):
        state = ledger.load_experiment_state(tmp_path / "nope.json")
        assert state == {"baseline_A": 0, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}

    def test_derive_counts_rows_by_arm(self, tmp_path):
        # The counter is now a projection of the ledger: count rows per arm.
        led = tmp_path / "harness_ledger.jsonl"
        _write_ledger(led, ["A", "A", "B", "BC"])
        state = ledger.derive_experiment_state(led)
        assert state["baseline_A"] == 2
        assert state["arm_B"] == 1
        assert state["arm_C"] == 0
        assert state["arm_BC"] == 1
        assert state["phase"] == "A"

    def test_derive_ignores_null_and_unknown_arm(self, tmp_path):
        # null / unknown arms count toward nothing (the old "no --arm doesn't
        # bump" behavior, now expressed as "no arm key matches").
        led = tmp_path / "harness_ledger.jsonl"
        _write_ledger(led, ["A", "A", None, "X"])
        state = ledger.derive_experiment_state(led)
        assert state["baseline_A"] == 2
        assert state["arm_B"] == state["arm_C"] == state["arm_BC"] == 0

    def test_derive_missing_ledger_returns_zeros(self, tmp_path):
        state = ledger.derive_experiment_state(tmp_path / "nope.jsonl")
        assert state == {"baseline_A": 0, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}

    def test_derive_skips_malformed_line(self, tmp_path):
        # A crashed write can leave a partial last line; it must not cost the
        # whole count (the same tolerance _iter_records gives the transcript).
        led = tmp_path / "harness_ledger.jsonl"
        led.write_text(
            json.dumps({"arm": "A"}) + "\n" + '{"arm": "A", partial',
            encoding="utf-8",
        )
        assert ledger.derive_experiment_state(led)["baseline_A"] == 1

    def test_derive_phase_thresholds(self, tmp_path):
        led = tmp_path / "harness_ledger.jsonl"
        # baseline_A > 15 -> BC-toggle.
        _write_ledger(led, ["A"] * 16)
        assert ledger.derive_experiment_state(led)["phase"] == "BC-toggle"
        # arm_B > 10 and arm_C > 10 -> BC.
        _write_ledger(led, ["A"] * 16 + ["B"] * 11 + ["C"] * 11)
        assert ledger.derive_experiment_state(led)["phase"] == "BC"
        # arm_BC > 10 -> report (most-advanced wins).
        _write_ledger(led, ["A"] * 16 + ["B"] * 11 + ["C"] * 11 + ["BC"] * 11)
        assert ledger.derive_experiment_state(led)["phase"] == "report"

    def test_refresh_writes_cache_matching_derived_counts(self, tmp_path):
        led = tmp_path / "harness_ledger.jsonl"
        cache = tmp_path / "experiment_state.json"
        _write_ledger(led, ["A", "A", "B"])
        state = ledger.refresh_experiment_state(led, cache)
        assert state["baseline_A"] == 2 and state["arm_B"] == 1
        # The cache file is written and matches the returned state.
        assert json.loads(cache.read_text(encoding="utf-8")) == state

    def test_phase_transitions_and_directives(self, tmp_path):
        # Phase A: baseline_A <= 15.
        s = {"baseline_A": 15, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}
        assert "Phase A (baseline)" in ledger.phase_directive(s)
        # baseline_A > 15 -> start B/C.
        s["baseline_A"] = 16
        assert "start B/C toggling" in ledger.phase_directive(s)
        # arm_B > 10 and arm_C > 10 -> report / maybe BC.
        s.update({"arm_B": 11, "arm_C": 11})
        assert "Independent arms done" in ledger.phase_directive(s)
        # arm_BC > 10 -> final report (most-advanced wins even with other counts high).
        s["arm_BC"] = 11
        assert "FINAL report" in ledger.phase_directive(s)


# --------------------------------------------------------------------------- #
# End-to-end CLI
# --------------------------------------------------------------------------- #
class TestMainCLI:
    def test_main_appends_and_derives_counter(self, tmp_path, monkeypatch):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=42, out=7))])
        ledger_path = tmp_path / "harness_ledger.jsonl"
        state_path = tmp_path / "experiment_state.json"
        monkeypatch.setattr(ledger, "LEDGER_PATH", ledger_path)
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", state_path)
        rc = ledger.main([
            "--transcript", str(t), "--bead", "polyglot-pdf-hrn.1",
            "--arm", "A", "--recorded-at", "2026-06-01T00:00:00Z",
        ])
        assert rc == 0
        row = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["tokens"]["total"]["input_tokens"] == 42
        assert row["beads"] == ["polyglot-pdf-hrn.1"]
        # The counter is DERIVED from the just-appended row (cache reflects it).
        assert json.loads(state_path.read_text(encoding="utf-8"))["baseline_A"] == 1
        assert ledger.derive_experiment_state(ledger_path)["baseline_A"] == 1

    def test_main_no_counter_skips_cache_refresh(self, tmp_path, monkeypatch):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        ledger_path = tmp_path / "harness_ledger.jsonl"
        state_path = tmp_path / "experiment_state.json"
        monkeypatch.setattr(ledger, "LEDGER_PATH", ledger_path)
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", state_path)
        rc = ledger.main(["--transcript", str(t), "--arm", "A", "--no-counter", "--recorded-at", "x"])
        assert rc == 0
        # --no-counter skips the cache write; the row is still appended, so the
        # count is recoverable by deriving from the ledger.
        assert not state_path.exists()
        assert ledger.derive_experiment_state(ledger_path)["baseline_A"] == 1

    def test_main_missing_transcript_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ledger, "claude_projects_dir", lambda: tmp_path / "projects")
        rc = ledger.main(["--recorded-at", "x"])
        assert rc == 1

    def test_main_dry_run_does_not_write(self, tmp_path, monkeypatch, capsys):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        ledger_path = tmp_path / "harness_ledger.jsonl"
        state_path = tmp_path / "experiment_state.json"
        monkeypatch.setattr(ledger, "LEDGER_PATH", ledger_path)
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", state_path)
        rc = ledger.main(["--transcript", str(t), "--arm", "A", "--dry-run", "--recorded-at", "x"])
        assert rc == 0
        assert not ledger_path.exists()
        assert not state_path.exists()

    def test_main_warns_when_arm_missing_but_counter_on(self, tmp_path, monkeypatch, capsys):
        # No --arm + no --no-counter: the row lands with arm=null and the
        # cache is refreshed but no arm is counted; a warning fires.
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        ledger_path = tmp_path / "harness_ledger.jsonl"
        state_path = tmp_path / "experiment_state.json"
        monkeypatch.setattr(ledger, "LEDGER_PATH", ledger_path)
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", state_path)
        rc = ledger.main(["--transcript", str(t), "--recorded-at", "x"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "no --arm given" in err
        row = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["arm"] is None
        # Cache refreshed, but the null-arm row counted toward nothing.
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state == {"baseline_A": 0, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}

    def test_main_print_directive_derives_without_cache(self, tmp_path, monkeypatch, capsys):
        # --print-directive must derive from the LEDGER on demand, working even
        # with the gitignored cache file absent. Point LEDGER_PATH at a missing
        # ledger -> all-zeros -> Phase A.
        monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "nope.jsonl")
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", tmp_path / "nope.json")
        rc = ledger.main(["--print-directive"])
        assert rc == 0
        assert "Phase A (baseline)" in capsys.readouterr().out
