"""Telemetry alert docs: alerts/{id} (Epic 3 bead E3.5, bd polyglot-pdf-bo95a).

WHAT THIS IS. Two hooks write into ONE collection with DETERMINISTIC ids, so
a repeated trigger dedups by overwriting the same document rather than
piling up a row per occurrence:

    link_exhausted_{jti}                   -- backend/services/link_spend.py's
                                               check_budget(), the moment a
                                               client link's spend ceiling is
                                               reached or exceeded.
    {firm_id}_credit_low_{YYYY-MM-DD}       -- backend/services/credit_ledger.py's
    {firm_id}_credit_exhausted_{YYYY-MM-DD}    append_entry(), the moment a
                                               debit leaves the firm's balance
                                               at or below CREDIT_LOW_THRESHOLD
                                               (runtime_config) or at/below
                                               zero.

WHY DETERMINISTIC IDS, NOT AN APPEND-ONLY LOG. A link that keeps trying
paid work after its ceiling trips would otherwise write one row per attempt;
a firm hovering right at its low-credit threshold across a busy day would
write one row per debit. The deterministic id turns every repeat into the
SAME document, so `set(..., merge=True)` is idempotent by construction:
a second refusal for the same jti, or a second low-balance crossing on the
same UTC day, overwrites fields on the existing doc rather than creating a
new one. This is the dedup the bead's exit criterion 1 tests.

ONE DOC PER (firm, kind, day) IS DELIBERATE, EVEN ACROSS MULTIPLE DEBITS.
The day-keyed id means a firm that crosses the low threshold on its first
debit of the day and again on its fifth still produces exactly one
`{firm_id}_credit_low_{day}` doc -- re-crossing is not a new event worth a
second email once Epic 3's dispatcher ships. A firm that recovers above the
threshold and drops below it again the SAME day still collapses onto the
same doc (the write is a merge, so `ts`/`context` reflect the latest
crossing); a NEW day gets a new id, which is the reset an operator would
expect ("still low today" is one alert, not one per debit).

BEST-EFFORT, NEVER RAISES INTO THE PAID PATH (exit criterion 2). Both
callers are on paths that must not fail because a TELEMETRY write had a bad
day: `check_budget` is called before starting a metered voice session, and
`append_entry` is the one transactional ledger writer other code depends on
completing. An alert-write failure is logged and swallowed here, in this
module, so neither caller needs its own try/except -- one guarded seam
rather than two hand-written copies that could drift (CLAUDE.md scar #8:
enumerate the set, fix it as a set). Both entry points below therefore never
raise for any reason.

FIELDS carry METADATA ONLY, never a field value (docs/standards/hipaa-pii-
policy.md and docs/standards/stateless-architecture.md): firm_id, kind,
level (warning|critical), ts, context (jti/spend_usd/ceiling_usd/balance --
whichever apply to that kind), acknowledged_by, acknowledged_at (both None
until an operator acknowledges through a later admin-console bead),
emailed_at (None until Epic 3's dispatcher bead sends it), expire_at (the
TTL policy scripts/setup-firestore-ttl.sh already declares on this
collection's `expire_at` field, so the doc reaps itself without a sweep).

ADMIN-SDK-ONLY, like every other collection in this family (firms,
app_config, the ledger, links, link_redemptions): firestore.rules carries an
explicit client deny block, pinned by the set-derived rules test
(backend/tests/unit/test_firestore_rules_text.py).

ASCII only.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog

_log = structlog.get_logger().bind(module="alerts")

COLLECTION = "alerts"

KIND_LINK_EXHAUSTED = "link_exhausted"
KIND_CREDIT_LOW = "credit_low"
KIND_CREDIT_EXHAUSTED = "credit_exhausted"

LEVEL_WARNING = "warning"
LEVEL_CRITICAL = "critical"

# Every field an alert doc carries. A frozenset rather than prose, mirroring
# credit_ledger.py's ENTRY_FIELDS precedent, so a writer that drops a field
# is a set difference a test catches rather than a silent NULL column at the
# console's read side.
ALERT_FIELDS = frozenset({
    "firm_id",
    "kind",
    "level",
    "ts",
    "context",
    "acknowledged_by",
    "acknowledged_at",
    "emailed_at",
    "expire_at",
})

# Retention past the alert's own timestamp before Firestore's TTL policy
# reaps the doc -- long enough for an operator to see it in the console and
# for Epic 3's (not-yet-built) dispatcher to have sent its email, mirroring
# links_store.py's own margin-past-the-triggering-event pattern.
_TTL_RETENTION_DAYS = 90


def _expire_at(stamp: float) -> datetime:
    return (
        datetime.fromtimestamp(stamp, tz=timezone.utc)
        + timedelta(days=_TTL_RETENTION_DAYS)
    )


def _collection():
    """The alerts collection, via the Admin SDK (bypasses Security Rules).

    Lazy-imported, matching every sibling store in this family
    (link_redemptions._collection, links_store._collection,
    runtime_config._read_channel_doc): this module must be importable with
    no firebase_admin app initialized, so the test suite and local dev can
    import it freely.
    """
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise RuntimeError("no firestore client")
    return db.collection(COLLECTION)


def _write(doc_id: str, *, firm_id: Optional[str], kind: str, level: str,
           context: dict[str, Any], now: Optional[float] = None) -> None:
    """The one write path both public hooks below call. NEVER RAISES: any
    failure (no firestore client, a store error) is logged and swallowed,
    per this module's best-effort contract.

    `set(..., merge=True)` is what makes the deterministic id idempotent: a
    repeat trigger for the SAME doc_id updates `ts`/`context`/`level` rather
    than failing on an existing document or requiring a second code path for
    "already exists". The three operator/dispatcher-owned fields --
    `acknowledged_by`, `acknowledged_at`, `emailed_at` -- are seeded to None
    ONLY on first creation (checked with a read before the write): a
    re-trigger of an already-acknowledged or already-emailed alert must not
    silently revive it by overwriting those fields back to None, so once the
    doc exists this function never touches them again, and only
    firm_id/kind/level/ts/context/expire_at are (re)written on a repeat.
    """
    stamp = float(now if now is not None else time.time())
    doc: dict[str, Any] = {
        "firm_id": firm_id,
        "kind": kind,
        "level": level,
        "ts": stamp,
        "context": context,
        "expire_at": _expire_at(stamp),
    }
    try:
        # _collection() itself is INSIDE the try, not just ref.get()/.set():
        # get_db() can raise (a broken firebase_admin app, per
        # backend/services/auth.py's plain firestore.client() call with no
        # guard of its own) rather than merely returning None, and that
        # exception must be swallowed here exactly like a write failure --
        # this module's whole contract is that NOTHING it does can raise
        # into check_budget or append_entry.
        ref = _collection().document(doc_id)
        if not ref.get().exists:
            doc.update({
                "acknowledged_by": None,
                "acknowledged_at": None,
                "emailed_at": None,
            })
        ref.set(doc, merge=True)
    except Exception as exc:  # noqa: BLE001 -- best-effort, never raise
        _log.error("alert_write_failed", doc_id=doc_id, kind=kind, error=str(exc))
        return
    _log.info("alert_written", doc_id=doc_id, kind=kind, level=level,
              firm_id=firm_id)


def record_link_exhausted(jti: str, *, firm_id: Optional[str],
                           spend_usd: float, ceiling_usd: float,
                           now: Optional[float] = None) -> None:
    """A client link hit or exceeded its spend ceiling.

    Called from link_spend.check_budget()'s refusal branch, ONCE per raise
    of LinkBudgetExhausted. Deterministic id `link_exhausted_{jti}` means a
    link that keeps attempting paid work after its ceiling trips (a client
    retrying, a flaky reconnect loop) collapses onto the SAME doc rather
    than paging an operator once per attempt -- exit criterion 1's "a second
    refusal for the same jti writes nothing new" (the doc already exists and
    the merge is a no-op content-wise beyond refreshing ts/context).

    NEVER RAISES: a failure here must not turn a bookkeeping write into a
    second reason to fail a session already being refused for spend.
    """
    if not isinstance(jti, str) or not jti:
        return
    _write(
        "link_exhausted_{}".format(jti),
        firm_id=firm_id,
        kind=KIND_LINK_EXHAUSTED,
        level=LEVEL_CRITICAL,
        context={
            "jti": jti,
            "spend_usd": round(float(spend_usd), 6),
            "ceiling_usd": float(ceiling_usd),
        },
        now=now,
    )


def _day_key(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d")


def record_credit_threshold(firm_id: str, *, balance: int, threshold: int,
                             now: Optional[float] = None) -> None:
    """A firm's balance crossed CREDIT_LOW_THRESHOLD, or hit zero-or-below.

    Called from credit_ledger.append_entry() AFTER a debit commits, with the
    balance the commit produced. Two kinds, both day-keyed so a firm that
    crosses the same boundary more than once in one UTC day still produces
    exactly one doc per kind per day (exit criterion 1: "a firm crossing the
    low threshold twice in one day yields one doc; crossing to zero yields
    the exhausted doc").

    NOT MUTUALLY EXCLUSIVE BY DESIGN WHEN THRESHOLD IS POSITIVE: a balance at
    or below zero is ALSO at or below a positive low threshold, so a firm
    hitting zero with e.g. threshold=10 gets BOTH docs -- `credit_low_{day}`
    and `credit_exhausted_{day}` -- the same day, which is correct: they are
    different severities an operator (and later, different email templates)
    treats differently, and the exhausted case is not a superset replacement
    for the low warning within the log.

    THRESHOLD=0 IS THE ONE CARVE-OUT: runtime_config.py's coercion
    deliberately accepts 0 for an operator who wants ONLY the zero-balance
    alert, no separate low warning (see KEY_CREDIT_LOW_THRESHOLD's coercion
    comment and test_credit_low_threshold_accepts_zero). Emitting credit_low
    at threshold=0 would defeat that operator's choice -- balance<=0 and
    balance<=0 are the same boundary, so the "low" doc would carry no
    information the "exhausted" doc doesn't already have. The low branch
    below therefore requires `threshold > 0` before comparing balance to it.

    Writes NOTHING when the balance is above the threshold (or the threshold
    is 0) -- this function is the caller's ENTIRE threshold check, not just
    the write; a caller that always invokes it unconditionally after every
    debit is correct.

    NEVER RAISES: a failure here must not undo or fail a debit that already
    committed.
    """
    stamp = float(now if now is not None else time.time())
    day = _day_key(stamp)
    if balance <= 0:
        _write(
            "{}_credit_exhausted_{}".format(firm_id, day),
            firm_id=firm_id,
            kind=KIND_CREDIT_EXHAUSTED,
            level=LEVEL_CRITICAL,
            context={"balance": int(balance), "threshold": int(threshold)},
            now=stamp,
        )
    if threshold > 0 and balance <= threshold:
        _write(
            "{}_credit_low_{}".format(firm_id, day),
            firm_id=firm_id,
            kind=KIND_CREDIT_LOW,
            level=LEVEL_WARNING,
            context={"balance": int(balance), "threshold": int(threshold)},
            now=stamp,
        )
