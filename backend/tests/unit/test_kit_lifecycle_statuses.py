"""Kit lifecycle statuses: unpublished + replace-current publish
(bd polyglot-pdf-6dz0).

A form has ONE live version. Retiring a published revision must hide it from
clients WITHOUT letting it become editable again -- its schema is what earlier
confirmation records were confirmed against (bd polyglot-pdf-w3zw), so an
editable retired revision would make the archive pointless.

The three exit criteria pinned here:
  1. Republishing a changed revision leaves exactly ONE catalogue entry.
  2. Unpublish hides the kit, keeps its files, blocks schema edits, and is
     reversible through the publish gate.
  3. Cross-kit "replace current" retires the superseded kit and leaves the new
     one as the only entry for that form.
"""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
from backend.services.form_kits import LocalFormKitStore


def _run(coro):
    # asyncio.run, never get_event_loop: the legacy accessor breaks once an
    # earlier test file has closed the main loop (bd polyglot-pdf-r8gq).
    return asyncio.run(coro)


# Reuse the fixture the editor-route suite already proves clears the publish
# gate (validate + extraction_info + v2 stamp + lint), rather than maintaining a
# second copy that drifts out of validity -- as this file's first draft did.
from backend.tests.unit.test_editor_kit_routes import VALID_SCHEMA as _SCHEMA


def _make_kit(root, kit_id, status="complete", schema=None):
    kit = root / kit_id
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(
        json.dumps(schema or _SCHEMA), encoding="utf-8"
    )
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

    async def _no_drift(_store, _kit_id, _schema, _schema_file):
        return 0, None

    monkeypatch.setattr(ekr, "_sweep_drifted_translations", _no_drift)
    return TestClient(app), store, tmp_path


HDR = {"X-Editor-Token": "edit-tok"}


def _status(client, kit_id, status, replaces=None):
    body = {"status": status}
    if replaces:
        body["replaces_kit_id"] = replaces
    return client.post(f"/api/editor/kits/{kit_id}/status", json=body, headers=HDR)


# --- the status model itself ------------------------------------------------


def test_unpublished_is_write_locked_but_not_complete():
    """The property every write gate now asks about. An unpublished kit is NOT
    complete, so a `== "complete"` check would let a write through -- which is
    exactly how the third status could silently reopen the lock."""
    assert ekr._is_write_locked({"status": "unpublished"})
    assert ekr._is_write_locked({"status": "complete"})
    assert not ekr._is_write_locked({"status": "draft"})
    assert ekr._status_of({"status": "unpublished"}) == "unpublished"


# --- criterion 2: unpublish hides, locks, and is reversible ------------------


def test_unpublish_hides_the_kit_but_keeps_its_files(client):
    c, store, root = client
    _make_kit(root, "w7")

    resp = _status(c, "w7", "unpublished")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "unpublished"
    # Hidden from the CLIENT manifest gate (complete-only), files intact.
    meta = _run(store.load_metadata("w7"))
    assert meta["status"] == "unpublished"
    assert (root / "w7" / "schema.json").exists()
    assert (root / "w7" / "form.pdf").exists()


def test_unpublished_kit_refuses_schema_edits(client):
    """The load-bearing half: hidden is not enough. A retired revision's bytes
    are what earlier confirmations point at, so they must stay frozen."""
    c, _store, root = client
    _make_kit(root, "w7", status="unpublished")

    resp = c.put("/api/editor/kits/w7/schema",
                 json={"fields": [{"id": "f1"}]}, headers=HDR)

    assert resp.status_code == 409
    assert "unpublished" in resp.json()["detail"].lower()


def test_unpublished_kit_cannot_be_reverted_to_draft(client):
    """Draft is editable, so allowing this would bypass the write-lock
    entirely -- the retired bytes could then be rewritten in place."""
    c, _store, root = client
    _make_kit(root, "w7", status="unpublished")

    resp = _status(c, "w7", "draft")

    assert resp.status_code == 409
    assert "cannot be reverted to draft" in resp.json()["detail"]


def test_unpublished_kit_returns_to_service_through_the_publish_gate(client):
    c, store, root = client
    _make_kit(root, "w7", status="unpublished")

    resp = _status(c, "w7", "complete")

    assert resp.status_code == 200, resp.text
    assert _run(store.load_metadata("w7"))["status"] == "complete"


def test_unpublishing_a_draft_is_refused(client):
    """Only a live kit can be retired; anything else is a confused request."""
    c, _store, root = client
    _make_kit(root, "w7", status="draft")

    resp = _status(c, "w7", "unpublished")

    assert resp.status_code == 409
    assert "Only a published form can be unpublished" in resp.json()["detail"]


def test_unpublishing_archives_the_retired_revision(client):
    """Retiring is a supersede: the bytes must be archived, exactly as a
    revert-to-draft archives them (bd polyglot-pdf-w3zw)."""
    c, store, root = client
    _make_kit(root, "w7")

    _status(c, "w7", "unpublished")

    assert _run(store.list_archived_markers("w7")), "no archive written"
    assert _run(store.load_archived_revision("w7", "12/2024")) == _SCHEMA


# --- criterion 3: cross-kit replace-current ---------------------------------


def test_replace_current_retires_the_superseded_kit(client):
    c, store, root = client
    _make_kit(root, "w7-2024")                       # the outgoing live kit
    _make_kit(root, "w7-2026", status="draft")       # the incoming revision

    resp = _status(c, "w7-2026", "complete", replaces="w7-2024")

    assert resp.status_code == 200, resp.text
    assert resp.json()["supersededKitId"] == "w7-2024"
    # Exactly one live kit for the form; the old one retired, files intact.
    assert _run(store.load_metadata("w7-2026"))["status"] == "complete"
    assert _run(store.load_metadata("w7-2024"))["status"] == "unpublished"
    assert (root / "w7-2024" / "schema.json").exists()


def test_replace_current_archives_the_superseded_revision(client):
    c, store, root = client
    _make_kit(root, "w7-2024")
    _make_kit(root, "w7-2026", status="draft")

    _status(c, "w7-2026", "complete", replaces="w7-2024")

    assert _run(store.list_archived_markers("w7-2024")), "outgoing kit not archived"


def test_a_kit_cannot_replace_itself(client):
    """Same-kit republish already replaces its own entry; naming itself is a
    confused request, and honouring it would archive-and-retire the very kit
    being published."""
    c, _store, root = client
    _make_kit(root, "w7", status="draft")

    resp = _status(c, "w7", "complete", replaces="w7")

    assert resp.status_code == 409
    assert "cannot replace itself" in resp.json()["detail"]


def test_replacing_a_kit_that_is_not_live_is_refused(client):
    c, _store, root = client
    _make_kit(root, "w7-2024", status="draft")
    _make_kit(root, "w7-2026", status="draft")

    resp = _status(c, "w7-2026", "complete", replaces="w7-2024")

    assert resp.status_code == 409
    assert "not published" in resp.json()["detail"]


def test_replaces_is_ignored_when_the_request_is_not_a_publish(client):
    """A supersede retires a live kit, so it may fire ONLY as part of putting a
    replacement into service. Left ungated it also fires on an unpublish or a
    revert, retiring the outgoing kit when nothing takes its place -- the form
    would then have NO live version. A mutation removing the publish condition
    survived every other test in this file, so pin it directly.
    """
    c, store, root = client
    _make_kit(root, "w7-2024")                 # live, and named as the outgoing
    _make_kit(root, "w7-2026")                 # live, the one being retired

    # Retiring w7-2026 must not touch w7-2024, whatever replaces_kit_id says.
    resp = _status(c, "w7-2026", "unpublished", replaces="w7-2024")

    assert resp.status_code == 200, resp.text
    assert resp.json()["supersededKitId"] is None
    assert _run(store.load_metadata("w7-2024"))["status"] == "complete"


def test_a_failed_incoming_write_leaves_the_outgoing_kit_live(client):
    """The ordering that matters: the outgoing kit is retired only AFTER the
    incoming one is actually live.

    The publish GATES protect against a validation failure, but not against the
    final metadata write failing. Retiring first and then failing there leaves
    the form with ZERO live versions -- worse than the two-entry state the
    supersede fixes. Publishing first makes the failure mode two live entries:
    visible, and fixable by unpublishing the old one (fresh-eyes finding).
    """
    from backend.services.form_kits import FormKitStoreError

    c, store, root = client
    _make_kit(root, "w7-2024")
    _make_kit(root, "w7-2026", status="draft")

    real_put = store.put_metadata
    calls = {"n": 0}

    async def _fail_incoming(kit_id, metadata):
        # Fail the INCOMING kit's own status write, after every gate passed.
        if kit_id == "w7-2026":
            calls["n"] += 1
            raise FormKitStoreError("simulated store failure")
        return await real_put(kit_id, metadata)

    store.put_metadata = _fail_incoming  # type: ignore[method-assign]
    try:
        resp = _status(c, "w7-2026", "complete", replaces="w7-2024")
    finally:
        store.put_metadata = real_put  # type: ignore[method-assign]

    assert resp.status_code == 502
    assert calls["n"] == 1, "the incoming write was never attempted"
    # The form still has its live version -- the outgoing kit was NOT retired.
    assert _run(store.load_metadata("w7-2024"))["status"] == "complete"


def test_a_failed_publish_leaves_the_outgoing_kit_live(client):
    """Ordering guard: the outgoing kit is retired only AFTER the incoming one
    clears every gate. Retiring first and then failing would leave the form
    with NO live version -- worse than the two-entry state being fixed."""
    c, store, root = client
    _make_kit(root, "w7-2024")
    # An incoming kit with no PDF fails the publish gate.
    kit = root / "w7-2026"
    kit.mkdir()
    (kit / "schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps({"status": "draft"}), encoding="utf-8"
    )

    resp = _status(c, "w7-2026", "complete", replaces="w7-2024")

    assert resp.status_code == 409
    # The form still has exactly one live version -- the old one.
    assert _run(store.load_metadata("w7-2024"))["status"] == "complete"


# --- criterion 1: one entry per form after a same-kit republish -------------


def test_same_kit_republish_needs_no_replace_flag(client):
    """One kit_id is one catalogue slot, so a kit always replaces itself --
    the checkbox exists only for the cross-kit case."""
    c, store, root = client
    _make_kit(root, "w7")

    # revert -> edit -> republish, the only route to a new revision
    assert _status(c, "w7", "draft").status_code == 200
    changed = json.loads(json.dumps(_SCHEMA))
    changed["fields"].append({
        "id": "f2", "name": "Field 2", "spoken_name": "field two",
        "type": "text", "section_id": "s1", "pdf_field_name": "f2[0]",
        "help": {"instructions": "Second field."},
    })
    changed["sections"][0]["fields"].append("f2")
    (root / "w7" / "schema.json").write_text(json.dumps(changed), encoding="utf-8")
    assert _status(c, "w7", "complete").status_code == 200

    # Still exactly one kit dir serving this form, now holding the new revision.
    assert _run(store.load_metadata("w7"))["status"] == "complete"
    assert len(_run(store.load_schema("w7"))["fields"]) == 2
    # ...and the superseded revision is retrievable, not gone.
    assert _run(store.list_archived_markers("w7"))
