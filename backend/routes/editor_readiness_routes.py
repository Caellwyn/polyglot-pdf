"""Local-save readiness stamping (sprint-18 C4b, bd polyglot-pdf-na1zy).

The one gap C4 left: a LOCAL-folder save (schema-editor App.handleSave ->
writeSchemaToHandle) is a pure File System Access write with no backend round
trip, so nothing refreshed the kit's readiness stamp -- a refreshed local
catalogue then rendered a STALE confident percentage (bd j8sr) or moved a
kit's number BACKWARD (bd bqgr).

This route closes it while keeping ONE stamp writer (the epic's thesis, and
the bead's preferred option b): the standard local dev stack runs the real
backend over the SAME form-kits folder the editor picked (the same-folder
handshake, bd s2bf, verifies exactly that), so after a local save the client
POSTs the just-written schema here and the BACKEND recomputes and persists the
stamp through the same `_stamp_readiness` the hosted save path uses --
identical lint inputs (the kit's persisted AcroForm dump), identical
best-effort semantics, identical metadata-preservation rules. The client
never computes or serializes a stamp; when no backend is reachable it only
INVALIDATES the old one (schema-editor/src/utils/localStamp.ts) so the card
degrades to the verify hint rather than lying.

Why a separate module rather than a route in editor_kit_routes.py: that file
is concurrently claimed by the sprint-19 kit-lifecycle work (bd
polyglot-pdf-6dz0); this route only IMPORTS its helpers, so the two changes
cannot conflict. Folding it back in later is a mechanical move.

The schema comes from the request BODY (what the editor just wrote to disk),
not from the store: the store read could race a slower disk flush, and the
hosted save path stamps its posted payload for the same reason. STATUS is
deliberately not checked: the stamp is derived display data, never content --
refusing to refresh it on a complete kit would preserve a stale number, the
exact lie C4b exists to end. (The write-locks on CONTENT routes are sprint-18
C2 / sprint-19 6dz0 territory.)
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException

from backend.routes.form_kit_routes import _safe_kit_id
from backend.routes.editor_kit_routes import (
    _is_write_locked,
    _lock_reason,
    _load_meta_or_404,
    _stamp_readiness,
    require_editor_role,
)
from backend.services.form_kits import get_form_kit_store

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/editor", tags=["editor-readiness"])


@router.post("/kits/{kit_id}/readiness")
async def stamp_kit_readiness(
    kit_id: str,
    role: Annotated[str, Depends(require_editor_role)],
    schema: Annotated[dict, Body()],
) -> dict:
    """Recompute and persist the kit's readiness stamp for the POSTED schema.

    Returns {"readiness": <stamp>} like the hosted save route, or
    {"readiness": null} when stamping was skipped (unparseable metadata --
    the same never-destroy rule `_stamp_readiness` applies on the hosted
    path). 404 for an unknown kit; 422 for a body with no fields list.
    """
    kit_id = _safe_kit_id(kit_id)
    if not isinstance(schema.get("fields"), list):
        raise HTTPException(
            status_code=422,
            detail="Schema must be a JSON object with a 'fields' list",
        )
    store = get_form_kit_store()
    meta, files = await _load_meta_or_404(store, kit_id)
    # A WRITE-LOCKED kit's stamp may only describe its published schema.
    # Every sibling write path guards this (PUT schema 409s on write-locked
    # kits; /status stamps only the reloaded gate-validated schema), and this
    # route is registered on the hosted app too -- without the check, an
    # editor token could overwrite a live kit's stamp with counts for a body
    # that was never saved (Opus cross-surface finding, bd na1zy). Uses the
    # bd 6dz0 write-lock predicate, so complete AND unpublished both refuse.
    if _is_write_locked(meta):
        # _lock_reason names the REAL state (complete vs unpublished), the
        # same detail every sibling lock site raises -- a retired revision
        # must not be told to use a publish flow that does not apply.
        raise HTTPException(status_code=409, detail=_lock_reason(meta))
    stamp = await _stamp_readiness(store, kit_id, schema, meta, files)
    _log.info("editor_readiness_restamped", kit_id=kit_id, role=role,
              readiness_percent=(stamp or {}).get("percent"),
              readiness_verified=(stamp or {}).get("verified"))
    return {"readiness": stamp}
