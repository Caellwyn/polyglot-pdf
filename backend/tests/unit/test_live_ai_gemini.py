import asyncio

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types


class _EmptyAsyncIterator:
    """Utility async iterator that immediately stops."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _DummySession:
    """Minimal fake Gemini session for background loop tests."""

    def __init__(self):
        self.inputs = []

    async def send_realtime_input(self, **kwargs):
        self.inputs.append(('audio', kwargs))

    async def send_tool_response(self, **kwargs):
        self.inputs.append(('tool', kwargs))

    async def send_client_content(self, **kwargs):
        # The adapter's text_sender / queued-content paths call this
        # (live_ai_gemini.py send_client_content); capture for assertions.
        self.inputs.append(('client_content', kwargs))

    def receive(self):
        return _EmptyAsyncIterator()


class _DummyContextManager:
    """Async context manager returning the supplied session."""

    def __init__(self, session: _DummySession):
        self.session = session
        self.entered = False

    async def __aenter__(self):
        self.entered = True
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


# Correctly patch the 'google.genai' module used by the adapter
@pytest.fixture
def mock_google_ai_client():
    """Mocks the google.genai.Client for live adapter."""
    with patch("backend.adapters.live_ai_gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_aio_live = MagicMock()

        # The session that `connect` will return
        mock_session = AsyncMock()

        # `connect` itself needs to be an AsyncMock to be awaitable
        mock_aio_live.connect = AsyncMock(return_value=mock_session)

        mock_client.aio.live = mock_aio_live

        # Patch the Client constructor to return our mock client
        mock_genai.Client = MagicMock(return_value=mock_client)

        yield mock_genai, mock_session


@pytest.mark.asyncio
async def test_live_ai_gemini_connect(mock_google_ai_client):
    """Tests that the connect method establishes a session."""
    from backend.adapters.live_ai_gemini import LiveAIGemini, LiveAIGeminiSession

    mock_genai, mock_session = mock_google_ai_client

    adapter = LiveAIGemini(api_key="test_key")

    model = "gemini-test"
    config = {"system_instruction": "test"}

    async with adapter.connect(model=model, config=config) as session:
        assert isinstance(session, LiveAIGeminiSession)
        # Ensure the Client constructor was called with the API key
        mock_genai.Client.assert_called_once_with(api_key="test_key")
        # Ensure the underlying client was called correctly
        adapter._client.aio.live.connect.assert_called_once_with(model=model, config=config)
        assert session._session == mock_session


@pytest.mark.asyncio
async def test_connect_rebuilds_client_with_api_key(mock_google_ai_client):
    """connect() reconstruction path must rebuild a KEYED AI Studio client.

    Regression guard for bd polyglot-pdf-jrl: if _client is torn down, the
    rebuild branch in connect() must pass the stored api_key, not fall back to a
    bare ClientCls() (which would resolve ADC and fail on the AI Studio path).
    """
    from backend.adapters.live_ai_gemini import LiveAIGemini

    mock_genai, _ = mock_google_ai_client

    # vertexai defaults to False -> AI Studio (API-key) path.
    adapter = LiveAIGemini(api_key="test_key")
    # __init__ already built one client; reset the call record and force a rebuild.
    mock_genai.Client.reset_mock()
    adapter._client = None

    async with adapter.connect(model="gemini-test", config={"system_instruction": "x"}):
        # The reconstruction branch must carry the key through, not call bare.
        mock_genai.Client.assert_called_once_with(api_key="test_key")


@pytest.mark.asyncio
async def test_live_ai_session_send_audio(mock_google_ai_client):
    """Tests that send_audio formats the request correctly."""
    from backend.adapters.live_ai_gemini import LiveAIGeminiSession

    _, mock_session = mock_google_ai_client
    session_adapter = LiveAIGeminiSession(mock_session)

    audio_chunk = b"\x01\x02\x03"
    await session_adapter.send_audio(audio_chunk)

    # Verify that the underlying session's method was called with a correctly structured Blob
    mock_session.send_realtime_input.assert_called_once()
    call_args = mock_session.send_realtime_input.call_args
    assert "audio" in call_args.kwargs
    audio_blob = call_args.kwargs["audio"]
    assert isinstance(audio_blob, types.Blob)
    assert audio_blob.data == audio_chunk
    assert audio_blob.mime_type == "audio/pcm;rate=16000"


@pytest.mark.asyncio
async def test_live_ai_session_send_tool_response(mock_google_ai_client):
    """Tests that send_tool_response formats the response correctly."""
    from backend.adapters.live_ai_gemini import LiveAIGeminiSession

    _, mock_session = mock_google_ai_client
    session_adapter = LiveAIGeminiSession(mock_session)

    # Our internal, simpler response format
    tool_responses = [
        {"id": "123", "name": "update_form_fields", "response": {"FullName": "John Doe"}}
    ]

    await session_adapter.send_tool_response(tool_responses)

    # Verify the call to the underlying session
    mock_session.send_tool_response.assert_called_once()
    call_args = mock_session.send_tool_response.call_args
    assert "function_responses" in call_args.kwargs

    # Check that our dict was correctly transformed into a FunctionResponse object
    function_responses_list = call_args.kwargs["function_responses"]
    assert len(function_responses_list) == 1
    function_response = function_responses_list[0]
    assert isinstance(function_response, types.FunctionResponse)
    assert function_response.id == "123"
    assert function_response.name == "update_form_fields"
    assert function_response.response == {"FullName": "John Doe"}


@pytest.mark.asyncio
async def test_live_ai_session_receive(mock_google_ai_client):
    """Tests that the receive method correctly yields chunks from the underlying session."""
    from backend.adapters.live_ai_gemini import LiveAIGeminiSession

    _, mock_session = mock_google_ai_client

    # Setup the mock session to behave like an async generator
    mock_chunks = [MagicMock(), MagicMock()]

    # The `receive` method itself returns an async generator
    async def async_gen():
        for chunk in mock_chunks:
            yield chunk

    # The mock should return an already-called async generator
    mock_session.receive = MagicMock(return_value=async_gen())
    session_adapter = LiveAIGeminiSession(mock_session)

    received_chunks = []
    # The adapter's receive method is what we are testing
    async for chunk in session_adapter.receive():
        received_chunks.append(chunk)

    assert received_chunks == mock_chunks
    mock_session.receive.assert_called_once()


@pytest.mark.asyncio
async def test_run_session_loop_awaits_coroutine_connect():
    """Ensure the background loop awaits coroutine-based connect objects."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    dummy_session = _DummySession()

    class _FakeLive:
        def __init__(self):
            self.calls = []

        async def connect(self, *, model, config):
            self.calls.append((model, config))
            return dummy_session

    fake_live = _FakeLive()
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    # Pre-create the audio + text queues to satisfy the sender loops. Without
    # _text_queue the text_sender task crashes on a None queue in the background
    # (silently swallowed but real). (PR #76 follow-up.)
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    # The fake connect should have been awaited once with the adapter's model
    assert len(fake_live.calls) == 1
    model_called, config_called = fake_live.calls[0]
    assert model_called == adapter._model_name
    assert config_called["response_modalities"] == ["AUDIO"]
    # transcription key is present only when transcripts are explicitly enabled
    assert ("output_audio_transcription" in config_called) == bool(adapter._enable_transcripts and adapter._on_transcript)
    assert "tools" in config_called and config_called["tools"]
    # ensure background tasks are cleaned up to avoid pending tasks
    await adapter.finalize()


@pytest.mark.asyncio
async def test_run_session_loop_handles_async_context_manager():
    """Ensure context-manager style connect objects are handled."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    dummy_session = _DummySession()
    ctx = _DummyContextManager(dummy_session)

    fake_live = MagicMock()
    fake_live.connect.return_value = ctx

    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()  # else text_sender crashes on None (PR #76 follow-up)

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    assert ctx.entered is True
    assert fake_live.connect.call_count >= 1
    _, kwargs = fake_live.connect.call_args_list[-1]
    assert kwargs["model"] == adapter._model_name
    assert kwargs["config"]["response_modalities"] == ["AUDIO"]
    # transcription key is present only when transcripts are explicitly enabled
    assert ("output_audio_transcription" in kwargs["config"]) == bool(adapter._enable_transcripts and adapter._on_transcript)
    assert "tools" in kwargs["config"]
    # ensure background tasks are cleaned up to avoid pending tasks
    await adapter.finalize()


@pytest.mark.asyncio
async def test_run_session_loop_logs_on_connect_failure():
    """Connection errors should be surfaced via the adapter logger."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._audio_queue = asyncio.Queue()

    logger = MagicMock()
    adapter._log = logger

    async def failing_connect(*, model, config):
        raise RuntimeError("boom")

    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=failing_connect)))

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    error_calls = [call for call in logger.error.call_args_list if call.args and call.args[0] == "session_loop_error"]
    assert error_calls, "expected session_loop_error to be logged"
    error_call = error_calls[-1]
    assert error_call.kwargs.get("error") == "boom"
    # ensure background tasks are cleaned up to avoid pending tasks
    await adapter.finalize()


@pytest.mark.asyncio
async def test_run_session_loop_dispatches_tool_calls():
    """Tool calls should trigger the callback and emit function responses."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    tool_calls_seen = []

    async def on_tool_call(name, args):
        tool_calls_seen.append((name, args))
        return {"Full Name": "Alice"}

    adapter._on_tool_call = on_tool_call
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()  # else text_sender crashes on None (PR #76 follow-up)

    class _ToolCallSession:
        def __init__(self):
            self.sent_responses = []
            self.sent_messages = []
            self._generator = None

        async def send_realtime_input(self, **_kwargs):
            return None

        async def send_tool_response(self, *, function_responses):
            self.sent_responses.append(function_responses)

        async def send_client_content(self, **kwargs):
            self.sent_messages.append(kwargs)

        def receive(self):
            # Return the same generator instance each time to avoid infinite loop
            if self._generator is None:
                async def gen():
                    tool_fc = SimpleNamespace(
                        name="update_form_fields",
                        id="call-1",
                        arguments='{"Full Name": "Alice"}'
                    )
                    yield SimpleNamespace(tool_call=SimpleNamespace(function_calls=[tool_fc]))
                self._generator = gen()
            return self._generator

    session = _ToolCallSession()
    ctx = _DummyContextManager(session)

    fake_live = MagicMock()
    fake_live.connect.return_value = ctx

    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    assert tool_calls_seen == [("update_form_fields", {"Full Name": "Alice"})]
    assert len(session.sent_responses) == 1
    responses = session.sent_responses[0]
    assert len(responses) == 1
    response_obj = responses[0]
    # FunctionResponse doesn't include 'id' - SDK matches internally
    assert response_obj.name == "update_form_fields"
    assert response_obj.response == {"Full Name": "Alice"}
    # ensure background tasks are cleaned up to avoid pending tasks
    await adapter.finalize()


@pytest.mark.asyncio
async def test_send_text_turn_uses_realtime_input_for_3p1():
    """3.1 family text turns must go via send_realtime_input(text=), not
    send_client_content -- the latter 1007s on gemini-3.1-flash-live-preview
    (bd polyglot-pdf-1g6, verified against the live endpoint)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini(api_key="k", model="gemini-3.1-flash-live-preview")
    session = SimpleNamespace(
        send_realtime_input=AsyncMock(),
        send_client_content=AsyncMock(),
    )

    await adapter._send_text_turn(session, "hello")

    session.send_realtime_input.assert_awaited_once()
    # text passed as the text= kwarg, not via turns/client_content
    assert session.send_realtime_input.await_args.kwargs.get("text") == "hello"
    session.send_client_content.assert_not_called()


@pytest.mark.asyncio
async def test_send_text_turn_uses_client_content_for_2p5():
    """2.5 (and other non-3.1) families keep send_client_content -- the
    send_realtime_input(text=) path is unverified there, so we must not switch it."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini(api_key="k", model="gemini-2.5-flash-native-audio-preview-12-2025")
    session = SimpleNamespace(
        send_realtime_input=AsyncMock(),
        send_client_content=AsyncMock(),
    )

    await adapter._send_text_turn(session, "hello")

    session.send_client_content.assert_awaited_once()
    session.send_realtime_input.assert_not_called()


def _count_summary_emits(mock_log) -> int:
    """How many session_cost_summary lines a mocked adapter._log emitted."""
    return sum(
        1 for c in mock_log.info.call_args_list
        if c.args and c.args[0] == "session_cost_summary"
    )


@pytest.mark.asyncio
async def test_session_cost_summary_emitted_once_on_finalize():
    """finalize() emits exactly one session_cost_summary when tokens were billed."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter.set_session_context(form_session_id="fs-1", form_id="I-90")
    # Simulate a session that billed some tokens.
    adapter._session_total_tokens = 500
    adapter._session_prompt_tokens = 400
    adapter._session_total_cost = 0.0123
    adapter._session_audio_input_tokens = 200

    await adapter.finalize()

    assert _count_summary_emits(adapter._log) == 1
    summary_call = next(
        c for c in adapter._log.info.call_args_list
        if c.args and c.args[0] == "session_cost_summary"
    )
    assert summary_call.kwargs["total_tokens"] == 500
    assert summary_call.kwargs["form_session_id"] == "fs-1"


@pytest.mark.asyncio
async def test_session_cost_summary_emitted_once_across_double_finalize():
    """A second finalize() must NOT re-emit (guards downstream double-count)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter._session_total_tokens = 42

    await adapter.finalize()
    await adapter.finalize()

    assert _count_summary_emits(adapter._log) == 1


@pytest.mark.asyncio
async def test_session_cost_summary_not_emitted_for_zero_token_session():
    """No summary line for a session that never billed any tokens (no noise)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    # _session_total_tokens stays 0 (never started / never billed).

    await adapter.finalize()

    assert _count_summary_emits(adapter._log) == 0


def _vad_settings(
    *,
    disabled=True,
    start="LOW",
    end="LOW",
    prefix=500,
    silence=500,
):
    """Build a settings stub for LiveAIGemini._build_vad_settings."""
    return SimpleNamespace(
        DISABLE_GEMINI_VAD=disabled,
        VAD_START_SENSITIVITY=start,
        VAD_END_SENSITIVITY=end,
        VAD_PREFIX_PADDING_MS=prefix,
        VAD_SILENCE_DURATION_MS=silence,
    )


def test_vad_disabled_sends_only_disabled_flag():
    """bd polyglot-pdf-p1t: when VAD is disabled, send ONLY {disabled: True}.

    The Live API rejects (1007) a config that sets disabled=True alongside any
    sensitivity/padding field — so even though the VAD_* knobs are populated
    (the default config), none of them may leak into the payload.
    """
    from backend.adapters.live_ai_gemini import LiveAIGemini

    # Defaults: disabled=True with all sensitivity/padding knobs set.
    result = LiveAIGemini._build_vad_settings(_vad_settings())

    assert result == {"disabled": True}


def test_vad_enabled_sends_sensitivity_fields_and_no_disabled():
    """When VAD is enabled, pass the knobs through and never set disabled."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from google.genai import types

    result = LiveAIGemini._build_vad_settings(_vad_settings(disabled=False))

    assert "disabled" not in result
    assert result["start_of_speech_sensitivity"] == types.StartSensitivity.START_SENSITIVITY_LOW
    assert result["end_of_speech_sensitivity"] == types.EndSensitivity.END_SENSITIVITY_LOW
    assert result["prefix_padding_ms"] == 500
    assert result["silence_duration_ms"] == 500


def test_vad_enabled_maps_mixed_sensitivity_values():
    """HIGH/LOW map to the right enum members per axis (catches a prefix mixup)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from google.genai import types

    result = LiveAIGemini._build_vad_settings(
        _vad_settings(disabled=False, start="HIGH", end="LOW")
    )

    assert result["start_of_speech_sensitivity"] == types.StartSensitivity.START_SENSITIVITY_HIGH
    assert result["end_of_speech_sensitivity"] == types.EndSensitivity.END_SENSITIVITY_LOW


def test_vad_enabled_omits_unspecified_and_none_knobs():
    """Enabled VAD with no usable knobs yields {} (Gemini uses its defaults)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    result = LiveAIGemini._build_vad_settings(
        _vad_settings(
            disabled=False,
            start="UNSPECIFIED",
            end="UNSPECIFIED",
            prefix=None,
            silence=None,
        )
    )

    assert result == {}


def test_vad_invalid_sensitivity_is_skipped_not_fatal():
    """bd polyglot-pdf-u01: a typo'd sensitivity (e.g. MEDIUM) is skipped, not raised.

    A bad VAD_*_SENSITIVITY value used to KeyError out of _build_vad_settings;
    the caller's broad except then dropped the ENTIRE realtime_input_config. The
    fix whitelists LOW/HIGH/UNSPECIFIED and skips unknown values with a warning,
    so the rest of the config (including the valid axis + padding) still applies.
    """
    import structlog
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from google.genai import types

    # start is a typo, end is valid -> end + padding survive, start is dropped,
    # and the dropped axis emits the invalid_vad_sensitivity_skipped warning.
    with structlog.testing.capture_logs() as logs:
        result = LiveAIGemini._build_vad_settings(
            _vad_settings(disabled=False, start="MEDIUM", end="HIGH")
        )

    assert "start_of_speech_sensitivity" not in result
    assert result["end_of_speech_sensitivity"] == types.EndSensitivity.END_SENSITIVITY_HIGH
    assert result["prefix_padding_ms"] == 500
    assert result["silence_duration_ms"] == 500

    skipped = [e for e in logs if e.get("event") == "invalid_vad_sensitivity_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["field"] == "VAD_START_SENSITIVITY"
    assert skipped[0]["value"] == "MEDIUM"


# === Context-window compression (epic polyglot-pdf-l3a, bead -45o) ===

async def _capture_session_config(monkeypatch, **settings_overrides):
    """Drive _run_session_loop with a fake live client and return the config dict
    it passed to connect(). settings_overrides patches the compression knobs on the
    settings object the adapter reads via get_settings() inside the loop.
    """
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from backend import config as _config

    base = _config.get_settings()
    for key, value in settings_overrides.items():
        setattr(base, key, value)
    # The adapter imports get_settings locally inside _run_session_loop, so patch the
    # module attribute it resolves at call time.
    monkeypatch.setattr(_config, "get_settings", lambda: base)

    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    captured = {}

    class _FakeLive:
        async def connect(self, *, model, config):
            captured["config"] = config
            return _DummySession()

    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=_FakeLive()))
    adapter._audio_queue = asyncio.Queue()
    # _handle_session starts a text_sender task that awaits _text_queue.get(); without
    # this the task crashes on a None queue in the background (silently swallowed, but
    # a strict-task-exception pytest config would surface it). fresh-eyes PR #76.
    adapter._text_queue = asyncio.Queue()

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)
    await adapter.finalize()
    return captured["config"]


@pytest.mark.asyncio
async def test_compression_block_present_when_enabled(monkeypatch):
    """With CONTEXT_COMPRESSION_ENABLED, the connect config carries the sliding
    window with the configured trigger/target token values."""
    config = await _capture_session_config(
        monkeypatch,
        CONTEXT_COMPRESSION_ENABLED=True,
        CONTEXT_COMPRESSION_TRIGGER_TOKENS=5000,
        CONTEXT_COMPRESSION_WINDOW_TOKENS=3000,
    )

    assert "context_window_compression" in config
    cwc = config["context_window_compression"]
    assert cwc["trigger_tokens"] == 5000
    assert cwc["sliding_window"]["target_tokens"] == 3000


@pytest.mark.asyncio
async def test_compression_block_absent_when_disabled(monkeypatch):
    """With the flag off (the default), no compression key is sent -- the live
    context stays unbounded, exactly as before this feature."""
    config = await _capture_session_config(
        monkeypatch,
        CONTEXT_COMPRESSION_ENABLED=False,
    )

    assert "context_window_compression" not in config


def test_compression_window_clamped_below_trigger_when_enabled():
    """The Live API requires target_tokens < trigger_tokens. A misconfig that
    inverts them must be clamped (when compression is enabled), not passed through,
    so the API never rejects it."""
    from backend.config import Settings

    s = Settings(
        CONTEXT_COMPRESSION_ENABLED=True,
        CONTEXT_COMPRESSION_TRIGGER_TOKENS=4000,
        CONTEXT_COMPRESSION_WINDOW_TOKENS=8000,  # invalid: >= trigger
    )

    assert s.CONTEXT_COMPRESSION_WINDOW_TOKENS < s.CONTEXT_COMPRESSION_TRIGGER_TOKENS
    assert s.CONTEXT_COMPRESSION_WINDOW_TOKENS == 2000  # trigger // 2


def test_compression_window_not_clamped_when_disabled():
    """When compression is OFF the values are inert; we must NOT silently rewrite
    them (an operator may be pre-staging values before flipping the flag)."""
    from backend.config import Settings

    s = Settings(
        CONTEXT_COMPRESSION_ENABLED=False,
        CONTEXT_COMPRESSION_TRIGGER_TOKENS=1000,
        CONTEXT_COMPRESSION_WINDOW_TOKENS=2000,  # inverted, but inert while disabled
    )

    assert s.CONTEXT_COMPRESSION_WINDOW_TOKENS == 2000  # left untouched


@pytest.mark.asyncio
async def test_compression_clamped_value_reaches_connect(monkeypatch):
    """End-to-end: an inverted window with compression ENABLED reaches connect() as
    the CLAMPED value (< trigger), not the raw one -- the path that actually keeps the
    API from rejecting the config. fresh-eyes PR #76."""
    from backend.config import Settings

    # Build via Settings(**kwargs) so the validator clamp runs, then drive the adapter.
    settings = Settings(
        CONTEXT_COMPRESSION_ENABLED=True,
        CONTEXT_COMPRESSION_TRIGGER_TOKENS=4000,
        CONTEXT_COMPRESSION_WINDOW_TOKENS=8000,  # invalid; clamped to 2000
    )
    from backend import config as _config
    monkeypatch.setattr(_config, "get_settings", lambda: settings)

    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    captured = {}

    class _FakeLive:
        async def connect(self, *, model, config):
            captured["config"] = config
            return _DummySession()

    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=_FakeLive()))
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()
    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)
    await adapter.finalize()

    cwc = captured["config"]["context_window_compression"]
    assert cwc["trigger_tokens"] == 4000
    assert cwc["sliding_window"]["target_tokens"] == 2000  # clamped, not 8000


# --- Native-VAD activity-signal gating (bd polyglot-pdf-333) ---------------
#
# When Gemini's own VAD is enabled (DISABLE_GEMINI_VAD=False), the adapter must
# NOT forward manual activity_start/end signals -- interleaving them with
# automatic detection is the conflicting turn-taking state _build_vad_settings
# warns about. When manual VAD is on (DISABLE_GEMINI_VAD=True) the signals fire.

def _adapter_with_session_and_vad(monkeypatch, *, disable_gemini_vad):
    """A LiveAIGemini with a mock active session and a patched DISABLE_GEMINI_VAD."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from backend import config as _config

    base = _config.get_settings()
    base.DISABLE_GEMINI_VAD = disable_gemini_vad
    # send_activity_start/end import get_settings locally, so patch the module attr.
    monkeypatch.setattr(_config, "get_settings", lambda: base)

    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter._current_session = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_activity_signals_suppressed_in_native_vad(monkeypatch):
    """DISABLE_GEMINI_VAD=False -> activity_start/end are dropped (Gemini owns VAD)."""
    adapter = _adapter_with_session_and_vad(monkeypatch, disable_gemini_vad=False)

    await adapter.send_activity_start()
    await adapter.send_activity_end()

    adapter._current_session.send_realtime_input.assert_not_awaited()


@pytest.mark.asyncio
async def test_activity_signals_fire_in_manual_vad(monkeypatch):
    """DISABLE_GEMINI_VAD=True -> activity_start/end ARE sent (manual turn-taking)."""
    adapter = _adapter_with_session_and_vad(monkeypatch, disable_gemini_vad=True)

    await adapter.send_activity_start()
    await adapter.send_activity_end()

    assert adapter._current_session.send_realtime_input.await_count == 2
    # The first call carries activity_start, the second activity_end.
    first_kwargs = adapter._current_session.send_realtime_input.await_args_list[0].kwargs
    second_kwargs = adapter._current_session.send_realtime_input.await_args_list[1].kwargs
    assert "activity_start" in first_kwargs
    assert "activity_end" in second_kwargs


