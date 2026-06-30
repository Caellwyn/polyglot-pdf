"""
Unit tests for the /api/form-kits routes.

list_form_kits (bd polyglot-pdf-snpi): the route must surface each kit's REAL
schema/pdf storage paths from the manifest so a kit declaring a custom schema
filename loads -- the client must not reconstruct `/<id>/schema.json`, which
404s for a custom-schema kit. When a manifest entry omits the paths (older
manifest), the route falls back to the conventional `/form-kits/<id>/schema.json`
and `/form-kits/<id>/form.pdf`.

Single-kit READ routes (bd polyglot-pdf-sbfk): get_form_kit_schema /
get_form_kit_pdf stream a kit's schema JSON and PDF bytes from the store (the
only path that serves those bytes in gcs mode). A hostile kit id must be rejected
(path-traversal guard) and a missing kit must 404.
"""
import asyncio
import json

import pytest
from fastapi import HTTPException

import backend.routes.form_kit_routes as fkr
from backend.services.form_kits import FormKitNotFound, FormKitStoreError


class _FakeStore:
    def __init__(self, manifest=None, schema=None, pdf=None):
        self._manifest = manifest
        self._schema = schema
        self._pdf = pdf
        # Records the filename the route asked for, so a test can assert the
        # route honored a custom manifest filename (bd polyglot-pdf-sbfk).
        self.requested_schema_file = None
        self.requested_pdf_file = None

    async def load_manifest(self, manifest_file: str = "index.json") -> dict:
        if self._manifest is None:
            raise FormKitNotFound("no manifest")
        return self._manifest

    async def load_schema(self, kit_id: str, schema_file: str = "schema.json") -> dict:
        self.requested_schema_file = schema_file
        if self._schema is None:
            raise FormKitNotFound(f"no schema for {kit_id}")
        return self._schema

    async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
        self.requested_pdf_file = pdf_filename
        if self._pdf is None:
            raise FormKitNotFound(f"no pdf for {kit_id}")
        return self._pdf


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_custom_schema_path_is_propagated(monkeypatch):
    manifest = {
        "forms": [
            {
                "id": "i90",
                "label": "Form I-90",
                "description": "Green card renewal",
                "schemaFile": "custom.json",
                "schemaPath": "/form-kits/i90/custom.json",
                "pdfFile": "i90.pdf",
                "pdfPath": "/form-kits/i90/i90.pdf",
            }
        ]
    }
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _FakeStore(manifest))

    resp = _run(fkr.list_form_kits())

    assert len(resp.forms) == 1
    form = resp.forms[0]
    assert form.id == "i90"
    assert form.label == "Form I-90"
    # The custom paths from the manifest survive -- NOT reconstructed as schema.json.
    assert form.schema_path == "/form-kits/i90/custom.json"
    assert form.pdf_path == "/form-kits/i90/i90.pdf"


def test_missing_paths_fall_back_to_convention(monkeypatch):
    # An older manifest entry without schemaPath/pdfPath -> conventional paths.
    manifest = {"forms": [{"id": "n400", "label": "Form N-400"}]}
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _FakeStore(manifest))

    resp = _run(fkr.list_form_kits())

    form = resp.forms[0]
    assert form.schema_path == "/form-kits/n400/schema.json"
    assert form.pdf_path == "/form-kits/n400/form.pdf"


def test_manifest_not_found_returns_empty(monkeypatch):
    class _NotFoundStore:
        async def load_manifest(self, manifest_file: str = "index.json") -> dict:
            raise fkr.FormKitNotFound("no manifest")

    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _NotFoundStore())

    resp = _run(fkr.list_form_kits())

    assert resp.forms == []


# --- single-kit READ routes (bd polyglot-pdf-sbfk) -------------------------


def test_get_schema_returns_json_body(monkeypatch):
    schema = {"title": "Form I-90", "fields": [{"id": "a"}]}
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _FakeStore(schema=schema))

    resp = _run(fkr.get_form_kit_schema("i90"))

    assert resp.media_type == "application/json"
    assert resp.headers["Cache-Control"] == "no-store"
    assert json.loads(resp.body) == schema


def test_get_pdf_returns_bytes(monkeypatch):
    pdf_bytes = b"%PDF-1.7 fake"
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _FakeStore(pdf=pdf_bytes))

    resp = _run(fkr.get_form_kit_pdf("i90"))

    assert resp.media_type == "application/pdf"
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.body == pdf_bytes


def test_get_schema_missing_kit_is_404(monkeypatch):
    # Store has no schema for this kit -> FormKitNotFound -> 404.
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _FakeStore(schema=None))

    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema("i90"))
    assert exc.value.status_code == 404


def test_get_pdf_missing_kit_is_404(monkeypatch):
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _FakeStore(pdf=None))

    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_pdf("i90"))
    assert exc.value.status_code == 404


@pytest.mark.parametrize(
    "bad_id",
    ["../secret", "..", "a/b", "a..b", "-leading", "with space", ""],
)
def test_bad_kit_id_is_rejected_400(bad_id, monkeypatch):
    # The guard must fire BEFORE the store is touched -- use a store that would
    # raise if its load methods were reached, proving the 400 comes from the guard.
    class _Boom:
        async def load_schema(self, *a, **k):
            raise AssertionError("store reached for an unsafe kit id")

        async def load_pdf_bytes(self, *a, **k):
            raise AssertionError("store reached for an unsafe kit id")

    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _Boom())

    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema(bad_id))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc2:
        _run(fkr.get_form_kit_pdf(bad_id))
    assert exc2.value.status_code == 400


def test_valid_kit_id_passes_guard():
    # Sanity: a conventional id is accepted by the guard helper unchanged.
    assert fkr._safe_kit_id("i-90") == "i-90"
    assert fkr._safe_kit_id("form_589") == "form_589"


def test_read_routes_against_real_local_store(tmp_path, monkeypatch):
    """End-to-end against a real LocalFormKitStore over a tmp kit dir.

    The _FakeStore tests above stub the store; this one exercises the actual
    LocalFormKitStore path interpolation + filesystem read (anyio thread) the
    routes use in dev, satisfying the rubric's "verified against a
    LocalFormKitStore" wording (fresh-eyes gap, bd polyglot-pdf-sbfk).
    """
    from backend.services.form_kits import LocalFormKitStore

    schema = {"title": "Form I-90", "fields": [{"id": "a"}]}
    pdf_bytes = b"%PDF-1.7 local"
    kit_dir = tmp_path / "i-90"
    kit_dir.mkdir()
    (kit_dir / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    (kit_dir / "form.pdf").write_bytes(pdf_bytes)

    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    schema_resp = _run(fkr.get_form_kit_schema("i-90"))
    assert schema_resp.media_type == "application/json"
    assert schema_resp.headers["Cache-Control"] == "no-store"
    assert json.loads(schema_resp.body) == schema

    pdf_resp = _run(fkr.get_form_kit_pdf("i-90"))
    assert pdf_resp.media_type == "application/pdf"
    assert pdf_resp.body == pdf_bytes

    # A kit that does not exist on disk -> the store raises FormKitNotFound -> 404.
    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema("absent"))
    assert exc.value.status_code == 404


def test_routes_honor_custom_manifest_filenames(monkeypatch):
    # A kit declaring custom schemaFile/pdfFile (bd snpi) must be read with THOSE
    # names, not the hardcoded defaults (Codex P1 on sbfk).
    manifest = {
        "forms": [
            {"id": "i90", "schemaFile": "custom.json", "pdfFile": "i90.pdf"}
        ]
    }
    store = _FakeStore(manifest=manifest, schema={"ok": True}, pdf=b"%PDF")
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    _run(fkr.get_form_kit_schema("i90"))
    assert store.requested_schema_file == "custom.json"

    _run(fkr.get_form_kit_pdf("i90"))
    assert store.requested_pdf_file == "i90.pdf"


def test_routes_fall_back_to_convention_without_manifest(monkeypatch):
    # No manifest -> conventional schema.json / form.pdf, not a 500.
    store = _FakeStore(manifest=None, schema={"ok": True}, pdf=b"%PDF")
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    _run(fkr.get_form_kit_schema("i90"))
    assert store.requested_schema_file == "schema.json"

    _run(fkr.get_form_kit_pdf("i90"))
    assert store.requested_pdf_file == "form.pdf"


def test_manifest_loaded_but_kit_absent_is_404(monkeypatch):
    # The manifest loads but does not list this kit -> 404, NOT a fallback read.
    # In gcs mode the deploy gate keeps drafts/unmarked kits out of the manifest,
    # so a guessed id must not be served (Codex P1 on sbfk). The store would
    # serve bytes if reached, proving the 404 comes from the allowlist check.
    manifest = {"forms": [{"id": "listed"}]}
    store = _FakeStore(manifest=manifest, schema={"ok": True}, pdf=b"%PDF")
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema("unlisted"))
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc2:
        _run(fkr.get_form_kit_pdf("unlisted"))
    assert exc2.value.status_code == 404


def test_local_store_reads_custom_filename_from_metadata(tmp_path, monkeypatch):
    # A local kit with metadata.json declaring a custom schema/pdf filename must
    # be readable via the routes (Codex P1 on sbfk: local custom-filename kits).
    from backend.services.form_kits import LocalFormKitStore

    schema = {"title": "Custom Kit"}
    kit_dir = tmp_path / "i-90"
    kit_dir.mkdir()
    (kit_dir / "metadata.json").write_text(
        json.dumps({"schema": "custom.json", "pdf": "doc.pdf"}), encoding="utf-8"
    )
    (kit_dir / "custom.json").write_text(json.dumps(schema), encoding="utf-8")
    (kit_dir / "doc.pdf").write_bytes(b"%PDF-1.7 custom")

    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    schema_resp = _run(fkr.get_form_kit_schema("i-90"))
    assert json.loads(schema_resp.body) == schema

    pdf_resp = _run(fkr.get_form_kit_pdf("i-90"))
    assert pdf_resp.body == b"%PDF-1.7 custom"


@pytest.mark.parametrize("bad_id", ["i-90\n", "i-90\r", "i-90\n\n"])
def test_trailing_newline_kit_id_rejected_400(bad_id, monkeypatch):
    # re.match lets `$` match before a trailing newline; fullmatch must reject it
    # (Codex P1 on sbfk). Store would raise if reached, so the 400 is the guard's.
    class _Boom:
        async def load_manifest(self, *a, **k):
            raise AssertionError("store reached for an unsafe kit id")

        async def load_schema(self, *a, **k):
            raise AssertionError("store reached for an unsafe kit id")

    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _Boom())

    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema(bad_id))
    assert exc.value.status_code == 400


def test_local_store_malformed_schema_maps_to_502(tmp_path, monkeypatch):
    # A present-but-unparseable schema in local mode is a STORE error -> 502,
    # not an uncaught 500 (Codex P1 on sbfk).
    from backend.services.form_kits import LocalFormKitStore

    kit_dir = tmp_path / "i-90"
    kit_dir.mkdir()
    (kit_dir / "schema.json").write_text("{ not valid json", encoding="utf-8")

    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema("i-90"))
    assert exc.value.status_code == 502


# --- round-3 fail-closed / validation hardening (Codex P1) ------------------


def test_corrupt_manifest_fails_closed_502(monkeypatch):
    # A manifest that loads-but-can't-be-parsed (FormKitStoreError) must NOT fall
    # back to convention -- that would bypass the allowlist. It maps to 502.
    class _CorruptManifestStore:
        async def load_manifest(self, manifest_file: str = "index.json") -> dict:
            raise FormKitStoreError("corrupt index.json")

        async def load_schema(self, *a, **k):
            raise AssertionError("store schema read reached despite corrupt manifest")

        async def load_pdf_bytes(self, *a, **k):
            raise AssertionError("store pdf read reached despite corrupt manifest")

    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _CorruptManifestStore())

    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema("i-90"))
    assert exc.value.status_code == 502

    with pytest.raises(HTTPException) as exc2:
        _run(fkr.get_form_kit_pdf("i-90"))
    assert exc2.value.status_code == 502


def test_traversal_filename_in_metadata_degrades_to_default(monkeypatch):
    # A listed kit whose manifest carries a traversal schemaFile must NOT escape
    # the kit dir -- _safe_filename degrades it to the conventional schema.json.
    manifest = {"forms": [{"id": "i90", "schemaFile": "../other/schema.json"}]}
    store = _FakeStore(manifest=manifest, schema={"ok": True})
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    _run(fkr.get_form_kit_schema("i90"))
    assert store.requested_schema_file == "schema.json"


def test_safe_filename_helper_rejects_separators_and_traversal():
    assert fkr._safe_filename("custom.json", "schema.json") == "custom.json"
    assert fkr._safe_filename("../x.json", "schema.json") == "schema.json"
    assert fkr._safe_filename("a/b.json", "schema.json") == "schema.json"
    assert fkr._safe_filename("a\\b.json", "schema.json") == "schema.json"
    assert fkr._safe_filename("", "schema.json") == "schema.json"


def test_non_dict_local_metadata_is_ignored(tmp_path, monkeypatch):
    # metadata.json that is valid JSON but a LIST must not crash the manifest /
    # routes -- it is treated as absent, and the kit reads conventionally.
    from backend.services.form_kits import LocalFormKitStore

    schema = {"title": "Listy"}
    kit_dir = tmp_path / "i-90"
    kit_dir.mkdir()
    (kit_dir / "metadata.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    (kit_dir / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    (kit_dir / "form.pdf").write_bytes(b"%PDF")

    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    # Manifest generation must not raise on the non-dict metadata.
    manifest = _run(store.load_manifest())
    assert any(f["id"] == "i-90" for f in manifest["forms"])

    schema_resp = _run(fkr.get_form_kit_schema("i-90"))
    assert json.loads(schema_resp.body) == schema


def test_non_utf8_schema_maps_to_502(tmp_path, monkeypatch):
    # A present schema whose bytes are not valid UTF-8 -> 502, not an uncaught 500.
    from backend.services.form_kits import LocalFormKitStore

    kit_dir = tmp_path / "i-90"
    kit_dir.mkdir()
    (kit_dir / "schema.json").write_bytes(b"\xff\xfe not utf8")

    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema("i-90"))
    assert exc.value.status_code == 502
