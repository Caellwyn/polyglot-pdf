"""
Form Kit Routes - Backend endpoint for serving form kit manifest

Provides the list of available form kits to the frontend.
The manifest (GET /api/form-kits) is metadata only -- the schema body is never
inlined there. The single-kit READ routes below (GET /api/form-kits/{kit_id}/schema
and .../pdf) stream a specific kit's schema JSON and PDF bytes from the store; in
GCS mode nothing else serves those bytes to the browser (the manifest returns
storage PATHS, but no host route backs them -- bd polyglot-pdf-sbfk).
"""

import re
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

from backend.services.form_kits import (
    FormKitNotFound,
    FormKitStoreError,
    get_form_kit_store,
)

_log = structlog.get_logger().bind(module="form_kit_routes")

router = APIRouter(prefix="/api", tags=["form-kits"])

# A kit id is a single bucket/path segment. Restrict it to a conservative charset
# and forbid traversal so a hostile id (e.g. "../../secret") cannot escape the
# store's prefix/root when it is interpolated into a blob path or filesystem path
# (bd polyglot-pdf-sbfk). Used by every {kit_id} route.
_KIT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _safe_kit_id(kit_id: str) -> str:
    """Return kit_id if it is a safe single path segment, else raise HTTP 400.

    Uses fullmatch (not match): with `match` the `$` anchor matches just before a
    trailing newline, so `i-90\n` would pass and reach the store -- fullmatch
    anchors both ends and rejects it (Codex P1 on bd polyglot-pdf-sbfk).
    """
    if ".." in kit_id or not _KIT_ID_RE.fullmatch(kit_id):
        raise HTTPException(status_code=400, detail="Invalid kit id")
    return kit_id


async def _resolve_kit_filenames(store, kit_id: str) -> tuple[str, str]:
    """Return (schema_file, pdf_file) for a kit, honoring custom manifest names.

    The manifest is the ALLOWLIST. `store.load_manifest()` returns a NORMALIZED
    shape (validated + sanitized at the store boundary by `normalize_manifest`),
    so this resolver trusts it: `forms` is a list of dicts whose `id`/`schemaFile`/
    `pdfFile` are safe strings. A kit may declare a custom schema/pdf filename
    (bd polyglot-pdf-snpi); these routes use the manifest's name. Three cases:

    - **Manifest loads but does NOT list kit_id -> FormKitNotFound (404).** The GCS
      deploy gate keeps draft/unmarked kits out of the manifest, so serving a
      guessed id would leak an object the public list never advertised. Draft
      access for the contractor editor is a separate token-gated route (Bead 2).
    - **Manifest MISSING (FormKitNotFound from load_manifest) -> fall back to
      convention ONLY if `store.allow_convention_fallback`.** Local mode (True)
      synthesizes its manifest from disk, so "missing" just means an empty root.
      GCS (False) FAILS CLOSED: a missing index.json (partial deploy/deletion)
      must not reopen convention reads of unlisted/draft blobs (Codex P1, round 5).
    - **Manifest present but UNREADABLE/corrupt (FormKitStoreError) -> propagate
      (502).** `normalize_manifest` raises this for a non-object manifest or a
      non-list `forms`; not caught here, so the route fails closed.
    """
    schema_file, pdf_file = "schema.json", "form.pdf"
    try:
        manifest = await store.load_manifest()
    except FormKitNotFound:
        if getattr(store, "allow_convention_fallback", True):
            return schema_file, pdf_file
        # GCS with no index.json: fail closed rather than allow a guessed read.
        raise
    # A FormKitStoreError (corrupt/unreadable manifest) is NOT caught here: it
    # propagates so the route fails closed with 502. The shape below is guaranteed
    # by normalize_manifest, so no per-entry type guards are needed.
    for form in manifest["forms"]:
        if form["id"] == kit_id:
            return form["schemaFile"], form["pdfFile"]
    # Manifest loaded but this kit is not in it -> not served (404, not fallback).
    raise FormKitNotFound(f"Kit not in manifest: {kit_id}")


class FormKitInfo(BaseModel):
    """Public metadata about a form kit (no schema content).

    schema_path / pdf_path are the manifest-relative URLs the client fetches to
    load the kit's schema and PDF. They carry the kit's REAL filenames (a kit may
    declare a custom schema filename via metadata.json -- bd polyglot-pdf-snpi), so
    the client must use these rather than reconstructing `/<id>/schema.json`, which
    would 404 for a custom-schema kit. These are public storage paths, not schema
    CONTENT -- the schema body is still never inlined here.
    """
    id: str
    label: str
    description: Optional[str] = None
    schema_path: Optional[str] = None
    pdf_path: Optional[str] = None


class FormKitManifestResponse(BaseModel):
    """Response containing list of available form kits"""
    forms: List[FormKitInfo]


@router.get("/form-kits", response_model=FormKitManifestResponse)
async def list_form_kits() -> FormKitManifestResponse:
    """
    List available form kits.

    Returns metadata only - schemas are not exposed directly.
    Frontend uses this to populate form selector in onboarding modal.
    """
    store = get_form_kit_store()
    _log.info("form_kits_list_request")

    try:
        manifest = await store.load_manifest()

        # `manifest` is NORMALIZED by the store (normalize_manifest): forms is a
        # list of dicts whose id/label/schemaPath/pdfPath are safe strings, so this
        # route needs no per-entry type guards. Each carries the kit's REAL storage
        # paths (a custom schema filename loads -- bd polyglot-pdf-snpi).
        forms = [
            FormKitInfo(
                id=form["id"],
                label=form["label"],
                description=form["description"],
                schema_path=form["schemaPath"],
                pdf_path=form["pdfPath"],
            )
            for form in manifest["forms"]
        ]

        _log.info("form_kits_list_success", count=len(forms))
        return FormKitManifestResponse(forms=forms)

    except FormKitNotFound as exc:
        _log.error("form_kits_manifest_not_found", error=str(exc))
        # Return empty list if no manifest (graceful degradation)
        return FormKitManifestResponse(forms=[])
    except FormKitStoreError as exc:
        _log.error("form_kits_list_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to load form kit manifest") from exc


@router.get("/form-kits/{kit_id}/schema")
async def get_form_kit_schema(kit_id: str) -> JSONResponse:
    """Return a single kit's schema JSON, streamed from the store.

    Works in both local and gcs mode. `Cache-Control: no-store` so a re-pull
    after the contractor (or maintainer) saves a new version is never stale.
    The schema filename is resolved from the manifest (custom filenames per
    bd polyglot-pdf-snpi are honored), falling back to the conventional
    `schema.json`.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    try:
        schema_file, _ = await _resolve_kit_filenames(store, kit_id)
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Schema not found for kit {kit_id}") from exc
    except FormKitStoreError as exc:
        _log.error("form_kit_schema_load_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc

    return JSONResponse(content=schema, headers={"Cache-Control": "no-store"})


@router.get("/form-kits/{kit_id}/pdf")
async def get_form_kit_pdf(kit_id: str) -> Response:
    """Return a single kit's PDF bytes, streamed from the store.

    Works in both local and gcs mode. The PDF filename is resolved from the
    manifest (custom filenames are honored), falling back to `form.pdf`.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    try:
        _, pdf_file = await _resolve_kit_filenames(store, kit_id)
        data = await store.load_pdf_bytes(kit_id, pdf_file)
    except FormKitNotFound as exc:
        raise HTTPException(status_code=404, detail=f"PDF not found for kit {kit_id}") from exc
    except FormKitStoreError as exc:
        _log.error("form_kit_pdf_load_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to load PDF") from exc

    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store"},
    )
