"""POST /api/signup/check (sprint 23 C3, PF-6): the server-side email-signup
allowlist check that replaced the browser's unauthenticated Firestore query.

Pins: the uniform 404 on a miss, on a malformed address and on a Firestore
failure (fail closed, indistinguishable from a miss); 204 on a hit; the
lower-casing; and that the address never reaches a log line.
"""
import pytest
from fastapi.testclient import TestClient

import backend.routes.signup_routes as sr
from backend.main import app

client = TestClient(app)


class _Doc:
    pass


class _FakeQuery:
    def __init__(self, hits, raise_exc=None):
        self._hits = hits
        self._raise = raise_exc
        self.filters = []

    def where(self, *args, filter=None):
        # The route uses the keyword FieldFilter form (the repo convention);
        # the fake records what it was given, so the test pins that shape.
        if filter is not None:
            assert not args, "positional args with filter= is a mixed call"
            self.filters.append((filter.field_path, filter.op_string, filter.value))
        else:
            self.filters.append(("POSITIONAL",) + tuple(args))
        return self

    def limit(self, n):
        return self

    def stream(self):
        if self._raise:
            raise self._raise
        return iter(self._hits)


class _FakeDb:
    def __init__(self, query):
        self.query = query
        self.collections = []

    def collection(self, name):
        self.collections.append(name)
        return self.query


def _install(monkeypatch, hits, raise_exc=None):
    q = _FakeQuery(hits, raise_exc)
    db = _FakeDb(q)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def test_allowlisted_email_gets_204(monkeypatch):
    db = _install(monkeypatch, [_Doc()])
    r = client.post("/api/signup/check", json={"email": "Staff@Example.com"})
    assert r.status_code == 204
    assert r.content == b""
    assert db.collections == [sr.ALLOWLIST_COLLECTION]
    # The lookup is on the lower-cased address, like the browser query it replaced.
    assert db.query.filters == [("email", "==", "staff@example.com")]


def test_surrounding_whitespace_is_trimmed_before_the_lookup(monkeypatch):
    """Same normalisation as the browser (trim + lower); pinned so the two
    sides cannot drift. Mutation: drop strip() -- red."""
    db = _install(monkeypatch, [_Doc()])
    r = client.post("/api/signup/check", json={"email": "  Staff@Example.com  "})
    assert r.status_code == 204
    assert db.query.filters == [("email", "==", "staff@example.com")]


def test_unknown_email_gets_the_uniform_404(monkeypatch):
    _install(monkeypatch, [])
    r = client.post("/api/signup/check", json={"email": "stranger@example.com"})
    assert r.status_code == 404
    assert r.json() == {"detail": "Not found"}


def test_a_firestore_failure_is_the_same_404(monkeypatch):
    """Fail CLOSED and indistinguishable: an outage must not become an oracle
    (or a way in). Mutation: return True on exception -- red."""
    _install(monkeypatch, [], raise_exc=RuntimeError("iam drift"))
    r = client.post("/api/signup/check", json={"email": "staff@example.com"})
    assert r.status_code == 404
    assert r.json() == {"detail": "Not found"}


def test_a_malformed_address_is_the_same_404_without_a_lookup(monkeypatch):
    db = _install(monkeypatch, [_Doc()])  # would be a hit if looked up
    r = client.post("/api/signup/check", json={"email": "not-an-address"})
    assert r.status_code == 404
    assert db.collections == [], "a string with no @ must not reach Firestore"


@pytest.mark.parametrize("body", [{}, {"email": ""}, {"email": "a" * 300}])
def test_a_bad_body_is_422_with_no_echo(body):
    r = client.post("/api/signup/check", json=body)
    assert r.status_code == 422
    # The value-free 422 handler (sprint 23 B1a) must not echo the input.
    assert "aaaa" not in r.text


def test_the_address_never_reaches_a_log_line(monkeypatch, capsys):
    """The refusal log carries the address LENGTH only (staff PII)."""
    _install(monkeypatch, [])
    client.post("/api/signup/check", json={"email": "secret.person@example.com"})
    out = capsys.readouterr()
    assert "secret.person" not in out.out + out.err


def test_the_route_is_unauthenticated_by_design():
    """No require_* dependency: the caller has no account yet. Pinned so a
    blanket-auth sweep cannot silently lock signup out."""
    route = next(r for r in app.routes if getattr(r, "path", "") == "/api/signup/check")
    dep_names = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
    assert not any(n.startswith("require_") for n in dep_names), dep_names
