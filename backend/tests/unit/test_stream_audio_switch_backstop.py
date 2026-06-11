"""
Unit tests for the FormFillingService.stream_audio switch-window backstop.

Regression coverage for the PR #150 fresh-eyes round-2 blocker: the frontend's
mic send gate (bd polyglot-pdf-xroy) forwards audio while the client status is
'switching_section'. The manual switch path is guarded by the WS route's
drop_audio flag, but the AI-initiated switch path (switch_section tool ->
_complete_section_switch) never sets drop_audio -- so mic frames captured
during the swap could be enqueued into the NEW Gemini session's audio queue
before the client learns the switch completed (cross-session audio leak).

The server-side backstop: _switch_lock is held for the ENTIRE swap on BOTH
switch paths, so stream_audio drops chunks while the lock is held. These tests
pin that contract; they would fail if the locked() guard were removed or the
drop accidentally started raising/forwarding.
"""
import pytest
from unittest.mock import AsyncMock

from backend.services.form_filling_service import FormFillingService


def _service_with_mock_audio_handler():
    service = FormFillingService()
    service._audio_handler = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_stream_audio_delegates_when_no_switch_in_flight():
    """Normal path: chunk reaches the AudioHandler."""
    service = _service_with_mock_audio_handler()

    await service.stream_audio(b"\x00\x01")

    service._audio_handler.stream_audio.assert_awaited_once_with(b"\x00\x01")


@pytest.mark.asyncio
async def test_stream_audio_drops_while_switch_lock_held():
    """The backstop: while _switch_lock is held (a section swap is in flight on
    EITHER path), audio must be dropped -- never forwarded to the adapter."""
    service = _service_with_mock_audio_handler()

    async with service._switch_lock:
        await service.stream_audio(b"\x00\x01")

    service._audio_handler.stream_audio.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_audio_resumes_after_switch_lock_released():
    """Once the swap completes (lock released), audio flows again."""
    service = _service_with_mock_audio_handler()

    async with service._switch_lock:
        await service.stream_audio(b"\x00\x01")
    await service.stream_audio(b"\x02\x03")

    service._audio_handler.stream_audio.assert_awaited_once_with(b"\x02\x03")


@pytest.mark.asyncio
async def test_stream_audio_drop_does_not_raise_without_audio_handler():
    """The drop path must be safe on a bare service (no handler configured)."""
    service = FormFillingService()
    service._audio_handler = None

    async with service._switch_lock:
        await service.stream_audio(b"\x00\x01")
