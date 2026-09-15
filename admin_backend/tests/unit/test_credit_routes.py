"""Credit grant/adjust routes (bd polyglot-pdf-zopqq, Epic 2 Track B bead B1).

EXIT CRITERION 1 lives here, over credit_ledger.append_entry rather than
config_routes.py's runtime-config writer: a grant or adjust writes EXACTLY
ONE ledger entry and EXACTLY ONE committed audit row in the SAME
transaction, and a forced audit failure leaves the balance unchanged.

THE FAKE FIRESTORE below is test_credit_ledger.py's own fake (subcollection-
capable, buffered-transaction), copied rather than imported: it is a test
double that belongs to the module under test's OWN test file by convention
in this repo (test_config_routes.py and test_firm_routes.py each keep their
own copy too), and importing test helpers across test modules is exactly
the kind of coupling that makes one test file's refactor break another's.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import credit_routes
from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import credit_ledger


# --------------------------------------------------------------------------
# The fake Firestore (mirrors backend/tests/unit/test_credit_ledger.py's).
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
        if self._store.audit_write_error is not None and (
                ref._path[-2] == audit_log.COLLECTION):
            raise self._store.audit_write_error
        self._buffer.append((ref._path, dict(data), merge))

    def commit(self):
        for path, data, merge in self._buffer:
            self._store.apply_set(path, data, merge)
        self._buffer = []


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
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
# EXIT CRITERION 1: exactly one ledger entry + one audit row, atomically.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("entry_type,usd_amount", [
    ("subscription_grant", 99.0),
    ("purchase", 249.0),
    ("promo_grant", None),
])
def test_grant_writes_exactly_one_ledger_entry_and_one_audit_row(
        client, fake_db, entry_type, usd_amount):
    resp = client.post("/admin/firms/acme/credits/grant", json={
        "type": entry_type, "amount": 50, "usd_amount": usd_amount,
    })
    assert resp.status_code == 200, resp.text

    rows = fake_db.ledger_rows("acme")
    assert len(rows) == 1
    assert rows[0]["type"] == entry_type
    assert rows[0]["amount"] == 50
    assert rows[0]["actor"] == "admin-uid-1"
    # bd polyglot-pdf-cpsi0: the operator's verified-token email rides on
    # the ledger entry alongside the uid.
    assert rows[0]["actor_email"] == "ops@example.com"
    assert fake_db.firm("acme")["balance_credits"] == 150

    audit_rows = fake_db.audit_rows()
    assert len(audit_rows) == 1
    assert audit_rows[0]["action"] == credit_routes.ACTION_CREDITS_GRANT
    assert audit_rows[0]["actor_uid"] == "admin-uid-1"
    assert audit_rows[0]["state"] == audit_log.STATE_COMMITTED
    assert audit_log.ROW_FIELDS <= set(audit_rows[0])
    assert resp.json()["balance_credits"] == 150
    assert resp.json()["request_id"] == audit_rows[0]["request_id"]


def test_adjust_writes_exactly_one_ledger_entry_and_one_audit_row(
        client, fake_db):
    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": -30, "reason": "double-charged on 09-07",
    })
    assert resp.status_code == 200, resp.text

    rows = fake_db.ledger_rows("acme")
    assert len(rows) == 1
    assert rows[0]["type"] == "adjustment"
    assert rows[0]["amount"] == -30
    assert rows[0]["reason"] == "double-charged on 09-07"
    # bd polyglot-pdf-cpsi0: same as grant -- the operator's email rides
    # alongside the uid on the adjustment entry too.
    assert rows[0]["actor_email"] == "ops@example.com"
    assert fake_db.firm("acme")["balance_credits"] == 70

    audit_rows = fake_db.audit_rows()
    assert len(audit_rows) == 1
    assert audit_rows[0]["action"] == credit_routes.ACTION_CREDITS_ADJUST


def test_a_forced_audit_failure_leaves_the_grant_balance_unchanged(
        client, fake_db):
    """THE CRITICAL HALF of exit criterion 1. Mutation: move
    record_in_transaction's call out of the extra_writes hook (or drop
    extra_writes entirely) in credit_routes._run_append_entry -- this goes
    red because the balance would then show 150 despite the forced
    failure."""
    fake_db.audit_write_error = RuntimeError("audit sink refused the write")
    resp = client.post("/admin/firms/acme/credits/grant", json={
        "type": "promo_grant", "amount": 50,
    })
    assert resp.status_code == 500
    assert fake_db.firm("acme")["balance_credits"] == 100
    assert fake_db.ledger_rows("acme") == []
    assert fake_db.audit_rows() == []


def test_a_forced_audit_failure_leaves_the_adjust_balance_unchanged(
        client, fake_db):
    fake_db.audit_write_error = RuntimeError("audit sink refused the write")
    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": 25, "reason": "goodwill credit",
    })
    assert resp.status_code == 500
    assert fake_db.firm("acme")["balance_credits"] == 100
    assert fake_db.ledger_rows("acme") == []
    assert fake_db.audit_rows() == []


# --------------------------------------------------------------------------
# EXIT CRITERION 2 (its credits half): promo_grant + usd_amount is 422.
# --------------------------------------------------------------------------

def test_promo_grant_with_usd_amount_is_refused_422(client, fake_db):
    """EXIT CRITERION 2. Mutation: drop the elif branch in grant_credits
    that refuses a usd_amount outside _USD_REQUIRED_GRANT_TYPES -- this
    goes red because the request would then reach append_entry, which
    itself refuses it as a LedgerError -> 422, so ALSO check no write
    happened (a mutation that instead widened the accepted types would
    still 422 by luck but would write)."""
    resp = client.post("/admin/firms/acme/credits/grant", json={
        "type": "promo_grant", "amount": 50, "usd_amount": 10.0,
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.firm("acme")["balance_credits"] == 100
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize("entry_type", ["subscription_grant", "purchase"])
def test_paid_grant_types_require_usd_amount(client, fake_db, entry_type):
    resp = client.post("/admin/firms/acme/credits/grant", json={
        "type": entry_type, "amount": 50,
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.ledger_rows("acme") == []


def test_grant_refuses_an_unknown_type(client, fake_db):
    resp = client.post("/admin/firms/acme/credits/grant", json={
        "type": "adjustment", "amount": 50,
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.ledger_rows("acme") == [], (
        "the adjustment type must not be reachable through the grant route")


@pytest.mark.parametrize("amount", [0, -5])
def test_grant_refuses_a_non_positive_amount(client, fake_db, amount):
    resp = client.post("/admin/firms/acme/credits/grant", json={
        "type": "promo_grant", "amount": amount,
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.ledger_rows("acme") == []


def test_adjust_requires_a_reason(client, fake_db):
    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": 10, "reason": "",
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.ledger_rows("acme") == []


def test_adjust_refuses_a_zero_amount(client, fake_db):
    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": 0, "reason": "no-op",
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.ledger_rows("acme") == []


def test_adjust_allows_a_negative_amount(client, fake_db):
    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": -10, "reason": "correction",
    })
    assert resp.status_code == 200, resp.text
    assert fake_db.firm("acme")["balance_credits"] == 90


# --------------------------------------------------------------------------
# Grants to mock firms are allowed (plan: "Grants to mock firms are
# allowed").
# --------------------------------------------------------------------------

def test_grant_to_a_mock_firm_succeeds_and_snapshots_mock_firm_kind(
        client, fake_db):
    fake_db.docs[("firms", "mockco")] = {
        "name": "MockCo", "status": "active", "kind": "mock",
        "balance_credits": 0,
    }
    resp = client.post("/admin/firms/mockco/credits/grant", json={
        "type": "promo_grant", "amount": 100,
    })
    assert resp.status_code == 200, resp.text
    rows = fake_db.ledger_rows("mockco")
    assert rows[0]["firm_kind"] == "mock"


def test_adjust_on_a_mock_firm_succeeds(client, fake_db):
    fake_db.docs[("firms", "mockco")] = {
        "name": "MockCo", "status": "active", "kind": "mock",
        "balance_credits": 50,
    }
    resp = client.post("/admin/firms/mockco/credits/adjust", json={
        "amount": -10, "reason": "test cleanup",
    })
    assert resp.status_code == 200, resp.text
    assert fake_db.firm("mockco")["balance_credits"] == 40


# --------------------------------------------------------------------------
# Ledger entries carry actor = the admin's uid, channel = None.
# --------------------------------------------------------------------------

def test_the_ledger_entry_actor_is_the_admins_uid_not_the_firm(
        client, fake_db):
    resp = client.post("/admin/firms/acme/credits/grant", json={
        "type": "promo_grant", "amount": 20,
    })
    assert resp.status_code == 200, resp.text
    assert fake_db.ledger_rows("acme")[0]["actor"] == "admin-uid-1"


def test_the_ledger_entry_channel_is_always_none(client, fake_db):
    resp = client.post("/admin/firms/acme/credits/grant", json={
        "type": "promo_grant", "amount": 20,
    })
    assert resp.status_code == 200, resp.text
    assert fake_db.ledger_rows("acme")[0]["channel"] is None


# --------------------------------------------------------------------------
# Unknown firm.
# --------------------------------------------------------------------------

def test_grant_against_an_unknown_firm_is_refused(client, fake_db):
    resp = client.post("/admin/firms/ghost/credits/grant", json={
        "type": "promo_grant", "amount": 20,
    })
    assert resp.status_code == 404, resp.text


def test_adjust_against_an_unknown_firm_is_refused(client, fake_db):
    resp = client.post("/admin/firms/ghost/credits/adjust", json={
        "amount": 20, "reason": "x",
    })
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------
# InsufficientCredits -> 402 (require_sufficient_balance is NOT passed here
# by default -- these routes never enforce it -- but the translation must
# still exist for when a future caller does).
# --------------------------------------------------------------------------

def test_insufficient_credits_translates_to_402(client, fake_db, monkeypatch):
    def _raise_insufficient(db, firm_id, **kwargs):
        raise credit_ledger.InsufficientCredits(firm_id, balance=5, amount=-50)

    monkeypatch.setattr(credit_ledger, "append_entry", _raise_insufficient)
    resp = client.post("/admin/firms/acme/credits/adjust", json={
        "amount": -50, "reason": "large debit",
    })
    assert resp.status_code == 402, resp.text


# --------------------------------------------------------------------------
# require_app_admin gate, over and above test_admin_route_auth.py's set pin.
# --------------------------------------------------------------------------

def test_every_credit_route_is_reachable_only_through_require_app_admin():
    from admin_backend.main import app as live_app

    credit_paths = {
        "/admin/firms/{firm_id}/credits/grant",
        "/admin/firms/{firm_id}/credits/adjust",
    }
    seen = set()
    for route in live_app.routes:
        if getattr(route, "path", None) not in credit_paths:
            continue
        seen.add(route.path)
        dependant = route.dependant
        names = {sub.call.__name__ for sub in dependant.dependencies
                 if getattr(sub.call, "__name__", None)}
        assert names == {"require_app_admin"}, (
            "{} carries {} instead of exactly require_app_admin".format(
                route.path, names))
    assert seen == credit_paths
