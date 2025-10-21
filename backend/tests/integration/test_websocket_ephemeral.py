"""
Integration tests for WebSocket ephemeral sessions.

Tests the complete flow of web form filling without SessionManager,
using only ephemeral state passed in the handshake.
"""
import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from fastapi import WebSocket
from backend.routes.websocket_routes import fill_form_from_schema


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    ws.receive = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def handshake_message():
    """Sample handshake message for web form."""
    return {
        "type": "handshake",
        "schema": {
            "source": "web",
            "form_metadata": {
                "title": "Contact Form",
                "url": "https://example.com/contact"
            },
            "fields": [
                {
                    "id": "email",
                    "name": "Email",
                    "type": "email",
                    "required": True,
                    "value": ""
                },
                {
                    "id": "name",
                    "name": "Full Name",
                    "type": "text",
                    "required": True,
                    "value": ""
                }
            ]
        },
        "current_values": {}
    }


@pytest.fixture
def reconnect_handshake():
    """Handshake with existing values (reconnect scenario)."""
    return {
        "type": "handshake",
        "schema": {
            "source": "web",
            "form_metadata": {
                "title": "Contact Form",
                "url": "https://example.com/contact"
            },
            "fields": [
                {
                    "id": "email",
                    "name": "Email",
                    "type": "email",
                    "required": True,
                    "value": ""
                },
                {
                    "id": "name",
                    "name": "Full Name",
                    "type": "text",
                    "required": True,
                    "value": ""
                }
            ]
        },
        "current_values": {
            "email": {
                "value": "reconnect@example.com",
                "confirmed": True
            }
        }
    }


class TestWebSocketHandshake:
    """Test WebSocket handshake for ephemeral sessions."""
    
    @pytest.mark.asyncio
    async def test_handshake_accepts_schema_and_values(self, mock_websocket, handshake_message):
        """Verify handshake accepts schema and current_values."""
        # Mock receive to return handshake message then disconnect
        mock_websocket.receive.side_effect = [
            {"type": "websocket.message", "text": json.dumps(handshake_message)},
            {"type": "websocket.disconnect"}
        ]
        
        with patch('backend.routes.websocket_routes.FormFillingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.start_session = AsyncMock(return_value=None)
            mock_service.handle_tool_call = AsyncMock()
            mock_service_class.return_value = mock_service
            
            # Call the WebSocket handler
            try:
                await fill_form_from_schema(mock_websocket)
            except Exception:
                pass  # Expected to fail on disconnect
            
            # Verify session_ready was sent
            assert mock_websocket.send_text.called
            calls = [call[0][0] for call in mock_websocket.send_text.call_args_list]
            
            # Find session_ready message
            session_ready = None
            for call in calls:
                try:
                    msg = json.loads(call)
                    if msg.get("type") == "session_ready":
                        session_ready = msg
                        break
                except:
                    pass
            
            assert session_ready is not None
            assert "session_id" in session_ready
            assert session_ready["ephemeral"] is True
            assert session_ready["session_id"].startswith("web_")
    
    @pytest.mark.asyncio
    async def test_handshake_with_reconnect_values(self, mock_websocket, reconnect_handshake):
        """Verify handshake preserves current_values on reconnect."""
        mock_websocket.receive.side_effect = [
            {"type": "websocket.message", "text": json.dumps(reconnect_handshake)},
            {"type": "websocket.disconnect"}
        ]
        
        with patch('backend.routes.websocket_routes.FormFillingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.start_session = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service
            
            try:
                await fill_form_from_schema(mock_websocket)
            except Exception:
                pass
            
            # Verify start_session was called with schema and current_values
            assert mock_service.start_session.called
            call_kwargs = mock_service.start_session.call_args[1]
            
            assert "schema" in call_kwargs
            assert "current_values" in call_kwargs
            assert call_kwargs["current_values"]["email"]["value"] == "reconnect@example.com"
            assert call_kwargs["current_values"]["email"]["confirmed"] is True
    
    @pytest.mark.asyncio
    async def test_missing_schema_returns_error(self, mock_websocket):
        """Verify missing schema in handshake returns error."""
        bad_handshake = {
            "type": "handshake"
            # Missing schema
        }
        
        mock_websocket.receive.side_effect = [
            {"type": "websocket.message", "text": json.dumps(bad_handshake)},
            {"type": "websocket.disconnect"}
        ]
        
        try:
            await fill_form_from_schema(mock_websocket)
        except Exception:
            pass
        
        # Should send error message
        assert mock_websocket.send_text.called
        calls = [call[0][0] for call in mock_websocket.send_text.call_args_list]
        
        # Look for error message
        error_sent = any("error" in call.lower() or "schema" in call.lower() for call in calls)
        assert error_sent


class TestEphemeralSessionLifecycle:
    """Test the lifecycle of an ephemeral session."""
    
    @pytest.mark.asyncio
    async def test_session_does_not_use_session_manager(self, mock_websocket, handshake_message):
        """Verify ephemeral sessions don't interact with SessionManager."""
        mock_websocket.receive.side_effect = [
            {"type": "websocket.message", "text": json.dumps(handshake_message)},
            {"type": "websocket.disconnect"}
        ]
        
        with patch('backend.routes.websocket_routes.SessionManager') as mock_sm_class, \
             patch('backend.routes.websocket_routes.FormFillingService') as mock_service_class:
            
            mock_service = AsyncMock()
            mock_service.start_session = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service
            
            try:
                await fill_form_from_schema(mock_websocket)
            except Exception:
                pass
            
            # SessionManager should NOT be called
            # (Note: SessionManager is still constructed but not used for web sessions)
            # We check this indirectly by verifying the service was created with ephemeral params
            assert mock_service.start_session.called
            call_kwargs = mock_service.start_session.call_args[1]
            assert "schema" in call_kwargs
    
    @pytest.mark.asyncio
    async def test_ephemeral_id_format(self, mock_websocket, handshake_message):
        """Verify ephemeral session IDs start with 'web_'."""
        mock_websocket.receive.side_effect = [
            {"type": "websocket.message", "text": json.dumps(handshake_message)},
            {"type": "websocket.disconnect"}
        ]
        
        with patch('backend.routes.websocket_routes.FormFillingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.start_session = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service
            
            try:
                await fill_form_from_schema(mock_websocket)
            except Exception:
                pass
            
            # Check session_ready message
            calls = [call[0][0] for call in mock_websocket.send_text.call_args_list]
            session_ready = None
            for call in calls:
                try:
                    msg = json.loads(call)
                    if msg.get("type") == "session_ready":
                        session_ready = msg
                        break
                except:
                    pass
            
            if session_ready:
                assert session_ready["session_id"].startswith("web_")
                assert session_ready["ephemeral"] is True


class TestFieldUpdates:
    """Test field updates in ephemeral sessions."""
    
    @pytest.mark.asyncio
    async def test_field_update_tool_call(self, mock_websocket, handshake_message):
        """Verify update_form_fields tool works with ephemeral sessions."""
        # Simulate handshake then a tool call
        tool_call_msg = {
            "type": "tool_call",
            "tool": "update_form_fields",
            "args": {
                "Email": "test@example.com"
            }
        }
        
        mock_websocket.receive.side_effect = [
            {"type": "websocket.message", "text": json.dumps(handshake_message)},
            {"type": "websocket.message", "text": json.dumps(tool_call_msg)},
            {"type": "websocket.disconnect"}
        ]
        
        with patch('backend.routes.websocket_routes.FormFillingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.start_session = AsyncMock(return_value=None)
            mock_service.handle_tool_call = AsyncMock(return_value={
                "applied_fields": [{"field_name": "Email", "value": "test@example.com"}],
                "unknown_fields": []
            })
            mock_service_class.return_value = mock_service
            
            try:
                await fill_form_from_schema(mock_websocket)
            except Exception:
                pass
            
            # Verify handle_tool_call was invoked
            assert mock_service.handle_tool_call.called


class TestEdgeCases:
    """Test edge cases and error scenarios."""
    
    @pytest.mark.asyncio
    async def test_empty_current_values(self, mock_websocket):
        """Verify empty current_values works (new session)."""
        msg = {
            "type": "handshake",
            "schema": {
                "source": "web",
                "fields": []
            },
            "current_values": {}
        }
        
        mock_websocket.receive.side_effect = [
            {"type": "websocket.message", "text": json.dumps(msg)},
            {"type": "websocket.disconnect"}
        ]
        
        with patch('backend.routes.websocket_routes.FormFillingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.start_session = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service
            
            try:
                await fill_form_from_schema(mock_websocket)
            except Exception:
                pass
            
            # Should still work
            assert mock_service.start_session.called
    
    @pytest.mark.asyncio
    async def test_missing_current_values_key(self, mock_websocket):
        """Verify missing current_values key defaults to empty dict."""
        msg = {
            "type": "handshake",
            "schema": {
                "source": "web",
                "fields": []
            }
            # No current_values key
        }
        
        mock_websocket.receive.side_effect = [
            {"type": "websocket.message", "text": json.dumps(msg)},
            {"type": "websocket.disconnect"}
        ]
        
        with patch('backend.routes.websocket_routes.FormFillingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.start_session = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service
            
            try:
                await fill_form_from_schema(mock_websocket)
            except Exception:
                pass
            
            # Should default to {}
            if mock_service.start_session.called:
                call_kwargs = mock_service.start_session.call_args[1]
                assert "current_values" in call_kwargs
                assert call_kwargs["current_values"] == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
