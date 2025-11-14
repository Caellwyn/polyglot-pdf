"""
Tests for CallbackHandler - Gemini Live AI callback routing.

Tests cover:
- Callback registration and delegation
- Tool routing (update_form_fields, get_form_status, switch_section, get_field_value, complete_section)
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
from backend.services.request_coordinator import RequestCoordinator


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
        "complete_section": AsyncMock(return_value={"success": True}),
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
        handle_complete_section=mock_handlers["complete_section"],
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
        complete_handler = AsyncMock()
        request_state_handler = AsyncMock()
        
        handler.set_tool_handlers(
            handle_update_fields=update_handler,
            handle_switch_section=switch_handler,
            handle_get_field_value=get_value_handler,
            handle_complete_section=complete_handler,
            request_form_state_from_client=request_state_handler,
            get_next_field_schema_for_jit=MagicMock(return_value=None),
        )
        
        assert handler._handle_update_fields == update_handler
        assert handler._handle_switch_section == switch_handler
        assert handler._handle_get_field_value == get_value_handler
        assert handler._handle_complete_section == complete_handler
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
        assert "field_values" in result

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

    @pytest.mark.asyncio
    async def test_complete_section_sends_form_update(self, callback_handler, mock_handlers):
        """Test that complete_section calls completion handler."""
        result = await callback_handler.on_tool_call(
            tool_name="complete_section",
            arguments={}
        )
        
        mock_handlers["complete_section"].assert_called_once()
        assert result["success"] is True

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
