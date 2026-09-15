"""Link listing + revoke on the admin service (bd polyglot-pdf-jmiys, Epic 2
Track B bead B4; the listing route's gate widened by bd polyglot-pdf-scaig).

TWO ROUTES, ONE FIRM-SCOPED READ AND ONE JTI-SCOPED WRITE:

    GET  /admin/firms/{firm_id}/links?status=&employee_id=&channel=
    POST /admin/links/{jti}/revoke?channel=

DIFFERENT GATES ON THE TWO ROUTES, DELIBERATELY. Revoke stays behind
require_app_admin_or_owning_manager (bd polyglot-pdf-dmjl5): an app admin
may revoke any firm's link; a firm manager only their own; an employee
never (there is no employee branch on that gate at all). Listing is behind
the WIDER require_app_admin_or_owning_manager_or_employee (bd
polyglot-pdf-scaig): the same two actors, PLUS a firm EMPLOYEE, who sees
ONLY links whose employee_id equals their own uid -- forced server-side
from the verified token, never the query (see list_firm_links's own
docstring). The two routes intentionally do NOT share one gate here: an
employee-role staff account was originally refused with a flat 403 on
LISTING (an actor kind the plan's original composite gate never had a
branch for), even though the bead that shipped this file already had the
right shape for a manager and an app admin -- see bd polyglot-pdf-scaig for
the full story and why a THIRD actor kind became a new dependency rather
than a widening of the existing one.

CHANNEL IS A REQUIRED, EXPLICIT QUERY PARAMETER ON BOTH ROUTES. The admin
service has no channel of its own (admin_backend/main.py's own docstring:
"nothing here may derive a Firestore collection name from LINK_CHANNEL"),
and links[_<channel>] / link_redemptions[_<channel>] are genuinely different
Firestore collections per channel (backend/services/links_store.py,
backend/services/link_redemptions.py) -- there is no cross-channel query
Firestore can express, so "which channel" cannot default to anything and
must not silently resolve to "demo". A missing or unknown value is 422,
validated against the same two-channel vocabulary sweep_routes.py and
firm_routes.py already use.

WHY THE FIRM-SCOPING SHAPE HERE IS NOT admin_auth.resolve_target_firm. That
helper answers "does the CALLER'S OWN firm identity match a firm named in
the REQUEST BODY", and refuses a manager who names ANY firm at all (even
their own) with 403 -- the right rule for /admin/users, where a manager
never has a reason to type their own firm_id. THIS route's firm_id is a URL
PATH SEGMENT, not a body field: a manager must be able to GET their own
firm's link list by naming it in the URL (there is nowhere else to put it
in a GET), so "manager named a firm" cannot be the refusal condition here.
What the bead requires instead is an EXISTENCE-HIDING scoping check --
"a manager listing another firm's links gets 404 (not 403)" (bead exit
criterion 2) -- the same 404-for-out-of-scope shape user_routes.py's
_require_account_in_firm and form_kit_routes.py's
_require_firm_owns_private_kit both use: a manager who tries a firm_id
that is not theirs must see the SAME response a nonexistent firm_id would
produce, so the status code cannot be used to probe which firms exist.
_require_owning_firm below is this route's OWN small helper for that
specific shape; it is not a rename or a second copy of resolve_target_firm,
which stays the one home for the body-field rule it already owns.

REVOKE HAS NO FIRM IN ITS URL AT ALL -- POST /admin/links/{jti}/revoke
takes only the jti. The firm a manager may revoke is discovered by READING
the mint record first (it already carries firm_id, per links_store.py's
schema) and then applying the SAME _require_owning_firm check against that
firm -- so a manager cannot revoke a jti from a firm that is not theirs,
and (for a jti that does not exist under `channel`) the response is the
SAME 404 as a jti from a firm outside their own, again refusing to let the
status code answer "does this jti exist at all".

WHY revoke_link IS NOT A NEW backend/services/links_store.py FUNCTION.
links_store.py's own docstring says schema-and-reader/writer functions land
with the bead that first needs them ("A5 adds the refund/revoke writers");
this bead (B4) is the first and only consumer of a revoke write, and it is
an ADMIN-SERVICE-ONLY mutation (the public backend never revokes anything).
Keeping the transactional write here, reading and writing the collection
through links_store's own PUBLIC constants and _collection_name() (never a
second hard-coded "links" string), mirrors exactly how admin_backend/routes/
sweep_routes.py already reads that same collection directly rather than
routing through a links_store.py function that does not exist -- one
precedent, not a new one. B4's surfaces list
(admin_backend/routes/link_routes.py, admin_backend/tests/unit/
test_admin_link_routes.py, backend/tests/integration/
test_revoked_link_open.py) names no backend/services/links_store.py change,
and none is made.

WHY REVOKE DOES ITS OWN TRANSACTIONAL READ-CHECK-WRITE (mirrors
firm_routes.py's _apply_firm_patch shape) RATHER THAN GOING THROUGH
backend/services/credit_ledger.py. A revoke touches NO credit balance and
writes NO ledger entry -- it only flips links[_<channel>]/{jti}.status and
stamps revoked_by/revoked_at. credit_ledger.append_entry's extra_writes
hook exists for a write that must share a TRANSACTION credit_ledger itself
opens around a balance mutation; there is no balance mutation here, so
there is nothing to attach to. The audit row shares THIS route's own
@firestore.transactional body instead (the plain in-transaction form
firm_routes.py and config_routes.py already use), so a forced audit failure
leaves the link's status unchanged (exit criterion 3's atomicity half).

REVOKING AN ALREADY-TERMINAL LINK (opened, completed, refunded, or already
revoked) IS A REFUSAL, NOT A SILENT NO-OP OR A SILENT OVERWRITE. Only a
STATUS_MINTED record may transition to STATUS_REVOKED: overwriting an
opened/completed link's status would corrupt a record a client has already
acted on (and, per links_store.py's own docstring, status is a read-mostly
DERIVED CACHE that real money-moving code never trusts alone -- but the
admin console's link table DOES display it, so it must stay a truthful
history rather than a field the last writer stomps). A 409 names the
current status so an operator sees WHY, rather than a bare failure.

THE RESPONSE KEY ALLOWLIST (exit criterion 1) is the SAME shape B2's user
routes and every other admin list route already use: build the dict by hand
from named fields, never **doc or doc.update(...), so a future field added
to either stored document (links[_<channel>] or link_redemptions[_<channel>])
does not silently start leaking to a firm manager who has no business seeing
internal bookkeeping keys.

A READ (GET), SO NO AUDIT ROW -- the audit log records mutations, and every
other list route in this service (list_firms, list_users) already omits one
for the same reason.

ASCII only.
"""
from __future__ import annotations

import asyncio
import time
from typing import Annotated, Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from admin_backend.services import audit_log, identity_labels
from admin_backend.services.admin_auth import (
    ACTOR_KIND_FIRM_EMPLOYEE,
    CompositeActor,
    require_app_admin_or_owning_manager,
    require_app_admin_or_owning_manager_or_employee,
)
from backend.services import links_store

_log = structlog.get_logger().bind(module="admin_link_routes")

router = APIRouter()

# The two channels that actually exist (docs/doctrine/promotion-tiers.md).
# Restated here rather than imported from firm_routes.py / sweep_routes.py,
# for the same reason both of those give their own copy: no shared constant
# exists today, and a channel typo is caught by the same literal pair either
# way.
KNOWN_CHANNELS = ("demo", "staging")

# The audit `action` string for revoke -- the ONE mutating route this module
# carries. A constant, not an inline literal, matching every other admin
# routes module's own audit-action constants (test_admin_audit_coverage.py
# and a future console filter both key on the STRING, not on a reference to
# this name).
ACTION_LINK_REVOKE = "link.revoke"

# The statuses link_redemptions.py's stored records can carry -- imported as
# a local literal set rather than a second import surface, since the only
# two keys this route reads off that document are opened_at/completed_at
# (plus the spend/turns pair link_spend.py defines), none of which needs a
# status vocabulary of their own.

# THE RESPONSE ALLOWLIST (exit criterion 1). Every key the bead names, and
# NO others -- see the module docstring's "why by-hand, not **doc" note.
# employee_label (bd polyglot-pdf-cpsi0) joins this allowlist the same
# by-hand way every other key did: _public_link_view sets it explicitly,
# never via **doc, so a future key added to links[_<channel>] cannot leak
# here by omission.
_ALLOWLISTED_KEYS = (
    "jti", "kit_id", "employee_id", "employee_label", "status", "minted_at",
    "open_deadline", "opened_at", "completed_at", "spend_usd", "turns",
    "cap_usd", "credit_cost",
)


def _validate_channel(channel: Optional[str]) -> str:
    """A known channel, or the 422 the bead requires for "missing or unknown
    channel" -- required, unlike every other admin route's optional
    ?channel= (sweep_routes.py's sweep-everything default has no analogue
    here: a link record lives in exactly ONE channel's collection, so there
    is no "every channel" reading that would make sense for a single jti's
    revoke or a single firm's link list).
    """
    if not channel or channel not in KNOWN_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail="channel is required and must be one of {}".format(
                ", ".join(KNOWN_CHANNELS)),
        )
    return channel


def _require_owning_firm(actor: CompositeActor, firm_id: str) -> None:
    """Refuse a manager OR EMPLOYEE acting on a firm that is not their own,
    with the SAME 404 an unknown firm_id would produce (see module
    docstring's "why not resolve_target_firm" section). An app admin is
    never refused here -- they may act on any firm, exactly like every
    other require_app_admin_or_owning_manager(_or_employee) route in this
    service. actor.firm_id is populated identically for a manager and an
    employee actor (bd polyglot-pdf-scaig), so this one check already
    covers both kinds -- no employee-specific branch is needed here.
    """
    if actor.is_app_admin:
        return
    if actor.firm_id != firm_id:
        raise HTTPException(status_code=404, detail="No such firm")


def _links_collection(db, channel: str):
    return db.collection(links_store._collection_name(channel))


def _redemptions_collection(db, channel: str):
    from backend.services import link_redemptions

    return db.collection(link_redemptions._collection_name(channel))


def _public_link_view(
    link_doc: dict, redemption_doc: Optional[dict], employee_label: Optional[str],
) -> dict:
    """The allowlisted join of a links[_<channel>] mint record with its
    (possibly nonexistent, if never opened) link_redemptions[_<channel>]
    record -- built by hand from named fields, one key at a time, never by
    spreading either stored dict (see module docstring).

    employee_label (bd polyglot-pdf-cpsi0) is resolved by the CALLER (
    _do_list_links, via ONE batched identity_labels.labels_for_uids call
    plus identity_labels.label_for_actor's precedence rule) and passed in
    rather than looked up per-row here -- a per-row Auth call would turn an
    N-row page into N Auth calls, exactly what labels_for_uids's own
    docstring says not to do.
    """
    redemption_doc = redemption_doc or {}
    row = {key: None for key in _ALLOWLISTED_KEYS}
    row.update({
        "jti": link_doc.get("jti"),
        "kit_id": link_doc.get("kit_id"),
        "employee_id": link_doc.get("employee_id"),
        "employee_label": employee_label,
        "status": link_doc.get("status"),
        "minted_at": link_doc.get("minted_at"),
        "open_deadline": link_doc.get("open_deadline"),
        "cap_usd": link_doc.get("cap_usd"),
        "credit_cost": link_doc.get("credit_cost"),
        "opened_at": redemption_doc.get("opened_at"),
        "completed_at": redemption_doc.get("completed_at"),
        "spend_usd": redemption_doc.get("spend_usd"),
        "turns": redemption_doc.get("turns"),
    })
    # Exactly the allowlisted keys, whatever extras either stored doc
    # carries -- the property exit criterion 1 pins, not merely today's
    # behavior of the dict literal above.
    return {key: row[key] for key in _ALLOWLISTED_KEYS}


def _db():
    """The Firestore client, or a 503 -- same lazy-import shape as every
    other admin route module (module import must not require an
    initialized firebase_admin app)."""
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="link store unavailable")
    return db


def _do_list_links(
    *, firm_id: str, channel: str, status: Optional[str],
    employee_id: Optional[str],
) -> list[dict]:
    """Synchronous body of list_firm_links(), run under asyncio.to_thread.

    Queries links[_<channel>] filtered to this firm (and, optionally,
    status / employee_id), then reads EACH matching link's redemption
    record individually -- link_redemptions is keyed by jti, not by firm,
    so there is no single query that could join the two collections
    server-side. A firm's link list is bounded by how many links a firm
    can mint (bd polyglot-pdf-ik7e's per-firm metering already caps this),
    so an N+1 read pattern here is the same shape reconcile_expired_for_
    firm and the sweep route already accept for per-link Firestore work.
    """
    db = _db()
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = _links_collection(db, channel).where(
            filter=FieldFilter("firm_id", "==", firm_id))
        if status is not None:
            query = query.where(filter=FieldFilter("status", "==", status))
        if employee_id is not None:
            query = query.where(
                filter=FieldFilter("employee_id", "==", employee_id))
    except ImportError:
        query = _links_collection(db, channel).where(
            "firm_id", "==", firm_id)
        if status is not None:
            query = query.where("status", "==", status)
        if employee_id is not None:
            query = query.where("employee_id", "==", employee_id)

    try:
        link_snaps = list(query.stream())
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_link_list_failed", firm_id=firm_id,
                   channel=channel, error=str(exc))
        raise HTTPException(status_code=503,
                            detail="link store unavailable") from exc

    link_docs = [snap.to_dict() or {} for snap in link_snaps]

    # ONE batched Auth lookup for every DISTINCT employee_id this page's
    # rows need a fallback label for (bd polyglot-pdf-cpsi0) -- mirrors
    # firm_routes.py's identical shape over the ledger's `actor` field. A
    # row minted after this bead already carries employee_email and needs
    # no lookup at all (label_for_actor prefers it); only a legacy row
    # (employee_email is None) costs anything here, and a firm's own staff
    # repeats across many links, so this is one Auth call per page, not one
    # per row.
    uids_needing_lookup = {
        doc.get("employee_id") for doc in link_docs
        if isinstance(doc.get("employee_id"), str) and doc.get("employee_id")
        and not doc.get("employee_email")
    }
    labels = identity_labels.labels_for_uids(uids_needing_lookup)

    redemptions = _redemptions_collection(db, channel)
    rows = []
    for snap, link_doc in zip(link_snaps, link_docs):
        jti = snap.id
        try:
            r_snap = redemptions.document(jti).get()
            redemption_doc = r_snap.to_dict() if r_snap.exists else None
        except Exception as exc:  # noqa: BLE001 -- one bad read must not
            # sink the whole list; the link's mint fields still show, just
            # without spend/opened/completed detail for this one row.
            _log.error("admin_link_redemption_read_failed", jti=jti,
                       channel=channel, error=str(exc))
            redemption_doc = None
        employee_label = identity_labels.label_for_actor(
            link_doc.get("employee_id"), link_doc.get("employee_email"),
            labels)
        rows.append(_public_link_view(link_doc, redemption_doc, employee_label))

    rows.sort(key=lambda r: (r["minted_at"] is None, r["minted_at"]),
              reverse=True)
    return rows


@router.get("/admin/firms/{firm_id}/links")
async def list_firm_links(
    firm_id: str,
    actor: Annotated[CompositeActor,
                     Depends(require_app_admin_or_owning_manager_or_employee)],
    channel: Annotated[Optional[str], Query()] = None,
    status: Annotated[Optional[str], Query()] = None,
    employee_id: Annotated[Optional[str], Query()] = None,
) -> dict:
    """This firm's links, joined with their redemption detail.

    channel is REQUIRED (422 when missing or unknown -- see
    _validate_channel). status/employee_id are optional equality filters,
    matching the bead's own query-param names exactly -- EXCEPT for an
    employee actor, for whom employee_id is FORCED to their own uid
    regardless of what (if anything) the query names (bd polyglot-pdf-scaig,
    plan's own words: "ids come from the token, not the query"). A query
    employee_id from an employee actor is silently overridden rather than
    refused: unlike resolve_target_firm's firm-naming rule (where naming
    ANY firm at all is the thing being refused, because a console bug
    sending the wrong firm must be visible), an employee-scoped console
    build may reasonably always send its own uid as a filter out of habit,
    and there is exactly one value that request could ever legitimately
    mean -- their own -- so silently substituting it is not hiding a
    disagreement, it is applying the only value that was ever going to be
    correct.

    A manager or employee reaches only their OWN firm (404 for any other
    firm_id, the same 404 an unknown firm_id would get -- see
    _require_owning_firm); an app admin may list any firm's links, matching
    every other require_app_admin_or_owning_manager(_or_employee) route's
    admin branch.
    """
    channel = _validate_channel(channel)
    _require_owning_firm(actor, firm_id)
    if actor.kind == ACTOR_KIND_FIRM_EMPLOYEE:
        employee_id = actor.employee_id
    rows = await asyncio.to_thread(
        _do_list_links, firm_id=firm_id, channel=channel, status=status,
        employee_id=employee_id,
    )
    return {"firm_id": firm_id, "channel": channel, "links": rows}


def _do_revoke_link(
    *, jti: str, channel: str, actor: CompositeActor, request_id: str,
) -> dict:
    """Synchronous body of revoke_link(), run under asyncio.to_thread.

    Mirrors firm_routes.py's _apply_firm_patch shape: read (inside the
    transaction, so a retry on contention re-reads rather than trusting a
    stale `before`), refuse if not revocable, write, audit -- all three in
    ONE @firestore.transactional body, so a forced audit failure leaves the
    link's status unchanged (exit criterion 3).

    Raises HTTPException(404) for a jti that does not exist under `channel`
    OR belongs to a firm the caller (a manager) does not own -- the SAME
    404 either way, per _require_owning_firm's own reasoning: the status
    code must not tell a manager whether a jti they cannot act on exists at
    all. Raises HTTPException(409) for a jti that exists but is not
    currently STATUS_MINTED (see module docstring: only a minted link may
    be revoked).
    """
    from firebase_admin import firestore

    db = _db()
    link_ref = _links_collection(db, channel).document(jti)

    # The firm-ownership check needs the record's firm_id, which means a
    # READ before the transaction can decide whether to proceed at all --
    # mirrors firm_routes.py's _get_firm_or_404 pre-check (called once,
    # outside the transaction, purely to shape the response code; the
    # transaction below re-reads for the value it actually writes from).
    pre_snap = link_ref.get()
    if not pre_snap.exists:
        raise HTTPException(status_code=404, detail="No such link")
    pre_doc = pre_snap.to_dict() or {}
    _require_owning_firm(actor, pre_doc.get("firm_id"))

    result: dict[str, Any] = {}

    @firestore.transactional
    def _txn(tx):
        snap = link_ref.get(transaction=tx)
        if not snap.exists:
            # Unreachable in practice (the pre-check above already 404'd on
            # a missing doc) but a real check rather than an assumption --
            # a doc deleted between that read and this transaction must not
            # silently write a phantom revoke back into existence.
            raise HTTPException(status_code=404, detail="No such link")
        doc = snap.to_dict() or {}
        before_status = doc.get("status")
        if before_status != links_store.STATUS_MINTED:
            raise HTTPException(
                status_code=409,
                detail="link is {} and cannot be revoked".format(
                    before_status),
            )
        now = int(time.time())
        tx.set(link_ref, {
            "status": links_store.STATUS_REVOKED,
            "revoked_by": actor.uid,
            "revoked_at": now,
        }, merge=True)
        audit_log.record_in_transaction(
            tx,
            db,
            actor_uid=actor.uid,
            actor_email=actor.email,
            action=ACTION_LINK_REVOKE,
            target="{}/{}".format(
                links_store._collection_name(channel), jti),
            before={"status": before_status},
            after={"status": links_store.STATUS_REVOKED,
                   "revoked_by": actor.uid, "revoked_at": now},
            channel=channel,
            request_id=request_id,
        )
        result["before_status"] = before_status
        result["revoked_at"] = now

    try:
        _txn(db.transaction())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_link_revoke_failed", jti=jti, channel=channel,
                   error=str(exc))
        raise HTTPException(status_code=500,
                            detail="link revoke failed") from exc

    return result


@router.post("/admin/links/{jti}/revoke")
async def revoke_link(
    jti: str,
    actor: Annotated[CompositeActor,
                     Depends(require_app_admin_or_owning_manager)],
    channel: Annotated[Optional[str], Query()] = None,
) -> dict:
    """Revoke a minted link. Sets status=revoked with revoked_by/revoked_at
    in one Firestore transaction with an in-transaction audit row (exit
    criterion 3); a revoked link is refused at open once bead A3's mint-
    record open gate lands (backend/routes/link_routes.py).

    A manager may revoke only a jti belonging to their OWN firm (404
    otherwise, indistinguishable from a jti that does not exist); an app
    admin may revoke any firm's link.
    """
    channel = _validate_channel(channel)
    request_id = audit_log.new_request_id()
    result = await asyncio.to_thread(
        _do_revoke_link, jti=jti, channel=channel, actor=actor,
        request_id=request_id,
    )
    _log.info("admin_link_revoked", jti=jti, channel=channel,
              before_status=result["before_status"], actor_uid=actor.uid,
              request_id=request_id)
    return {
        "jti": jti, "channel": channel,
        "status": links_store.STATUS_REVOKED,
        "before_status": result["before_status"],
        "revoked_at": result["revoked_at"],
        "request_id": request_id,
    }
