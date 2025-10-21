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

    # Pre-create the audio queue to satisfy the sender loop
    adapter._audio_queue = asyncio.Queue()

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

    await asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    assert ctx.entered is True
    assert fake_live.connect.call_count == 1
    _, kwargs = fake_live.connect.call_args
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

    logger.error.assert_called_once()
    error_call = logger.error.call_args
    assert error_call.args and error_call.args[0] == "session_loop_error"
    assert "error" in error_call.kwargs
    assert error_call.kwargs["error"] == "boom"
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
async def test_heartbeat_sends_silence_periodically():
    """Test that heartbeat task sends silence packets at regular intervals."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    from unittest.mock import patch, MagicMock
    import time
    
    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()
    
    audio_inputs = []
    
    class _TrackingSession:
        def __init__(self):
            self.event_count = 0
            
        async def send_realtime_input(self, **kwargs):
            audio_inputs.append((time.time(), kwargs))
        
        async def send_client_content(self, **kwargs):
            pass
        
        async def send_tool_response(self, **kwargs):
            pass
        
        def receive(self):
            # Create a generator that yields events for 35 seconds, then stops
            async def gen():
                start = time.time()
                while time.time() - start < 35:
                    await asyncio.sleep(1)
                    self.event_count += 1
                    # Yield a dummy event to keep the loop running
                    yield SimpleNamespace(text="dummy")
            return gen()
    
    session = _TrackingSession()
    ctx = _DummyContextManager(session)
    
    fake_live = MagicMock()
    fake_live.connect.return_value = ctx
    
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))
    
    # Run the session loop
    start_time = time.time()
    await asyncio.wait_for(adapter._run_session_loop(), timeout=40.0)
    elapsed = time.time() - start_time
    
    # Filter for heartbeat packets (320 bytes of silence)
    heartbeats = [(t, inp) for t, inp in audio_inputs 
                  if 'audio' in inp 
                  and hasattr(inp['audio'], 'data')
                  and len(inp['audio'].data) == 320 
                  and inp['audio'].data == bytes(320)]
    
    # In 35 seconds, we should get at least 1 heartbeat (at 30s mark)
    assert len(heartbeats) >= 1, f"Expected at least 1 heartbeat in {elapsed:.1f}s, got {len(heartbeats)}"
    
    # Verify heartbeats are sent at ~30 second intervals
    if len(heartbeats) >= 2:
        time_diff = heartbeats[1][0] - heartbeats[0][0]
        assert 28 <= time_diff <= 32, f"Expected ~30s between heartbeats, got {time_diff:.1f}s"
    
    # Clean up
    await adapter.finalize()


@pytest.mark.asyncio
async def test_heartbeat_cleanup_on_session_end():
    """Test that heartbeat task is properly cancelled when session ends."""
    from backend.adapters.live_ai_gemini import LiveAIGemini
    
    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()
    
    audio_inputs = []
    
    class _QuickSession:
        async def send_realtime_input(self, **kwargs):
            audio_inputs.append(kwargs)
        
        async def send_client_content(self, **kwargs):
            pass
        
        async def send_tool_response(self, **kwargs):
            pass
        
        def receive(self):
            # End immediately with empty iterator
            async def gen():
                # Yield nothing - session ends immediately
                if False:
                    yield
            return gen()
    
    session = _QuickSession()
    ctx = _DummyContextManager(session)
    
    fake_live = MagicMock()
    fake_live.connect.return_value = ctx
    
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))
    
    # Run the session loop (should complete quickly)
    await asyncio.wait_for(adapter._run_session_loop(), timeout=5.0)
    
    # Wait to ensure heartbeat task would have fired if not cancelled
    await asyncio.sleep(2)
    
    # Count heartbeat packets
    heartbeat_count = sum(1 for inp in audio_inputs 
                         if 'audio' in inp 
                         and hasattr(inp.get('audio'), 'data')
                         and len(inp['audio'].data) == 320 
                         and inp['audio'].data == bytes(320))
    
    # Session ended immediately, so no heartbeats should have been sent
    assert heartbeat_count == 0, f"Expected 0 heartbeats after quick session end, got {heartbeat_count}"
    
    # Clean up
    await adapter.finalize()
