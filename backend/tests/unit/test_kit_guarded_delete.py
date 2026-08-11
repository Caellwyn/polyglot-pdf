"""Guarded hard delete of a kit (bd polyglot-pdf-6x1j).

Deletion is the ONLY destructive operation in the editor API, and it takes the
revision archive with it -- the bytes bd polyglot-pdf-w3zw/xzw5 exist to keep
retrievable. So the guard, not the delete, is the feature:

  records exist        -> 409, offering unpublish
  no records, VERIFIED -> deleted
  could not check      -> 409, refusing

The third case is the one that needs pinning hardest. The confirmation sink is
Firestore, enabled only by the deploy env; with it off the check falls back to
a local JSONL file that dies with the instance. Treating that silence as "no
records" would let an author working locally destroy evidence that exists.
"""
import asyncio
import json

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
from backend.services.form_kits import LocalFormKitStore, FormKitNotFound
from backend.utils.confirmation_logger import ConfirmationCheckUnavailable


def _run(coro):
    # asyncio.run, never get_event_loop (bd polyglot-pdf-r8gq).
    return asyncio.run(coro)


from backend.tests.unit.test_editor_kit_routes import VALID_SCHEMA as _SCHEMA


def _make_kit(root, kit_id, status="draft"):
    kit = root / kit_id
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps({"status": status, "label": kit_id}), encoding="utf-8"
    )
    (kit / "form.pdf").write_bytes(b"%PDF-1.7 test")
    return kit


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend.tests.unit.test_editor_kit_routes import _settings

    app = FastAPI()
    app.include_router(ekr.router)
    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok")
    )
    return TestClient(app), store, tmp_path


AUTH = {"X-Editor-Token": "auth-tok"}
EDIT = {"X-Editor-Token": "edit-tok"}


def _no_records(monkeypatch):
    monkeypatch.setattr(ekr, "kit_has_confirmation_records", lambda kit_id: False)


def _has_records(monkeypatch):
    monkeypatch.setattr(ekr, "kit_has_confirmation_records", lambda kit_id: True)


def _cannot_check(monkeypatch):
    def _raise(kit_id):
        raise ConfirmationCheckUnavailable("sink disabled")
    monkeypatch.setattr(ekr, "kit_has_confirmation_records", _raise)


# --- the three guard states -------------------------------------------------


def test_a_kit_with_NO_records_is_deleted(client, monkeypatch):
    c, store, root = client
    _make_kit(root, "scratch")
    _no_records(monkeypatch)

    resp = c.delete("/api/editor/kits/scratch", headers=AUTH)

    assert resp.status_code == 200, resp.text
    assert resp.json()["kitId"] == "scratch"
    assert resp.json()["objectsRemoved"] == 3   # schema, metadata, pdf
    assert not (root / "scratch").exists()


def test_a_kit_WITH_records_is_refused_and_offered_unpublish(client, monkeypatch):
    """Those records name the exact revision a client agreed to; deleting the
    kit destroys the evidence behind them."""
    c, _store, root = client
    _make_kit(root, "in-use", status="complete")
    _has_records(monkeypatch)

    resp = c.delete("/api/editor/kits/in-use", headers=AUTH)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "confirmation records" in detail
    assert "Unpublish" in detail          # the safe alternative is NAMED
    assert (root / "in-use" / "schema.json").exists()   # nothing removed


def test_an_UNVERIFIABLE_kit_is_refused_not_deleted(client, monkeypatch):
    """The case that makes this guard honest. A local editor pointed at the
    real bucket queries a JSONL file that dies with the instance -- empty is
    not the same as none. "Cannot verify" must read as NO."""
    c, _store, root = client
    _make_kit(root, "unknown-history", status="complete")
    _cannot_check(monkeypatch)

    resp = c.delete("/api/editor/kits/unknown-history", headers=AUTH)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "Cannot verify" in detail
    assert "Unpublish" in detail
    assert (root / "unknown-history" / "schema.json").exists()


# --- who may delete ---------------------------------------------------------


def test_an_EDITOR_token_cannot_delete(client, monkeypatch):
    """Maintainer rule: editors never take destructive actions, because their
    work must always be recoverable. Enforced server-side, not just hidden in
    the UI -- an editor holds a token and can call the API directly."""
    c, _store, root = client
    _make_kit(root, "scratch")
    _no_records(monkeypatch)

    resp = c.delete("/api/editor/kits/scratch", headers=EDIT)

    assert resp.status_code in (401, 403), resp.text
    assert (root / "scratch" / "schema.json").exists()


def test_an_unauthenticated_delete_is_refused(client, monkeypatch):
    c, _store, root = client
    _make_kit(root, "scratch")
    _no_records(monkeypatch)

    resp = c.delete("/api/editor/kits/scratch")

    assert resp.status_code in (401, 403), resp.text
    assert (root / "scratch" / "schema.json").exists()


# --- ordering + absent kits -------------------------------------------------


def test_a_missing_kit_404s_rather_than_reporting_a_guard_result(client, monkeypatch):
    """A typo'd id should say "not found", not answer a question about records
    for a kit that never existed."""
    c, _store, _root = client
    _no_records(monkeypatch)

    resp = c.delete("/api/editor/kits/never-existed", headers=AUTH)

    assert resp.status_code == 404, resp.text


def test_the_guard_runs_even_when_the_kit_is_a_draft(client, monkeypatch):
    """Records are keyed on kit_id, not on status: a kit reverted to draft can
    still have confirmations behind an earlier published revision. Gating the
    check on status would delete exactly those."""
    c, _store, root = client
    _make_kit(root, "was-live", status="draft")
    _has_records(monkeypatch)

    resp = c.delete("/api/editor/kits/was-live", headers=AUTH)

    assert resp.status_code == 409, resp.text
    assert (root / "was-live" / "schema.json").exists()


# --- the delete takes the archive with it ------------------------------------


def test_delete_removes_the_ARCHIVE_too(client, monkeypatch):
    """Deliberate, not an oversight: a kit with no confirmation records has
    nothing naming its superseded revisions, so leaving them would strand bytes
    no record can ever retrieve."""
    c, store, root = client
    kit = _make_kit(root, "scratch")
    archive = kit / "_archive" / "12-2024"
    archive.mkdir(parents=True)
    (archive / "schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    _no_records(monkeypatch)

    resp = c.delete("/api/editor/kits/scratch", headers=AUTH)

    assert resp.status_code == 200, resp.text
    assert resp.json()["objectsRemoved"] == 4   # 3 live + 1 archived
    assert not (root / "scratch").exists()


# --- the store primitive itself ---------------------------------------------


def test_delete_kit_refuses_to_escape_the_root(tmp_path):
    """_kit_dir is a bare join, so a traversing id resolves OUTSIDE the root --
    harmless for the reads it was written for, catastrophic for a recursive
    delete. Containment is checked before anything is removed."""
    from backend.services.form_kits import FormKitStoreError

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me", encoding="utf-8")
    root = tmp_path / "form-kits"
    root.mkdir()
    store = LocalFormKitStore(root)

    for evil in ("..", "../outside", "../../"):
        with pytest.raises(FormKitStoreError):
            _run(store.delete_kit(evil))

    assert (outside / "precious.txt").exists()


def test_delete_kit_raises_not_found_for_an_absent_kit(tmp_path):
    store = LocalFormKitStore(tmp_path)
    with pytest.raises(FormKitNotFound):
        _run(store.delete_kit("never-existed"))


def test_delete_kit_does_not_touch_a_SIBLING_with_a_shared_prefix(tmp_path):
    """"w7" must not take "w7-2024" with it. Trivially true for a directory
    delete; pinned because the GCS implementation matches on a string prefix,
    where it is only true because of the trailing slash."""
    store = LocalFormKitStore(tmp_path)
    for kit_id in ("w7", "w7-2024"):
        _make_kit(tmp_path, kit_id)

    removed = _run(store.delete_kit("w7"))

    assert removed == 3
    assert not (tmp_path / "w7").exists()
    assert (tmp_path / "w7-2024" / "schema.json").exists()


# --- the Firestore path (exit criterion 2) -----------------------------------
#
# The criterion is explicit that the kit_id existence query must be exercised
# against the FIRESTORE path, not just the local JSONL fallback -- because
# Firestore is the only durable sink, and it is the one the guard actually
# consults in production.
#
# This fake HONOURS the filter and limit rather than ignoring them (the
# neighbouring sink suite's fake returns every doc from where(), which would
# let a broken or absent filter pass this test).


class _FilteringQuery:
    def __init__(self, docs, field=None, value=None, limit=None):
        self._docs = docs
        self._field = field
        self._value = value
        self._limit = limit

    def limit(self, n):
        return _FilteringQuery(self._docs, self._field, self._value, n)

    def stream(self):
        matched = [
            d for d in self._docs
            if self._field is None or d.get(self._field) == self._value
        ]
        if self._limit is not None:
            matched = matched[:self._limit]
        for d in matched:
            m = MagicMock()
            m.to_dict.return_value = d
            yield m


class _FilteringCollection:
    def __init__(self, docs):
        self.docs = docs
        self.where_calls = []

    def where(self, *args, **kwargs):
        flt = kwargs.get("filter")
        if flt is not None:
            field, _op, value = flt.field_path, flt.op_string, flt.value
        else:
            field, _op, value = args
        self.where_calls.append((field, value))
        return _FilteringQuery(self.docs, field, value)


class _FilteringDB:
    def __init__(self, docs):
        self._collection = _FilteringCollection(docs)

    def collection(self, name):
        return self._collection


def _firestore_with(monkeypatch, docs):
    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")
    db = _FilteringDB(docs)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def test_firestore_existence_query_finds_a_record_for_THIS_kit(monkeypatch):
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    db = _firestore_with(monkeypatch, [{"kit_id": "w7", "field_id": "f1"}])

    assert kit_has_confirmation_records("w7") is True
    # Filtered on kit_id server-side, not by streaming everything and checking
    # client-side -- an equality query needs no composite index, and streaming a
    # kit's whole history to answer yes/no is the wrong shape.
    assert db._collection.where_calls == [("kit_id", "w7")]


def test_firestore_existence_query_ignores_records_for_OTHER_kits(monkeypatch):
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"kit_id": "i-90", "field_id": "f1"},
        {"kit_id": "w7-2024", "field_id": "f2"},
    ])

    assert kit_has_confirmation_records("w7") is False


def test_firestore_query_failure_is_UNAVAILABLE_not_absent(monkeypatch):
    """A broken query must not read as "no records" -- that is the difference
    between "verified safe" and "never asked"."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")

    def _broken():
        raise RuntimeError("firestore unreachable")

    monkeypatch.setattr("backend.services.auth.get_db", _broken)

    with pytest.raises(ConfirmationCheckUnavailable):
        kit_has_confirmation_records("w7")


def test_a_DISABLED_sink_is_UNAVAILABLE_not_absent(monkeypatch):
    """The production-shaped hazard: the sink defaults to off, and the local
    JSONL fallback dies with the instance. Silence there is not evidence."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "false")

    def _explode():
        raise AssertionError("get_db must not be called when the sink is off")

    monkeypatch.setattr("backend.services.auth.get_db", _explode)

    with pytest.raises(ConfirmationCheckUnavailable):
        kit_has_confirmation_records("w7")
