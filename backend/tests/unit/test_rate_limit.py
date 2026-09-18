"""The per-instance limiter on the unauthenticated write doors (sprint 23
PF-5, bd polyglot-pdf-o2fub).

Mutations (each RED): remove `Depends(rate_limited(...))` from any one of the
three doors (the set pin names it and that door's own case fails); make the
links/open refusal say "Too many requests" (the byte-identical pin); log an
address on refusal (the kwarg pin); key the client bucket on the FIRST hop
(the forged-hop cases); drop the connection bucket (the rotating-forge case);
change `_take` to never refuse (every limit case); drop the LRU bound (the
bounded-map case).
"""
from __future__ import annotations

import time as _time
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
    """Client bucket 3, connection bucket 5, one-minute window."""
    s = get_settings()
    monkeypatch.setattr(s, "RATE_LIMIT_ENABLED", True, raising=False)
    monkeypatch.setattr(s, "RATE_LIMIT_BUDGET", 3, raising=False)
    monkeypatch.setattr(s, "RATE_LIMIT_SHARED_BUDGET", 5, raising=False)
    monkeypatch.setattr(s, "RATE_LIMIT_WINDOW_SEC", 60.0, raising=False)
    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _allow_all_signups(monkeypatch):
    monkeypatch.setattr(signup_routes, "email_is_allowlisted", lambda email: True)


def _signup(client, xff=None):
    headers = {"x-forwarded-for": xff} if xff else {}
    return client.post("/api/signup/check", json={"email": "a@b.co"}, headers=headers).status_code


# --- the bucket itself ---------------------------------------------------------------


def test_the_bucket_refuses_the_call_after_the_budget_and_refills_with_time():
    rate_limit.reset()
    now = 1000.0
    allowed = [rate_limit._take("d", "client", "k", 3, 60.0, now) for _ in range(4)]
    assert allowed == [True, True, True, False]
    # One token refills after window/budget seconds (20 s here).
    assert rate_limit._take("d", "client", "k", 3, 60.0, now + 19.0) is False
    assert rate_limit._take("d", "client", "k", 3, 60.0, now + 21.0) is True


def test_buckets_are_per_key_per_door_per_kind():
    rate_limit.reset()
    for _ in range(3):
        assert rate_limit._take("d", "client", "a", 3, 60.0, 0.0)
    assert rate_limit._take("d", "client", "a", 3, 60.0, 0.0) is False
    assert rate_limit._take("d", "client", "b", 3, 60.0, 0.0) is True      # another key
    assert rate_limit._take("e", "client", "a", 3, 60.0, 0.0) is True      # another door
    assert rate_limit._take("d", "connection", "a", 3, 60.0, 0.0) is True  # the other kind


def test_the_map_is_bounded_and_evicts_the_oldest_key():
    """A flood of forged hops must not grow memory: the per-door map is an
    LRU capped at MAX_KEYS_PER_DOOR. Mutation: drop the `while` -> red."""
    rate_limit.reset()
    for i in range(rate_limit.MAX_KEYS_PER_DOOR + 50):
        rate_limit._take("d", "client", "k%d" % i, 3, 60.0, 0.0)
    per = rate_limit._buckets[("d", "client")]
    assert len(per) == rate_limit.MAX_KEYS_PER_DOOR
    assert "k0" not in per and "k49" not in per and "k50" in per


# --- the keys: taken from the END of the forwarded chain ----------------------------


def _req(xff=None, peer="127.0.0.1"):
    req = MagicMock()
    req.headers = {"x-forwarded-for": xff} if xff is not None else {}
    req.client.host = peer
    return req


def test_the_keys_are_the_second_to_last_hop_and_the_last_hop():
    assert rate_limit.client_keys(_req("203.0.113.9, 198.51.100.7")) == ("203.0.113.9", "198.51.100.7")
    # A forged prefix changes neither key: only the end of the chain counts.
    assert rate_limit.client_keys(_req("9.9.9.9, 203.0.113.9, 198.51.100.7")) == ("203.0.113.9", "198.51.100.7")
    # A direct caller (one hop) is keyed on itself twice over.
    assert rate_limit.client_keys(_req("203.0.113.9")) == ("203.0.113.9", "203.0.113.9")
    # No chain at all (local dev): the socket peer.
    assert rate_limit.client_keys(_req(None, peer="127.0.0.1")) == ("127.0.0.1", "127.0.0.1")


def test_a_browser_behind_a_rotating_hosting_egress_is_still_one_client(client, tiny_budget, monkeypatch):
    """Measured on staging (2026-09-18): Hosting's egress address differs on
    every request. The client key is the browser hop alone, so the 4th call
    is refused even though the last hop never repeats. Mutation: key on
    `prev|last` -> red (every call would be 204)."""
    _allow_all_signups(monkeypatch)
    codes = [_signup(client, "203.0.113.9, 198.51.100.%d" % (10 + i)) for i in range(4)]
    assert codes == [204, 204, 204, 404]


def test_a_forged_first_hop_does_not_open_a_fresh_bucket(client, tiny_budget, monkeypatch):
    """Through Hosting the browser's address sits second-to-last and the
    egress last; a browser that rotates a forged FIRST hop stays in its own
    client bucket. Mutation: key on hops[0] -> red."""
    _allow_all_signups(monkeypatch)
    codes = [_signup(client, "10.0.0.%d, 203.0.113.9, 198.51.100.7" % i) for i in range(4)]
    assert codes == [204, 204, 204, 404]


def test_a_direct_caller_rotating_forged_hops_hits_the_connection_bucket(client, tiny_budget, monkeypatch):
    """A direct caller controls every hop but the last; rotating the
    second-to-last opens fresh client buckets, and the connection bucket
    (keyed on the last hop alone) is the backstop. Mutation: drop the
    connection bucket -> red (every call would be 204)."""
    _allow_all_signups(monkeypatch)
    codes = [_signup(client, "10.0.0.%d, 203.0.113.9" % i) for i in range(7)]
    assert codes == [204, 204, 204, 204, 204, 404, 404]


def test_one_abuser_behind_hosting_does_not_drain_the_shared_bucket(client, tiny_budget, monkeypatch):
    """A refused client call must not draw on the connection bucket, or one
    abuser behind Hosting's egress would lock out everyone behind it."""
    _allow_all_signups(monkeypatch)
    abuser = [_signup(client, "203.0.113.9, 198.51.100.7") for _ in range(10)]
    assert abuser == [204, 204, 204] + [404] * 7
    # A different browser behind the same egress still has the shared budget
    # left (5 shared - 3 used by the abuser = 2 more).
    other = [_signup(client, "203.0.113.10, 198.51.100.7") for _ in range(3)]
    assert other == [204, 204, 404]


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
    _allow_all_signups(monkeypatch)
    codes = [_signup(client) for _ in range(4)]
    assert codes == [204, 204, 204, 404]
    r = client.post("/api/signup/check", json={"email": "a@b.co"})
    assert r.status_code == 404 and r.json() == {"detail": "Not found"}


def test_disclaimer_acceptance_over_budget_is_429(client, tiny_budget, monkeypatch):
    monkeypatch.setattr(disclaimer_routes, "write_durable_acceptance_record", MagicMock())
    body = {"form_session_id": "fss_rl", "language": "English", "timestamp": int(_time.time() * 1000)}
    codes = [client.post("/api/disclaimer-acceptance", json=body).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429], codes
    assert client.post("/api/disclaimer-acceptance", json=body).json() == {"detail": "Too many requests"}


def test_the_refusal_log_line_carries_no_address(client, tiny_budget, monkeypatch):
    mock_log = MagicMock()
    monkeypatch.setattr(rate_limit, "_log", mock_log)
    _allow_all_signups(monkeypatch)
    for _ in range(4):
        _signup(client, "203.0.113.9, 198.51.100.7")
    calls = [c for c in mock_log.warning.call_args_list if c.args and c.args[0] == "rate_limited"]
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert set(kwargs) == {"door", "bucket", "budget", "window_sec", "hops"}
    assert kwargs["hops"] == 2
    assert "203.0.113.9" not in repr(kwargs) and "198.51.100.7" not in repr(kwargs)


def test_disabled_means_no_refusal(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "RATE_LIMIT_ENABLED", False, raising=False)
    monkeypatch.setattr(s, "RATE_LIMIT_BUDGET", 1, raising=False)
    rate_limit.reset()
    _allow_all_signups(monkeypatch)
    assert [_signup(client) for _ in range(3)] == [204, 204, 204]


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
