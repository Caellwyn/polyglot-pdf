"""GET /admin/firms/{firm_id}/usage and GET /admin/kits/{kit_id}/usage --
the console's read side of Epic 3's Firestore usage rollups (bd
polyglot-pdf-mpebj, E3.11a).

READS ONLY THE E3.4 ROLLUP DOCS (bd polyglot-pdf-w828m,
backend/services/usage_rollups.py): firms/{firm_id}/usage/{month} and
kits/{kit_id}/usage/{month}. This module writes nothing and adds no second
rollup writer -- it is a plain Firestore GET against a document id this
module derives with THE SAME channel-suffix rule usage_rollups.py's own
_month_key uses (mirrored, not imported: that function lives in a module
this route has no other reason to depend on, and the rule is a two-line
string format any drift would show up in immediately).

TWO DIFFERENT GATES, PER THE BEAD. The firm route takes
require_app_admin_or_owning_manager: a firm manager may read their OWN
firm's usage (404, not 403, for any other firm_id -- the SAME existence-
hiding shape link_routes.py's _require_owning_firm already uses, restated
here as this module's own copy for the same reason every other route module
in this package keeps its own small firm-scoping helper rather than
importing another route module's). The kit route takes require_app_admin
only -- a kit's usage spans every firm that used it, so there is no
"owning" manager to scope it to.

`?month=YYYY-MM` IS REQUIRED ON BOTH ROUTES, validated against a strict
4-digit-year/2-digit-month shape (422 on anything else, including a
valid-looking but malformed value like "2026-9" or "2026-13" -- the
Firestore doc id this resolves to must be exactly what usage_rollups.py
would have written, or the read silently returns "no data" for a month that
in fact has some). The DEMO channel keeps the bare "YYYY-MM" doc id
(usage_rollups.py's own convention: "the demo keeps the bare id so nothing
already written is orphaned"); every other channel's rollup lives under
"YYYY-MM_{channel}". Since a firm or kit can be used from EITHER channel
this admin service serves, and the rollup docs are genuinely separate
Firestore documents per channel (not a single doc this route could merge),
`?channel=` is REQUIRED here too (422 if missing/unknown) -- there is no
default that would not silently hide the other channel's numbers, mirroring
link_routes.py's own required-channel rule for the identical reason.

A MISSING ROLLUP DOC IS NOT A 404 -- IT IS AN EMPTY READING (a firm with no
sessions that month). usage_rollups.py's own docstring: a document is
created lazily on FIRST WRITE (set(merge=True) on a doc that may not exist
yet), so "no doc yet" and "a firm that exists but had a quiet month" are the
identical, unremarkable state. 404 is reserved for a firm_id itself that
does not exist at all (this module's own existence check runs first for the
firm route, matching every other admin route's "the resource path segment
must resolve" convention). The kit route does NOT 404 on a missing kit
profile -- see get_kit_usage's own docstring for why.

THE RESPONSE IS AN EXPLICIT KEY ALLOWLIST, never the raw stored dict (the
same by-hand-dict discipline link_routes.py's own module docstring
explains): a future field added to the rollup doc by usage_rollups.py must
not silently start reaching the console with no route change reviewing it.
`by_kit`/`by_employee`/`by_language` (firm doc) and `by_firm` (kit doc) are
passed through as-is (they are themselves maps this route does not
interpret further), everything else is read by name.

SYNC HELPER, ASYNC ROUTE, matching every other admin-service Firestore
read/write in this package.

ASCII only.
"""
from __future__ import annotations

import asyncio
import re
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from admin_backend.services.admin_auth import (
    AdminActor,
    CompositeActor,
    require_app_admin,
    require_app_admin_or_owning_manager,
)

_log = structlog.get_logger().bind(module="admin_usage_routes")

router = APIRouter()

# The two channels that actually exist (docs/doctrine/promotion-tiers.md),
# restated here rather than imported -- same reasoning as every other admin
# route module's own copy (firm_routes.py, link_routes.py, sweep_routes.py):
# no shared constant exists today, and a typo is caught by the same literal
# pair either way.
KNOWN_CHANNELS = ("demo", "staging")

# usage_rollups.py's own doc-id convention: "demo" keeps the bare "YYYY-MM"
# id (nothing already written is orphaned); every other channel gets a
# "_{channel}" suffix. Mirrored here, not imported, for the same reason this
# module restates KNOWN_CHANNELS -- see usage_rollups._month_key's own
# docstring for the full rationale this module's _rollup_doc_id below mirrors.
_DEFAULT_CHANNEL = "demo"

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# The two collections usage_rollups.py writes into.
_FIRMS_COLLECTION = "firms"
_KITS_COLLECTION = "kits"
_USAGE_SUBCOLLECTION = "usage"

# The response key allowlist for a firm-month rollup doc (see module
# docstring: usage_rollups.record_session_end's own field list, restated
# here as the read side's contract). by_kit/by_employee/by_language are
# passed through as stored (they are themselves maps this route does not
# further interpret).
_FIRM_USAGE_KEYS = (
    "connections_ended", "sessions_completed", "cost_usd_total",
    "links_opened", "links_completed", "by_kit", "by_employee",
    "by_language", "kind", "channel",
)

# The response key allowlist for a kit-month rollup doc.
_KIT_USAGE_KEYS = (
    "connections_ended", "sessions_completed", "cost_usd_total", "by_firm",
    "kind", "channel",
)


def _validated_month(month: Optional[str]) -> str:
    """A strict YYYY-MM string, or the 422 the bead requires for "missing or
    malformed" -- never silently coerced or defaulted (see module
    docstring: a wrong-shaped month resolves to a DIFFERENT Firestore doc id
    than the caller meant, which would read back as an innocent-looking
    empty rollup rather than an error).
    """
    if not month or not _MONTH_RE.fullmatch(month):
        raise HTTPException(
            status_code=422,
            detail="month is required and must be YYYY-MM, got {!r}".format(
                month),
        )
    return month


def _validated_channel(channel: Optional[str]) -> str:
    """A known channel, required -- mirrors link_routes.py's
    _validate_channel exactly (see module docstring for why no default is
    safe here)."""
    if not channel or channel not in KNOWN_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail="channel is required and must be one of {}".format(
                ", ".join(KNOWN_CHANNELS)),
        )
    return channel


def _rollup_doc_id(month: str, channel: str) -> str:
    """The Firestore document id usage_rollups.py's own _month_key would
    have produced for this (month, channel) pair -- see that function's
    docstring for why "demo" alone keeps the bare id."""
    return month if channel == _DEFAULT_CHANNEL else "{}_{}".format(
        month, channel)


def _db():
    """The Firestore client, or a 503. Lazy-imported like every other
    Firestore caller in this repo (module import must not require
    firebase_admin to be initialized)."""
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503,
                            detail="usage store unavailable")
    return db


def _require_owning_firm(actor: CompositeActor, firm_id: str) -> None:
    """Refuse a manager acting on a firm that is not their own, with the
    SAME 404 an unknown firm_id would produce -- mirrors link_routes.py's
    _require_owning_firm exactly (see that module's docstring for why this
    is a small per-module helper rather than a shared one: no other route
    module has a reason to depend on link_routes.py, and the rule is a
    two-line comparison any drift in would show up immediately).
    """
    if actor.is_app_admin:
        return
    if actor.firm_id != firm_id:
        raise HTTPException(status_code=404, detail="No such firm")


def _public_firm_usage_view(doc: dict) -> dict:
    return {key: doc.get(key) for key in _FIRM_USAGE_KEYS}


def _public_kit_usage_view(doc: dict) -> dict:
    return {key: doc.get(key) for key in _KIT_USAGE_KEYS}


def _do_get_firm_usage(*, firm_id: str, month: str, channel: str) -> dict:
    """Synchronous body of get_firm_usage(), run under asyncio.to_thread.

    404s when the FIRM itself does not exist (never when the rollup doc
    for this month is simply missing -- see module docstring).
    """
    db = _db()
    firm_snap = db.collection(_FIRMS_COLLECTION).document(firm_id).get()
    if not firm_snap.exists:
        raise HTTPException(status_code=404, detail="No such firm")

    doc_id = _rollup_doc_id(month, channel)
    try:
        usage_snap = (
            db.collection(_FIRMS_COLLECTION).document(firm_id)
            .collection(_USAGE_SUBCOLLECTION).document(doc_id).get()
        )
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_firm_usage_read_failed", firm_id=firm_id,
                   month=month, channel=channel, error=str(exc))
        raise HTTPException(status_code=503,
                            detail="usage store unavailable") from exc

    doc = usage_snap.to_dict() if usage_snap.exists else {}
    return _public_firm_usage_view(doc or {})


@router.get("/admin/firms/{firm_id}/usage")
async def get_firm_usage(
    firm_id: str,
    actor: Annotated[CompositeActor,
                     Depends(require_app_admin_or_owning_manager)],
    month: Annotated[Optional[str], Query()] = None,
    channel: Annotated[Optional[str], Query()] = None,
) -> dict:
    """This firm's usage rollup for one month (bd polyglot-pdf-w828m's
    firms/{firm_id}/usage/{month} doc), an explicit key allowlist. `?month=`
    and `?channel=` are both REQUIRED (422 if missing/malformed -- see
    _validated_month/_validated_channel). A manager reaches only their own
    firm (404 for any other firm_id, the same 404 an unknown firm_id would
    get); an app admin reaches any firm. A read, so no audit row.
    """
    month = _validated_month(month)
    channel = _validated_channel(channel)
    _require_owning_firm(actor, firm_id)
    usage = await asyncio.to_thread(
        _do_get_firm_usage, firm_id=firm_id, month=month, channel=channel)
    return {"firm_id": firm_id, "month": month, "channel": channel,
            "usage": usage}


def _do_get_kit_usage(*, kit_id: str, month: str, channel: str) -> dict:
    """Synchronous body of get_kit_usage(), run under asyncio.to_thread.

    UNLIKE the firm route, this does NOT 404 on a kit with no
    kits/{kit_id} profile document -- usage_rollups.py writes
    kits/{kit_id}/usage/{month} directly under a kit_id it never verifies
    against a kits/{kit_id} profile doc (that document may not even exist:
    form kits are their own store, backend/services/form_kits.py, not
    Firestore-profile-backed the way firms are). Requiring a profile doc
    here would 404 every kit that has real usage but no separate Firestore
    kits/{kit_id} record -- exactly backwards for a usage-reporting route.
    A kit_id with no rollup doc for this month simply reads as an empty
    usage reading, matching the firm route's own "missing doc is not an
    error" rule.
    """
    db = _db()
    doc_id = _rollup_doc_id(month, channel)
    try:
        usage_snap = (
            db.collection(_KITS_COLLECTION).document(kit_id)
            .collection(_USAGE_SUBCOLLECTION).document(doc_id).get()
        )
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_kit_usage_read_failed", kit_id=kit_id,
                   month=month, channel=channel, error=str(exc))
        raise HTTPException(status_code=503,
                            detail="usage store unavailable") from exc

    doc = usage_snap.to_dict() if usage_snap.exists else {}
    return _public_kit_usage_view(doc or {})


@router.get("/admin/kits/{kit_id}/usage")
async def get_kit_usage(
    kit_id: str,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    month: Annotated[Optional[str], Query()] = None,
    channel: Annotated[Optional[str], Query()] = None,
) -> dict:
    """This kit's usage rollup for one month (bd polyglot-pdf-w828m's
    kits/{kit_id}/usage/{month} doc), an explicit key allowlist. `?month=`
    and `?channel=` are both REQUIRED. require_app_admin only -- a kit spans
    every firm that used it, so there is no owning manager to scope it to.
    A read, so no audit row.
    """
    month = _validated_month(month)
    channel = _validated_channel(channel)
    usage = await asyncio.to_thread(
        _do_get_kit_usage, kit_id=kit_id, month=month, channel=channel)
    return {"kit_id": kit_id, "month": month, "channel": channel,
            "usage": usage}
