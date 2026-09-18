"""Firm CRUD on the admin service (bd polyglot-pdf-zopqq, Epic 2 Track B
bead B1).

SEVEN ROUTES:

    POST  /admin/firms                       create (kind REQUIRED)
    GET   /admin/firms                       list (kind, balance, status)
    GET   /admin/firms/{firm_id}             profile + balance + ledger page
    PATCH /admin/firms/{firm_id}/status      active | suspended
    PATCH /admin/firms/{firm_id}/allowed_kits
    PATCH /admin/firms/{firm_id}/kind        reason required
    PATCH /admin/firms/{firm_id}/plan        tier + monthly_credits + rollover
                                              (bd polyglot-pdf-0euzk)

ALL SEVEN behind require_app_admin -- unlike the user routes (bd
polyglot-pdf-dmjl5), there is no firm-manager counterpart here in this
bead: a firm manager never creates or reclassifies firms, and the plan lists
this surface under the app-admin-only routes. (Link listing, which a
manager DOES reach, is Track B bead B4's require_app_admin_or_owning_manager
route, not this one.)

WRITES MATCH backend/services/firms.py::upsert_firm's FIELD SHAPE BUT DO NOT
CALL IT. upsert_firm() is still the operator-bootstrap writer, and
create_firm() below (this module) is the SECOND deliberate site that
0-initializes balance_credits/balance_updated_at on first create -- both
carve-outs are named in the scar #8 guard's allowlist
(test_credit_ledger_is_the_only_module_that_writes_balance_credits, which
walks both backend/ and admin_backend/). upsert_firm() does its own
non-transactional get()-then-set() -- it is not @firestore.transactional
and takes no `transaction` argument -- while every write in THIS module must
share one Firestore transaction with its audit_log.record_in_transaction
call (exit criterion 1). Firestore requires all reads in a transaction
before any write; a transactional caller invoking upsert_firm would trigger
upsert_firm's OWN untransacted get() as a second, transaction-illegal read.
So create_firm() and _apply_firm_patch() each do their own read-patch-write
against firm_ref directly, inside their own @firestore.transactional body,
deliberately mirroring upsert_firm's payload shape (name, contact_email,
allowed_kits, status, kind, updated_at; balance fields only on first
create) by hand rather than delegating to it -- two writers of the SAME
shape, not sharing one function, because the transactional and
non-transactional callers cannot compose. Nothing today couples the two
copies other than this docstring and each function's own; a change to one
payload shape must be mirrored in the other by hand.

EVERY MUTATION IS A FIRESTORE WRITE, so every one uses
audit_log.record_in_transaction INSIDE a @firestore.transactional body,
mirroring config_routes.py's _apply_config_write shape exactly: read
(before), write, audit -- all three in the one transaction, so a forced
audit failure leaves the firm doc unchanged (exit criterion 1's audit half,
shared with credit_routes.py).

PATCH .../plan (bd polyglot-pdf-0euzk, the firm-plan + monthly top-up
follow-up). `firms/{firm_id}.plan` is a NEW sub-object -- {tier,
monthly_credits, rollover} -- validated by backend/services/plans.py's
validate_plan() (a closed PLAN_TIERS list; monthly_credits a positive int;
rollover a bool) BEFORE the transaction opens, exactly like the kind and
create routes validate their own enums up front. Same in-transaction audit
form as every other patch route here. GET .../{firm_id} and POST /admin/firms
(create) both now include `plan` in their response/write: create applies
plans.DEFAULT_PLAN when the request carries none (mirroring
scripts/backfill_firm_kind.py's own "only when plan is absent" rule for an
EXISTING firm), and _public_firm_view falls back to DEFAULT_PLAN for any
doc with no stored `plan` key (the same pre-backfill-window fallback
pattern _public_firm_view already uses for `kind`).

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

EACH LEDGER ROW GAINS actor_label (bd polyglot-pdf-cpsi0). credit_ledger.py
now optionally stamps `actor_email` on a NEW entry, but a row written before
that landed carries only the uid in `actor`. Rather than leave old rows
showing a raw uid forever, _do_get_firm resolves every DISTINCT actor uid on
the returned page through ONE batched call, identity_labels.labels_for_uids
-- a firm's ledger page repeats the same few staff uids across many rows, so
this is one Auth lookup per page view, not one per row. identity_labels.
label_for_actor is the ONE place precedence is decided: a row's own stored
actor_email wins when present (no lookup needed), the batch-resolved map is
the fallback for a legacy row, and the raw uid is the last resort (an
unresolvable uid, or a None actor). The uid itself is UNCHANGED on the row
(`actor` still carries it) -- actor_label is an ADDITIONAL field, never a
replacement, so a console that has not been updated yet still works exactly
as before.

LIST IS DELIBERATELY UNFILTERED. The bead's wording ("list with kind,
balance, status") is a describe-the-columns request, not a describe-the-
filters one -- unlike GET /admin/audit (bd polyglot-pdf-li9x0), which
documents named filters up front and ships a composite index per filter
(test_firestore_indexes.py). Adding an equality filter here later needs the
same index discipline; this bead ships none, so none is owed.

SYNC HELPER, ASYNC ROUTE: every route's Firestore/credit_ledger work is a
private `_do_*` function, and every handler runs its `_do_*` under
asyncio.to_thread -- matching credit_routes.py's own explicit design rule in
the SAME diff (its docstring: "both handlers run it under asyncio.to_thread,
matching every other admin-service call into a synchronous Firestore/Auth
helper") and user_routes.py's asyncio.to_thread(user_admin....) precedent.
Cheap, DB-free request validation (kind/status/reason membership checks)
stays inline in the async handler, before the to_thread call, so a bad
request 422s without ever touching a thread.

ASCII only.
"""
from __future__ import annotations

import asyncio
import re
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from admin_backend.services import audit_log, identity_labels
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import credit_ledger, firms, plans

_log = structlog.get_logger(module="admin_firm_routes")

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
ACTION_FIRM_PLAN = "firm.plan"

_FIRM_STATUSES = (firms.FIRM_STATUS_ACTIVE, firms.FIRM_STATUS_SUSPENDED)
_FIRM_KINDS = (firms.FIRM_KIND_MOCK, firms.FIRM_KIND_LIVE)

_FIRMS_COLLECTION = "firms"

# Same slug rule as scripts/bootstrap_firm.py's FIRM_ID_RE and
# admin_backend/routes/user_routes.py's own copy of it, restated here for
# the same reason both of those give: importing backend.* / running a
# cross-module constant at collection time is more fragile than a literal
# regex three places agree on, and test_credit_ledger.py's set-derived scar
# #8 shape (walk every firm-naming site, assert the SET, not one instance)
# is exactly the guard that would have caught this route skipping the rule
# (cross-surface review finding 1 on bd polyglot-pdf-zopqq: this route
# 201'd "Acme", "ACME Corp", "acme/../x", "-lead", a 200-char id and
# "acme\n" -- all of which the other two sites already refuse, and a firm
# created under one of the case-colliding or embedded-newline spellings is
# then unreachable from POST /admin/users, which enforces this same regex).
# Lowercase-only on purpose: Firestore doc IDs are case-sensitive, so
# Acme/acme would be two different firms -- an operator error this rule
# makes impossible.
FIRM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")

# Sentinel for "the stored firm doc never had this key" -- distinct from any
# real stored value (None included), so _apply_firm_patch can drop a field
# from its re-write rather than inventing a default for it (cross-surface
# review finding 1/2 on bd polyglot-pdf-zopqq).
_ABSENT = object()


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
    # Bounded like the credit-adjust reason (ONE number, credit_ledger's;
    # bd polyglot-pdf-e8wzz, the PF-9 class): operator free text is stored in
    # the audit row, bounded, and never in a log line.
    reason: str = Field(max_length=credit_ledger.REASON_MAX_LENGTH)


class SetPlanRequest(BaseModel):
    """The three fields backend/services/plans.py's validate_plan() checks.
    No confirm-twice here (unlike kind): a plan change has no "mints for
    free" failure mode -- it only changes a monthly top-up amount the
    scheduled route applies once a month, so a single console save is
    enough (bd polyglot-pdf-0euzk exit criterion 3: "one write per save")."""

    tier: str
    monthly_credits: int
    rollover: bool


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
    list and detail routes cannot silently diverge on shape.

    `balance_credits_malformed` (nit 1 from the polyglot-pdf-zopqq fresh-eyes
    review, bd polyglot-pdf-0w13i) is a distinguishing signal for the
    fail-closed `balance_credits` fallback just below: a stored value that
    is present but not a plain int (a corrupted doc, a stray float/string/
    bool written by something other than credit_ledger.append_entry) would
    otherwise report the SAME `0` a real "$0 firm" reports, with nothing in
    the response telling an operator the two apart. The key is present and
    False on every normal firm (including one truly at a zero balance, or
    one where the key was never written yet), and True only when a stored
    value exists and fails the int check -- so a console can render a
    "balance unreadable" badge instead of a trustworthy-looking $0 without
    guessing from the number alone. Read-only diagnostic; it changes no
    write path, and credit_ledger.append_entry remains the only writer of
    balance_credits (scar #8's guard,
    test_credit_ledger_is_the_only_module_that_writes_balance_credits).

    KNOWN BLIND SPOT: dict.get() cannot distinguish "the key was never
    written" from "the key is explicitly stored as None" -- both read back
    as None -- so a doc that somehow stored balance_credits=None reads as
    the ordinary never-written case, not as malformed. Every other wrong
    type (str, float, bool, list, ...) is still caught."""
    raw_balance = doc.get("balance_credits")
    balance_is_valid_int = (
        isinstance(raw_balance, int) and not isinstance(raw_balance, bool)
    )
    return {
        "firm_id": firm_id,
        "name": doc.get("name"),
        "contact_email": doc.get("contact_email"),
        "kind": doc.get("kind") if doc.get("kind") in _FIRM_KINDS else
        firms.FIRM_KIND_LIVE,
        "status": doc.get("status"),
        "allowed_kits": doc.get("allowed_kits")
        if isinstance(doc.get("allowed_kits"), list) else [],
        "balance_credits": raw_balance if balance_is_valid_int else 0,
        # True only for a PRESENT-but-malformed stored value -- "the key was
        # never written" (raw_balance is None) is the ordinary pre-first-
        # grant state, not corruption, so it reads False like any other
        # valid-zero firm.
        "balance_credits_malformed": (
            raw_balance is not None and not balance_is_valid_int
        ),
        # A doc with no stored `plan` (the pre-backfill window, same as
        # `kind` above) reads as the maintainer's own default rather than
        # None -- a console page showing "no plan" for an unclassified firm
        # would be misleading, since backend/services/plans.py's
        # DEFAULT_PLAN is exactly what scripts/backfill_firm_kind.py and the
        # monthly top-up route (admin_backend/routes/credit_routes.py) both
        # already treat that firm as having.
        "plan": doc.get("plan")
        if isinstance(doc.get("plan"), dict) else dict(plans.DEFAULT_PLAN),
    }


def _validated_firm_id(firm_id: str) -> str:
    """Reject a firm_id that is not a valid slug, on EVERY route this
    module has -- create (body.firm_id) and every path-segment {firm_id}
    alike.

    fullmatch, not match: a $-anchored .match still accepts a trailing
    newline ("acme\\n"), the exact bug class _KIT_ID_RE was fixed for
    (backend/routes/form_kit_routes.py, bd polyglot-pdf-sbfk) and that
    scripts/bootstrap_firm.py and user_routes.py's own copies of this same
    check both already guard against.

    Applying this to the path-segment call sites too (not just create) is
    deliberate, not incidental: a firm that somehow exists under a
    non-conforming id (case, embedded slash/newline, over-length) must not
    be reachable for status/allowed_kits/kind mutation or its own detail
    page either -- reachability under an invalid id is exactly the
    "unusable once created" failure mode this rule exists to prevent
    (cross-surface review finding 1 on bd polyglot-pdf-zopqq).
    """
    if not firm_id or not FIRM_ID_RE.fullmatch(firm_id):
        raise HTTPException(
            status_code=422,
            detail="firm_id {!r} is not a valid firm slug".format(firm_id),
        )
    return firm_id


def _apply_firm_patch(
    *, db, firm_id: str, patch: dict, actor: AdminActor,
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

    MERGE IS BUILT FROM ONLY THE KEYS THE STORED DOC ALREADY HAS, PLUS
    `patch` (cross-surface review finding 1/2 on this bead, polyglot-pdf-
    zopqq): a status-only or allowed_kits-only PATCH must not invent a
    `kind`/`status`/`allowed_kits` value on a doc that never had one.
    scripts/backfill_firm_kind.py gates its `--mock` allowlist AND its
    `--seed-credits` grant on `"kind" in firm` (had_kind) -- a stray write
    that materializes `kind` here during the still-open pre-backfill
    window (A6 exit criterion 2 has no journal-recorded staging run yet)
    would make that firm skip both, silently converting an unclassified
    firm into a permanently-`live`, unseeded one. tx.set(..., merge=True)
    already leaves every OTHER stored field untouched; the fix is for
    `merged` to mirror that same merge-only-what's-named discipline for
    the fields upsert_firm's shape lists, rather than coercing them to a
    default the caller never asked for.
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
        # One dict literal carrying the SAME key set as upsert_firm's
        # `payload` (test_apply_firm_patch_merged_dict_matches_upsert_
        # firm_payload_keys pins the two by AST-walking each function's
        # first dict literal, so this stays a literal rather than a
        # build-up of conditional assignments). Each value is _ABSENT when
        # `current` never had that key, so the drop-absent-keys step right
        # after this literal can tell "stored empty/false-y" apart from
        # "never stored" without coercing the latter to a default.
        merged = {
            "name": current.get("name", _ABSENT),
            "contact_email": current.get("contact_email", _ABSENT),
            "allowed_kits": current["allowed_kits"]
            if isinstance(current.get("allowed_kits"), list) else _ABSENT,
            "status": current.get("status", _ABSENT),
            "kind": (current.get("kind") if current.get("kind") in
                     _FIRM_KINDS else firms.FIRM_KIND_LIVE)
            if "kind" in current else _ABSENT,
        }
        merged = {k: v for k, v in merged.items() if v is not _ABSENT}
        # `plan` is deliberately NOT in the literal above (and therefore not
        # part of the merged/upsert_firm key-set parity test -- see that
        # test's own docstring): unlike name/contact_email/allowed_kits/
        # status/kind, backend/services/firms.py::upsert_firm (the CLI
        # bootstrap path) never writes it. It needs no explicit preservation
        # code either: tx.set(..., merge=True) below already leaves every
        # field not named in a write's payload untouched (Firestore's own
        # merge semantics, mirrored exactly by the fake in
        # test_firm_routes.py's _FakeDb.apply_set) -- so a status/
        # allowed_kits/kind-only PATCH already carries a stored plan forward
        # with no code here needing to say so, and a plan-only PATCH
        # (set_firm_plan below) likewise never invents kind/status/
        # allowed_kits. Verified by test_set_status_on_a_planned_doc_still_
        # preserves_plan and test_set_plan_on_a_kindless_doc_does_not_
        # invent_kind_status_or_allowed_kits.
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
                   action=action, error_type=type(exc).__name__)
        raise HTTPException(status_code=500,
                            detail="firm write failed") from exc


def _do_create_firm(*, firm_id: str, body: CreateFirmRequest,
                    actor: AdminActor, request_id: str) -> dict:
    """Synchronous body of create_firm(), run under asyncio.to_thread.

    Writes the same field shape as backend/services/firms.py::upsert_firm
    (see the module docstring for why this does not call upsert_firm
    itself).

    AUDITED IN-TRANSACTION, not through upsert_firm (which has no
    transaction of its own and is also the operator-bootstrap path that
    must keep working with no admin service running at all). This does its
    own transactional create so the audit row shares the same commit,
    mirroring _apply_firm_patch's shape for the update routes.
    """
    db = _db()
    from firebase_admin import firestore

    firm_ref = _firm_ref(db, firm_id)
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
            # A brand-new firm gets the maintainer's default plan
            # (backend/services/plans.py::DEFAULT_PLAN) immediately, rather
            # than needing a separate scripts/backfill_firm_kind.py run just
            # to become eligible for the monthly top-up -- mirrors
            # balance_credits' own "0-initialize on first create" rule right
            # above. dict(...) copies the module-level default rather than
            # writing the same mutable object into two firm docs.
            payload["plan"] = dict(plans.DEFAULT_PLAN)
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
                   error_type=type(exc).__name__)
        raise HTTPException(status_code=500,
                            detail="firm write failed") from exc

    return {"created": created_holder["created"]}


@router.post("/admin/firms")
async def create_firm(
    body: CreateFirmRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Create a firm (see _do_create_firm for the write shape and the
    audit-in-transaction rationale).

    `kind` is REQUIRED by the request schema (no default value on the
    field) -- an omitted kind 422s before this handler ever runs, which is
    the write-layer backstop upsert_firm's own required parameter already
    provides, restated at the HTTP boundary so the error is a clean 422
    rather than upsert_firm's ValueError surfacing as a 500.
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

    request_id = audit_log.new_request_id()
    result = await asyncio.to_thread(
        _do_create_firm, firm_id=firm_id, body=body, actor=actor,
        request_id=request_id,
    )

    _log.info("admin_firm_created", firm_id=firm_id, kind=body.kind,
              created=result["created"], actor_uid=actor.uid,
              request_id=request_id)
    return {
        "firm_id": firm_id,
        "created": result["created"],
        "request_id": request_id,
    }


def _do_list_firms() -> list[dict]:
    """Synchronous body of list_firms(), run under asyncio.to_thread."""
    db = _db()
    try:
        docs = list(db.collection(_FIRMS_COLLECTION).stream())
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_firm_list_failed", error_type=type(exc).__name__)
        raise HTTPException(status_code=503,
                            detail="firm store unavailable") from exc
    firms_view = [
        _public_firm_view(snap.id, snap.to_dict() or {}) for snap in docs
    ]
    firms_view.sort(key=lambda f: f["firm_id"])
    return firms_view


@router.get("/admin/firms")
async def list_firms(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Every firm, with kind/balance/status -- unfiltered (see module
    docstring). A read, so no audit row."""
    firms_view = await asyncio.to_thread(_do_list_firms)
    return {"firms": firms_view}


def _do_get_firm(*, firm_id: str, ledger_limit: int) -> dict:
    """Synchronous body of get_firm(), run under asyncio.to_thread.

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
    for channel in KNOWN_CHANNELS:
        try:
            credit_ledger.reconcile_expired_for_firm(firm_id, channel=channel)
        except Exception as exc:  # noqa: BLE001 -- best-effort, see docstring
            _log.error("admin_firm_reconcile_failed", firm_id=firm_id,
                       channel=channel, error_type=type(exc).__name__)

    db = _db()
    doc = _get_firm_or_404(db, firm_id)
    # read_recent_entries reads at most ledger_limit + 1 docs regardless of
    # how many entries this firm has ever accumulated (bd polyglot-pdf-y1t68)
    # -- the firm's ledger has no TTL/pruning, so a full read_entries(limit=
    # None) here would get slower and dearer for exactly the firms an
    # operator looks at most.
    page, truncated = credit_ledger.read_recent_entries(
        db, firm_id, ledger_limit)

    # ONE batched Auth lookup for every DISTINCT uid this page's rows need a
    # fallback label for (bd polyglot-pdf-cpsi0) -- a row with its own
    # stored actor_email needs no lookup at all (label_for_actor prefers it),
    # so only legacy rows (actor_email is None) actually cost anything here,
    # and a page repeating the same few staff uids across many rows still
    # costs exactly one Auth call, not one per row.
    uids_needing_lookup = {
        row.get("actor") for row in page
        if isinstance(row.get("actor"), str) and row.get("actor")
        and not row.get("actor_email")
    }
    labels = identity_labels.labels_for_uids(uids_needing_lookup)
    # Allowlisted to credit_ledger.ENTRY_FIELDS, NOT a bare **row spread:
    # row is read_recent_entries' unfiltered snap.to_dict(), and actor_email
    # is a raw PII-shaped field this route must never put on the wire on its
    # own -- actor_label (resolved above) is the ONLY actor-identifying
    # field this response exposes, mirroring link_routes.py's
    # _public_link_view hand-built allowlist for the identical employee_
    # email/employee_label pair (bd polyglot-pdf-cpsi0 fresh-eyes finding).
    page_with_labels = [
        {**{k: row.get(k) for k in credit_ledger.ENTRY_FIELDS
            if k != "actor_email"},
         "actor_label": identity_labels.label_for_actor(
             row.get("actor"), row.get("actor_email"), labels)}
        for row in page
    ]
    return {
        **_public_firm_view(firm_id, doc),
        "ledger": page_with_labels,
        "ledger_truncated": truncated,
    }


@router.get("/admin/firms/{firm_id}")
async def get_firm(
    firm_id: str,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    ledger_limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    """One firm's profile, balance, and a page of ledger rows (see
    _do_get_firm for the reconcile-before-read rationale)."""
    firm_id = _validated_firm_id(firm_id)
    return await asyncio.to_thread(
        _do_get_firm, firm_id=firm_id, ledger_limit=ledger_limit)


def _do_set_firm_status(*, firm_id: str, body: SetStatusRequest,
                        actor: AdminActor, request_id: str) -> dict:
    """Synchronous body of set_firm_status(), run under asyncio.to_thread."""
    db = _db()
    doc = _get_firm_or_404(db, firm_id)
    before_status = doc.get("status")
    _apply_firm_patch(
        db=db, firm_id=firm_id, patch={"status": body.status},
        actor=actor, action=ACTION_FIRM_STATUS,
        before={"status": before_status}, after={"status": body.status},
        request_id=request_id,
    )
    return {"before_status": before_status}


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
    request_id = audit_log.new_request_id()
    result = await asyncio.to_thread(
        _do_set_firm_status, firm_id=firm_id, body=body, actor=actor,
        request_id=request_id,
    )
    _log.info("admin_firm_status_set", firm_id=firm_id, status=body.status,
              actor_uid=actor.uid, request_id=request_id)
    return {
        "firm_id": firm_id, "status": body.status,
        "before_status": result["before_status"], "request_id": request_id,
    }


def _do_set_firm_allowed_kits(*, firm_id: str, body: SetAllowedKitsRequest,
                              actor: AdminActor, request_id: str) -> None:
    """Synchronous body of set_firm_allowed_kits(), run under
    asyncio.to_thread."""
    db = _db()
    doc = _get_firm_or_404(db, firm_id)
    before_kits = doc.get("allowed_kits") if isinstance(
        doc.get("allowed_kits"), list) else []
    _apply_firm_patch(
        db=db, firm_id=firm_id,
        patch={"allowed_kits": list(body.allowed_kits)},
        actor=actor, action=ACTION_FIRM_ALLOWED_KITS,
        before={"allowed_kits": before_kits},
        after={"allowed_kits": list(body.allowed_kits)},
        request_id=request_id,
    )


@router.patch("/admin/firms/{firm_id}/allowed_kits")
async def set_firm_allowed_kits(
    firm_id: str,
    body: SetAllowedKitsRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    firm_id = _validated_firm_id(firm_id)
    request_id = audit_log.new_request_id()
    await asyncio.to_thread(
        _do_set_firm_allowed_kits, firm_id=firm_id, body=body, actor=actor,
        request_id=request_id,
    )
    _log.info("admin_firm_allowed_kits_set", firm_id=firm_id,
              count=len(body.allowed_kits), actor_uid=actor.uid,
              request_id=request_id)
    return {
        "firm_id": firm_id, "allowed_kits": list(body.allowed_kits),
        "request_id": request_id,
    }


def _do_set_firm_kind(*, firm_id: str, body: SetKindRequest,
                      actor: AdminActor, request_id: str) -> dict:
    """Synchronous body of set_firm_kind(), run under asyncio.to_thread."""
    db = _db()
    doc = _get_firm_or_404(db, firm_id)
    before_kind = doc.get("kind") if doc.get("kind") in _FIRM_KINDS else \
        firms.FIRM_KIND_LIVE
    _apply_firm_patch(
        db=db, firm_id=firm_id, patch={"kind": body.kind},
        actor=actor, action=ACTION_FIRM_KIND,
        before={"kind": before_kind, "reason": None},
        after={"kind": body.kind, "reason": body.reason},
        request_id=request_id,
    )
    return {"before_kind": before_kind}


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
    request_id = audit_log.new_request_id()
    result = await asyncio.to_thread(
        _do_set_firm_kind, firm_id=firm_id, body=body, actor=actor,
        request_id=request_id,
    )
    # reason is DELIBERATELY absent (bd polyglot-pdf-e8wzz, PF-9): the audit
    # row carries it, bounded, under access control; Cloud Logging would be a
    # second copy with no control of its own. request_id looks it up.
    _log.info("admin_firm_kind_set", firm_id=firm_id, kind=body.kind,
              actor_uid=actor.uid, request_id=request_id)
    return {
        "firm_id": firm_id, "kind": body.kind,
        "before_kind": result["before_kind"], "request_id": request_id,
    }


def _do_set_firm_plan(*, firm_id: str, body: SetPlanRequest,
                      actor: AdminActor, request_id: str) -> dict:
    """Synchronous body of set_firm_plan(), run under asyncio.to_thread."""
    db = _db()
    doc = _get_firm_or_404(db, firm_id)
    before_plan = doc.get("plan") if isinstance(doc.get("plan"), dict) \
        else dict(plans.DEFAULT_PLAN)
    new_plan = {
        "tier": body.tier,
        "monthly_credits": body.monthly_credits,
        "rollover": body.rollover,
    }
    _apply_firm_patch(
        db=db, firm_id=firm_id, patch={"plan": new_plan},
        actor=actor, action=ACTION_FIRM_PLAN,
        before={"plan": before_plan}, after={"plan": new_plan},
        request_id=request_id,
    )
    return {"before_plan": before_plan}


@router.patch("/admin/firms/{firm_id}/plan")
async def set_firm_plan(
    firm_id: str,
    body: SetPlanRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Set a firm's plan (tier, monthly_credits, rollover) -- bd
    polyglot-pdf-0euzk. Refuses BEFORE any write via backend/services/
    plans.py::validate_plan (an unknown tier or a non-positive
    monthly_credits is a 422, same shape as SetKindRequest's own kind
    check). No confirm-twice (see SetPlanRequest's docstring) -- one write
    per save."""
    firm_id = _validated_firm_id(firm_id)
    try:
        plans.validate_plan({
            "tier": body.tier, "monthly_credits": body.monthly_credits,
            "rollover": body.rollover,
        })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    request_id = audit_log.new_request_id()
    result = await asyncio.to_thread(
        _do_set_firm_plan, firm_id=firm_id, body=body, actor=actor,
        request_id=request_id,
    )
    _log.info("admin_firm_plan_set", firm_id=firm_id, tier=body.tier,
              monthly_credits=body.monthly_credits, rollover=body.rollover,
              actor_uid=actor.uid, request_id=request_id)
    return {
        "firm_id": firm_id,
        "plan": {
            "tier": body.tier, "monthly_credits": body.monthly_credits,
            "rollover": body.rollover,
        },
        "before_plan": result["before_plan"], "request_id": request_id,
    }
