"""
Half-Cascade Error Recovery Service - Phase 3C

Handles error scenarios in the half-cascade architecture with graceful recovery:
1. Audio size validation and chunking
2. JSON parsing errors with fallback
3. Language fallback handling
4. TTS quota management
5. Network retry logic
6. Tool call error handling

Exit Criteria:
- All error scenarios handled
- Fallback to Live API works
- User feedback appropriate
- Errors logged with context
- Recovery time <3 seconds
"""

import asyncio
import base64
import structlog
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

_log = structlog.get_logger().bind(module="half_cascade_error_recovery")


# Constants
MAX_AUDIO_SIZE_MB = 20
MAX_AUDIO_BYTES = MAX_AUDIO_SIZE_MB * 1024 * 1024
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 2  # Exponential backoff base (2^n seconds)
DEFAULT_FALLBACK_LANGUAGE = "en-US"


@dataclass
class ErrorRecoveryResult:
    """Result of error recovery attempt."""
    success: bool
    error_type: str
    recovery_action: str
    fallback_activated: bool = False
    user_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class HalfCascadeErrorRecovery:
    """
    Error recovery coordinator for half-cascade pipeline.

    Handles all error scenarios with appropriate recovery strategies.
    """

    def __init__(
        self,
        websocket,
        session_id: Optional[str] = None,
        fallback_to_live_api: bool = True
    ):
        """
        Initialize error recovery service.

        Args:
            websocket: WebSocket connection for sending error messages
            session_id: Session ID for logging
            fallback_to_live_api: Whether to fall back to Live API on critical errors
        """
        self._websocket = websocket
        self._session_id = session_id
        self._fallback_to_live_api = fallback_to_live_api

        _log.info(
            "error_recovery_initialized",
            session_id=session_id,
            fallback_enabled=fallback_to_live_api
        )

    # ========================================================================
    # Error Scenario 1: Audio Size Validation
    # ========================================================================

    async def validate_audio_size(
        self,
        audio_data_base64: str
    ) -> ErrorRecoveryResult:
        """
        Validate audio size and handle oversized audio.

        Strategy: If >20MB, return error asking user to speak shorter utterances.

        Args:
            audio_data_base64: Base64-encoded audio

        Returns:
            ErrorRecoveryResult
        """
        try:
            # Decode to check actual size
            audio_bytes = base64.b64decode(audio_data_base64)
            size_mb = len(audio_bytes) / (1024 * 1024)

            if len(audio_bytes) > MAX_AUDIO_BYTES:
                _log.warning(
                    "audio_too_large",
                    size_mb=size_mb,
                    max_mb=MAX_AUDIO_SIZE_MB,
                    session_id=self._session_id
                )

                # Send error to frontend
                await self._send_error(
                    error_code="audio_too_large",
                    message=f"Audio size ({size_mb:.1f}MB) exceeds limit ({MAX_AUDIO_SIZE_MB}MB). Please speak in shorter segments.",
                    recoverable=True,
                    user_message="Audio too long. Please try speaking in shorter segments."
                )

                return ErrorRecoveryResult(
                    success=False,
                    error_type="audio_too_large",
                    recovery_action="user_guidance",
                    user_message="Please speak in shorter segments."
                )

            return ErrorRecoveryResult(
                success=True,
                error_type="none",
                recovery_action="none"
            )

        except Exception as e:
            _log.error(
                "audio_validation_failed",
                error=str(e),
                session_id=self._session_id
            )
            return ErrorRecoveryResult(
                success=False,
                error_type="validation_error",
                recovery_action="retry",
                user_message="Audio validation failed. Please try again."
            )

    # ========================================================================
    # Error Scenario 2: JSON Parsing Errors
    # ========================================================================

    async def handle_json_parse_error(
        self,
        raw_response: Any,
        error: Exception
    ) -> ErrorRecoveryResult:
        """
        Handle JSON parsing errors from Flash-Lite.

        Strategy: Fall back to Live API if enabled, otherwise return error.

        Args:
            raw_response: Raw response from Flash-Lite
            error: Parsing error

        Returns:
            ErrorRecoveryResult
        """
        _log.error(
            "json_parse_error",
            error=str(error),
            response_type=type(raw_response).__name__,
            session_id=self._session_id
        )

        if self._fallback_to_live_api:
            # Fall back to Live API
            await self._send_error(
                error_code="json_parse_error",
                message="Switching to alternative processing method",
                recoverable=True,
                fallback_activated=True,
                user_message="Processing via alternative method..."
            )

            return ErrorRecoveryResult(
                success=True,  # Recovery successful via fallback
                error_type="json_parse_error",
                recovery_action="fallback_to_live_api",
                fallback_activated=True,
                user_message="Processing via alternative method..."
            )
        else:
            # No fallback available
            await self._send_error(
                error_code="json_parse_error",
                message="Response parsing failed. Please try again.",
                recoverable=True,
                user_message="Sorry, there was an error. Please try again."
            )

            return ErrorRecoveryResult(
                success=False,
                error_type="json_parse_error",
                recovery_action="user_retry",
                user_message="Please try again."
            )

    # ========================================================================
    # Error Scenario 3: Unsupported Language
    # ========================================================================

    async def handle_unsupported_language(
        self,
        detected_language: str,
        supported_languages: list
    ) -> ErrorRecoveryResult:
        """
        Handle unsupported language detection.

        Strategy: Default to English and inform user.

        Args:
            detected_language: Detected language code
            supported_languages: List of supported language codes

        Returns:
            ErrorRecoveryResult
        """
        _log.warning(
            "unsupported_language",
            detected=detected_language,
            supported_count=len(supported_languages),
            session_id=self._session_id
        )

        # Send language status with fallback
        await self._websocket.send_json({
            "type": "language_status",
            "detected": detected_language,
            "current": DEFAULT_FALLBACK_LANGUAGE,
            "confidence": 0.5,
            "fallback": True
        })

        return ErrorRecoveryResult(
            success=True,  # Recovery successful
            error_type="unsupported_language",
            recovery_action="fallback_to_english",
            user_message="Continuing in English",
            details={"detected": detected_language, "fallback": DEFAULT_FALLBACK_LANGUAGE}
        )

    # ========================================================================
    # Error Scenario 4: TTS Quota Exceeded
    # ========================================================================

    async def handle_tts_quota_exceeded(
        self,
        transcript_text: str
    ) -> ErrorRecoveryResult:
        """
        Handle TTS quota exceeded errors.

        Strategy: Return text-only response without audio.

        Args:
            transcript_text: Text to display instead of speaking

        Returns:
            ErrorRecoveryResult
        """
        _log.warning(
            "tts_quota_exceeded",
            session_id=self._session_id
        )

        # Send text-only response
        await self._websocket.send_json({
            "type": "text_response",
            "text": transcript_text,
            "audio_disabled": True,
            "reason": "quota_exceeded"
        })

        await self._send_error(
            error_code="tts_quota_exceeded",
            message="Text-to-speech temporarily unavailable. Showing text response.",
            recoverable=True,
            user_message="Audio temporarily unavailable"
        )

        return ErrorRecoveryResult(
            success=True,  # Recovery successful
            error_type="tts_quota_exceeded",
            recovery_action="text_only_response",
            user_message="Audio temporarily unavailable. Please read the text response."
        )

    # ========================================================================
    # Error Scenario 5: Network Timeout with Retry
    # ========================================================================

    async def retry_with_backoff(
        self,
        operation: Callable,
        operation_name: str,
        max_attempts: int = MAX_RETRY_ATTEMPTS
    ) -> ErrorRecoveryResult:
        """
        Retry an operation with exponential backoff.

        Strategy: Retry up to max_attempts with exponential backoff (2^n seconds).

        Args:
            operation: Async function to retry
            operation_name: Name of operation for logging
            max_attempts: Maximum retry attempts

        Returns:
            ErrorRecoveryResult
        """
        for attempt in range(1, max_attempts + 1):
            try:
                _log.info(
                    "retry_attempt",
                    operation=operation_name,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    session_id=self._session_id
                )

                # Send status to user
                if attempt > 1:
                    await self._websocket.send_json({
                        "type": "retry_status",
                        "operation": operation_name,
                        "attempt": attempt,
                        "max_attempts": max_attempts
                    })

                # Try operation
                result = await operation()

                _log.info(
                    "retry_succeeded",
                    operation=operation_name,
                    attempt=attempt,
                    session_id=self._session_id
                )

                return ErrorRecoveryResult(
                    success=True,
                    error_type="none",
                    recovery_action="retry",
                    details={"attempts": attempt}
                )

            except Exception as e:
                _log.warning(
                    "retry_failed",
                    operation=operation_name,
                    attempt=attempt,
                    error=str(e),
                    session_id=self._session_id
                )

                if attempt < max_attempts:
                    # Calculate backoff delay
                    delay = RETRY_BACKOFF_BASE ** attempt
                    _log.info(
                        "retry_backoff",
                        delay=delay,
                        session_id=self._session_id
                    )
                    await asyncio.sleep(delay)
                else:
                    # All attempts exhausted
                    await self._send_error(
                        error_code="operation_failed",
                        message=f"{operation_name} failed after {max_attempts} attempts",
                        recoverable=True,
                        user_message="Connection issue. Please try again."
                    )

                    return ErrorRecoveryResult(
                        success=False,
                        error_type="network_timeout",
                        recovery_action="exhausted_retries",
                        user_message="Connection issue. Please try again.",
                        details={"attempts": max_attempts}
                    )

    # ========================================================================
    # Error Scenario 6: Invalid Tool Call
    # ========================================================================

    async def handle_invalid_tool_call(
        self,
        tool_name: str,
        error: Exception
    ) -> ErrorRecoveryResult:
        """
        Handle invalid or failed tool calls.

        Strategy: Log error and continue (don't fail entire pipeline).

        Args:
            tool_name: Name of tool that failed
            error: Error that occurred

        Returns:
            ErrorRecoveryResult
        """
        _log.error(
            "tool_call_failed",
            tool=tool_name,
            error=str(error),
            session_id=self._session_id
        )

        # Log but don't interrupt user experience
        # Tool call failures are non-critical

        return ErrorRecoveryResult(
            success=True,  # Recovery successful (silent)
            error_type="tool_call_error",
            recovery_action="log_and_continue",
            details={"tool": tool_name, "error": str(error)}
        )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _send_error(
        self,
        error_code: str,
        message: str,
        recoverable: bool = True,
        fallback_activated: bool = False,
        user_message: Optional[str] = None
    ) -> None:
        """Send error message to frontend."""
        if self._websocket:
            await self._websocket.send_json({
                "type": "half_cascade_error",
                "error_code": error_code,
                "message": message,
                "recoverable": recoverable,
                "fallback_activated": fallback_activated,
                "user_message": user_message or message
            })
