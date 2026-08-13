from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


# /ws/fill is auth-gated: it requires a `token` query param and verifies it
# (commit aa66f45, AUTH_AND_PROFILES_PLAN). Patch verify_token so the handshake
# itself is what's under test, and pass a token so the route accepts the socket.
@patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
def test_websocket_schema_initializes_session(mock_verify_token):
    """Test that web form handshake creates an ephemeral session."""
    handshake = {
        "type": "handshake",
        "schema": {
            "source": "web",
            "form_metadata": {"title": "Contact", "url": "https://example.com"},
            "fields": [
                {"id": "name", "name": "Full Name", "type": "text"},
            ],
        },
        "current_values": {}
    }

    with client.websocket_connect("/ws/fill?token=test-token") as ws:
        ws.send_json(handshake)
        response = ws.receive_json()

        # Verify session_ready response
        assert response["type"] == "session_ready"
        assert "session_id" in response
        assert response["session_id"].startswith("web_")

        # Stateless architecture: session is ephemeral, connection-scoped
        # No need to verify session_manager persistence


@patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
def test_a_non_dict_form_metadata_on_the_legacy_handshake_does_not_drop_the_session(
    mock_verify_token,
):
    """bd polyglot-pdf-ypk4: the LEGACY (non-JIT) handshake branch validates
    only that `schema` itself is a dict (websocket_routes.py's
    schema_missing_or_invalid check), never the nested form_metadata key. A
    client whose form_metadata is a string/list would otherwise raise
    AttributeError inside FormFillingService.start_session's unguarded
    `schema.get("form_metadata", {}).get("form_number", ...)` and drop the WS
    connection on the very first handshake of the session (jitModeEnabled
    starts false, so this legacy branch is what a brand-new browser session
    hits before session_ready ever arrives).
    """
    handshake = {
        "type": "handshake",
        "schema": {
            "source": "web",
            "form_metadata": "12/2024",  # a STRING, not a dict
            "fields": [
                {"id": "name", "name": "Full Name", "type": "text"},
            ],
        },
        "current_values": {},
    }

    with client.websocket_connect("/ws/fill?token=test-token") as ws:
        ws.send_json(handshake)
        response = ws.receive_json()

        # The session degrades gracefully rather than the socket closing with
        # an error -- session_ready proves start_session did not raise.
        assert response["type"] == "session_ready"
        assert "session_id" in response
