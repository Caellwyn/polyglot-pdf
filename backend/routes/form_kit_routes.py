"""
Form Kit Routes - Backend endpoint for serving form kit manifest

Provides the list of available form kits to the frontend.
The manifest (GET /api/form-kits) is metadata only -- the schema body is never
inlined there. The single-kit READ routes below (GET /api/form-kits/{kit_id}/schema
and .../pdf) stream a specific kit's schema JSON and PDF bytes from the store; in
GCS mode nothing else serves those bytes to the browser (the manifest returns
storage PATHS, but no host route backs them -- bd polyglot-pdf-sbfk).
"""

import asyncio
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

from backend.services.auth import require_auth, verify_token
from backend.services.form_kits import (
    FormKitNotFound,
    FormKitStoreError,
    get_form_kit_store,
)
from backend.services.kit_gates import (
    firm_allowed_kits as _firm_allowed_kits,
    is_safe_marker,
    kit_visibility as _kit_visibility,  # noqa: F401 (re-exported for tests/docs symmetry)
    load_live_metadata as _load_live_metadata,
    require_published as _require_published,
    require_visible as _require_visible,
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
    # Explicit filenames (bd polyglot-pdf-vccy): the client must NOT derive
    # these by splitting the URLs above -- for a PRIVATE kit the paths are the
    # authenticated backend routes (".../schema", ".../pdf"), whose last
    # segment is a literal route word, and /api/fill-pdf needs the kit's REAL
    # pdf filename (store.load_pdf_bytes(kit_id, filename)).
    schema_file: Optional[str] = None
    pdf_file: Optional[str] = None


class FormKitManifestResponse(BaseModel):
    """Response containing list of available form kits"""
    forms: List[FormKitInfo]


@router.get("/form-kits", response_model=FormKitManifestResponse)
async def list_form_kits(user: dict = Depends(require_auth)) -> FormKitManifestResponse:
    """
    List available form kits.

    Returns metadata only - schemas are not exposed directly.
    Frontend uses this to populate form selector in onboarding modal.
    Auth-gated (bd polyglot-pdf-z2is); VFF_DISABLE_AUTH bypasses for local dev.
    """
    store = get_form_kit_store()
    _log.info("form_kits_list_request")

    try:
        manifest = await store.load_manifest()

        # `manifest` is NORMALIZED by the store (normalize_manifest): forms is a
        # list of dicts whose id/label/schemaPath/pdfPath are safe strings, so this
        # route needs no per-entry type guards. Each carries the kit's REAL storage
        # paths (a custom schema filename loads -- bd polyglot-pdf-snpi).
        entries = manifest["forms"]

        # ONE live-metadata gather per listed kit, feeding BOTH filters below.
        # Visibility must come from LIVE metadata when the store can supply it
        # (the GCS index.json is baked at deploy time and can be stale); the
        # normalized manifest entry is the fallback for stores without a
        # metadata loader (test doubles).
        loader = getattr(store, "load_metadata", None)
        if loader is not None:
            metas = await asyncio.gather(*(loader(form["id"]) for form in entries))
        else:
            metas = [None] * len(entries)

        # On stores enforcing live-status reads (GCS), drop entries whose kit is
        # no longer complete -- a contractor reverting a published kit to draft
        # must ALSO vanish from this list, or the voice app would offer a form
        # whose schema read now 404s (the single-kit gate below).
        if getattr(store, "enforce_complete_on_public_reads", False):
            kept = [
                (form, meta) for form, meta in zip(entries, metas)
                if isinstance(meta, dict) and meta.get("status") == "complete"
            ]
        else:
            kept = list(zip(entries, metas))

        # Firm-scoped visibility (bd polyglot-pdf-vccy): a requester sees kits
        # that are (public OR kit_id in their firm's allowed_kits). The firm
        # allowlist is resolved LAZILY -- an all-public catalogue never pays
        # the Firestore read.
        firm_allowed = None
        visible = []
        for form, meta in kept:
            # SAME verdict function as the single-kit/fill gates
            # (kit_gates.kit_visibility) -- Opus r2 caught the asymmetry: a
            # manifest-entry fallback here answered the visibility question
            # differently than the gates when live metadata was absent. Live
            # metadata is the ONLY source; a store with no loader lists
            # everything public, exactly as its single-kit reads serve it.
            if _kit_visibility(meta) != "private":
                visible.append((form, False))
                continue
            if firm_allowed is None:
                firm_allowed = await _firm_allowed_kits(user)
            if form["id"] in firm_allowed:
                visible.append((form, True))

        forms = []
        for form, is_private in visible:
            if is_private:
                # Rewrite private kits' paths to the authenticated backend
                # routes: the static Hosting bundle excludes private kits
                # (bd polyglot-pdf-kkos -- kitPublishFilter.isPubliclyServable
                # ships only complete AND public), so their baked static
                # paths would 404. This route is THE per-request rewrite
                # site: it already holds the caller's decoded claims
                # (sprint-19 plan; normalize_manifest is a firm-agnostic
                # store-boundary validator and must not do this). The viewer
                # attaches its Bearer token on /api/ paths.
                schema_path = f"/api/form-kits/{form['id']}/schema"
                pdf_path = f"/api/form-kits/{form['id']}/pdf"
            else:
                schema_path = form["schemaPath"]
                pdf_path = form["pdfPath"]
            forms.append(
                FormKitInfo(
                    id=form["id"],
                    label=form["label"],
                    description=form["description"],
                    schema_path=schema_path,
                    pdf_path=pdf_path,
                    schema_file=form.get("schemaFile"),
                    pdf_file=form.get("pdfFile"),
                )
            )

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
async def get_form_kit_schema(kit_id: str, user: dict = Depends(require_auth)) -> JSONResponse:
    """Return a single kit's schema JSON, streamed from the store.

    Works in both local and gcs mode. `Cache-Control: no-store` so a re-pull
    after the contractor (or maintainer) saves a new version is never stale.
    The schema filename is resolved from the manifest (custom filenames per
    bd polyglot-pdf-snpi are honored), falling back to the conventional
    `schema.json`.
    Auth-gated (bd polyglot-pdf-z2is); VFF_DISABLE_AUTH bypasses for local
    dev. Firm-scoped (bd polyglot-pdf-vccy): a PRIVATE kit 404s unless the
    caller's firm_id claim resolves to an allowlist containing it -- same
    invisibility contract as the pdf route below.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    try:
        schema_file, _ = await _resolve_kit_filenames(store, kit_id)
        meta = await _load_live_metadata(store, kit_id)
        _require_published(store, kit_id, meta)
        await _require_visible(kit_id, meta, user)
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Schema not found for kit {kit_id}") from exc
    except FormKitStoreError as exc:
        _log.error("form_kit_schema_load_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc

    return JSONResponse(content=schema, headers={"Cache-Control": "no-store"})


@router.get("/form-kits/{kit_id}/pdf")
async def get_form_kit_pdf(
    kit_id: str, authorization: Optional[str] = Header(None)
) -> Response:
    """Return a single kit's PDF bytes, streamed from the store.

    Works in both local and gcs mode. The PDF filename is resolved from the
    manifest (custom filenames are honored), falling back to `form.pdf`.

    PUBLIC kits: deliberately unauthenticated (bd polyglot-pdf-z2is) -- a
    public kit's blank-template bytes ship publicly in the Hosting bundle
    regardless, so gating this read would protect nothing. PRIVATE kits
    (bd polyglot-pdf-vccy -- the "revisit when kits become firm-scoped" this
    comment used to promise): the auth header is parsed OPTIONALLY; a valid
    Firebase ID token whose firm_id claim resolves to an allowlist containing
    this kit passes, anything else -- no header, an invalid token, the wrong
    firm -- 404s exactly like a nonexistent kit (invisibility, not 401: the
    kit's existence is the secret). The viewer sends the Bearer header on
    /api/ pdf paths (usePDFDocument's header-carrying fetch).
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    # Optional auth: resolve a user if a plausible Bearer token is present;
    # an invalid one degrades to anonymous (NOT 401 -- see docstring).
    user: Optional[dict] = None
    # isinstance, not truthiness: a DIRECT call (tests) leaves the Header()
    # default object in the parameter, which is truthy but not a str.
    if isinstance(authorization, str) and authorization.lower().startswith("bearer "):
        try:
            user = verify_token(authorization[7:].strip())
        except HTTPException:
            user = None
    try:
        _, pdf_file = await _resolve_kit_filenames(store, kit_id)
        meta = await _load_live_metadata(store, kit_id)
        _require_published(store, kit_id, meta)
        await _require_visible(kit_id, meta, user)
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


# The marker contract lives in kit_gates.is_safe_marker (ONE definition for
# the client + editor archive routes); this wrapper only maps refusal to 400
# (same discipline as _safe_kit_id -- a hostile marker never reaches the
# store as a path segment).
def _safe_marker(marker: str) -> str:
    if not is_safe_marker(marker):
        raise HTTPException(status_code=400, detail="Invalid revision marker")
    return marker


class ArchivedRevisionInfo(BaseModel):
    """One superseded revision of a kit (bd polyglot-pdf-qfyxr).

    marker is the ENCODED archive marker (the path segment under
    <kit>/_archive/); published_at is the archived metadata snapshot's stamp,
    None when the snapshot predates the stamp or is missing.
    """
    marker: str
    published_at: Optional[str] = None


class KitArchiveResponse(BaseModel):
    revisions: List[ArchivedRevisionInfo]


@router.get("/form-kits/{kit_id}/archive", response_model=KitArchiveResponse)
async def list_kit_archive(
    kit_id: str, user: dict = Depends(require_auth)
) -> KitArchiveResponse:
    """A kit's superseded revisions, NEWEST FIRST (bd polyglot-pdf-qfyxr).

    The firm-facing half of the archived-versions navigation (maintainer
    requirement 2026-08-06: history is organized by form, then
    chronologically). Same gates as the schema read -- publish + firm
    visibility -- so a caller sees a kit's HISTORY exactly when they may see
    the kit; a private kit's archive 404s for non-members like the kit
    itself (existence is the secret). Sorted newest-first by the archived
    snapshot's published_at (ISO strings sort chronologically); revisions
    whose snapshot lacks the stamp sort last.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    try:
        # Manifest membership FIRST, like the sibling schema/pdf reads: a
        # NONEXISTENT kit must 404 in every mode, never answer 200 with an
        # empty archive -- "no archived versions" and "no such form" are
        # different answers (qfyxr fresh-eyes, reproduced live in local
        # mode where list_archived_markers returns [] for a ghost).
        await _resolve_kit_filenames(store, kit_id)
        meta = await _load_live_metadata(store, kit_id)
        _require_published(store, kit_id, meta)
        await _require_visible(kit_id, meta, user)
        markers = await store.list_archived_markers(kit_id)
        snapshots = await asyncio.gather(
            *(store.load_archived_metadata_or_none(kit_id, m) for m in markers)
        )
    except FormKitNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Kit not found: {kit_id}") from exc
    except FormKitStoreError as exc:
        _log.error("kit_archive_list_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to list archived revisions") from exc

    revisions = []
    for marker, snapshot in zip(markers, snapshots):
        stamp = (snapshot or {}).get("published_at")
        revisions.append(
            ArchivedRevisionInfo(
                marker=marker,
                published_at=stamp if isinstance(stamp, str) else None,
            )
        )
    # (has stamp, stamp) descending: stamped revisions newest-first, then the
    # stampless tail -- False sorts after True under reverse=True.
    revisions.sort(
        key=lambda r: (r.published_at is not None, r.published_at or ""),
        reverse=True,
    )
    return KitArchiveResponse(revisions=revisions)


@router.get("/form-kits/{kit_id}/archive/{marker}/schema")
async def get_archived_kit_schema(
    kit_id: str, marker: str, user: dict = Depends(require_auth)
) -> JSONResponse:
    """An archived revision's schema, READ-ONLY (bd polyglot-pdf-qfyxr).

    Same gates as the live schema read (publish + firm visibility on the
    OWNING kit). The response is the superseded schema bytes the audit trail
    references -- never served as a fillable form; the client renders it in
    the read-only revision view.
    """
    kit_id = _safe_kit_id(kit_id)
    marker = _safe_marker(marker)
    store = get_form_kit_store()
    try:
        # Same manifest-membership check as the list route and the sibling
        # schema/pdf reads -- DELIBERATE, not incidental: without it a ghost
        # kit's 404 relied solely on load_archived_revision happening to
        # fail closed in both store impls (qfyxr fresh-eyes round 2).
        await _resolve_kit_filenames(store, kit_id)
        meta = await _load_live_metadata(store, kit_id)
        _require_published(store, kit_id, meta)
        await _require_visible(kit_id, meta, user)
        schema = await store.load_archived_revision(kit_id, marker)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Archived revision not found for kit {kit_id}",
        ) from exc
    except FormKitStoreError as exc:
        _log.error(
            "kit_archive_read_failed", kit_id=kit_id, marker=marker, error=str(exc)
        )
        raise HTTPException(status_code=502, detail="Unable to load archived revision") from exc

    return JSONResponse(content=schema, headers={"Cache-Control": "no-store"})
