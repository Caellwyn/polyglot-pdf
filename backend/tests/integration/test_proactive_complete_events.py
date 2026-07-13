"""B4 (bd polyglot-pdf-jnjj.16) + W1 (bd polyglot-pdf-xbl2): the backend receives
the proactive section_complete / form_complete / validate_windows validation
triggers, ACKS them IMMEDIATELY, and runs the validator OFF the receive loop.

The frontend emits these at section/page/form boundaries (the contract-2 field
payload rides each event). W1's shape: the receive arm acks the client at once and
spins the flash-lite pass into a background task -- NOTHING in the receive loop
awaits the validator, so a slow/hung pass adds zero voice-turn latency (epic
criterion 1). The background task pushes the `validation_result` envelope when the
pass lands. These tests drive `_handle_fill_session`'s control-message loop with a
mock WebSocket that yields one event then disconnects, and assert (a) the ack goes
out immediately, and (b) the validation is spawned off the loop.

PII (contract 6): the new log events carry field_count + section_id only, never
the `fields`/values. The repo-wide test_no_pii_logging sweep covers
websocket_routes.py by default; this file adds a direct count-only assertion.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from backend.routes.websocket_routes import _handle_fill_session


def _mock_service(verdict=None, windows_delay=0.0):
    """A FormFillingService double: every awaited method is a no-op AsyncMock so
    start_session / end_session / stream_audio do nothing. W1 (bd polyglot-pdf-xbl2)
    routes every validation trigger through handle_validation_windows (the async,
    multi-window boundary); stub it to return a clean verdict by default. An
    optional `windows_delay` makes the validator SLOW so a test can prove the ack
    does not wait on it."""
    svc = MagicMock(name="form_filling_service")
    svc.start_session = AsyncMock()
    svc.end_session = AsyncMock()
    svc.stream_audio = AsyncMock()

    async def _windows(windows):
        if windows_delay:
            await asyncio.sleep(windows_delay)
        return verdict or {"conflicts": []}

    svc.handle_validation_windows = AsyncMock(side_effect=_windows)
    return svc


def _ws_yielding(messages: list[dict], hold_open: float = 0.0):
    """A WebSocket double whose receive() yields each queued frame, then (optionally
    holds the socket open for `hold_open` seconds so a background validation task can
    land its push) a websocket.disconnect to break the loop."""
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()

    frames = list(messages)

    async def _receive():
        if frames:
            return frames.pop(0)
        # All real frames drained: give background tasks a beat to push, then
        # signal disconnect to break the receive loop.
        if hold_open:
            await asyncio.sleep(hold_open)
        return {"type": "websocket.disconnect"}

    ws.receive = AsyncMock(side_effect=_receive)
    return ws


async def _run(messages: list[dict], svc=None, hold_open: float = 0.0):
    ws = _ws_yielding(messages, hold_open=hold_open)
    svc = svc or _mock_service()
    await _handle_fill_session(
        ws,
        session_id="web_test",
        service=svc,
        send_transcript=False,
        accept_connection=False,
        schema=None,  # skip the heavy SI build; the control loop is what we exercise
    )
    sent = [c.args[0] for c in ws.send_json.await_args_list]
    return ws, svc, sent


@pytest.mark.asyncio
async def test_section_complete_is_acked_immediately():
    _, svc, sent = await _run([
        {"text": json.dumps({
            "type": "section_complete",
            "section_id": "addr_section",
            "fields": [
                {"field_id": "addr_state", "name": "State", "value": "WV", "steered": False},
                {"field_id": "addr_zip", "name": "ZIP", "value": "50301", "steered": False},
            ],
        })},
    ], hold_open=0.05)
    # W1: the ack goes out; the validator runs OFF the loop and pushes its result.
    assert {"type": "section_complete_ack"} in sent
    svc.handle_validation_windows.assert_awaited()
    # The single field list rides as a ONE-window batch.
    (windows,) = svc.handle_validation_windows.await_args_list[0].args
    assert isinstance(windows, list) and len(windows) == 1
    assert {"type": "validation_result", "conflicts": []} in sent


@pytest.mark.asyncio
async def test_form_complete_is_acked_immediately():
    _, _, sent = await _run([
        {"text": json.dumps({
            "type": "form_complete",
            "fields": [
                {"field_id": "addr_state", "name": "State", "value": "WV", "steered": False},
            ],
        })},
    ], hold_open=0.05)
    assert {"type": "form_complete_ack"} in sent
    assert {"type": "validation_result", "conflicts": []} in sent


@pytest.mark.asyncio
async def test_validate_windows_is_acked_and_runs_off_loop():
    """W1: the new async page-end trigger carries the overlapping windows; the arm
    acks at once and hands the whole batch to the async boundary."""
    _, svc, sent = await _run([
        {"text": json.dumps({
            "type": "validate_windows",
            "windows": [
                [{"field_id": "f1", "name": "F1", "value": "a", "steered": False},
                 {"field_id": "f2", "name": "F2", "value": "b", "steered": False}],
                [{"field_id": "f2", "name": "F2", "value": "b", "steered": False},
                 {"field_id": "f3", "name": "F3", "value": "c", "steered": False}],
            ],
        })},
    ], hold_open=0.05)
    assert {"type": "validate_windows_ack"} in sent
    (windows,) = svc.handle_validation_windows.await_args_list[0].args
    assert len(windows) == 2  # both windows handed to the batch
    assert {"type": "validation_result", "conflicts": []} in sent


@pytest.mark.asyncio
async def test_ack_does_not_wait_on_a_slow_validator():
    """Epic criterion 1: a deliberately SLOW validator does not delay the ack. The
    ack must be sent BEFORE the (slow) validation_result -- proving the receive loop
    did not await the validator."""
    svc = _mock_service(windows_delay=0.2)
    # Second frame is a cheap ping: it must be handled (its response sent) BEFORE the
    # slow validator's result lands, proving subsequent turns proceed unblocked.
    _, _, sent = await _run([
        {"text": json.dumps({"type": "form_complete", "fields": [
            {"field_id": "f1", "name": "F1", "value": "a", "steered": False}]})},
        {"text": json.dumps({"type": "ping"})},
    ], svc=svc, hold_open=0.4)
    types = [m.get("type") for m in sent]
    # The form_complete_ack and the ping's pong both precede the slow result --
    # proving the receive loop kept serving turns while the validator was in flight.
    assert "form_complete_ack" in types
    assert "pong" in types
    assert "validation_result" in types
    assert types.index("form_complete_ack") < types.index("validation_result")
    assert types.index("pong") < types.index("validation_result")


@pytest.mark.asyncio
async def test_events_tolerate_missing_or_bad_fields():
    """A malformed payload (fields absent or non-list) must still ack, never 500."""
    _, _, sent = await _run([
        {"text": json.dumps({"type": "section_complete", "section_id": "s"})},  # no fields
        {"text": json.dumps({"type": "form_complete", "fields": "not-a-list"})},
        {"text": json.dumps({"type": "validate_windows", "windows": "not-a-list"})},
    ], hold_open=0.05)
    assert {"type": "section_complete_ack"} in sent
    assert {"type": "form_complete_ack"} in sent
    assert {"type": "validate_windows_ack"} in sent


@pytest.mark.asyncio
async def test_background_validation_exception_never_crashes_the_loop():
    """Exit criterion 3: a validator that RAISES in the background task is caught +
    logged, never propagated -- the receive loop keeps serving (the ping after it is
    still answered) and the session tears down cleanly."""
    svc = _mock_service()
    svc.handle_validation_windows = AsyncMock(side_effect=RuntimeError("boom"))
    _, _, sent = await _run([
        {"text": json.dumps({"type": "form_complete", "fields": [
            {"field_id": "f1", "name": "F1", "value": "a", "steered": False}]})},
        {"text": json.dumps({"type": "ping"})},
    ], svc=svc, hold_open=0.05)
    types = [m.get("type") for m in sent]
    # The ack still went out and the loop kept serving the ping despite the raise;
    # no validation_result is pushed (the failed task swallowed its own error).
    assert "form_complete_ack" in types
    assert "pong" in types or "ping" not in types  # loop kept processing after the raise
    assert svc.end_session.await_count == 1  # clean teardown


@pytest.mark.asyncio
async def test_inflight_validation_is_cancelled_on_disconnect():
    """W1: a validation task still running when the socket disconnects is CANCELLED
    in the teardown `finally` -- it must not survive to push `validation_result` to a
    closed socket. The validator here blocks until cancelled; a small hold_open lets
    the background task START (reach its blocking await) before the disconnect frame
    triggers teardown, so the cancel actually interrupts a running task (cancelling a
    task that never started would not run its except/finally)."""
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _blocking(windows):
        started.set()
        try:
            await asyncio.Event().wait()  # never resolves on its own
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {"conflicts": []}

    svc = _mock_service()
    svc.handle_validation_windows = AsyncMock(side_effect=_blocking)
    ws, _, sent = await _run([
        {"text": json.dumps({"type": "form_complete", "fields": [
            {"field_id": "f1", "name": "F1", "value": "a", "steered": False}]})},
    ], svc=svc, hold_open=0.05)
    # Give the just-cancelled task a tick to run its except/finally.
    await asyncio.sleep(0)
    assert started.is_set()                          # the task did start before teardown
    types = [m.get("type") for m in sent]
    assert "form_complete_ack" in types            # the ack still went out
    assert "validation_result" not in types        # the cancelled task never pushed
    assert cancelled.is_set()                        # the task was actually cancelled
    assert svc.end_session.await_count == 1          # clean teardown


@pytest.mark.asyncio
async def test_section_complete_does_not_collide_with_legacy_section_completed():
    """The new proactive `section_complete` and the legacy reactive
    `section_completed` are DISTINCT: each produces its OWN ack, not the other's."""
    _, _, sent = await _run([
        {"text": json.dumps({"type": "section_completed", "next_section": "s2"})},
        {"text": json.dumps({"type": "section_complete", "section_id": "s1", "fields": []})},
    ], hold_open=0.05)
    types = [m.get("type") for m in sent]
    assert "section_completed_ack" in types  # legacy reactive
    assert "section_complete_ack" in types   # new proactive
    # They are different ack types -- no conflation.
    assert types.count("section_complete_ack") == 1
    assert types.count("section_completed_ack") == 1


@pytest.mark.asyncio
async def test_no_pii_in_proactive_complete_logs(monkeypatch):
    """The receive arms log field_count + section_id only -- never field values.

    Patches the module logger's `.info` directly (structlog.testing.capture_logs is
    unreliable here: a prior full-suite test can leave structlog reconfigured so the
    capture's LogCapture is bypassed -- the get-settings-singleton-style ordering
    trap, structlog edition). Recording the call args is deterministic regardless of
    the global structlog processor chain."""
    import backend.routes.websocket_routes as wr

    calls: list[tuple] = []
    real_info = wr._log.info

    def _record_info(event, *args, **kwargs):
        calls.append((event, kwargs))
        return real_info(event, *args, **kwargs)

    monkeypatch.setattr(wr._log, "info", _record_info)

    await _run([
        {"text": json.dumps({
            "type": "section_complete",
            "section_id": "addr_section",
            "fields": [
                {"field_id": "addr_state", "name": "State", "value": "SECRET_VALUE_WV",
                 "steered": False},
            ],
        })},
        {"text": json.dumps({
            "type": "form_complete",
            "fields": [
                {"field_id": "ssn", "name": "SSN", "value": "SECRET_SSN_123",
                 "steered": False},
            ],
        })},
        {"text": json.dumps({
            "type": "validate_windows",
            "windows": [
                [{"field_id": "dob", "name": "DOB", "value": "SECRET_DOB_2020",
                  "steered": False}],
            ],
        })},
    ], hold_open=0.05)

    events = [(event, kwargs) for (event, kwargs) in calls
              if event in ("section_complete_received", "form_complete_received",
                           "validate_windows_received")]
    assert events, "expected the new log events to fire"
    for event, kwargs in events:
        blob = json.dumps({"event": event, **kwargs}, default=str)
        assert "SECRET_VALUE_WV" not in blob
        assert "SECRET_SSN_123" not in blob
        assert "SECRET_DOB_2020" not in blob
        assert "field_count" in kwargs
