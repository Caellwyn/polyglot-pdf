"""Per-user identity for the SCHEMA EDITOR (bd polyglot-pdf-hn0jq).

The editor authenticated with two shared secrets -- everyone holding the editor
token was one principal to the server, and likewise every author. No user id, no
session, nothing in a request saying WHO acted. That blocked editor-vs-editor
locking, made every audit answer "an editor did it", and turned revoking one
subcontractor into rotating the token for everyone.

This resolves a caller to a PERSON, from a Firebase ID token.

DELIBERATELY SEPARATE FROM backend/services/auth.py, which serves the voice app.
Maintainer constraint, 2026-08-20: "separating them fully right now is out of
scope. That's its own epic. What I don't want is to create NEW dependencies that
I will just need to unravel against later." So:

  * The editor reads its OWN claim (EDITOR_ROLE_CLAIM), not the voice app's
    firm_role. A voice-app account carries no editor access, and an editor
    account carries no voice access -- verified by test, both directions.
  * This module does not import from backend.services.auth, and nothing there
    imports from here. Either could move to another project without touching
    the other.
  * It reuses the SAME Firebase project deliberately -- a second project is the
    separation epic's job, not this bead's, and standing one up here would be a
    new dependency to unravel.

The claim-stamping side lives in scripts/bootstrap_editor_user.py, mirroring
scripts/bootstrap_firm.py as a TEMPLATE rather than extending it.
"""
from __future__ import annotations

import os
from typing import Annotated, Optional

import structlog
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

_log = structlog.get_logger().bind(module="editor_auth")

# The custom claim carrying a person's editor role. Named for THIS surface so a
# voice-app account cannot grant editor access by accident, and so a future
# separation epic can move it wholesale.
EDITOR_ROLE_CLAIM = "schema_editor_role"

ROLE_EDITOR = "editor"
ROLE_AUTHOR = "author"
_VALID_ROLES = (ROLE_EDITOR, ROLE_AUTHOR)


class EditorActor(BaseModel):
    """WHO is acting, and in what capacity.

    Replaces the bare role string the shared-token guards returned. `role` keeps
    the same two values so the ~16 gate-only and log-only call sites are
    unaffected; the ~10 sites that use the value read `.role`.
    """

    uid: str
    email: Optional[str] = None
    role: str

    @property
    def is_author(self) -> bool:
        return self.role == ROLE_AUTHOR

    def label(self) -> str:
        """Human-facing name for this person -- for `heldBy` and log lines.

        Email when known, else the uid. Never empty: a lock that displays
        nothing is worse than one that displays an opaque id.
        """
        return self.email or self.uid


def _dev_bypass_allowed() -> bool:
    """True only for genuine local dev, never on a deployed instance.

    Mirrors the voice app's posture: K_SERVICE is Cloud Run's marker, so its
    presence means we are deployed and the bypass is refused however the env is
    set. Fail-closed by construction rather than by discipline.
    """
    if os.getenv("VFF_DISABLE_AUTH", "").lower() != "true":
        return False
    if os.getenv("K_SERVICE"):
        _log.error("editor_auth_dev_bypass_refused_on_deployed_instance")
        return False
    return True


def verify_editor_token(token: str) -> EditorActor:
    """Resolve a Firebase ID token to an EditorActor, or raise 401/403.

    401 for a token that does not verify; 403 for a VALID account with no editor
    claim -- the distinction matters, since the second means "you are who you say
    you are, but you are not listed here", which is exactly what a voice-app user
    hitting the editor should see.
    """
    if _dev_bypass_allowed():
        return EditorActor(uid="dev_user", email="dev@example.com",
                           role=ROLE_AUTHOR)

    import firebase_admin
    from firebase_admin import auth as fb_auth

    # OWN the init rather than inheriting whichever module happened to import
    # first. Without this the editor works only because the voice app's auth.py
    # initialised the default app -- lift the editor out and every sign-in 401s
    # with a message blaming the user's credential, because the broad except
    # below swallows "The default Firebase app does not exist". Measured.
    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    try:
        # NO check_revoked -- and this is a REGRESSION accepted on purpose.
        #
        # It forces a Firebase USER-RECORD FETCH, needing firebaseauth.users.get.
        # The editor API runs on the SAME Cloud Run service as the voice app
        # (polyglot-backend), whose service account deliberately lacks that
        # permission, so every deployed sign-in failed with
        # INSUFFICIENT_PERMISSION. Measured on the live service 2026-08-26.
        #
        # STRUCTURALLY INVISIBLE locally and in tests: the dev bypass returns
        # before this line and every test stubs the SDK.
        #
        # THE COST, stated plainly: revoking an editor now takes effect when
        # their token expires (up to an hour), NOT immediately -- which is
        # weaker than the shared secret this replaced, where rotation was
        # instant. bootstrap_editor_user.py still revokes refresh tokens, so a
        # revoked user cannot MINT a new token; they simply keep the one they
        # hold until it expires. The maintainer chose this over granting the
        # deployed backend permission to read any user record (2026-08-26).
        claims = fb_auth.verify_id_token(token)
    except Exception:
        # Deliberately opaque: the reason a token failed is not the caller's
        # business, and the specific exception types vary by SDK version.
        raise HTTPException(status_code=401,
                            detail="Invalid or expired sign-in")

    role = claims.get(EDITOR_ROLE_CLAIM)
    if role not in _VALID_ROLES:
        # A REAL account with no editor role. Not 401 -- they authenticated
        # fine; they are simply not an editor here. This is the line that keeps
        # a voice-app account from reaching the editor.
        raise HTTPException(
            status_code=403,
            detail="This account does not have schema editor access",
        )

    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        # A verified token with no subject should be impossible; treat it as a
        # failure rather than inventing an identity, since every downstream use
        # (locking, attribution) depends on uid being a real person.
        raise HTTPException(status_code=401,
                            detail="Invalid or expired sign-in")

    return EditorActor(uid=uid, email=claims.get("email"), role=role)


async def require_editor_actor(
    authorization: Annotated[Optional[str], Header()] = None,
    x_editor_token: Annotated[Optional[str], Header()] = None,
) -> EditorActor:
    """FastAPI dependency: the caller, as a person, with editor or author role.

    Author strictly includes editor, so routes needing only editor accept both --
    the same rule the shared-token guards used.

    Reads the ID token from EITHER `Authorization: Bearer` (the standard, and
    what a Firebase client sends) or `X-Editor-Token` (the header this surface
    has always used). Accepting both is what lets the frontend move over in its
    own child bead rather than having to land in the same commit as the server
    -- the header carries a per-user ID token either way, so this is a transport
    detail, not a second auth path.
    """
    # The bypass is checked FIRST, as backend/services/auth.py does for the
    # voice app. Behind the header check it was unreachable without a token, so
    # a local caller that sent no header got 401 "Sign-in required" even with
    # the bypass on -- the two surfaces silently disagreed, and the local
    # editor only worked because its launcher happens to bake a token.
    # _dev_bypass_allowed refuses this outright on a deployed instance.
    if _dev_bypass_allowed():
        return EditorActor(uid="dev_user", email="dev@example.com",
                           role=ROLE_AUTHOR)

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif x_editor_token:
        token = x_editor_token
    if not token:
        raise HTTPException(status_code=401, detail="Sign-in required")
    return verify_editor_token(token)


async def require_author_actor(
    actor: Annotated[EditorActor, Depends(require_editor_actor)],
) -> EditorActor:
    """Author-only gate. 403 for an editor, matching the previous behaviour."""
    if not actor.is_author:
        raise HTTPException(
            status_code=403,
            detail="This action requires the author role",
        )
    return actor
