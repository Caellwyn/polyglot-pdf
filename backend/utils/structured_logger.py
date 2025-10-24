"""
Structured logger for production logging.

Outputs JSON-formatted logs to stdout for Cloud Run → BigQuery pipeline.
Enforces HIPAA compliance - NEVER logs field values, PHI, or PII.
"""

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.utils.log_schemas import (
    BaseLogEvent,
    EventType,
    EventSource,
    Severity,
)


class StructuredLogger:
    """
    Production logger that outputs structured JSON to stdout.

    Format matches Cloud Run / BigQuery expectations:
    {
        "severity": "INFO",
        "timestamp": "2025-10-24T12:34:56.789Z",
        "message": {
            "event_type": "session_start",
            "client_id": "demo",
            ...
        }
    }
    """

    def __init__(self, client_id: str = "demo"):
        """
        Initialize the structured logger.

        Args:
            client_id: Client identifier (e.g., "demo")
        """
        self.client_id = client_id

    def _emit(
        self,
        severity: Severity,
        event_type: EventType,
        source: EventSource,
        form_id: Optional[str] = None,
        form_version: Optional[str] = None,
        form_session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
        section_number: Optional[int] = None,
        section_label: Optional[str] = None,
        field_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit a structured log event to stdout.

        Args:
            severity: Log severity level
            event_type: Type of event being logged
            source: Event source (frontend or backend)
            form_id: Form identifier
            form_version: Form version
            form_session_id: Session ID that persists across sections
            ws_session_id: WebSocket session ID
            section_number: Section number
            section_label: Section label
            field_id: Field ID (NEVER include field value!)
            metadata: Additional event-specific metadata
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Build the event message
        event: Dict[str, Any] = {
            "event_type": event_type,
            "timestamp": timestamp,
            "source": source,
            "client_id": self.client_id,
        }

        # Add optional identifiers
        if form_id:
            event["form_id"] = form_id
        if form_version:
            event["form_version"] = form_version
        if form_session_id:
            event["form_session_id"] = form_session_id
        if ws_session_id:
            event["ws_session_id"] = ws_session_id

        # Add optional context
        if section_number is not None:
            event["section_number"] = section_number
        if section_label:
            event["section_label"] = section_label
        if field_id:
            event["field_id"] = field_id

        # Add metadata
        if metadata:
            event["metadata"] = metadata

        # Wrap in Cloud Run / BigQuery format
        log_entry = {
            "severity": severity,
            "timestamp": timestamp,
            "message": event,
        }

        # Output to stdout (Cloud Run captures this)
        print(json.dumps(log_entry), file=sys.stdout, flush=True)

    # Session events
    def log_session_start(
        self,
        form_id: str,
        form_version: str,
        form_session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log session start event."""
        self._emit(
            severity="INFO",
            event_type="session_start",
            source="frontend",
            form_id=form_id,
            form_version=form_version,
            form_session_id=form_session_id,
            metadata=metadata or {},
        )

    def log_session_complete(
        self,
        form_id: str,
        form_version: str,
        form_session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log session completion event."""
        self._emit(
            severity="INFO",
            event_type="session_complete",
            source="frontend",
            form_id=form_id,
            form_version=form_version,
            form_session_id=form_session_id,
            metadata=metadata or {},
        )

    # WebSocket events
    def log_ws_connect(
        self,
        form_id: str,
        form_version: str,
        form_session_id: str,
        ws_session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log WebSocket connection event."""
        self._emit(
            severity="INFO",
            event_type="ws_connect",
            source="backend",
            form_id=form_id,
            form_version=form_version,
            form_session_id=form_session_id,
            ws_session_id=ws_session_id,
            metadata=metadata or {},
        )

    def log_ws_disconnect(
        self,
        form_id: str,
        form_version: str,
        form_session_id: str,
        ws_session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log WebSocket disconnection event."""
        self._emit(
            severity="INFO",
            event_type="ws_disconnect",
            source="backend",
            form_id=form_id,
            form_version=form_version,
            form_session_id=form_session_id,
            ws_session_id=ws_session_id,
            metadata=metadata or {},
        )

    # Token tracking (PRIORITY)
    def log_gemini_api_response(
        self,
        form_id: str,
        form_version: str,
        form_session_id: str,
        ws_session_id: str,
        metadata: Dict[str, Any],
        section_number: Optional[int] = None,
    ) -> None:
        """
        Log Gemini API response with token usage.

        Args:
            form_id: Form identifier
            form_version: Form version
            form_session_id: Session ID
            ws_session_id: WebSocket session ID
            metadata: Must include token counts and cost estimate
            section_number: Optional section number
        """
        self._emit(
            severity="INFO",
            event_type="gemini_api_response",
            source="backend",
            form_id=form_id,
            form_version=form_version,
            form_session_id=form_session_id,
            ws_session_id=ws_session_id,
            section_number=section_number,
            metadata=metadata,
        )

    # Field events
    def log_field_voice_attempt(
        self,
        form_id: str,
        form_version: str,
        form_session_id: str,
        ws_session_id: str,
        field_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        section_number: Optional[int] = None,
    ) -> None:
        """Log field update attempt via voice (tool call)."""
        self._emit(
            severity="INFO",
            event_type="field_voice_attempt",
            source="backend",
            form_id=form_id,
            form_version=form_version,
            form_session_id=form_session_id,
            ws_session_id=ws_session_id,
            field_id=field_id,
            section_number=section_number,
            metadata=metadata or {},
        )

    def log_field_manual_edit(
        self,
        form_id: str,
        form_version: str,
        form_session_id: str,
        field_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        ws_session_id: Optional[str] = None,
        section_number: Optional[int] = None,
    ) -> None:
        """Log manual field edit by user."""
        self._emit(
            severity="INFO",
            event_type="field_manual_edit",
            source="frontend",
            form_id=form_id,
            form_version=form_version,
            form_session_id=form_session_id,
            ws_session_id=ws_session_id,
            field_id=field_id,
            section_number=section_number,
            metadata=metadata or {},
        )

    # Error events
    def log_error(
        self,
        error_type: EventType,
        error_message: str,
        source: EventSource,
        form_id: Optional[str] = None,
        form_version: Optional[str] = None,
        form_session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
        field_id: Optional[str] = None,
        section_number: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        severity: Severity = "ERROR",
    ) -> None:
        """
        Log an error event.

        Args:
            error_type: Type of error (error_validation, error_network, etc.)
            error_message: Error description (NO PHI!)
            source: Event source
            severity: Error severity level
            ... other standard fields
        """
        error_metadata = metadata or {}
        error_metadata["error_message"] = error_message

        self._emit(
            severity=severity,
            event_type=error_type,
            source=source,
            form_id=form_id,
            form_version=form_version,
            form_session_id=form_session_id,
            ws_session_id=ws_session_id,
            field_id=field_id,
            section_number=section_number,
            metadata=error_metadata,
        )


# Global logger instance
_logger: Optional[StructuredLogger] = None


def get_logger(client_id: str = "demo") -> StructuredLogger:
    """
    Get or create the global structured logger instance.

    Args:
        client_id: Client identifier

    Returns:
        StructuredLogger instance
    """
    global _logger
    if _logger is None:
        _logger = StructuredLogger(client_id=client_id)
    return _logger
