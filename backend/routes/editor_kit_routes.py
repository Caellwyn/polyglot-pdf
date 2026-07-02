"""
Editor Kit Routes -- the token-gated read/write surface for the hosted schema
editor (bd polyglot-pdf-92qe.1).

The public /api/form-kits* routes (form_kit_routes.py) serve the VOICE app and
are manifest-gated: in GCS mode they never list or serve a draft kit. The hosted
schema-editor needs the opposite -- a contractor's job IS the drafts: see them,
edit their schemas, flip their status. So this is a separate surface that
enumerates the store directly (list_kit_files + per-kit metadata.json),
bypassing the complete-only manifest ON PURPOSE, and gated by a shared-secret
token instead of being public.

Two access tiers (the 2026-07-01 goal's contractor permission levels), each its
own token, both sent as the X-Editor-Token header:

  - editor (SCHEMA_EDITOR_TOKEN): list/read kits incl. drafts, save schemas,
    flip status -- the "polish a provided collection" contractor.
  - author (SCHEMA_AUTHOR_TOKEN): everything editor can do; onboarding + hosted
    extraction routes (bd 92qe.3) additionally require this role.

Fail-closed: 503 when the server has no tokens configured (the surface is off,
not open), 401 on mismatch, compared with hmac.compare_digest. A shared secret
(not per-user auth) is the approved 92qe design: it stops drive-by writes to the
public Cloud Run service for a small set of trusted contractors; rotate by
changing the secret.

Status semantics: marking a kit `complete` is the publish gate the deploy keys
on, so THAT transition validates the schema against the canonical Pydantic
FormSchema -- a contractor cannot promote a structurally-broken schema. Draft
saves stay lenient (work-in-progress is allowed to be incomplete).
"""

import hmac
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
import structlog

from backend.config import get_settings
from backend.models.form_models import FormSchema
from backend.routes.form_kit_routes import _safe_kit_id
from backend.services.form_kits import (
    FormKitNotFound,
    FormKitStoreError,
    get_form_kit_store,
    safe_filename,
)

_log = structlog.get_logger().bind(module="editor_kit_routes")

router = APIRouter(prefix="/api/editor", tags=["editor-kits"])

# Role constants (author strictly includes editor).
ROLE_EDITOR = "editor"
ROLE_AUTHOR = "author"


async def require_editor_role(
    x_editor_token: Annotated[Optional[str], Header()] = None,
) -> str:
    """FastAPI dependency: resolve the caller's role from X-Editor-Token.

    Returns "author" or "editor". Fail-closed: with NEITHER token configured the
    surface is disabled (503, not open); a missing/wrong token is 401. Tokens are
    compared with hmac.compare_digest (constant-time). The author token implies
    every editor capability, so routes that need only editor accept both.
    """
    settings = get_settings()
    editor_token = settings.SCHEMA_EDITOR_TOKEN
    author_token = settings.SCHEMA_AUTHOR_TOKEN
    if not editor_token and not author_token:
        raise HTTPException(
            status_code=503,
            detail="The editor surface is not configured on this server",
        )
    supplied = x_editor_token or ""
    if author_token and hmac.compare_digest(supplied, author_token):
        return ROLE_AUTHOR
    if editor_token and hmac.compare_digest(supplied, editor_token):
        return ROLE_EDITOR
    raise HTTPException(status_code=401, detail="Invalid or missing access code")


async def require_author_role(
    role: Annotated[str, Depends(require_editor_role)],
) -> str:
    """Author-only gate (onboard/extract routes, bd 92qe.3). 403 for editor."""
    if role != ROLE_AUTHOR:
        raise HTTPException(
            status_code=403,
            detail="This action needs the author access code",
        )
    return role


class EditorSessionResponse(BaseModel):
    role: str


class EditorKitInfo(BaseModel):
    """One kit as the editor catalogue sees it -- mirrors the local editor's
    CatalogueEntry (schema-editor formKitDirectory.ts) minus the directory
    handle, so the hosted catalogue renders from the same shape."""

    id: str
    label: str
    description: Optional[str] = None
    status: str  # draft | complete | unknown
    hasSchema: bool
    hasPdf: bool
    schemaFile: str
    pdfFile: str


class EditorKitListResponse(BaseModel):
    kits: list[EditorKitInfo]


class KitStatusBody(BaseModel):
    status: Literal["draft", "complete"]


def _resolve_meta_names(meta: Optional[dict]) -> tuple[str, str]:
    """(schema_file, pdf_file) from a kit's metadata, defaulted + sanitized."""
    meta = meta if isinstance(meta, dict) else {}
    schema_file = safe_filename(meta.get("schema") or "schema.json", "schema.json")
    pdf_file = safe_filename(meta.get("pdf") or "form.pdf", "form.pdf")
    return schema_file, pdf_file


def _status_of(meta: Optional[dict]) -> str:
    status = (meta or {}).get("status")
    return status if status in ("draft", "complete") else "unknown"


@router.get("/session", response_model=EditorSessionResponse)
async def editor_session(
    role: Annotated[str, Depends(require_editor_role)],
) -> EditorSessionResponse:
    """Access-code probe: the hosted editor calls this once after code entry to
    learn the caller's role (author-only UI is gated on it) and to validate the
    code before any kit traffic."""
    return EditorSessionResponse(role=role)


@router.get("/kits", response_model=EditorKitListResponse)
async def list_editor_kits(
    role: Annotated[str, Depends(require_editor_role)],
) -> EditorKitListResponse:
    """Every kit in the store, DRAFTS INCLUDED -- the contractor work list.

    Built from one storage listing (list_kit_files) + each kit's metadata.json,
    never from the complete-only index.json manifest. A kit whose metadata is
    missing/unreadable still lists (status unknown, conventional filenames) --
    one malformed kit must not hide the rest.
    """
    store = get_form_kit_store()
    try:
        files_by_kit = await store.list_kit_files()
    except FormKitStoreError as exc:
        _log.error("editor_kits_list_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to list kits") from exc

    kits: list[EditorKitInfo] = []
    for kit_id in sorted(files_by_kit):
        # Skip ids the single-kit routes would reject (defense in depth: such a
        # folder could never be opened, so listing it would be a dead card).
        try:
            _safe_kit_id(kit_id)
        except HTTPException:
            continue
        try:
            meta = await store.load_metadata(kit_id)
        except FormKitStoreError:
            meta = None  # unreadable metadata -> list with unknowns, don't 502
        schema_file, pdf_file = _resolve_meta_names(meta)
        names = set(files_by_kit[kit_id])
        label = (meta or {}).get("label")
        description = (meta or {}).get("description")
        kits.append(
            EditorKitInfo(
                id=kit_id,
                label=label if isinstance(label, str) and label else kit_id,
                description=description if isinstance(description, str) else None,
                status=_status_of(meta),
                hasSchema=schema_file in names,
                hasPdf=pdf_file in names,
                schemaFile=schema_file,
                pdfFile=pdf_file,
            )
        )
    _log.info("editor_kits_listed", count=len(kits), role=role)
    return EditorKitListResponse(kits=kits)


async def _load_meta_or_404(store, kit_id: str) -> tuple[Optional[dict], set[str]]:
    """The kit's (metadata, filenames) -- 404 when the kit isn't in the store.

    Existence = presence in the storage listing (a kit is its folder), NOT
    presence in the manifest: drafts are exactly the kits the editor works on.
    """
    try:
        files_by_kit = await store.list_kit_files()
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to list kits") from exc
    if kit_id not in files_by_kit:
        raise HTTPException(status_code=404, detail=f"Unknown kit: {kit_id}")
    try:
        meta = await store.load_metadata(kit_id)
    except FormKitStoreError:
        meta = None
    return meta, set(files_by_kit[kit_id])


@router.get("/kits/{kit_id}/schema")
async def get_editor_kit_schema(
    kit_id: str,
    role: Annotated[str, Depends(require_editor_role)],
) -> JSONResponse:
    """A kit's schema for editing -- unlike the public route this serves DRAFTS
    (filenames resolved from the kit's own metadata, not the manifest)."""
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, _ = await _load_meta_or_404(store, kit_id)
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no schema yet"
        ) from exc
    except FormKitStoreError as exc:
        _log.error("editor_schema_load_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc
    return JSONResponse(content=schema, headers={"Cache-Control": "no-store"})


@router.get("/kits/{kit_id}/pdf")
async def get_editor_kit_pdf(
    kit_id: str,
    role: Annotated[str, Depends(require_editor_role)],
) -> Response:
    """A kit's PDF bytes for the editor's viewer (drafts included)."""
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, _ = await _load_meta_or_404(store, kit_id)
    _schema, pdf_file = _resolve_meta_names(meta)
    try:
        data = await store.load_pdf_bytes(kit_id, pdf_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no PDF"
        ) from exc
    except FormKitStoreError as exc:
        _log.error("editor_pdf_load_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to load PDF") from exc
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store"},
    )


@router.put("/kits/{kit_id}/schema")
async def save_editor_kit_schema(
    kit_id: str,
    role: Annotated[str, Depends(require_editor_role)],
    schema: Annotated[dict, Body()],
) -> dict:
    """Save a contractor's edited schema back to the store (the hosted Cmd+S).

    Lenient by design -- a draft mid-polish may be incomplete -- but never
    formless: it must be a JSON object with a `fields` list (the minimum the
    editor itself can reopen). Full FormSchema validation runs at the
    mark-complete gate, not here. Writes only to EXISTING kits (the kit's own
    schema filename from its metadata); creating kits is the author-tier
    onboarding route (bd 92qe.3).
    """
    kit_id = _safe_kit_id(kit_id)
    if not isinstance(schema.get("fields"), list):
        raise HTTPException(
            status_code=422,
            detail="Schema must be a JSON object with a 'fields' list",
        )
    store = get_form_kit_store()
    meta, _ = await _load_meta_or_404(store, kit_id)
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        await store.put_schema(kit_id, schema, schema_file)
    except FormKitStoreError as exc:
        _log.error("editor_schema_save_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to save schema") from exc
    _log.info("editor_schema_saved", kit_id=kit_id, role=role,
              field_count=len(schema.get("fields", [])))
    return {"ok": True, "schemaFile": schema_file}


@router.post("/kits/{kit_id}/status")
async def set_editor_kit_status(
    kit_id: str,
    body: KitStatusBody,
    role: Annotated[str, Depends(require_editor_role)],
) -> dict:
    """Flip a kit's status (draft <-> complete), preserving other metadata keys.

    `complete` is the PUBLISH gate: the deploy ships only complete kits to the
    voice app, so that transition requires a schema that exists AND validates
    against the canonical FormSchema -- a broken schema surfaces here, to the
    person who can fix it, not later in the voice app. Reverting to draft is
    unconditional.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, _files = await _load_meta_or_404(store, kit_id)
    schema_file, _pdf = _resolve_meta_names(meta)

    if body.status == "complete":
        try:
            schema = await store.load_schema(kit_id, schema_file)
        except FormKitNotFound as exc:
            raise HTTPException(
                status_code=409,
                detail="Kit has no schema yet -- extract and save one before "
                       "marking it complete",
            ) from exc
        except FormKitStoreError as exc:
            raise HTTPException(
                status_code=502, detail="Unable to load schema"
            ) from exc
        try:
            FormSchema.model_validate(schema)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Schema does not validate against the form contract, so "
                       f"it cannot be marked complete: {str(exc)[:400]}",
            ) from exc

    next_meta = {**(meta or {}), "status": body.status}
    try:
        await store.put_metadata(kit_id, next_meta)
    except FormKitStoreError as exc:
        _log.error("editor_status_save_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to update status") from exc
    _log.info("editor_status_set", kit_id=kit_id, status=body.status, role=role)
    return {"ok": True, "status": body.status}
