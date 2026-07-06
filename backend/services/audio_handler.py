"""
Audio handler for streaming audio and activity signals to Gemini.

Handles audio forwarding, activity signaling (speech start/end), and
context synchronization between the frontend and Gemini Live API.
Extracted from FormFillingService for better separation of concerns.
"""
from typing import Any, Optional
import structlog

from backend.ports.live_ai_port import ILiveAI

_log = structlog.get_logger().bind(module="audio_handler")


class AudioHandler:
    """Handles audio streaming and activity signals to Gemini."""
    
    def __init__(
        self,
        live_ai: Optional[ILiveAI],
        session_id: Optional[str] = None
    ):
        """
        Initialize audio handler.
        
        Args:
            live_ai: LiveAI adapter instance for Gemini communication
            session_id: Optional session ID for logging context
        """
        self._live_ai = live_ai
        self._session_id = session_id
        self._first_audio_logged = False
    
    async def stream_audio(self, audio_chunk: bytes) -> None:
        """
        Stream audio chunk to Gemini.
        
        Forwards raw audio bytes from the frontend to Gemini's Live API.
        Logs the first chunk for debugging but remains quiet afterward
        to avoid log spam.
        
        Args:
            audio_chunk: Raw audio bytes (typically PCM16 format)
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return
        
        # Log first audio chunk to verify flow
        if not self._first_audio_logged:
            _log.info(
                "[mic] [AudioHandler] First audio chunk forwarding to LiveAI",
                bytes=len(audio_chunk),
                session_id=self._session_id
            )
            self._first_audio_logged = True
        
        await self._live_ai.stream_audio(audio_chunk)
    
    async def send_activity_start(self) -> None:
        """
        Signal to Gemini that user started speaking.
        
        Sent when frontend VAD (Voice Activity Detection) detects speech.
        Tells Gemini to prepare for incoming audio and start processing.
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return
        
        _log.info(
            "[mic] [AudioHandler] Sending activity_start to Gemini",
            session_id=self._session_id
        )
        await self._live_ai.send_activity_start()
    
    async def send_activity_end(self) -> None:
        """
        Signal to Gemini that user stopped speaking.
        
        Sent when frontend VAD detects speech end. Flushes Gemini's
        cached audio buffer and triggers final transcription/response.
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return
        
        _log.info(
            "[mic-off] [AudioHandler] Sending activity_end to Gemini",
            session_id=self._session_id
        )
        await self._live_ai.send_activity_end()
    
    async def send_context_hint(self, hint_text: str) -> None:
        """
        Send context hint (e.g., next field to fill) to Gemini.
        
        This is sent asynchronously after tool responses, allowing frontend
        to provide navigation guidance without blocking tool call latency.
        
        Args:
            hint_text: Text message to send to Gemini (e.g., "Next unfilled field is 'email'")
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return
        
        # No logging - too verbose for recovery prompts
        await self._live_ai.send_text_message(hint_text)
    
    async def send_manual_field_update(
        self,
        field_id: str,
        field_name: str,
        value: Any,
        next_field_hint: Optional[str] = None
    ) -> None:
        """
        Notify Gemini when user manually updates a field.
        
        Keeps Gemini's context synchronized with manual user edits so it
        doesn't ask about fields the user has already filled.
        
        Args:
            field_id: Technical field identifier
            field_name: Human-readable field label
            value: The value the user entered
            next_field_hint: Optional hint for next field to direct user
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return
        
        # Skip notification only when the field was not actually filled: None/missing,
        # or a whitespace-only string (e.g. user clicked in/out without typing). A
        # manually-entered False (unchecked checkbox) or 0 is a real answer and must
        # still notify Gemini, or the model re-asks for an already-set field (bd
        # polyglot-pdf-vtdx; same falsy-vs-empty predicate as get_form_status's
        # skip in callback_handler.py, bd polyglot-pdf-gihj).
        if value is None or (isinstance(value, str) and not value.strip()):
            _log.debug(
                "send_manual_field_update_skipped",
                field_id=field_id,
                field_name=field_name,
                reason="empty_value",
                session_id=self._session_id
            )
            return
        
        # Format as natural language notification with next field guidance
        value_str = str(value)
        message = f"User manually updated field '{field_name}' with value: {value_str}"
        
        # Add next field guidance if provided
        if next_field_hint:
            message += f"\n\n{next_field_hint}"
        
        # REDACT: Do not log field values (PHI)
        _log.info(
            "send_manual_field_update",
            field_id=field_id,
            field_name=field_name,
            has_next_hint=bool(next_field_hint),
            session_id=self._session_id
        )
        await self._live_ai.send_text_message(message)
