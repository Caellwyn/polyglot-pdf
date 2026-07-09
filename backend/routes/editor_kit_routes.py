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

import asyncio
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import weakref
from pathlib import Path
from typing import Annotated, Literal, Optional

import anyio

from fastapi import (
    APIRouter, Body, Depends, File, Form, Header, HTTPException, Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
import structlog

from backend.config import get_settings
from backend.models import conditional_vocabulary as vocab
from backend.models.form_models import FormSchema, FormSource
from backend.routes.form_kit_routes import _safe_kit_id
from backend.services.schema_lint import (
    SEVERITY_ERROR, SEVERITY_WARNING, lint_schema,
)
from backend.services.schema_repair import (
    RepairError, alias_hit_count, repair as repair_schema,
)
from backend.services.widget_picker import unclaimed_button_widgets
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

# extract_form.py's tri-state exit code for a stored-with-issues draft (bd
# polyglot-pdf-v96b, P5.3a). Mirrored here (the extractor runs as a subprocess,
# so the route cannot import the constant); extract_form.EXIT_ISSUES is the
# source of truth and a sync test pins the two equal.
_EXTRACT_EXIT_ISSUES = 3


def _token_matches(supplied: str, expected: str) -> bool:
    """Constant-time token compare over UTF-8 BYTES.

    hmac.compare_digest on str raises TypeError for non-ASCII input, so a
    pasted smart-quote in a wrong access code would turn an auth miss into a
    500 instead of the documented 401 (Codex P1, PR #279). Bytes never raise.
    """
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


async def require_editor_role(
    x_editor_token: Annotated[Optional[str], Header()] = None,
) -> str:
    """FastAPI dependency: resolve the caller's role from X-Editor-Token.

    Returns "author" or "editor". Fail-closed: with NEITHER token configured the
    surface is disabled (503, not open); a missing/wrong token is 401. Tokens are
    compared constant-time over bytes (see _token_matches). The author token
    implies every editor capability, so routes that need only editor accept both.
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
    if author_token and _token_matches(supplied, author_token):
        return ROLE_AUTHOR
    if editor_token and _token_matches(supplied, editor_token):
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


class KitLabelBody(BaseModel):
    """The new display label for a kit (bd 15ic). Whitespace-stripped server-side;
    an empty/blank label is a 422."""
    label: str


class LintFindingOut(BaseModel):
    """One lint finding as the editor's ValidationPanel renders it.

    Mirrors schema_lint.LintFinding.as_dict(): the raw finding fields plus the
    derived field_id (the field the panel focuses on click; null for a
    non-field-anchored finding like a dump widget-claim)."""

    severity: str  # ERROR | WARNING
    rule: str
    path: str
    message: str
    field_id: Optional[str] = None


class LintResponse(BaseModel):
    """Load-time lint report for a schema (bd h76m.11, P4.3).

    findings are in the linter's emission order; counts are the split the panel
    shows in its header. The frontend NEVER runs its own copy of these rules --
    this endpoint is the single Python implementation surfaced to the editor."""

    findings: list[LintFindingOut]
    errorCount: int
    warningCount: int


class RepairResponse(BaseModel):
    """One-click Repair-all result (bd polyglot-pdf-zgln, P5.3b).

    The repaired schema is stored server-side; this reports what changed. The
    `repairs` list + counts mirror the CLI's _bakeoff.authoring.repair block
    (same schema_repair.repair() call, so the output equals the CLI on the same
    input). errorCount/warningCount are the POST-repair lint counts the editor
    re-renders (they should drop toward zero)."""

    applied: int          # substantive repairs that succeeded
    dropped: int          # substantive repairs that dropped data (recorded ERROR)
    aliasHits: int        # invented-operator alias table hit count
    repairs: list[dict]   # the full repair report (verbatim from schema_repair)
    errorCount: int       # lint ERRORs remaining after repair
    warningCount: int     # lint WARNINGs remaining after repair


class UnclaimedWidget(BaseModel):
    """One PDF button widget the schema does not yet claim (bd nivy, P5.3c)."""

    name: str                        # the widget's PDF field name
    type: Optional[str] = None       # checkbox | radio
    on_value: Optional[str] = None   # the widget's non-Off state (-> option.pdf_on_value)
    tooltip: Optional[str] = None    # the /TU tooltip, a suggested label
    page: Optional[int] = None       # 0-indexed page (for the author's orientation)
    # True when this is one kid of a SHARED-name group (one dump name, >1 kid):
    # the option gets pdf_on_value + the FIELD carries pdf_field_name=name. False
    # for a distinct-name widget: the option carries pdf_field_name=name. Putting
    # the shared name on every option's pdf_field_name would trip the widget-claim
    # lint rule (bd nivy fresh-eyes / Opus fallback).
    shared_name: bool = False


class UnclaimedWidgetsResponse(BaseModel):
    """The kit's unclaimed button widgets for the "Add from PDF widgets" picker.

    Empty when the kit has no persisted AcroForm dump (pre-v96b kits) -- the
    picker then simply shows nothing to add."""

    widgets: list[UnclaimedWidget]


def _resolve_meta_names(meta: Optional[dict]) -> tuple[str, str]:
    """(schema_file, pdf_file) from a kit's metadata, defaulted + sanitized."""
    meta = meta if isinstance(meta, dict) else {}
    schema_file = safe_filename(meta.get("schema") or "schema.json", "schema.json")
    pdf_file = safe_filename(meta.get("pdf") or "form.pdf", "form.pdf")
    return schema_file, pdf_file


def _status_of(meta: Optional[dict]) -> str:
    status = (meta or {}).get("status")
    return status if status in ("draft", "complete") else "unknown"


# The kit's persisted AcroForm dump artifact filename (bd polyglot-pdf-v96b). The
# extract route writes it; the promotion-gate lint and the P5.3c widget picker
# read it.
_ACROFORM_ARTIFACT = "acroform.json"


async def _load_kit_dump(store, kit_id: str) -> Optional[dict]:
    """The kit's stored AcroForm dump, or None when absent/unreadable.

    Best-effort: a missing dump (FormKitNotFound) is the common pre-v96b case
    and simply means "no dump" -- callers degrade to the dump-less lint/repair
    path. A present-but-unreadable dump (FormKitStoreError) also degrades to None
    rather than failing the caller: the dump only ENRICHES lint (the widget-claim
    rule); it must never turn a promotable schema un-promotable by being corrupt.
    """
    try:
        dump = await store.load_json_artifact(kit_id, _ACROFORM_ARTIFACT)
    except (FormKitNotFound, FormKitStoreError):
        return None
    return dump if isinstance(dump, dict) else None


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

    A FAILED metadata read (FormKitStoreError) propagates as 502 -- it must NOT
    degrade to None: metadata.status is the GUARD input for the write paths
    (the publish gate refuses saves on complete kits), so suppressing a
    transient read failure would let a save land on a possibly-published kit
    (Codex P1 r2, PR #279). Only the LIST route tolerates unreadable metadata
    (one bad kit must not hide the rest), and it does so with its own catch.
    """
    try:
        files_by_kit = await store.list_kit_files()
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to list kits") from exc
    if kit_id not in files_by_kit:
        raise HTTPException(status_code=404, detail=f"Unknown kit: {kit_id}")
    try:
        meta = await store.load_metadata(kit_id)
    except FormKitStoreError as exc:
        raise HTTPException(
            status_code=502, detail="Unable to read kit metadata"
        ) from exc
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
    # A PUBLISHED (complete) kit's schema blob is exactly what the public read
    # routes stream to voice users, so a lenient draft save over it would go
    # live instantly, bypassing the promote-time validation gate (Codex P1,
    # PR #279). Require the explicit revert-to-draft first -- which unpublishes
    # the kit immediately (the public routes honor live status on the shared
    # store), so work-in-progress never reaches users.
    if _status_of(meta) == "complete":
        raise HTTPException(
            status_code=409,
            detail="This form is published (status complete). Revert it to "
                   "draft first, then edit -- otherwise work-in-progress would "
                   "go live to users immediately.",
        )
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        await store.put_schema(kit_id, schema, schema_file)
    except FormKitStoreError as exc:
        _log.error("editor_schema_save_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to save schema") from exc
    _log.info("editor_schema_saved", kit_id=kit_id, role=role,
              field_count=len(schema.get("fields", [])))
    return {"ok": True, "schemaFile": schema_file}


@router.post("/lint", response_model=LintResponse)
async def lint_editor_schema(
    role: Annotated[str, Depends(require_editor_role)],
    schema: Annotated[dict, Body()],
) -> LintResponse:
    """Lint a schema and return structured findings for load-time display.

    The editor POSTs the schema it currently HOLDS (which may carry unsaved
    edits), not a kit id -- so the panel lints exactly what is on screen, before
    any save, over the same authoritative Python rules the mark-complete
    promotion gate uses (backend/services/schema_lint.py). This is P4.3's "single
    Python implementation": the frontend renders these findings instead of
    maintaining a parallel TS ruleset that could drift from the promotion gate.

    Never 4xx on schema shape -- lint_schema never raises, and a malformed draft
    IS the thing the contractor needs the findings for (a structural problem
    surfaces as a condition-malformed finding, not an HTTP error). No dump is
    passed: this route lints the POSTED schema (no kit id), so it has no kit dump
    to load -- the dump-aware widget-claim rule runs at the kit-scoped gates (the
    extract route + the promotion gate, bd v96b) where the acroform.json artifact
    is available.
    """
    findings = lint_schema(schema)
    out = [LintFindingOut(**f.as_dict()) for f in findings]
    error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    _log.info("editor_schema_linted", role=role,
              errors=error_count, warnings=warning_count)
    return LintResponse(
        findings=out, errorCount=error_count, warningCount=warning_count,
    )


@router.post("/kits/{kit_id}/repair", response_model=RepairResponse)
async def repair_editor_kit(
    kit_id: str,
    role: Annotated[str, Depends(require_author_role)],
) -> RepairResponse:
    """One-click Repair-all for a kit's stored draft (bd polyglot-pdf-zgln, P5.3b).

    Loads the kit's schema + its persisted AcroForm dump (bd v96b) and runs the
    SAME deterministic backend.services.schema_repair.repair() the CLI extraction
    pass runs, so the result equals CLI repair on the same input. The repaired
    schema is stored back; the response reports what changed (mirroring the CLI's
    _bakeoff.authoring.repair block) plus the POST-repair lint counts the editor
    re-renders.

    Author tier: repair MUTATES the stored schema (like extraction), so it needs
    the author code, not the polish-only editor code. RepairError (the draft
    references PDF widgets that do not exist -- repair cannot invent mappings) is
    a 422 CLIENT error naming the widgets, not a 500: a human must fix the
    hallucinated reference. A complete (published) kit is refused (409) -- repair
    would rewrite a live schema; revert to draft first, same as save.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, _files = await _load_meta_or_404(store, kit_id)
    if _status_of(meta) == "complete":
        raise HTTPException(
            status_code=409,
            detail="This form is published (status complete). Revert it to draft "
                   "before repairing -- repair rewrites the schema.",
        )
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no schema to repair"
        ) from exc
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc

    dump_data = await _load_kit_dump(store, kit_id)
    try:
        repaired, repairs = repair_schema(schema, dump_data)
    except RepairError as exc:
        # Hallucinated widgets: repair must NOT paper over them (a 500 would read
        # as a server bug; this is a fixable data defect the author must resolve).
        raise HTTPException(status_code=422, detail=str(exc)[:400]) from exc

    try:
        await store.put_schema(kit_id, repaired, schema_file)
    except FormKitStoreError as exc:
        raise HTTPException(
            status_code=502, detail="Repair succeeded but the schema could not be "
                                    "stored",
        ) from exc

    # Report shape mirrors the CLI's _repair_schema (extract_form.py): substantive
    # repairs split applied/dropped, plus the alias hit count; alias-hit-rate is
    # the meta entry, not a substantive repair.
    substantive = [r for r in repairs if r.get("action") != "alias-hit-rate"]
    applied = sum(1 for r in substantive if not r.get("error"))
    dropped = sum(1 for r in substantive if r.get("error"))

    # Re-lint the repaired schema (dump-aware) so the editor re-renders the
    # remaining findings -- the SAME schema_lint the promotion gate uses.
    findings = lint_schema(repaired, dump_data)
    error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    _log.info("editor_schema_repaired", kit_id=kit_id, role=role,
              applied=applied, dropped=dropped,
              errors_after=error_count, warnings_after=warning_count)
    return RepairResponse(
        applied=applied, dropped=dropped, aliasHits=alias_hit_count(repairs),
        repairs=repairs, errorCount=error_count, warningCount=warning_count,
    )


@router.get("/kits/{kit_id}/unclaimed-widgets",
            response_model=UnclaimedWidgetsResponse)
async def get_unclaimed_widgets(
    kit_id: str,
    role: Annotated[str, Depends(require_author_role)],
) -> UnclaimedWidgetsResponse:
    """The kit's PDF button widgets that no field/option claims (bd nivy, P5.3c).

    Powers the author-tier "Add from PDF widgets" picker: when the extractor
    missed a checkbox/radio box, the box exists in the persisted AcroForm dump
    (acroform.json, bd v96b) but nothing in the schema claims it. This returns
    those unclaimed button widgets so the author can add one to a group.

    Author tier (it feeds an edit that adds a PDF-mapped option -- an author-only
    capability, matching the per-option pdf_field_name editor). A kit with no
    persisted dump (pre-v96b) returns an empty list -- the picker shows nothing.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, _files = await _load_meta_or_404(store, kit_id)
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no schema"
        ) from exc
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc

    dump = await _load_kit_dump(store, kit_id)
    widgets = [UnclaimedWidget(**w) for w in unclaimed_button_widgets(schema, dump)]
    _log.info("editor_unclaimed_widgets", kit_id=kit_id, role=role,
              count=len(widgets), has_dump=dump is not None)
    return UnclaimedWidgetsResponse(widgets=widgets)


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
    meta, files = await _load_meta_or_404(store, kit_id)
    schema_file, pdf_file = _resolve_meta_names(meta)

    if body.status == "complete":
        # The voice app serves BOTH the schema and the PDF of a complete kit;
        # the deploy manifest falls back to a conventional pdf name when none
        # exists, so promoting a PDF-less kit would ship a form whose PDF read
        # 404s in the voice app (Codex P1 r2, PR #279).
        if pdf_file not in files:
            raise HTTPException(
                status_code=409,
                detail=f"Kit has no {pdf_file} -- a complete kit needs its "
                       "form PDF (the voice app serves it)",
            )
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
            parsed = FormSchema.model_validate(schema)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Schema does not validate against the form contract, so "
                       f"it cannot be marked complete: {str(exc)[:400]}",
            ) from exc
        # Pydantic v2 does not run field validators for an OMITTED default, so
        # the model's "extraction_info required for PDF forms" rule never fires
        # on an absent value -- a PDF schema with no extraction metadata would
        # validate. Enforce the documented contract explicitly at the publish
        # gate (Codex P1 r2, PR #279); the extraction pipeline emits it, so a
        # legitimate kit is unaffected.
        if parsed.source == FormSource.PDF and parsed.extraction_info is None:
            raise HTTPException(
                status_code=422,
                detail="Schema is missing extraction_info (required for PDF "
                       "forms), so it cannot be marked complete",
            )
        # v2-only gate (bd h76m.16, P6.2 flip): schema v2 is the only shape a
        # complete kit may carry. The model IGNORES unknown keys (extra="ignore"),
        # so a v2-shaped-but-unstamped schema still carrying a removed trigger-side
        # key (controls_fields / conditional_fields) would slip past both the model
        # AND the is_v2-gated lint below; requiring the stamp here closes that
        # (bd polyglot-pdf-t96a). The extraction + migration pipelines both stamp
        # v2, so a legitimate kit is unaffected.
        if str(schema.get("schema_version")) != vocab.SCHEMA_VERSION_V2:
            raise HTTPException(
                status_code=422,
                detail="Schema is not v2 (schema_version must be \"2\"); migrate "
                       "it before marking complete",
            )
        # Lint gate (bd h76m.5, P2.1): zero lint ERRORs to promote. Pydantic
        # above enforces the wire contract; lint catches the class of defect
        # that PARSES but misbehaves (duplicate option values, unresolved
        # conditional references, invented operators on a v1-stamped draft).
        # This is one half of the two-gate seam: a stored-with-issues draft
        # (P5.3) stays un-promotable until repaired. WARNINGs never block.
        # The AcroForm dump is now a per-kit artifact (bd v96b), so pass it when
        # present -- this closes the dump-only widget-claim rule at the promotion
        # gate too (a missing dump degrades to the dump-less rules, never blocks).
        dump_data = await _load_kit_dump(store, kit_id)
        lint_errors = [
            f for f in lint_schema(schema, dump_data) if f.severity == SEVERITY_ERROR
        ]
        if lint_errors:
            # Cap the finding list BEFORE appending the "and N more" tail so a
            # long list can never truncate away the count of what was elided.
            # Each segment is ALSO capped (~200 chars) before joining: a single
            # finding whose message embeds a very long option value (e.g. a
            # 10KB string) would otherwise eat the whole [:1400] budget on its
            # own, hiding later findings' text within the first 8 (bd
            # polyglot-pdf-tmby nit 1).
            shown = "; ".join(
                f"[{f.rule}] {f.path}: {f.message}"[:200] for f in lint_errors[:8]
            )[:1400]
            more = len(lint_errors) - 8
            if more > 0:
                shown += f"; ... and {more} more"
            raise HTTPException(
                status_code=409,
                detail=f"Schema has {len(lint_errors)} lint error(s), so it "
                       f"cannot be marked complete: {shown}",
            )

    next_meta = {**(meta or {}), "status": body.status}
    try:
        await store.put_metadata(kit_id, next_meta)
    except FormKitStoreError as exc:
        _log.error("editor_status_save_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to update status") from exc
    _log.info("editor_status_set", kit_id=kit_id, status=body.status, role=role)
    return {"ok": True, "status": body.status}


@router.post("/kits/{kit_id}/label")
async def set_editor_kit_label(
    kit_id: str,
    body: KitLabelBody,
    role: Annotated[str, Depends(require_editor_role)],
) -> dict:
    """Rename a kit's DISPLAY label (bd polyglot-pdf-15ic), preserving every
    other metadata key -- the exact read-merge-write shape of the status flip.

    The label is pure display: the catalogue and the voice app's form picker
    render it, but nothing keys on it (the kit's identity is the immutable
    kit_id / storage path). Onboarding derives a label from the PDF filename, so
    nameless uploads collide into "Form", "Form 2", ... -- this lets a human fix
    that after the fact. The identity is deliberately NOT renameable here.
    """
    kit_id = _safe_kit_id(kit_id)
    label = _safe_label(body.label)
    store = get_form_kit_store()
    meta, _files = await _load_meta_or_404(store, kit_id)
    next_meta = {**(meta or {}), "label": label}
    try:
        await store.put_metadata(kit_id, next_meta)
    except FormKitStoreError as exc:
        _log.error("editor_label_save_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to update label") from exc
    _log.info("editor_label_set", kit_id=kit_id, role=role)
    return {"ok": True, "label": label}


# --- author tier: PDF onboarding + hosted extraction (bd polyglot-pdf-92qe.3) --
#
# The (a)-tier contractor permission from the 2026-07-01 goal: collect (upload a
# blank AcroForm PDF into the shared store), extract (run the PDF->schema
# authoring pass server-side), review. Both routes require the AUTHOR role --
# extraction spends paid model tokens and onboarding creates kits, neither of
# which the polish-only editor tier may do.

# Mirror of the editor's deriveFormId (formKitDirectory.ts): a URL-safe kit id
# from an uploaded filename ("Form I-90 (1).pdf" -> "form-i-90-1"). CAPPED well
# under _KIT_ID_RE's 128-char limit: a realistic long download name ("USCIS
# Form I-90 Application to Replace ... Downloaded From ....pdf") would
# otherwise derive a >128-char slug and 400 with a baffling "Invalid kit id"
# (fresh-eyes, reproduced live). 64 chars leaves ample room for the -2/-3
# uniquifier suffixes.
_KIT_ID_MAX_DERIVED = 64


def _derive_kit_id(filename: str) -> str:
    base = re.sub(r"\.pdf$", "", filename or "", flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    slug = slug[:_KIT_ID_MAX_DERIVED].rstrip("-")
    return slug or "form"


def _friendly_label(kit_id: str) -> str:
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), kit_id.replace("-", " ").replace("_", " "))


def _safe_label(raw: str) -> str:
    """Validate a caller-supplied DISPLAY label (bd 15ic); returns it stripped.

    Raises 422 on: blank; >200 chars (a display name, not a document); a double
    quote, backslash, or control character. The character ban is LOAD-BEARING,
    not cosmetic: the deploy scripts extract the label from metadata.json with
    a grep/sed pipeline and splice it into index.json by string concatenation
    (deploy-all.sh / scripts/deploy-form-kit.sh) -- a quote or backslash there
    truncates the extraction and ships INVALID manifest JSON, which the voice
    app cannot parse (no forms would load). Opus review, bd 15ic.
    """
    label = (raw or "").strip()
    if not label:
        raise HTTPException(status_code=422, detail="Label must not be empty")
    if len(label) > 200:
        raise HTTPException(status_code=422, detail="Label too long (max 200 characters)")
    if '"' in label or "\\" in label or any(ord(ch) < 32 for ch in label):
        raise HTTPException(
            status_code=422,
            detail="Label may not contain double quotes, backslashes, or "
                   "control characters",
        )
    return label


# ONE extraction subprocess per instance at a time: each run holds a PDF +
# schema in memory and spawns a Python child; serializing keeps the container's
# memory bounded and makes concurrent-write races on one kit impossible. A
# second author's request queues (the HTTP request waits; Cloud Run's
# --timeout=3600 covers it).
_extract_semaphore = asyncio.Semaphore(1)

# Serialize the onboard list->derive->write window (fresh-eyes, reproduced):
# two concurrent uploads deriving the SAME kit id both read the listing
# snapshot, both uniquify to the same id, and one author's PDF silently
# vanishes behind a false 200. Per-instance serialization closes the reachable
# race (one Cloud Run instance handles a small contractor pool's uploads);
# a cross-instance collision remains theoretically possible and is accepted --
# same-second same-filename uploads from two authors on two instances.
#
# The lock is PER EVENT LOOP (lazy, keyed weakly by the running loop). An
# asyncio.Lock binds to a loop only on a CONTENDED acquire (the uncontended
# fast path never touches the loop check), so a module-level Lock would work
# for most sequential tests -- but any genuinely contended acquire on a second
# loop (the TestClient runs each request on its own) raises RuntimeError. The
# per-loop map removes that trap defensively; under uvicorn (one loop for the
# process) exactly one entry ever exists.
_onboard_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _get_onboard_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _onboard_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _onboard_locks[loop] = lock
    return lock


def _repo_root() -> Path:
    """The checkout/container root: backend/routes/x.py -> two parents up.

    Locally this is the repo root; in the Cloud Run image it is /app (the image
    copies backend/ AND scripts/ under /app -- see backend/Dockerfile).
    """
    return Path(__file__).resolve().parents[2]


async def _read_upload_pdf(pdf: UploadFile, max_mb: float) -> bytes:
    """Read + sanity-check an uploaded PDF (size cap, %PDF magic).

    STREAMED in chunks with the cap enforced as bytes arrive (fresh-eyes): a
    single `await pdf.read()` would materialize an oversized body fully in
    memory before rejecting it. Cloud Run's ~32 MB request ceiling bounds the
    worst case, but check-as-you-read is the right shape regardless.
    """
    limit = int(max_mb * 1024 * 1024)
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await pdf.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"PDF is larger than the {max_mb:g} MB upload limit",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    # Magic-byte check: the `accept` filter client-side is advisory; a renamed
    # HTML page must not land in the store as form.pdf.
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="The file is not a PDF")
    return data


@router.post("/kits", response_model=EditorKitInfo)
async def onboard_editor_kit(
    role: Annotated[str, Depends(require_author_role)],
    pdf: Annotated[UploadFile, File(description="The blank AcroForm PDF")],
    label: Annotated[Optional[str], Form()] = None,
) -> EditorKitInfo:
    """Create a new kit in the shared store from an uploaded form PDF.

    The hosted counterpart of the local catalogue's drag-drop onboarding
    (formKitDirectory.onboardPdf): derive a URL-safe kit id from the filename
    (uniquified with -2/-3... if taken), write form.pdf + metadata.json
    (status draft). No schema yet -- extraction is the separate step.
    """
    settings = get_settings()
    data = await _read_upload_pdf(pdf, settings.EXTRACTOR_MAX_PDF_MB)

    store = get_form_kit_store()
    # The list->derive->write window runs under the onboard lock: without it,
    # two concurrent uploads deriving the same id both pass the uniquifier and
    # one PDF silently loses (fresh-eyes, reproduced live).
    async with _get_onboard_lock():
        try:
            existing = await store.list_kit_files()
        except FormKitStoreError as exc:
            raise HTTPException(status_code=502, detail="Unable to list kits") from exc

        base = _derive_kit_id(pdf.filename or "form")
        kit_id = base
        n = 2
        while kit_id in existing:
            kit_id = f"{base}-{n}"
            n += 1
        # The derived id must survive the same guard every later route applies.
        kit_id = _safe_kit_id(kit_id)

        # A caller-supplied label goes through the same validation as a rename
        # (the deploy-manifest pipeline cannot tolerate quotes/backslashes --
        # see _safe_label); absent/blank falls back to the derived name.
        kit_label = (_safe_label(label) if isinstance(label, str) and label.strip()
                     else _friendly_label(kit_id))
        try:
            await store.put_pdf_bytes(kit_id, data, "form.pdf")
            await store.put_metadata(kit_id, {"label": kit_label, "status": "draft"})
        except FormKitStoreError as exc:
            _log.error("editor_onboard_failed", kit_id=kit_id, error=str(exc))
            raise HTTPException(status_code=502, detail="Unable to store the PDF") from exc

    _log.info("editor_kit_onboarded", kit_id=kit_id, size_bytes=len(data), role=role)
    return EditorKitInfo(
        id=kit_id, label=kit_label, description=None, status="draft",
        hasSchema=False, hasPdf=True, schemaFile="schema.json", pdfFile="form.pdf",
    )


class ExtractResponse(BaseModel):
    ok: bool
    detail: str
    schemaFile: Optional[str] = None
    fieldCount: Optional[int] = None
    # Store-with-issues (bd polyglot-pdf-v96b, P5.3a): a parseable draft with >= 1
    # field is STORED even when it is lint-dirty or invalid, and the response
    # carries the lint counts so the editor surfaces them. storedWithIssues is
    # True exactly when the stored draft has lint ERRORs or failed validation
    # (extractor tri-state exit 3); the draft is un-promotable until repaired
    # (the two-gate seam -- promotion still 409s on lint ERRORs).
    errorCount: int = 0
    warningCount: int = 0
    storedWithIssues: bool = False


@router.post("/kits/{kit_id}/extract", response_model=ExtractResponse)
async def extract_editor_kit(
    kit_id: str,
    role: Annotated[str, Depends(require_author_role)],
    force: Annotated[bool, Form()] = False,
    instructions_pdf: Annotated[Optional[UploadFile], File(
        description="OPTIONAL official instructions PDF; enriches help text"
    )] = None,
) -> ExtractResponse:
    """Run the PDF -> draft-schema authoring pass for a kit, server-side.

    The hosted counterpart of the Vite dev server's /api/extract (which spawns
    the extractor on the maintainer's machine): stream the kit's PDF from the
    store to a temp dir, run scripts/authoring/extract_form.py as a subprocess
    (model = EXTRACTOR_MODEL, a gemini-* model -- the local `claude` CLI does
    not exist in the container).

    STORE-WITH-ISSUES (bd polyglot-pdf-v96b, P5.3a): a parseable draft with >= 1
    field is stored EVEN when it is lint-dirty or fails validation -- the response
    returns 200 carrying the lint counts and a storedWithIssues flag so the editor
    surfaces them and the author repairs in place. Only a hard failure (no usable
    draft: crash, timeout, no JSON, zero fields) is a 5xx. The AcroForm dump is
    persisted as the kit's acroform.json artifact alongside the draft. The draft
    stays UN-PROMOTABLE until repaired -- the two-gate seam: mark-complete still
    409s on lint ERRORs (store != promote).

    Synchronous by design: Cloud Run's --timeout=3600 covers a minutes-long run,
    and the editor shows elapsed progress. Refuses to clobber an existing schema
    unless force=true (the same no-overwrite contract as the dev endpoint).
    """
    kit_id = _safe_kit_id(kit_id)
    settings = get_settings()
    if not (settings.EXTRACTOR_MODEL or "").lower().startswith("gemini"):
        raise HTTPException(
            status_code=503,
            detail="Hosted extraction needs a gemini-* EXTRACTOR_MODEL "
                   "(the local claude CLI is not available on the server)",
        )
    # Extraction is "configured" if it can authenticate to Gemini AT ALL: either
    # Vertex AI (ADC / service account -- how Cloud Run runs, no key) OR an AI
    # Studio key (local dev). The provider picks the same way (llm_providers.py),
    # so this gate must not demand a key when VERTEXAI is on, or it would 503
    # before ever reaching the working Vertex path (bd polyglot-pdf-fyq4).
    if not (settings.VERTEXAI or settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")):
        raise HTTPException(
            status_code=503,
            detail="Hosted extraction is not configured (set VERTEXAI=true for "
                   "service-account auth, or provide a GEMINI_API_KEY)",
        )

    store = get_form_kit_store()
    meta, files = await _load_meta_or_404(store, kit_id)
    schema_file, pdf_file = _resolve_meta_names(meta)
    if pdf_file not in files:
        raise HTTPException(status_code=409, detail=f"Kit {kit_id} has no {pdf_file} to extract from")
    if schema_file in files and not force:
        raise HTTPException(
            status_code=409,
            detail=f'"{schema_file}" already exists for kit "{kit_id}"; re-extracting '
                   "would overwrite it (pass force=true to replace it)",
        )

    script = _repo_root() / "scripts" / "authoring" / "extract_form.py"
    if not script.exists():
        raise HTTPException(
            status_code=503,
            detail="The extraction script is not present on this server "
                   "(the image must include scripts/authoring + scripts/bakeoff)",
        )

    try:
        pdf_bytes = await store.load_pdf_bytes(kit_id, pdf_file)
    except (FormKitNotFound, FormKitStoreError) as exc:
        raise HTTPException(status_code=502, detail="Unable to read the kit PDF") from exc

    instructions_bytes: Optional[bytes] = None
    if instructions_pdf is not None and (instructions_pdf.filename or "") != "":
        instructions_bytes = await _read_upload_pdf(
            instructions_pdf, settings.EXTRACTOR_MAX_PDF_MB
        )

    async with _extract_semaphore:
        tmp_dir = tempfile.mkdtemp(prefix=f"extract_{kit_id}_")
        try:
            tmp = Path(tmp_dir)
            pdf_path = tmp / "form.pdf"
            out_path = tmp / "schema.json"
            # extract_form writes the AcroForm dump next to --out as
            # <out-stem>_acroform.json under --keep-dump; we persist it as the
            # kit's acroform.json artifact (bd v96b) so the promotion gate's
            # dump-widget-claim rule and the P5.3c widget picker can use it.
            dump_out_path = out_path.with_name(out_path.stem + "_acroform.json")
            pdf_path.write_bytes(pdf_bytes)
            cmd = [
                sys.executable, str(script),
                "--pdf", str(pdf_path),
                "--out", str(out_path),
                "--model", settings.EXTRACTOR_MODEL,
                "--keep-dump",
            ]
            if instructions_bytes is not None:
                instructions_path = tmp / "instructions.pdf"
                instructions_path.write_bytes(instructions_bytes)
                cmd += ["--instructions-pdf", str(instructions_path)]

            # Pass the RESOLVED auth mode to the subprocess so the extractor's
            # provider (llm_providers.py) picks the same client the gate above
            # authorized. settings.VERTEXAI is the source of truth (config.py
            # defaults it True when unset); without pinning it here, the child
            # would re-read a possibly-unset VERTEXAI env with the opposite
            # default and could take the key path the gate did not require
            # (bd polyglot-pdf-fyq4).
            child_env = {
                **os.environ,
                "PYTHONUTF8": "1",
                "VERTEXAI": "true" if settings.VERTEXAI else "false",
            }

            def _run() -> subprocess.CompletedProcess:
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=settings.EXTRACTOR_TIMEOUT_SEC,
                    cwd=str(_repo_root()),
                    env=child_env,
                )

            _log.info("editor_extract_start", kit_id=kit_id,
                      model=settings.EXTRACTOR_MODEL,
                      with_instructions=instructions_bytes is not None)
            try:
                proc = await anyio.to_thread.run_sync(_run)
            except subprocess.TimeoutExpired as exc:
                _log.error("editor_extract_timeout", kit_id=kit_id,
                           timeout_s=settings.EXTRACTOR_TIMEOUT_SEC)
                raise HTTPException(
                    status_code=504,
                    detail=f"Extraction timed out after "
                           f"{settings.EXTRACTOR_TIMEOUT_SEC:g}s",
                ) from exc

            lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
            last_line = lines[-1] if lines else "(no output)"
            # Scrub the internal temp paths from the pipeline's detail line on
            # EVERY path -- an INVALID/store-with-issues draft (a common, expected
            # outcome) names the temp --out path in its message, and the detail
            # must not leak internals the clean path scrubs (Opus fallback review,
            # PR #282). Same discipline as the dev endpoint.
            last_line = (last_line
                         .replace(str(out_path), schema_file)
                         .replace(str(tmp), "")
                         .replace(tmp_dir, ""))

            # Store-with-issues (bd v96b): the extractor's tri-state exit code
            # distinguishes a usable-but-imperfect draft (EXIT_ISSUES=3 -> STORE
            # it with its report) from no usable draft (EXIT_HARD_FAIL=1 -> 502).
            # A crash exits with neither 0 nor 3. We ALSO re-derive the floor from
            # the written draft (parseable + >=1 field) rather than trusting the
            # exit code alone, so a mis-exit can never store garbage.
            if not out_path.exists():
                _log.error("editor_extract_failed", kit_id=kit_id,
                           exit_code=proc.returncode, detail=last_line[:400])
                raise HTTPException(
                    status_code=502,
                    detail=f"Extraction failed (exit {proc.returncode}): {last_line[:400]}",
                )

            try:
                schema = json.loads(out_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Extractor wrote an unreadable schema: {exc}",
                ) from exc
            # The store-with-issues FLOOR: a dict carrying at least one FIELD-
            # SHAPED (dict) member in `fields`. Checking only "non-empty list" is
            # not enough (fresh-eyes): a crash mid-write can leave a non-empty
            # list of NON-DICT junk (["a","b"]) that lint_schema silently filters
            # out (so it reports 0 findings) -- storing it would report a false
            # "clean success" with a junk field count. The floor is re-derived
            # from the WRITTEN content (dict members), not the exit code, so a
            # mis-exit can never store garbage. real_fields is reused below for
            # an honest field count.
            real_fields = (
                [f for f in schema["fields"] if isinstance(f, dict)]
                if isinstance(schema, dict) and isinstance(schema.get("fields"), list)
                else []
            )
            if not real_fields:
                _log.error("editor_extract_no_usable_draft", kit_id=kit_id,
                           exit_code=proc.returncode, detail=last_line[:400])
                raise HTTPException(
                    status_code=502,
                    detail="Extractor produced no usable draft (a schema with at "
                           "least one field is required)",
                )

            # Read the extractor's persisted dump. A missing/unreadable dump is
            # the legitimate dump-less path (the store-time lint below and the
            # promotion gate both then run dump-less, so they AGREE); it is only
            # a STORED dump that must stay consistent with the stored schema.
            dump_data: Optional[dict] = None
            if dump_out_path.exists():
                try:
                    dump_data = json.loads(dump_out_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                    dump_data = None

            # Persist the dump artifact BEFORE the schema, and make it FATAL: the
            # dump is the gating input for the dump-widget-multiclaim ERROR at the
            # promotion gate, so a schema stored WITHOUT its dump would let a
            # dump-only error the author saw at store time silently vanish at
            # promotion -- re-opening the two-gate seam (Opus fallback review, PR
            # #323). Dump-first ordering means a dump-write failure 502s before
            # anything is stored (no inconsistent state); a later schema-write
            # failure leaves only an orphan dump, overwritten on the next extract.
            if isinstance(dump_data, dict):
                try:
                    await store.put_json_artifact(
                        kit_id, dump_data, _ACROFORM_ARTIFACT
                    )
                except FormKitStoreError as exc:
                    _log.error("editor_extract_dump_store_failed",
                               kit_id=kit_id, error=str(exc))
                    raise HTTPException(
                        status_code=502,
                        detail="Extraction succeeded but its PDF-widget map could "
                               "not be stored (needed to validate the draft)",
                    ) from exc
            try:
                await store.put_schema(kit_id, schema, schema_file)
            except FormKitStoreError as exc:
                raise HTTPException(
                    status_code=502, detail="Extraction succeeded but the schema "
                                            "could not be stored",
                ) from exc

            # Lint the stored draft (dump-aware when we have it) so the response
            # carries the counts the editor surfaces -- the SAME schema_lint the
            # promotion gate uses, so store-with-issues and promote agree.
            findings = lint_schema(schema, dump_data)
            error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
            warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
            stored_with_issues = (
                proc.returncode == _EXTRACT_EXIT_ISSUES or error_count > 0
            )

            # Count REAL (dict-shaped) fields, not the raw list length -- a list
            # with non-dict junk must not overstate the usable field count in the
            # response/log (fresh-eyes; same root cause as the floor above).
            field_count = len(real_fields)
            _log.info("editor_extract_done", kit_id=kit_id, fields=field_count,
                      role=role, errors=error_count, warnings=warning_count,
                      stored_with_issues=stored_with_issues)
            return ExtractResponse(
                ok=True, detail=last_line, schemaFile=schema_file,
                fieldCount=field_count, errorCount=error_count,
                warningCount=warning_count, storedWithIssues=stored_with_issues,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
