"""/dev/console-log fail-closed gating (bd polyglot-pdf-6088m, sprint 23 C4; PF-10).

Two INDEPENDENT gates protect this route in production:

1. DEV_LOGGING_ENABLED -- the backend/.env.DEV marker-file check. This is
   already exercised by the route's normal behavior tests elsewhere; the marker
   itself is excluded from the built container by .dockerignore
   (see tests/test_dockerignore_env_exclusion.py).
2. K_SERVICE -- set by Cloud Run and by nothing else. This is the NEW guard:
   a deployed service must 404 here even in the (should-never-happen) case that
   the marker-file gate is somehow satisfied, e.g. a broken .dockerignore or a
   build context that copied backend/.env.DEV in by mistake. Fail-closed means
   BOTH conditions must hold before the route does anything: dev logging must be
   enabled AND the process must not look like a deployed Cloud Run service.

This file drives the route through the real ASGI app (TestClient), not by
calling the coroutine directly, so the fastapi routing/exception-handling layer
is exercised too.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import backend.routes.dev_console_routes as dcr
from backend.main import app

client = TestClient(app)

_BODY = {"ws_session_id": "sess-1", "entries": [{"level": "log", "text": "hello", "ts": 123}]}


def test_404_when_dev_logging_disabled_and_no_k_service(monkeypatch):
    """Baseline: the pre-existing marker-file gate still 404s alone."""
    monkeypatch.setattr(dcr, "DEV_LOGGING_ENABLED", False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    resp = client.post("/dev/console-log", json=_BODY)
    assert resp.status_code == 404


def test_404_on_k_service_even_when_dev_logging_is_enabled(monkeypatch):
    """THE NEW GUARD. A deployed service (K_SERVICE set) must 404 here even if
    dev logging somehow reads as enabled -- e.g. a packaging mistake that let
    backend/.env.DEV reach the container despite .dockerignore. Before this
    bead's fix, DEV_LOGGING_ENABLED=True alone was sufficient to reach the
    handler regardless of K_SERVICE, which is exactly the gap this closes.
    """
    monkeypatch.setattr(dcr, "DEV_LOGGING_ENABLED", True)
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    resp = client.post("/dev/console-log", json=_BODY)
    assert resp.status_code == 404


def test_404_on_k_service_and_dev_logging_disabled(monkeypatch):
    """Both gates closed -- still 404 (the ordinary production shape)."""
    monkeypatch.setattr(dcr, "DEV_LOGGING_ENABLED", False)
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    resp = client.post("/dev/console-log", json=_BODY)
    assert resp.status_code == 404


def test_200_only_when_dev_logging_enabled_and_no_k_service(monkeypatch):
    """The one shape that must still work: real local dev."""
    monkeypatch.setattr(dcr, "DEV_LOGGING_ENABLED", True)
    monkeypatch.delenv("K_SERVICE", raising=False)

    class _FakeLogger:
        enabled = True

        def log_event(self, **kwargs):
            pass

    monkeypatch.setattr(dcr, "get_dev_logger", lambda: _FakeLogger())
    resp = client.post("/dev/console-log", json=_BODY)
    assert resp.status_code == 200
    assert resp.json()["written"] == 1
