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
