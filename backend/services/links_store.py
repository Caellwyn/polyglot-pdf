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

WIRED INTO BOTH DOORS (Epic 2 bead A3). The MINT route reserves a credit
and writes this record in ONE transaction -- it composes build_mint_record()
+ mint_record_ref() below inside credit_ledger.append_entry(), so the debit,
the ledger entry and this record commit together or not at all. The OPEN
gate (link_redemptions.enforce_link_redemption, which serves /api/links/open,
the WebSocket and require_paid_client_work) reads this record through
get_link() and REFUSES a link with no record at all. record_mint()'s plain
non-transactional set() remains for callers with no credit to reserve (a
migration backfill, a test fixture). A5 adds the refund/revoke writers.

DOC SHAPE (links[_<channel>]/{jti}):
    firm_id: str            kit_id: str             employee_id: str
    employee_email: str | None
                              (bd polyglot-pdf-cpsi0: the minting account's
                               email claim, when the verified token carried
                               one -- a human-readable label ALONGSIDE
                               employee_id, never instead of it; no gate or
                               query keys on this field)
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

_log = structlog.get_logger(module="links_store")

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

# THE STATUSES THAT REFUSE AN OPEN (Epic 2 bead A3, read by
# link_redemptions.enforce_link_redemption). Deliberately an ALLOW-LIST'S
# COMPLEMENT stated as the small closed set of hard stops, because the
# plan's rule runs that way: "refuses when the record is missing or its
# status is revoked or refunded; EVERY OTHER STATUS falls through to the
# existing redemption gate". `opened` and `completed` are best-effort
# MIRRORS -- a failed mirror write must never lock a client out of a link
# they are part-way through, and `completed` is already the redemption
# ledger's call to make, not this cache's. `budget_exhausted` is telemetry
# only pending a maintainer pricing call, and the socket's own spend
# ceiling is what actually stops the spending.
#
# Both members are TERMINAL money states: `refunded` means the credit has
# been given back (opening would buy a session nobody paid for) and
# `revoked` means a human said stop. A new status must be added here only
# if it, too, means the money is gone -- otherwise it belongs in the
# fall-through.
OPEN_BLOCKING_STATUSES = frozenset({STATUS_REFUNDED, STATUS_REVOKED})

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


def mint_record_ref(db, jti: str, channel: str):
    """The DocumentReference for one mint record, on a CALLER-SUPPLIED
    client (Epic 2 bead A3).

    Exists so the MINT TRANSACTION can write this document. Everything else
    in this module resolves its own client through _collection(), but a
    Firestore transaction must write through refs built on the SAME client
    the transaction belongs to -- the mint route holds that client
    (credit_ledger.append_entry's `db`) and hands it here rather than
    letting this module fetch a second one.

    `channel` is REQUIRED here, not defaulted: the only caller is a
    transaction that has already decided which channel it is acting on, and
    silently defaulting would let a mis-wired caller write a demo record
    from staging.
    """
    return db.collection(_collection_name(channel)).document(jti)


def build_mint_record(
    jti: str,
    firm_id: str,
    kit_id: str,
    employee_id: str,
    credit_cost: int,
    cap_usd: float,
    open_deadline: int,
    now: Optional[float] = None,
    employee_email: Optional[str] = None,
) -> dict:
    """The mint record DOCUMENT, validated but NOT written (Epic 2 bead A3).

    THE ONE PLACE THE SHAPE IS DEFINED. record_mint() below writes what this
    returns with a plain set(); the mint route's transaction
    (backend/routes/link_routes.py:_reserve_mint) writes what this returns
    with tx.set(). Two writers, one builder -- a transactional copy that
    drifted from the plain one would produce records the sweep, the open
    gate and the console each read differently.

    Raises ValueError for a non-positive credit_cost or cap_usd (a link that
    costs nothing or has no spend ceiling is a configuration bug, not a
    valid mint) -- callers must not silently record a broken snapshot.

    employee_email (bd polyglot-pdf-cpsi0): OPTIONAL, never validated -- a
    human-readable label riding alongside employee_id, never a substitute
    for it. See the module docstring's DOC SHAPE entry.
    """
    if not all(isinstance(v, str) and v for v in (jti, firm_id, kit_id, employee_id)):
        raise ValueError("jti, firm_id, kit_id and employee_id are required")
    if not isinstance(credit_cost, int) or isinstance(credit_cost, bool) or credit_cost <= 0:
        raise ValueError(f"credit_cost must be a positive int, got {credit_cost!r}")
    if not isinstance(cap_usd, (int, float)) or isinstance(cap_usd, bool) or cap_usd <= 0:
        raise ValueError(f"cap_usd must be a positive number, got {cap_usd!r}")

    stamp = int(now if now is not None else time.time())
    return {
        "jti": jti,
        "firm_id": firm_id,
        "kit_id": kit_id,
        "employee_id": employee_id,
        "credit_cost": credit_cost,
        "employee_email": employee_email,
        "cap_usd": float(cap_usd),
        "minted_at": stamp,
        "open_deadline": int(open_deadline),
        "status": STATUS_MINTED,
        "revoked_by": None,
        "revoked_at": None,
        "expire_at": expire_at_for(int(open_deadline)),
    }


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
    employee_email: Optional[str] = None,
) -> dict:
    """Write the mint record for a freshly-minted link. Returns the record.

    NON-TRANSACTIONAL: the atomic "debit credit + ledger entry + this
    record" path is the MINT ROUTE's transaction (Epic 2 bead A3,
    backend/routes/link_routes.py:_reserve_mint), which composes
    build_mint_record() + mint_record_ref() above rather than calling this
    function. This plain write remains for callers with no credit to
    reserve -- a migration backfill, a test fixture -- and does not itself
    touch firms/{firm_id}.balance_credits.

    Raises LinksStoreUnavailable when the store cannot be reached; raises
    ValueError (from build_mint_record) for a malformed snapshot.
    """
    record = build_mint_record(
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
    try:
        _collection(channel).document(jti).set(record)
    except LinksStoreUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 -- any store failure is unavailable
        _log.error("links_store_write_failed", jti=jti, error_type=type(exc).__name__)
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
        _log.error("links_store_read_failed", jti=jti, error_type=type(exc).__name__)
        raise LinksStoreUnavailable(str(exc)) from exc
    if not snap.exists:
        return None
    return snap.to_dict() or {}


def mark_opened(jti: str, now: Optional[float] = None,
                channel: Optional[str] = None) -> bool:
    """BEST-EFFORT mirror: stamp this record `opened`. Returns whether it
    stuck (Epic 2 bead A3).

    NEVER RAISES, and its return value is advisory. `status` is a derived
    cache for listing (see the module docstring): the AUTHORITATIVE record
    of "was this link opened" is the redemption doc
    link_redemptions[_<channel>]/{jti}, which the redemption gate has
    already written by the time this is called, and which the A5 refund
    transaction reads. A failed mirror write must therefore cost nothing --
    swallowing the error here is what keeps a Firestore hiccup from turning
    a successful client open into a refused one.

    It only ever moves `minted` -> `opened`. A record already `opened`,
    `completed`, `revoked` or `refunded` is left alone: this is a mirror of
    the FIRST open, and re-stamping it on every reconnect would overwrite a
    later, more meaningful status with an earlier one.
    """
    stamp = int(now if now is not None else time.time())
    try:
        ref = _collection(channel).document(jti)
        snap = ref.get()
        if not snap.exists:
            return False
        current = (snap.to_dict() or {}).get("status")
        if current != STATUS_MINTED:
            return False
        ref.update({"status": STATUS_OPENED, "opened_at": stamp})
        return True
    except Exception as exc:  # noqa: BLE001 -- advisory mirror, never fatal
        _log.warning("links_store_mark_opened_failed", jti=jti, error_type=type(exc).__name__)
        return False


def links_store_status(channel: Optional[str] = None) -> str:
    """Report whether the links store can actually be READ.

    Same probe shape as firms.firms_store_status() and the confirmation
    sink's status probe: READ-shaped (limit-1 stream), never write+delete,
    because this path never needs write permission and probing with a write
    would test the wrong grant. Returns "ok" or "error: <ExceptionClass>" -- unlike
    firms_store_status() this store has no enable/disable env gate (it is
    Admin-SDK-only by rules, not by a feature flag), so there is no
    "disabled" branch.
    """
    try:
        list(_collection(channel).limit(1).stream())
        return "ok"
    except Exception as e:
        _log.error("links_store_probe_failed", error_type=type(e).__name__)
        # Class only, like its two siblings (sprint 23 B1b): a probe string can
        # end up on an unauthenticated route.
        return f"error: {type(e).__name__}"
