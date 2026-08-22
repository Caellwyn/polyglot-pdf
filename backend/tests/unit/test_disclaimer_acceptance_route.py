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


def test_the_route_reaches_the_REAL_durable_util(monkeypatch):
    """The route must call the UTILITY, not something shaped like it.

    THIS TEST EXISTS BECAUSE THE FIRST VERSION SHIPPED BROKEN. The route
    handler is itself named log_disclaimer_acceptance, so a bare
    `from ..utils.confirmation_logger import log_disclaimer_acceptance` was
    SHADOWED by the handler at import time: the call resolved to the handler,
    raised TypeError on the kwargs, and the fail-open except swallowed it. The
    durable write never happened, and the original tests passed anyway because
    they monkeypatched the shadowed name -- patching over the very bug.

    So patch the util IN ITS OWN MODULE and assert it is reached THROUGH the
    route. That cannot be satisfied by a shadowed name.
    """
    import backend.utils.confirmation_logger as cl

    seen = {}
    monkeypatch.setattr(cl, "log_disclaimer_acceptance",
                        lambda **kw: seen.update(kw))
    # Re-bind the route's alias to the patched util, as an import-time alias
    # holds its own reference.
    monkeypatch.setattr(dr, "write_durable_acceptance_record",
                        cl.log_disclaimer_acceptance)

    resp = client.post("/api/disclaimer-acceptance", json={
        "form_session_id": "fss_real",
        "language": "Spanish",
        "timestamp": 1755000000000,
        "script_version": "deadbeefcafe0001",
        "user_agent": "ua",
    })
    assert resp.status_code == 200
    assert seen, (
        "the durable util was never reached -- the route is not wired to it "
        "(this is the shadowing bug, and it is silent by design)"
    )
    assert seen["form_session_id"] == "fss_real"
    assert seen["language"] == "Spanish"
    assert seen["script_version"] == "deadbeefcafe0001"
    assert seen["firm_id"] is None


def test_the_route_alias_is_the_util_not_the_handler():
    """Pin the WIRING itself, independent of any request.

    The shadowing bug is a module-level identity error, so assert identity:
    the name the route body calls must BE the util. A behavioral test can be
    monkeypatched into passing; this cannot.
    """
    import backend.utils.confirmation_logger as cl

    assert dr.write_durable_acceptance_record is cl.log_disclaimer_acceptance
    # And the handler must NOT be what that name refers to.
    assert dr.write_durable_acceptance_record is not dr.log_disclaimer_acceptance


def test_a_sink_outage_does_NOT_break_the_agree_click(monkeypatch):
    """FAIL-OPEN: the durable write must never 500 an Agree click.

    bd polyglot-pdf-0dsv4. If Firestore is down, or the sink raises for any
    reason, the user must still get through the disclaimer and into their
    form. Losing an audit record is bad; blocking every user from starting is
    worse, and the structlog line still records the acceptance either way.
    """
    def _boom(**kwargs):
        raise RuntimeError("firestore is down")

    monkeypatch.setattr(dr, "write_durable_acceptance_record", _boom)
    response = client.post(
        "/api/disclaimer-acceptance",
        json={
            "form_session_id": "fss_outage",
            "language": "English",
            "timestamp": 1755000000000,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "logged"


def test_the_durable_write_actually_HAPPENS_on_the_happy_path(monkeypatch):
    """The fail-open guard must not hide a write that never fires.

    A try/except around a call that was never wired would satisfy the outage
    test above while recording nothing -- so pin that the route really does
    reach the sink, with the values it was given.
    """
    seen = {}

    def _capture(**kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(dr, "write_durable_acceptance_record", _capture)
    response = client.post(
        "/api/disclaimer-acceptance",
        json={
            "form_session_id": "fss_happy",
            "language": "Spanish",
            "timestamp": 1755000000000,
            "script_version": "deadbeefcafe0001",
            "user_agent": "ua",
        },
    )
    assert response.status_code == 200
    assert seen["form_session_id"] == "fss_happy"
    assert seen["language"] == "Spanish"
    assert seen["script_version"] == "deadbeefcafe0001"
    # Written as None TODAY (no auth on this route), but the key must be
    # passed so the record shape is stable when firm auth arrives.
    assert seen["firm_id"] is None


def test_a_WIRING_error_logs_distinctly_from_a_sink_outage(monkeypatch):
    """A signature mismatch must not look like a transient outage.

    This feature once shipped completely broken: the util was shadowed by this
    route handler (same name), so every call raised TypeError and the fail-open
    except logged it as an ordinary durable-write failure -- a 100% failure
    rate wearing the costume of intermittent degradation. Wiring errors now get
    their own event name so that is greppable.
    """
    mock_log = MagicMock()
    monkeypatch.setattr(dr, "_log", mock_log)

    def _wrong_signature(*args, **kwargs):
        raise TypeError("got an unexpected keyword argument 'form_session_id'")

    monkeypatch.setattr(dr, "write_durable_acceptance_record", _wrong_signature)
    resp = client.post("/api/disclaimer-acceptance", json=_BODY)

    assert resp.status_code == 200  # still fail-open
    events = [c.args[0] for c in mock_log.error.call_args_list]
    assert "disclaimer_acceptance_wiring_error" in events
    assert "disclaimer_acceptance_durable_write_failed" not in events


def test_a_genuine_sink_outage_still_logs_as_a_write_failure(monkeypatch):
    """The other side of the split: a real outage keeps its own name."""
    mock_log = MagicMock()
    monkeypatch.setattr(dr, "_log", mock_log)

    def _outage(**kwargs):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(dr, "write_durable_acceptance_record", _outage)
    resp = client.post("/api/disclaimer-acceptance", json=_BODY)

    assert resp.status_code == 200
    events = [c.args[0] for c in mock_log.error.call_args_list]
    assert "disclaimer_acceptance_durable_write_failed" in events
    assert "disclaimer_acceptance_wiring_error" not in events
