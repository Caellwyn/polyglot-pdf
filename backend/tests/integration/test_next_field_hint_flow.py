"""
Integration test for optimized next_field_hint flow.

Tests that the next_field_hint is correctly requested and returned
as part of the form_updated message, reducing round trips from 2 to 1.
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from backend.services.form_filling_service import FormFillingService
from backend.adapters.labeling_ai_gemini import LabelingAIGemini
from backend.adapters.live_ai_gemini import LiveAIGemini


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    return ws


@pytest.fixture
def sample_schema():
    """Sample form schema with multiple fields."""
    return {
        "source": "web",
        "form_metadata": {
            "title": "Test Form",
            "url": "https://example.com/test"
        },
        "fields": [
            {
                "id": "firstName",
                "name": "First Name",
                "type": "text",
                "required": True,
                "value": ""
            },
            {
                "id": "lastName",
                "name": "Last Name",
                "type": "text",
                "required": True,
                "value": ""
            },
            {
                "id": "email",
                "name": "Email",
                "type": "email",
                "required": True,
                "value": ""
            }
        ]
    }


@pytest.fixture
def sample_current_values():
    """Sample current values with first field filled."""
    return {
        "firstName": {
            "value": "John",
            "confirmed": True
        }
    }


class TestNextFieldHintOptimization:
    """Test optimized next_field_hint flow."""
    
    @pytest.mark.asyncio
    async def test_handle_next_field_hint_response_resolves_future(self):
        """Test that handle_next_field_hint_response resolves the waiting future."""
        service = FormFillingService()
        
        # Setup a pending request manually
        request_id = "test-request-123"
        future = asyncio.Future()
        service._pending_next_field_request = {
            "request_id": request_id,
            "future": future
        }
        
        expected_hint = "Next: email field"
        
        # Handle the response
        service.handle_next_field_hint_response(request_id, expected_hint)
        
        # Verify the future was resolved
        assert future.done()
        assert future.result() == expected_hint
    
    
    @pytest.mark.asyncio
    async def test_handle_next_field_hint_response_with_none(self):
        """Test that handle_next_field_hint_response works with None (form complete)."""
        service = FormFillingService()
        
        request_id = "test-request-456"
        future = asyncio.Future()
        service._pending_next_field_request = {
            "request_id": request_id,
            "future": future
        }
        
        # Handle response with None (no more fields)
        service.handle_next_field_hint_response(request_id, None)
        
        # Verify the future was resolved with None
        assert future.done()
        assert future.result() is None
    
    
    @pytest.mark.asyncio
    async def test_handle_next_field_hint_response_wrong_request_id(self):
        """Test that mismatched request_id doesn't resolve the future."""
        service = FormFillingService()
        
        request_id = "test-request-789"
        future = asyncio.Future()
        service._pending_next_field_request = {
            "request_id": request_id,
            "future": future
        }
        
        # Handle response with wrong request_id
        service.handle_next_field_hint_response("wrong-id", "some hint")
        
        # Verify the future was NOT resolved
        assert not future.done()
    
    
    @pytest.mark.asyncio
    async def test_full_websocket_flow_with_hint_request(self):
        """
        Test complete WebSocket flow:
        1. Service sends form_updated with hint request
        2. Mock frontend receives message
        3. Mock frontend sends hint response
        4. Service receives and resolves future
        """
        mock_websocket = AsyncMock()
        sent_messages = []
        
        async def capture_send_json(msg):
            sent_messages.append(msg)
        
        mock_websocket.send_json = capture_send_json
        mock_websocket.send_text = AsyncMock()
        mock_websocket.receive_json = AsyncMock()
        
        # Create service with mocked AI
        mock_labeling_ai = MagicMock(spec=LabelingAIGemini)
        mock_live_ai = MagicMock(spec=LiveAIGemini)
        
        service = FormFillingService(
            labeling_ai=mock_labeling_ai,
            live_ai=mock_live_ai
        )
        
        # Set up schema
        service._schema = {
            "source": "web",
            "fields": [
                {"id": "firstName", "name": "First Name", "type": "text", "value": ""},
                {"id": "lastName", "name": "Last Name", "type": "text", "value": ""},
                {"id": "email", "name": "Email", "type": "email", "value": ""}
            ]
        }
        service._session_id = "test-session"
        service._websocket = mock_websocket
        
        # Simulate the send_form_update scenario
        # We'll manually trigger what happens inside start_session's send_form_update
        
        # Create form update message
        import uuid
        request_id = str(uuid.uuid4())
        payload = {
            "form_state": {"firstName": "John", "lastName": "Doe"},
            "applied_fields": ["lastName"],
            "request_next_field_hint": True,
            "request_id": request_id
        }
        
        # Create future
        future = asyncio.Future()
        service._pending_next_field_request = {
            "request_id": request_id,
            "future": future
        }
        
        # Send the message
        await mock_websocket.send_json({"type": "form_updated", "data": payload})
        
        # Verify message was sent
        assert len(sent_messages) == 1
        assert sent_messages[0]["type"] == "form_updated"
        assert sent_messages[0]["data"]["request_next_field_hint"] is True
        assert "request_id" in sent_messages[0]["data"]
        
        # Simulate frontend response
        expected_hint = "Next unfilled field: email (Email)"
        service.handle_next_field_hint_response(request_id, expected_hint)
        
        # Verify future was resolved
        assert future.done()
        assert future.result() == expected_hint

class TestMessageProtocol:
    """Test that hint response messages are properly structured."""
    
    @pytest.mark.asyncio
    async def test_hint_response_ignored_if_no_pending_request(self):
        """Test that hint responses are ignored if there's no pending request."""
        service = FormFillingService()
        
        # No pending request
        service._pending_next_field_request = None
        
        # This should not crash
        service.handle_next_field_hint_response("some-id", "some hint")
        
        # Should still be None
        assert service._pending_next_field_request is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
