"""GET /admin/alerts, PATCH /admin/alerts/{id}/acknowledge (bd
polyglot-pdf-mpebj, E3.11a).

Pins: list filters (acknowledged/firm_id/kind), newest-first ordering, the
explicit key allowlist, and acknowledge's exit criterion 1 -- the write and
its audit row share ONE Firestore transaction (a forced audit failure
leaves acknowledged_at unset), plus the 409 on a repeat acknowledge and the
404 on an unknown id.

THE FAKE FIRESTORE mirrors test_sweep_routes.py's / test_kit_routes.py's
own shape: a real all-or-nothing transaction (writes buffer until commit),
because "does a forced audit failure leave the doc unchanged?" is the whole
question a call-recording mock cannot answer.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import alerts


# --------------------------------------------------------------------------
# A minimal Firestore stand-in with REAL transaction semantics (mirrors
# test_kit_routes.py / test_config_routes.py).
# --------------------------------------------------------------------------

class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store, collection, doc_id):
        self._store = store
        self.collection_id = collection
        self.id = doc_id

    @property
    def _path(self):
        return (self.collection_id, self.id)

    def get(self, transaction=None):
        if self._store.read_error is not None:
            raise self._store.read_error
        return _Snap(self._store.docs.get(self._path))


class _Collection:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.auto_id_counter += 1
            doc_id = "auto{}".format(self._store.auto_id_counter)
        return _DocRef(self._store, self._name, doc_id)

    def stream(self):
        for (coll, doc_id), data in self._store.docs.items():
            if coll == self._name:
                yield _StreamSnap(doc_id, data)


class _StreamSnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Transaction:
    """Buffers writes; the buffer is applied only on a clean commit."""

    def __init__(self, store):
        self._store = store
        self._buffer = []

    def get(self, ref):
        return ref.get(transaction=self)

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
        # {(collection, doc_id): {...}}
        self.docs = dict(docs or {})
        self.read_error = None
        self.audit_write_error = None
        self.auto_id_counter = 0

    def collection(self, name):
        return _Collection(self, name)

    def transaction(self):
        return _Transaction(self)

    def apply_set(self, path, data, merge):
        if merge and path in self.docs:
            self.docs[path].update(data)
        else:
            self.docs[path] = dict(data)

    # test helpers --------------------------------------------------
    def alert(self, alert_id):
        return self.docs.get((alerts.COLLECTION, alert_id))

    def audit_rows(self):
        return [v for (coll, _), v in self.docs.items()
                if coll == audit_log.COLLECTION]


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
    db = _FakeDb()
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


@pytest.fixture
def client():
    actor = AdminActor(uid="admin-1", email="ops@example.com")
    app.dependency_overrides[require_app_admin] = lambda: actor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_alert(fake_db, alert_id, **over):
    doc = {
        "firm_id": "acme", "kind": alerts.KIND_LINK_EXHAUSTED,
        "level": alerts.LEVEL_CRITICAL, "ts": 1000.0,
        "context": {"jti": "jti-1"}, "acknowledged_by": None,
        "acknowledged_at": None, "emailed_at": None, "expire_at": None,
    }
    doc.update(over)
    fake_db.docs[(alerts.COLLECTION, alert_id)] = doc
    return doc


# --------------------------------------------------------------------------
# List.
# --------------------------------------------------------------------------

def test_list_alerts_returns_the_allowlisted_fields_newest_first(
        client, fake_db):
    _seed_alert(fake_db, "a1", ts=1000.0)
    _seed_alert(fake_db, "a2", ts=2000.0)
    resp = client.get("/admin/alerts")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["alerts"]
    assert [r["id"] for r in rows] == ["a2", "a1"]
    assert set(alerts.ALERT_FIELDS) <= set(rows[0])


def test_list_alerts_filters_by_acknowledged(client, fake_db):
    _seed_alert(fake_db, "unack", acknowledged_by=None)
    _seed_alert(fake_db, "ack", acknowledged_by="admin-1",
               acknowledged_at=500.0)

    resp_false = client.get("/admin/alerts?acknowledged=false")
    assert [r["id"] for r in resp_false.json()["alerts"]] == ["unack"]

    resp_true = client.get("/admin/alerts?acknowledged=true")
    assert [r["id"] for r in resp_true.json()["alerts"]] == ["ack"]


def test_list_alerts_filters_by_firm_id_and_kind(client, fake_db):
    _seed_alert(fake_db, "a1", firm_id="acme", kind=alerts.KIND_CREDIT_LOW)
    _seed_alert(fake_db, "a2", firm_id="other",
               kind=alerts.KIND_LINK_EXHAUSTED)

    resp = client.get("/admin/alerts?firm_id=acme")
    assert [r["id"] for r in resp.json()["alerts"]] == ["a1"]

    resp = client.get("/admin/alerts?kind=link_exhausted")
    assert [r["id"] for r in resp.json()["alerts"]] == ["a2"]


def test_list_alerts_unknown_kind_is_422(client, fake_db):
    resp = client.get("/admin/alerts?kind=nonsense")
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# Acknowledge -- exit criterion 1.
# --------------------------------------------------------------------------

def test_acknowledge_sets_actor_uid_and_writes_one_audit_row(
        client, fake_db):
    _seed_alert(fake_db, "a1")
    resp = client.patch("/admin/alerts/a1/acknowledge")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["acknowledged_by"] == "admin-1"
    assert isinstance(body["acknowledged_at"], float)

    stored = fake_db.alert("a1")
    assert stored["acknowledged_by"] == "admin-1"
    assert stored["acknowledged_at"] == body["acknowledged_at"]

    rows = fake_db.audit_rows()
    assert len(rows) == 1
    assert rows[0]["action"] == "alert.acknowledge"
    assert rows[0]["actor_uid"] == "admin-1"


def test_acknowledging_twice_is_409(client, fake_db):
    """Mutation: drop the `if doc.get("acknowledged_by"): raise 409` guard
    -- a second acknowledge would silently overwrite the first
    acknowledger's identity -- red."""
    _seed_alert(fake_db, "a1")
    first = client.patch("/admin/alerts/a1/acknowledge")
    assert first.status_code == 200, first.text

    second = client.patch("/admin/alerts/a1/acknowledge")
    assert second.status_code == 409, second.text

    # The first acknowledger's identity must survive the refused second
    # attempt untouched.
    assert fake_db.alert("a1")["acknowledged_by"] == "admin-1"
    assert len(fake_db.audit_rows()) == 1, (
        "a refused second acknowledge must not write a second audit row")


def test_acknowledge_unknown_alert_is_404(client, fake_db):
    resp = client.patch("/admin/alerts/ghost/acknowledge")
    assert resp.status_code == 404


def test_a_forced_audit_failure_leaves_acknowledged_at_unset(
        client, fake_db):
    """THE ATOMICITY PIN (exit criterion 1): the write and its audit row
    share ONE Firestore transaction, so a forced audit failure must leave
    the alert doc's acknowledged_by/acknowledged_at UNCHANGED.

    Mutation: move the audit_log.record_in_transaction call in
    _do_acknowledge_alert OUTSIDE the @firestore.transactional body (e.g.
    call it after _txn(db.transaction()) returns) -- the acknowledge would
    then commit even though this fixture's forced audit failure fires, and
    the assertions below would go red."""
    _seed_alert(fake_db, "a1")
    fake_db.audit_write_error = RuntimeError("audit sink unavailable")

    resp = client.patch("/admin/alerts/a1/acknowledge")
    assert resp.status_code == 500, resp.text

    stored = fake_db.alert("a1")
    assert stored["acknowledged_by"] is None, (
        "acknowledged_by must be unset when the joined audit write fails")
    assert stored["acknowledged_at"] is None, (
        "acknowledged_at must be unset when the joined audit write fails")
    assert fake_db.audit_rows() == []
