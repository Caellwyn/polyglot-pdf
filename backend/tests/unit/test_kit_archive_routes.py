"""Editor archive-read routes (bd polyglot-pdf-qfyxr).

bd w3zw shipped superseded revisions as storage + operator-CLI only; these
routes expose them to the editor UI (list newest-first + read one schema,
read-only -- there is deliberately no write counterpart, since an archived
revision is what the audit trail names). Driven against the REAL
LocalFormKitStore over a temp tree, so the store's archive primitives are
exercised end to end, not a double.

ASCII only.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
from backend.services.form_kits import LocalFormKitStore

from backend.tests.unit.test_editor_kit_routes import VALID_SCHEMA as _SCHEMA


def _make_kit(root, kit_id, status="complete"):
    kit = root / kit_id
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps({"status": status, "label": kit_id}), encoding="utf-8")
    (kit / "form.pdf").write_bytes(b"%PDF-1.7 test")
    return kit


def _archive_revision(kit_dir, marker, tag, published_at=None):
    d = kit_dir / "_archive" / marker
    d.mkdir(parents=True, exist_ok=True)
    (d / "schema.json").write_text(json.dumps({"rev": tag}), encoding="utf-8")
    if published_at is not None:
        (d / "metadata.json").write_text(
            json.dumps({"status": "complete", "published_at": published_at}),
            encoding="utf-8")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend.tests.unit.test_editor_kit_routes import _settings

    app = FastAPI()
    app.include_router(ekr.router)
    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok"))
    return TestClient(app), tmp_path


EDIT = {"X-Editor-Token": "edit-tok"}


def test_archive_routes_are_token_gated(client):
    c, root = client
    _make_kit(root, "w7")
    assert c.get("/api/editor/kits/w7/archive").status_code in (401, 403)
    assert c.get(
        "/api/editor/kits/w7/archive/2024-01/schema").status_code in (401, 403)


def test_archive_lists_newest_first_with_stampless_last(client):
    """The maintainer's 'organized by form, then chronologically': stamped
    revisions newest-first, a stampless (pre-stamp era) revision last.
    Mutation: drop the revisions.sort in list_kit_archive -- red (the store
    lists markers in name order: 2024-01 first)."""
    c, root = client
    kit = _make_kit(root, "w7")
    _archive_revision(kit, "2024-01", "old", "2024-01-05T00:00:00+00:00")
    _archive_revision(kit, "2025-06", "newer", "2025-06-01T00:00:00+00:00")
    _archive_revision(kit, "sha256-abc", "unstamped", None)

    resp = c.get("/api/editor/kits/w7/archive", headers=EDIT)
    assert resp.status_code == 200
    assert [r["marker"] for r in resp.json()["revisions"]] == [
        "2025-06", "2024-01", "sha256-abc",
    ]
    stamps = {r["marker"]: r["published_at"] for r in resp.json()["revisions"]}
    assert stamps["2025-06"] == "2025-06-01T00:00:00+00:00"
    assert stamps["sha256-abc"] is None


def test_kit_with_no_archive_lists_empty(client):
    """'No archived versions' is the normal state, not an error."""
    c, root = client
    _make_kit(root, "w7")
    resp = c.get("/api/editor/kits/w7/archive", headers=EDIT)
    assert resp.status_code == 200
    assert resp.json() == {"revisions": []}


def test_archive_list_on_missing_kit_is_404(client):
    """'No archived versions' and 'no such form' are different answers (the
    draft-snapshots lesson). Mutation: drop the _load_meta_or_404 call --
    red."""
    c, _root = client
    assert c.get("/api/editor/kits/ghost/archive", headers=EDIT).status_code == 404


def test_archived_schema_reads_back_exact(client):
    c, root = client
    kit = _make_kit(root, "w7")
    _archive_revision(kit, "2024-01", "old", "2024-01-05T00:00:00+00:00")

    resp = c.get("/api/editor/kits/w7/archive/2024-01/schema", headers=EDIT)
    assert resp.status_code == 200
    assert resp.json() == {"rev": "old"}
    assert resp.headers["cache-control"] == "no-store"


def test_unknown_marker_is_404(client):
    c, root = client
    _make_kit(root, "w7")
    resp = c.get("/api/editor/kits/w7/archive/2099-01/schema", headers=EDIT)
    assert resp.status_code == 404


@pytest.mark.parametrize("marker", ["a..b", "a" * 129, "a b"])
def test_invalid_marker_is_400_from_validation_not_the_store(client, marker):
    """A hostile marker must be refused by VALIDATION (400), never by luck of
    the store lookup missing (404 would mean it REACHED the store). Mutation:
    drop the _safe_archive_marker call -- these rows 404 via the store miss
    instead -- red."""
    c, root = client
    _make_kit(root, "w7")
    resp = c.get(f"/api/editor/kits/w7/archive/{marker}/schema", headers=EDIT)
    assert resp.status_code == 400
