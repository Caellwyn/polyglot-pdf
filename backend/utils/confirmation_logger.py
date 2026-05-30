"""
Confirmation logging for liability protection.

Logs field confirmations with timestamps (NO PII).
Demonstrates proper confirmation workflow for legal defense.

CRITICAL: Only log metadata, NEVER log actual field values or user data.
"""
import os
import structlog
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal

_log = structlog.get_logger().bind(module="confirmation_logger")

# Confirmation log directory (separate from application logs). Overridable via
# the CONFIRMATION_LOG_DIR env var so tests can redirect writes to a tmp dir
# instead of the repo tree. Resolved per-call (not cached at import) so the env
# var / a test fixture can set it after this module is imported.
_DEFAULT_CONFIRMATION_LOG_DIR = "logs/confirmations"


def _confirmation_log_dir() -> Path:
    """Return the confirmation-log directory, creating it if needed."""
    log_dir = Path(os.getenv("CONFIRMATION_LOG_DIR", _DEFAULT_CONFIRMATION_LOG_DIR))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir

# Matches the confirm_field tool's confirmation_method enum (backend/config.py)
# and the values actually written by callback_handler._handle_confirm_field_tool.
ConfirmationMethod = Literal["verbal", "manual"]


def log_field_confirmation(
    form_id: str,
    form_session_id: str,
    field_id: str,
    field_name: Optional[str],
    confirmation_method: ConfirmationMethod,
) -> None:
    """
    Log field confirmation event (NO PII).

    Args:
        form_id: Form type identifier (e.g., "I-90", "I-589")
        form_session_id: Persistent form session ID (e.g., "fss_xxx")
        field_id: Field identifier (e.g., "p1_line1_aliennumber")
        field_name: Human-readable field name (e.g., "Alien Registration Number")
        confirmation_method: How field was confirmed

    CRITICAL: This function MUST NEVER receive or log actual field values or PII.

    Example log entry:
        {
            "timestamp": "2025-11-18T20:30:45.123Z",
            "event": "field_confirmed",
            "form_id": "I-90",
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

    _log.info("form_session_started", **event)
    _write_confirmation_to_file(form_session_id, event)


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

    _log.info("form_session_ended", **event)
    _write_confirmation_to_file(form_session_id, event)


def get_confirmation_log_path(form_session_id: str) -> Path:
    """
    Get path to confirmation log file for a specific form session.

    Useful for retrieving logs for review or legal purposes.
    """
    return _confirmation_log_dir() / f"{form_session_id}.jsonl"


def read_confirmation_log(form_session_id: str) -> list[dict]:
    """
    Read all confirmation events for a form session.

    Returns list of confirmation events in chronological order.
    """
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
