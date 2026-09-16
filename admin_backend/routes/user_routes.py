"""Staff-account management routes (bd polyglot-pdf-dmjl5).

FOUR ROUTES, TWO ACTORS:

    POST   /admin/users                 create a staff account + reset link
    PATCH  /admin/users/{uid}/disable   disable or re-enable one
    PATCH  /admin/users/{uid}/role      manager <-> employee
    GET    /admin/users?firm_id=        the firm's staff pool

Both an APP ADMIN and a FIRM MANAGER reach all four, under
require_app_admin_or_owning_manager (the plan's third gate, shipping here
with its first consuming routes rather than untested). The difference is
where the firm comes from: an admin NAMES it, a manager's comes from their
verified token and a request that names one is refused 403 -- see
admin_auth.resolve_target_firm, which is the one home for that rule.

WHY A MANAGER IS ALLOWED HERE AT ALL. bd polyglot-pdf-gob8l shipped
firm-admin employee management: a firm manages its own staff without an
operator in the loop. The security property that makes that safe is the same
one the retire route relies on -- the firm identity is never a request
parameter -- so every firm-scoped read and write below goes through the
resolved firm_id, never through anything the caller typed.

THE CLAIMS ALLOWLIST lives in admin_backend/services/user_admin.py: these
routes write ONLY firm_id and firm_role, and app_admin in particular is set
exclusively by scripts/bootstrap_admin_user.py. The routes here never
assemble a claims dict of their own -- every write goes through
user_admin.merge_firm_claims -- which is what makes the allowlist a property
rather than a promise.

AUDITING: the PENDING-THEN-COMMITTED form, and it must be. Firebase Auth
mutations cannot join a Firestore transaction (there is no transaction to
join), so each write route records a pending row BEFORE the Auth call and
marks it committed or failed after. A row stuck at pending is the exact
signal an operator needs: the action MAY have taken effect, so check before
retrying. See admin_backend/services/audit_log.py, and
test_admin_audit_coverage.py, which derives this requirement per route.

OFF THE EVENT LOOP. Every firebase_admin.auth call is synchronous and does
network I/O; calling one directly from an async handler blocks the shared
Cloud Run loop for every concurrent request. They all run through
asyncio.to_thread, the same posture backend/services/auth.py takes for its
Admin-SDK reads.

ASCII only.
"""
from __future__ import annotations

import asyncio
import re
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from admin_backend.services import audit_log, user_admin
from admin_backend.services.admin_auth import (
    CompositeActor,
    require_app_admin_or_owning_manager,
    resolve_target_firm,
)

_log = structlog.get_logger().bind(module="admin_user_routes")

router = APIRouter()

# The audit `action` strings for this surface. Constants rather than inline
# literals: a console filter keys on them, and one typo'd literal would make
# a whole class of mutation invisible to the very query the log exists for.
ACTION_USER_CREATE = "user.create"
ACTION_USER_DISABLE = "user.disable"
ACTION_USER_ROLE = "user.role"

# Same slug rule as scripts/bootstrap_firm.py's FIRM_ID_RE, restated here
# rather than imported for the reason that script gives for its own literals:
# an import of backend.* at module scope pulls in a bare initialize_app().
# Pinned against the script's regex by test_user_routes.py so they cannot
# drift.
FIRM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")

# Deliberately permissive. Firebase itself is the authority on whether an
# address is usable (create_user refuses a malformed one), so this exists
# only to reject the obviously-not-an-email before spending a network call --
# never to be a second, stricter opinion that would refuse a valid address
# Firebase would have accepted.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CreateUserRequest(BaseModel):
    """A new staff account.

    firm_id is OPTIONAL IN THE SCHEMA and required by the GATE, not by
    pydantic: the two actors disagree about it (an admin must name a firm, a
    manager may not), and only resolve_target_firm can see which actor this
    is. A pydantic-required field would 422 every legitimate manager request
    before the gate ever ran.
    """

    email: str
    firm_role: str
    firm_id: Optional[str] = None
    display_name: Optional[str] = Field(default=None, max_length=200)


class DisableUserRequest(BaseModel):
    """Disable (default) or re-enable an account.

    `disabled` is explicit rather than the route being a toggle: a toggle
    applied twice by a retrying console leaves the account in whichever state
    the race decided, and the operator cannot tell which from the response.
    """

    disabled: bool = True
    firm_id: Optional[str] = None


class SetRoleRequest(BaseModel):
    firm_role: str
    firm_id: Optional[str] = None


def _db():
    """The Firestore client the audit log writes through, or a 503.

    Lazy-imported, like every other Firestore caller in this repo, so module
    import does not require an initialized firebase_admin app.
    """
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="audit log unavailable")
    return db


def _validated_firm_id(firm_id: str) -> str:
    """A firm slug that could name a real firm, or 422.

    fullmatch, not match: a $-anchored .match still accepts a trailing
    newline, the exact bug class _KIT_ID_RE was fixed for (bd
    polyglot-pdf-sbfk). Only reachable for an APP ADMIN -- a manager's
    firm_id comes from a verified token and was never caller text.
    """
    if not FIRM_ID_RE.fullmatch(firm_id):
        raise HTTPException(
            status_code=422,
            detail="firm_id {!r} is not a valid firm slug".format(firm_id),
        )
    return firm_id


def _validated_role(firm_role: str) -> str:
    if firm_role not in user_admin.FIRM_ROLES:
        raise HTTPException(
            status_code=422,
            detail="firm_role must be one of {}".format(
                ", ".join(user_admin.FIRM_ROLES)),
        )
    return firm_role


def _resolved_firm(actor: CompositeActor, body_firm_id: Optional[str]) -> str:
    """The firm this request acts on, gate rule then slug validation.

    resolve_target_firm FIRST, always: the manager-named-a-firm refusal must
    fire even when the named firm is malformed, or a manager could learn
    which slugs are well-formed by watching the status code change.
    """
    return _validated_firm_id(resolve_target_firm(actor, body_firm_id))


async def _require_account_in_firm(uid: str, firm_id: str) -> dict:
    """The account's claims, having proved it belongs to `firm_id`.

    THE SCOPING CHECK for the two by-uid routes, and the reason they are not
    a cross-firm hole: a uid is a bearer of nothing, so without this a
    manager could disable any account in the project by pasting its uid.

    404, not 403, for an account outside the caller's firm -- and the SAME
    404 for a uid that does not exist. A 403 here would confirm that a
    guessed uid names a real account, which is the existence leak the kit
    read gates are built to prevent (see form_kit_routes.
    _require_firm_owns_private_kit). An APP ADMIN gets the same treatment for
    a uid outside the firm they named: they can act on any firm, but only on
    the one they said, so a typo does not silently hit somebody else.
    """
    try:
        claims = await asyncio.to_thread(user_admin.get_user_claims, uid)
    except user_admin.UserNotFound:
        raise HTTPException(status_code=404, detail="No such account")
    except user_admin.UserAdminError as exc:
        _log.error("admin_user_lookup_failed", error_type=type(exc).__name__)
        raise HTTPException(status_code=502,
                            detail="user directory unavailable") from exc
    if claims.get("firm_id") != firm_id:
        raise HTTPException(status_code=404, detail="No such account")
    return claims


@router.post("/admin/users")
async def create_user(
    body: CreateUserRequest,
    actor: Annotated[CompositeActor,
                     Depends(require_app_admin_or_owning_manager)],
) -> dict:
    """Create a staff account for a firm and return a password-reset link.

    NO OUTBOUND EMAIL (planner decision, plan "Admin-service routes"): the
    console displays the link and the operator delivers it. The response
    carries no password -- the reset link is the only credential path.
    """
    firm_id = _resolved_firm(actor, body.firm_id)
    firm_role = _validated_role(body.firm_role)
    email = body.email.strip()
    if not _EMAIL_RE.fullmatch(email):
        raise HTTPException(status_code=422,
                            detail="email is not a valid address")

    db = _db()
    request_id = audit_log.new_request_id()
    # PENDING FIRST. The Auth call below cannot join a transaction, so the
    # intent is recorded before it runs; a row left at pending is what tells
    # a retrying operator the account may already exist.
    ref = audit_log.record_pending(
        db,
        actor_uid=actor.uid,
        actor_email=actor.email,
        action=ACTION_USER_CREATE,
        target="firms/{}/users#{}".format(firm_id, email),
        before=None,
        after={"firm_id": firm_id, "firm_role": firm_role},
        request_id=request_id,
    )

    try:
        result = await asyncio.to_thread(
            user_admin.create_staff_user,
            email=email,
            firm_id=firm_id,
            firm_role=firm_role,
            display_name=body.display_name,
        )
    except user_admin.EmailAlreadyExists as exc:
        audit_log.mark_failed(ref, error=str(exc))
        raise HTTPException(
            status_code=409,
            detail=("an account already exists for that address; stamp the "
                    "existing account instead of creating one"),
        ) from exc
    except user_admin.UserAdminError as exc:
        audit_log.mark_failed(ref, error=str(exc))
        _log.error("admin_user_create_failed", firm_id=firm_id,
                   error_type=type(exc).__name__)
        raise HTTPException(status_code=502,
                            detail="could not create the account") from exc

    audit_log.mark_committed(ref, after={
        "uid": result["uid"], "firm_id": firm_id, "firm_role": firm_role})
    # NO email and NO reset_link in the log line: the link is a
    # credential-bearing URL and the address is personal data. The audit row
    # names the target; the log line names the request.
    _log.info("admin_user_created", firm_id=firm_id, firm_role=firm_role,
              uid=result["uid"], actor_uid=actor.uid, request_id=request_id)
    return {**result, "request_id": request_id}


@router.patch("/admin/users/{uid}/disable")
async def set_user_disabled(
    uid: str,
    body: DisableUserRequest,
    actor: Annotated[CompositeActor,
                     Depends(require_app_admin_or_owning_manager)],
) -> dict:
    """Disable (or re-enable) a staff account in this firm."""
    firm_id = _resolved_firm(actor, body.firm_id)
    await _require_account_in_firm(uid, firm_id)

    db = _db()
    request_id = audit_log.new_request_id()
    ref = audit_log.record_pending(
        db,
        actor_uid=actor.uid,
        actor_email=actor.email,
        action=ACTION_USER_DISABLE,
        target="users/{}".format(uid),
        before=None,
        after={"disabled": body.disabled, "firm_id": firm_id},
        request_id=request_id,
    )

    try:
        result = await asyncio.to_thread(
            user_admin.set_user_disabled, uid=uid, disabled=body.disabled)
    except user_admin.UserNotFound as exc:
        audit_log.mark_failed(ref, error=str(exc))
        raise HTTPException(status_code=404, detail="No such account") from exc
    except user_admin.UserAdminError as exc:
        audit_log.mark_failed(ref, error=str(exc))
        _log.error("admin_user_disable_failed", uid=uid, error_type=type(exc).__name__)
        raise HTTPException(status_code=502,
                            detail="could not update the account") from exc

    audit_log.mark_committed(ref, after={
        "disabled": result["disabled"], "was_disabled": result["was_disabled"],
        "firm_id": firm_id})
    _log.info("admin_user_disabled_set", uid=uid, firm_id=firm_id,
              disabled=body.disabled, actor_uid=actor.uid,
              request_id=request_id)
    return {
        "uid": uid,
        "disabled": result["disabled"],
        "firm_id": firm_id,
        "request_id": request_id,
    }


@router.patch("/admin/users/{uid}/role")
async def set_user_role(
    uid: str,
    body: SetRoleRequest,
    actor: Annotated[CompositeActor,
                     Depends(require_app_admin_or_owning_manager)],
) -> dict:
    """Move a staff account between manager and employee.

    The firm_id written is the RESOLVED one, which for a manager is their own
    token's -- so this route cannot move an account from one firm to another
    however the request is shaped: _require_account_in_firm has already
    proved the account is in that same firm.
    """
    firm_id = _resolved_firm(actor, body.firm_id)
    firm_role = _validated_role(body.firm_role)
    before_claims = await _require_account_in_firm(uid, firm_id)

    db = _db()
    request_id = audit_log.new_request_id()
    ref = audit_log.record_pending(
        db,
        actor_uid=actor.uid,
        actor_email=actor.email,
        action=ACTION_USER_ROLE,
        target="users/{}".format(uid),
        before={"firm_role": before_claims.get("firm_role"),
                "firm_id": firm_id},
        after={"firm_role": firm_role, "firm_id": firm_id},
        request_id=request_id,
    )

    try:
        result = await asyncio.to_thread(
            user_admin.set_user_role,
            uid=uid, firm_id=firm_id, firm_role=firm_role)
    except user_admin.UserNotFound as exc:
        audit_log.mark_failed(ref, error=str(exc))
        raise HTTPException(status_code=404, detail="No such account") from exc
    except user_admin.UserAdminError as exc:
        audit_log.mark_failed(ref, error=str(exc))
        _log.error("admin_user_role_failed", uid=uid, error_type=type(exc).__name__)
        raise HTTPException(status_code=502,
                            detail="could not update the account") from exc

    audit_log.mark_committed(ref, after={
        "firm_role": firm_role, "firm_id": firm_id})
    _log.info("admin_user_role_set", uid=uid, firm_id=firm_id,
              firm_role=firm_role, actor_uid=actor.uid, request_id=request_id)
    return {
        "uid": uid,
        "firm_id": firm_id,
        "firm_role": result["firm_role"],
        "before_role": result["before_role"],
        "request_id": request_id,
    }


@router.get("/admin/users")
async def list_users(
    actor: Annotated[CompositeActor,
                     Depends(require_app_admin_or_owning_manager)],
    firm_id: Annotated[Optional[str], Query()] = None,
) -> dict:
    """The firm's staff pool.

    A READ, so no audit row: the log records MUTATIONS, and a row per list
    would bury them.

    firm_id is a QUERY parameter here and a body field on the writes, but the
    rule is the same object either way -- a manager who passes one is refused
    403, an admin who omits it gets 422 -- because both go through
    resolve_target_firm. A read is not a softer case: a manager who could
    name a firm here would get a directory of another firm's staff.
    """
    resolved = _resolved_firm(actor, firm_id)
    try:
        result = await asyncio.to_thread(user_admin.list_firm_users, resolved)
    except user_admin.UserAdminError as exc:
        _log.error("admin_user_list_failed", firm_id=resolved, error_type=type(exc).__name__)
        raise HTTPException(status_code=502,
                            detail="user directory unavailable") from exc
    return {
        "firm_id": resolved,
        "users": result["users"],
        "truncated": result["truncated"],
    }
