"""
Unit tests for FormFillingService.restart_gemini_session.

Regression coverage for polyglot-pdf-8x5: restart_gemini_session previously
called set_callbacks with non-existent handle_* methods (handle_form_update,
handle_transcript, handle_audio, handle_tool_call) and awaited a synchronous
call. Both bugs would raise on the live restart path (which is swallowed by a
try/except in websocket_routes, so the restart failed silently). These tests
assert restart re-registers the *real* CallbackHandler callables and that the
call is not awaited.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.services.form_filling_service import FormFillingService
from backend.services.callback_handler import CallbackHandler


def _make_service_ready_for_restart(send_transcript: bool = True):
    """Build a service in the state restart_gemini_session expects.

    live_ai is a MagicMock so set_callbacks is *synchronous* — if the code ever
    re-introduces `await self._live_ai.set_callbacks(...)`, awaiting a MagicMock
    return value raises TypeError and this test fails.
    """
    service = FormFillingService()

    live_ai = MagicMock()
    # restart proceeds only when no session is currently active
    live_ai.is_session_active.return_value = False
    service._live_ai = live_ai

    service._websocket = AsyncMock()
    service._session_id = "test-session"
    service._send_transcript = send_transcript
    service._schema = {
        "form_metadata": {"form_number": "I-90"},
        "fields": [{"id": "name", "name": "Full Name", "type": "text"}],
    }

    # A real CallbackHandler so we can assert identity of the bound callbacks
    service._callback_handler = CallbackHandler(
        websocket=service._websocket,
        session_id="test-session",
        request_coordinator=AsyncMock(),
        send_transcript=send_transcript,
    )
    return service


@pytest.mark.asyncio
async def test_restart_registers_real_callback_handler_methods():
    """restart_gemini_session must register the CallbackHandler's on_* callbacks,
    not the non-existent handle_* methods from the old (never-run) code path."""
    service = _make_service_ready_for_restart(send_transcript=True)
    handler = service._callback_handler

    await service.restart_gemini_session(next_field_hint="name (Full Name)")

    service._live_ai.set_callbacks.assert_called_once()
    kwargs = service._live_ai.set_callbacks.call_args.kwargs

    # The exact bound methods used at session creation (form_filling_service.py:155)
    assert kwargs["on_form_update"] == handler.on_form_update
    assert kwargs["on_transcript"] == handler.on_transcript
    assert kwargs["on_audio"] == handler.on_audio
    assert kwargs["on_tool_call"] == handler.on_tool_call

    # All callbacks are real callables, not None
    assert all(
        callable(kwargs[k])
        for k in ("on_form_update", "on_transcript", "on_audio", "on_tool_call")
    )

    # Transcript gating is carried by enable_transcripts, not by nulling on_transcript
    assert kwargs["enable_transcripts"] is True
    assert kwargs["system_instruction"]
    assert kwargs["tool_declarations"] is not None


@pytest.mark.asyncio
async def test_restart_passes_on_transcript_even_when_transcripts_disabled():
    """on_transcript is always registered; enable_transcripts is what gates emission."""
    service = _make_service_ready_for_restart(send_transcript=False)
    handler = service._callback_handler

    await service.restart_gemini_session()

    kwargs = service._live_ai.set_callbacks.call_args.kwargs
    assert kwargs["on_transcript"] == handler.on_transcript
    assert kwargs["enable_transcripts"] is False


@pytest.mark.asyncio
async def test_restart_noop_when_session_already_active():
    """If a session is already active, restart is a no-op and does not re-register."""
    service = _make_service_ready_for_restart()
    service._live_ai.is_session_active.return_value = True

    await service.restart_gemini_session()

    service._live_ai.set_callbacks.assert_not_called()


@pytest.mark.asyncio
async def test_restart_raises_without_callback_handler():
    """Restart with no callback handler must fail loudly, not register bad callbacks."""
    service = _make_service_ready_for_restart()
    service._callback_handler = None

    with pytest.raises(RuntimeError, match="callback handler"):
        await service.restart_gemini_session()

    service._live_ai.set_callbacks.assert_not_called()
