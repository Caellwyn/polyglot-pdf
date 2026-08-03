"""bd polyglot-pdf-xp4q: the `client_diagnostic` WS arm -- whitelist logging.

The frontend emits `client_diagnostic` when the field-1 opener auto-send was
expected at session_ready but skipped (the silent gate that hid the live-demo
opener failure). The backend arm exists so the skip reason reaches PRODUCTION
logs from real sessions -- but the payload is raw client input, so the log line
must carry ONLY the named, coerced fields, never arbitrary keys or values
(no-PII policy; same rule as the unknown-field-id redaction).

Also pins: the message is one-way (no reply), and the receive loop continues.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
import backend.routes.websocket_routes as ws_routes


client = TestClient(app)

HANDSHAKE = {
    "type": "handshake",
    "schema": {
        "source": "web",
        "form_metadata": {"title": "T", "url": "https://example.com"},
        "fields": [{"id": "f_a", "name": "Field A", "type": "text"}],
    },
    "current_values": {},
}


@patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
def test_client_diagnostic_logs_whitelisted_fields_only(mock_verify_token):
    """A poisoned payload (extra keys, PII-shaped values, oversized event) must
    reach the log as coerced booleans + a capped token -- and nothing else."""
    poisoned = {
        "type": "client_diagnostic",
        "event": "field1_opener_skipped" + "X" * 200,  # oversized -> capped
        "was_section_switch": "yes-ish",               # truthy non-bool -> True
        "disclaimer_accepted": 0,                      # falsy non-bool -> False
        "has_selected_language": True,
        "has_next_field_hint": None,                   # -> False
        "is_form_complete": "truthy-string",           # -> True
        # A swapped-args style leak attempt: MUST NOT reach the log line.
        "ssn": "123-45-6789",
        "free_text": "my address is 1 Main St",
    }

    with client.websocket_connect("/ws/fill?token=t") as ws:
        ws.send_json(HANDSHAKE)
        assert ws.receive_json()["type"] == "session_ready"

        with patch.object(ws_routes._log, "warning") as warn:
            ws.send_json(poisoned)
            # One-way: no reply for client_diagnostic. Prove the loop continued
            # by provoking the NEXT reply -- an unknown type's error. If the
            # diagnostic arm had replied, this would receive that instead.
            ws.send_json({"type": "zzz_not_a_type"})
            reply = ws.receive_json()

    assert reply == {"type": "error", "code": "unknown_control"}

    diag_calls = [c for c in warn.call_args_list if c.args and c.args[0] == "client_diagnostic"]
    assert len(diag_calls) == 1
    kwargs = diag_calls[0].kwargs
    assert kwargs["diagnostic_event"].startswith("field1_opener_skipped")
    assert len(kwargs["diagnostic_event"]) == 64  # capped
    assert kwargs["was_section_switch"] is True
    assert kwargs["disclaimer_accepted"] is False
    assert kwargs["has_selected_language"] is True
    assert kwargs["has_next_field_hint"] is False
    assert kwargs["is_form_complete"] is True
    # The leak attempt must not appear anywhere on the line.
    assert "123-45-6789" not in repr(diag_calls[0])
    assert "1 Main St" not in repr(diag_calls[0])
    # Exactly the whitelisted keys + session_id -- a new field must be a
    # deliberate, reviewed addition, not payload passthrough.
    assert set(kwargs.keys()) == {
        "diagnostic_event", "was_section_switch", "disclaimer_accepted",
        "has_selected_language", "has_next_field_hint", "is_form_complete",
        "session_id",
    }
