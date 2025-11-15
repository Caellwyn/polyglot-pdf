"""
WebSocket message type definitions for half-cascade architecture.

Defines protocol messages for:
- Audio buffering and processing status
- Language detection and switching
- Conversation state transfer
- Backward compatibility with existing messages
"""

from __future__ import annotations

from typing import Literal, Optional, Any, TypedDict


# ============================================================================
# Existing Message Types (Backward Compatible)
# ============================================================================

class AudioDataMessage(TypedDict):
    """Audio data message (binary frames)."""
    type: Literal["audio"]
    data: str  # base64 encoded


class ToolCallMessage(TypedDict):
    """Tool call message from backend to frontend."""
    type: Literal["tool_call"]
    tool: str
    args: dict[str, Any]


# ============================================================================
# Half-Cascade Message Types (New)
# ============================================================================

class AudioEndMessage(TypedDict, total=False):
    """
    Audio end message for half-cascade mode.

    Frontend sends this when audio buffer is complete (PTT release or VAD silence).
    Includes form state and conversation history for stateless backend.
    """
    type: Literal["audio_end"]
    audio_data: str  # base64 encoded complete audio buffer
    form_state: str  # "field_id:value|field_id2:value2" format
    current_field: str  # Current field ID
    current_part: str  # Current part ID
    conversation_history: list[dict[str, str]]  # [{"role": "user", "content": "..."}]


class ProcessingStatusMessage(TypedDict, total=False):
    """
    Processing status update from backend to frontend.

    Informs user of current processing stage in half-cascade pipeline.
    """
    type: Literal["processing_status"]
    stage: Literal["buffering", "transcribing", "generating", "synthesizing"]
    progress: Optional[int]  # 0-100 percentage (optional)


class LanguageStatusMessage(TypedDict):
    """
    Language detection status from backend to frontend.

    Informs frontend of detected language and confidence.
    """
    type: Literal["language_status"]
    detected: str  # Detected language code (e.g., "es-ES")
    current: str  # Currently active language
    confidence: float  # Detection confidence (0.0-1.0)


class TranscriptMessage(TypedDict):
    """
    User transcript message from backend to frontend.

    Contains transcribed user speech for conversation history building.
    Cheaper than storing audio for context.
    """
    type: Literal["transcript"]
    user_transcript: str  # User's spoken words (transcribed)
    assistant_response: str  # AI's text response (before TTS)
    language: str  # Language code


class AudioResponseChunk(TypedDict, total=False):
    """
    Audio response chunk from backend to frontend.

    Streamed TTS audio in small chunks for low latency.
    """
    type: Literal["audio_response"]
    data: str  # base64 encoded audio chunk
    language: str  # Language of this segment
    is_final: bool  # True for last chunk


class HalfCascadeError(TypedDict, total=False):
    """
    Half-cascade specific error message.

    Indicates error in half-cascade pipeline with fallback info.
    """
    type: Literal["half_cascade_error"]
    error_code: str
    message: str
    fallback_activated: bool  # True if falling back to Live API
    recoverable: bool  # True if retry possible


# ============================================================================
# Message Type Union
# ============================================================================

WebSocketMessage = (
    AudioDataMessage
    | ToolCallMessage
    | AudioEndMessage
    | ProcessingStatusMessage
    | LanguageStatusMessage
    | TranscriptMessage
    | AudioResponseChunk
    | HalfCascadeError
)


# ============================================================================
# Helper Functions
# ============================================================================

def create_processing_status(
    stage: Literal["buffering", "transcribing", "generating", "synthesizing"],
    progress: Optional[int] = None
) -> ProcessingStatusMessage:
    """Create a processing status message.

    Args:
        stage: Current processing stage
        progress: Optional progress percentage (0-100)

    Returns:
        ProcessingStatusMessage
    """
    msg: ProcessingStatusMessage = {"type": "processing_status", "stage": stage}
    if progress is not None:
        msg["progress"] = progress
    return msg


def create_language_status(
    detected: str,
    current: str,
    confidence: float
) -> LanguageStatusMessage:
    """Create a language status message.

    Args:
        detected: Detected language code
        current: Current active language
        confidence: Detection confidence (0.0-1.0)

    Returns:
        LanguageStatusMessage
    """
    return {
        "type": "language_status",
        "detected": detected,
        "current": current,
        "confidence": confidence
    }


def create_transcript(
    user_transcript: str,
    assistant_response: str,
    language: str
) -> TranscriptMessage:
    """Create a transcript message for conversation history.

    Args:
        user_transcript: User's spoken words
        assistant_response: AI's text response
        language: Language code

    Returns:
        TranscriptMessage
    """
    return {
        "type": "transcript",
        "user_transcript": user_transcript,
        "assistant_response": assistant_response,
        "language": language
    }


def create_audio_response_chunk(
    data: str,
    language: str,
    is_final: bool = False
) -> AudioResponseChunk:
    """Create an audio response chunk message.

    Args:
        data: Base64 encoded audio data
        language: Language of this segment
        is_final: True if this is the last chunk

    Returns:
        AudioResponseChunk
    """
    return {
        "type": "audio_response",
        "data": data,
        "language": language,
        "is_final": is_final
    }


def create_half_cascade_error(
    error_code: str,
    message: str,
    fallback_activated: bool = False,
    recoverable: bool = True
) -> HalfCascadeError:
    """Create a half-cascade error message.

    Args:
        error_code: Error code identifier
        message: Human-readable error message
        fallback_activated: Whether fallback to Live API was triggered
        recoverable: Whether the error is recoverable

    Returns:
        HalfCascadeError
    """
    return {
        "type": "half_cascade_error",
        "error_code": error_code,
        "message": message,
        "fallback_activated": fallback_activated,
        "recoverable": recoverable
    }
