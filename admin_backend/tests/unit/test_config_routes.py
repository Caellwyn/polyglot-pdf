"""GET/PUT /admin/config/{channel}, and the in-transaction audit form it is
the first consumer of (bd polyglot-pdf-li9x0).

EXIT CRITERION 1 lives here: writing app_config/staging through the route
produces EXACTLY ONE committed audit row carrying actor, action, target,
before/after and ts; and a FORCED AUDIT FAILURE leaves the config unchanged.

THE FAKE FIRESTORE below is the interesting part. It is not a mock that
records calls -- a call-recording mock cannot answer "did the config survive
the audit failure?", which is the whole question. It is a tiny STORE with a
real all-or-nothing transaction: writes buffer on the transaction and are
applied to the store only at commit, so an exception raised inside the
transaction body discards the buffered config write exactly as Firestore
would. Without that, a test asserting "config unchanged" would pass against
a helper that never wrote anything at all.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import config_routes
from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import runtime_config


# --------------------------------------------------------------------------
# A minimal Firestore stand-in with REAL transaction semantics.
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

    def set(self, data, merge=False):
        self._store.apply_set(self._path, data, merge)

    def update(self, data):
        existing = self._store.docs.setdefault(self._path, {})
        existing.update(data)


class _Collection:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.auto_id_counter += 1
            doc_id = "auto{}".format(self._store.auto_id_counter)
        return _DocRef(self._store, self._name, doc_id)


class _Transaction:
    """Buffers writes; the buffer is applied only on a clean commit.

    THIS is what makes "a forced audit failure leaves the config unchanged" a
    real assertion rather than a tautology: the config tx.set lands in
    _buffer, the audit write raises before commit, and nothing is applied.
    """

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

    # Test helpers -------------------------------------------------------
    def config_doc(self, channel):
        return self.docs.get((runtime_config.COLLECTION, channel))

    def audit_rows(self):
        return [v for (coll, _), v in self.docs.items()
                if coll == audit_log.COLLECTION]


class _FakeTransactionalDecorator:
    """Stands in for firebase_admin.firestore.transactional.

    The real decorator wraps the body so it runs, then commits (retrying on
    contention). This does the same minus the retry: run the body, then
    commit. An exception from the body propagates with NOTHING committed,
    which is the property under test.
    """

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
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    return db


@pytest.fixture
def client():
    """A TestClient whose caller is a known admin.

    Overriding the DEPENDENCY rather than faking a Firebase token: the gate
    itself is pinned by test_admin_auth.py / test_admin_route_auth.py, and
    re-proving it here would couple these tests to token plumbing they are
    not about.
    """
    actor = AdminActor(uid="admin-uid-1", email="ops@example.com")
    app.dependency_overrides[require_app_admin] = lambda: actor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Exit criterion 1: one committed row, and an audit failure blocks the write.
# --------------------------------------------------------------------------

def test_put_writes_the_value_and_exactly_one_committed_audit_row(
        client, fake_db):
    """EXIT CRITERION 1, the happy half. Mutation: drop the
    record_in_transaction call from _apply_config_write -- the audit-row
    assertions go red while the config write still succeeds, which is
    exactly the regression this pins."""
    resp = client.put(
        "/admin/config/staging",
        json={"key": "LINK_COST_CEILING_USD", "value": 4.5},
    )
    assert resp.status_code == 200, resp.text

    assert fake_db.config_doc("staging") == {"LINK_COST_CEILING_USD": 4.5}

    rows = fake_db.audit_rows()
    assert len(rows) == 1, "expected exactly one audit row, got {}".format(rows)
    row = rows[0]
    assert row["actor_uid"] == "admin-uid-1"
    assert row["actor_email"] == "ops@example.com"
    assert row["action"] == config_routes.ACTION_CONFIG_SET
    assert row["target"] == "app_config/staging#LINK_COST_CEILING_USD"
    assert row["before"] == {"LINK_COST_CEILING_USD": None}
    assert row["after"] == {"LINK_COST_CEILING_USD": 4.5}
    assert row["channel"] == "staging"
    assert row["state"] == audit_log.STATE_COMMITTED
    assert isinstance(row["ts"], float) and row["ts"] > 0
    assert row["request_id"] == resp.json()["request_id"]
    # Every documented field is present -- a writer that quietly drops one
    # makes an audit query mean two different things for two eras of rows.
    assert audit_log.ROW_FIELDS <= set(row)


def test_a_forced_audit_failure_leaves_the_config_unchanged(client, fake_db):
    """EXIT CRITERION 1, the half that matters. The audit row and the config
    write share one transaction, so an audit failure must abort BOTH.

    Mutation: move audit_log.record_in_transaction out of the @transactional
    body (or wrap it in try/except) -- the config doc then shows the new
    value and this goes red."""
    fake_db.docs[(runtime_config.COLLECTION, "staging")] = {
        "LINK_COST_CEILING_USD": 9.0}
    fake_db.audit_write_error = RuntimeError("audit sink refused the write")

    resp = client.put(
        "/admin/config/staging",
        json={"key": "LINK_COST_CEILING_USD", "value": 4.5},
    )
    assert resp.status_code == 500

    assert fake_db.config_doc("staging") == {"LINK_COST_CEILING_USD": 9.0}, (
        "the config write survived an audit failure -- the two are not in "
        "the same transaction")
    assert fake_db.audit_rows() == []


def test_the_audit_row_records_the_previous_value_as_before(client, fake_db):
    """before must be the value that was actually there, not None or the new
    one -- a row whose before equals its after answers no question."""
    fake_db.docs[(runtime_config.COLLECTION, "demo")] = {
        "LINK_FIRM_CAP": 30, "LINK_MINTING_ENABLED": True}

    resp = client.put("/admin/config/demo",
                      json={"key": "LINK_FIRM_CAP", "value": 5})
    assert resp.status_code == 200, resp.text

    row = fake_db.audit_rows()[0]
    assert row["before"] == {"LINK_FIRM_CAP": 30}
    assert row["after"] == {"LINK_FIRM_CAP": 5}
    assert resp.json()["before"] == 30


def test_the_write_merges_and_does_not_drop_the_channels_other_keys(
        client, fake_db):
    """merge=True. Mutation: drop merge=True from the tx.set -- red, because
    LINK_MINTING_ENABLED disappears."""
    fake_db.docs[(runtime_config.COLLECTION, "demo")] = {
        "LINK_MINTING_ENABLED": True, "LINK_FIRM_CAP": 30}

    resp = client.put("/admin/config/demo",
                      json={"key": "LINK_FIRM_CAP", "value": 5})
    assert resp.status_code == 200, resp.text
    assert fake_db.config_doc("demo") == {
        "LINK_MINTING_ENABLED": True, "LINK_FIRM_CAP": 5}


# --------------------------------------------------------------------------
# Refusals, all BEFORE any write.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("channel", ["prod", "production", "Staging", ""])
def test_an_unknown_channel_is_refused_with_no_write(client, fake_db, channel):
    """A typo must not create an orphan config doc that looks configured and
    is read by nothing. Parametrized over the real shapes: the dead prod
    project, a plausible alias, a case variant, and empty."""
    resp = client.put("/admin/config/{}".format(channel),
                      json={"key": "LINK_FIRM_CAP", "value": 5})
    assert resp.status_code in (404, 405), resp.text
    assert fake_db.docs == {}


def test_an_unknown_key_is_refused_with_no_write(client, fake_db):
    """runtime_config ignores unknown keys on READ; a write-time refusal is
    stricter and correctly so -- a typo'd key nothing reads should fail
    loudly, not sit in the doc forever looking configured."""
    resp = client.put("/admin/config/staging",
                      json={"key": "LINK_TOKEN_SECRET", "value": "hunter2"})
    assert resp.status_code == 400
    assert "runtime config key" in resp.json()["detail"]
    assert fake_db.docs == {}


@pytest.mark.parametrize("key,value", [
    ("LINK_COST_CEILING_USD", "not-a-number"),
    ("LINK_COST_CEILING_USD", 0),
    ("LINK_COST_CEILING_USD", -1),
    ("LINK_FIRM_CAP", True),
    ("LINK_FIRM_CAP", 0),
    ("LINK_MINTING_ENABLED", "maybe"),
    ("CREDITS_ENFORCED", 7),
])
def test_a_value_the_reader_would_reject_is_refused_with_no_write(
        client, fake_db, key, value):
    """THE IMPORTANT REFUSAL. A value runtime_config's own coercion rejects
    would be stored happily and then IGNORED on every read -- the console
    would show success while the backend kept the old value. Refusing at the
    write is what makes the console's confirmation mean something.

    Parametrized over each type's failure shapes, including LINK_FIRM_CAP's
    bool trap (bool is an int subclass, so True would otherwise store as a
    cap of 1)."""
    resp = client.put("/admin/config/staging",
                      json={"key": key, "value": value})
    assert resp.status_code == 400, resp.text
    assert fake_db.docs == {}


def test_the_route_and_runtime_config_agree_on_what_is_valid():
    """The route delegates to runtime_config.coerce_value rather than
    restating the rules (CLAUDE.md scar #8). Pinned so a future edit that
    inlines a second copy of the validation is caught: every key the route
    accepts must be a key the reader knows, and vice versa."""
    import inspect
    source = inspect.getsource(config_routes)
    assert "runtime_config.RUNTIME_CONFIG_KEYS" in source, (
        "the route must validate keys against runtime_config's own set")
    assert "runtime_config.coerce_value" in source, (
        "the route must validate values with the coercion a READ applies")


# --------------------------------------------------------------------------
# The read half.
# --------------------------------------------------------------------------

def test_get_returns_the_raw_stored_values_and_flags_unknown_keys(
        client, fake_db):
    """The console's diagnostic view shows what is ACTUALLY in the doc,
    malformed values included -- hiding them behind the coercion would make
    a broken setting invisible on the one screen meant to diagnose it."""
    fake_db.docs[(runtime_config.COLLECTION, "staging")] = {
        "LINK_FIRM_CAP": 30,
        "LINK_COST_CEILING_USD": "broken",
        "TYPOD_KEY": 1,
    }
    resp = client.get("/admin/config/staging")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["channel"] == "staging"
    assert body["values"]["LINK_COST_CEILING_USD"] == "broken"
    assert body["unknown_keys"] == ["TYPOD_KEY"]
    assert set(body["known_keys"]) == set(runtime_config.RUNTIME_CONFIG_KEYS)


def test_get_on_a_channel_with_no_doc_is_empty_not_an_error(client, fake_db):
    resp = client.get("/admin/config/demo")
    assert resp.status_code == 200
    assert resp.json()["values"] == {}


def test_a_read_writes_no_audit_row(client, fake_db):
    """The log records MUTATIONS. A row per read would bury them under the
    console's own polling."""
    fake_db.docs[(runtime_config.COLLECTION, "staging")] = {"LINK_FIRM_CAP": 30}
    client.get("/admin/config/staging")
    assert fake_db.audit_rows() == []


# --------------------------------------------------------------------------
# The gate.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,payload", [
    ("get", "/admin/config/staging", None),
    ("put", "/admin/config/staging", {"key": "LINK_FIRM_CAP", "value": 5}),
    ("get", "/admin/audit", None),
])
def test_a_tokenless_caller_is_refused(method, path, payload):
    """Cloud Run runs this service with --allow-unauthenticated, so the
    app-level gate IS the access control. With no dependency override, an
    unauthenticated request must 401 -- pinned per ROUTE, since a gate
    omitted on one of the three is invisible to a single-route check."""
    with TestClient(app) as c:
        resp = getattr(c, method)(path, **({"json": payload} if payload else {}))
    assert resp.status_code == 401, (path, resp.text)
