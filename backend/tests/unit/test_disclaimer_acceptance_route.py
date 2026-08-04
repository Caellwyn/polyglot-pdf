"""Disclaimer-acceptance route: PII-minimized audit log (bd polyglot-pdf-z2is).

The route used to log the caller's IP. An IP is PII under GDPR/CCPA and made
the "no personal data stored" posture literally false, so it was dropped; the
acceptance evidence is form_session_id + timestamp + language (+ user_agent as
a deliberate low-sensitivity retention pending counsel, bd polyglot-pdf-pol2).

The log shape is pinned with an ALLOWLIST (exact kwarg set), never a blacklist:
banning `client_ip` by name would be one rename away from defeat.
"""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import backend.routes.disclaimer_routes as dr
from backend.main import app

client = TestClient(app)

_BODY = {
    "form_session_id": "fss_disc_1",
    "language": "Spanish",
    "timestamp": 1754200000000,
    "user_agent": "TestAgent/1.0",
}


def test_acceptance_returns_logged(monkeypatch):
    monkeypatch.setattr(dr, "_log", MagicMock())
    resp = client.post("/api/disclaimer-acceptance", json=_BODY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "logged"
    assert body["session_id"] == "fss_disc_1"


def test_acceptance_log_kwargs_are_exactly_the_allowlist(monkeypatch):
    mock_log = MagicMock()
    monkeypatch.setattr(dr, "_log", mock_log)

    resp = client.post("/api/disclaimer-acceptance", json=_BODY)
    assert resp.status_code == 200

    mock_log.info.assert_called_once()
    args, kwargs = mock_log.info.call_args
    assert args == ("disclaimer_accepted",)
    # Exact allowlist: adding client_ip (or any new key) back must fail here
    # and be a deliberate, reviewed decision.
    assert set(kwargs) == {
        "form_session_id",
        "language",
        "timestamp_unix_ms",
        "timestamp_iso",
        "user_agent",
    }
    assert kwargs["form_session_id"] == "fss_disc_1"
    assert kwargs["language"] == "Spanish"
