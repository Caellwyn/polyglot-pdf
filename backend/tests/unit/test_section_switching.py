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


def _set_event_live_ai():
    """An AsyncMock LiveAI whose begin_graceful_shutdown returns an already-set
    asyncio.Event, so _complete_section_switch's wait_for(closed.wait()) resolves
    immediately in tests (the real adapter sets the event when the loop exits)."""
    live_ai = AsyncMock()
    ev = asyncio.Event()
    ev.set()
    live_ai.begin_graceful_shutdown = MagicMock(return_value=ev)
    return live_ai


@pytest.mark.asyncio
async def test_handle_switch_section_responds_before_teardown_then_swaps_off_task():
    """y4a (bd polyglot-pdf-0c1): handle_switch_section must RETURN the success
    payload (the switch_section FunctionResponse) WITHOUT awaiting switch_to_section
    inline -- the swap runs on a detached task. This proves the response is produced
    before any session teardown, instead of the old self-cancel that orphaned it."""
    service = FormFillingService()
    coordinator = AsyncMock()
    service._request_coordinator = coordinator
    service._session_id = "test-session"
    service._live_ai = _set_event_live_ai()

    section_info = {
        "schema": {"fields": []},
        "current_values": {"name": "Jane"},
        "metadata": {"section_number": 2, "section_label": "Personal", "total_sections": 4},
        "initial_field_hint": "Next field: name",
    }
    coordinator.request_section_info.return_value = section_info

    # Patch the swap so we can assert it runs on the detached task, AFTER the return.
    service.switch_to_section = AsyncMock()

    result = await service.handle_switch_section("2")

    # The success payload is returned -- and at that instant the swap has NOT yet
    # run (it is scheduled on _switch_task, not awaited inline). This is the ordering
    # that delivers the FunctionResponse on the OLD session before teardown.
    coordinator.request_section_info.assert_awaited_once_with("2")
    assert result["success"] is True
    assert "Switched to section" in result["message"]
    assert service._live_ai.begin_graceful_shutdown.called
    assert service._switch_task is not None

    # Now let the detached task run to completion and assert the swap happened.
    await service._switch_task
    service.switch_to_section.assert_awaited_once_with(
        section_schema=section_info["schema"],
        section_values=section_info["current_values"],
        section_metadata=section_info["metadata"],
        initial_field_hint=section_info["initial_field_hint"],
    )


@pytest.mark.asyncio
async def test_handle_switch_section_rejects_concurrent_switch():
    """A second switch while one is in flight returns success:false (bd 0c1) -- a
    manual click during an AI switch can't start two swaps."""
    service = FormFillingService()
    coordinator = AsyncMock()
    service._request_coordinator = coordinator
    service._session_id = "test-session"
    service._live_ai = _set_event_live_ai()
    coordinator.request_section_info.return_value = {
        "schema": {"fields": []},
        "current_values": {},
        "metadata": {"section_number": 2, "section_label": "P", "total_sections": 4},
        "initial_field_hint": "x",
    }

    # A still-running prior swap task blocks a new switch.
    async def _never():
        await asyncio.Event().wait()
    service._switch_task = asyncio.create_task(_never())
    try:
        result = await service.handle_switch_section("2")
        assert result["success"] is False
        assert "in progress" in result["message"].lower()
    finally:
        service._switch_task.cancel()


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
async def test_switch_to_section_threads_section_id_into_token_context():
    """bd polyglot-pdf-tb7: the active section id reaches set_session_context on switch.

    Previously start_session always passed current_section_id=None, so every
    token event logged a null section. switch_to_section must forward the new
    section's id (from section_metadata) so the token log carries a real section.
    """
    service = FormFillingService()

    live_ai = AsyncMock()
    service._live_ai = live_ai
    service._session_id = "test-session"
    service._websocket = AsyncMock()

    section_metadata = {
        "section_id": "part_2_1_personal",
        "section_number": 2,
        "total_sections": 3,
        "section_label": "Personal Information",
        "previous_spoken_names": [],
    }

    await service.switch_to_section(
        section_schema={"fields": []},
        section_values={},
        section_metadata=section_metadata,
        initial_field_hint=None,
    )

    # set_session_context should have been called with the new section id, not None.
    assert live_ai.set_session_context.called
    ctx_kwargs = live_ai.set_session_context.call_args.kwargs
    assert ctx_kwargs["current_section_id"] == "part_2_1_personal"


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


# ===========================================================================
# y4a keystone (bd polyglot-pdf-0c1): the swap must await the OLD loop's
# graceful close BEFORE starting the new session, and the switch_section
# FunctionResponse must be delivered on the old session (not orphaned by a
# self-cancel). These tests record call ORDER -- the old `.called`-only asserts
# could not catch the ordering bug.
# ===========================================================================

@pytest.mark.asyncio
async def test_swap_awaits_graceful_close_before_starting_new_session():
    """plan hazard 5: _complete_section_switch must await _closed_event (the old
    loop finished) BEFORE switch_to_section restarts the session -- otherwise two
    live receive loops could briefly share callbacks. We record the order of
    (closed_event awaited) vs (switch_to_section called)."""
    service = FormFillingService()
    coordinator = AsyncMock()
    service._request_coordinator = coordinator
    service._session_id = "s"

    order = []

    # An event that records WHEN it is awaited (resolves only after we set it).
    closed = asyncio.Event()

    class _RecordingWait:
        async def wait(self):
            order.append("awaited_closed_event")
            await closed.wait()

    live_ai = AsyncMock()
    live_ai.begin_graceful_shutdown = MagicMock(return_value=_RecordingWait())
    service._live_ai = live_ai

    async def _record_switch(**kwargs):
        order.append("switch_to_section")
    service.switch_to_section = _record_switch

    coordinator.request_section_info.return_value = {
        "schema": {"fields": []},
        "current_values": {},
        "metadata": {"section_number": 2, "section_label": "P", "total_sections": 4},
        "initial_field_hint": "x",
    }

    result = await service.handle_switch_section("2")
    assert result["success"] is True

    # The swap task is now waiting on the closed event. Release it.
    await asyncio.sleep(0)  # let the task reach the await
    closed.set()
    await service._switch_task

    assert order == ["awaited_closed_event", "switch_to_section"], (
        "switch_to_section must run AFTER the old loop's graceful close is awaited"
    )


@pytest.mark.asyncio
async def test_detached_swap_failure_notifies_frontend():
    """A detached swap task must NOT swallow exceptions silently -- a failed swap
    surfaces to the frontend as section_switch_failed (bd 0c1)."""
    service = FormFillingService()
    coordinator = AsyncMock()
    service._request_coordinator = coordinator
    service._session_id = "s"
    service._websocket = AsyncMock()

    ev = asyncio.Event()
    ev.set()
    live_ai = AsyncMock()
    live_ai.begin_graceful_shutdown = MagicMock(return_value=ev)
    service._live_ai = live_ai

    async def _boom(**kwargs):
        raise RuntimeError("swap exploded")
    service.switch_to_section = _boom

    coordinator.request_section_info.return_value = {
        "schema": {"fields": []},
        "current_values": {},
        "metadata": {"section_number": 2, "section_label": "P", "total_sections": 4},
        "initial_field_hint": "x",
    }

    await service.handle_switch_section("2")
    await service._switch_task  # detached task swallows the error internally

    # The frontend was told the switch failed (not left on a dead session).
    sent_types = [c.args[0].get("type") for c in service._websocket.send_json.call_args_list]
    assert "section_switch_failed" in sent_types
