"""
Unit tests for TTS Segment Queue Manager (Phase 2C)

Tests cover:
- Segment queuing and processing
- Language switching tracking
- Audio buffering
- Memory management
- Pre-loading optimization
- Gap prevention
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from backend.services.tts_segment_queue import (
    TTSSegment,
    AudioChunk,
    SegmentQueue,
    StreamingTTSQueue
)


@pytest.fixture
def mock_tts_service():
    """Mock TTS service for testing."""
    service = Mock()

    # Mock synthesize_speech to return audio chunks
    async def mock_synthesize(text, language):
        # Simulate 3 chunks per segment
        for i in range(3):
            yield f"{language}:{text}:chunk{i}".encode()

    service.synthesize_speech = mock_synthesize
    service.preload_language = AsyncMock()

    return service


@pytest.fixture
def segment_queue(mock_tts_service):
    """Create a segment queue for testing."""
    return SegmentQueue(mock_tts_service, buffer_chunks=3)


@pytest.fixture
def streaming_queue(mock_tts_service):
    """Create a streaming queue for testing."""
    return StreamingTTSQueue(mock_tts_service)


class TestTTSSegment:
    """Test TTSSegment dataclass."""

    def test_segment_creation(self):
        """Test creating a TTS segment."""
        segment = TTSSegment(
            text="Hello",
            language="en-US",
            confidence=0.95,
            segment_id="seg_1"
        )

        assert segment.text == "Hello"
        assert segment.language == "en-US"
        assert segment.confidence == 0.95
        assert segment.segment_id == "seg_1"

    def test_segment_optional_fields(self):
        """Test segment with optional fields."""
        segment = TTSSegment(text="Hello", language="en-US")

        assert segment.confidence is None
        assert segment.segment_id is None


class TestAudioChunk:
    """Test AudioChunk dataclass."""

    def test_chunk_creation(self):
        """Test creating an audio chunk."""
        chunk = AudioChunk(
            data=b"audio_data",
            segment_id="seg_1",
            language="en-US",
            is_last_in_segment=True
        )

        assert chunk.data == b"audio_data"
        assert chunk.segment_id == "seg_1"
        assert chunk.language == "en-US"
        assert chunk.is_last_in_segment is True


class TestSegmentQueueBasics:
    """Test basic segment queue operations."""

    def test_queue_initialization(self, segment_queue):
        """Test queue initialization."""
        assert segment_queue.buffer_chunks == 3
        assert segment_queue.max_concurrent_synthesis == 2
        assert len(segment_queue._segment_queue) == 0
        assert len(segment_queue._buffer) == 0

    def test_add_single_segment(self, segment_queue):
        """Test adding a single segment to queue."""
        segment_queue.add_segment("Hello", "en-US")

        assert len(segment_queue._segment_queue) == 1
        assert segment_queue._stats["segments_queued"] == 1

    def test_add_segment_with_metadata(self, segment_queue):
        """Test adding segment with metadata."""
        segment_queue.add_segment(
            "Hello",
            "en-US",
            confidence=0.95,
            segment_id="seg_1"
        )

        segment = segment_queue._segment_queue[0]
        assert segment.confidence == 0.95
        assert segment.segment_id == "seg_1"

    def test_add_multiple_segments(self, segment_queue):
        """Test adding multiple segments at once."""
        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "Hola", "language": "es-ES"},
            {"text": "你好", "language": "zh-CN"}
        ]

        segment_queue.add_segments(segments)

        assert len(segment_queue._segment_queue) == 3
        assert segment_queue._stats["segments_queued"] == 3


class TestSegmentSynthesis:
    """Test segment synthesis in queue."""

    @pytest.mark.asyncio
    async def test_synthesize_single_segment(self, segment_queue):
        """Test synthesizing a single segment."""
        segment = TTSSegment(text="Hello", language="en-US")

        chunks = []
        async for chunk in segment_queue._synthesize_segment(segment):
            chunks.append(chunk)

        assert len(chunks) == 3  # Mock returns 3 chunks
        assert all(isinstance(c, AudioChunk) for c in chunks)
        assert all(c.language == "en-US" for c in chunks)

    @pytest.mark.asyncio
    async def test_segment_chunk_metadata(self, segment_queue):
        """Test that synthesized chunks have correct metadata."""
        segment = TTSSegment(
            text="Hello",
            language="en-US",
            segment_id="seg_1"
        )

        chunks = []
        async for chunk in segment_queue._synthesize_segment(segment):
            chunks.append(chunk)

        assert all(c.segment_id == "seg_1" for c in chunks)
        assert all(c.language == "en-US" for c in chunks)


class TestLanguageSwitching:
    """Test language switching and tracking."""

    @pytest.mark.asyncio
    async def test_language_switch_tracking(self, segment_queue):
        """Test that language switches are tracked."""
        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "Hola", "language": "es-ES"},
            {"text": "Bonjour", "language": "fr-FR"}
        ]

        segment_queue.add_segments(segments)

        # Stream audio
        chunks = []
        async for chunk in segment_queue.stream_audio():
            chunks.append(chunk)

        # Should track 2 language switches (en→es, es→fr)
        stats = segment_queue.get_stats()
        assert stats["language_switches"] == 2

    @pytest.mark.asyncio
    async def test_no_switch_same_language(self, segment_queue):
        """Test that same language doesn't count as switch."""
        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "World", "language": "en-US"}
        ]

        segment_queue.add_segments(segments)

        chunks = []
        async for chunk in segment_queue.stream_audio():
            chunks.append(chunk)

        stats = segment_queue.get_stats()
        assert stats["language_switches"] == 0


class TestPreloading:
    """Test language pre-loading optimization."""

    @pytest.mark.asyncio
    async def test_preload_next_language(self, segment_queue, mock_tts_service):
        """Test that next language is pre-loaded."""
        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "Hola", "language": "es-ES"}
        ]

        segment_queue.add_segments(segments)

        # Stream first chunk
        chunk_iter = segment_queue.stream_audio()
        first_chunk = await chunk_iter.__anext__()

        # Give time for pre-loading to be scheduled
        await asyncio.sleep(0.1)

        # Pre-load should have been called for Spanish
        mock_tts_service.preload_language.assert_called()


class TestBuffering:
    """Test audio buffering behavior."""

    @pytest.mark.asyncio
    async def test_buffer_size_limit(self, mock_tts_service):
        """Test that buffer respects size limit."""
        queue = SegmentQueue(mock_tts_service, buffer_chunks=2)

        segment = TTSSegment(text="Hello", language="en-US")

        # Process segment into buffer
        await queue._process_segment(segment)

        # Buffer should not exceed max size
        assert len(queue._buffer) <= 2

    def test_get_stats(self, segment_queue):
        """Test getting queue statistics."""
        segment_queue.add_segment("Hello", "en-US")

        stats = segment_queue.get_stats()

        assert "segments_queued" in stats
        assert "segments_processed" in stats
        assert "queue_size" in stats
        assert "buffer_size" in stats
        assert stats["queue_size"] == 1


class TestStreamingQueue:
    """Test simplified streaming queue."""

    @pytest.mark.asyncio
    async def test_stream_single_segment(self, streaming_queue):
        """Test streaming a single segment."""
        segments = [
            {"text": "Hello", "language": "en-US"}
        ]

        chunks = []
        async for chunk in streaming_queue.stream_segments(segments):
            chunks.append(chunk)

        assert len(chunks) == 3  # Mock returns 3 chunks per segment

    @pytest.mark.asyncio
    async def test_stream_multiple_segments(self, streaming_queue):
        """Test streaming multiple segments."""
        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "Hola", "language": "es-ES"}
        ]

        chunks = []
        async for chunk in streaming_queue.stream_segments(segments):
            chunks.append(chunk)

        assert len(chunks) == 6  # 3 chunks per segment × 2 segments

    @pytest.mark.asyncio
    async def test_skip_empty_segments(self, streaming_queue):
        """Test that empty segments are skipped."""
        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "", "language": "es-ES"},  # Empty
            {"text": "   ", "language": "fr-FR"},  # Whitespace only
            {"text": "World", "language": "en-US"}
        ]

        chunks = []
        async for chunk in streaming_queue.stream_segments(segments):
            chunks.append(chunk)

        # Should only have chunks from non-empty segments (2 segments)
        assert len(chunks) == 6  # 3 chunks × 2 valid segments

    @pytest.mark.asyncio
    async def test_language_switch_logged(self, streaming_queue):
        """Test that language switches are logged."""
        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "Hola", "language": "es-ES"}
        ]

        chunks = []
        async for chunk in streaming_queue.stream_segments(segments):
            chunks.append(chunk)

        # Should have tracked language change
        assert streaming_queue._current_language == "es-ES"

    @pytest.mark.asyncio
    async def test_preload_called(self, streaming_queue, mock_tts_service):
        """Test that pre-loading is triggered for next language."""
        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "Hola", "language": "es-ES"}
        ]

        chunks = []
        async for chunk in streaming_queue.stream_segments(segments):
            chunks.append(chunk)

        # Pre-load should have been called
        mock_tts_service.preload_language.assert_called()


class TestQueueClearing:
    """Test queue clearing and cleanup."""

    @pytest.mark.asyncio
    async def test_clear_queue(self, segment_queue):
        """Test clearing the queue."""
        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "Hola", "language": "es-ES"}
        ]

        segment_queue.add_segments(segments)
        assert len(segment_queue._segment_queue) == 2

        await segment_queue.clear()

        assert len(segment_queue._segment_queue) == 0
        assert len(segment_queue._buffer) == 0
        assert len(segment_queue._synthesis_tasks) == 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_queue_stream(self, segment_queue):
        """Test streaming from empty queue."""
        chunks = []
        async for chunk in segment_queue.stream_audio():
            chunks.append(chunk)

        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_queue_with_no_text(self, segment_queue):
        """Test queue with segments that have no text."""
        segments = [
            {"text": "", "language": "en-US"},
            {"text": "   ", "language": "es-ES"}
        ]

        segment_queue.add_segments(segments)

        chunks = []
        async for chunk in segment_queue.stream_audio():
            chunks.append(chunk)

        # Empty segments should be filtered during synthesis
        # Stats should still track them as queued
        assert segment_queue._stats["segments_queued"] == 2

    @pytest.mark.asyncio
    async def test_default_language_fallback(self, streaming_queue):
        """Test that missing language defaults to en-US."""
        segments = [
            {"text": "Hello"}  # No language specified
        ]

        chunks = []
        async for chunk in streaming_queue.stream_segments(segments):
            chunks.append(chunk)

        # Should use default language
        assert streaming_queue._current_language == "en-US"


class TestConcurrency:
    """Test concurrent synthesis handling."""

    @pytest.mark.asyncio
    async def test_max_concurrent_synthesis(self, mock_tts_service):
        """Test that concurrent synthesis is limited."""
        queue = SegmentQueue(mock_tts_service, max_concurrent_synthesis=2)

        # Add many segments
        segments = [
            {"text": f"Text {i}", "language": "en-US"}
            for i in range(10)
        ]

        queue.add_segments(segments)

        # Start streaming
        chunk_iter = queue.stream_audio()
        first_chunk = await chunk_iter.__anext__()

        # Should never have more than max_concurrent tasks active
        assert len(queue._synthesis_tasks) <= queue.max_concurrent_synthesis
