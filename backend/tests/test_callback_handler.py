"""
Tests for CallbackHandler - Gemini Live AI callback routing.

Tests cover:
- Callback registration and delegation
- Tool routing (update_form_fields, get_form_status, switch_section, get_field_value, confirm_field)
- Argument parsing and normalization
- Error response building
- Form update coordination
"""

import base64
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from fastapi import WebSocket

from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import HINT_REQUEST_TIMEOUT, RequestCoordinator


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    ws = MagicMock(spec=WebSocket)
    # Make async methods return awaitable values
    ws.send_json = AsyncMock()
    ws.send_bytes = AsyncMock()
    return ws


@pytest.fixture
def mock_coordinator():
    """Create a mock RequestCoordinator."""
    coordinator = MagicMock(spec=RequestCoordinator)
    coordinator.request_form_state = AsyncMock()
    coordinator.request_next_field_hint = AsyncMock()
    coordinator.request_field_value = AsyncMock()
    coordinator.request_section_info = AsyncMock()
    # confirm_field is a synchronous round-trip (bd polyglot-pdf-wpw.2): the FE acks
    # whether it recorded the confirmation. Default to recorded so the existing
    # next-hint tests exercise the recorded path explicitly (not via an implicit
    # truthy AsyncMock).
    coordinator.request_confirm_field = AsyncMock(
        return_value={"recorded": True, "reason": None}
    )
    return coordinator


@pytest.fixture
def mock_handlers():
    """Create mock tool handler functions."""
    return {
        "update_fields": MagicMock(return_value={
            "form_state": {},
            "applied_fields": ["name"],
            "unknown_fields": [],
            "validation_errors": []
        }),
        "switch_section": AsyncMock(return_value={"success": True}),
        "get_field_value": AsyncMock(return_value={"found": True, "value": "test"}),
        "request_form_state": AsyncMock(return_value={}),
        "get_next_field_schema": MagicMock(return_value={
            "id": "next_field",
            "spoken_name": "Next Field"
        })
    }


@pytest.fixture
def callback_handler(mock_websocket, mock_coordinator, mock_handlers):
    """Create a CallbackHandler instance for testing."""
    handler = CallbackHandler(
        websocket=mock_websocket,
        request_coordinator=mock_coordinator,
        session_id="test-session-123"
    )
    
    # Inject tool handlers
    handler.set_tool_handlers(
        handle_update_fields=mock_handlers["update_fields"],
        handle_switch_section=mock_handlers["switch_section"],
        handle_get_field_value=mock_handlers["get_field_value"],
        request_form_state_from_client=mock_handlers["request_form_state"],
        get_next_field_schema_for_jit=mock_handlers["get_next_field_schema"],
    )
    
    return handler


class TestCallbackRegistration:
    """Test callback registration and basic delegation."""

    def test_initialization(self, callback_handler, mock_websocket, mock_coordinator):
        """Test that handler is initialized with correct dependencies."""
        assert callback_handler._websocket == mock_websocket
        assert callback_handler._request_coordinator == mock_coordinator
        assert callback_handler._session_id == "test-session-123"

    def test_set_tool_handlers(self, mock_websocket, mock_coordinator):
        """Test that tool handlers can be registered."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            request_coordinator=mock_coordinator,
            session_id="test-123"
        )
        
        update_handler = MagicMock()
        switch_handler = AsyncMock()
        get_value_handler = AsyncMock()
        request_state_handler = AsyncMock()

        handler.set_tool_handlers(
            handle_update_fields=update_handler,
            handle_switch_section=switch_handler,
            handle_get_field_value=get_value_handler,
            request_form_state_from_client=request_state_handler,
            get_next_field_schema_for_jit=MagicMock(return_value=None),
        )

        assert handler._handle_update_fields == update_handler
        assert handler._handle_switch_section == switch_handler
        assert handler._handle_get_field_value == get_value_handler
        assert handler._request_form_state_from_client == request_state_handler

    # Note: on_form_update, on_transcript, on_audio, and send_form_update
    # have complex async coordination with WebSocket and coordinator.
    # These are integration-tested via the full service tests.
    # Tool routing tests (below) cover the main callback functionality.


class TestToolRouting:
    """Test tool call routing to appropriate handlers."""

    @pytest.mark.asyncio
    async def test_update_form_fields_routes_to_handler(self, callback_handler, mock_handlers):
        """Test that update_form_fields tool routes correctly with new single-field format."""
        await callback_handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"field_id": "name", "value": "John"}
        )
        
        mock_handlers["update_fields"].assert_called_once()

    @pytest.mark.asyncio
    async def test_get_form_status_routes_to_handler(self, callback_handler, mock_handlers):
        """Test that get_form_status tool routes correctly."""
        result = await callback_handler.on_tool_call(
            tool_name="get_form_status",
            arguments={"field_ids": []}
        )
        
        mock_handlers["request_form_state"].assert_called_once()
        # Response is the ultra-compact format under "state" (was "field_values")
        assert "state" in result

    @pytest.mark.asyncio
    async def test_switch_section_uses_handler(self, callback_handler, mock_handlers):
        """Test that switch_section requests section info via handler."""
        result = await callback_handler.on_tool_call(
            tool_name="switch_section",
            arguments={"section_identifier": "Personal Info"}
        )
        
        mock_handlers["switch_section"].assert_called_once_with("Personal Info")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_get_field_value_uses_handler(self, callback_handler, mock_handlers):
        """Test that get_field_value requests field value via handler."""
        result = await callback_handler.on_tool_call(
            tool_name="get_field_value",
            arguments={"spoken_name": "name"}
        )
        
        mock_handlers["get_field_value"].assert_called_once_with("name")
        assert result["found"] is True

    # NOTE: the `complete_section` tool was removed (section completion is now
    # auto-detected by the frontend when all fields are confirmed). Its routing
    # and handler are gone, so a `complete_section` call falls through to the
    # unknown-tool path -- covered by test_unknown_tool_returns_empty_dict below.

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_empty_dict(self, callback_handler):
        """Test that unknown tool names return empty dict."""
        result = await callback_handler.on_tool_call(
            tool_name="unknown_tool",
            arguments={}
        )
        
        assert result == {}


class TestArgumentParsing:
    """Test argument parsing and normalization."""

    @pytest.mark.asyncio
    async def test_parse_update_arguments_handles_dict(self, callback_handler, mock_handlers):
        """Test parsing single update with new single-field format."""
        await callback_handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"field_id": "email", "value": "test@example.com"}
        )
        
        # Handler should have been called with parsed args
        assert mock_handlers["update_fields"].call_count == 1

    @pytest.mark.asyncio
    async def test_parse_update_handles_empty_updates(self, callback_handler, mock_handlers):
        """Test handling empty updates returns error message."""
        result = await callback_handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"updates": {}}
        )
        
        # Empty updates should return error response
        assert result["success"] is False
        assert "message" in result
        assert "empty" in result["message"].lower()

    def test_normalize_updates_unwraps_nested_values(self, callback_handler):
        """Test that normalization unwraps nested value objects."""
        # Test the helper method directly
        updates = callback_handler._normalize_updates({
            "name": {"value": "John"},
            "age": 30  # Should pass through
        })
        
        assert updates["name"] == "John"
        assert updates["age"] == 30


class TestErrorHandling:
    """Test error response building and handling."""

    @pytest.mark.asyncio
    async def test_null_session_returns_none(self, mock_websocket, mock_coordinator, mock_handlers):
        """Test that tool calls with null session return None."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            request_coordinator=mock_coordinator,
            session_id=None  # No session
        )
        
        result = await handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={}
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_websocket_exception_is_handled(self, callback_handler, mock_websocket):
        """Test that WebSocket exceptions are handled gracefully."""
        mock_websocket.send_json.side_effect = RuntimeError("Connection lost")
        
        # Should not raise exception
        try:
            await callback_handler.on_form_update({"type": "test"})
        except RuntimeError:
            pytest.fail("WebSocket exception should be handled gracefully")


class TestFormUpdateCoordination:
    """Test send_form_update method and coordinator integration."""

    # Note: send_form_update is integration-tested via full service tests
    # as it requires complex async coordination between WebSocket and coordinator.
    pass


class TestConfirmFieldNextHint:
    """confirm_field must distinguish timeout from genuine completion.

    bd polyglot-pdf-tks: request_next_field_hint() returns a hint string,
    None (form genuinely complete), or HINT_REQUEST_TIMEOUT (frontend did not
    answer in 2s). A timeout previously collapsed to None and made the tool
    response say "All fields confirmed.", so a slow round-trip made Gemini wrap
    the form up early. These tests pin all three outcomes.
    """

    @pytest.mark.asyncio
    async def test_confirm_field_with_next_hint(self, callback_handler, mock_coordinator):
        mock_coordinator.request_next_field_hint.return_value = "Next field: email"

        response = await callback_handler.on_tool_call(
            "confirm_field", {"field_id": "name", "confirmation_method": "verbal"}
        )

        assert response["success"] is True
        assert response["next_field_hint"] == "Next field: email"
        assert "All fields confirmed" not in response["message"]

    @pytest.mark.asyncio
    async def test_confirm_field_form_complete(self, callback_handler, mock_coordinator):
        # Genuine completion: frontend answered with None.
        mock_coordinator.request_next_field_hint.return_value = None

        response = await callback_handler.on_tool_call(
            "confirm_field", {"field_id": "name", "confirmation_method": "verbal"}
        )

        assert response["next_field_hint"] is None
        assert "All fields confirmed" in response["message"]

    @pytest.mark.asyncio
    async def test_confirm_field_hint_timeout_does_not_claim_complete(
        self, callback_handler, mock_coordinator
    ):
        # Frontend did not answer in time.
        mock_coordinator.request_next_field_hint.return_value = HINT_REQUEST_TIMEOUT

        response = await callback_handler.on_tool_call(
            "confirm_field", {"field_id": "name", "confirmation_method": "verbal"}
        )

        # The sentinel must never reach the wire (it is not JSON-serializable
        # in a meaningful way); it collapses to None for next_field_hint.
        assert response["next_field_hint"] is None
        # ...but the message must NOT claim completion, and must steer Gemini to
        # keep going rather than wrap up.
        assert "All fields confirmed" not in response["message"]
        assert "do NOT assume the form is complete" in response["message"]


class TestGoAway:
    """on_go_away forwards a Live GoAway to the client (bd polyglot-pdf-c5t)."""

    @pytest.mark.asyncio
    async def test_on_go_away_forwards_ws_message_with_time_left(
        self, callback_handler, mock_websocket
    ):
        await callback_handler.on_go_away("3.5s")
        mock_websocket.send_json.assert_awaited_once_with(
            {"type": "go_away", "time_left": "3.5s"}
        )

    @pytest.mark.asyncio
    async def test_on_go_away_forwards_none_time_left(
        self, callback_handler, mock_websocket
    ):
        # The SDK field is Optional[str]; a missing time_left still forwards so the
        # client at least learns a GoAway arrived.
        await callback_handler.on_go_away(None)
        mock_websocket.send_json.assert_awaited_once_with(
            {"type": "go_away", "time_left": None}
        )

    @pytest.mark.asyncio
    async def test_on_go_away_swallows_send_failure(
        self, callback_handler, mock_websocket
    ):
        # A WS send failure must never crash the session loop (same discipline as
        # on_audio / on_transcript).
        mock_websocket.send_json.side_effect = RuntimeError("ws closed")
        await callback_handler.on_go_away("1s")  # must not raise

    @pytest.mark.asyncio
    async def test_on_go_away_noop_without_websocket(self, mock_coordinator):
        # No websocket -> nothing sent, no crash.
        handler = CallbackHandler(
            websocket=None,
            request_coordinator=mock_coordinator,
            session_id="test-123",
        )
        await handler.on_go_away("2s")  # must not raise


class TestAskSecretaryRouting:
    """ask_secretary tool routing + fail-open (bd polyglot-pdf-jnjj.45c)."""

    @pytest.mark.asyncio
    async def test_ask_secretary_routes_to_handler(
        self, mock_websocket, mock_coordinator
    ):
        """on_tool_call routes ask_secretary to the injected handler and returns
        the secretary's prose answer."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            request_coordinator=mock_coordinator,
            session_id="test-123",
        )
        # The handler returns a status dict (bd jnjj.43): ok / pending / failed.
        ask = AsyncMock(return_value={"status": "ok", "answer": "Their first name is Ada."})
        handler.set_tool_handlers(
            handle_update_fields=MagicMock(),
            handle_switch_section=AsyncMock(),
            handle_get_field_value=AsyncMock(),
            request_form_state_from_client=AsyncMock(return_value={}),
            get_next_field_schema_for_jit=MagicMock(),
            handle_ask_secretary=ask,
        )

        result = await handler.on_tool_call(
            tool_name="ask_secretary",
            arguments={"query": "what is their first name?"},
        )

        ask.assert_awaited_once_with("what is their first name?")
        assert result["answer"] == "Their first name is Ada."
        assert result["available"] is True

    @pytest.mark.asyncio
    async def test_ask_secretary_pending_returns_wait_instruction(
        self, mock_websocket, mock_coordinator
    ):
        """A pending status (lookup blew the deadline; answer delivered async, bd
        jnjj.43) yields a WAIT instruction with available=True -- NOT an apology and
        NOT a re-ask. The model is told the answer is coming as a follow-up."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            request_coordinator=mock_coordinator,
            session_id="test-123",
        )
        handler.set_tool_handlers(
            handle_update_fields=MagicMock(),
            handle_switch_section=AsyncMock(),
            handle_get_field_value=AsyncMock(),
            request_form_state_from_client=AsyncMock(return_value={}),
            get_next_field_schema_for_jit=MagicMock(),
            handle_ask_secretary=AsyncMock(return_value={"status": "pending", "answer": ""}),
        )

        result = await handler.on_tool_call(
            tool_name="ask_secretary", arguments={"query": "q"}
        )
        # Pending is NOT a failure: available stays True (no apology).
        assert result["available"] is True
        answer = result["answer"].lower()
        assert "apolog" not in answer  # NOT the failure path
        # Must steer the model to wait for the follow-up, not answer or re-ask now.
        assert "do not answer the question yet" in answer
        assert "do not repeat" in answer

    @pytest.mark.asyncio
    async def test_ask_secretary_fail_open_on_empty_answer(
        self, mock_websocket, mock_coordinator
    ):
        """An empty answer (timeout/error inside the handler) yields the fail-open
        APOLOGY instruction with available=False -- and explicitly does NOT tell
        the model to repeat the question back (the knock-knock anti-pattern)."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            request_coordinator=mock_coordinator,
            session_id="test-123",
        )
        handler.set_tool_handlers(
            handle_update_fields=MagicMock(),
            handle_switch_section=AsyncMock(),
            handle_get_field_value=AsyncMock(),
            request_form_state_from_client=AsyncMock(return_value={}),
            get_next_field_schema_for_jit=MagicMock(),
            handle_ask_secretary=AsyncMock(return_value={"status": "failed", "answer": ""}),
        )

        result = await handler.on_tool_call(
            tool_name="ask_secretary", arguments={"query": "q"}
        )
        assert result["available"] is False
        answer = result["answer"].lower()
        # The instruction must steer toward an apology for an internal error...
        assert "apolog" in answer
        assert "internal error" in answer
        # ...and must NOT tell the model to just repeat the question back.
        assert "repeat their question" in answer  # the explicit DO-NOT clause

    @pytest.mark.asyncio
    async def test_ask_secretary_fail_open_without_handler(
        self, callback_handler
    ):
        """The default fixture wires NO ask_secretary handler -> fail-open with the
        SAME apology instruction (not a re-ask)."""
        result = await callback_handler.on_tool_call(
            tool_name="ask_secretary", arguments={"query": "q"}
        )
        assert result["available"] is False
        answer = result["answer"].lower()
        assert "apolog" in answer and "repeat their question" in answer

    @pytest.mark.asyncio
    async def test_ask_secretary_swallows_handler_exception(
        self, mock_websocket, mock_coordinator
    ):
        """A handler that raises must not crash the tool-call path -> fail-open,
        and logs EXACTLY ONE ERROR for the failure (not a doubled error-rate from
        the except block + the empty-answer branch both firing; fresh-eyes
        finding). Patches the module logger's .error directly rather than using
        structlog.capture_logs -- the latter is sensitive to global structlog
        config that other suite tests mutate, making it flaky under full-suite
        ordering (it captured nothing)."""
        from unittest.mock import patch as _patch
        import backend.services.callback_handler as cbh

        handler = CallbackHandler(
            websocket=mock_websocket,
            request_coordinator=mock_coordinator,
            session_id="test-123",
        )
        handler.set_tool_handlers(
            handle_update_fields=MagicMock(),
            handle_switch_section=AsyncMock(),
            handle_get_field_value=AsyncMock(),
            request_form_state_from_client=AsyncMock(return_value={}),
            get_next_field_schema_for_jit=MagicMock(),
            handle_ask_secretary=AsyncMock(side_effect=RuntimeError("boom")),
        )
        with _patch.object(cbh._log, "error") as mock_error:
            result = await handler.on_tool_call(
                tool_name="ask_secretary", arguments={"query": "q"}
            )
        assert result["available"] is False
        # Exactly ONE ask_secretary* ERROR for the single failure -- the
        # handler-error log -- NOT a second ask_secretary_failed for the same event.
        ask_errors = [c for c in mock_error.call_args_list
                      if c.args and str(c.args[0]).startswith("ask_secretary")]
        assert len(ask_errors) == 1, ask_errors
        assert ask_errors[0].args[0] == "ask_secretary_handler_error"


def _processing_sends(ws):
    """All agent_processing messages sent on a mock websocket, in order."""
    return [
        c.args[0] for c in ws.send_json.await_args_list
        if c.args and isinstance(c.args[0], dict)
        and c.args[0].get("type") == "agent_processing"
    ]


class TestThinkingIndicator:
    """agent_processing signal for the thinking indicator (bd polyglot-pdf-wpw.5)."""

    @pytest.mark.asyncio
    async def test_on_user_activity_emits_processing_true_and_chains_inner(
        self, mock_websocket, mock_coordinator
    ):
        """A user turn (on_user_activity) emits agent_processing:true AND calls the
        injected liveness inner callback (the idle-watchdog bump)."""
        handler = CallbackHandler(
            websocket=mock_websocket, request_coordinator=mock_coordinator,
            session_id="t",
        )
        bumped = []
        handler.set_user_activity_inner(lambda: bumped.append(1))

        await handler.on_user_activity()

        assert _processing_sends(mock_websocket) == [
            {"type": "agent_processing", "processing": True}
        ]
        assert bumped == [1]  # inner liveness callback chained through

    @pytest.mark.asyncio
    async def test_signal_processing_start_emits_without_liveness_chain(
        self, mock_websocket, mock_coordinator
    ):
        """The manual/PTT path (signal_processing_start) emits processing:true but
        does NOT call the liveness inner callback (that path handles liveness
        separately) -- bd polyglot-pdf-wpw.5."""
        handler = CallbackHandler(
            websocket=mock_websocket, request_coordinator=mock_coordinator,
            session_id="t",
        )
        bumped = []
        handler.set_user_activity_inner(lambda: bumped.append(1))

        await handler.signal_processing_start()

        assert _processing_sends(mock_websocket) == [
            {"type": "agent_processing", "processing": True}
        ]
        assert bumped == []  # liveness NOT chained on this path

    @pytest.mark.asyncio
    async def test_on_processing_done_clears_processing(
        self, mock_websocket, mock_coordinator
    ):
        """on_processing_done (fired on a barge-in OR a real server turn_complete --
        NOT tied to output transcripts, which are off in prod) clears the processing
        state, and a NEXT turn's processing:true is sent again, not deduped to nothing
        (bd polyglot-pdf-wpw.5, Codex PR #273)."""
        handler = CallbackHandler(
            websocket=mock_websocket, request_coordinator=mock_coordinator,
            session_id="t",
        )
        await handler.signal_processing_start()   # processing -> True
        await handler.on_processing_done()        # turn-end -> processing False
        await handler.signal_processing_start()   # next turn -> True again (not deduped)

        assert _processing_sends(mock_websocket) == [
            {"type": "agent_processing", "processing": True},
            {"type": "agent_processing", "processing": False},
            {"type": "agent_processing", "processing": True},
        ]

    @pytest.mark.asyncio
    async def test_on_user_activity_awaits_async_inner(
        self, mock_websocket, mock_coordinator
    ):
        """An ASYNC inner liveness callback (the real WS-route one is async) is awaited."""
        handler = CallbackHandler(
            websocket=mock_websocket, request_coordinator=mock_coordinator,
            session_id="t",
        )
        bumped = []
        async def _inner():
            bumped.append(1)
        handler.set_user_activity_inner(_inner)

        await handler.on_user_activity()
        assert bumped == [1]

    @pytest.mark.asyncio
    async def test_first_audio_clears_processing(
        self, mock_websocket, mock_coordinator
    ):
        """The first response audio after a user turn emits agent_processing:false;
        subsequent chunks do NOT re-emit (dedup)."""
        handler = CallbackHandler(
            websocket=mock_websocket, request_coordinator=mock_coordinator,
            session_id="t",
        )
        await handler.on_user_activity()          # processing -> True
        await handler.on_audio(b"\x00\x01")       # first chunk -> processing False
        await handler.on_audio(b"\x02\x03")       # later chunk -> no re-emit

        assert _processing_sends(mock_websocket) == [
            {"type": "agent_processing", "processing": True},
            {"type": "agent_processing", "processing": False},
        ]

    @pytest.mark.asyncio
    async def test_turn_complete_clears_processing_when_no_audio(
        self, mock_websocket, mock_coordinator
    ):
        """A text-only turn (no audio) still clears processing on turn_complete
        (on_transcript), so the indicator can never stick on."""
        handler = CallbackHandler(
            websocket=mock_websocket, request_coordinator=mock_coordinator,
            session_id="t",
        )
        await handler.on_user_activity()   # processing -> True
        await handler.on_transcript("done")  # turn_complete -> processing False

        sends = _processing_sends(mock_websocket)
        assert {"type": "agent_processing", "processing": False} in sends
        assert sends[-1] == {"type": "agent_processing", "processing": False}

    @pytest.mark.asyncio
    async def test_audio_without_active_processing_does_not_emit(
        self, mock_websocket, mock_coordinator
    ):
        """Audio with no preceding user turn (processing not active) emits nothing --
        no spurious agent_processing:false."""
        handler = CallbackHandler(
            websocket=mock_websocket, request_coordinator=mock_coordinator,
            session_id="t",
        )
        await handler.on_audio(b"\x00\x01")
        assert _processing_sends(mock_websocket) == []

    @pytest.mark.asyncio
    async def test_no_inner_callback_is_safe(
        self, mock_websocket, mock_coordinator
    ):
        """on_user_activity with no inner liveness callback wired still emits the
        signal and does not crash."""
        handler = CallbackHandler(
            websocket=mock_websocket, request_coordinator=mock_coordinator,
            session_id="t",
        )
        await handler.on_user_activity()  # no set_user_activity_inner
        assert _processing_sends(mock_websocket) == [
            {"type": "agent_processing", "processing": True}
        ]
