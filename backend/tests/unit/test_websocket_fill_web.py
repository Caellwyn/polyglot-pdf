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
