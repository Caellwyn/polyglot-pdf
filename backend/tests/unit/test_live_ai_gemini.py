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
async def test_live_ai_session_send_tool_response_missing_id(mock_google_ai_client):
    """A response dict without an id is tolerated (id omitted, no KeyError).

    bd polyglot-pdf-c4a: the wrapper now routes through _build_function_response
    and uses .get("id"), so a missing id omits the field instead of raising
    KeyError. Mirrors the hot path's omit-if-absent behavior (bd polyglot-pdf-0ux).
    """
    from backend.adapters.live_ai_gemini import LiveAIGeminiSession

    _, mock_session = mock_google_ai_client
    session_adapter = LiveAIGeminiSession(mock_session)

    tool_responses = [
        {"name": "update_form_fields", "response": {"FullName": "John Doe"}}
    ]

    await session_adapter.send_tool_response(tool_responses)

    mock_session.send_tool_response.assert_called_once()
    function_responses_list = mock_session.send_tool_response.call_args.kwargs[
        "function_responses"
    ]
    assert len(function_responses_list) == 1
    function_response = function_responses_list[0]
    assert isinstance(function_response, types.FunctionResponse)
    assert function_response.id is None
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
    assert response_obj.name == "update_form_fields"
    assert response_obj.response == {"Full Name": "Alice"}
    # bd polyglot-pdf-0ux: the FunctionResponse MUST echo the tool call's id back.
    # The SDK's AI-Studio (mldev) path raises _FUNCTION_RESPONSE_REQUIRES_ID without
    # it, crashing the receive loop after the first fill. The earlier code dropped
    # the id here (on a wrong "SDK matches by order" assumption); this asserts it is
    # carried through.
    assert response_obj.id == "call-1"
    # ensure background tasks are cleaned up to avoid pending tasks
    await adapter.finalize()


@pytest.mark.asyncio
async def test_model_turn_parts_tool_call_without_id_still_responds():
    """A model_turn.parts function_call with NO id must still get a response.

    Regression guard (bd polyglot-pdf-tks): Gemini Live blocks until every
    function call it issues gets a FunctionResponse. The model_turn.parts receive
    path previously gated the response append on `call_id`, so a function_call
    that arrived without an 'id' produced no response at all and Gemini hung on
    the first tool-call/response loop. The append now gates on tool_name only;
    the id is echoed back when present (the normal case -- bd polyglot-pdf-0ux)
    and omitted only for this rare id-less call, so Gemini still gets SOME response
    instead of hanging (the Vertex path tolerates a missing id; AI Studio does not,
    but a real id-less call is the exception, not the rule).
    """
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    tool_calls_seen = []

    async def on_tool_call(name, args):
        tool_calls_seen.append((name, args))
        return {"state": "ok"}

    adapter._on_tool_call = on_tool_call
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    class _PartsToolCallSession:
        def __init__(self):
            self.sent_responses = []
            self._generator = None

        async def send_realtime_input(self, **_kwargs):
            return None

        async def send_tool_response(self, *, function_responses):
            self.sent_responses.append(function_responses)

        async def send_client_content(self, **kwargs):
            return None

        def receive(self):
            if self._generator is None:
                async def gen():
                    # function_call on the model_turn.parts path, deliberately
                    # WITHOUT an `id` (the SDK does not always populate it here).
                    fc = SimpleNamespace(
                        name="get_form_status",
                        arguments='{"field_ids": []}',
                    )
                    part = SimpleNamespace(function_call=fc)
                    model_turn = SimpleNamespace(parts=[part])
                    server_content = SimpleNamespace(model_turn=model_turn)
                    yield SimpleNamespace(server_content=server_content)
                self._generator = gen()
            return self._generator

    session = _PartsToolCallSession()
    ctx = _DummyContextManager(session)

    fake_live = MagicMock()
    fake_live.connect.return_value = ctx
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    # The callback fired AND a response was sent despite the missing id.
    assert tool_calls_seen == [("get_form_status", {"field_ids": []})]
    assert len(session.sent_responses) == 1
    responses = session.sent_responses[0]
    assert len(responses) == 1
    assert responses[0].name == "get_form_status"
    assert responses[0].response == {"state": "ok"}


# ===========================================================================
# Structured tool-error envelope on a callback RAISE (bd polyglot-pdf-wpw.1 /
# WS-C2). A callback exception must send {"status":"error",...}, NOT the silent
# {} that reads as success and makes the model confabulate. Extends the uov.14
# tool-contract scope.
# ===========================================================================

def test_tool_error_envelope_is_structured_and_pii_free():
    from backend.adapters.live_ai_gemini import _tool_error_envelope
    env = _tool_error_envelope()
    assert env["status"] == "error"
    assert env["retryable"] is True
    assert isinstance(env["message"], str) and env["message"]
    # The failure must nest under an `error` key -- the documented Live API
    # tool-failure shape (response={"error": ...}); without it the model can read
    # a free-form response dict as a successful result (Codex PR #138 round 2).
    assert env["error"] == env["message"]
    # Default message must be a fixed string, never echo exception/argument text.
    env2 = _tool_error_envelope("custom note")
    assert env2["message"] == "custom note"
    assert env2["error"] == "custom note"


def _make_tool_call_session(path: str):
    """A fake session that yields ONE tool call on the requested receive path and
    records the FunctionResponses sent back."""
    class _Session:
        def __init__(self):
            self.sent_responses = []
            self._generator = None

        async def send_realtime_input(self, **_kwargs):
            return None

        async def send_tool_response(self, *, function_responses):
            self.sent_responses.append(function_responses)

        async def send_client_content(self, **kwargs):
            return None

        def receive(self):
            if self._generator is None:
                async def gen():
                    if path == "event.tool_call":
                        fc = SimpleNamespace(
                            name="update_form_fields",
                            id="function-call-1",
                            arguments='{"field_id": "x", "value": "y"}',
                        )
                        tool_call = SimpleNamespace(function_calls=[fc])
                        yield SimpleNamespace(tool_call=tool_call)
                    else:  # model_turn.parts
                        fc = SimpleNamespace(
                            name="update_form_fields",
                            id="function-call-1",
                            arguments='{"field_id": "x", "value": "y"}',
                        )
                        part = SimpleNamespace(function_call=fc)
                        model_turn = SimpleNamespace(parts=[part])
                        server_content = SimpleNamespace(model_turn=model_turn)
                        yield SimpleNamespace(server_content=server_content)
                self._generator = gen()
            return self._generator
    return _Session()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["event.tool_call", "model_turn.parts"])
async def test_callback_raise_sends_structured_error_not_empty_dict(path):
    """On BOTH receive paths, a callback that RAISES must send a structured error
    envelope, not a bare {} (bd polyglot-pdf-wpw.1)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    async def on_tool_call(name, args):
        raise RuntimeError("field value 12345 -- must NOT appear in the response")
    adapter._on_tool_call = on_tool_call
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    session = _make_tool_call_session(path)
    fake_live = MagicMock()
    fake_live.connect.return_value = _DummyContextManager(session)
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    assert len(session.sent_responses) == 1
    resp = session.sent_responses[0][0]
    assert resp.name == "update_form_fields"
    # Structured error -- NOT the silent {} that reads as success. The `error`
    # key is the documented Live API tool-failure shape (Codex PR #138 round 2).
    assert resp.response.get("status") == "error", resp.response
    assert resp.response.get("retryable") is True, resp.response
    assert resp.response.get("error"), resp.response
    assert resp.response != {}
    # The call_id is still echoed (0ux invariant preserved).
    assert resp.id == "function-call-1"
    # No PII: the exception text (with the field value) must not leak into the body.
    assert "12345" not in str(resp.response)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["event.tool_call", "model_turn.parts"])
async def test_callback_returning_none_still_coerces_to_empty_dict(path):
    """The tks invariant is preserved: a callback that legitimately RETURNS None
    (not a raise) still gets the {} coercion -- only a RAISE produces the error
    envelope (bd polyglot-pdf-wpw.1). Both receive paths, so neither routes a
    legitimate None through the error envelope."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    async def on_tool_call(name, args):
        return None
    adapter._on_tool_call = on_tool_call
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    session = _make_tool_call_session(path)
    fake_live = MagicMock()
    fake_live.connect.return_value = _DummyContextManager(session)
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    resp = session.sent_responses[0][0]
    assert resp.response == {}  # legitimate None -> {} (NOT an error envelope)

    await adapter.finalize()


@pytest.mark.asyncio
async def test_model_turn_parts_tool_call_exception_still_responds():
    """A callback exception on the model_turn.parts path must still respond.

    Regression guard (bd polyglot-pdf-tks): if the tool callback raises, the
    exception is caught and logged and a FunctionResponse must STILL be sent so
    Gemini is not left blocking on an unanswered call. The BODY is now a structured
    error envelope (bd polyglot-pdf-wpw.1), not the old silent {} -- so the model
    re-asks instead of confabulating success.
    """
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    async def on_tool_call(name, args):
        raise RuntimeError("boom")

    adapter._on_tool_call = on_tool_call
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    class _RaisingPartsSession:
        def __init__(self):
            self.sent_responses = []
            self._generator = None

        async def send_realtime_input(self, **_kwargs):
            return None

        async def send_tool_response(self, *, function_responses):
            self.sent_responses.append(function_responses)

        async def send_client_content(self, **kwargs):
            return None

        def receive(self):
            if self._generator is None:
                async def gen():
                    fc = SimpleNamespace(
                        name="get_form_status",
                        id="call-xyz",
                        arguments='{"field_ids": []}',
                    )
                    part = SimpleNamespace(function_call=fc)
                    model_turn = SimpleNamespace(parts=[part])
                    server_content = SimpleNamespace(model_turn=model_turn)
                    yield SimpleNamespace(server_content=server_content)
                self._generator = gen()
            return self._generator

    session = _RaisingPartsSession()
    ctx = _DummyContextManager(session)

    fake_live = MagicMock()
    fake_live.connect.return_value = ctx
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    # Even though the callback raised, a response was still sent (tks invariant) --
    # now a STRUCTURED error envelope, not the old silent {} (wpw.1).
    assert len(session.sent_responses) == 1
    responses = session.sent_responses[0]
    assert len(responses) == 1
    assert responses[0].name == "get_form_status"
    assert responses[0].response.get("status") == "error"
    assert responses[0].response != {}

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
    # 2.5 is the prod path -- pin the exact pre-fix payload shape so a future
    # refactor can't silently change it (no explicit role; turn_complete=True).
    kwargs = session.send_client_content.await_args.kwargs
    assert kwargs["turns"] == {"parts": [{"text": "hello"}]}
    assert kwargs["turn_complete"] is True


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
    sensitivity/padding field -- so even though the VAD_* knobs are populated
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

    # Build a FRESH Settings to mutate -- get_settings() is lru_cached, so mutating
    # its result would poison the shared singleton for later tests (the cache
    # outlives monkeypatch's function-reference restore). Settings() is the
    # un-cached constructor the cache wraps.
    base = _config.Settings()
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

    # Fresh Settings, not the lru_cached get_settings() result -- mutating the
    # cached singleton would leak into later tests (see _capture_session_config).
    base = _config.Settings()
    base.DISABLE_GEMINI_VAD = disable_gemini_vad
    # send_activity_start/end import get_settings locally, so patch the module attr.
    monkeypatch.setattr(_config, "get_settings", lambda: base)

    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter._current_session = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_activity_signals_suppressed_in_native_vad(monkeypatch):
    """DISABLE_GEMINI_VAD=False (native VAD) -> the conflicting manual
    activity_start/activity_end signals are suppressed (Gemini owns turn-taking).

    activity_start is dropped entirely. activity_end does NOT send the conflicting
    types.ActivityEnd; instead it sends audio_stream_end=True -- the documented
    realtime signal that is compatible with automatic VAD -- so PTT-as-a-gate can
    still finalize the audio segment after release without the session going silent
    (bd polyglot-pdf-6vo / PR #119). So exactly ONE send_realtime_input fires here,
    carrying audio_stream_end, and never activity_start or activity_end.
    """
    adapter = _adapter_with_session_and_vad(monkeypatch, disable_gemini_vad=False)
    send = adapter._current_session.send_realtime_input

    # start and end are asserted INDEPENDENTLY (Codex review, PR #122): an
    # aggregate "exactly one call" check would still pass if native mode regressed
    # to emit the realtime input on START and suppress END -- which would silently
    # break the PTT-release turn-close. So pin each half on its own.
    await adapter.send_activity_start()
    assert send.await_count == 0  # start is fully suppressed in native mode

    await adapter.send_activity_end()
    assert send.await_count == 1  # end is the ONLY emitter here
    only_kwargs = send.await_args_list[0].kwargs
    assert only_kwargs.get("audio_stream_end") is True
    assert "activity_start" not in only_kwargs
    assert "activity_end" not in only_kwargs


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


# ===========================================================================
# Cooperative receive-loop shutdown (bd polyglot-pdf-0c1 / y4a).
# ===========================================================================

def test_begin_graceful_shutdown_sets_flags_without_cancel():
    """begin_graceful_shutdown is sync + lock-free: it sets _close_after_flush and
    _intentional_shutdown, clears _session_ready, and returns the per-session
    _closed_event -- WITHOUT cancelling the task (the whole point of y4a)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini(api_key="test_key")
    ev = asyncio.Event()
    adapter._closed_event = ev
    adapter._session_ready = True
    adapter._close_after_flush = False
    adapter._intentional_shutdown = False

    returned = adapter.begin_graceful_shutdown()

    assert returned is ev
    assert adapter._close_after_flush is True
    assert adapter._intentional_shutdown is True
    assert adapter._session_ready is False


def test_begin_graceful_shutdown_returns_set_event_when_no_session():
    """With no live session (_closed_event is None) the returned event is already
    SET, so a caller awaiting it never hangs."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini(api_key="test_key")
    adapter._closed_event = None

    ev = adapter.begin_graceful_shutdown()
    assert ev.is_set()


@pytest.mark.asyncio
async def test_finalize_from_bg_task_downgrades_to_graceful(monkeypatch):
    """The y4a self-cancel guard: if finalize() is ever awaited from the receive
    task itself, it must NOT cancel that task -- it downgrades to a cooperative
    shutdown instead, so the in-flight tool response can never be orphaned."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini(api_key="test_key")
    adapter._closed_event = asyncio.Event()

    cancelled = {"v": False}

    async def _fake_bg():
        # Simulate the receive task calling finalize() on ITSELF.
        await adapter.finalize()
        # If finalize self-cancelled, we'd never reach here on this task.
        return "reached-after-finalize"

    task = asyncio.create_task(_fake_bg())
    adapter._bg_task = task
    result = await task

    assert result == "reached-after-finalize"  # task was NOT cancelled
    assert adapter._close_after_flush is True   # downgraded to graceful shutdown
    assert cancelled["v"] is False


@pytest.mark.asyncio
async def test_set_callbacks_resets_close_after_flush_and_event():
    """A stale _close_after_flush must never kill the NEXT session, and a fresh
    _closed_event is bound per session (bd 0c1). set_callbacks resets both."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini(api_key="test_key")
    adapter._close_after_flush = True  # stale from a prior session
    old_event = asyncio.Event()
    adapter._closed_event = old_event

    # Force the "spawn a new bg task" branch by leaving _bg_task None; patch the
    # loop coroutine so no real Gemini connect happens.
    async def _noop_loop():
        return None
    adapter._run_session_loop = _noop_loop

    adapter.set_callbacks()

    assert adapter._close_after_flush is False
    assert adapter._closed_event is not old_event  # a fresh per-session event
    # Let the trivial bg task finish so its done-callback sets the new event.
    await adapter._bg_task
    assert adapter._closed_event.is_set()


@pytest.mark.asyncio
async def test_run_session_loop_invokes_on_go_away():
    """A GoAway event in the receive stream fires on_go_away with time_left
    (bd polyglot-pdf-c5t). Detection must not break the loop -- the stream ends
    normally and the callback receives the duration string."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    go_aways_seen = []

    async def on_go_away(time_left):
        go_aways_seen.append(time_left)

    adapter._on_go_away = on_go_away
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    class _GoAwaySession:
        def __init__(self):
            self._generator = None

        async def send_realtime_input(self, **_kwargs):
            return None

        async def send_tool_response(self, **_kwargs):
            return None

        async def send_client_content(self, **_kwargs):
            return None

        def receive(self):
            if self._generator is None:
                async def gen():
                    # Mirror the SDK shape: LiveServerMessage.go_away is a
                    # LiveServerGoAway with a time_left string (verified against
                    # google-genai 2.8.0 types).
                    yield SimpleNamespace(
                        go_away=SimpleNamespace(time_left="3.5s")
                    )
                self._generator = gen()
            return self._generator

    session = _GoAwaySession()
    ctx = _DummyContextManager(session)
    fake_live = MagicMock()
    fake_live.connect.return_value = ctx
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    assert go_aways_seen == ["3.5s"]
    await adapter.finalize()


@pytest.mark.asyncio
async def test_run_session_loop_go_away_without_callback_does_not_crash():
    """If no on_go_away is registered, a GoAway event is logged-only and the
    loop still completes cleanly (the callback is optional -- bd c5t)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter._on_go_away = None  # no callback registered
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    class _GoAwaySession:
        def __init__(self):
            self._generator = None

        async def send_realtime_input(self, **_kwargs):
            return None

        async def send_tool_response(self, **_kwargs):
            return None

        async def send_client_content(self, **_kwargs):
            return None

        def receive(self):
            if self._generator is None:
                async def gen():
                    yield SimpleNamespace(go_away=SimpleNamespace(time_left="1s"))
                self._generator = gen()
            return self._generator

    session = _GoAwaySession()
    ctx = _DummyContextManager(session)
    fake_live = MagicMock()
    fake_live.connect.return_value = ctx
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    # Must not raise despite the absent callback; the warning log still fires.
    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)
    adapter._log.warning.assert_any_call(
        "gemini_go_away_received", time_left="1s", event_count=1
    )
    await adapter.finalize()


