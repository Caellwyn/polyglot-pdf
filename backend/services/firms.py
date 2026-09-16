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
    kind: "mock" | "live"  (required on CREATE; see firm_kind() below)
    balance_credits: int          (materialized; written ONLY by the one
                                    transactional ledger helper,
                                    backend/services/credit_ledger.py -- Epic
                                    2 bead A2. upsert_firm() initializes it to
                                    0 on first create and NEVER touches it on
                                    a re-run, so a re-bootstrap of an existing
                                    firm cannot clobber a real balance.)
    balance_updated_at            (set alongside balance_credits by the same
                                    ledger helper; also 0-initialized here)
    created_at, updated_at: server timestamps

THE BALANCE IS NOT CHANNEL-PARTITIONED: one firm, one balance_credits,
whichever channel's mint debits it. That is safe ONLY because a `live` firm
cannot mint outside the demo channel (Epic 2 bead A3's gate) and a `mock`
firm carries no real money -- so nothing that debits a live firm's balance
can happen on staging, and nothing staging debits matters financially. Do
not read this as "channel doesn't matter here": it matters a great deal, and
the invariant it rests on lives in the mint route, not in this module.

kind DEFAULTING. A firm doc with NO `kind` key -- the window between this
code deploying and the backfill migration (Epic 2 bead A6) running -- is
treated as `live` by firm_kind() below. This is the deliberately
conservative direction: a mis-defaulted `mock` firm merely blocks staging
testing, while a mis-defaulted `live` firm mints for free. Every firm
created from here on (scripts/bootstrap_firm.py, which now requires
--kind) carries an explicit kind; only pre-migration docs and hand-crafted
test fixtures ever hit the missing-key fallback in production.

Deferred by design: token_hash (magic-link bead polyglot-pdf-ugm6), usage
rollups (queried from confirmation_events by firm_id, never stored here).
Staff membership lives ONLY as firm_id/firm_role custom claims on the staff
Firebase accounts -- no roster on this doc (one source of truth).
"""
import os
import threading
import time
from typing import Optional

import structlog

_log = structlog.get_logger().bind(module="firms")

_FIRMS_COLLECTION = "firms"

FIRM_STATUS_ACTIVE = "active"
FIRM_STATUS_SUSPENDED = "suspended"

FIRM_KIND_MOCK = "mock"
FIRM_KIND_LIVE = "live"

# The two firm ROLES a staff account can hold (docs/components/auth.md, the
# four-level access model). A manager manages the firm -- its staff, its
# forms; an employee sends links and tracks status.
FIRM_ROLE_MANAGER = "manager"
FIRM_ROLE_EMPLOYEE = "employee"


def manager_firm_id(claims: Optional[dict]) -> Optional[str]:
    """The firm this caller MANAGES, or None if they manage none.

    THE ONE HOME for "who is a firm manager, and which firm are they a
    manager of" (bd polyglot-pdf-dmjl5, CLAUDE.md scar #8). Before this it
    was written inline in backend/routes/form_kit_routes.py's
    _require_firm_owns_private_kit and was about to be written a second time
    on the admin service's user routes; two hand-written copies of an
    authorization rule is how one of them drifts.

    IT LIVES HERE, in the firm-identity module, rather than in
    backend/services/auth.py, so BOTH surfaces can reach it. The admin
    service's admin_auth.py is deliberately liftable -- it must not import
    backend.services.auth or backend.services.editor_auth, pinned by
    admin_backend/tests/unit/test_admin_auth.py::test_admin_auth_does_not_
    import_the_other_two_auth_modules -- and that constraint is about not
    depending on another surface's VERIFIER. This module is neither
    surface's verifier: it is a pure, side-effect-free function over an
    already-verified claims dict, in the module that already owns what a
    firm IS. backend.services.auth re-exports the name so the voice app's
    callers keep reading it from their own auth module.

    THE CALLER MUST HAVE VERIFIED THE TOKEN. This decides authorization, not
    authentication: handed an unverified dict it will happily report a
    manager, because deciding whether the claims are real is the verifier's
    job and doing it twice in two places is how the two disagree.

    Returns the firm_id only when BOTH hold: firm_role is exactly "manager",
    and firm_id is a non-empty string. An employee, a dev with no firm, and a
    client link (which carries no firm claims at all) each get None.
    """
    if not isinstance(claims, dict):
        return None
    firm_id = claims.get("firm_id")
    if not isinstance(firm_id, str) or not firm_id:
        return None
    if claims.get("firm_role") != FIRM_ROLE_MANAGER:
        return None
    return firm_id


def employee_firm_id(claims: Optional[dict]) -> Optional[str]:
    """The firm this caller is an EMPLOYEE of, or None if they are not.

    THE SAME SHAPE as manager_firm_id above, one role over (bd
    polyglot-pdf-scaig): a pure, side-effect-free predicate over an
    already-verified claims dict, living beside the manager rule rather than
    written inline a second time at its one call site (CLAUDE.md scar #8).
    Added because the admin service's link-listing route needed an employee
    actor kind and this repo has already paid once for hand-written copies
    of "who is a firm X" (manager_firm_id's own docstring).

    THE CALLER MUST HAVE VERIFIED THE TOKEN, exactly as manager_firm_id
    requires -- this decides authorization, not authentication.

    Returns the firm_id only when BOTH hold: firm_role is exactly
    "employee", and firm_id is a non-empty string. A manager, a dev with no
    firm, and a client link each get None -- deliberately NOT "not a
    manager", since an app admin or a firm manager token must not also read
    as an employee of their own or any firm.
    """
    if not isinstance(claims, dict):
        return None
    firm_id = claims.get("firm_id")
    if not isinstance(firm_id, str) or not firm_id:
        return None
    if claims.get("firm_role") != FIRM_ROLE_EMPLOYEE:
        return None
    return firm_id


def _firms_enabled() -> bool:
    """Env-resolved per call (mirrors confirmation_logger._firestore_enabled)
    so tests and deploys control it without an import-order dance.

    FIRMS_FIRESTORE_ENABLED is set true in deploy-all.sh's BACKEND_ENV
    (bd polyglot-pdf-vccy, the consumer); the deploy-form-kit.sh drop-list
    hint names it, pinned by tests/test_deploy_form_kit_hints.py.
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
        _log.error("firms_read_failed", firm_id=firm_id, error_type=type(e).__name__)
        return []


def firm_kind(firm_id: str) -> str:
    """Return this firm's kind: "mock" or "live".

    FAILS CLOSED TO "live" -- the OPPOSITE polarity from get_allowed_kits'
    fail-closed-to-[]. A mis-read here (store disabled, firm missing,
    malformed doc, read error) must not let a firm mint for free, so every
    failure branch resolves to the MORE RESTRICTIVE kind: "live", which the
    mint gate (Epic 2 bead A3) then subjects to the demo-channel-only rule.
    A doc with no `kind` key at all -- the pre-backfill window -- gets the
    same treatment, for the same reason (see the module docstring).

    This module's OTHER reader (get_allowed_kits) fails closed to [] because
    widening kit visibility is the risk there; here, widening who can mint
    without the live-firm gate is the risk, and "live" is what applies that
    gate. Same discipline, different value, because the two calls guard
    different failure directions.
    """
    if not _firms_enabled():
        return FIRM_KIND_LIVE
    try:
        from backend.services.auth import get_db

        snap = get_db().collection(_FIRMS_COLLECTION).document(firm_id).get()
        if not snap.exists:
            return FIRM_KIND_LIVE
        doc = snap.to_dict() or {}
        kind = doc.get("kind")
        if kind not in (FIRM_KIND_MOCK, FIRM_KIND_LIVE):
            return FIRM_KIND_LIVE
        return kind
    except Exception as e:
        _log.error("firm_kind_read_failed", firm_id=firm_id, error_type=type(e).__name__)
        return FIRM_KIND_LIVE


def upsert_firm(
    firm_id: str,
    name: str,
    contact_email: str,
    allowed_kits: list[str],
    kind: str,
    status: str = FIRM_STATUS_ACTIVE,
) -> dict:
    """Create or update firms/{firm_id}. Operator/bootstrap path ONLY.

    `kind` is REQUIRED (no default): scripts/bootstrap_firm.py's --kind flag
    is itself required, and this is the write-layer backstop for any other
    caller -- a firm bootstrapped without deciding mock-vs-live is exactly
    the ambiguity firm_kind()'s fail-closed-to-live default exists to absorb
    for docs that predate this bead, not a way to opt out of choosing.

    NOT gated by FIRMS_FIRESTORE_ENABLED, and any failure RAISES to the
    caller: the bootstrap script maps that to its exit code 2 rather than
    letting an admin action silently no-op.

    Idempotent re-runs (read-first): a missing doc gets the full payload
    with created_at=SERVER_TIMESTAMP, balance_credits=0, and
    balance_updated_at=SERVER_TIMESTAMP; an existing doc gets
    set(..., merge=True) with updated_at bumped and created_at,
    balance_credits, balance_updated_at OMITTED from the payload entirely --
    a SERVER_TIMESTAMP in the merge payload would overwrite the original
    creation time on every re-run, and re-including balance_credits=0 would
    zero out a real balance on every re-bootstrap. balance_credits is
    written ONLY by the transactional ledger helper (Epic 2 bead A2) after
    the first create. Full-replace of the known non-balance fields; there is
    deliberately no partial-update API.
    """
    # The CLI's argparse choices= enforce this too, but this is the WRITE
    # layer: a future non-CLI caller passing junk would otherwise store a
    # status that silently fail-closes the firm (get_allowed_kits treats
    # anything != active as inactive).
    if status not in (FIRM_STATUS_ACTIVE, FIRM_STATUS_SUSPENDED):
        raise ValueError(
            f"status {status!r} is not one of "
            f"({FIRM_STATUS_ACTIVE!r}, {FIRM_STATUS_SUSPENDED!r})"
        )
    if kind not in (FIRM_KIND_MOCK, FIRM_KIND_LIVE):
        raise ValueError(
            f"kind {kind!r} is not one of "
            f"({FIRM_KIND_MOCK!r}, {FIRM_KIND_LIVE!r})"
        )
    from firebase_admin import firestore

    from backend.services.auth import get_db

    ref = get_db().collection(_FIRMS_COLLECTION).document(firm_id)
    snap = ref.get()
    payload = {
        "name": name,
        "contact_email": contact_email,
        "allowed_kits": list(allowed_kits),
        "status": status,
        "kind": kind,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if snap.exists:
        ref.set(payload, merge=True)
        created = False
    else:
        payload["created_at"] = firestore.SERVER_TIMESTAMP
        payload["balance_credits"] = 0
        payload["balance_updated_at"] = firestore.SERVER_TIMESTAMP
        ref.set(payload)
        created = True
    _log.info(
        "firm_upserted",
        firm_id=firm_id,
        created=created,
        allowed_kits_count=len(allowed_kits),
        status=status,
        kind=kind,
    )
    return {"firm_id": firm_id, "created": created}


# Probe cache for firms_store_status (monotonic timestamp, status), and the
# in-flight Event that coalesces concurrent callers onto ONE round trip.
# Same shape and the same reason as confirmation_sink_status's
# (backend/utils/confirmation_logger.py, bd polyglot-pdf-fzwp): /health is
# UNAUTHENTICATED (backend/main.py), so any caller can drive this probe at
# their own request rate. Without the coalescing, N concurrent /health polls
# on a cold or stale cache each fall through to their OWN Firestore round
# trip -- and a stalled Firestore, which is exactly the outage this probe
# exists to detect, is when that pile-up is worst.
_probe_cache: Optional[tuple] = None
_probe_lock = threading.Lock()
_probe_in_flight: Optional[threading.Event] = None


def firms_store_status(max_age_s: float = 300.0) -> str:
    """Report whether the firms store can actually be READ.

    The mirror image of confirmation_sink_status's reason to exist: that
    writer fails OPEN (looks healthy while silently writing nothing), this
    reader fails CLOSED -- under IAM drift every firm's private kits vanish
    with no error surfaced anywhere. This probe is the diagnosis handle.

    READ-shaped (limit-1 stream), deliberately NOT the sink probe's
    write+delete: this path never needs write permission, and probing with a
    write would test the wrong grant. Returns "disabled", "ok", or
    "error: <msg>".

    CACHED + COALESCED (bd polyglot-pdf-vq5wd, wired into /health by bd
    polyglot-pdf-e4dt8). The cache bounds how often an unauthenticated caller
    can reach Firestore through /health; the in-flight Event bounds how many
    can do so AT ONCE. The caller (/health) additionally wraps this in an
    asyncio.wait_for, because neither guard makes a stalled Firestore return.
    """
    global _probe_cache, _probe_in_flight

    if not _firms_enabled():
        return "disabled"

    with _probe_lock:
        if _probe_cache and (time.monotonic() - _probe_cache[0]) < max_age_s:
            return _probe_cache[1]
        if _probe_in_flight is not None:
            in_flight = _probe_in_flight
            we_are_prober = False
        else:
            # Claim the probe BEFORE releasing the lock, so no other thread
            # starts a duplicate round trip.
            in_flight = _probe_in_flight = threading.Event()
            we_are_prober = True

    if not we_are_prober:
        # Bounded WELL UNDER /health's own 3.0s wait_for budget. asyncio's
        # wait_for does NOT cancel the underlying to_thread worker on
        # timeout -- it just stops awaiting it -- so a waiter blocked here
        # past that deadline keeps occupying a thread-pool slot it can no
        # longer usefully return through (the lesson bd polyglot-pdf-fzwp
        # round 2 learned on the confirmation probe).
        in_flight.wait(timeout=2.0)
        with _probe_lock:
            if _probe_cache:
                return _probe_cache[1]
        # REACHABLE, not dead code: a genuinely stalled prober -- the outage
        # this probe exists to detect -- is still running past our wait.
        return "error: probe coalescing timed out waiting for another in-flight probe"

    try:
        from backend.services.auth import get_db

        list(get_db().collection(_FIRMS_COLLECTION).limit(1).stream())
        status = "ok"
    except Exception as e:
        _log.error("firms_store_probe_failed", error_type=type(e).__name__)
        # Class only: /health returns this verbatim to anyone (sprint 23 B1b).
        status = f"error: {type(e).__name__}"

    with _probe_lock:
        _probe_cache = (time.monotonic(), status)
        _probe_in_flight = None
    in_flight.set()
    return status
