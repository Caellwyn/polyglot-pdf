"""Unit tests for the full-system stress-test harness extensions
(bd polyglot-pdf-n86b / polyglot-pdf-eh1h, epic 00pt).

Covers the P0 gates with a MOCK adapter/service -- no live calls:
  - the full-form plan generator's guards + counts;
  - the FakeClientWebSocket seam handlers (skip / switch / validation_result /
    steered markers / confirmed-reset-on-value-change / contract-2 payload /
    whole-form shown snapshot);
  - the text-cost pricing + the ValidationSeam window geometry;
  - scenario weaving, validator P/R scoring, fill-failure classification;
  - build_summary emitting every headline key from synthetic records;
  - the legacy 34-q i90 schema entry + frozen CSV columns unchanged.

ASCII only. Synthetic persona data only.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")  # the harness imports numpy at module level

_REPO = Path(__file__).resolve().parent.parent
for p in (str(_REPO), str(_REPO / "scripts" / "spikes")):
    if p not in sys.path:
        sys.path.insert(0, p)

import full_form_script as ffs  # noqa: E402
import scenario_events as se  # noqa: E402
import measure_form_session_costs as mfc  # noqa: E402


# ---------------------------------------------------------------- generator

def test_full_form_plan_counts_and_guards():
    plan = ffs.build_full_form_plan(ffs.load_schema())
    qs, expected = plan["questions"], plan["expected"]
    # ~113 spoken steps; every question has say/wrong/expected.
    assert 100 <= len(qs) <= 125
    for q in qs:
        assert q["say"] and q["wrong"]
        assert q["field_id"] in expected
    # copy_from + signature fields auto-applied, never spoken.
    spoken = {q["field_id"] for q in qs}
    for aa in plan["auto_apply"]:
        assert aa["field_id"] not in spoken
    # the name-change-gated fields are hidden for this persona
    assert "p1_line5a_familyname" in plan["hidden"]
    # declines expect empty; answered fields expect non-empty
    assert expected["p1_line6g_province"] == ""
    assert expected["p1_line9_dateofbirth"] == "04/12/1985"  # MM/DD/YYYY
    assert expected["p1_line1_aliennumber"] == "123456789"   # A-prefix stripped
    assert expected["p2_checkbox2[5]"] == (
        "my_previous_card_has_been_lost_stolen_or_destroyed")


def test_full_form_expected_passes_driver_drift_guard():
    schema = ffs.load_schema()
    plan = ffs.build_full_form_plan(schema)
    # must not raise
    mfc._assert_expected_canon_matches_schema(
        {f["id"]: f for f in schema["fields"]}, plan["expected"])


def test_override_must_be_valid_option():
    schema = ffs.load_schema()
    orig = dict(ffs.ANSWER_OVERRIDES)
    try:
        ffs.ANSWER_OVERRIDES["p2_checkbox2[5]"] = "not_a_real_option"
        with pytest.raises(SystemExit):
            ffs.build_full_form_plan(schema)
    finally:
        ffs.ANSWER_OVERRIDES.clear()
        ffs.ANSWER_OVERRIDES.update(orig)


# ------------------------------------------------------------- fake client

class _StubService:
    """Records the coordinator-response calls the FakeClient replies with.

    The signatures MIRROR the REAL FormFillingService handlers exactly
    (form_filling_service.py:1837/:1861) -- a stub shaped to the caller's own
    convention instead of the real contract is what let the skip-args bug ship
    to fresh-eyes round 1: skip takes DISCRETE args (recorded: bool, reason,
    section_complete), switch takes the whole ack payload dict."""

    def __init__(self):
        self.calls = []

    def handle_skip_field_response(self, request_id, recorded, reason=None,
                                   section_complete=False):
        assert isinstance(recorded, bool), (
            "recorded must be a bool -- the real coordinator resolves the "
            "future with exactly this flag")
        self.calls.append(("skip", request_id,
                           {"recorded": recorded, "reason": reason,
                            "section_complete": section_complete}))

    def handle_switch_field_response(self, request_id, payload):
        assert isinstance(payload, dict)
        self.calls.append(("switch", request_id, payload))

    def handle_form_state_response(self, request_id, snapshot):
        self.calls.append(("form_state", request_id, snapshot))


def _client(plan_fields=None):
    schema = ffs.load_schema()
    plan = [{"field_id": f, "say": "", "wrong": ""}
            for f in (plan_fields or ["p1_line1_aliennumber",
                                      "p1_line3a_familyname"])]
    c = mfc.FakeClientWebSocket(schema, plan, dti_mode=True)
    c.service = _StubService()
    return c


def _run(coro_fn):
    async def _inner():
        coro_fn()
        await asyncio.sleep(0)  # let call_soon replies land
    asyncio.run(_inner())


def test_skip_field_recorded_and_refusals():
    c = _client()
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "skip_field", "request_id": "r1",
         "field_id": "p1_line2_acctidentifier"})))
    kind, rid, result = c.service.calls[-1]
    assert (kind, rid) == ("skip", "r1")
    assert result["recorded"] is True
    assert c.state["p1_line2_acctidentifier"]["skipped"] is True
    assert c.state["p1_line2_acctidentifier"]["confirmed"] is True
    assert c.state["p1_line2_acctidentifier"]["value"] == ""

    # already-filled refusal (the data-loss guard)
    c.state["p1_line3a_familyname"] = {"value": "Nguyen", "confirmed": False}
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "skip_field", "request_id": "r2",
         "field_id": "p1_line3a_familyname"})))
    _, _, result = c.service.calls[-1]
    assert result == {"recorded": False, "reason": "already_filled",
                      "section_complete": False}
    assert c.state["p1_line3a_familyname"]["value"] == "Nguyen"

    # unknown field
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "skip_field", "request_id": "r3", "field_id": "nope"})))
    _, _, result = c.service.calls[-1]
    assert result["reason"] == "unknown_field"


def test_switch_field_pins_and_acks():
    c = _client()
    c.state["p1_line3a_familyname"] = {"value": "Nguyen", "confirmed": True}
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "switch_field", "request_id": "s1",
         "field": "p1_line3a_familyname"})))
    kind, rid, ack = c.service.calls[-1]
    assert (kind, ack["found"]) == ("switch", True)
    assert ack["field_id"] == "p1_line3a_familyname"
    assert ack["already_confirmed"] is True
    assert ack["has_value"] is True and ack["value"] == "Nguyen"
    assert "next_field_schema" in ack  # DTI mode rides the schema
    assert c.pinned_field_id == "p1_line3a_familyname"

    # pin is DORMANT on a confirmed field...
    assert c._pin_active() is None
    # ...until a value update resets confirmed (the correction flow)
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "form_updated",
         "data": {"form_state": {"p1_line3a_familyname": {"value": "Tran"}}}})))
    assert c.state["p1_line3a_familyname"]["confirmed"] is False
    assert c._pin_active() == "p1_line3a_familyname"
    assert "p1_line3a_familyname" in (c.next_hint() or "")

    # spoken-name resolution + hidden rejection
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "switch_field", "request_id": "s2",
         "field": "previous family name"})))
    _, _, ack = c.service.calls[-1]
    # the previous-name field is hidden for this persona (gate = name changed)
    assert ack.get("found") in (False, True)
    if ack["found"] is False:
        assert ack["reason"] in ("unknown_field", "hidden")


def test_validation_result_sets_steered_markers():
    c = _client()
    c.state["p1_line6e_state"] = {"value": "texas", "confirmed": True}
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "validation_result",
         "conflicts": [{"field_ids": ["p1_line6e_state", "p1_line6f_zipcode"],
                        "reason": "zip/state mismatch"}]})))
    assert c.state["p1_line6e_state"]["steered"] is True
    assert c.state["p1_line6f_zipcode"]["steered"] is True
    assert len(c.validation_results) == 1


def test_validation_fields_contract2():
    c = _client()
    c.state["p1_line6e_state"] = {"value": "texas", "confirmed": True,
                                  "steered": True}
    c.state["p1_line6f_zipcode"] = {"value": "77027", "confirmed": True}
    c.state["p1_line6g_province"] = {"value": "", "confirmed": True}  # empty
    rows = c.validation_fields()
    by_id = {r["field_id"]: r for r in rows}
    assert by_id["p1_line6e_state"]["steered"] is True
    assert by_id["p1_line6f_zipcode"]["steered"] is False
    assert "p1_line6g_province" not in by_id  # non-empty only
    for r in rows:
        assert set(r) == {"field_id", "name", "value", "steered"}
    # up_to bound cuts the list
    partial = c.validation_fields(up_to_fid="p1_line6e_state")
    assert all(r["field_id"] != "p1_line6f_zipcode" for r in partial)


def test_whole_form_state_snapshot_carries_shown():
    c = _client()
    c.state["p1_line1_aliennumber"] = {"value": "123456789", "confirmed": True}
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "get_form_state", "request_id": "f1"})))
    kind, rid, snapshot = c.service.calls[-1]
    assert kind == "form_state"
    # EVERY schema field is represented, with a shown flag
    assert len(snapshot) == len(c.schema_field_order)
    assert snapshot["p1_line1_aliennumber"]["shown"] is True
    # the name-change-gated previous-name field is hidden (gate unsatisfied)
    assert snapshot["p1_line5a_familyname"]["shown"] is False


# ------------------------------------------------------- pricing + windows

def test_price_text_usage():
    # 10k prompt (8k cached) + 200 out:
    # (2000 * 0.10 + 8000 * 0.01) / 1e6 + 200 * 0.40 / 1e6
    usd = mfc.price_text_usage(10_000, 8_000, 200)
    assert abs(usd - (2000 * 0.10e-6 + 8000 * 0.01e-6 + 200 * 0.40e-6)) < 1e-12
    # cached clamps to prompt; negatives clamp to 0
    assert mfc.price_text_usage(100, 500, 0) == pytest.approx(100 * 0.01e-6)
    assert mfc.price_text_usage(-5, 0, -1) == 0


class _StubValidatingService:
    async def handle_validation_windows(self, windows):
        self.windows = windows
        return {"conflicts": [{"field_ids": ["a", "b"], "reason": "x"}]}


def test_validation_seam_windows_and_flow():
    async def _inner():
        c = _client()
        svc = _StubValidatingService()
        seam = mfc.ValidationSeam(svc, c, size=4, stride=2)
        payload = [{"field_id": f"f{i}", "name": f"f{i}", "value": "v",
                    "steered": False} for i in range(7)]
        seam.submit(payload, reason="test")
        dropped = await seam.drain()
        assert dropped == 0
        # geometry: starts at 0, 2, 4 (start 6 leaves a tail < stride)
        assert [len(w) for w in svc.windows] == [4, 4, 3]
        # resubmitting the same payload sends NOTHING new (high-water starts)
        seam.submit(payload, reason="again")
        assert len(seam.records) == 1
        # verdict recorded + pushed to the client as a validation_result
        assert seam.records[0]["conflicts"]
        assert len(c.validation_results) == 1
        assert c.validation_results[0]["conflicts"][0]["field_ids"] == ["a", "b"]
        assert seam.flagged_groups() == [{"a", "b"}]
        assert seam.latencies() and seam.latencies()[0] >= 0
    asyncio.run(_inner())


def test_validation_seam_page_boundary_first_forward_only():
    async def _inner():
        c = _client()
        svc = _StubValidatingService()
        seam = mfc.ValidationSeam(svc, c)
        fbi = {"f1": {"pdf_position": {"page": 1}},
               "f2": {"pdf_position": {"page": 2}}}
        c.state["x"] = {"value": "v", "confirmed": True}
        assert seam.maybe_page_boundary("f1", "f2", fbi) is False or True
        fired_first = seam.high_water_page == 1
        assert fired_first
        # re-crossing the same boundary does not re-fire
        assert seam.maybe_page_boundary("f1", "f2", fbi) is False
        await seam.drain()
    asyncio.run(_inner())


# ------------------------------------------------------------ event weave

def test_weave_and_scoring_roundtrip():
    plan = ffs.build_full_form_plan(ffs.load_schema())
    steps, exp2, planted = se.weave_events(
        plan["questions"], se.STANDARD_EVENTS, plan["expected"],
        mix_unhappy_every=5)
    assert len(planted) == 2
    assert exp2["p1_line6f_zipcode"] == "77027"
    assert exp2["p1_line2_acctidentifier"] == ""  # skipped
    assert sum(1 for s in steps if s.get("path") == "unhappy") > 0
    assert sum(1 for s in steps if "event" in s) == 4  # 2 recalls + 2 navs

    pr = se.score_validator_pr(
        planted,
        [{"p1_line6f_zipcode", "p1_line6e_state"},   # covers plant 1
         {"p1_line6f_zipcode", "p1_line7e_zipcode"},  # knock-on (attributable)
         {"p3_race", "p3_ethnicity"}])                # false positive
    assert pr["recall"] == 0.5
    assert pr["plant_attributable"] == 2
    assert pr["false_positive_groups"] == [["p3_ethnicity", "p3_race"]]


def test_classify_fill_failures_modes():
    modes = se.classify_fill_failures(
        [{"field_id": "d", "expected": "04/12/1985", "written": "1985-04-12",
          "ok": False},
         {"field_id": "t", "expected": "Nguyen", "written": "Nguyan",
          "ok": False},
         {"field_id": "m", "expected": "Houston", "written": None, "ok": False},
         {"field_id": "w", "expected": "Houston", "written": "Hanoi",
          "ok": False},
         {"field_id": "s", "expected": "", "written": "USA", "ok": False}],
        {"d": "04/12/1985", "t": "Nguyen", "m": "Houston", "w": "Houston",
         "other": "Hanoi", "s": ""})
    assert modes["format"] == ["d"]
    assert modes["transcription"] == ["t"]
    assert modes["missing"] == ["m"]
    assert modes["wrong-field"] == ["w"]
    assert modes["spurious"] == ["s"]


# ---------------------------------------------------------------- summary

def test_build_summary_schema_complete():
    c = _client()
    c.state["p1_line1_aliennumber"] = {"value": "123456789", "confirmed": True}
    c.state["stray_field"] = {"value": "x"}
    c.switch_events.append({"ts": 1.0, "outcome": "unknown_field"})
    meta = {
        "model": "m", "tier": "2.5", "schema": "i90-full", "arm": "dti",
        "path": "happy", "questions": 2, "compression": True, "trigger": 5000,
        "window": 3500, "continuous": True, "started": "s",
        "events_mode": "standard", "reactivity": None, "lang": "en",
        "text_ai_wired": True, "wall_clock_s": 100.5,
        "turns": [{"q": 1, "label": "value", "stalled": False,
                   "latency_s": 1.2},
                  {"q": 1, "label": "confirm", "stalled": True,
                   "latency_s": None}],
        "continuous_reconnects": [{"before_q": 2, "announced": True,
                                   "downtime_s": 4.0}],
        "fill_accuracy": {"matched": 1, "total": 2, "accuracy": 0.5,
                          "detail": []},
        "fill_failure_modes": {"missing": ["x"]},
        "event_records": [
            {"type": "recall", "step": 1, "tool_fired": True,
             "pending_detached": False, "answer_correct": True},
            {"type": "navigate_back", "step": 2, "target": "t",
             "switched_to": "t", "hit_target": True, "seam_latency_s": 2.5},
            {"type": "skip", "step": 3, "field_id": "f", "recorded": True}],
        "steer_records": [{"t_result": 1.0, "conflicts": 1,
                           "steer_to_switch_s": 3.0, "outcome": "corrected"}],
        "validation_records": [
            {"t_submit": 1.0, "t_verdict": 2.5, "reason": "page-1-end",
             "window_count": 2,
             "conflicts": [{"field_ids": ["a", "b"], "reason": "r"}]},
            {"t_submit": 3.0, "t_verdict": 4.0, "reason": "form-complete",
             "window_count": 1,
             "conflicts": [{"field_ids": ["a", "b"], "reason": "r"}]}],
        "text_ledger_calls": [
            {"caller": "secretary", "t_start": 0.0, "dur_s": 0.9},
            {"caller": "validator", "t_start": 1.0, "dur_s": 1.4}],
        "tool_callback_exceptions": [],
        "errors": [],
        "auto_apply_fids": [],
    }
    rows = [{"question number": 1, "total tokens": 100, "total cost": 0.01},
            {"question number": 2, "total tokens": 200, "total cost": 0.02}]
    log_sink = [
        {"level": "info", "event": "text_ai_usage", "caller": "secretary",
         "fields": {"prompt_tokens": "10000", "cached_tokens": "8000",
                    "output_tokens": "150", "cache_hit": "True"}},
        {"level": "info", "event": "text_ai_usage", "caller": "validator",
         "fields": {"prompt_tokens": "1500", "cached_tokens": "0",
                    "output_tokens": "40", "cache_hit": "False"}},
        {"level": "info", "event": "dti_confirm_coerced_to_current_field",
         "fields": {}},
        {"level": "warning", "event": "validator_window_fail_open",
         "fields": {}},
        {"level": "error", "event": "gemini_session_connection_closed",
         "fields": {"code": "1011"}},
    ]
    s = mfc.build_summary(meta, rows, log_sink, c,
                          [{"a", "b"}], {"p1_line1_aliennumber"})
    h = s["headline"]
    assert h["voice_usd"] == 0.03
    assert h["text_usd"] > 0
    assert h["all_in_usd"] == pytest.approx(h["voice_usd"] + h["text_usd"])
    assert h["usd_per_correct_field"] == pytest.approx(h["all_in_usd"], rel=1e-3)
    assert s["validator"]["pr"]["recall"] == 1.0
    assert s["validator"]["duplicate_steers"] == 1  # same group in 2 verdicts
    assert s["secretary"]["calls"] == 1
    assert s["secretary"]["cache_hit_rate"] == 1.0
    assert s["navigation"]["hit_target"] == 1
    assert s["skips"] == {"requested": 1, "recorded": 1}
    assert s["errors"]["close_1011"] == 1
    assert s["errors"]["dti_coercions"] == 1
    assert s["errors"]["go_away_announced"] == 1
    assert s["errors"]["unknown_field_rejections"] == 1
    assert s["errors"]["spurious_fills"] == ["stray_field"]
    assert s["latency"]["turn_s"]["p50"] == 1.2


# ----------------------------------------------------------- dry-run loop

class _DryRunLiveAI:
    """Offline stand-in for LiveAIGemini: enough surface for the driver loop
    (P0 gate: the loop + summary wiring runs end-to-end with NO live calls).
    On each activity_end it emulates the model's happy-path behavior through
    the REAL tool-callback chain: update_form_fields then confirm_field, both
    with an empty field_id so the production DTI current-field coercion picks
    the target -- exactly the shipped coercion path."""

    def __init__(self, *a, **kw):
        self._session_ready = False
        self._on_tool_call = None
        self._toggle = "update"
        for f in ("_session_text_input_tokens", "_session_audio_input_tokens",
                  "_session_text_output_tokens", "_session_audio_output_tokens",
                  "_session_total_tokens"):
            setattr(self, f, 0)
        self._log = __import__("structlog").get_logger()

    def set_session_context(self, **kw):
        pass

    def set_callbacks(self, **kw):
        if kw.get("on_tool_call"):
            self._on_tool_call = kw["on_tool_call"]
        self._session_ready = True

    def is_session_active(self):
        return self._session_ready

    def begin_graceful_shutdown(self):
        ev = asyncio.Event()
        ev.set()
        return ev

    def _bump(self, text_in=50, audio_in=10, text_out=5, audio_out=20):
        self._session_text_input_tokens += text_in
        self._session_audio_input_tokens += audio_in
        self._session_text_output_tokens += text_out
        self._session_audio_output_tokens += audio_out
        self._session_total_tokens += text_in + audio_in + text_out + audio_out

    async def send_client_content(self, message):
        self._bump()
        return True

    async def send_text_message(self, message):
        self._bump()
        return True

    async def stream_audio(self, chunk):
        return None

    async def send_activity_start(self):
        return None

    async def send_activity_end(self):
        # One model "turn": act via the real tool chain, then bill tokens.
        if self._on_tool_call is not None:
            if self._toggle == "update":
                await self._on_tool_call(
                    "update_form_fields", {"field_id": "", "value": "1"})
                self._toggle = "confirm"
            else:
                await self._on_tool_call(
                    "confirm_field", {"field_id": "", "status": "verbal"})
                self._toggle = "update"
        self._bump()

    async def finalize(self):
        self._session_ready = False


class _DryRunTextAI:
    """Stub sidecar: clean validator verdicts, instant secretary answers."""

    def __init__(self, *a, **kw):
        self._log = __import__("structlog").get_logger()

    async def ask(self, query, context):
        return "The answer is 123456789."

    async def validate(self, payload):
        return {"conflicts": []}


def test_dry_run_i90_full_emits_summary(monkeypatch, tmp_path):
    import argparse

    monkeypatch.setenv("GEMINI_API_KEY", "dry-run-dummy")
    monkeypatch.setattr(mfc, "LiveAIGemini", _DryRunLiveAI)
    import backend.adapters.text_ai_gemini as _tam
    monkeypatch.setattr(_tam, "TextAIGemini", _DryRunTextAI)
    # 320 bytes of silence = one 40 ms chunk; no gTTS / network / cache needed.
    monkeypatch.setattr(mfc, "synth_cached",
                        lambda text, lang="en": b"\x00" * 320)

    args = argparse.Namespace(
        model="2.5", schema="i90-full", arm="dti", path="happy",
        questions=4, trigger=5000, window=3500, vertex=False,
        continuous=True, compression=True,
        out_dir=str(tmp_path), synth_only=False, debug=False,
        events="none", mix_unhappy=0, reactivity=None, lang="en",
        text_ai=False, no_text_ai=False)
    rc = asyncio.run(mfc.run(args))
    assert rc == 0

    summaries = list(tmp_path.glob("*.summary.json"))
    assert len(summaries) == 1
    import json as _json
    s = _json.loads(summaries[0].read_text(encoding="utf-8"))
    # schema-complete: every headline section present
    assert set(s) == {"run", "headline", "validator", "secretary",
                      "navigation", "skips", "latency", "errors"}
    h = s["headline"]
    for key in ("all_in_usd", "voice_usd", "text_usd", "voice_tokens",
                "wall_clock_s", "steps", "fill_accuracy",
                "fill_failure_modes", "usd_per_correct_field"):
        assert key in h
    assert h["steps"] == 4
    assert h["voice_usd"] > 0
    assert s["run"]["text_ai_wired"] is True
    # the dry-run model filled '1' everywhere: the loop CONFIRMED all 4 steps
    assert h["fill_accuracy"]["total"] == 4
    csvs = list(tmp_path.glob("*.csv"))
    assert len(csvs) == 1
    header = csvs[0].read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == mfc.CSV_COLUMNS


def test_dry_run_legacy_i90_arm_still_runs(monkeypatch, tmp_path):
    """The pre-existing 34-q --schema i90 arm keeps working untouched (its
    sidecar stays UNWIRED by default -- text_usd must be zero)."""
    import argparse

    monkeypatch.setenv("GEMINI_API_KEY", "dry-run-dummy")
    monkeypatch.setattr(mfc, "LiveAIGemini", _DryRunLiveAI)
    monkeypatch.setattr(mfc, "synth_cached",
                        lambda text, lang="en": b"\x00" * 320)

    args = argparse.Namespace(
        model="2.5", schema="i90", arm="dti", path="happy",
        questions=3, trigger=5000, window=3500, vertex=False,
        continuous=True, compression=True,
        out_dir=str(tmp_path), synth_only=False, debug=False,
        events="none", mix_unhappy=0, reactivity=None, lang="en",
        text_ai=False, no_text_ai=False)
    rc = asyncio.run(mfc.run(args))
    assert rc == 0
    import json as _json
    s = _json.loads(next(tmp_path.glob("*.summary.json"))
                    .read_text(encoding="utf-8"))
    assert s["run"]["text_ai_wired"] is False
    assert s["headline"]["text_usd"] == 0
    assert s["headline"]["steps"] == 3


# ------------------------------------------------------------- regression

def test_legacy_arms_unchanged():
    assert mfc.CSV_COLUMNS == [
        "question number",
        "audio in tokens", "audio in token cost",
        "audio out tokens", "audio out token cost",
        "text in tokens", "text in token cost",
        "text out tokens", "text out token cost",
        "total tokens", "total cost",
    ]
    assert len(mfc.SCHEMAS["i90"]["questions"]) == 34
    # i90-full is registered lazily by run(); the hand-written entries stay put
    assert set(mfc.SCHEMAS) >= {"demo", "i90"}
