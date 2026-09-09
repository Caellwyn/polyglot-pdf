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


_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a is not None and a < b,
    "<=": lambda a, b: a is not None and a <= b,
    ">": lambda a, b: a is not None and a > b,
    ">=": lambda a, b: a is not None and a >= b,
}


class _Query:
    """Supports the ONE query shape credit_ledger.reconcile_expired_for_firm
    issues: chained equality/less-than .where() filters, no order_by/limit
    (that combination belongs to read_entries, handled separately above).
    """

    def __init__(self, store, path, order_field=None, filters=None):
        self._store = store
        self._path = path
        self._order = order_field
        self._filters = list(filters or [])

    def order_by(self, field, direction="ASCENDING"):
        return _Query(self._store, self._path, field, self._filters)

    def limit(self, n):
        return self  # unused by this file's routes; read_entries takes None

    def where(self, *args, filter=None):
        if filter is not None:
            field, op, value = (
                filter.field_path, filter.op_string, filter.value)
        else:
            field, op, value = args
        return _Query(
            self._store, self._path, self._order,
            self._filters + [(field, op, value)])

    def stream(self):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path
        ]
        for field, op, value in self._filters:
            fn = _OPS[op]
            rows = [(p, d) for p, d in rows if fn(d.get(field), value)]
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

    def where(self, *args, filter=None):
        return _Query(self._store, self._path).where(*args, filter=filter)

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


@pytest.mark.parametrize("bad_firm_id", [
    "Acme", "ACME Corp", "acme/../x", "-lead", "a" * 200, "acme\n", "",
])
def test_create_firm_refuses_a_firm_id_the_other_two_naming_sites_refuse(
        client, fake_db, bad_firm_id):
    """Cross-surface review finding 1 on bd polyglot-pdf-zopqq: this route
    used to accept every one of these seven cases (confirmed by probe,
    7/7) while scripts/bootstrap_firm.py and POST /admin/users both refuse
    them via the same FIRM_ID_RE. A firm created under one of these
    spellings is then unreachable from POST /admin/users (which 422s on
    the identical id), so no staff account could ever be attached to it --
    and "Acme" vs "acme" would silently create two Firestore documents for
    what an operator believes is one firm.

    Mutation: revert _validated_firm_id to the blank-only check -- every
    case here goes from 422 to 201/200."""
    resp = client.post("/admin/firms", json={
        "firm_id": bad_firm_id, "name": "Bad", "contact_email": "a@b.com",
        "kind": "live",
    })
    assert resp.status_code == 422, resp.text
    assert fake_db.docs == {}


@pytest.mark.parametrize("bad_firm_id", [
    # "acme/../x" is deliberately excluded here: a literal "/" splits a URL
    # path into multiple segments (so it never reaches this route as ONE
    # {firm_id} value), and percent-encoding it as "%2F" is rejected by
    # Starlette's router itself with a bare 404 before any route --
    # including this one -- ever matches, so this route cannot be the
    # thing that lets it through. The create-body test above (where the
    # id arrives as a JSON string field, not a URL path) still covers it.
    "Acme", "ACME Corp", "-lead", "a" * 200, "acme\n",
])
def test_path_segment_firm_id_routes_refuse_the_same_bad_slugs(
        client, fake_db, bad_firm_id):
    """The same rule must hold on every OTHER route naming a firm by path
    segment, not just create -- a firm that somehow already exists under a
    non-conforming id must not be reachable for status/allowed_kits/kind
    mutation or its detail page either. GET is included: a 404 (unknown
    firm) and a 422 (invalid slug) are different signals, and a
    non-conforming id must never reach the "unknown firm" branch.

    Mutation: revert _validated_firm_id to the blank-only check -- every
    case here goes from 422 to 404/200."""
    # Percent-encode so a trailing newline arrives intact as part of the
    # single path segment rather than being stripped/rejected by the HTTP
    # client layer first.
    import urllib.parse
    quoted = urllib.parse.quote(bad_firm_id, safe="")
    cases = [
        ("get", "/admin/firms/{}".format(quoted), None),
        ("patch", "/admin/firms/{}/status".format(quoted),
         {"status": "active"}),
        ("patch", "/admin/firms/{}/allowed_kits".format(quoted),
         {"allowed_kits": []}),
        ("patch", "/admin/firms/{}/kind".format(quoted),
         {"kind": "live", "reason": "test"}),
    ]
    for method, path, json_body in cases:
        resp = getattr(client, method)(path, json=json_body) \
            if json_body is not None else client.get(path)
        assert resp.status_code == 422, "{} {} -> {}".format(
            method.upper(), path, resp.text)
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


def test_get_firm_reconciles_a_real_expired_mint_record_end_to_end(
        client, fake_db):
    """EXIT CRITERION 3, LITERALLY: 'test with one expired mint record' --
    unlike the mocked-reconcile test below, this drives the REAL
    credit_ledger.reconcile_expired_for_firm -> refund_expired_link ->
    append_entry chain against one genuinely expired, unopened links/{jti}
    record on the demo channel, with no link_redemptions doc (so the link
    was never opened). The balance the route returns must be the PRE-
    refund balance plus the record's credit_cost, and the mint record's
    status must have flipped to refunded.

    Mutation: delete the reconcile_expired_for_firm call from get_firm --
    this goes red because the balance would then read 100 (the credit_cost
    is never refunded) instead of 105, and the mint record would still show
    status=minted."""
    _seed_firm(fake_db, "acme", balance_credits=100)
    fake_db.docs[("links", "jti-expired-1")] = {
        "jti": "jti-expired-1", "firm_id": "acme", "kit_id": "w7",
        "employee_id": "emp-1", "credit_cost": 5, "cap_usd": 3.0,
        "minted_at": 100, "open_deadline": 200, "status": "minted",
        "revoked_by": None, "revoked_at": None,
    }
    # now (module default time.time()) is far past open_deadline=200, so
    # the query's `open_deadline < now` always matches this fixture.

    resp = client.get("/admin/firms/acme")
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance_credits"] == 105

    link_doc = fake_db.docs[("links", "jti-expired-1")]
    assert link_doc["status"] == "refunded"

    rows = fake_db.ledger_rows("acme")
    assert len(rows) == 1
    assert rows[0]["type"] == "expiry_refund"
    assert rows[0]["amount"] == 5
    assert rows[0]["link_jti"] == "jti-expired-1"


def test_get_firm_does_not_refund_an_expired_link_that_was_opened(
        client, fake_db):
    """The redemption doc's existence alone refuses the refund (module
    contract of credit_ledger.refund_expired_link), even though the mint
    record itself is expired and still shows status=minted."""
    _seed_firm(fake_db, "acme", balance_credits=100)
    fake_db.docs[("links", "jti-expired-2")] = {
        "jti": "jti-expired-2", "firm_id": "acme", "kit_id": "w7",
        "employee_id": "emp-1", "credit_cost": 5, "cap_usd": 3.0,
        "minted_at": 100, "open_deadline": 200, "status": "minted",
        "revoked_by": None, "revoked_at": None,
    }
    fake_db.docs[("link_redemptions", "jti-expired-2")] = {
        "opened_at": 150, "form_session_id": "fs-1",
    }

    resp = client.get("/admin/firms/acme")
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance_credits"] == 100
    assert fake_db.docs[("links", "jti-expired-2")]["status"] == "minted"
    assert fake_db.ledger_rows("acme") == []


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


def _seed_kindless_firm(fake_db, firm_id="acme"):
    """A pre-A1 firm doc: no `kind` key at all (scripts/backfill_firm_kind.py
    has not yet run on it), and -- for the same reason -- no `status` or
    `allowed_kits` key either, matching a doc bootstrap_firm.py wrote before
    those fields existed. Built by hand rather than via _seed_firm (which
    always seeds all five fields) so the missing keys are truly absent from
    the fake store, not merely falsy."""
    doc = {"name": "Acme LLC", "contact_email": "ops@acme.example"}
    fake_db.docs[("firms", firm_id)] = doc
    return doc


# --------------------------------------------------------------------------
# Cross-surface review findings 1 + 2 on bd polyglot-pdf-zopqq: a PATCH must
# not materialize a default for a field the stored doc never had.
# scripts/backfill_firm_kind.py gates its --mock allowlist and its
# --seed-credits grant on `"kind" in firm`; a PATCH that invents `kind` on a
# kindless doc makes the backfill script skip that firm for both, silently
# and permanently misclassifying it as a paying live firm.
# --------------------------------------------------------------------------

def test_set_status_on_a_kindless_doc_does_not_invent_kind(client, fake_db):
    """Reproduces the reviewer's repro: PATCH .../status on a doc with no
    stored `kind` must leave `kind` absent, not write kind="live".

    Mutation-verified: reverting _apply_firm_patch's merged-dict fix (making
    every field always-present, defaulted via .get(key, default) the way the
    pre-fix code did) turns this red -- 'kind' appears in the doc as 'live'
    after a status-only patch. Confirmed 2026-09-08; fix restored after."""
    _seed_kindless_firm(fake_db, "acme")
    resp = client.patch("/admin/firms/acme/status", json={"status": "active"})
    assert resp.status_code == 200, resp.text
    doc = fake_db.firm("acme")
    assert "kind" not in doc, (
        "a status-only PATCH must not materialize kind onto a kindless "
        "doc -- doing so makes scripts/backfill_firm_kind.py's had_kind "
        "gate skip this firm for both --mock and --seed-credits")
    assert doc["status"] == "active"


def test_set_status_on_a_kindless_doc_does_not_invent_allowed_kits(
        client, fake_db):
    """Same root cause as the kind case: allowed_kits must stay absent too
    (finding 2 -- same fix, enumerated together per CLAUDE.md scar #8)."""
    _seed_kindless_firm(fake_db, "acme")
    client.patch("/admin/firms/acme/status", json={"status": "active"})
    doc = fake_db.firm("acme")
    assert "allowed_kits" not in doc


def test_set_allowed_kits_on_a_kindless_doc_does_not_invent_kind_or_status(
        client, fake_db):
    """The allowed_kits route must not invent kind or status either --
    enumerating the OTHER patch route for the same finding, not just the
    status one the repro happened to use."""
    _seed_kindless_firm(fake_db, "acme")
    resp = client.patch("/admin/firms/acme/allowed_kits",
                        json={"allowed_kits": ["w7"]})
    assert resp.status_code == 200, resp.text
    doc = fake_db.firm("acme")
    assert "kind" not in doc
    assert "status" not in doc
    assert doc["allowed_kits"] == ["w7"]


def test_set_kind_on_a_kindless_doc_does_not_invent_status_or_allowed_kits(
        client, fake_db):
    """The kind route itself must not invent status/allowed_kits when
    reclassifying a firm that never had them stored."""
    _seed_kindless_firm(fake_db, "acme")
    resp = client.patch("/admin/firms/acme/kind",
                        json={"kind": "mock", "reason": "backfill by hand"})
    assert resp.status_code == 200, resp.text
    doc = fake_db.firm("acme")
    assert "status" not in doc
    assert "allowed_kits" not in doc
    assert doc["kind"] == "mock"


def test_set_status_on_a_fully_seeded_doc_still_preserves_kind(
        client, fake_db):
    """Guard against overcorrecting: a doc that DOES have a stored kind
    must still carry it forward unchanged on a status-only patch (this is
    test_set_status_preserves_the_firms_other_fields's assertion restated
    against the new absent-key-aware merge, so a fix for the kindless case
    cannot regress the already-classified case)."""
    _seed_firm(fake_db, "acme", kind="mock", allowed_kits=["w7"])
    client.patch("/admin/firms/acme/status", json={"status": "suspended"})
    doc = fake_db.firm("acme")
    assert doc["kind"] == "mock"
    assert doc["allowed_kits"] == ["w7"]


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


# --------------------------------------------------------------------------
# Coupling check: this module's two hand-rolled writers vs. upsert_firm's
# payload shape (module docstring: "WRITES MATCH ... BUT DO NOT CALL IT").
# --------------------------------------------------------------------------

def _dict_literal_keys(tree, *, func_name, var_name):
    """The string keys of the FIRST dict literal assigned to `var_name`
    inside function `func_name`, found via an AST walk (not a source grep --
    see test_credit_ledger.py's identical rationale: a grep pins one
    spelling, an AST walk pins the actual shape).
    """
    import ast

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Assign)
                        and len(inner.targets) == 1
                        and isinstance(inner.targets[0], ast.Name)
                        and inner.targets[0].id == var_name
                        and isinstance(inner.value, ast.Dict)):
                    return {
                        key.value for key in inner.value.keys
                        if isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                    }
    return None


def test_apply_firm_patch_merged_dict_matches_upsert_firm_payload_keys():
    """Scar #8: pin the SET, not the instance. _apply_firm_patch's `merged`
    dict (admin_backend/routes/firm_routes.py) and upsert_firm's `payload`
    dict (backend/services/firms.py) are two INDEPENDENT writers of the
    firms/{firm_id} document that must agree on which non-timestamp,
    non-balance fields a firm document carries -- the module docstring
    explains why they cannot be merged into one function (upsert_firm's
    read+write is not transactional, so a transactional caller cannot call
    it without a second, transaction-illegal read). Nothing else ties the
    two together, so a field added to one payload and not the other would
    silently drift: a PATCH route would either drop a real field on every
    re-write, or upsert_firm's bootstrap path would omit a field this
    service depends on.

    Compares the key sets, not the dict contents or ordering -- `merged`
    also carries `updated_at` (added right after this literal, mirroring
    upsert_firm's own `updated_at` key), so both sides are widened by that
    one key before comparing, keeping the assertion about the FIELD SET
    upsert_firm's docstring calls "the known non-balance fields", not about
    incidental literal placement.

    Mutation-verified: dropping "status" from _apply_firm_patch's `merged`
    literal turns this red (2026-09-08); restored after confirming the
    failure.
    """
    import ast
    import pathlib

    firm_routes_path = pathlib.Path(firm_routes.__file__)
    firms_path = pathlib.Path(firms.__file__)

    routes_tree = ast.parse(firm_routes_path.read_text(encoding="utf-8"))
    firms_tree = ast.parse(firms_path.read_text(encoding="utf-8"))

    merged_keys = _dict_literal_keys(
        routes_tree, func_name="_apply_firm_patch", var_name="merged")
    payload_keys = _dict_literal_keys(
        firms_tree, func_name="upsert_firm", var_name="payload")

    assert merged_keys is not None, (
        "_apply_firm_patch's `merged` dict literal was not found -- update "
        "this test's AST walk if the write was restructured")
    assert payload_keys is not None, (
        "upsert_firm's `payload` dict literal was not found -- update this "
        "test's AST walk if the write was restructured")

    # upsert_firm's payload additionally carries the FIRST-CREATE-only keys
    # (created_at, balance_credits, balance_updated_at) added conditionally
    # after this literal -- those are deliberately NOT part of
    # _apply_firm_patch's re-write set (a PATCH route never re-creates a
    # firm), so they are excluded from the comparison rather than asserted
    # equal.
    first_create_only = {
        "created_at", "balance_credits", "balance_updated_at"}
    # _apply_firm_patch adds "updated_at" via `**merged` spread right after
    # this literal (mirroring upsert_firm's own inline "updated_at" key) --
    # add it here so the comparison is over the FIELD SET both writers
    # produce, not over which line each happens to add updated_at on.
    merged_keys = merged_keys | {"updated_at"}
    assert payload_keys - first_create_only == merged_keys, (
        "backend/services/firms.py::upsert_firm's payload keys and "
        "admin_backend/routes/firm_routes.py::_apply_firm_patch's merged "
        "keys have drifted apart -- these are two independent writers of "
        "the SAME firms document shape (see the firm_routes.py module "
        "docstring) and must be updated together. upsert_firm (minus "
        "first-create-only fields): {} -- _apply_firm_patch: {}".format(
            sorted(payload_keys - first_create_only), sorted(merged_keys))
    )


# --------------------------------------------------------------------
# Scar #8, set-derived: every site that validates a firm_id slug must
# apply the SAME rule (cross-surface review finding 1 on bd
# polyglot-pdf-zopqq -- this module's own copy of the check was missing
# entirely until this fix; a future fourth site could just as easily skip
# it again unless the SET, not one instance, is pinned).
# --------------------------------------------------------------------

_FIRM_ID_VALIDATING_MODULES = {
    "admin_backend/routes/firm_routes.py",
    "admin_backend/routes/user_routes.py",
    "scripts/bootstrap_firm.py",
}


def _module_firm_id_re_source(repo_root, rel_path):
    """The RHS source text of that module's `FIRM_ID_RE = re.compile(...)`
    assignment, via an AST walk (not a source grep, for the same reason
    the balance_credits scar #8 guard uses ast.walk: a grep pins one
    spelling, not the assignment itself)."""
    import ast

    path = repo_root / rel_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "FIRM_ID_RE"
                   for t in node.targets):
            continue
        return ast.dump(node.value)
    return None


def test_every_firm_id_validating_site_applies_the_same_slug_rule():
    """Pin the SET, not the instance (scar #8). This bead's own review
    found firm_routes.py had joined the set of modules that name a firm by
    caller-supplied id WITHOUT actually enforcing the shared rule
    (_validated_firm_id checked only non-blank) -- a set-derived test is
    the guard the reviewer asked for so the next such site cannot skip it
    silently the same way.

    Three things are pinned together:
      1. Every module in _FIRM_ID_VALIDATING_MODULES actually DEFINES a
         FIRM_ID_RE (catches a rename/refactor that drops the constant
         instead of just weakening its pattern).
      2. All three definitions are IDENTICAL by AST comparison, not string
         equality on source text (whitespace/formatting must not matter,
         but the actual regex must).
      3. firm_routes.py's _validated_firm_id calls FIRM_ID_RE.fullmatch --
         not .match (bd polyglot-pdf-sbfk's trailing-newline bug class) --
         mirroring the AST check test_bootstrap_firm_cli.py already runs
         for the script's own call site.

    Mutation: change firm_routes.py's FIRM_ID_RE pattern (or its
    fullmatch call) without updating the other two sites -- red.
    """
    import ast
    import pathlib

    repo_root = pathlib.Path(firm_routes.__file__).resolve().parents[2]

    sources = {}
    for rel_path in sorted(_FIRM_ID_VALIDATING_MODULES):
        dumped = _module_firm_id_re_source(repo_root, rel_path)
        assert dumped is not None, (
            "{} no longer defines FIRM_ID_RE -- either restore it or "
            "remove it from _FIRM_ID_VALIDATING_MODULES here (and confirm "
            "that module no longer validates a firm_id at all)".format(
                rel_path)
        )
        sources[rel_path] = dumped

    distinct = set(sources.values())
    assert len(distinct) == 1, (
        "FIRM_ID_RE has drifted apart across the firm-slug-validating "
        "sites -- every site must enforce the identical rule: {}".format(
            {k: v for k, v in sources.items()})
    )

    # firm_routes.py's own call site: fullmatch, not match.
    firm_routes_path = repo_root / "admin_backend/routes/firm_routes.py"
    tree = ast.parse(firm_routes_path.read_text(encoding="utf-8"))
    calls_fullmatch = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "fullmatch"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "FIRM_ID_RE"
        for node in ast.walk(tree)
    )
    assert calls_fullmatch, (
        "admin_backend/routes/firm_routes.py must call "
        "FIRM_ID_RE.fullmatch(...), not .match(...) -- a $-anchored "
        ".match still accepts a trailing newline (bd polyglot-pdf-sbfk)"
    )
