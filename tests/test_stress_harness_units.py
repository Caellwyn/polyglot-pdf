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


def test_no_degenerate_unhappy_wrong_utterances():
    """Every answered (non-empty-expected) question must have a 'wrong'
    utterance DISTINCT from 'say' -- a degenerate unhappy-path turn (REJECT
    then re-hear the identical value) corrupts the unhappy-path measurement
    (bd polyglot-pdf-3gt9). Declines are exempt (phrase() intentionally
    returns the same text for both -- a decline has no distinct unhappy
    variant)."""
    plan = ffs.build_full_form_plan(ffs.load_schema())
    qs, expected = plan["questions"], plan["expected"]
    degenerate = [q["field_id"] for q in qs
                  if expected[q["field_id"]] != "" and q["say"] == q["wrong"]]
    assert degenerate == []


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


# ------------------------------------------------------- Spanish (E6, 0cyu)

def test_es_plan_matches_en_field_ids_and_expected_canon():
    """The Spanish arm speaks the SAME persona in Spanish, but the form still
    fills in English: build_full_form_plan(schema, lang='es') must produce
    the identical set of field ids and the IDENTICAL expected canon as
    lang='en' -- only the spoken say/wrong phrasings differ."""
    schema = ffs.load_schema()
    plan_en = ffs.build_full_form_plan(schema, lang="en")
    plan_es = ffs.build_full_form_plan(schema, lang="es")

    fids_en = {q["field_id"] for q in plan_en["questions"]}
    fids_es = {q["field_id"] for q in plan_es["questions"]}
    assert fids_en == fids_es
    assert len(fids_es) == len(plan_en["questions"]) == len(plan_es["questions"])

    assert plan_en["expected"] == plan_es["expected"]
    assert plan_en["hidden"] == plan_es["hidden"]
    assert plan_en["auto_apply"] == plan_es["auto_apply"]


def test_no_degenerate_unhappy_wrong_utterances_es():
    """The same degenerate say==wrong guard the English arm relies on
    (bd polyglot-pdf-3gt9) must also hold for the Spanish arm's phrasings."""
    plan = ffs.build_full_form_plan(ffs.load_schema(), lang="es")
    qs, expected = plan["questions"], plan["expected"]
    degenerate = [q["field_id"] for q in qs
                  if expected[q["field_id"]] != "" and q["say"] == q["wrong"]]
    assert degenerate == []


def test_es_phrasing_spot_checks():
    schema = ffs.load_schema()
    field_by_id = {f["id"]: f for f in schema["fields"]}
    answers = ffs.persona_answers()

    a_number_field = field_by_id["p1_line1_aliennumber"]
    say, wrong = ffs.phrase(a_number_field, answers["p1_line1_aliennumber"],
                            lang="es")
    assert "uno dos tres" in say
    assert say != wrong

    dob_field = field_by_id["p1_line9_dateofbirth"]
    say, wrong = ffs.phrase(dob_field, answers["p1_line9_dateofbirth"], lang="es")
    assert "abril" in say
    assert "mil novecientos ochenta y cinco" in say
    assert say != wrong

    # Every ES override/decline phrasing must be plain ASCII (CLAUDE.md scar
    # #6 -- gTTS 'es' pronounces unaccented Spanish acceptably, and non-ASCII
    # in a code string risks a cp1252 crash on Windows stdout).
    for value in list(ffs._SAY_OVERRIDES_ES.values()):
        for text in value:
            if text is not None:
                assert text.isascii(), f"non-ASCII ES override text: {text!r}"
    for text in ffs._DECLINE_OVERRIDES_ES.values():
        assert text.isascii(), f"non-ASCII ES decline text: {text!r}"


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

    async def handle_validation_windows(self, windows):
        self.calls.append(("validation_windows", None, windows))
        return {"conflicts": []}

    async def handle_drain_findings(self, conflicts):
        self.calls.append(("drain_findings", None, conflicts))
        return {"conflicts": []}


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


def test_validation_result_enqueues_not_steers_directly():
    """W3 report/drain split (bd polyglot-pdf-pr3i, mirrored 0cyu): a
    validation_result with conflicts must NOT set steered directly -- it only
    ENQUEUES the findings (mirror handleValidationResult). steered is set
    ONLY at drain_findings_result (test_drain_findings_result_sets_steered_
    and_consumes below)."""
    c = _client()
    c.state["p1_line6e_state"] = {"value": "texas", "confirmed": True}

    async def _inner():
        await c.send_json(
            {"type": "validation_result",
             "conflicts": [{"field_ids": ["p1_line6e_state", "p1_line6f_zipcode"],
                            "reason": "zip/state mismatch"}]})
        await asyncio.sleep(0)  # let the drain task run against the stub
        await asyncio.sleep(0)
    asyncio.run(_inner())

    assert len(c.validation_results) == 1
    # NOT steered yet -- the drain round-trip (against _StubService, which
    # returns {"conflicts": []} i.e. UNDELIVERED) never marked it.
    assert c.state["p1_line6e_state"].get("steered") is not True
    # The finding stays queued (undelivered -> retry).
    assert len(c.validator_findings_queue) == 1
    assert c.drain_in_flight is False  # cleared once the drain result landed


def test_drain_findings_result_sets_steered_and_consumes():
    """The steered marker is set + the finding consumed from the queue ONLY
    on drain_findings_result (mirror handleDrainFindingsResult)."""
    c = _client()
    c.state["p1_line6e_state"] = {"value": "texas", "confirmed": True}
    c.state["p1_line6f_zipcode"] = {"value": "77027", "confirmed": True}
    c.validator_findings_queue.append({
        "field_ids": ["p1_line6e_state", "p1_line6f_zipcode"],
        "reason": "r", "field_names": {}})
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "drain_findings_result",
         "conflicts": [{"field_ids": ["p1_line6e_state", "p1_line6f_zipcode"],
                        "reason": "r"}]})))
    assert c.state["p1_line6e_state"]["steered"] is True
    assert c.state["p1_line6f_zipcode"]["steered"] is True
    assert c.validator_findings_queue == []  # consumed
    assert c.drain_in_flight is False


def test_drain_findings_result_undelivered_keeps_queued():
    c = _client()
    c.validator_findings_queue.append({
        "field_ids": ["p1_line6e_state"], "reason": "r", "field_names": {}})
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "drain_findings_result", "conflicts": []})))
    assert c.validator_findings_queue == [
        {"field_ids": ["p1_line6e_state"], "reason": "r", "field_names": {}}]
    assert c.drain_in_flight is False


def test_enqueue_dedupes_by_field_id_set():
    """Mirror enqueueValidatorFindings: a second finding naming the SAME
    field-id set (order-insensitive) is not queued twice."""
    c = _client()
    c.service = None  # do not trigger a real drain task for this pure check
    c._enqueue_validator_findings(
        [{"field_ids": ["a", "b"], "reason": "r1"}])
    c._enqueue_validator_findings(
        [{"field_ids": ["b", "a"], "reason": "r2 (same set, reordered)"}])
    assert len(c.validator_findings_queue) == 1
    c._enqueue_validator_findings([{"field_ids": ["a", "c"], "reason": "r3"}])
    assert len(c.validator_findings_queue) == 2


def test_drain_single_flight_and_redrain_on_growth():
    """Mirror drainFindings' single-flight guard + handleDrainFindingsResult's
    re-drain-if-grew-mid-flight behavior."""
    class _SlowStubService:
        def __init__(self):
            self.calls = 0

        async def handle_drain_findings(self, conflicts):
            self.calls += 1
            return {"conflicts": []}  # undelivered every time (keeps queued)

    async def _inner():
        c = _client()
        c.service = _SlowStubService()
        c._enqueue_validator_findings([{"field_ids": ["a"], "reason": "r1"}])
        assert c.drain_in_flight is True
        # A second enqueue while the first drain is in flight must NOT start
        # a second drain call (single-flight).
        c._enqueue_validator_findings([{"field_ids": ["b"], "reason": "r2"}])
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        # Exactly one drain call ran for BOTH findings (they were queued
        # together before the single in-flight call snapshotted the queue).
        assert c.service.calls == 1
    asyncio.run(_inner())


# --------------------------------------- W4 steered lifecycle (bd ny4s)

def test_steered_cleared_on_genuine_value_change():
    """Mirror W4 updateField's re-arm rule (schemaFormState.ts:339-365): a
    steered field's marker CLEARS when its value actually changes."""
    c = _client()
    c.state["p1_line3a_familyname"] = {"value": "Vasquez", "confirmed": True,
                                       "steered": True}
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "form_updated",
         "data": {"form_state": {"p1_line3a_familyname": {"value": "Vargas"}}}})))
    assert c.state["p1_line3a_familyname"]["value"] == "Vargas"
    assert c.state["p1_line3a_familyname"]["steered"] is False
    assert c.state["p1_line3a_familyname"]["confirmed"] is False


def test_steered_preserved_on_same_value_rewrite():
    """A same-value re-write (the 'both are intentional' confirm path) must
    NOT clear steered -- the no-nagging guarantee (W4 fresh-eyes)."""
    c = _client()
    c.state["p1_line3a_familyname"] = {"value": "Vasquez", "confirmed": True,
                                       "steered": True}
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "form_updated",
         "data": {"form_state": {"p1_line3a_familyname": {"value": "Vasquez"}}}})))
    assert c.state["p1_line3a_familyname"]["steered"] is True
    # confirmed is NOT reset either -- no value moved.
    assert c.state["p1_line3a_familyname"]["confirmed"] is True


def test_steered_preserved_across_confirm_field():
    """confirm_field (no value write) must never touch the steered marker."""
    c = _client()
    c.state["p1_line3a_familyname"] = {"value": "Vasquez", "confirmed": False,
                                       "steered": True}
    _run(lambda: asyncio.ensure_future(c.send_json(
        {"type": "confirm_field", "request_id": "cf1",
         "field_id": "p1_line3a_familyname"})))
    assert c.state["p1_line3a_familyname"]["confirmed"] is True
    assert c.state["p1_line3a_familyname"]["steered"] is True


def test_same_field_value_checkbox_group_order_insensitive():
    """Mirror _sameFieldValue's set-equality on checkbox-group arrays (W4
    fresh-eyes finding: CheckboxField.handleToggle re-appends, so a re-checked
    box can land in a different order -- that must NOT read as a change)."""
    same = mfc.FakeClientWebSocket._same_field_value
    assert same(["a", "b"], ["b", "a"]) is True
    assert same(["a", "b"], ["a", "c"]) is False
    assert same(None, "") is True
    assert same([], None) is True
    assert same("", []) is True
    assert same("x", "x") is True
    assert same("x", "y") is False


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


def test_price_text_usage_per_model():
    """bd polyglot-pdf-0cyu: per-model rate rows. flash-lite (explicit + the
    None-model back-compat default) vs pro vs an unknown model (priced at the
    highest known rate, never silently under-priced)."""
    lite = mfc.price_text_usage(10_000, 8_000, 200, model="gemini-2.5-flash-lite")
    default = mfc.price_text_usage(10_000, 8_000, 200)  # back-compat: no model
    assert lite == pytest.approx(default)
    pro = mfc.price_text_usage(10_000, 8_000, 200, model="gemini-2.5-pro")
    assert pro > lite  # pro's per-token rates are strictly higher
    rates, unpriced = mfc._rates_for_model("gemini-9000-mystery")
    assert unpriced is True
    for k in ("input", "cached_input", "output"):
        assert rates[k] == max(r[k] for r in mfc.TEXT_RATES_BY_MODEL.values())


# ------------------------------------------------------- W2 windows (0cyu)

def _window_client():
    """A client whose active plan is EVERY real i-90 field visible for the
    default (name-unchanged) persona -- so field settledness can be driven
    directly through c.state without touching client-only plumbing."""
    schema = ffs.load_schema()
    field_ids = [f["id"] for f in schema["fields"]]
    plan = [{"field_id": f, "say": "", "wrong": ""} for f in field_ids]
    c = mfc.FakeClientWebSocket(schema, plan, dti_mode=True)
    c.service = _StubService()
    return c, field_ids


def _confirm_all(c, field_ids, start, end):
    for fid in field_ids[start:end]:
        if c.field_shown(fid):
            c.state[fid] = {"value": "v", "confirmed": True}


def test_compute_ready_windows_requires_all_settled():
    c, field_ids = _window_client()
    # Window 0 covers indices [0, 5). Confirm only 4 of the 5 -> NOT eligible
    # (the real 132-field schema can have OTHER windows made eligible purely
    # by hidden fields, so assert on window 0 specifically, not the full
    # return list).
    _confirm_all(c, field_ids, 0, 4)
    ready = {w["index"]: w for w in c.compute_ready_windows(size=5, stride=3)}
    assert 0 not in ready
    # Confirm the 5th -> now eligible.
    _confirm_all(c, field_ids, 4, 5)
    ready = {w["index"]: w for w in c.compute_ready_windows(size=5, stride=3)}
    assert ready[0] == {"index": 0, "start": 0, "end": 5}


def test_compute_ready_windows_hidden_counts_as_settled():
    """p1_line5a/b/c (indices 6-8) are HIDDEN by default (name-change gate
    unsatisfied) -- a window covering them must be eligible WITHOUT ever
    confirming those fields, mirroring isSettled's shouldShowField branch."""
    c, field_ids = _window_client()
    assert field_ids[5:9] == ["p1_checkbox4", "p1_line5a_familyname",
                              "p1_line5b_givenname", "p1_line5c_middlename"]
    # Confirm p1_checkbox4 (index 5) -- its "no" answer is what HIDES the
    # previous-name fields at indices 6-8. Use a stride-1 window starting
    # exactly at index 5 so [5, 9) is the ONLY window under test.
    c.state["p1_checkbox4"] = {"value": "no", "confirmed": True}
    ready = {w["index"]: w for w in c.compute_ready_windows(size=4, stride=1)}
    assert ready[5] == {"index": 5, "start": 5, "end": 9}


def test_compute_ready_windows_index_dedup_across_calls():
    c, field_ids = _window_client()
    _confirm_all(c, field_ids, 0, 5)
    first = {w["index"] for w in c.compute_ready_windows(size=5, stride=5)}
    assert 0 in first
    c.validated_window_indices |= first
    # Calling again without further progress never re-returns an
    # already-sent index.
    again = {w["index"] for w in c.compute_ready_windows(size=5, stride=5)}
    assert 0 not in again


def test_maybe_emit_validate_windows_submits_and_marks_sent():
    async def _inner():
        c, field_ids = _window_client()
        svc = _StubService()
        c.service = svc
        _confirm_all(c, field_ids, 0, 5)
        # Isolate to window geometry that makes ONLY window 0 eligible here
        # (size covers exactly the confirmed prefix; stride == size avoids
        # a same-index overlap window also going eligible off hidden fields
        # elsewhere in the real 132-field schema).
        mfc.WEBFORM_VALIDATOR_WINDOW_SIZE, orig_size = 5, mfc.WEBFORM_VALIDATOR_WINDOW_SIZE
        mfc.WEBFORM_VALIDATOR_WINDOW_STRIDE, orig_stride = 5, mfc.WEBFORM_VALIDATOR_WINDOW_STRIDE
        try:
            c.maybe_emit_validate_windows()
            await asyncio.sleep(0)
            assert 0 in c.validated_window_indices
            assert len(c.validation_records) == 1
            assert c.validation_records[0]["window_count"] >= 1
            # A second call with no new progress submits nothing further for
            # the SAME index (it stays marked sent).
            sent_before = set(c.validated_window_indices)
            c.maybe_emit_validate_windows()
            await asyncio.sleep(0)
            assert 0 in c.validated_window_indices
            assert sent_before <= c.validated_window_indices
        finally:
            mfc.WEBFORM_VALIDATOR_WINDOW_SIZE = orig_size
            mfc.WEBFORM_VALIDATOR_WINDOW_STRIDE = orig_stride
    asyncio.run(_inner())


def test_reconnect_rechecks_windows_and_redrains():
    """handleSessionReady parity: after a reconnect, re-checking windows finds
    newly-eligible ones, and a survived findings queue re-drains."""
    async def _inner():
        c, field_ids = _window_client()
        _confirm_all(c, field_ids, 0, 5)
        c.validator_findings_queue.append(
            {"field_ids": ["p1_line1_aliennumber"], "reason": "r",
             "field_names": {}})
        orig_size = mfc.WEBFORM_VALIDATOR_WINDOW_SIZE
        orig_stride = mfc.WEBFORM_VALIDATOR_WINDOW_STRIDE
        mfc.WEBFORM_VALIDATOR_WINDOW_SIZE = 5
        mfc.WEBFORM_VALIDATOR_WINDOW_STRIDE = 5
        try:
            # Mirror the driver's post-reconnect calls.
            c.maybe_emit_validate_windows()
            c._drain_findings()
            await asyncio.sleep(0)
            assert 0 in c.validated_window_indices
            assert len(c.validation_records) == 1
            assert len(c.drain_results) == 1
        finally:
            mfc.WEBFORM_VALIDATOR_WINDOW_SIZE = orig_size
            mfc.WEBFORM_VALIDATOR_WINDOW_STRIDE = orig_stride
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


class _DryRunTextAIOneConflict(_DryRunTextAI):
    """bd polyglot-pdf-0cyu: like _DryRunTextAI, but .validate() returns ONE
    conflict on its FIRST call, then clean thereafter -- exercises the full
    offline enqueue -> drain -> drain_findings_result -> steered lifecycle
    end-to-end without a live call (the audit's requested dry-run coverage)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._calls = 0

    async def validate(self, payload):
        self._calls += 1
        if self._calls == 1:
            return {"conflicts": [{"field_ids": ["p1_line1_aliennumber",
                                                  "p1_line2_acctidentifier"],
                                   "reason": "dry-run planted conflict"}]}
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
    # schema-complete: every headline section present (pro_pass added bd 0cyu)
    assert set(s) == {"run", "headline", "validator", "pro_pass", "secretary",
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
    # run() writes TWO csvs per run since bd wiadk: the per-question CSV and
    # the per-turn .turns.csv sidecar. Pin both shapes.
    all_csvs = sorted(tmp_path.glob("*.csv"))
    csvs = [p for p in all_csvs if not p.name.endswith(".turns.csv")]
    turns_csvs = [p for p in all_csvs if p.name.endswith(".turns.csv")]
    assert len(csvs) == 1
    assert len(turns_csvs) == 1
    header = csvs[0].read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == mfc.CSV_COLUMNS
    turns_header = turns_csvs[0].read_text(encoding="utf-8").splitlines()[0]
    assert turns_header.split(",") == mfc.TURNS_CSV_COLUMNS


def test_dry_run_i90_full_drain_round_trip():
    """bd polyglot-pdf-0cyu: end-to-end OFFLINE drain lifecycle, driven
    directly against the FakeClient + the REAL FormFillingService (wired with
    the stubbed _DryRunTextAIOneConflict sidecar -- no live call). The
    dry-run VOICE driver never actually gets a field to `confirmed` (its
    fake update_form_fields/confirm_field tool calls fail real-field
    validation for the i-90 schema, a pre-existing property of
    test_dry_run_i90_full_emits_summary's own baseline -- matched stays 0
    there too), so this test isolates the seam machinery instead: settle two
    real fields directly, drive one window-check + drain round, and assert
    the queue/drain/steered lifecycle completes with the stub returning one
    conflict once, then clean."""
    class _ActiveLiveAI:
        """Minimal fake: an ACTIVE live session that always accepts the
        steer send, so _inject_validator_steer's delivery gate passes and the
        drain_findings_result carries a real `delivered` conflict (mirrors a
        healthy live session; a dead one is exercised by
        test_drain_findings_result_undelivered_keeps_queued instead)."""

        def is_session_active(self):
            return True

        async def send_client_content(self, message):
            return True

    async def _inner():
        schema = ffs.load_schema()
        field_ids = [f["id"] for f in schema["fields"]]
        plan = [{"field_id": f, "say": "", "wrong": ""} for f in field_ids]
        c = mfc.FakeClientWebSocket(schema, plan, dti_mode=True)

        text_ai = _DryRunTextAIOneConflict()
        service = mfc.FormFillingService(
            live_ai=_ActiveLiveAI(), settings=mfc._config.Settings(),
            text_ai=text_ai)
        c.service = service

        # Settle the first 2 fields (a real conflict-bearing pair) so window
        # 0 becomes eligible.
        c.state["p1_line1_aliennumber"] = {"value": "123456789", "confirmed": True}
        c.state["p1_line2_acctidentifier"] = {"value": "123456789012",
                                              "confirmed": True}
        orig_size = mfc.WEBFORM_VALIDATOR_WINDOW_SIZE
        orig_stride = mfc.WEBFORM_VALIDATOR_WINDOW_STRIDE
        mfc.WEBFORM_VALIDATOR_WINDOW_SIZE = 2
        mfc.WEBFORM_VALIDATOR_WINDOW_STRIDE = 2
        try:
            c.maybe_emit_validate_windows()
            # Let the validate_windows task run, push validation_result,
            # enqueue, and single-flight drain to completion.
            for _ in range(5):
                await asyncio.sleep(0)
        finally:
            mfc.WEBFORM_VALIDATOR_WINDOW_SIZE = orig_size
            mfc.WEBFORM_VALIDATOR_WINDOW_STRIDE = orig_stride

        # The planted conflict was reported, enqueued, drained, delivered,
        # and consumed -- nothing left queued.
        assert c.validator_findings_queue == []
        assert c.drain_in_flight is False
        assert c.state["p1_line1_aliennumber"]["steered"] is True
        assert c.state["p1_line2_acctidentifier"]["steered"] is True
        assert len(c.drain_results) == 1
        assert c.drain_results[0]["delivered"] == 1
        # The drain record retains ITS OWN delivered field ids (bd 0cyu fix --
        # check_steers must scope to this drain's fields, not a scan of every
        # steered field in client.state, which can carry stale markers from
        # an earlier un-cleared "overridden_unplanted" ack).
        assert set(c.drain_results[0]["field_ids"]) == {
            "p1_line1_aliennumber", "p1_line2_acctidentifier"}

        # A SECOND window check (the stub validator is clean on later calls)
        # must not enqueue anything further.
        c.state["p1_line3a_familyname"] = {"value": "Vasquez", "confirmed": True}
        c.state["p1_line3b_givenname"] = {"value": "Maria", "confirmed": True}
        c.maybe_emit_validate_windows()
        for _ in range(5):
            await asyncio.sleep(0)
        assert c.validator_findings_queue == []
        assert len(c.drain_results) == 1  # no new drain triggered

        summary = mfc.build_summary(
            {"validation_records": list(c.validation_records),
             "drain_records": list(c.drain_results), "pro_pass": None,
             "text_ledger_calls": [], "wall_clock_s": 1.0},
            [], [], c, [], set())
        assert summary["validator"]["drains"] == {
            "count": 1, "delivered": 1, "undelivered_retries": 0}
        assert "drain_latency_s" in summary["validator"]
        assert summary["pro_pass"]["ran"] is False
    asyncio.run(_inner())


# ------------------------------------------------- i90-v2 continuous-DTI drip
#
# bd polyglot-pdf-2nikx: a live 57-question --schema i90-v2 --arm dti
# --continuous run filled+confirmed q1, then emitted ZERO tool calls for q3
# onward (52 straight questions of pure conversation, no stalls/errors). The
# HYPOTHESIS was that i90-v2's schema.json shape -- sections[].fields as a
# list of field-id STRINGS referencing the top-level fields[] list of dicts,
# rather than inlining full field dicts -- silently starves the harness's
# next_field_hint / manifest / DTI-drip machinery once the plan crosses the
# first section boundary.
#
# INVESTIGATION FINDING: every form kit (w7, i-90, i-90_v2, f1040) already
# uses the string-id shape for sections[].fields -- there is no dict-inlining
# kit left to regress against, and the harness's own section-order test
# (test_measure_harness_i90v2_plan.py::TestSectionOrder) already reads
# sections[].fields as ID strings. So the hypothesis is REFUTED at the schema
# level. This test proves it is refuted at the BEHAVIORAL level too: driven
# by a well-behaved fake model that (a) looks up the client's own real
# "current unconfirmed field" (exactly what the DTI drip's next_field_hint /
# next_field_schema round-trip is supposed to keep in sync) and (b) supplies
# a VALUE THAT ACTUALLY PASSES that field's OWN validation constraints, the
# continuous-DTI drip advances past the section-1/section-2 boundary (field 3,
# "family_name", a DIFFERENT schema section than field 1/2) and keeps
# confirming every field through question 15 -- with NO live Gemini call.
#
# This differs from _DryRunLiveAI (used by test_dry_run_i90_full_emits_summary
# / test_dry_run_i90_full_drain_round_trip) in exactly one respect: those
# fakes send a HARDCODED value ("1") with an EMPTY field_id, relying solely on
# the DTI current-field coercion gate -- which works, but the hardcoded "1"
# fails real per-field validation (e.g. a_number's ^[0-9]{7,9}$ pattern), so
# confirm_field never actually records True and the current-field pointer
# never advances (their own docstrings note this is a pre-existing dry-run
# limitation, not a bug). This test's fake instead supplies a value that
# genuinely validates, so confirm_field succeeds for real and the drip's
# request_next_field_hint -> merge_field_schema -> _current_field_id advance
# is exercised end-to-end -- proving the starvation the live run hit is a
# live-model behavior variance (confirmed independently: the artifact from
# the same bead's 3-question smoke run shows the model calling skip_field
# instead of confirm_field for the very same optional "uscis_account" field
# and continuing normally, vs. the failing run's model calling neither),
# not a harness data-shape defect.
def _dti_drip_valid_value_for(field: dict) -> str:
    """A value that should pass THIS field's own validation constraints --
    mirrors what a well-behaved voice model / real user answer would supply,
    so confirm_field genuinely succeeds instead of silently failing validation
    the way _DryRunLiveAI's hardcoded "1" does for most text fields."""
    import re as _re

    ftype = field.get("type")
    validation = field.get("validation") or {}
    if ftype in ("radio", "select", "checkbox_group"):
        options = field.get("options") or []
        return options[0]["value"] if options else ""
    if not validation.get("required", False):
        # An optional field with no pattern constraint: the empty "does not
        # apply" answer is a legitimate, common real-world path (and is
        # exactly what tripped the live bug's q2 "uscis_account" -- pinning
        # this path is the point, not an incidental simplification).
        if not validation.get("pattern"):
            return ""
    pattern = validation.get("pattern")
    if pattern:
        m = _re.match(r"^\^\[0-9\]\{(\d+)(?:,(\d+))?\}\$$", pattern)
        if m:
            n = int(m.group(2) or m.group(1))
            return "1" * n
    min_len = validation.get("min_length")
    if min_len:
        return "1" * min_len
    if ftype == "date":
        return "01/01/1990"
    if ftype == "email":
        return "a@example.com"
    return "test value"


class _DtiDripLiveAI:
    """Like _DryRunLiveAI, but looks up the FakeClientWebSocket's own current
    unconfirmed field (via active_field_ids + confirmed state -- exactly what
    the DTI protocol's next_field_hint/next_field_schema round-trip is meant
    to keep the backend's _current_field_id pointer in sync with) and sends
    that field's real id plus a validation-passing value. This is the
    minimal change needed to exercise the REAL confirm-succeeds ->
    request_next_field_hint -> merge_field_schema -> pointer-advances path,
    instead of always failing validation and never advancing (bd
    polyglot-pdf-2nikx investigation)."""

    def __init__(self, *a, **kw):
        self._session_ready = False
        self._on_tool_call = None
        self._toggle = "update"
        self.client = None  # set by the test after FakeClientWebSocket exists
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

    def _current_field(self):
        client = self.client
        if client is None:
            return None
        for fid in client.active_field_ids:
            entry = client.state.get(fid)
            if not entry or not entry.get("confirmed"):
                return client.schema_fields.get(fid)
        return None

    async def send_activity_end(self):
        if self._on_tool_call is not None:
            field = self._current_field()
            fid = field["id"] if field else ""
            if self._toggle == "update":
                value = _dti_drip_valid_value_for(field) if field else "1"
                await self._on_tool_call(
                    "update_form_fields", {"field_id": fid, "value": value})
                self._toggle = "confirm"
            else:
                await self._on_tool_call(
                    "confirm_field", {"field_id": fid, "status": "verbal"})
                self._toggle = "update"
        self._bump()

    async def finalize(self):
        self._session_ready = False


def test_dry_run_i90_v2_continuous_dti_drip_advances_past_section_boundary(
        monkeypatch, tmp_path):
    """The offline reproduction for bd polyglot-pdf-2nikx: with a
    validation-passing fake model, --schema i90-v2 --arm dti --continuous
    fills+confirms every one of the first 15 plan questions -- crossing from
    section 1 (a_number, uscis_account) into later sections (family_name
    onward) -- with NO live Gemini call and NO starvation. This refutes the
    string-vs-dict sections[].fields hypothesis behaviorally, not just by
    schema-shape inspection.

    MUTATION-VERIFIED (per CLAUDE.md 'test the tests'): reverting
    _dti_drip_valid_value_for to always return the OLD _DryRunLiveAI-style
    hardcoded "1" (which fails a_number's ^[0-9]{7,9}$ pattern) turns this RED
    -- confirmed_fields stops at 0 and the drip never leaves field 1, proving
    this test actually discriminates a starved drip from a healthy one.
    """
    import argparse

    monkeypatch.setenv("GEMINI_API_KEY", "dry-run-dummy")
    monkeypatch.setattr(mfc, "LiveAIGemini", _DtiDripLiveAI)
    monkeypatch.setattr(mfc, "synth_cached",
                        lambda text, lang="en": b"\x00" * 320)

    fake_ai_holder = {}
    _orig_live_ai_gemini = _DtiDripLiveAI

    def _capturing_live_ai(*a, **kw):
        inst = _orig_live_ai_gemini(*a, **kw)
        fake_ai_holder["ai"] = inst
        return inst

    monkeypatch.setattr(mfc, "LiveAIGemini", _capturing_live_ai)

    _orig_client_init = mfc.FakeClientWebSocket.__init__

    def _capturing_client_init(self, *a, **kw):
        _orig_client_init(self, *a, **kw)
        if "ai" in fake_ai_holder:
            fake_ai_holder["ai"].client = self

    monkeypatch.setattr(mfc.FakeClientWebSocket, "__init__", _capturing_client_init)

    args = argparse.Namespace(
        model="2.5", schema="i90-v2", arm="dti", path="happy",
        questions=15, trigger=5000, window=3500, vertex=False,
        continuous=True, compression=True,
        out_dir=str(tmp_path), synth_only=False, debug=False,
        events="none", mix_unhappy=0, reactivity=None, lang="en",
        text_ai=False, no_text_ai=False)
    rc = asyncio.run(mfc.run(args))
    assert rc == 0

    import json as _json
    m = _json.loads(next(tmp_path.glob("*.meta.json")).read_text(encoding="utf-8"))

    # The plan's first 2 questions (a_number, uscis_account) are section 1;
    # family_name (question 3) is a DIFFERENT schema section -- confirming it
    # is the section-boundary crossing the live bug never made.
    confirmed = set(m["client_confirmed_fields"])
    assert "family_name" in confirmed, (
        "the DTI drip never advanced past the first schema section -- this "
        "is exactly the live starvation bd polyglot-pdf-2nikx reported")
    # All 15 asked questions confirmed, not just the first section's 2.
    asked_ids = {q["field_id"] for q in mfc.I90V2_QUESTIONS[:15]}
    assert asked_ids <= confirmed, (
        f"drip starved partway through: missing {asked_ids - confirmed}")

    # Every question actually saw BOTH tool calls (no silent no-op turns).
    per_q = m["per_question_tools"]
    for i in range(1, 16):
        tools = per_q[str(i)]
        assert "update_form_fields" in tools and "confirm_field" in tools, (
            f"question {i} got no tool calls: {tools}")


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


def test_events_unhappy_path_happy_mismatch_exits_loudly(monkeypatch, tmp_path):
    """--events unhappy combined with the --path default (happy) must FAIL
    LOUDLY before any adapter is constructed (bd polyglot-pdf-3gt9), not
    silently measure a mostly-happy session mislabeled as the E3 unhappy arm.
    Monkeypatch LiveAIGemini to raise if constructed, so a guard that fires
    too late (after adapter construction) fails this test instead of passing
    it by accident."""
    import argparse

    def _boom(*a, **kw):
        raise AssertionError(
            "LiveAIGemini constructed -- the events/path guard did not fire "
            "before adapter construction")

    monkeypatch.setenv("GEMINI_API_KEY", "dry-run-dummy")
    monkeypatch.setattr(mfc, "LiveAIGemini", _boom)

    args = argparse.Namespace(
        model="2.5", schema="i90-full", arm="dti", path="happy",
        questions=4, trigger=5000, window=3500, vertex=False,
        continuous=True, compression=True,
        out_dir=str(tmp_path), synth_only=False, debug=False,
        events="unhappy", mix_unhappy=0, reactivity=None, lang="en",
        text_ai=False, no_text_ai=False)
    # no allow_path_mismatch attribute at all -- getattr(..., False) default
    with pytest.raises(SystemExit):
        asyncio.run(mfc.run(args))


def test_events_unhappy_path_unhappy_is_allowed(monkeypatch, tmp_path):
    """The matched combination (--events unhappy --path unhappy) must NOT
    trip the guard. synth_only=True: run() exits 0 right after plan build +
    event weave + (stubbed) fixture synthesis -- past the guard, before any
    adapter -- so the test stays fast (no 113-step dry-run driver loop)."""
    import argparse

    monkeypatch.setenv("GEMINI_API_KEY", "dry-run-dummy")
    monkeypatch.setattr(mfc, "synth_cached",
                        lambda text, lang="en": b"\x00" * 320)

    args = argparse.Namespace(
        model="2.5", schema="i90-full", arm="dti", path="unhappy",
        questions=None, trigger=5000, window=3500, vertex=False,
        continuous=True, compression=True,
        out_dir=str(tmp_path), synth_only=True, debug=False,
        events="unhappy", mix_unhappy=0, reactivity=None, lang="en",
        text_ai=False, no_text_ai=False)
    rc = asyncio.run(mfc.run(args))
    assert rc == 0


def test_events_unhappy_path_happy_allowed_with_override(monkeypatch, tmp_path):
    """--allow-path-mismatch lets the mismatched combination proceed
    (synth_only=True for speed, as above)."""
    import argparse

    monkeypatch.setenv("GEMINI_API_KEY", "dry-run-dummy")
    monkeypatch.setattr(mfc, "synth_cached",
                        lambda text, lang="en": b"\x00" * 320)

    args = argparse.Namespace(
        model="2.5", schema="i90-full", arm="dti", path="happy",
        questions=None, trigger=5000, window=3500, vertex=False,
        continuous=True, compression=True,
        out_dir=str(tmp_path), synth_only=True, debug=False,
        events="unhappy", mix_unhappy=0, reactivity=None, lang="en",
        text_ai=False, no_text_ai=False, allow_path_mismatch=True)
    rc = asyncio.run(mfc.run(args))
    assert rc == 0


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
