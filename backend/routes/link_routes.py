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
cost ceiling that bound that spend were a SEPARATE bead (polyglot-pdf-ik7e).
THAT BEAD HAS SHIPPED, so the interlock is satisfied and enabling the flag is
legitimate: deploy-demo.sh turns it on for the demo (bd polyglot-pdf-gob8l).
The default stays false, and must stay false in any environment where the
spend ceiling is not enforced -- the flag is what keeps "a mintable link
exists" and "nothing bounds its spend" from ever being true at once.

LINK_MINTING_ENABLED is now a RUNTIME setting (bd polyglot-pdf-bg313):
_minting_enabled() reads backend.services.runtime_config, which resolves
app_config/{channel} in Firestore (TTL-cached, with an env-default fallback
matching the value above) instead of os.getenv directly. This lets an
operator flip the flag from the admin console with no redeploy.

RESERVE BEFORE SIGNING (bd polyglot-pdf-jecrl / Epic 2 bead A3). The mint
route now spends a CREDIT, and the order is load-bearing: the jti is
generated first (link_tokens.new_jti()), the reservation transaction runs
second, and the token is signed LAST, from the jti the reservation already
committed. Any other order leaves a signed token behind a refused
reservation -- and a signed token that opens is a paid Gemini session
nobody was charged for. The whole reservation (the live-firm channel gate,
the balance check, the ledger debit, and the links/{jti} mint record) is
ONE Firestore transaction via credit_ledger.append_entry(); if any part of
it refuses, nothing was written and nothing was signed.

The other half of the same contract lives in
backend/services/link_redemptions.py: open now REQUIRES that mint record,
so a token can only open if a reservation committed for it. The two rules
are one invariant seen from both ends.

ASCII only.
"""
import asyncio
import os
import time
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.services import links_store
from backend.services.auth import get_db, require_auth
from backend.services.credit_ledger import (
    InsufficientCredits,
    LedgerError,
    TYPE_MINT_DEBIT,
    append_entry,
)
from backend.services.firms import FIRM_KIND_MOCK, get_allowed_kits
from backend.services.kit_commercials import resolve_commercial
from backend.services.link_metering import record_mint
from backend.services.link_redemptions import (
    LinkAlreadyUsed,
    LinkNotMinted,
    LinkWindowElapsed,
    RedemptionUnavailable,
    enforce_link_redemption,
)
from backend.services.link_tokens import (
    DEFAULT_COMPLETE_WINDOW_S,
    DEFAULT_OPEN_WINDOW_S,
    LinkTokenError,
    completion_deadline,
    link_channel,
    mint_link_token,
    new_jti,
    verify_link_token,
)
from backend.services.runtime_config import credits_enforced as _rc_credits_enforced
from backend.services.runtime_config import minting_enabled as _rc_minting_enabled
from backend.services.usage_rollups import record_link_minted

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
    return _rc_minting_enabled()


def _credits_enforced() -> bool:
    return _rc_credits_enforced()


class MintRefused(Exception):
    """A reservation refused the mint. Carries the HTTP status to return.

    STAFF-FACING, so unlike the client-facing /open surface these DO
    differentiate: an employee who cannot mint needs to know whether their
    firm is out of credits (402, buy more) or is a live firm on a non-demo
    channel (403, you are on the wrong deployment). The uniform-404 oracle
    rule protects the UNAUTHENTICATED door; this door already knows exactly
    who the caller is and which firm they belong to, so hiding the reason
    would only cost the console a useful message.
    """

    def __init__(self, status_code: int, detail: str, reason: str):
        self.status_code = status_code
        self.detail = detail
        self.reason = reason
        super().__init__(reason)


def _live_firm_channel_ok(firm_kind: Optional[str]) -> bool:
    """May a firm of this kind mint on THIS process's channel?

    THE RAW ENV VAR, DELIBERATELY NOT link_channel(). link_channel()'s
    default is "demo" (services/link_tokens.py: an unconfigured deploy keeps
    minting and opening exactly the links it does today), so asking it would
    make an UNSET channel -- a laptop, a one-off container, a misconfigured
    revision -- look like the demo and let it mint against a paying firm.
    Reading os.environ directly means "demo" has to be written down
    somewhere before a live firm can be charged.

    Both halves of that are deliberate and both are pinned: an unset channel
    still MINTS (with aud=demo, today's behaviour, for mock firms) while
    still REFUSING live firms. A firm with no `kind` at all -- the window
    between this code deploying and the backfill (Epic 2 bead A6) -- is
    treated as live, the same fail-closed polarity firms.firm_kind() uses,
    because a mis-defaulted mock firm merely blocks staging while a
    mis-defaulted live firm mints for free.
    """
    if firm_kind == FIRM_KIND_MOCK:
        return True
    return os.environ.get("LINK_CHANNEL", "").strip() == "demo"


def _reserve_mint(
    jti: str,
    firm_id: str,
    kit_id: str,
    employee_id: str,
    credit_cost: int,
    cap_usd: float,
    open_deadline: int,
    channel: str,
    enforced: bool,
    now: Optional[float] = None,
    employee_email: Optional[str] = None,
) -> dict:
    """Reserve one link's credit, ATOMICALLY, before any token is signed.

    SYNC (Admin SDK transaction). The route runs this under
    asyncio.to_thread, like every other Firestore call in this file.

    ONE transaction writes three things or none: the firm's new balance, the
    `mint_debit` ledger entry, and the links/{jti} mint record. It is
    credit_ledger.append_entry() -- the repo's ONE writer of
    balance_credits -- with the mint record passed as an `extra_writes`
    join, so there is no second transaction and no window in which a debit
    exists without a record (a link nobody can open, silently charged for)
    or a record exists without a debit (a free paid session).

    Raises MintRefused for the two refusals a caller must translate to HTTP:
      403 -- a live firm (or a firm with no `kind`) on a channel that is not
             explicitly `demo`. Checked INSIDE the transaction, off the same
             firm snapshot the balance comes from, so a firm flipped from
             mock to live mid-flight cannot slip a mint through between the
             read and the write.
      402 -- `enforced` and the balance does not cover `credit_cost`.

    Raises LedgerError for anything else (no such firm, unreachable store):
    the route turns those into a 503, because they are deployment faults,
    not caller errors.

    `enforced` is passed IN rather than read here so the route resolves it
    once, off the event loop, alongside the minting flag -- and so a test
    can drive both settings without patching runtime_config's cache.

    employee_email (bd polyglot-pdf-cpsi0): the minting account's email
    claim, when the verified token carries one. Threaded to BOTH the mint
    record (`employee_email`, via build_mint_record) and the ledger entry
    (`actor_email`, via append_entry) so the two records the console reads
    -- the links table and the ledger table -- agree on the same label for
    the same mint. Optional: a token with no email claim (should not
    happen for a real Firebase account, but is not assumed) leaves both
    fields None, exactly as they were before this bead.
    """
    db = get_db()
    if db is None:
        raise LedgerError("no firestore client")

    def _extra_writes(tx, firm):
        # Runs INSIDE append_entry's transaction body, after its reads. The
        # gate lives here, not before the transaction, because `firm` is the
        # transaction's own snapshot: checking a separately-read copy would
        # let a firm flipped mock -> live between the two reads mint once on
        # staging against real money.
        kind = firm.get("kind")
        if not _live_firm_channel_ok(kind):
            raise MintRefused(
                403,
                "This deployment cannot mint links for a live firm.",
                "live firm on channel " + repr(os.environ.get("LINK_CHANNEL", "")),
            )
        # links_store.record_mint() builds the SAME document shape, but it
        # issues its own set() -- this write must ride the transaction, so
        # the shape is built through the store's builder and written with
        # tx.set(). Any drift between the two is a set difference a test
        # catches (test_mint_record_shape_matches_links_store).
        record = links_store.build_mint_record(
            jti=jti,
            firm_id=firm_id,
            kit_id=kit_id,
            employee_id=employee_id,
            credit_cost=credit_cost,
            cap_usd=cap_usd,
            open_deadline=open_deadline,
            now=now,
            employee_email=employee_email,
        )
        tx.set(links_store.mint_record_ref(db, jti, channel), record)

    try:
        return append_entry(
            db,
            firm_id,
            entry_type=TYPE_MINT_DEBIT,
            amount=-int(credit_cost),
            actor=employee_id,
            actor_email=employee_email,
            channel=channel,
            link_jti=jti,
            kit_id=kit_id,
            require_sufficient_balance=enforced,
            extra_writes=_extra_writes,
            ts=now,
        )
    except InsufficientCredits as exc:
        raise MintRefused(
            402,
            "This firm does not have enough credits to mint a link.",
            "insufficient credits",
        ) from exc


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
    their link names.

    `firm_id` is INFORMATIONAL ONLY. An earlier version of this docstring said
    the frontend "must send it on the WS handshake for firm-keyed telemetry",
    which was false in both directions (Opus r10): the frontend never reads
    it, and it must not -- the socket derives firm identity from the signed
    TOKEN CLAIM precisely so the handshake is never trusted for identity.
    Wiring it the way that sentence described would have been a security
    regression. It is kept because it is not a secret from the person the
    firm sent the link to, and a console/debug view may want it.
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

    RESERVE, THEN SIGN (Epic 2 bead A3). The credit is debited, the ledger
    entry written and the links/{jti} mint record created in ONE transaction
    BEFORE mint_link_token() is called. The token is then signed from the
    jti that transaction committed. A refusal therefore leaves nothing
    behind: no token, no ledger entry, no record -- and no way for the
    caller to open a link they were not charged for.

    THE REFUSALS, and why they are NOT the uniform 404 the client-facing
    /open uses: this door is authenticated staff, so it may say what went
    wrong. 402 -- the firm is out of credits (only when CREDITS_ENFORCED;
    with enforcement off the debit is still written and the balance may go
    negative, the metered soft-launch mode). 403 -- a live firm on a
    deployment whose LINK_CHANNEL is not exactly `demo`.
    """
    # Off the event loop: _minting_enabled() now resolves runtime_config,
    # which on a cache miss is a sync Admin-SDK Firestore read (bd
    # polyglot-pdf-bg313, Opus cross-surface r1). A sync read inside an async
    # route blocks the SHARED Cloud Run loop, so a slow Firestore would stall
    # every concurrent request, in-flight audio included -- the same hazard
    # services/auth.py:291 documents and the other Firestore reads in this
    # file already avoid.
    if not await asyncio.to_thread(_minting_enabled):
        # 404, not 503: an endpoint that is not turned on should not advertise
        # that it exists.
        raise HTTPException(status_code=404, detail="Not found")

    firm_id = user.get("firm_id") if isinstance(user, dict) else None
    employee_id = user.get("uid") if isinstance(user, dict) else None
    # bd polyglot-pdf-cpsi0: the verified token's email claim, purely a
    # human-readable label riding alongside employee_id -- never validated,
    # never required (an absent claim leaves the label None, exactly the
    # prior behavior), and never used for identity: employee_id (the uid)
    # remains the only value any gate or query keys on.
    employee_email = user.get("email") if isinstance(user, dict) else None
    if not isinstance(employee_email, str) or not employee_email:
        employee_email = None
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

    # --- RESERVE (before anything is signed) ----------------------------
    # The jti comes first because the reservation writes links/{jti}: the
    # document is keyed by an id the token does not exist to supply yet.
    jti = new_jti()
    open_window_s = min(body.open_window_s, _MAX_OPEN_WINDOW_S)
    complete_window_s = min(body.complete_window_s, _MAX_COMPLETE_WINDOW_S)
    # ONE clock for the reservation and the signature. The mint record's
    # `open_deadline` must EQUAL the token's `exp` -- the A5 expiry sweep
    # queries Firestore on that field to decide what to refund, and a record
    # whose deadline drifted from the token's would either refund a link
    # that can still open (giving back a credit for a session about to be
    # spent) or leave a dead link unrefunded. Passing `now=issued` into
    # mint_link_token pins both to the same second instead of letting two
    # time.time() calls straddle a tick.
    issued = int(time.time())
    open_deadline = issued + open_window_s

    # The kit's commercial doc. Read OUTSIDE the transaction and fail-soft
    # (see services/kit_commercials.py): a price and a ceiling both have safe
    # defaults, and the invariant that matters -- a signed token always has a
    # debit and a record behind it -- is the transaction's job, not this
    # read's.
    commercial = await asyncio.to_thread(resolve_commercial, body.kit_id)
    credit_cost = commercial["credit_cost"]
    cap_usd = commercial["cap_usd"]

    channel = link_channel()
    enforced = await asyncio.to_thread(_credits_enforced)
    try:
        reservation = await asyncio.to_thread(
            _reserve_mint,
            jti,
            firm_id,
            body.kit_id,
            employee_id,
            credit_cost,
            cap_usd,
            open_deadline,
            channel,
            enforced,
            issued,
            employee_email=employee_email,
        )
    except MintRefused as exc:
        _log.info("link_mint_refused", firm_id=firm_id, kit_id=body.kit_id,
                  employee_id=employee_id, reason=exc.reason,
                  status_code=exc.status_code)
        raise HTTPException(status_code=exc.status_code,
                            detail=exc.detail) from exc
    except LedgerError as exc:
        # No such firm, or an unreachable store. A deployment/data fault, not
        # a caller error -- and NOTHING was committed, so nothing is signed.
        _log.error("link_mint_reserve_failed", firm_id=firm_id,
                   kit_id=body.kit_id, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Link minting is temporarily unavailable") from exc

    # USAGE ROLLUP (bd polyglot-pdf-he3lt), AFTER the reservation has
    # committed -- never inside it (see usage_rollups.record_link_minted's
    # own docstring). Wrapped in its OWN try/except here, on top of
    # record_link_minted's own never-raises contract -- defense in depth,
    # mirroring websocket_routes.py's own record_session_end call site: a
    # rollup failure must leave the mint successful, and this guards against
    # an unexpected exception raised BEFORE record_link_minted's own
    # internal try/except is reached (or a future edit that removes it),
    # not just the write itself failing.
    try:
        await asyncio.to_thread(
            record_link_minted,
            firm_id=firm_id,
            kit_id=body.kit_id,
            employee_id=employee_id,
            channel=channel,
            now=issued,
        )
    except Exception as exc:  # noqa: BLE001 -- best-effort, never fail the mint
        _log.error("link_mint_usage_rollup_failed", firm_id=firm_id,
                  jti=jti, error=str(exc))

    # --- SIGN (only now, from the jti the reservation committed) ---------
    try:
        token, signed_jti = mint_link_token(
            firm_id=firm_id,
            kit_id=body.kit_id,
            employee_id=employee_id,
            open_window_s=open_window_s,
            complete_window_s=complete_window_s,
            now=issued,
            jti=jti,
            cap_usd=cap_usd,
        )
    except LinkTokenError as exc:
        # The only expected cause is a missing signing secret -- a deployment
        # fault, not a caller error. The reservation has already committed:
        # the firm has been debited for a link whose token was never handed
        # out. That is the SAFE direction of the two (the alternative order
        # gives away free sessions) and it is recoverable -- the record is
        # `minted` and unopened, so A5's expiry sweep refunds it at its open
        # deadline with no operator action. Logged loudly so it is visible
        # before then.
        _log.error("link_mint_failed_after_reserve", firm_id=firm_id,
                   jti=jti, error=str(exc))
        raise HTTPException(status_code=503,
                            detail="Link minting is not configured") from exc

    payload = verify_link_token(token)
    # BILLING METER (bd polyglot-pdf-ik7e). Counted at MINT, because the
    # redemption record is only created when a CLIENT OPENS a link -- so
    # counting documents would miss every minted-but-unopened link, which is
    # exactly the set a firm has been billed for.
    #
    # DELIBERATELY NOT A GATE. The allowance is a subscription tier
    # ($500/mo for 30, then $15 each), not an abuse limit: a firm minting
    # link 31 has PAID for link 31, and refusing it would break a paying
    # customer over a number the maintainer has explicitly called provisional
    # pending market research. Margin is protected by the per-LINK spend
    # ceiling instead. record_mint never raises and never refuses.
    usage = record_mint(firm_id)

    # AUDIT, keyed like the rest of the firm tier (bd xwlt): who minted what,
    # for which form. The jti is OUR pseudonym, never a client identifier.
    # `credit_cost`, `balance_after` and `commercial_source` are here so an
    # operator can see from one line what a mint cost, what it left, and
    # whether the form is actually priced or riding kit_commercials'
    # default. No PII, no field values -- ids and counts only.
    _log.info("link_minted", firm_id=firm_id, kit_id=body.kit_id,
              employee_id=employee_id, jti=signed_jti,
              credit_cost=credit_cost, cap_usd=cap_usd,
              commercial_source=commercial["source"],
              balance_after=reservation["balance_after"],
              credits_enforced=enforced, channel=channel,
              period=usage["period"], minted_this_period=usage["minted"],
              over_allowance=usage["over_allowance"])

    # The token rides in the FRAGMENT (#t=), which browsers do not send to
    # servers -- so it stays out of access logs, referrers, and proxy logs.
    # signed_jti, not the local `jti`: they are the same string by
    # construction (mint_link_token was handed `jti=jti`), and returning the
    # one the TOKEN actually carries means a future change to that
    # parameter's handling cannot silently hand the firm a join key their
    # client's link does not use.
    return MintLinkResponse(
        url=_link_base_url() + "/f#t=" + token,
        jti=signed_jti,
        expires_at=payload["exp"],
    )


@router.post("/open", response_model=OpenLinkResponse)
async def open_client_link(body: OpenLinkRequest) -> OpenLinkResponse:
    """Redeem a client link. UNAUTHENTICATED by design -- the token is the
    credential.

    EVERY failure returns the SAME 404. A bad signature, an expired window, a
    replayed link, a suspended firm, a kit the firm no longer holds, and (bd
    polyglot-pdf-jecrl) a link with no mint record or a revoked one must be
    indistinguishable, or the differences become an oracle for probing which
    links and firms exist. The specific cause is logged, never returned.
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

    # THE SHARED GATE (bd polyglot-pdf-ugm6, Opus cross-surface r2). This
    # route used to hand-roll the same sequence the socket and require_auth
    # run -- redeem, validate the stored open time, check the completion
    # window -- and the copies HAD ALREADY DRIFTED: the helper refuses a
    # credential whose completion window is unusable, this copy would have
    # computed a deadline from whatever `cw` held. Not exploitable (the mint
    # route bounds it and the verifier type-checks it), but drift-in-waiting
    # is exactly what the extraction was for, and the docs claimed one helper
    # served every door while two copies existed.
    #
    # The helper reads `link_kit_id`; the token payload spells it `kit_id`.
    # Normalize rather than teaching the helper two spellings.
    gate_claims = {**payload, "link_kit_id": kit_id}
    try:
        record = await asyncio.to_thread(enforce_link_redemption, gate_claims)
    except LinkAlreadyUsed as exc:
        _log.info("link_open_refused", reason="already completed",
                  jti=payload["jti"])
        raise generic from exc
    except LinkWindowElapsed as exc:
        _log.info("link_open_refused", reason="completion window elapsed",
                  jti=payload["jti"])
        raise generic from exc
    except LinkNotMinted as exc:
        # NO MINT RECORD, or one that is revoked/refunded (bd
        # polyglot-pdf-jecrl). Caught BEFORE RedemptionUnavailable because it
        # is a SUBCLASS of it -- an except-clause order swap would swallow
        # this branch into the store-outage branch and mislabel every
        # cutover-era token as an outage. Same generic 404 either way; only
        # the log line differs.
        _log.info("link_open_refused", reason="no usable mint record",
                  jti=payload["jti"])
        raise generic from exc
    except RedemptionUnavailable as exc:
        # FAIL CLOSED: unable to confirm the link is unredeemed means we must
        # not admit it -- the failure being guarded is a replayed link
        # starting a second paid session.
        _log.error("link_open_unavailable", jti=payload["jti"], error=str(exc))
        raise generic from exc

    deadline = completion_deadline(payload, record["opened_at"])

    # BEST-EFFORT MIRROR (bd polyglot-pdf-jecrl): stamp the mint record
    # `opened` for the console's link listing. Deliberately AFTER the gate
    # and deliberately incapable of failing the request -- links_store's
    # mark_opened() never raises, and the authoritative "was this opened"
    # answer is the redemption doc the gate just wrote, not this cache. A
    # failed mirror must never turn a successful client open into a refusal,
    # and (A5) must never cause a refund of a link someone is filling: the
    # refund transaction reads the redemption doc, not this field.
    await asyncio.to_thread(links_store.mark_opened, payload["jti"])

    _log.info("link_opened_ok", firm_id=firm_id, kit_id=kit_id,
              jti=payload["jti"], employee_id=payload["employee_id"])
    return OpenLinkResponse(
        kit_id=kit_id, firm_id=firm_id, jti=payload["jti"],
        complete_by=deadline,
    )
