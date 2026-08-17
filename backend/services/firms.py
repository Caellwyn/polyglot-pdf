"""Firms datastore access (bd polyglot-pdf-lo88, epic polyglot-pdf-02ye).

The firm tier's identity backbone: one Firestore document per customer firm
(firms/{firm_id}) holding the profile and the allowed-kits list that
firm-scoped kit visibility (bd polyglot-pdf-vccy) gates on. Access is
Admin-SDK-only -- firestore.rules carries an explicit client deny block for
firms/** as defense in depth.

READ CONTRACT -- FAIL CLOSED. get_allowed_kits() returns [] on EVERY failure
branch: store disabled (FIRMS_FIRESTORE_ENABLED unset/false), firm missing,
firm not active, malformed doc, or any read error (logged loudly, never
raised). This is the deliberate INVERSE of the confirmation sink's fail-open
writes (backend/utils/confirmation_logger.py, where a lost mirror write
degrades durability, not behavior): a broken firms store must never WIDEN
private-kit visibility, so every failure resolves to "this firm may see zero
private kits".

WRITE CONTRACT. upsert_firm() is NOT gated by the env var and RAISES on
failure: it is called only by the operator bootstrap script
(scripts/bootstrap_firm.py), and an explicitly-invoked admin tool must fail
loudly, never silently no-op.

Doc shape (firms/{firm_id}):
    name: str              contact_email: str
    allowed_kits: [kit_id, ...]
    status: "active" | "suspended"
    created_at, updated_at: server timestamps
Deferred by design: token_hash (magic-link bead polyglot-pdf-ugm6), usage
rollups (queried from confirmation_events by firm_id, never stored here).
Staff membership lives ONLY as firm_id/firm_role custom claims on the staff
Firebase accounts -- no roster on this doc (one source of truth).
"""
import os

import structlog

_log = structlog.get_logger().bind(module="firms")

_FIRMS_COLLECTION = "firms"

FIRM_STATUS_ACTIVE = "active"
FIRM_STATUS_SUSPENDED = "suspended"


def _firms_enabled() -> bool:
    """Env-resolved per call (mirrors confirmation_logger._firestore_enabled)
    so tests and deploys control it without an import-order dance.

    Deploy wiring of FIRMS_FIRESTORE_ENABLED lands with the consumer bead
    (vccy), not here -- see the site enumeration in the lo88 plan.
    """
    return os.getenv("FIRMS_FIRESTORE_ENABLED", "false").lower() == "true"


def get_allowed_kits(firm_id: str) -> list[str]:
    """Return the kit_ids this firm may see beyond public kits.

    FAIL CLOSED: returns [] -- never None, never raises -- when the store is
    disabled, the firm is missing or not active, the stored allowed_kits is
    not a list of strings, or the read fails (logged loudly). A caller gating PRIVATE
    kit visibility on this must treat [] as "this firm may see zero private
    kits" -- which is exactly what a fail-closed default requires.
    """
    if not _firms_enabled():
        return []
    try:
        # Lazy import: keeps firebase_admin out of this module's import chain
        # and makes the client patchable at backend.services.auth.get_db
        # (same pattern as confirmation_logger._firestore_write).
        from backend.services.auth import get_db

        snap = get_db().collection(_FIRMS_COLLECTION).document(firm_id).get()
        if not snap.exists:
            return []
        doc = snap.to_dict() or {}
        if doc.get("status") != FIRM_STATUS_ACTIVE:
            return []
        kits = doc.get("allowed_kits")
        # A list with ANY non-string entry is malformed: fail the whole doc
        # closed rather than partially filtering (the docstring's contract --
        # every failure branch resolves to [], nothing in between).
        if not isinstance(kits, list) or not all(
            isinstance(k, str) for k in kits
        ):
            return []
        return list(kits)
    except Exception as e:
        _log.error("firms_read_failed", firm_id=firm_id, error=str(e))
        return []


def upsert_firm(
    firm_id: str,
    name: str,
    contact_email: str,
    allowed_kits: list[str],
    status: str = FIRM_STATUS_ACTIVE,
) -> dict:
    """Create or update firms/{firm_id}. Operator/bootstrap path ONLY.

    NOT gated by FIRMS_FIRESTORE_ENABLED, and any failure RAISES to the
    caller: the bootstrap script maps that to its exit code 2 rather than
    letting an admin action silently no-op.

    Idempotent re-runs (read-first): a missing doc gets the full payload
    with created_at=SERVER_TIMESTAMP; an existing doc gets
    set(..., merge=True) with updated_at bumped and created_at OMITTED from
    the payload entirely -- a SERVER_TIMESTAMP in the merge payload would
    overwrite the original creation time on every re-run. Full-replace of
    the known fields; there is deliberately no partial-update API.
    """
    from firebase_admin import firestore

    from backend.services.auth import get_db

    ref = get_db().collection(_FIRMS_COLLECTION).document(firm_id)
    snap = ref.get()
    payload = {
        "name": name,
        "contact_email": contact_email,
        "allowed_kits": list(allowed_kits),
        "status": status,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if snap.exists:
        ref.set(payload, merge=True)
        created = False
    else:
        payload["created_at"] = firestore.SERVER_TIMESTAMP
        ref.set(payload)
        created = True
    _log.info(
        "firm_upserted",
        firm_id=firm_id,
        created=created,
        allowed_kits_count=len(allowed_kits),
        status=status,
    )
    return {"firm_id": firm_id, "created": created}


def firms_store_status() -> str:
    """Report whether the firms store can actually be READ.

    The mirror image of confirmation_sink_status's reason to exist: that
    writer fails OPEN (looks healthy while silently writing nothing), this
    reader fails CLOSED -- under IAM drift every firm's private kits vanish
    with no error surfaced anywhere. This probe is the diagnosis handle.

    READ-shaped (limit-1 stream), deliberately NOT the sink probe's
    write+delete: this path never needs write permission, and probing with a
    write would test the wrong grant. Returns "disabled", "ok", or
    "error: <msg>". No cache: nothing calls this on a hot path today; the
    bead that wires it to /health adds caching there if needed.
    """
    if not _firms_enabled():
        return "disabled"
    try:
        from backend.services.auth import get_db

        list(get_db().collection(_FIRMS_COLLECTION).limit(1).stream())
        return "ok"
    except Exception as e:
        _log.error("firms_store_probe_failed", error=str(e))
        return f"error: {e}"
