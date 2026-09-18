"""One-time-use bookkeeping for client magic links (bd polyglot-pdf-ugm6).

The maintainer's requirement (2026-08-17, window widened 2026-08-24): a
client link is good for ONE specific form and ONE completion, with ~48h to
open and SEVEN DAYS to complete after opening. The bound is on FINISHING --
reopening an unfinished form across that week is intended, so a client who
loses their work returns to the original message rather than phoning the
firm. "One time" cannot live in the token -- a signed bearer string
is inherently replayable -- so redemption state is the only place it can be
enforced.

WHY THIS DOES NOT BREAK THE STATELESS RULE: that rule
(docs/standards/stateless-architecture.md) forbids server-side FIELD VALUES,
PII, and PHI -- the client owns form state. A redemption record holds a
`jti`, a firm id, a kit id, and timestamps: no field values, and by the
no-client-identifier invariant (see link_tokens.py) nothing identifying the
person. The sibling rate-limit bead (polyglot-pdf-ik7e) already sanctions
Firestore counters on the same reasoning.

FAIL-CLOSED, and note this is the OPPOSITE polarity from the firm-allowlist
read (services/firms.py), which fails closed by returning an EMPTY list. Here
"closed" means REFUSING THE OPEN: if we cannot confirm a link is unredeemed,
we must not let it through, because the failure we are guarding against is a
replayed link starting a second paid session.

OPEN NOW REQUIRES A MINT RECORD (Epic 2 bead A3). Before any of the
redemption bookkeeping below runs, enforce_link_redemption() reads
links[_<channel>]/{jti} (services/links_store.py) and refuses a token with
NO record, or one whose status is `revoked` or `refunded`. That is the other
half of the mint route's reserve-before-sign order: a signed token exists
only because a credit was reserved for it, and this gate is what makes that
true from the client's side too -- a forged-but-somehow-valid token, or a
token whose link an operator has since revoked, cannot buy a session.

CONSEQUENCE, DELIBERATE: a token minted BEFORE the mint record existed
cannot open. There are few or no live client links today, the same reasoning
the `aud`-claim cutover used, and the maintainer re-mints any outstanding
link at cutover (plan: docs/sprint_22_admin-console_plan.md, maintainer
calls).

ASCII only.
"""
import os
import time
from typing import Optional

import structlog

_log = structlog.get_logger(module="link_redemptions")

COLLECTION = "link_redemptions"


def _collection_name(channel: str) -> str:
    """The redemption collection for the GIVEN channel.

    `channel` is an EXPLICIT argument (Epic 2 bead A1), not read from the
    environment here: the admin service acts on a channel it names itself (a
    sweep request, a firm-console read) and sets no LINK_CHANNEL env var of
    its own, so an env-reading version of this helper would silently resolve
    to the wrong (or default) channel for every admin-service caller. The
    PUBLIC backend's one caller, `_collection()` below, passes
    `link_channel()` explicitly -- this function itself makes no assumption
    about which process is calling it.

    The demo keeps the bare `link_redemptions` name so nothing already written
    there is orphaned; every other channel gets its own suffixed collection
    (bd polyglot-pdf-3q9qn).

    WHY THIS MATTERS SEPARATELY FROM THE TOKEN CLAIM: a link is single-use, and
    the burn is recorded under the jti alone. Two channels sharing one
    collection means a staging test-drive marks a DEMO link used -- the client
    then finds a dead link with no explanation. The `aud` claim stops a staging
    link OPENING on the demo; this stops the two channels writing over each
    other's ledger.
    """
    from backend.services.link_tokens import DEFAULT_CHANNEL

    return COLLECTION if channel == DEFAULT_CHANNEL else f"{COLLECTION}_{channel}"

# Same env-gate shape as the firms store (services/firms.py): off by default,
# so a deployment that has not provisioned Firestore does not silently treat
# every link as fresh.
_ENABLED_ENV = "LINK_REDEMPTIONS_FIRESTORE_ENABLED"

# WHAT THE BURN ACTUALLY BOUNDS: a new BACKEND CONNECTION -- i.e. a new paid
# Gemini session. Not saving, not printing, not previewing (maintainer,
# 2026-08-24: "There's not really any reason to have a time limit on saving
# or printing. That's all client side. The TTL should be backend
# connection.").
#
# The distinction the callers draw, and why one-time use is unaffected:
#
#   PAID work -- /ws/fill (a Gemini session) and the two TTS routes
#   (synthesis) -- redeems. A completed link cannot start another.
#
#   RETRIEVING YOUR OWN WORK -- /api/fill-pdf (a pure PyMuPDF render, no
#   model call), the schema/manifest/PDF reads -- does NOT redeem. It still
#   requires a VALID SIGNED link inside its open window, scoped to that
#   link's one kit, so nothing is opened up: the same person, the same form,
#   no model spend.
#
# This replaces a 30-minute grace window I added first (Opus r11 found that a
# finished form was undownloadable). That was a band-aid on the wrong
# boundary: it put a clock on the client's own document, when the thing worth
# bounding was never the download.



class RedemptionUnavailable(Exception):
    """The store could not be reached or read. Callers MUST refuse the open."""


class LinkNotMinted(RedemptionUnavailable):
    """No usable mint record backs this link (Epic 2 bead A3).

    Raised when links[_<channel>]/{jti} is missing, or its status is
    `revoked` or `refunded`.

    A SUBCLASS OF RedemptionUnavailable ON PURPOSE, belt and braces. Every
    door that spends already catches RedemptionUnavailable and fails closed
    on it -- /api/links/open, the WebSocket gate, and
    require_paid_client_work -- so a NEW exception type could not slip past
    one of them unhandled and turn a refusal into a 500 (or worse, into an
    admitted session). The three doors also name this class explicitly, so
    the refusal reads correctly in their logs; the subclassing is what makes
    a door someone adds LATER, catching only the base class, still safe.

    All three doors already return the SAME uniform 404/1008 refusal for
    every redemption failure, so this adds no new oracle: "never minted",
    "revoked", "already completed", and "store unreachable" remain
    indistinguishable from outside.
    """


class LinkAlreadyUsed(Exception):
    """The link was already completed. Callers refuse, indistinguishably."""


class LinkWindowElapsed(Exception):
    """The completion window closed. Callers refuse, indistinguishably."""


def _enabled() -> bool:
    return os.getenv(_ENABLED_ENV, "false").lower() == "true"


def _collection(channel: Optional[str] = None):
    """The redemption collection for `channel`, defaulting to THIS process's
    own channel (backend.services.link_tokens.link_channel()) -- the public
    backend never names a channel explicitly; it acts on its own. A caller
    that DOES know which channel it means (a future admin-service reconciler)
    passes one.
    """
    # Imported lazily: module import must not require firebase_admin to be
    # initialized (the test suite and local dev import this module freely).
    from backend.services.auth import get_db
    from backend.services.link_tokens import link_channel

    db = get_db()
    if db is None:
        raise RedemptionUnavailable("no firestore client")
    return db.collection(_collection_name(channel or link_channel()))


def open_link(jti: str, firm_id: str, kit_id: str,
              now: Optional[float] = None) -> dict:
    """Record (or re-confirm) the FIRST open of a link. Returns its record.

    Idempotent for the SAME link being re-opened inside its completion
    window: a client who refreshes the page, loses their connection, or comes
    back after lunch must not be locked out -- that would turn a network blip
    into "your link is dead, call the firm". What is refused is a link that
    was already COMPLETED, or one whose completion window has passed.

    Raises RedemptionUnavailable when the store cannot answer, and the caller
    must then refuse the open.
    """
    if not _enabled():
        # Deliberately NOT a silent pass. With minting disabled by default
        # this path is unreachable in a normal deployment; if it is reached,
        # it means links are live without the store that enforces one-time
        # use, which must fail loudly rather than admit every replay.
        raise RedemptionUnavailable(_ENABLED_ENV + " is not enabled")

    stamp = int(now if now is not None else time.time())
    try:
        doc_ref = _collection().document(jti)
        snap = doc_ref.get()
        if snap.exists:
            rec = snap.to_dict() or {}
            if rec.get("completed_at"):
                # A completed link starts no NEW paid session. The callers
                # that reach here are the paid ones -- the socket, the TTS
                # routes -- plus /api/links/open, which redeems because
                # opening IS the start of a session. Retrieval never calls
                # this, so the refusal costs the client nothing they own.
                raise LinkAlreadyUsed("link already completed")
            return rec
        rec = {
            "jti": jti,
            "firm_id": firm_id,
            "kit_id": kit_id,
            "opened_at": stamp,
            "completed_at": None,
        }
        doc_ref.set(rec)
        _log.info("link_opened", jti=jti, firm_id=firm_id, kit_id=kit_id)
        # Usage rollup (Epic 3 bead E3.4, bd polyglot-pdf-w828m): ONLY on the
        # genuine first open (this branch), never on the idempotent re-open
        # above (snap.exists) -- a client who refreshes mid-form must not
        # inflate links_opened on every reconnect. Best-effort by the
        # helper's own contract; no try/except needed here.
        from backend.services.usage_rollups import record_link_opened

        record_link_opened(firm_id, now=stamp)
        return rec
    except (LinkAlreadyUsed, RedemptionUnavailable):
        raise
    except Exception as exc:  # noqa: BLE001 -- any store failure refuses
        _log.error("link_open_failed", jti=jti, error_type=type(exc).__name__)
        raise RedemptionUnavailable(str(exc)) from exc


def complete_link(jti: str, now: Optional[float] = None) -> None:
    """Mark a link finished. Best-effort: a failure here must not destroy the
    client's completed work, so it logs loudly and returns.

    The asymmetry with open_link is deliberate. Failing to RECORD a
    completion costs at most one extra reopen of a form the client already
    finished; failing to BLOCK an open costs a second paid session. Refuse
    the risky direction, absorb the cheap one.
    """
    stamp = int(now if now is not None else time.time())
    try:
        doc_ref = _collection().document(jti)
        doc_ref.update({"completed_at": stamp})
        _log.info("link_completed", jti=jti)
        # Usage rollup (Epic 3 bead E3.4, bd polyglot-pdf-w828m). Reads the
        # firm_id back off the just-updated record rather than taking a new
        # parameter: complete_link's only caller (websocket_routes.py's
        # teardown) does not otherwise have a reason to thread firm_id
        # through this call, and the record already carries it from
        # open_link. Best-effort, so a read failure here degrades to "no
        # rollup counter", never to a failed completion (the completed_at
        # write above already succeeded).
        try:
            snap = doc_ref.get()
            rec = snap.to_dict() if snap.exists else None
            firm_id = rec.get("firm_id") if isinstance(rec, dict) else None
        except Exception:  # noqa: BLE001 -- best-effort read for telemetry only
            firm_id = None

        from backend.services.usage_rollups import record_link_completed

        record_link_completed(firm_id, now=stamp)
    except Exception as exc:  # noqa: BLE001
        _log.error("link_complete_failed", jti=jti, error_type=type(exc).__name__)


def _require_mint_record(jti) -> dict:
    """Refuse unless links[_<channel>]/{jti} says this link may open.

    Returns the mint record. Raises LinkNotMinted when there is no record at
    all, or when its status is one of links_store.OPEN_BLOCKING_STATUSES
    (`revoked` / `refunded`). Raises RedemptionUnavailable when the store
    cannot be read -- fail closed, the same polarity the rest of this module
    uses, because "cannot confirm a credit was reserved" must not admit a
    paid session.

    EVERY OTHER STATUS FALLS THROUGH. `opened` and `completed` are
    best-effort mirrors, and a link that is genuinely finished is refused by
    the redemption gate below on the AUTHORITATIVE record, not by this
    cache. Refusing on `opened` here would break the reopen-an-unfinished-
    link behaviour the seven-day completion window exists to provide.
    """
    from backend.services import links_store
    from backend.services.link_tokens import link_channel

    if not isinstance(jti, str) or not jti:
        # A claims dict with no jti cannot be looked up at all, and the
        # verifier type-checks the field -- so this is an internal caller
        # bug, refused rather than admitted.
        raise LinkNotMinted("no jti on the claims")
    try:
        record = links_store.get_link(jti, channel=link_channel())
    except links_store.LinksStoreUnavailable as exc:
        _log.error("link_mint_record_unavailable", jti=jti, error_type=type(exc).__name__)
        raise RedemptionUnavailable(str(exc)) from exc
    if record is None:
        # Either a token from before the cutover (the maintainer re-mints
        # those) or a token whose reservation never committed. Both refuse.
        _log.info("link_open_refused_no_mint_record", jti=jti)
        raise LinkNotMinted("no mint record for " + jti)
    status = record.get("status")
    if status in links_store.OPEN_BLOCKING_STATUSES:
        _log.info("link_open_refused_status", jti=jti, status=status)
        raise LinkNotMinted("mint record status " + repr(status))
    return record


def enforce_link_redemption(claims: dict, now: Optional[float] = None) -> dict:
    """THE ONE redemption gate, called by every door that can SPEND.

    bd polyglot-pdf-ugm6, Opus cross-surface r1. `verify_link_token` answers
    only "did we issue this, unmodified, and is it inside its OPEN window?"
    -- it deliberately knows nothing about one-time use, because that lives
    here. So a door that calls only the verifier accepts a link that was
    already COMPLETED, or whose completion window has elapsed, for the whole
    ~48h `exp`.

    That was the state of the HTTP surface: the socket redeemed, the
    require_auth routes did not, so a burned link kept serving schema, PDF
    bytes, fill-pdf, and the two PAID TTS routes until exp. The docs claimed
    one-time use was "enforced at BOTH doors" while the door this bead had
    just opened enforced neither check.

    THE FIX WAS THEN OVER-APPLIED, and the correction matters as much as the
    original hole: redeeming on RETRIEVAL made a finished client unable to
    download their own form (Opus r11; maintainer, 2026-08-24: "There's not
    really any reason to have a time limit on saving or printing. That's all
    client side. The TTL should be backend connection."). So this gate is
    called by the SPEND doors only -- /api/links/open, the WebSocket, and
    require_paid_client_work -- and NOT by require_auth or require_signin,
    which serve the client their own data.

    Extracted rather than duplicated ON PURPOSE: two hand-written copies of a
    security check drift, and the drift is silent. Callers pass the claims
    dict from verify_link_token / require_auth and get the redemption record
    back; anything else raises.

    Raises LinkNotMinted (no usable mint record), LinkAlreadyUsed,
    RedemptionUnavailable (unreachable store -- fail closed), or
    LinkWindowElapsed.
    """
    stamp = int(now if now is not None else time.time())

    # THE MINT-RECORD GATE (Epic 2 bead A3), and it runs FIRST -- before
    # open_link(), which CREATES the redemption doc. Order matters: checking
    # after the redemption write would stamp `opened_at` on a link we are
    # about to refuse, which for a revoked link burns the reopen window of a
    # replacement link sharing nothing but bad luck, and for a never-minted
    # token would leave a redemption record for a link that never existed.
    # Refuse before writing anything.
    _require_mint_record(claims.get("jti"))

    # Forward `now`: honoring it for the deadline math but not for the OPEN
    # would make the two halves disagree about what time it is -- the first
    # open would stamp wall-clock while the comparison used the injected
    # value. Harmless in production (both are time.time()) and quietly wrong
    # anywhere a caller controls the clock, which is exactly where a
    # window-expiry bug would be caught.
    record = open_link(claims["jti"], claims.get("firm_id"),
                       claims.get("link_kit_id"), now=stamp)

    # Validate the stored stamp rather than trusting it: a corrupt or missing
    # value computes a deadline in 1970 and locks out a client who just
    # opened their link, while a far-future one extends the window forever.
    opened_at = record.get("opened_at") if isinstance(record, dict) else None
    if (not isinstance(opened_at, int) or isinstance(opened_at, bool)
            or opened_at <= 0 or opened_at > stamp + 300):
        _log.warning("link_opened_at_implausible", jti=claims.get("jti"),
                     opened_at=repr(opened_at))
        opened_at = stamp

    window = claims.get("cw")
    if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
        # A credential with no usable completion window cannot be checked, so
        # it must not be admitted -- failing open here would restore exactly
        # the hole this function exists to close.
        raise LinkWindowElapsed("no usable completion window on the claims")
    if stamp >= opened_at + window:
        raise LinkWindowElapsed("completion window elapsed")

    # Return the record with a VALIDATED opened_at. Handing back the raw
    # record made every caller re-read the unvalidated stamp and re-derive
    # the fallback themselves -- which is how the deadline math and the
    # validation drifted apart in the first place. One value, already
    # checked, so a caller cannot accidentally use the bad one.
    return {**record, "opened_at": opened_at}
