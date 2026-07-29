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
import argparse
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

    def test_cache_creation_ttl_breakdown_is_parsed_off_the_record(self, tmp_path):
        """bd polyglot-pdf-aefl: the per-TTL split must be READ from the record.

        Real transcripts carry usage.cache_creation alongside the flat count;
        parse_transcript has to pick it up, or compute_cost silently falls back
        to the 5m rate and under-reports every 1h write by 37.5%.
        """
        usage = _usage(inp=5, cc=1000)
        usage["cache_creation"] = {
            "ephemeral_1h_input_tokens": 900,
            "ephemeral_5m_input_tokens": 100,
        }
        legacy = _usage(inp=5, cc=500)  # no breakdown -> stays unattributed
        t = _write_transcript(tmp_path, [
            _assistant(usage, model="claude-opus-5"),
            _assistant(legacy, model="claude-opus-5"),
        ])
        parsed = ledger.parse_transcript(t)
        m = parsed["models"]["orchestrator"]["claude-opus-5"]

        # The breakdown is a SPLIT of the flat field, never additive to it.
        assert m["cache_creation_input_tokens"] == 1500
        assert m["cache_creation_1h_input_tokens"] == 900
        assert m["cache_creation_5m_input_tokens"] == 100

        # 600 tokens are unattributed (the legacy record) -> "mixed", 5m-priced.
        c = ledger.compute_cost(parsed["models"])
        assert c["cache_write_ttl_source"] == "mixed"
        assert c["cache_write_tokens_1h"] == 900
        assert c["cache_write_tokens_5m"] == 600

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


def _write_subagent_sidecar(main_transcript, agent_id, records):
    """Write a subagents/agent-<id>.jsonl sidecar next to the main transcript,
    mirroring Claude Code's layout (<stem>/subagents/agent-<id>.jsonl)."""
    sub_dir = main_transcript.with_suffix("") / "subagents"
    sub_dir.mkdir(parents=True, exist_ok=True)
    p = sub_dir / f"agent-{agent_id}.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


class TestSubagentSidecars:
    """bd polyglot-pdf-17k: spawned-subagent tokens live in subagents/agent-*.jsonl,
    not as isSidechain rows in the main transcript, and must be folded in."""

    def test_subagent_sidecar_tokens_fold_into_subagent_bucket(self, tmp_path):
        # Main transcript: orchestrator only, NO subagent rows (the bug condition).
        main = _write_transcript(tmp_path, [
            _assistant(_usage(inp=100, out=10), sidechain=False),
        ])
        # Two spawned-subagent sidecars, each with isSidechain:true rows.
        _write_subagent_sidecar(main, "aaa111", [
            _assistant(_usage(inp=200, out=20), sidechain=True, model="claude-sonnet-4-6"),
        ])
        _write_subagent_sidecar(main, "bbb222", [
            _assistant(_usage(inp=300, out=30), sidechain=True, model="claude-haiku-4-5"),
        ])

        parsed = ledger.parse_transcript(main)

        # Orchestrator unchanged; subagent bucket now reflects BOTH sidecars.
        assert parsed["tokens"]["orchestrator"]["input_tokens"] == 100
        assert parsed["tokens"]["subagent"]["input_tokens"] == 500  # 200 + 300
        assert parsed["tokens"]["subagent"]["output_tokens"] == 50  # 20 + 30
        assert parsed["tokens"]["total"]["input_tokens"] == 600
        assert parsed["assistant_turns"]["subagent"] == 2
        # Per-model subagent breakdown (the arm-B signal) sees both models.
        assert ledger.subagent_models(parsed) == ["claude-haiku-4-5", "claude-sonnet-4-6"]

    def test_meta_stays_anchored_to_main_not_sidecars(self, tmp_path):
        # Main defines the session id + the wall-clock span.
        main = _write_transcript(tmp_path, [
            {"type": "user", "sessionId": "main-sess", "timestamp": "2026-06-01T00:00:00Z"},
            _assistant(_usage(inp=1), ts="2026-06-01T00:01:00Z"),
            {"type": "user", "sessionId": "main-sess", "timestamp": "2026-06-01T00:02:00Z"},
        ])
        # A sidecar with a DIFFERENT session id and timestamps OUTSIDE the main span.
        _write_subagent_sidecar(main, "ccc333", [
            {"type": "user", "sessionId": "sub-sess", "timestamp": "2025-01-01T00:00:00Z"},
            _assistant(_usage(inp=9), sidechain=True, ts="2030-12-31T23:59:59Z"),
        ])

        parsed = ledger.parse_transcript(main)

        # Session id + span come from MAIN only; the sidecar's id/timestamps are ignored.
        assert parsed["session_id"] == "main-sess"
        assert parsed["first_ts"] == "2026-06-01T00:00:00Z"
        assert parsed["last_ts"] == "2026-06-01T00:02:00Z"
        # But the sidecar's TOKENS are still counted...
        assert parsed["tokens"]["subagent"]["input_tokens"] == 9
        # ...and the orchestrator bucket is UNAFFECTED by the sidecar (the main-only
        # assistant record's 1 input token, nothing leaked from the sidecar).
        assert parsed["tokens"]["orchestrator"]["input_tokens"] == 1

    def test_sidecar_row_without_sidechain_flag_still_buckets_as_subagent(self, tmp_path):
        # A record in a subagents/ sidecar IS a subagent turn by definition. Even if
        # an assistant row there lacks isSidechain (unobserved today, but a format
        # assumption we must not depend on), it must NOT leak into orchestrator.
        main = _write_transcript(tmp_path, [
            _assistant(_usage(inp=100), sidechain=False),
        ])
        _write_subagent_sidecar(main, "ddd444", [
            # isSidechain absent/false on purpose:
            _assistant(_usage(inp=50, out=5), sidechain=False, model="claude-sonnet-4-6"),
        ])

        parsed = ledger.parse_transcript(main)

        assert parsed["tokens"]["orchestrator"]["input_tokens"] == 100  # NOT 150
        assert parsed["tokens"]["subagent"]["input_tokens"] == 50
        assert parsed["assistant_turns"]["subagent"] == 1

    def test_no_subagents_dir_is_fine(self, tmp_path):
        # A session that spawned no subagents has no sidecar dir -> subagent bucket 0.
        main = _write_transcript(tmp_path, [_assistant(_usage(inp=7), sidechain=False)])
        assert ledger.discover_subagent_transcripts(main) == []
        parsed = ledger.parse_transcript(main)
        assert parsed["tokens"]["subagent"]["input_tokens"] == 0
        assert parsed["tokens"]["orchestrator"]["input_tokens"] == 7


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
# Append (per-row file protocol)
# --------------------------------------------------------------------------- #
class TestAppendRow:
    def test_creates_unique_file_per_row(self, tmp_path):
        tdir = tmp_path / "telemetry"
        r1 = {"recorded_at": "2026-06-01T00:00:00Z", "session_id": "aabbccdd", "arm": "A"}
        r2 = {"recorded_at": "2026-06-02T00:00:00Z", "session_id": "eeff0011", "arm": "B"}
        p1 = ledger.append_row(r1, tdir)
        p2 = ledger.append_row(r2, tdir)
        assert p1 != p2
        assert json.loads(p1.read_text(encoding="utf-8")) == r1
        assert json.loads(p2.read_text(encoding="utf-8")) == r2

    def test_creates_directory_if_missing(self, tmp_path):
        tdir = tmp_path / "nested" / "telemetry"
        p = ledger.append_row({"recorded_at": "2026-06-01T00:00:00Z", "session_id": "x"}, tdir)
        assert p.exists()

    def test_filename_uses_hyphens_not_colons(self, tmp_path):
        tdir = tmp_path / "telemetry"
        p = ledger.append_row({"recorded_at": "2026-06-01T12:34:56Z", "session_id": "abcd1234"}, tdir)
        assert ":" not in p.name
        assert "2026-06-01T12-34-56Z" in p.name
        assert "abcd1234" in p.name


# --------------------------------------------------------------------------- #
# Experiment counter + directives
# --------------------------------------------------------------------------- #
def _write_telemetry(tdir, arms):
    """Write one JSON file per arm value into tdir (as per-row protocol).

    Each file gets a unique timestamp derived from its index.
    """
    tdir.mkdir(parents=True, exist_ok=True)
    for i, a in enumerate(arms):
        ts = "2026-06-01T00:00:{:02d}Z".format(i % 60)
        fname = "{}-{:08d}.json".format(ts.replace(":", "-"), i)
        (tdir / fname).write_text(
            json.dumps({"arm": a, "recorded_at": ts, "session_id": "{:08d}".format(i)}) + "\n",
            encoding="utf-8",
        )


def _write_legacy_ledger(path, arms):
    """Write a legacy JSONL ledger with one row per entry in arms."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for a in arms:
            f.write(json.dumps({"arm": a}) + "\n")


class TestExperimentState:
    def test_load_default_when_absent(self, tmp_path):
        state = ledger.load_experiment_state(tmp_path / "nope.json")
        assert state == {"baseline_A": 0, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}

    def test_derive_counts_rows_by_arm(self, tmp_path):
        tdir = tmp_path / "telemetry"
        no_legacy = tmp_path / "nope.jsonl"
        _write_telemetry(tdir, ["A", "A", "B", "BC"])
        state = ledger.derive_experiment_state(no_legacy, tdir)
        assert state["baseline_A"] == 2
        assert state["arm_B"] == 1
        assert state["arm_C"] == 0
        assert state["arm_BC"] == 1
        assert state["phase"] == "A"

    def test_derive_ignores_null_and_unknown_arm(self, tmp_path):
        tdir = tmp_path / "telemetry"
        no_legacy = tmp_path / "nope.jsonl"
        _write_telemetry(tdir, ["A", "A", None, "X"])
        state = ledger.derive_experiment_state(no_legacy, tdir)
        assert state["baseline_A"] == 2
        assert state["arm_B"] == state["arm_C"] == state["arm_BC"] == 0

    def test_derive_missing_both_returns_zeros(self, tmp_path):
        state = ledger.derive_experiment_state(tmp_path / "nope.jsonl", tmp_path / "nope_dir")
        assert state == {"baseline_A": 0, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}

    def test_derive_skips_malformed_file(self, tmp_path):
        tdir = tmp_path / "telemetry"
        tdir.mkdir()
        (tdir / "2026-06-01T00-00-00Z-good.json").write_text(
            json.dumps({"arm": "A"}) + "\n", encoding="utf-8"
        )
        (tdir / "2026-06-01T00-00-01Z-bad.json").write_text(
            '{"arm": "A", partial', encoding="utf-8"
        )
        assert ledger.derive_experiment_state(tmp_path / "nope.jsonl", tdir)["baseline_A"] == 1

    def test_derive_reads_legacy_jsonl_when_telemetry_dir_empty(self, tmp_path):
        # Backwards compat: when telemetry dir is absent/empty, the old JSONL counts.
        led = tmp_path / "harness_ledger.jsonl"
        _write_legacy_ledger(led, ["A", "B"])
        state = ledger.derive_experiment_state(led, tmp_path / "nope_dir")
        assert state["baseline_A"] == 1
        assert state["arm_B"] == 1

    def test_derive_deduplicates_migrated_rows(self, tmp_path):
        # No double-counting: rows present in BOTH per-file dir and legacy JSONL
        # (migrated rows) are only counted once via dedup on (recorded_at, session_id).
        led = tmp_path / "harness_ledger.jsonl"
        tdir = tmp_path / "telemetry"
        # Write an "A" row to legacy with a known key.
        ts = "2026-06-01T00:00:00Z"
        sid = "aabbccdd"
        row = {"arm": "A", "recorded_at": ts, "session_id": sid}
        led.parent.mkdir(parents=True, exist_ok=True)
        led.write_text(json.dumps(row) + "\n", encoding="utf-8")
        # Also write the same row to the per-file dir (as migration would have done).
        tdir.mkdir()
        fn = "{}-{}.json".format(ts.replace(":", "-"), sid[:8])
        (tdir / fn).write_text(json.dumps(row) + "\n", encoding="utf-8")
        # Write a NEW row in legacy only (pre-migration branch still in flight).
        new_row = {"arm": "B", "recorded_at": "2026-06-02T00:00:00Z", "session_id": "new00001"}
        led.write_text(json.dumps(row) + "\n" + json.dumps(new_row) + "\n", encoding="utf-8")
        state = ledger.derive_experiment_state(led, tdir)
        assert state["baseline_A"] == 1  # migrated row counted once (not twice)
        assert state["arm_B"] == 1       # new legacy-only row counted

    def test_derive_phase_thresholds(self, tmp_path):
        tdir = tmp_path / "telemetry"
        no_legacy = tmp_path / "nope.jsonl"
        # baseline_A > 15 -> BC-toggle.
        _write_telemetry(tdir, ["A"] * 16)
        assert ledger.derive_experiment_state(no_legacy, tdir)["phase"] == "BC-toggle"
        # arm_B > 10 and arm_C > 10 -> BC.
        _write_telemetry(tdir, ["A"] * 16 + ["B"] * 11 + ["C"] * 11)
        assert ledger.derive_experiment_state(no_legacy, tdir)["phase"] == "BC"
        # arm_BC > 10 -> report (most-advanced wins).
        _write_telemetry(tdir, ["A"] * 16 + ["B"] * 11 + ["C"] * 11 + ["BC"] * 11)
        assert ledger.derive_experiment_state(no_legacy, tdir)["phase"] == "report"

    def test_refresh_writes_cache_matching_derived_counts(self, tmp_path):
        tdir = tmp_path / "telemetry"
        no_legacy = tmp_path / "nope.jsonl"
        cache = tmp_path / "experiment_state.json"
        _write_telemetry(tdir, ["A", "A", "B"])
        state = ledger.refresh_experiment_state(no_legacy, cache, tdir)
        assert state["baseline_A"] == 2 and state["arm_B"] == 1
        # The cache file is written and matches the returned state.
        assert json.loads(cache.read_text(encoding="utf-8")) == state

    def test_phase_transitions_and_directives(self, tmp_path):
        # Isolate the threshold->directive mapping from the real REPORT_DONE
        # sentinel (which exists in the repo now that the experiment is closed):
        # point `sentinel` at a path that does not exist so the count-based
        # branches are exercised.
        no_sentinel = tmp_path / "REPORT_DONE_absent"
        d = lambda s: ledger.phase_directive(s, sentinel=no_sentinel)
        # Phase A: baseline_A <= 15.
        s = {"baseline_A": 15, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}
        assert "Phase A (baseline)" in d(s)
        # baseline_A > 15 -> start B/C.
        s["baseline_A"] = 16
        assert "start B/C toggling" in d(s)
        # arm_B > 10 and arm_C > 10 -> report / maybe BC.
        s.update({"arm_B": 11, "arm_C": 11})
        assert "Independent arms done" in d(s)
        # arm_BC > 10 -> final report (most-advanced wins even with other counts high).
        s["arm_BC"] = 11
        assert "FINAL report" in d(s)

    def test_report_done_sentinel_closes_experiment(self, tmp_path, monkeypatch):
        # With the sentinel present, the directive short-circuits regardless of
        # how high the arm counts are -- the write-the-report nag stops firing.
        s = {"baseline_A": 200, "arm_B": 11, "arm_C": 11, "arm_BC": 99, "phase": "report"}
        present = tmp_path / "REPORT_DONE"
        present.write_text("closed", encoding="utf-8")
        out = ledger.phase_directive(s, sentinel=present)
        assert "experiment CLOSED" in out
        assert "FINAL report" not in out
        # Default sentinel path is derived from a (monkeypatched) TELEMETRY_DIR at
        # call time, so a closed experiment dir short-circuits without an explicit arg.
        tdir = tmp_path / "telemetry"
        tdir.mkdir()
        (tdir / ledger.REPORT_DONE_FILENAME).write_text("closed", encoding="utf-8")
        monkeypatch.setattr(ledger, "TELEMETRY_DIR", tdir)
        assert "experiment CLOSED" in ledger.phase_directive(s)


# --------------------------------------------------------------------------- #
# End-to-end CLI
# --------------------------------------------------------------------------- #
class TestMainCLI:
    def test_main_writes_file_and_derives_counter(self, tmp_path, monkeypatch):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=42, out=7))])
        tdir = tmp_path / "telemetry"
        no_legacy = tmp_path / "nope.jsonl"
        state_path = tmp_path / "experiment_state.json"
        monkeypatch.setattr(ledger, "TELEMETRY_DIR", tdir)
        monkeypatch.setattr(ledger, "LEDGER_PATH", no_legacy)
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", state_path)
        rc = ledger.main([
            "--transcript", str(t), "--bead", "polyglot-pdf-hrn.1",
            "--arm", "A", "--recorded-at", "2026-06-01T00:00:00Z",
        ])
        assert rc == 0
        files = list(tdir.glob("*.json"))
        assert len(files) == 1
        row = json.loads(files[0].read_text(encoding="utf-8"))
        assert row["tokens"]["total"]["input_tokens"] == 42
        assert row["beads"] == ["polyglot-pdf-hrn.1"]
        # The counter is DERIVED from the just-written file.
        assert json.loads(state_path.read_text(encoding="utf-8"))["baseline_A"] == 1
        assert ledger.derive_experiment_state(no_legacy, tdir)["baseline_A"] == 1

    def test_main_prints_telemetry_file_line(self, tmp_path, monkeypatch, capsys):
        # closeout_finish.py relies on "TELEMETRY_FILE: <path>" being on stdout.
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        tdir = tmp_path / "telemetry"
        monkeypatch.setattr(ledger, "TELEMETRY_DIR", tdir)
        monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "nope.jsonl")
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", tmp_path / "state.json")
        rc = ledger.main(["--transcript", str(t), "--arm", "A", "--recorded-at", "2026-06-01T00:00:01Z"])
        assert rc == 0
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if l.startswith("TELEMETRY_FILE: ")]
        assert len(lines) == 1
        assert lines[0].endswith(".json")

    def test_main_counts_the_just_written_row(self, tmp_path, monkeypatch):
        # Pin the write-BEFORE-refresh ordering: with N existing rows, one more
        # closeout must show N+1 -- proving the new row is counted.
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        tdir = tmp_path / "telemetry"
        no_legacy = tmp_path / "nope.jsonl"
        state_path = tmp_path / "experiment_state.json"
        _write_telemetry(tdir, ["A", "A", "A"])  # N = 3 before this run
        monkeypatch.setattr(ledger, "TELEMETRY_DIR", tdir)
        monkeypatch.setattr(ledger, "LEDGER_PATH", no_legacy)
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", state_path)
        rc = ledger.main(["--transcript", str(t), "--arm", "A", "--recorded-at", "2026-06-02T00:00:00Z"])
        assert rc == 0
        assert json.loads(state_path.read_text(encoding="utf-8"))["baseline_A"] == 4

    def test_main_no_counter_skips_cache_refresh(self, tmp_path, monkeypatch):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        tdir = tmp_path / "telemetry"
        state_path = tmp_path / "experiment_state.json"
        monkeypatch.setattr(ledger, "TELEMETRY_DIR", tdir)
        monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "nope.jsonl")
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", state_path)
        rc = ledger.main(["--transcript", str(t), "--arm", "A", "--no-counter", "--recorded-at", "2026-06-01T00:00:02Z"])
        assert rc == 0
        # --no-counter skips the cache write; the row is still written, so the
        # count is recoverable by deriving from the telemetry dir.
        assert not state_path.exists()
        assert ledger.derive_experiment_state(tmp_path / "nope.jsonl", tdir)["baseline_A"] == 1

    def test_main_missing_transcript_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ledger, "claude_projects_dir", lambda: tmp_path / "projects")
        rc = ledger.main(["--recorded-at", "x"])
        assert rc == 1

    def test_main_dry_run_does_not_write(self, tmp_path, monkeypatch, capsys):
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        tdir = tmp_path / "telemetry"
        state_path = tmp_path / "experiment_state.json"
        monkeypatch.setattr(ledger, "TELEMETRY_DIR", tdir)
        monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "nope.jsonl")
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", state_path)
        rc = ledger.main(["--transcript", str(t), "--arm", "A", "--dry-run", "--recorded-at", "x"])
        assert rc == 0
        assert not tdir.exists()
        assert not state_path.exists()

    def test_main_warns_when_arm_missing_but_counter_on(self, tmp_path, monkeypatch, capsys):
        # No --arm + no --no-counter: the row lands with arm=null and the
        # cache is refreshed but no arm is counted; a warning fires.
        t = _write_transcript(tmp_path, [_assistant(_usage(inp=1))])
        tdir = tmp_path / "telemetry"
        state_path = tmp_path / "experiment_state.json"
        monkeypatch.setattr(ledger, "TELEMETRY_DIR", tdir)
        monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "nope.jsonl")
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", state_path)
        rc = ledger.main(["--transcript", str(t), "--recorded-at", "2026-06-01T00:00:03Z"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "no --arm given" in err
        files = list(tdir.glob("*.json"))
        assert len(files) == 1
        row = json.loads(files[0].read_text(encoding="utf-8"))
        assert row["arm"] is None
        # Cache refreshed, but the null-arm row counted toward nothing.
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state == {"baseline_A": 0, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}

    def test_main_print_directive_derives_without_cache(self, tmp_path, monkeypatch, capsys):
        # --print-directive must derive from all rows on demand, working even
        # with the gitignored cache file absent. Empty telemetry dir + no legacy
        # -> all-zeros -> Phase A.
        monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "nope.jsonl")
        monkeypatch.setattr(ledger, "TELEMETRY_DIR", tmp_path / "nope_dir")
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", tmp_path / "nope.json")
        rc = ledger.main(["--print-directive"])
        assert rc == 0
        assert "Phase A (baseline)" in capsys.readouterr().out

    def test_main_print_directive_reflects_telemetry_dir(self, tmp_path, monkeypatch, capsys):
        # A populated telemetry dir with NO cache file must drive the directive
        # past Phase A. The old code (reading the absent cache / legacy JSONL)
        # would still say "Phase A (baseline)"; only scanning the new dir advances it.
        tdir = tmp_path / "telemetry"
        _write_telemetry(tdir, ["A"] * 16)  # baseline_A=16 > 15 -> "Phase A done"
        monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "nope.jsonl")
        monkeypatch.setattr(ledger, "TELEMETRY_DIR", tdir)
        monkeypatch.setattr(ledger, "EXPERIMENT_STATE_PATH", tmp_path / "nope.json")
        rc = ledger.main(["--print-directive"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Phase A done" in out and "Phase A (baseline)" not in out


class TestCost:
    """USD cost computation from token counts (bd polyglot-pdf-cb6i)."""

    def test_known_vectors(self):
        # 1M output on opus = $25 exactly (output rate 25/MTok).
        c = ledger.compute_cost(
            {"orchestrator": {"claude-opus-4-8": {"output_tokens": 1_000_000}}}
        )
        assert c["total"] == 25.0
        assert c["orchestrator_total"] == 25.0
        assert c["subagent_total"] == 0.0

    def test_cache_read_priced_at_one_tenth_input(self):
        # 1M cache-read on haiku (input 1/MTok) = 1.0 * 0.1 = $0.10.
        c = ledger.compute_cost(
            {"subagent": {"claude-haiku-4-5": {"cache_read_input_tokens": 1_000_000}}}
        )
        assert c["total"] == 0.1

    def test_legacy_cache_write_without_ttl_breakdown_falls_back_to_5m(self):
        # A LEGACY record (flat cache_creation_input_tokens, no usage.cache_creation
        # breakdown) keeps its historical 1.25x pricing rather than being silently
        # re-priced upward: 1M on sonnet (input 3/MTok) = 3.0 * 1.25 = $3.75.
        c = ledger.compute_cost(
            {"orchestrator": {"claude-sonnet-4-6": {"cache_creation_input_tokens": 1_000_000}}}
        )
        assert c["total"] == 3.75
        assert c["cache_write_ttl_source"] == "assumed-5m"
        assert c["cache_write_tokens_5m"] == 1_000_000
        assert c["cache_write_tokens_1h"] == 0

    def test_1h_cache_write_priced_at_2x_input(self):
        # bd polyglot-pdf-aefl: 1-hour cache writes cost 2.0x the base input rate,
        # not 1.25x. MEASURED reality -- every cache write in recent transcripts is
        # ephemeral_1h. 1M on sonnet (input 3/MTok) = 3.0 * 2.0 = $6.00.
        c = ledger.compute_cost({"orchestrator": {"claude-sonnet-4-6": {
            "cache_creation_input_tokens": 1_000_000,
            "cache_creation_1h_input_tokens": 1_000_000,
        }}})
        assert c["total"] == 6.00
        assert c["cache_write_ttl_source"] == "measured"
        assert c["cache_write_tokens_1h"] == 1_000_000
        assert c["cache_write_tokens_5m"] == 0

    def test_5m_cache_write_priced_at_1_25x_input(self):
        # The other measured bucket: an explicit 5m write stays at 1.25x.
        c = ledger.compute_cost({"orchestrator": {"claude-sonnet-4-6": {
            "cache_creation_input_tokens": 1_000_000,
            "cache_creation_5m_input_tokens": 1_000_000,
        }}})
        assert c["total"] == 3.75
        assert c["cache_write_ttl_source"] == "measured"

    def test_mixed_ttl_buckets_price_independently(self):
        # A transcript with both kinds prices each at its own multiplier:
        # 1M @ 2.0x + 1M @ 1.25x on sonnet = 6.00 + 3.75 = $9.75.
        c = ledger.compute_cost({"orchestrator": {"claude-sonnet-4-6": {
            "cache_creation_input_tokens": 2_000_000,
            "cache_creation_1h_input_tokens": 1_000_000,
            "cache_creation_5m_input_tokens": 1_000_000,
        }}})
        assert c["total"] == 9.75
        assert c["cache_write_ttl_source"] == "measured"

    def test_partial_ttl_breakdown_routes_remainder_to_5m(self):
        # Defensive: if the breakdown accounts for only part of the flat total
        # (a TTL kind we do not model yet), the remainder must still be priced --
        # at the conservative 5m rate -- and the source flagged "mixed", never
        # silently dropped. 1M @ 2.0x + 1M unattributed @ 1.25x = $9.75.
        c = ledger.compute_cost({"orchestrator": {"claude-sonnet-4-6": {
            "cache_creation_input_tokens": 2_000_000,
            "cache_creation_1h_input_tokens": 1_000_000,
        }}})
        assert c["total"] == 9.75
        assert c["cache_write_ttl_source"] == "mixed"
        assert c["cache_write_tokens_5m"] == 1_000_000

    def test_dated_haiku_id_resolves_by_prefix(self):
        # The real transcript carries the dated id; it must resolve to the family.
        c = ledger.compute_cost(
            {"subagent": {"claude-haiku-4-5-20251001": {"input_tokens": 1_000_000}}}
        )
        assert c["total"] == 1.0  # haiku input rate 1/MTok
        assert "claude-haiku-4-5-20251001" in c["subagent"]
        assert c["unpriced_models"] == []

    def test_combined_all_token_kinds(self):
        # All four kinds on opus (in 5, out 25): uncached 1M*5 + out 1M*25 +
        # cache_read 1M*5*0.1 + cache_write 1M*5*1.25 = 5 + 25 + 0.5 + 6.25 = 36.75.
        c = ledger.compute_cost({"orchestrator": {"claude-opus-4-8": {
            "input_tokens": 1_000_000, "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
            "cache_creation_input_tokens": 1_000_000,
        }}})
        assert c["total"] == 36.75

    def test_active_4_5_models_are_priced_not_unpriced(self):
        # Opus/Sonnet 4.5 are still active; a session on them must be priced, not
        # dropped to $0 as unpriced (Codex PR #261). Dated ids resolve too.
        c = ledger.compute_cost({
            "orchestrator": {"claude-opus-4-5-20251101": {"output_tokens": 1_000_000}},
            "subagent": {"claude-sonnet-4-5": {"output_tokens": 1_000_000}},
        })
        assert c["orchestrator_total"] == 25.0  # opus output 25/MTok
        assert c["subagent_total"] == 15.0      # sonnet output 15/MTok
        assert c["unpriced_models"] == []

    def test_unknown_model_is_zero_and_flagged_not_crash(self):
        c = ledger.compute_cost(
            {"orchestrator": {"claude-mystery-9": {"output_tokens": 1_000_000}}}
        )
        assert c["total"] == 0.0
        assert c["orchestrator"]["claude-mystery-9"] == 0.0
        assert c["unpriced_models"] == ["claude-mystery-9"]

    def test_empty_or_none_models_safe(self):
        assert ledger.compute_cost(None)["total"] == 0.0
        assert ledger.compute_cost({})["total"] == 0.0

    def test_malformed_counts_dict_does_not_raise(self):
        # The warn-only promise must hold even for a malformed models dict (a
        # None actor value, or a None/non-dict counts entry) -- never AttributeError
        # (fresh-eyes finding). parse_transcript never produces these, but a
        # hand-crafted or future-schema row might.
        assert ledger.compute_cost({"orchestrator": None})["total"] == 0.0
        c = ledger.compute_cost({"orchestrator": {"claude-opus-4-8": None}})
        assert c["total"] == 0.0
        assert c["orchestrator"]["claude-opus-4-8"] == 0.0

    def test_build_row_includes_cost_usd_block(self):
        # build_row must carry a cost_usd block derived from parsed["models"].
        parsed = {
            "session_id": "s", "first_ts": None, "last_ts": None,
            "tokens": {}, "assistant_turns": {},
            "models": {"orchestrator": {"claude-opus-4-8": {"output_tokens": 1_000_000}}},
        }
        args = argparse.Namespace(
            bead=["polyglot-pdf-cb6i"], arm="A", cost_category="production",
            phase_tokens=None, copilot_rounds=0, maintainer_touchpoints=0,
            deferred_nits=0, haiku_escalations=0, errors_shipped=0,
        )
        row = ledger.build_row(parsed, args, recorded_at="2026-06-28T00:00:00Z")
        assert "cost_usd" in row
        assert row["cost_usd"]["total"] == 25.0
        assert row["cost_usd"]["by_model"]["claude-opus-4-8"] == 25.0
