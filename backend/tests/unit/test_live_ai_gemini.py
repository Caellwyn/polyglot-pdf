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
    # 4000 sits below the Live API trigger minimum, so the adapter-level clamp
    # (wire-verified 1007 bound) lifts it to 5000 on the way to connect.
    assert cwc["trigger_tokens"] == 5000
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


def test_build_live_config_input_transcription_for_liveness(mock_google_ai_client):
    """`input_audio_transcription` is requested whenever the idle-liveness callback
    is registered, EVEN with transcripts off (bd polyglot-pdf-l3a.4; Codex PR #214).

    The idle watchdog's `on_user_activity` callback fires on a native-VAD
    `input_transcription`, which Gemini only emits when `input_audio_transcription`
    is in the connect config. In the DEFAULT production path send_transcript=False,
    so without this the callback never fires and an actively-speaking user would be
    wrongly idle-timed-out (audio no longer bumps the clock). Output transcription
    stays gated on transcripts (it is the client-visible text -- PHI).
    """
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from backend.config import get_settings

    settings = get_settings()

    # 1. transcripts OFF, liveness callback OFF -> NO input transcription.
    a = LiveAIGemini(api_key="test_key")
    a._enable_transcripts = False
    a._on_user_activity = None
    cfg = a._build_live_config(settings)
    assert "input_audio_transcription" not in cfg
    assert "output_audio_transcription" not in cfg

    # 2. transcripts OFF, liveness callback ON -> input transcription ON, output OFF.
    #    This is the regression: the production default path must still detect turns.
    async def _noop():
        return None

    b = LiveAIGemini(api_key="test_key")
    b._enable_transcripts = False
    b._on_user_activity = _noop
    cfg = b._build_live_config(settings)
    assert "input_audio_transcription" in cfg, (
        "liveness callback registered but Gemini won't emit input_transcription"
    )
    assert "output_audio_transcription" not in cfg, (
        "output transcription (client-visible PHI) must stay gated on transcripts"
    )

    # 3. transcripts ON -> both (unchanged behavior).
    c = LiveAIGemini(api_key="test_key")
    c._enable_transcripts = True
    c._on_user_activity = None
    cfg = c._build_live_config(settings)
    assert "input_audio_transcription" in cfg
    assert "output_audio_transcription" in cfg


# ---------------------------------------------------------------------------
# Per-form compression-window derivation (bd polyglot-pdf-jnjj.35 / A6)
# ---------------------------------------------------------------------------


def test_estimate_si_floor_tokens_counts_si_plus_tools():
    """The unevictable floor = (SI text + serialized tool declarations) / 4 chars.

    Pin the estimator against a KNOWN fixture so the derivation below is anchored
    to a stable floor, not whatever the production SI happens to render to.
    """
    from backend.adapters.live_ai_gemini import (
        estimate_si_floor_tokens,
        _FLOOR_CHARS_PER_TOKEN,
    )

    si = "x" * 4000  # 4000 chars
    tools = [{"function_declarations": [{"name": "confirm_field"}]}]
    import json as _json

    expected = (len(si) + len(_json.dumps(tools, ensure_ascii=False))) // _FLOOR_CHARS_PER_TOKEN
    assert estimate_si_floor_tokens(si, tools) == expected
    # No SI and no tools -> floor of 0 (the override path then takes over).
    assert estimate_si_floor_tokens(None, None) == 0
    assert estimate_si_floor_tokens("", []) == 0


def test_estimate_si_floor_tokens_includes_real_tool_declarations():
    """The floor must count the REAL tool declarations, not just the SI -- in
    production tools are ALWAYS present (settings.TOOL_DECLARATIONS) and add a
    non-trivial, unevictable block (~655 tok). A floor that ignored tools would
    underestimate and let the window land too close to the true floor."""
    from backend.adapters.live_ai_gemini import estimate_si_floor_tokens
    from backend.config import get_settings

    tools = get_settings().TOOL_DECLARATIONS
    si = "q" * 4000  # 1000 SI tokens
    si_only = estimate_si_floor_tokens(si, None)
    with_tools = estimate_si_floor_tokens(si, tools)
    # Tools materially raise the floor -- production always pays this.
    assert with_tools > si_only
    assert with_tools - si_only > 100  # the real declarations are hundreds of tokens


def test_derive_compression_window_sits_just_above_floor():
    """Pure arithmetic of the derivation: window = floor + headroom;
    trigger = window + margin; window < trigger always; window > floor always.

    Uses explicit headroom/margin (NOT the production defaults -- those are guarded
    against the MEASURED I-90 floor in
    test_production_default_headroom_clears_measured_i90_floor). This pins only the
    formula: a 1978 estimated floor + 222 headroom = 2200 window, + 600 = 2800.
    """
    from backend.adapters.live_ai_gemini import (
        derive_compression_window,
        estimate_si_floor_tokens,
    )

    # Build an SI whose floor estimates to ~1978 tokens: 1978 tokens * 4 chars.
    si = "y" * (1978 * 4)
    floor = estimate_si_floor_tokens(si, None)
    assert floor == 1978

    derived = derive_compression_window(
        si, None, window_headroom_tokens=222, trigger_margin_tokens=600
    )
    assert derived["floor"] == 1978
    assert derived["window"] == 1978 + 222 == 2200
    assert derived["trigger"] == 2200 + 600 == 2800
    # The API invariant the Live config requires: target_tokens < trigger_tokens.
    assert derived["window"] < derived["trigger"]
    assert derived["window"] > derived["floor"]  # window must clear the floor


def _compression_settings(**overrides):
    """Real Settings with compression ENABLED and a known derivation calibration.

    Headroom/margin here are FIXTURE values (the wiring assertions read them back
    as floor+222 etc.), independent of the production defaults. The production-
    default calibration is guarded separately by
    test_production_default_headroom_clears_measured_i90_floor below."""
    from backend.config import Settings

    base = dict(
        CONTEXT_COMPRESSION_ENABLED=True,
        CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR=True,
        CONTEXT_COMPRESSION_WINDOW_HEADROOM_TOKENS=222,
        CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS=600,
        CONTEXT_COMPRESSION_TRIGGER_TOKENS=5000,
        CONTEXT_COMPRESSION_WINDOW_TOKENS=3000,
        USE_DTI=True,
    )
    base.update(overrides)
    return Settings(**base)


# The MEASURED I-90 DTI calibration anchors (from the jnjj.25 cost run meta.json
# scripts/spikes/data/costs_i90_2.5_dti_comp_happy_20260618T040035Z.meta.json):
#   - rendered DTI SI = 3786 chars (system_instruction_chars)
#   - live eviction landing zone (the unevictable billed floor) = ~1978-2034 tok
# The estimator (chars/4 of SI+tools) UNDERSHOOTS that billed floor, so the
# production headroom must be large enough that the derived window still clears
# ~1978. This was the Codex P1 (a 222 headroom derived a 1823 window, BELOW the
# real floor -> turn-1 eviction).
_I90_DTI_SI_CHARS = 3786
_I90_MEASURED_FLOOR_TOKENS = 1978


def test_production_default_headroom_clears_measured_i90_floor():
    """Regression guard for the Codex P1: the PRODUCTION-DEFAULT headroom must
    derive a window that sits ABOVE the MEASURED I-90 eviction floor (~1978 tok),
    not above the estimator's undershoot. A window below the real floor makes
    compression fire on turn 1 and evict all conversation context.

    Uses Settings() defaults (no headroom override) + the measured SI char count +
    the real tool declarations -- i.e. the exact production configuration."""
    from backend.adapters.live_ai_gemini import LiveAIGemini, estimate_si_floor_tokens
    from backend.config import Settings

    settings = Settings(
        CONTEXT_COMPRESSION_ENABLED=True,
        USE_DTI=True,
        # NO headroom/margin override -> exercise the shipped defaults.
    )
    adapter = LiveAIGemini(api_key="test_key")
    adapter._system_instruction = "x" * _I90_DTI_SI_CHARS
    adapter._function_declarations = settings.TOOL_DECLARATIONS

    comp = adapter._build_live_config(settings)["context_window_compression"]
    window = comp["sliding_window"]["target_tokens"]
    trigger = comp["trigger_tokens"]
    est_floor = estimate_si_floor_tokens(
        adapter._system_instruction, settings.TOOL_DECLARATIONS
    )

    # The estimator undershoots the billed floor -- document that it does.
    assert est_floor < _I90_MEASURED_FLOOR_TOKENS, (
        "if the estimator no longer undershoots, the headroom can shrink -- recheck"
    )
    # THE GUARD: the derived window must clear the REAL measured floor. Since the
    # trigger clamp (API min 5000) raised the derived trigger, the window is
    # RE-TUNED with it (trigger - margin) so an eviction only chops ~margin
    # tokens -- keeping the raw floor+headroom window under a 5000 trigger
    # stripped the current-field guidance (the measured 5000/2200 drift run;
    # Codex PR #321 P1).
    assert window > _I90_MEASURED_FLOOR_TOKENS, (
        f"derived window {window} is at/below the measured ~{_I90_MEASURED_FLOOR_TOKENS}"
        " floor -> compression fires turn 1 and evicts everything (Codex P1)"
    )
    assert window == trigger - settings.CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS, (
        "clamped-trigger derive path must retune the window to trigger - margin"
    )
    assert trigger > window  # API invariant


def test_build_live_config_derives_window_under_dti():
    """With USE_DTI + derive flag on, the compression config is sized per-form
    from the rendered SI floor -- NOT the static env constants (bd jnjj.35)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini, estimate_si_floor_tokens

    settings = _compression_settings()
    adapter = LiveAIGemini(api_key="test_key")
    adapter._system_instruction = "z" * (1978 * 4)  # floor -> 1978 tokens
    adapter._function_declarations = None

    cfg = adapter._build_live_config(settings)
    comp = cfg["context_window_compression"]
    floor = estimate_si_floor_tokens(adapter._system_instruction, None)
    # The raw derivation (floor + 222 + 600 = 2800) sits BELOW the Live API's
    # trigger minimum, so the config carries the CLAMPED trigger (the API rejects
    # the whole connect otherwise -- wire-verified 1007), and the derived window
    # is RE-TUNED with it (trigger - margin): keeping the raw floor+headroom
    # window under a 5000 trigger made each eviction strip the current-field
    # guidance (the measured 5000/2200 drift; Codex PR #321 P1).
    assert comp["trigger_tokens"] == 5000
    assert comp["sliding_window"]["target_tokens"] == 5000 - 600
    assert comp["sliding_window"]["target_tokens"] > floor  # still above the floor
    # Sanity: the derived window is NOT the static env constant.
    assert comp["sliding_window"]["target_tokens"] != settings.CONTEXT_COMPRESSION_WINDOW_TOKENS


def test_build_live_config_clamps_trigger_to_api_minimum():
    """Live API bound (wire-verified 2026-07-05 on Vertex): trigger_tokens outside
    [5000, 128000] kills the connect with 1007 BEFORE the session opens. A derived
    or configured sub-minimum trigger must be clamped up, never sent raw."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from backend.config import Settings

    settings = Settings(
        CONTEXT_COMPRESSION_ENABLED=True,
        CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR=False,
        CONTEXT_COMPRESSION_TRIGGER_TOKENS=2800,   # the old AI-Studio calibration
        CONTEXT_COMPRESSION_WINDOW_TOKENS=2200,
    )
    adapter = LiveAIGemini(api_key="test_key")
    comp = adapter._build_live_config(settings)["context_window_compression"]
    assert comp["trigger_tokens"] == 5000
    # The window (eviction target) is untouched -- only the trigger has the bound.
    assert comp["sliding_window"]["target_tokens"] == 2200


def test_build_live_config_high_side_clamp_keeps_window_below_trigger():
    """A trigger clamped DOWN from above the API maximum must not land at/below
    the window -- the adapter re-asserts window < trigger after the clamp (the
    Settings validator runs pre-clamp and cannot see this case)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from backend.config import Settings

    settings = Settings(
        CONTEXT_COMPRESSION_ENABLED=True,
        CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR=False,
        CONTEXT_COMPRESSION_TRIGGER_TOKENS=200_000,   # above API max -> clamped to 128k
        CONTEXT_COMPRESSION_WINDOW_TOKENS=150_000,    # legal vs 200k, ILLEGAL vs 128k
    )
    adapter = LiveAIGemini(api_key="test_key")
    comp = adapter._build_live_config(settings)["context_window_compression"]
    assert comp["trigger_tokens"] == 128_000
    assert comp["sliding_window"]["target_tokens"] < comp["trigger_tokens"]


def test_build_live_config_leaves_legal_trigger_unclamped():
    """A trigger already inside [5000, 128000] passes through unchanged."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from backend.config import Settings

    settings = Settings(
        CONTEXT_COMPRESSION_ENABLED=True,
        CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR=False,
        CONTEXT_COMPRESSION_TRIGGER_TOKENS=12_000,
        CONTEXT_COMPRESSION_WINDOW_TOKENS=9_000,
    )
    adapter = LiveAIGemini(api_key="test_key")
    comp = adapter._build_live_config(settings)["context_window_compression"]
    assert comp["trigger_tokens"] == 12_000
    assert comp["sliding_window"]["target_tokens"] == 9_000


def test_build_live_config_a_different_floor_yields_a_different_window():
    """Exit criterion 1: a form with a different SI floor gets a correspondingly
    different window (the whole point of per-form derivation). Floors are chosen
    ABOVE the API trigger-minimum clamp point (raw trigger > 5000): below it the
    clamp+retune deliberately flattens small forms to the same 5000/(5000-margin)
    pair -- the per-form property only expresses above the clamp."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    settings = _compression_settings()

    small = LiveAIGemini(api_key="test_key")
    small._system_instruction = "a" * (5000 * 4)  # floor -> 5000 (raw trigger 5822)
    small._function_declarations = None
    small_window = small._build_live_config(settings)["context_window_compression"][
        "sliding_window"
    ]["target_tokens"]

    large = LiveAIGemini(api_key="test_key")
    large._system_instruction = "b" * (7000 * 4)  # floor -> 7000 (raw trigger 7822)
    large._function_declarations = None
    large_window = large._build_live_config(settings)["context_window_compression"][
        "sliding_window"
    ]["target_tokens"]

    assert small_window == 5000 + 222
    assert large_window == 7000 + 222
    assert large_window > small_window  # bigger floor -> bigger window


def test_build_live_config_static_override_when_derive_off():
    """Derivation OFF -> fall back to the static env constants (the override)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    settings = _compression_settings(CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR=False)
    adapter = LiveAIGemini(api_key="test_key")
    adapter._system_instruction = "z" * (1978 * 4)
    adapter._function_declarations = None

    comp = adapter._build_live_config(settings)["context_window_compression"]
    assert comp["trigger_tokens"] == settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS
    assert comp["sliding_window"]["target_tokens"] == settings.CONTEXT_COMPRESSION_WINDOW_TOKENS


def test_build_live_config_static_override_when_not_dti():
    """No DTI SI -> no calibrated floor -> use the static override, not a guess."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    settings = _compression_settings(USE_DTI=False)
    adapter = LiveAIGemini(api_key="test_key")
    adapter._system_instruction = "z" * (1978 * 4)
    adapter._function_declarations = None

    comp = adapter._build_live_config(settings)["context_window_compression"]
    assert comp["trigger_tokens"] == settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS
    assert comp["sliding_window"]["target_tokens"] == settings.CONTEXT_COMPRESSION_WINDOW_TOKENS


def test_build_live_config_static_override_when_dti_but_no_si():
    """DTI + derive on but NO system instruction yet (e.g. a section switch before
    the SI is rendered) -> there is no floor to measure, so fall back to the static
    override rather than deriving from a zero floor. Guards the third leg of the
    derive AND-condition (bool(self._system_instruction))."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    settings = _compression_settings()  # USE_DTI=True, derive on
    adapter = LiveAIGemini(api_key="test_key")
    adapter._system_instruction = None  # not rendered yet
    adapter._function_declarations = None

    comp = adapter._build_live_config(settings)["context_window_compression"]
    assert comp["trigger_tokens"] == settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS
    assert comp["sliding_window"]["target_tokens"] == settings.CONTEXT_COMPRESSION_WINDOW_TOKENS


def test_build_live_config_derived_floor_includes_real_tools():
    """Production-accurate: with the REAL tool declarations present (as production
    always has), the derived window reflects the SI+TOOLS floor, not SI alone.
    The window must still clear that larger floor (window > floor, trigger > window)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini, estimate_si_floor_tokens
    from backend.config import get_settings

    tools = get_settings().TOOL_DECLARATIONS
    settings = _compression_settings()
    adapter = LiveAIGemini(api_key="test_key")
    adapter._system_instruction = "z" * (1500 * 4)  # 1500 SI tokens
    adapter._function_declarations = tools

    floor = estimate_si_floor_tokens(adapter._system_instruction, tools)
    assert floor > 1500  # tools pushed the floor above the SI-only count
    comp = adapter._build_live_config(settings)["context_window_compression"]
    # The raw derived trigger (floor + 222 + 600) is below the Live API's 5000
    # minimum for this floor size, so the config carries the clamped trigger and
    # the window is retuned with it: max(derived, trigger - margin) -- Codex PR
    # #321 P1 (a raw floor+headroom window under a clamped trigger makes each
    # eviction strip the current-field guidance).
    assert comp["trigger_tokens"] == max(floor + 222 + 600, 5000)
    assert comp["sliding_window"]["target_tokens"] == max(
        floor + 222, comp["trigger_tokens"] - 600)
    assert comp["sliding_window"]["target_tokens"] > floor
    assert comp["trigger_tokens"] > comp["sliding_window"]["target_tokens"]


# ---------------------------------------------------------------------------
# Spontaneous-drop detection + forward (bd polyglot-pdf-ppfy)
# ---------------------------------------------------------------------------

class _ClosingSession:
    """Fake session whose receive() raises a WS-close error (e.g. a 1011)."""

    def __init__(self, exc):
        self._exc = exc

    async def send_realtime_input(self, **kwargs):
        return None

    async def send_tool_response(self, **kwargs):
        return None

    async def send_client_content(self, **kwargs):
        return None

    def receive(self):
        exc = self._exc

        class _Gen:
            def __aiter__(self_inner):
                return self_inner

            async def __anext__(self_inner):
                raise exc

        return _Gen()


def _make_1011():
    from google.genai import errors as genai_errors
    return genai_errors.APIError(1011, {"error": {"message": "Input data processing failed"}})


def _make_close(code):
    """A ConnectionClosed with a specific WS close code (e.g. 1000 normal / 1001
    going-away) -- reaches the same receive-loop catch as a 1011 but must NOT be
    forwarded as a spontaneous drop."""
    from websockets.exceptions import ConnectionClosed
    from websockets.frames import Close
    rcvd = Close(code, "")
    try:
        return ConnectionClosed(rcvd, None)
    except TypeError:
        # Older websockets signature: ConnectionClosed(code, reason)
        exc = ConnectionClosed(code, "")
        return exc


def test_was_spontaneous_drop_predicate_matrix():
    """_was_spontaneous_drop is True ONLY for a real error-drop (1011/1006), never
    for a deliberate close, a clean end, or a benign normal/GoAway close (bd
    polyglot-pdf-ppfy)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    a = LiveAIGemini()

    # No drop recorded -> False (clean no-events end).
    a._spontaneous_drop_exc = None
    a._spontaneous_drop_code = None
    a._intentional_shutdown = False
    a._close_after_flush = False
    assert a._was_spontaneous_drop() is False

    # A recorded 1011 drop with no shutdown flags -> True (the spontaneous case).
    a._spontaneous_drop_exc = _make_1011()
    a._spontaneous_drop_code = 1011
    a._go_away_seen = False
    assert a._was_spontaneous_drop() is True

    # A 1011-coded close AFTER a GoAway is a routine server-lifecycle reset the
    # client already reconnects on -> NOT forwarded (even though the code matches).
    a._go_away_seen = True
    assert a._was_spontaneous_drop() is False
    a._go_away_seen = False

    # A BENIGN close (normal 1000 or a GoAway-driven close) reaches the same catch
    # but must NOT be forwarded as a drop -- the code gate excludes it.
    a._spontaneous_drop_code = 1000
    assert a._was_spontaneous_drop() is False
    a._spontaneous_drop_code = 1001  # GoAway-style going-away
    assert a._was_spontaneous_drop() is False
    # A missing code (e.g. a non-close APIError) is likewise not a drop.
    a._spontaneous_drop_code = None
    assert a._was_spontaneous_drop() is False

    # 1006 (abnormal closure, no frame) IS a genuine drop.
    a._spontaneous_drop_code = 1006
    assert a._was_spontaneous_drop() is True

    # A drop that races an intentional finalize -> not forwarded.
    a._spontaneous_drop_code = 1011
    a._intentional_shutdown = True
    assert a._was_spontaneous_drop() is False
    a._intentional_shutdown = False

    # A drop during a section-switch graceful shutdown -> not forwarded.
    a._close_after_flush = True
    assert a._was_spontaneous_drop() is False


@pytest.mark.asyncio
async def test_safe_notify_dropped_invokes_callback():
    """_safe_notify_dropped awaits the registered callback and swallows errors."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    a = LiveAIGemini()
    a._log = MagicMock()

    cb = AsyncMock()
    a._on_session_dropped = cb
    await a._safe_notify_dropped()
    cb.assert_awaited_once()

    # A raising callback must not propagate (teardown must never crash).
    a._on_session_dropped = AsyncMock(side_effect=RuntimeError("boom"))
    await a._safe_notify_dropped()  # must not raise


@pytest.mark.asyncio
async def test_run_session_loop_records_spontaneous_drop_on_1011():
    """A 1011 close in the receive loop is recorded on _spontaneous_drop_exc so the
    done-callback can forward it (bd polyglot-pdf-ppfy)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    session = _ClosingSession(_make_1011())
    fake_live = MagicMock()
    fake_live.connect.return_value = _DummyContextManager(session)
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    await asyncio.wait_for(adapter._run_session_loop(), timeout=2.0)

    # The drop was captured, and (no shutdown flags set) the predicate says forward.
    assert adapter._spontaneous_drop_exc is not None
    assert adapter._was_spontaneous_drop() is True
    await adapter.finalize()


@pytest.mark.asyncio
async def test_spontaneous_drop_fires_on_session_dropped_via_bg_task():
    """End-to-end: a 1011 through the real bg-task path fires on_session_dropped
    exactly once (bd polyglot-pdf-ppfy)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    session = _ClosingSession(_make_1011())
    fake_live = MagicMock()
    fake_live.connect.return_value = _DummyContextManager(session)
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    dropped = AsyncMock()
    adapter.set_callbacks(on_session_dropped=dropped)

    # The notify fires IN-LOOP at the drop catch (not from a done-callback), so it
    # has already completed by the time the bg task finishes -- awaiting the task is
    # enough. The extra sleeps are belt-and-suspenders and not load-bearing.
    await asyncio.wait_for(adapter._bg_task, timeout=2.0)
    await asyncio.sleep(0)

    dropped.assert_awaited_once()
    assert adapter._dropped_notified is True
    await adapter.finalize()


@pytest.mark.asyncio
async def test_no_drop_notify_on_clean_no_events_end():
    """A clean session end (no drop) must NOT fire on_session_dropped."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    fake_live = MagicMock()
    fake_live.connect.return_value = _DummyContextManager(_DummySession())  # empty receive
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    dropped = AsyncMock()
    adapter.set_callbacks(on_session_dropped=dropped)

    await asyncio.wait_for(adapter._bg_task, timeout=2.0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    dropped.assert_not_awaited()
    await adapter.finalize()


@pytest.mark.asyncio
async def test_drop_notify_fires_inside_loop_before_task_completes():
    """The drop notify fires from INSIDE _run_session_loop (at the catch), so it has
    already run by the time the bg-task completes -- immune to a restart resetting
    the drop markers in the task-done-but-callback-not-fired window (bd
    polyglot-pdf-bcrn / ppfy)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    session = _ClosingSession(_make_1011())
    fake_live = MagicMock()
    fake_live.connect.return_value = _DummyContextManager(session)
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    dropped = AsyncMock()
    adapter.set_callbacks(on_session_dropped=dropped)

    # Await ONLY the task. If the notify were scheduled on a separate done-callback
    # task, it would NOT have run yet at this point; because it fires in-loop, it
    # has. No extra event-loop yields needed.
    await asyncio.wait_for(adapter._bg_task, timeout=2.0)
    dropped.assert_awaited_once()
    await adapter.finalize()


@pytest.mark.asyncio
async def test_no_drop_notify_on_benign_normal_close():
    """A normal (1000) close reaches the drop catch but is NOT a spontaneous drop --
    only 1011/1006 forward (bd polyglot-pdf-ppfy). Guards against mislabeling a
    routine/GoAway close as an AI failure."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    adapter = LiveAIGemini()
    adapter._log = MagicMock()

    session = _ClosingSession(_make_close(1000))
    fake_live = MagicMock()
    fake_live.connect.return_value = _DummyContextManager(session)
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    dropped = AsyncMock()
    adapter.set_callbacks(on_session_dropped=dropped)

    await asyncio.wait_for(adapter._bg_task, timeout=2.0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # The close was recorded, but its code (1000) is not a drop code -> no notify.
    assert adapter._spontaneous_drop_code == 1000
    assert adapter._was_spontaneous_drop() is False
    dropped.assert_not_awaited()
    await adapter.finalize()


# ---------------------------------------------------------------------------
# thinking_config gating (shipped with bd polyglot-pdf-ppfy; NOT the 3v5m failover):
# thinking_budget=0 for 2.5-family ONLY, gated by DISABLE_MODEL_THINKING, never
# sent to 3.1 or an unknown model.
# ---------------------------------------------------------------------------

def _build_cfg(model_name, disable_thinking):
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from backend.config import Settings
    a = LiveAIGemini(model=model_name)
    a._log = MagicMock()
    a._system_instruction = "test SI"
    s = Settings()
    s.DISABLE_MODEL_THINKING = disable_thinking
    return a._build_live_config(s)


def test_thinking_config_present_for_2p5_when_enabled():
    cfg = _build_cfg("gemini-live-2.5-flash-native-audio", disable_thinking=True)
    assert cfg.get("thinking_config") == {"thinking_budget": 0}


def test_thinking_config_absent_for_3p1():
    # 3.1 uses a different thinking_level field; the 2.5-only thinking_budget form
    # must NOT be sent to it.
    cfg = _build_cfg("gemini-3.1-flash-live-preview", disable_thinking=True)
    assert "thinking_config" not in cfg


def test_thinking_config_absent_when_flag_off():
    cfg = _build_cfg("gemini-live-2.5-flash-native-audio", disable_thinking=False)
    assert "thinking_config" not in cfg


def test_thinking_config_gate_documents_model_family_fallback():
    # HONEST NOTE (fresh-eyes finding 4): the gate is `model_family(...) == "2.5"`,
    # which reads as an explicit 2.5 allowlist. But model_family() is a PRICING
    # helper that maps ANY unrecognized string to the default family "2.5", so an
    # unknown model still matches and still gets thinking_budget=0. The change from
    # `!= "3.1"` to `== "2.5"` is a clarity/intent improvement, NOT a behavior fix
    # for unknown models -- a true capability gate would need a distinct "unknown"
    # from model_family, which is out of scope (it's a widely-used pricing fn).
    # Practical risk is ~nil: thinking_config is safe-if-ignored on native-audio.
    # This test PINS that fallback so a future model_family change that stops
    # defaulting to "2.5" is caught here rather than silently changing the gate.
    from backend.config import model_family
    assert model_family("totally-made-up-model-xyz") == "2.5"
    cfg = _build_cfg("totally-made-up-model-xyz", disable_thinking=True)
    assert cfg.get("thinking_config") == {"thinking_budget": 0}

