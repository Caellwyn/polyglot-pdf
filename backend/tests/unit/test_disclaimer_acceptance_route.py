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
        # ADDED DELIBERATELY (bd polyglot-pdf-s1iex.7): which exact disclaimer
        # TEXT the user agreed to. Non-PII -- a hash of copy that ships in the
        # client bundle -- and it is what turns the epic's determinism into
        # evidence: without it the record proves someone clicked Agree but not
        # what they were told.
        "script_version",
    }
    assert kwargs["form_session_id"] == "fss_disc_1"
    assert kwargs["language"] == "Spanish"


def test_script_version_reaches_the_log_when_the_client_sends_it(monkeypatch):
    """The evidence half of the audit record (bd polyglot-pdf-s1iex.7).

    The allowlist test above pins the KEY SET; this pins that the VALUE
    survives the route rather than being silently dropped -- an allowlist
    entry that always logs None would satisfy the set check while recording
    nothing.
    """
    mock_log = MagicMock()
    monkeypatch.setattr(dr, "_log", mock_log)

    body = dict(_BODY)
    body["script_version"] = "a1b2c3d4e5f60718"
    resp = client.post("/api/disclaimer-acceptance", json=body)
    assert resp.status_code == 200

    _args, kwargs = mock_log.info.call_args
    assert kwargs["script_version"] == "a1b2c3d4e5f60718"


def test_script_version_is_optional_for_an_older_client(monkeypatch):
    """The legacy model-read path omits script_version (the client sources it
    from the intro player, which is only built when the intro flag is on --
    NOT because that path lacks deterministic text; see bd
    polyglot-pdf-pyebx), and a client one deploy behind omits the field
    entirely. Both must still log (a 422 here would break disclaimer
    acceptance outright), with the key present and null rather than
    absent."""
    mock_log = MagicMock()
    monkeypatch.setattr(dr, "_log", mock_log)

    resp = client.post("/api/disclaimer-acceptance", json=_BODY)
    assert resp.status_code == 200

    _args, kwargs = mock_log.info.call_args
    assert kwargs["script_version"] is None
