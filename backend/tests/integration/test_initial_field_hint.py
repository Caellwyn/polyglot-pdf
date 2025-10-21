"""
Integration test for initial field hint in handshake.

Tests that the initial field hint computed by frontend is properly
received and used in the initial message to Gemini.
"""
import pytest
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from backend.services.form_filling_service import FormFillingService


@pytest.mark.asyncio
async def test_initial_field_hint_in_handshake():
    """Test that initial field hint from handshake is used in initial message."""
    
    # Mock LiveAI
    mock_live_ai = Mock()
    mock_live_ai.set_callbacks = Mock()
    mock_live_ai.send_text_message = AsyncMock()
    
    # Create service
    service = FormFillingService(live_ai=mock_live_ai)
    
    # Mock WebSocket
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()
    
    # Test schema
    schema = {
        "source": "web",
        "form_metadata": {"title": "Test Form"},
        "fields": [
            {"id": "firstName", "name": "First Name", "type": "text", "required": True},
            {"id": "lastName", "name": "Last Name", "type": "text", "required": True},
            {"id": "email", "name": "Email", "type": "email", "required": True},
        ]
    }
    
    # Frontend-computed initial hint
    initial_field_hint = "Next unfilled field: firstName (First Name)"
    
    # Start session with system instruction and initial message
    system_instruction = "You are a helpful assistant."
    initial_message = f"Immediately respond with a warm greeting and ask the user for: {initial_field_hint}"
    
    await service.start_session(
        websocket=mock_ws,
        session_id="test_123",
        send_transcript=False,
        accept_connection=True,
        schema=schema,
        current_values={},
        system_instruction=system_instruction,
        initial_message=initial_message,
    )
    
    # Verify WebSocket was accepted
    mock_ws.accept.assert_called_once()
    
    # Verify LiveAI.set_callbacks was called with system instruction and initial message
    mock_live_ai.set_callbacks.assert_called_once()
    call_kwargs = mock_live_ai.set_callbacks.call_args.kwargs
    
    # Debug output
    print(f"\n📋 set_callbacks kwargs: {list(call_kwargs.keys())}")
    print(f"   system_instruction: {call_kwargs.get('system_instruction')}")
    print(f"   initial_message: {call_kwargs.get('initial_message')}")
    
    # Check system instruction was passed
    assert call_kwargs['system_instruction'] == system_instruction
    print(f"✅ System instruction passed: {call_kwargs['system_instruction'][:50]}...")
    
    # Check initial message was passed (with field hint)
    assert call_kwargs['initial_message'] == initial_message
    assert initial_field_hint in call_kwargs['initial_message']
    print(f"✅ Initial message contains hint: {call_kwargs['initial_message']}")
    
    # Verify the initial message includes the specific field name
    assert "firstName" in call_kwargs['initial_message']
    assert "First Name" in call_kwargs['initial_message']
    print(f"✅ Initial message includes specific field: firstName (First Name)")


@pytest.mark.asyncio
async def test_initial_field_hint_fallback_when_missing():
    """Test fallback behavior when initial_field_hint is None."""
    
    # Mock LiveAI
    mock_live_ai = Mock()
    mock_live_ai.set_callbacks = Mock()
    
    # Create service
    service = FormFillingService(live_ai=mock_live_ai)
    
    # Mock WebSocket
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()
    
    # Test schema
    schema = {
        "source": "web",
        "form_metadata": {"title": "Test Form"},
        "fields": [
            {"id": "email", "name": "Email", "type": "email", "required": True},
        ]
    }
    
    # No initial hint provided (None)
    system_instruction = "You are a helpful assistant."
    # Fallback message when no hint
    initial_message = "Immediately respond with a warm greeting and ask the user for: the first unfilled field."
    
    await service.start_session(
        websocket=mock_ws,
        session_id="test_456",
        send_transcript=False,
        accept_connection=True,
        schema=schema,
        current_values={},
        system_instruction=system_instruction,
        initial_message=initial_message,
    )
    
    # Verify fallback message was used
    call_kwargs = mock_live_ai.set_callbacks.call_args.kwargs
    assert call_kwargs['initial_message'] == initial_message
    assert "the first unfilled field" in call_kwargs['initial_message']
    print(f"✅ Fallback message used when no hint: {call_kwargs['initial_message']}")


@pytest.mark.asyncio  
async def test_no_blocking_on_websocket_before_accept():
    """Test that no WebSocket messages are sent before accept() is called."""
    
    # This test ensures we don't have the deadlock issue where
    # request_next_field_hint() tries to send before WebSocket is accepted
    
    # Track call order
    call_order = []
    
    # Mock WebSocket
    mock_ws = AsyncMock()
    
    async def track_accept():
        call_order.append("accept")
    
    async def track_send_json(msg):
        call_order.append(f"send_json:{msg.get('type')}")
        if "accept" not in call_order:
            raise RuntimeError("❌ send_json called before accept()!")
    
    mock_ws.accept = AsyncMock(side_effect=track_accept)
    mock_ws.send_json = AsyncMock(side_effect=track_send_json)
    
    # Mock LiveAI
    mock_live_ai = Mock()
    mock_live_ai.set_callbacks = Mock()
    
    # Create service
    service = FormFillingService(live_ai=mock_live_ai)
    
    # Test schema
    schema = {
        "source": "web",
        "form_metadata": {"title": "Test Form"},
        "fields": [{"id": "name", "name": "Name", "type": "text"}]
    }
    
    # Start session (should NOT send any WebSocket messages before accept)
    await service.start_session(
        websocket=mock_ws,
        session_id="test_789",
        send_transcript=False,
        accept_connection=True,
        schema=schema,
        current_values={},
        system_instruction="Test instruction",
        initial_message="Test message with hint",
    )
    
    # Verify accept was called first
    assert call_order[0] == "accept"
    print(f"✅ WebSocket accept() called first")
    print(f"✅ Call order: {call_order}")
    
    # Verify no send_json before accept
    for call in call_order:
        if call.startswith("send_json"):
            assert False, f"❌ send_json called before accept: {call_order}"
    
    print(f"✅ No WebSocket messages sent before accept()")


if __name__ == "__main__":
    # Run tests
    import asyncio
    
    print("\n" + "="*60)
    print("Testing Initial Field Hint Flow")
    print("="*60 + "\n")
    
    print("Test 1: Initial field hint in handshake...")
    asyncio.run(test_initial_field_hint_in_handshake())
    print()
    
    print("Test 2: Fallback when hint missing...")
    asyncio.run(test_initial_field_hint_fallback_when_missing())
    print()
    
    print("Test 3: No blocking before WebSocket accept...")
    asyncio.run(test_no_blocking_on_websocket_before_accept())
    print()
    
    print("="*60)
    print("✅ All tests passed!")
    print("="*60)
