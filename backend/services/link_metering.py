"""Per-firm monthly link METERING (bd polyglot-pdf-ik7e).

THIS IS BILLING, NOT ABUSE PREVENTION, and the distinction decides the
behavior. Maintainer, 2026-08-27: "it's going to fit into an example possible
tiered subscription model, $500/mo for 30 links. Then $15 per link after.
That's why the $10 cap. But, those need market research before being finalized.
It's just so we have something in place. We might offer other tiers, or pay as
you go, too."

SO EXCEEDING THE ALLOWANCE MUST NOT REFUSE THE MINT. A firm minting link 31 has
paid for link 31 -- refusing it would break a paying customer to enforce a
number that is explicitly provisional. This module COUNTS and REPORTS; it does
not gate. The thing that actually protects margin is the per-link SPEND ceiling
(link_budget/link_spend), which bounds what any one link can cost.

The counter is per-FIRM per-CALENDAR-MONTH, because the subscription is
monthly. A month bucket also means a miscount self-heals at the month
boundary rather than accumulating forever.

WHY A COUNTER AND NOT A QUERY. The redemption record is created when a client
OPENS a link, not when staff mint one, so counting documents would miss every
minted-but-unopened link -- exactly the ones a firm has been billed for. The
count must be incremented at MINT time, which is what this does.

PROVISIONAL BY DESIGN. Tiers, prices and the allowance itself are pre-market-
research placeholders. Everything here is therefore tunable at call time
(LINK_FIRM_CAP) and stored per-firm, so a later tier model -- different
allowances per firm, pay-as-you-go with no allowance at all -- changes a stored
number rather than this code.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog

from backend.services.link_budget import firm_link_cap

_log = structlog.get_logger(__name__)

_FIRMS_COLLECTION = "firms"

# Sub-collection on a firm holding one document per billing month.
_USAGE_SUBCOLLECTION = "link_usage"

MINTED_FIELD = "minted"


def billing_period(now: Optional[float] = None) -> str:
    """The current billing bucket, as YYYY-MM.

    UTC deliberately: a firm's month boundary must not move with the server's
    local timezone, and a bucket that shifts is a bucket that double-counts.
    """
    stamp = time.gmtime(now if now is not None else time.time())
    return f"{stamp.tm_year:04d}-{stamp.tm_mon:02d}"


def _usage_doc(firm_id: str, period: str):
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise RuntimeError("no firestore client")
    return (
        db.collection(_FIRMS_COLLECTION)
        .document(firm_id)
        .collection(_USAGE_SUBCOLLECTION)
        .document(period)
    )


def links_minted_this_period(firm_id: str, now: Optional[float] = None) -> int:
    """How many links this firm has minted in the current billing month.

    Returns 0 rather than raising when the count cannot be read: this is a
    REPORTING number, and failing to read it must never block a mint. A missed
    count costs an invoice line; a refused mint costs the client their form.
    """
    if not firm_id:
        return 0
    try:
        snap = _usage_doc(firm_id, billing_period(now)).get()
    except Exception as exc:  # noqa: BLE001 -- reporting must not break minting
        _log.warning("link_usage_read_failed", firm_id=firm_id, error=str(exc))
        return 0
    if not snap.exists:
        return 0
    rec = snap.to_dict() or {}
    raw = rec.get(MINTED_FIELD)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return 0
    return raw if raw > 0 else 0


def record_mint(firm_id: str, now: Optional[float] = None) -> dict[str, Any]:
    """Count one minted link, and report where the firm now stands.

    NEVER RAISES and never refuses. Returns a dict describing the firm's
    position for logging and, later, the console:
        {"period", "minted", "allowance", "over_allowance"}

    `over_allowance` is the billable-overage signal (the "$15 per link after"
    half of the model), not a refusal.
    """
    period = billing_period(now)
    allowance = firm_link_cap()
    minted = 0
    try:
        from firebase_admin import firestore

        ref = _usage_doc(firm_id, period)
        ref.set(
            {
                MINTED_FIELD: firestore.Increment(1),
                "updated_at": int(now if now is not None else time.time()),
            },
            merge=True,   # the month's first mint creates the document
        )
        snap = ref.get()
        rec = (snap.to_dict() or {}) if snap.exists else {}
        raw = rec.get(MINTED_FIELD)
        minted = raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
    except Exception as exc:  # noqa: BLE001 -- billing must not break minting
        _log.warning("link_usage_write_failed", firm_id=firm_id, error=str(exc))

    over = minted > allowance if minted else False
    if over:
        # An operational signal, not a refusal: this is the billable overage.
        _log.info(
            "firm_over_link_allowance",
            firm_id=firm_id,
            period=period,
            minted=minted,
            allowance=allowance,
        )
    return {
        "period": period,
        "minted": minted,
        "allowance": allowance,
        "over_allowance": over,
    }
