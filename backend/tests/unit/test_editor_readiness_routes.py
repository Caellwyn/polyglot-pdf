"""POST /api/editor/kits/{kit_id}/readiness (sprint-18 C4b, bd polyglot-pdf-na1zy).

The local-save stamp refresher: after an in-place local kit save the editor
POSTs the just-written schema and the BACKEND recomputes + persists the
readiness stamp -- the same `_stamp_readiness` the hosted save path runs, so
there is exactly ONE stamp writer in the tree.

Pinned here:
1. The route is token-gated like every /api/editor route (401 / 404 / 422).
2. The happy path persists a stamp measuring the POSTED schema into
   metadata.json, preserving every other metadata key.
3. The never-destroy rule: unparseable metadata.json is left byte-identical
   and the response says readiness null.

ASCII only.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
import backend.routes.editor_readiness_routes as err_routes
from backend.services.form_kits import LocalFormKitStore


def _settings(editor=None, author=None):
    return SimpleNamespace(
        SCHEMA_EDITOR_TOKEN=editor,
        SCHEMA_AUTHOR_TOKEN=author,
    )


def _make_kit(root, kit_id, *, meta_text=None, meta=None):
    kit_dir = root / kit_id
    kit_dir.mkdir()
    if meta_text is not None:
        (kit_dir / "metadata.json").write_text(meta_text, encoding="utf-8")
    elif meta is not None:
        (kit_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    (kit_dir / "schema.json").write_text("{}", encoding="utf-8")
    (kit_dir / "form.pdf").write_bytes(b"%PDF-1.7 test")
    return kit_dir


SCHEMA = {
    "form_metadata": {"title": "T", "version": "1"},
    "sections": [],
    "fields": [
        {"id": "f1", "name": "Field 1", "spoken_name": "field one",
         "type": "text", "pdf_field_name": "f1[0]",
         "help": {"instructions": "Enter it."},
         "_review": {"status": "reviewed_correct"}},
        {"id": "f2", "name": "Field 2", "spoken_name": "field two",
         "type": "text", "pdf_field_name": "f2[0]",
         "help": {"instructions": "Enter it too."}},
    ],
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(err_routes.router)
    store = LocalFormKitStore(tmp_path)
    # The route resolves the store via its own import; auth resolves settings
    # via the require_editor_role dependency it imports from ekr.
    monkeypatch.setattr(err_routes, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok")
    )
    return TestClient(app), tmp_path


AUTH = {"X-Editor-Token": "edit-tok"}


def test_route_is_token_gated(client):
    c, root = client
    _make_kit(root, "kit-a", meta={"status": "draft"})
    assert c.post("/api/editor/kits/kit-a/readiness", json=SCHEMA).status_code == 401
    assert c.post(
        "/api/editor/kits/kit-a/readiness", json=SCHEMA,
        headers={"X-Editor-Token": "wrong"},
    ).status_code == 401


def test_unknown_kit_404_and_fieldless_body_422(client):
    c, root = client
    _make_kit(root, "kit-a", meta={"status": "draft"})
    assert c.post(
        "/api/editor/kits/nope/readiness", json=SCHEMA, headers=AUTH
    ).status_code == 404
    assert c.post(
        "/api/editor/kits/kit-a/readiness", json={"fields": "not-a-list"},
        headers=AUTH,
    ).status_code == 422


def test_happy_path_persists_a_stamp_for_the_posted_schema(client):
    c, root = client
    _make_kit(root, "kit-a", meta={"status": "draft", "label": "Kit A"})
    resp = c.post(
        "/api/editor/kits/kit-a/readiness", json=SCHEMA, headers=AUTH
    )
    assert resp.status_code == 200
    stamp = resp.json()["readiness"]
    assert stamp is not None
    # The stamp measures the POSTED schema: 1 of 2 fields signed off.
    assert stamp["total"] == 2
    assert stamp["reviewed"] == 1
    assert stamp["percent"] == 50
    # A dump-less kit still lints (degraded to the dump-less rules, exactly
    # like the hosted save), so the stamp is VERIFIED -- the card may show it.
    assert stamp["verified"] is True
    assert stamp["schema_sha1"] == ekr._schema_hash(SCHEMA)
    # ...and it is PERSISTED, with every other metadata key preserved.
    on_disk = json.loads(
        (root / "kit-a" / "metadata.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "draft"
    assert on_disk["label"] == "Kit A"
    assert on_disk["readiness"]["percent"] == 50
    assert on_disk["readiness"]["schema_sha1"] == stamp["schema_sha1"]


def test_restamp_replaces_a_stale_stamp(client):
    """The C4b bug in miniature: a stale stamp from an earlier save must be
    REPLACED by the fresh measurement, not left describing the old schema."""
    c, root = client
    stale = {"reviewed": 9, "to_review": 0, "total": 9, "errors": 0,
             "percent": 100, "ready": True, "verified": True,
             "schema_sha1": "0" * 40, "stamped_at": "2026-01-01T00:00:00+00:00"}
    _make_kit(root, "kit-a", meta={"status": "draft", "readiness": stale})
    resp = c.post(
        "/api/editor/kits/kit-a/readiness", json=SCHEMA, headers=AUTH
    )
    assert resp.status_code == 200
    on_disk = json.loads(
        (root / "kit-a" / "metadata.json").read_text(encoding="utf-8"))
    assert on_disk["readiness"]["percent"] == 50
    assert on_disk["readiness"]["schema_sha1"] == ekr._schema_hash(SCHEMA)


def test_unparseable_metadata_is_never_destroyed(client):
    c, root = client
    _make_kit(root, "kit-a", meta_text="{not json")
    before = (root / "kit-a" / "metadata.json").read_bytes()
    resp = c.post(
        "/api/editor/kits/kit-a/readiness", json=SCHEMA, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["readiness"] is None
    assert (root / "kit-a" / "metadata.json").read_bytes() == before


import pytest as _pytest


@_pytest.mark.parametrize("status", ["complete", "unpublished"])
def test_write_locked_kit_is_refused_409(client, status):
    """A WRITE-LOCKED kit's stamp may only describe its published schema
    (Opus cross-surface finding): without this guard, an editor token could
    overwrite a live kit's stamp with counts for a body never saved -- the
    one write path whose siblings (PUT schema, /status) all refuse.
    Parametrized over the FULL bd 6dz0 write-locked set, not a sample: an
    unpublished kit is write-locked exactly like a complete one."""
    c, root = client
    stale = {"reviewed": 2, "to_review": 0, "total": 2, "errors": 0,
             "percent": 100, "ready": True, "verified": True,
             "schema_sha1": "f" * 40, "stamped_at": "2026-08-01T00:00:00+00:00"}
    _make_kit(root, "kit-a", meta={"status": status, "readiness": stale})
    before = (root / "kit-a" / "metadata.json").read_bytes()
    resp = c.post(
        "/api/editor/kits/kit-a/readiness", json=SCHEMA, headers=AUTH
    )
    assert resp.status_code == 409
    # The detail names the REAL state via _lock_reason -- not one blanket
    # "published" message for both (Opus round 3): a retired revision must
    # not be pointed at a publish flow that does not apply to it.
    detail = resp.json()["detail"]
    if status == "unpublished":
        assert "superseded revision" in detail
    else:
        assert "status complete" in detail
    assert (root / "kit-a" / "metadata.json").read_bytes() == before
