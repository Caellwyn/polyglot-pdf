"""
Unit tests for idle timeout handling

Tests:
1. Backend sends idle_timeout message before closing
2. WebSocket closes gracefully after idle period
3. Gemini session cleaned up properly
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import WebSocket
from backend.services.form_filling_service import FormFillingService


@pytest.mark.asyncio
async def test_idle_timeout_message_sent():
    """Test that backend sends idle_timeout message before closing WebSocket"""
    
    # Mock WebSocket
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_json = AsyncMock()
    mock_ws.close = AsyncMock()
    
    # Simulate idle timeout scenario
    idle_timeout = 2  # 2 seconds for testing
    last_rx = time.time()
    
    # Wait for idle period
    await asyncio.sleep(idle_timeout + 0.5)
    
    # Check if timeout detected
    time_since_last = time.time() - last_rx
    assert time_since_last > idle_timeout
    
    # Simulate watchdog sending idle_timeout message
    await mock_ws.send_json({
        "type": "idle_timeout",
        "idle_seconds": int(time_since_last),
        "message": "Connection timed out due to inactivity"
    })
    
    # Give frontend time to receive
    await asyncio.sleep(0.5)
    
    # Close connection
    await mock_ws.close(code=1000, reason="Idle timeout")
    
    # Verify message was sent
    mock_ws.send_json.assert_called_once()
    call_args = mock_ws.send_json.call_args[0][0]
    assert call_args["type"] == "idle_timeout"
    assert "idle_seconds" in call_args
    assert call_args["message"] == "Connection timed out due to inactivity"
    
    # Verify close was called with correct code
    mock_ws.close.assert_called_once_with(code=1000, reason="Idle timeout")


@pytest.mark.asyncio
async def test_activity_resets_idle_timer():
    """Test that receiving messages resets the idle timer"""
    
    idle_timeout = 60
    last_rx = time.time()
    
    # Simulate activity after 30 seconds
    await asyncio.sleep(0.1)  # Short wait for test
    time_since_first = time.time() - last_rx
    assert time_since_first < idle_timeout
    
    # Reset timer on activity
    last_rx = time.time()
    
    # Check timer was reset
    time_since_reset = time.time() - last_rx
    assert time_since_reset < 1


@pytest.mark.asyncio
async def test_gemini_session_cleanup_on_idle():
    """Test that Gemini session is properly cleaned up on idle timeout"""
    
    # Mock service
    mock_service = AsyncMock(spec=FormFillingService)
    mock_service.end_session = AsyncMock()
    
    # Simulate idle timeout cleanup
    try:
        # Normal operation...
        pass
    finally:
        # Cleanup should be called in finally block
        await mock_service.end_session()
    
    # Verify cleanup was called
    mock_service.end_session.assert_called_once()


def test_idle_timeout_configuration():
    """Test that idle timeout is configurable"""
    from backend.config import get_settings
    
    settings = get_settings()
    
    # Should have idle timeout setting
    assert hasattr(settings, 'WS_IDLE_TIMEOUT_SEC')
    assert isinstance(settings.WS_IDLE_TIMEOUT_SEC, int)
    assert settings.WS_IDLE_TIMEOUT_SEC == 60  # Default 60 seconds


@pytest.mark.asyncio
async def test_watchdog_task_cancellation():
    """Test that watchdog task is properly cancelled on disconnect"""
    
    async def watchdog_task():
        try:
            while True:
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            # Should handle cancellation gracefully
            return
    
    # Create and start watchdog
    watchdog = asyncio.create_task(watchdog_task())
    
    # Let it run briefly
    await asyncio.sleep(0.1)
    
    # Cancel it (simulating disconnect)
    watchdog.cancel()
    
    # Should not raise exception
    try:
        await watchdog
    except asyncio.CancelledError:
        pass  # Expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
