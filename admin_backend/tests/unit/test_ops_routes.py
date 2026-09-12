"""GET /admin/errors, GET /admin/health (bd polyglot-pdf-mpebj, E3.11a).

Pins: the required ?channel= validation on both routes; errors returns
TYPE + TOP FRAME ONLY for a mocked groupStats payload carrying a sentinel
message, and the sentinel appears NOWHERE in the response (exit criterion
3); health returns a partial result (reachable: false) when one channel's
backend is unreachable, never a 500; BACKEND_URLS_JSON resolution
(configured: false on a missing entry, a malformed segment degrades to
"nothing configured" rather than crashing -- see ops_routes.py's own
_backend_urls docstring for why the wire format is "channel=url;
channel=url" rather than literal JSON despite the env var's name).

error_stats.py's `_fetch_group_stats` and ops_routes.py's
`_fetch_backend_probe` (via `requests.get`) are the seams this file
monkeypatches -- no real GCP credentials or network calls are made.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.services import error_stats
from admin_backend.services.admin_auth import AdminActor, require_app_admin


@pytest.fixture
def client():
    actor = AdminActor(uid="admin-1", email="ops@example.com")
    app.dependency_overrides[require_app_admin] = lambda: actor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# GET /admin/errors.
# --------------------------------------------------------------------------

_SENTINEL = "SENTINEL do-not-leak field_value=SSN-123-45-6789"

# Shaped like the REAL Error Reporting API, not a convenient fiction: the
# live v1beta1 discovery document's ErrorEvent schema has exactly
# context/serviceContext/message/eventTime -- there is no "type" field.
# "message" is shaped exactly like backend/utils/logging.py's
# pii_safe_exception_info output: a traceback carrying the sentinel in a
# frame line (proving a real leak shape is exercised, not an empty
# message) and ending on the bare exception type name alone, which is the
# only thing error_stats._error_type_from_message is allowed to recover.
_SENTINEL_MESSAGE = (
    'Traceback (most recent call last):\n'
    '  File "backend/adapters/live_ai_gemini.py", line 3012, in '
    '_handle_tool_call\n'
    '  # {}\n'
    'ValueError'
).format(_SENTINEL)

_RAW_GROUP_STATS_RESPONSE = {
    "errorGroupStats": [
        {
            "group": {"groupId": "grp-1"},
            "count": "42",
            "firstSeenTime": "2026-09-01T00:00:00Z",
            "lastSeenTime": "2026-09-10T00:00:00Z",
            "representative": {
                "message": _SENTINEL_MESSAGE,
                "context": {
                    "reportLocation": {
                        "filePath": "backend/adapters/live_ai_gemini.py",
                        "lineNumber": 3012,
                        "functionName": "_handle_tool_call",
                    },
                },
            },
        },
    ],
}


def test_errors_requires_a_known_channel(client, monkeypatch):
    resp = client.get("/admin/errors")
    assert resp.status_code == 422

    resp = client.get("/admin/errors?channel=prod")
    assert resp.status_code == 422


def test_errors_returns_type_and_top_frame_only_never_the_message(
        client, monkeypatch):
    """EXIT CRITERION 3. Mocks the REAL Error Reporting shape -- no
    "type" field on representative, a message that looks like this
    repo's own pii_safe_exception_info output. Mutation: add "message":
    representative.get("message") to _public_group_view's return dict --
    the sentinel assertion below goes red."""
    monkeypatch.setattr(
        error_stats, "_project_id", lambda: "test-project")
    monkeypatch.setattr(error_stats, "_access_token", lambda: "tok")
    monkeypatch.setattr(
        error_stats, "_fetch_group_stats",
        lambda project, token, service: _RAW_GROUP_STATS_RESPONSE)

    resp = client.get("/admin/errors?channel=demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["service"] == "polyglot-backend"

    raw_text = resp.text
    assert _SENTINEL not in raw_text, (
        "the raw exception message must never reach the response body")

    group = body["groups"][0]
    assert group["count"] == 42
    # Recovered from the terminating line of representative.message, since
    # the real API has no representative.type field at all.
    assert group["error_type"] == "ValueError"
    assert group["first_seen_time"] == "2026-09-01T00:00:00Z"
    assert group["last_seen_time"] == "2026-09-10T00:00:00Z"
    assert group["top_frame"] == {
        "file_path": "backend/adapters/live_ai_gemini.py",
        "line_number": 3012,
        "function_name": "_handle_tool_call",
    }
    assert "message" not in group


def test_error_type_recovery_rejects_anything_not_a_bare_type_token(
        client, monkeypatch):
    """error_type must degrade to None (never guess) when the message's
    last line is not a single bare identifier -- e.g. a real "Type:
    message" rendering, or an empty message. Mutation: relax the " " / ":"
    guard in _error_type_from_message -- this goes red."""
    raw = {
        "errorGroupStats": [
            {
                "group": {"groupId": "grp-2"},
                "count": "1",
                "firstSeenTime": "2026-09-01T00:00:00Z",
                "lastSeenTime": "2026-09-01T00:00:00Z",
                "representative": {
                    "message": "ValueError: {}".format(_SENTINEL),
                    "context": {"reportLocation": {}},
                },
            },
            {
                "group": {"groupId": "grp-3"},
                "count": "1",
                "firstSeenTime": "2026-09-01T00:00:00Z",
                "lastSeenTime": "2026-09-01T00:00:00Z",
                "representative": {
                    "message": "",
                    "context": {"reportLocation": {}},
                },
            },
        ],
    }
    monkeypatch.setattr(
        error_stats, "_project_id", lambda: "test-project")
    monkeypatch.setattr(error_stats, "_access_token", lambda: "tok")
    monkeypatch.setattr(
        error_stats, "_fetch_group_stats",
        lambda project, token, service: raw)

    resp = client.get("/admin/errors?channel=demo")
    assert resp.status_code == 200, resp.text
    groups = resp.json()["groups"]
    assert groups[0]["error_type"] is None
    assert groups[1]["error_type"] is None
    assert _SENTINEL not in resp.text


def test_errors_uses_the_staging_service_name_for_staging_channel(
        client, monkeypatch):
    """Mutation: hard-code "polyglot-backend" regardless of channel --
    red."""
    captured = {}

    def _fake_fetch(project, token, service):
        captured["service"] = service
        return {"errorGroupStats": []}

    monkeypatch.setattr(error_stats, "_project_id", lambda: "test-project")
    monkeypatch.setattr(error_stats, "_access_token", lambda: "tok")
    monkeypatch.setattr(error_stats, "_fetch_group_stats", _fake_fetch)

    resp = client.get("/admin/errors?channel=staging")
    assert resp.status_code == 200, resp.text
    assert captured["service"] == "polyglot-backend-staging"
    assert resp.json()["service"] == "polyglot-backend-staging"


def test_errors_maps_unavailable_to_503(client, monkeypatch):
    def _boom():
        raise error_stats.ErrorReportingUnavailable("no ADC")

    monkeypatch.setattr(error_stats, "_project_id", _boom)
    resp = client.get("/admin/errors?channel=demo")
    assert resp.status_code == 503, resp.text


# --------------------------------------------------------------------------
# GET /admin/health.
# --------------------------------------------------------------------------

def test_health_requires_a_known_channel(client):
    resp = client.get("/admin/health")
    assert resp.status_code == 422
    resp = client.get("/admin/health?channel=prod")
    assert resp.status_code == 422


def test_health_reports_configured_false_when_backend_urls_json_is_unset(
        client, monkeypatch):
    monkeypatch.delenv("BACKEND_URLS_JSON", raising=False)
    resp = client.get("/admin/health?channel=demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["backend"]["configured"] is False
    assert body["backend"]["reachable"] is False
    assert body["backend"]["health"] is None


def test_health_reports_configured_false_for_a_missing_channel_entry(
        client, monkeypatch):
    """BACKEND_URLS_JSON has an entry for demo but not staging -- staging
    must read configured: false, never crash or silently reuse demo's URL."""
    monkeypatch.setenv(
        "BACKEND_URLS_JSON", "demo=https://polyglot-backend-x.a.run.app")
    resp = client.get("/admin/health?channel=staging")
    assert resp.status_code == 200, resp.text
    assert resp.json()["backend"]["configured"] is False


def test_health_degrades_gracefully_on_malformed_backend_urls_json(
        client, monkeypatch):
    """Mutation: let a malformed segment (no "=") raise uncaught instead of
    being skipped -- this would 500 instead of degrading to "nothing
    configured" -- red."""
    monkeypatch.setenv("BACKEND_URLS_JSON", "not-a-valid-segment")
    resp = client.get("/admin/health?channel=demo")
    assert resp.status_code == 200, resp.text
    assert resp.json()["backend"]["configured"] is False


def test_health_parses_both_channels_from_one_semicolon_joined_value(
        client, monkeypatch):
    """The real deploy-admin.sh shape: two "channel=url" segments joined by
    a semicolon (never a comma -- see ops_routes.py's own module docstring
    for why: this value rides inside a comma-joined --set-env-vars block).
    Mutation: split on "," instead of ";" -- this would see ONE malformed
    segment instead of two clean ones and both channels would read
    configured: false -- red."""
    monkeypatch.setenv(
        "BACKEND_URLS_JSON",
        "demo=https://polyglot-backend-demo.example;"
        "staging=https://polyglot-backend-staging.example")
    resp_demo = client.get("/admin/health?channel=demo")
    assert resp_demo.json()["backend"]["configured"] is True
    resp_staging = client.get("/admin/health?channel=staging")
    assert resp_staging.json()["backend"]["configured"] is True


def test_health_returns_a_partial_result_when_the_backend_is_unreachable(
        client, monkeypatch):
    """EXIT CRITERION 3'S OTHER HALF. Mutation: let the requests.get
    exception in _fetch_backend_probe propagate instead of being caught --
    this whole request would 500 instead of returning a partial result."""
    monkeypatch.setenv(
        "BACKEND_URLS_JSON",
        "demo=https://polyglot-backend-unreachable.example")

    def _boom(url, timeout):
        raise ConnectionError("connection refused")

    import requests as _requests
    monkeypatch.setattr(_requests, "get", _boom)

    resp = client.get("/admin/health?channel=demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["backend"]["configured"] is True
    assert body["backend"]["reachable"] is False
    assert body["backend"]["health"] is None
    assert body["backend"]["version"] is None
    # The admin service's OWN version must still be present -- one
    # channel's outage must not blank out this service's own identity.
    assert body["admin_service"]["version"]


def test_health_returns_the_backend_bodies_when_reachable(client, monkeypatch):
    monkeypatch.setenv(
        "BACKEND_URLS_JSON",
        "demo=https://polyglot-backend-ok.example")

    class _FakeResponse:
        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self._body

    def _fake_get(url, timeout):
        if url.endswith("/health"):
            return _FakeResponse({"status": "ok"})
        return _FakeResponse({"version": "0.1.0", "git_sha": "abc123"})

    import requests as _requests
    monkeypatch.setattr(_requests, "get", _fake_get)

    resp = client.get("/admin/health?channel=demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()["backend"]
    assert body["configured"] is True
    assert body["reachable"] is True
    assert body["health"] == {"status": "ok"}
    assert body["version"] == {"version": "0.1.0", "git_sha": "abc123"}


def test_health_reachable_requires_both_health_and_version_to_succeed(
        client, monkeypatch):
    """Mutation: OR the two success flags instead of AND-ing them -- a
    backend answering /health but not /version would then read
    reachable=True, hiding a real half-degraded state -- red."""
    monkeypatch.setenv(
        "BACKEND_URLS_JSON",
        "demo=https://polyglot-backend-half.example")

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "ok"}

    def _fake_get(url, timeout):
        if url.endswith("/health"):
            return _FakeResponse()
        raise ConnectionError("version endpoint down")

    import requests as _requests
    monkeypatch.setattr(_requests, "get", _fake_get)

    resp = client.get("/admin/health?channel=demo")
    body = resp.json()["backend"]
    assert body["health"] == {"status": "ok"}
    assert body["version"] is None
    assert body["reachable"] is False
