"""Firms datastore service (bd polyglot-pdf-lo88).

Pins the two load-bearing contracts of backend/services/firms.py:

- FAIL-CLOSED reads: get_allowed_kits returns [] on EVERY failure branch
  (disabled store, missing firm, non-active firm, malformed doc, read error)
  -- bd polyglot-pdf-vccy will gate PRIVATE kit visibility on this call, so
  any fail-open branch here becomes an information-disclosure bug there.
- Idempotent upserts: re-running the bootstrap must not corrupt created_at,
  must merge (not clobber), and upsert failures RAISE (the operator script
  maps them to exit 2 -- an admin tool must never silently no-op).

The fakes extend test_confirmation_firestore_sink.py's _FakeDB shape (that
one has no document-get()/snapshot support, which a read-modify-write needs),
kept local to this file like the precedent.

Each test's docstring names the mutation that must turn it red
(docs/standards/testing.md#test-the-tests).

ASCII only.
"""
import pytest
from firebase_admin import firestore as fb_firestore

import backend.services.firms as firms


class _FakeSnap:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._doc_id = doc_id
        self.set_calls = []  # list of (payload, merge)

    def get(self):
        return _FakeSnap(self._store.get(self._doc_id))

    def set(self, payload, merge=False):
        self.set_calls.append((dict(payload), merge))
        if merge and self._doc_id in self._store:
            self._store[self._doc_id].update(payload)
        else:
            self._store[self._doc_id] = dict(payload)


class _FakeCollection:
    def __init__(self):
        self.store = {}
        self.doc_refs = {}
        self.stream_docs = []
        self.limit_calls = []

    def document(self, doc_id):
        return self.doc_refs.setdefault(
            doc_id, _FakeDocRef(self.store, doc_id)
        )

    def limit(self, n):
        self.limit_calls.append(n)
        return self

    def stream(self):
        return iter(self.stream_docs)


class _FakeDB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _FakeCollection())


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setenv("FIRMS_FIRESTORE_ENABLED", "true")
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def _firm_doc(**over):
    doc = {
        "name": "Acme Legal Aid",
        "contact_email": "intake@acme.example",
        "allowed_kits": ["w7", "i-90"],
        "status": "active",
    }
    doc.update(over)
    return doc


def _exploding_get_db():
    raise AssertionError("get_db must not be touched on this path")


# ---------------------------------------------------------------- reads


def test_get_allowed_kits_is_inert_when_disabled(monkeypatch):
    """Mutation: invert the _firms_enabled() gate -- the explode-mock fires."""
    monkeypatch.delenv("FIRMS_FIRESTORE_ENABLED", raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", _exploding_get_db)
    assert firms.get_allowed_kits("acme") == []


@pytest.mark.parametrize(
    "case",
    [
        "missing_firm",
        "suspended",
        "kits_not_a_list",
        "kits_mixed_types",
        "read_raises",
    ],
)
def test_get_allowed_kits_fails_closed_to_empty_list(fake_db, monkeypatch, case):
    """Every failure branch resolves to [] -- a list, never None, never a
    raise (a None leaking into `kit_id in allowed` raises instead of
    denying). A list with ANY non-string entry is malformed and fails the
    WHOLE doc closed -- no partial filtering (round-2 fresh-eyes: the code
    contradicted its own every-failure-to-[] docstring). Mutation per
    branch: delete that branch's guard in get_allowed_kits (the not-exists
    early return, the status gate, the isinstance/all check -- for
    kits_mixed_types, revert it to a per-entry isinstance filter -- the
    try/except) -- the corresponding parametrization goes red."""
    col = fake_db.collection(firms._FIRMS_COLLECTION)
    if case == "suspended":
        col.store["acme"] = _firm_doc(status="suspended")
    elif case == "kits_not_a_list":
        col.store["acme"] = _firm_doc(allowed_kits="w7")
    elif case == "kits_mixed_types":
        col.store["acme"] = _firm_doc(allowed_kits=["w7", 123, None])
    elif case == "read_raises":
        def _boom():
            raise RuntimeError("iam drift")

        monkeypatch.setattr("backend.services.auth.get_db", _boom)
    # missing_firm: store stays empty on purpose.

    result = firms.get_allowed_kits("acme")

    assert isinstance(result, list)
    assert result == []


def test_get_allowed_kits_returns_stored_list_for_active_firm(fake_db):
    """The positive case. Mutation: return [] unconditionally -- red."""
    fake_db.collection(firms._FIRMS_COLLECTION).store["acme"] = _firm_doc()
    assert firms.get_allowed_kits("acme") == ["w7", "i-90"]


# --------------------------------------------------------------- upserts


def test_upsert_first_write_sets_created_at_server_timestamp(fake_db):
    """POSITIVE pin on the first write: created_at present and IS the
    SERVER_TIMESTAMP sentinel (key-existence alone would pass with any
    garbage value). Mutation: drop created_at from the first-write payload
    -- red."""
    firms.upsert_firm("acme", "Acme", "a@x.example", ["w7"])

    ref = fake_db.collection(firms._FIRMS_COLLECTION).document("acme")
    payload, merge = ref.set_calls[0]
    assert merge is False
    assert payload["created_at"] is fb_firestore.SERVER_TIMESTAMP
    assert payload["updated_at"] is fb_firestore.SERVER_TIMESTAMP
    assert payload["allowed_kits"] == ["w7"]
    assert payload["status"] == "active"


def test_upsert_rerun_omits_created_at_and_merges(fake_db):
    """The idempotency pin: the SECOND call's payload must carry NO
    created_at key (a SERVER_TIMESTAMP there would overwrite the original
    creation time on every re-run) AND must use merge=True (a bare set()
    would wipe fields the doc gained elsewhere). Mutation (named in the
    plan): make upsert_firm unconditionally include created_at -> the
    no-created_at assertion goes red; drop merge=True -> the merge
    assertion goes red."""
    firms.upsert_firm("acme", "Acme", "a@x.example", ["w7"])
    firms.upsert_firm("acme", "Acme Legal", "a@x.example", ["w7", "i-90"])

    ref = fake_db.collection(firms._FIRMS_COLLECTION).document("acme")
    assert len(ref.set_calls) == 2
    payload2, merge2 = ref.set_calls[1]
    assert merge2 is True
    assert "created_at" not in payload2
    assert payload2["updated_at"] is fb_firestore.SERVER_TIMESTAMP
    assert payload2["allowed_kits"] == ["w7", "i-90"]


def test_upsert_is_ungated_by_the_env_var(monkeypatch):
    """upsert_firm is the operator path and must work with the read gate
    off (the script would otherwise silently no-op). Mutation: add a
    _firms_enabled() early return to upsert_firm -- red."""
    monkeypatch.delenv("FIRMS_FIRESTORE_ENABLED", raising=False)
    db = _FakeDB()
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)

    firms.upsert_firm("acme", "Acme", "a@x.example", [])

    assert "acme" in db.collection(firms._FIRMS_COLLECTION).store


def test_upsert_raises_on_store_failure(monkeypatch):
    """Upsert failures RAISE (loud admin tool), unlike the fail-closed
    reads. Mutation: wrap upsert_firm's body in try/except-return -- red."""
    monkeypatch.setenv("FIRMS_FIRESTORE_ENABLED", "true")

    def _boom():
        raise RuntimeError("no creds")

    monkeypatch.setattr("backend.services.auth.get_db", _boom)
    with pytest.raises(RuntimeError):
        firms.upsert_firm("acme", "Acme", "a@x.example", [])


# ----------------------------------------------------------------- probe


def test_firms_store_status_disabled(monkeypatch):
    """Mutation: invert the gate -- 'disabled' never returned."""
    monkeypatch.delenv("FIRMS_FIRESTORE_ENABLED", raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", _exploding_get_db)
    assert firms.firms_store_status() == "disabled"


def test_firms_store_status_ok_and_read_shaped(fake_db):
    """The probe must be READ-shaped: 'ok' with ZERO document writes (the
    sink probe's write+delete shape would test the wrong permission for a
    read-only path). Mutation: switch the probe to the sink's write+delete
    -- the no-writes assertion goes red."""
    assert firms.firms_store_status() == "ok"

    col = fake_db.collection(firms._FIRMS_COLLECTION)
    assert col.limit_calls == [1]
    assert all(not ref.set_calls for ref in col.doc_refs.values())


def test_firms_store_status_reports_error(monkeypatch):
    """Mutation: swallow the exception into 'ok' -- red."""
    monkeypatch.setenv("FIRMS_FIRESTORE_ENABLED", "true")

    def _boom():
        raise RuntimeError("iam drift")

    monkeypatch.setattr("backend.services.auth.get_db", _boom)
    assert firms.firms_store_status().startswith("error:")
