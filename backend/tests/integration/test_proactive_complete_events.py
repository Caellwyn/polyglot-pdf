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
    # W3 (bd polyglot-pdf-pr3i): the drain arm routes through handle_drain_findings;
    # echo the conflicts back as "delivered" by default.
    async def _drain(conflicts):
        return {"conflicts": conflicts if isinstance(conflicts, list) else []}
    svc.handle_drain_findings = AsyncMock(side_effect=_drain)
    # W6 (bd polyglot-pdf-gbus): the form_complete arm now routes through
    # handle_form_complete_pro (the pro pass). Stub it clean by default; the
    # windows_delay knob also slows it so the slow-validator ack test still holds.
    async def _pro(fields):
        if windows_delay:
            await asyncio.sleep(windows_delay)
        return verdict or {"conflicts": []}
    svc.handle_form_complete_pro = AsyncMock(side_effect=_pro)
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


async def _run(messages: list[dict], svc=None, hold_open: float = 0.0,
               link_jti=None):
    ws = _ws_yielding(messages, hold_open=hold_open)
    svc = svc or _mock_service()
    await _handle_fill_session(
        ws,
        session_id="web_test",
        service=svc,
        send_transcript=False,
        accept_connection=False,
        schema=None,  # skip the heavy SI build; the control loop is what we exercise
        link_jti=link_jti,  # set for a CLIENT-LINK session (bd polyglot-pdf-ugm6)
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
async def test_drain_findings_is_acked_and_pushes_result_off_loop():
    """W3 (bd polyglot-pdf-pr3i): the drain arm acks immediately, hands the queued
    conflicts to handle_drain_findings off the receive loop, and pushes the delivered
    conflicts back as drain_findings_result."""
    conflicts = [{"field_ids": ["a", "b"], "reason": "mismatch",
                  "field_names": {"a": "A", "b": "B"}}]
    _, svc, sent = await _run([
        {"text": json.dumps({"type": "drain_findings", "conflicts": conflicts})},
    ], hold_open=0.05)
    assert {"type": "drain_findings_ack"} in sent
    (passed,) = svc.handle_drain_findings.await_args_list[0].args
    assert passed == conflicts
    # The delivered conflicts ride back so the client marks steered + consumes.
    results = [m for m in sent if m.get("type") == "drain_findings_result"]
    assert len(results) == 1
    assert results[0]["conflicts"] == conflicts


@pytest.mark.asyncio
async def test_drain_findings_tolerates_bad_conflicts():
    """A malformed drain payload (conflicts absent or non-list) must still ack."""
    _, _, sent = await _run([
        {"text": json.dumps({"type": "drain_findings"})},              # no conflicts
        {"text": json.dumps({"type": "drain_findings", "conflicts": "nope"})},
    ], hold_open=0.05)
    assert sent.count({"type": "drain_findings_ack"}) == 2


@pytest.mark.asyncio
async def test_drain_findings_pushes_empty_result_even_when_handler_raises():
    """W3: handle_drain_findings raising must STILL push a drain_findings_result
    (delivered=[]) so the client's drainInFlight guard clears -- a missing result
    would stall the client's queue until reconnect (Opus outer-review finding). The
    empty result means the client keeps the finding queued to retry but is unblocked.
    """
    svc = _mock_service()
    svc.handle_drain_findings = AsyncMock(side_effect=RuntimeError("compose boom"))
    _, _, sent = await _run([
        {"text": json.dumps({"type": "drain_findings", "conflicts": [
            {"field_ids": ["a"], "reason": "x", "field_names": {"a": "A"}}]})},
        {"text": json.dumps({"type": "ping"})},
    ], svc=svc, hold_open=0.05)
    assert {"type": "drain_findings_ack"} in sent
    # The result STILL went out, empty (the raise was swallowed).
    assert {"type": "drain_findings_result", "conflicts": []} in sent
    # The loop kept serving despite the raise.
    assert any(m.get("type") == "pong" for m in sent)


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
    still answered) and the session tears down cleanly. W6: form_complete now runs
    the pro pass, so raise handle_form_complete_pro (the code path _run_pro_complete_
    and_push's crash-safe try/except now guards); a validate_windows frame also
    raises handle_validation_windows so BOTH background runners' guards are covered."""
    svc = _mock_service()
    svc.handle_form_complete_pro = AsyncMock(side_effect=RuntimeError("pro boom"))
    svc.handle_validation_windows = AsyncMock(side_effect=RuntimeError("windows boom"))
    _, _, sent = await _run([
        {"text": json.dumps({"type": "form_complete", "fields": [
            {"field_id": "f1", "name": "F1", "value": "a", "steered": False}]})},
        {"text": json.dumps({"type": "validate_windows", "windows": [
            [{"field_id": "f1", "name": "F1", "value": "a", "steered": False}]]})},
        {"text": json.dumps({"type": "ping"})},
    ], svc=svc, hold_open=0.05)
    types = [m.get("type") for m in sent]
    # Both acks went out and the loop kept serving the ping despite the raises;
    # no validation_result is pushed (the failed tasks swallowed their own errors).
    assert "form_complete_ack" in types
    assert "validate_windows_ack" in types
    assert "pong" in types  # loop kept processing after both raises
    assert "validation_result" not in types
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

    async def _blocking(fields):
        started.set()
        try:
            await asyncio.Event().wait()  # never resolves on its own
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {"conflicts": []}

    svc = _mock_service()
    # W6: form_complete now routes through handle_form_complete_pro; block THAT.
    svc.handle_form_complete_pro = AsyncMock(side_effect=_blocking)
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


@pytest.mark.asyncio
async def test_a_COMPLETED_client_link_session_BURNS_the_link(monkeypatch):
    """ONE COMPLETION PER LINK, from the other end (bd polyglot-pdf-ugm6).

    Nothing called complete_link before fresh-eyes r1 -- so a link could
    never actually become "used" and the one-time guarantee could never take
    effect no matter how well the open path was guarded.

    THIS TEST'S ABSENCE ALSO HID A NameError: the first version of the burn
    reached for `claims`, which lives in fill_form_from_schema -- a DIFFERENT
    function -- so every completed session raised at runtime. Six unrelated
    tests in this file went red and pointed at it; nothing pinned the burn
    itself. Now it does.

    Mutation: drop the complete_link call -- red.
    """
    burned = []
    monkeypatch.setattr("backend.routes.websocket_routes.complete_link",
                        lambda jti: burned.append(jti))

    await _run([
        {"text": json.dumps({"type": "form_complete", "fields": []})},
    ], hold_open=0.05, link_jti="jti-abc")

    assert burned == ["jti-abc"]


@pytest.mark.asyncio
async def test_an_ABANDONED_client_link_session_does_NOT_burn_the_link(
    monkeypatch,
):
    """A dropped connection, a closed laptop, or a client coming back after
    lunch must NOT consume their one chance at the form. Abandonment is the
    COMMON case on a 40-minute immigration form; burning there would strand a
    client mid-intake with no recourse but to phone the firm.

    Mutation: burn unconditionally (drop the session_completed guard) -- red.
    """
    burned = []
    monkeypatch.setattr("backend.routes.websocket_routes.complete_link",
                        lambda jti: burned.append(jti))

    # No form_complete message -- the socket just ends.
    await _run([], hold_open=0.05, link_jti="jti-abc")

    assert burned == []


@pytest.mark.asyncio
async def test_a_STAFF_session_never_touches_the_link_store(monkeypatch):
    """link_jti is None for a staff session, so the burn must not fire (and
    must not raise on the None)."""
    burned = []
    monkeypatch.setattr("backend.routes.websocket_routes.complete_link",
                        lambda jti: burned.append(jti))

    await _run([
        {"text": json.dumps({"type": "form_complete", "fields": []})},
    ], hold_open=0.05, link_jti=None)

    assert burned == []
