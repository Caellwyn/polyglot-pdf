import inspect
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


# ---------------------------------------------------------------------------
# Manual/voice mode over the wire (bd polyglot-pdf-wurj8)
#
# These drive the REAL route through TestClient rather than calling the handler,
# so they pin the client-visible contract: the message name, the ack, the
# rejection of a bad mode, and -- the one that carries the user-facing promise --
# that a PTT press leaves manual mode without the user finding the toggle.
# ---------------------------------------------------------------------------

_MODE_HANDSHAKE = {
    "type": "handshake",
    "schema": {
        "source": "web",
        "form_metadata": {"title": "Contact", "url": "https://example.com"},
        "fields": [{"id": "name", "name": "Full Name", "type": "text"}],
    },
    "current_values": {},
}


def _connect_ready(ws):
    ws.send_json(_MODE_HANDSHAKE)
    assert ws.receive_json()["type"] == "session_ready"


@patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
def test_voice_mode_manual_is_acked(mock_verify_token):
    """The client can put the session into manual mode and is told it took."""
    with client.websocket_connect("/ws/fill?token=test-token") as ws:
        _connect_ready(ws)
        ws.send_json({"type": "voice_mode", "mode": "manual"})
        ack = ws.receive_json()

    assert ack["type"] == "voice_mode_ack"
    assert ack["mode"] == "manual"


@patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
def test_voice_mode_voice_is_acked(mock_verify_token):
    """...and back out again."""
    with client.websocket_connect("/ws/fill?token=test-token") as ws:
        _connect_ready(ws)
        ws.send_json({"type": "voice_mode", "mode": "voice"})
        ack = ws.receive_json()

    assert ack["type"] == "voice_mode_ack"
    assert ack["mode"] == "voice"


@patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
def test_an_unrecognised_voice_mode_is_rejected_not_defaulted(mock_verify_token):
    """A malformed toggle must not be able to silence the assistant.

    The failure mode of a wrongly-muted session is a user who concludes the app
    is broken and leaves, so an unknown mode is refused outright rather than
    coerced -- in EITHER direction, but the dangerous coercion is toward manual.
    """
    with client.websocket_connect("/ws/fill?token=test-token") as ws:
        _connect_ready(ws)
        ws.send_json({"type": "voice_mode", "mode": "quiet"})
        reply = ws.receive_json()

    assert reply["type"] == "error"
    assert reply["code"] == "invalid_voice_mode"


@patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
def test_a_ptt_press_leaves_manual_mode(mock_verify_token):
    """bd polyglot-pdf-wurj8 exit criterion 2.

    Pressing to talk is an unambiguous request FOR the assistant, so it must
    leave manual mode on its own -- a user who presses PTT and gets silence has
    hit the exact dead end this control is meant to avoid.

    Asserted on the SERVICE (the thing that decides whether the model speaks),
    not on a client echo, by overriding the route's own dependency and recording
    every set_voice_muted call. The manual->False ORDER is what is pinned: a
    route that never muted, or one that unmuted before the mode was set, cannot
    produce it.
    """
    from backend.dependencies import get_form_filling_service
    from backend.main import app as fastapi_app

    calls = []

    class _ModeSpy:
        """Wraps the real service; records mode flips, delegates everything else."""

        def __init__(self, inner):
            self._inner = inner

        def set_voice_muted(self, muted):
            calls.append(muted)
            return self._inner.set_voice_muted(muted)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    real_dep = get_form_filling_service

    async def _spied(*args, **kwargs):
        inner = await real_dep(*args, **kwargs)
        return _ModeSpy(inner)

    _spied.__signature__ = inspect.signature(real_dep)
    fastapi_app.dependency_overrides[get_form_filling_service] = _spied
    try:
        with client.websocket_connect("/ws/fill?token=test-token") as ws:
            _connect_ready(ws)
            ws.send_json({"type": "voice_mode", "mode": "manual"})
            assert ws.receive_json()["mode"] == "manual"

            ws.send_json({"type": "vad_activity_start", "timestamp": 0})
            # A PTT press is fire-and-forget (no ack by design), so round-trip a
            # message behind it to be sure the press was actually processed
            # before the assertions below read `calls`.
            ws.send_json({"type": "voice_mode", "mode": "manual"})
            assert ws.receive_json()["mode"] == "manual"
    finally:
        fastapi_app.dependency_overrides.pop(get_form_filling_service, None)

    # manual (the toggle), then False (the PTT press), then manual again (the
    # round-trip). The middle entry is the behaviour under test.
    assert calls[:2] == [True, False], calls
