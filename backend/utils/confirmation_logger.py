"""
Confirmation logging for liability protection.

Logs field confirmations with timestamps (NO PII).
Demonstrates proper confirmation workflow for legal defense.

CRITICAL: Only log metadata, NEVER log actual field values or user data.

Durability (bd polyglot-pdf-z2is): the local JSONL file is a dev convenience --
on Cloud Run the filesystem is ephemeral tmpfs and the service scales to zero,
so file-only confirmation logs did NOT survive production. When
CONFIRMATION_FIRESTORE_ENABLED=true (set in the deploy env), every event is
ALSO mirrored to the `confirmation_events` Firestore collection via a
fire-and-forget background writer, so the liability trail is durable and
retrievable per form-session. Events are metadata-only (field ids, methods,
timestamps -- never values), so this persistence does not touch the
stateless/no-PII invariant (docs/standards/stateless-architecture.md).
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import structlog
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Literal

_log = structlog.get_logger().bind(module="confirmation_logger")

# Confirmation log directory (separate from application logs). Overridable via
# the CONFIRMATION_LOG_DIR env var so tests can redirect writes to a tmp dir
# instead of the repo tree. Resolved per-call (not cached at import) so the env
# var / a test fixture can set it after this module is imported.
_DEFAULT_CONFIRMATION_LOG_DIR = "logs/confirmations"

# Firestore mirror (bd polyglot-pdf-z2is). Env-resolved per call, like the dir,
# so tests and deploys control it without an import-order dance.
_FIRESTORE_COLLECTION = "confirmation_events"

# Single background writer so the voice hot path (callback_handler's confirm
# round-trip) never blocks on a network write. ThreadPoolExecutor threads are
# non-daemon, so queued writes drain on interpreter exit (graceful shutdown).
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def _confirmation_log_dir() -> Path:
    """Return the confirmation-log directory, creating it if needed."""
    log_dir = Path(os.getenv("CONFIRMATION_LOG_DIR", _DEFAULT_CONFIRMATION_LOG_DIR))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _firestore_enabled() -> bool:
    return os.getenv("CONFIRMATION_FIRESTORE_ENABLED", "false").lower() == "true"


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="confirmation-sink"
            )
        return _executor


def flush_confirmation_sink() -> None:
    """Drain pending Firestore writes (tests + graceful shutdown).

    Loops swap-then-drain until no executor remains (bd polyglot-pdf-wv3j):
    shutdown(wait=True) runs OUTSIDE the lock (so submitters aren't blocked on
    a long drain), which means a concurrent _submit_firestore_write can lazily
    create a FRESH executor while the swapped-out one drains. A single-pass
    flush would return with that sibling alive and its write undrained; the
    loop re-checks and drains it too, so the post-condition "no live executor,
    nothing queued" actually holds.
    """
    global _executor
    while True:
        with _executor_lock:
            executor, _executor = _executor, None
        if executor is None:
            return
        executor.shutdown(wait=True)


def _firestore_write(event: dict) -> None:
    """Write one confirmation event to Firestore (runs on the sink thread).

    Failures are logged LOUDLY (error level -> Cloud Logging) but never raised:
    the voice session must not die because the audit mirror hiccupped. The
    parallel structlog line in the caller already reached Cloud Logging, so a
    failed mirror write degrades durability, not evidence.
    """
    try:
        # Lazy import: keeps firebase_admin out of this module's import chain
        # (unit tests import confirmation_logger without Firestore creds) and
        # makes the client patchable at backend.services.auth.get_db.
        from backend.services.auth import get_db

        doc = dict(event)
        retention_days = os.getenv("CONFIRMATION_RETENTION_DAYS")
        if retention_days:
            # expire_at feeds a Firestore TTL policy. The policy itself is a
            # deploy-time decision gated on counsel's answer to what retention
            # is legally REQUIRED (bd polyglot-pdf-pol2); until the env var is
            # set, events carry no expiry.
            doc["expire_at"] = datetime.now(timezone.utc) + timedelta(
                days=int(retention_days)
            )
        get_db().collection(_FIRESTORE_COLLECTION).add(doc)
    except Exception as e:
        _log.error(
            "confirmation_firestore_write_failed",
            error=str(e),
            form_session_id=event.get("form_session_id"),
            event_type=event.get("event"),
        )


def _submit_firestore_write(event: dict) -> None:
    """Queue a Firestore mirror write; never blocks or raises into the caller."""
    if not _firestore_enabled():
        return
    try:
        _get_executor().submit(_firestore_write, dict(event))
    except RuntimeError:
        # Shutdown race (fresh-eyes on bd z2is): flush_confirmation_sink() can
        # swap+shut the executor between _get_executor() returning and submit()
        # running, and submit-after-shutdown raises RuntimeError. That window is
        # exactly Cloud Run's SIGTERM drain -- the moment a liability event is
        # most likely to matter -- so fall back to a SYNCHRONOUS write instead
        # of dropping it. Blocking briefly is fine mid-shutdown, and
        # _firestore_write never raises (it logs loudly on failure).
        _firestore_write(dict(event))
    except Exception as e:
        _log.error(
            "confirmation_firestore_submit_failed",
            error=str(e),
            form_session_id=event.get("form_session_id"),
        )

# Matches the confirm_field tool's confirmation_method enum (backend/config.py)
# and the values actually written by callback_handler._handle_confirm_field_tool.
ConfirmationMethod = Literal["verbal", "manual"]


def resolve_edition_marker(
    edition_date: Optional[str], schema: Optional[dict]
) -> Optional[str]:
    """Return the revision marker to record, best source first.

    bd polyglot-pdf-47r3. A disputed filing needs to pin WHICH revision of the
    form the client confirmed against.

    1. `edition_date` -- the GOVERNMENT's own revision marker ("12/2024"). The
       right answer for an official form, and the only one an agency recognizes.
    2. A short fingerprint of the kit's field structure (`sha256:<12 hex>`).
       A CUSTOM form -- a firm's proprietary intake sheet, which the firm-tier
       epic exists to support -- has no government edition, and refusing to
       record anything would leave those confirmations unable to pin any
       revision at all. Not human-readable, but stable for a given revision and
       CHANGING when the form changes, which is the property that matters:
       "was this the same version of the form the client saw?".

    The fingerprint covers field ids + types + option values (the answerable
    shape of the form), not labels or guidance prose: a typo fix in help text
    must not read as a different revision, while adding/removing/retyping a
    field or changing an option's value must.

    A THIRD, better source for case 2 is coming: an author-supplied version
    (prefilled with the publish date) plus the marked-complete date, per epic
    bd polyglot-pdf-7jmy. Those live in kit METADATA, which neither the client
    nor this code path currently receives -- reaching them means a manifest/wire
    change or a per-connect storage read, so they are deliberately deferred to
    that epic. `editor_kit_routes` already stamps `metadata.published_at` on
    promotion (shipped here), so the data accumulates until it can be surfaced.

    Returns None when there is neither an edition_date nor a usable schema.
    """
    if isinstance(edition_date, str) and edition_date.strip():
        return edition_date.strip()
    if not isinstance(schema, dict):
        return None

    fields = schema.get("fields")
    if not isinstance(fields, list):
        return None

    import hashlib
    import json as _json

    shape = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        options = field.get("options")
        option_values = (
            sorted(
                str(o.get("value"))
                for o in options
                if isinstance(o, dict) and o.get("value") is not None
            )
            if isinstance(options, list)
            else []
        )
        shape.append([
            str(field.get("id") or ""),
            str(field.get("type") or ""),
            option_values,
        ])
    shape.sort()
    if not shape:
        return None

    digest = hashlib.sha256(
        _json.dumps(shape, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest[:12]}"


def log_field_confirmation(
    form_id: str,
    form_session_id: str,
    field_id: str,
    field_name: Optional[str],
    confirmation_method: ConfirmationMethod,
    kit_id: Optional[str] = None,
    edition_date: Optional[str] = None,
) -> None:
    """
    Log field confirmation event (NO PII).

    Args:
        form_id: Form type identifier (e.g., "I-90", "I-589")
        form_session_id: Persistent form session ID (e.g., "fss_xxx")
        field_id: Field identifier (e.g., "p1_line1_aliennumber")
        field_name: Human-readable field name (e.g., "Alien Registration Number")
        confirmation_method: How field was confirmed
        kit_id: Kit identifier (e.g., "w7") -- the UNIQUE kit key. form_id is a
            form NUMBER and is not unique: two kits can share it (a standard
            W-7 and a firm-specific variant), so only kit_id distinguishes
            them in the record (bd polyglot-pdf-47r3).
        edition_date: The form's government edition (e.g., "12/2024"). Agencies
            revise forms and enforce edition dates, so a disputed filing must be
            able to answer "which edition did the client confirm against?".
            Sourced from form_metadata.edition_date, NOT form_metadata.version --
            `version` is a schema-authoring field whose values differ in meaning
            per kit ("v9_conformant", "draft") and would be misleading here.
        Both default to None so an older client that omits the handshake keys
        degrades to the pre-47r3 record shape rather than erroring.

    CRITICAL: This function MUST NEVER receive or log actual field values or PII.

    Example log entry:
        {
            "timestamp": "2025-11-18T20:30:45.123Z",
            "event": "field_confirmed",
            "form_id": "I-90",
            "kit_id": "i-90",
            "edition_date": "01/20/25",
            "form_session_id": "fss_abc123_xyz789",
            "field_id": "p1_line1_aliennumber",
            "field_name": "Alien Registration Number",
            "confirmation_method": "verbal"
        }
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build confirmation event (NO PII)
    confirmation_event = {
        "timestamp": timestamp,
        "event": "field_confirmed",
        "form_id": form_id,
        # Kit identity + government edition (bd polyglot-pdf-47r3). Always
        # present as keys so every record has a uniform shape; None on an older
        # client that does not send them.
        "kit_id": kit_id,
        "edition_date": edition_date,
        "form_session_id": form_session_id,
        "field_id": field_id,
        "field_name": field_name or field_id,
        "confirmation_method": confirmation_method,
    }

    # Log to structured logger (goes to confirmation logs)
    # Note: event is passed as first arg, so remove it from dict to avoid duplicate
    log_data = {k: v for k, v in confirmation_event.items() if k != "event"}
    _log.info(
        "field_confirmed",
        **log_data
    )

    # Also write to dedicated confirmation log file (one file per form session)
    _write_confirmation_to_file(form_session_id, confirmation_event)
    # ...and mirror to the durable Firestore sink when enabled (bd z2is).
    _submit_firestore_write(confirmation_event)


def _write_confirmation_to_file(form_session_id: str, event: dict) -> None:
    """
    Write confirmation event to dedicated log file.

    One log file per form session for easy correlation.
    File format: logs/confirmations/{form_session_id}.jsonl
    """
    try:
        log_file = _confirmation_log_dir() / f"{form_session_id}.jsonl"

        # Append to JSONL file (one JSON object per line)
        import json
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event) + '\n')

    except Exception as e:
        _log.error("confirmation_log_write_failed", error=str(e), form_session_id=form_session_id)


def log_form_session_start(
    form_id: str,
    form_session_id: str,
    section_id: Optional[str] = None,
) -> None:
    """
    Log start of form filling session.

    Args:
        form_id: Form type (e.g., "I-90")
        form_session_id: Persistent session ID
        section_id: Initial section ID if applicable
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    event = {
        "timestamp": timestamp,
        "event": "form_session_started",
        "form_id": form_id,
        "form_session_id": form_session_id,
        "section_id": section_id,
    }

    # Filter the "event" key: it collides with structlog's positional event
    # name (same pattern as log_field_confirmation). Latent TypeError until the
    # z2is sink tests gave this function its first caller.
    _log.info("form_session_started", **{k: v for k, v in event.items() if k != "event"})
    _write_confirmation_to_file(form_session_id, event)
    _submit_firestore_write(event)


def log_form_session_end(
    form_id: str,
    form_session_id: str,
    completion_status: Literal["completed", "abandoned", "error"],
    total_fields_confirmed: int,
) -> None:
    """
    Log end of form filling session.

    Args:
        form_id: Form type
        form_session_id: Persistent session ID
        completion_status: How session ended
        total_fields_confirmed: Count of fields confirmed in this session
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    event = {
        "timestamp": timestamp,
        "event": "form_session_ended",
        "form_id": form_id,
        "form_session_id": form_session_id,
        "completion_status": completion_status,
        "total_fields_confirmed": total_fields_confirmed,
    }

    _log.info("form_session_ended", **{k: v for k, v in event.items() if k != "event"})
    _write_confirmation_to_file(form_session_id, event)
    _submit_firestore_write(event)


def get_confirmation_log_path(form_session_id: str) -> Path:
    """
    Get path to confirmation log file for a specific form session.

    Useful for retrieving logs for review or legal purposes.
    """
    return _confirmation_log_dir() / f"{form_session_id}.jsonl"


# Probe cache for confirmation_sink_status (monotonic timestamp, status).
_probe_cache: Optional[tuple] = None
_probe_lock = threading.Lock()


def confirmation_sink_status(max_age_s: float = 300.0) -> str:
    """Report whether the Firestore confirmation sink can actually WRITE.

    Round-3 fresh-eyes on bd z2is: without this, IAM drift (e.g. the runtime
    SA losing roles/datastore.user) is detectable only by a manual
    read_confirmations.py run -- the writer logs-and-continues by design, so
    the app looks healthy while the liability trail silently stays empty.
    Surfaced on /health so the standard post-deploy check sees it.

    Returns "disabled" (sink off), "ok" (probe write+delete succeeded), or
    "error: <msg>". The probe writes then deletes a `_health_probe` doc in the
    events collection (a READ would not verify write perms). Result is cached
    for max_age_s so /health polling does not hammer Firestore.
    """
    global _probe_cache
    if not _firestore_enabled():
        return "disabled"
    with _probe_lock:
        if _probe_cache and (time.monotonic() - _probe_cache[0]) < max_age_s:
            return _probe_cache[1]
    try:
        from backend.services.auth import get_db

        ref = get_db().collection(_FIRESTORE_COLLECTION).document("_health_probe")
        ref.set({"probe": True, "ts": datetime.now(timezone.utc)})
        ref.delete()
        status = "ok"
    except Exception as e:
        _log.error("confirmation_sink_probe_failed", error=str(e))
        status = f"error: {e}"
    with _probe_lock:
        _probe_cache = (time.monotonic(), status)
    return status


class ConfirmationReadError(Exception):
    """The Firestore sink could not be QUERIED (perms/ADC/project/transport).

    Distinct from 'the session has no events': for a legal-retrieval surface,
    'the record does not exist' and 'I could not check' must never be the same
    answer (fresh-eyes on bd z2is).
    """


def read_confirmation_log(form_session_id: str, strict: bool = False) -> list[dict]:
    """
    Read all confirmation events for a form session.

    Returns list of confirmation events in chronological order.

    When the Firestore sink is enabled, Firestore is the authoritative source
    (the local file dies with the Cloud Run instance); any events found there
    are returned, sorted by timestamp client-side (an equality-only query needs
    no composite index). The local JSONL file remains the dev-mode fallback.

    strict=True makes a FAILED Firestore query raise ConfirmationReadError
    instead of degrading to the (usually absent) local file -- so an operator
    tool can distinguish 'no events' from 'could not check'. Default False
    preserves the never-raise contract for in-app callers.
    """
    if _firestore_enabled():
        try:
            events = _read_confirmation_log_firestore(form_session_id)
        except ConfirmationReadError:
            if strict:
                raise
            events = []
        if events:
            return events

    log_file = get_confirmation_log_path(form_session_id)

    if not log_file.exists():
        return []

    import json
    events = []
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
    except Exception as e:
        _log.error("confirmation_log_read_failed", error=str(e), form_session_id=form_session_id)

    return events


def _read_confirmation_log_firestore(form_session_id: str) -> list[dict]:
    """Fetch a form-session's events from the Firestore sink.

    Raises ConfirmationReadError on any query failure (after logging it) --
    the caller decides whether to degrade or surface (see read_confirmation_log).
    """
    try:
        from backend.services.auth import get_db

        collection = get_db().collection(_FIRESTORE_COLLECTION)
        try:
            # Newer google-cloud-firestore deprecates positional where().
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = collection.where(
                filter=FieldFilter("form_session_id", "==", form_session_id)
            )
        except ImportError:
            query = collection.where("form_session_id", "==", form_session_id)
        events = [doc.to_dict() for doc in query.stream()]
        events.sort(key=lambda e: e.get("timestamp", ""))
        return events
    except Exception as e:
        _log.error(
            "confirmation_firestore_read_failed",
            error=str(e),
            form_session_id=form_session_id,
        )
        raise ConfirmationReadError(str(e)) from e
