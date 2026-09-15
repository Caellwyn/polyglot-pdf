"""GET /admin/audit -- read the append-only audit log (bd polyglot-pdf-li9x0).

The READ half of the log admin_backend/services/audit_log.py writes. An
audit trail nobody can read is a compliance artifact, not a control: the
console's audit-log list page (bead 1.7) is this route's first consumer, and
the maintainer's "who granted this" question is answered here.

NEWEST FIRST, and paginated by an opaque cursor rather than an offset.
Firestore has no OFFSET that skips server-side work -- offset(n) still reads
and bills the n skipped documents -- so a deep page would get slower and
dearer the further back an operator scrolled. The cursor is the last row's
(ts, doc_id) pair, which start_after consumes directly; doc_id breaks the tie
when two rows share a millisecond, so a page boundary can neither repeat nor
drop a row.

FILTERS are deliberately few: action, actor_uid, channel, state. Each is an
equality filter combined with the ts ordering, which Firestore serves ONLY
from a COMPOSITE INDEX -- an unindexed one fails at runtime with
FAILED_PRECONDITION while every local test passes, because the test fake
filters and sorts in Python (CLAUDE.md scar #7, applied to indexes rather
than IAM). The four indexes therefore SHIP, in firestore.indexes.json, wired
through firebase.json and deployed by deploy-demo.sh; the set is pinned
against this route's filter list by
admin_backend/tests/unit/test_firestore_indexes.py, so a FIFTH filter added
here without its index fails CI. The unfiltered default view needs no
composite (single-field auto-index on ts), which is exactly why the gap
would otherwise stay invisible until an operator first used a filter.

Free-text search over `target` is NOT offered -- Firestore cannot do it, and
faking it with a client-side scan over an unbounded collection is how a
console page becomes a bill.

READS ARE NOT AUDITED. The log records mutations; a row per read would bury
them under the console's own polling.

ASCII only.
"""
from __future__ import annotations

from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin

_log = structlog.get_logger().bind(module="admin_audit_routes")

router = APIRouter()

# Page size bounds. The default is what the console's list page asks for; the
# max stops a caller turning one request into a full-collection read (the
# collection grows without bound -- nothing prunes it, by design).
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# The cursor's two halves, joined by a character that cannot appear in a
# Firestore auto-id (which is [A-Za-z0-9] only). A colon would be ambiguous
# the day a doc id contains one; this cannot be.
_CURSOR_SEP = "|"


def _encode_cursor(row: dict) -> Optional[str]:
    ts = row.get("ts")
    doc_id = row.get("doc_id")
    if ts is None or not doc_id:
        return None
    return "{}{}{}".format(ts, _CURSOR_SEP, doc_id)


def _decode_cursor(cursor: str) -> list:
    """The (ts, doc_id) pair start_after needs, or a 400.

    A malformed cursor is the caller's error, not a reason to silently serve
    page one again -- an operator paging through an audit trail must never be
    quietly rewound to the top without noticing.
    """
    parts = cursor.split(_CURSOR_SEP)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="malformed cursor")
    try:
        ts = float(parts[0])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="malformed cursor")
    if not parts[1]:
        raise HTTPException(status_code=400, detail="malformed cursor")
    return [ts, parts[1]]


@router.get("/admin/audit")
async def list_audit_rows(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    action: Optional[str] = None,
    actor_uid: Optional[str] = None,
    channel: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: Optional[str] = None,
) -> dict:
    """One page of audit rows, newest first.

    `next_cursor` is null on the last page. A caller that keeps passing the
    returned cursor walks the whole log; a caller that ignores it sees only
    the newest page, which is the console's default view.
    """
    if state is not None and state not in audit_log.STATES:
        raise HTTPException(
            status_code=400,
            detail="state must be one of {}".format(sorted(audit_log.STATES)),
        )

    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="audit store unavailable")

    # FieldFilter rather than the positional where(): newer
    # google-cloud-firestore deprecates the positional form (the same import
    # backend/utils/confirmation_logger.py already makes for the same
    # reason).
    from google.cloud.firestore_v1.base_query import FieldFilter
    # Lazy, matching every other google.* import in this route/service
    # (this file's own FieldFilter above, get_db() below; sweep_routes.py,
    # link_routes.py, credit_ledger.py, usage_rollups.py) -- admin_backend/
    # main.py imports this module at module scope, so a module-scope
    # google.* import here would take down all 13 routers on an ImportError
    # instead of only this one route (bd polyglot-pdf-8uraj).
    from google.api_core.exceptions import FailedPrecondition, InvalidArgument

    try:
        query = db.collection(audit_log.COLLECTION)
        for field, value in (
            ("action", action),
            ("actor_uid", actor_uid),
            ("channel", channel),
            ("state", state),
        ):
            if value is not None:
                query = query.where(filter=FieldFilter(field, "==", value))
        # doc_id is the tiebreaker for the cursor -- __name__ is Firestore's
        # name for the document id in an order_by, and ordering by it makes
        # the (ts, doc_id) start_after pair total.
        query = query.order_by("ts", direction="DESCENDING").order_by(
            "__name__", direction="DESCENDING")
        if cursor:
            query = query.start_after(_decode_cursor(cursor))
        # One extra document tells us whether a next page exists without a
        # second round trip or a count query.
        docs = list(query.limit(limit + 1).stream())
    except HTTPException:
        raise
    except (FailedPrecondition, InvalidArgument) as exc:
        # A CLIENT-DIAGNOSABLE query problem, not a store outage -- most
        # often a missing composite index (FAILED_PRECONDITION, whose
        # message carries a console URL that creates it in one click) or a
        # malformed cursor (INVALID_ARGUMENT). Reporting this as the same
        # 503 as a genuine Firestore outage tells the operator "wait" when
        # the real answer is "click this link" or "the cursor is bad" --
        # see the module docstring's own note on why an unindexed filter
        # fails only at runtime. 400 (not 503): the caller can act on it.
        _log.error("admin_audit_read_failed", error=str(exc))
        raise HTTPException(
            status_code=400,
            detail="AUDIT_QUERY_ERROR: {}".format(exc))
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_audit_read_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="audit store unavailable")

    has_more = len(docs) > limit
    rows = []
    for snap in docs[:limit]:
        row = snap.to_dict() or {}
        row["doc_id"] = snap.id
        rows.append(row)

    return {
        "rows": rows,
        "next_cursor": _encode_cursor(rows[-1]) if (has_more and rows) else None,
    }
