import asyncio
import sys
import os
sys.path.append(os.getcwd())

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocketDisconnect
from backend.services.form_filling_service import FormFillingService
from backend.config import Settings

async def test_send_disclaimer_message_formats_correctly():
    print("Running test_send_disclaimer_message_formats_correctly...")
    # Setup
    mock_ai = AsyncMock()
    settings = Settings()
    # Override the template to be sure we are testing the new one
    settings.DISCLAIMER_INITIATING_MESSAGE = "Speak {spoken_language}. Read: '{disclaimer_text}'"
    
    service = FormFillingService(live_ai=mock_ai, settings=settings)
    service._session_id = "test_session"
    
    # Execute
    await service.send_disclaimer_message("Spanish", "Texto de descargo")
    
    # Verify
    mock_ai.send_client_content.assert_called_once_with(
        "Speak Spanish. Read: 'Texto de descargo'"
    )
    print("PASS")

async def test_read_disclaimer_route_logic():
    print("Running test_read_disclaimer_route_logic...")
    # We want to test that the route handler extracts the text and calls the service
    # Since the route handler is a loop inside _handle_fill_session, we can import it
    from backend.routes.websocket_routes import _handle_fill_session
    
    mock_ws = AsyncMock()
    # Simulate handshake already done, just processing messages
    # The loop calls ws.receive_json()
    mock_ws.receive_json.side_effect = [
        {
            "type": "read_disclaimer", 
            "spoken_language": "French", 
            "disclaimer_text": "Ceci est un avis important"
        },
        WebSocketDisconnect() # Break the loop
    ]
    
    mock_service = MagicMock()
    mock_service.send_disclaimer_message = AsyncMock()
    
    # Run
    try:
        await _handle_fill_session(
            websocket=mock_ws,
            session_id="test_session",
            service=mock_service,
            send_transcript=False,
            accept_connection=False # Don't try to accept again
        )
    except WebSocketDisconnect:
        pass
        
    # Verify
    mock_service.send_disclaimer_message.assert_awaited_once_with("French", "Ceci est un avis important")
    print("PASS")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_send_disclaimer_message_formats_correctly())
    loop.run_until_complete(test_read_disclaimer_route_logic())
    loop.close()
