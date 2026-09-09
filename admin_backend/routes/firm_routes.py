"""Firm CRUD on the admin service (bd polyglot-pdf-zopqq, Epic 2 Track B
bead B1).

SIX ROUTES:

    POST  /admin/firms                       create (kind REQUIRED)
    GET   /admin/firms                       list (kind, balance, status)
    GET   /admin/firms/{firm_id}             profile + balance + ledger page
    PATCH /admin/firms/{firm_id}/status      active | suspended
    PATCH /admin/firms/{firm_id}/allowed_kits
    PATCH /admin/firms/{firm_id}/kind        reason required

ALL SIX behind require_app_admin -- unlike the user routes (bd
polyglot-pdf-dmjl5), there is no firm-manager counterpart here in this
bead: a firm manager never creates or reclassifies firms, and the plan lists
this surface under the app-admin-only routes. (Link listing, which a
manager DOES reach, is Track B bead B4's require_app_admin_or_owning_manager
route, not this one.)

WRITES REUSE backend/services/firms.py::upsert_firm RATHER THAN A SECOND
WRITER. upsert_firm() is the ONE home for the firms/{firm_id} document shape
(CLAUDE.md scar #8) -- it already carries the create/update idempotency
rule (balance_credits initialized to 0 on first create only, never touched
on a re-run) that a second hand-rolled Firestore write here would have to
duplicate or drift from. The three PATCH routes below therefore read the
existing doc, compute the ONE field that changes, and re-call upsert_firm
with the rest of the doc's current values -- never a partial merge of their
own, since upsert_firm has no partial-update API by design.

EVERY MUTATION IS A FIRESTORE WRITE, so every one uses
audit_log.record_in_transaction INSIDE a @firestore.transactional body,
mirroring config_routes.py's _apply_config_write shape exactly: read
(before), write, audit -- all three in the one transaction, so a forced
audit failure leaves the firm doc unchanged (exit criterion 1's audit half,
shared with credit_routes.py).

GET /admin/firms/{firm_id} RECONCILES BEFORE IT READS THE BALANCE
(exit criterion 3). credit_ledger.reconcile_expired_for_firm() is a lazy,
best-effort catch-up for links the hourly sweep (Track B bead B5, not yet
built) has not reached -- it runs as ITS OWN transaction per expired link,
never inside this route's own write (there is no write here; a GET writes
no audit row for the same reason every other read route in this service
does not). The admin service has NO channel of its own (admin_backend/
main.py), so this route reconciles across BOTH known channels
(KNOWN_CHANNELS) rather than guessing one -- a firm's outstanding links can
exist under either channel's collection, and skipping one would leave that
channel's expired links unrefunded on every admin console visit until the
sweep endpoint ships.

LIST IS DELIBERATELY UNFILTERED. The bead's wording ("list with kind,
balance, status") is a describe-the-columns request, not a describe-the-
filters one -- unlike GET /admin/audit (bd polyglot-pdf-li9x0), which
documents named filters up front and ships a composite index per filter
(test_firestore_indexes.py). Adding an equality filter here later needs the
same index discipline; this bead ships none, so none is owed.

ASCII only.
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import credit_ledger, firms

_log = structlog.get_logger().bind(module="admin_firm_routes")

router = APIRouter()

# The two channels that actually exist (docs/doctrine/promotion-tiers.md),
# restated here rather than imported for the same reason config_routes.py
# restates it locally: there is no shared constant today, and this route's
# reconciliation loop needs the same vocabulary a future filter query would.
KNOWN_CHANNELS = ("demo", "staging")

# The audit `action` strings for this surface. Constants, not inline
# literals: test_admin_audit_coverage.py and a future console filter both
# key on them.
ACTION_FIRM_CREATE = "firm.create"
ACTION_FIRM_STATUS = "firm.status"
ACTION_FIRM_ALLOWED_KITS = "firm.allowed_kits"
ACTION_FIRM_KIND = "firm.kind"

_FIRM_STATUSES = (firms.FIRM_STATUS_ACTIVE, firms.FIRM_STATUS_SUSPENDED)
_FIRM_KINDS = (firms.FIRM_KIND_MOCK, firms.FIRM_KIND_LIVE)

_FIRMS_COLLECTION = "firms"


class CreateFirmRequest(BaseModel):
    """A new firm. `kind` is REQUIRED -- no default (plan: "kind REQUIRED,
    no default"). Pydantic enforces presence; the value itself is checked
    against _FIRM_KINDS below so a typo 422s rather than reaching
    upsert_firm's own ValueError as a 500.
    """

    firm_id: str
    name: str
    contact_email: str
    kind: str
    allowed_kits: list[str] = Field(default_factory=list)
    status: str = firms.FIRM_STATUS_ACTIVE


class SetStatusRequest(BaseModel):
    status: str


class SetAllowedKitsRequest(BaseModel):
    allowed_kits: list[str]


class SetKindRequest(BaseModel):
    """kind is confirm-twice in the UI (plan: "kind changes are confirm-
    twice in the UI") -- this route enforces only the SERVER-side half of
    that: `reason` is required, but the double-confirmation itself is the
    console's job, not this route's, since a route cannot see how many times
    a human clicked."""

    kind: str
    reason: str


def _db():
    """The Firestore client, or a 503. Lazy-imported like every other
    Firestore caller in this repo (module import must not require
    firebase_admin to be initialized)."""
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="firm store unavailable")
    return db


def _firm_ref(db, firm_id: str):
    return db.collection(_FIRMS_COLLECTION).document(firm_id)


def _get_firm_or_404(db, firm_id: str) -> dict:
    snap = _firm_ref(db, firm_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="No such firm")
    return snap.to_dict() or {}


def _public_firm_view(firm_id: str, doc: dict) -> dict:
    """The fields a console list/detail view needs, in one place so the
    list and detail routes cannot silently diverge on shape."""
    return {
        "firm_id": firm_id,
        "name": doc.get("name"),
        "contact_email": doc.get("contact_email"),
        "kind": doc.get("kind") if doc.get("kind") in _FIRM_KINDS else
        firms.FIRM_KIND_LIVE,
        "status": doc.get("status"),
        "allowed_kits": doc.get("allowed_kits")
        if isinstance(doc.get("allowed_kits"), list) else [],
        "balance_credits": doc.get("balance_credits")
        if isinstance(doc.get("balance_credits"), int)
        and not isinstance(doc.get("balance_credits"), bool) else 0,
    }


def _validated_firm_id(firm_id: str) -> str:
    """Reject an empty/blank path segment before it reaches Firestore as a
    document id nothing else would ever create.

    FastAPI's path converter already refuses an empty {firm_id} segment (it
    would not match the route at all), so this exists for the whitespace-only
    case a client could still send.
    """
    if not firm_id or not firm_id.strip():
        raise HTTPException(status_code=422, detail="firm_id is required")
    return firm_id


def _apply_firm_patch(
    *, db, firm_id: str, doc: dict, patch: dict, actor: AdminActor,
    action: str, before: dict, after: dict, request_id: str,
) -> None:
    """Re-write the firm doc through upsert_firm with ONE field changed,
    audited in the SAME Firestore transaction as the write.

    Mirrors config_routes.py's _apply_config_write shape: the
    @firestore.transactional decorator applies INSIDE this function so the
    module imports with no firebase_admin app initialized. upsert_firm()
    itself is not transactional (it is the operator-bootstrap writer,
    called outside any transaction by scripts/bootstrap_firm.py) so this
    route does its OWN transactional read-patch-write, calling
    firm_ref.set(..., merge=True) directly rather than through upsert_firm
    -- going through upsert_firm here would mean a SECOND read inside the
    transaction (Firestore's reads-before-writes rule would then be
    violated the moment upsert_firm did its own get()). The payload shape
    below is deliberately the SAME field set upsert_firm's own re-run
    branch writes (name, contact_email, allowed_kits, status, kind,
    updated_at), so the two writers can never disagree about what a firm
    document contains.
    """
    from firebase_admin import firestore

    firm_ref = _firm_ref(db, firm_id)

    @firestore.transactional
    def _txn(tx):
        # The READ lives inside the transaction (mirrors config_routes.py):
        # Firestore re-runs this whole body on contention, and a `before`
        # captured outside would go stale on a retry.
        snap = firm_ref.get(transaction=tx)
        if not snap.exists:
            # Unreachable in practice -- the caller already 404'd on a
            # missing firm before opening this transaction -- but a real
            # check rather than an assumption, since a doc deleted between
            # that read and this transaction must not silently write a
            # phantom back into existence.
            raise HTTPException(status_code=404, detail="No such firm")
        current = snap.to_dict() or {}
        merged = {
            "name": current.get("name"),
            "contact_email": current.get("contact_email"),
            "allowed_kits": current.get("allowed_kits")
            if isinstance(current.get("allowed_kits"), list) else [],
            "status": current.get("status", firms.FIRM_STATUS_ACTIVE),
            "kind": current.get("kind") if current.get("kind") in
            _FIRM_KINDS else firms.FIRM_KIND_LIVE,
        }
        merged.update(patch)
        tx.set(firm_ref, {
            **merged,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)

        # SAME transaction: a failing audit write aborts the firm write too
        # (exit criterion 1).
        audit_log.record_in_transaction(
            tx,
            db,
            actor_uid=actor.uid,
            actor_email=actor.email,
            action=action,
            target="firms/{}".format(firm_id),
            before=before,
            after=after,
            request_id=request_id,
        )

    try:
        _txn(db.transaction())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_firm_patch_failed", firm_id=firm_id,
                   action=action, error=str(exc))
        raise HTTPException(status_code=500,
                            detail="firm write failed") from exc


@router.post("/admin/firms")
async def create_firm(
    body: CreateFirmRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Create a firm via backend/services/firms.py::upsert_firm.

    `kind` is REQUIRED by the request schema (no default value on the
    field) -- an omitted kind 422s before this handler ever runs, which is
    the write-layer backstop upsert_firm's own required parameter already
    provides, restated at the HTTP boundary so the error is a clean 422
    rather than upsert_firm's ValueError surfacing as a 500.

    AUDITED IN-TRANSACTION, not through upsert_firm (which has no
    transaction of its own and is also the operator-bootstrap path that
    must keep working with no admin service running at all). This route
    does its own transactional create so the audit row shares the same
    commit, mirroring _apply_firm_patch's shape for the update routes.
    """
    firm_id = _validated_firm_id(body.firm_id)
    if body.kind not in _FIRM_KINDS:
        raise HTTPException(
            status_code=422,
            detail="kind must be one of {}".format(", ".join(_FIRM_KINDS)),
        )
    if body.status not in _FIRM_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of {}".format(
                ", ".join(_FIRM_STATUSES)),
        )

    db = _db()
    from firebase_admin import firestore

    firm_ref = _firm_ref(db, firm_id)
    request_id = audit_log.new_request_id()
    created_holder: dict[str, Any] = {}

    @firestore.transactional
    def _txn(tx):
        snap = firm_ref.get(transaction=tx)
        existed = snap.exists
        payload = {
            "name": body.name,
            "contact_email": body.contact_email,
            "allowed_kits": list(body.allowed_kits),
            "status": body.status,
            "kind": body.kind,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        if existed:
            tx.set(firm_ref, payload, merge=True)
        else:
            payload["created_at"] = firestore.SERVER_TIMESTAMP
            payload["balance_credits"] = 0
            payload["balance_updated_at"] = firestore.SERVER_TIMESTAMP
            tx.set(firm_ref, payload)
        created_holder["created"] = not existed

        audit_log.record_in_transaction(
            tx,
            db,
            actor_uid=actor.uid,
            actor_email=actor.email,
            action=ACTION_FIRM_CREATE,
            target="firms/{}".format(firm_id),
            before=None if not existed else (snap.to_dict() or {}),
            after={
                "name": body.name, "contact_email": body.contact_email,
                "kind": body.kind, "status": body.status,
                "allowed_kits": list(body.allowed_kits),
            },
            request_id=request_id,
        )

    try:
        _txn(db.transaction())
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_firm_create_failed", firm_id=firm_id,
                   error=str(exc))
        raise HTTPException(status_code=500,
                            detail="firm write failed") from exc

    _log.info("admin_firm_created", firm_id=firm_id, kind=body.kind,
              created=created_holder["created"], actor_uid=actor.uid,
              request_id=request_id)
    return {
        "firm_id": firm_id,
        "created": created_holder["created"],
        "request_id": request_id,
    }


@router.get("/admin/firms")
async def list_firms(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Every firm, with kind/balance/status -- unfiltered (see module
    docstring). A read, so no audit row."""
    db = _db()
    try:
        docs = list(db.collection(_FIRMS_COLLECTION).stream())
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_firm_list_failed", error=str(exc))
        raise HTTPException(status_code=503,
                            detail="firm store unavailable") from exc
    firms_view = [
        _public_firm_view(snap.id, snap.to_dict() or {}) for snap in docs
    ]
    firms_view.sort(key=lambda f: f["firm_id"])
    return {"firms": firms_view}


@router.get("/admin/firms/{firm_id}")
async def get_firm(
    firm_id: str,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    ledger_limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    """One firm's profile, balance, and a page of ledger rows.

    RECONCILES FIRST (exit criterion 3): reconcile_expired_for_firm runs as
    ITS OWN transaction per expired link, once per KNOWN_CHANNELS entry,
    BEFORE the firm doc (and therefore the balance) is read -- so a dead
    hourly sweep (Track B bead B5) cannot leave this page showing a balance
    that does not yet reflect an expired link's refund. A per-channel
    reconciliation failure is logged and skipped rather than 500ing the
    whole page, matching reconcile_expired_for_firm's own per-link
    tolerance: an operator viewing a firm's balance must not be blocked by
    an unrelated Firestore hiccup on the OTHER channel's link collection.
    """
    firm_id = _validated_firm_id(firm_id)

    for channel in KNOWN_CHANNELS:
        try:
            credit_ledger.reconcile_expired_for_firm(firm_id, channel=channel)
        except Exception as exc:  # noqa: BLE001 -- best-effort, see docstring
            _log.error("admin_firm_reconcile_failed", firm_id=firm_id,
                       channel=channel, error=str(exc))

    db = _db()
    doc = _get_firm_or_404(db, firm_id)
    entries = credit_ledger.read_entries(db, firm_id, limit=None)
    # Newest first for a console table; read_entries returns oldest-first
    # (the replay-friendly order credit_ledger.py's own docstring names).
    page = list(reversed(entries))[:ledger_limit]
    return {
        **_public_firm_view(firm_id, doc),
        "ledger": page,
        "ledger_truncated": len(entries) > len(page),
    }


@router.patch("/admin/firms/{firm_id}/status")
async def set_firm_status(
    firm_id: str,
    body: SetStatusRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    firm_id = _validated_firm_id(firm_id)
    if body.status not in _FIRM_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of {}".format(
                ", ".join(_FIRM_STATUSES)),
        )
    db = _db()
    doc = _get_firm_or_404(db, firm_id)
    before_status = doc.get("status")
    request_id = audit_log.new_request_id()
    _apply_firm_patch(
        db=db, firm_id=firm_id, doc=doc, patch={"status": body.status},
        actor=actor, action=ACTION_FIRM_STATUS,
        before={"status": before_status}, after={"status": body.status},
        request_id=request_id,
    )
    _log.info("admin_firm_status_set", firm_id=firm_id, status=body.status,
              actor_uid=actor.uid, request_id=request_id)
    return {
        "firm_id": firm_id, "status": body.status,
        "before_status": before_status, "request_id": request_id,
    }


@router.patch("/admin/firms/{firm_id}/allowed_kits")
async def set_firm_allowed_kits(
    firm_id: str,
    body: SetAllowedKitsRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    firm_id = _validated_firm_id(firm_id)
    db = _db()
    doc = _get_firm_or_404(db, firm_id)
    before_kits = doc.get("allowed_kits") if isinstance(
        doc.get("allowed_kits"), list) else []
    request_id = audit_log.new_request_id()
    _apply_firm_patch(
        db=db, firm_id=firm_id, doc=doc,
        patch={"allowed_kits": list(body.allowed_kits)},
        actor=actor, action=ACTION_FIRM_ALLOWED_KITS,
        before={"allowed_kits": before_kits},
        after={"allowed_kits": list(body.allowed_kits)},
        request_id=request_id,
    )
    _log.info("admin_firm_allowed_kits_set", firm_id=firm_id,
              count=len(body.allowed_kits), actor_uid=actor.uid,
              request_id=request_id)
    return {
        "firm_id": firm_id, "allowed_kits": list(body.allowed_kits),
        "request_id": request_id,
    }


@router.patch("/admin/firms/{firm_id}/kind")
async def set_firm_kind(
    firm_id: str,
    body: SetKindRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Reclassify a firm mock<->live. `reason` is required; the UI's
    confirm-twice is a client-side control this route cannot see or
    enforce (see SetKindRequest's docstring)."""
    firm_id = _validated_firm_id(firm_id)
    if body.kind not in _FIRM_KINDS:
        raise HTTPException(
            status_code=422,
            detail="kind must be one of {}".format(", ".join(_FIRM_KINDS)),
        )
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason is required")
    db = _db()
    doc = _get_firm_or_404(db, firm_id)
    before_kind = doc.get("kind") if doc.get("kind") in _FIRM_KINDS else \
        firms.FIRM_KIND_LIVE
    request_id = audit_log.new_request_id()
    _apply_firm_patch(
        db=db, firm_id=firm_id, doc=doc, patch={"kind": body.kind},
        actor=actor, action=ACTION_FIRM_KIND,
        before={"kind": before_kind, "reason": None},
        after={"kind": body.kind, "reason": body.reason},
        request_id=request_id,
    )
    _log.info("admin_firm_kind_set", firm_id=firm_id, kind=body.kind,
              reason=body.reason, actor_uid=actor.uid, request_id=request_id)
    return {
        "firm_id": firm_id, "kind": body.kind, "before_kind": before_kind,
        "request_id": request_id,
    }
