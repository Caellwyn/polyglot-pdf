"""Per-user identity for the ADMIN service (bd polyglot-pdf-7w17m).

MIRRORS backend/services/editor_auth.py -- same shape (dev-bypass check first,
then verify_id_token with no check_revoked, a 401/403 split with a
machine-readable prefix on the "no access at all" 403), same reasons:

  * The admin service reads its OWN claim (APP_ADMIN_CLAIM), not the voice
    app's firm_role or the editor's schema_editor_role. None of the three
    grants access to either of the others.
  * check_revoked stays OFF, on purpose (same scar as the editor and the
    public backend, CLAUDE.md scar #7): it forces a Firebase USER-RECORD
    FETCH needing firebaseauth.users.get. admin-backend-sa DOES hold
    roles/firebaseauth.admin (plan: "Admin service" gating,
    scripts/setup-admin-service.sh) -- unlike the public backend's narrow SA,
    it COULD afford this call. It is left off anyway for symmetry with the
    other two verifiers and because nothing in this bead's scope measured a
    need for instant revocation; if the admin service ever needs it, this
    comment is the note to revisit for THIS service specifically, since the
    IAM justification that ruled it out for the other two does not apply
    here.
  * admin-backend-sa's revoke_refresh_tokens still makes bootstrap_admin_
    user.py's --revoke take effect on the caller's NEXT token mint, same
    caveat as the editor's revoke path.

This is the FIRST of the four gates the plan names
(require_app_admin; require_firm_manager; require_app_admin_or_owning_
manager; require_google_oidc). The other three ship with their first
consuming routes (Epic 2 B-track / Epic 4), each proven against a real route
rather than shipped untested -- see admin_backend/tests/unit/
test_admin_route_auth.py, which derives the registered route set and asserts
each carries exactly one of the four names.
"""
from __future__ import annotations

import os
from typing import Annotated, Optional

import structlog
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

_log = structlog.get_logger().bind(module="admin_auth")

# The custom claim granting admin-console access. Boolean, per the plan
# ("Admin service" gating): a person either holds full admin access or does
# not -- there is no admin role gradient in this epic. Named for THIS
# surface so neither a firm claim nor an editor claim can grant it by
# accident, mirroring EDITOR_ROLE_CLAIM's isolation.
APP_ADMIN_CLAIM = "app_admin"

# Marks the ONE 403 that means "this account holds no admin access at all",
# so the console can route it to a refused/sign-out screen rather than
# surfacing it as an ordinary in-app refusal. Same idiom as
# editor_auth.NO_EDITOR_ACCESS_PREFIX: a machine-readable prefix, not prose a
# client string-matches -- every previous attempt in this repo to key on
# message text has been defeated by a rewording.
NO_ADMIN_ACCESS_PREFIX = "NO_ADMIN_ACCESS:"


class AdminActor(BaseModel):
    """WHO is acting, as an app admin.

    Mirrors EditorActor's shape (uid, email, label()) without the role field
    -- APP_ADMIN_CLAIM is boolean, so there is no second value to carry.
    """

    uid: str
    email: Optional[str] = None

    def label(self) -> str:
        """Human-facing name for this person -- for audit rows and log lines.

        Email when known, else the uid. Never empty: an audit row that names
        nobody is worse than one naming an opaque id.
        """
        return self.email or self.uid


def _dev_bypass_allowed() -> bool:
    """True only for genuine local dev, never on a deployed instance.

    Identical rule to editor_auth._dev_bypass_allowed and
    backend.services.auth's bypass: K_SERVICE is Cloud Run's marker, so its
    presence means we are deployed and the bypass is refused however the env
    is set. Fail-closed by construction rather than by discipline.
    """
    if os.getenv("VFF_DISABLE_AUTH", "").lower() != "true":
        return False
    if os.getenv("K_SERVICE"):
        _log.error("admin_auth_dev_bypass_refused_on_deployed_instance")
        return False
    return True


def verify_admin_token(token: str) -> AdminActor:
    """Resolve a Firebase ID token to an AdminActor, or raise 401/403.

    401 for a token that does not verify; 403 for a VALID account with no
    app_admin claim -- the distinction matters, since the second means "you
    are who you say you are, but you are not listed here".
    """
    if _dev_bypass_allowed():
        return AdminActor(uid="dev_admin", email="dev@example.com")

    import firebase_admin
    from firebase_admin import auth as fb_auth

    # OWN the init rather than inheriting whichever module happened to import
    # first -- same reasoning as editor_auth: without this, standing up the
    # admin service alone (no public backend, no editor import ahead of it)
    # would 401 every sign-in blaming the user's credential.
    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    try:
        # NO check_revoked -- see the module docstring.
        claims = fb_auth.verify_id_token(token)
    except Exception:
        # Deliberately opaque: the reason a token failed is not the caller's
        # business, and the specific exception types vary by SDK version.
        raise HTTPException(status_code=401,
                            detail="Invalid or expired sign-in")

    if claims.get(APP_ADMIN_CLAIM) is not True:
        # A REAL account with no admin claim. Not 401 -- they authenticated
        # fine; they are simply not an admin here.
        raise HTTPException(
            status_code=403,
            detail=(NO_ADMIN_ACCESS_PREFIX
                    + " This account does not have admin console access"),
        )

    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        # A verified token with no subject should be impossible; treat it as
        # a failure rather than inventing an identity, since every
        # downstream use (audit attribution) depends on uid being real.
        raise HTTPException(status_code=401,
                            detail="Invalid or expired sign-in")

    return AdminActor(uid=uid, email=claims.get("email"))


async def require_app_admin(
    authorization: Annotated[Optional[str], Header()] = None,
) -> AdminActor:
    """FastAPI dependency: the caller, as a person holding app_admin.

    `Authorization: Bearer` ONLY -- there is no legacy shared-token header on
    this surface to carry forward (unlike the editor's retired
    X-Editor-Token).

    The bypass is checked FIRST, matching both sibling verifiers: a
    tokenless local request must not 401 ahead of the bypass check.
    _dev_bypass_allowed refuses this outright on a deployed instance.
    """
    if _dev_bypass_allowed():
        return AdminActor(uid="dev_admin", email="dev@example.com")

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Sign-in required")
    return verify_admin_token(token)


# ---------------------------------------------------------------------------
# The COMPOSITE gate: app admin OR the owning firm's manager
# (bd polyglot-pdf-dmjl5)
# ---------------------------------------------------------------------------
#
# The plan's third gate. Two very different people reach the same routes:
#
#   * an APP ADMIN, who serves every firm and therefore must NAME the firm
#     they are acting on -- there is no other way to know which one;
#   * a FIRM MANAGER, whose firm comes from their VERIFIED TOKEN and who may
#     therefore not name one at all.
#
# THE REFUSAL IS THE POINT. A manager whose request body names a firm is
# refused with 403 rather than having the body quietly ignored. Silently
# overriding a caller-supplied firm_id with the token's would be SAFE (the
# token still wins) but it would be dishonest: a console bug that sent the
# wrong firm would look like it worked, and the operator would believe they
# had acted on a firm they had not. Refusing makes the disagreement visible
# at the one moment it is cheap to fix.

# The two shapes an actor can have on a composite route, as a machine-readable
# discriminator rather than "did email come back None" inference.
ACTOR_KIND_APP_ADMIN = "app_admin"
ACTOR_KIND_FIRM_MANAGER = "firm_manager"


class CompositeActor(BaseModel):
    """WHO is acting on a route both actors can reach.

    firm_id is the manager's own firm, taken from the token, and is None for
    an app admin -- an admin's target firm arrives in the request and is
    resolved by the ROUTE (which is also where the "a manager may not name
    one" refusal lives, since only the route can see its own body).
    """

    uid: str
    email: Optional[str] = None
    kind: str
    firm_id: Optional[str] = None

    @property
    def is_app_admin(self) -> bool:
        return self.kind == ACTOR_KIND_APP_ADMIN

    def label(self) -> str:
        """Human-facing name for audit rows and log lines. Never empty."""
        return self.email or self.uid


async def require_app_admin_or_owning_manager(
    authorization: Annotated[Optional[str], Header()] = None,
) -> CompositeActor:
    """FastAPI dependency: an app admin, OR a manager of some firm.

    ORDER MATTERS AND IS DELIBERATE. The app_admin claim is checked FIRST, so
    an account holding both app_admin and a firm manager claim acts as an app
    admin -- the strictly wider role. The reverse order would silently
    downgrade such an account to its own firm, which is the surprising
    outcome (and the one an operator would debug for an hour).

    Both branches verify the SAME token through the SAME call --
    firebase_admin.auth.verify_id_token, made by THIS module in both cases.
    Neither branch reaches into another surface's verifier, and neither
    invents a second credential path. What the manager branch borrows is the
    manager RULE (backend.services.firms.manager_firm_id), a pure predicate
    over the claims this module already verified.

    401 when the token does not verify at all; 403 when it verifies and the
    account is neither an app admin nor any firm's manager.
    """
    if _dev_bypass_allowed():
        return CompositeActor(
            uid="dev_admin",
            email="dev@example.com",
            kind=ACTOR_KIND_APP_ADMIN,
        )

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Sign-in required")

    # Branch 1: app admin. verify_admin_token raises 403 for a VALID account
    # with no app_admin claim -- which is not a refusal here, it is the
    # signal to try the manager branch. A 401 IS terminal: an unverifiable
    # token will not verify differently for the second reader.
    try:
        admin = verify_admin_token(token)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise
        admin = None
    if admin is not None:
        return CompositeActor(
            uid=admin.uid, email=admin.email, kind=ACTOR_KIND_APP_ADMIN)

    # Branch 2: firm manager. THIS MODULE VERIFIES THE TOKEN ITSELF, with
    # the same fb_auth.verify_id_token the admin branch used -- it does not
    # call backend.services.auth.verify_token. That module is the VOICE
    # app's verifier: importing it would make the admin service depend on
    # the voice surface's enrolment rules (which have nothing to do with
    # managing staff) and would break this module's liftability, pinned by
    # test_admin_auth.py::test_admin_auth_does_not_import_the_other_two_
    # auth_modules.
    #
    # What IS shared is the manager RULE, and only the rule:
    # backend.services.firms.manager_firm_id is a pure, side-effect-free
    # predicate over an already-verified claims dict, living in the module
    # that owns what a firm IS. Sharing it is what keeps that rule in ONE
    # home (CLAUDE.md scar #8) without sharing a verifier.
    from backend.services.firms import manager_firm_id

    import firebase_admin
    from firebase_admin import auth as fb_auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    try:
        claims = fb_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401,
                            detail="Invalid or expired sign-in")

    firm_id = manager_firm_id(claims)
    if not firm_id:
        raise HTTPException(
            status_code=403,
            detail=(NO_ADMIN_ACCESS_PREFIX
                    + " This account is neither an admin nor a firm manager"),
        )
    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        raise HTTPException(status_code=401,
                            detail="Invalid or expired sign-in")
    return CompositeActor(
        uid=uid,
        email=claims.get("email"),
        kind=ACTOR_KIND_FIRM_MANAGER,
        firm_id=firm_id,
    )


def resolve_target_firm(actor: CompositeActor,
                        body_firm_id: Optional[str]) -> str:
    """The firm this request acts on, or the refusal that ends it.

    THE ONE HOME for the two-actor firm rule (CLAUDE.md scar #8), so every
    composite route resolves it identically instead of each restating it:

      * a MANAGER's firm comes from the token; a body that names ANY firm is
        403, including one naming their own -- "the same value" is not the
        test, "did you try to choose" is. Accepting a matching value would
        make the refusal depend on what the caller happened to send, and the
        next console version that sends it for every request would silently
        stop being refused.
      * an APP ADMIN must name one; omitting it is 422, since there is no
        firm to fall back to and defaulting to any particular firm would be
        a guess with a write behind it.
    """
    if not actor.is_app_admin:
        if body_firm_id is not None:
            raise HTTPException(
                status_code=403,
                detail=("a firm manager may not name a firm; the firm is "
                        "taken from your sign-in"),
            )
        assert actor.firm_id, "a manager actor always carries a firm_id"
        return actor.firm_id
    if not body_firm_id:
        raise HTTPException(
            status_code=422,
            detail="firm_id is required when acting as an app admin",
        )
    return body_firm_id
