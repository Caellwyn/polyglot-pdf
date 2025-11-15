"""
Parser for structured outputs from Gemini Flash-Lite in half-cascade architecture.

Handles parsing, validation, and extraction of components from Flash-Lite
responses following the structured output schema.
"""

import json
from typing import Dict, List, Tuple, Optional, Any
import structlog
from pydantic import ValidationError

from backend.models.half_cascade_schema import (
    FlashLiteResponse,
    ResponseSegment,
    ToolCall,
    SUPPORTED_LANGUAGES
)

_log = structlog.get_logger().bind(module="structured_output_parser")


class StructuredOutputParser:
    """Parser for Flash-Lite structured JSON responses."""

    def __init__(self):
        """Initialize the parser."""
        self._supported_languages = set(SUPPORTED_LANGUAGES)

    def parse_response(self, raw_response: str | dict) -> FlashLiteResponse:
        """
        Parse and validate a Flash-Lite response.

        Args:
            raw_response: Raw JSON string or dict from Flash-Lite

        Returns:
            FlashLiteResponse: Validated response object

        Raises:
            ValueError: If response is invalid JSON or doesn't match schema
            ValidationError: If Pydantic validation fails
        """
        # Parse JSON if string
        if isinstance(raw_response, str):
            try:
                response_dict = json.loads(raw_response)
            except json.JSONDecodeError as e:
                _log.error("json_parse_failed", error=str(e))
                raise ValueError(f"Invalid JSON response: {e}")
        else:
            response_dict = raw_response

        # Validate against Pydantic model
        try:
            response = FlashLiteResponse(**response_dict)
            _log.info(
                "response_parsed",
                language=response.detected_language,
                segments=len(response.segments),
                tool_calls=len(response.tool_calls) if response.tool_calls else 0,
                transcript_length=len(response.user_transcript)
            )
            return response
        except ValidationError as e:
            _log.error(
                "validation_failed",
                error=str(e),
                response_keys=list(response_dict.keys())
            )
            raise

    def extract_conversation_entries(
        self,
        response: FlashLiteResponse
    ) -> Tuple[str, str]:
        """
        Extract conversation history entries from response.

        Used to build conversation history that's sent with next request
        for context continuity.

        Args:
            response: Parsed Flash-Lite response

        Returns:
            Tuple of (user_message, assistant_message)
        """
        user_message = response.user_transcript

        # Combine all segments into single assistant message
        assistant_message = " ".join(
            segment.text for segment in response.segments
        )

        return user_message, assistant_message

    def extract_tts_segments(
        self,
        response: FlashLiteResponse
    ) -> List[Tuple[str, str]]:
        """
        Extract segments for TTS processing.

        Returns segments as (text, language) tuples for routing to
        appropriate TTS language model.

        Args:
            response: Parsed Flash-Lite response

        Returns:
            List of (text, language_code) tuples
        """
        segments = []
        for segment in response.segments:
            # Validate language is supported
            if segment.language not in self._supported_languages:
                _log.warning(
                    "unsupported_language_in_segment",
                    language=segment.language,
                    fallback="en-US"
                )
                # Fallback to English
                language = "en-US"
            else:
                language = segment.language

            segments.append((segment.text, language))

        return segments

    def extract_tool_calls(
        self,
        response: FlashLiteResponse
    ) -> List[Dict[str, Any]]:
        """
        Extract tool calls for execution.

        Returns tool calls in format compatible with existing
        tool execution infrastructure.

        Args:
            response: Parsed Flash-Lite response

        Returns:
            List of tool call dicts with 'tool' and 'args' keys
        """
        if not response.tool_calls:
            return []

        tool_calls = []
        for tool_call in response.tool_calls:
            tool_calls.append({
                "tool": tool_call.tool,
                "args": tool_call.args
            })

        _log.info(
            "tool_calls_extracted",
            count=len(tool_calls),
            tools=[tc["tool"] for tc in tool_calls]
        )

        return tool_calls

    def validate_language_support(self, language_code: str) -> bool:
        """
        Check if a language code is supported.

        Args:
            language_code: BCP 47 language code

        Returns:
            bool: True if language is supported
        """
        return language_code in self._supported_languages

    def get_fallback_language(self, unsupported_language: str) -> str:
        """
        Get fallback language for unsupported language codes.

        Args:
            unsupported_language: Unsupported language code

        Returns:
            str: Fallback language code (default: "en-US")
        """
        # Try to match by language family (e.g., 'en-GB' -> 'en-US')
        if "-" in unsupported_language:
            base_lang = unsupported_language.split("-")[0]
            for supported in self._supported_languages:
                if supported.startswith(base_lang + "-"):
                    _log.info(
                        "language_fallback",
                        requested=unsupported_language,
                        fallback=supported
                    )
                    return supported

        # Default fallback to English
        _log.warning(
            "language_fallback_to_default",
            requested=unsupported_language,
            fallback="en-US"
        )
        return "en-US"


# Singleton instance for convenience
_parser_instance: Optional[StructuredOutputParser] = None


def get_parser() -> StructuredOutputParser:
    """Get singleton parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = StructuredOutputParser()
    return _parser_instance
