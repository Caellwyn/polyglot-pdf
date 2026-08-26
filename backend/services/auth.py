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

def verify_token(token: str) -> dict:
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
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        logger.warning("token_verification_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI dependency: require a Firebase ID token on an HTTP route.

    Reads `Authorization: Bearer <token>` and verifies it via verify_token
    (which honors the VFF_DISABLE_AUTH dev bypass, so local dev and the voice
    harness are unaffected). 401 on a missing or invalid token.

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
