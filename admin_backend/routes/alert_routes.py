"""GET /admin/alerts and PATCH /admin/alerts/{id}/acknowledge -- the
console's read + acknowledge surface over Epic 3's telemetry alert docs
(bd polyglot-pdf-mpebj, E3.11a; docs: bd polyglot-pdf-bo95a,
backend/services/alerts.py, Surface contract 21).

BOTH ROUTES BEHIND require_app_admin -- alerts are an operator concern with
no firm-manager counterpart (mirroring kit_routes.py's own "no firm-manager
counterpart" reasoning): a firm manager has no console page in this bead's
scope that would need to see their own firm's alerts, and the plan does not
name one.

LIST IS THE ONLY READ, FILTERED BY THREE OPTIONAL QUERY PARAMS
(`acknowledged`, `firm_id`, `kind`), matching the bead's own wording
exactly. `acknowledged=false` is the console's "show me what still needs
attention" default view; querying is done IN PYTHON over a full collection
stream (see _do_list_alerts's own docstring for why, mirroring the audit
route's own no-composite-Firestore-index reasoning) with a PAGE CAP
(`_PAGE_LIMIT`) so a growing alerts collection cannot make this route
unboundedly slow -- newest first, matching every other admin list route's
own "the operator wants to see the newest first" convention (firm_routes.py
's ledger page, link_routes.py's link list).

ACKNOWLEDGE SETS acknowledged_by (the ACTOR'S uid, never a request body
value -- the plan's own wording: "acknowledged_by (actor uid)") and
acknowledged_at, INSIDE ONE Firestore transaction WITH its audit row
(mirrors firm_routes.py's _apply_firm_patch / config_routes.py's
_apply_config_write shape exactly): a forced audit failure leaves
acknowledged_at unset (exit criterion 1). ACKNOWLEDGING TWICE IS A 409
(bead requirement) -- alerts.py's own alert docs seed acknowledged_at to
None on first creation and never touch it again on a re-trigger (see that
module's docstring), so a truthy acknowledged_at on read is unambiguously
"someone already acknowledged this", never a re-triggered alert's own
write clobbering it.

THE RESPONSE IS AN EXPLICIT KEY ALLOWLIST built from alerts.ALERT_FIELDS
plus the doc's own id -- the same by-hand-dict discipline every other list
route in this service uses (never **doc), so a future field added to an
alert doc by alerts.py does not silently reach the console with no route
review.

SYNC HELPER, ASYNC ROUTE, matching every other admin-service Firestore call
in this package.

ASCII only.
"""
from __future__ import annotations

import asyncio
import time
from typing import Annotated, Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import alerts

_log = structlog.get_logger().bind(module="admin_alert_routes")

router = APIRouter()

# The audit `action` string for this surface's one mutation.
ACTION_ALERT_ACKNOWLEDGE = "alert.acknowledge"

# The recognized `kind` values (alerts.py's own vocabulary) -- validated
# here so a typo'd ?kind= 422s instead of silently matching zero rows.
_KNOWN_KINDS = (
    alerts.KIND_LINK_EXHAUSTED, alerts.KIND_CREDIT_LOW,
    alerts.KIND_CREDIT_EXHAUSTED,
)

# A page cap on the list route (see module docstring) -- generous enough
# for an operator's working set, bounded enough that a growing alerts
# collection cannot make this route unboundedly slow. Mirrors
# firm_routes.py's own `ledger_limit` upper bound (200) in spirit; alerts
# have no per-firm scoping to shrink the collection the way a firm's own
# ledger page does, so this is a flat cap on the WHOLE query result rather
# than a caller-tunable one.
_PAGE_LIMIT = 200

# The response key allowlist: alerts.ALERT_FIELDS (the stored doc's own
# field set) plus the doc id itself, which is not a stored field.
_ALERT_RESPONSE_KEYS = ("id",) + tuple(sorted(alerts.ALERT_FIELDS))


def _db():
    """The Firestore client, or a 503. Lazy-imported like every other
    Firestore caller in this repo."""
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503,
                            detail="alert store unavailable")
    return db


def _public_alert_view(doc_id: str, doc: dict) -> dict:
    row = {"id": doc_id}
    row.update({key: doc.get(key) for key in alerts.ALERT_FIELDS})
    return {key: row[key] for key in _ALERT_RESPONSE_KEYS}


def _do_list_alerts(
    *, acknowledged: Optional[bool], firm_id: Optional[str],
    kind: Optional[str],
) -> list[dict]:
    """Synchronous body of list_alerts(), run under asyncio.to_thread.

    FILTERS IN PYTHON, OVER A FULL COLLECTION STREAM, deliberately --
    mirroring the audit route's own no-composite-Firestore-index approach
    (admin_audit_log's own GET /admin/audit route). A Firestore
    `acknowledged_by == None` equality filter combined with a second
    inequality/order-by needs a composite index this bead does not ship
    (see test_firestore_indexes.py's own set-derived discipline for WHY a
    new filter combination needs its own declared index); reading every
    alert doc and filtering client-side is the same tradeoff this service
    already accepts elsewhere for a collection this bounded (90-day TTL,
    alerts.py's own retention window) and this operator-facing (a human
    reading a list, not a hot path).
    """
    db = _db()
    try:
        docs = list(db.collection(alerts.COLLECTION).stream())
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_alert_list_failed", error=str(exc))
        raise HTTPException(status_code=503,
                            detail="alert store unavailable") from exc

    rows = []
    for snap in docs:
        doc = snap.to_dict() or {}
        if firm_id is not None and doc.get("firm_id") != firm_id:
            continue
        if kind is not None and doc.get("kind") != kind:
            continue
        if acknowledged is not None:
            is_ack = bool(doc.get("acknowledged_by"))
            if is_ack != acknowledged:
                continue
        rows.append(_public_alert_view(snap.id, doc))

    # Newest first (ts is a plain epoch float, alerts.py's own _write). A
    # missing ts sorts last rather than crashing the comparison.
    rows.sort(key=lambda r: (r["ts"] is None, r["ts"]), reverse=True)
    return rows[:_PAGE_LIMIT]


@router.get("/admin/alerts")
async def list_alerts(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    acknowledged: Annotated[Optional[bool], Query()] = None,
    firm_id: Annotated[Optional[str], Query()] = None,
    kind: Annotated[Optional[str], Query()] = None,
) -> dict:
    """Alert docs, newest first, up to _PAGE_LIMIT -- optionally filtered by
    `acknowledged` (bool), `firm_id` (equality), `kind` (validated against
    alerts.py's own vocabulary; 422 on an unrecognized value). A read, so
    no audit row.
    """
    if kind is not None and kind not in _KNOWN_KINDS:
        raise HTTPException(
            status_code=422,
            detail="kind must be one of {}".format(", ".join(_KNOWN_KINDS)),
        )
    rows = await asyncio.to_thread(
        _do_list_alerts, acknowledged=acknowledged, firm_id=firm_id,
        kind=kind,
    )
    return {"alerts": rows}


def _do_acknowledge_alert(
    *, alert_id: str, actor: AdminActor, request_id: str,
) -> dict:
    """Synchronous body of acknowledge_alert(), run under asyncio.to_thread.

    Mirrors firm_routes.py's _apply_firm_patch shape: read (inside the
    transaction, so a retry on contention re-reads rather than trusting a
    stale snapshot), refuse if already acknowledged, write, audit -- all
    three in ONE @firestore.transactional body, so a forced audit failure
    leaves acknowledged_at unset (exit criterion 1).
    """
    from firebase_admin import firestore

    db = _db()
    alert_ref = db.collection(alerts.COLLECTION).document(alert_id)

    result: dict[str, Any] = {}

    @firestore.transactional
    def _txn(tx):
        snap = alert_ref.get(transaction=tx)
        if not snap.exists:
            raise HTTPException(status_code=404, detail="No such alert")
        doc = snap.to_dict() or {}
        if doc.get("acknowledged_by"):
            raise HTTPException(
                status_code=409,
                detail="alert {} was already acknowledged by {}".format(
                    alert_id, doc.get("acknowledged_by")),
            )
        now = time.time()
        tx.set(alert_ref, {
            "acknowledged_by": actor.uid,
            "acknowledged_at": now,
        }, merge=True)
        audit_log.record_in_transaction(
            tx,
            db,
            actor_uid=actor.uid,
            actor_email=actor.email,
            action=ACTION_ALERT_ACKNOWLEDGE,
            target="{}/{}".format(alerts.COLLECTION, alert_id),
            before={"acknowledged_by": doc.get("acknowledged_by")},
            after={"acknowledged_by": actor.uid, "acknowledged_at": now},
            request_id=request_id,
        )
        result["acknowledged_at"] = now

    try:
        _txn(db.transaction())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_alert_acknowledge_failed", alert_id=alert_id,
                   error=str(exc))
        raise HTTPException(status_code=500,
                            detail="alert acknowledge failed") from exc

    return result


@router.patch("/admin/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Acknowledge one alert. Sets acknowledged_by (this ACTOR's uid) and
    acknowledged_at in one Firestore transaction with an in-transaction
    audit row (exit criterion 1). 404 for an unknown alert id; 409 for one
    already acknowledged, naming who acknowledged it first.
    """
    request_id = audit_log.new_request_id()
    result = await asyncio.to_thread(
        _do_acknowledge_alert, alert_id=alert_id, actor=actor,
        request_id=request_id,
    )
    _log.info("admin_alert_acknowledged", alert_id=alert_id,
              actor_uid=actor.uid, request_id=request_id)
    return {
        "id": alert_id, "acknowledged_by": actor.uid,
        "acknowledged_at": result["acknowledged_at"],
        "request_id": request_id,
    }
