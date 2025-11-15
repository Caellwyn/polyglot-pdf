"""
Tests for audio buffer manager (Phase 1B).

Tests PTT mode, VAD mode, buffer limits, and memory management.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock

from backend.services.audio_buffer_manager import (
    AudioBufferManager,
    BufferMode
)


class TestAudioBufferManagerPTT:
    """Test PTT (Push-to-Talk) mode."""

    @pytest.fixture
    def callback(self):
        """Create mock callback."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, callback):
        """Create PTT mode manager."""
        return AudioBufferManager(
            mode=BufferMode.PTT,
            session_id="test_session",
            on_buffer_complete=callback
        )

    @pytest.mark.asyncio
    async def test_ptt_start_stop(self, manager, callback):
        """Test basic PTT start/stop cycle."""
        # Start recording
        manager.start_recording()
        assert manager.is_recording is True

        # Add audio chunk
        audio_chunk = b"test_audio_data" * 100
        await manager.add_audio_chunk(audio_chunk)

        assert manager.buffer_size_bytes > 0

        # Stop recording
        await manager.stop_recording()

        # Callback should be called with buffer
        assert callback.called
        assert len(callback.call_args[0][0]) > 0

    @pytest.mark.asyncio
    async def test_ptt_multiple_chunks(self, manager, callback):
        """Test buffering multiple audio chunks."""
        manager.start_recording()

        # Add multiple chunks
        chunk1 = b"chunk1" * 50
        chunk2 = b"chunk2" * 50
        chunk3 = b"chunk3" * 50

        await manager.add_audio_chunk(chunk1)
        await manager.add_audio_chunk(chunk2)
        await manager.add_audio_chunk(chunk3)

        await manager.stop_recording()

        # Buffer should contain all chunks
        buffer = callback.call_args[0][0]
        assert chunk1 in buffer
        assert chunk2 in buffer
        assert chunk3 in buffer

    @pytest.mark.asyncio
    async def test_ptt_ignore_audio_when_not_recording(self, manager):
        """Test that audio is ignored when not recording."""
        # Don't start recording
        audio_chunk = b"test_data"

        await manager.add_audio_chunk(audio_chunk)

        # Buffer should be empty
        assert manager.buffer_size_bytes == 0

    @pytest.mark.asyncio
    async def test_ptt_buffer_statistics(self, manager):
        """Test buffer statistics tracking."""
        manager.start_recording()

        chunk = b"data" * 100
        await manager.add_audio_chunk(chunk)

        stats = manager.get_statistics()

        assert stats["mode"] == "ptt"
        assert stats["is_recording"] is True
        assert stats["buffer_size_bytes"] > 0
        assert stats["total_chunks"] == 1
        assert stats["total_bytes"] == len(chunk)


class TestAudioBufferManagerVAD:
    """Test VAD (Voice Activity Detection) mode."""

    @pytest.fixture
    def callback(self):
        """Create mock callback."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, callback):
        """Create VAD mode manager."""
        return AudioBufferManager(
            mode=BufferMode.VAD,
            session_id="test_session",
            on_buffer_complete=callback
        )

    @pytest.mark.asyncio
    async def test_vad_silence_detection(self, manager, callback):
        """Test that silence triggers buffer flush."""
        manager.start_recording()

        # Add audio chunk
        audio_chunk = b"test_audio" * 100
        await manager.add_audio_chunk(audio_chunk)

        # Wait for silence threshold (1.5 seconds)
        await asyncio.sleep(1.6)

        # Callback should be triggered by silence
        assert callback.called

    @pytest.mark.asyncio
    async def test_vad_continuous_audio_no_flush(self, manager, callback):
        """Test that continuous audio doesn't trigger flush."""
        manager.start_recording()

        # Add chunks continuously
        for _ in range(5):
            await manager.add_audio_chunk(b"audio" * 100)
            await asyncio.sleep(0.2)  # Less than silence threshold

        # Should not have flushed yet
        assert not callback.called

    @pytest.mark.asyncio
    async def test_vad_restart_timer(self, manager, callback):
        """Test that new audio restarts silence timer."""
        manager.start_recording()

        # Add first chunk
        await manager.add_audio_chunk(b"chunk1" * 100)

        # Wait almost to threshold
        await asyncio.sleep(1.4)

        # Add another chunk (should restart timer)
        await manager.add_audio_chunk(b"chunk2" * 100)

        # Wait less than threshold
        await asyncio.sleep(1.0)

        # Should not have flushed yet
        assert not callback.called


class TestBufferSizeLimits:
    """Test buffer size limit handling."""

    @pytest.fixture
    def callback(self):
        """Create mock callback."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, callback):
        """Create manager."""
        return AudioBufferManager(
            mode=BufferMode.PTT,
            on_buffer_complete=callback
        )

    @pytest.mark.asyncio
    async def test_max_buffer_size(self, manager, callback):
        """Test that buffer respects max size limit."""
        manager.start_recording()

        # Try to add more than max buffer size (20MB)
        # Create 5MB chunks
        large_chunk = b"x" * (5 * 1024 * 1024)

        # Add 5 chunks (25MB total, exceeds 20MB limit)
        for _ in range(5):
            await manager.add_audio_chunk(large_chunk)

        # Should have flushed at least once when limit reached
        assert callback.called

    @pytest.mark.asyncio
    async def test_buffer_duration_estimate(self, manager):
        """Test buffer duration estimation."""
        manager.start_recording()

        # Add 32,000 bytes (should be ~1 second at 16kHz PCM16)
        audio_chunk = b"x" * 32000
        await manager.add_audio_chunk(audio_chunk)

        duration_ms = manager.buffer_duration_estimate_ms

        # Should be approximately 1000ms
        assert 900 <= duration_ms <= 1100

    @pytest.mark.asyncio
    async def test_empty_buffer_duration(self, manager):
        """Test duration of empty buffer."""
        duration = manager.buffer_duration_estimate_ms
        assert duration == 0.0


class TestBufferModeSwitch:
    """Test switching between buffer modes."""

    @pytest.fixture
    def callback(self):
        """Create mock callback."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, callback):
        """Create manager."""
        return AudioBufferManager(
            mode=BufferMode.PTT,
            on_buffer_complete=callback
        )

    def test_mode_switch_ptt_to_vad(self, manager):
        """Test switching from PTT to VAD mode."""
        assert manager.mode == BufferMode.PTT

        manager.change_mode(BufferMode.VAD)

        assert manager.mode == BufferMode.VAD

    def test_mode_switch_vad_to_ptt(self):
        """Test switching from VAD to PTT mode."""
        manager = AudioBufferManager(mode=BufferMode.VAD)

        manager.change_mode(BufferMode.PTT)

        assert manager.mode == BufferMode.PTT

    def test_mode_switch_same_mode_noop(self, manager):
        """Test switching to same mode is no-op."""
        manager.change_mode(BufferMode.PTT)

        assert manager.mode == BufferMode.PTT


class TestBufferCleanup:
    """Test buffer cleanup and resource management."""

    @pytest.fixture
    def callback(self):
        """Create mock callback."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, callback):
        """Create manager."""
        return AudioBufferManager(
            mode=BufferMode.VAD,
            on_buffer_complete=callback
        )

    @pytest.mark.asyncio
    async def test_cleanup_cancels_silence_task(self, manager):
        """Test that cleanup cancels silence detection task."""
        manager.start_recording()
        await manager.add_audio_chunk(b"test" * 100)

        # Should have active silence task
        await manager.cleanup()

        # Task should be cancelled
        assert manager._silence_task is None

    @pytest.mark.asyncio
    async def test_cleanup_flushes_buffer(self, manager, callback):
        """Test that cleanup flushes remaining buffer."""
        manager.start_recording()
        await manager.add_audio_chunk(b"test" * 100)

        await manager.cleanup()

        # Buffer should be flushed
        assert callback.called

    @pytest.mark.asyncio
    async def test_cleanup_statistics(self, manager):
        """Test statistics after cleanup."""
        manager.start_recording()

        chunk = b"data" * 1000
        await manager.add_audio_chunk(chunk)

        await manager.cleanup()

        stats = manager.get_statistics()

        # Should track total bytes even after cleanup
        assert stats["total_bytes"] == len(chunk)
        assert stats["total_chunks"] == 1


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_start_recording_twice(self):
        """Test calling start_recording twice."""
        manager = AudioBufferManager(mode=BufferMode.PTT)

        manager.start_recording()
        manager.start_recording()  # Should log warning but not fail

        assert manager.is_recording is True

    @pytest.mark.asyncio
    async def test_stop_recording_when_not_started(self):
        """Test stopping when not recording."""
        callback = AsyncMock()
        manager = AudioBufferManager(
            mode=BufferMode.PTT,
            on_buffer_complete=callback
        )

        await manager.stop_recording()  # Should not fail

        # Callback should not be called
        assert not callback.called

    @pytest.mark.asyncio
    async def test_callback_exception_handling(self):
        """Test that callback exceptions are caught."""
        # Create callback that raises exception
        callback = AsyncMock(side_effect=Exception("Test error"))

        manager = AudioBufferManager(
            mode=BufferMode.PTT,
            on_buffer_complete=callback
        )

        manager.start_recording()
        await manager.add_audio_chunk(b"test" * 100)

        # Should not raise exception
        await manager.stop_recording()

    @pytest.mark.asyncio
    async def test_empty_buffer_flush(self):
        """Test flushing empty buffer."""
        callback = AsyncMock()
        manager = AudioBufferManager(
            mode=BufferMode.PTT,
            on_buffer_complete=callback
        )

        manager.start_recording()
        await manager.stop_recording()  # Flush empty buffer

        # Callback should not be called for empty buffer
        assert not callback.called


class TestIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_ptt_complete_workflow(self):
        """Test complete PTT workflow."""
        buffers_received = []

        async def callback(buffer_bytes):
            buffers_received.append(buffer_bytes)

        manager = AudioBufferManager(
            mode=BufferMode.PTT,
            on_buffer_complete=callback
        )

        # First utterance
        manager.start_recording()
        await manager.add_audio_chunk(b"hello" * 100)
        await manager.stop_recording()

        # Second utterance
        manager.start_recording()
        await manager.add_audio_chunk(b"world" * 100)
        await manager.stop_recording()

        # Should have received two buffers
        assert len(buffers_received) == 2
        assert b"hello" in buffers_received[0]
        assert b"world" in buffers_received[1]

    @pytest.mark.asyncio
    async def test_vad_complete_workflow(self):
        """Test complete VAD workflow."""
        buffers_received = []

        async def callback(buffer_bytes):
            buffers_received.append(buffer_bytes)

        manager = AudioBufferManager(
            mode=BufferMode.VAD,
            on_buffer_complete=callback
        )

        # Start recording
        manager.start_recording()

        # Add audio chunks
        for i in range(3):
            await manager.add_audio_chunk(f"chunk{i}".encode() * 100)
            await asyncio.sleep(0.1)

        # Wait for silence to trigger flush
        await asyncio.sleep(1.6)

        # Should have received one buffer
        assert len(buffers_received) == 1
        assert b"chunk0" in buffers_received[0]
        assert b"chunk2" in buffers_received[0]

        await manager.cleanup()
