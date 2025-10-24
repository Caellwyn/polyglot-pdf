"""
Log event schemas for Voice Form Filler.

Type definitions for structured logging events following the LOGGING_OVERHAUL_PLAN.
All schemas enforce HIPAA compliance - NEVER include field values, PHI, or PII.
"""

from typing import TypedDict, Literal, Optional, Any, Dict


# Severity levels
Severity = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Event sources
EventSource = Literal["frontend", "backend"]


class BaseLogEvent(TypedDict, total=False):
    """Base structure for all log events."""
    # Identifiers (REQUIRED)
    client_id: str
    form_id: str
    form_version: str
    form_session_id: str
    ws_session_id: Optional[str]  # Optional for frontend-only events

    # Event metadata (REQUIRED)
    event_type: str
    timestamp: str  # ISO 8601
    source: EventSource

    # Context (OPTIONAL)
    section_number: Optional[int]
    section_label: Optional[str]
    field_id: Optional[str]  # NEVER include field values!
    severity: Optional[Severity]

    # Event-specific data
    metadata: Dict[str, Any]


class TokenUsageMetadata(TypedDict, total=False):
    """Metadata for Gemini API token tracking events."""
    # From response.usage_metadata
    prompt_token_count: int
    candidates_token_count: int
    total_token_count: int

    # Context
    api_call_type: Literal["audio_stream", "text_message", "tool_response", "session_start"]
    tool_name: Optional[str]

    # Sizes (for debugging)
    system_instruction_size: Optional[int]  # Characters
    schema_size: Optional[int]
    tool_result_size: Optional[int]

    # Cumulative
    session_tokens_so_far: int
    form_tokens_so_far: Optional[int]

    # Performance
    latency_ms: float
    cost_estimate_usd: float


class SessionEventMetadata(TypedDict, total=False):
    """Metadata for session lifecycle events."""
    trigger: Optional[Literal["blur", "connect", "timeout", "user"]]
    form_type: Optional[str]
    total_sections: Optional[int]
    total_fields: Optional[int]
    device_type: Optional[Literal["mobile", "desktop", "tablet"]]
    browser: Optional[str]
    language: Optional[str]
    duration_seconds: Optional[float]
    sections_completed: Optional[int]
    fields_total: Optional[int]
    fields_voice: Optional[int]
    fields_manual: Optional[int]
    total_corrections: Optional[int]
    voice_to_manual_switches: Optional[int]


class FieldEventMetadata(TypedDict, total=False):
    """Metadata for field interaction events."""
    attempt_number: Optional[int]
    tool_name: Optional[str]
    validation_passed: Optional[bool]
    validation_error: Optional[str]
    previously_filled_by: Optional[Literal["voice", "manual"]]
    is_correction: Optional[bool]
    filled: Optional[bool]
    fill_method: Optional[Literal["voice", "manual"]]
    attempts: Optional[int]
    time_spent_seconds: Optional[float]


class ErrorEventMetadata(TypedDict, total=False):
    """Metadata for error tracking events."""
    error_message: str
    error_code: Optional[str]
    error_type: Optional[str]
    context: Optional[Dict[str, Any]]
    stack_trace: Optional[str]  # Backend only
    recoverable: Optional[bool]
    recovery_action: Optional[Literal["retry", "skip", "abort"]]


class WebSocketEventMetadata(TypedDict, total=False):
    """Metadata for WebSocket lifecycle events."""
    close_code: Optional[int]
    close_reason: Optional[str]
    reconnect_attempt: Optional[int]
    connection_duration_seconds: Optional[float]


# Event type literals for type safety
EventType = Literal[
    # Session events
    "session_start",
    "session_pause",
    "session_resume",
    "session_complete",
    "session_submit",
    "session_abandon",
    "session_timeout",

    # WebSocket events
    "ws_connect",
    "ws_disconnect",
    "ws_reconnect",
    "ws_error",

    # Field events
    "field_blur",
    "field_voice_attempt",
    "field_voice_success",
    "field_manual_edit",
    "field_correction",
    "field_validation_error",

    # Section events
    "section_start",
    "section_complete",
    "section_switch",

    # Token events
    "gemini_api_response",
    "gemini_error",

    # Tool events
    "tool_call",
    "tool_response",

    # Error events
    "error_validation",
    "error_network",
    "error_ai",
    "error_tool",
    "error_timeout",

    # Audit events (Phase 2)
    "audit_form_start",
    "audit_field_update",
    "audit_form_submit",
]
