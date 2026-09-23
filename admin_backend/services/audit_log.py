"""The admin service's append-only audit log (bd polyglot-pdf-li9x0).

WHAT IT IS. One row in admin_audit_log/{auto} per privileged mutation, with
WHO did it, WHAT they did, to WHAT, and the before/after METADATA. It is the
answer to "who granted this firm 500 credits, and when" -- a question the
confirmation sink (backend/utils/confirmation_logger.py) cannot answer,
because that sink records the CLIENT's field confirmations, not the
OPERATOR's actions.

WHY IT IS NOT SHAPED LIKE THAT SINK. The confirmation sink is deliberately
fire-and-forget: a failed write there costs at most one missing line about a
field the client already confirmed. This log is the opposite polarity. Its
whole job is preventing a DOUBLE APPLY: an operator who sees a 500 retries,
and without an audit row bound to the mutation there is no way to tell a
first attempt from a second. So the two forms below both bind the row to the
mutation rather than firing it alongside.

THE TWO FORMS, and which one a route must use:

  1. FIRESTORE MUTATIONS (grants, adjustments, kit commercials, firm edits,
     revocations, and this bead's own PUT /admin/config/{channel}) use
     record_in_transaction(tx, db, ...). The audit row is written INSIDE the
     same Firestore transaction as the mutation, so either BOTH commit or
     NEITHER does. A forced audit failure leaves the mutation unapplied; a
     retried transaction re-runs the whole body, so it cannot double-apply.

  2. NON-FIRESTORE MUTATIONS (firebase_admin.auth user create/disable, claim
     stamps, Cloud Build triggers) cannot join a Firestore transaction --
     there is no transaction to join. They use the PENDING-THEN-COMMITTED
     form: record_pending() BEFORE the action, then mark_committed() (or
     mark_failed(error=...)) after. A row stuck at pending is exactly the
     signal an operator needs: the action MAY have taken effect, so check
     before retrying.

APPEND-ONLY is a property of the WRITERS, not of Firestore: nothing here
deletes or rewrites a row's identity fields. mark_committed / mark_failed
update only state (plus error / committed_ts) on a row THIS process just
created -- the state machine's one legal transition, pending -> committed |
failed. The client-side deny block in firestore.rules keeps browsers out
entirely; the Admin SDK bypasses rules, so the discipline is here.

WHAT NEVER GOES IN A ROW: form field values, PII, or PHI
(docs/standards/hipaa-pii-policy.md). before and after carry CONFIG and
COMMERCIAL metadata -- a config key's old and new value, a firm's credit
balance, a kit's price -- never a client's answers. Nothing in this service
has access to field values in the first place: the admin service serves
operators, not form sessions.

IAM: the writes here need roles/datastore.user, which admin-backend-sa
already holds and which admin_backend/tests/unit/test_admin_sa_iam_envelope.py
pins by name AND by justification ("Firestore reads and writes: firms, the
credit ledger, kits, links, admin_audit_log, deployments, app_config") --
this bead adds no new permission (CLAUDE.md scar #7).

ASCII only.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional

import structlog

_log = structlog.get_logger(module="audit_log")

COLLECTION = "admin_audit_log"

# The row's lifecycle states. committed is terminal and is what a
# Firestore-transaction row is born as (it commits with its mutation or not
# at all -- there is no window in which it is pending). pending and failed
# exist only for the non-Firestore form.
STATE_COMMITTED = "committed"
STATE_PENDING = "pending"
STATE_FAILED = "failed"

STATES = frozenset({STATE_COMMITTED, STATE_PENDING, STATE_FAILED})

# Every field a row carries, per the plan's "Append-only audit log" section.
# Pinned as a frozenset (not prose) so a reader that adds a field, or a
# writer that drops one, is a set difference a test can catch rather than a
# paragraph someone has to re-read.
ROW_FIELDS = frozenset({
    "actor_uid",
    "actor_email",
    "action",
    "target",
    "before",
    "after",
    "channel",
    "request_id",
    "state",
    "ts",
})


def new_request_id() -> str:
    """A correlation id for one operator action.

    Generated per-request rather than per-row so the pending row and its
    committed follow-up share one id, and so a multi-row action (a later
    epic's batch grant) is greppable as one unit. uuid4 rather than a
    Firestore auto-id: the id must exist BEFORE any write, since the pending
    form logs it before the action runs.
    """
    return uuid.uuid4().hex


def build_row(
    *,
    actor_uid: str,
    actor_email: Optional[str],
    action: str,
    target: str,
    before: Any,
    after: Any,
    state: str,
    channel: Optional[str] = None,
    request_id: Optional[str] = None,
    ts: Optional[float] = None,
) -> dict:
    """The row payload, built in ONE place for both forms.

    Both writers below go through here so a field can never be present in
    one form's rows and absent from the other's -- the exact drift that makes
    an audit query return "no channel" for half the rows and mean two
    different things.

    ts is a plain epoch float, not firestore.SERVER_TIMESTAMP: the pending
    form needs the value to EXIST client-side before the action runs (it is
    logged alongside the request id), and a sentinel that only resolves at
    commit cannot be logged. A few milliseconds of clock skew is irrelevant
    for an audit ordering that is already keyed by request id.
    """
    if state not in STATES:
        # A typo'd state would make every state-filtered query silently miss
        # these rows -- fail at the write instead.
        raise ValueError(
            "state {!r} is not one of {}".format(state, sorted(STATES)))
    return {
        "actor_uid": actor_uid,
        "actor_email": actor_email,
        "action": action,
        "target": target,
        "before": before,
        "after": after,
        "channel": channel,
        "request_id": request_id or new_request_id(),
        "state": state,
        "ts": float(ts if ts is not None else time.time()),
    }


def _collection(db):
    return db.collection(COLLECTION)


def record_in_transaction(
    tx,
    db,
    *,
    actor_uid: str,
    actor_email: Optional[str],
    action: str,
    target: str,
    before: Any,
    after: Any,
    channel: Optional[str] = None,
    request_id: Optional[str] = None,
    ts: Optional[float] = None,
) -> dict:
    """FORM 1: the audit row, written inside the CALLER'S transaction.

    Takes the transaction rather than opening one, which is the whole point:
    the row and the mutation must share ONE transaction so Firestore's
    all-or-nothing commit covers both. A helper that opened its own would
    give two independent commits and exactly the double-apply window this
    log exists to close.

    Returns the row it wrote (state=committed -- see STATE_COMMITTED's note:
    a transactional row has no pending window), plus the doc_id, so a route
    can echo the request id back to the console.

    db is passed alongside tx because a firestore Transaction carries no
    reference back to its client -- the document ref has to be built from the
    client the caller already has.
    """
    row = build_row(
        actor_uid=actor_uid,
        actor_email=actor_email,
        action=action,
        target=target,
        before=before,
        after=after,
        state=STATE_COMMITTED,
        channel=channel,
        request_id=request_id,
        ts=ts,
    )
    ref = _collection(db).document()
    tx.set(ref, row)
    # NO try/except. An audit failure MUST propagate: it aborts the
    # transaction, which is the behaviour criterion 1 pins (a forced audit
    # failure leaves the config unchanged). Swallowing it here would let the
    # mutation commit unaudited, which is the one outcome this form exists
    # to make impossible.
    return {**row, "doc_id": ref.id}


def record_pending(
    db,
    *,
    actor_uid: str,
    actor_email: Optional[str],
    action: str,
    target: str,
    before: Any,
    after: Any,
    channel: Optional[str] = None,
    request_id: Optional[str] = None,
    ts: Optional[float] = None,
):
    """FORM 2, step 1: claim the action BEFORE performing it.

    For mutations Firestore cannot wrap -- firebase_admin.auth user
    create/disable, claim stamps, Cloud Build triggers. Returns the document
    REFERENCE, which the caller hands to mark_committed / mark_failed; the
    reference is the handle, so a caller cannot accidentally close out a
    different row.

    RAISES on a write failure, and callers must let it: if the intent cannot
    be recorded, the action must not happen. A best-effort pending row would
    reduce this form to fire-and-forget, and the retry ambiguity would be
    back.
    """
    row = build_row(
        actor_uid=actor_uid,
        actor_email=actor_email,
        action=action,
        target=target,
        before=before,
        after=after,
        state=STATE_PENDING,
        channel=channel,
        request_id=request_id,
        ts=ts,
    )
    ref = _collection(db).document()
    ref.set(row)
    _log.info(
        "admin_audit_pending",
        action=action, target=target, actor_uid=actor_uid,
        request_id=row["request_id"],
    )
    return ref


def mark_committed(ref, *, after: Any = None, ts: Optional[float] = None) -> None:
    """FORM 2, step 2a: the action succeeded.

    after is optional and updates the row only when the real result was not
    known at pending time (an auth create returns the new uid, which is the
    most useful after there is).

    Best-effort BY DESIGN, and this is the one place that asymmetry is
    correct: the action ALREADY HAPPENED. Failing loudly here would surface
    an error for a mutation that succeeded, and a caller that retried on it
    would double-apply -- precisely what the pending row was written to
    prevent. A row stuck at pending is the readable, conservative outcome:
    it says "this may have taken effect", which is true.
    """
    payload: dict[str, Any] = {
        "state": STATE_COMMITTED,
        "committed_ts": float(ts if ts is not None else time.time()),
    }
    if after is not None:
        payload["after"] = after
    try:
        ref.update(payload)
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        _log.error("admin_audit_commit_failed", error_type=type(exc).__name__)


def mark_failed(ref, *, error: str, ts: Optional[float] = None) -> None:
    """FORM 2, step 2b: the action failed; record why.

    Best-effort for the same reason as mark_committed: the outcome is already
    decided, and raising here would replace a real error with a bookkeeping
    one. The error string is truncated -- an audit row is a record, not a log
    sink, and an unbounded exception repr can carry a stack trace's worth of
    unvetted text into a document meant to be read in a console table.
    """
    payload = {
        "state": STATE_FAILED,
        "error": str(error)[:500],
        "committed_ts": float(ts if ts is not None else time.time()),
    }
    try:
        ref.update(payload)
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        _log.error("admin_audit_fail_mark_failed", error_type=type(exc).__name__)
