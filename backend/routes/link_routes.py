"""Client magic links: mint (staff) + open (client). bd polyglot-pdf-ugm6.

TWO ENDPOINTS AT OPPOSITE ENDS OF THE TRUST SPECTRUM, in one file because
they are two halves of one contract -- what mint promises, open enforces:

  POST /api/links/mint  -- FIRM STAFF ONLY. Per-user Firebase auth, same as
                           the rest of the firm tier. Returns the URL and the
                           `jti` join key.
  POST /api/links/open  -- THE CLIENT. Completely unauthenticated: the token
                           IS the credential, because a client has no account
                           and must never have one.

MINTING IS OFF BY DEFAULT (LINK_MINTING_ENABLED). A live link is an
unauthenticated door to a paid Gemini session, and the rate limits + session
cost ceiling that bound that spend are a SEPARATE bead (polyglot-pdf-ik7e)
landing immediately after this one. The flag is what keeps those two facts
from ever being false at the same time: this bead can merge, and be deployed,
without a mintable link existing. ik7e flips it on. Do not default it to true
before that bead ships.

ASCII only.
"""
import asyncio
import os
import time
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.services.auth import require_auth
from backend.services.firms import get_allowed_kits
from backend.services.link_redemptions import (
    LinkAlreadyUsed,
    RedemptionUnavailable,
    open_link,
)
from backend.services.link_tokens import (
    DEFAULT_COMPLETE_WINDOW_S,
    DEFAULT_OPEN_WINDOW_S,
    LinkTokenError,
    completion_deadline,
    mint_link_token,
    verify_link_token,
)

_log = structlog.get_logger().bind(module="link_routes")

router = APIRouter(prefix="/api/links", tags=["client-links"])

# Windows are capped so a mis-set console (or a hostile staff request) cannot
# mint a link that is effectively permanent. The defaults are 48h to open and
# SEVEN DAYS to complete (services/link_tokens.py); these ceilings sit above
# them deliberately -- a cap equal to the default would mean any firm wanting
# slightly longer had to re-issue, which is exactly the staff work the 7-day
# window exists to avoid.
_MAX_OPEN_WINDOW_S = 14 * 24 * 3600
_MAX_COMPLETE_WINDOW_S = 30 * 24 * 3600


def _minting_enabled() -> bool:
    return os.getenv("LINK_MINTING_ENABLED", "false").lower() == "true"


class MintLinkRequest(BaseModel):
    """What an employee supplies. NOTE WHAT IS ABSENT: no client name, email,
    or case reference. Those live with the FIRM, keyed by the returned jti --
    the split-key invariant (see services/link_tokens.py). There is
    deliberately nowhere in this request to put a client identifier."""
    kit_id: str
    open_window_s: int = Field(default=DEFAULT_OPEN_WINDOW_S, ge=300)
    complete_window_s: int = Field(default=DEFAULT_COMPLETE_WINDOW_S, ge=300)


class MintLinkResponse(BaseModel):
    url: str
    jti: str
    expires_at: int


class OpenLinkRequest(BaseModel):
    token: str


class OpenLinkResponse(BaseModel):
    """What the client's browser needs to start filling -- and NOTHING else.

    Specifically NOT the firm's kit list: the client sees exactly the one form
    their link names. `firm_id` is included because the frontend must send it
    on the WS handshake for firm-keyed telemetry (bd xwlt), and it is not a
    secret from the person the firm sent the link to.
    """
    kit_id: str
    firm_id: str
    jti: str
    complete_by: int


def _link_base_url() -> str:
    """Where a minted link points. Configured, never derived from the request:
    trusting a Host header would let a caller mint links pointing at a domain
    they control while carrying OUR valid signature."""
    return os.getenv("LINK_BASE_URL", "").rstrip("/")


@router.post("/mint", response_model=MintLinkResponse)
async def mint_link(
    body: MintLinkRequest, user: dict = Depends(require_auth)
) -> MintLinkResponse:
    """Mint a one-time client link for a form this firm may use.

    AUTHORIZATION is the firm tier's normal per-user identity -- NOT a
    per-firm API key. The bead originally specified one "X-Editor-Token-
    style"; that is superseded (see services/link_tokens.py): it would
    duplicate a credential staff already hold, re-introduce the shared-secret
    pattern epic polyglot-pdf-ijntk is removing, and could not identify WHICH
    employee minted the link -- which the telemetry requirement needs.

    The kit must be in the firm's allowlist. `get_allowed_kits` already folds
    in "the firm exists and is active" and fails closed to [], so a suspended
    firm mints nothing without a second status read.
    """
    if not _minting_enabled():
        # 404, not 503: an endpoint that is not turned on should not advertise
        # that it exists.
        raise HTTPException(status_code=404, detail="Not found")

    firm_id = user.get("firm_id") if isinstance(user, dict) else None
    employee_id = user.get("uid") if isinstance(user, dict) else None
    if not isinstance(firm_id, str) or not firm_id:
        raise HTTPException(status_code=403, detail="Not a firm account")
    if not isinstance(employee_id, str) or not employee_id:
        # Every Firebase token carries a uid; its absence means something is
        # wrong with the token path, and minting an unattributable link would
        # silently break the telemetry requirement.
        raise HTTPException(status_code=403, detail="Unidentified caller")

    if not _link_base_url():
        _log.error("link_base_url_unset")
        raise HTTPException(status_code=503,
                            detail="Link delivery is not configured")

    # Firestore read (sync Admin SDK) off the event loop.
    allowed = await asyncio.to_thread(get_allowed_kits, firm_id)
    if body.kit_id not in set(allowed):
        # 404 for "not yours" AND "does not exist", exactly like the kit read
        # gates: the response must not reveal which kits other firms hold.
        raise HTTPException(status_code=404, detail="Kit not available")

    try:
        token, jti = mint_link_token(
            firm_id=firm_id,
            kit_id=body.kit_id,
            employee_id=employee_id,
            open_window_s=min(body.open_window_s, _MAX_OPEN_WINDOW_S),
            complete_window_s=min(body.complete_window_s,
                                  _MAX_COMPLETE_WINDOW_S),
        )
    except LinkTokenError as exc:
        # The only expected cause is a missing signing secret -- a deployment
        # fault, not a caller error.
        _log.error("link_mint_failed", firm_id=firm_id, error=str(exc))
        raise HTTPException(status_code=503,
                            detail="Link minting is not configured") from exc

    payload = verify_link_token(token)
    # AUDIT, keyed like the rest of the firm tier (bd xwlt): who minted what,
    # for which form. The jti is OUR pseudonym, never a client identifier.
    _log.info("link_minted", firm_id=firm_id, kit_id=body.kit_id,
              employee_id=employee_id, jti=jti)

    # The token rides in the FRAGMENT (#t=), which browsers do not send to
    # servers -- so it stays out of access logs, referrers, and proxy logs.
    return MintLinkResponse(
        url=_link_base_url() + "/f#t=" + token,
        jti=jti,
        expires_at=payload["exp"],
    )


@router.post("/open", response_model=OpenLinkResponse)
async def open_client_link(body: OpenLinkRequest) -> OpenLinkResponse:
    """Redeem a client link. UNAUTHENTICATED by design -- the token is the
    credential.

    EVERY failure returns the SAME 404. A bad signature, an expired window, a
    replayed link, a suspended firm, and a kit the firm no longer holds must
    be indistinguishable, or the differences become an oracle for probing
    which links and firms exist. The specific cause is logged, never returned.
    """
    generic = HTTPException(status_code=404, detail="This link is not valid.")

    try:
        payload = verify_link_token(body.token)
    except LinkTokenError as exc:
        _log.info("link_open_refused", reason=str(exc))
        raise generic from exc

    firm_id, kit_id = payload["firm_id"], payload["kit_id"]

    # RE-CHECK ENTITLEMENT AT OPEN, never trust the mint-time snapshot: a firm
    # may have been suspended, or the kit retired/removed from its allowlist,
    # in the 48 hours since. get_allowed_kits folds in the active-status check
    # and fails closed.
    allowed = await asyncio.to_thread(get_allowed_kits, firm_id)
    if kit_id not in set(allowed):
        _log.info("link_open_refused", reason="kit no longer allowed",
                  firm_id=firm_id, jti=payload["jti"])
        raise generic

    try:
        record = open_link(payload["jti"], firm_id, kit_id)
    except LinkAlreadyUsed as exc:
        _log.info("link_open_refused", reason="already completed",
                  jti=payload["jti"])
        raise generic from exc
    except RedemptionUnavailable as exc:
        # FAIL CLOSED: unable to confirm the link is unredeemed means we must
        # not admit it -- the failure being guarded is a replayed link
        # starting a second paid session.
        _log.error("link_open_unavailable", jti=payload["jti"], error=str(exc))
        raise generic from exc

    # VALIDATE opened_at rather than trusting the stored value. A corrupt or
    # missing stamp must not silently become "opened at the epoch", which
    # computes a deadline decades in the past and locks a legitimate client
    # out of a link they just opened -- nor a far-future stamp, which would
    # extend the window indefinitely. Fall back to NOW: the conservative
    # reading is that this open is the first one.
    opened_at = record.get("opened_at")
    now_s = int(time.time())
    if not isinstance(opened_at, int) or isinstance(opened_at, bool)             or opened_at <= 0 or opened_at > now_s + 300:
        _log.warning("link_opened_at_implausible", jti=payload["jti"],
                     opened_at=repr(opened_at))
        opened_at = now_s

    deadline = completion_deadline(payload, opened_at)
    if now_s >= deadline:
        _log.info("link_open_refused", reason="completion window elapsed",
                  jti=payload["jti"])
        raise generic

    _log.info("link_opened_ok", firm_id=firm_id, kit_id=kit_id,
              jti=payload["jti"], employee_id=payload["employee_id"])
    return OpenLinkResponse(
        kit_id=kit_id, firm_id=firm_id, jti=payload["jti"],
        complete_by=deadline,
    )
