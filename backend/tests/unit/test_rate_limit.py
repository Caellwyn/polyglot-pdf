"""The per-instance limiter on the unauthenticated write doors (sprint 23
PF-5, bd polyglot-pdf-o2fub).

Mutations (each RED): remove `Depends(rate_limited(...))` from any one of the
three doors (the set pin names it and that door's own case fails); make the
links/open refusal say "Too many requests" (the byte-identical pin); log the
address on refusal (the PII guard's kwarg rule + the kwarg pin here);
change `_take` to never refuse (every limit case).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import app
from backend.routes import disclaimer_routes, link_routes, signup_routes
from backend.tests.integration.test_access_matrix import _DELIBERATELY_UNGATED_HTTP_ROUTES
from backend.utils import rate_limit


@pytest.fixture
def tiny_budget(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "RATE_LIMIT_ENABLED", True, raising=False)
    monkeypatch.setattr(s, "RATE_LIMIT_BUDGET", 3, raising=False)
    monkeypatch.setattr(s, "RATE_LIMIT_WINDOW_SEC", 60.0, raising=False)
    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest.fixture
def client():
    return TestClient(app)


# --- the bucket itself ---------------------------------------------------------------


def test_the_bucket_refuses_the_call_after_the_budget_and_refills_with_time():
    rate_limit.reset()
    now = 1000.0
    allowed = [rate_limit._take("d", "k", 3, 60.0, now) for _ in range(4)]
    assert allowed == [True, True, True, False]
    # One token refills after window/budget seconds (20 s here).
    assert rate_limit._take("d", "k", 3, 60.0, now + 19.0) is False
    assert rate_limit._take("d", "k", 3, 60.0, now + 21.0) is True


def test_buckets_are_per_address_and_per_door():
    rate_limit.reset()
    for _ in range(3):
        assert rate_limit._take("d", "a", 3, 60.0, 0.0)
    assert rate_limit._take("d", "a", 3, 60.0, 0.0) is False
    assert rate_limit._take("d", "b", 3, 60.0, 0.0) is True    # another address
    assert rate_limit._take("e", "a", 3, 60.0, 0.0) is True    # another door


def test_the_address_is_the_first_forwarded_hop():
    req = MagicMock()
    req.headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}
    assert rate_limit.client_address(req) == "203.0.113.9"
    req.headers = {}
    req.client.host = "127.0.0.1"
    assert rate_limit.client_address(req) == "127.0.0.1"


# --- the doors ------------------------------------------------------------------------


def test_links_open_over_budget_is_the_same_404_as_a_bad_token(client, tiny_budget, monkeypatch):
    """Oracle posture: a limited caller sees exactly what a wrong-token caller
    sees. And the handler never runs for the refused call."""
    from backend.services.link_tokens import LinkTokenError
    verify = MagicMock(side_effect=LinkTokenError("bad token"))
    monkeypatch.setattr(link_routes, "verify_link_token", verify)
    bodies = []
    for _ in range(4):
        r = client.post("/api/links/open", json={"token": "x.y"})
        bodies.append((r.status_code, r.json()))
    assert all(b == (404, {"detail": "This link is not valid."}) for b in bodies), bodies
    assert verify.call_count == 3, "the fourth call must be refused before the handler"


def test_signup_check_over_budget_is_the_uniform_404(client, tiny_budget, monkeypatch):
    monkeypatch.setattr(signup_routes, "email_is_allowlisted", lambda email: True)
    codes = [client.post("/api/signup/check", json={"email": "a@b.co"}).status_code for _ in range(4)]
    assert codes == [204, 204, 204, 404]
    r = client.post("/api/signup/check", json={"email": "a@b.co"})
    assert r.status_code == 404 and r.json() == {"detail": "Not found"}


def test_disclaimer_acceptance_over_budget_is_429(client, tiny_budget, monkeypatch):
    monkeypatch.setattr(disclaimer_routes, "write_durable_acceptance_record", MagicMock())
    import time as _time
    body = {"form_session_id": "fss_rl", "language": "English", "timestamp": int(_time.time() * 1000)}
    codes = [client.post("/api/disclaimer-acceptance", json=body).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429], codes
    assert client.post("/api/disclaimer-acceptance", json=body).json() == {"detail": "Too many requests"}


def test_the_refusal_log_line_carries_no_address(client, tiny_budget, monkeypatch):
    mock_log = MagicMock()
    monkeypatch.setattr(rate_limit, "_log", mock_log)
    monkeypatch.setattr(signup_routes, "email_is_allowlisted", lambda email: True)
    for _ in range(4):
        client.post("/api/signup/check", json={"email": "a@b.co"},
                    headers={"x-forwarded-for": "203.0.113.9"})
    calls = [c for c in mock_log.warning.call_args_list if c.args and c.args[0] == "rate_limited"]
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert set(kwargs) == {"door", "budget", "window_sec"}
    assert "203.0.113.9" not in repr(kwargs)


def test_disabled_means_no_refusal(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "RATE_LIMIT_ENABLED", False, raising=False)
    monkeypatch.setattr(s, "RATE_LIMIT_BUDGET", 1, raising=False)
    rate_limit.reset()
    monkeypatch.setattr(signup_routes, "email_is_allowlisted", lambda email: True)
    codes = [client.post("/api/signup/check", json={"email": "a@b.co"}).status_code for _ in range(3)]
    assert codes == [204, 204, 204]


# --- the SET: every deliberately ungated POST door is limited ------------------------


def _limited_doors() -> set:
    doors = set()
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        stack = list(dependant.dependencies)
        while stack:
            dep = stack.pop()
            if getattr(dep.call, "_rate_limit_door", None):
                for method in sorted(route.methods or []):
                    doors.add((method, route.path))
            stack.extend(dep.dependencies)
    return doors


def test_every_deliberately_ungated_write_door_is_rate_limited():
    """Derived from the access matrix's ungated set: every POST there (the
    dev-only console sink excepted -- it is closed on Cloud Run) carries the
    limiter, so a fourth unauthenticated write door fails CI here."""
    ungated_posts = {(m, p) for (m, p) in _DELIBERATELY_UNGATED_HTTP_ROUTES
                     if m == "POST" and p != "/dev/console-log"}
    assert ungated_posts, "the ungated set lost its POST doors?"
    assert ungated_posts == _limited_doors(), (
        "unlimited: %s; limited but not ungated: %s" % (
            sorted(ungated_posts - _limited_doors()), sorted(_limited_doors() - ungated_posts)))
