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

ASCII only.
"""
import os
import time
from typing import Optional

import structlog

_log = structlog.get_logger().bind(module="link_redemptions")

COLLECTION = "link_redemptions"

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


class LinkAlreadyUsed(Exception):
    """The link was already completed. Callers refuse, indistinguishably."""


class LinkWindowElapsed(Exception):
    """The completion window closed. Callers refuse, indistinguishably."""


def _enabled() -> bool:
    return os.getenv(_ENABLED_ENV, "false").lower() == "true"


def _collection():
    # Imported lazily: module import must not require firebase_admin to be
    # initialized (the test suite and local dev import this module freely).
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise RedemptionUnavailable("no firestore client")
    return db.collection(COLLECTION)


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
        return rec
    except (LinkAlreadyUsed, RedemptionUnavailable):
        raise
    except Exception as exc:  # noqa: BLE001 -- any store failure refuses
        _log.error("link_open_failed", jti=jti, error=str(exc))
        raise RedemptionUnavailable(str(exc)) from exc


def complete_link(jti: str, now: Optional[float] = None) -> None:
    """Mark a link finished. Best-effort: a failure here must not destroy the
    client's completed work, so it logs loudly and returns.

    The asymmetry with open_link is deliberate. Failing to RECORD a
    completion costs at most one extra reopen of a form the client already
    finished; failing to BLOCK an open costs a second paid session. Refuse
    the risky direction, absorb the cheap one.
    """
    try:
        _collection().document(jti).update(
            {"completed_at": int(now if now is not None else time.time())}
        )
        _log.info("link_completed", jti=jti)
    except Exception as exc:  # noqa: BLE001
        _log.error("link_complete_failed", jti=jti, error=str(exc))


def enforce_link_redemption(claims: dict, now: Optional[float] = None) -> dict:
    """THE ONE redemption gate, called by EVERY door a client credential opens.

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

    Extracted rather than duplicated ON PURPOSE: two hand-written copies of a
    security check drift, and the drift is silent. Callers pass the claims
    dict from verify_link_token / require_auth and get the redemption record
    back; anything else raises.

    Raises LinkAlreadyUsed, RedemptionUnavailable (unreachable store -- fail
    closed), or LinkWindowElapsed.
    """
    stamp = int(now if now is not None else time.time())
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
