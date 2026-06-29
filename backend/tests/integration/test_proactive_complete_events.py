"""B4 (bd polyglot-pdf-jnjj.16): backend receives the proactive section_complete /
form_complete events and acks them.

The frontend emits these at section/form boundaries (the contract-2 field payload
rides each event); B4's backend job is to RECEIVE and ACK only (exit criterion 1)
-- feeding the payload to the validator + the verdict/steer is B5 (jnjj.17). These
tests drive `_handle_fill_session`'s control-message loop with a mock WebSocket
that yields one event then disconnects, and assert the ack goes out with no
validator/Gemini side effect (criterion 2: no double-fire / no premature B5 work).

PII (contract 6): the new log events carry field_count + section_id only, never
the `fields`/values. The repo-wide test_no_pii_logging sweep covers
websocket_routes.py by default; this file adds a direct count-only assertion.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from backend.routes.websocket_routes import _handle_fill_session


def _mock_service():
    """A FormFillingService double: every awaited method is a no-op AsyncMock so
    start_session / end_session / stream_audio do nothing. We assert NONE of the
    validator/steer-bearing methods are touched by the B4 receive arms."""
    svc = MagicMock(name="form_filling_service")
    svc.start_session = AsyncMock()
    svc.end_session = AsyncMock()
    svc.stream_audio = AsyncMock()
    return svc


def _ws_yielding(messages: list[dict]):
    """A WebSocket double whose receive() yields each queued frame, then a
    websocket.disconnect to break the loop."""
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    queue = list(messages) + [{"type": "websocket.disconnect"}]
    ws.receive = AsyncMock(side_effect=queue)
    return ws


async def _run(messages: list[dict]):
    ws = _ws_yielding(messages)
    svc = _mock_service()
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
async def test_section_complete_is_acked():
    _, svc, sent = await _run([
        {"text": json.dumps({
            "type": "section_complete",
            "section_id": "addr_section",
            "fields": [
                {"field_id": "addr_state", "name": "State", "value": "WV", "steered": False},
                {"field_id": "addr_zip", "name": "ZIP", "value": "50301", "steered": False},
            ],
        })},
    ])
    assert {"type": "section_complete_ack"} in sent
    # B4 must NOT run the validator or inject a steer -- that is B5.
    assert not svc.method_calls or all(
        "validate" not in str(c) and "steer" not in str(c) for c in svc.method_calls
    )


@pytest.mark.asyncio
async def test_form_complete_is_acked():
    _, _, sent = await _run([
        {"text": json.dumps({
            "type": "form_complete",
            "fields": [
                {"field_id": "addr_state", "name": "State", "value": "WV", "steered": False},
            ],
        })},
    ])
    assert {"type": "form_complete_ack"} in sent


@pytest.mark.asyncio
async def test_events_tolerate_missing_or_bad_fields():
    """A malformed payload (fields absent or non-list) must still ack, never 500."""
    _, _, sent = await _run([
        {"text": json.dumps({"type": "section_complete", "section_id": "s"})},  # no fields
        {"text": json.dumps({"type": "form_complete", "fields": "not-a-list"})},
    ])
    assert {"type": "section_complete_ack"} in sent
    assert {"type": "form_complete_ack"} in sent


@pytest.mark.asyncio
async def test_section_complete_does_not_collide_with_legacy_section_completed():
    """The new proactive `section_complete` and the legacy reactive
    `section_completed` are DISTINCT: each produces its OWN ack, not the other's."""
    _, _, sent = await _run([
        {"text": json.dumps({"type": "section_completed", "next_section": "s2"})},
        {"text": json.dumps({"type": "section_complete", "section_id": "s1", "fields": []})},
    ])
    types = [m.get("type") for m in sent]
    assert "section_completed_ack" in types  # legacy reactive
    assert "section_complete_ack" in types   # new proactive
    # They are different ack types -- no conflation.
    assert types.count("section_complete_ack") == 1
    assert types.count("section_completed_ack") == 1


@pytest.mark.asyncio
async def test_no_pii_in_proactive_complete_logs():
    """The receive arms log field_count + section_id only -- never field values."""
    import structlog.testing

    with structlog.testing.capture_logs() as logs:
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
        ])

    events = [e for e in logs if e.get("event") in
              ("section_complete_received", "form_complete_received")]
    assert events, "expected the new log events to fire"
    for e in events:
        blob = json.dumps(e, default=str)
        assert "SECRET_VALUE_WV" not in blob
        assert "SECRET_SSN_123" not in blob
        assert "field_count" in e
