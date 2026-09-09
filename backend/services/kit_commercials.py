"""The kit COMMERCIAL doc: kits/{kit_id} (Epic 2 bead A3, epic
polyglot-pdf-e374w).

WHAT THIS IS NOT. It is not the kit's SCHEMA and it is not its
`metadata.json` -- both of those live in the form-kits GCS bucket and are
owned by the schema editor (backend/routes/editor_kit_routes.py,
backend/services/form_kits.py). This module reads a small FIRESTORE doc
carrying only what the money path needs: what a link on this form costs in
credits, and how many dollars of AI spend one such link may buy. Kept out of
the bucket on purpose -- pricing is edited from the admin console (Epic 2
Track B's PUT /admin/kits/{kit_id}/commercial), by a different role, on a
different cadence, and must not require republishing a form.

FAIL-SOFT BY DESIGN, IN ONE DIRECTION ONLY. A missing doc, an unreachable
store, or a malformed value resolves to the GLOBAL defaults -- never to
"free" and never to "no ceiling". This is the same defensive-parsing rule
backend/services/link_budget.py already applies to a per-kit ceiling ("a
typo in one kit's metadata must not remove that form's ceiling"), and it is
the reason the two numbers resolve through DIFFERENT paths:

  burn_cap_usd -> link_budget.cost_ceiling_usd_for_kit(), so a bad value
                  falls back to the same global ceiling a bad METADATA value
                  falls back to. One parsing rule for "a spend ceiling read
                  from outside link_budget", not two that could drift.
  credit_cost  -> DEFAULT_CREDIT_COST below, because there is no global
                  runtime-config key for it and no pricing signal exists to
                  derive one (the plan: the migration script takes a REQUIRED
                  --default-credit-cost). A kit with no commercial doc costs
                  the default rather than nothing: a mis-priced mint that
                  charges a credit is recoverable with an `adjustment` ledger
                  entry, while a mint that charges ZERO is invisible revenue
                  loss that nothing later reconciles.

WHY AN UNREACHABLE STORE DOES NOT REFUSE THE MINT. The firm doc read that
sits beside this one is inside the mint TRANSACTION and its failure aborts
the whole thing (no debit, no record, no token). This read is deliberately
outside that transaction and deliberately soft: the numbers it produces are
a price and a ceiling, both of which have safe defaults, and refusing every
mint in the demo because one pricing doc was slow would trade a real outage
for a rounding error. The invariant that must never break -- "a signed token
always has a debit and a record behind it" -- is enforced by the
transaction, not by this read.

ADMIN-SDK-ONLY: firestore.rules carries a client deny block for `kits`,
pinned by the set-derived rules test
(backend/tests/unit/test_firestore_rules_text.py).

DOC SHAPE (kits/{kit_id}):
    credit_cost: int      how many credits minting a link on this form costs
    burn_cap_usd: float   the per-link USD spend ceiling signed into the
                          token as `cap_usd` (bd polyglot-pdf-4tjt7)
    display: dict         console label etc.; not read here
    updated_by: str       updated_at: number

ASCII only.
"""
from __future__ import annotations

from typing import Any, Optional

import structlog

_log = structlog.get_logger().bind(module="kit_commercials")

COLLECTION = "kits"

CREDIT_COST_KEY = "credit_cost"
BURN_CAP_USD_KEY = "burn_cap_usd"

# What a link costs when the kit has no commercial doc, or an unusable one.
# ONE credit, because that is the unit the ledger is denominated in and the
# smallest charge that still records the mint as having cost something. The
# per-kit doc is how a form gets a different price; this is only the floor
# under a kit nobody has priced yet.
DEFAULT_CREDIT_COST = 1


def _positive_int(raw: Any, fallback: int) -> int:
    """Parse a positive int, falling back on anything unusable.

    Mirrors link_budget._positive_int's polarity for the identical reason: a
    malformed price must resolve to the default, not to zero. A stored 0 read
    literally would mean "this form is free", but as a bad edit it far more
    likely means "unset", and guessing wrong in that direction gives away
    paid sessions silently. bool is excluded explicitly (bool is an int
    subclass, so a stray true would otherwise price a form at 1 credit by
    accident rather than by the default rule).
    """
    if isinstance(raw, bool):
        return fallback
    if isinstance(raw, int):
        return raw if raw > 0 else fallback
    if isinstance(raw, float):
        # A fractional price is a bad edit, not a valid one -- credits are
        # whole. 2.0 is accepted as 2 (an admin UI posting JSON numbers may
        # send one); 2.5 is not a number of credits and falls back.
        if raw != raw or raw in (float("inf"), float("-inf")):
            return fallback
        if raw > 0 and float(raw).is_integer():
            return int(raw)
        return fallback
    if isinstance(raw, str):
        try:
            value = int(raw.strip())
        except (TypeError, ValueError):
            return fallback
        return value if value > 0 else fallback
    return fallback


def read_commercial(kit_id: str) -> Optional[dict]:
    """The raw commercial doc for `kit_id`, or None when there is none.

    Returns None for BOTH "no such doc" and "the store could not be read" --
    the caller's next step is identical in either case (fall back to the
    defaults), and the store failure is logged here so the distinction is
    not lost. Never raises: see the module docstring on why this read is
    soft while the mint transaction's firm read is not.
    """
    if not isinstance(kit_id, str) or not kit_id:
        return None
    try:
        from backend.services.auth import get_db

        db = get_db()
        if db is None:
            return None
        snap = db.collection(COLLECTION).document(kit_id).get()
    except Exception as exc:  # noqa: BLE001 -- any failure is "no doc"
        _log.error("kit_commercial_read_failed", kit_id=kit_id, error=str(exc))
        return None
    if not snap.exists:
        return None
    return snap.to_dict() or {}


def resolve_commercial(kit_id: str) -> dict:
    """The credit price and USD ceiling for a link on this form.

    Returns {"credit_cost": int, "cap_usd": float, "source": str}. `source`
    is "kit" when a commercial doc was found and "default" when it was not
    -- for the mint log line, so an operator can see at a glance whether a
    form is priced or riding the fallback.

    SYNC (Admin SDK). Async callers must wrap this in asyncio.to_thread, as
    backend/routes/link_routes.py does for every other Firestore read.

    Both numbers are resolved ONCE, here, at mint: `cap_usd` is then signed
    into the token (bd polyglot-pdf-ah5d3) and `credit_cost` is snapshotted
    onto the links/{jti} record, so neither a later pricing edit nor a slow
    Firestore can change what an already-minted link costs or may spend.
    """
    from backend.services.link_budget import (
        KIT_COST_CEILING_KEY,
        cost_ceiling_usd_for_kit,
    )

    doc = read_commercial(kit_id)
    credit_cost = _positive_int(
        (doc or {}).get(CREDIT_COST_KEY), DEFAULT_CREDIT_COST
    )
    # cost_ceiling_usd_for_kit reads its OWN key name, so hand it a dict
    # spelled the way it expects rather than teaching it a second spelling
    # (the same normalize-at-the-boundary move link_routes makes for
    # `link_kit_id`). A missing, None or malformed burn_cap_usd therefore
    # lands on the SAME global fallback a malformed metadata value gets.
    raw_cap = (doc or {}).get(BURN_CAP_USD_KEY)
    cap_usd = cost_ceiling_usd_for_kit({KIT_COST_CEILING_KEY: raw_cap})
    return {
        "credit_cost": credit_cost,
        "cap_usd": float(cap_usd),
        "source": "kit" if doc is not None else "default",
    }
