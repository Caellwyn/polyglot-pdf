"""GET /admin/alerts, GET /admin/firms/{firm_id}/alerts, and PATCH
/admin/alerts/{id}/acknowledge -- the console's AND the firm console's
read + acknowledge surface over Epic 3's telemetry alert docs (bd
polyglot-pdf-mpebj, E3.11a; bd polyglot-pdf-62o4d widens the firm-scoped
half; docs: bd polyglot-pdf-bo95a, backend/services/alerts.py, Surface
contract 21).

THREE ROUTES, TWO GATES, NOW.

    GET   /admin/alerts                          require_app_admin
    GET   /admin/firms/{firm_id}/alerts          require_app_admin_or_owning_manager_or_employee
    PATCH /admin/alerts/{alert_id}/acknowledge    require_app_admin_or_owning_manager_or_employee
                                                   (employee branch REFUSED inside the route body)

GET /admin/alerts (operator-wide list, unchanged from E3.11a) stays behind
require_app_admin -- the app admin's cross-firm "everything that needs
attention" view, filtered by ?acknowledged=/?firm_id=/?kind=.

GET /admin/firms/{firm_id}/alerts is the NEW route this bead adds: a firm
manager or employee's OWN alerts, scoped server-side to their firm
(_require_owning_firm, the same 404-not-403 existence-hiding shape
link_routes.py's list route already uses -- a manager or employee naming a
firm that is not theirs gets the SAME 404 an unknown firm_id would produce,
never a 403 that would confirm the firm exists). An app admin may name any
firm_id. `?acknowledged=` is the console/banner's own filter (the banner's
"show me what still needs attention" default is acknowledged=false, the
SAME semantics as the operator-wide route's own default-omitted filter);
`?channel=` is accepted (never 422 on an unknown value here) because
alerts/{id} carries no `channel` field at all (backend/services/alerts.py's
own ALERT_FIELDS has none -- alerts are not channel-partitioned the way
links[_<channel>] is) -- there is nothing to filter ON, so inventing a
validation rule for a parameter this collection cannot express would be
pure friction. It exists on the wire ONLY because
frontend/src/console/adminApi.ts's adminFetch/withChannel appends
`?channel=<build's own channel>` to EVERY firm-scoped call unconditionally
(Surface contract 23) -- this route must not 422 a caller it cannot avoid
being called by.

THE FIRM-SCOPED RESPONSE IS A NARROWER ALLOWLIST than the operator-wide
route's (bead's own wording): id, kind, level, ts, context,
acknowledged_at -- NOT firm_id (a firm's own console has no use naming the
firm it already knows it is), NOT acknowledged_by (an employee or manager
has no business seeing WHICH staffer acknowledged something -- and for
their OWN firm, "was this acknowledged" is exactly what acknowledged_at
already answers), NOT emailed_at (a dispatcher implementation detail with
no console-facing meaning). `context` is carried through verbatim -- it is
METADATA ONLY by construction (alerts.py's own module docstring:
jti/balance/spend_usd/ceiling_usd, NEVER a form field value), so no further
scrubbing is needed here, only the SAME by-hand-dict discipline as every
other allowlist in this service.

ACKNOWLEDGE WIDENS TO THE COMPOSITE-OR-EMPLOYEE GATE, BUT AN EMPLOYEE IS
STILL REFUSED, INSIDE THE ROUTE BODY, NOT THE DEPENDENCY. The bead's own
words: "an employee may read but not acknowledge (403 with the existing
prefix)". require_app_admin_or_owning_manager_or_employee resolves WHO is
calling (app admin / manager / employee); this route additionally requires
`actor.kind != ACTOR_KIND_FIRM_EMPLOYEE`, refusing with the SAME
NO_ADMIN_ACCESS_PREFIX-carrying 403 shape admin_auth.py's own dependencies
use for "verified, but not entitled" -- an employee who successfully
authenticates as an employee is not confused with an unverifiable token
(401), matching every other split in this service. A manager may
acknowledge only an alert belonging to THEIR OWN firm (_require_owning_firm
again, this time discovered from the ALERT DOC's own firm_id, read inside
the same transaction that decides everything else -- no separate pre-read
is needed here, unlike link_routes.py's revoke, because acknowledge's own
transaction body already reads the doc once for the 409 check and that one
read answers both questions); an app admin may acknowledge any firm's
alert, or a firm-less one (a KIND_LINK_EXHAUSTED alert may carry
firm_id=None per alerts.py's own _write -- a manager/employee can never
own a None firm, so a firm-less alert is admin-only to acknowledge, which
is correct: nobody's firm console should be offering to acknowledge an
alert that names no firm).

ACKNOWLEDGE SETS acknowledged_by (the ACTOR'S uid, never a request body
value -- the plan's own wording: "acknowledged_by (actor uid)") and
acknowledged_at, INSIDE ONE Firestore transaction WITH its audit row
(mirrors firm_routes.py's _apply_firm_patch / config_routes.py's
_apply_config_write shape exactly): a forced audit failure leaves
acknowledged_at unset (exit criterion 1, unchanged from E3.11a).
ACKNOWLEDGING TWICE IS A 409 (bead requirement, unchanged) -- alerts.py's
own alert docs seed acknowledged_at to None on first creation and never
touch it again on a re-trigger (see that module's docstring), so a truthy
acknowledged_at on read is unambiguously "someone already acknowledged
this", never a re-triggered alert's own write clobbering it.

THE OPERATOR-WIDE RESPONSE (GET /admin/alerts) IS UNCHANGED: still the
FULL alerts.ALERT_FIELDS allowlist plus id, built by _public_alert_view --
an app admin already sees firm_id/acknowledged_by/emailed_at today and
this bead does not narrow that view. The firm-scoped route's NARROWER
_public_firm_alert_view is a SEPARATE function, not a parameter on the
first, so the two allowlists cannot drift into each other by a
shared-default accident.

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
from admin_backend.services.admin_auth import (
    ACTOR_KIND_FIRM_EMPLOYEE,
    AdminActor,
    CompositeActor,
    NO_ADMIN_ACCESS_PREFIX,
    require_app_admin,
    require_app_admin_or_owning_manager_or_employee,
)
from backend.services import alerts

_log = structlog.get_logger(module="admin_alert_routes")

router = APIRouter()

# The audit `action` string for this surface's one mutation.
ACTION_ALERT_ACKNOWLEDGE = "alert.acknowledge"

# The recognized `kind` values (alerts.py's own vocabulary) -- validated
# here so a typo'd ?kind= 422s instead of silently matching zero rows.
_KNOWN_KINDS = (
    alerts.KIND_LINK_EXHAUSTED, alerts.KIND_CREDIT_LOW,
    alerts.KIND_CREDIT_EXHAUSTED,
)

# A page cap on the list routes (see module docstring) -- generous enough
# for an operator's working set, bounded enough that a growing alerts
# collection cannot make either route unboundedly slow. Mirrors
# firm_routes.py's own `ledger_limit` upper bound (200) in spirit; alerts
# have no per-firm scoping to shrink the collection the way a firm's own
# ledger page does, so this is a flat cap on the WHOLE query result rather
# than a caller-tunable one. Both list helpers filter FIRST (firm_id/kind/
# acknowledged, in the Python loop over the full stream), sort, and only
# THEN apply this cap to the already-filtered result -- so the cap is
# per-firm on the firm-scoped route, not global: a firm with more than
# _PAGE_LIMIT of its OWN alerts loses only its oldest ones, ordinary
# paging, not a cross-firm truncation hazard.
_PAGE_LIMIT = 200

# The response key allowlist for the OPERATOR-WIDE route (unchanged from
# E3.11a): alerts.ALERT_FIELDS (the stored doc's own field set) plus the
# doc id itself, which is not a stored field.
_ALERT_RESPONSE_KEYS = ("id",) + tuple(sorted(alerts.ALERT_FIELDS))

# The NARROWER response key allowlist for the FIRM-SCOPED route (bd
# polyglot-pdf-62o4d, this bead's own wording): id, kind, level, ts,
# context, acknowledged_at -- deliberately NOT firm_id, acknowledged_by, or
# emailed_at. See module docstring's "THE FIRM-SCOPED RESPONSE" section for
# why each omission is deliberate.
_FIRM_ALERT_RESPONSE_KEYS = (
    "id", "kind", "level", "ts", "context", "acknowledged_at",
)


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
    """The OPERATOR-WIDE allowlisted view (GET /admin/alerts) -- unchanged
    from E3.11a."""
    row = {"id": doc_id}
    row.update({key: doc.get(key) for key in alerts.ALERT_FIELDS})
    return {key: row[key] for key in _ALERT_RESPONSE_KEYS}


def _public_firm_alert_view(doc_id: str, doc: dict) -> dict:
    """The FIRM-SCOPED allowlisted view (GET /admin/firms/{firm_id}/alerts)
    -- bd polyglot-pdf-62o4d's own narrower key set. Built by hand from
    named fields, exactly like _public_alert_view and every other allowlist
    in this service, never **doc: a future field added to an alert doc by
    alerts.py must not silently reach a firm's own console with no route
    review, and in particular must never reach it before an operator-wide
    route review has already cleared it for THAT wider audience.
    """
    row = {
        "id": doc_id,
        "kind": doc.get("kind"),
        "level": doc.get("level"),
        "ts": doc.get("ts"),
        "context": doc.get("context"),
        "acknowledged_at": doc.get("acknowledged_at"),
    }
    return {key: row[key] for key in _FIRM_ALERT_RESPONSE_KEYS}


def _do_list_alerts(
    *, acknowledged: Optional[bool], firm_id: Optional[str],
    kind: Optional[str],
) -> list[dict]:
    """Synchronous body of list_alerts(), run under asyncio.to_thread.

    FILTERS IN PYTHON, OVER A FULL COLLECTION STREAM, deliberately --
    mirroring the audit route's own no-composite-Firestore-index approach
    (admin_audit_log's own GET /admin/audit route). Reading every alert doc
    and filtering client-side is the same tradeoff this service already
    accepts elsewhere for a collection this bounded (90-day TTL) and this
    operator-facing (a human reading a list, not a hot path).
    """
    db = _db()
    try:
        docs = list(db.collection(alerts.COLLECTION).stream())
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_alert_list_failed", error_type=type(exc).__name__)
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
        rows.append((snap.id, doc))

    # Newest first (ts is a plain epoch float, alerts.py's own _write). A
    # missing ts sorts last rather than crashing the comparison. `reverse=True`
    # applies to the WHOLE tuple, so the has-a-ts flag must itself already be
    # true-sorts-first (has_ts, not is_none) or reverse=True would put the
    # missing-ts rows ahead of the newest real one (bd polyglot-pdf-xq3nb).
    rows.sort(key=lambda r: (r[1].get("ts") is not None, r[1].get("ts") or 0),
             reverse=True)
    return [_public_alert_view(doc_id, doc) for doc_id, doc in
            rows[:_PAGE_LIMIT]]


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
    no audit row. Operator-wide (require_app_admin); see
    list_firm_alerts below for the firm-scoped counterpart.
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


def _require_owning_firm(actor: CompositeActor,
                          firm_id: Optional[str]) -> None:
    """Refuse a manager OR EMPLOYEE acting on a firm that is not their own,
    with the SAME 404 an unknown firm_id would produce -- mirrors
    link_routes.py's own _require_owning_firm exactly (not imported from
    there: that module's copy is scoped to link records and this route has
    no reason to depend on link_routes.py for an identical two-line check;
    CLAUDE.md scar #8's "enumerate the set" is about not hand-writing the
    RULE twice, and the rule here -- backend.services.firms.manager_firm_id
    / employee_firm_id compared against actor.firm_id -- already lives in
    exactly one place; this is a second small caller of that one rule, not
    a second copy of it).

    An app admin is never refused here -- they may act on any firm, or a
    firm-less alert (firm_id=None), exactly like every other
    require_app_admin_or_owning_manager(_or_employee) route in this
    service. A manager or employee whose OWN firm_id does not match
    `firm_id` (including a None firm_id, which can never equal any real
    firm) gets 404.
    """
    if actor.is_app_admin:
        return
    if actor.firm_id != firm_id:
        raise HTTPException(status_code=404, detail="No such firm")


def _do_list_firm_alerts(
    *, firm_id: str, acknowledged: Optional[bool],
) -> list[dict]:
    """Synchronous body of list_firm_alerts(), run under asyncio.to_thread.

    Same full-stream-then-filter shape as _do_list_alerts, filtered to ONE
    firm_id and, optionally, `acknowledged` -- narrower than the
    operator-wide route (no `kind` filter; the bead names none for this
    route), and returning the FIRM-SCOPED allowlist
    (_public_firm_alert_view), not the operator-wide one.
    """
    db = _db()
    try:
        docs = list(db.collection(alerts.COLLECTION).stream())
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_firm_alert_list_failed", firm_id=firm_id,
                   error_type=type(exc).__name__)
        raise HTTPException(status_code=503,
                            detail="alert store unavailable") from exc

    rows = []
    for snap in docs:
        doc = snap.to_dict() or {}
        if doc.get("firm_id") != firm_id:
            continue
        if acknowledged is not None:
            is_ack = bool(doc.get("acknowledged_by"))
            if is_ack != acknowledged:
                continue
        rows.append((snap.id, doc))

    # Newest first, missing ts last -- see list_alerts's sibling sort above
    # for why the key uses has_ts (not is_none) under reverse=True
    # (bd polyglot-pdf-xq3nb).
    rows.sort(key=lambda r: (r[1].get("ts") is not None, r[1].get("ts") or 0),
             reverse=True)
    return [_public_firm_alert_view(doc_id, doc) for doc_id, doc in
            rows[:_PAGE_LIMIT]]


@router.get("/admin/firms/{firm_id}/alerts")
async def list_firm_alerts(
    firm_id: str,
    actor: Annotated[
        CompositeActor,
        Depends(require_app_admin_or_owning_manager_or_employee)],
    acknowledged: Annotated[Optional[bool], Query()] = None,
    channel: Annotated[Optional[str], Query()] = None,
) -> dict:
    """This firm's alerts, newest first, up to _PAGE_LIMIT -- the
    firm-console counterpart of the operator-wide GET /admin/alerts (bd
    polyglot-pdf-62o4d).

    `acknowledged` is the banner's own filter (the banner's default view is
    `acknowledged=false`, applied by the CALLER -- frontend/src/console/
    FirmAlertsBanner.tsx -- not forced here, so an app admin or console
    page can still ask for the acknowledged history). `channel` is accepted
    and ignored -- see module docstring's "GET /admin/firms" section for
    why: alerts carry no channel field, and adminFetch appends `?channel=`
    to every firm-scoped call unconditionally.

    A manager or employee reaches only their OWN firm_id (404 for any
    other, the SAME 404 an unknown firm_id would get); an app admin may
    list any firm's alerts. A read, so no audit row.
    """
    del channel  # accepted, unused -- see module + route docstrings.
    _require_owning_firm(actor, firm_id)
    rows = await asyncio.to_thread(
        _do_list_firm_alerts, firm_id=firm_id, acknowledged=acknowledged,
    )
    return {"firm_id": firm_id, "alerts": rows}


def _do_acknowledge_alert(
    *, alert_id: str, actor: CompositeActor, request_id: str,
) -> dict:
    """Synchronous body of acknowledge_alert(), run under asyncio.to_thread.

    Mirrors firm_routes.py's _apply_firm_patch shape: read (inside the
    transaction, so a retry on contention re-reads rather than trusting a
    stale snapshot), refuse if already acknowledged OR not owned by this
    actor, write, audit -- all three in ONE @firestore.transactional body,
    so a forced audit failure leaves acknowledged_at unset (exit
    criterion 1).

    THE OWNERSHIP CHECK RUNS INSIDE THE TRANSACTION, AFTER THE READ -- one
    read already gives both answers this route needs (the alert's firm_id
    for ownership, and its acknowledged_by for the 409 check), so there is
    no reason to read twice; the transaction's own retry-on-contention
    re-read covers the same staleness concern a two-read shape would.
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
        _require_owning_firm(actor, doc.get("firm_id"))
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
                   error_type=type(exc).__name__)
        raise HTTPException(status_code=500,
                            detail="alert acknowledge failed") from exc

    return result


@router.patch("/admin/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    actor: Annotated[
        CompositeActor,
        Depends(require_app_admin_or_owning_manager_or_employee)],
) -> dict:
    """Acknowledge one alert. Sets acknowledged_by (this ACTOR's uid) and
    acknowledged_at in one Firestore transaction with an in-transaction
    audit row (exit criterion 1). 404 for an unknown alert id, OR one
    belonging to a firm the caller (a manager or employee) does not own
    (the same 404 either way -- see _require_owning_firm); 409 for one
    already acknowledged, naming who acknowledged it first.

    AN EMPLOYEE IS REFUSED HERE WITH A 403, EVEN THOUGH THE DEPENDENCY
    ITSELF ALLOWS AN EMPLOYEE ACTOR THROUGH (bd polyglot-pdf-62o4d's own
    wording: "an employee may read but not acknowledge"). This gate is
    shared with the read-side list_firm_alerts route above (both need the
    same "app admin, or THIS firm's manager/employee" resolution), so the
    write-only refusal lives here, in the route body, as an explicit early
    check -- not as a second, narrower dependency the way link_routes.py
    split its read (require_app_admin_or_owning_manager_or_employee) and
    write (require_app_admin_or_owning_manager) onto two DIFFERENT
    dependencies. That split was possible there because revoke's actor set
    is the plan's own original two-actor composite; here, acknowledge's
    actor set (admin + owning manager) has no existing two-actor dependency
    to fall back to -- routing through a second dependency would mean the
    employee branch resolves successfully and is thrown away only for a
    DIFFERENT dependency to re-verify the same token a second time. One
    dependency, one explicit refusal, is simpler.
    """
    if actor.kind == ACTOR_KIND_FIRM_EMPLOYEE:
        raise HTTPException(
            status_code=403,
            detail=(NO_ADMIN_ACCESS_PREFIX
                    + " An employee account may not acknowledge alerts"),
        )
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
