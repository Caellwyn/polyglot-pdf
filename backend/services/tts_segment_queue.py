"""
TTS Segment Queue Manager

Manages queuing and streaming of multi-language TTS segments to ensure:
- No audio gaps between segments (<50ms)
- Smooth language transitions
- Memory-efficient buffering
- Pre-loading of upcoming languages

This is part of Phase 2C: Language-Aware TTS implementation.
"""

import asyncio
import structlog
from typing import AsyncIterator, Dict, Optional, Any, List
from dataclasses import dataclass
from collections import deque

_log = structlog.get_logger().bind(module="tts_segment_queue")


@dataclass
class TTSSegment:
    """A single TTS segment with text and language."""
    text: str
    language: str
    confidence: Optional[float] = None
    segment_id: Optional[str] = None


@dataclass
class AudioChunk:
    """An audio chunk with metadata."""
    data: bytes
    segment_id: Optional[str] = None
    language: str = "en-US"
    is_last_in_segment: bool = False


class SegmentQueue:
    """
    Queue manager for TTS segments with pre-loading and buffering.

    Ensures smooth audio playback by:
    1. Pre-buffering audio chunks to avoid gaps
    2. Pre-loading next language while playing current segment
    3. Managing memory efficiently with sliding window buffer
    """

    def __init__(
        self,
        tts_service,
        buffer_chunks: int = 3,
        max_concurrent_synthesis: int = 2
    ):
        """
        Initialize segment queue.

        Args:
            tts_service: FlashTTSService instance
            buffer_chunks: Number of chunks to buffer ahead (3 chunks ~= 150ms @ 50ms/chunk)
            max_concurrent_synthesis: Max segments to synthesize concurrently
        """
        self.tts_service = tts_service
        self.buffer_chunks = buffer_chunks
        self.max_concurrent_synthesis = max_concurrent_synthesis

        # Audio chunk buffer
        self._buffer: deque[AudioChunk] = deque(maxlen=buffer_chunks)

        # Segment queue
        self._segment_queue: deque[TTSSegment] = deque()

        # Synthesis tasks
        self._synthesis_tasks: List[asyncio.Task] = []

        # Statistics
        self._stats = {
            "segments_queued": 0,
            "segments_processed": 0,
            "chunks_buffered": 0,
            "language_switches": 0,
            "buffer_underruns": 0,
        }

        _log.info(
            "segment_queue_initialized",
            buffer_chunks=buffer_chunks,
            max_concurrent=max_concurrent_synthesis
        )

    def add_segment(self, text: str, language: str, **kwargs) -> None:
        """
        Add a segment to the queue.

        Args:
            text: Text to synthesize
            language: Language code
            **kwargs: Additional segment metadata (confidence, segment_id)
        """
        segment = TTSSegment(
            text=text,
            language=language,
            confidence=kwargs.get("confidence"),
            segment_id=kwargs.get("segment_id")
        )

        self._segment_queue.append(segment)
        self._stats["segments_queued"] += 1

        _log.debug(
            "segment_added_to_queue",
            language=language,
            text_length=len(text),
            queue_size=len(self._segment_queue)
        )

    def add_segments(self, segments: List[Dict[str, Any]]) -> None:
        """
        Add multiple segments to the queue.

        Args:
            segments: List of segment dicts with 'text' and 'language' keys
        """
        for segment in segments:
            self.add_segment(
                text=segment.get("text", ""),
                language=segment.get("language", "en-US"),
                confidence=segment.get("confidence"),
                segment_id=segment.get("segment_id")
            )

    async def _synthesize_segment(self, segment: TTSSegment) -> AsyncIterator[AudioChunk]:
        """
        Synthesize a single segment to audio chunks.

        Args:
            segment: Segment to synthesize

        Yields:
            Audio chunks with metadata
        """
        chunk_count = 0

        try:
            async for audio_data in self.tts_service.synthesize_speech(
                text=segment.text,
                language=segment.language
            ):
                chunk_count += 1
                is_last = False  # We'll mark the last chunk after the loop

                chunk = AudioChunk(
                    data=audio_data,
                    segment_id=segment.segment_id,
                    language=segment.language,
                    is_last_in_segment=is_last
                )

                yield chunk

            # Mark the last chunk
            if chunk_count > 0:
                # Since we can't modify the already-yielded chunks,
                # we yield a final marker chunk if needed
                # For now, we'll track this in the queue manager
                pass

            _log.debug(
                "segment_synthesis_complete",
                segment_id=segment.segment_id,
                language=segment.language,
                chunks=chunk_count
            )

        except Exception as e:
            _log.error(
                "segment_synthesis_error",
                segment_id=segment.segment_id,
                language=segment.language,
                error=str(e),
                exc_info=True
            )
            raise

    async def stream_audio(self) -> AsyncIterator[bytes]:
        """
        Stream audio data with seamless segment transitions.

        This is the main output method that ensures:
        - Pre-buffering to avoid gaps
        - Language pre-loading
        - Memory-efficient streaming

        Yields:
            Raw audio data bytes (PCM16 @ 24kHz)
        """
        current_language = None

        while self._segment_queue or self._synthesis_tasks or self._buffer:
            # Start synthesis for pending segments
            while (
                len(self._synthesis_tasks) < self.max_concurrent_synthesis
                and self._segment_queue
            ):
                segment = self._segment_queue.popleft()

                # Track language switches
                if current_language and segment.language != current_language:
                    self._stats["language_switches"] += 1
                    _log.debug(
                        "language_switch_detected",
                        from_lang=current_language,
                        to_lang=segment.language
                    )

                current_language = segment.language

                # Pre-load next language if available
                if self._segment_queue:
                    next_segment = self._segment_queue[0]
                    if next_segment.language != segment.language:
                        asyncio.create_task(
                            self.tts_service.preload_language(next_segment.language)
                        )

                # Start synthesis task
                task = asyncio.create_task(self._process_segment(segment))
                self._synthesis_tasks.append(task)

            # Wait for chunks or task completion
            if self._buffer:
                # Stream from buffer
                chunk = self._buffer.popleft()
                yield chunk.data

            elif self._synthesis_tasks:
                # Wait for at least one task to produce chunks
                done, pending = await asyncio.wait(
                    self._synthesis_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=0.1
                )

                # Clean up completed tasks
                for task in done:
                    self._synthesis_tasks.remove(task)
                    try:
                        await task  # Raise any exceptions
                    except Exception as e:
                        _log.error("synthesis_task_failed", error=str(e))

                # Check for buffer underrun
                if not self._buffer and self._segment_queue:
                    self._stats["buffer_underruns"] += 1
                    _log.warning(
                        "buffer_underrun",
                        queue_size=len(self._segment_queue),
                        active_tasks=len(self._synthesis_tasks)
                    )

            else:
                # No more segments or tasks
                break

        _log.info("stream_complete", stats=self._stats)

    async def _process_segment(self, segment: TTSSegment) -> None:
        """
        Process a segment and add chunks to buffer.

        Args:
            segment: Segment to process
        """
        async for chunk in self._synthesize_segment(segment):
            self._buffer.append(chunk)
            self._stats["chunks_buffered"] += 1

        self._stats["segments_processed"] += 1

    def get_stats(self) -> Dict[str, int]:
        """
        Get queue statistics.

        Returns:
            Dictionary with queue stats
        """
        return {
            **self._stats,
            "queue_size": len(self._segment_queue),
            "buffer_size": len(self._buffer),
            "active_tasks": len(self._synthesis_tasks)
        }

    async def clear(self) -> None:
        """Clear all queued segments and cancel active tasks."""
        self._segment_queue.clear()

        # Cancel all synthesis tasks
        for task in self._synthesis_tasks:
            task.cancel()

        # Wait for cancellation
        if self._synthesis_tasks:
            await asyncio.gather(*self._synthesis_tasks, return_exceptions=True)

        self._synthesis_tasks.clear()
        self._buffer.clear()

        _log.info("segment_queue_cleared")


class StreamingTTSQueue:
    """
    Simplified streaming TTS queue for real-time usage.

    This version streams audio immediately without complex buffering,
    suitable for low-latency requirements.
    """

    def __init__(self, tts_service):
        """
        Initialize streaming queue.

        Args:
            tts_service: FlashTTSService instance
        """
        self.tts_service = tts_service
        self._current_language = None

    async def stream_segments(
        self,
        segments: List[Dict[str, Any]]
    ) -> AsyncIterator[bytes]:
        """
        Stream audio for segments with minimal buffering.

        Args:
            segments: List of segments with 'text' and 'language'

        Yields:
            Raw audio bytes
        """
        for i, segment in enumerate(segments):
            text = segment.get("text", "")
            language = segment.get("language", "en-US")

            if not text or not text.strip():
                continue

            # Track language switches
            if self._current_language and language != self._current_language:
                _log.debug(
                    "language_switch",
                    from_lang=self._current_language,
                    to_lang=language
                )

            self._current_language = language

            # Pre-load next language
            if i + 1 < len(segments):
                next_language = segments[i + 1].get("language", "en-US")
                if next_language != language:
                    asyncio.create_task(
                        self.tts_service.preload_language(next_language)
                    )

            # Stream audio for this segment
            async for chunk in self.tts_service.synthesize_speech(text, language):
                yield chunk
