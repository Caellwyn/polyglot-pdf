"""One-time-use bookkeeping for client magic links (bd polyglot-pdf-ugm6).

The maintainer's requirement (2026-08-17): a client link is good for ONE
specific form and ONE completion, with ~48h to open and ~24h to complete
after opening. "One time" cannot live in the token -- a signed bearer string
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


class RedemptionUnavailable(Exception):
    """The store could not be reached or read. Callers MUST refuse the open."""


class LinkAlreadyUsed(Exception):
    """The link was already completed. Callers refuse, indistinguishably."""


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
