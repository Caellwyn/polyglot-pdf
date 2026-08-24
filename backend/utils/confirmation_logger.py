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
import re
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
    edition_date: Optional[str],
    schema: Optional[dict],
    author_version: Optional[str] = None,
) -> Optional[str]:
    """Return the revision marker to record, best source first.

    bd polyglot-pdf-47r3, extended by bd polyglot-pdf-xzw5. A disputed filing
    needs to pin WHICH revision of the form the client confirmed against.

    1. `edition_date` -- the GOVERNMENT's own revision marker ("12/2024"). The
       right answer for an official form, and the only one an agency recognizes.
    2. `author_version` -- what the KIT AUTHOR typed at publish time, for a form
       that has no government edition (a firm's own intake sheet). Human-
       readable and meaningful in a dispute ("2026-08-07"), which the
       fingerprint below is not. Never invented here: it is recorded only if an
       author actually supplied one.
    3. A short fingerprint of the kit's field structure (`sha256:<12 hex>`).
       A CUSTOM form -- a firm's proprietary intake sheet, which the firm-tier
       epic exists to support -- has no government edition, and refusing to
       record anything would leave those confirmations unable to pin any
       revision at all. Not human-readable, but stable for a given revision and
       CHANGING when the form changes, which is the property that matters:
       "was this the same version of the form the client saw?".

    WHY author_version RANKS BELOW edition_date: the government marker is the
    only one an agency recognizes, so a kit carrying both records the official
    one. WHY IT RANKS ABOVE the fingerprint: both identify a revision, but only
    one of them a human can read back in a dispute.

    NOT the same as `form_metadata.version`, which is auto-extracted, free-form
    and frequently meaningless for this purpose (real shipped values include
    "draft" and "v9_conformant"). That field stays a display string; this one is
    author-asserted and audit-facing.

    The fingerprint covers field ids + types + option values + the answerable
    CONSTRAINTS (validation rules, the required flag, and pdf_field_name --
    bd polyglot-pdf-8x56), not labels or guidance prose: a typo fix in help
    text must not read as a different revision, while adding/removing/
    retyping a field, changing an option's value, tightening/loosening a
    validation rule, flipping required, or remapping which PDF widget a field
    prints into (the same answers now landing on a DIFFERENT printed
    document) must. Measured on the shipped W-7 kit: 0 of 53 fields carry a
    top-level 'required' key but 27 of 53 carry a 'validation' block, so
    before this fix over half the answerable constraints in a real kit were
    invisible to the marker -- a genuine revision of what the client was
    asked could fingerprint identically to the one before it.

    The author version above IS the "third, better source" this docstring used
    to anticipate (bd polyglot-pdf-xzw5). It needed no manifest/wire change in
    the end: it lives in `form_metadata` alongside `edition_date`, inside the
    schema the client already sends whole -- not in kit metadata, where the
    earlier design expected it.

    Returns None when there is neither an edition_date, an author_version, nor
    a usable schema.

    COMPAT NOTE (bd polyglot-pdf-8x56): widening the fingerprint's inputs
    changes its OUTPUT for any kit on this fallback tier -- an already-
    archived revision or confirmation record keyed on the narrower pre-8x56
    digest will not match a freshly-recomputed marker after this change
    ships. Zero live impact at the time of this fix (every shipped
    form-kits/*/schema.json carries an edition_date or author_version, so
    none are on the fingerprint tier), but a future kit that reaches this
    fallback should not assume its marker is stable across THIS kind of
    change again.
    """
    if isinstance(edition_date, str) and edition_date.strip():
        return edition_date.strip()
    if isinstance(author_version, str) and author_version.strip():
        return author_version.strip()
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
        # sorted(<generator>) PRESERVES duplicates, so a kit with a duplicated
        # option value fingerprinted differently from the de-duplicated one --
        # a false-positive drift signal (bd polyglot-pdf-8x56). De-dup via a
        # set before sorting; lower-impact than the constraint gaps below
        # (duplicate option values are already a separate lint ERROR), fixed
        # alongside them since both live in this same shape-building loop.
        option_values = (
            sorted({
                str(o.get("value"))
                for o in options
                if isinstance(o, dict) and o.get("value") is not None
            })
            if isinstance(options, list)
            else []
        )
        # validation rules + the top-level required flag + pdf_field_name (bd
        # polyglot-pdf-8x56): each is a genuine revision of what the client was
        # asked / what document was produced, and previously left the
        # fingerprint byte-identical. json.dumps(sort_keys=True) below makes
        # the validation dict's own key order irrelevant; only its content
        # (and the field's position in the outer `shape.sort()`) affects the
        # digest. A validation dict that fails to json-serialize (should not
        # happen -- schema.json is itself JSON) degrades to its repr() rather
        # than raising, so a malformed kit still fingerprints instead of
        # crashing the audit path.
        validation = field.get("validation")
        try:
            validation_repr = (
                _json.dumps(validation, sort_keys=True)
                if isinstance(validation, dict) else None
            )
        except TypeError:
            validation_repr = repr(validation)
        shape.append([
            str(field.get("id") or ""),
            str(field.get("type") or ""),
            option_values,
            validation_repr,
            bool(field.get("required")),
            str(field.get("pdf_field_name") or ""),
        ])
    shape.sort(key=lambda s: repr(s))
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
    firm_id: Optional[str] = None,
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
        firm_id: The CUSTOMER FIRM this session ran under, from the staff
            member's firm_id token claim (bd polyglot-pdf-xwlt, epic 02ye).
            Identifies the FIRM, never the client -- per-firm usage is then an
            equality query on this key. None for a session with no firm claim
            (a legacy authed user or local dev), which logs exactly as before.
        All three default to None so an older client that omits the handshake
        keys degrades to the pre-47r3 record shape rather than erroring.

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
        # Firm identity (bd polyglot-pdf-xwlt). Always present as a key so
        # every record has a uniform shape; None when no firm claim rode the
        # session.
        "firm_id": firm_id,
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


# A form session id is client-generated: `fss_<base36 ts>_<8 chars>`
# (schemaFormState.ts). It becomes a FILENAME below, so it must be a single
# path segment and nothing else.
#
# fullmatch, NOT match: with `match` the `$` anchor also matches just before a
# trailing newline, so an id ending in a newline would pass and reach the
# filesystem. That exact bug was found in _safe_kit_id (bd
# polyglot-pdf-sbfk) -- same trap, same fix.
_FORM_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}")


# Windows treats these as DEVICES, not files, with or without an extension:
# opening "NUL.jsonl" succeeds and discards every byte, so an attacker could
# make a session's evidence vanish silently rather than noisily. This backend
# runs on Linux in production and Windows in local dev; the check is
# unconditional so behavior does not diverge between them.
_WINDOWS_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + ["COM%d" % i for i in range(1, 10)]
    + ["LPT%d" % i for i in range(1, 10)]
)


def _is_safe_session_id(form_session_id: str) -> bool:
    """Whether this id is safe to use as a single filename segment.

    Rejects, in order: non-strings; anything containing "..";  anything outside
    the charset/length bound; a name that is only dots; a name ending in a dot
    (Windows silently strips trailing dots, so "x." and "x" collide); and the
    Windows reserved device names.

    All of these were reached by adversarially attacking this function rather
    than by reasoning about it -- the device names and trailing dots passed the
    first version (bd polyglot-pdf-0dsv4).
    """
    if not isinstance(form_session_id, str):
        return False
    if ".." in form_session_id:
        return False
    if _FORM_SESSION_ID_RE.fullmatch(form_session_id) is None:
        return False
    if form_session_id.strip(".") == "":
        return False
    if form_session_id.endswith("."):
        return False
    # Windows matches the device name before the extension, case-insensitively.
    stem = form_session_id.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        return False
    return True


def _write_confirmation_to_file(form_session_id: str, event: dict) -> None:
    """
    Write confirmation event to dedicated log file.

    One log file per form session for easy correlation.
    File format: logs/confirmations/{form_session_id}.jsonl

    REFUSES a form_session_id that is not a single safe path segment. This is
    enforced HERE, at the write, rather than in any one caller: the id reaches
    this function from an UNAUTHENTICATED route (POST /api/disclaimer-acceptance
    -- Agree fires before any session exists, so it carries no token), and
    "../../PWNED" wrote outside the log directory and returned 200 (reproduced,
    bd polyglot-pdf-0dsv4 cross-surface review). Validating at the sink protects
    every caller, including ones added later.
    """
    if not _is_safe_session_id(form_session_id):
        _log.error(
            "confirmation_log_unsafe_session_id",
            note="refused: not a single safe path segment; no file written",
            length=len(form_session_id) if isinstance(form_session_id, str) else None,
        )
        return
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
    firm_id: Optional[str] = None,
    kit_id: Optional[str] = None,
) -> None:
    """
    Log start of form filling session.

    Args:
        form_id: Form type (e.g., "I-90")
        form_session_id: Persistent session ID
        section_id: Initial section ID if applicable
        firm_id: Customer firm this session runs under (bd polyglot-pdf-xwlt);
            None when no firm claim rode the token.
        kit_id: Kit identity, so a session record names the same kit its
            confirmations do.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    event = {
        "timestamp": timestamp,
        "event": "form_session_started",
        "form_id": form_id,
        "kit_id": kit_id,
        "firm_id": firm_id,
        "form_session_id": form_session_id,
        "section_id": section_id,
    }

    # Filter the "event" key: it collides with structlog's positional event
    # name (same pattern as log_field_confirmation). Latent TypeError until the
    # z2is sink tests gave this function its first caller.
    _log.info("form_session_started", **{k: v for k, v in event.items() if k != "event"})
    _write_confirmation_to_file(form_session_id, event)
    _submit_firestore_write(event)


# ONE ACCEPTANCE PER SESSION (bd polyglot-pdf-g3kui).
#
# POST /api/disclaimer-acceptance is UNAUTHENTICATED and cannot be gated: a
# client filling a form has no account by design -- the magic link is their
# only entry (maintainer, 2026-08-24) -- so requiring a token would 401 every
# real user at the Agree button. Since bd polyglot-pdf-0dsv4 it also writes
# DURABLY to the legal-evidence collection, so an unbounded caller is an
# unbounded writer to the collection the kit-deletion guard and every legal
# retrieval read.
#
# A session accepts ONCE. That domain fact is the bound: the first acceptance
# for a form_session_id is recorded, later ones are dropped. A flood from one
# caller costs one row per DISTINCT id instead of one row per request.
#
# IN-PROCESS, deliberately. The alternative -- read Firestore before every
# write -- adds a round trip on the Agree path, races the executor that
# actually performs the write, and fails open anyway when the read fails. This
# does not survive a restart or bound a distributed flood across instances; it
# is a cheap bound on the common case, NOT a replacement for a rate limit.
# That gap is stated in the bead and in confirmation-and-audit.md rather than
# implied by the code.
#
# The cap stops the guard itself becoming a memory leak: a flood of distinct
# ids would otherwise grow this set without limit. At the cap the guard stops
# deduping (writes proceed) rather than stops writing -- losing legal evidence
# is worse than a duplicated row.
_ACCEPTED_SESSIONS: set = set()
_ACCEPTED_SESSIONS_LOCK = threading.Lock()
_ACCEPTED_SESSIONS_CAP = 10000


def _claim_first_acceptance(form_session_id: str) -> bool:
    """True if this is the FIRST acceptance seen for this session id.

    Returns True (write it) when the set is at capacity, so a memory bound can
    never silently discard evidence.
    """
    with _ACCEPTED_SESSIONS_LOCK:
        if len(_ACCEPTED_SESSIONS) >= _ACCEPTED_SESSIONS_CAP:
            return True
        if form_session_id in _ACCEPTED_SESSIONS:
            return False
        _ACCEPTED_SESSIONS.add(form_session_id)
        return True


def _reset_acceptance_dedupe() -> None:
    """Test seam: clear the in-process dedupe state."""
    with _ACCEPTED_SESSIONS_LOCK:
        _ACCEPTED_SESSIONS.clear()


def log_disclaimer_acceptance(
    form_session_id: str,
    language: str,
    timestamp_unix_ms: int,
    script_version: Optional[str] = None,
    user_agent: Optional[str] = None,
    firm_id: Optional[str] = None,
) -> None:
    """Log the user's acceptance of the disclaimer, DURABLY.

    Why this exists (bd polyglot-pdf-0dsv4): the acceptance used to be a
    single structured log line and nothing else, so the record that a user
    accepted the legal terms was LESS durable than the record of what they
    typed into a field -- backwards for a legal-evidence trail. It now goes
    through the same sink the field confirmations use, keyed on
    form_session_id, so `read_confirmation_log(form_session_id)` returns the
    acceptance and the confirmations as ONE timestamp-ordered session record.

    NO PII, and deliberately no client IP (bd polyglot-pdf-z2is): an IP is
    PII under GDPR/CCPA. `script_version` is a hash of copy that ships in the
    client bundle, so it names WHICH text was agreed to without carrying user
    content.

    firm_id: the customer firm, matching the session-lifecycle and
        confirmation records (bd polyglot-pdf-xwlt). ALWAYS None here, and
        PERMANENTLY so: a client filling a form has no account by design --
        the magic link is their only entry path (maintainer, 2026-08-24) --
        so this route cannot carry a client token and must never require one.
        An earlier note called this a temporary compromise pending firm auth;
        that was wrong (bd polyglot-pdf-g3kui). The field is still written so
        the collection has ONE shape, and a firm's acceptances are reached by
        joining on form_session_id against their confirmation records, which
        DO carry firm_id -- see firm_of_events below. That join is the
        long-term answer, not a stopgap.
    """
    # ONE per session: the domain fact that bounds an unauthenticated writer.
    # A duplicate is DROPPED silently, not an error -- a retry after a lost
    # response is a legitimate client behavior, and the first record is the
    # one that matters.
    if not _claim_first_acceptance(form_session_id):
        _log.info(
            "disclaimer_acceptance_duplicate_dropped",
            form_session_id=form_session_id,
            note="this session already has an acceptance record",
        )
        return
    timestamp = datetime.now(timezone.utc).isoformat()

    event = {
        "timestamp": timestamp,
        "event": "disclaimer_accepted",
        "form_session_id": form_session_id,
        "firm_id": firm_id,
        "language": language,
        "timestamp_unix_ms": timestamp_unix_ms,
        "script_version": script_version,
        "user_agent": user_agent,
    }

    # Filter the "event" key: it collides with structlog's positional event
    # name (same pattern as log_field_confirmation).
    _log.info(
        "disclaimer_accepted", **{k: v for k, v in event.items() if k != "event"}
    )
    _write_confirmation_to_file(form_session_id, event)
    _submit_firestore_write(event)


def firm_of_events(events: list) -> Optional[str]:
    """The firm a session's records attribute it to, or None.

    Split out so a caller that ALREADY holds the events (the retrieval script)
    attributes without a second query, and so the attribution rule is testable
    without a datastore.

    DISAGREEMENT IS NOT SILENTLY RESOLVED. One session belongs to one firm, so
    two different firm_ids on one session means something is wrong upstream --
    returning the first would launder that into a confident wrong answer on a
    legal-evidence path. Log it loudly and return None: "we do not know" is the
    honest result, and a caller can still read the raw records.
    """
    firms = {e.get("firm_id") for e in events if e.get("firm_id")}
    if not firms:
        return None
    if len(firms) > 1:
        _log.error(
            "firm_attribution_conflict",
            firm_ids=sorted(firms),
            note="one session mapped to multiple firms; refusing to guess",
        )
        return None
    return firms.pop()


def log_form_session_end(
    form_id: str,
    form_session_id: str,
    completion_status: Literal["completed", "abandoned", "error"],
    total_fields_confirmed: int,
    firm_id: Optional[str] = None,
    kit_id: Optional[str] = None,
) -> None:
    """
    Log end of form filling session.

    Args:
        form_id: Form type
        form_session_id: Persistent session ID
        completion_status: How session ended
        total_fields_confirmed: Count of fields confirmed in this session
        firm_id: Customer firm this session ran under (bd polyglot-pdf-xwlt).
        kit_id: Kit identity, matching the session-start record.

    ONE ROW PER CONNECTION, not per session. The WS teardown cannot know
    whether it is the end of the form or the middle of a reconnect (the
    protocol has no terminal-close signal), so this fires on every
    connection teardown and the reader aggregates: a per-firm SESSION count
    is a DISTINCT count over form_session_id, never a row count. See
    docs/standards/confirmation-and-audit.md.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    event = {
        "timestamp": timestamp,
        "event": "form_session_ended",
        "form_id": form_id,
        "kit_id": kit_id,
        "firm_id": firm_id,
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
# bd polyglot-pdf-fzwp: /health has no auth (backend/main.py), so any
# unauthenticated caller can drive concurrent confirmation_sink_status()
# calls at their own request rate. On a cold/stale cache each one used to
# fall through to its OWN Firestore write+delete round trip -- the lock only
# guarded the cache READ/WRITE, not the probe itself, so N concurrent callers
# produced N round trips against the collection that holds the legal audit
# trail. _probe_in_flight coalesces concurrent callers onto ONE round trip:
# the first caller through does the real probe and publishes the result via
# this Event; everyone else waits on it instead of starting their own.
_probe_in_flight: Optional[threading.Event] = None


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
    for max_age_s so /health polling does not hammer Firestore -- including
    CONCURRENT polling (bd polyglot-pdf-fzwp): only the first caller past a
    cold/stale cache does the real probe, everyone racing in behind them
    waits for and reuses that one result instead of each doing their own.
    """
    global _probe_cache, _probe_in_flight
    if not _firestore_enabled():
        return "disabled"

    with _probe_lock:
        if _probe_cache and (time.monotonic() - _probe_cache[0]) < max_age_s:
            return _probe_cache[1]
        if _probe_in_flight is not None:
            # Someone else is already probing -- wait for them OUTSIDE the
            # lock (below), then reuse whatever they publish.
            in_flight = _probe_in_flight
            we_are_prober = False
        else:
            # We are the one doing the real probe. Claim it BEFORE releasing
            # the lock so no other thread starts a duplicate round trip.
            in_flight = _probe_in_flight = threading.Event()
            we_are_prober = True

    if not we_are_prober:
        # bd polyglot-pdf-fzwp round 2 (Opus cross-surface review): the sole
        # real caller (/health, backend/main.py) wraps this whole call in
        # asyncio.wait_for(timeout=3.0). asyncio.wait_for does NOT cancel the
        # underlying asyncio.to_thread worker on timeout -- it just stops
        # awaiting it -- so a waiter blocked here for the OLD 30s timeout
        # kept running on its executor thread well past /health's own
        # deadline, tying up thread-pool capacity for every subsequent
        # concurrent poll during exactly the kind of stalled-Firestore
        # outage this probe exists to detect. A wait longer than the only
        # caller's own budget can never usefully return to that caller
        # anyway, so bound it well under 3.0s instead.
        in_flight.wait(timeout=2.0)
        with _probe_lock:
            if _probe_cache:
                return _probe_cache[1]
        # A genuinely slow/stalled prober (the outage this probe exists to
        # detect) can still be running past our wait -- this is a REACHABLE
        # path, not dead code, and the message says so honestly rather than
        # claiming "should be unreachable".
        return "error: probe coalescing timed out waiting for another in-flight probe"

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
        _probe_in_flight = None
    in_flight.set()
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

    strict=True ALSO raises when the Firestore sink is not ENABLED at all
    (bd polyglot-pdf-k3v7): without this, an operator who forgets
    --firestore (or runs with CONFIRMATION_FIRESTORE_ENABLED unset, the
    normal laptop case) silently falls through to a local JSONL file that
    does not exist off the deployed instance, and gets 'no events found' --
    indistinguishable from a genuinely empty durable trail. For a
    legal-retrieval surface that conflation is exactly what strict exists to
    prevent, and it is reachable by a single forgotten flag.
    """
    if strict and not _firestore_enabled():
        raise ConfirmationReadError(
            "the durable Firestore confirmation sink is not enabled for this "
            "read, so the durable trail was NOT consulted -- only the local "
            "JSONL file (a dev convenience that does not survive a deployed "
            "instance) would be checked. Enable CONFIRMATION_FIRESTORE_ENABLED "
            "or pass --firestore before treating an empty result as authoritative."
        )
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


class ConfirmationCheckUnavailable(Exception):
    """The durable confirmation record could not be consulted at all.

    DISTINCT from "no records exist" (bd polyglot-pdf-6x1j), and the difference
    is load-bearing: a caller about to do something irreversible must be able
    to tell "I verified this is safe" from "I could not verify". Raised when
    the Firestore sink is disabled or its query fails -- the local JSONL file
    is a dev convenience that dies with the Cloud Run instance, so its silence
    is not evidence of absence.
    """


# How many field_confirmed docs to inspect for the pre-47r3 (no kit_id key)
# shape. Firestore cannot query for a MISSING key at all, so this is a bounded
# client-side SAMPLE rather than a filter -- and stream() without order_by
# returns __name__ order, which for .add()-generated ids is arbitrary, so these
# are an arbitrary 50 and NOT the oldest 50.
#
# That sampling is acceptable because of what the legacy population looks like:
# every field_confirmed doc written in the two days between the Firestore sink
# shipping and kit_id joining the event dict. If any exist they exist as a
# contiguous cohort, so a 50-doc sample effectively cannot miss them. Making it
# deterministic (order_by timestamp) would need a composite index, and the repo
# ships no firestore.indexes.json -- the query would 400 at runtime instead
# (Opus outer cross-surface review, which enumerated every event value ever
# written and confirmed this bound is the right call).
#
# THE BOUND APPLIES TO THIS LEGACY SWEEP ONLY. It briefly bounded the whole
# guard, which silently turned the POSITIVE kit match into an arbitrary
# 50-document sample -- a false "no records" on any busy collection, and a
# hard delete of a kit clients had really confirmed against (bd
# polyglot-pdf-u66ka). The contiguous-cohort argument above justifies
# sampling a CLOSED population; it does not transfer to a live one. The kit
# match and the stored-null check are exhaustive equality queries.
_LEGACY_SCAN_LIMIT = 50


def kit_has_confirmation_records(kit_id: str) -> bool:
    """True when ANY confirmation event names this kit.

    The guard behind irreversible kit deletion. Three checks, in order:

    1. EXHAUSTIVE: `kit_id == kit_id AND event == "field_confirmed"`,
       limit(1). Both filters are equality, which Firestore serves by merging
       auto-created single-field indexes -- no composite index (the repo
       ships no firestore.indexes.json). limit(1) bounds the RESULT, not the
       search, so the scan cannot miss a record for being far down the
       collection.
    2. EXHAUSTIVE: the same pair with `kit_id == None` -- a real confirmation
       naming NO kit is unattributable evidence, so it refuses.
    3. BOUNDED (_LEGACY_SCAN_LIMIT): the pre-47r3 missing-key shape, which
       Firestore cannot query for. Sampling is defensible only here; see that
       constant's comment.

    The event scope on every one of them is load-bearing: since bd
    polyglot-pdf-xwlt the session-lifecycle events carry a kit_id, so an
    unscoped kit query matches session telemetry and makes a kit undeletable
    after a single voice session (bd polyglot-pdf-68s2q).

    Raises ConfirmationCheckUnavailable rather than returning False when the
    durable record cannot be consulted (sink disabled, or the query failed).
    Returning False there would let a caller delete a kit whose records exist
    but are simply out of reach -- destroying the evidence the whole revision
    archive exists to preserve, on the strength of a question never actually
    asked (maintainer decision 2026-08-08: refuse when the check is
    unavailable).
    """
    if not _firestore_enabled():
        raise ConfirmationCheckUnavailable(
            "the confirmation record sink is not enabled, so records cannot be checked"
        )
    try:
        from backend.services.auth import get_db

        collection = get_db().collection(_FIRESTORE_COLLECTION)
        from google.cloud.firestore_v1.base_query import FieldFilter

        # EVERY query here is scoped to event == "field_confirmed" (bd
        # polyglot-pdf-xwlt / 68s2q). The session-lifecycle events became live
        # callers WITH a kit_id under xwlt, so an unscoped kit_id query
        # matched them: one voice session made a kit permanently undeletable,
        # and a session with a null kit_id made EVERY kit unverifiable.
        #
        # Both filters are EQUALITY, which Firestore serves by merging
        # auto-created single-field indexes -- no composite index, no
        # firestore.indexes.json (verified: the repo ships none). The first
        # cut of this fix filtered only on the event and compared kit_id
        # client-side over a bounded stream, which silently turned the
        # POSITIVE check from exhaustive into an arbitrary 50-document sample
        # -- a false "no records" on a busy collection, i.e. a hard delete of
        # a kit clients really had confirmed against (bd polyglot-pdf-u66ka).
        # limit(1) bounds the RESULT, not the search: the scan stays
        # exhaustive through the index.
        kit_match = (
            collection
            .where(filter=FieldFilter("kit_id", "==", kit_id))
            .where(filter=FieldFilter("event", "==", "field_confirmed"))
            .limit(1)
        )
        if any(True for _ in kit_match.stream()):
            return True

        # A stored NULL kit_id on a REAL confirmation: unattributable evidence
        # that a client confirmed something, so refuse rather than guess.
        # Equality-on-null resolves to IS_NULL, which matches a stored null and
        # NOT a missing key -- the missing-key shape is the legacy sweep below.
        unattributed = (
            collection
            .where(filter=FieldFilter("kit_id", "==", None))
            .where(filter=FieldFilter("event", "==", "field_confirmed"))
            .limit(1)
        )
        if any(True for _ in unattributed.stream()):
            _log.info("confirmation_unattributed_records_block_delete", kit_id=kit_id)
            raise ConfirmationCheckUnavailable(
                "confirmation records exist that name no kit, so this kit cannot "
                "be cleared for deletion"
            )

        # ...and the same blindness one shape over: IS_NULL cannot match a
        # MISSING key, and records written between the sink shipping
        # (2026-08-03) and kit_id joining the event dict (2026-08-05, bd
        # polyglot-pdf-47r3) omit it entirely. Firestore cannot query for a
        # missing key, so this is a BOUNDED client-side scan -- and the bound
        # is defensible ONLY here: legacy records are a contiguous, closed
        # cohort (nothing writes that shape any more), so a sample that finds
        # none is strong evidence none exist. That reasoning does NOT extend
        # to the positive match above, which is why it is a separate,
        # exhaustive query (bd polyglot-pdf-u66ka).
        legacy = collection.where(
            filter=FieldFilter("event", "==", "field_confirmed")
        ).limit(_LEGACY_SCAN_LIMIT)
        for doc in legacy.stream():
            if "kit_id" not in (doc.to_dict() or {}):
                _log.info("confirmation_legacy_records_block_delete", kit_id=kit_id)
                raise ConfirmationCheckUnavailable(
                    "confirmation records predating kit identity exist, so this "
                    "kit cannot be cleared for deletion"
                )
        return False
    except ConfirmationCheckUnavailable:
        raise
    except Exception as e:
        _log.error(
            "confirmation_kit_existence_check_failed",
            error=str(e),
            kit_id=kit_id,
        )
        raise ConfirmationCheckUnavailable(str(e)) from e


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
