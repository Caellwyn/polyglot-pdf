"""Allowlist tests for admin_audit_log.before/after key shapes per route,
and for the firms/{firm_id} doc's own key set (bd polyglot-pdf-uaxt5, sprint
23 workstream A, PF-9).

WHY THIS FILE EXISTS. admin_audit_log.before/after are typed `Any` in
audit_log.py (see build_row's own docstring: a config key's old/new value, a
firm's balance, a kit's price -- generic metadata, deliberately not
schema-locked at the write layer, since different routes audit different
shapes). That flexibility is also the risk PF-9 named: nothing stops a
future route from putting a client-data key on `before`/`after` by mistake.
This file is the CONTENT allowlist that flexibility needs -- one test per
route family, asserting the exact key set the row carries, so a stray key
(client data, or just an unreviewed addition) fails here rather than only
being caught by a human reading raw Firestore.

Reuses credit_routes.py's own test fixtures (the fake Firestore + fake
firestore.transactional module) rather than re-inventing a third copy --
test_credit_routes.py and test_firm_routes.py each already keep their own by
convention in this repo; this file keeps a THIRD small copy for the same
reason (importing test helpers across test modules couples one file's
refactor to another's).

ASCII only.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import credit_routes, firm_routes
from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin


# --------------------------------------------------------------------------
# The fake Firestore -- identical shape to test_credit_routes.py's own copy.
# --------------------------------------------------------------------------

class _Snap:
    def __init__(self, data):
        self._data = dict(data) if data is not None else None

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path
        self.id = path[-1]

    def collection(self, name):
        return _Collection(self._store, self._path + (name,))

    def get(self, transaction=None):
        return _Snap(self._store.docs.get(self._path))

    def set(self, data, merge=False):
        self._store.apply_set(self._path, data, merge)


class _Query:
    def __init__(self, store, path, order_field=None, limit=None):
        self._store = store
        self._path = path
        self._order = order_field
        self._limit = limit

    def order_by(self, field, direction="ASCENDING"):
        return _Query(self._store, self._path, field, self._limit)

    def limit(self, n):
        return _Query(self._store, self._path, self._order, n)

    def stream(self):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path
        ]
        if self._order:
            rows.sort(key=lambda kv: kv[1].get(self._order))
        if self._limit is not None:
            rows = rows[: self._limit]
        return [_Snap(data) for _, data in rows]


class _Collection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.auto_id_counter += 1
            doc_id = "auto{}".format(self._store.auto_id_counter)
        return _DocRef(self._store, self._path + (doc_id,))

    def order_by(self, field):
        return _Query(self._store, self._path).order_by(field)

    def limit(self, n):
        return _Query(self._store, self._path).limit(n)

    def stream(self):
        return _Query(self._store, self._path).stream()


class _Transaction:
    def __init__(self, store):
        self._store = store
        self._buffer = []

    def set(self, ref, data, merge=False):
        self._buffer.append((ref._path, dict(data), merge))

    def commit(self):
        for path, data, merge in self._buffer:
            self._store.apply_set(path, data, merge)
        self._buffer = []


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.auto_id_counter = 0

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        return _Transaction(self)

    def apply_set(self, path, data, merge):
        if merge and path in self.docs:
            self.docs[path].update(data)
        else:
            self.docs[path] = dict(data)

    def firm(self, firm_id):
        return self.docs.get(("firms", firm_id))

    def ledger_rows(self, firm_id):
        return [data for path, data in self.docs.items()
                if path[:3] == ("firms", firm_id, "ledger")]

    def audit_rows(self):
        return [v for path, v in self.docs.items()
                if path[0] == audit_log.COLLECTION]


class _FakeTransactionalDecorator:
    def __call__(self, fn):
        def wrapper(transaction):
            fn(transaction)
            transaction.commit()
        return wrapper


class _FakeFirestoreModule:
    transactional = _FakeTransactionalDecorator()
    SERVER_TIMESTAMP = "SERVER_TIMESTAMP"


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb({("firms", "acme"): {
        "name": "Acme", "status": "active", "kind": "live",
        "balance_credits": 100,
    }})
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    return db


@pytest.fixture
def client():
    actor = AdminActor(uid="admin-uid-1", email="ops@example.com")
    app.dependency_overrides[require_app_admin] = lambda: actor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# admin_audit_log.before/after key-shape allowlists, one per route.
#
# Each asserts an EXACT key set (never `<=` / a superset check) -- a route
# that starts also stamping a client-data-shaped key must fail here, not
# only be caught by a human reading the raw Firestore doc later.
# --------------------------------------------------------------------------

def test_credits_grant_audit_row_before_after_keys(client, fake_db):
    resp = client.post("/admin/firms/acme/credits/grant", json={
        "type": "promo_grant", "amount": 25,
    })
    assert resp.status_code == 200, resp.text
    row = fake_db.audit_rows()[0]
    assert row["action"] == credit_routes.ACTION_CREDITS_GRANT
    assert set(row["before"]) == {"balance_credits"}
    assert set(row["after"]) == {"type", "amount", "usd_amount", "kit_id"}


def test_credits_adjust_audit_row_before_after_keys(client, fake_db):
    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": -10, "reason": "correction",
    })
    assert resp.status_code == 200, resp.text
    row = fake_db.audit_rows()[0]
    assert row["action"] == credit_routes.ACTION_CREDITS_ADJUST
    assert set(row["before"]) == {"balance_credits"}
    # `reason` IS expected here (bd polyglot-pdf-uaxt5): the ledger entry and
    # the audit row are the two stores where an operator's justification
    # legitimately belongs -- only the Cloud Logging line drops it (see
    # test_admin_credits_adjusted_log_line_has_no_reason below). This test
    # would also catch a future widening of `after` to include a client-data
    # key, since it asserts the exact set, not a subset.
    assert set(row["after"]) == {"amount", "reason"}


@pytest.mark.parametrize("route_kwargs,action,before_keys,after_keys", [
    (
        {"path": "/admin/firms/acme/status", "json": {"status": "suspended"}},
        firm_routes.ACTION_FIRM_STATUS, {"status"}, {"status"},
    ),
    (
        {"path": "/admin/firms/acme/allowed_kits",
         "json": {"allowed_kits": ["i-90"]}},
        firm_routes.ACTION_FIRM_ALLOWED_KITS,
        {"allowed_kits"}, {"allowed_kits"},
    ),
    (
        {"path": "/admin/firms/acme/kind",
         "json": {"kind": "mock", "reason": "moving to staging test"}},
        firm_routes.ACTION_FIRM_KIND,
        {"kind", "reason"}, {"kind", "reason"},
    ),
    (
        {"path": "/admin/firms/acme/plan",
         "json": {"tier": "starter", "monthly_credits": 100,
                  "rollover": True}},
        firm_routes.ACTION_FIRM_PLAN, {"plan"}, {"plan"},
    ),
], ids=["status", "allowed_kits", "kind", "plan"])
def test_firm_patch_routes_audit_row_before_after_keys(
        client, fake_db, route_kwargs, action, before_keys, after_keys):
    resp = client.patch(route_kwargs["path"], json=route_kwargs["json"])
    assert resp.status_code == 200, resp.text
    rows = [r for r in fake_db.audit_rows() if r["action"] == action]
    assert len(rows) == 1
    assert set(rows[0]["before"]) == before_keys
    assert set(rows[0]["after"]) == after_keys


def test_firm_create_audit_row_before_after_keys(client, fake_db):
    resp = client.post("/admin/firms", json={
        "firm_id": "newco", "name": "Newco", "contact_email": "x@newco.example",
        "kind": "mock",
    })
    assert resp.status_code == 200, resp.text
    rows = [r for r in fake_db.audit_rows()
            if r["action"] == firm_routes.ACTION_FIRM_CREATE]
    assert len(rows) == 1
    # A create's `before` is None (no prior doc) -- not an empty dict, which
    # would read as "a doc existed with nothing in it".
    assert rows[0]["before"] is None
    assert set(rows[0]["after"]) == {
        "name", "contact_email", "allowed_kits", "status", "kind",
    }


# --------------------------------------------------------------------------
# firms/{firm_id} doc key set -- pinned so a new writer cannot silently add
# a client-data-shaped field to the firm profile (the same "client value
# reaches a store" class bd polyglot-pdf-u9gtj tracks for spoken_language).
# --------------------------------------------------------------------------

# Every key ANY writer in this repo puts on a firms/{firm_id} doc:
# backend/services/firms.py::upsert_firm (name, contact_email, allowed_kits,
# status, kind, created_at, updated_at, balance_credits, balance_updated_at)
# plus admin_backend/routes/credit_routes.py's ledger helper (balance_credits,
# balance_updated_at -- already in the set above) and
# admin_backend/routes/firm_routes.py's own create/plan writers (plan).
FIRM_DOC_ALLOWED_KEYS = frozenset({
    "name",
    "contact_email",
    "allowed_kits",
    "status",
    "kind",
    "plan",
    "balance_credits",
    "balance_updated_at",
    "created_at",
    "updated_at",
})


def test_firm_doc_key_set_after_create_and_every_patch_route(client, fake_db):
    """Drive every firm-mutating route once, then assert the resulting
    firms/{firm_id} doc carries only keys from the pinned allowlist.

    Mutation: add `stray_field` to any route's write payload -- this goes
    red, since the doc-level allowlist check runs after every route.
    """
    resp = client.post("/admin/firms", json={
        "firm_id": "acme2", "name": "Acme2",
        "contact_email": "x@acme2.example", "kind": "live",
    })
    assert resp.status_code == 200, resp.text
    doc = fake_db.firm("acme2")
    assert set(doc) <= FIRM_DOC_ALLOWED_KEYS, (
        "firms/acme2 carries a key outside the pinned allowlist after "
        "create: {}".format(set(doc) - FIRM_DOC_ALLOWED_KEYS)
    )

    for path, payload in [
        ("/admin/firms/acme2/status", {"status": "suspended"}),
        ("/admin/firms/acme2/allowed_kits", {"allowed_kits": ["i-90"]}),
        ("/admin/firms/acme2/kind",
         {"kind": "mock", "reason": "test"}),
        ("/admin/firms/acme2/plan",
         {"tier": "starter", "monthly_credits": 50, "rollover": False}),
    ]:
        resp = client.patch(path, json=payload)
        assert resp.status_code == 200, resp.text
        doc = fake_db.firm("acme2")
        assert set(doc) <= FIRM_DOC_ALLOWED_KEYS, (
            "firms/acme2 carries a key outside the pinned allowlist after "
            "{}: {}".format(path, set(doc) - FIRM_DOC_ALLOWED_KEYS)
        )


def test_a_stray_key_on_a_firm_patch_is_caught_by_the_allowlist(
        client, fake_db):
    """Prove the allowlist test above can actually fail (test-the-tests,
    CLAUDE.md scar #9): hand-inject a client-data-shaped key straight into
    the fake store, bypassing every route, and confirm the allowlist
    assertion this file relies on would flag it."""
    fake_db.docs[("firms", "acme")]["client_intake_notes"] = "should never be here"
    doc = fake_db.firm("acme")
    assert not (set(doc) <= FIRM_DOC_ALLOWED_KEYS), (
        "the allowlist check failed to catch an injected stray key -- it "
        "would pass a real regression silently"
    )


# --------------------------------------------------------------------------
# PF-9: `reason` is bounded at the Pydantic model, and absent from the
# Cloud Logging line -- the ledger entry and the audit row (both pinned
# above/elsewhere) remain the two stores where it legitimately lives.
# --------------------------------------------------------------------------

def test_adjust_reason_over_the_bound_is_refused_422(client, fake_db):
    """Refused BEFORE any write: a bad request must not reach the ledger or
    the audit row at all.

    Mutation: drop `max_length` from AdjustRequest.reason -- this goes red,
    since FastAPI/Pydantic would then accept the oversized body and write it.
    """
    too_long = "x" * (credit_routes._REASON_MAX_LENGTH + 1)
    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": -5, "reason": too_long,
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.ledger_rows("acme") == []
    assert fake_db.audit_rows() == []


def test_adjust_reason_at_the_bound_is_accepted(client, fake_db):
    """Pin both directions (scar #9): the bound must not also refuse a
    reason exactly at the limit."""
    at_bound = "x" * credit_routes._REASON_MAX_LENGTH
    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": -5, "reason": at_bound,
    })
    assert resp.status_code == 200, resp.text


def test_admin_credits_adjusted_log_line_has_no_reason(client, fake_db,
                                                       monkeypatch):
    """The Cloud Logging line for an adjustment must never carry `reason`
    (bd polyglot-pdf-uaxt5, PF-9): an operator's free-text content has no
    legitimate reason to reach a THIRD store with no access control of its
    own, when the ledger entry and the audit row already carry it.

    Mutation: restore `reason=body.reason` to the admin_credits_adjusted
    call -- this goes red, since the log call's own kwargs would then carry
    the reason text.
    """
    mock_log = MagicMock()
    monkeypatch.setattr(credit_routes, "_log", mock_log)

    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": -5, "reason": "a client's intake notes should never land here",
    })
    assert resp.status_code == 200, resp.text

    calls = [c for c in mock_log.info.call_args_list
             if c.args and c.args[0] == "admin_credits_adjusted"]
    assert len(calls) == 1, "expected exactly one admin_credits_adjusted line"
    _, kwargs = calls[0]
    assert "reason" not in kwargs, (
        "admin_credits_adjusted logged 'reason' -- an operator's free-text "
        "content reached Cloud Logging, a third, uncontrolled copy"
    )
    # Also prove the reason TEXT itself does not leak through some other
    # kwarg (e.g. a stray error= or detail= carrying str(exc)).
    for value in kwargs.values():
        assert "intake notes" not in str(value)
