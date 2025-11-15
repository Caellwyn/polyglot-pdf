"""
Tests for structured output parser (Phase 1C).

Tests parsing, validation, and extraction of Flash-Lite responses.
"""

import pytest
import json
from pydantic import ValidationError

from backend.models.half_cascade_schema import (
    FlashLiteResponse,
    ResponseSegment,
    ToolCall,
    SUPPORTED_LANGUAGES,
    generate_json_schema_for_gemini
)
from backend.services.structured_output_parser import (
    StructuredOutputParser,
    get_parser
)


class TestFlashLiteResponseModel:
    """Test the Pydantic model for Flash-Lite responses."""

    def test_valid_response(self):
        """Test parsing a valid response."""
        data = {
            "user_transcript": "My name is John Smith",
            "detected_language": "en-US",
            "segments": [
                {
                    "text": "Thank you, John.",
                    "language": "en-US",
                    "confidence": 0.98
                }
            ],
            "tool_calls": [
                {
                    "tool": "update_form_fields",
                    "args": {"field_id": "name", "value": "John Smith"}
                }
            ]
        }

        response = FlashLiteResponse(**data)

        assert response.user_transcript == "My name is John Smith"
        assert response.detected_language == "en-US"
        assert len(response.segments) == 1
        assert response.segments[0].text == "Thank you, John."
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].tool == "update_form_fields"

    def test_minimal_response(self):
        """Test response with only required fields."""
        data = {
            "user_transcript": "Hello",
            "detected_language": "en-US",
            "segments": []
        }

        response = FlashLiteResponse(**data)

        assert response.user_transcript == "Hello"
        assert response.detected_language == "en-US"
        assert len(response.segments) == 0
        assert len(response.tool_calls) == 0

    def test_empty_transcript_fails(self):
        """Test that empty transcript is rejected."""
        data = {
            "user_transcript": "",
            "detected_language": "en-US",
            "segments": []
        }

        with pytest.raises(ValidationError):
            FlashLiteResponse(**data)

    def test_invalid_language_code(self):
        """Test that invalid language codes are rejected."""
        data = {
            "user_transcript": "Hello",
            "detected_language": "x",  # Too short
            "segments": []
        }

        with pytest.raises(ValidationError):
            FlashLiteResponse(**data)

    def test_multiple_segments(self):
        """Test response with multiple segments."""
        data = {
            "user_transcript": "My name is John",
            "detected_language": "en-US",
            "segments": [
                {"text": "Gracias, ", "language": "es-ES"},
                {"text": "John.", "language": "en-US"}
            ]
        }

        response = FlashLiteResponse(**data)

        assert len(response.segments) == 2
        assert response.segments[0].language == "es-ES"
        assert response.segments[1].language == "en-US"

    def test_tool_call_validation(self):
        """Test tool call validation."""
        data = {
            "user_transcript": "Test",
            "detected_language": "en-US",
            "segments": [],
            "tool_calls": [
                {"tool": "", "args": {}}  # Empty tool name
            ]
        }

        with pytest.raises(ValidationError):
            FlashLiteResponse(**data)


class TestStructuredOutputParser:
    """Test the structured output parser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return StructuredOutputParser()

    def test_parse_json_string(self, parser):
        """Test parsing from JSON string."""
        json_str = json.dumps({
            "user_transcript": "Hello",
            "detected_language": "en-US",
            "segments": [
                {"text": "Hi there", "language": "en-US"}
            ]
        })

        response = parser.parse_response(json_str)

        assert response.user_transcript == "Hello"
        assert len(response.segments) == 1

    def test_parse_dict(self, parser):
        """Test parsing from dict."""
        data = {
            "user_transcript": "Hello",
            "detected_language": "en-US",
            "segments": []
        }

        response = parser.parse_response(data)

        assert response.user_transcript == "Hello"

    def test_parse_invalid_json(self, parser):
        """Test handling of invalid JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            parser.parse_response("{invalid json}")

    def test_extract_conversation_entries(self, parser):
        """Test extracting conversation history entries."""
        response = FlashLiteResponse(
            user_transcript="My name is John",
            detected_language="en-US",
            segments=[
                ResponseSegment(text="Thank you, ", language="en-US"),
                ResponseSegment(text="John.", language="en-US")
            ]
        )

        user_msg, assistant_msg = parser.extract_conversation_entries(response)

        assert user_msg == "My name is John"
        assert assistant_msg == "Thank you, John."

    def test_extract_tts_segments(self, parser):
        """Test extracting TTS segments."""
        response = FlashLiteResponse(
            user_transcript="Test",
            detected_language="en-US",
            segments=[
                ResponseSegment(text="Hello", language="en-US"),
                ResponseSegment(text="Hola", language="es-ES")
            ]
        )

        segments = parser.extract_tts_segments(response)

        assert len(segments) == 2
        assert segments[0] == ("Hello", "en-US")
        assert segments[1] == ("Hola", "es-ES")

    def test_extract_tts_segments_with_unsupported_language(self, parser):
        """Test TTS segment extraction with unsupported language."""
        response = FlashLiteResponse(
            user_transcript="Test",
            detected_language="en-US",
            segments=[
                ResponseSegment(text="Hello", language="xx-XX")  # Unsupported
            ]
        )

        segments = parser.extract_tts_segments(response)

        # Should fallback to English
        assert len(segments) == 1
        assert segments[0] == ("Hello", "en-US")

    def test_extract_tool_calls(self, parser):
        """Test extracting tool calls."""
        response = FlashLiteResponse(
            user_transcript="Test",
            detected_language="en-US",
            segments=[],
            tool_calls=[
                ToolCall(
                    tool="update_form_fields",
                    args={"field_id": "name", "value": "John"}
                ),
                ToolCall(
                    tool="get_form_status",
                    args={}
                )
            ]
        )

        tool_calls = parser.extract_tool_calls(response)

        assert len(tool_calls) == 2
        assert tool_calls[0]["tool"] == "update_form_fields"
        assert tool_calls[0]["args"]["field_id"] == "name"
        assert tool_calls[1]["tool"] == "get_form_status"

    def test_extract_tool_calls_empty(self, parser):
        """Test extracting tool calls when none present."""
        response = FlashLiteResponse(
            user_transcript="Test",
            detected_language="en-US",
            segments=[]
        )

        tool_calls = parser.extract_tool_calls(response)

        assert tool_calls == []

    def test_validate_language_support(self, parser):
        """Test language support validation."""
        assert parser.validate_language_support("en-US") is True
        assert parser.validate_language_support("es-ES") is True
        assert parser.validate_language_support("xx-XX") is False

    def test_get_fallback_language(self, parser):
        """Test fallback language selection."""
        # Exact match family
        assert parser.get_fallback_language("en-GB") == "en-US"

        # No match - fallback to English
        assert parser.get_fallback_language("xx-XX") == "en-US"

    def test_singleton_parser(self):
        """Test that get_parser returns singleton."""
        parser1 = get_parser()
        parser2 = get_parser()

        assert parser1 is parser2


class TestResponseSegment:
    """Test the ResponseSegment model."""

    def test_valid_segment(self):
        """Test creating a valid segment."""
        segment = ResponseSegment(
            text="Hello",
            language="en-US",
            confidence=0.95
        )

        assert segment.text == "Hello"
        assert segment.language == "en-US"
        assert segment.confidence == 0.95

    def test_segment_without_confidence(self):
        """Test segment without confidence score."""
        segment = ResponseSegment(
            text="Hello",
            language="en-US"
        )

        assert segment.confidence is None

    def test_invalid_language_format(self):
        """Test invalid language format rejection."""
        with pytest.raises(ValidationError):
            ResponseSegment(
                text="Hello",
                language="eng-US-extra"  # Too many parts
            )


class TestToolCall:
    """Test the ToolCall model."""

    def test_valid_tool_call(self):
        """Test creating a valid tool call."""
        tool_call = ToolCall(
            tool="update_form_fields",
            args={"field_id": "name", "value": "John"}
        )

        assert tool_call.tool == "update_form_fields"
        assert tool_call.args["field_id"] == "name"

    def test_empty_args(self):
        """Test tool call with empty args."""
        tool_call = ToolCall(tool="get_form_status", args={})

        assert tool_call.args == {}

    def test_empty_tool_name_fails(self):
        """Test that empty tool name is rejected."""
        with pytest.raises(ValidationError):
            ToolCall(tool="", args={})


class TestGeminiJSONSchema:
    """Test JSON schema generation for Gemini API."""

    def test_schema_generation(self):
        """Test generating JSON schema for Gemini."""
        schema = generate_json_schema_for_gemini()

        assert schema["type"] == "object"
        assert "user_transcript" in schema["properties"]
        assert "detected_language" in schema["properties"]
        assert "segments" in schema["properties"]
        assert "tool_calls" in schema["properties"]

    def test_schema_required_fields(self):
        """Test that required fields are specified."""
        schema = generate_json_schema_for_gemini()

        assert "user_transcript" in schema["required"]
        assert "detected_language" in schema["required"]
        assert "segments" in schema["required"]

    def test_schema_language_enum(self):
        """Test that language enum includes supported languages."""
        schema = generate_json_schema_for_gemini()

        lang_enum = schema["properties"]["detected_language"]["enum"]

        assert "en-US" in lang_enum
        assert "es-ES" in lang_enum
        assert "zh-CN" in lang_enum
        assert len(lang_enum) == len(SUPPORTED_LANGUAGES)

    def test_schema_segments_structure(self):
        """Test segments array structure in schema."""
        schema = generate_json_schema_for_gemini()

        segments = schema["properties"]["segments"]

        assert segments["type"] == "array"
        assert "items" in segments
        assert "text" in segments["items"]["properties"]
        assert "language" in segments["items"]["properties"]
