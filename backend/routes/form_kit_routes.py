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
    """Return kit_id if it is a safe single path segment, else raise HTTP 400."""
    if ".." in kit_id or not _KIT_ID_RE.match(kit_id):
        raise HTTPException(status_code=400, detail="Invalid kit id")
    return kit_id


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

        # Extract public metadata: id, label, description, and the storage PATHS
        # (not the schema CONTENT). The paths are needed so a kit with a custom
        # schema filename loads (bd polyglot-pdf-snpi); reconstructing
        # `/<id>/schema.json` client-side 404s for such a kit. Fall back to the
        # conventional paths when the manifest entry omits them (older manifests).
        forms = []
        for form in manifest.get("forms", []):
            kit_id = form.get("id", "")
            forms.append(FormKitInfo(
                id=kit_id,
                label=form.get("label", form.get("id", "Unknown")),
                description=form.get("description"),
                schema_path=form.get("schemaPath") or f"/form-kits/{kit_id}/schema.json",
                pdf_path=form.get("pdfPath") or f"/form-kits/{kit_id}/form.pdf",
            ))

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
    The schema filename defaults to the conventional `schema.json`; custom
    filenames are resolved by the manifest path on the public list route, and
    will be wired here once the store exposes metadata (bd polyglot-pdf, Bead 2).
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    try:
        schema = await store.load_schema(kit_id)
    except FormKitNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Schema not found for kit {kit_id}") from exc
    except FormKitStoreError as exc:
        _log.error("form_kit_schema_load_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc

    return JSONResponse(content=schema, headers={"Cache-Control": "no-store"})


@router.get("/form-kits/{kit_id}/pdf")
async def get_form_kit_pdf(kit_id: str) -> Response:
    """Return a single kit's PDF bytes, streamed from the store.

    Works in both local and gcs mode. The PDF filename defaults to the
    conventional `form.pdf`.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    try:
        data = await store.load_pdf_bytes(kit_id, "form.pdf")
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
