"""
Unit tests for the /api/form-kits route (bd polyglot-pdf-snpi).

The route must surface each kit's REAL schema/pdf storage paths from the manifest
so a kit declaring a custom schema filename loads -- the client must not
reconstruct `/<id>/schema.json`, which 404s for a custom-schema kit. When a
manifest entry omits the paths (older manifest), the route falls back to the
conventional `/form-kits/<id>/schema.json` and `/form-kits/<id>/form.pdf`.
"""
import asyncio

import backend.routes.form_kit_routes as fkr


class _FakeStore:
    def __init__(self, manifest):
        self._manifest = manifest

    async def load_manifest(self, manifest_file: str = "index.json") -> dict:
        return self._manifest


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
