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

    # Usage event v2 -- text + TTS paid calls (bd polyglot-pdf-wio6m).
    # The live-voice path keeps emitting "gemini_api_response" so existing
    # queries and dashboards built on that name keep resolving; usage_kind in
    # the metadata is what distinguishes the paths from here on.
    "text_ai_usage",
    "tts_usage",

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


# ============================================================================
# Usage event v2 (bd polyglot-pdf-wio6m)
# ============================================================================
# ONE structured event shape for EVERY paid model or TTS call, so the Cloud
# Logging -> BigQuery sink sees a single column shape instead of one schema per
# call path. The kind of paid call is carried in `usage_kind`, NOT in the key
# set: every wrapper emits the FULL key set below, with None for the keys its
# path genuinely has no value for. A BigQuery column that appears on some rows
# and not others is the thing this avoids -- a missing key and a null are
# different at the sink, and only the second is queryable.

# Closed set. A new paid call path adds a member HERE (and the coverage test's
# allowlist) rather than inventing a free-form string at the call site.
UsageKind = Literal[
    "live_voice",        # aio.live.connect -- the voice form-filling session
    "text_secretary",    # generate_content -- the secretary/ask path
    "text_validator",    # generate_content -- the validator path
    "text_translation",  # generate_content -- authoring-time kit translation
    "tts_spellback",     # synthesize_speech -- the value verification clip
    "tts_notice",        # synthesize_speech -- a spoken notice
    "tts_intro",         # synthesize_speech -- the session intro clip
]

# The usage envelope's OPTIONAL identity/context keys. Named here (rather than
# only in the emitter) so the schema test and the emitter derive from one list:
# a key added to the envelope without a matching entry here fails the test.
#
# PII rule (docs/standards/hipaa-pii-policy.md): ids, counts, costs and model
# names only. There is deliberately no slot for a field value, a transcript, or
# any free text, so the shape is HIPAA-safe by construction.
USAGE_CONTEXT_KEYS = (
    "firm_id",      # the paying firm, when known
    "employee_id",  # the firm employee whose link this is, when known
    "link_jti",     # the client-link token id, when the call is under a link
    "kit_id",       # the form kit being filled or translated
    "channel",      # staging | demo -- which deploy channel spent this
    "model",        # the concrete model/voice-tier name that was billed
)


class UsageEventMetadata(TypedDict, total=False):
    """Metadata block of a usage event.

    `usage_kind` plus the context keys are always PRESENT (possibly None);
    the count/cost keys are per-path and carry whatever that path measures.
    """
    usage_kind: UsageKind

    # Identity / context (always present as keys; values may be None)
    firm_id: Optional[str]
    employee_id: Optional[str]
    link_jti: Optional[str]
    kit_id: Optional[str]
    channel: Optional[str]
    model: Optional[str]

    # Token counts (model calls) / character counts (TTS)
    prompt_token_count: Optional[int]
    candidates_token_count: Optional[int]
    total_token_count: Optional[int]
    cached_content_token_count: Optional[int]
    character_count: Optional[int]

    # Cost
    cost_estimate_usd: Optional[float]
