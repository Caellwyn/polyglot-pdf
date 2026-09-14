"""Draft saves are recoverable (bd polyglot-pdf-y2l0p).

MAINTAINER PRINCIPLE, 2026-08-08: "Editors should not ever be able to make
destructive actions. Their work should always be recoverable."

The gap this closes: PUT /schema is editor-gated and called put_schema
directly. The write-lock refuses only a COMPLETE or UNPUBLISHED kit, so a
published revision was protected and a DRAFT was overwritten in place with no
copy anywhere. Editor A spends hours on a draft; editor B -- or A, from a stale
tab -- saves over it, and the earlier contents are gone. The in-editor undo
stack does not help: it is cleared on load, so it never survives a reload and
never covered a cross-session overwrite.

These tests drive the bead's three exit criteria: recover a schema after it is
overwritten, prove the same behaviour in both stores, and prove draft snapshots
never touch the revision archive's keyspace.
"""
import asyncio
import json
import pathlib
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
from backend.services.form_kits import (
    DRAFT_SNAPSHOT_LIMIT,
    FormKitNotFound,
    FormKitStoreError,
    LocalFormKitStore,
)

from backend.tests.unit.test_editor_kit_routes import VALID_SCHEMA as _SCHEMA


def _run(coro):
    return asyncio.run(coro)


def _schema(tag):
    s = json.loads(json.dumps(_SCHEMA))
    s["_tag"] = tag  # a marker so we can tell revisions apart
    return s


def _make_kit(root, kit_id, status="draft", schema=None):
    kit = root / kit_id
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(
        json.dumps(schema if schema is not None else _SCHEMA), encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps({"status": status, "label": kit_id}), encoding="utf-8")
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
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok"))
    return TestClient(app), store, tmp_path


EDIT = {"X-Editor-Token": "edit-tok"}
AUTH = {"X-Editor-Token": "auth-tok"}


def _save(c, kit_id, schema, headers=EDIT):
    return c.put(f"/api/editor/kits/{kit_id}/schema", json=schema, headers=headers)


def _snapshots(c, kit_id, headers=EDIT):
    return c.get(f"/api/editor/kits/{kit_id}/draft-snapshots", headers=headers)


def _restore(c, kit_id, snap_id, headers=EDIT):
    return c.post(
        f"/api/editor/kits/{kit_id}/draft-snapshots/{snap_id}/restore", headers=headers)


# --- exit criterion 1: the overwritten contents are still retrievable --------


def test_an_overwritten_draft_is_RECOVERABLE(client):
    """The bead's scenario, end to end: save A, save B over it, recover A."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))

    assert _save(c, "w7", _schema("B")).status_code == 200

    snaps = _snapshots(c, "w7").json()["snapshots"]
    assert len(snaps) == 1, "the overwritten draft was not snapshotted"

    recovered = _run(store.load_draft_snapshot("w7", snaps[0]["id"]))
    assert recovered["_tag"] == "A"


def test_restoring_puts_the_earlier_work_BACK(client):
    """A snapshot nobody can restore is not recovery."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))

    snaps = _snapshots(c, "w7").json()["snapshots"]
    resp = _restore(c, "w7", snaps[0]["id"])

    assert resp.status_code == 200, resp.text
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "A"


def test_a_RESTORE_is_itself_undoable(client):
    """Restoring overwrites current work, so it snapshots that work first --
    which is what makes it safe to let an editor restore without an author."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))  # snapshot 1 holds A, live is B

    snaps = _snapshots(c, "w7").json()["snapshots"]
    resp = _restore(c, "w7", snaps[0]["id"])  # live becomes A again

    replaced = resp.json()["snapshotOfReplaced"]
    assert replaced, "restoring did not snapshot the work it replaced"
    assert _run(store.load_draft_snapshot("w7", replaced))["_tag"] == "B"


def test_the_FIRST_save_of_a_new_kit_snapshots_nothing(client):
    """There is no prior work to protect, and an empty snapshot would just be
    noise in the recovery list."""
    c, _store, root = client
    kit = root / "fresh"
    kit.mkdir()
    (kit / "metadata.json").write_text(
        json.dumps({"status": "draft", "label": "fresh"}), encoding="utf-8")
    (kit / "form.pdf").write_bytes(b"%PDF-1.7")

    assert _save(c, "fresh", _schema("A")).status_code == 200

    assert _snapshots(c, "fresh").json()["snapshots"] == []


# --- the ring is bounded ----------------------------------------------------


def test_the_ring_keeps_the_LAST_N_and_evicts_the_oldest(client):
    """Maintainer decision 2026-08-18: keep the last 10 saves. Bounded, so a
    busy kit cannot grow storage without limit."""
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("v0"))
    for i in range(1, DRAFT_SNAPSHOT_LIMIT + 4):
        _save(c, "w7", _schema(f"v{i}"))

    snaps = _snapshots(c, "w7").json()["snapshots"]

    assert len(snaps) == DRAFT_SNAPSHOT_LIMIT


def test_snapshots_are_listed_NEWEST_first(client):
    """The order someone recovering work reads them in."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))
    _save(c, "w7", _schema("C"))

    snaps = _snapshots(c, "w7").json()["snapshots"]

    # Two snapshots: A (from the B save) then B (from the C save). Newest
    # first means B leads.
    assert [_run(store.load_draft_snapshot("w7", s["id"]))["_tag"] for s in snaps] \
        == ["B", "A"]


def test_snapshot_ids_sort_NUMERICALLY_past_single_digits(client):
    """"10" must follow "9", not sort beside "1" -- a lexical sort evicts the
    wrong snapshot the moment the ring passes ten."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("v0"))
    for i in range(1, 12):
        _save(c, "w7", _schema(f"v{i}"))

    snaps = _snapshots(c, "w7").json()["snapshots"]
    ids = [int(s["id"]) for s in snaps]

    assert ids == sorted(ids, reverse=True)
    assert max(ids) == 11


# --- exit criterion 3: the revision archive is untouched --------------------


def test_draft_snapshots_NEVER_land_in_the_revision_archive(client):
    """The archive is keyed on the revision marker a confirmation record names
    (bd polyglot-pdf-w3zw/xzw5). A draft has no marker, and polluting that
    keyspace would break retrieval by marker."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    before = _run(store.list_archived_markers("w7"))

    for tag in ("B", "C", "D"):
        _save(c, "w7", _schema(tag))

    assert _run(store.list_archived_markers("w7")) == before == []
    # ...and the snapshots live in their own directory.
    assert (root / "w7" / "_drafts").exists()
    assert not (root / "w7" / "_archive").exists()


def test_snapshots_do_not_appear_as_KITS(client):
    """The underscore prefix keeps them invisible to the catalogue, the same
    way _archive is invisible."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))

    listed = _run(store.list_kit_files())

    assert "_drafts" not in listed
    assert set(listed) == {"w7"}
    # The assertion that actually binds: _drafts is nested INSIDE w7, so it
    # could never be a top-level key -- the two lines above are true no matter
    # what. The property the docstring claims is enforced by list_kit_files'
    # is_file() filter, so assert on w7's own FILE LIST (Opus round 3).
    assert "_drafts" not in listed["w7"]


# --- who may recover --------------------------------------------------------


def test_an_EDITOR_can_list_and_restore_their_own_work(client):
    """Maintainer decision 2026-08-18. Routing recovery through an author means
    the person who lost the work cannot get it back themselves."""
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))

    snaps = _snapshots(c, "w7", headers=EDIT)
    assert snaps.status_code == 200, snaps.text
    assert _restore(c, "w7", snaps.json()["snapshots"][0]["id"],
                    headers=EDIT).status_code == 200


def test_an_AUTHOR_can_too(client):
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))

    snaps = _snapshots(c, "w7", headers=AUTH)
    assert snaps.status_code == 200
    assert _restore(c, "w7", snaps.json()["snapshots"][0]["id"],
                    headers=AUTH).status_code == 200


def test_an_unauthenticated_caller_gets_nothing(client):
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))

    assert c.get("/api/editor/kits/w7/draft-snapshots").status_code in (401, 403)


# --- restore respects the same locks a save does ----------------------------


# The FULL write-locked set, derived rather than retyped. Narrowing the route
# guard to ("complete", "unpublished") -- dropping `submitted` -- left 204 tests
# passing, and `submitted` is the one status whose whole point is that an author
# reviews one thing and approves that same thing (Opus fresh-eyes round 2).
@pytest.mark.parametrize("status", list(ekr._WRITE_LOCKED_STATUSES))
def test_restore_is_REFUSED_on_a_write_locked_kit(client, status):
    """A published revision is what confirmation records name; reopening it
    goes through the explicit revert-to-draft, never a side door."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))
    snaps = _snapshots(c, "w7").json()["snapshots"]
    # Lock it AFTER the snapshot exists.
    (root / "w7" / "metadata.json").write_text(
        json.dumps({"status": status, "label": "w7"}), encoding="utf-8")

    resp = _restore(c, "w7", snaps[0]["id"])

    assert resp.status_code == 409, resp.text
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "B"


def test_a_TRAVERSING_snapshot_id_is_refused(client):
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))

    # ".." never reaches the route -- the router resolves it as a path segment
    # and 404s first, so asserting 400 there would be testing routing, not the
    # guard. Values that DO arrive intact must be refused with 400.
    for bad in ("1abc", "1/2", "-1", "1.5", ""):
        resp = _restore(c, "w7", bad)
        assert resp.status_code in (400, 404, 405), f"{bad!r} -> {resp.status_code}"
    # The one that proves the guard itself, not the router: a well-formed
    # segment that is simply not a snapshot id.
    assert _restore(c, "w7", "1abc").status_code == 400


def test_load_draft_snapshot_ITSELF_refuses_a_traversing_id(client, tmp_path):
    """bd polyglot-pdf-xddtl: the ROUTE's guard is not the only caller this
    store method will ever have. Drive the store directly, bypassing the
    route/router entirely -- a `..` segment never reaches FastAPI's router as
    a literal string (it resolves the path first), so this is the only way to
    exercise what load_draft_snapshot itself does with one.

    A real escape, reproduced before this bead's fix landed: a sibling
    directory outside the kit's own tree, read back via
    load_draft_snapshot('w7', '../../../outside_secret'). Three levels, not
    two: the real path being escaped is
    <root>/w7/_drafts/<snapshot_id>/schema.json, so climbing out to a sibling
    of <root> itself takes _drafts -> w7 -> root -- three hops."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))

    outside = tmp_path.parent / "outside_secret"
    outside.mkdir(exist_ok=True)
    (outside / "schema.json").write_text(json.dumps({"pwn": True}), encoding="utf-8")

    for bad in ("../../../outside_secret", "1abc", "1/2", "-1", "1.5", ""):
        with pytest.raises(FormKitNotFound):
            _run(store.load_draft_snapshot("w7", bad))


def test_an_unknown_snapshot_404s(client):
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))

    assert _restore(c, "w7", "999").status_code == 404


# --- the save must not be blocked by snapshot trouble -----------------------


def test_a_snapshot_failure_does_NOT_block_the_save(client, monkeypatch):
    """The editor's CURRENT work is what matters most. Refusing to save in
    order to protect an older copy inverts the priority."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))

    from backend.services.form_kits import FormKitStoreError

    async def _boom(*_a, **_kw):
        raise FormKitStoreError("snapshot store down")

    monkeypatch.setattr(store, "put_draft_snapshot", _boom)

    assert _save(c, "w7", _schema("B")).status_code == 200
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "B"


def test_a_failed_pre_restore_snapshot_REFUSES_the_restore(client, monkeypatch):
    """The opposite call, and deliberately so: a restore knowingly destroys the
    current draft, so failing to protect it first must stop the restore. A
    recovery feature that loses work is worse than one that declines."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))
    snaps = _snapshots(c, "w7").json()["snapshots"]

    from backend.services.form_kits import FormKitStoreError

    async def _boom(*_a, **_kw):
        raise FormKitStoreError("snapshot store down")

    monkeypatch.setattr(store, "put_draft_snapshot", _boom)

    resp = _restore(c, "w7", snaps[0]["id"])

    assert resp.status_code == 502, resp.text
    assert "Nothing was changed" in resp.json()["detail"]
    # The live schema is untouched.
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "B"


# --- exit criterion 2: the SAME behaviour in GCS ----------------------------
#
# Written after the local-only version of this file passed while the GCS ring
# was INERT: _build_blob_path drops an empty part, so the listing prefix lost
# its trailing slash, no snapshot id ever parsed, and every save overwrote
# snapshot 1 while listing returned nothing. In the deployed mode the feature
# kept no history at all (Opus fresh-eyes round 1).
#
# Criterion 2 asks for recovery "in GCS and local-folder mode". A test that
# only drives the local store cannot answer it, and the store that ships is the
# one that was broken.

from backend.tests.unit.test_editor_kit_routes import _gcs_store


def test_GCS_snapshots_get_distinct_ids(client_unused=None):
    """The bug in one assertion: ids must advance, not stay at 1."""
    registry = {}
    store = _gcs_store(registry)

    ids = [_run(store.put_draft_snapshot("w7", {"_tag": f"v{i}"})) for i in range(3)]

    assert ids == ["1", "2", "3"], f"ids did not advance: {ids}"


def test_GCS_recovers_an_overwritten_draft():
    """Criterion 1's scenario, driven against the store that ships."""
    registry = {}
    store = _gcs_store(registry)
    _run(store.put_draft_snapshot("w7", {"_tag": "A"}))
    _run(store.put_draft_snapshot("w7", {"_tag": "B"}))

    snaps = _run(store.list_draft_snapshots("w7"))

    assert [s["id"] for s in snaps] == ["2", "1"], "newest-first listing broken"
    assert _run(store.load_draft_snapshot("w7", "1"))["_tag"] == "A"
    assert _run(store.load_draft_snapshot("w7", "2"))["_tag"] == "B"


def test_GCS_lists_nothing_for_a_kit_with_no_snapshots():
    registry = {}
    store = _gcs_store(registry)

    assert _run(store.list_draft_snapshots("w7")) == []


def test_GCS_evicts_only_the_OLDEST_not_its_prefix_matches():
    """The destructive half of the same bug: without a trailing slash the
    eviction prefix '<kit>/_drafts/1' string-matches 10, 11, 12... so evicting
    snapshot 1 would delete most of the ring the moment it passed ten."""
    registry = {}
    store = _gcs_store(registry)
    for i in range(DRAFT_SNAPSHOT_LIMIT + 2):
        _run(store.put_draft_snapshot("w7", {"_tag": f"v{i}"}))

    snaps = _run(store.list_draft_snapshots("w7"))
    ids = sorted(int(s["id"]) for s in snaps)

    assert len(snaps) == DRAFT_SNAPSHOT_LIMIT
    # A contiguous run ending at the newest: 3..12 for a limit of 10 after 12
    # saves. A prefix over-match would punch holes (10, 11, 12 gone).
    assert ids == list(range(ids[0], ids[0] + DRAFT_SNAPSHOT_LIMIT)), ids
    assert max(ids) == DRAFT_SNAPSHOT_LIMIT + 2


def test_GCS_snapshots_land_outside_the_revision_archive():
    """Criterion 3, in the store that ships."""
    registry = {}
    store = _gcs_store(registry)
    _run(store.put_draft_snapshot("w7", {"_tag": "A"}))

    keys = list(registry)

    assert any("/_drafts/" in k for k in keys)
    assert not any("/_archive/" in k for k in keys)


def test_GCS_load_of_a_missing_snapshot_raises_NotFound():
    from backend.services.form_kits import FormKitNotFound

    registry = {}
    store = _gcs_store(registry)

    with pytest.raises(FormKitNotFound):
        _run(store.load_draft_snapshot("w7", "999"))


def test_GCS_load_draft_snapshot_ITSELF_refuses_a_traversing_id():
    """bd polyglot-pdf-xddtl's GCS twin. _build_blob_path just joins its
    parts with "/" -- blob names are flat strings with no path-resolution
    semantics, so a ".."-bearing snapshot_id does not climb anywhere; it
    becomes a literal substring of the constructed blob name. The registry
    key below is that literal construction -- "form-kits/w7/_drafts/../other-
    firms-kit/schema.json", NOT a resolved "form-kits/other-firms-kit/..." --
    because a real fake-GCS backend does exactly this flat string match, and
    proving the guard matters means proving this exact literal would
    otherwise resolve to a real blob."""
    injected_path = "form-kits/w7/_drafts/../other-firms-kit/schema.json"
    registry = {injected_path: {"data": json.dumps({"pwn": True})}}
    store = _gcs_store(registry)

    for bad in ("../other-firms-kit", "1abc", "1/2", "-1", "1.5", ""):
        with pytest.raises(FormKitNotFound):
            _run(store.load_draft_snapshot("w7", bad))


# --- the guards that had no test --------------------------------------------


def test_a_UNICODE_digit_directory_does_not_break_the_save(client):
    """str.isdigit() is True for superscript/circled digits that int() then
    REJECTS -- so a stray directory named "\u00b9" crashed the sort with a
    ValueError, escaped the OSError wrap, and 500'd the SAVE, losing the
    editor's current work. The exact harm this feature exists to prevent,
    triggered by a directory name (Opus fresh-eyes round 2).
    """
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    (root / "w7" / "_drafts" / "\u00b9").mkdir(parents=True)

    resp = _save(c, "w7", _schema("B"))

    assert resp.status_code == 200, resp.text
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "B"


def test_a_UNICODE_digit_snapshot_id_is_refused_by_the_route(client):
    """The same mismatch at the route guard: isdigit() alone would let it
    through to a store that cannot parse it."""
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))

    assert _restore(c, "w7", "\u00b9").status_code == 400


def test_an_unreadable_drafts_dir_does_not_block_the_SAVE(client):
    """The best-effort contract, pinned. _snapshot_ids raising a raw OSError
    would escape the route's `except FormKitStoreError` and 500 the save --
    the round-1 fix for that had no test, so replacing the wrap with a bare
    re-raise left 529 tests passing."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    # _drafts as a FILE, so iterdir() raises NotADirectoryError.
    (root / "w7" / "_drafts").write_text("not a directory", encoding="utf-8")

    resp = _save(c, "w7", _schema("B"))

    assert resp.status_code == 200, resp.text
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "B"


def test_an_unreadable_drafts_dir_surfaces_on_the_LIST(client):
    """The other half: the save must survive, but LISTING must not silently
    report "no earlier versions" when it could not look."""
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    (root / "w7" / "_drafts").write_text("not a directory", encoding="utf-8")

    assert _snapshots(c, "w7").status_code == 502


# --- the guards that had no test (Opus fresh-eyes round 3) -------------------


def test_restore_honours_a_kit_s_OWN_schema_filename(client):
    """A kit may name its own schema file (bd polyglot-pdf-snpi). Hardcoding
    "schema.json" in the restore route left every test green while producing a
    SILENT FALSE SUCCESS: HTTP 200, the real file still holding the overwritten
    work, and a stray schema.json written beside it. The editor is told their
    work came back when it did not."""
    c, store, root = client
    kit = root / "i90"
    kit.mkdir()
    (kit / "i90.json").write_text(json.dumps(_schema("A")), encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps({"status": "draft", "label": "i90", "schema": "i90.json"}),
        encoding="utf-8")
    (kit / "form.pdf").write_bytes(b"%PDF-1.7")

    assert _save(c, "i90", _schema("B")).status_code == 200
    snaps = _snapshots(c, "i90").json()["snapshots"]
    assert _restore(c, "i90", snaps[0]["id"]).status_code == 200

    assert _run(store.load_schema("i90", "i90.json"))["_tag"] == "A"
    # ...and nothing was written under the conventional name.
    assert not (kit / "schema.json").exists()


def test_restore_honours_the_EDITING_LOCK(client):
    """An author who took the kit back is mid-review; a restore from under them
    means they approve something they never saw. The guard was reachable and
    correct but entirely unpinned -- deleting the call left all 29 tests
    passing, and its own docstring records this guard being missed on a sibling
    route twice before."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))
    snaps = _snapshots(c, "w7").json()["snapshots"]
    # An AUTHOR takes the kit for review.
    (root / "w7" / "metadata.json").write_text(
        json.dumps({"status": "draft", "label": "w7",
                    "editing_lock": {"role": "author"}}), encoding="utf-8")

    resp = _restore(c, "w7", snaps[0]["id"], headers=EDIT)

    assert resp.status_code == 409, resp.text
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "B"


def test_savedAt_is_a_real_timestamp_not_null(client):
    """The only field distinguishing snapshots in a recovery UI -- the ids are
    bare counters. Four separate mutations (forcing None in each store, and
    skipping the meta.json write in each) all survived."""
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))

    snaps = _snapshots(c, "w7").json()["snapshots"]

    stamp = snaps[0]["savedAt"]
    assert stamp, "savedAt was null -- a recovery list of bare counters"
    parsed = datetime.fromisoformat(stamp)
    assert parsed.tzinfo is not None, "savedAt must carry a timezone"


def test_GCS_savedAt_is_a_real_timestamp_too():
    """The store that ships, held to the same contract."""
    registry = {}
    store = _gcs_store(registry)
    _run(store.put_draft_snapshot("w7", {"_tag": "A"}))

    snaps = _run(store.list_draft_snapshots("w7"))

    assert snaps[0]["savedAt"]
    assert datetime.fromisoformat(snaps[0]["savedAt"]).tzinfo is not None


def test_GCS_skips_a_unicode_digit_blob_instead_of_going_blind():
    """Round 2 added the isascii guard to all three sites but pinned only the
    local store and the route. On the GCS side the failure is quieter and
    worse: _snapshot_ids wraps bare Exception, so a unicode-digit blob turns
    every call into FormKitStoreError -- which the save path SWALLOWS as
    best-effort, so the deployed ring silently stops snapshotting entirely."""
    registry = {"form-kits/w7/_drafts/\u00b9/schema.json": {"data": "{}"}}
    store = _gcs_store(registry)

    assert _run(store._snapshot_ids("w7")) == []
    # ...and snapshotting still works rather than erroring out.
    assert _run(store.put_draft_snapshot("w7", {"_tag": "A"})) == "1"


@pytest.fixture()
def gcs_client(monkeypatch):
    """The REAL routes over the GCS store -- the one that ships.

    The earlier version of the end-to-end test hand-replicated the route's
    sequence (snapshot, overwrite, snapshot, restore) against the store
    primitives. That attests to the STORE, not to the RESTORE, so a route-level
    regression that only bites GCS could not redden it -- precisely the round-1
    miss shape, where the local suite stayed green while the GCS ring was
    inert. Criterion 2 says "the same RESTORE exercised against BOTH store
    implementations", so drive the routes (Opus fresh-eyes round 4).
    """
    from backend.tests.unit.test_editor_kit_routes import _settings

    app = FastAPI()
    app.include_router(ekr.router)
    registry = {}
    store = _gcs_store(registry)
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok"))
    return TestClient(app), store, registry


def _seed_gcs_kit(store, registry, kit_id="w7", schema=None):
    _run(store.put_schema(kit_id, schema if schema is not None else _schema("A")))
    _run(store.put_metadata(kit_id, {"status": "draft", "label": kit_id}))
    registry[f"form-kits/{kit_id}/form.pdf"] = {"data": "%PDF-1.7"}


def test_GCS_restore_works_end_to_end_THROUGH_THE_ROUTES(gcs_client):
    """Criterion 2, driven the way an editor actually drives it."""
    c, store, registry = gcs_client
    _seed_gcs_kit(store, registry, schema=_schema("A"))

    assert _save(c, "w7", _schema("B")).status_code == 200

    snaps = _snapshots(c, "w7").json()["snapshots"]
    assert len(snaps) == 1, "the overwritten draft was not snapshotted in GCS"

    resp = _restore(c, "w7", snaps[0]["id"])

    assert resp.status_code == 200, resp.text
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "A"
    # The restore protected the work it replaced, in GCS too.
    assert _run(store.load_draft_snapshot(
        "w7", resp.json()["snapshotOfReplaced"]))["_tag"] == "B"


def test_GCS_restore_honours_a_kit_s_OWN_schema_filename(gcs_client):
    """The silent-false-success from round 3, pinned on the deployed store."""
    c, store, registry = gcs_client
    _run(store.put_schema("i90", _schema("A"), "i90.json"))
    _run(store.put_metadata(
        "i90", {"status": "draft", "label": "i90", "schema": "i90.json"}))
    registry["form-kits/i90/form.pdf"] = {"data": "%PDF"}

    assert _save(c, "i90", _schema("B")).status_code == 200
    snaps = _snapshots(c, "i90").json()["snapshots"]
    assert _restore(c, "i90", snaps[0]["id"]).status_code == 200

    assert _run(store.load_schema("i90", "i90.json"))["_tag"] == "A"


def test_GCS_restore_is_REFUSED_on_a_write_locked_kit(gcs_client):
    """The write-lock, on the store that ships."""
    c, store, registry = gcs_client
    _seed_gcs_kit(store, registry, schema=_schema("A"))
    _save(c, "w7", _schema("B"))
    snaps = _snapshots(c, "w7").json()["snapshots"]
    _run(store.put_metadata("w7", {"status": "complete", "label": "w7"}))

    assert _restore(c, "w7", snaps[0]["id"]).status_code == 409
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "B"


# --- the last unpinned guards -----------------------------------------------


def test_listing_an_UNKNOWN_kit_is_404_not_an_empty_list(client):
    """"You have no earlier versions" and "that form does not exist" are
    different answers. Deleting the existence check left all 35 tests green
    while turning the 404 into 200 {"snapshots": []} -- the false-negative
    direction in a recovery feature (Opus fresh-eyes round 4)."""
    c, _store, _root = client

    assert _snapshots(c, "nosuchkit").status_code == 404


def test_a_CORRUPT_stamp_does_not_hide_the_snapshot(client):
    """meta.json holding valid JSON that is not an OBJECT has no .get, and the
    AttributeError escaped to a 500 on the LIST route -- unreachable recovery
    from a one-byte corruption in a metadata file, while GCS returned 200 with
    a null stamp. The code contradicted its own comment."""
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))
    (root / "w7" / "_drafts" / "1" / "meta.json").write_text(
        json.dumps(["corrupt"]), encoding="utf-8")

    resp = _snapshots(c, "w7")

    assert resp.status_code == 200, resp.text
    snaps = resp.json()["snapshots"]
    assert len(snaps) == 1, "a corrupt stamp hid the snapshot itself"
    assert snaps[0]["savedAt"] is None


def test_a_NON_UTF8_snapshot_fails_as_a_STORAGE_fault_not_a_crash(client):
    """UnicodeDecodeError is a ValueError, not an OSError, so it escaped the
    wrap and 500'd the restore while the GCS twin raised FormKitStoreError ->
    502. Every sibling reader in the class already caught it."""
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))
    (root / "w7" / "_drafts" / "1" / "schema.json").write_bytes(bytes([0xff, 0xfe, 0x00]) + b"bad")

    assert _restore(c, "w7", "1").status_code == 502


def test_an_UNREADABLE_current_draft_REFUSES_the_restore(client):
    """The read side of the pre-restore guarantee.

    FormKitNotFound means "nothing to protect"; FormKitStoreError means "the
    work IS there and I could not read it". Collapsing them skipped the
    pre-restore snapshot and fell through to put_schema, permanently destroying
    bytes that were never copied anywhere -- and returning 200. The write side
    was already guarded; this is the same guarantee on the read side (Opus
    fresh-eyes round 5).
    """
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))
    snaps = _snapshots(c, "w7").json()["snapshots"]

    # The live schema is present but unreadable.
    original = (root / "w7" / "schema.json").read_bytes()
    (root / "w7" / "schema.json").write_text("{ truncated", encoding="utf-8")

    resp = _restore(c, "w7", snaps[0]["id"])

    assert resp.status_code == 502, resp.text
    # ...and NOTHING was changed: the unreadable bytes are still there.
    assert (root / "w7" / "schema.json").read_text(encoding="utf-8") == "{ truncated"
    assert original  # the fixture really did write a schema first


def test_a_TRANSIENT_store_error_REFUSES_the_restore(client, monkeypatch):
    """The realistic trigger: a GCS 503 or a permissions blip. load_schema
    wraps those as FormKitStoreError, and a restore must refuse rather than
    overwrite work it could not copy."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))
    snaps = _snapshots(c, "w7").json()["snapshots"]

    real_load = store.load_schema
    calls = {"n": 0}

    async def _flaky(kit_id, schema_file="schema.json"):
        calls["n"] += 1
        # The schema_file check is what discriminates -- an earlier version
        # also tested calls["n"] > 0, which is always true because the counter
        # is incremented directly above it (Opus fresh-eyes round 10).
        if schema_file == "schema.json":
            raise FormKitStoreError("503 backend error")
        return await real_load(kit_id, schema_file)

    monkeypatch.setattr(store, "load_schema", _flaky)

    resp = _restore(c, "w7", snaps[0]["id"])

    assert resp.status_code == 502, resp.text
    monkeypatch.undo()
    # The live draft is untouched -- still B, not the restored A.
    assert _run(store.load_schema("w7", "schema.json"))["_tag"] == "B"


def test_GCS_ignores_a_FOLDER_MARKER_blob():
    """GCS consoles and gsutil create placeholder objects named exactly
    "<kit>/_drafts/7". Without the depth guard that registers as snapshot 7,
    jumping the id counter and listing a phantom entry that 404s on restore."""
    registry = {"form-kits/w7/_drafts/7": {"data": ""}}
    store = _gcs_store(registry)

    assert _run(store._snapshot_ids("w7")) == []
    assert _run(store.put_draft_snapshot("w7", {"_tag": "A"})) == "1"


# --- concurrency: the bead's CENTRAL case -----------------------------------
#
# "Editor B -- or A, from a stale tab -- saves over it" is TWO SAVES AT ONCE.
# The id was computed from a listing and then written to, a TOCTOU: both savers
# read the same last id, both picked the same next one, and the second write
# destroyed the first's snapshot. Measured before the fix: 4 concurrent saves
# returned ids ['1','1','1','1'] locally and ['3','3','3','3'] on GCS, with ONE
# snapshot surviving out of four. The protection was silently absent in exactly
# the situation it was built for (Opus fresh-eyes round 6).


def test_CONCURRENT_snapshots_do_not_destroy_each_other(client):
    """Local store: every concurrent save keeps its own snapshot."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))

    async def _six():
        return await asyncio.gather(*[
            store.put_draft_snapshot("w7", {"_tag": f"v{i}"}) for i in range(6)])

    ids = _run(_six())

    assert len(set(ids)) == 6, f"ids collided: {sorted(ids)}"
    snaps = _run(store.list_draft_snapshots("w7"))
    assert len(snaps) == 6, f"snapshots destroyed: {len(snaps)} of 6"
    # ...and every schema is still individually loadable.
    tags = {_run(store.load_draft_snapshot("w7", i))["_tag"] for i in ids}
    assert tags == {f"v{i}" for i in range(6)}


def test_GCS_CONCURRENT_snapshots_do_not_destroy_each_other():
    """The store that ships, via if_generation_match=0 (compare-and-swap)."""
    registry = {}
    store = _gcs_store(registry)

    async def _six():
        return await asyncio.gather(*[
            store.put_draft_snapshot("w7", {"_tag": f"v{i}"}) for i in range(6)])

    ids = _run(_six())

    assert len(set(ids)) == 6, f"ids collided: {sorted(ids)}"
    snaps = _run(store.list_draft_snapshots("w7"))
    assert len(snaps) == 6, f"snapshots destroyed: {len(snaps)} of 6"
    tags = {_run(store.load_draft_snapshot("w7", i))["_tag"] for i in ids}
    assert tags == {f"v{i}" for i in range(6)}


def test_CONCURRENT_saves_through_the_ROUTE_each_keep_a_snapshot(client):
    """The same property at the HTTP layer, which is where editors meet it."""
    import threading

    c, store, root = client
    _make_kit(root, "w7", schema=_schema("base"))

    results = []
    def _save_one(n):
        results.append(_save(c, "w7", _schema(f"v{n}")).status_code)

    threads = [threading.Thread(target=_save_one, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == [200] * 4, results
    # Four saves over an existing draft: four snapshots of prior states.
    snaps = _run(store.list_draft_snapshots("w7"))
    assert len(snaps) == 4, f"concurrent saves collapsed to {len(snaps)} snapshots"


# --- claimed-but-unwritten ids ----------------------------------------------
#
# The claim creates the directory as its lock, so any failure between the mkdir
# and the write -- full disk, killed worker, recycled Cloud Run instance --
# leaves an empty one behind. Counting those as ring members meant abandoned
# claims EVICTED REAL WORK: measured at 10 listed entries with 1 actually
# restorable, the three genuine snapshots deleted to make room for empty
# directories (Opus fresh-eyes round 7).


def test_ABANDONED_claims_do_not_evict_real_work(client):
    """The measured harm, pinned."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("v0"))
    for i in range(3):
        _save(c, "w7", _schema(f"real{i}"))

    # Ten crashes between claim and write.
    drafts = root / "w7" / "_drafts"
    highest = max(int(d.name) for d in drafts.iterdir() if d.name.isdigit())
    for n in range(highest + 1, highest + 11):
        (drafts / str(n)).mkdir()

    _save(c, "w7", _schema("after"))

    snaps = _snapshots(c, "w7").json()["snapshots"]
    restorable = 0
    for snap in snaps:
        try:
            _run(store.load_draft_snapshot("w7", snap["id"]))
            restorable += 1
        except Exception:
            pass

    assert restorable == len(snaps), (
        f"{len(snaps)} listed but only {restorable} restorable -- phantoms are "
        "in the recovery list")
    # The real work survived rather than being evicted by empty directories.
    tags = {_run(store.load_draft_snapshot("w7", x["id"]))["_tag"] for x in snaps}
    assert {"real0", "real1", "real2"} <= tags, tags


def test_an_abandoned_claim_is_REAPED(client):
    """Otherwise they accumulate forever and push the counter ever upward."""
    c, _store, root = client
    _make_kit(root, "w7", schema=_schema("A"))
    _save(c, "w7", _schema("B"))

    drafts = root / "w7" / "_drafts"
    (drafts / "99").mkdir()
    # A save whose claim lands ABOVE the orphan reaps it.
    for _ in range(3):
        _save(c, "w7", _schema("more"))

    assert not (drafts / "99").exists() or         (drafts / "99" / "schema.json").exists()


def test_a_CLAIM_skips_an_id_another_saver_already_holds(client):
    """An unwritten directory is still a held id, and mkdir refuses it.

    NOTE ON WHAT THIS DOES *NOT* PROVE: I first named this
    "...still_blocks_a_concurrent_saver" and asserted it pinned the
    include_unwritten flag. It does not -- removing that flag leaves this test
    passing, because the atomic mkdir refuses the taken id anyway and the loop
    walks on. The flag earns its keep in the REAPER (which must distinguish an
    abandoned claim from a live one), not in collision safety, and
    test_an_abandoned_claim_is_REAPED is what pins it. Renamed rather than left
    claiming more than it shows.
    """
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("A"))

    # An in-flight claim nobody has written yet.
    drafts = root / "w7" / "_drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "1").mkdir()

    new_id = _run(store.put_draft_snapshot("w7", {"_tag": "concurrent"}))

    assert new_id != "1", "the claim handed out an id another saver held"


def test_the_REAPER_never_deletes_a_snapshot_someone_just_COMPLETED(client):
    """The reaper is the one operation here that DELETES, so its blast radius
    needs a test of its own.

    My first version bounded it by id -- skip anything >= the id just written
    -- and the comment claimed a concurrent saver was "never disturbed". Wrong
    side: the saver in danger holds a LOWER id. One whose schema.json landed
    between the two listings was absent from `written`, below next_id, and got
    deleted. Measured at 85 silent losses in 360 trials in a sub-3ms window
    (Opus fresh-eyes round 8).

    This lands the concurrent write INSIDE that window deterministically,
    rather than hoping to hit a millisecond race.
    """
    import backend.services.form_kits as fk

    c, store, root = client
    _make_kit(root, "w7", schema=_schema("live"))
    drafts = root / "w7" / "_drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "1").mkdir()  # another saver has CLAIMED id 1, not yet written

    real = fk.LocalFormKitStore._snapshot_ids
    state = {"n": 0}

    def hooked(self, kit_id, include_unwritten=False):
        out = real(self, kit_id, include_unwritten)
        state["n"] += 1
        # Immediately after the reaper takes its `written` listing, the other
        # saver completes -- the exact gap the id bound cannot cover.
        if state["n"] == 2:
            (drafts / "1" / "schema.json").write_text(
                json.dumps(_schema("THEIR_WORK")), encoding="utf-8")
        return out

    fk.LocalFormKitStore._snapshot_ids = hooked
    try:
        _run(store.put_draft_snapshot("w7", _schema("mine")))
    finally:
        fk.LocalFormKitStore._snapshot_ids = real

    assert (drafts / "1" / "schema.json").exists(),         "the reaper deleted a snapshot another saver had just completed"
    assert _run(store.load_draft_snapshot("w7", "1"))["_tag"] == "THEIR_WORK"


def test_a_precondition_failure_on_an_ORDINARY_write_stays_fail_closed():
    """_SnapshotIdTaken subclasses FormKitStoreError.

    _upload_json is shared by put_schema, put_metadata, put_json_artifact and
    both archived-revision writes, and its `except Exception ->
    FormKitStoreError` is the fail-closed guarantee the routes depend on. As a
    bare Exception the new retry signal escaped that guarantee for all five
    untouched writers: a 412 from any other source (a retention policy, an
    object hold) on a plain put_schema became an unhandled 500 rather than a
    handled 502 -- on the editor's save route (Opus fresh-eyes round 8).
    """
    from backend.tests.unit.test_editor_kit_routes import (
        _FakePreconditionFailed, _gcs_store)

    registry = {}
    store = _gcs_store(registry)

    class _AlwaysRefuses:
        def blob(self, name):
            class _B:
                cache_control = None
                def upload_from_string(self, *a, **k):
                    raise _FakePreconditionFailed("object hold")
            return _B()

    store._bucket = _AlwaysRefuses()

    # An ORDINARY write, nothing to do with draft snapshots.
    with pytest.raises(FormKitStoreError):
        _run(store.put_schema("w7", _schema("A")))


# --- the reaper's guards, ONE LAYER AT A TIME -------------------------------
#
# test_the_REAPER_never_deletes_a_snapshot_someone_just_COMPLETED only reddens
# when BOTH guards are removed: its concurrent write lands in the OUTER window
# (between the two listings), so the early return fires and rmdir is never
# reached -- swapping rmdir for rmtree is invisible to it. Each guard covers a
# different window and needs its own test, or a refactor silently deletes one
# and reopens the round-8 data loss (Opus fresh-eyes round 9).


def test_the_reaper_SKIPS_a_directory_that_now_holds_a_schema(client):
    """Guard 1, the emptiness re-check.

    Pinned WITHOUT hooking the check itself: an earlier version of this test
    monkeypatched Path.exists to fire mid-check, which could never catch the
    deletion of that very call -- with the early return gone there is no
    .exists() left to hook, so the test passed by construction. Instead: put a
    completed snapshot where the reaper's stale listing says an orphan is, and
    assert it survives. That binds whichever guard stops it (Opus round 9).
    """
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("live"))
    drafts = root / "w7" / "_drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "1").mkdir()
    # Between the reaper's listing and its delete, another saver finishes.
    real_ids = type(store)._snapshot_ids
    state = {"n": 0}

    def hooked(self, kit_id, include_unwritten=False):
        out = real_ids(self, kit_id, include_unwritten)
        state["n"] += 1
        if state["n"] == 2:
            (drafts / "1" / "schema.json").write_text(
                json.dumps(_schema("THEIR_WORK")), encoding="utf-8")
            (drafts / "1" / "meta.json").write_text(
                # A REAL stamp, as put_draft_snapshot writes one: the
                # assertion below is that the reaper does not strip it, so the
                # fixture must have one to strip.
                json.dumps({"id": "1", "savedAt": "2026-08-18T12:00:00+00:00"}),
                encoding="utf-8")
        return out

    type(store)._snapshot_ids = hooked
    try:
        _run(store.put_draft_snapshot("w7", _schema("mine")))
    finally:
        type(store)._snapshot_ids = real_ids

    assert (drafts / "1" / "schema.json").exists(),         "a completed snapshot was reaped"
    assert _run(store.load_draft_snapshot("w7", "1"))["_tag"] == "THEIR_WORK"
    # THE ASSERTION THAT MAKES THIS BIND. The unlink runs BEFORE rmdir is
    # reached, so without the schema.json early return a completed snapshot
    # keeps its schema but loses its STAMP -- savedAt goes null, and that is
    # the only field distinguishing entries in a recovery list of bare
    # counters. My earlier version asked only "does the schema survive?", so
    # it passed under that mutation and I wrongly concluded the guard was an
    # optimization (Opus fresh-eyes round 10).
    assert (drafts / "1" / "meta.json").exists(),         "the reaper stripped a completed snapshot's stamp"
    listed = _snapshots(c, "w7").json()["snapshots"]
    stamp = next(x["savedAt"] for x in listed if x["id"] == "1")
    assert stamp, "savedAt went null -- the stamp was destroyed"


def test_the_reaper_leaves_an_IN_FLIGHT_temp_write_alone(client):
    """A saver mid-_write_json holds only .schema.json.<pid>.<hex>.tmp in its
    directory. Unlinking anything other than meta.json removes that temp file,
    lets rmdir succeed, and the saver dies on os.replace -- losing the
    snapshot it was in the middle of writing."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("live"))
    drafts = root / "w7" / "_drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "1").mkdir()
    # Exactly what an in-flight _write_json leaves on disk.
    tmp = drafts / "1" / ".schema.json.19436.deadbeef.tmp"
    tmp.write_text(json.dumps(_schema("MID_WRITE")), encoding="utf-8")

    _run(store.put_draft_snapshot("w7", _schema("mine")))

    assert tmp.exists(), "the reaper unlinked another saver's in-flight write"
    assert (drafts / "1").exists(), "and removed the directory under them"


def test_the_reaper_DOES_still_reap(client):
    """The other failure direction: a reaper so cautious it never deletes would
    pass every test above and silently regrow the phantom problem."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("live"))
    drafts = root / "w7" / "_drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "1").mkdir()                       # a genuinely abandoned claim
    (drafts / "2").mkdir()
    (drafts / "2" / "meta.json").write_text("{}", encoding="utf-8")  # ...and one with a stamp only

    _run(store.put_draft_snapshot("w7", _schema("mine")))

    assert not (drafts / "1").exists(), "an abandoned claim was not reaped"
    assert not (drafts / "2").exists(), "a stamp-only claim was not reaped"


def test_CONCURRENT_savers_never_share_an_id_or_lose_a_snapshot(client):
    """What the reaper's id bound actually has to hold, measured rather than
    reasoned about.

    Ids never collide, but NOT for the reason I first gave. I claimed
    _claim_snapshot_id "always walks past the highest existing id so the bound
    never fires" -- that is empirically false; instrumenting the real path
    shows it firing 5 times in 60 concurrent trials on shapes like (orphan=8,
    next_id=3). A saver that claimed 3 while the max was 2 is still running
    when others reach 8.

    The actual reason ids never collide: `candidate = max(existing) + 1`, and
    the reaping saver's own id is written by reap time, so the max never drops
    and a freed lower id is never re-handed-out.

    This test pins the OUTCOME -- concurrent savers never share an id and never
    lose a snapshot -- because that survives being wrong about the mechanism,
    which three rounds running now have been (Opus fresh-eyes round 12).
    """
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("live"))

    async def _eight():
        return await asyncio.gather(*[
            store.put_draft_snapshot("w7", {"_tag": f"v{i}"}) for i in range(8)])

    ids = _run(_eight())

    assert len(set(ids)) == 8, f"two savers shared an id: {sorted(ids, key=int)}"
    snaps = _run(store.list_draft_snapshots("w7"))
    assert len(snaps) == 8, f"{len(snaps)} of 8 snapshots survived"
    tags = {_run(store.load_draft_snapshot("w7", i))["_tag"] for i in ids}
    assert tags == {f"v{i}" for i in range(8)}, "a schema was overwritten"


def test_the_reaper_still_takes_LOWER_abandoned_claims(client):
    """The bound must not become 'never reap anything': ids below the one just
    written are genuinely abandoned and have to go, or they accumulate."""
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("live"))
    drafts = root / "w7" / "_drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "1").mkdir()
    (drafts / "2").mkdir()

    _run(store.put_draft_snapshot("w7", _schema("mine")))

    assert not (drafts / "1").exists(), "a lower abandoned claim was not reaped"
    assert not (drafts / "2").exists(), "a lower abandoned claim was not reaped"


def test_the_reaper_SPARES_a_higher_in_flight_claim(client):
    """The id bound protects a HIGHER claim that is still being written.

    A saver that claimed 3 while the max was 2 can still be running when others
    have raced to 8, so (orphan=8, next_id=3) is a real shape -- measured
    firing 5 times in 60 concurrent trials. Without the bound the reaper
    rmdir's that claim out from under its writer, whose _write_json then dies:
    4 failed snapshot writes in 120 trials, versus 0 with it.

    Deterministic rather than timing-dependent: drive the reap loop directly at
    the shape the concurrency produces, so the guard is pinned without needing
    to win a race (Opus fresh-eyes round 12).

    I argued in round 11 that this bound never fires. It does. The test exists
    because I was wrong and the comment above it said so for two rounds.
    """
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("live"))
    drafts = root / "w7" / "_drafts"
    drafts.mkdir(parents=True, exist_ok=True)

    # Drive the REAL put_draft_snapshot, not a hand-rolled copy of its reap
    # loop -- a reimplementation cannot catch the guard being deleted, which is
    # how my first version of this test passed under the mutation.
    #
    # The shape: a saver takes a LOW id, and a HIGHER claim appears in flight
    # before its reap pass runs.
    real_claim = type(store)._claim_snapshot_id

    def claim_then_race(self, kit_id):
        target, low_id = real_claim(self, kit_id)
        # Another saver claims a much higher id and is still writing it.
        (drafts / "8").mkdir(exist_ok=True)
        return target, low_id

    type(store)._claim_snapshot_id = claim_then_race
    try:
        _run(store.put_draft_snapshot("w7", _schema("mine")))
    finally:
        type(store)._claim_snapshot_id = real_claim

    assert (drafts / "8").exists(), (
        "the reaper deleted a higher in-flight claim -- its writer's "
        "_write_json would die with FileNotFoundError")


def test_the_reaper_SPARES_a_LOWER_in_flight_claim(client):
    """bd polyglot-pdf-tcwck: the id bound only protects a HIGHER claim.

    The CI traceback: `FileExistsError` from `path.parent.mkdir(parents=True,
    exist_ok=True)` inside A's own _write_json. pathlib's mkdir catches the
    OSError from `os.mkdir` (the directory already existed -- A claimed it)
    and re-raises ONLY if `not self.is_dir()` by the time it checks. So the
    narrow window is: A's `os.mkdir` sees its own claimed directory and
    raises FileExistsError, and BEFORE the follow-up `self.is_dir()` runs,
    a concurrent saver B's reap pass -- which considers A's claim abandoned
    because A's id is BELOW B's own `next_id`, and the `>= next_id` bound
    only spares claims ABOVE it -- rmdir's that directory out from under A.
    `is_dir()` then reports False and the exception re-raises right back out
    as a FormKitStoreError, exactly the CI failure.

    Deterministic rather than timing-dependent: a hook on `Path.is_dir` fires
    exactly when A's mkdir checks it (not on any other is_dir call in the
    process) and, in that instant, runs claimant B's ENTIRE real
    put_draft_snapshot -- claim, write, and full reap pass -- against the
    disk. That is the real reaper code, not a reimplementation, so the fix
    (or its removal) is genuinely exercised rather than assumed.
    """
    c, store, root = client
    _make_kit(root, "w7", schema=_schema("live"))

    # Claimant A has already claimed id "1" (the atomic mkdir in
    # _claim_snapshot_id) but not yet written -- exactly the shape a delayed
    # anyio worker leaves on disk. Called directly (it is a plain sync
    # method): put_draft_snapshot itself only ever reaches it via
    # anyio.to_thread.run_sync, which adds no behavior worth re-driving here.
    claim_dir, claimed_id = store._claim_snapshot_id("w7")
    assert claimed_id == "1"

    real_is_dir = pathlib.Path.is_dir
    state = {"fired": False}

    def hooked_is_dir(self):
        # Fire once, only for A's own claimed directory -- every other
        # is_dir() call in the process (schema.json checks, _snapshot_ids
        # scans inside B's own save) must pass straight through untouched.
        if not state["fired"] and self == claim_dir:
            state["fired"] = True
            _run(store.put_draft_snapshot("w7", {"_tag": "B"}))
        return real_is_dir(self)

    pathlib.Path.is_dir = hooked_is_dir
    try:
        # A's write, driven directly at the exact point put_draft_snapshot
        # would call it after claiming "1" above.
        _run(store._write_json(claim_dir / "schema.json", {"_tag": "A"}))
        _run(store._write_json(claim_dir / "meta.json", {"id": "1"}))
    finally:
        pathlib.Path.is_dir = real_is_dir

    # Before the fix: the write above raised FormKitStoreError with
    # "[Errno 17] File exists" / WinError 183 -- the CI traceback -- because
    # B's reap pass rmdir'd A's claimed-but-then-empty directory in the
    # instant between A's os.mkdir and its is_dir() re-check.
    assert _run(store.load_draft_snapshot("w7", "1"))["_tag"] == "A", (
        "claimant A's snapshot did not survive -- the reaper took its "
        "lower, still-in-flight claim")
    snaps = _run(store.list_draft_snapshots("w7"))
    tags = {_run(store.load_draft_snapshot("w7", s["id"]))["_tag"] for s in snaps}
    assert tags == {"A", "B"}, f"expected both snapshots, got {tags}"
