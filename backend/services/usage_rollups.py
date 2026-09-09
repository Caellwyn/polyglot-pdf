"""Session-end Firestore usage rollups: firms/{firm_id}/usage/{YYYY-MM[_channel]}
and kits/{kit_id}/usage/{YYYY-MM[_channel]} (Epic 3 bead E3.4, bd
polyglot-pdf-w828m).

DOC ID IS CHANNEL-SUFFIXED, NOT firm_id/kit_id. Staging and demo share one
Firestore project (docs/technical_guide.md, CLAUDE.md "Deployment /
promotion"), and unlike credit_ledger.py's append-only entries -- where
`channel` is honestly just a record of where a debit happened, per that
module's own docstring -- these rollup docs are shared AGGREGATE counters
that each write overwrites in place. A bare "YYYY-MM" id would let a
staging test-drive increment the SAME document the demo's billing view
reads, with no way to filter it back out at read time. So the month id
itself is the partition key, following the established channel-suffix
convention from bd polyglot-pdf-3q9qn (link_redemptions._collection_name /
links_store._collection_name): the demo channel keeps the bare "YYYY-MM"
id (nothing already written is orphaned), every other channel gets
"YYYY-MM_{channel}". See `_month_key`'s docstring for the resolution order.

WHAT THIS IS. TWO entry points write into the same rollup documents:

  record_session_end(...) -- called from the SAME teardown block in
  backend/routes/websocket_routes.py that already runs log_form_session_end
  and _bank_link_spend, on every connection teardown. Writes ONE BATCHED set
  of firestore.Increment updates -- both docs committed together via
  db.batch() -- so a mid-write failure cannot leave a firm's counters bumped
  with no matching kit counters (or vice versa):

    firms/{firm_id}/usage/{YYYY-MM[_channel]}:
      connections_ended, sessions_completed, cost_usd_total,
      by_kit.{kit_id}.{sessions,cost_usd},
      by_employee.{uid}.{sessions,cost_usd},
      by_language.{code}.{sessions,cost_usd}, kind, channel

    kits/{kit_id}/usage/{YYYY-MM[_channel]}:
      connections_ended, sessions_completed, cost_usd_total,
      by_firm.{firm_id}.{sessions,cost_usd}, kind, channel

  record_link_opened(...) / record_link_completed(...) -- called from
  backend/services/link_redemptions.py's open_link() and complete_link(),
  the existing best-effort hooks for a client link's lifecycle. Each is a
  SINGLE Increment on the firm-month doc only (links_opened /
  links_completed): a link's kit/employee/language are already counted by
  record_session_end at the connection that redeemed it, so these two do not
  duplicate that side -- they add the two counters record_session_end has no
  way to produce (open and complete are redemption-record events, not
  connection-teardown events, and a link can be opened without a session
  ever completing).

`connections_ended` is the HONEST name (not `sessions_ended`): this fires
once per CONNECTION teardown, and a reconnect is a second connection for the
same logical session -- exactly the distinction
docs/standards/confirmation-and-audit.md already documents for
log_form_session_end. `sessions_completed` increments only when this
connection's teardown carries completion_status == "completed", mirroring
that same field on the per-connection audit row so the two counts are
readable against each other.

HYPHENATED MAP KEYS BREAK DOTTED STRING FIELD PATHS -- AND THE TWO FIRESTORE
WRITE APIS BREAK ON THEM DIFFERENTLY, WHICH IS THE PART THAT IS EASY TO GET
WRONG BY TESTING ONLY ONE. This module writes with
`batch.set(ref, data, merge=True)`, chosen over `update()` because the
FIRST write of a new month document must CREATE it: `update()` defaults to
an exists=True precondition and raises on a document that is not there yet,
which for a brand-new firm/kit-month doc is the common case, not the
exception. set(merge=True) does NOT dot-expand a flat string key at all -- google.cloud.firestore_v1's merge extractor calls
extract_fields(document_data, prefix_path) with expand_dots defaulting to
False, so a key like "by_kit.i-90.sessions" (or even a properly-escaped
FieldPath(...).to_api_repr() string, which is what `update()` -- a
DIFFERENT extractor -- needs) is stored as ONE literal top-level field
NAMED "by_kit.i-90.sessions", not the nested path by_kit -> i-90 ->
sessions. That failure mode has NOTHING to do with hyphens -- it silently
mis-nests EVERY map key, hyphenated or not, the moment a flat dotted string
is handed to set(merge=True). Confirmed against the vendored SDK source
(backend/.venv/Lib/site-packages/google/cloud/firestore_v1/_helpers.py,
DocumentExtractorForMerge._get_document_iterator vs. ...ForUpdate's, the
latter passing expand_dots=True) before writing a line of this module.

So every nested increment here is built as a REAL nested dict via
_nest_increment(), which walks a FieldPath's `.parts` (the raw, unescaped
segment strings -- never serialized through a dotted string at any point)
and creates one dict level per segment. Because no string-splitting ever
happens, a segment containing a hyphen, a literal dot, or a backtick is
equally safe -- there is no path syntax for any of those characters to be
mis-parsed by. FieldPath is still the RIGHT tool even though its
to_api_repr() string form goes unused: `.parts` is what makes "one segment
per map level, whatever characters that segment contains" a property of the
type rather than a convention this module would otherwise have to maintain
by hand (i.e. the "shared sanitizer" alternative the bead allows -- FieldPath
already IS that sanitizer's parts-splitting half). Pinned by
test_usage_rollups.py's hyphenated-kit-id and hyphenated-language-code
cases, which assert on the REAL nested dict shape a fake Firestore merge
would receive, not a hand-typed dotted string.

BEST-EFFORT, NEVER RAISES. Same contract as alerts.py and
_bank_link_spend: this runs inside websocket_routes.py's teardown `finally`
block, so a Firestore hiccup here must not stop the OTHER teardown steps
(session-end telemetry, link completion, spend banking) or crash the
connection close. Every exception is caught here; nothing propagates.

NO IAM CHANGE. This writes through the SAME get_db() (firebase_admin's
Firestore client) every other backend Firestore write in this codebase uses
-- the public backend's runtime service account already has whatever
Firestore permission that client needs (it already writes firms/{firm_id}
ledger entries, links, link_redemptions, alerts). See CLAUDE.md scar #7: a
NEW external API would need an IAM check; this is the same client, same
project, a new document shape under collections the service account already
writes into.

NO SHARDING. The documented escape hatch, matching link_spend.py and
credit_ledger.py's own reasoning: 1 write/s/doc is only threatened by many
sessions ending on the SAME firm+month or kit+month in the same second, and
the existing per-firm/per-kit counters in this codebase use the identical
unsharded Increment pattern. If contention becomes real, shard the doc id
(YYYY-MM-{n}) and sum shards on read -- not needed now.

by_employee KEYS ON THE LINK'S employee_id, OR THE STAFF uid, WHICHEVER
EXISTS -- never both, never neither for a session that has one. A client-
link session has no signed-in uid; a staff session has no link_employee_id.
The caller (websocket_routes.py) resolves which one applies before calling
this module, mirroring log_form_session_end's own employee_id parameter.

ASCII only.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

_log = structlog.get_logger().bind(module="usage_rollups")

FIRMS_COLLECTION = "firms"
KITS_COLLECTION = "kits"
USAGE_SUBCOLLECTION = "usage"

# Mirrors form_kit_routes.py's _KIT_ID_RE exactly (bd polyglot-pdf-sbfk /
# 0dsv4 -- "id becomes a path segment" hardening). NOT imported from there:
# form_kit_routes is a route module (FastAPI, Depends, HTTPException) and
# this is a service that must stay importable with no FastAPI app running;
# pulling a route module into a service is the wrong direction for that
# dependency to point. Duplicated on purpose, same charset.
_KIT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _safe_kit_id(kit_id: Optional[str]) -> Optional[str]:
    """Return kit_id if it is a safe single Firestore path segment, else
    None.

    On a STAFF session (not a client link) the handshake's kit_id is raw,
    unvalidated client input -- websocket_routes.py's client-link branch
    overrides it with the signed token's link_kit_id, but that guard does
    not run for staff, so this module is the only place left to check it
    before it becomes `db.collection("kits").document(kit_id)` (Opus
    cross-surface, bd polyglot-pdf-w828m finding 1). `.document()` does not
    reject embedded slashes -- an even number of them (e.g. "a/b/c") commits
    successfully to a collection this module never intended to touch, and a
    single slash raises ValueError only because Firestore then sees an ODD
    path length, not because the slash itself was rejected. Never raises
    (this module's contract): an invalid kit_id degrades to "treat this
    connection as kit-less", exactly like a genuinely absent one, rather
    than failing the whole rollup write or being tolerated as a valid id.
    """
    if not kit_id or not isinstance(kit_id, str):
        return None
    if ".." in kit_id or not _KIT_ID_RE.fullmatch(kit_id):
        _log.warning("usage_rollup_invalid_kit_id_dropped", kit_id=kit_id[:200])
        return None
    return kit_id


def _month_key(stamp: float, channel: Optional[str] = None) -> str:
    """The rollup document id for both collections: YYYY-MM in UTC, suffixed
    by channel for every channel except the demo default.

    Staging and demo share one Firestore project (docs/technical_guide.md,
    CLAUDE.md "Deployment / promotion"), so a bare "YYYY-MM" id would let a
    staging test-drive increment the SAME document the demo's billing view
    reads -- this doc is a shared AGGREGATE counter, not an append-only row,
    so there is no way to filter staging traffic back out at read time the
    way credit_ledger.py's per-entry `channel` field allows (that module's
    own docstring: "channel on an entry is a record of WHERE a debit
    happened, not a partition key" -- a distinction that does NOT transfer
    to a counter that overwrites in place). Mirrors the established
    channel-suffix convention from bd polyglot-pdf-3q9qn
    (link_redemptions._collection_name / links_store._collection_name):
    the demo keeps the bare id so nothing already written is orphaned,
    every other channel gets its own suffixed id.

    `channel=None` (the two callers that have not been given a channel
    explicitly cannot happen in production -- see record_session_end's own
    channel parameter, which is required) falls back to link_channel(),
    this process's own channel, matching link_redemptions' default-
    resolution pattern.
    """
    from backend.services.link_tokens import DEFAULT_CHANNEL, link_channel

    month = datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m")
    resolved = channel if channel is not None else link_channel()
    return month if resolved == DEFAULT_CHANNEL else f"{month}_{resolved}"


def _nest_increment(target: dict[str, Any], *parts: str, amount) -> None:
    """Set target[parts[0]][parts[1]]...[parts[-1]] = amount, creating every
    intermediate dict level along the way.

    THE LOAD-BEARING FUNCTION OF THIS MODULE. `parts` are map-key segments
    that may contain hyphens (a kit id like "i-90"), a BCP-47 hyphen (a
    language code like "zh-CN"), or in principle any other string a caller
    passes as an id. Routed through google.cloud.firestore_v1.field_path.
    FieldPath(*parts).parts rather than used directly: FieldPath validates
    the segments the same way the rest of this codebase's Firestore writes
    implicitly rely on (non-empty, no accidental empty-string segment from a
    stray double-dot upstream), and `.parts` is the raw, UNESCAPED tuple of
    segment strings -- nothing here ever passes through a dotted string, so
    there is no path syntax for a hyphen, dot, or backtick in a segment to
    be mis-parsed by. See the module docstring for why this must build a
    real nested dict rather than a flat FieldPath.to_api_repr() string key:
    set(merge=True) (the write API this module uses, for its create-on-
    first-write behavior) does not dot-expand a flat key at all.
    """
    from google.cloud.firestore_v1.field_path import FieldPath
    from firebase_admin import firestore

    segments = FieldPath(*parts).parts
    cur = target
    for segment in segments[:-1]:
        cur = cur.setdefault(segment, {})
    cur[segments[-1]] = firestore.Increment(amount)


def _get_db():
    """The Admin-SDK Firestore client, or None if it cannot be reached.

    Lazy-imported and NEVER RAISES, matching alerts.py's own _collection()
    convention: this module must be importable with no firebase_admin app
    initialized, and a broken app must degrade to "skip the write" rather
    than crash the caller.
    """
    try:
        from backend.services.auth import get_db

        return get_db()
    except Exception as exc:  # noqa: BLE001 -- best-effort, never raise
        _log.error("usage_rollups_get_db_failed", error=str(exc))
        return None


def record_session_end(
    *,
    firm_id: Optional[str],
    kit_id: Optional[str],
    employee_id: Optional[str],
    language: Optional[str],
    channel: str,
    kind: str,
    completion_status: str,
    cost_usd: float,
    now: Optional[float] = None,
) -> bool:
    """Write one batched usage-rollup update for a connection teardown.

    Called from websocket_routes.py's teardown block, best-effort, on EVERY
    connection close that has a firm_id (a session with no firm cannot be
    attributed to a rollup at all -- there is nothing to increment). A
    session with no kit_id still writes the firm-side doc; a session with no
    firm_id writes NOTHING (both docs are firm/kit KEYED, so a firm-less
    session has no document to bump).

    `completion_status` mirrors log_form_session_end's own literal
    ("completed" | "abandoned" | "error"): only "completed" increments
    sessions_completed, matching that sibling record's own semantics so the
    two are comparable.

    `employee_id` is the CALLER-RESOLVED attribution (the link's
    employee_id for a client-link session, the staff uid for a staff
    session) -- this function does not choose between them; see the module
    docstring.

    Returns True when a write was attempted and did not raise, False when
    skipped (no firm_id, no Firestore client) or when the write failed.
    NEVER RAISES either way -- the return value is for tests and logging
    only, never a signal a caller must branch on.
    """
    if not firm_id:
        # No firm to attribute this connection to -- both target documents
        # are firm/kit-keyed, so there is nothing to increment. Mirrors
        # log_form_session_end's own firm_id=None sessions, which still log
        # the audit row (attribution-free rows are valid there); a rollup
        # has no such "unattributed" bucket to write into.
        return False

    # kit_id becomes a Firestore document-path segment AND a by_kit map key
    # below -- validate it here, once, before either use. A client-link
    # session's kit_id is already safe (websocket_routes.py's client-link
    # branch overrides the handshake value with the signed token's
    # link_kit_id), but a STAFF session's kit_id is raw handshake input with
    # no such guard, and this module is the last stop before .document()
    # (see _safe_kit_id's docstring). An invalid id degrades to kit-less,
    # same as one that was never provided -- it does not fail the firm-side
    # write.
    kit_id = _safe_kit_id(kit_id)

    stamp = float(now if now is not None else time.time())
    month = _month_key(stamp, channel)
    cost = float(cost_usd) if cost_usd and cost_usd > 0 else 0.0
    completed = completion_status == "completed"

    db = _get_db()
    if db is None:
        return False

    try:
        from firebase_admin import firestore

        batch = db.batch()

        firm_updates: dict[str, Any] = {
            "connections_ended": firestore.Increment(1),
            "kind": kind,
            "channel": channel,
        }
        if completed:
            firm_updates["sessions_completed"] = firestore.Increment(1)
        if cost > 0:
            firm_updates["cost_usd_total"] = firestore.Increment(cost)
        if kit_id:
            _nest_increment(firm_updates, "by_kit", kit_id, "sessions", amount=1)
            if cost > 0:
                _nest_increment(firm_updates, "by_kit", kit_id, "cost_usd", amount=cost)
        if employee_id:
            _nest_increment(firm_updates, "by_employee", employee_id, "sessions", amount=1)
            if cost > 0:
                _nest_increment(firm_updates, "by_employee", employee_id, "cost_usd", amount=cost)
        if language:
            _nest_increment(firm_updates, "by_language", language, "sessions", amount=1)
            if cost > 0:
                _nest_increment(firm_updates, "by_language", language, "cost_usd", amount=cost)

        firm_ref = (
            db.collection(FIRMS_COLLECTION)
            .document(firm_id)
            .collection(USAGE_SUBCOLLECTION)
            .document(month)
        )
        batch.set(firm_ref, firm_updates, merge=True)

        if kit_id:
            kit_updates: dict[str, Any] = {
                "connections_ended": firestore.Increment(1),
                "kind": kind,
                "channel": channel,
            }
            if completed:
                kit_updates["sessions_completed"] = firestore.Increment(1)
            if cost > 0:
                kit_updates["cost_usd_total"] = firestore.Increment(cost)
            _nest_increment(kit_updates, "by_firm", firm_id, "sessions", amount=1)
            if cost > 0:
                _nest_increment(kit_updates, "by_firm", firm_id, "cost_usd", amount=cost)

            kit_ref = (
                db.collection(KITS_COLLECTION)
                .document(kit_id)
                .collection(USAGE_SUBCOLLECTION)
                .document(month)
            )
            batch.set(kit_ref, kit_updates, merge=True)

        batch.commit()
    except Exception as exc:  # noqa: BLE001 -- best-effort, never raise
        _log.error(
            "usage_rollup_write_failed",
            firm_id=firm_id,
            kit_id=kit_id,
            error=str(exc),
        )
        return False

    _log.info(
        "usage_rollup_written",
        firm_id=firm_id,
        kit_id=kit_id,
        month=month,
        completed=completed,
        cost_usd=round(cost, 6),
    )
    return True


def _increment_firm_counter(
    firm_id: Optional[str], field: str, *, now: Optional[float] = None,
) -> bool:
    """Shared body for record_link_opened/record_link_completed: bump ONE
    top-level counter on firms/{firm_id}/usage/{YYYY-MM[_channel]}. Never
    raises.

    No `channel` parameter: both callers (open_link, complete_link) run only
    on the public backend, which has exactly one channel of its own -- so
    `_month_key`'s channel=None default (this process's own link_channel())
    is always the right one here, the same default-resolution the sibling
    `link_redemptions._collection()` uses. See `_month_key`'s docstring for
    why the id is channel-suffixed at all.
    """
    if not firm_id:
        return False
    db = _get_db()
    if db is None:
        return False
    try:
        from firebase_admin import firestore

        stamp = float(now if now is not None else time.time())
        ref = (
            db.collection(FIRMS_COLLECTION)
            .document(firm_id)
            .collection(USAGE_SUBCOLLECTION)
            .document(_month_key(stamp))
        )
        ref.set({field: firestore.Increment(1)}, merge=True)
    except Exception as exc:  # noqa: BLE001 -- best-effort, never raise
        _log.error(
            "usage_rollup_link_counter_failed", firm_id=firm_id, field=field,
            error=str(exc),
        )
        return False
    return True


def record_link_opened(firm_id: Optional[str], *, now: Optional[float] = None) -> bool:
    """A client link's FIRST open (link_redemptions.open_link). Increments
    firms/{firm_id}/usage/{YYYY-MM}.links_opened by 1. Best-effort, never
    raises: called from open_link(), which is itself on the paid-session-
    start path and must not fail a real open over a bookkeeping write.
    """
    return _increment_firm_counter(firm_id, "links_opened", now=now)


def record_link_completed(firm_id: Optional[str], *, now: Optional[float] = None) -> bool:
    """A client link's completion (link_redemptions.complete_link).
    Increments firms/{firm_id}/usage/{YYYY-MM}.links_completed by 1.
    Best-effort, never raises: called from complete_link(), which is itself
    best-effort so as not to jeopardize the client's already-finished work.
    """
    return _increment_firm_counter(firm_id, "links_completed", now=now)
