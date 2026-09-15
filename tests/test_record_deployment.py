"""scripts/record_deployment.py::record (bd polyglot-pdf-tb3kp, Epic 4
bead 4.3 of docs/sprint_22_admin-console_plan.md).

Pins two fresh-eyes/cross-surface review findings:

1. record() must write a `ts` field (a float Unix epoch), the SAME field
   GET /admin/deploys (admin_backend/routes/deploy_routes.py) orders the
   whole `deployments` collection on. Without `ts`, a row this script
   writes carries only `created_at` (an ISO-8601 string) and Firestore's
   order_by("ts") EXCLUDES any document missing the ordered-on field -- so
   every staging-success row this script writes (exactly the rows the
   promotion gate reads) would be invisible to the console's deploys list
   on a query ordered by ts, even though the gate itself still passes.

2. record() must UPSERT by build_id, never blindly create a new document.
   The webhook (admin_backend/routes/deploy_webhook.py) already has a row
   for a console-triggered build's build_id by the time this script's
   build step runs (Cloud Build publishes QUEUED/WORKING before the build
   finishes) -- a blind create would leave TWO documents with the same
   build_id, and a later Pub/Sub message's own `.limit(1)` lookup would
   pick one non-deterministically, leaving the other's status permanently
   stale.

Mutation-verified: deleting the "ts" key from the written doc, and
reverting the upsert-by-build_id lookup back to a blind
`collection.document().set()`, are each what prove the corresponding test
can fail.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.record_deployment import (  # noqa: E402
    COLLECTION,
    record,
)
import scripts.record_deployment as record_deployment_module  # noqa: E402


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self.doc_id = doc_id

    def set(self, doc):
        self._store[self.doc_id] = dict(doc)

    def update(self, fields):
        assert self.doc_id in self._store, "update() on a nonexistent doc"
        self._store[self.doc_id].update(fields)


class _FakeSnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.reference = None  # set by the query

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(self, store, field, value):
        self._store = store
        self._field = field
        self._value = value
        self._limit = None

    def where(self, field, op, value):
        assert op == "=="
        return _FakeQuery(self._store, field, value)

    def limit(self, n):
        self._limit = n
        return self

    def stream(self):
        matches = [
            (doc_id, data) for doc_id, data in self._store.items()
            if data.get(self._field) == self._value
        ]
        if self._limit is not None:
            matches = matches[: self._limit]
        results = []
        for doc_id, data in matches:
            snap = _FakeSnap(doc_id, data)
            snap.reference = _FakeDocRef(self._store, doc_id)
            results.append(snap)
        return results


class _FakeCollection:
    def __init__(self, store):
        self._store = store
        self._next_id = 0

    def document(self):
        self._next_id += 1
        doc_id = "auto-{}".format(self._next_id)
        return _FakeDocRef(self._store, doc_id)

    def where(self, field, op, value):
        return _FakeQuery(self._store, field, value).where(field, op, value)


class _FakeClient:
    def __init__(self, store):
        self._store = store

    def collection(self, name):
        assert name == COLLECTION
        return _FakeCollection(self._store)


@pytest.fixture
def store():
    return {}


@pytest.fixture
def fake_client(monkeypatch, store):
    monkeypatch.setattr(
        record_deployment_module, "_client", lambda project: _FakeClient(store))
    return store


def test_record_writes_a_float_ts_field(fake_client):
    exit_code = record(
        target="backend-staging", channel="staging", sha="a" * 40,
        build_id="build-1", status="success", project="proj-1",
    )

    assert exit_code == 0
    assert len(fake_client) == 1
    doc = next(iter(fake_client.values()))
    # THE PINNED ASSERTION: ts must be present and be a float epoch, the
    # same type deploy_routes.py's own time.time() writes and
    # deploy_webhook.py's own _to_epoch() writes. Deleting this field makes
    # the assertion fail (mutation-verified).
    assert "ts" in doc, (
        "record() must write a 'ts' field (sort key for GET /admin/deploys)"
    )
    assert isinstance(doc["ts"], float)
    # created_at is kept too -- a human-readable display value, not removed.
    assert "created_at" in doc
    assert isinstance(doc["created_at"], str)


def test_record_still_derives_target_family_and_marks_triggered_by_build(
        fake_client):
    record(
        target="admin-service", channel="staging", sha="b" * 40,
        build_id="build-2", status="success", project=None,
    )

    doc = next(iter(fake_client.values()))
    assert doc["target_family"] == "admin-service"
    assert doc["triggered_by"] == "build"


def test_record_returns_1_on_a_write_failure(monkeypatch, capsys):
    class _BoomClient:
        def collection(self, name):
            raise RuntimeError("firestore unreachable")

    monkeypatch.setattr(
        record_deployment_module, "_client", lambda project: _BoomClient())

    exit_code = record(
        target="backend-staging", channel="staging", sha="c" * 40,
        build_id="build-3", status="success", project="proj-1",
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "could not write" in captured.err


def test_record_updates_an_existing_row_for_the_same_build_id_instead_of_duplicating(
        fake_client):
    """THE PINNED REGRESSION (finding 3): a console-triggered build already
    has a webhook-written row for this build_id (QUEUED, arrived before
    this build step ran) by the time record() is called. record() must
    UPDATE that row, not create a sibling. Reverting the upsert lookup
    back to a blind collection.document().set() makes this test fail
    (mutation-verified): the store would then hold 2 documents instead of
    1, both carrying build_id="build-4".
    """
    # Seed the webhook's own row, exactly as deploy_webhook.py's
    # _upsert_deployment would have written it for a QUEUED message.
    fake_client["webhook-row"] = {
        "target": "backend-staging",
        "target_family": "backend",
        "channel": "staging",
        "sha": "d" * 40,
        "build_id": "build-4",
        "status": "queued",
        "triggered_by": "op-1",
        "ts": 1000.0,
    }

    exit_code = record(
        target="backend-staging", channel="staging", sha="d" * 40,
        build_id="build-4", status="success", project="proj-1",
    )

    assert exit_code == 0
    # Exactly ONE row for this build_id -- no duplicate created.
    rows_for_build = [
        doc for doc in fake_client.values() if doc.get("build_id") == "build-4"
    ]
    assert len(rows_for_build) == 1, (
        "record() must upsert by build_id, not create a second document "
        "for a build_id that already has a row"
    )
    # The EXISTING row (webhook-row) was updated in place, not replaced by
    # a new auto-id document.
    assert "webhook-row" in fake_client
    assert fake_client["webhook-row"]["status"] == "success"
    # triggered_by is corrected to "build" -- this step's own identity,
    # overwriting the webhook's earlier "op-1" (or "external") value, since
    # this step running IS the authoritative record of who/what deployed.
    assert fake_client["webhook-row"]["triggered_by"] == "build"


def test_record_creates_a_new_row_when_no_existing_build_id_row(fake_client):
    """A bash-triggered build (or one whose webhook message has not
    arrived yet) has no pre-existing row -- record() must still create
    one, matching its original (pre-upsert) behavior for this case."""
    exit_code = record(
        target="backend-staging", channel="staging", sha="e" * 40,
        build_id="build-5", status="success", project="proj-1",
    )

    assert exit_code == 0
    assert len(fake_client) == 1
    doc = next(iter(fake_client.values()))
    assert doc["build_id"] == "build-5"
    assert doc["status"] == "success"
