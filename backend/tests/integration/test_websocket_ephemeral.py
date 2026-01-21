"""Integration-style tests for WebSocket `/ws/fill` handshake logic."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket

from backend.routes.websocket_routes import fill_form_from_schema


@pytest.fixture
def mock_websocket():
    """Provide a WebSocket double with the methods used by the handler."""
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_service():
    """Service dependency injected via Depends in production."""
    return MagicMock(name="form_filling_service")


@pytest.fixture
def handshake_message():
    return {
        "type": "handshake",
        "schema": {
            "source": "web",
            "form_metadata": {"title": "Contact Form", "url": "https://example.com"},
            "fields": [
                {"id": "email", "name": "Email", "type": "email", "required": True},
                {"id": "name", "name": "Full Name", "type": "text", "required": True},
            ],
        },
        "current_values": {}
    }


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_handshake_sends_session_ready(mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message):
    """Happy-path handshake should acknowledge and invoke the fill session helper."""
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="test-token")

    # Validate session_ready payload
    mock_websocket.send_json.assert_awaited()
    payloads = [args.args[0] for args in mock_websocket.send_json.await_args_list]
    session_ready = next((p for p in payloads if p.get("type") == "session_ready"), None)
    assert session_ready is not None
    assert session_ready["ephemeral"] is True
    assert session_ready["session_id"].startswith("web_")

    # Ensure helper is invoked with parsed handshake data
    mock_fill_session.assert_awaited_once()
    helper_args, helper_kwargs = mock_fill_session.await_args
    assert helper_args[0] is mock_websocket
    assert helper_args[2] is mock_service
    assert helper_kwargs["schema"] == handshake_message["schema"]
    assert helper_kwargs["current_values"] == handshake_message["current_values"]


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_handshake_passes_reconnect_values(mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message):
    reconnect = handshake_message | {
        "current_values": {
            "email": {"value": "reconnect@example.com", "confirmed": True}
        }
    }
    mock_websocket.receive_text.return_value = json.dumps(reconnect)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="test-token")

    mock_fill_session.assert_awaited_once()
    _, helper_kwargs = mock_fill_session.await_args
    assert helper_kwargs["current_values"]["email"]["value"] == "reconnect@example.com"
    assert helper_kwargs["current_values"]["email"]["confirmed"] is True


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_missing_schema_returns_error(mock_fill_session, mock_verify_token, mock_websocket, mock_service):
    mock_websocket.receive_text.return_value = json.dumps({"type": "handshake"})

    await fill_form_from_schema(mock_websocket, service=mock_service, token="test-token")

    mock_fill_session.assert_not_called()
    mock_websocket.send_json.assert_awaited()
    error_payload = mock_websocket.send_json.await_args_list[0].args[0]
    assert error_payload["type"] == "error"
    assert error_payload["code"] == "invalid_schema"
    mock_websocket.close.assert_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_missing_current_values_defaults_to_empty(mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message):
    handshake = dict(handshake_message)
    handshake.pop("current_values", None)
    mock_websocket.receive_text.return_value = json.dumps(handshake)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="test-token")

    _, helper_kwargs = mock_fill_session.await_args
    assert helper_kwargs["current_values"] == {}

