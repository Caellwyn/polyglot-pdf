"""W1 (bd polyglot-pdf-xbl2): FormFillingService.handle_validation_windows -- the
ASYNC, multi-window validator boundary that runs off the WS receive loop.

These exercise the service method directly with a mocked ITextAI (per-window
verdicts) and a mocked ILiveAI (the steer sink), proving the W1 exit criteria at
the service layer:
  - overlapping windows that surface the SAME conflicting field-id set yield
    exactly ONE steer after batch dedupe (criterion 2 / epic criterion 3 dedupe);
  - each window is validated concurrently and fails open independently -- one dead
    window never blocks the others (criterion 3 / fail-open);
  - the existing already-steered suppression + one-steer injection still hold over
    the UNION of the windows' fields.

The websocket-level "off the receive loop" + "background exception never crashes
the loop" criteria live in test_proactive_complete_events.py (the arm that spawns
this in a background task).

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.form_filling_service import FormFillingService


def _service():
    """A FormFillingService whose validator + live session are mockable per test.
    The text_ai.validate mock is shared across windows (handle_validation_windows
    builds a fresh ValidatorService(self._text_ai) per window), so tests that want
    per-window verdicts set a side_effect keyed on the payload's field ids."""
    text_ai = MagicMock(name="text_ai")
    live_ai = MagicMock(name="live_ai")
    live_ai.is_session_active = MagicMock(return_value=True)
    live_ai.send_client_content = AsyncMock(return_value=True)
    svc = FormFillingService(live_ai=live_ai, text_ai=text_ai)
    return svc, live_ai, text_ai


def _ids_in_payload(payload) -> set:
    """Extract the field_ids the ValidatorService rendered into this window's
    request body (the fresh_tail JSON), so a side_effect can key a verdict on which
    window is being validated."""
    import json
    tail = "".join(payload.get("fresh_tail", []))
    # fresh_tail is "FIELDS:\n<json>"; parse the json part.
    try:
        blob = tail.split("\n", 1)[1]
        data = json.loads(blob)
        return {f.get("field_id") for f in data.get("fields", []) if isinstance(f, dict)}
    except Exception:
        return set()


# Overlapping windows (size 3, stride 2 for the test) over f1..f5. The pair
# (f2, f3) sits in BOTH windows -- a real conflict there is structural duplication.
_W1 = [
    {"field_id": "f1", "name": "F1", "value": "a", "steered": False},
    {"field_id": "f2", "name": "West Virginia", "value": "West Virginia", "steered": False},
    {"field_id": "f3", "name": "ZIP", "value": "50301", "steered": False},
]
_W2 = [
    {"field_id": "f3", "name": "ZIP", "value": "50301", "steered": False},
    {"field_id": "f4", "name": "F4", "value": "d", "steered": False},
    {"field_id": "f2", "name": "West Virginia", "value": "West Virginia", "steered": False},
]


@pytest.mark.asyncio
async def test_overlapping_windows_same_conflict_dedupes_to_one_steer():
    """Both windows span (f2, f3) and both report the SAME conflict; after batch
    dedupe by field-id set, exactly one conflict survives and one steer fires."""
    conflict = {"field_ids": ["f2", "f3"], "reason": "state/ZIP mismatch"}

    async def _validate(payload):
        ids = _ids_in_payload(payload)
        # Both windows contain f2 and f3, so both return the conflict.
        if {"f2", "f3"} <= ids:
            return {"conflicts": [dict(conflict)]}
        return {"conflicts": []}

    svc, live_ai, text_ai = _service()
    text_ai.validate = AsyncMock(side_effect=_validate)

    returned = await svc.handle_validation_windows([_W1, _W2])

    # Exactly ONE conflict returned (deduped). W3: REPORT-ONLY -- the windows path
    # NO LONGER injects a steer (the client enqueues + drains). The returned conflict
    # carries field_ids + reason + a field_names rider.
    assert len(returned["conflicts"]) == 1
    conflict_out = returned["conflicts"][0]
    assert set(conflict_out["field_ids"]) == {"f2", "f3"}
    # W3: the field_names id->name rider is populated from the union fields (the
    # names _W1/_W2 carry), so the client's drain payload has the names the steer
    # composer needs. This is a load-bearing wire contract -- pin its content.
    assert conflict_out["field_names"] == {"f2": "West Virginia", "f3": "ZIP"}
    live_ai.send_client_content.assert_not_awaited()
    # The two validate calls (one per window) both ran.
    assert text_ai.validate.await_count == 2


@pytest.mark.asyncio
async def test_dedupe_is_order_insensitive_on_field_ids():
    """Two windows report the conflict with the field_ids in DIFFERENT order
    (['f2','f3'] vs ['f3','f2']); the frozenset key collapses them to one."""
    async def _validate(payload):
        ids = _ids_in_payload(payload)
        if "f1" in ids:  # window 1
            return {"conflicts": [{"field_ids": ["f2", "f3"], "reason": "a"}]}
        if "f4" in ids:  # window 2
            return {"conflicts": [{"field_ids": ["f3", "f2"], "reason": "b (dup)"}]}
        return {"conflicts": []}

    svc, live_ai, text_ai = _service()
    text_ai.validate = AsyncMock(side_effect=_validate)

    returned = await svc.handle_validation_windows([_W1, _W2])
    assert len(returned["conflicts"]) == 1  # order-insensitive collapse
    live_ai.send_client_content.assert_not_awaited()  # W3: report-only, no steer here


@pytest.mark.asyncio
async def test_distinct_conflicts_across_windows_both_survive():
    """Different field-id sets are NOT deduped -- each real conflict rides the one
    combined steer."""
    async def _validate(payload):
        ids = _ids_in_payload(payload)
        if "f1" in ids:  # window 1
            return {"conflicts": [{"field_ids": ["f2", "f3"], "reason": "geo"}]}
        if "f4" in ids:  # window 2
            return {"conflicts": [{"field_ids": ["f4"], "reason": "future DOB"}]}
        return {"conflicts": []}

    svc, live_ai, text_ai = _service()
    text_ai.validate = AsyncMock(side_effect=_validate)

    returned = await svc.handle_validation_windows([_W1, _W2])
    keys = {frozenset(c["field_ids"]) for c in returned["conflicts"]}
    assert keys == {frozenset({"f2", "f3"}), frozenset({"f4"})}
    live_ai.send_client_content.assert_not_awaited()  # W3: report-only, drained later


@pytest.mark.asyncio
async def test_one_window_failing_open_does_not_block_the_others():
    """A window whose validate RAISES fails open (empty) without dropping the batch;
    the other window's conflict still surfaces."""
    async def _validate(payload):
        ids = _ids_in_payload(payload)
        if "f1" in ids:  # window 1 raises -> fail-open
            raise RuntimeError("window 1 boom")
        # window 2 returns a conflict
        return {"conflicts": [{"field_ids": ["f4"], "reason": "bad"}]}

    svc, live_ai, text_ai = _service()
    text_ai.validate = AsyncMock(side_effect=_validate)

    returned = await svc.handle_validation_windows([_W1, _W2])
    assert [c["field_ids"] for c in returned["conflicts"]] == [["f4"]]
    live_ai.send_client_content.assert_not_awaited()  # W3: report-only


@pytest.mark.asyncio
async def test_one_window_timeout_fails_open(monkeypatch):
    """A hung window fails open at VALIDATOR_TIMEOUT_SEC without blocking the batch."""
    async def _validate(payload):
        ids = _ids_in_payload(payload)
        if "f1" in ids:  # window 1 hangs
            await asyncio.sleep(10)
        return {"conflicts": [{"field_ids": ["f4"], "reason": "bad"}]}

    svc, live_ai, text_ai = _service()
    text_ai.validate = AsyncMock(side_effect=_validate)
    monkeypatch.setattr(svc._settings, "VALIDATOR_TIMEOUT_SEC", 0.05)

    returned = await svc.handle_validation_windows([_W1, _W2])
    assert [c["field_ids"] for c in returned["conflicts"]] == [["f4"]]


@pytest.mark.asyncio
async def test_already_steered_field_suppressed_across_windows():
    """A field marked steered in ANY window suppresses its conflict over the union
    (per-field max-resteer bound, contract 3)."""
    w1 = [
        {"field_id": "f2", "name": "State", "value": "WV", "steered": True},
        {"field_id": "f3", "name": "ZIP", "value": "50301", "steered": False},
    ]
    w2 = [
        {"field_id": "f2", "name": "State", "value": "WV", "steered": False},
        {"field_id": "f3", "name": "ZIP", "value": "50301", "steered": False},
    ]
    svc, live_ai, text_ai = _service()
    text_ai.validate = AsyncMock(
        return_value={"conflicts": [{"field_ids": ["f2", "f3"], "reason": "x"}]}
    )
    returned = await svc.handle_validation_windows([w1, w2])
    # f2 is steered in w1 -> the union treats it steered -> conflict suppressed.
    assert returned == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_or_bad_windows_is_all_clear():
    svc, live_ai, text_ai = _service()
    text_ai.validate = AsyncMock(return_value={"conflicts": []})
    assert await svc.handle_validation_windows([]) == {"conflicts": []}
    assert await svc.handle_validation_windows("not-a-list") == {"conflicts": []}
    assert await svc.handle_validation_windows([[], []]) == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_text_ai_is_all_clear():
    svc = FormFillingService(live_ai=MagicMock(), text_ai=None)
    assert await svc.handle_validation_windows([_W1, _W2]) == {"conflicts": []}


@pytest.mark.asyncio
async def test_concurrency_is_bounded_by_the_config_cap(monkeypatch):
    """VALIDATOR_MAX_CONCURRENT_WINDOWS caps how many windows validate at once. With
    the cap at 2 and 5 windows, at most 2 run concurrently."""
    svc, _, text_ai = _service()
    monkeypatch.setattr(svc._settings, "VALIDATOR_MAX_CONCURRENT_WINDOWS", 2)

    in_flight = 0
    peak = 0

    async def _validate(payload):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return {"conflicts": []}

    text_ai.validate = AsyncMock(side_effect=_validate)
    windows = [[{"field_id": f"f{i}", "name": "N", "value": "v", "steered": False}]
               for i in range(5)]
    await svc.handle_validation_windows(windows)
    assert peak <= 2
    assert text_ai.validate.await_count == 5


# --------------------------------------------------------------------------- #
# Pure-helper unit tests (dedupe / union) -- no async, no model.
# --------------------------------------------------------------------------- #

def test_dedupe_by_field_set_collapses_same_set():
    dedupe = FormFillingService._dedupe_conflicts_by_field_set
    out = dedupe([
        {"field_ids": ["a", "b"], "reason": "first"},
        {"field_ids": ["b", "a"], "reason": "dup, dropped"},
        {"field_ids": ["c"], "reason": "distinct"},
    ])
    assert len(out) == 2
    assert out[0]["reason"] == "first"  # first occurrence wins
    keys = {frozenset(c["field_ids"]) for c in out}
    assert keys == {frozenset({"a", "b"}), frozenset({"c"})}


def test_dedupe_drops_malformed_conflicts():
    dedupe = FormFillingService._dedupe_conflicts_by_field_set
    out = dedupe([
        {"field_ids": [], "reason": "empty"},
        {"reason": "no field_ids"},
        "not-a-dict",
        {"field_ids": ["a"], "reason": "kept"},
    ])
    assert out == [{"field_ids": ["a"], "reason": "kept"}]


def test_union_window_fields_dedups_and_ors_steered():
    union = FormFillingService._union_window_fields
    out = union([
        [{"field_id": "a", "name": "A", "value": "1", "steered": False},
         {"field_id": "b", "name": "B", "value": "2", "steered": True}],
        [{"field_id": "a", "name": "A", "value": "1", "steered": True},  # a steered here
         {"field_id": "c", "name": "C", "value": "3", "steered": False}],
    ])
    by_id = {f["field_id"]: f for f in out}
    assert set(by_id) == {"a", "b", "c"}
    assert by_id["a"]["steered"] is True   # OR across windows
    assert by_id["b"]["steered"] is True
    assert by_id["c"]["steered"] is False
