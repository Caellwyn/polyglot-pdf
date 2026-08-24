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
    # bd polyglot-pdf-333: session_ready advertises the native-VAD mode so the
    # frontend can match the backend's turn-taking model.
    from backend.routes.websocket_routes import settings as _route_settings
    assert session_ready["native_vad"] == (not _route_settings.DISABLE_GEMINI_VAD)

    # Ensure helper is invoked with parsed handshake data
    mock_fill_session.assert_awaited_once()
    helper_args, helper_kwargs = mock_fill_session.await_args
    assert helper_args[0] is mock_websocket
    assert helper_args[2] is mock_service
    assert helper_kwargs["schema"] == handshake_message["schema"]
    assert helper_kwargs["current_values"] == handshake_message["current_values"]


@pytest.mark.asyncio
@pytest.mark.parametrize("disable_gemini_vad,expected_native_vad", [(True, False), (False, True)])
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_session_ready_native_vad_tracks_flag(
    mock_fill_session, mock_verify_token, mock_websocket, mock_service,
    handshake_message, monkeypatch, disable_gemini_vad, expected_native_vad,
):
    """session_ready.native_vad is the inverse of DISABLE_GEMINI_VAD (bd polyglot-pdf-333)."""
    from backend.routes import websocket_routes as _routes
    monkeypatch.setattr(_routes.settings, "DISABLE_GEMINI_VAD", disable_gemini_vad)
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="test-token")

    payloads = [args.args[0] for args in mock_websocket.send_json.await_args_list]
    session_ready = next((p for p in payloads if p.get("type") == "session_ready"), None)
    assert session_ready is not None
    assert session_ready["native_vad"] is expected_native_vad


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



# --- firm identity from the TOKEN, not the handshake (bd polyglot-pdf-xwlt) ---


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_firm_id_comes_from_the_verified_token_claim(
    mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message
):
    """The firm_id custom claim on the verified token reaches the session.

    Before bd xwlt the WS gate CALLED verify_token and threw the decoded
    claims away, so the voice path could not see firm identity at all.
    Mutation: revert `claims = verify_token(token)` to a bare call, or drop
    firm_id from the _handle_fill_session kwargs -- red.
    """
    mock_verify_token.return_value = {"uid": "staff-a", "firm_id": "firm-a"}
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="tok")

    assert mock_fill_session.await_args.kwargs["firm_id"] == "firm-a"


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_handshake_supplied_firm_id_is_IGNORED(
    mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message
):
    """A firm id a CLIENT can type is not an identity.

    The handshake is client-controlled, so a firm_id there must never become
    the telemetry key -- otherwise any signed-in user could bill their usage
    to another firm (or hide their own). Mutation: read firm_id from the
    handshake instead of the claims -- red.
    """
    mock_verify_token.return_value = {"uid": "legacy-user"}  # NO firm claim
    spoofed = dict(handshake_message, firm_id="firm-victim")
    mock_websocket.receive_text.return_value = json.dumps(spoofed)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="tok")

    assert mock_fill_session.await_args.kwargs["firm_id"] is None


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_session_with_no_firm_claim_still_runs(
    mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message
):
    """EXIT CRITERION 2: a legacy authed user (and the dev-bypass stub, which
    returns a claims dict with no firm_id) connects unchanged, firm_id None.
    Mutation: require a firm claim to proceed -- red."""
    mock_verify_token.return_value = {"uid": "dev_user", "email": "dev@example.com"}
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="tok")

    mock_fill_session.assert_awaited()
    assert mock_fill_session.await_args.kwargs["firm_id"] is None


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_client_link_CANNOT_fill_a_form_it_does_not_name(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """A LINK NAMES ONE FORM (bd polyglot-pdf-ugm6).

    The handshake is client-controlled, so a link holder who edits `kit_id`
    could otherwise fill a DIFFERENT form of the same firm -- one they were
    never sent -- and produce a confirmation record naming it. The token's
    kit_id wins, and a mismatch is REFUSED rather than silently substituted:
    quietly swapping the form would mean the record names a form the client
    never saw.

    Found unpinned by mutation: disabling the mismatch check left every other
    test in this bead green.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")
    # Stub the store so this test proves the KIT MISMATCH refusal specifically,
    # not an unstubbed-store fail-closed that would pass for the wrong reason.
    import time as _t
    monkeypatch.setattr(
        "backend.routes.websocket_routes.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": int(_t.time()), "completed_at": None,
        },
    )
    hostile = dict(handshake_message)
    hostile["kit_id"] = "n-400"          # NOT the form the link names
    mock_websocket.receive_text.return_value = json.dumps(hostile)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_websocket.close.assert_awaited()
    assert mock_websocket.close.await_args.kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_client_link_session_carries_the_links_firm_and_form(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """The telemetry requirement for a CLIENT session: firm + form come from
    the signed link, with no account anywhere in the picture. The matching
    handshake kit_id is accepted."""
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")
    # The socket REDEEMS the link (not just verifies the signature), so a
    # session test must supply the redemption store -- an unstubbed store
    # fails closed, which is the correct behavior and is pinned separately
    # below.
    import time as _t
    monkeypatch.setattr(
        "backend.routes.websocket_routes.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": int(_t.time()), "completed_at": None,
        },
    )
    ok = dict(handshake_message)
    ok["kit_id"] = "i-90"
    mock_websocket.receive_text.return_value = json.dumps(ok)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_fill_session.assert_awaited()
    kwargs = mock_fill_session.await_args.kwargs
    assert kwargs.get("firm_id") == "firm-a"


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_COMPLETED_link_cannot_open_a_second_socket(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """ONE COMPLETION PER LINK, ENFORCED WHERE IT MATTERS (bd
    polyglot-pdf-ugm6, fresh-eyes r1 finding 2).

    The signature check alone cannot know a link was used -- that lives in the
    redemption store. Before this, the socket only verified the signature, so
    anyone holding the raw token (a forwarded URL, a screenshot) could start
    UNLIMITED paid Gemini sessions for the full ~48h window by connecting
    directly and never calling /api/links/open. The one-time guarantee was
    enforced only on a route an attacker need not call.

    Mutation: drop the open_link call in _verify_ws_credential's caller --
    red.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_redemptions import LinkAlreadyUsed
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")

    def _already_used(jti, firm_id, kit_id, now=None):
        raise LinkAlreadyUsed("already completed")

    monkeypatch.setattr("backend.routes.websocket_routes.open_link",
                        _already_used)
    ok = dict(handshake_message)
    ok["kit_id"] = "i-90"
    mock_websocket.receive_text.return_value = json.dumps(ok)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_websocket.close.assert_awaited()
    assert mock_websocket.close.await_args.kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_an_UNREACHABLE_redemption_store_refuses_the_socket(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """FAIL CLOSED at the socket too. Unable to confirm a link is unredeemed
    means we must not start a paid session -- the same polarity as /open.

    Mutation: treat RedemptionUnavailable as "proceed" -- red.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_redemptions import RedemptionUnavailable
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")

    def _down(jti, firm_id, kit_id, now=None):
        raise RedemptionUnavailable("firestore down")

    monkeypatch.setattr("backend.routes.websocket_routes.open_link", _down)
    ok = dict(handshake_message)
    ok["kit_id"] = "i-90"
    mock_websocket.receive_text.return_value = json.dumps(ok)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_websocket.close.assert_awaited()
    assert mock_websocket.close.await_args.kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_the_COMPLETION_WINDOW_is_enforced_at_the_socket(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """verify_link_token knows only the OPEN deadline (~48h). The ~24h
    COMPLETION clock starts at first open and lives in the store, so the
    socket has to check it or a link opened 3 days ago still works.

    Mutation: drop the opened_at + cw check -- red.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    import time as _t

    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7",
                                  complete_window_s=3600)
    opened_long_ago = int(_t.time()) - 10_000     # past the 1h window
    monkeypatch.setattr(
        "backend.routes.websocket_routes.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": opened_long_ago, "completed_at": None,
        },
    )
    ok = dict(handshake_message)
    ok["kit_id"] = "i-90"
    mock_websocket.receive_text.return_value = json.dumps(ok)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_websocket.close.assert_awaited()
    assert mock_websocket.close.await_args.kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()
