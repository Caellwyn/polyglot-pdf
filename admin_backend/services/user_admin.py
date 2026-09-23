"""Staff-account management for the admin service (bd polyglot-pdf-dmjl5).

WHAT IT IS. The thin, testable layer between the user routes and
firebase_admin.auth: create a staff account, stamp its firm claims, disable
it, change its role, and list a firm's staff. The routes own HTTP shape and
auditing; this module owns the CLAIMS RULE and the Auth calls.

THE CLAIMS ALLOWLIST IS THE WHOLE POINT (plan, "Admin-service routes"):
these routes write ONLY firm_id and firm_role. They can never write
app_admin, schema_editor_role or vff_dev -- not "should not", CANNOT: the
merge below builds its output from WRITABLE_CLAIMS and the account's EXISTING
claims, and there is no path by which a request value reaches any other key.
app_admin is set exclusively by scripts/bootstrap_admin_user.py, under an
operator's own credentials; schema_editor_role by
scripts/bootstrap_editor_user.py; vff_dev by scripts/bootstrap_voice_dev.py.
A console that could mint its own admins would make the bootstrap scripts'
whole containment story fiction.

MERGE, NEVER REPLACE. firebase_admin.auth.set_custom_user_claims REPLACES
the entire claims object -- the single highest-risk line in
scripts/bootstrap_firm.py, and pinned there by
test_existing_custom_claims_survive_the_stamp. The same trap is here, so the
same discipline is: read the account's existing claims, spread them, then
overlay the two writable keys. Without it, promoting a firm's dev to manager
would silently strip their vff_dev claim and lock them out of the voice app.

NO OUTBOUND EMAIL in this epic (planner decision). Creating an account
returns a Firebase password-RESET link for the console to display, and the
operator delivers it however they already talk to that firm. Sending mail
would need a provider, a sender identity, deliverability and an unsubscribe
story -- none of which this bead authorizes.

IAM: create_user, set_custom_user_claims, update_user, list_users and
generate_password_reset_link all need roles/firebaseauth.admin, which
admin-backend-sa already holds and
admin_backend/tests/unit/test_admin_sa_iam_envelope.py pins by name (CLAUDE.md
scar #7: a mock cannot tell you the real dependency is forbidden). This bead
adds NO new permission.

ASCII only.
"""
from __future__ import annotations

import secrets
from typing import Optional

import structlog

_log = structlog.get_logger(module="user_admin")

# THE ALLOWLIST. The only two custom claims these routes may write. Kept as a
# frozenset rather than two literals so the rule is one object a test can
# assert against, and so "which claims can the console write" is a set
# difference rather than a grep through route bodies.
WRITABLE_CLAIMS = frozenset({"firm_id", "firm_role"})

# The claims these routes must NEVER write, named explicitly. Redundant with
# WRITABLE_CLAIMS by construction -- if the merge is right, naming these adds
# nothing -- and that redundancy is deliberate: it makes the SPECIFIC
# escalation this allowlist exists to prevent testable by name, so a future
# refactor that widened WRITABLE_CLAIMS would fail on a test that says what
# was lost rather than one that says a set changed.
FORBIDDEN_CLAIMS = frozenset({"app_admin", "schema_editor_role", "vff_dev"})

# The firm roles a staff account can hold (docs/components/auth.md, the
# four-level access model). Spelled here rather than imported because they
# are a WIRE contract on this surface -- the console sends these strings --
# and pinned against backend.services.auth.FIRM_ROLE_MANAGER by
# test_user_routes.py so the two cannot drift.
ROLE_MANAGER = "manager"
ROLE_EMPLOYEE = "employee"
FIRM_ROLES = (ROLE_MANAGER, ROLE_EMPLOYEE)


class UserAdminError(Exception):
    """A Firebase Auth operation failed in a way the route must surface."""


class EmailAlreadyExists(UserAdminError):
    """The address already has an account. Distinct because the console's
    remedy differs: stamp the existing account rather than create one."""


class UserNotFound(UserAdminError):
    """No account with that uid."""


def _fb_auth():
    """The Firebase Auth admin module, imported lazily.

    Lazy for the reason every Firebase caller in this repo is lazy: module
    import must not require an initialized firebase_admin app, so the test
    suite can import routers freely. Also OWNS the init, like
    admin_auth.verify_admin_token, so the admin service standing up alone
    does not depend on whichever module happened to import first.
    """
    import firebase_admin
    from firebase_admin import auth as fb_auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    return fb_auth


def merge_firm_claims(
    existing: Optional[dict],
    *,
    firm_id: str,
    firm_role: str,
) -> dict:
    """The claims object to write: existing claims, with the two writable
    keys overlaid.

    THE ONE PLACE claims are assembled for these routes, and the reason the
    allowlist is a property rather than a promise. Two things are true of
    every dict this returns:

      1. every key present in `existing` is still present, with its original
         value unless it is one of WRITABLE_CLAIMS (merge-not-replace);
      2. the only keys whose values come from THIS CALL are WRITABLE_CLAIMS.

    So an app_admin claim already on the account survives untouched, and no
    request can put one there. Both directions are pinned by
    test_user_routes.py.

    `existing` is not trusted to be well-formed: it is whatever Firebase
    returned, which is None for an account with no custom claims.
    """
    base = dict(existing) if isinstance(existing, dict) else {}
    overlay = {"firm_id": firm_id, "firm_role": firm_role}
    # Built from the allowlist rather than spelled out, so the two can never
    # disagree: a key added to WRITABLE_CLAIMS with no value here raises at
    # the write instead of silently writing nothing.
    writable = {k: overlay[k] for k in sorted(WRITABLE_CLAIMS)}
    return {**base, **writable}


def _new_unguessable_password() -> str:
    """A password nobody knows, including us.

    create_user REQUIRES a password (or the account cannot use the
    email/password provider at all), but this account is meant to be claimed
    through the reset link -- so the value must be strong and must never be
    returned, logged, or stored. token_urlsafe(32) is 256 bits from the
    system CSPRNG; the value dies with the request.
    """
    return secrets.token_urlsafe(32)


def create_staff_user(
    *,
    email: str,
    firm_id: str,
    firm_role: str,
    display_name: Optional[str] = None,
) -> dict:
    """Create a staff account, stamp its firm claims, and return a reset link.

    THE ORDER IS create -> stamp -> link, and a failure at the stamp is
    RAISED rather than swallowed: an account that exists with no firm claims
    is invisible to every firm-scoped query and would look to the operator
    like the create had failed. The route's pending audit row is what makes
    that half-state legible -- it stays pending, which says exactly "this may
    have taken effect".

    Returns {uid, email, firm_id, firm_role, reset_link}. NO password is
    returned: the reset link is the only credential path, so a link that is
    never delivered leaves an account nobody can sign into rather than one
    with a password loose in a console log.
    """
    fb_auth = _fb_auth()

    try:
        user = fb_auth.create_user(
            email=email,
            email_verified=False,
            password=_new_unguessable_password(),
            display_name=display_name,
            disabled=False,
        )
    except Exception as exc:  # noqa: BLE001
        if _is_email_exists(fb_auth, exc):
            raise EmailAlreadyExists(
                "an account already exists for {}".format(email)) from exc
        raise UserAdminError(str(exc)) from exc

    # MERGE even on a fresh account: create_user returns no custom claims, so
    # the merge is a no-op here -- but routing every stamp through ONE helper
    # is what keeps the allowlist a property of all the write routes rather
    # than of most of them.
    claims = merge_firm_claims(
        getattr(user, "custom_claims", None),
        firm_id=firm_id,
        firm_role=firm_role,
    )
    try:
        fb_auth.set_custom_user_claims(user.uid, claims)
    except Exception as exc:  # noqa: BLE001
        raise UserAdminError(
            "account {} created but claims stamp failed: {}".format(
                user.uid, exc)) from exc

    # Best-effort, and deliberately so: the account and its claims are
    # already correct. A link-generation failure is an inconvenience with an
    # obvious remedy (the operator resends from the console, or the user uses
    # "forgot password"), not a reason to report the create as failed and
    # invite a retry that would refuse on the duplicate email.
    reset_link = None
    try:
        reset_link = fb_auth.generate_password_reset_link(email)
    except Exception as exc:  # noqa: BLE001
        _log.warning("user_admin_reset_link_failed", error_type=type(exc).__name__)

    return {
        "uid": user.uid,
        "email": email,
        "firm_id": firm_id,
        "firm_role": firm_role,
        "reset_link": reset_link,
    }


def _is_email_exists(fb_auth, exc: Exception) -> bool:
    """True when this exception is Firebase's duplicate-email refusal.

    Matched on the SDK's own exception class where it exists, with a string
    fallback only for SDK versions that do not export it -- never on the
    message alone, which is the pattern this repo has repeatedly been burned
    by (a reworded message defeats it silently).
    """
    cls = getattr(fb_auth, "EmailAlreadyExistsError", None)
    if cls is not None and isinstance(exc, cls):
        return True
    return "EMAIL_EXISTS" in str(exc)


def set_user_disabled(*, uid: str, disabled: bool) -> dict:
    """Disable or re-enable an account. Claims are NOT touched.

    Disabling rather than deleting is the whole design: a deleted uid takes
    its audit trail's subject with it, and every link that account minted
    would name a uid nothing resolves. A disabled account cannot sign in and
    keeps its history.
    """
    fb_auth = _fb_auth()
    before = _get_user_or_raise(fb_auth, uid)
    try:
        fb_auth.update_user(uid, disabled=disabled)
    except Exception as exc:  # noqa: BLE001
        raise UserAdminError(str(exc)) from exc
    return {
        "uid": uid,
        "email": getattr(before, "email", None),
        "disabled": disabled,
        "was_disabled": bool(getattr(before, "disabled", False)),
    }


def set_user_role(*, uid: str, firm_id: str, firm_role: str) -> dict:
    """Set a staff account's firm_role, keeping every other claim.

    firm_id is passed rather than read off the account because the caller has
    already resolved it (a manager's from their token, an admin's from the
    body) AND checked that it matches this account's current firm -- the
    route owns that check, since only it can turn the mismatch into the right
    refusal.
    """
    fb_auth = _fb_auth()
    user = _get_user_or_raise(fb_auth, uid)
    existing = getattr(user, "custom_claims", None) or {}
    before_role = existing.get("firm_role")
    claims = merge_firm_claims(existing, firm_id=firm_id, firm_role=firm_role)
    try:
        fb_auth.set_custom_user_claims(uid, claims)
    except Exception as exc:  # noqa: BLE001
        raise UserAdminError(str(exc)) from exc
    return {
        "uid": uid,
        "email": getattr(user, "email", None),
        "firm_id": firm_id,
        "firm_role": firm_role,
        "before_role": before_role,
    }


def get_user_claims(uid: str) -> dict:
    """The account's current custom claims, for a route's pre-flight checks.

    Returns {} for an account with none, so callers can .get() freely.
    """
    fb_auth = _fb_auth()
    user = _get_user_or_raise(fb_auth, uid)
    return dict(getattr(user, "custom_claims", None) or {})


def _get_user_or_raise(fb_auth, uid: str):
    try:
        return fb_auth.get_user(uid)
    except Exception as exc:  # noqa: BLE001
        cls = getattr(fb_auth, "UserNotFoundError", None)
        if (cls is not None and isinstance(exc, cls)) or \
                "USER_NOT_FOUND" in str(exc) or "NOT_FOUND" in str(exc):
            raise UserNotFound("no account with uid {}".format(uid)) from exc
        raise UserAdminError(str(exc)) from exc


def list_firm_users(firm_id: str, *, max_results: int = 1000) -> dict:
    """Every staff account whose firm_id claim is `firm_id`.

    CLIENT-SIDE FILTER, on purpose. Firebase Auth has no server-side query
    over custom claims: list_users() pages the whole pool and the filter runs
    here. That is acceptable precisely because the pool is STAFF ONLY --
    firm staff, editors and devs. Clients never get accounts (they arrive on
    signed magic links), so this list does not grow with a firm's caseload
    and there is no members mirror to keep in sync (plan, "Admin-service
    routes"). If the pool ever includes clients, this becomes a Firestore
    mirror; it does not, so it is not one yet.

    max_results bounds the WALK (accounts examined, not accounts returned) so
    a pathological pool cannot hang a console request. Returns
    {users, truncated} rather than a bare list, so a truncated walk says so
    instead of looking like a firm with fewer staff than it has.
    """
    fb_auth = _fb_auth()
    rows = []
    truncated = False
    seen = 0
    try:
        page = fb_auth.list_users()
        while page is not None:
            for user in (getattr(page, "users", None) or []):
                seen += 1
                if seen > max_results:
                    truncated = True
                    break
                claims = dict(getattr(user, "custom_claims", None) or {})
                if claims.get("firm_id") != firm_id:
                    continue
                rows.append(_user_row(user, claims))
            if truncated:
                break
            page = page.get_next_page()
    except Exception as exc:  # noqa: BLE001
        raise UserAdminError(str(exc)) from exc
    rows.sort(key=lambda r: (r.get("email") or "", r["uid"]))
    return {"users": rows, "truncated": truncated}


def _user_row(user, claims: dict) -> dict:
    """ONE staff account, as an EXPLICIT key allowlist.

    Never `{**claims}` or a dump of the UserRecord: a future internal claim
    (or a Firebase field like phone_number or provider metadata) would then
    reach the console the day it appeared, with nobody having decided it
    should. The response shape is a decision, so it is written out.

    firm_role, schema_editor_role and vff_dev ride along READ-ONLY -- an
    operator needs to see that an account is also a dev, and showing it does
    not make it writable (that is WRITABLE_CLAIMS' job, and these routes
    write through merge_firm_claims only).
    """
    return {
        "uid": user.uid,
        "email": getattr(user, "email", None),
        "display_name": getattr(user, "display_name", None),
        "disabled": bool(getattr(user, "disabled", False)),
        "firm_id": claims.get("firm_id"),
        "firm_role": claims.get("firm_role"),
        "schema_editor_role": claims.get("schema_editor_role"),
        "vff_dev": bool(claims.get("vff_dev")),
    }
