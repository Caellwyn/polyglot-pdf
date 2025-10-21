"""
Unit tests for section switching (backend-side reconnect pattern).

Tests cover:
- Section info request/response flow
- Gemini session recreation
- Section metadata building
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from backend.services.form_filling_service import FormFillingService


@pytest.mark.asyncio
async def test_handle_switch_section_requests_section_info():
    """handle_switch_section should request section info from frontend."""
    service = FormFillingService()
    
    # Mock websocket
    websocket = AsyncMock()
    service._websocket = websocket
    service._session_id = "test-session"
    
    # Call handle_switch_section
    task = asyncio.create_task(service.handle_switch_section("2"))
    
    # Wait a moment for request to be sent
    await asyncio.sleep(0.1)
    
    # Should have sent prepare_section_switch message
    assert websocket.send_json.call_count == 1
    call_args = websocket.send_json.call_args[0][0]
    assert call_args["type"] == "prepare_section_switch"
    assert call_args["identifier"] == "2"
    assert "request_id" in call_args
    
    # Cancel task (it's waiting for response)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_handle_section_info_response_resolves_future():
    """handle_section_info_response should resolve the pending future."""
    service = FormFillingService()
    
    # Create a pending request
    request_id = "test-request-123"
    future = asyncio.Future()
    service._pending_section_switch = {
        "request_id": request_id,
        "future": future,
    }
    
    # Send response
    section_info = {
        "schema": {"fields": []},
        "current_values": {},
        "metadata": {"section_number": 2},
        "initial_field_hint": "Next field: name",
    }
    
    service.handle_section_info_response(request_id, section_info)
    
    # Future should be resolved
    assert future.done()
    result = await future
    assert result == section_info


@pytest.mark.asyncio
async def test_switch_to_section_closes_and_recreates_gemini():
    """switch_to_section should close old Gemini session and create new one."""
    service = FormFillingService()
    
    # Mock LiveAI
    live_ai = AsyncMock()
    service._live_ai = live_ai
    service._session_id = "test-session"
    
    # Mock websocket
    websocket = AsyncMock()
    service._websocket = websocket
    
    # Call switch_to_section
    section_schema = {
        "fields": [
            {"id": "name", "name": "Full Name", "type": "text"},
        ]
    }
    section_values = {}
    section_metadata = {
        "section_number": 2,
        "total_sections": 3,
        "section_label": "Personal Information",
        "previous_spoken_names": ["email"],
    }
    
    await service.switch_to_section(
        section_schema=section_schema,
        section_values=section_values,
        section_metadata=section_metadata,
        initial_field_hint="Next field: name",
    )
    
    # Should have called finalize (close old session)
    assert live_ai.finalize.called
    
    # Should have called set_callbacks with system_instruction
    # Note: switch_to_section calls start_session which calls set_callbacks
    assert service._live_ai.set_callbacks.called
    
    # System instruction should include section context
    # Get the call_args from set_callbacks
    call_kwargs = service._live_ai.set_callbacks.call_args.kwargs
    system_instruction = call_kwargs.get("system_instruction", "")
    # Check for section number formatting (e.g., "Section 2/3")
    assert "Section 2/3" in system_instruction or "2/3" in system_instruction
    assert "Personal Information" in system_instruction
    
    # Should have sent section_switched confirmation
    assert websocket.send_json.called
    confirmation = websocket.send_json.call_args[0][0]
    assert confirmation["type"] == "section_switched"
    assert confirmation["section_number"] == 2


@pytest.mark.asyncio
async def test_switch_to_section_handles_no_live_ai():
    """switch_to_section should handle gracefully when no LiveAI configured."""
    service = FormFillingService()
    service._live_ai = None  # No AI (unit test mode)
    service._session_id = "test-session"
    
    # Should not raise, just log warning
    await service.switch_to_section(
        section_schema={"fields": []},
        section_values={},
        section_metadata={"section_number": 2, "total_sections": 3, "section_label": "Test"},
    )
    
    # No exception raised = success


def test_handle_section_info_response_ignores_mismatched_request_id():
    """handle_section_info_response should ignore responses with wrong request ID."""
    service = FormFillingService()
    
    # Create pending request
    future = asyncio.Future()
    service._pending_section_switch = {
        "request_id": "correct-id",
        "future": future,
    }
    
    # Send response with wrong ID
    service.handle_section_info_response("wrong-id", {"schema": {}})
    
    # Future should NOT be resolved
    assert not future.done()
    
    # Pending request should still exist
    assert service._pending_section_switch is not None


def test_handle_section_info_response_ignores_when_no_pending():
    """handle_section_info_response should handle no pending request gracefully."""
    service = FormFillingService()
    service._pending_section_switch = None
    
    # Should not raise
    service.handle_section_info_response("any-id", {"schema": {}})
