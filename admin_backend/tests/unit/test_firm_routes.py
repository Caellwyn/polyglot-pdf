"""Firm CRUD routes (bd polyglot-pdf-zopqq, Epic 2 Track B bead B1).

EXIT CRITERIA THIS FILE PINS:

  2 (its firm-CRUD half). POST /admin/firms refuses a missing `kind` with
     422, and every route here carries require_app_admin -- proven
     end-to-end through test_admin_route_auth.py's set-derived pin, which
     this file does not re-derive; it only proves the 422 behavior.
  3. GET /admin/firms/{firm_id} returns the balance AFTER lazy
     reconciliation of an expired unopened link, via a fake credit_ledger
     that records which channels reconcile_expired_for_firm was called
     with and mutates the balance as a side effect the route must observe.

THE FAKE FIRESTORE below is the SAME shape as test_config_routes.py's --
a real, buffered, all-or-nothing transaction so "a forced audit failure
leaves the firm doc unchanged" is an assertion about actual behavior, not a
tautology.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import firm_routes
from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import firms


# --------------------------------------------------------------------------
# A minimal Firestore stand-in with REAL transaction semantics AND nested
# subcollection support (test_config_routes.py's _FakeDb/_Transaction,
# generalized to the tuple-path shape test_credit_ledger.py's fake uses --
# get_firm() reads firms/{id}/ledger via credit_ledger.read_entries(), which
# a flat (collection, doc_id) path cannot address).
# --------------------------------------------------------------------------

class _Snap:
    def __init__(self, path, data):
        self.id = path[-1] if data is not None else None
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
        # Kept for _Transaction.set's audit-collection check below: the
        # collection a doc lives directly under is the path's second-to-
        # last segment for both a top-level doc (("firms","acme")) and a
        # nested one (("firms","acme","ledger","e1")).
        self.collection_id = path[-2]

    def collection(self, name):
        return _Collection(self._store, self._path + (name,))

    def get(self, transaction=None):
        if self._store.read_error is not None:
            raise self._store.read_error
        return _Snap(self._path, self._store.docs.get(self._path))

    def set(self, data, merge=False):
        self._store.apply_set(self._path, data, merge)

    def update(self, data):
        existing = self._store.docs.setdefault(self._path, {})
        existing.update(data)


class _Query:
    def __init__(self, store, path, order_field=None):
        self._store = store
        self._path = path
        self._order = order_field

    def order_by(self, field, direction="ASCENDING"):
        return _Query(self._store, self._path, field)

    def limit(self, n):
        return self  # unused by this file's routes; read_entries takes None

    def stream(self):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path
        ]
        if self._order:
            rows.sort(key=lambda kv: kv[1].get(self._order))
        return [_Snap(path, data) for path, data in rows]


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

    def stream(self):
        return _Query(self._store, self._path).stream()


class _Transaction:
    def __init__(self, store):
        self._store = store
        self._buffer = []

    def set(self, ref, data, merge=False):
        if self._store.audit_write_error is not None and (
                ref.collection_id == audit_log.COLLECTION):
            raise self._store.audit_write_error
        self._buffer.append((ref._path, dict(data), merge))

    def commit(self):
        for path, data, merge in self._buffer:
            self._store.apply_set(path, data, merge)
        self._buffer = []


class _FakeDb:
    def __init__(self, docs=None):
        # {(collection, doc_id, [subcollection, doc_id, ...]): {...}}
        self.docs = dict(docs or {})
        self.read_error = None
        self.audit_write_error = None
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

    # test helpers ---------------------------------------------------
    def firm(self, firm_id):
        return self.docs.get(("firms", firm_id))

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
    db = _FakeDb()
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


def _seed_firm(fake_db, firm_id="acme", **over):
    doc = {
        "name": "Acme LLC", "contact_email": "ops@acme.example",
        "allowed_kits": ["w7"], "status": firms.FIRM_STATUS_ACTIVE,
        "kind": firms.FIRM_KIND_LIVE, "balance_credits": 100,
        "balance_updated_at": 1000.0,
    }
    doc.update(over)
    fake_db.docs[("firms", firm_id)] = doc
    return doc


# --------------------------------------------------------------------------
# POST /admin/firms
# --------------------------------------------------------------------------

def test_create_firm_requires_kind(client, fake_db):
    """EXIT CRITERION 2: a missing kind is refused with 422 before any
    write. Mutation: make `kind` optional on CreateFirmRequest -- this goes
    red (the request would then reach the handler and write a firm with no
    kind, or crash trying)."""
    resp = client.post("/admin/firms", json={
        "firm_id": "newco", "name": "NewCo", "contact_email": "a@b.com",
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.docs == {}


@pytest.mark.parametrize("kind", ["Mock", "LIVE", "", "test", "premium"])
def test_create_firm_refuses_an_invalid_kind(client, fake_db, kind):
    resp = client.post("/admin/firms", json={
        "firm_id": "newco", "name": "NewCo", "contact_email": "a@b.com",
        "kind": kind,
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.docs == {}


def test_create_firm_writes_the_doc_and_exactly_one_audit_row(client, fake_db):
    resp = client.post("/admin/firms", json={
        "firm_id": "newco", "name": "NewCo", "contact_email": "a@b.com",
        "kind": "mock", "allowed_kits": ["w7", "i-90"],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] is True

    doc = fake_db.firm("newco")
    assert doc["name"] == "NewCo"
    assert doc["kind"] == "mock"
    assert doc["status"] == firms.FIRM_STATUS_ACTIVE
    assert doc["allowed_kits"] == ["w7", "i-90"]
    assert doc["balance_credits"] == 0

    rows = fake_db.audit_rows()
    assert len(rows) == 1
    assert rows[0]["action"] == firm_routes.ACTION_FIRM_CREATE
    assert rows[0]["actor_uid"] == "admin-uid-1"
    assert rows[0]["state"] == audit_log.STATE_COMMITTED
    assert audit_log.ROW_FIELDS <= set(rows[0])


def test_a_forced_audit_failure_leaves_no_firm_created(client, fake_db):
    """EXIT CRITERION 1 (shared form, over the create writer): a Firestore
    mutation that audits outside its transaction would still create the
    firm. Mutation: move record_in_transaction outside create_firm's
    @firestore.transactional body -- this goes red because the firm doc
    would then exist despite the forced failure."""
    fake_db.audit_write_error = RuntimeError("audit sink refused")
    resp = client.post("/admin/firms", json={
        "firm_id": "newco", "name": "NewCo", "contact_email": "a@b.com",
        "kind": "mock",
    })
    assert resp.status_code == 500
    assert fake_db.firm("newco") is None
    assert fake_db.audit_rows() == []


def test_create_firm_on_an_existing_firm_does_not_reset_balance(
        client, fake_db):
    """Mirrors upsert_firm's own re-run contract: balance_credits is
    omitted from the merge payload on an existing doc."""
    _seed_firm(fake_db, "acme", balance_credits=250)
    resp = client.post("/admin/firms", json={
        "firm_id": "acme", "name": "Acme Renamed",
        "contact_email": "ops@acme.example", "kind": "live",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] is False
    assert fake_db.firm("acme")["balance_credits"] == 250
    assert fake_db.firm("acme")["name"] == "Acme Renamed"


# --------------------------------------------------------------------------
# GET /admin/firms
# --------------------------------------------------------------------------

def test_list_firms_returns_kind_balance_and_status(client, fake_db):
    _seed_firm(fake_db, "acme", kind="live", balance_credits=42,
              status=firms.FIRM_STATUS_ACTIVE)
    _seed_firm(fake_db, "zenith", kind="mock", balance_credits=7,
              status=firms.FIRM_STATUS_SUSPENDED)

    resp = client.get("/admin/firms")
    assert resp.status_code == 200, resp.text
    rows = {r["firm_id"]: r for r in resp.json()["firms"]}
    assert rows["acme"]["kind"] == "live"
    assert rows["acme"]["balance_credits"] == 42
    assert rows["acme"]["status"] == firms.FIRM_STATUS_ACTIVE
    assert rows["zenith"]["kind"] == "mock"
    assert rows["zenith"]["balance_credits"] == 7
    assert rows["zenith"]["status"] == firms.FIRM_STATUS_SUSPENDED


def test_list_firms_writes_no_audit_row(client, fake_db):
    _seed_firm(fake_db, "acme")
    client.get("/admin/firms")
    assert fake_db.audit_rows() == []


# --------------------------------------------------------------------------
# GET /admin/firms/{firm_id} -- EXIT CRITERION 3: reconcile before balance.
# --------------------------------------------------------------------------

def test_get_firm_404s_for_an_unknown_firm(client, fake_db):
    resp = client.get("/admin/firms/ghost")
    assert resp.status_code == 404


def test_get_firm_returns_profile_balance_and_ledger(client, fake_db):
    _seed_firm(fake_db, "acme")
    fake_db.docs[("firms", "acme", "ledger", "e1")] = {
        "type": "promo_grant", "amount": 100, "usd_amount": None,
        "firm_kind": "live", "channel": None, "balance_after": 100,
        "actor": "system:seed", "reason": None, "link_jti": None,
        "kit_id": None, "ts": 1.0,
    }
    resp = client.get("/admin/firms/acme")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["firm_id"] == "acme"
    assert body["balance_credits"] == 100
    assert len(body["ledger"]) == 1
    assert body["ledger"][0]["type"] == "promo_grant"
    assert body["ledger_truncated"] is False


def test_get_firm_runs_reconciliation_before_reading_the_balance(
        client, fake_db, monkeypatch):
    """EXIT CRITERION 3, the pin that matters: reconcile_expired_for_firm
    is called (once per KNOWN_CHANNELS entry) BEFORE the firm doc backing
    the response is read, and the response reflects whatever reconciliation
    changed. Mutation: delete the reconcile_expired_for_firm call from
    get_firm -- this goes red because the balance would then read 100 (the
    stale ledger.py 0-credit call never happens) instead of 130."""
    _seed_firm(fake_db, "acme", balance_credits=100)
    calls = []

    def _fake_reconcile(firm_id, channel=None, now=None):
        calls.append((firm_id, channel))
        # Simulate a refund actually crediting the firm -- exactly what a
        # real reconcile_expired_for_firm call does via append_entry.
        fake_db.docs[("firms", "acme")]["balance_credits"] += 15
        return [{"amount": 15}]

    monkeypatch.setattr(
        "backend.services.credit_ledger.reconcile_expired_for_firm",
        _fake_reconcile,
    )

    resp = client.get("/admin/firms/acme")
    assert resp.status_code == 200, resp.text
    # Two channels, one call each, BOTH run (100 + 15 + 15 = 130).
    assert sorted(calls) == [("acme", "demo"), ("acme", "staging")]
    assert resp.json()["balance_credits"] == 130


def test_get_firm_tolerates_a_reconciliation_failure_on_one_channel(
        client, fake_db, monkeypatch):
    """A reconcile failure on ONE channel must not 500 the whole page --
    the other channel's reconciliation and the balance read still happen."""
    _seed_firm(fake_db, "acme", balance_credits=100)

    def _flaky_reconcile(firm_id, channel=None, now=None):
        if channel == "demo":
            raise RuntimeError("firestore hiccup")
        fake_db.docs[("firms", "acme")]["balance_credits"] += 15
        return [{"amount": 15}]

    monkeypatch.setattr(
        "backend.services.credit_ledger.reconcile_expired_for_firm",
        _flaky_reconcile,
    )

    resp = client.get("/admin/firms/acme")
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance_credits"] == 115


def test_get_firm_writes_no_audit_row(client, fake_db, monkeypatch):
    _seed_firm(fake_db, "acme")
    monkeypatch.setattr(
        "backend.services.credit_ledger.reconcile_expired_for_firm",
        lambda *a, **k: [],
    )
    client.get("/admin/firms/acme")
    assert fake_db.audit_rows() == []


# --------------------------------------------------------------------------
# PATCH /admin/firms/{firm_id}/status
# --------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["active", "suspended"])
def test_set_status_writes_the_value_and_one_audit_row(
        client, fake_db, status):
    _seed_firm(fake_db, "acme", status=firms.FIRM_STATUS_ACTIVE
              if status == "suspended" else firms.FIRM_STATUS_SUSPENDED)
    resp = client.patch("/admin/firms/acme/status", json={"status": status})
    assert resp.status_code == 200, resp.text
    assert fake_db.firm("acme")["status"] == status
    rows = fake_db.audit_rows()
    assert len(rows) == 1
    assert rows[0]["action"] == firm_routes.ACTION_FIRM_STATUS
    assert rows[0]["after"] == {"status": status}


def test_set_status_refuses_an_unknown_value(client, fake_db):
    _seed_firm(fake_db, "acme")
    resp = client.patch("/admin/firms/acme/status",
                        json={"status": "archived"})
    assert resp.status_code == 422
    assert fake_db.firm("acme")["status"] == firms.FIRM_STATUS_ACTIVE
    assert fake_db.audit_rows() == []


def test_set_status_404s_for_an_unknown_firm(client, fake_db):
    resp = client.patch("/admin/firms/ghost/status", json={"status": "active"})
    assert resp.status_code == 404
    assert fake_db.audit_rows() == []


def test_a_forced_audit_failure_leaves_status_unchanged(client, fake_db):
    _seed_firm(fake_db, "acme", status=firms.FIRM_STATUS_ACTIVE)
    fake_db.audit_write_error = RuntimeError("audit sink refused")
    resp = client.patch("/admin/firms/acme/status",
                        json={"status": "suspended"})
    assert resp.status_code == 500
    assert fake_db.firm("acme")["status"] == firms.FIRM_STATUS_ACTIVE
    assert fake_db.audit_rows() == []


def test_set_status_preserves_the_firms_other_fields(client, fake_db):
    _seed_firm(fake_db, "acme", allowed_kits=["w7"], kind="live")
    client.patch("/admin/firms/acme/status", json={"status": "suspended"})
    doc = fake_db.firm("acme")
    assert doc["allowed_kits"] == ["w7"]
    assert doc["kind"] == "live"


# --------------------------------------------------------------------------
# PATCH /admin/firms/{firm_id}/allowed_kits
# --------------------------------------------------------------------------

def test_set_allowed_kits_writes_the_list_and_one_audit_row(client, fake_db):
    _seed_firm(fake_db, "acme", allowed_kits=["w7"])
    resp = client.patch("/admin/firms/acme/allowed_kits",
                        json={"allowed_kits": ["w7", "i-90", "n-400"]})
    assert resp.status_code == 200, resp.text
    assert fake_db.firm("acme")["allowed_kits"] == ["w7", "i-90", "n-400"]
    rows = fake_db.audit_rows()
    assert len(rows) == 1
    assert rows[0]["before"] == {"allowed_kits": ["w7"]}
    assert rows[0]["after"] == {"allowed_kits": ["w7", "i-90", "n-400"]}


def test_set_allowed_kits_accepts_an_empty_list(client, fake_db):
    _seed_firm(fake_db, "acme", allowed_kits=["w7"])
    resp = client.patch("/admin/firms/acme/allowed_kits",
                        json={"allowed_kits": []})
    assert resp.status_code == 200, resp.text
    assert fake_db.firm("acme")["allowed_kits"] == []


def test_set_allowed_kits_404s_for_an_unknown_firm(client, fake_db):
    resp = client.patch("/admin/firms/ghost/allowed_kits",
                        json={"allowed_kits": []})
    assert resp.status_code == 404
    assert fake_db.audit_rows() == []


def test_a_forced_audit_failure_leaves_allowed_kits_unchanged(
        client, fake_db):
    _seed_firm(fake_db, "acme", allowed_kits=["w7"])
    fake_db.audit_write_error = RuntimeError("audit sink refused")
    resp = client.patch("/admin/firms/acme/allowed_kits",
                        json={"allowed_kits": ["i-90"]})
    assert resp.status_code == 500
    assert fake_db.firm("acme")["allowed_kits"] == ["w7"]
    assert fake_db.audit_rows() == []


# --------------------------------------------------------------------------
# PATCH /admin/firms/{firm_id}/kind
# --------------------------------------------------------------------------

def test_set_kind_requires_a_reason(client, fake_db):
    _seed_firm(fake_db, "acme", kind="live")
    resp = client.patch("/admin/firms/acme/kind",
                        json={"kind": "mock", "reason": ""})
    assert resp.status_code == 422
    assert fake_db.firm("acme")["kind"] == "live"
    assert fake_db.audit_rows() == []


def test_set_kind_requires_the_reason_field_at_all(client, fake_db):
    _seed_firm(fake_db, "acme", kind="live")
    resp = client.patch("/admin/firms/acme/kind", json={"kind": "mock"})
    assert resp.status_code == 422
    assert fake_db.firm("acme")["kind"] == "live"


@pytest.mark.parametrize("kind", ["Mock", "LIVE", "test", ""])
def test_set_kind_refuses_an_invalid_kind(client, fake_db, kind):
    _seed_firm(fake_db, "acme", kind="live")
    resp = client.patch("/admin/firms/acme/kind",
                        json={"kind": kind, "reason": "staging test firm"})
    assert resp.status_code == 422
    assert fake_db.firm("acme")["kind"] == "live"


def test_set_kind_writes_the_value_and_one_audit_row_carrying_the_reason(
        client, fake_db):
    _seed_firm(fake_db, "acme", kind="live")
    resp = client.patch("/admin/firms/acme/kind",
                        json={"kind": "mock", "reason": "sandbox for QA"})
    assert resp.status_code == 200, resp.text
    assert fake_db.firm("acme")["kind"] == "mock"
    rows = fake_db.audit_rows()
    assert len(rows) == 1
    assert rows[0]["after"] == {"kind": "mock", "reason": "sandbox for QA"}
    assert rows[0]["before"]["kind"] == "live"


def test_set_kind_404s_for_an_unknown_firm(client, fake_db):
    resp = client.patch("/admin/firms/ghost/kind",
                        json={"kind": "mock", "reason": "x"})
    assert resp.status_code == 404


def test_a_forced_audit_failure_leaves_kind_unchanged(client, fake_db):
    _seed_firm(fake_db, "acme", kind="live")
    fake_db.audit_write_error = RuntimeError("audit sink refused")
    resp = client.patch("/admin/firms/acme/kind",
                        json={"kind": "mock", "reason": "sandbox for QA"})
    assert resp.status_code == 500
    assert fake_db.firm("acme")["kind"] == "live"
    assert fake_db.audit_rows() == []


# --------------------------------------------------------------------------
# require_app_admin gate (proven end to end here; the SET pin lives in
# test_admin_route_auth.py).
# --------------------------------------------------------------------------

def test_every_firm_route_is_reachable_only_through_require_app_admin():
    """A structural cross-check specific to this module's routes, over and
    above test_admin_route_auth.py's whole-app set pin -- this asserts it
    is EXACTLY require_app_admin (not the composite gate) for the firm
    routes specifically, mirroring test_config_routes.py's equivalent."""
    from admin_backend.main import app as live_app

    firm_paths = {
        "/admin/firms", "/admin/firms/{firm_id}",
        "/admin/firms/{firm_id}/status",
        "/admin/firms/{firm_id}/allowed_kits",
        "/admin/firms/{firm_id}/kind",
    }
    seen = set()
    for route in live_app.routes:
        if getattr(route, "path", None) not in firm_paths:
            continue
        seen.add(route.path)
        dependant = route.dependant
        names = {sub.call.__name__ for sub in dependant.dependencies
                 if getattr(sub.call, "__name__", None)}
        assert names == {"require_app_admin"}, (
            "{} carries {} instead of exactly require_app_admin".format(
                route.path, names))
    assert seen == firm_paths
