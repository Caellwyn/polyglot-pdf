"""Credit grant/adjust routes on the admin service (bd polyglot-pdf-zopqq,
Epic 2 Track B bead B1).

TWO ROUTES, ONE UNDERLYING WRITER:

    POST /admin/firms/{firm_id}/credits/grant    subscription_grant | purchase | promo_grant
    POST /admin/firms/{firm_id}/credits/adjust    the signed operator escape hatch

Both call backend/services/credit_ledger.py::append_entry -- THE ONE writer
of firms/{firm_id}.balance_credits (CLAUDE.md scar #8: one rule, one home).
This module adds NO second balance-writing path; it only shapes the HTTP
request into append_entry's keyword arguments and audits the call.

GRANTS TO MOCK FIRMS ARE ALLOWED (plan: "Grants to mock firms are allowed" --
staging needs credits to test). Neither route checks firm.kind at all: kind
only ever gates MINTING (backend/routes/link_routes.py's live-firm-on-
demo-channel-only rule, Epic 2 bead A3), never granting or adjusting. A mock
firm's grants are real ledger entries with firm_kind="mock" snapshotted on
them, which is exactly what keeps them OUT of the income view without this
route needing to refuse anything.

WHY grant AND adjust ARE SEPARATE ROUTES rather than one route branching on
type. append_entry's own type vocabulary already carries six entry types,
and this bead exposes two admin-facing verbs over it: "give this firm
credits for a normal commercial reason" (grant: subscription_grant |
purchase | promo_grant, POSITIVE amounts, usd_amount required for the paid
two) and "the operator's arbitrary correction" (adjust: any sign, `reason`
mandatory). Splitting the ROUTE the same way the plan splits the VERB means
the request schema for each can be exactly as permissive as its meaning
requires -- grant never accepts a `reason` field it would ignore, adjust
never accepts a `usd_amount` field append_entry would then refuse for
carrying one on the wrong type.

AUDITED IN THE SAME FIRESTORE TRANSACTION AS THE LEDGER WRITE (exit
criterion 1). append_entry() already accepts an `extra_writes(tx, firm)`
hook that runs INSIDE its own transaction, after the reads and alongside the
balance/entry writes -- exactly the extension point Epic 2 bead A3's mint
route uses to join a links/{jti} record to the same commit. This module
passes audit_log.record_in_transaction through that hook, so a forced audit
failure aborts append_entry's transaction and the balance is left unchanged
(the SAME property config_routes.py's PUT proves, over a different writer).

actor IS THE ADMIN'S UID (plan: "actor = the admin's uid"), channel IS
ALWAYS None (plan: "channel None" -- the admin service has no channel of its
own; a channel-tagged debit only ever comes from the public backend's mint
route), and firm_kind is SNAPSHOTTED BY append_entry ITSELF from the firm
doc it reads inside its own transaction -- this module never reads the
firm's kind and never passes one in.

SYNC HELPER, ASYNC ROUTE: append_entry is synchronous (Admin SDK), so both
handlers run it under asyncio.to_thread, matching every other admin-service
call into a synchronous Firestore/Auth helper (user_routes.py's
asyncio.to_thread(user_admin....) precedent).

ASCII only.
"""
from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import credit_ledger

_log = structlog.get_logger().bind(module="admin_credit_routes")

router = APIRouter()

# The audit `action` strings for this surface.
ACTION_CREDITS_GRANT = "credits.grant"
ACTION_CREDITS_ADJUST = "credits.adjust"

# The three grant-shaped entry types append_entry recognizes; adjustment is
# deliberately excluded here (it is the OTHER route's only type) so a grant
# request can never smuggle in the signed escape hatch under a "grant" verb.
GRANT_TYPES = (
    credit_ledger.TYPE_SUBSCRIPTION_GRANT,
    credit_ledger.TYPE_PURCHASE,
    credit_ledger.TYPE_PROMO_GRANT,
)

# The two grant types that record money changing hands -- restated here
# (rather than importing credit_ledger.USD_REQUIRED_TYPES and calling it a
# day) because this route must refuse a bad request BEFORE opening a
# transaction, with a 422 the console can show inline, whereas append_entry's
# _validate raises LedgerError meant for a 400/500 boundary a route already
# translates. Kept identical to credit_ledger.USD_REQUIRED_TYPES by
# test_credit_routes.py, so the two cannot silently diverge.
_USD_REQUIRED_GRANT_TYPES = frozenset({
    credit_ledger.TYPE_SUBSCRIPTION_GRANT, credit_ledger.TYPE_PURCHASE,
})


class GrantRequest(BaseModel):
    """type in subscription_grant | purchase | promo_grant; usd_amount
    REQUIRED for the first two and REFUSED otherwise -- exactly as
    append_entry's own _validate enforces, checked again here so the
    refusal is a clean 422 rather than a 500 wrapping a LedgerError.
    """

    type: str
    amount: int
    usd_amount: Optional[float] = None
    kit_id: Optional[str] = None


class AdjustRequest(BaseModel):
    """The signed operator escape hatch. `reason` is required (plan:
    "reason required"), matching credit_ledger.REASON_REQUIRED_TYPES."""

    amount: int
    reason: str


def _validated_firm_id(firm_id: str) -> str:
    if not firm_id or not firm_id.strip():
        raise HTTPException(status_code=422, detail="firm_id is required")
    return firm_id


def _run_append_entry(*, actor: AdminActor, request_id: str, **kwargs) -> dict:
    """append_entry(), with the audit row joined to its transaction via
    extra_writes, plus the shared error-to-HTTP translation both routes
    need.

    `firm` (the snapshot append_entry's transaction body already read) is
    what extra_writes receives -- this closure only needs it to know
    nothing else about the firm, since the audit row's `after` is built from
    the CALLER-SUPPLIED kwargs (the request as submitted), not re-derived
    from the snapshot.
    """
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="credit ledger unavailable")

    action = kwargs.pop("_action")
    target = kwargs.pop("_target")
    after = kwargs.pop("_after")

    def _audit(tx, firm):
        audit_log.record_in_transaction(
            tx,
            db,
            actor_uid=actor.uid,
            actor_email=actor.email,
            action=action,
            target=target,
            before={"balance_credits": firm.get("balance_credits")},
            after=after,
            request_id=request_id,
        )

    try:
        return credit_ledger.append_entry(
            db, actor=actor.uid, extra_writes=_audit, **kwargs)
    except credit_ledger.InsufficientCredits as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except credit_ledger.LedgerError as exc:
        msg = str(exc)
        status = 404 if "does not exist" in msg else 422
        raise HTTPException(status_code=status, detail=msg) from exc
    except Exception as exc:  # noqa: BLE001
        # A forced audit-write failure (exit criterion 1) surfaces here as
        # whatever Firestore raises, NOT as a LedgerError -- append_entry's
        # transaction aborts and re-raises the underlying exception
        # untouched. Without this catch-all it would propagate as an
        # unhandled 500 through FastAPI's default exception middleware
        # instead of the same clean, logged 500 config_routes.py's and
        # firm_routes.py's equivalents return.
        _log.error("admin_credit_write_failed", action=kwargs.get("entry_type"),
                   firm_id=kwargs.get("firm_id"), error=str(exc))
        raise HTTPException(status_code=500,
                            detail="credit ledger write failed") from exc


@router.post("/admin/firms/{firm_id}/credits/grant")
async def grant_credits(
    firm_id: str,
    body: GrantRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Grant credits to a firm (subscription_grant | purchase | promo_grant).

    Refuses BEFORE any write: an unknown type, a non-positive amount, a
    missing usd_amount on the two paid types, or a usd_amount on promo_grant
    -- all 422, all checked here so the console gets a clean field-level
    error rather than a 500 from append_entry's own LedgerError (which still
    backstops this route for any case the checks below miss, e.g. a
    negative usd_amount).
    """
    firm_id = _validated_firm_id(firm_id)
    if body.type not in GRANT_TYPES:
        raise HTTPException(
            status_code=422,
            detail="type must be one of {}".format(", ".join(GRANT_TYPES)),
        )
    if body.amount <= 0:
        raise HTTPException(status_code=422,
                            detail="amount must be a positive integer")
    if body.type in _USD_REQUIRED_GRANT_TYPES:
        if body.usd_amount is None:
            raise HTTPException(
                status_code=422,
                detail="{} requires usd_amount".format(body.type),
            )
    elif body.usd_amount is not None:
        raise HTTPException(
            status_code=422,
            detail="{} must not carry a usd_amount".format(body.type),
        )

    request_id = audit_log.new_request_id()
    result = await asyncio.to_thread(
        _run_append_entry,
        actor=actor, request_id=request_id,
        firm_id=firm_id, entry_type=body.type, amount=body.amount,
        usd_amount=body.usd_amount, kit_id=body.kit_id,
        _action=ACTION_CREDITS_GRANT,
        _target="firms/{}/ledger#grant".format(firm_id),
        _after={
            "type": body.type, "amount": body.amount,
            "usd_amount": body.usd_amount, "kit_id": body.kit_id,
        },
    )
    _log.info("admin_credits_granted", firm_id=firm_id, type=body.type,
              amount=body.amount, actor_uid=actor.uid, request_id=request_id)
    return {**result, "request_id": request_id}


@router.post("/admin/firms/{firm_id}/credits/adjust")
async def adjust_credits(
    firm_id: str,
    body: AdjustRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """The operator's signed adjustment. `reason` is required (422 if
    blank); `amount` may be positive or negative, matching adjustment's
    place outside both POSITIVE_ONLY_TYPES and NEGATIVE_ONLY_TYPES."""
    firm_id = _validated_firm_id(firm_id)
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason is required")
    if body.amount == 0:
        raise HTTPException(status_code=422, detail="amount must be non-zero")

    request_id = audit_log.new_request_id()
    result = await asyncio.to_thread(
        _run_append_entry,
        actor=actor, request_id=request_id,
        firm_id=firm_id, entry_type=credit_ledger.TYPE_ADJUSTMENT,
        amount=body.amount, reason=body.reason,
        _action=ACTION_CREDITS_ADJUST,
        _target="firms/{}/ledger#adjust".format(firm_id),
        _after={"amount": body.amount, "reason": body.reason},
    )
    _log.info("admin_credits_adjusted", firm_id=firm_id, amount=body.amount,
              reason=body.reason, actor_uid=actor.uid, request_id=request_id)
    return {**result, "request_id": request_id}
