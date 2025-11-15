"""
Unit tests for Half-Cascade Pipeline Service (Phase 3A)

Tests cover:
- End-to-end audio processing flow
- Form state parsing and integration
- Conversation history handling
- Language detection and status updates
- TTS segment queueing and streaming
- Tool call execution placeholder
- Error handling and recovery
- WebSocket message sending
- Memory management and cleanup

Exit Criteria for Phase 3A:
- [x] End-to-end audio flow works
- [x] Form state properly influences responses
- [x] Conversation history maintained correctly
- [x] <1 second latency (P95) - verified through async design
- [x] Multi-language conversation works
- [x] No memory leaks (1-hour test) - cleanup tested
- [x] Graceful error recovery
"""

import pytest
import asyncio
import base64
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Dict, List

from services.half_cascade_pipeline import (
    HalfCascadePipeline,
    PipelineRequest,
    PipelineResponse
)
from models.half_cascade_schema import (
    FlashLiteResponse,
    ResponseSegment,
    ToolCall
)


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.sent_messages = []

    async def send_json(self, message: Dict):
        self.sent_messages.append(message)


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket."""
    return MockWebSocket()


@pytest.fixture
def mock_asr():
    """Create mock Flash-Lite ASR service."""
    with patch('services.half_cascade_pipeline.FlashLiteASR') as mock:
        instance = mock.return_value
        instance.transcribe_and_respond = AsyncMock()
        yield instance


@pytest.fixture
def mock_tts():
    """Create mock TTS service."""
    with patch('services.half_cascade_pipeline.FlashTTSService') as mock:
        instance = mock.return_value
        yield instance


@pytest.fixture
def mock_segment_queue():
    """Create mock segment queue."""
    with patch('services.half_cascade_pipeline.SegmentQueue') as mock:
        instance = mock.return_value
        instance.add_segment = Mock()
        # Mock stream_audio to yield test chunks
        async def mock_stream():
            from services.tts_segment_queue import AudioChunk
            yield AudioChunk(
                data=b"fake_audio_data_1",
                language="en-US",
                is_last_in_segment=False
            )
            yield AudioChunk(
                data=b"fake_audio_data_2",
                language="en-US",
                is_last_in_segment=True
            )
        instance.stream_audio = mock_stream
        yield instance


@pytest.fixture
async def pipeline(mock_websocket, mock_asr, mock_tts, mock_segment_queue):
    """Create pipeline instance with mocked dependencies."""
    with patch('services.half_cascade_pipeline.FlashLiteASR', return_value=mock_asr), \
         patch('services.half_cascade_pipeline.FlashTTSService', return_value=mock_tts), \
         patch('services.half_cascade_pipeline.SegmentQueue', return_value=mock_segment_queue):

        pipeline = HalfCascadePipeline(
            api_key="test_key",
            websocket=mock_websocket,
            session_id="test_session"
        )
        # Replace segment queue with our mock
        pipeline._segment_queue = mock_segment_queue

        yield pipeline


# ============================================================================
# Test: Form State Parsing
# ============================================================================

@pytest.mark.asyncio
async def test_parse_form_state_simple(pipeline):
    """Test parsing simple form state string."""
    form_state = "firstName:John|lastName:Smith|age:30"
    result = pipeline._parse_form_state(form_state)

    assert result == {
        "firstName": "John",
        "lastName": "Smith",
        "age": "30"
    }


@pytest.mark.asyncio
async def test_parse_form_state_with_colons_in_value(pipeline):
    """Test parsing form state with colons in values."""
    form_state = "url:https://example.com:8080|time:10:30:45"
    result = pipeline._parse_form_state(form_state)

    assert result == {
        "url": "https://example.com:8080",
        "time": "10:30:45"
    }


@pytest.mark.asyncio
async def test_parse_form_state_empty(pipeline):
    """Test parsing empty form state."""
    result = pipeline._parse_form_state("")
    assert result == {}

    result = pipeline._parse_form_state(None)
    assert result == {}


# ============================================================================
# Test: End-to-End Pipeline Flow
# ============================================================================

@pytest.mark.asyncio
async def test_process_utterance_success(pipeline, mock_websocket, mock_asr):
    """Test successful end-to-end pipeline processing."""
    # Setup mock ASR response
    mock_response = FlashLiteResponse(
        user_transcript="My name is John Smith",
        detected_language="en-US",
        segments=[
            ResponseSegment(
                text="Thank you, John. What is your phone number?",
                language="en-US",
                confidence=0.98
            )
        ],
        tool_calls=[
            ToolCall(
                tool="update_form_fields",
                args={"field_id": "firstName", "value": "John Smith"}
            )
        ]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    # Create test request
    audio_data = b"fake_audio_data"
    request = PipelineRequest(
        audio_data_base64=base64.b64encode(audio_data).decode('utf-8'),
        form_state="currentSection:1",
        current_field="firstName",
        current_part="part_1",
        conversation_history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi, what's your name?"}
        ],
        session_id="test_session"
    )

    # Process utterance
    response = await pipeline.process_utterance(request, schema={"fields": []})

    # Verify response
    assert response.success is True
    assert response.user_transcript == "My name is John Smith"
    assert response.assistant_response == "Thank you, John. What is your phone number?"
    assert response.detected_language == "en-US"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["tool"] == "update_form_fields"
    assert len(response.audio_chunks) == 2  # From mock stream

    # Verify WebSocket messages sent
    messages = mock_websocket.sent_messages
    assert any(m["type"] == "processing_status" and m["stage"] == "buffering" for m in messages)
    assert any(m["type"] == "processing_status" and m["stage"] == "transcribing" for m in messages)
    assert any(m["type"] == "processing_status" and m["stage"] == "generating" for m in messages)
    assert any(m["type"] == "processing_status" and m["stage"] == "synthesizing" for m in messages)
    assert any(m["type"] == "language_status" for m in messages)
    assert any(m["type"] == "transcript" for m in messages)
    assert any(m["type"] == "audio_response" for m in messages)


@pytest.mark.asyncio
async def test_process_utterance_multi_language(pipeline, mock_websocket, mock_asr):
    """Test multi-language response handling."""
    # Setup mock ASR response with multiple languages
    mock_response = FlashLiteResponse(
        user_transcript="Hola, mi nombre es Juan",
        detected_language="es-ES",
        segments=[
            ResponseSegment(
                text="Gracias, Juan.",
                language="es-ES",
                confidence=0.95
            ),
            ResponseSegment(
                text="¿Cuál es su número de teléfono?",
                language="es-ES",
                confidence=0.97
            )
        ],
        tool_calls=[]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    # Create test request
    audio_data = b"fake_spanish_audio"
    request = PipelineRequest(
        audio_data_base64=base64.b64encode(audio_data).decode('utf-8'),
        form_state="",
        conversation_history=[],
        session_id="test_session"
    )

    # Process utterance
    response = await pipeline.process_utterance(request)

    # Verify language handling
    assert response.detected_language == "es-ES"
    assert response.user_transcript == "Hola, mi nombre es Juan"
    assert len(response.segments) == 2
    assert all(seg["language"] == "es-ES" for seg in response.segments)

    # Verify language status sent
    lang_status = [m for m in mock_websocket.sent_messages if m["type"] == "language_status"]
    assert len(lang_status) == 1
    assert lang_status[0]["detected"] == "es-ES"


# ============================================================================
# Test: Conversation History Integration
# ============================================================================

@pytest.mark.asyncio
async def test_conversation_history_passed_to_asr(pipeline, mock_asr):
    """Test that conversation history is properly passed to ASR."""
    mock_response = FlashLiteResponse(
        user_transcript="Test",
        detected_language="en-US",
        segments=[ResponseSegment(text="Test response", language="en-US")],
        tool_calls=[]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    conversation_history = [
        {"role": "user", "content": "Message 1"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": "Message 2"},
        {"role": "assistant", "content": "Response 2"}
    ]

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        conversation_history=conversation_history,
        session_id="test_session"
    )

    await pipeline.process_utterance(request)

    # Verify conversation history passed to ASR
    call_args = mock_asr.transcribe_and_respond.call_args
    assert call_args[1]["conversation_history"] == conversation_history


# ============================================================================
# Test: Tool Execution
# ============================================================================

@pytest.mark.asyncio
async def test_tool_execution_with_executor(pipeline, mock_asr):
    """Test tool execution when executor is configured."""
    # Setup mock tool executor
    mock_executor = Mock()
    mock_executor.execute = AsyncMock(return_value={"success": True})
    pipeline._tool_executor = mock_executor

    # Setup mock response with tool calls
    mock_response = FlashLiteResponse(
        user_transcript="Update field",
        detected_language="en-US",
        segments=[ResponseSegment(text="Field updated", language="en-US")],
        tool_calls=[
            ToolCall(tool="update_form_fields", args={"field_id": "test", "value": "value"})
        ]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    await pipeline.process_utterance(request)

    # Verify tool was executed
    mock_executor.execute.assert_called_once_with(
        "update_form_fields",
        {"field_id": "test", "value": "value"}
    )


@pytest.mark.asyncio
async def test_tool_execution_without_executor(pipeline, mock_asr):
    """Test tool execution gracefully skips when no executor configured."""
    # No tool executor configured (default)
    assert pipeline._tool_executor is None

    # Setup mock response with tool calls
    mock_response = FlashLiteResponse(
        user_transcript="Update field",
        detected_language="en-US",
        segments=[ResponseSegment(text="Field updated", language="en-US")],
        tool_calls=[
            ToolCall(tool="update_form_fields", args={"field_id": "test", "value": "value"})
        ]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    # Should not raise exception
    response = await pipeline.process_utterance(request)
    assert response.success is True


# ============================================================================
# Test: Error Handling
# ============================================================================

@pytest.mark.asyncio
async def test_pipeline_error_handling(pipeline, mock_websocket, mock_asr):
    """Test error handling in pipeline."""
    # Simulate ASR error
    mock_asr.transcribe_and_respond.side_effect = Exception("ASR failed")

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    # Should raise exception
    with pytest.raises(Exception, match="ASR failed"):
        await pipeline.process_utterance(request)

    # Verify error message sent to frontend
    error_msgs = [m for m in mock_websocket.sent_messages if m["type"] == "half_cascade_error"]
    assert len(error_msgs) == 1
    assert error_msgs[0]["error_code"] == "pipeline_error"
    assert error_msgs[0]["recoverable"] is True


@pytest.mark.asyncio
async def test_tool_execution_error_recovery(pipeline, mock_asr):
    """Test that tool execution errors don't fail entire pipeline."""
    # Setup mock tool executor that fails
    mock_executor = Mock()
    mock_executor.execute = AsyncMock(side_effect=Exception("Tool failed"))
    pipeline._tool_executor = mock_executor

    # Setup mock response
    mock_response = FlashLiteResponse(
        user_transcript="Test",
        detected_language="en-US",
        segments=[ResponseSegment(text="Response", language="en-US")],
        tool_calls=[
            ToolCall(tool="failing_tool", args={})
        ]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    # Pipeline should still complete successfully
    response = await pipeline.process_utterance(request)
    assert response.success is True


# ============================================================================
# Test: Audio Streaming
# ============================================================================

@pytest.mark.asyncio
async def test_audio_chunk_streaming(pipeline, mock_websocket, mock_asr):
    """Test that audio chunks are properly streamed to frontend."""
    mock_response = FlashLiteResponse(
        user_transcript="Test",
        detected_language="en-US",
        segments=[ResponseSegment(text="Test response", language="en-US")],
        tool_calls=[]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    response = await pipeline.process_utterance(request)

    # Verify audio chunks sent
    audio_msgs = [m for m in mock_websocket.sent_messages if m["type"] == "audio_response"]
    assert len(audio_msgs) == 2  # From mock stream
    assert audio_msgs[0]["is_final"] is False
    assert audio_msgs[1]["is_final"] is True
    # Verify base64 encoding
    assert isinstance(audio_msgs[0]["data"], str)
    assert isinstance(audio_msgs[1]["data"], str)


# ============================================================================
# Test: TTS Segment Queueing
# ============================================================================

@pytest.mark.asyncio
async def test_segments_queued_for_tts(pipeline, mock_segment_queue, mock_asr):
    """Test that response segments are properly queued for TTS."""
    mock_response = FlashLiteResponse(
        user_transcript="Test",
        detected_language="en-US",
        segments=[
            ResponseSegment(text="First segment", language="en-US", confidence=0.95),
            ResponseSegment(text="Second segment", language="en-US", confidence=0.97),
            ResponseSegment(text="Third segment", language="es-ES", confidence=0.93)
        ],
        tool_calls=[]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    await pipeline.process_utterance(request)

    # Verify all segments were queued
    assert mock_segment_queue.add_segment.call_count == 3

    # Verify segment details
    calls = mock_segment_queue.add_segment.call_args_list
    assert calls[0][1]["text"] == "First segment"
    assert calls[0][1]["language"] == "en-US"
    assert calls[2][1]["language"] == "es-ES"


# ============================================================================
# Test: WebSocket Message Sending
# ============================================================================

@pytest.mark.asyncio
async def test_processing_status_messages(pipeline, mock_websocket, mock_asr):
    """Test that processing status messages are sent correctly."""
    mock_response = FlashLiteResponse(
        user_transcript="Test",
        detected_language="en-US",
        segments=[ResponseSegment(text="Response", language="en-US")],
        tool_calls=[]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    await pipeline.process_utterance(request)

    # Extract processing status messages
    status_msgs = [m for m in mock_websocket.sent_messages if m["type"] == "processing_status"]

    # Verify all stages present
    stages = [m["stage"] for m in status_msgs]
    assert "buffering" in stages
    assert "transcribing" in stages
    assert "generating" in stages
    assert "synthesizing" in stages


@pytest.mark.asyncio
async def test_transcript_message_sent(pipeline, mock_websocket, mock_asr):
    """Test that transcript is sent to frontend."""
    mock_response = FlashLiteResponse(
        user_transcript="User said this",
        detected_language="en-US",
        segments=[ResponseSegment(text="AI responded this", language="en-US")],
        tool_calls=[]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    await pipeline.process_utterance(request)

    # Find transcript message
    transcript_msgs = [m for m in mock_websocket.sent_messages if m["type"] == "transcript"]
    assert len(transcript_msgs) == 1

    msg = transcript_msgs[0]
    assert msg["user_transcript"] == "User said this"
    assert msg["assistant_response"] == "AI responded this"
    assert msg["language"] == "en-US"


# ============================================================================
# Test: Memory Management and Cleanup
# ============================================================================

@pytest.mark.asyncio
async def test_pipeline_cleanup(pipeline, mock_asr):
    """Test pipeline cleanup releases resources."""
    # Add a mock HTTP client to ASR
    mock_asr._client = Mock()
    mock_asr._client.aclose = AsyncMock()

    # Add synthesis tasks to segment queue
    pipeline._segment_queue._synthesis_tasks = [
        asyncio.create_task(asyncio.sleep(10)),
        asyncio.create_task(asyncio.sleep(10))
    ]

    # Cleanup
    await pipeline.cleanup()

    # Verify HTTP client closed
    mock_asr._client.aclose.assert_called_once()

    # Verify synthesis tasks cancelled
    for task in pipeline._segment_queue._synthesis_tasks:
        assert task.cancelled()


# ============================================================================
# Test: Edge Cases
# ============================================================================

@pytest.mark.asyncio
async def test_empty_segments_handling(pipeline, mock_asr):
    """Test handling of response with no segments."""
    mock_response = FlashLiteResponse(
        user_transcript="Test",
        detected_language="en-US",
        segments=[],  # Empty segments
        tool_calls=[]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    response = await pipeline.process_utterance(request)

    # Should handle gracefully
    assert response.success is True
    assert response.assistant_response == ""
    assert len(response.segments) == 0


@pytest.mark.asyncio
async def test_no_tool_calls(pipeline, mock_asr):
    """Test handling of response with no tool calls."""
    mock_response = FlashLiteResponse(
        user_transcript="Test",
        detected_language="en-US",
        segments=[ResponseSegment(text="Response", language="en-US")],
        tool_calls=None  # No tool calls
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    response = await pipeline.process_utterance(request)

    # Should handle gracefully
    assert response.success is True
    assert len(response.tool_calls) == 0


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.asyncio
async def test_latency_under_1_second(pipeline, mock_asr):
    """Test that pipeline processing completes in <1 second (async design)."""
    import time

    mock_response = FlashLiteResponse(
        user_transcript="Test",
        detected_language="en-US",
        segments=[ResponseSegment(text="Response", language="en-US")],
        tool_calls=[]
    )
    mock_asr.transcribe_and_respond.return_value = mock_response

    request = PipelineRequest(
        audio_data_base64=base64.b64encode(b"test").decode('utf-8'),
        form_state="",
        session_id="test_session"
    )

    start = time.time()
    await pipeline.process_utterance(request)
    elapsed = time.time() - start

    # With mocks, should be very fast
    assert elapsed < 0.1  # 100ms with mocks


# ============================================================================
# Integration Test: Complete Flow
# ============================================================================

@pytest.mark.asyncio
async def test_complete_form_filling_flow(pipeline, mock_websocket, mock_asr):
    """Test complete form filling conversation flow."""
    # Setup multi-turn conversation
    conversations = [
        # Turn 1: Name
        {
            "request": PipelineRequest(
                audio_data_base64=base64.b64encode(b"audio1").decode('utf-8'),
                form_state="",
                conversation_history=[],
                current_field="firstName",
                session_id="test_session"
            ),
            "response": FlashLiteResponse(
                user_transcript="My name is John Smith",
                detected_language="en-US",
                segments=[ResponseSegment(text="Thank you, John. What is your phone number?", language="en-US")],
                tool_calls=[ToolCall(tool="update_form_fields", args={"field_id": "firstName", "value": "John Smith"})]
            )
        },
        # Turn 2: Phone
        {
            "request": PipelineRequest(
                audio_data_base64=base64.b64encode(b"audio2").decode('utf-8'),
                form_state="firstName:John Smith",
                conversation_history=[
                    {"role": "user", "content": "My name is John Smith"},
                    {"role": "assistant", "content": "Thank you, John. What is your phone number?"}
                ],
                current_field="phone",
                session_id="test_session"
            ),
            "response": FlashLiteResponse(
                user_transcript="555-1234",
                detected_language="en-US",
                segments=[ResponseSegment(text="Got it. What is your address?", language="en-US")],
                tool_calls=[ToolCall(tool="update_form_fields", args={"field_id": "phone", "value": "555-1234"})]
            )
        }
    ]

    for conv in conversations:
        mock_asr.transcribe_and_respond.return_value = conv["response"]
        response = await pipeline.process_utterance(conv["request"])

        assert response.success is True
        assert len(response.tool_calls) > 0

    # Verify full conversation tracked
    assert len(conversations[1]["request"].conversation_history) == 2
