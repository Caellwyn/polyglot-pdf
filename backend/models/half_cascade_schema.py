"""
Structured output schema for Half-Cascade architecture.

Defines the JSON schema that Gemini Flash-Lite will return when processing
audio input. This schema includes user transcript, language detection,
response segments with language tags, and tool calls.

Based on HALF_CASCADE_IMPLEMENTATION.md Phase 1C specification.
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field, validator


class ResponseSegment(BaseModel):
    """A segment of the assistant's response with language tagging."""

    text: str = Field(..., description="Text content of this segment")
    language: str = Field(
        ...,
        description="BCP 47 language code (e.g., 'en-US', 'es-ES', 'zh-CN')"
    )
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence score for language detection (0.0-1.0)"
    )

    @validator('language')
    def validate_language_code(cls, v):
        """Validate that language code follows BCP 47 format."""
        # Basic validation - should be in format like 'en-US' or 'zh-CN'
        if not v or len(v) < 2:
            raise ValueError("Language code must be at least 2 characters")
        # Allow both 'en' and 'en-US' formats
        parts = v.split('-')
        if len(parts) > 2:
            raise ValueError("Invalid BCP 47 language code format")
        return v


class ToolCall(BaseModel):
    """A tool call request from the AI."""

    tool: str = Field(..., description="Name of the tool to call")
    args: dict = Field(
        default_factory=dict,
        description="Arguments to pass to the tool"
    )

    @validator('tool')
    def validate_tool_name(cls, v):
        """Validate that tool name is not empty."""
        if not v or not v.strip():
            raise ValueError("Tool name cannot be empty")
        return v.strip()


class FlashLiteResponse(BaseModel):
    """
    Structured response from Gemini Flash-Lite in half-cascade architecture.

    This schema is used for:
    1. Parsing responses from Flash-Lite after audio processing
    2. Validating response structure
    3. Extracting transcript for conversation history
    4. Routing segments to appropriate TTS language models
    5. Executing tool calls for form updates
    """

    user_transcript: str = Field(
        ...,
        description="Transcription of user's spoken input (for conversation history)"
    )

    detected_language: str = Field(
        ...,
        description="Primary detected language of user's speech (BCP 47 code)"
    )

    segments: List[ResponseSegment] = Field(
        default_factory=list,
        description="Response segments with language tags for TTS routing"
    )

    tool_calls: Optional[List[ToolCall]] = Field(
        default_factory=list,
        description="Tool calls to execute (e.g., update_form_fields)"
    )

    @validator('detected_language')
    def validate_detected_language(cls, v):
        """Validate detected language follows BCP 47 format."""
        if not v or len(v) < 2:
            raise ValueError("Detected language must be valid BCP 47 code")
        return v

    @validator('user_transcript')
    def validate_transcript_not_empty(cls, v):
        """Ensure user transcript is not empty."""
        if not v or not v.strip():
            raise ValueError("User transcript cannot be empty")
        return v.strip()

    class Config:
        """Pydantic configuration."""
        schema_extra = {
            "example": {
                "user_transcript": "My name is John Smith",
                "detected_language": "en-US",
                "segments": [
                    {
                        "text": "Thank you, John. What is your phone number?",
                        "language": "en-US",
                        "confidence": 0.98
                    }
                ],
                "tool_calls": [
                    {
                        "tool": "update_form_fields",
                        "args": {
                            "field_id": "Part1_Text1",
                            "value": "John Smith"
                        }
                    }
                ]
            }
        }


# Supported languages for the half-cascade system
# Based on Gemini Live API language support
SUPPORTED_LANGUAGES = [
    "en-US",  # English (United States)
    "es-ES",  # Spanish (Spain)
    "es-MX",  # Spanish (Mexico)
    "zh-CN",  # Chinese (Simplified)
    "zh-TW",  # Chinese (Traditional)
    "ko-KR",  # Korean
    "ar-SA",  # Arabic (Saudi Arabia)
    "fr-FR",  # French
    "pt-BR",  # Portuguese (Brazil)
    "ru-RU",  # Russian
    "ja-JP",  # Japanese
    "hi-IN",  # Hindi
    "de-DE",  # German
    "it-IT",  # Italian
    "vi-VN",  # Vietnamese
    "tl-PH",  # Tagalog (Philippines)
    "bn-BD",  # Bengali
    "ur-PK",  # Urdu (Pakistan)
    "fa-IR",  # Farsi/Persian (Iran)
    "tr-TR",  # Turkish
    "pl-PL",  # Polish
]


def generate_json_schema_for_gemini() -> dict:
    """
    Generate the JSON schema to send to Gemini Flash-Lite API.

    This schema instructs Flash-Lite to return structured JSON matching
    the FlashLiteResponse model.

    Returns:
        dict: JSON schema compatible with Gemini's structured output format
    """
    return {
        "type": "object",
        "properties": {
            "user_transcript": {
                "type": "string",
                "description": "Transcription of the user's spoken input"
            },
            "detected_language": {
                "type": "string",
                "description": "Primary detected language (BCP 47 code)",
                "enum": SUPPORTED_LANGUAGES
            },
            "segments": {
                "type": "array",
                "description": "Response segments with language tags",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text content of this segment"
                        },
                        "language": {
                            "type": "string",
                            "description": "Language code for this segment",
                            "enum": SUPPORTED_LANGUAGES
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score (0.0-1.0)",
                            "minimum": 0.0,
                            "maximum": 1.0
                        }
                    },
                    "required": ["text", "language"]
                }
            },
            "tool_calls": {
                "type": "array",
                "description": "Tool calls to execute",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "description": "Name of the tool"
                        },
                        "args": {
                            "type": "object",
                            "description": "Tool arguments"
                        }
                    },
                    "required": ["tool", "args"]
                }
            }
        },
        "required": ["user_transcript", "detected_language", "segments"]
    }
