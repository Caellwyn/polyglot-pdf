import asyncio
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

    # TWO CREDENTIAL KINDS reach HTTP routes, exactly as on /ws/fill
    # (bd polyglot-pdf-ugm6). A firm's CLIENT has no Firebase account and
    # never will, so their signed magic-link token is what authenticates the
    # manifest read, the schema read, and the PDF fill their session needs.
    # Without this the client tier dead-ends at "Unable to load forms": the
    # WS was taught to accept a link token, but every HTTP route it depends
    # on still 401'd.
    #
    # Dispatch is on SHAPE and only on shape -- a link token has ONE dot, a
    # Firebase JWT has two -- so neither verifier can be handed the other's
    # token and a caller cannot opt into the weaker check by labelling
    # theirs. See services/link_tokens.py for the credential boundary.
    if token.count(".") == 1:
        # NO REDEMPTION: require_auth gates RETRIEVAL (the manifest, the
        # schema, /api/fill-pdf's pure PyMuPDF render). Burning a link must
        # not take away the document the client already filled. The two PAID
        # routes it also gates (/api/tts/*) declare require_paid_client_work
        # instead, which does redeem.
        return await asyncio.to_thread(resolve_client_link_credential, token)

    return verify_token(token)


def resolve_client_link_credential(token: str, *, redeem: bool = False) -> dict:
    """Resolve a CLIENT LINK token to claims. Raises 401.

    REDEEM=TRUE ONLY FOR PAID WORK (maintainer, 2026-08-24: "There's not
    really any reason to have a time limit on saving or printing. That's all
    client side. The TTL should be backend connection."). A completed link
    must not start another Gemini session or buy another TTS synthesis -- but
    downloading, printing and previewing are the client retrieving the
    document they already produced, and a clock on that only loses them their
    work. Retrieval still requires a VALID SIGNED link inside its open
    window, scoped to that link's single kit.

    THE ONE PLACE a link credential is turned into claims (bd
    polyglot-pdf-ugm6). Extracted from require_auth because it is not the
    only door: GET /api/form-kits/{kit_id}/pdf resolves credentials itself
    (it is OPTIONAL-auth -- a public kit's blank template is served
    anonymously), so it bypasses require_auth entirely and silently rejected
    every client link, leaving a client staring at their form with no PDF
    (Opus cross-surface r6).

    The set of credential-resolution sites is exactly three -- this, the
    socket's _verify_ws_credential, and the pdf route -- and it is PINNED BY
    TEST so a fourth fails CI instead of a review round.

    Synchronous on purpose: callers decide whether to hop off the loop
    (require_auth does; the pdf route is already sync at that point).
    """
    from backend.services.link_redemptions import (
        LinkAlreadyUsed,
        LinkWindowElapsed,
        RedemptionUnavailable,
        enforce_link_redemption,
    )
    from backend.services.link_tokens import LinkTokenError, verify_link_token

    _unauth = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_link_token(token)
    except LinkTokenError as exc:
        logger.warning("link_token_rejected", error=str(exc))
        raise _unauth from exc

    claims = {
        "uid": None,
        "firm_id": payload["firm_id"],
        "link_kit_id": payload["kit_id"],
        "employee_id": payload["employee_id"],
        "jti": payload["jti"],
        "cw": payload["cw"],
        "is_client_link": True,
    }
    if redeem:
        try:
            enforce_link_redemption(claims)
        except (LinkAlreadyUsed, LinkWindowElapsed, RedemptionUnavailable) as exc:
            logger.warning("link_redemption_refused", error=str(exc))
            raise _unauth from exc
    return claims


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

    A CLIENT LINK IS ALSO A VALID CREDENTIAL HERE (bd polyglot-pdf-ugm6).
    These two routes are the client's FIRST TWO CALLS -- the form list and
    its schema -- so refusing a link token here dead-ends the client tier
    before it reaches the voice session, on this surface only. That is the
    same failure the enrolment gate caused for claimless users and the same
    remedy: dispatch on the token's SHAPE, never on a caller-supplied hint.
    Retrieval, so NO REDEMPTION -- reading the form you were sent must not
    burn the link that sent it.
    """
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token.count(".") == 1:
        return await asyncio.to_thread(resolve_client_link_credential, token)
    return verify_token(token, require_enrolment=False)


def get_db():
    """Returns Firestore client"""
    return firestore.client()


async def require_paid_client_work(
    authorization: Optional[str] = Header(None),
) -> dict:
    """require_auth PLUS redemption -- for routes that SPEND MONEY.

    The split is the whole point of the correction: "one time" bounds paid
    work, not the client's access to their own document. A completed link
    buys no further synthesis and starts no further session; it can still
    download the PDF it already produced.

    Declare this instead of require_auth on any route that calls a model.
    The set is pinned by test_http_route_auth.py.
    """
    claims = await require_auth(authorization)
    if not (isinstance(claims, dict) and claims.get("is_client_link")):
        return claims          # staff: there is no link to redeem

    from backend.services.link_redemptions import (
        LinkAlreadyUsed,
        LinkWindowElapsed,
        RedemptionUnavailable,
        enforce_link_redemption,
    )
    try:
        # Off the event loop: a sync Admin-SDK read inside an async
        # dependency blocks the SHARED Cloud Run loop, so a slow Firestore
        # would stall every concurrent request, in-flight audio included.
        await asyncio.to_thread(enforce_link_redemption, claims)
    except (LinkAlreadyUsed, LinkWindowElapsed, RedemptionUnavailable) as exc:
        # One refusal for all three -- already-used, window-closed and
        # store-unreachable must be indistinguishable, and an unreachable
        # store FAILS CLOSED.
        logger.warning("link_redemption_refused", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return claims
