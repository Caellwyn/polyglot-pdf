from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_websocket_schema_initializes_session():
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

    with client.websocket_connect("/ws/fill") as ws:
        ws.send_json(handshake)
        response = ws.receive_json()
        
        # Verify session_ready response
        assert response["type"] == "session_ready"
        assert "session_id" in response
        assert response["session_id"].startswith("web_")
        
        # Stateless architecture: session is ephemeral, connection-scoped
        # No need to verify session_manager persistence

