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

    live_ai is a MagicMock so set_callbacks is *synchronous* -- if the code ever
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


@pytest.mark.asyncio
async def test_restart_preserves_section_metadata(monkeypatch):
    """bd polyglot-pdf-umv: after a section switch, restart_gemini_session must
    rebuild the system instruction WITH the user's section position + previously-
    spoken field names, not default to "section 1 of 1" with no history.

    We assert on the args threaded into build_form_context_message rather than on
    the rendered text, so the test is robust to SI wording changes.
    """
    service = _make_service_ready_for_restart()

    # Simulate having switched to section 7 of 16 (what switch_to_section retains).
    service._last_section_metadata = {
        "section_number": 7,
        "total_sections": 16,
        "section_label": "Address History",
        "previous_spoken_names": ["family name", "given name", "date of birth"],
    }

    captured = {}
    real_build = service.build_form_context_message

    def _spy(schema, values, **kwargs):
        captured.update(kwargs)
        return real_build(schema, values, **kwargs)

    monkeypatch.setattr(service, "build_form_context_message", _spy)

    await service.restart_gemini_session()

    assert captured.get("section_number") == 7
    assert captured.get("total_sections") == 16
    assert captured.get("section_label") == "Address History"
    assert captured.get("previous_spoken_names") == [
        "family name", "given name", "date of birth",
    ]


@pytest.mark.asyncio
async def test_restart_without_prior_section_switch_passes_no_section_metadata(monkeypatch):
    """Single-section forms (or restart before any switch) keep the original
    behavior: no section args, so build_form_context defaults cleanly. _last_section_
    metadata is None here, which must NOT raise and must pass section_number=None."""
    service = _make_service_ready_for_restart()
    assert service._last_section_metadata is None  # never switched

    captured = {}
    real_build = service.build_form_context_message

    def _spy(schema, values, **kwargs):
        captured.update(kwargs)
        return real_build(schema, values, **kwargs)

    monkeypatch.setattr(service, "build_form_context_message", _spy)

    await service.restart_gemini_session()

    # No prior switch -> all section args are None (the original non-sectioned path).
    assert captured.get("section_number") is None
    assert captured.get("total_sections") is None
    assert captured.get("section_label") is None
    assert captured.get("previous_spoken_names") is None
    # Restart still succeeds and registers callbacks with a built SI.
    kwargs = service._live_ai.set_callbacks.call_args.kwargs
    assert kwargs["system_instruction"]


@pytest.mark.asyncio
async def test_restart_label_matches_switch_for_present_none_label(monkeypatch):
    """fresh-eyes PR #82: when stored section_label is present-but-None, restart must
    pass label=None (-> build_form_context falls back to form_title), EXACTLY as
    switch_to_section's `.get("section_label", default)` does -- not convert it to
    "Section N". The restart label must never diverge from the switch's."""
    service = _make_service_ready_for_restart()
    service._last_section_metadata = {
        "section_number": 5,
        "total_sections": 16,
        "section_label": None,  # present but None (frontend sent null)
        "previous_spoken_names": [],
    }

    captured = {}
    real_build = service.build_form_context_message

    def _spy(schema, values, **kwargs):
        captured.update(kwargs)
        return real_build(schema, values, **kwargs)

    monkeypatch.setattr(service, "build_form_context_message", _spy)

    await service.restart_gemini_session()

    # present-None label passes through as None (mirrors switch_to_section), NOT "Section 5"
    assert captured.get("section_number") == 5
    assert captured.get("section_label") is None


@pytest.mark.asyncio
async def test_switch_to_section_retains_metadata_for_restart():
    """switch_to_section must stash the section metadata so a later restart can
    reuse it (the producer side of the umv fix)."""
    service = FormFillingService()
    live_ai = MagicMock()
    live_ai.finalize = AsyncMock()
    service._live_ai = live_ai
    service._websocket = AsyncMock()
    service._session_id = "test-session"
    service._send_transcript = False
    service._callback_handler = CallbackHandler(
        websocket=service._websocket,
        session_id="test-session",
        request_coordinator=AsyncMock(),
        send_transcript=False,
    )

    metadata = {
        "section_number": 3,
        "total_sections": 16,
        "section_label": "Biographic Information",
        "previous_spoken_names": ["family name"],
    }
    await service.switch_to_section(
        section_schema={"form_metadata": {}, "fields": []},
        section_values={},
        section_metadata=metadata,
    )

    assert service._last_section_metadata == metadata


@pytest.mark.asyncio
async def test_restart_fires_initiating_message_in_dti(monkeypatch):
    """bd polyglot-pdf-h1bn (closing the fu1h-flagged gap): in DTI mode the rebuilt
    SI is static and carries no field data, so restart MUST fire the initiating
    message to re-deliver the current field's guidance + metadata after the restart
    (e.g. a Level-3 farewell reconnect). Otherwise the model has no field-1 id."""
    from backend.config import Settings
    service = _make_service_ready_for_restart()
    # Use a FRESH Settings instance (NOT the lru_cached get_settings() singleton) so
    # toggling USE_DTI does not leak into other tests.
    service._settings = Settings()
    service._settings.USE_DTI = True
    sent = []

    async def _capture(spoken, hint, force_resume=False):
        sent.append((spoken, hint, force_resume))

    monkeypatch.setattr(service, "send_initiating_message", _capture)

    await service.restart_gemini_session(next_field_hint="name (field_id: 'name')")

    assert len(sent) == 1, "DTI restart must fire the initiating message"
    assert sent[0][1] == "name (field_id: 'name')"
    # bd polyglot-pdf-bhem: restart must force the RESUME template so a Level-3
    # farewell reconnect never re-greets the user, even when the ORIGINAL
    # connection was a fresh (non-resume) start.
    assert sent[0][2] is True, "restart must pass force_resume=True"


@pytest.mark.asyncio
async def test_restart_does_not_fire_initiating_message_in_non_dti(monkeypatch):
    """Non-DTI (legacy/JIT): the rebuilt SI carries the field catalog, so restart
    must NOT fire an extra initiating message (no behavior change vs pre-h1bn)."""
    from backend.config import Settings
    service = _make_service_ready_for_restart()
    service._settings = Settings()
    service._settings.USE_DTI = False
    sent = []

    async def _capture(spoken, hint, force_resume=False):
        sent.append((spoken, hint, force_resume))

    monkeypatch.setattr(service, "send_initiating_message", _capture)

    await service.restart_gemini_session(next_field_hint="name (Full Name)")

    assert sent == [], "non-DTI restart must not fire an initiating message"


@pytest.mark.asyncio
async def test_restart_uses_resume_template_even_after_fresh_original_connect():
    """bd polyglot-pdf-bhem: after a Level-3 farewell + restart_gemini_session, the
    initiating message must use RESUME_INITIATING_MESSAGE (no re-greeting) even
    though the ORIGINAL session was a fresh (non-resume) connect, i.e.
    _is_resume_session is False. Exercises the real send_initiating_message (not
    monkeypatched) so the actual message text sent to Gemini is asserted on."""
    from backend.config import Settings
    service = _make_service_ready_for_restart()
    service._settings = Settings()
    service._settings.USE_DTI = True

    # The ORIGINAL connection was a fresh start, not a resume (set at start_session
    # time in the real flow -- see websocket_routes.py:196).
    service._is_resume_session = False

    sent = []

    async def _capture_send_client_content(message):
        sent.append(message)

    service._live_ai.send_client_content = _capture_send_client_content

    await service.restart_gemini_session(next_field_hint="name (field_id: 'name')")

    assert len(sent) == 1, "restart must fire exactly one initiating message"
    message = sent[0].lower()
    assert "greet user warmly" not in message, (
        "restart after a fresh original connect must NOT re-greet the user"
    )
    assert "do not greet" in message or "not greet" in message, (
        "restart must use the RESUME template's explicit skip-greeting instruction"
    )
    # _is_resume_session itself is untouched (force_resume overrides the template
    # pick without mutating the flag build_form_context_message also reads).
    assert service._is_resume_session is False


@pytest.mark.asyncio
async def test_non_restart_fresh_session_still_greets():
    """Sanity: a normal (non-restart) fresh-connect initiating message is
    unchanged by bd polyglot-pdf-bhem -- it still uses the greeting template."""
    service = _make_service_ready_for_restart()
    service._is_resume_session = False

    sent = []

    async def _capture_send_client_content(message):
        sent.append(message)

    service._live_ai.send_client_content = _capture_send_client_content

    await service.send_initiating_message("English", "First Name")

    assert len(sent) == 1
    assert "greet" in sent[0].lower(), (
        "a fresh non-restart session must still greet the user"
    )


@pytest.mark.asyncio
async def test_restart_rethreads_injection_budget_tokens():
    """The restart's set_callbacks must re-thread the inline-details window
    budget (bd wsao.8 fresh-eyes): set_callbacks resets the adapter's budget,
    so omitting the kwarg here re-derived the compression window WITHOUT
    details headroom and a reconnect whose current field carries large
    help.details 1007'd at session assemble -- the wsao.2 failure back on the
    routine reconnect path."""
    service = _make_service_ready_for_restart(send_transcript=False)
    service._schema = {
        "form_metadata": {"form_number": "W-7"},
        "fields": [
            {"id": "reason_a", "name": "Reason a", "type": "checkbox",
             "help": {"details": "x" * 8000}},
        ],
    }

    await service.restart_gemini_session(next_field_hint="reason_a (Reason a)")

    kwargs = service._live_ai.set_callbacks.call_args.kwargs
    from backend.services import guidance_contract as gc
    assert kwargs["injection_budget_tokens"] == 2000 + gc.INJECTION_BUDGET_SLOP_TOKENS
