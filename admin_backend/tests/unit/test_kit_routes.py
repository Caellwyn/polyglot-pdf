"""GET /admin/kits, GET/PUT /admin/kits/{kit_id}/commercial (bd
polyglot-pdf-f0kuu, Epic 2 Track B bead B3).

EXIT CRITERION 1 lives here: a PUT writes the doc and exactly one audit row
in the same transaction; a malformed body (zero, negative, NaN,
bool-as-number, string) is refused with 422 and writes NOTHING.

EXIT CRITERION 2 lives here too: GET for a kit with no commercial doc
returns the global defaults and says so via `source`, and the route calls
the SAME reader bead A3 shipped (backend/services/kit_commercials.py) --
pinned by an import-site assertion, not just by matching output, so a
future rewrite that inlines a second copy of the fallback logic is caught
even if it happens to compute the same numbers today.

THE FAKE FIRESTORE below is copied from test_config_routes.py's shape: a
real all-or-nothing transaction (writes buffer until commit), not a
call-recording mock, because "did the doc survive a forced audit failure?"
is the whole question a call-recording mock cannot answer.

ASCII only.
"""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import kit_routes
from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import kit_commercials


# --------------------------------------------------------------------------
# A minimal Firestore stand-in with REAL transaction semantics (mirrors
# test_config_routes.py / test_firm_routes.py).
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
    """Buffers writes; the buffer is applied only on a clean commit -- what
    makes "a forced audit failure leaves the commercial doc unchanged" a
    real assertion rather than a tautology."""

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
    def kit_doc(self, kit_id):
        return self.docs.get((kit_commercials.COLLECTION, kit_id))

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
    SERVER_TIMESTAMP = "SERVER_TIMESTAMP"


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    return db


class _FakeFormKitStore:
    """Stands in for backend.services.form_kits's FormKitStore -- only the
    one async method this route calls."""

    def __init__(self, kit_ids):
        self._kit_ids = list(kit_ids)

    async def list_kit_ids(self):
        return list(self._kit_ids)


@pytest.fixture
def client():
    """A TestClient whose caller is a known admin. Overriding the
    DEPENDENCY rather than faking a Firebase token: the gate itself is
    pinned by test_admin_auth.py / test_admin_route_auth.py."""
    actor = AdminActor(uid="admin-uid-1", email="ops@example.com")
    app.dependency_overrides[require_app_admin] = lambda: actor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Exit criterion 1: one committed row, and an audit failure blocks the write.
# --------------------------------------------------------------------------

def test_put_writes_the_doc_and_exactly_one_committed_audit_row(
        client, fake_db):
    """EXIT CRITERION 1, the happy half. Mutation: drop the
    record_in_transaction call from _apply_kit_commercial_write -- the
    audit-row assertions go red while the kit write still succeeds, which
    is exactly the regression this pins."""
    resp = client.put(
        "/admin/kits/w-7/commercial",
        json={"credit_cost": 2, "burn_cap_usd": 5.5,
              "display": {"label": "Form W-7"}},
    )
    assert resp.status_code == 200, resp.text

    doc = fake_db.kit_doc("w-7")
    assert doc["credit_cost"] == 2
    assert doc["burn_cap_usd"] == 5.5
    assert doc["display"] == {"label": "Form W-7"}
    assert doc["updated_by"] == "admin-uid-1"

    rows = fake_db.audit_rows()
    assert len(rows) == 1, "expected exactly one audit row, got {}".format(rows)
    row = rows[0]
    assert row["actor_uid"] == "admin-uid-1"
    assert row["actor_email"] == "ops@example.com"
    assert row["action"] == kit_routes.ACTION_KIT_COMMERCIAL_SET
    assert row["target"] == "kits/w-7"
    assert row["before"] is None
    assert row["after"] == {
        "credit_cost": 2, "burn_cap_usd": 5.5, "display": {"label": "Form W-7"},
    }
    assert row["state"] == audit_log.STATE_COMMITTED
    assert isinstance(row["ts"], float) and row["ts"] > 0
    assert row["request_id"] == resp.json()["request_id"]
    assert audit_log.ROW_FIELDS <= set(row)


def test_a_forced_audit_failure_leaves_the_kit_doc_unchanged(client, fake_db):
    """EXIT CRITERION 1, the half that matters. Mutation: move
    audit_log.record_in_transaction out of the @transactional body (or wrap
    it in try/except) -- the kit doc then shows the new value and this goes
    red."""
    fake_db.docs[(kit_commercials.COLLECTION, "w-7")] = {
        "credit_cost": 1, "burn_cap_usd": 10.0, "display": {},
    }
    fake_db.audit_write_error = RuntimeError("audit sink refused the write")

    resp = client.put(
        "/admin/kits/w-7/commercial",
        json={"credit_cost": 2, "burn_cap_usd": 5.5, "display": {}},
    )
    assert resp.status_code == 500

    assert fake_db.kit_doc("w-7") == {
        "credit_cost": 1, "burn_cap_usd": 10.0, "display": {},
    }, ("the kit write survived an audit failure -- the two are not in the "
        "same transaction")
    assert fake_db.audit_rows() == []


def test_the_audit_row_records_the_previous_doc_as_before(client, fake_db):
    fake_db.docs[(kit_commercials.COLLECTION, "i-90")] = {
        "credit_cost": 3, "burn_cap_usd": 8.0, "display": {"label": "old"},
    }
    resp = client.put(
        "/admin/kits/i-90/commercial",
        json={"credit_cost": 4, "burn_cap_usd": 9.0, "display": {}},
    )
    assert resp.status_code == 200, resp.text
    row = fake_db.audit_rows()[0]
    assert row["before"] == {
        "credit_cost": 3, "burn_cap_usd": 8.0, "display": {"label": "old"},
    }
    assert row["after"] == {"credit_cost": 4, "burn_cap_usd": 9.0, "display": {}}
    assert resp.json()["before"] == {
        "credit_cost": 3, "burn_cap_usd": 8.0, "display": {"label": "old"},
    }


def test_put_defaults_display_to_an_empty_map_when_omitted(client, fake_db):
    resp = client.put(
        "/admin/kits/w-7/commercial",
        json={"credit_cost": 1, "burn_cap_usd": 10.0},
    )
    assert resp.status_code == 200, resp.text
    assert fake_db.kit_doc("w-7")["display"] == {}


# --------------------------------------------------------------------------
# Exit criterion 1, other half: malformed bodies refuse BEFORE any write.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("credit_cost", [
    0, -1, -100, True, False, "2", None, 2.5,
])
def test_a_malformed_credit_cost_is_refused_with_no_write(
        client, fake_db, credit_cost):
    """THE IMPORTANT REFUSAL, credit_cost half. Parametrized over zero,
    negative, bool-as-number (True/False, the int-subclass trap), a numeric
    string, None, and a fractional float -- every shape exit criterion 1
    names except NaN/inf, which credit_cost has no route to receive as a
    real float (int only; see test_a_credit_cost_of_nan_or_inf_is_refused
    below for those two, sent as raw JSON since Python's json.dumps cannot
    even encode them under httpx's client -- a real caller could only send
    those tokens over the wire directly, exactly what that test does)."""
    resp = client.put(
        "/admin/kits/w-7/commercial",
        json={"credit_cost": credit_cost, "burn_cap_usd": 5.0, "display": {}},
    )
    assert resp.status_code == 422, resp.text
    assert fake_db.docs == {}


@pytest.mark.parametrize("burn_cap_usd", [
    0, -1, -0.01, True, False, "5.0", None,
])
def test_a_malformed_burn_cap_usd_is_refused_with_no_write(
        client, fake_db, burn_cap_usd):
    """THE IMPORTANT REFUSAL, burn_cap_usd half. A malformed ceiling here
    must never reach the store as a "successful" write -- the module
    docstring's whole point: a bad edit must never remove a form's
    ceiling. NaN/+-inf are pinned separately below (see
    test_a_burn_cap_usd_of_nan_or_inf_is_refused) since httpx's own JSON
    encoder refuses to serialize a Python float("nan")/float("inf") at
    all -- the only way those tokens reach a real server is a raw request
    body, which is what that test sends."""
    resp = client.put(
        "/admin/kits/w-7/commercial",
        json={"credit_cost": 2, "burn_cap_usd": burn_cap_usd, "display": {}},
    )
    assert resp.status_code == 422, resp.text
    assert fake_db.docs == {}


@pytest.mark.parametrize("credit_cost_json", ["NaN", "Infinity", "-Infinity"])
def test_a_credit_cost_of_nan_or_inf_is_refused(client, fake_db, credit_cost_json):
    """NaN/+-inf sent as RAW JSON body bytes (the literal, non-standard JSON
    tokens Python's own json module both emits and parses) -- httpx's
    client-side JSON encoder refuses to produce these from a Python float,
    so json= cannot exercise this path; a raw body is the faithful
    equivalent of a caller that sent them directly over the wire."""
    body = '{{"credit_cost": {}, "burn_cap_usd": 5.0, "display": {{}}}}'.format(
        credit_cost_json)
    resp = client.put(
        "/admin/kits/w-7/commercial",
        content=body.encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 422, resp.text
    assert fake_db.docs == {}


@pytest.mark.parametrize("burn_cap_json", ["NaN", "Infinity", "-Infinity"])
def test_a_burn_cap_usd_of_nan_or_inf_is_refused(client, fake_db, burn_cap_json):
    """See test_a_credit_cost_of_nan_or_inf_is_refused above for why this
    sends a raw body rather than json=."""
    body = '{{"credit_cost": 2, "burn_cap_usd": {}, "display": {{}}}}'.format(
        burn_cap_json)
    resp = client.put(
        "/admin/kits/w-7/commercial",
        content=body.encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 422, resp.text
    assert fake_db.docs == {}


@pytest.mark.parametrize("display", [
    "not-a-dict", ["a", "list"], 5,
    {"label": 5},
    {"k{}".format(i): "v" for i in range(21)},
])
def test_a_malformed_display_is_refused_with_no_write(
        client, fake_db, display):
    """A non-dict, a non-string value, and an oversized map -- every shape
    reachable over the wire. A non-string KEY is not parametrized here:
    JSON object keys are always strings on the wire (json= would silently
    stringify {5: ...} to {"5": ...} before the request is even sent), so
    that shape cannot arrive as a real HTTP body; _validated_display's own
    isinstance(key, str) check is still exercised structurally by the
    module's own logic, just not reachable from an HTTP-level test."""
    resp = client.put(
        "/admin/kits/w-7/commercial",
        json={"credit_cost": 2, "burn_cap_usd": 5.0, "display": display},
    )
    assert resp.status_code == 422, resp.text
    assert fake_db.docs == {}


@pytest.mark.parametrize("kit_id", ["", "a" * 200, "w 7", "w%2Fetc"])
def test_a_malformed_kit_id_is_refused_with_no_write(client, fake_db, kit_id):
    """Every shape reachable as a REAL HTTP path segment: empty (falls
    through to GET /admin/kits, a different route -- refused as a 405 on
    this PUT-only path), over-length, an embedded space, and a
    percent-encoded slash (the URL-safe way to smuggle a path separator
    into one path segment; a literal "../" or embedded newline is not
    parametrized here because httpx normalizes the former to a shorter
    path and refuses to encode the latter into a URL at all -- neither
    shape can reach this route as a real request, so a 422 assertion on
    them would test httpx's URL parser, not this route)."""
    resp = client.put(
        "/admin/kits/{}/commercial".format(kit_id),
        json={"credit_cost": 2, "burn_cap_usd": 5.0, "display": {}},
    )
    assert resp.status_code in (404, 405, 422), resp.text
    assert fake_db.docs == {}


# --------------------------------------------------------------------------
# Exit criterion 2: GET reuses bead A3's reader, and defaults on a miss.
# --------------------------------------------------------------------------

def test_get_commercial_calls_the_shared_a3_reader():
    """Pins the IMPORT, not just the output: the plan says "do not write a
    second reader", and a future rewrite that inlines a second copy of the
    fallback logic would compute the same numbers today while silently
    drifting from kit_commercials.py's own defensive-parsing rules on the
    next edit to either copy."""
    import inspect
    source = inspect.getsource(kit_routes)
    assert "kit_commercials.resolve_commercial" in source, (
        "the route must call kit_commercials.resolve_commercial -- the "
        "SAME reader bead A3's mint transaction uses -- rather than "
        "resolving the doc itself")


def test_get_for_a_kit_with_no_commercial_doc_returns_the_global_defaults(
        client, fake_db):
    resp = client.get("/admin/kits/unpriced-kit/commercial")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kit_id"] == "unpriced-kit"
    assert body["credit_cost"] == kit_commercials.DEFAULT_CREDIT_COST
    assert body["source"] == "default"
    assert isinstance(body["cap_usd"], float) and body["cap_usd"] > 0


def test_get_for_a_priced_kit_returns_its_own_values_and_source_kit(
        client, fake_db):
    fake_db.docs[(kit_commercials.COLLECTION, "w-7")] = {
        "credit_cost": 3, "burn_cap_usd": 7.5, "display": {"label": "W-7"},
    }
    resp = client.get("/admin/kits/w-7/commercial")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["credit_cost"] == 3
    assert body["cap_usd"] == 7.5
    assert body["source"] == "kit"


def test_get_writes_no_audit_row(client, fake_db):
    client.get("/admin/kits/w-7/commercial")
    assert fake_db.audit_rows() == []


# --------------------------------------------------------------------------
# GET /admin/kits -- the list route.
# --------------------------------------------------------------------------

def test_list_kits_joins_every_kit_id_with_its_resolved_commercial(
        client, fake_db, monkeypatch):
    fake_db.docs[(kit_commercials.COLLECTION, "w-7")] = {
        "credit_cost": 3, "burn_cap_usd": 7.5, "display": {},
    }
    store = _FakeFormKitStore(["w-7", "i-90"])
    monkeypatch.setattr(
        "backend.services.form_kits.get_form_kit_store", lambda: store)

    resp = client.get("/admin/kits")
    assert resp.status_code == 200, resp.text
    kits = {k["kit_id"]: k for k in resp.json()["kits"]}
    assert set(kits) == {"w-7", "i-90"}
    assert kits["w-7"]["credit_cost"] == 3
    assert kits["w-7"]["source"] == "kit"
    assert kits["i-90"]["credit_cost"] == kit_commercials.DEFAULT_CREDIT_COST
    assert kits["i-90"]["source"] == "default"


def test_list_kits_on_an_empty_store_returns_an_empty_list(
        client, fake_db, monkeypatch):
    store = _FakeFormKitStore([])
    monkeypatch.setattr(
        "backend.services.form_kits.get_form_kit_store", lambda: store)
    resp = client.get("/admin/kits")
    assert resp.status_code == 200, resp.text
    assert resp.json()["kits"] == []


def test_list_kits_writes_no_audit_row(client, fake_db, monkeypatch):
    store = _FakeFormKitStore(["w-7"])
    monkeypatch.setattr(
        "backend.services.form_kits.get_form_kit_store", lambda: store)
    client.get("/admin/kits")
    assert fake_db.audit_rows() == []


# --------------------------------------------------------------------------
# The gate.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,payload", [
    ("get", "/admin/kits", None),
    ("get", "/admin/kits/w-7/commercial", None),
    ("put", "/admin/kits/w-7/commercial",
     {"credit_cost": 1, "burn_cap_usd": 5.0, "display": {}}),
])
def test_a_tokenless_caller_is_refused(method, path, payload):
    """Cloud Run runs this service with --allow-unauthenticated, so the
    app-level gate IS the access control. Pinned per route, since a gate
    omitted on one of the three is invisible to a single-route check."""
    with TestClient(app) as c:
        resp = getattr(c, method)(path, **({"json": payload} if payload else {}))
    assert resp.status_code == 401, (path, resp.text)
