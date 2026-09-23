"""POST /admin/links/sweep-expired -- the hourly expired-link refund sweep
(bd polyglot-pdf-8vgfh, plan: "Refund on unopened expiry").

WHAT THIS ROUTE IS. Cloud Scheduler's hourly caller of bead A5's
transactional refund helper (backend/services/credit_ledger.py's
refund_expired_link). It queries links[_<channel>] for every record with
status == minted AND open_deadline < now, and refunds each ONE AT A TIME
through that helper -- which itself re-reads link_redemptions first and
refuses when the link was opened, so a race with a client filling the form
out cannot be refunded out from under them (see credit_ledger.py's own
"WHY THE REDEMPTION DOC IS READ FIRST" section for the full argument; this
route adds no new refund logic of its own).

WHY A CHANNEL LOOP, NOT ONE QUERY. THE ADMIN SERVICE HAS NO CHANNEL (same
rule as every other admin_backend module, see admin_backend/main.py's
docstring): links and links_staging are separate Firestore collections, so
"sweep everything" means one query per known channel, not a single
cross-channel query Firestore cannot express. An explicit `?channel=`
query param sweeps ONE channel (an operator manually re-running a stuck
channel, or a future per-channel Scheduler job); omitting it iterates the
full KNOWN_CHANNELS list, which is what the hourly job actually calls.

WHY THE RESPONSE IS COUNTS ONLY. "Every refund the sweep performs is
audited by A5's helper" (the bead description) in TWO senses: refund_
expired_link's committed ledger entry (actor=system:sweep_expired_links)
IS the accounting record of what happened to a firm's balance, and this
route additionally writes an admin_audit_log row IN THE SAME TRANSACTION
as each refund (via credit_ledger.refund_expired_link's extra_writes hook,
bd polyglot-pdf-8vgfh's extension to that function) to satisfy Epic 2
criterion 5 ("every mutating admin route audits in the required form").
Between the ledger entry and the audit row, per-link detail already has a
durable home; returning it a third time in the HTTP response would be a
copy that can drift; per-channel and total COUNTS are what an operator or
a Scheduler failure alert actually needs to see at a glance.

GATE: require_google_oidc(audience, allowed_caller_emails), THIS ROUTE'S
own URL as audience and the Cloud Scheduler job's service account email as
the sole allowed caller (admin_backend/services/admin_auth.py). Configured
by two env vars read at IMPORT time -- ADMIN_SERVICE_URL and
SWEEP_SCHEDULER_SA_EMAIL -- because require_google_oidc is a FACTORY that
needs both bound before FastAPI can wire the dependency; a missing value
refuses every call rather than accepting an unconfigured (thus effectively
audience-less or allowlist-less) gate.

A PER-LINK FAILURE (LinkNotRefundable from a race the lazy path already
won, or a single link's store hiccup) is logged and SKIPPED, exactly like
reconcile_expired_for_firm's own per-link handling -- one bad link must
never abort the whole hourly pass and leave every other expired link in
the channel unrefunded for another hour.

ASCII only.
"""
from __future__ import annotations

import os
import time
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException

from admin_backend.services import audit_log
from admin_backend.services.admin_auth import (
    GoogleServiceActor,
    require_google_oidc,
)
from backend.services import credit_ledger

_log = structlog.get_logger(module="sweep_routes")

router = APIRouter()

# The channels that actually exist -- same pair config_routes.py validates
# against (docs/doctrine/promotion-tiers.md): staging is the disposable test
# deploy, demo is the protected target. Kept as this module's OWN copy
# rather than importing config_routes.KNOWN_CHANNELS: the two routes have no
# other reason to depend on each other, and a channel typo here is caught by
# the same literal pair either way.
KNOWN_CHANNELS = ("demo", "staging")

# The audit `action` string for a sweep-triggered refund. A constant, since
# the audit-coverage AST walk and a console filter both key on the STRING
# audit_log.record_in_transaction's `action` argument carries, not on a
# reference to this name.
ACTION_EXPIRY_REFUND = "credits.expiry_refund"

# The actor string A5's helper stamps on every ledger entry this route
# writes. "system:" prefix matches reconcile_expired_for_firm's own
# convention (actor="system:reconcile_expired_for_firm") so a ledger export
# reader can tell "a human clicked something" apart from "a scheduled job
# ran" by the actor field alone, without cross-referencing anything else.
SWEEP_ACTOR = "system:sweep_expired_links"


_SWEEP_ROUTE_PATH = "/admin/links/sweep-expired"


def _audience() -> str:
    """This route's own URL (service root + path) -- the OIDC audience
    Cloud Scheduler's job must present.

    ADMIN_SERVICE_URL holds the admin service's bare Cloud Run URL (the
    SERVICE ROOT, set by an operator from `gcloud run services describe
    ... --format 'value(status.url)'` per deploy-admin.sh's own output,
    and referenced the same way everywhere else this env var appears --
    scripts/setup-admin-service.sh's `--uri="$ADMIN_SERVICE_URL/admin/
    links/sweep-expired"` NOTE line). Cloud Scheduler's job is declared
    with `--oidc-token-audience="$ADMIN_SERVICE_URL/admin/links/
    sweep-expired"` (the FULL route path, not the bare root) -- so this
    function must append the same path here, or every scheduled call's
    `aud` claim (root+path) would never match a bare-root comparison and
    require_google_oidc would reject the one caller it exists to admit
    (bd polyglot-pdf-8vgfh cross-surface review finding 2).

    Never hard-coded: the admin service's own Cloud Run URL is assigned by
    Google at first deploy and is not knowable at code-review time. A
    missing ADMIN_SERVICE_URL means an operator has not finished wiring the
    scheduler job to this route yet, so every call is refused (503, at
    request time via require_google_oidc) rather than accepted against a
    bare "/admin/links/sweep-expired" audience nothing could ever
    legitimately present (no real caller's URL is just a path).
    """
    root = os.getenv("ADMIN_SERVICE_URL", "")
    return root + _SWEEP_ROUTE_PATH if root else ""


def _allowed_caller_emails() -> tuple:
    """The Cloud Scheduler job's service-account email, as the sole
    accepted OIDC caller identity.

    SWEEP_SCHEDULER_SA_EMAIL is set at deploy time (scripts/setup-admin-
    service.sh provisions no NEW service account for the scheduler job
    itself -- see that script's own comment on this -- an operator names
    the identity they attached to the job). Empty when unset, which
    ALLOWLISTS NOTHING: an unconfigured deployment refuses every caller
    rather than silently accepting one nobody has pinned yet.
    """
    email = os.getenv("SWEEP_SCHEDULER_SA_EMAIL", "")
    return (email,) if email else tuple()


def _sweep_channel(channel: str, *, now: float) -> dict:
    """Refund every expired, unopened link in ONE channel. Returns
    {"channel": ..., "refunded": N, "skipped": N}.

    Queries links[_<channel>] directly (rather than reusing
    reconcile_expired_for_firm, which is FIRM-scoped and reads its own
    get_db()) because this sweep is cross-firm by design -- the plan's
    query is "status == minted AND open_deadline < now" with no firm_id
    filter at all.
    """
    from backend.services import links_store as _links_store
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503,
                            detail="link store unavailable")

    collection_name = _links_store._collection_name(channel)
    collection = db.collection(collection_name)
    deadline = int(now)
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = (
            collection
            .where(filter=FieldFilter(
                "status", "==", _links_store.STATUS_MINTED))
            .where(filter=FieldFilter("open_deadline", "<", deadline))
        )
    except ImportError:
        query = (
            collection
            .where("status", "==", _links_store.STATUS_MINTED)
            .where("open_deadline", "<", deadline)
        )

    refunded = 0
    skipped = 0
    for snap in query.stream():
        jti = snap.id
        request_id = audit_log.new_request_id()

        def _audit_write(tx, firm_snapshot, *, _jti=jti,
                         _request_id=request_id, _channel=channel):
            # Reuses links_store's OWN collection-name rule rather than
            # re-deriving the channel-suffix convention here (CLAUDE.md
            # scar #8: one rule, one home).
            audit_log.record_in_transaction(
                tx,
                db,
                actor_uid=SWEEP_ACTOR,
                actor_email=None,
                action=ACTION_EXPIRY_REFUND,
                target="{}/{}".format(
                    _links_store._collection_name(_channel), _jti),
                before={"status": _links_store.STATUS_MINTED},
                after={"status": _links_store.STATUS_REFUNDED},
                channel=_channel,
                request_id=_request_id,
            )

        try:
            credit_ledger.refund_expired_link(
                db, jti, actor=SWEEP_ACTOR, channel=channel, now=now,
                extra_writes=_audit_write,
            )
            refunded += 1
        except credit_ledger.LinkNotRefundable as exc:
            # Already handled (a race with the lazy reconcile path, or the
            # redemption doc landed between the query and this read) --
            # not a failure of THIS pass.
            _log.info("sweep_skip", jti=jti, channel=channel,
                      reason=exc.reason)
            skipped += 1
        except Exception as exc:  # noqa: BLE001 -- one bad link must not
            # abort the whole hourly pass; every other expired link in this
            # channel still gets its refund attempt.
            _log.error("sweep_link_failed", jti=jti, channel=channel,
                       error_type=type(exc).__name__)
            skipped += 1

    return {"channel": channel, "refunded": refunded, "skipped": skipped}


_sweep_oidc_gate = require_google_oidc(
    # Passed as CALLABLES, not resolved values -- see require_google_oidc's
    # own docstring: this module imports once at process start, well
    # before ADMIN_SERVICE_URL / SWEEP_SCHEDULER_SA_EMAIL are necessarily
    # set, so the read must happen per-request, not at import time.
    audience=_audience,
    allowed_caller_emails=_allowed_caller_emails,
)


@router.post("/admin/links/sweep-expired")
async def sweep_expired_links(
    channel: Optional[str] = None,
    actor: Annotated[GoogleServiceActor, Depends(_sweep_oidc_gate)] = None,
) -> dict:
    """Refund every expired, unopened link, one channel or all of them.

    `channel` omitted -> every channel in KNOWN_CHANNELS (the hourly
    Scheduler job's own call shape). `channel` given -> that one channel
    only, validated against KNOWN_CHANNELS exactly like config_routes.py's
    `_validate_channel` (404 on an unknown value, never a query against a
    collection nothing reads).

    Returns {"results": [{"channel", "refunded", "skipped"}, ...],
    "total_refunded": N, "total_skipped": N} -- counts only, per this
    module's docstring.
    """
    if channel is not None and channel not in KNOWN_CHANNELS:
        raise HTTPException(
            status_code=404,
            detail="unknown channel {!r}; known channels are {}".format(
                channel, ", ".join(KNOWN_CHANNELS)),
        )

    channels = (channel,) if channel is not None else KNOWN_CHANNELS
    now = time.time()
    results = [_sweep_channel(ch, now=now) for ch in channels]

    _log.info(
        "sweep_expired_links_complete",
        actor_email=actor.email if actor is not None else None,
        channels=list(channels),
        total_refunded=sum(r["refunded"] for r in results),
        total_skipped=sum(r["skipped"] for r in results),
    )

    return {
        "results": results,
        "total_refunded": sum(r["refunded"] for r in results),
        "total_skipped": sum(r["skipped"] for r in results),
    }
