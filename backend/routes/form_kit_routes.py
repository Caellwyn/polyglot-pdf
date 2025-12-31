"""
Form Kit Routes - Backend endpoint for serving form kit manifest

Provides the list of available form kits to the frontend.
Schemas are protected (not directly exposed) - frontend gets metadata only.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

from backend.services.form_kits import (
    FormKitNotFound,
    FormKitStoreError,
    get_form_kit_store,
)

_log = structlog.get_logger().bind(module="form_kit_routes")

router = APIRouter(prefix="/api", tags=["form-kits"])


class FormKitInfo(BaseModel):
    """Public metadata about a form kit (no schema content)"""
    id: str
    label: str
    description: Optional[str] = None


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

        # Extract only public metadata (id, label, description)
        # Do NOT expose schema paths or PDF paths
        forms = []
        for form in manifest.get("forms", []):
            forms.append(FormKitInfo(
                id=form.get("id", ""),
                label=form.get("label", form.get("id", "Unknown")),
                description=form.get("description"),
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
