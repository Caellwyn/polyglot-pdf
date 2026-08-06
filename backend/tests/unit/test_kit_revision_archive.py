"""Kit revision archive (bd polyglot-pdf-w3zw).

Kit storage is ONE slot per kit_id, so republishing used to destroy the schema
an old confirmation record was confirmed against -- the audit trail could name a
revision the store could no longer produce. These tests pin the three exit
criteria: the superseded schema stays retrievable by the marker its records
carry, an unchanged re-press does not re-archive, and archives stay invisible to
both catalogues.
"""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
from backend.services.form_kits import (
    FormKitNotFound,
    LocalFormKitStore,
    encode_marker,
)
from backend.utils.confirmation_logger import resolve_edition_marker


def _run(coro):
    # asyncio.run (not get_event_loop): the legacy accessor breaks when an
    # earlier test file has closed the main loop via its own asyncio.run --
    # these tests pass in isolation and fail in the full suite (bd
    # polyglot-pdf-r8gq, re-hit here).
    return asyncio.run(coro)


def _schema(*field_ids, edition=None):
    """A minimal schema whose ANSWERABLE SHAPE is driven by field_ids -- which
    is what the fingerprint marker keys on."""
    out = {
        "schema_version": "2",
        "fields": [{"id": fid, "type": "text"} for fid in field_ids],
    }
    if edition is not None:
        out["form_metadata"] = {"edition_date": edition}
    return out


def _make_kit(root, kit_id, schema, meta=None):
    kit = root / kit_id
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps(meta or {"status": "complete"}), encoding="utf-8"
    )
    return kit


# --- store primitives -------------------------------------------------------


def test_archived_revision_roundtrips_by_marker(tmp_path):
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    old = _schema("a", "b", edition="12/2024")

    _run(store.put_archived_revision("w7", "12/2024", old, {"status": "complete"}))

    assert _run(store.load_archived_revision("w7", "12/2024")) == old


def test_missing_archived_revision_is_not_found(tmp_path):
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    with pytest.raises(FormKitNotFound):
        _run(store.load_archived_revision("w7", "12/2024"))


def test_list_archived_markers_is_empty_not_error_without_archive(tmp_path):
    # "No superseded revisions" is the normal state of a fresh kit, not a fault.
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    assert _run(store.list_archived_markers("w7")) == []


@pytest.mark.parametrize("marker", [
    "12/2024",                  # a government edition date: contains a slash
    "sha256:1a2b3c4d5e6f",      # a fingerprint: contains a colon
    "../../etc/passwd",         # a traversal attempt
    "v2 (revised)",             # spaces and parens
    "..",                       # degenerate: dots only
    "",                         # degenerate: empty
])
def test_marker_encoding_is_a_safe_single_segment(tmp_path, marker):
    """Every marker must round-trip to SOME addressable archive dir, and none
    may escape the kit. A marker is kit-controlled and becomes a path segment,
    so it is untrusted exactly like a filename -- but it cannot be REJECTED
    (real markers contain '/' and ':'), so it is encoded instead."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    schema = _schema("x")

    _run(store.put_archived_revision("w7", marker, schema))

    segment = encode_marker(marker)
    assert "/" not in segment and "\\" not in segment and ".." not in segment
    assert segment  # never empty -> always addressable
    # It landed INSIDE the kit's archive dir, nowhere else.
    assert (tmp_path / "w7" / "_archive" / segment / "schema.json").exists()
    assert _run(store.load_archived_revision("w7", marker)) == schema


def test_archive_is_invisible_to_the_editor_catalogue(tmp_path):
    """Exit criterion 3. list_kit_files is the editor catalogue's source of
    truth; the archive must not appear as a kit or as a kit file."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    _run(store.put_archived_revision("w7", "12/2024", _schema("a", "b")))

    files = _run(store.list_kit_files())
    assert set(files) == {"w7"}                      # no "_archive" pseudo-kit
    assert files["w7"] == ["metadata.json", "schema.json"]  # no nested entries
    assert "_archive" not in _run(store.list_kit_ids())


def test_archive_is_invisible_to_the_client_manifest(tmp_path):
    """Exit criterion 3, second catalogue: the voice app's manifest."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    _run(store.put_archived_revision("w7", "12/2024", _schema("a", "b")))

    manifest = _run(store.load_manifest())
    assert [f["id"] for f in manifest["forms"]] == ["w7"]


# --- the promotion-route hook ----------------------------------------------


def _archive_hook(store, kit_id, meta):
    from backend.routes.editor_kit_routes import _archive_published_revision

    return _run(_archive_published_revision(store, kit_id, meta))


def test_revert_archives_the_published_revision_under_its_own_marker(tmp_path):
    """Exit criterion 1. The marker must come from the SUPERSEDED revision's own
    schema, so it matches what that revision's confirmation records carry."""
    store = LocalFormKitStore(tmp_path)
    published = _schema("a", "b", edition="12/2024")
    _make_kit(tmp_path, "w7", published)

    marker = _archive_hook(store, "w7", {"status": "complete"})

    assert marker == "12/2024"
    assert _run(store.load_archived_revision("w7", "12/2024")) == published


def test_fingerprint_era_revision_archives_under_its_fingerprint(tmp_path):
    """A firm's custom form has no government edition, so its records carry a
    sha256 fingerprint -- the archive must key on that SAME value, or those
    records become unresolvable."""
    store = LocalFormKitStore(tmp_path)
    published = _schema("a", "b")  # no edition_date
    _make_kit(tmp_path, "acme-intake", published)
    expected = resolve_edition_marker(None, published)
    assert expected.startswith("sha256:")

    marker = _archive_hook(store, "acme-intake", {"status": "complete"})

    assert marker == expected
    assert _run(store.load_archived_revision("acme-intake", expected)) == published


def test_reverting_twice_without_a_schema_change_archives_once(tmp_path):
    """Exit criterion 2: an idempotent revert->republish cycle that did not
    change the answerable shape must not pile up duplicate archive copies."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a", "b", edition="12/2024"))

    first = _archive_hook(store, "w7", {"status": "complete"})
    second = _archive_hook(store, "w7", {"status": "complete"})

    assert first == "12/2024"
    assert second is None  # already archived -> no second copy
    assert _run(store.list_archived_markers("w7")) == [encode_marker("12/2024")]


def test_a_changed_revision_archives_alongside_the_earlier_one(tmp_path):
    """Two genuinely different revisions must BOTH stay retrievable -- the
    second archive must not overwrite the first."""
    store = LocalFormKitStore(tmp_path)
    rev_a = _schema("a", "b", edition="12/2024")
    _make_kit(tmp_path, "w7", rev_a)
    _archive_hook(store, "w7", {"status": "complete"})

    # A new revision is published, then itself superseded.
    rev_b = _schema("a", "b", "c", edition="01/2026")
    (tmp_path / "w7" / "schema.json").write_text(json.dumps(rev_b), encoding="utf-8")
    _archive_hook(store, "w7", {"status": "complete"})

    assert _run(store.load_archived_revision("w7", "12/2024")) == rev_a
    assert _run(store.load_archived_revision("w7", "01/2026")) == rev_b


def test_archive_failure_does_not_block_the_revert(tmp_path):
    """A kit whose schema cannot be read must still be revertible: failing the
    revert would strand it published-and-uneditable, which is worse than a
    missing archive entry (which is logged loudly)."""
    store = LocalFormKitStore(tmp_path)
    kit = tmp_path / "w7"
    kit.mkdir()
    (kit / "metadata.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    # No schema.json at all.

    assert _archive_hook(store, "w7", {"status": "complete"}) is None


def test_fieldless_schema_archives_nothing(tmp_path):
    """No edition date and no fingerprintable shape means no marker a
    confirmation record could name -- so there is nothing to key an archive on."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "empty-kit", {"schema_version": "2", "fields": []})

    assert _archive_hook(store, "empty-kit", {"status": "complete"}) is None
    assert _run(store.list_archived_markers("empty-kit")) == []


# --- the REAL route: the archive must actually be WIRED IN ------------------
# The helper tests above all call _archive_published_revision directly, so they
# stay green even if the status route never calls it (verified by mutation:
# deleting the call site left all of them passing). These drive the actual HTTP
# endpoint, which is the only thing that pins the WIRING.


@pytest.fixture()
def route_client(tmp_path, monkeypatch):
    from backend.tests.unit.test_editor_kit_routes import _settings

    app = FastAPI()
    app.include_router(ekr.router)
    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok")
    )
    return TestClient(app), store, tmp_path


def test_revert_to_draft_route_archives_the_published_revision(route_client):
    """THE wiring test (exit criterion 1, end to end): POST status=draft on a
    published kit must leave its schema retrievable under its own marker."""
    client, store, root = route_client
    published = _schema("a", "b", edition="12/2024")
    _make_kit(root, "w7", published, {"status": "complete"})

    resp = client.post(
        "/api/editor/kits/w7/status",
        json={"status": "draft"},
        headers={"X-Editor-Token": "edit-tok"},
    )

    assert resp.status_code == 200, resp.text
    # The published bytes survive the revert, keyed by the marker its
    # confirmation records carry.
    assert _run(store.load_archived_revision("w7", "12/2024")) == published


def test_two_revisions_sharing_one_edition_date_both_survive(tmp_path):
    """An author may edit fields WITHOUT bumping the government edition string,
    producing two different revisions under one marker. A marker is therefore
    not a unique key: skipping on the marker NAME alone destroyed the second
    revision and made retrieval return the FIRST one -- a wrong answer, which
    for a legal record is worse than a missing one (fresh-eyes, reproduced live).
    """
    store = LocalFormKitStore(tmp_path)
    rev_1 = _schema("a", "b", edition="12/2024")
    _make_kit(tmp_path, "w7", rev_1)
    _archive_hook(store, "w7", {"status": "complete"})

    # Same edition_date, different answerable shape.
    rev_2 = _schema("a", "b", "c", edition="12/2024")
    (tmp_path / "w7" / "schema.json").write_text(json.dumps(rev_2), encoding="utf-8")
    second = _archive_hook(store, "w7", {"status": "complete"})

    # The first revision is untouched...
    assert _run(store.load_archived_revision("w7", "12/2024")) == rev_1
    # ...and the second was NOT silently dropped.
    assert second is not None
    assert _run(store.load_archived_revision("w7", second)) == rev_2


def test_repeating_the_same_colliding_revision_still_skips(tmp_path):
    """The disambiguated sibling must itself stay idempotent -- a repeated
    revert of the SAME revision must not pile up copies."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a", edition="12/2024"))
    _archive_hook(store, "w7", {"status": "complete"})
    rev_2 = _schema("a", "b", edition="12/2024")
    (tmp_path / "w7" / "schema.json").write_text(json.dumps(rev_2), encoding="utf-8")

    first = _archive_hook(store, "w7", {"status": "complete"})
    again = _archive_hook(store, "w7", {"status": "complete"})

    assert first is not None
    assert again is None  # same bytes already archived -> no third copy
    assert len(_run(store.list_archived_markers("w7"))) == 2


def test_every_schema_writing_editor_route_refuses_a_published_kit(route_client):
    """The PROPERTY the archive's placement depends on: a published kit's schema
    cannot be written by ANY editor route, so revert-to-draft is genuinely the
    last moment the superseded bytes exist.

    Pinning the property rather than the one route that was found missing it:
    the extract route had no complete-gate, which silently falsified the whole
    design premise. A new schema-writing route added later must either gate or
    fail this test.
    """
    client, _store, root = route_client
    _make_kit(root, "w7", _schema("a", edition="12/2024"), {"status": "complete"})
    (root / "w7" / "form.pdf").write_bytes(b"%PDF-1.7 test")
    hdr = {"X-Editor-Token": "edit-tok"}
    author = {"X-Editor-Token": "auth-tok"}

    # Every route that can write schema.json for an EXISTING kit.
    assert client.put("/api/editor/kits/w7/schema", json={"fields": []},
                      headers=hdr).status_code == 409
    assert client.post("/api/editor/kits/w7/repair", headers=author).status_code == 409
    assert client.post("/api/editor/kits/w7/translate-options",
                       headers=author).status_code == 409
    assert client.post("/api/editor/kits/w7/derive-divisions",
                       headers=author).status_code == 409
    assert client.post("/api/editor/kits/w7/regenerate-guidance",
                       headers=author).status_code == 409
    # The one this bead's review found ungated: force=true would have
    # overwritten the published schema in place, bypassing the archive.
    assert client.post("/api/editor/kits/w7/extract", data={"force": "true"},
                       headers=author).status_code == 409


def test_revert_of_an_already_draft_kit_archives_nothing(route_client):
    """Only the complete -> draft transition supersedes a PUBLISHED revision; a
    draft->draft no-op must not manufacture archive entries."""
    client, store, root = route_client
    _make_kit(root, "w7", _schema("a", edition="12/2024"), {"status": "draft"})

    resp = client.post(
        "/api/editor/kits/w7/status",
        json={"status": "draft"},
        headers={"X-Editor-Token": "edit-tok"},
    )

    assert resp.status_code == 200, resp.text
    assert _run(store.list_archived_markers("w7")) == []
