"""Guarded hard delete of a kit (bd polyglot-pdf-6x1j).

Deletion is the ONLY destructive operation in the editor API, and it takes the
revision archive with it -- the bytes bd polyglot-pdf-w3zw/xzw5 exist to keep
retrievable. So the guard, not the delete, is the feature -- but it GRADES rather than
blocks (bd polyglot-pdf-6zhaf). An absolute refusal turned out to be its own
bug: un-attributable legacy records made the check permanently unavailable, so
every kit became undeletable forever and the store filled with junk nobody
could clear. Risk decides how firmly the caller is asked, never whether the
door exists:

  never live, no records, VERIFIED  -> deleted
  never live, records OR unverified -> 409 DELETE_NEEDS_ACK
  EVER LIVE (any check result)      -> 409 DELETE_NEEDS_DOUBLE_ACK

Each refusal names the acknowledgement that clears it, and the two levels are
DISTINCT values on the wire -- the weaker one must not satisfy an ever-live
delete, or "double confirmation" lives only in the client and any direct API
call skips it.

Unverified still is not safe, which is why tier B exists at all. The
confirmation sink is Firestore, enabled only by the deploy env; with it off the
check falls back to a local JSONL file that dies with the instance. Treating
that silence as "no records" would let an author working locally destroy
evidence that exists -- so it warns, and says the cause is GLOBAL rather than
about the kit in front of them.
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


def test_an_EVER_LIVE_kit_needs_a_DOUBLE_ack(client, monkeypatch):
    """Tier C. A published kit may have been filled and agreed to, so the first
    attempt refuses -- but it refuses with a MARKER the client can act on, not
    a dead end (bd polyglot-pdf-6zhaf)."""
    c, _store, root = client
    _make_kit(root, "in-use", status="complete")
    _has_records(monkeypatch)

    resp = c.delete("/api/editor/kits/in-use", headers=AUTH)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail.startswith(ekr.DELETE_NEEDS_DOUBLE_ACK_PREFIX)
    assert "Unpublishing" in detail       # the safe alternative is still NAMED
    assert (root / "in-use" / "schema.json").exists()   # nothing removed

    # WHAT THE WARNING CLAIMS MUST BE TRUE. delete_kit removes only this kit's
    # own prefix; the confirmation records live in a separate Firestore
    # collection and survive. Saying "this deletes their agreement records"
    # would be false, and false warnings teach people to click through true
    # ones -- so pin that the copy says the accurate thing instead.
    assert "will survive" in detail
    assert "no longer be able to show what they agreed to" in detail


def test_an_EVER_LIVE_kit_IS_deletable_once_acknowledged(client, monkeypatch):
    """The half that makes this a safeguard rather than a wall. Nothing may be
    permanently invulnerable (maintainer, 2026-08-28)."""
    c, _store, root = client
    _make_kit(root, "in-use", status="complete")
    _has_records(monkeypatch)

    resp = c.delete(
        f"/api/editor/kits/in-use?acknowledged={ekr.ACK_UNDERSTOOD_PUBLISHED}",
        headers=AUTH)

    assert resp.status_code == 200, resp.text
    assert not (root / "in-use").exists()


def test_the_WEAKER_ack_does_NOT_clear_an_ever_live_delete(client, monkeypatch):
    """The two levels must be DISTINCT on the wire, or the "double" in double
    confirmation lives only in the client's checkbox and any direct API call
    skips it (fresh-eyes, bd polyglot-pdf-6zhaf). One boolean cannot express
    two levels -- that is exactly how the first cut of this got it wrong."""
    c, _store, root = client
    _make_kit(root, "in-use", status="complete")
    _has_records(monkeypatch)

    resp = c.delete(f"/api/editor/kits/in-use?acknowledged={ekr.ACK_UNDERSTOOD}",
                    headers=AUTH)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"].startswith(ekr.DELETE_NEEDS_DOUBLE_ACK_PREFIX)
    assert (root / "in-use" / "schema.json").exists()

    # And a junk value is not a skeleton key either.
    junk = c.delete("/api/editor/kits/in-use?acknowledged=true", headers=AUTH)
    assert junk.status_code == 409, junk.text
    assert (root / "in-use" / "schema.json").exists()


def test_a_kit_with_NO_metadata_is_tier_A_not_tier_C(client, monkeypatch):
    """ABSENT metadata is not UNREADABLE metadata.

    A kit with no metadata.json is a NORMAL shipped state (form-kits/w9-heldout
    is exactly that: a PDF and a note), and it has manifestly never been
    published -- there is no status to say so. The first cut of _kit_was_ever_live
    collapsed "no dict" into "assume the worst", which handed the scariest
    possible warning ("This form has been published") to precisely the
    junk-cleanup case this bead exists to unblock. Every fixture wrote a
    metadata.json, so nothing caught it (fresh-eyes round 2).
    """
    c, _store, root = client
    kit = root / "bare"
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    (kit / "form.pdf").write_bytes(b"%PDF-1.4 ")
    _no_records(monkeypatch)

    resp = c.delete("/api/editor/kits/bare", headers=AUTH)

    assert resp.status_code == 200, resp.text
    assert not (root / "bare").exists()


def test_metadata_that_is_PRESENT_but_unreadable_stays_strict(client, monkeypatch):
    """The other half. A metadata.json that exists and did not parse IS
    suspicious -- we cannot see a status, and something wrote that file. It
    keeps the strictest tier, so the absent-vs-unreadable distinction cannot be
    read as "unparseable is fine now"."""
    c, _store, root = client
    kit = root / "corrupt"
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    (kit / "metadata.json").write_text("{not json at all", encoding="utf-8")
    _no_records(monkeypatch)

    resp = c.delete("/api/editor/kits/corrupt", headers=AUTH)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"].startswith(ekr.DELETE_NEEDS_DOUBLE_ACK_PREFIX)


def test_a_RETIRED_kit_is_treated_as_ever_live(client, monkeypatch):
    """`unpublished` means a RETIRED FORMERLY-LIVE revision (bd 6dz0), NOT
    "never published" -- so it belongs in the STRICTEST tier despite the
    reassuring word. Reading the status string naively puts a form clients have
    seen on the light path, which is the exact inversion to guard against."""
    c, _store, root = client
    _make_kit(root, "retired", status="unpublished")
    _no_records(monkeypatch)      # even with a CLEAN check

    resp = c.delete("/api/editor/kits/retired", headers=AUTH)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"].startswith(ekr.DELETE_NEEDS_DOUBLE_ACK_PREFIX)


def test_a_kit_with_published_at_is_ever_live_whatever_its_status(client, monkeypatch):
    """The second half of the ever-live test. Status alone is not enough: a kit
    can carry published_at while reading `draft` (reopened after publication),
    and it has still been seen."""
    c, _store, root = client
    kit = root / "reopened"
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    (kit / "metadata.json").write_text(json.dumps({
        "status": "draft", "label": "Reopened",
        "published_at": "2026-08-01T00:00:00+00:00",
    }), encoding="utf-8")
    _no_records(monkeypatch)

    resp = c.delete("/api/editor/kits/reopened", headers=AUTH)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"].startswith(ekr.DELETE_NEEDS_DOUBLE_ACK_PREFIX)


def test_a_NEVER_LIVE_kit_WITH_records_needs_a_single_ack(client, monkeypatch):
    """Tier B. Never published, but someone filled it -- warn, do not block."""
    c, _store, root = client
    _make_kit(root, "draft-but-filled", status="draft")
    _has_records(monkeypatch)

    resp = c.delete("/api/editor/kits/draft-but-filled", headers=AUTH)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail.startswith(ekr.DELETE_NEEDS_ACK_PREFIX)
    assert "confirmation records" in detail

    ok = c.delete(
        f"/api/editor/kits/draft-but-filled?acknowledged={ekr.ACK_UNDERSTOOD}",
        headers=AUTH)
    assert ok.status_code == 200, ok.text
    assert not (root / "draft-but-filled").exists()


def test_an_UNVERIFIABLE_never_live_kit_warns_then_deletes(client, monkeypatch):
    """THE BUG THIS BEAD EXISTS FOR. Un-attributable legacy records make the
    check permanently unavailable, so under the old rule EVERY kit was
    undeletable forever and the store filled with junk nobody could clear.

    Unverified still is not the same as safe -- the sink can be disabled, and a
    local instance reading an empty JSONL would otherwise conclude "no records".
    So it warns, names what it could not check, and lets an author through."""
    c, _store, root = client
    _make_kit(root, "unknown-history", status="draft")
    _cannot_check(monkeypatch)

    resp = c.delete("/api/editor/kits/unknown-history", headers=AUTH)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail.startswith(ekr.DELETE_NEEDS_ACK_PREFIX)
    # It names the REASON it could not check, rather than implying something
    # about this kit specifically -- the old message read as a per-kit verdict
    # when the cause was global, which is why the maintainer tried other forms.
    # The cause is GLOBAL. The old message read as a verdict on this kit, which
    # is why the maintainer worked through every form in the catalogue looking
    # for one that would delete -- so the wording must say so, and must NOT
    # echo the raw exception ("...so THIS KIT cannot be cleared"), which would
    # relocate the same bug into a parenthetical.
    assert "not specific to this one" in detail
    assert "cannot be cleared for deletion" not in detail
    assert (root / "unknown-history" / "schema.json").exists()

    ok = c.delete(
        f"/api/editor/kits/unknown-history?acknowledged={ekr.ACK_UNDERSTOOD}",
        headers=AUTH)
    assert ok.status_code == 200, ok.text
    assert not (root / "unknown-history").exists()


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


def test_a_delete_RACE_404s_by_the_kits_NAME_not_its_folder(client, monkeypatch):
    """The kit passed every guard and was gone by the write -- someone else
    deleted it in between (bd polyglot-pdf-ytd3m).

    The author is looking at a card that still shows the kit's LABEL, so a
    refusal naming only the folder id cannot be matched to anything on screen
    -- the exact complaint bd kztlr fixed everywhere else in this route. The
    label computed at the top of the request describes what the kit WAS a
    moment ago, which is what this message should say.

    NOTE THE FIXTURE. _make_kit writes label == kit_id, and _kit_name treats
    that as a restatement and returns the bare id -- so a test built on it
    would produce byte-identical output fixed or broken. The label here differs
    from the folder deliberately; six tests passed on that coincidence in bd
    n5fwd.
    """
    c, store, root = client
    kit = _make_kit(root, "form-2")
    (kit / "metadata.json").write_text(
        json.dumps({"status": "draft", "label": "W-7"}), encoding="utf-8"
    )
    _no_records(monkeypatch)

    # Vanishes between the guards and the write, which is what a race IS.
    async def _gone(_kit_id):
        from backend.services.form_kits import FormKitNotFound
        raise FormKitNotFound("deleted by someone else")

    monkeypatch.setattr(store, "delete_kit", _gone)

    resp = c.delete("/api/editor/kits/form-2", headers=AUTH)

    assert resp.status_code == 404, resp.text
    detail = resp.json()["detail"]
    # BOTH identities: the label matches the card, the id is what the delete
    # dialog made them type. Naming only one leaves the other unresolvable.
    assert "W-7" in detail
    assert "form-2" in detail


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
    """A fake query supporting CHAINED equality filters.

    Chaining is not a nicety: the guard now filters on kit_id AND event
    together (two equality filters, which Firestore serves by merging
    single-field indexes). A fake that honored only the last filter would
    model a query the production code does not make -- and would have hidden
    the sampling regression this chaining fixes (bd polyglot-pdf-u66ka).
    """

    def __init__(self, docs, filters=None, limit=None, sink=None, calls=None):
        self._docs = docs
        self._filters = list(filters or [])   # [(field, value, op), ...]
        self._limit = limit
        self._sink = sink
        self._calls = calls

    def where(self, *args, **kwargs):
        flt = kwargs.get("filter")
        if flt is not None:
            field, op, value = flt.field_path, flt.op_string, flt.value
        else:
            field, op, value = args[0], args[1], args[2]
        if self._calls is not None:
            # Record CHAINED filters as well as the first: the event scope is
            # applied second, and it is exactly the property that must never
            # drift (bd polyglot-pdf-68s2q).
            self._calls.append((field, getattr(op, "name", None) or str(op), value))
        return _FilteringQuery(
            self._docs, self._filters + [(field, value, op)], self._limit,
            self._sink, self._calls,
        )

    def limit(self, n):
        return _FilteringQuery(
            self._docs, self._filters, n, self._sink, self._calls
        )

    @staticmethod
    def _match_one(d, field, value, op):
        # Mirror the SDK's resolved semantics: IS_NULL matches a STORED null
        # and not a missing key; IS_NOT_NULL is its complement.
        opname = getattr(op, "name", None) or str(op or "")
        if "IS_NOT_NULL" in opname:
            return field in d and d[field] is not None
        if "IS_NULL" in opname:
            return field in d and d[field] is None
        return field in d and d[field] == value

    def _match(self, d):
        return all(self._match_one(d, f, v, o) for f, v, o in self._filters)

    def stream(self):
        matched = [d for d in self._docs if self._match(d)]
        if self._limit is not None:
            matched = matched[:self._limit]
        # `streamed` counts documents the caller actually CONSUMED, not the
        # batch size: a caller that breaks early reads fewer, and on a metered
        # path that difference is the whole point.
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
        return _FilteringQuery(
            self.docs, [(field, value, op)], sink=self.streams, calls=self.where_calls
        )


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
    # BOTH filters server-side, as one chained equality query (bd
    # polyglot-pdf-xwlt / 68s2q / u66ka). The kit scope alone matched session
    # telemetry once those events carried a kit_id; the event scope ALONE
    # (with kit_id compared client-side over a bounded stream) turned this
    # into an arbitrary 50-doc sample that could miss a real record and
    # permit a delete. Two equality filters need no composite index --
    # Firestore merges single-field indexes -- so the query stays exhaustive
    # with limit(1) bounding only the RESULT.
    assert db._collection.where_calls == [
        ("kit_id", "==", "w7"),
        ("event", "==", "field_confirmed"),
    ]


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
    """Existence is a yes/no, so limit(1) is what stops a popular kit's whole
    confirmation history streaming on a metered read path -- while the SEARCH
    stays exhaustive (limit bounds the result, not the scan), so a record far
    down the collection is still found (bd polyglot-pdf-u66ka).

    Asserts the SHAPE the query asked for, recorded by the fake. An earlier
    version tried to wrap stream() after the fact and silently measured
    nothing -- dropping the limit left it green (caught by re-running the
    mutation rather than trusting the pass)."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    docs = [{"event": "field_confirmed", "kit_id": "w7", "field_id": f"f{i}"}
            for i in range(50)]
    db = _firestore_with(monkeypatch, docs)

    assert kit_has_confirmation_records("w7") is True

    assert db._collection.streams == [{"limit": 1, "streamed": 1}], (
        "the existence check must ask for at most one document"
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

    # PIN THE OPERATOR. The SDK resolves ("kit_id","==",None) to a
    # UnaryFilter(IS_NULL); the INVERSE (IS_NOT_NULL) matches every record
    # that HAS a kit_id and would make every kit permanently undeletable --
    # a value-only assertion cannot tell the two apart (Opus fresh-eyes round
    # 3 proved that inversion kept all 31 tests green). The null check is
    # ALSO event-scoped, or session telemetry trips it (bd 68s2q).
    assert ("kit_id", "IS_NULL", None) in db._collection.where_calls
    assert ("event", "==", "field_confirmed") in db._collection.where_calls


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

    # Both exhaustive checks ran, and NEITHER streamed more than one document.
    assert db._collection.streams[:2] == [
        {"limit": 1, "streamed": 0},   # kit-scoped: no record names w7
        {"limit": 1, "streamed": 1},   # the null check: found one unattributed
    ]


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


def test_a_confirmation_BEYOND_the_scan_window_is_still_found(monkeypatch):
    """THE regression the sampling bug shipped past (bd polyglot-pdf-u66ka).

    The positive check must be EXHAUSTIVE. When it briefly filtered only on
    the event and compared kit_id client-side over a _LEGACY_SCAN_LIMIT
    stream, a kit whose confirmation sat past document 50 answered "no
    records" -- and the delete route then hard-deleted the kit AND its
    revision archive. That is the evidence-destroying direction: the guard
    exists precisely to prevent it.

    One field_confirmed doc is written per FIELD, so 50 documents is roughly
    one or two filled forms -- this is reachable on any real collection, not
    a theoretical edge.

    Mutation: drop the kit_id filter and compare client-side over a bounded
    stream (the u66ka shape) -- red.
    """
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    docs = [
        {"event": "field_confirmed", "kit_id": "i-90", "field_id": f"f{i}"}
        for i in range(80)
    ]
    docs.append({"event": "field_confirmed", "kit_id": "w7", "field_id": "late"})
    _firestore_with(monkeypatch, docs)

    assert kit_has_confirmation_records("w7") is True, (
        "the kit match must be exhaustive -- limit(1) bounds the RESULT, "
        "never the search"
    )


def test_an_unattributed_record_BEYOND_the_window_still_blocks(monkeypatch):
    """The same exhaustiveness for the stored-null refusal: a real
    confirmation naming no kit is unattributable evidence wherever it sits.
    Mutation: bound the null check with _LEGACY_SCAN_LIMIT -- red."""
    from backend.utils.confirmation_logger import kit_has_confirmation_records

    docs = [
        {"event": "field_confirmed", "kit_id": "i-90", "field_id": f"f{i}"}
        for i in range(80)
    ]
    docs.append({"event": "field_confirmed", "kit_id": None, "field_id": "late"})
    _firestore_with(monkeypatch, docs)

    with pytest.raises(ConfirmationCheckUnavailable):
        kit_has_confirmation_records("w7")
