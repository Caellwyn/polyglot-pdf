"""
Audio Buffer Manager for Half-Cascade architecture.

Handles collecting streaming audio chunks and determining when to send
complete utterances to Gemini Flash-Lite for processing.

Supports two modes:
- PTT (Push-to-Talk): Buffer until button release
- VAD (Voice Activity Detection): Buffer until silence detected
"""

import asyncio
import time
from typing import Optional, Callable, Awaitable
from enum import Enum
import structlog

_log = structlog.get_logger().bind(module="audio_buffer_manager")


class BufferMode(Enum):
    """Audio buffering mode."""
    PTT = "ptt"  # Push-to-talk mode
    VAD = "vad"  # Voice activity detection mode


class AudioBufferManager:
    """
    Manages audio buffering for half-cascade architecture.

    Collects audio chunks until a complete utterance is ready, then
    triggers processing callback.
    """

    # Constants
    MAX_BUFFER_SIZE_MB = 20  # Gemini Flash-Lite limit
    MAX_BUFFER_SIZE_BYTES = MAX_BUFFER_SIZE_MB * 1024 * 1024
    VAD_SILENCE_THRESHOLD_MS = 1500  # 1.5 seconds of silence triggers send
    CHUNK_DURATION_MS = 50  # Expected chunk duration (for estimation)

    def __init__(
        self,
        mode: BufferMode = BufferMode.PTT,
        session_id: Optional[str] = None,
        on_buffer_complete: Optional[Callable[[bytes], Awaitable[None]]] = None
    ):
        """
        Initialize audio buffer manager.

        Args:
            mode: Buffering mode (PTT or VAD)
            session_id: Optional session ID for logging
            on_buffer_complete: Async callback when buffer is ready to process
        """
        self._mode = mode
        self._session_id = session_id
        self._on_buffer_complete = on_buffer_complete

        # Buffer state
        self._buffer: bytearray = bytearray()
        self._is_recording = False
        self._last_audio_time: Optional[float] = None

        # VAD silence detection
        self._silence_task: Optional[asyncio.Task] = None

        # Statistics
        self._total_chunks = 0
        self._total_bytes = 0
        self._buffer_start_time: Optional[float] = None

        _log.info(
            "audio_buffer_initialized",
            mode=mode.value,
            session_id=session_id
        )

    @property
    def mode(self) -> BufferMode:
        """Get current buffer mode."""
        return self._mode

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._is_recording

    @property
    def buffer_size_bytes(self) -> int:
        """Get current buffer size in bytes."""
        return len(self._buffer)

    @property
    def buffer_duration_estimate_ms(self) -> float:
        """
        Estimate buffer duration in milliseconds.

        Assumes 16kHz sample rate, 16-bit PCM mono.
        """
        # 16kHz * 2 bytes/sample = 32,000 bytes/second
        if self._buffer:
            return (len(self._buffer) / 32000) * 1000
        return 0.0

    def start_recording(self) -> None:
        """
        Start recording audio.

        Called when:
        - PTT mode: User presses button
        - VAD mode: Voice activity detected
        """
        if self._is_recording:
            _log.warning("recording_already_started", session_id=self._session_id)
            return

        self._is_recording = True
        self._buffer = bytearray()
        self._buffer_start_time = time.time()
        self._last_audio_time = time.time()

        _log.info(
            "recording_started",
            mode=self._mode.value,
            session_id=self._session_id
        )

    async def add_audio_chunk(self, audio_bytes: bytes) -> None:
        """
        Add audio chunk to buffer.

        Args:
            audio_bytes: Raw audio bytes (PCM16 format expected)
        """
        if not self._is_recording:
            # Ignore audio when not recording
            return

        # Check buffer size limit
        if len(self._buffer) + len(audio_bytes) > self.MAX_BUFFER_SIZE_BYTES:
            _log.warning(
                "buffer_size_limit_reached",
                current_bytes=len(self._buffer),
                chunk_bytes=len(audio_bytes),
                max_bytes=self.MAX_BUFFER_SIZE_BYTES,
                session_id=self._session_id
            )
            # Process current buffer before overflow
            await self._flush_buffer()
            # Start new buffer with this chunk
            self.start_recording()

        # Add chunk to buffer
        self._buffer.extend(audio_bytes)
        self._total_chunks += 1
        self._total_bytes += len(audio_bytes)
        self._last_audio_time = time.time()

        # Log first chunk
        if self._total_chunks == 1:
            _log.info(
                "first_audio_chunk_buffered",
                bytes=len(audio_bytes),
                session_id=self._session_id
            )

        # VAD mode: Restart silence detection timer
        if self._mode == BufferMode.VAD:
            await self._restart_silence_detection()

    async def stop_recording(self) -> None:
        """
        Stop recording and flush buffer.

        Called when:
        - PTT mode: User releases button
        - VAD mode: Silence threshold exceeded
        """
        if not self._is_recording:
            return

        # Cancel silence detection if running
        if self._silence_task:
            self._silence_task.cancel()
            self._silence_task = None

        await self._flush_buffer()

    async def _flush_buffer(self) -> None:
        """Flush buffer and trigger processing callback."""
        if not self._buffer:
            _log.warning("flush_called_on_empty_buffer", session_id=self._session_id)
            return

        buffer_bytes = bytes(self._buffer)
        buffer_size = len(buffer_bytes)
        duration_ms = self.buffer_duration_estimate_ms

        _log.info(
            "buffer_flushed",
            buffer_size_bytes=buffer_size,
            duration_ms=duration_ms,
            chunks=self._total_chunks,
            mode=self._mode.value,
            session_id=self._session_id
        )

        # Reset state
        self._is_recording = False
        self._buffer = bytearray()
        self._buffer_start_time = None

        # Trigger callback
        if self._on_buffer_complete:
            try:
                await self._on_buffer_complete(buffer_bytes)
            except Exception as e:
                _log.error(
                    "buffer_complete_callback_failed",
                    error=str(e),
                    session_id=self._session_id
                )

    async def _restart_silence_detection(self) -> None:
        """
        Restart silence detection timer (VAD mode only).

        Cancels existing timer and starts new one. When timer expires
        without new audio, triggers buffer flush.
        """
        if self._mode != BufferMode.VAD:
            return

        # Cancel existing timer
        if self._silence_task:
            self._silence_task.cancel()

        # Start new timer
        self._silence_task = asyncio.create_task(self._silence_watchdog())

    async def _silence_watchdog(self) -> None:
        """
        Watchdog task for VAD silence detection.

        Waits for silence threshold duration, then flushes buffer.
        """
        try:
            await asyncio.sleep(self.VAD_SILENCE_THRESHOLD_MS / 1000.0)

            # Check if audio arrived during sleep
            if self._last_audio_time:
                time_since_audio = time.time() - self._last_audio_time
                if time_since_audio >= (self.VAD_SILENCE_THRESHOLD_MS / 1000.0):
                    _log.info(
                        "vad_silence_detected",
                        silence_duration_ms=time_since_audio * 1000,
                        session_id=self._session_id
                    )
                    await self.stop_recording()

        except asyncio.CancelledError:
            # Timer was cancelled - this is normal
            pass

    def change_mode(self, new_mode: BufferMode) -> None:
        """
        Change buffering mode.

        Args:
            new_mode: New buffer mode
        """
        if new_mode == self._mode:
            return

        _log.info(
            "buffer_mode_changed",
            old_mode=self._mode.value,
            new_mode=new_mode.value,
            session_id=self._session_id
        )

        # Cancel silence detection if switching from VAD
        if self._mode == BufferMode.VAD and self._silence_task:
            self._silence_task.cancel()
            self._silence_task = None

        self._mode = new_mode

    async def cleanup(self) -> None:
        """Cleanup resources and cancel pending tasks."""
        if self._silence_task:
            self._silence_task.cancel()
            self._silence_task = None

        # Flush any remaining buffer
        if self._buffer and self._is_recording:
            await self._flush_buffer()

        _log.info(
            "buffer_manager_cleaned_up",
            total_chunks=self._total_chunks,
            total_bytes=self._total_bytes,
            session_id=self._session_id
        )

    def get_statistics(self) -> dict:
        """
        Get buffer statistics.

        Returns:
            dict: Statistics including total chunks, bytes, current buffer size
        """
        return {
            "mode": self._mode.value,
            "is_recording": self._is_recording,
            "buffer_size_bytes": len(self._buffer),
            "buffer_duration_ms": self.buffer_duration_estimate_ms,
            "total_chunks": self._total_chunks,
            "total_bytes": self._total_bytes,
            "max_buffer_size_bytes": self.MAX_BUFFER_SIZE_BYTES
        }
