import os
from typing import Optional

import firebase_admin
from firebase_admin import auth, credentials, firestore
from fastapi import Header, HTTPException, status
import structlog

logger = structlog.get_logger()

# Initialize Firebase Admin
# In Cloud Run, credentials are auto-detected (ADC).
# Locally, requires `gcloud auth application-default login`.
try:
    if not firebase_admin._apps:
        # Check if running locally/custom creds needed, or just default
        # For this setup, we assume ADC is sufficient.
        firebase_admin.initialize_app()
        logger.info("firebase_admin_initialized", method="ADC")
except Exception as e:
    logger.error("firebase_admin_init_failed", error=str(e))
    # We don't raise immediately to allow import, but verify_token will fail if not init

# TWO SEPARATE ALLOWLISTS (maintainer, 2026-08-22): "voice app accounts should
# be tied to firms, or a devs. editor accounts are separate and only tied to
# access to the editor and the forms in the GCS bucket that are not locked or
# deployed. Those should be 2 separate auth lists."
#
# So a valid Firebase account is NOT sufficient here. Without this, an
# editor-only account -- a subcontractor who polishes forms -- reaches
# /api/fill-pdf and /ws/fill, which is the second direction of bd
# polyglot-pdf-ijntk's criterion 3 and failed until this existed.
#
# This does NOT deepen the editor/voice coupling: each surface checks its OWN
# claim and neither reads the other's. That is more separable, not less.
VOICE_DEV_CLAIM = "vff_dev"


def _require_voice_access(claims: dict) -> None:
    """Refuse a valid account that is not a firm user or a dev.

    403 rather than 401 -- they authenticated fine; they are simply not on this
    list. Same distinction the editor draws, for the same reason: "wrong
    password" and "not permitted here" are different problems for whoever is
    reading the error.
    """
    if claims.get("firm_id") or claims.get(VOICE_DEV_CLAIM):
        return
    logger.warning("voice_access_refused_no_firm_or_dev_claim",
                   uid=claims.get("uid") or claims.get("sub"))
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This account is not enrolled for the voice application",
    )


def verify_token(token: str, require_enrolment: bool = True) -> dict:
    """
    Verifies a Firebase ID Token.
    Returns the decoded token dict (claims) if valid.
    Raises HTTPException(401) if invalid.
    """
    # Development Bypass -- LOCAL ONLY, inert on a deployed service.
    #
    # K_SERVICE is set by Cloud Run and by nothing else, so its presence means
    # "this is a real deployment" (the same signal the VERTEXAI guard uses,
    # bd polyglot-pdf-5e6a). Without this check the bypass returned a stub user
    # for EVERY caller of every auth-gated surface -- /ws/fill plus each
    # require_auth route, including /api/fill-pdf, which renders the client's
    # entered PII into a PDF -- on a service deployed
    # --allow-unauthenticated (bd polyglot-pdf-knmp).
    #
    # Settings carries the matching STARTUP guard, which is the primary
    # defense: a deployed service with this flag set refuses to boot. This
    # runtime check is the second layer, and it is not redundant -- it holds
    # even where Settings is never constructed or is bypassed, and it fails
    # the request CLOSED rather than trusting that startup validation ran.
    if os.getenv("VFF_DISABLE_AUTH", "false").lower() == "true":
        if os.getenv("K_SERVICE"):
            logger.error("auth_bypass_refused_on_deployed_service")
        else:
            logger.warning("auth_bypassed_via_env")
            return {"uid": "dev_user", "email": "dev@example.com"}

    try:
        # check_revoked costs a Firebase USER-RECORD FETCH per call, so it is
        # opt-in per caller rather than always-on:
        #   * SESSION START (the /ws/fill handshake) passes it -- that is where
        #     revoking a compromised account must actually take effect, and it
        #     happens once per session.
        #   * The PER-REQUEST hot path (TTS spellback fires MID-CONVERSATION)
        #     does not, because a round trip per utterance would be felt by the
        #     person speaking.
        # The window this leaves is one session, not the up-to-an-hour token
        # lifetime -- and a revoked user cannot start a new one.
        # SIGNATURE VERIFICATION ONLY -- deliberately no check_revoked.
        #
        # That flag turns this into a USER-RECORD FETCH needing
        # firebaseauth.users.get, which polyglot-backend-sa does not have. It
        # broke EVERY deployed connection with INSUFFICIENT_PERMISSION on
        # 2026-08-26; the app could not connect at all, while local tests and
        # CI stayed green because they stub this SDK.
        #
        # The PARAMETER is gone too, not just defaulted off: a knob nothing can
        # safely turn on is a trap, and a caller passing True would re-break
        # production. Restoring it means granting the IAM role FIRST.
        decoded_token = auth.verify_id_token(token)
    except Exception as e:
        logger.warning("token_verification_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # OUTSIDE the try: the broad `except Exception` above would otherwise catch
    # this 403 and re-raise it as a 401, collapsing "you are not enrolled" back
    # into "your credentials are bad" -- two different problems for whoever
    # reads the error.
    # Callers that only need to know WHO this is -- browsing the form
    # catalogue -- pass require_enrolment=False. Enrolment gates ACTING
    # on a form, not SELECTING one.
    if require_enrolment:
        _require_voice_access(decoded_token)
    return decoded_token

async def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI dependency: require a Firebase ID token on an HTTP route.

    Reads `Authorization: Bearer <token>` and verifies it via verify_token
    (which honors the VFF_DISABLE_AUTH dev bypass, so local dev and the voice
    harness are unaffected). 401 on a missing or invalid token, and 403 when
    the token is VALID but the account is not enrolled for the voice app (no
    firm_id and no dev claim) -- a caller that handles only 401 will mis-report
    an enrolment refusal as a credentials problem.

    This is the HTTP counterpart of the `?token=` check on /ws/fill
    (bd polyglot-pdf-z2is: /api/fill-pdf renders user-entered field values and
    must not be an open endpoint on a service deployed --allow-unauthenticated).
    """
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    return verify_token(token)


async def require_signin(authorization: Optional[str] = Header(None)) -> dict:
    """Require a VALID sign-in, but NOT voice-app enrolment.

    For the routes where a user SELECTS a form. Maintainer, 2026-08-25:

      "choosing a form to work on is a fundamental part of using the voice app
       and the whole app is blocked without access to that ... anyone using the
       app must have access to at least one form kit."

    A signed-in user with no firm and no dev claim otherwise lands in an app
    with nothing to pick and no way out: the only remedy the UI can offer is
    "sign in again", and signing in was never the problem.

    THIS COSTS NO CONFIDENTIALITY. These routes filter by firm THEMSELVES --
    list_form_kits returns only kits that are public or in the caller's own
    firm allowlist, and the schema route 404s a private kit the caller cannot
    see. The enrolment check never protected a private kit here; it only
    decided whether someone saw the PUBLIC ones, which is exactly what they
    need to use the app at all.

    Enrolment still gates ACTING on a form -- /api/fill-pdf, /ws/fill, TTS,
    and kit retirement -- through require_auth.
    """
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    # check_revoked stays off, as on the other per-request routes: it costs a
    # Firebase round trip and this runs on every catalogue load.
    return verify_token(token, require_enrolment=False)


def get_db():
    """Returns Firestore client"""
    return firestore.client()
