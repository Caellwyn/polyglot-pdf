"""The credit ledger: firms/{firm_id}/ledger/{auto} plus the materialized
balance on firms/{firm_id} (Epic 2 bead A2, epic polyglot-pdf-e374w).

ONE HELPER, EVERY ENTRY TYPE. append_entry() below is the ONLY code in this
repo that writes firms/{firm_id}.balance_credits. Subscription grants,
prepaid purchases, promotional grants, mint debits, expiry refunds and
operator adjustments all go through it, so the invariant

    balance_credits == sum(every ledger entry's amount)

holds by CONSTRUCTION rather than by six call sites each remembering to
update the balance. A second writer of that field -- even a "quick fix" in a
migration -- breaks the invariant silently, because nothing recomputes the
balance from the ledger on a read. Add entry TYPES here; never add balance
writers elsewhere. (backend/services/firms.py's upsert_firm() 0-initializes
balance_credits on FIRST CREATE only and never touches it again; that is the
one deliberate exception, and it writes a zero into a firm with no ledger.)

THE ENTRY IS SIGNED. `amount` is the credit delta: POSITIVE for the four
credit-adding types (subscription_grant, purchase, promo_grant,
expiry_refund) and NEGATIVE for mint_debit. `adjustment` is the one type
that takes either sign -- it is the operator's escape hatch, which is
exactly why it also REQUIRES a `reason`. balance_after is the balance the
entry produced, so replaying the collection in ts order reproduces both the
running total and every stored balance_after (pinned by
test_ledger_balance_invariant_holds_after_replay).

READS BEFORE WRITES -- THE FIRESTORE TRANSACTION RULE. A Firestore
transaction must perform ALL of its reads BEFORE any of its writes; a read
issued after a write in the same transaction raises. The transaction body
below therefore reads firms/{firm_id} first, computes everything from that
snapshot, and only then issues its two writes (the balance update and the
ledger entry). Firestore also RE-RUNS the whole body on contention, so
nothing may be computed OUTSIDE the body and carried in: a balance read
before the transaction would be stale on the retry, and the retry is
precisely the double-mint race that
test_mint_transaction_double_mint_race_is_safe pins. Everything that depends
on the current balance -- the sufficiency check, the new balance, and
balance_after -- is computed inside the body, every time it runs.

SYNC BY DESIGN, ON THE ADMIN SDK. The firebase_admin Firestore client is
synchronous, so this helper is synchronous. Every caller on an async path
(the mint route, the socket, the refund sweep) must run it under
asyncio.to_thread, exactly as backend/routes/link_routes.py already does for
its Firestore reads. Calling it directly from a coroutine blocks the event
loop for the duration of a multi-round-trip transaction, which on a
contended firm is not a small number.

EVERY WRITE EMITS A ledger_export LOG LINE. After a successful commit the
helper logs a structured `ledger_export` event carrying type, amount,
usd_amount, firm_id, firm_kind, channel and link_jti -- the income and spend
feed Epic 3's Cloud Logging -> BigQuery sink filters on
(jsonPayload.event_type == "ledger_export"; structlog's JSONRenderer puts
every bound key at the top level of the JSON line, which is what makes that
filter work). It is emitted AFTER the commit, never before: a line for an
entry that never committed would inflate the income view with money that was
not moved. It carries NO field values, no PII and no PHI
(docs/standards/hipaa-pii-policy.md) -- ids, credit counts and dollar
amounts only.

WHY usd_amount IS NULLABLE BUT NOT OPTIONAL. purchase and subscription_grant
REQUIRE it (that is the income figure Epic 5's reporting sums, recorded from
day one so no migration is needed later); promo_grant, mint_debit,
expiry_refund and adjustment REQUIRE it to be absent, because a dollar
figure on a promotional grant or a debit would be double-counted as income.
The requirement runs both ways on purpose: "forgot to pass it" and "passed
it where it does not belong" are both refused at the write.

WHY firm_kind IS SNAPSHOTTED. The income view filters on `firm_kind ==
"live"` -- test firms must not appear as revenue. It is snapshotted onto
each entry rather than joined from the firm doc at read time because the
admin service that writes grants has NO channel of its own (channel is
nullable here for the same reason), and because a firm flipped from mock to
live later must not retroactively turn its test grants into income.

THE BALANCE IS NOT CHANNEL-PARTITIONED: one firm, one balance_credits,
whichever channel's mint debits it (backend/services/firms.py's module
docstring carries the full statement). `channel` on an entry is a record of
WHERE a debit happened, not a partition key.

ADMIN-SDK-ONLY: firestore.rules carries a client deny block for the nested
firms/{firmId}/ledger subcollection, pinned by the set-derived rules test
(backend/tests/unit/test_firestore_rules_text.py).

ASCII only.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import structlog

_log = structlog.get_logger().bind(module="credit_ledger")

FIRMS_COLLECTION = "firms"
LEDGER_SUBCOLLECTION = "ledger"

# The structured-log event name Epic 3's Cloud Logging -> BigQuery sink
# filters on (jsonPayload.event_type). Named as a constant so the sink
# filter, the tests, and the emitter cannot drift apart in three places.
LEDGER_EXPORT_EVENT = "ledger_export"

TYPE_SUBSCRIPTION_GRANT = "subscription_grant"
TYPE_PURCHASE = "purchase"
TYPE_PROMO_GRANT = "promo_grant"
TYPE_MINT_DEBIT = "mint_debit"
TYPE_EXPIRY_REFUND = "expiry_refund"
TYPE_ADJUSTMENT = "adjustment"

ENTRY_TYPES = (
    TYPE_SUBSCRIPTION_GRANT,
    TYPE_PURCHASE,
    TYPE_PROMO_GRANT,
    TYPE_MINT_DEBIT,
    TYPE_EXPIRY_REFUND,
    TYPE_ADJUSTMENT,
)

# The two types that record MONEY CHANGING HANDS, and therefore require a
# usd_amount. Every other type must NOT carry one (see the module docstring:
# a dollar figure on a promo or a debit would be double-counted as income).
USD_REQUIRED_TYPES = frozenset({TYPE_PURCHASE, TYPE_SUBSCRIPTION_GRANT})

# Types whose amount must be strictly POSITIVE (they add credits) and
# strictly NEGATIVE (they remove them). adjustment is in NEITHER set: it is
# the signed escape hatch, and its `reason` requirement is the control that
# replaces the sign rule.
POSITIVE_ONLY_TYPES = frozenset({
    TYPE_SUBSCRIPTION_GRANT,
    TYPE_PURCHASE,
    TYPE_PROMO_GRANT,
    TYPE_EXPIRY_REFUND,
})
NEGATIVE_ONLY_TYPES = frozenset({TYPE_MINT_DEBIT})

# Types that require a human-readable justification. adjustment is the only
# entry an operator can write with an arbitrary sign and no upstream event
# (no purchase, no mint, no expiry) explaining it, so the explanation is
# mandatory or the ledger becomes unauditable exactly where it matters most.
REASON_REQUIRED_TYPES = frozenset({TYPE_ADJUSTMENT})

# Every field an entry carries. A frozenset rather than prose so a writer
# that drops a field, or a reader that expects one nobody writes, is a set
# difference a test catches (the audit_log.ROW_FIELDS precedent).
ENTRY_FIELDS = frozenset({
    "type",
    "amount",
    "usd_amount",
    "firm_kind",
    "channel",
    "balance_after",
    "actor",
    "reason",
    "link_jti",
    "kit_id",
    "ts",
})

# The fields the ledger_export log line carries, per the plan's BigQuery
# section. Pinned as a set for the same reason ENTRY_FIELDS is: Epic 3's
# sink and its BigQuery table are built from this list, and a silently
# dropped key becomes a NULL column nobody notices until a revenue number is
# wrong.
LEDGER_EXPORT_FIELDS = frozenset({
    "event_type",
    "type",
    "amount",
    "usd_amount",
    "firm_id",
    "firm_kind",
    "channel",
    "link_jti",
})


class LedgerError(Exception):
    """A ledger write could not be performed. Nothing was committed."""


class InsufficientCredits(LedgerError):
    """A debit was refused because the balance would not cover it.

    Raised ONLY when the caller passed require_sufficient_balance=True. The
    mint route's CREDITS_ENFORCED gate (Epic 2 bead A3) is what decides
    whether to pass it: with enforcement OFF the debit is still written and
    the balance may go negative, which is the metered soft-launch mode.
    """

    def __init__(self, firm_id: str, balance: int, amount: int):
        self.firm_id = firm_id
        self.balance = balance
        self.amount = amount
        super().__init__(
            "firm {} has {} credits, which does not cover a debit of {}".format(
                firm_id, balance, abs(amount)
            )
        )


def _validate(
    entry_type: str,
    amount: int,
    usd_amount: Optional[float],
    actor: str,
    reason: Optional[str],
) -> None:
    """Refuse a malformed entry BEFORE opening a transaction.

    Every check here is on caller-supplied data only -- nothing needs a
    Firestore read -- so running them up front keeps a bad call from costing
    a transaction round trip, and keeps the transaction body free of
    argument checking that would re-run on every retry.
    """
    if entry_type not in ENTRY_TYPES:
        raise LedgerError(
            "type {!r} is not one of {}".format(entry_type, sorted(ENTRY_TYPES))
        )
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise LedgerError("amount must be an int, got {!r}".format(amount))
    if amount == 0:
        # A zero-credit entry moves nothing and would still consume a
        # balance write; it is always a caller bug (a miscomputed cost, an
        # empty grant form), never a legitimate record.
        raise LedgerError("amount must be non-zero")
    if entry_type in POSITIVE_ONLY_TYPES and amount < 0:
        raise LedgerError(
            "{} requires a positive amount, got {}".format(entry_type, amount)
        )
    if entry_type in NEGATIVE_ONLY_TYPES and amount > 0:
        raise LedgerError(
            "{} requires a negative amount, got {}".format(entry_type, amount)
        )
    if entry_type in USD_REQUIRED_TYPES:
        if usd_amount is None:
            raise LedgerError(
                "{} requires usd_amount (the income figure)".format(entry_type)
            )
        if not isinstance(usd_amount, (int, float)) or isinstance(
                usd_amount, bool):
            raise LedgerError(
                "usd_amount must be a number, got {!r}".format(usd_amount)
            )
        if usd_amount < 0:
            raise LedgerError(
                "usd_amount must not be negative, got {!r}".format(usd_amount)
            )
    elif usd_amount is not None:
        raise LedgerError(
            "{} must not carry a usd_amount (only {} record income)".format(
                entry_type, sorted(USD_REQUIRED_TYPES)
            )
        )
    if not isinstance(actor, str) or not actor.strip():
        # "never blank" is the plan's word: an entry whose actor is empty is
        # unattributable, and an unattributable credit movement is the one
        # thing the ledger exists to make impossible.
        raise LedgerError("actor is required (a uid or 'system:<origin>')")
    if entry_type in REASON_REQUIRED_TYPES and not (
            isinstance(reason, str) and reason.strip()):
        raise LedgerError("{} requires a reason".format(entry_type))


def append_entry(
    db,
    firm_id: str,
    *,
    entry_type: str,
    amount: int,
    actor: str,
    usd_amount: Optional[float] = None,
    channel: Optional[str] = None,
    reason: Optional[str] = None,
    link_jti: Optional[str] = None,
    kit_id: Optional[str] = None,
    require_sufficient_balance: bool = False,
    extra_writes=None,
    ts: Optional[float] = None,
) -> dict:
    """Append ONE ledger entry and update the firm's balance, atomically.

    THE ONE WRITER of firms/{firm_id}.balance_credits. Returns the committed
    entry plus its doc_id, the firm_id, and the resulting balance.

    SYNC (Admin SDK). Async callers must wrap this in asyncio.to_thread.

    READS BEFORE WRITES: the transaction body reads the firm doc first and
    computes the new balance, balance_after and the sufficiency verdict from
    THAT snapshot before issuing any write. Firestore re-runs the body on
    contention, so a loser in a double-debit race re-reads the winner's
    committed balance and refuses (or goes negative, if enforcement is off)
    on real state rather than on a value captured before the race.

    firm_kind comes from the SAME snapshot the balance does, and defaults to
    "live" when the doc carries no `kind` -- the identical fail-closed
    polarity as backend/services/firms.py's firm_kind(), for the identical
    reason: a mis-read must not turn a paying firm's grant into a test row
    that the income view then drops.

    require_sufficient_balance=True raises InsufficientCredits (nothing
    committed) when the pre-entry balance would not cover a negative amount.
    The default is False because the soft-launch mode deliberately lets the
    balance go negative -- the mint route's CREDITS_ENFORCED gate is what
    turns it on (Epic 2 bead A3).

    extra_writes lets a CALLER join additional documents to this same
    transaction -- Epic 2 bead A3 passes the links/{jti} mint record so the
    debit, the entry and the record commit together or not at all. It is a
    callable taking (tx, firm_snapshot_dict) and returning None; it runs
    INSIDE the body, AFTER the reads, and any exception it raises aborts the
    whole transaction. It must not read (reads-before-writes), and because
    the body re-runs on contention it must write the same thing from the
    same inputs on every run.
    """
    _validate(entry_type, amount, usd_amount, actor, reason)
    if db is None:
        raise LedgerError("no firestore client")

    from firebase_admin import firestore

    firm_ref = db.collection(FIRMS_COLLECTION).document(firm_id)
    entry_ref = firm_ref.collection(LEDGER_SUBCOLLECTION).document()
    stamp = float(ts if ts is not None else time.time())
    captured: dict[str, Any] = {}

    @firestore.transactional
    def _txn(tx):
        # --- READS (all of them, before any write) ---------------------
        snap = firm_ref.get(transaction=tx)
        if not snap.exists:
            # A ledger entry against a firm that does not exist would create
            # the balance field on a phantom doc and make the firm appear in
            # listings. Refuse rather than conjure.
            raise LedgerError("firm {} does not exist".format(firm_id))
        firm = snap.to_dict() or {}

        balance = firm.get("balance_credits")
        if not isinstance(balance, int) or isinstance(balance, bool):
            # A missing or malformed balance is treated as 0 rather than
            # refused: the pre-backfill window (Epic 2 bead A6) has firm docs
            # with no balance_credits at all, and a grant is exactly how an
            # operator gets one out of that window.
            balance = 0
        kind = firm.get("kind")
        if kind not in ("mock", "live"):
            kind = "live"

        if require_sufficient_balance and amount < 0 and balance + amount < 0:
            raise InsufficientCredits(firm_id, balance, amount)

        new_balance = balance + amount
        entry = {
            "type": entry_type,
            "amount": amount,
            "usd_amount": (
                float(usd_amount) if usd_amount is not None else None
            ),
            "firm_kind": kind,
            "channel": channel,
            "balance_after": new_balance,
            "actor": actor,
            "reason": reason,
            "link_jti": link_jti,
            "kit_id": kit_id,
            "ts": stamp,
        }

        # --- WRITES ----------------------------------------------------
        tx.set(firm_ref, {
            "balance_credits": new_balance,
            "balance_updated_at": stamp,
        }, merge=True)
        tx.set(entry_ref, entry)
        if extra_writes is not None:
            # Runs inside the SAME transaction so a caller's mint record
            # either commits with the debit or not at all. Its exceptions
            # are deliberately NOT caught: aborting is the contract.
            extra_writes(tx, firm)

        captured["entry"] = entry
        captured["balance"] = new_balance
        captured["firm_kind"] = kind

    _txn(db.transaction())

    entry = captured["entry"]
    # AFTER the commit, never before: see the module docstring. A
    # ledger_export line for an entry that failed to commit would inflate
    # the income view with money that never moved.
    _log.info(
        LEDGER_EXPORT_EVENT,
        event_type=LEDGER_EXPORT_EVENT,
        type=entry_type,
        amount=amount,
        usd_amount=entry["usd_amount"],
        firm_id=firm_id,
        firm_kind=captured["firm_kind"],
        channel=channel,
        link_jti=link_jti,
    )
    return {
        **entry,
        "doc_id": entry_ref.id,
        "firm_id": firm_id,
        "balance_credits": captured["balance"],
    }


def read_balance(db, firm_id: str) -> Optional[int]:
    """The firm's materialized balance, or None when the firm does not exist.

    A plain read of the field append_entry() maintains -- it does NOT sum the
    ledger. Summing on every read would make a firm's mint path O(entries),
    and the materialized field is exactly what the transaction exists to keep
    correct. A malformed stored balance reads as 0, matching the transaction
    body's treatment of the same case.
    """
    snap = db.collection(FIRMS_COLLECTION).document(firm_id).get()
    if not snap.exists:
        return None
    balance = (snap.to_dict() or {}).get("balance_credits")
    if not isinstance(balance, int) or isinstance(balance, bool):
        return 0
    return balance


def read_entries(db, firm_id: str, limit: Optional[int] = None) -> list[dict]:
    """This firm's ledger entries in ts order (oldest first).

    The replay source: summing `amount` over this list must reproduce
    read_balance(), and each entry's balance_after must equal the running
    sum. `limit` is applied AFTER ordering, so a limited read is the OLDEST
    n entries -- the shape a replay check wants, not the newest-n a console
    table wants (the console's own reader belongs to the admin service).
    """
    query = (
        db.collection(FIRMS_COLLECTION)
        .document(firm_id)
        .collection(LEDGER_SUBCOLLECTION)
        .order_by("ts")
    )
    if limit is not None:
        query = query.limit(limit)
    return [snap.to_dict() or {} for snap in query.stream()]
