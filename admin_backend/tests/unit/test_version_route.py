"""GET /version returns the deployed commit SHA on the admin service too
(bd polyglot-pdf-9hzod, Epic 1 child 1.6).

Mirrors backend/tests/unit/test_version_route.py -- same env var, same
"unknown" fallback (including the empty-string shape), so the admin
console's "what is live per channel" view (bead 1.7) can treat both
services' /version identically.
"""
from fastapi.testclient import TestClient

from admin_backend.main import app


client = TestClient(app)


def test_version_reports_the_git_sha_when_set(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc1234def5678")
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["git_sha"] == "abc1234def5678"
    assert body["version"] == app.version


def test_version_reports_unknown_when_git_sha_is_unset(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json()["git_sha"] == "unknown"


def test_version_reports_unknown_when_git_sha_is_empty(monkeypatch):
    """An empty (but SET) GIT_SHA is a real `--set-env-vars` shape (the same
    one the Dockerfile's `${APP_MODULE:-...}` guards for APP_MODULE); pins
    the `or` fallback rather than a plain getenv default.
    """
    monkeypatch.setenv("GIT_SHA", "")
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json()["git_sha"] == "unknown"


def test_version_is_a_distinct_route_from_the_public_backend():
    """Guards against the same accidental-re-export shape
    test_admin_health.py pins for /health -- an
    `from backend.main import app` would satisfy the assertions above while
    actually serving the public backend's app.version, not this service's.
    """
    from backend.main import app as public_app

    assert app is not public_app
