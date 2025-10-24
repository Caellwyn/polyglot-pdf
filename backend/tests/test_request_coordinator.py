"""
Tests for request_coordinator module.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.request_coordinator import RequestCoordinator


class TestRequestCoordinatorInit:
    """Tests for RequestCoordinator initialization."""
    
    def test_init_with_websocket(self):
        """Should initialize with provided websocket."""
        mock_ws = MagicMock()
        coordinator = RequestCoordinator(websocket=mock_ws, session_id="test-session")
        
        assert coordinator._websocket is mock_ws
        assert coordinator._session_id == "test-session"
        assert coordinator._pending_form_state_request is None
        assert coordinator._pending_next_field_request is None
        assert coordinator._pending_field_value_request is None
        assert coordinator._pending_section_switch is None
    
    def test_init_without_websocket(self):
        """Should initialize with None websocket."""
        coordinator = RequestCoordinator()
        
        assert coordinator._websocket is None
        assert coordinator._session_id is None
    
    def test_set_websocket(self):
        """Should update websocket connection."""
        coordinator = RequestCoordinator()
        mock_ws = MagicMock()
        
        coordinator.set_websocket(mock_ws)
        
        assert coordinator._websocket is mock_ws


class TestRequestFormState:
    """Tests for request_form_state method."""
    
    @pytest.mark.asyncio
    async def test_request_form_state_no_websocket(self):
        """Should return empty dict when no websocket."""
        coordinator = RequestCoordinator()
        
        result = await coordinator.request_form_state()
        
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_request_form_state_sends_message(self):
        """Should send get_form_state message with request_id."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        # Simulate response in background
        async def send_response():
            await asyncio.sleep(0.01)
            # Get the request_id from the sent message
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_form_state_response(request_id, {"field1": "value1"})
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_form_state()
        
        # Verify message sent
        assert mock_ws.send_json.called
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["type"] == "get_form_state"
        assert "request_id" in sent_message
        assert sent_message["field_ids"] == []
        
        # Verify result
        assert result == {"field1": "value1"}
    
    @pytest.mark.asyncio
    async def test_request_form_state_with_field_ids(self):
        """Should send specific field_ids when provided."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_form_state_response(request_id, {"email": "test@example.com"})
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_form_state(field_ids=["email", "phone"])
        
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["field_ids"] == ["email", "phone"]
        assert result == {"email": "test@example.com"}
    
    @pytest.mark.asyncio
    async def test_request_form_state_timeout(self):
        """Should return empty dict on timeout."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        # Don't send response, let it timeout
        result = await coordinator.request_form_state()
        
        assert result == {}
        assert coordinator._pending_form_state_request is None
    
    @pytest.mark.asyncio
    async def test_request_form_state_send_error(self):
        """Should handle send_json errors."""
        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("Connection error")
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        result = await coordinator.request_form_state()
        
        assert result == {}
        assert coordinator._pending_form_state_request is None


class TestRequestNextFieldHint:
    """Tests for request_next_field_hint method."""
    
    @pytest.mark.asyncio
    async def test_request_next_field_hint_no_websocket(self):
        """Should return None when no websocket."""
        coordinator = RequestCoordinator()
        
        result = await coordinator.request_next_field_hint()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_request_next_field_hint_sends_message(self):
        """Should send get_next_field_hint message."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_next_field_hint_response(request_id, "Next field: email")
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_next_field_hint()
        
        assert mock_ws.send_json.called
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["type"] == "get_next_field_hint"
        assert "request_id" in sent_message
        assert result == "Next field: email"
    
    @pytest.mark.asyncio
    async def test_request_next_field_hint_no_more_fields(self):
        """Should handle None hint when form is complete."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_next_field_hint_response(request_id, None)
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_next_field_hint()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_request_next_field_hint_timeout(self):
        """Should return None on timeout."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        result = await coordinator.request_next_field_hint()
        
        assert result is None
        assert coordinator._pending_next_field_request is None


class TestRequestFieldValue:
    """Tests for request_field_value method."""
    
    @pytest.mark.asyncio
    async def test_request_field_value_no_websocket(self):
        """Should return not found when no websocket."""
        coordinator = RequestCoordinator()
        
        result = await coordinator.request_field_value("email")
        
        assert result == {"found": False, "value": None}
    
    @pytest.mark.asyncio
    async def test_request_field_value_sends_message(self):
        """Should send get_field_value message with spoken_name."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_field_value_response(request_id, "test@example.com", True)
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_field_value("email")
        
        assert mock_ws.send_json.called
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["type"] == "get_field_value"
        assert sent_message["spoken_name"] == "email"
        assert "request_id" in sent_message
        assert result == {"value": "test@example.com", "found": True}
    
    @pytest.mark.asyncio
    async def test_request_field_value_not_found(self):
        """Should handle field not found response."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_field_value_response(request_id, None, False)
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_field_value("nonexistent")
        
        assert result == {"value": None, "found": False}
    
    @pytest.mark.asyncio
    async def test_request_field_value_timeout(self):
        """Should return not found on timeout."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        result = await coordinator.request_field_value("email")
        
        assert result == {"found": False, "value": None}
        assert coordinator._pending_field_value_request is None


class TestRequestSectionInfo:
    """Tests for request_section_info method."""
    
    @pytest.mark.asyncio
    async def test_request_section_info_no_websocket(self):
        """Should return None when no websocket."""
        coordinator = RequestCoordinator()
        
        result = await coordinator.request_section_info("3")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_request_section_info_sends_message(self):
        """Should send prepare_section_switch message."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        section_data = {
            "schema": {"field1": {}},
            "current_values": {},
            "metadata": {"section_number": 3},
            "initial_field_hint": "Start with field1"
        }
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_section_info_response(request_id, section_data)
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_section_info("3")
        
        assert mock_ws.send_json.called
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["type"] == "prepare_section_switch"
        assert sent_message["identifier"] == "3"
        assert "request_id" in sent_message
        assert result == section_data
    
    @pytest.mark.asyncio
    async def test_request_section_info_timeout(self):
        """Should return None on timeout."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        result = await coordinator.request_section_info("3")
        
        assert result is None
        assert coordinator._pending_section_switch is None


class TestResponseHandlers:
    """Tests for response handler methods."""
    
    def test_handle_form_state_response_no_pending(self):
        """Should warn when no pending request."""
        coordinator = RequestCoordinator()
        
        # Should not raise, just log warning
        coordinator.handle_form_state_response("test-id", {})
    
    def test_handle_form_state_response_mismatched_id(self):
        """Should warn when request_id doesn't match."""
        coordinator = RequestCoordinator()
        coordinator._pending_form_state_request = {
            "request_id": "correct-id",
            "future": asyncio.Future()
        }
        
        coordinator.handle_form_state_response("wrong-id", {})
        
        # Future should not be resolved
        assert not coordinator._pending_form_state_request["future"].done()
    
    def test_handle_form_state_response_resolves_future(self):
        """Should resolve future with field values."""
        coordinator = RequestCoordinator()
        future = asyncio.Future()
        coordinator._pending_form_state_request = {
            "request_id": "test-id",
            "future": future
        }
        
        coordinator.handle_form_state_response("test-id", {"field1": "value1"})
        
        assert future.done()
        assert future.result() == {"field1": "value1"}
        assert coordinator._pending_form_state_request is None
    
    def test_handle_next_field_hint_response_resolves_future(self):
        """Should resolve future with hint."""
        coordinator = RequestCoordinator()
        future = asyncio.Future()
        coordinator._pending_next_field_request = {
            "request_id": "test-id",
            "future": future
        }
        
        coordinator.handle_next_field_hint_response("test-id", "Next: email")
        
        assert future.done()
        assert future.result() == "Next: email"
        assert coordinator._pending_next_field_request is None
    
    def test_handle_field_value_response_resolves_future(self):
        """Should resolve future with value and found status."""
        coordinator = RequestCoordinator()
        future = asyncio.Future()
        coordinator._pending_field_value_request = {
            "request_id": "test-id",
            "future": future
        }
        
        coordinator.handle_field_value_response("test-id", "test@example.com", True)
        
        assert future.done()
        assert future.result() == {"value": "test@example.com", "found": True}
        assert coordinator._pending_field_value_request is None
    
    def test_handle_section_info_response_resolves_future(self):
        """Should resolve future with section info."""
        coordinator = RequestCoordinator()
        future = asyncio.Future()
        coordinator._pending_section_switch = {
            "request_id": "test-id",
            "future": future
        }
        
        section_data = {"schema": {}, "current_values": {}}
        coordinator.handle_section_info_response("test-id", section_data)
        
        assert future.done()
        assert future.result() == section_data
        assert coordinator._pending_section_switch is None


class TestMultipleConcurrentRequests:
    """Tests for handling multiple concurrent requests."""
    
    @pytest.mark.asyncio
    async def test_concurrent_different_request_types(self):
        """Should handle different request types concurrently."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_responses():
            await asyncio.sleep(0.01)
            # Respond to both requests
            calls = mock_ws.send_json.call_args_list
            for call in calls:
                message = call[0][0]
                request_id = message["request_id"]
                if message["type"] == "get_form_state":
                    coordinator.handle_form_state_response(request_id, {"field1": "value1"})
                elif message["type"] == "get_next_field_hint":
                    coordinator.handle_next_field_hint_response(request_id, "Next: email")
        
        asyncio.create_task(send_responses())
        
        # Make concurrent requests of different types
        form_state_task = coordinator.request_form_state()
        next_hint_task = coordinator.request_next_field_hint()
        
        results = await asyncio.gather(form_state_task, next_hint_task)
        
        assert results[0] == {"field1": "value1"}
        assert results[1] == "Next: email"
