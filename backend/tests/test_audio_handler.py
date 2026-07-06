"""
Unit tests for audio_handler module.

Tests audio streaming, activity signals, and context synchronization.
"""
import pytest
from unittest.mock import AsyncMock, Mock, call
from backend.services.audio_handler import AudioHandler


class TestAudioHandlerInitialization:
    """Tests for AudioHandler initialization."""
    
    def test_initialization_with_live_ai(self):
        """Test handler initialization with LiveAI instance."""
        mock_live_ai = Mock()
        handler = AudioHandler(mock_live_ai, session_id="test_123")
        
        assert handler._live_ai is mock_live_ai
        assert handler._session_id == "test_123"
        assert handler._first_audio_logged is False
    
    def test_initialization_without_session_id(self):
        """Test handler initialization without session ID."""
        mock_live_ai = Mock()
        handler = AudioHandler(mock_live_ai)
        
        assert handler._live_ai is mock_live_ai
        assert handler._session_id is None
    
    def test_initialization_with_none_live_ai(self):
        """Test handler initialization with None (test mode)."""
        handler = AudioHandler(None, session_id="test_123")
        
        assert handler._live_ai is None
        assert handler._session_id == "test_123"


class TestStreamAudio:
    """Tests for stream_audio method."""
    
    @pytest.mark.asyncio
    async def test_stream_audio_forwards_to_live_ai(self):
        """Test that audio chunks are forwarded to LiveAI."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai, session_id="test_123")
        
        audio_chunk = b"fake_audio_data"
        await handler.stream_audio(audio_chunk)
        
        mock_live_ai.stream_audio.assert_called_once_with(audio_chunk)
    
    @pytest.mark.asyncio
    async def test_stream_audio_logs_first_chunk(self):
        """Test that first audio chunk is logged."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai, session_id="test_123")
        
        # First chunk should trigger logging
        await handler.stream_audio(b"first_chunk")
        assert handler._first_audio_logged is True
        
        # Second chunk should not log (flag already set)
        await handler.stream_audio(b"second_chunk")
        assert handler._first_audio_logged is True
        
        # Both chunks should still be forwarded
        assert mock_live_ai.stream_audio.call_count == 2
    
    @pytest.mark.asyncio
    async def test_stream_audio_noop_when_no_live_ai(self):
        """Test that stream_audio is no-op when LiveAI is None."""
        handler = AudioHandler(None, session_id="test_123")
        
        # Should not raise, just no-op
        await handler.stream_audio(b"audio_data")
        
        # Flag should not be set
        assert handler._first_audio_logged is False
    
    @pytest.mark.asyncio
    async def test_stream_audio_multiple_chunks(self):
        """Test streaming multiple audio chunks."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)
        
        chunks = [b"chunk1", b"chunk2", b"chunk3"]
        for chunk in chunks:
            await handler.stream_audio(chunk)
        
        assert mock_live_ai.stream_audio.call_count == 3
        calls = [call(b"chunk1"), call(b"chunk2"), call(b"chunk3")]
        mock_live_ai.stream_audio.assert_has_calls(calls)


class TestActivitySignals:
    """Tests for activity_start and activity_end methods."""
    
    @pytest.mark.asyncio
    async def test_send_activity_start(self):
        """Test sending activity_start signal."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai, session_id="test_123")
        
        await handler.send_activity_start()
        
        mock_live_ai.send_activity_start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_activity_end(self):
        """Test sending activity_end signal."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai, session_id="test_123")
        
        await handler.send_activity_end()
        
        mock_live_ai.send_activity_end.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_activity_start_noop_when_no_live_ai(self):
        """Test that activity_start is no-op when LiveAI is None."""
        handler = AudioHandler(None)
        
        # Should not raise
        await handler.send_activity_start()
    
    @pytest.mark.asyncio
    async def test_activity_end_noop_when_no_live_ai(self):
        """Test that activity_end is no-op when LiveAI is None."""
        handler = AudioHandler(None)
        
        # Should not raise
        await handler.send_activity_end()
    
    @pytest.mark.asyncio
    async def test_activity_sequence(self):
        """Test typical activity sequence: start -> audio -> end."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)
        
        # Typical VAD flow
        await handler.send_activity_start()
        await handler.stream_audio(b"audio_chunk_1")
        await handler.stream_audio(b"audio_chunk_2")
        await handler.send_activity_end()
        
        # Verify call order
        assert mock_live_ai.send_activity_start.call_count == 1
        assert mock_live_ai.stream_audio.call_count == 2
        assert mock_live_ai.send_activity_end.call_count == 1


class TestContextHint:
    """Tests for send_context_hint method."""
    
    @pytest.mark.asyncio
    async def test_send_context_hint(self):
        """Test sending context hint to Gemini."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai, session_id="test_123")
        
        hint = "Next field is 'email'"
        await handler.send_context_hint(hint)
        
        mock_live_ai.send_text_message.assert_called_once_with(hint)
    
    @pytest.mark.asyncio
    async def test_context_hint_noop_when_no_live_ai(self):
        """Test that context hint is no-op when LiveAI is None."""
        handler = AudioHandler(None)
        
        # Should not raise
        await handler.send_context_hint("some hint")
    
    @pytest.mark.asyncio
    async def test_multiple_context_hints(self):
        """Test sending multiple context hints."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)
        
        hints = ["Hint 1", "Hint 2", "Hint 3"]
        for hint in hints:
            await handler.send_context_hint(hint)
        
        assert mock_live_ai.send_text_message.call_count == 3


class TestManualFieldUpdate:
    """Tests for send_manual_field_update method."""
    
    @pytest.mark.asyncio
    async def test_send_manual_field_update(self):
        """Test sending manual field update notification."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai, session_id="test_123")
        
        await handler.send_manual_field_update(
            field_id="email",
            field_name="Email Address",
            value="test@example.com"
        )
        
        # Should send text message with field update
        mock_live_ai.send_text_message.assert_called_once()
        message = mock_live_ai.send_text_message.call_args[0][0]
        assert "Email Address" in message
        assert "test@example.com" in message
    
    @pytest.mark.asyncio
    async def test_manual_field_update_with_next_hint(self):
        """Test manual field update includes next field hint."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)
        
        await handler.send_manual_field_update(
            field_id="first_name",
            field_name="First Name",
            value="John",
            next_field_hint="Next field is 'Last Name'"
        )
        
        message = mock_live_ai.send_text_message.call_args[0][0]
        assert "First Name" in message
        assert "John" in message
        assert "Next field is 'Last Name'" in message
    
    @pytest.mark.asyncio
    async def test_manual_field_update_skips_empty_string(self):
        """Test that empty string values are skipped."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)
        
        await handler.send_manual_field_update(
            field_id="email",
            field_name="Email",
            value=""
        )
        
        # Should not send message for empty value
        mock_live_ai.send_text_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_manual_field_update_skips_whitespace(self):
        """Test that whitespace-only values are skipped."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)
        
        await handler.send_manual_field_update(
            field_id="email",
            field_name="Email",
            value="   "
        )
        
        # Should not send message for whitespace
        mock_live_ai.send_text_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_manual_field_update_skips_none(self):
        """Test that None values are skipped."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)
        
        await handler.send_manual_field_update(
            field_id="email",
            field_name="Email",
            value=None
        )
        
        # Should not send message for None
        mock_live_ai.send_text_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_manual_field_update_notifies_on_false(self):
        """A manually-unchecked checkbox (value=False) is a real answer and
        must still notify Gemini (bd polyglot-pdf-vtdx)."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)

        await handler.send_manual_field_update(
            field_id="agrees_to_terms",
            field_name="Agrees to Terms",
            value=False
        )

        mock_live_ai.send_text_message.assert_called_once()
        message = mock_live_ai.send_text_message.call_args[0][0]
        assert "False" in message

    @pytest.mark.asyncio
    async def test_manual_field_update_notifies_on_zero(self):
        """A manually-entered 0 is a real answer and must still notify
        Gemini (bd polyglot-pdf-vtdx)."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)

        await handler.send_manual_field_update(
            field_id="num_dependents",
            field_name="Number of Dependents",
            value=0
        )

        mock_live_ai.send_text_message.assert_called_once()
        message = mock_live_ai.send_text_message.call_args[0][0]
        assert "0" in message

    @pytest.mark.asyncio
    async def test_manual_field_update_noop_when_no_live_ai(self):
        """Test that manual update is no-op when LiveAI is None."""
        handler = AudioHandler(None)
        
        # Should not raise
        await handler.send_manual_field_update(
            field_id="email",
            field_name="Email",
            value="test@example.com"
        )
    
    @pytest.mark.asyncio
    async def test_manual_field_update_converts_value_to_string(self):
        """Test that non-string values are converted to strings."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)
        
        # Send numeric value
        await handler.send_manual_field_update(
            field_id="age",
            field_name="Age",
            value=25
        )
        
        message = mock_live_ai.send_text_message.call_args[0][0]
        assert "25" in message


class TestIntegration:
    """Integration tests combining multiple audio handler operations."""
    
    @pytest.mark.asyncio
    async def test_complete_voice_session(self):
        """Test a complete voice interaction session."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai, session_id="session_123")
        
        # Complete flow: VAD start, audio, VAD end, context hint
        await handler.send_activity_start()
        await handler.stream_audio(b"audio_1")
        await handler.stream_audio(b"audio_2")
        await handler.send_activity_end()
        await handler.send_context_hint("Next: email")
        
        # Verify all calls made
        assert mock_live_ai.send_activity_start.call_count == 1
        assert mock_live_ai.stream_audio.call_count == 2
        assert mock_live_ai.send_activity_end.call_count == 1
        assert mock_live_ai.send_text_message.call_count == 1
    
    @pytest.mark.asyncio
    async def test_manual_update_between_voice_sessions(self):
        """Test manual field update between voice sessions."""
        mock_live_ai = AsyncMock()
        handler = AudioHandler(mock_live_ai)
        
        # Voice session 1
        await handler.send_activity_start()
        await handler.stream_audio(b"audio")
        await handler.send_activity_end()
        
        # User manually updates field
        await handler.send_manual_field_update(
            field_id="email",
            field_name="Email",
            value="test@example.com",
            next_field_hint="Next: phone"
        )
        
        # Voice session 2
        await handler.send_activity_start()
        await handler.stream_audio(b"more_audio")
        await handler.send_activity_end()
        
        # Verify sequence
        assert mock_live_ai.send_activity_start.call_count == 2
        assert mock_live_ai.send_activity_end.call_count == 2
        assert mock_live_ai.send_text_message.call_count == 1
