"""The mint record: links[_<channel>]/{jti} (Epic 2 bead A1, epic
polyglot-pdf-e374w).

WHAT THIS IS, AND WHY IT IS NOT link_redemptions.py. link_redemptions.py
answers "has this link been opened/completed yet" -- the load-bearing
one-time-use invariant, written on the client's FIRST open. This module
answers a different question: "was this link ever legitimately minted, by
whom, for how much, and is it still good to open" -- written at MINT time,
by staff, before any client ever sees the link. Kept as a SEPARATE
collection on purpose (plan: "Kept SEPARATE from link_redemptions so the
load-bearing 'no redemption doc until first open' invariant is untouched"):
folding mint bookkeeping into the redemption collection would mean a doc
exists before the client's first open, which is precisely the state
link_redemptions.py's callers currently treat as proof of a real open.

STATUS IS A DERIVED CACHE, NEVER THE MONEY DECISION. `status` exists for
listing (the admin console's link table, a firm manager's dashboard) and is
a best-effort mirror written from several places: the mint route sets
`minted`, the open route/socket best-effort-mirrors `opened`,
complete_link's caller best-effort-mirrors `completed`, the sweep writes
`refunded`, a revoke route writes `revoked`, socket teardown on a spend-cap
trip writes `budget_exhausted` (telemetry only, no ledger entry -- pending a
maintainer pricing call, see the plan). ANY transaction that moves real
credits (the mint debit, the expiry refund) reads the AUTHORITATIVE record
directly -- the mint transaction and refund transaction, both landing in
Epic 2 bead A2/A5, not this bead -- and never trusts this field alone. This
bead writes ONLY the mint-time record (status=minted); every other writer
listed above belongs to a later bead.

CHANNEL IS AN EXPLICIT ARGUMENT, exactly like link_redemptions.py's
_collection_name() (bd polyglot-pdf-3q9qn precedent, generalized here by
this bead): the public backend passes
backend.services.link_tokens.link_channel(), the admin service passes
whichever channel it is acting on (it sets no LINK_CHANNEL of its own). No
function in this module reads the environment for a channel; every public
function takes one.

WHY THIS IS ADMIN-SDK-ONLY. Like firms.py and link_redemptions.py, nothing
here is reachable from a browser -- firestore.rules carries an explicit
client deny block for every links[_<channel>] collection as defense in
depth, pinned by the set-derived test
(backend/tests/unit/test_firestore_rules_text.py, bd polyglot-pdf-li9x0).

SCHEMA ONLY IN THIS BEAD. record_mint() below performs a single
non-transactional Firestore set(): the ATOMIC "reserve credit + write ledger
entry + write this record" transaction is Epic 2 bead A2/A3's
backend/services/credit_ledger.py, not this module. Nothing here is wired
into a route yet -- that is A3 (mint_link route rewrite) and A5 (refund /
revoke). This bead lays the collection, its document shape, and the reader/
writer functions the later beads compose.

DOC SHAPE (links[_<channel>]/{jti}):
    firm_id: str            kit_id: str             employee_id: str
    credit_cost: int         (snapshot at mint time)
    cap_usd: float            (snapshot at mint time -- the resolved
                               burn_cap_usd, closes bd polyglot-pdf-4tjt7)
    minted_at: int            (unix seconds)
    open_deadline: int        (unix seconds; == the token's `exp`, stored
                               separately so the sweep can query Firestore
                               without decoding a token)
    status: one of STATUS_MINTED | STATUS_OPENED | STATUS_COMPLETED |
            STATUS_REFUNDED | STATUS_REVOKED | STATUS_BUDGET_EXHAUSTED
    revoked_by: str | None    revoked_at: int | None
    expire_at:                a datetime for the Firestore TTL policy
                               (scripts/setup-firestore-ttl.sh), set to
                               open_deadline plus a retention margin so the
                               admin console has time to show link history
                               before Firestore reaps the doc.

ASCII only.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

_log = structlog.get_logger().bind(module="links_store")

COLLECTION = "links"

STATUS_MINTED = "minted"
STATUS_OPENED = "opened"
STATUS_COMPLETED = "completed"
STATUS_REFUNDED = "refunded"
STATUS_REVOKED = "revoked"
STATUS_BUDGET_EXHAUSTED = "budget_exhausted"

ALL_STATUSES = (
    STATUS_MINTED,
    STATUS_OPENED,
    STATUS_COMPLETED,
    STATUS_REFUNDED,
    STATUS_REVOKED,
    STATUS_BUDGET_EXHAUSTED,
)

# The mint record's TTL retention margin: how much LONGER than the open
# deadline a record is kept before Firestore's TTL policy reaps it. Wide
# enough that a firm manager or the admin console can still show recent link
# history (the plan: "the admin console reads history from BigQuery beyond
# that") well after a link's open window has closed. Not the completion
# window (7 days, link_tokens.DEFAULT_COMPLETE_WINDOW_S) -- deliberately
# longer than that too, so a completed-but-recent link's record survives
# long enough to be useful in the console before it ages out.
_TTL_RETENTION_MARGIN_S = 30 * 24 * 3600  # 30 days


class LinksStoreUnavailable(Exception):
    """The store could not be reached. Callers must not assume any status."""


def _collection_name(channel: str) -> str:
    """The mint-record collection for the GIVEN channel.

    Mirrors link_redemptions._collection_name() exactly (same channel-
    suffix convention, same "demo keeps the bare name" rule) -- a link and
    its redemption record live in different collections but under the SAME
    channel-isolation scheme, so an operator reasoning about one already
    knows the other.
    """
    from backend.services.link_tokens import DEFAULT_CHANNEL

    return COLLECTION if channel == DEFAULT_CHANNEL else f"{COLLECTION}_{channel}"


def _collection(channel: Optional[str] = None):
    """The mint-record collection for `channel`, defaulting to THIS
    process's own channel (link_channel()) -- same default-resolution
    contract as link_redemptions._collection().
    """
    from backend.services.auth import get_db
    from backend.services.link_tokens import link_channel

    db = get_db()
    if db is None:
        raise LinksStoreUnavailable("no firestore client")
    return db.collection(_collection_name(channel or link_channel()))


def expire_at_for(open_deadline: int) -> datetime:
    """The TTL field value for a mint record with the given open_deadline
    (unix seconds): the deadline plus the retention margin, as a
    timezone-aware UTC datetime (the shape Firestore's TTL policy and the
    Admin SDK expect).
    """
    return (
        datetime.fromtimestamp(open_deadline, tz=timezone.utc)
        + timedelta(seconds=_TTL_RETENTION_MARGIN_S)
    )


def record_mint(
    jti: str,
    firm_id: str,
    kit_id: str,
    employee_id: str,
    credit_cost: int,
    cap_usd: float,
    open_deadline: int,
    now: Optional[float] = None,
    channel: Optional[str] = None,
) -> dict:
    """Write the mint record for a freshly-minted link. Returns the record.

    NON-TRANSACTIONAL in this bead: the atomic "debit credit + ledger entry
    + this record" transaction is Epic 2 bead A2/A3's
    backend/services/credit_ledger.py. This function is the plain write the
    later transaction will call (or a caller drives directly, e.g. a test or
    a migration backfill) -- it does not itself reserve a credit or touch
    firms/{firm_id}.balance_credits.

    Raises LinksStoreUnavailable when the store cannot be reached; raises
    ValueError for a non-positive credit_cost or cap_usd (a link that costs
    nothing or has no spend ceiling is a configuration bug, not a valid
    mint) -- callers must not silently record a broken snapshot.
    """
    if not all(isinstance(v, str) and v for v in (jti, firm_id, kit_id, employee_id)):
        raise ValueError("jti, firm_id, kit_id and employee_id are required")
    if not isinstance(credit_cost, int) or isinstance(credit_cost, bool) or credit_cost <= 0:
        raise ValueError(f"credit_cost must be a positive int, got {credit_cost!r}")
    if not isinstance(cap_usd, (int, float)) or isinstance(cap_usd, bool) or cap_usd <= 0:
        raise ValueError(f"cap_usd must be a positive number, got {cap_usd!r}")

    stamp = int(now if now is not None else time.time())
    record = {
        "jti": jti,
        "firm_id": firm_id,
        "kit_id": kit_id,
        "employee_id": employee_id,
        "credit_cost": credit_cost,
        "cap_usd": float(cap_usd),
        "minted_at": stamp,
        "open_deadline": int(open_deadline),
        "status": STATUS_MINTED,
        "revoked_by": None,
        "revoked_at": None,
        "expire_at": expire_at_for(int(open_deadline)),
    }
    try:
        _collection(channel).document(jti).set(record)
    except LinksStoreUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 -- any store failure is unavailable
        _log.error("links_store_write_failed", jti=jti, error=str(exc))
        raise LinksStoreUnavailable(str(exc)) from exc
    _log.info(
        "link_minted",
        jti=jti,
        firm_id=firm_id,
        kit_id=kit_id,
        employee_id=employee_id,
        credit_cost=credit_cost,
        cap_usd=cap_usd,
        channel=channel,
    )
    return record


def get_link(jti: str, channel: Optional[str] = None) -> Optional[dict]:
    """Return the mint record for `jti`, or None if it does not exist.

    FAIL-CLOSED FOR THE OPEN GATE: this function itself returns None on a
    missing doc (that is a legitimate "no such link" answer, not a store
    failure) but RAISES LinksStoreUnavailable on an unreachable store -- a
    caller gating "may this link open" (Epic 2 bead A3's open-requires-a-
    mint-record check) must not treat a store outage as "no record, refuse"
    silently conflated with "genuinely never minted, refuse": both refuse,
    but the raise lets the caller log which one happened.
    """
    try:
        snap = _collection(channel).document(jti).get()
    except LinksStoreUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        _log.error("links_store_read_failed", jti=jti, error=str(exc))
        raise LinksStoreUnavailable(str(exc)) from exc
    if not snap.exists:
        return None
    return snap.to_dict() or {}


def links_store_status(channel: Optional[str] = None) -> str:
    """Report whether the links store can actually be READ.

    Same probe shape as firms.firms_store_status() and the confirmation
    sink's status probe: READ-shaped (limit-1 stream), never write+delete,
    because this path never needs write permission and probing with a write
    would test the wrong grant. Returns "ok" or "error: <msg>" -- unlike
    firms_store_status() this store has no enable/disable env gate (it is
    Admin-SDK-only by rules, not by a feature flag), so there is no
    "disabled" branch.
    """
    try:
        list(_collection(channel).limit(1).stream())
        return "ok"
    except Exception as e:
        _log.error("links_store_probe_failed", error=str(e))
        return f"error: {e}"
