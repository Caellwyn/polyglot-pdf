"""
Unit tests for the skip_field tool handler (bd polyglot-pdf-7yra).

skip_field lets the voice assistant force-skip a REQUIRED field the user cannot
answer right now (distinct from marking a field not-applicable). It mirrors
confirm_field's synchronous round-trip: the frontend records the skip
(markFieldSkipped) and acks; a skipped field satisfies the section, so the
handler advances (next-field hint or section-boundary short-circuit) exactly like
a confirm.

ASCII only.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import (
    CONFIRM_REQUEST_TIMEOUT,
    RequestCoordinator,
)


@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def mock_coordinator():
    coordinator = AsyncMock(spec=RequestCoordinator)
    coordinator.request_next_field_hint = AsyncMock(
        return_value="Next, please provide your last name"
    )
    # Default: the FE recorded the skip. Failure-path tests override.
    coordinator.request_skip_field = AsyncMock(
        return_value={"recorded": True, "reason": None, "section_complete": False}
    )
    return coordinator


@pytest.fixture
def callback_handler(mock_websocket, mock_coordinator):
    return CallbackHandler(
        websocket=mock_websocket,
        session_id="test_session_123",
        request_coordinator=mock_coordinator,
        send_transcript=False,
        form_id="I-90",
        form_session_id="fss_test_12345",
    )


class TestSkipFieldTool:
    @pytest.mark.asyncio
    async def test_skip_success_records_and_advances(self, callback_handler, mock_coordinator):
        """A recorded skip returns success, echoes the field, and advances to the
        next field via the hint (the skip satisfies the field)."""
        response = await callback_handler.on_tool_call(
            tool_name="skip_field",
            arguments={"field_id": "p1_uscis_number"},
        )

        assert response["success"] is True
        assert response["field_skipped"] == "p1_uscis_number"
        assert response["next_field_hint"] == "Next, please provide your last name"

        mock_coordinator.request_skip_field.assert_awaited_once_with("p1_uscis_number")
        # Recorded path advances -> asks for the next field hint.
        mock_coordinator.request_next_field_hint.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skip_not_recorded_returns_failure(self, callback_handler, mock_coordinator):
        """When the FE reports the skip was NOT recorded, the tool returns a
        failure envelope (not success) so Gemini re-asks rather than confabulating
        a skip, and does NOT advance."""
        mock_coordinator.request_skip_field = AsyncMock(
            return_value={"recorded": False, "reason": "unknown_field"}
        )

        response = await callback_handler.on_tool_call(
            tool_name="skip_field",
            arguments={"field_id": "ghost"},
        )

        assert response.get("success") is not True
        mock_coordinator.request_next_field_hint.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_timeout_returns_failure(self, callback_handler, mock_coordinator):
        """A round-trip timeout (the sentinel) must NOT be read as a recorded skip;
        the tool returns failure and does not advance."""
        mock_coordinator.request_skip_field = AsyncMock(
            return_value=CONFIRM_REQUEST_TIMEOUT
        )

        response = await callback_handler.on_tool_call(
            tool_name="skip_field",
            arguments={"field_id": "p1_uscis_number"},
        )

        assert response.get("success") is not True
        mock_coordinator.request_next_field_hint.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_section_boundary_short_circuits_hint(self, callback_handler, mock_coordinator):
        """When the skip completes the section (FE signals section_complete), the
        handler SKIPS the racing next-field-hint round-trip (bd njvh parity)."""
        mock_coordinator.request_skip_field = AsyncMock(
            return_value={"recorded": True, "reason": None, "section_complete": True}
        )

        response = await callback_handler.on_tool_call(
            tool_name="skip_field",
            arguments={"field_id": "p1_uscis_number"},
        )

        assert response["success"] is True
        assert response["field_skipped"] == "p1_uscis_number"
        # Section boundary: no next-field-hint request (it would race the FE's
        # section-switch teardown).
        mock_coordinator.request_next_field_hint.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_field_arg_is_read(self, callback_handler, mock_coordinator):
        """The handler reads the declared 'field_id' arg and passes it verbatim to
        the coordinator (a rename of the key would break this)."""
        await callback_handler.on_tool_call(
            tool_name="skip_field",
            arguments={"field_id": "p2_checkbox3"},
        )
        mock_coordinator.request_skip_field.assert_awaited_once_with("p2_checkbox3")
