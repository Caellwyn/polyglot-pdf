"""GET /admin/alerts, GET /admin/firms/{firm_id}/alerts, PATCH
/admin/alerts/{id}/acknowledge (bd polyglot-pdf-mpebj E3.11a; bd
polyglot-pdf-62o4d widens the firm-scoped half).

Pins: the OPERATOR-WIDE route's list filters/ordering/allowlist/acknowledge
atomicity (unchanged from E3.11a); the NEW firm-scoped list route's
404-not-403 firm scoping for a manager/employee and its narrower response
allowlist; and acknowledge's widened gate -- a manager may acknowledge only
their own firm's alert (404 for another firm's), an employee is refused
with 403 even though the same dependency lets them THROUGH to read, and an
app admin may acknowledge any firm's alert (or a firm-less one).

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
from admin_backend.services.admin_auth import (
    ACTOR_KIND_APP_ADMIN,
    ACTOR_KIND_FIRM_EMPLOYEE,
    ACTOR_KIND_FIRM_MANAGER,
    AdminActor,
    CompositeActor,
    require_app_admin,
    require_app_admin_or_owning_manager_or_employee,
)
from backend.services import alerts


# --------------------------------------------------------------------------
# A minimal Firestore stand-in with REAL transaction semantics (mirrors
# test_kit_routes.py / test_config_routes.py / the pre-widening version of
# this file).
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
# Actors -- mirrors test_admin_link_routes.py's own actor constants exactly.
# --------------------------------------------------------------------------

ADMIN_ACTOR = CompositeActor(uid="admin-1", email="ops@example.com",
                             kind=ACTOR_KIND_APP_ADMIN)
MANAGER_ACTOR = CompositeActor(uid="mgr-1", email="ada@acme.example",
                               kind=ACTOR_KIND_FIRM_MANAGER, firm_id="acme")
OTHER_MANAGER_ACTOR = CompositeActor(
    uid="mgr-2", email="bo@other.example",
    kind=ACTOR_KIND_FIRM_MANAGER, firm_id="other-firm")
EMPLOYEE_ACTOR = CompositeActor(
    uid="emp-1", email="al@acme.example",
    kind=ACTOR_KIND_FIRM_EMPLOYEE, firm_id="acme", employee_id="emp-1")
OTHER_FIRM_EMPLOYEE_ACTOR = CompositeActor(
    uid="emp-2", email="cy@other.example",
    kind=ACTOR_KIND_FIRM_EMPLOYEE, firm_id="other-firm", employee_id="emp-2")


@pytest.fixture
def admin_actor_client():
    """The OPERATOR-WIDE route's own fixture (require_app_admin), unchanged
    from the pre-widening version of this file."""
    actor = AdminActor(uid="admin-1", email="ops@example.com")
    app.dependency_overrides[require_app_admin] = lambda: actor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# Alias kept for the pre-existing operator-wide tests below, which were
# written against the name `client` -- renamed only where a NEW fixture
# needed a distinct name.
client = admin_actor_client


def _composite_client(actor):
    app.dependency_overrides[
        require_app_admin_or_owning_manager_or_employee] = lambda: actor
    return TestClient(app)


@pytest.fixture
def admin_client():
    with _composite_client(ADMIN_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def manager_client():
    with _composite_client(MANAGER_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def other_manager_client():
    with _composite_client(OTHER_MANAGER_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def employee_client():
    with _composite_client(EMPLOYEE_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def other_firm_employee_client():
    with _composite_client(OTHER_FIRM_EMPLOYEE_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Operator-wide list (GET /admin/alerts) -- unchanged from E3.11a.
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
# Firm-scoped list (GET /admin/firms/{firm_id}/alerts) -- bd
# polyglot-pdf-62o4d, exit criterion 1.
# --------------------------------------------------------------------------

def test_manager_reads_own_firm_alerts_narrow_allowlist(
        manager_client, fake_db):
    _seed_alert(fake_db, "a1", firm_id="acme", ts=1000.0,
               context={"balance": 3, "threshold": 10})
    resp = manager_client.get("/admin/firms/acme/alerts?channel=demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["firm_id"] == "acme"
    rows = body["alerts"]
    assert [r["id"] for r in rows] == ["a1"]
    row = rows[0]
    assert set(row) == {"id", "kind", "level", "ts", "context",
                        "acknowledged_at"}
    # Never firm_id, acknowledged_by, or emailed_at (module docstring's
    # "THE FIRM-SCOPED RESPONSE" section).
    assert "firm_id" not in row
    assert "acknowledged_by" not in row
    assert "emailed_at" not in row
    assert row["context"] == {"balance": 3, "threshold": 10}


def test_employee_reads_own_firm_alerts(employee_client, fake_db):
    _seed_alert(fake_db, "a1", firm_id="acme")
    resp = employee_client.get("/admin/firms/acme/alerts")
    assert resp.status_code == 200, resp.text
    assert [r["id"] for r in resp.json()["alerts"]] == ["a1"]


def test_manager_reading_another_firm_is_404_not_403(
        manager_client, fake_db):
    """Mutation: change _require_owning_firm's raise to status_code=403 --
    a manager naming a firm that is not theirs must see the SAME response
    an UNKNOWN firm_id would produce, never a 403 that confirms the firm
    exists -- red."""
    _seed_alert(fake_db, "a1", firm_id="other-firm")
    resp = manager_client.get("/admin/firms/other-firm/alerts")
    assert resp.status_code == 404, resp.text


def test_employee_reading_another_firm_is_404_not_403(
        other_firm_employee_client, fake_db):
    _seed_alert(fake_db, "a1", firm_id="acme")
    resp = other_firm_employee_client.get("/admin/firms/acme/alerts")
    assert resp.status_code == 404, resp.text


def test_app_admin_reads_any_firm_alerts(admin_client, fake_db):
    _seed_alert(fake_db, "a1", firm_id="acme")
    _seed_alert(fake_db, "a2", firm_id="other-firm")
    resp = admin_client.get("/admin/firms/other-firm/alerts")
    assert resp.status_code == 200, resp.text
    assert [r["id"] for r in resp.json()["alerts"]] == ["a2"]


def test_firm_alerts_filters_by_acknowledged(manager_client, fake_db):
    _seed_alert(fake_db, "unack", firm_id="acme", acknowledged_by=None)
    _seed_alert(fake_db, "ack", firm_id="acme", acknowledged_by="mgr-1",
               acknowledged_at=500.0)
    resp = manager_client.get(
        "/admin/firms/acme/alerts?acknowledged=false")
    assert [r["id"] for r in resp.json()["alerts"]] == ["unack"]


def test_firm_alerts_never_returns_another_firms_row(
        manager_client, fake_db):
    _seed_alert(fake_db, "mine", firm_id="acme")
    _seed_alert(fake_db, "theirs", firm_id="other-firm")
    resp = manager_client.get("/admin/firms/acme/alerts")
    assert [r["id"] for r in resp.json()["alerts"]] == ["mine"]


# --------------------------------------------------------------------------
# Acknowledge -- widened gate (bd polyglot-pdf-62o4d, exit criterion 1).
# --------------------------------------------------------------------------

def test_manager_acknowledges_own_firm_alert_and_it_is_audited(
        manager_client, fake_db):
    _seed_alert(fake_db, "a1", firm_id="acme")
    resp = manager_client.patch("/admin/alerts/a1/acknowledge")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["acknowledged_by"] == "mgr-1"

    stored = fake_db.alert("a1")
    assert stored["acknowledged_by"] == "mgr-1"

    rows = fake_db.audit_rows()
    assert len(rows) == 1
    assert rows[0]["action"] == "alert.acknowledge"
    assert rows[0]["actor_uid"] == "mgr-1"


def test_manager_acknowledging_another_firms_alert_is_404(
        manager_client, fake_db):
    """Mutation: drop the _require_owning_firm call inside the
    transaction -- a manager could then acknowledge (and silently claim
    responsibility for) an alert belonging to a firm that is not theirs --
    red."""
    _seed_alert(fake_db, "a1", firm_id="other-firm")
    resp = manager_client.patch("/admin/alerts/a1/acknowledge")
    assert resp.status_code == 404, resp.text
    assert fake_db.alert("a1")["acknowledged_by"] is None
    assert fake_db.audit_rows() == []


def test_employee_acknowledge_is_403(employee_client, fake_db):
    """Mutation: delete the `if actor.kind == ACTOR_KIND_FIRM_EMPLOYEE`
    early refusal in acknowledge_alert -- an employee (who the shared
    dependency lets THROUGH, unlike the read-only composite gate elsewhere)
    would then be able to acknowledge their own firm's alert -- red."""
    _seed_alert(fake_db, "a1", firm_id="acme")
    resp = employee_client.patch("/admin/alerts/a1/acknowledge")
    assert resp.status_code == 403, resp.text
    assert "NO_ADMIN_ACCESS:" in resp.json()["detail"]
    assert fake_db.alert("a1")["acknowledged_by"] is None
    assert fake_db.audit_rows() == []


def test_employee_of_a_different_firm_acknowledge_is_still_403(
        other_firm_employee_client, fake_db):
    """An employee is refused on the actor-kind check BEFORE any firm
    ownership check even runs -- confirms the 403 fires regardless of
    which firm the alert or the employee belongs to."""
    _seed_alert(fake_db, "a1", firm_id="acme")
    resp = other_firm_employee_client.patch(
        "/admin/alerts/a1/acknowledge")
    assert resp.status_code == 403, resp.text


def test_app_admin_acknowledges_any_firms_alert(admin_client, fake_db):
    _seed_alert(fake_db, "a1", firm_id="other-firm")
    resp = admin_client.patch("/admin/alerts/a1/acknowledge")
    assert resp.status_code == 200, resp.text
    assert fake_db.alert("a1")["acknowledged_by"] == "admin-1"


def test_app_admin_acknowledges_a_firm_less_alert(admin_client, fake_db):
    """A KIND_LINK_EXHAUSTED alert may carry firm_id=None
    (backend/services/alerts.py's own _write). A manager can never own
    None, so only an app admin may acknowledge it."""
    _seed_alert(fake_db, "a1", firm_id=None,
               kind=alerts.KIND_LINK_EXHAUSTED)
    resp = admin_client.patch("/admin/alerts/a1/acknowledge")
    assert resp.status_code == 200, resp.text


def test_manager_cannot_acknowledge_a_firm_less_alert(
        manager_client, fake_db):
    _seed_alert(fake_db, "a1", firm_id=None)
    resp = manager_client.patch("/admin/alerts/a1/acknowledge")
    assert resp.status_code == 404, resp.text


def test_acknowledging_twice_is_409(manager_client, fake_db):
    """Mutation: drop the `if doc.get("acknowledged_by"): raise 409` guard
    -- a second acknowledge would silently overwrite the first
    acknowledger's identity -- red."""
    _seed_alert(fake_db, "a1", firm_id="acme")
    first = manager_client.patch("/admin/alerts/a1/acknowledge")
    assert first.status_code == 200, first.text

    second = manager_client.patch("/admin/alerts/a1/acknowledge")
    assert second.status_code == 409, second.text

    assert fake_db.alert("a1")["acknowledged_by"] == "mgr-1"
    assert len(fake_db.audit_rows()) == 1, (
        "a refused second acknowledge must not write a second audit row")


def test_acknowledge_unknown_alert_is_404(manager_client, fake_db):
    resp = manager_client.patch("/admin/alerts/ghost/acknowledge")
    assert resp.status_code == 404


def test_a_forced_audit_failure_leaves_acknowledged_at_unset(
        manager_client, fake_db):
    """THE ATOMICITY PIN (exit criterion 1): the write and its audit row
    share ONE Firestore transaction, so a forced audit failure must leave
    the alert doc's acknowledged_by/acknowledged_at UNCHANGED.

    Mutation: move the audit_log.record_in_transaction call in
    _do_acknowledge_alert OUTSIDE the @firestore.transactional body (e.g.
    call it after _txn(db.transaction()) returns) -- the acknowledge would
    then commit even though this fixture's forced audit failure fires, and
    the assertions below would go red."""
    _seed_alert(fake_db, "a1", firm_id="acme")
    fake_db.audit_write_error = RuntimeError("audit sink unavailable")

    resp = manager_client.patch("/admin/alerts/a1/acknowledge")
    assert resp.status_code == 500, resp.text

    stored = fake_db.alert("a1")
    assert stored["acknowledged_by"] is None, (
        "acknowledged_by must be unset when the joined audit write fails")
    assert stored["acknowledged_at"] is None, (
        "acknowledged_at must be unset when the joined audit write fails")
    assert fake_db.audit_rows() == []
