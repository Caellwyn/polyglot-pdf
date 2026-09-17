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

import ast
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import (
    alert_routes,
    config_routes,
    credit_routes,
    deploy_routes,
    deploy_webhook,
    firm_routes,
    kit_routes,
    link_routes,
    sweep_routes,
    user_routes,
)
from admin_backend.services import audit_log
from admin_backend.services.admin_auth import (
    ACTOR_KIND_APP_ADMIN,
    AdminActor,
    CompositeActor,
    require_app_admin,
)


# --------------------------------------------------------------------------
# The fake Firestore -- identical shape to test_credit_routes.py's own copy.
# --------------------------------------------------------------------------

class _Snap:
    def __init__(self, data, doc_id=None):
        self._data = dict(data) if data is not None else None
        self.id = doc_id

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
        return _Snap(self._store.docs.get(self._path), doc_id=self._path[-1])

    def set(self, data, merge=False):
        self._store.apply_set(self._path, data, merge)

    def update(self, data):
        # record_pending/mark_committed (the non-transactional audit form,
        # user_routes.py's own path) call .update() directly, outside any
        # transaction.
        existing = self._store.docs.setdefault(self._path, {})
        existing.update(data)


class _Query:
    def __init__(self, store, path, order_field=None, limit=None,
                clauses=()):
        self._store = store
        self._path = path
        self._order = order_field
        self._limit = limit
        self._clauses = tuple(clauses)

    def order_by(self, field, direction="ASCENDING"):
        return _Query(self._store, self._path, field, self._limit,
                     self._clauses)

    def limit(self, n):
        return _Query(self._store, self._path, self._order, n,
                     self._clauses)

    def where(self, *args, **kwargs):
        if "filter" in kwargs:
            ff = kwargs["filter"]
            field, op, value = ff.field_path, ff.op_string, ff.value
        else:
            field, op, value = args
        return _Query(self._store, self._path, self._order, self._limit,
                     self._clauses + ((field, op, value),))

    def _matches(self, data):
        for field, op, value in self._clauses:
            actual = data.get(field)
            if op == "==":
                if actual != value:
                    return False
            elif op == "<":
                if actual is None or not (actual < value):
                    return False
            else:  # pragma: no cover - not needed by any route this file drives
                raise NotImplementedError(op)
        return True

    def stream(self):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path and self._matches(data)
        ]
        if self._order:
            rows.sort(key=lambda kv: kv[1].get(self._order))
        if self._limit is not None:
            rows = rows[: self._limit]
        return [_Snap(data, doc_id=path[-1]) for path, data in rows]


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

    def where(self, *args, **kwargs):
        return _Query(self._store, self._path).where(*args, **kwargs)

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

    def seed(self, collection, doc_id, data):
        """Directly place a document, for the six route families below that
        each need a pre-existing record of their own shape (a link, an
        alert, a kit) rather than the firms/ledger fixtures the credit/firm
        tests above use."""
        self.docs[(collection, doc_id)] = dict(data)


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


# ==========================================================================
# COMPLETENESS: every admin_audit_log writer, not just credit_routes.py and
# firm_routes.py (fresh-eyes GAP, bd polyglot-pdf-uaxt5 round 2).
#
# `grep -rn "audit_log\.(record_in_transaction|record_pending|mark_committed)("
# admin_backend/routes/` lists EIGHT files: credit_routes.py and
# firm_routes.py (pinned above already), plus user_routes.py,
# sweep_routes.py, link_routes.py, kit_routes.py, config_routes.py,
# alert_routes.py -- pinned below. `target` is a free-form string by design
# across all eight (user_routes.py embeds the staff email in it, e.g.) and
# is OUT OF SCOPE for these allowlists on purpose: they cover before/after
# content only, never target's shape.
# ==========================================================================

def _admin_actor():
    return AdminActor(uid="admin-uid-1", email="ops@example.com")


def _app_admin_composite():
    return CompositeActor(uid="admin-uid-1", email="ops@example.com",
                          kind=ACTOR_KIND_APP_ADMIN)


def test_sweep_expired_link_audit_row_before_after_keys(fake_db):
    """sweep_routes.py's _sweep_channel -> credit_ledger.refund_expired_link's
    extra_writes hook -> audit_log.record_in_transaction, driven directly
    (the OIDC gate is a caller-identity concern this file does not need to
    exercise to pin the audit row's own shape)."""
    import backend.services.link_redemptions as link_redemptions
    import backend.services.links_store as links_store

    fake_db.seed(links_store._collection_name("demo"), "jti-sweep", {
        "jti": "jti-sweep", "firm_id": "acme", "kit_id": "w7",
        "employee_id": "emp-1", "credit_cost": 2, "cap_usd": 5.0,
        "minted_at": 1, "open_deadline": 10, "status": links_store.STATUS_MINTED,
        "revoked_by": None, "revoked_at": None, "expire_at": None,
    })

    result = sweep_routes._sweep_channel("demo", now=1000.0)
    assert result["refunded"] == 1, result

    rows = [r for r in fake_db.audit_rows()
            if r["action"] == sweep_routes.ACTION_EXPIRY_REFUND]
    assert len(rows) == 1
    assert set(rows[0]["before"]) == {"status"}
    assert set(rows[0]["after"]) == {"status"}


def test_link_revoke_audit_row_before_after_keys(fake_db):
    """link_routes.py's _do_revoke_link, driven directly with an app-admin
    actor (sidesteps _require_owning_firm's ownership check, which is not
    this file's concern)."""
    import backend.services.links_store as links_store

    fake_db.seed(links_store._collection_name("demo"), "jti-revoke", {
        "jti": "jti-revoke", "firm_id": "acme", "kit_id": "w7",
        "employee_id": "emp-1", "credit_cost": 2, "cap_usd": 5.0,
        "minted_at": 1, "open_deadline": 10, "status": links_store.STATUS_MINTED,
        "revoked_by": None, "revoked_at": None, "expire_at": None,
    })

    result = link_routes._do_revoke_link(
        jti="jti-revoke", channel="demo", actor=_app_admin_composite(),
        request_id=audit_log.new_request_id())
    assert result["before_status"] == links_store.STATUS_MINTED

    rows = [r for r in fake_db.audit_rows()
            if r["action"] == link_routes.ACTION_LINK_REVOKE]
    assert len(rows) == 1
    assert set(rows[0]["before"]) == {"status"}
    assert set(rows[0]["after"]) == {"status", "revoked_by", "revoked_at"}


def test_kit_commercial_set_audit_row_after_keys_and_dynamic_before(fake_db):
    """kit_routes.py's _apply_kit_commercial_write. `before` is the RAW
    stored kit doc (snap.to_dict()) -- unlike every other route pinned in
    this file, it is NOT a fixed key set (kits/{kit_id} has no single
    schema-owning writer the way firms/{firm_id} does), so this test pins
    `after` exactly and asserts `before` is whatever was actually stored
    beforehand (None on first write, the prior doc's own keys on an edit) --
    never asserting a false closed shape for it.
    """
    import backend.services.kit_commercials as kit_commercials

    result = kit_routes._apply_kit_commercial_write(
        db=fake_db, kit_id="w7", credit_cost=3, burn_cap_usd=1.5,
        display={"label": "Form W-7"}, actor=_admin_actor(),
        request_id=audit_log.new_request_id())
    assert result["before"] is None  # no prior kits/w7 doc

    rows = [r for r in fake_db.audit_rows()
            if r["action"] == kit_routes.ACTION_KIT_COMMERCIAL_SET]
    assert len(rows) == 1
    assert rows[0]["before"] is None  # no prior kits/w7 doc in this fake
    assert set(rows[0]["after"]) == {
        kit_commercials.CREDIT_COST_KEY, kit_commercials.BURN_CAP_USD_KEY,
        "display",
    }

    # A SECOND write, over the doc the first one just created, proves
    # `before` really does track "whatever was stored", not a fixed set --
    # it is now the first write's OWN `after`-shaped doc plus updated_by/
    # updated_at (kit_routes.py's own write payload, not this test's guess).
    result2 = kit_routes._apply_kit_commercial_write(
        db=fake_db, kit_id="w7", credit_cost=4, burn_cap_usd=2.0,
        display={}, actor=_admin_actor(),
        request_id=audit_log.new_request_id())
    assert result2["before"] is not None
    rows2 = [r for r in fake_db.audit_rows()
            if r["action"] == kit_routes.ACTION_KIT_COMMERCIAL_SET]
    assert len(rows2) == 2
    assert rows2[1]["before"] == {
        kit_commercials.CREDIT_COST_KEY: 3,
        kit_commercials.BURN_CAP_USD_KEY: 1.5,
        "display": {"label": "Form W-7"},
        "updated_by": _admin_actor().uid,
        "updated_at": "SERVER_TIMESTAMP",
    }


def test_config_set_audit_row_before_after_are_one_key_from_the_runtime_set(
        fake_db):
    """config_routes.py's _apply_config_write. before/after are each a
    SINGLE-KEY dict, but the key NAME is caller-chosen (validated by the
    route against runtime_config.RUNTIME_CONFIG_KEYS before this function
    ever runs) -- so the pin here is "exactly one key, and it is a real
    runtime-config key", not a fixed literal key name."""
    from backend.services import runtime_config

    key = next(iter(runtime_config.RUNTIME_CONFIG_KEYS))
    result = config_routes._apply_config_write(
        db=fake_db, channel="demo", key=key, value=True,
        actor=_admin_actor(), request_id=audit_log.new_request_id())
    assert result["before"] is None  # app_config/demo did not exist yet

    rows = [r for r in fake_db.audit_rows()
            if r["action"] == config_routes.ACTION_CONFIG_SET]
    assert len(rows) == 1
    assert set(rows[0]["before"]) == {key}
    assert set(rows[0]["after"]) == {key}
    assert set(rows[0]["before"]) <= runtime_config.RUNTIME_CONFIG_KEYS
    assert set(rows[0]["after"]) <= runtime_config.RUNTIME_CONFIG_KEYS


def test_alert_acknowledge_audit_row_before_after_keys(fake_db):
    """alert_routes.py's _do_acknowledge_alert, driven directly with an
    app-admin actor (sidesteps _require_owning_firm, not this file's
    concern)."""
    fake_db.seed(alert_routes.alerts.COLLECTION, "alert-1", {
        "firm_id": "acme", "kind": "credit_low", "level": "warning",
        "ts": 123.0, "context": {}, "expire_at": None,
        "acknowledged_by": None, "acknowledged_at": None, "emailed_at": None,
    })

    result = alert_routes._do_acknowledge_alert(
        alert_id="alert-1", actor=_app_admin_composite(),
        request_id=audit_log.new_request_id())
    assert result["acknowledged_at"] > 0

    rows = [r for r in fake_db.audit_rows()
            if r["action"] == alert_routes.ACTION_ALERT_ACKNOWLEDGE]
    assert len(rows) == 1
    assert set(rows[0]["before"]) == {"acknowledged_by"}
    assert set(rows[0]["after"]) == {"acknowledged_by", "acknowledged_at"}


def test_user_create_audit_row_before_after_keys(fake_db, monkeypatch):
    """user_routes.py's create_user -- the PENDING-THEN-COMMITTED form
    (record_pending then mark_committed), since a Firebase Auth create
    cannot join a Firestore transaction. Monkeypatches user_admin.
    create_staff_user directly (the ONE seam this route calls into) rather
    than building a full fake Auth SDK -- this file is pinning the AUDIT
    ROW's shape, not Auth SDK behavior, which test_user_routes.py already
    owns."""
    import admin_backend.services.user_admin as user_admin

    monkeypatch.setattr(
        user_admin, "create_staff_user",
        lambda *, email, firm_id, firm_role, display_name=None: {
            "uid": "new-uid-1", "email": email, "firm_id": firm_id,
            "firm_role": firm_role, "reset_link": "https://example/reset",
        },
    )

    body = user_routes.CreateUserRequest(
        email="new@acme.example", firm_role="employee", firm_id="acme")
    result = asyncio.run(user_routes.create_user(
        body=body, actor=_app_admin_composite()))
    assert result["uid"] == "new-uid-1"

    rows = [r for r in fake_db.audit_rows()
            if r["action"] == user_routes.ACTION_USER_CREATE]
    assert len(rows) == 1
    # `before` is None for the pending form's create (no prior audit-worthy
    # state -- see audit_log.record_pending's own docstring).
    assert rows[0]["before"] is None
    # The COMMITTED after (mark_committed's own value) is what a reader
    # sees once the row settles -- the pending-time after is overwritten.
    assert set(rows[0]["after"]) == {"uid", "firm_id", "firm_role"}


def test_user_disable_audit_row_before_after_keys(fake_db, monkeypatch):
    import admin_backend.services.user_admin as user_admin

    monkeypatch.setattr(
        user_admin, "get_user_claims",
        lambda uid: {"firm_id": "acme", "firm_role": "employee"},
    )
    monkeypatch.setattr(
        user_admin, "set_user_disabled",
        lambda *, uid, disabled: {"disabled": disabled, "was_disabled": False},
    )

    body = user_routes.DisableUserRequest(disabled=True, firm_id="acme")
    result = asyncio.run(user_routes.set_user_disabled(
        uid="staff-uid-1", body=body, actor=_app_admin_composite()))
    assert result["disabled"] is True

    rows = [r for r in fake_db.audit_rows()
            if r["action"] == user_routes.ACTION_USER_DISABLE]
    assert len(rows) == 1
    assert rows[0]["before"] is None
    assert set(rows[0]["after"]) == {"disabled", "was_disabled", "firm_id"}


def test_user_role_audit_row_before_after_keys(fake_db, monkeypatch):
    import admin_backend.services.user_admin as user_admin

    monkeypatch.setattr(
        user_admin, "get_user_claims",
        lambda uid: {"firm_id": "acme", "firm_role": "employee"},
    )
    monkeypatch.setattr(
        user_admin, "set_user_role",
        lambda *, uid, firm_id, firm_role: {
            "firm_role": firm_role, "before_role": "employee"},
    )

    body = user_routes.SetRoleRequest(firm_role="manager", firm_id="acme")
    result = asyncio.run(user_routes.set_user_role(
        uid="staff-uid-1", body=body, actor=_app_admin_composite()))
    assert result["firm_role"] == "manager"

    rows = [r for r in fake_db.audit_rows()
            if r["action"] == user_routes.ACTION_USER_ROLE]
    assert len(rows) == 1
    # The PENDING row's before -- user_routes.py records the CLAIMS it read
    # (firm_role + firm_id) before the write, unlike create/disable which
    # record None (there is no "before" identity for a brand-new account or
    # a disable that only flips a bool).
    assert set(rows[0]["before"]) == {"firm_role", "firm_id"}
    assert set(rows[0]["after"]) == {"firm_role", "firm_id"}


# --------------------------------------------------------------------------
# COMPLETENESS: a new audit-writing route without a table row above fails
# CI, mechanically, by grepping the route modules for every
# audit_log.record_* call site.
# --------------------------------------------------------------------------

# One row per (file, action) this file's tests above actually exercise.
# Keys are the route module's filename (matching what the grep below finds)
# mapped to the set of ACTION_* values that module's audit-writing routes
# use -- not every literal call SITE (kit_routes.py's transaction has one
# call site for one action; user_routes.py has three call sites for three
# actions; credit_routes.py has a third action, monthly_topup, deliberately
# excluded below -- see its own comment).
AUDITED_ACTIONS_BY_FILE = {
    "credit_routes.py": {
        credit_routes.ACTION_CREDITS_GRANT,
        credit_routes.ACTION_CREDITS_ADJUST,
        # ACTION_CREDITS_MONTHLY_TOPUP is a Cloud-Scheduler-only route with
        # no operator-facing before/after content risk (its `after` is
        # {period, amount, monthly_credits, rollover} -- all derived from
        # the firm's OWN stored plan, never operator free text) -- out of
        # scope for THIS file's PF-9-style content pins, which are about a
        # HUMAN operator's free-text input reaching a store. Tracked instead
        # by test_admin_audit_coverage.py's _EXTRA_WRITES_TRANSACTION_OPENERS
        # shape check.
        credit_routes.ACTION_CREDITS_MONTHLY_TOPUP,
    },
    "firm_routes.py": {
        firm_routes.ACTION_FIRM_CREATE, firm_routes.ACTION_FIRM_STATUS,
        firm_routes.ACTION_FIRM_ALLOWED_KITS, firm_routes.ACTION_FIRM_KIND,
        firm_routes.ACTION_FIRM_PLAN,
    },
    "user_routes.py": {
        user_routes.ACTION_USER_CREATE, user_routes.ACTION_USER_DISABLE,
        user_routes.ACTION_USER_ROLE,
    },
    "sweep_routes.py": {sweep_routes.ACTION_EXPIRY_REFUND},
    "link_routes.py": {link_routes.ACTION_LINK_REVOKE},
    "kit_routes.py": {kit_routes.ACTION_KIT_COMMERCIAL_SET},
    "config_routes.py": {config_routes.ACTION_CONFIG_SET},
    "alert_routes.py": {alert_routes.ACTION_ALERT_ACKNOWLEDGE},
    # The deploy pair (bd polyglot-pdf-tb3kp). Neither carries operator
    # free text: the trigger route audits a (target, sha) pair already
    # validated against deploy/targets.py and a 40-hex regex, and the
    # webhook audits a status Cloud Build itself sent. Listed so the
    # completeness grep stays satisfied by a deliberate row rather than
    # by silence.
    "deploy_routes.py": {deploy_routes.ACTION_DEPLOY_TRIGGER},
    "deploy_webhook.py": {deploy_webhook.ACTION_DEPLOY_STATUS_UPDATE},
}

_ROUTES_DIR = Path(admin_backend_routes_path := credit_routes.__file__).parent

_MODULE_BY_FILENAME = {
    "credit_routes.py": credit_routes,
    "firm_routes.py": firm_routes,
    "user_routes.py": user_routes,
    "sweep_routes.py": sweep_routes,
    "link_routes.py": link_routes,
    "kit_routes.py": kit_routes,
    "config_routes.py": config_routes,
    "alert_routes.py": alert_routes,
    "deploy_routes.py": deploy_routes,
    "deploy_webhook.py": deploy_webhook,
}

# The three audit_log entry points that take (or, for mark_committed,
# never take) an `action=` keyword. Matched by bare attribute/name (fresh-
# eyes nit: a `from ...audit_log import record_in_transaction` alias must
# resolve too -- see _is_audit_writer_call below).
_AUDIT_WRITER_NAMES = frozenset({"record_in_transaction", "record_pending"})


class _UnresolvableAction(Exception):
    """An action= argument could not be traced to a literal ACTION_*
    constant. Raised, never swallowed -- the fresh-eyes GAP this rewrite
    fixes was exactly a silent drop of unresolvable cases, so this walker
    fails loudly instead (module docstring: 'if unresolvable, FAIL loudly,
    never skip')."""


def _is_audit_writer_call(call_node: ast.Call) -> bool:
    func = call_node.func
    if isinstance(func, ast.Attribute):
        return func.attr in _AUDIT_WRITER_NAMES
    if isinstance(func, ast.Name):
        return func.id in _AUDIT_WRITER_NAMES
    return False


def _action_arg_node(call_node: ast.Call):
    """The AST node bound to `action=` on this writer call, or None if the
    call carries no such keyword (mark_committed never does)."""
    for kw in call_node.keywords:
        if kw.arg == "action":
            return kw.value
    return None


def _enclosing_functions(tree: ast.AST, target: ast.AST) -> "list":
    """Every FunctionDef/AsyncFunctionDef in `tree` that contains `target`,
    innermost first -- a name referenced inside a nested closure
    (config_routes.py's `_txn(tx):`, or credit_routes.py's `_audit(tx,
    firm):`) can be a FREE VARIABLE closed over from an OUTER function
    (credit_routes.py's `action = kwargs.pop("_action")` lives in
    `_run_append_entry`, one level up from the `_audit` closure that
    actually calls record_in_transaction), so a caller resolving a
    parameter/kwargs-pop reference must be able to walk outward, not just
    take the single innermost function."""
    containing = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if sub is target:
                containing.append(node)
                break
    # Innermost first: the SMALLEST span is the most deeply nested.
    containing.sort(key=_node_span)
    return containing


def _node_span(node: ast.AST) -> int:
    """A rough 'how much source this node covers' proxy (end minus start
    line), used only to prefer the SMALLEST (innermost) enclosing function
    when more than one contains the target node."""
    return getattr(node, "end_lineno", node.lineno) - node.lineno


def _param_names(func_node) -> "list[str]":
    args = func_node.args
    return [a.arg for a in (args.posonlyargs + args.args + args.kwonlyargs)]


def _kwargs_pop_key(func_node, param_name: str):
    """If `param_name` is assigned via `param_name = kwargs.pop("KEY")`
    inside `func_node` (credit_routes.py's _run_append_entry shape --
    `action = kwargs.pop("_action")`), return "KEY"; else None.
    """
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != param_name:
            continue
        call = node.value
        if (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "pop"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "kwargs"
                and call.args
                and isinstance(call.args[0], ast.Constant)):
            return call.args[0].value
    return None


def _call_site_keyword_or_positional(call_node: ast.Call, func_node,
                                     param_name: str):
    """The AST node bound to `param_name` at ONE call site of `func_node`,
    matching either a keyword (`param_name=...` or, for the
    kwargs.pop("_action") shape, `_action=...`) or the equivalent
    positional slot. Returns None if this call site does not supply it
    (a default was used, or it truly is not passed -- callers of this
    helper decide whether that is an error).
    """
    pop_key = _kwargs_pop_key(func_node, param_name)
    keyword_names = {param_name}
    if pop_key is not None:
        keyword_names.add(pop_key)

    for kw in call_node.keywords:
        if kw.arg in keyword_names:
            return kw.value

    # Positional fallback: only meaningful when the parameter is a plain
    # positional/regular arg (not the **kwargs-popped shape, which is never
    # positional in this repo's call sites).
    if pop_key is None:
        params = _param_names(func_node)
        if param_name in params:
            idx = params.index(param_name)
            if idx < len(call_node.args):
                return call_node.args[idx]
    return None


# asyncio.to_thread(func, *args, **kwargs) is this repo's own convention
# for running a sync Firestore/Auth helper off the event loop (every route
# in this file's coverage does this) -- a plain `ast.Call` walk looking
# for `Call(func=Name(id=owner.name))` misses every one of these, since
# the actual keyword arguments (credit_routes.py's `_action=...` among
# them) live on the OUTER `asyncio.to_thread(...)` call, with `owner.name`
# passed as to_thread's first positional argument, not called directly.
def _call_sites_of(tree: ast.AST, func_name: str) -> "list[ast.Call]":
    """Every ast.Call that invokes `func_name`, either directly
    (`func_name(...)`) or via `asyncio.to_thread(func_name, ...)` -- in the
    to_thread case, the RETURNED node is the to_thread call itself, since
    that is where the keyword arguments actually live."""
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        direct_name = (func.id if isinstance(func, ast.Name)
                       else func.attr if isinstance(func, ast.Attribute)
                       else None)
        if direct_name == func_name:
            sites.append(node)
            continue
        is_to_thread = (
            (isinstance(func, ast.Attribute) and func.attr == "to_thread")
            or (isinstance(func, ast.Name) and func.id == "to_thread")
        )
        if is_to_thread and node.args and isinstance(node.args[0], ast.Name) \
                and node.args[0].id == func_name:
            sites.append(node)
    return sites


def _resolve_action_names(tree: ast.AST, module, source_file: str) -> set:
    """Every ACTION_* string VALUE actually reachable from an `action=`
    argument to record_in_transaction/record_pending in this module's
    AST -- resolving straight-through module-level constant references
    AND indirect ones (the argument is a function PARAMETER, and the
    actual constant is supplied by each call site of that function in the
    same module -- firm_routes.py's `_apply_firm_patch(action, ...)` and
    credit_routes.py's `_run_append_entry(..., **kwargs)` with
    `action = kwargs.pop("_action")` are both this shape).

    FAILS LOUDLY (raises _UnresolvableAction) rather than silently
    dropping anything it cannot trace -- the fresh-eyes gap this function
    exists to close was exactly a silent drop (the old regex-based
    version's `hasattr` filter).
    """
    resolved = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_audit_writer_call(node)):
            continue
        arg = _action_arg_node(node)
        if arg is None:
            # mark_committed never carries action=; a record_* call with no
            # action= at all would be a different, real bug -- but that is
            # exactly what the OTHER coverage test in this file
            # (test_admin_audit_coverage.py's sibling machinery) pins via a
            # different property. This function's only job is resolving
            # actions that ARE present.
            continue

        if isinstance(arg, ast.Attribute):
            # module.ACTION_X -- not a shape any file in this repo uses
            # today, but resolve it rather than fail if one ever does.
            const_name = arg.attr
        elif isinstance(arg, ast.Name):
            const_name = arg.id
        else:
            raise _UnresolvableAction(
                "cannot resolve action for {}:{} -- action= is neither a "
                "plain name nor an attribute reference ({!r})".format(
                    source_file, node.lineno, ast.dump(arg))
            )

        if hasattr(module, const_name):
            resolved.add(getattr(module, const_name))
            continue

        # Not a module-level constant: must be a parameter (or a
        # kwargs.pop("_KEY")-derived local) of SOME enclosing function --
        # tried innermost first, then outward, since the name can be a
        # FREE VARIABLE closed over from an outer function (credit_routes
        # .py's `_audit(tx, firm)` closure reads `action`, which is
        # actually bound one level up in `_run_append_entry` via
        # `action = kwargs.pop("_action")`).
        owner = None
        for candidate in _enclosing_functions(tree, node):
            if (const_name in _param_names(candidate)
                    or _kwargs_pop_key(candidate, const_name) is not None):
                owner = candidate
                break
        if owner is None:
            raise _UnresolvableAction(
                "cannot resolve action for {}:{} -- {!r} is not a "
                "module-level ACTION_* constant and not a parameter (or "
                "kwargs.pop-derived local) of any enclosing function".format(
                    source_file, node.lineno, const_name)
            )

        found_any_call_site = False
        for call_site in _call_sites_of(tree, owner.name):
            value_node = _call_site_keyword_or_positional(
                call_site, owner, const_name)
            if value_node is None:
                continue
            found_any_call_site = True
            if isinstance(value_node, ast.Attribute):
                call_const_name = value_node.attr
            elif isinstance(value_node, ast.Name):
                call_const_name = value_node.id
            else:
                raise _UnresolvableAction(
                    "cannot resolve action for {}:{} -- {}() is called "
                    "with a non-name/attribute value for {!r} at line {} "
                    "({!r})".format(
                        source_file, node.lineno, owner.name,
                        const_name, call_site.lineno, ast.dump(value_node))
                )
            if not hasattr(module, call_const_name):
                raise _UnresolvableAction(
                    "cannot resolve action for {}:{} -- {}() caller at "
                    "line {} passes {!r} for {!r}, which is not a "
                    "module-level constant".format(
                        source_file, node.lineno, owner.name,
                        call_site.lineno, call_const_name, const_name)
                )
            resolved.add(getattr(module, call_const_name))

        if not found_any_call_site:
            raise _UnresolvableAction(
                "cannot resolve action for {}:{} -- {!r} is bound in "
                "{}(), but no call site in this module supplies it".format(
                    source_file, node.lineno, const_name, owner.name)
            )

    return resolved


def test_every_audit_writing_route_file_has_a_table_row():
    """A new file calling audit_log.record_in_transaction/record_pending
    without a row in AUDITED_ACTIONS_BY_FILE fails here -- the mechanical
    half of the fresh-eyes gap: 'a new audit-writing route without a pin
    fails CI'.

    Mutation: remove one row from AUDITED_ACTIONS_BY_FILE (e.g.
    "alert_routes.py") -- this goes red, since that file's action constant
    is still referenced by the source grep below but no longer has a table
    entry to match against.
    """
    writer_files = sorted(
        p.name for p in _ROUTES_DIR.glob("*.py")
        if "audit_log.record_in_transaction(" in p.read_text(encoding="utf-8")
        or "audit_log.record_pending(" in p.read_text(encoding="utf-8")
    )
    # Every file that calls a writer must have a table row.
    missing = set(writer_files) - set(AUDITED_ACTIONS_BY_FILE)
    assert not missing, (
        "these admin_backend/routes/*.py files call an audit_log writer "
        "but have no row in AUDITED_ACTIONS_BY_FILE: {} -- add one (see "
        "this file's module docstring section)".format(sorted(missing))
    )
    # And no table row names a file that no longer writes at all (a stale
    # entry hides a real removal rather than describing current code).
    stale = set(AUDITED_ACTIONS_BY_FILE) - set(writer_files)
    assert not stale, (
        "AUDITED_ACTIONS_BY_FILE names {} but that file no longer calls an "
        "audit_log writer -- remove the stale row".format(sorted(stale))
    )


def test_every_referenced_action_constant_is_in_the_table():
    """The content half: every action= constant actually reachable in each
    audited file's source (AST-resolved, not regex-matched -- see the
    module-level rewrite above, fresh-eyes round 3) must appear in that
    file's table entry -- so a NEW action added to an already-covered file
    (a second mutating route in kit_routes.py, say) without extending the
    table also fails here, and so does an action= that is an indirect
    parameter/kwargs-pop reference the old regex-based version silently
    dropped (bd polyglot-pdf-uaxt5 fresh-eyes round 3: config_routes.py's
    nested-closure indentation defeated the old regex entirely; firm_routes
    .py's `_apply_firm_patch(action, ...)` and credit_routes.py's
    `_run_append_entry`'s `kwargs.pop("_action")` both resolved to nothing
    under `hasattr` and were silently dropped).

    Mutation (proven on a scratch copy, not committed): rename
    ACTION_CONFIG_SET to ACTION_CONFIG_WIPE in config_routes.py -- the OLD
    regex-based test stayed GREEN under this rename (config_routes.py's
    call is indented 8 spaces, inside the `_txn` closure, so the old
    `\\n    )` regex never matched it at all -- zero actions were ever
    checked for that file). This AST version goes RED, since
    ACTION_CONFIG_WIPE is a real, resolved module-level constant not
    present in AUDITED_ACTIONS_BY_FILE["config_routes.py"].
    """
    for filename, table_actions in AUDITED_ACTIONS_BY_FILE.items():
        path = _ROUTES_DIR / filename
        module = _MODULE_BY_FILENAME[filename]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        resolved = _resolve_action_names(tree, module, filename)
        missing = resolved - table_actions
        assert not missing, (
            "{} references audit action(s) {} not listed in "
            "AUDITED_ACTIONS_BY_FILE[{!r}] -- add them, and if they carry "
            "operator free text, add a content-shape test above too".format(
                filename, missing, filename)
        )


# --- e8wzz: the firm-kind reason (the PF-9 class, second site) ------------------------


def test_admin_firm_kind_set_log_line_has_no_reason(client, fake_db, monkeypatch):
    """Same rule as admin_credits_adjusted (bd polyglot-pdf-e8wzz): the
    operator's free-text reason stays in the audit row and never reaches a
    log line. Mutation: restore `reason=body.reason` on the call -> red."""
    from admin_backend.routes import firm_routes
    mock_log = MagicMock()
    monkeypatch.setattr(firm_routes, "_log", mock_log)
    resp = client.patch("/admin/firms/acme/kind", json={
        "kind": "live", "reason": "a client's intake notes should never land here",
    })
    assert resp.status_code == 200, resp.text
    calls = [c for c in mock_log.info.call_args_list
             if c.args and c.args[0] == "admin_firm_kind_set"]
    assert len(calls) == 1, "expected exactly one admin_firm_kind_set line"
    _, kwargs = calls[0]
    assert "reason" not in kwargs, "admin_firm_kind_set logged the operator's reason"
    for value in kwargs.values():
        assert "intake notes" not in str(value)


def test_the_firm_kind_reason_is_bounded_like_the_credit_reason():
    """One number: credit_ledger.REASON_MAX_LENGTH bounds both operator
    free-text doors. Mutation: drop the Field(max_length=...) -> red."""
    from pydantic import ValidationError
    from admin_backend.routes.firm_routes import SetKindRequest
    from backend.services import credit_ledger
    SetKindRequest(kind="live", reason="x" * credit_ledger.REASON_MAX_LENGTH)
    with pytest.raises(ValidationError):
        SetKindRequest(kind="live", reason="x" * (credit_ledger.REASON_MAX_LENGTH + 1))


# --- the SET: no log line in either backend carries client-supplied free text ------


_FREE_TEXT_KWARGS = {"reason", "note", "notes", "comment", "comments", "description", "message"}
_BODY_NAMES = {"body", "req", "request", "payload", "data"}
# The terminal levels AND structlog's context binders: a `log.bind(reason=body.x)`
# threads the value into every later line (fresh-eyes on bd e8wzz).
_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "critical", "exception",
                "bind", "new", "unbind"}


def _client_free_text_log_sites(root):
    """Every `<log>.<level>(..., reason=body.<x>)`-shaped kwarg: a log call whose
    keyword is a free-text name and whose value is an attribute of a request
    body. Walks both services' routes dirs (scar #8: the set, not the site)."""
    import pathlib
    hits = []
    walked = {"modules": 0, "log_calls": 0}
    for base in ("backend/routes", "admin_backend/routes"):
        for path in sorted((root / base).glob("*.py")):
            walked["modules"] += 1
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if not (isinstance(fn, ast.Attribute) and fn.attr in _LOG_METHODS):
                    continue
                walked["log_calls"] += 1
                for kw in node.keywords:
                    v = kw.value
                    if (kw.arg in _FREE_TEXT_KWARGS and isinstance(v, ast.Attribute)
                            and isinstance(v.value, ast.Name) and v.value.id in _BODY_NAMES):
                        hits.append("{}:{} {}={}.{}".format(
                            path.name, node.lineno, kw.arg, v.value.id, v.attr))
    return hits, walked


def test_no_log_line_in_either_backend_carries_client_supplied_free_text():
    """The PF-9 set (bd polyglot-pdf-uaxt5 fixed credit-adjust; e8wzz the
    firm-kind route): zero log kwargs named like free text whose value comes
    straight off a request body. Mutation: restore either site -> red, and
    the test names the site."""
    import ast as _ast  # noqa: F401  (the module-level import is what the walker uses)
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[3]
    assert (root / "backend" / "routes").is_dir() and (root / "admin_backend" / "routes").is_dir()
    hits, walked = _client_free_text_log_sites(root)
    # Guard the guard (the outer review on e8wzz): an empty hit list must mean
    # "clean", never "walked nothing" -- the sibling sweep in
    # test_no_pii_logging.py carries the same floor. 26 route modules and
    # several hundred log calls today.
    assert walked["modules"] >= 20, walked
    assert walked["log_calls"] >= 100, walked
    assert hits == [], "client-supplied free text reaches a log line at: {}".format(hits)
