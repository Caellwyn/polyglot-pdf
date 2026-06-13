"""Spec: the /ws/fill auth gate + connection lifecycle (bd polyglot-pdf-uov.9, T2.2).

The existing test_websocket_ephemeral.py mocks verify_token throughout and only
exercises the happy path, so the SECURITY-critical and lifecycle behaviors the
WS contract promises (docs/components/websocket-routing.md) were unspecified.
This module specs them, deriving each assertion from that doc + the route code:

  1. AUTH GATE -- verify_token is called BEFORE websocket.accept(); on failure the
     socket is closed with 1008 and NEITHER accepted NOR handed to the fill
     session. (A failed auth that accepted-then-closed, or that still started a
     session, is the regression this guards.)
  2. HANDSHAKE CLOSE CODES -- the doc pins specific close codes: bad JSON / not-an-
     object -> 1007, missing schema -> 1007, bad source -> 1008. The existing
     missing-schema test only asserts close() was awaited, not the CODE; these
     assert the exact code so a silent code change is caught.
  3. IDLE WATCHDOG -- on idle timeout the backend sends {"type":"idle_timeout",...}
     and THEN closes with 1000 (graceful), driving the REAL watchdog in
     _handle_fill_session (not a hand-rolled stand-in -- see the note on
     test_idle_timeout.py below).

NOTE on test_idle_timeout.py (a finding from this audit): that file's
"idle_timeout" tests do NOT invoke the route's watchdog -- they call
mock_ws.send_json/close themselves and assert the mock recorded their own call,
so they would stay green even if the watchdog were deleted. Filed as a finding
bead; the idle-watchdog spec here exercises the real coroutine instead.

These are route-level async unit tests with a mocked WebSocket/service (the same
double the sibling test uses); they import nothing live and run under the default
`pytest -m "not external"`.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket

from backend.routes.websocket_routes import (
    fill_form_from_schema,
    _handle_fill_session,
)


# --------------------------------------------------------------------------
# Fixtures (mirror test_websocket_ephemeral.py so the doubles behave the same)
# --------------------------------------------------------------------------
@pytest.fixture
def mock_websocket():
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.receive = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_service():
    return MagicMock(name="form_filling_service")


def _valid_handshake() -> dict:
    return {
        "type": "handshake",
        "schema": {
            "source": "web",
            "form_metadata": {"title": "Contact Form"},
            "fields": [{"id": "email", "name": "Email", "type": "email"}],
        },
        "current_values": {},
    }


# --------------------------------------------------------------------------
# 1. AUTH GATE -- verify_token before accept; failure -> close 1008, no session
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
@patch("backend.routes.websocket_routes.verify_token")
async def test_auth_failure_closes_1008_without_accepting(
    mock_verify_token, mock_fill_session, mock_websocket, mock_service
):
    """A token that fails verification closes with 1008 BEFORE accept, and never
    starts a fill session."""
    mock_verify_token.side_effect = Exception("invalid token")

    await fill_form_from_schema(mock_websocket, service=mock_service, token="bad-token")

    # Closed with the auth-failure code...
    mock_websocket.close.assert_awaited_once()
    _, close_kwargs = mock_websocket.close.await_args
    assert close_kwargs.get("code") == 1008
    # ...and the socket was NEVER accepted (close-before-accept is the contract).
    mock_websocket.accept.assert_not_awaited()
    # ...and no session was started with an unauthenticated socket.
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
@patch("backend.routes.websocket_routes.verify_token")
async def test_auth_runs_before_accept_on_success(
    mock_verify_token, mock_fill_session, mock_websocket, mock_service
):
    """On the happy path verify_token is still called, and accept happens only
    after it returns (the gate is on the path, not bypassed)."""
    order: list[str] = []
    mock_verify_token.side_effect = lambda *_a, **_k: order.append("verify")
    mock_websocket.accept.side_effect = lambda *_a, **_k: order.append("accept")
    mock_websocket.receive_text.return_value = json.dumps(_valid_handshake())

    await fill_form_from_schema(mock_websocket, service=mock_service, token="good-token")

    mock_verify_token.assert_called_once_with("good-token")
    # verify must precede accept in the actual call order.
    assert order[:2] == ["verify", "accept"], order
    mock_websocket.close.assert_not_awaited()


# --------------------------------------------------------------------------
# 2. HANDSHAKE CLOSE CODES -- exact codes per the WS-routing doc
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
@patch("backend.routes.websocket_routes.verify_token")
async def test_non_json_handshake_closes_1007(
    mock_verify_token, mock_fill_session, mock_websocket, mock_service
):
    """A first frame that is not valid JSON -> error + close 1007, no session."""
    mock_websocket.receive_text.return_value = "this is not json{"

    await fill_form_from_schema(mock_websocket, service=mock_service, token="t")

    mock_websocket.close.assert_awaited_once()
    _, kwargs = mock_websocket.close.await_args
    assert kwargs.get("code") == 1007
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
@patch("backend.routes.websocket_routes.verify_token")
async def test_non_object_handshake_closes_1007(
    mock_verify_token, mock_fill_session, mock_websocket, mock_service
):
    """A JSON first frame that decodes to a non-object (e.g. a list) -> 1007."""
    mock_websocket.receive_text.return_value = json.dumps(["not", "an", "object"])

    await fill_form_from_schema(mock_websocket, service=mock_service, token="t")

    mock_websocket.close.assert_awaited_once()
    _, kwargs = mock_websocket.close.await_args
    assert kwargs.get("code") == 1007
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
@patch("backend.routes.websocket_routes.verify_token")
async def test_missing_schema_closes_1007(
    mock_verify_token, mock_fill_session, mock_websocket, mock_service
):
    """A legacy handshake with no schema -> invalid_schema + close 1007. (The
    sibling test asserts only that close() was awaited; this pins the code.)"""
    mock_websocket.receive_text.return_value = json.dumps({"type": "handshake"})

    await fill_form_from_schema(mock_websocket, service=mock_service, token="t")

    mock_websocket.close.assert_awaited_once()
    _, kwargs = mock_websocket.close.await_args
    assert kwargs.get("code") == 1007
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
@patch("backend.routes.websocket_routes.verify_token")
async def test_bad_source_closes_1008(
    mock_verify_token, mock_fill_session, mock_websocket, mock_service
):
    """A schema whose source is neither web nor pdf -> invalid_schema + close 1008."""
    hs = _valid_handshake()
    hs["schema"]["source"] = "malicious"
    mock_websocket.receive_text.return_value = json.dumps(hs)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="t")

    mock_websocket.close.assert_awaited_once()
    _, kwargs = mock_websocket.close.await_args
    assert kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
@patch("backend.routes.websocket_routes.verify_token")
async def test_pdf_source_is_accepted(
    mock_verify_token, mock_fill_session, mock_websocket, mock_service
):
    """A 'pdf' source is explicitly allowed (PDF schemas are voice-fillable),
    so it must NOT be rejected like a bad source -- the session starts."""
    hs = _valid_handshake()
    hs["schema"]["source"] = "pdf"
    mock_websocket.receive_text.return_value = json.dumps(hs)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="t")

    mock_websocket.close.assert_not_awaited()
    mock_fill_session.assert_awaited_once()


# --------------------------------------------------------------------------
# 3. IDLE WATCHDOG -- the REAL watchdog in _handle_fill_session sends the
#    idle_timeout message and then closes 1000 (graceful). Driven with a
#    controllable clock + instant sleeps so no wall-clock time elapses.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idle_watchdog_sends_message_then_closes_1000(
    mock_websocket, mock_service, monkeypatch
):
    """Exercise the route's actual watchdog_task: with the last-receive clock
    held in the past, one watchdog tick must send {"type":"idle_timeout"} and
    THEN close the socket with code 1000 + reason 'Idle timeout'."""
    # The service surface _handle_fill_session touches before the receive loop.
    mock_service._is_resume_session = False
    mock_service.start_session = AsyncMock()
    mock_service.end_session = AsyncMock()

    # Drive the watchdog deterministically:
    #  - idle timeout = 5s (small);
    #  - asyncio.sleep inside the route yields instantly (no real wait);
    #  - time.time() jumps 10s past the start so (now - last_rx) > idle_timeout
    #    on the first tick.
    import backend.routes.websocket_routes as routes
    monkeypatch.setattr(routes.get_settings(), "WS_IDLE_TIMEOUT_SEC", 5, raising=False)

    clock = {"t": 1000.0}
    monkeypatch.setattr(routes.time, "time", lambda: clock["t"])

    real_sleep = asyncio.sleep

    async def fast_sleep(_seconds):
        # Advance the clock so the watchdog's idle check trips, but actually
        # yield ~0s so the test is fast and deterministic.
        clock["t"] += 10.0
        await real_sleep(0)

    monkeypatch.setattr(routes.asyncio, "sleep", fast_sleep)

    # receive() blocks until the watchdog closes the socket; once close() is
    # awaited we release it with a disconnect so the loop exits cleanly.
    closed = asyncio.Event()

    async def blocking_receive():
        await closed.wait()
        return {"type": "websocket.disconnect"}

    mock_websocket.receive.side_effect = blocking_receive
    mock_websocket.close.side_effect = lambda *_a, **_k: closed.set()

    await asyncio.wait_for(
        _handle_fill_session(
            mock_websocket,
            "web_test",
            mock_service,
            False,
            accept_connection=False,
            schema=None,
        ),
        timeout=5.0,
    )

    # The idle_timeout message was sent before the close.
    idle_msgs = [
        c.args[0]
        for c in mock_websocket.send_json.await_args_list
        if isinstance(c.args[0], dict) and c.args[0].get("type") == "idle_timeout"
    ]
    assert idle_msgs, "watchdog never sent an idle_timeout message"
    assert idle_msgs[0]["message"] == "Connection timed out due to inactivity"

    # And the socket was closed gracefully (1000) with the idle reason.
    close_calls = [
        c for c in mock_websocket.close.await_args_list
        if c.kwargs.get("code") == 1000
    ]
    assert close_calls, "watchdog never closed with code 1000"
    assert close_calls[0].kwargs.get("reason") == "Idle timeout"

    # Session cleanup ran in the finally block.
    mock_service.end_session.assert_awaited_once()
