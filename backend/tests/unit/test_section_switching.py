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
async def test_handle_switch_section_requests_via_coordinator_and_switches():
    """handle_switch_section should delegate to RequestCoordinator then switch sections."""
    service = FormFillingService()
    coordinator = AsyncMock()
    service._request_coordinator = coordinator
    service._session_id = "test-session"

    section_info = {
        "schema": {"fields": []},
        "current_values": {"name": "Jane"},
        "metadata": {"section_number": 2, "section_label": "Personal", "total_sections": 4},
        "initial_field_hint": "Next field: name",
    }
    coordinator.request_section_info.return_value = section_info

    # Patch switch_to_section so we can assert on the arguments without invoking Gemini
    service.switch_to_section = AsyncMock()

    result = await service.handle_switch_section("2")

    coordinator.request_section_info.assert_awaited_once_with("2")
    service.switch_to_section.assert_awaited_once_with(
        section_schema=section_info["schema"],
        section_values=section_info["current_values"],
        section_metadata=section_info["metadata"],
        initial_field_hint=section_info["initial_field_hint"],
    )
    assert result["success"] is True
    assert "Switched to section" in result["message"]


@pytest.mark.asyncio
async def test_handle_switch_section_returns_failure_on_missing_section_info():
    """If section info cannot be retrieved, the handler should fail gracefully."""
    service = FormFillingService()
    coordinator = AsyncMock()
    service._request_coordinator = coordinator
    coordinator.request_section_info.return_value = None

    result = await service.handle_switch_section("missing")

    coordinator.request_section_info.assert_awaited_once_with("missing")
    assert result == {
        "success": False,
        "message": "Section switch request failed or timed out.",
    }


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


def test_handle_section_info_response_delegates_to_request_coordinator():
    """Responses should be forwarded to the RequestCoordinator for resolution."""
    service = FormFillingService()
    coordinator = MagicMock()
    service._request_coordinator = coordinator

    payload = {"schema": {"fields": []}}
    service.handle_section_info_response("req-1", payload)

    coordinator.handle_section_info_response.assert_called_once_with("req-1", payload)


def test_handle_section_info_response_no_coordinator_is_noop():
    """Handler should not raise when coordinator is missing (legacy sessions)."""
    service = FormFillingService()
    service._request_coordinator = None

    service.handle_section_info_response("req-1", {"schema": {}})
