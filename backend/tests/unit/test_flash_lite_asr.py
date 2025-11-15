"""
Tests for Flash-Lite ASR service (Phase 2A).

Tests audio processing, context building, API integration, and response parsing.
"""

import pytest
import json
import base64
from unittest.mock import AsyncMock, Mock, patch

from backend.services.flash_lite_asr import (
    FlashLiteASR,
    create_flash_lite_asr
)
from backend.models.half_cascade_schema import FlashLiteResponse


class TestFlashLiteASRInit:
    """Test Flash-Lite ASR initialization."""

    def test_initialization(self):
        """Test basic initialization."""
        asr = FlashLiteASR(
            api_key="test_key",
            model="gemini-2.5-flash-lite-preview",
            session_id="test_session"
        )

        assert asr._api_key == "test_key"
        assert asr._model == "gemini-2.5-flash-lite-preview"
        assert asr._session_id == "test_session"
        assert asr._system_instruction is not None

    def test_default_model(self):
        """Test default model selection."""
        asr = FlashLiteASR(api_key="test_key")

        assert asr._model == FlashLiteASR.DEFAULT_MODEL

    def test_factory_function(self):
        """Test factory function."""
        asr = create_flash_lite_asr(
            api_key="test_key",
            model="custom-model",
            session_id="test"
        )

        assert isinstance(asr, FlashLiteASR)
        assert asr._model == "custom-model"


class TestSystemInstruction:
    """Test system instruction building."""

    def test_system_instruction_content(self):
        """Test that system instruction contains key elements."""
        asr = FlashLiteASR(api_key="test_key")

        instruction = asr._system_instruction

        # Check for key components
        assert "multilingual" in instruction.lower()
        assert "JSON" in instruction
        assert "user_transcript" in instruction
        assert "detected_language" in instruction
        assert "tool_calls" in instruction
        assert "form" in instruction.lower()

    def test_system_instruction_language_handling(self):
        """Test language handling instructions."""
        asr = FlashLiteASR(api_key="test_key")

        instruction = asr._system_instruction

        assert "language" in instruction.lower()
        assert "english" in instruction.lower()
        assert "bcp 47" in instruction.lower()


class TestContextBuilding:
    """Test context string building."""

    @pytest.fixture
    def asr(self):
        """Create ASR instance."""
        return FlashLiteASR(api_key="test_key")

    def test_context_with_form_state(self, asr):
        """Test context building with form state."""
        form_schema = {"id": "test_form", "fields": []}
        form_state = {
            "field1": "value1",
            "field2": "value2"
        }
        conversation_history = []

        context = asr._build_context(
            form_schema=form_schema,
            form_state=form_state,
            conversation_history=conversation_history,
            current_field="field3",
            current_part="part_1"
        )

        assert "field1:value1" in context
        assert "field2:value2" in context
        assert "field3" in context
        assert "part_1" in context

    def test_context_with_conversation_history(self, asr):
        """Test context building with conversation history."""
        form_schema = {"id": "test_form"}
        form_state = {}
        conversation_history = [
            {"role": "user", "content": "My name is John"},
            {"role": "assistant", "content": "Thank you, John"}
        ]

        context = asr._build_context(
            form_schema=form_schema,
            form_state=form_state,
            conversation_history=conversation_history,
            current_field=None,
            current_part=None
        )

        assert "User: My name is John" in context
        assert "Assistant: Thank you, John" in context

    def test_context_with_empty_state(self, asr):
        """Test context with empty form state."""
        form_schema = {"id": "test_form"}
        form_state = {}
        conversation_history = []

        context = asr._build_context(
            form_schema=form_schema,
            form_state=form_state,
            conversation_history=conversation_history,
            current_field=None,
            current_part=None
        )

        assert "(empty)" in context
        assert "(no history)" in context

    def test_context_limits_history(self, asr):
        """Test that context limits conversation history."""
        form_schema = {"id": "test_form"}
        form_state = {}

        # Create 20 conversation turns
        conversation_history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(20)
        ]

        context = asr._build_context(
            form_schema=form_schema,
            form_state=form_state,
            conversation_history=conversation_history,
            current_field=None,
            current_part=None
        )

        # Should only include last 10
        assert "Message 19" in context
        assert "Message 10" in context
        assert "Message 0" not in context


class TestRequestPayloadBuilding:
    """Test API request payload building."""

    @pytest.fixture
    def asr(self):
        """Create ASR instance."""
        return FlashLiteASR(api_key="test_key")

    def test_payload_structure(self, asr):
        """Test request payload structure."""
        audio_b64 = base64.b64encode(b"test_audio").decode('utf-8')
        context = "test context"

        payload = asr._build_request_payload(
            audio_b64=audio_b64,
            context=context
        )

        # Check structure
        assert "contents" in payload
        assert "systemInstruction" in payload
        assert "generationConfig" in payload

        # Check generation config
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseSchema" in payload["generationConfig"]

    def test_payload_includes_audio(self, asr):
        """Test that payload includes audio data."""
        audio_bytes = b"test_audio_data"
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        context = "test"

        payload = asr._build_request_payload(
            audio_b64=audio_b64,
            context=context
        )

        # Find audio part
        parts = payload["contents"][0]["parts"]
        audio_part = next(
            (p for p in parts if "inline_data" in p),
            None
        )

        assert audio_part is not None
        assert audio_part["inline_data"]["data"] == audio_b64
        assert "audio/pcm" in audio_part["inline_data"]["mime_type"]

    def test_payload_includes_context(self, asr):
        """Test that payload includes context text."""
        audio_b64 = "dGVzdA=="  # "test" in base64
        context = "This is the context"

        payload = asr._build_request_payload(
            audio_b64=audio_b64,
            context=context
        )

        # Find text part
        parts = payload["contents"][0]["parts"]
        text_part = next(
            (p for p in parts if "text" in p),
            None
        )

        assert text_part is not None
        assert text_part["text"] == context


class TestResponseParsing:
    """Test API response parsing."""

    @pytest.fixture
    def asr(self):
        """Create ASR instance."""
        return FlashLiteASR(api_key="test_key")

    def test_parse_valid_response(self, asr):
        """Test parsing a valid API response."""
        api_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({
                                    "user_transcript": "Hello",
                                    "detected_language": "en-US",
                                    "segments": [
                                        {
                                            "text": "Hi there",
                                            "language": "en-US"
                                        }
                                    ],
                                    "tool_calls": []
                                })
                            }
                        ]
                    }
                }
            ]
        }

        response = asr._parse_response(api_response)

        assert isinstance(response, FlashLiteResponse)
        assert response.user_transcript == "Hello"
        assert response.detected_language == "en-US"
        assert len(response.segments) == 1

    def test_parse_response_with_tool_calls(self, asr):
        """Test parsing response with tool calls."""
        api_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({
                                    "user_transcript": "My name is John",
                                    "detected_language": "en-US",
                                    "segments": [
                                        {
                                            "text": "Got it",
                                            "language": "en-US"
                                        }
                                    ],
                                    "tool_calls": [
                                        {
                                            "tool": "update_form_fields",
                                            "args": {
                                                "field_id": "name",
                                                "value": "John"
                                            }
                                        }
                                    ]
                                })
                            }
                        ]
                    }
                }
            ]
        }

        response = asr._parse_response(api_response)

        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].tool == "update_form_fields"

    def test_parse_empty_candidates_fails(self, asr):
        """Test that empty candidates raises error."""
        api_response = {"candidates": []}

        with pytest.raises(ValueError, match="No candidates"):
            asr._parse_response(api_response)

    def test_parse_missing_parts_fails(self, asr):
        """Test that missing parts raises error."""
        api_response = {
            "candidates": [
                {
                    "content": {
                        "parts": []
                    }
                }
            ]
        }

        with pytest.raises(ValueError, match="No parts"):
            asr._parse_response(api_response)

    def test_parse_empty_text_fails(self, asr):
        """Test that empty text raises error."""
        api_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": ""
                            }
                        ]
                    }
                }
            ]
        }

        with pytest.raises(ValueError, match="Empty response"):
            asr._parse_response(api_response)


class TestIntegration:
    """Integration tests for complete workflow."""

    @pytest.fixture
    def mock_httpx_client(self):
        """Mock httpx client."""
        with patch('backend.services.flash_lite_asr.httpx.AsyncClient') as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_transcribe_and_respond_success(self, mock_httpx_client):
        """Test complete transcribe and respond workflow."""
        # Setup mock response
        mock_client = AsyncMock()
        mock_httpx_client.return_value = mock_client

        mock_response = Mock()
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({
                                    "user_transcript": "My name is John",
                                    "detected_language": "en-US",
                                    "segments": [
                                        {
                                            "text": "Thank you, John",
                                            "language": "en-US"
                                        }
                                    ],
                                    "tool_calls": []
                                })
                            }
                        ]
                    }
                }
            ]
        }
        mock_client.post.return_value = mock_response

        # Create ASR and send request
        asr = FlashLiteASR(api_key="test_key")

        audio_bytes = b"test_audio_data" * 100
        form_schema = {"id": "test_form", "fields": []}
        form_state = {}
        conversation_history = []

        response = await asr.transcribe_and_respond(
            audio_bytes=audio_bytes,
            form_schema=form_schema,
            form_state=form_state,
            conversation_history=conversation_history
        )

        # Verify response
        assert isinstance(response, FlashLiteResponse)
        assert response.user_transcript == "My name is John"
        assert response.detected_language == "en-US"

        # Verify API was called
        assert mock_client.post.called

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup closes HTTP client."""
        with patch('backend.services.flash_lite_asr.httpx.AsyncClient') as mock:
            mock_client = AsyncMock()
            mock.return_value = mock_client

            asr = FlashLiteASR(api_key="test_key")

            await asr.cleanup()

            # Verify client was closed
            mock_client.aclose.assert_called_once()


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_api_request_failure(self):
        """Test handling of API request failures."""
        with patch('backend.services.flash_lite_asr.httpx.AsyncClient') as mock:
            mock_client = AsyncMock()
            mock.return_value = mock_client

            # Simulate API error
            mock_client.post.side_effect = Exception("API Error")

            asr = FlashLiteASR(api_key="test_key")

            with pytest.raises(Exception, match="API Error"):
                await asr.transcribe_and_respond(
                    audio_bytes=b"test",
                    form_schema={},
                    form_state={},
                    conversation_history=[]
                )

    @pytest.mark.asyncio
    async def test_invalid_json_response(self):
        """Test handling of invalid JSON in response."""
        with patch('backend.services.flash_lite_asr.httpx.AsyncClient') as mock:
            mock_client = AsyncMock()
            mock.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "invalid json {"
                                }
                            ]
                        }
                    }
                ]
            }
            mock_client.post.return_value = mock_response

            asr = FlashLiteASR(api_key="test_key")

            with pytest.raises(Exception):  # Should raise parsing error
                await asr.transcribe_and_respond(
                    audio_bytes=b"test",
                    form_schema={},
                    form_state={},
                    conversation_history=[]
                )
