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
    def __init__(self, docs, field=None, value=None, limit=None, sink=None, op=None):
        self._docs = docs
        self._field = field
        self._value = value
        self._limit = limit
        self._sink = sink
        self._op = op

    def limit(self, n):
        return _FilteringQuery(
            self._docs, self._field, self._value, n, self._sink, self._op
        )

    def _match(self, d):
        # Mirror the SDK's resolved semantics: IS_NULL matches a STORED null and
        # not a missing key; IS_NOT_NULL is its complement.
        op = getattr(self._op, "name", None) or str(self._op or "")
        if "IS_NOT_NULL" in op:
            return self._field in d and d[self._field] is not None
        if "IS_NULL" in op:
            return self._field in d and d[self._field] is None
        return self._field in d and d[self._field] == self._value

    def stream(self):
        matched = [
            d for d in self._docs
            if self._field is None or self._match(d)
        ]
        if self._limit is not None:
            matched = matched[:self._limit]
        # Record the SHAPE of the request (see the limit test) rather than
        # only its boolean answer. `streamed` counts documents the caller
        # actually CONSUMED, not the batch size: a caller that breaks early
        # reads fewer, and on a metered path that difference is the whole
        # point. Counting the batch instead made an early `return` invisible
        # (bd polyglot-pdf-xwlt).
        record = {"limit": self._limit, "streamed": 0}
        if self._sink is not None:
            self._sink.append(record)
        for d in matched:
            record["streamed"] += 1
            m = MagicMock()
            m.to_dict.return_value = d
            yield m


class _FilteringCollection:
    def __init__(self, docs):
        self.docs = docs
        self.where_calls = []
        self.streams = []

    def where(self, *args, **kwargs):
        flt = kwargs.get("filter")
        if flt is not None:
            # op_string is what the SDK RESOLVED to, not what the caller typed:
            # ("kit_id","==",None) becomes a UnaryFilter whose op_string is the
            # IS_NULL enum. Record it, because an inverted sweep (IS_NOT_NULL)
            # would make every kit permanently undeletable in production while
            # a value-only fake stayed green (Opus fresh-eyes round 3).
            field, op, value = flt.field_path, flt.op_string, flt.value
        else:
            field, op, value = args
        # A resolved unary op is an ENUM whose str() is its integer ("3"), so
        # record .name when there is one -- otherwise every operator assertion
        # compares against a meaningless digit.
        self.where_calls.append((field, getattr(op, "name", None) or str(op), value))
        return _FilteringQuery(self.docs, field, value, op=op, sink=self.streams)


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

    db = _firestore_with(monkeypatch, [{"event": "field_confirmed", "kit_id": "w7", "field_id": "f1"}])

    assert kit_has_confirmation_records("w7") is True
    # Filtered on EVENT server-side, with the kit_id test client-side over the
    # bounded stream (bd polyglot-pdf-xwlt / 68s2q). It was a kit_id equality
    # query until the session-lifecycle events became live callers WITH a
    # kit_id: an unscoped kit_id query then matched them, and one voice session
    # made a kit permanently undeletable. Filtering on both fields server-side
    # would need a COMPOSITE INDEX, which this guard deliberately avoids.
    assert db._collection.where_calls == [("event", "==", "field_confirmed")]


def test_firestore_existence_query_ignores_records_for_OTHER_kits(monkeypatch):
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"event": "field_confirmed", "kit_id": "i-90", "field_id": "f1"},
        {"event": "field_confirmed", "kit_id": "w7-2024", "field_id": "f2"},
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
    JSONL fallback dies with the instance. Silence there is not evidence.

    This test used to pass for the WRONG REASON (Opus fresh-eyes): its stub
    raised AssertionError, which the function's broad `except Exception`
    caught and re-raised as ConfirmationCheckUnavailable -- so deleting the
    enabled-check entirely left it green. It now asserts get_db was never
    reached AND that the message names the DISABLED sink rather than a query
    failure, so the two paths into this exception cannot be confused.
    """
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "false")
    db = MagicMock(side_effect=AssertionError("get_db must not be called"))
    monkeypatch.setattr("backend.services.auth.get_db", db)

    with pytest.raises(ConfirmationCheckUnavailable) as exc:
        kit_has_confirmation_records("w7")

    # The short-circuit fired: the sink was never consulted at all.
    assert db.call_count == 0
    # ...and it says WHY, distinguishing "never asked" from "asked and failed".
    assert "not enabled" in str(exc.value)


# --- the GCS impl (the one that actually ships) ------------------------------
#
# LocalFormKitStore is the dev fallback; GCS is production. The sibling-prefix
# test above exercises the LOCAL store, where a directory delete makes prefix
# collision structurally impossible -- so it passed for a reason unrelated to
# what its docstring claimed to protect (Opus fresh-eyes). These drive the GCS
# implementation, where the trailing slash is the only thing preventing
# collateral destruction.


def _gcs(registry, prefix="form-kits"):
    from backend.tests.unit.test_editor_kit_routes import _gcs_store
    return _gcs_store(registry, prefix)


def _seed(registry, *names):
    for n in names:
        registry[n] = {"data": b"x", "content_type": "application/json"}


def test_gcs_delete_removes_the_kit_and_its_archive(tmp_path):
    registry = {}
    _seed(registry,
          "form-kits/w7/schema.json",
          "form-kits/w7/metadata.json",
          "form-kits/w7/form.pdf",
          "form-kits/w7/_archive/12-2024/schema.json")
    store = _gcs(registry)

    removed = _run(store.delete_kit("w7"))

    assert removed == 4
    assert registry == {}


def test_gcs_delete_does_NOT_touch_a_SIBLING_WITH_A_SHARED_PREFIX(tmp_path):
    """The trailing slash is the whole defense. list_blobs matches a RAW string
    prefix, so deleting "w7" without it also sweeps away "w7-2024" and every
    archived revision under it -- a silent multi-kit destruction of exactly the
    bytes the revision archive exists to preserve. Removing the slash left the
    full 1903-test backend suite green (Opus fresh-eyes)."""
    registry = {}
    _seed(registry,
          "form-kits/w7/schema.json",
          "form-kits/w7-2024/schema.json",
          "form-kits/w7-2024/_archive/12-2024/schema.json",
          "form-kits/w7-old/metadata.json")
    store = _gcs(registry)

    removed = _run(store.delete_kit("w7"))

    assert removed == 1
    assert sorted(registry) == [
        "form-kits/w7-2024/_archive/12-2024/schema.json",
        "form-kits/w7-2024/schema.json",
        "form-kits/w7-old/metadata.json",
    ]


def test_gcs_delete_raises_not_found_for_an_absent_kit():
    from backend.services.form_kits import FormKitNotFound as NF

    registry = {}
    _seed(registry, "form-kits/other/schema.json")
    store = _gcs(registry)

    with pytest.raises(NF):
        _run(store.delete_kit("never-existed"))
    assert "form-kits/other/schema.json" in registry


@pytest.mark.parametrize("unsafe", ["", ".", "..", "a/b", "../other", "/abs"])
def test_gcs_delete_refuses_an_unsafe_kit_id(unsafe):
    """A kit id containing a separator would widen the prefix past this kit."""
    from backend.services.form_kits import FormKitStoreError

    registry = {}
    _seed(registry, "form-kits/w7/schema.json")
    store = _gcs(registry)

    with pytest.raises(FormKitStoreError):
        _run(store.delete_kit(unsafe))
    assert "form-kits/w7/schema.json" in registry


def test_gcs_delete_honours_an_empty_prefix_deployment():
    """FORM_KITS_REMOTE_PREFIX may be blank, making the kit id the FIRST path
    segment -- the case where a missing trailing slash would be worst, since
    every kit sits at the bucket root."""
    registry = {}
    _seed(registry, "w7/schema.json", "w7-2024/schema.json")
    store = _gcs(registry, prefix="")

    removed = _run(store.delete_kit("w7"))

    assert removed == 1
    assert sorted(registry) == ["w7-2024/schema.json"]


def test_gcs_delete_refuses_wholesale_if_the_listing_returns_a_STRAY(tmp_path):
    """A blob outside the prefix means the client or the prefix maths is
    broken. Skipping it would return a count that quietly disagrees with the
    listing and leave a half-deleted kit -- so refuse before removing
    anything (Opus fresh-eyes: the old guard skipped, and was unreachable)."""
    from backend.services.form_kits import FormKitStoreError
    from types import SimpleNamespace

    registry = {}
    _seed(registry, "form-kits/w7/schema.json")
    store = _gcs(registry)
    # A listing that violates its own contract.
    store._client = SimpleNamespace(
        list_blobs=lambda bucket_name, prefix: [
            SimpleNamespace(name="form-kits/w7/schema.json", delete=lambda: None),
            SimpleNamespace(name="form-kits/OTHER/schema.json", delete=lambda: None),
        ]
    )

    with pytest.raises(FormKitStoreError) as exc:
        _run(store.delete_kit("w7"))
    assert "outside" in str(exc.value)
    # Nothing was removed -- the refusal came BEFORE any delete.
    assert "form-kits/w7/schema.json" in registry


def test_the_existence_query_asks_for_at_most_ONE_document(monkeypatch):
    """The check is BOUNDED, so a popular kit's whole confirmation history
    never streams on a metered read path.

    The bound moved from limit(1) on a kit_id query to _LEGACY_SCAN_LIMIT on
    the event-scoped stream (bd polyglot-pdf-xwlt / 68s2q): a kit_id query
    could not stay unscoped once the session events carried a kit_id. The
    stream still SHORT-CIRCUITS on the first record naming this kit, so the
    common case reads one document, and the worst case is bounded by the
    limit -- never the full history.

    Asserts the SHAPE the query asked for, recorded by the fake. An earlier
    version tried to wrap stream() after the fact and silently measured
    nothing -- dropping the limit left it green (caught by re-running the
    mutation rather than trusting the pass)."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    docs = [{"event": "field_confirmed", "kit_id": "w7", "field_id": f"f{i}"}
            for i in range(50)]
    db = _firestore_with(monkeypatch, docs)

    assert kit_has_confirmation_records("w7") is True

    assert db._collection.streams == [{"limit": 50, "streamed": 1}], (
        "the check must be BOUNDED by the scan limit, and must short-circuit "
        "on the first record naming this kit"
    )


def test_a_record_naming_NO_kit_blocks_deletion_rather_than_clearing_it(monkeypatch):
    """An equality filter cannot match a record whose kit_id is NULL -- and
    those are real: kit_id is optional end to end, and today's frontend sends
    `?? null`. A kit-scoped query is blind to them, so "no rows" would be a
    silent false SAFE on a form clients really did confirm against (Opus
    fresh-eyes round 2; the sink suite's own docstring warned that "a query
    cannot silently skip pre-47r3 sessions" -- this was such a query).

    Those records cannot be attributed to a specific kit, so guessing is not
    available. Refusing is the honest answer.
    """
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    db = _firestore_with(monkeypatch, [{"event": "field_confirmed", "kit_id": None, "form_id": "W-7"}])

    with pytest.raises(ConfirmationCheckUnavailable) as exc:
        kit_has_confirmation_records("w7")
    assert "name no kit" in str(exc.value)

    # PIN THE SERVER-SIDE FILTER. The null test moved client-side (bd
    # polyglot-pdf-xwlt / 68s2q: a kit_id-shaped query could not stay unscoped
    # once the session events carried a kit_id), so the operator this once
    # pinned -- IS_NULL vs its catastrophic inverse IS_NOT_NULL -- no longer
    # exists. What must NOT drift is that the ONLY server-side filter is the
    # event scope: a query on kit_id here would match session rows again and
    # resurrect the undeletable-kit bug, and one on any other field could
    # sweep in every record that HAS a kit_id (the inversion danger, in its
    # new form). The client-side null semantics are pinned by outcome above
    # and by test_a_session_event_with_a_kit_id_does_NOT_block_deletion.
    assert db._collection.where_calls == [("event", "==", "field_confirmed")], (
        "the guard must filter server-side ONLY on the event scope; a kit_id "
        "filter here would match session-telemetry rows and make a kit "
        "permanently undeletable after one voice session"
    )


def test_an_unattributed_record_does_not_mask_a_DIRECT_hit(monkeypatch):
    """A kit that IS named still reports True -- the null sweep must not
    downgrade a definite yes into "cannot verify", or the 409 would name the
    wrong reason."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"event": "field_confirmed", "kit_id": None, "form_id": "W-7"},
        {"event": "field_confirmed", "kit_id": "w7", "field_id": "f1"},
    ])

    assert kit_has_confirmation_records("w7") is True


def test_a_clean_collection_still_clears_a_kit_for_deletion(monkeypatch):
    """The refusal must not become universal: with records that all name OTHER
    kits and none naming nothing, deletion is still permitted -- otherwise the
    feature is unusable the moment any confirmation exists."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"event": "field_confirmed", "kit_id": "i-90", "field_id": "f1"},
        {"event": "field_confirmed", "kit_id": "w7-2024", "field_id": "f2"},
    ])

    assert kit_has_confirmation_records("w7") is False


def test_a_session_event_with_NO_kit_id_KEY_does_not_block_deletion(monkeypatch):
    """log_form_session_start/_end omit the key entirely rather than storing
    null. Firestore equality-on-null does not match a missing key, so these
    must not trip the refusal -- otherwise every kit becomes undeletable as
    soon as one session has ever been logged."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"event": "form_session_started", "form_session_id": "s1"},
        {"event": "form_session_ended", "form_session_id": "s1"},
    ])

    assert kit_has_confirmation_records("w7") is False


def test_the_NULL_SWEEP_also_asks_for_at_most_one_document(monkeypatch):
    """The unattributed-record refusal is reached only after the whole bounded
    stream is checked (a definite match for THIS kit must win first), so this
    seeds records that name NO kit and asserts the scan is still bounded --
    the expensive path, unpinned before Opus fresh-eyes round 3."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    docs = [{"event": "field_confirmed", "kit_id": None, "form_id": f"F{i}"}
            for i in range(50)]
    db = _firestore_with(monkeypatch, docs)

    with pytest.raises(ConfirmationCheckUnavailable):
        kit_has_confirmation_records("w7")

    # ONE bounded stream now does both jobs (event-scoped, kit tested
    # client-side): it reads to the limit because no record names w7, and
    # never beyond it.
    assert db._collection.streams == [{"limit": 50, "streamed": 50}]


def test_the_refusal_is_NOT_reported_as_a_query_failure(monkeypatch):
    """An operator triaging "why can't I delete this?" must not be sent hunting
    a Firestore outage that never happened.

    The refusal is raised INSIDE the try that wraps the queries, so without an
    explicit re-raise it was caught and logged as
    `confirmation_kit_existence_check_failed` -- an ERROR naming a broken
    client. The ConfirmationCheckUnavailable-vs-False design exists to keep
    "product decision" apart from "infrastructure fault"; the telemetry must
    not re-merge them (Opus fresh-eyes round 3).

    Captures structlog directly: my first attempt used caplog, which does not
    see these events, so the assertion was vacuous and the mutation survived.
    """
    import backend.utils.confirmation_logger as cl

    # Patch the MODULE's logger, not the global config: structlog binds the
    # logger at import, so reconfiguring afterwards never reaches it (my
    # structlog.configure attempt captured nothing and the assertion was
    # vacuous a second time).
    names = []

    class _Spy:
        def _record(self, event, **kw):
            names.append(event)
        info = warning = error = debug = _record

    monkeypatch.setattr(cl, "_log", _Spy())

    _firestore_with(monkeypatch, [{"event": "field_confirmed", "kit_id": None, "form_id": "W-7"}])
    with pytest.raises(ConfirmationCheckUnavailable):
        cl.kit_has_confirmation_records("w7")
    assert "confirmation_kit_existence_check_failed" not in names, (
        f"a legitimate refusal was logged as a query failure: {names}"
    )
    assert "confirmation_unattributed_records_block_delete" in names, names


def test_a_LEGACY_record_with_no_kit_id_KEY_blocks_deletion(monkeypatch):
    """The same blindness one shape over. IS_NULL matches a STORED null, not a
    MISSING key -- and field_confirmed records written between the Firestore
    sink shipping (2026-08-03) and kit_id joining the event dict (2026-08-05,
    bd polyglot-pdf-47r3) omit the key entirely. Both earlier queries skip
    them, so a kit whose only records are that vintage reported "verified: no
    records" and was hard-deleted WITH its archive (Opus outer cross-surface
    review, confirmed against the pre-47r3 event literal in git)."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        # Exactly the pre-47r3 shape: no kit_id key at all.
        {"event": "field_confirmed", "form_id": "W-7", "field_id": "f1"},
    ])

    with pytest.raises(ConfirmationCheckUnavailable) as exc:
        kit_has_confirmation_records("w7")
    assert "predating kit identity" in str(exc.value)


def test_SESSION_records_with_no_kit_id_key_still_do_NOT_block(monkeypatch):
    """The reason the legacy sweep is scoped to event == field_confirmed.
    Session-lifecycle records share the missing-key shape, so sweeping on the
    SHAPE alone would make every kit permanently undeletable the moment one
    session is logged -- the failure mode the IS_NOT_NULL assertion exists to
    prevent, arrived at from the other direction."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"event": "form_session_started", "form_session_id": "s1"},
        {"event": "form_session_ended", "form_session_id": "s1"},
    ])

    assert kit_has_confirmation_records("w7") is False


def test_a_MODERN_record_for_another_kit_does_not_block(monkeypatch):
    """A field_confirmed record that HAS a kit_id naming a different kit is
    fully attributed -- it must not trip the legacy sweep, or one confirmation
    anywhere would make every other kit undeletable."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"event": "field_confirmed", "kit_id": "i-90", "field_id": "f1"},
    ])

    assert kit_has_confirmation_records("w7") is False


def test_the_legacy_scan_is_BOUNDED(monkeypatch):
    """Firestore cannot filter for a MISSING key, so this is a client-side
    scan. It must stay bounded, or a delete streams a large collection on a
    metered read path."""
    from backend.utils.confirmation_logger import (
        _LEGACY_SCAN_LIMIT, kit_has_confirmation_records,
    )

    # 500 fully-attributed records for other kits: none block, and the scan
    # must stop at the limit rather than reading them all.
    docs = [
        {"event": "field_confirmed", "kit_id": f"other-{i}", "field_id": "f"}
        for i in range(500)
    ]
    db = _firestore_with(monkeypatch, docs)

    assert kit_has_confirmation_records("w7") is False
    assert db._collection.streams[-1] == {
        "limit": _LEGACY_SCAN_LIMIT, "streamed": _LEGACY_SCAN_LIMIT,
    }


# --- session telemetry must never block a delete (bd polyglot-pdf-68s2q) -----
#
# bd polyglot-pdf-xwlt wired log_form_session_start/_end as live callers AND
# gave both events a kit_id. Two of this guard's three queries were unscoped,
# so those rows matched: ONE voice session made a kit permanently undeletable,
# and one session with a null kit_id made EVERY kit unverifiable. Reproduced
# by the outer cross-surface review against this very harness.


def test_a_session_event_with_a_kit_id_does_NOT_block_deletion(monkeypatch):
    """THE bug: a kit whose only records are session telemetry is deletable.

    Mutation: drop the `event == "field_confirmed"` filter (query on kit_id
    instead) -- red. This is the 68s2q reproduction, kept as a regression.
    """
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"event": "form_session_started", "kit_id": "w7", "form_session_id": "s1"},
        {"event": "form_session_ended", "kit_id": "w7", "form_session_id": "s1"},
    ])

    assert kit_has_confirmation_records("w7") is False, (
        "session telemetry is not evidence a client confirmed anything"
    )


def test_a_session_event_with_a_NULL_kit_id_does_not_make_every_kit_unverifiable(
    monkeypatch,
):
    """The worse half: a no-firm/no-kit session wrote kit_id as a STORED null,
    which tripped the unattributed-records refusal for EVERY kit queried --
    project-wide, from one session. Mutation: drop the event filter -- red
    (raises ConfirmationCheckUnavailable instead of returning False).
    """
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"event": "form_session_started", "kit_id": None, "form_session_id": "s1"},
    ])

    assert kit_has_confirmation_records("i-90") is False
    assert kit_has_confirmation_records("w7") is False


def test_a_REAL_confirmation_with_a_null_kit_id_still_blocks(monkeypatch):
    """The scoping must not weaken the guard it protects: an actual
    field_confirmed record naming no kit is still unattributable evidence and
    still refuses. Mutation: skip the client-side `record_kit is None` branch
    -- red."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    _firestore_with(monkeypatch, [
        {"event": "form_session_started", "kit_id": None, "form_session_id": "s1"},
        {"event": "field_confirmed", "kit_id": None, "field_id": "f1"},
    ])

    with pytest.raises(ConfirmationCheckUnavailable):
        kit_has_confirmation_records("w7")
