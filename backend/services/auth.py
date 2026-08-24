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
        # Imported here, not at module scope: link_tokens imports nothing
        # from this module, and keeping the edge one-way avoids a cycle.
        from backend.services.link_tokens import (
            LinkTokenError,
            verify_link_token,
        )
        try:
            payload = verify_link_token(token)
        except LinkTokenError as exc:
            logger.warning("link_token_rejected", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        # The claims a CLIENT gets. Note what is ABSENT: no uid (they have no
        # account) and NO firm_role -- so every role-gated surface (the firm
        # retire route, and anything added later) refuses them by the same
        # check that refuses an ordinary employee. A client is not staff.
        claims = {
            "uid": None,
            "firm_id": payload["firm_id"],
            "link_kit_id": payload["kit_id"],
            "employee_id": payload["employee_id"],
            "jti": payload["jti"],
            "cw": payload["cw"],   # completion window, needed by the gate below
            "is_client_link": True,
        }

        # REDEEM HERE TOO (Opus cross-surface r1). verify_link_token checks
        # the signature and the OPEN window and nothing else, so without this
        # a COMPLETED link -- or one whose completion window elapsed -- kept
        # serving schema, PDF bytes, /api/fill-pdf and the two PAID TTS
        # routes for the rest of its ~48h exp. The socket redeemed; these
        # nine routes did not, which is the same "enforced only on a door an
        # attacker need not use" hole the socket fix closed.
        from backend.services.link_redemptions import (
            LinkAlreadyUsed,
            LinkWindowElapsed,
            RedemptionUnavailable,
            enforce_link_redemption,
        )
        try:
            # OFF THE EVENT LOOP. This is a synchronous Admin-SDK Firestore
            # read inside an async dependency, so calling it directly blocks
            # the SHARED Cloud Run loop -- a slow (not failed) Firestore
            # would stall every concurrent request in the container,
            # including in-flight audio frames for other sessions. The
            # fail-closed handling below covers the store being DOWN; only
            # this covers it being SLOW. The socket already does it this way
            # (websocket_routes) -- this was the one site that did not.
            await asyncio.to_thread(enforce_link_redemption, claims)
        except (LinkAlreadyUsed, LinkWindowElapsed, RedemptionUnavailable) as exc:
            # ONE refusal for all three: already-used, window-closed, and
            # store-unreachable must be indistinguishable, and an unreachable
            # store must FAIL CLOSED here exactly as it does at the socket.
            logger.warning("link_redemption_refused", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        return claims

    return verify_token(token)


def get_db():
    """Returns Firestore client"""
    return firestore.client()
