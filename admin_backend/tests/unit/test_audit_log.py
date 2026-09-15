"""The audit-log helper itself, and GET /admin/audit (bd polyglot-pdf-li9x0).

The route-level behaviour (one committed row per config write; a forced audit
failure leaving the config unchanged) is pinned in test_config_routes.py --
that is where exit criterion 1 lives. THIS file pins the helper's own
contract, which the routes depend on but do not exercise in full:

  * the row shape is IDENTICAL across both forms (a field present in one
    form's rows and absent from the other's makes an audit query mean two
    different things);
  * the pending form's asymmetry -- record_pending RAISES, mark_committed /
    mark_failed do NOT -- because the actions on either side of it have
    opposite consequences for a retry;
  * the read route's pagination and filters.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import audit_routes
from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin


# --------------------------------------------------------------------------
# build_row / the shared shape
# --------------------------------------------------------------------------

def _kwargs(**over):
    base = dict(
        actor_uid="u1", actor_email="ops@example.com", action="test.action",
        target="thing/1", before={"x": 1}, after={"x": 2},
    )
    base.update(over)
    return base


def test_build_row_carries_every_documented_field():
    """ROW_FIELDS is the documented shape; build_row is its only producer.
    Mutation: drop `channel` from the returned dict -- red."""
    row = audit_log.build_row(state=audit_log.STATE_COMMITTED, **_kwargs())
    assert set(row) == audit_log.ROW_FIELDS


@pytest.mark.parametrize("state", sorted(audit_log.STATES))
def test_every_legal_state_builds_and_a_typo_does_not(state):
    """A typo'd state would make every state-filtered query silently miss
    these rows. Parametrized over the whole state set, not a sample."""
    row = audit_log.build_row(state=state, **_kwargs())
    assert row["state"] == state
    with pytest.raises(ValueError):
        audit_log.build_row(state=state.upper(), **_kwargs())


def test_a_request_id_is_generated_when_none_is_given_and_kept_when_one_is():
    generated = audit_log.build_row(state=audit_log.STATE_PENDING, **_kwargs())
    assert generated["request_id"]
    other = audit_log.build_row(state=audit_log.STATE_PENDING, **_kwargs())
    assert other["request_id"] != generated["request_id"], (
        "two rows built without an explicit request id shared one -- the "
        "correlation id would group unrelated actions")

    kept = audit_log.build_row(state=audit_log.STATE_PENDING,
                               **_kwargs(request_id="fixed-id"))
    assert kept["request_id"] == "fixed-id", (
        "the pending row and its committed follow-up must share ONE id")


def test_the_two_forms_produce_the_same_field_set():
    """The drift this guards against: a field added to one writer only.
    Mutation: add a key to the transactional row's payload without adding it
    to build_row -- red."""
    db = _FakeDb()
    tx = _FakeTx()
    tx_row = audit_log.record_in_transaction(tx, db, **_kwargs())
    ref = audit_log.record_pending(db, **_kwargs())
    pending_row = db.docs[ref.id]

    assert set(tx_row) - {"doc_id"} == set(pending_row)
    assert set(pending_row) == audit_log.ROW_FIELDS


# --------------------------------------------------------------------------
# A minimal store for the helper's own tests.
# --------------------------------------------------------------------------

class _Ref:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def set(self, data, merge=False):
        if self._store.write_error is not None:
            raise self._store.write_error
        self._store.docs[self.id] = dict(data)

    def update(self, data):
        if self._store.update_error is not None:
            raise self._store.update_error
        self._store.docs.setdefault(self.id, {}).update(data)


class _Coll:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.counter += 1
            doc_id = "auto{}".format(self._store.counter)
        return _Ref(self._store, doc_id)


class _FakeDb:
    def __init__(self):
        self.docs = {}
        self.counter = 0
        self.write_error = None
        self.update_error = None

    def collection(self, name):
        assert name == audit_log.COLLECTION
        return _Coll(self)


class _FakeTx:
    def __init__(self, error=None):
        self.writes = []
        self.error = error

    def set(self, ref, data, merge=False):
        if self.error is not None:
            raise self.error
        self.writes.append((ref.id, dict(data)))


# --------------------------------------------------------------------------
# Form 1: in-transaction
# --------------------------------------------------------------------------

def test_record_in_transaction_writes_through_the_transaction_not_the_ref():
    """The row must go through tx.set, never ref.set. Mutation: swap
    tx.set(ref, row) for ref.set(row) -- red, because the write lands in the
    store immediately instead of on the transaction, which is precisely how
    an audit row survives an aborted mutation."""
    db = _FakeDb()
    tx = _FakeTx()
    audit_log.record_in_transaction(tx, db, **_kwargs())
    assert len(tx.writes) == 1
    assert db.docs == {}, (
        "the row was written directly to the store, bypassing the "
        "transaction")


def test_record_in_transaction_rows_are_born_committed():
    """There is no pending window for a transactional row: it commits with
    its mutation or not at all."""
    db = _FakeDb()
    tx = _FakeTx()
    row = audit_log.record_in_transaction(tx, db, **_kwargs())
    assert row["state"] == audit_log.STATE_COMMITTED
    assert tx.writes[0][1]["state"] == audit_log.STATE_COMMITTED


def test_a_transaction_write_failure_propagates():
    """NO try/except, deliberately. Swallowing it would let the mutation
    commit unaudited -- the one outcome this form exists to prevent.
    Mutation: wrap the tx.set in try/except -- red."""
    db = _FakeDb()
    tx = _FakeTx(error=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        audit_log.record_in_transaction(tx, db, **_kwargs())


# --------------------------------------------------------------------------
# Form 2: pending-then-committed
# --------------------------------------------------------------------------

def test_record_pending_writes_a_pending_row_and_returns_its_ref():
    db = _FakeDb()
    ref = audit_log.record_pending(db, **_kwargs())
    assert db.docs[ref.id]["state"] == audit_log.STATE_PENDING


def test_record_pending_raises_so_an_unrecordable_action_never_happens():
    """If the intent cannot be recorded, the action must not run. Mutation:
    wrap ref.set in try/except -- red."""
    db = _FakeDb()
    db.write_error = RuntimeError("store down")
    with pytest.raises(RuntimeError):
        audit_log.record_pending(db, **_kwargs())


def test_mark_committed_closes_the_row_out():
    db = _FakeDb()
    ref = audit_log.record_pending(db, **_kwargs())
    audit_log.mark_committed(ref, after={"uid": "new-user"})
    row = db.docs[ref.id]
    assert row["state"] == audit_log.STATE_COMMITTED
    assert row["after"] == {"uid": "new-user"}
    assert row["committed_ts"] > 0


def test_mark_committed_without_an_after_leaves_the_original_after():
    """A caller that already knew the result at pending time must not have
    it blanked by the closeout. Mutation: make `after` unconditional in the
    update payload -- red."""
    db = _FakeDb()
    ref = audit_log.record_pending(db, **_kwargs(after={"planned": True}))
    audit_log.mark_committed(ref)
    assert db.docs[ref.id]["after"] == {"planned": True}


def test_mark_failed_records_the_reason_and_truncates_it():
    db = _FakeDb()
    ref = audit_log.record_pending(db, **_kwargs())
    audit_log.mark_failed(ref, error="x" * 5000)
    row = db.docs[ref.id]
    assert row["state"] == audit_log.STATE_FAILED
    assert len(row["error"]) == 500, (
        "an unbounded error string can carry a stack trace into a document "
        "meant to be read in a console table")


@pytest.mark.parametrize("closeout", ["mark_committed", "mark_failed"])
def test_the_closeouts_are_best_effort_because_the_action_already_happened(
        closeout):
    """The asymmetry with record_pending, and why it is correct: raising here
    would surface an error for a mutation that SUCCEEDED, and a caller that
    retried on it would double-apply. A row stuck at pending is the honest,
    conservative outcome.

    Parametrized over BOTH closeouts: proving one swallows says nothing about
    the other (memory: mutation-verify per parametrization). Mutation: remove
    either try/except -- that case goes red."""
    db = _FakeDb()
    ref = audit_log.record_pending(db, **_kwargs())
    db.update_error = RuntimeError("store down")
    fn = getattr(audit_log, closeout)
    if closeout == "mark_failed":
        fn(ref, error="the action failed")
    else:
        fn(ref)
    assert db.docs[ref.id]["state"] == audit_log.STATE_PENDING, (
        "a failed closeout must leave the row at pending, which reads as "
        "'this may have taken effect'")


# --------------------------------------------------------------------------
# GET /admin/audit
# --------------------------------------------------------------------------

class _QuerySnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Query:
    """Enough of a Firestore query to exercise the route's own logic.

    Filters, orders and slices in Python. It is NOT trying to be Firestore --
    it is here so the route's paging arithmetic (the limit+1 probe, the
    cursor round-trip, the has_more flag) is exercised against something that
    actually returns rows in an order.
    """

    def __init__(self, rows, filters=None, cursor=None, limit=None,
                 orders=None):
        self._rows = rows
        self._filters = list(filters or [])
        self._cursor = cursor
        self._limit = limit
        # The order_by fields the ROUTE actually asked for, in order. Honored
        # rather than ignored: a fake that always sorted by (ts, doc_id)
        # would supply a tiebreaker the route had dropped, and the cursor
        # test would stay green through exactly the bug it claims to catch
        # (caught in mutation testing -- M13 survived until this was fixed).
        self._orders = list(orders or [])

    def _derive(self, **over):
        kwargs = dict(rows=self._rows, filters=self._filters,
                      cursor=self._cursor, limit=self._limit,
                      orders=self._orders)
        kwargs.update(over)
        return _Query(**kwargs)

    def where(self, filter=None):  # noqa: A002 -- Firestore's own kwarg name
        return self._derive(filters=self._filters + [filter])

    def order_by(self, field, direction=None):
        assert direction == "DESCENDING", (
            "the audit list is newest-first; an ASCENDING order_by would "
            "page backwards from the oldest row")
        return self._derive(orders=self._orders + [field])

    def start_after(self, cursor):
        return self._derive(cursor=cursor)

    def limit(self, n):
        return self._derive(limit=n)

    def _sort_key(self, pair):
        """The ordering the ROUTE requested, mapped onto the fixture rows.

        __name__ is Firestore's name for the document id. A field the route
        never ordered by contributes nothing -- which is what makes dropping
        the tiebreaker observable here.
        """
        doc_id, data = pair
        key = []
        for field in self._orders:
            key.append(doc_id if field == "__name__" else data.get(field))
        return tuple(key)

    def stream(self):
        rows = [
            (doc_id, data) for doc_id, data in self._rows
            if all(data.get(f.field) == f.value for f in self._filters)
        ]
        assert self._orders, "the route streamed an unordered query"
        # Python's sort is stable, so without a doc-id tiebreaker in
        # _orders, rows sharing a ts keep their INSERTION order regardless of
        # the reverse -- exactly how Firestore's own unspecified tiebreak
        # would make a cursor walk repeat or skip a row.
        rows.sort(key=self._sort_key, reverse=True)
        if self._cursor is not None:
            # start_after consumes the SAME ordered key vector the query was
            # ordered by; comparing against a (ts, doc_id) pair the query did
            # not order by is the bug, so build the cursor's key the same way.
            ts, doc_id = self._cursor
            cursor_key = tuple(
                doc_id if field == "__name__" else ts
                for field in self._orders)
            rows = [r for r in rows if self._sort_key(r) < cursor_key]
        if self._limit is not None:
            rows = rows[:self._limit]
        return [_QuerySnap(doc_id, data) for doc_id, data in rows]


class _StubFilter:
    def __init__(self, field, op, value):
        self.field = field
        self.op = op
        self.value = value


class _AuditDb:
    def __init__(self, rows):
        self._rows = rows

    def collection(self, name):
        assert name == audit_log.COLLECTION
        return _Query(self._rows)


@pytest.fixture
def audit_client(monkeypatch):
    rows = [
        ("d{}".format(i), {
            "action": "config.set" if i % 2 == 0 else "firm.grant",
            "actor_uid": "u1" if i < 6 else "u2",
            "channel": "staging" if i % 3 == 0 else "demo",
            # Mixed states on purpose: a fixture where every row is
            # committed cannot tell a working state filter from a missing
            # one. d3 and d7 are the pending rows.
            "state": (audit_log.STATE_PENDING if i in (3, 7)
                      else audit_log.STATE_COMMITTED),
            # TIES ON PURPOSE. d4/d5 and d8/d9 share a ts, so the
            # __name__ tiebreaker is the only thing that makes the walk
            # total. Distinct timestamps everywhere would make a route that
            # dropped the tiebreaker indistinguishable from one that kept it
            # -- two rows a millisecond apart is the realistic case anyway
            # (build_row stamps time.time(), not a monotonic counter).
            "ts": float(1000 + (i // 2) * 2 if i >= 4 else 1000 + i),
            "target": "thing/{}".format(i),
        })
        for i in range(10)
    ]
    db = _AuditDb(rows)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    monkeypatch.setattr(
        "google.cloud.firestore_v1.base_query.FieldFilter", _StubFilter)
    actor = AdminActor(uid="admin-uid-1", email="ops@example.com")
    app.dependency_overrides[require_app_admin] = lambda: actor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_audit_rows_come_back_newest_first_with_their_doc_id(audit_client):
    body = audit_client.get("/admin/audit").json()
    assert [r["doc_id"] for r in body["rows"][:3]] == ["d9", "d8", "d7"]
    assert body["next_cursor"] is None, (
        "10 rows fit in the default page of 50; there is no next page")


def test_the_cursor_walks_the_whole_log_without_repeats_or_gaps(audit_client):
    """The property that matters about pagination. Mutation: drop the
    __name__ tiebreaker order_by, or change limit+1 to limit -- the walk
    then repeats or stalls."""
    seen = []
    cursor = None
    for _ in range(10):
        params = {"limit": 3}
        if cursor:
            params["cursor"] = cursor
        body = audit_client.get("/admin/audit", params=params).json()
        seen.extend(r["doc_id"] for r in body["rows"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert cursor is None, "the walk never terminated"
    assert seen == ["d{}".format(i) for i in range(9, -1, -1)]
    assert len(seen) == len(set(seen)), "a row was returned on two pages"


@pytest.mark.parametrize("param,value,field", [
    ("action", "config.set", "action"),
    ("actor_uid", "u2", "actor_uid"),
    ("channel", "staging", "channel"),
    ("state", audit_log.STATE_COMMITTED, "state"),
    ("state", audit_log.STATE_PENDING, "state"),
])
def test_each_filter_narrows_the_result(audit_client, param, value, field):
    """One parametrization per filter: a filter wired to the wrong field
    would otherwise hide behind its neighbours."""
    body = audit_client.get("/admin/audit", params={param: value}).json()
    assert body["rows"], "the filter matched nothing; the fixture is wrong"
    assert all(r[field] == value for r in body["rows"])
    unfiltered = audit_client.get("/admin/audit").json()
    assert len(body["rows"]) < len(unfiltered["rows"]), (
        "the {} filter returned everything -- it is not being applied".format(
            param))


def test_an_unknown_state_is_refused_rather_than_silently_matching_nothing(
        audit_client):
    resp = audit_client.get("/admin/audit", params={"state": "commited"})
    assert resp.status_code == 400


@pytest.mark.parametrize("cursor", ["garbage", "1000", "abc|d1", "1000|",
                                    "1000|d1|extra"])
def test_a_malformed_cursor_is_refused_not_silently_rewound(audit_client,
                                                            cursor):
    """An operator paging through an audit trail must never be quietly
    rewound to page one. Mutation: return page one on a parse failure
    instead of raising -- red."""
    resp = audit_client.get("/admin/audit", params={"cursor": cursor})
    assert resp.status_code == 400, resp.text


@pytest.mark.parametrize("limit", [0, -1, audit_routes.MAX_PAGE_SIZE + 1])
def test_the_page_size_is_bounded(audit_client, limit):
    """The collection grows without bound and nothing prunes it, so an
    unbounded limit turns one request into a full-collection read."""
    resp = audit_client.get("/admin/audit", params={"limit": limit})
    assert resp.status_code == 422, resp.text


def test_a_missing_composite_index_is_distinguishable_from_a_real_outage(
        audit_client, monkeypatch):
    """bd polyglot-pdf-xdbqm. FAILED_PRECONDITION (most often a missing
    composite index, whose message carries a console URL that creates it in
    one click) must not collapse into the same 503 "store unavailable" a
    genuine Firestore outage returns -- the two responses call for opposite
    operator actions (click a link vs. wait). Mutation: remove the
    FailedPrecondition/InvalidArgument except clause -- goes red (503
    instead of 400)."""
    from google.api_core.exceptions import FailedPrecondition

    def _boom(self):
        raise FailedPrecondition(
            "index required, create it: https://console.example/create-index")

    monkeypatch.setattr(
        "admin_backend.tests.unit.test_audit_log._Query.stream", _boom)
    resp = audit_client.get("/admin/audit")
    assert resp.status_code == 400, resp.text
    assert "AUDIT_QUERY_ERROR" in resp.json()["detail"]


def test_a_genuine_firestore_outage_still_returns_503(audit_client,
                                                       monkeypatch):
    """Guard the guard: an ordinary Firestore failure (not FAILED_PRECONDITION
    / INVALID_ARGUMENT) must still map to the original 503 -- this bead only
    narrows the generic except, it does not remove it."""
    def _boom(self):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(
        "admin_backend.tests.unit.test_audit_log._Query.stream", _boom)
    resp = audit_client.get("/admin/audit")
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"] == "audit store unavailable"
