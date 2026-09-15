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

A THIRD ROUTE, THE MONTHLY PLAN TOP-UP (bd polyglot-pdf-0euzk):

    POST /admin/credits/monthly-topup

Cloud Scheduler's monthly caller (cron "5 0 1 * *" UTC -- the 1st of the
month, 5 minutes past midnight, matching scripts/setup-admin-service.sh's
NOTE block), gated by require_google_oidc EXACTLY like sweep_routes.py's
hourly expired-link sweep (its own module docstring's "WHY A CHANNEL LOOP"
section does not apply here -- a firm's balance is not channel-partitioned,
so this route needs no channel loop at all). For every firm with `status ==
active` and a stored `plan`, it writes ONE subscription_grant through
append_entry() so the balance becomes EXACTLY plan.monthly_credits when
plan.rollover is False (amount = monthly_credits - balance; SKIPPED,
writing nothing, when the balance is already at or above the cap -- a
mid-month grant or a firm that has not spent down must not be topped up a
second time in the same run) or INCREASES by monthly_credits when rollover
is True. usd_amount is ALWAYS None ("no money moved" -- the plan's own
words: a monthly top-up is not income, the firm already pays its recurring
fee outside this ledger), which is exactly why bd polyglot-pdf-0euzk widened
credit_ledger.py's subscription_grant from always-requiring usd_amount to
USD_OPTIONAL_TYPES (validated when given, never required) -- see that
module's own comment on the split.

THE CLOUD SCHEDULER TRIGGER IS INTERIM (bd polyglot-pdf-hnlj3, 2026-09-15).
Epic 5's Stripe integration will call the SAME per-firm helper,
topup_firm() (below), from a payment webhook (invoice.paid / subscription
renewal) instead of waiting for the monthly cron pass -- topping up the
one firm the webhook event names the moment its payment actually clears,
rather than on a fixed calendar date that may run before or after the
firm's own billing cycle lands. This is WHY the per-firm top-up logic is
its own function (topup_firm) rather than inlined in the loop below: the
loop (run_monthly_topup / _run_monthly_topup) is the Scheduler-specific
caller, and topup_firm is the reusable core the webhook route will call
directly, once, for its one firm -- no change to topup_firm's own contract
expected when that lands. Until Epic 5 ships, the Scheduler route below
remains the ONLY way a firm's monthly credits are actually granted.

IDEMPOTENT BY MONTH, ON THE LEDGER ITSELF, NOT ON A SEPARATE MARKER DOC,
AND SAFE UNDER CONCURRENT INVOCATION. Every entry this route writes carries
`period: "YYYY-MM"` (credit_ledger.py's nullable `period` field, bd
polyglot-pdf-0euzk). TWO checks enforce this, not one: a fast pre-
transaction query (_already_topped_up_this_period) that skips the common
sequential re-run without paying for a transaction round trip, AND a
second, RACE-SAFE check inside credit_ledger.append_entry()'s own
transaction (raises DuplicatePeriodEntry) that is what actually makes two
OVERLAPPING invocations safe -- Firestore re-runs a contended transaction
body on the loser, so the loser re-reads the winner's just-committed
period row and refuses there, on real state, rather than on a value read
before either committed. A re-run in the same month (a retried Scheduler
call, a second manual invocation, or two calls racing each other)
therefore writes NOTHING for any firm already topped up that period --
the sequential case proven by test_monthly_topup.py (dropping the fast
check and watching a second run double-grant), the concurrent case by
test_credit_ledger.py's transactional race test for this route
(interleaving two append_entry calls with the same period and watching
exactly one commit).

MOCK FIRMS ARE TOPPED UP TOO (plan: "Mock firms are topped up too -- staging
needs credits"), mirroring grant_credits/credit_routes.py's own "grants to
mock firms are allowed" rule: this route does not read or filter on
firm.kind at all, only on status and the presence of a plan.

A NEGATIVE BALANCE (the metered soft-launch mode, CREDITS_ENFORCED off,
letting a firm's balance go below zero) is brought UP TO THE CAP too, not
just topped up by the shortfall from zero -- `monthly_credits - balance`
already computes the right amount when balance is negative (a bigger
positive amount than a from-zero top-up would grant), since the top-up's
whole point is "the balance IS monthly_credits after this runs" for a
no-rollover plan.

A PER-FIRM FAILURE (a malformed plan on one firm's doc, a Firestore hiccup)
is LOGGED AND SKIPPED, exactly like sweep_routes.py's per-link tolerance --
one bad firm must never abort the whole monthly pass and leave every other
firm un-topped-up for another month.

ASCII only.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin_backend.services import audit_log
from admin_backend.services.admin_auth import (
    AdminActor,
    GoogleServiceActor,
    require_app_admin,
    require_google_oidc,
)
from backend.services import credit_ledger, plans

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


# ==========================================================================
# POST /admin/credits/monthly-topup (bd polyglot-pdf-0euzk)
# ==========================================================================

_MONTHLY_TOPUP_ROUTE_PATH = "/admin/credits/monthly-topup"

ACTION_CREDITS_MONTHLY_TOPUP = "credits.monthly_topup"

# The actor stamped on every entry this route writes -- "system:" prefix
# matches sweep_routes.py's SWEEP_ACTOR convention, so a ledger_export
# reader can tell "a scheduled job ran" from "a human clicked something" by
# the actor field alone.
MONTHLY_TOPUP_ACTOR = "system:monthly_topup"


def _topup_audience() -> str:
    """This route's own URL (service root + path) -- mirrors sweep_routes.py's
    _audience() exactly, including WHY it is a function (read per-request,
    not at import time, since ADMIN_SERVICE_URL is set at deploy time)."""
    root = os.getenv("ADMIN_SERVICE_URL", "")
    return root + _MONTHLY_TOPUP_ROUTE_PATH if root else ""


def _topup_allowed_caller_emails() -> tuple:
    """The Cloud Scheduler monthly-top-up job's service-account email --
    mirrors sweep_routes.py's _allowed_caller_emails() exactly, one env var
    over. A SEPARATE env var from SWEEP_SCHEDULER_SA_EMAIL on purpose: the
    two jobs may run under different scheduler identities, and conflating
    them would mean rotating one job's caller credential silently changes
    what the other job accepts."""
    email = os.getenv("MONTHLY_TOPUP_SCHEDULER_SA_EMAIL", "")
    return (email,) if email else tuple()


def _current_period(now: float) -> str:
    """The calendar month `now` falls in, as "YYYY-MM" in UTC -- the ledger
    entry's `period` and the idempotency key this route queries on. UTC,
    not local time: the Scheduler job itself is declared in UTC (cron
    "5 0 1 * *" UTC, scripts/setup-admin-service.sh), and a server-local
    timezone would make the boundary firm-dependent for no reason."""
    return time.strftime("%Y-%m", time.gmtime(now))


def _already_topped_up_this_period(db, firm_id: str, period: str) -> bool:
    """True if firms/{firm_id}/ledger already carries a subscription_grant
    entry for THIS period -- the FAST-PATH half of the idempotency gate (bd
    polyglot-pdf-0euzk exit criterion 1: "a second run in the same month
    writes nothing").

    Runs BEFORE append_entry's transaction even opens, purely to skip the
    transaction round trip in the overwhelmingly common case (a re-run
    hours or days later, never overlapping the original run). It is NOT
    what makes idempotency safe under concurrency -- a caller-side
    pre-check is check-then-act, and two overlapping calls could both pass
    it before either commits. The RACE-SAFE half is
    credit_ledger.append_entry()'s own in-transaction re-check (raises
    DuplicatePeriodEntry), which topup_firm below also treats as
    skipped_already_run. Both halves call the SAME
    credit_ledger.query_period_entries() so they can never disagree about
    what "already topped up" means.
    """
    return len(credit_ledger.query_period_entries(
        db, firm_id, credit_ledger.TYPE_SUBSCRIPTION_GRANT, period)) > 0


def topup_firm(db, firm_id: str, firm: dict, *, period: str,
               actor: str = None) -> str:
    """Top up ONE firm's balance per its stored plan. Returns one of
    "topped_up", "skipped_at_cap", "skipped_already_run", or
    "skipped_no_plan" -- a per-firm outcome the route sums into its
    response, mirroring sweep_routes.py's refunded/skipped counts.

    FACTORED OUT (bd polyglot-pdf-hnlj3) so a single-firm caller can reuse
    it without going through the whole-firm-collection loop below --
    Epic 5's Stripe webhook (invoice.paid / subscription renewal) is the
    named future caller, topping up the ONE firm the webhook event names
    the moment its payment clears, rather than waiting for the monthly
    Scheduler pass. `actor` defaults to MONTHLY_TOPUP_ACTOR (the Scheduler
    route's own actor string, unchanged) so run_monthly_topup below needs
    no call-site change; a future webhook caller passes its OWN actor
    string (e.g. "system:stripe_webhook") so a ledger_export reader can
    still tell which trigger produced a given entry, exactly the same
    distinction MONTHLY_TOPUP_ACTOR's own "system:" prefix convention
    exists to preserve (see that constant's comment). NO BEHAVIOUR CHANGE
    beyond the extraction and the new (defaulted) parameter -- every
    existing test in test_monthly_topup.py pins this unchanged.

    "skipped_already_run" comes back via TWO different paths: the fast
    _already_topped_up_this_period check below (the common case -- a re-run
    that does not overlap the original), or a caught
    credit_ledger.DuplicatePeriodEntry from append_entry() itself (the rare
    concurrent-overlap case, where this call's fast check ran before the
    other call committed, and append_entry's own in-transaction re-check is
    what actually catches it). Both outcomes are indistinguishable to the
    caller on purpose -- "this firm was already topped up this period" is
    true either way, and which of the two checks caught it is an
    implementation detail the response does not need to expose.

    RAISES on a genuine write failure (a malformed plan, a Firestore
    hiccup) -- the caller (run_monthly_topup) catches per-firm, logs, and
    counts it as a failure, exactly like reconcile_expired_for_firm's own
    per-link tolerance.
    """
    if actor is None:
        actor = MONTHLY_TOPUP_ACTOR

    plan = firm.get("plan")
    if not isinstance(plan, dict):
        return "skipped_no_plan"
    try:
        plans.validate_plan(plan)
    except ValueError:
        # A malformed plan (should be impossible once every write goes
        # through set_firm_plan's own validate_plan call, but a hand-edited
        # doc or a pre-validation-era row is not this route's problem to
        # crash the whole monthly pass over) is treated as no-plan: skip,
        # log, move on.
        return "skipped_no_plan"

    if _already_topped_up_this_period(db, firm_id, period):
        return "skipped_already_run"

    monthly_credits = plan["monthly_credits"]
    rollover = plan["rollover"]
    balance = firm.get("balance_credits")
    if not isinstance(balance, int) or isinstance(balance, bool):
        balance = 0

    if rollover:
        amount = monthly_credits
    else:
        if balance >= monthly_credits:
            # Already at or above the cap (a mid-month grant, or a firm
            # that has not spent down) -- nothing to write. This is NOT
            # "skipped_already_run": the period check above already ruled
            # that out, so reaching here means this firm's balance is
            # simply already at/over the cap this run.
            return "skipped_at_cap"
        amount = monthly_credits - balance

    def _audit(tx, firm_snapshot):
        audit_log.record_in_transaction(
            tx,
            db,
            actor_uid=actor,
            actor_email=None,
            action=ACTION_CREDITS_MONTHLY_TOPUP,
            target="firms/{}/ledger#monthly_topup".format(firm_id),
            before={"balance_credits": firm_snapshot.get("balance_credits")},
            after={"period": period, "amount": amount,
                  "monthly_credits": monthly_credits, "rollover": rollover},
            request_id=audit_log.new_request_id(),
        )

    try:
        credit_ledger.append_entry(
            db, firm_id, entry_type=credit_ledger.TYPE_SUBSCRIPTION_GRANT,
            amount=amount, actor=actor, usd_amount=None,
            channel=None, reason="monthly top-up {}".format(period),
            period=period, extra_writes=_audit,
        )
    except credit_ledger.DuplicatePeriodEntry:
        # The RACE this route's fast _already_topped_up_this_period check
        # above cannot close by itself: two overlapping invocations can
        # both pass that check before either commits. append_entry()'s own
        # in-transaction re-check is what actually catches the loser here,
        # on Firestore's automatic retry-on-contention -- see
        # DuplicatePeriodEntry's own docstring. Same outcome as the fast
        # path: this firm was (by the time this call is done) already
        # topped up for this period, by the winner of the race.
        return "skipped_already_run"
    return "topped_up"


def _run_monthly_topup(*, period: str) -> dict:
    """Synchronous body of run_monthly_topup(), run under asyncio.to_thread.

    Iterates EVERY active firm (backend/services/firms.py's
    FIRM_STATUS_ACTIVE -- a suspended firm is not topped up, matching the
    intuition that suspending a firm pauses its subscription too) and calls
    topup_firm() for each (bd polyglot-pdf-hnlj3: factored out of this loop
    so a future single-firm caller, e.g. Epic 5's Stripe webhook, can reuse
    it without this loop). A per-firm exception is caught, logged, and
    counted as a failure -- one bad firm's doc must never abort the whole
    monthly pass and leave every other firm un-topped-up.
    """
    from backend.services.auth import get_db
    from backend.services.firms import FIRM_STATUS_ACTIVE

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503,
                            detail="firm store unavailable")

    outcomes = {
        "topped_up": [], "skipped_at_cap": [], "skipped_already_run": [],
        "skipped_no_plan": [], "failed": [],
    }
    for snap in db.collection(credit_ledger.FIRMS_COLLECTION).stream():
        firm_id = snap.id
        firm = snap.to_dict() or {}
        if firm.get("status") != FIRM_STATUS_ACTIVE:
            continue
        try:
            outcome = topup_firm(db, firm_id, firm, period=period)
            outcomes[outcome].append(firm_id)
        except Exception as exc:  # noqa: BLE001 -- one bad firm must not
            # abort the whole monthly pass.
            _log.error("monthly_topup_firm_failed", firm_id=firm_id,
                       error=str(exc))
            outcomes["failed"].append(firm_id)

    return outcomes


_monthly_topup_oidc_gate = require_google_oidc(
    audience=_topup_audience,
    allowed_caller_emails=_topup_allowed_caller_emails,
)


@router.post(_MONTHLY_TOPUP_ROUTE_PATH)
async def run_monthly_topup(
    actor: Annotated[GoogleServiceActor, Depends(_monthly_topup_oidc_gate)] = None,
) -> dict:
    """The monthly plan top-up: for every active firm with a stored plan,
    write ONE subscription_grant that brings the balance to (no rollover) or
    adds (rollover) plan.monthly_credits -- see the module docstring for the
    full rule and the idempotency guarantee.

    Returns per-outcome firm_id lists plus their counts -- enough detail for
    an operator to see WHICH firms were topped up without a second read,
    while still keeping the response small (a firm_id list, not a ledger
    entry per firm; the entry and its audit row are the durable record,
    exactly as sweep_routes.py's own docstring argues for its counts-only
    response).
    """
    period = _current_period(time.time())
    outcomes = await asyncio.to_thread(_run_monthly_topup, period=period)

    _log.info(
        "monthly_topup_complete",
        actor_email=actor.email if actor is not None else None,
        period=period,
        topped_up=len(outcomes["topped_up"]),
        skipped_at_cap=len(outcomes["skipped_at_cap"]),
        skipped_already_run=len(outcomes["skipped_already_run"]),
        skipped_no_plan=len(outcomes["skipped_no_plan"]),
        failed=len(outcomes["failed"]),
    )

    return {
        "period": period,
        "topped_up": outcomes["topped_up"],
        "skipped_at_cap": outcomes["skipped_at_cap"],
        "skipped_already_run": outcomes["skipped_already_run"],
        "skipped_no_plan": outcomes["skipped_no_plan"],
        "failed": outcomes["failed"],
    }
