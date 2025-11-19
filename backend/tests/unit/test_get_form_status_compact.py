"""
Unit tests for get_form_status compact response format.

Tests that get_form_status returns ultra-minimal token format:
field_id:value:status|field_id:value:status

Status indicators:
- ✓ = confirmed
- ✗ = unconfirmed (filled but not confirmed)
- − = empty
"""
import pytest
from unittest.mock import AsyncMock
from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import RequestCoordinator


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    return AsyncMock()


@pytest.fixture
def mock_coordinator():
    """Mock RequestCoordinator with form state."""
    coordinator = AsyncMock(spec=RequestCoordinator)
    coordinator.request_form_state_from_client = AsyncMock()
    return coordinator


@pytest.fixture
def callback_handler(mock_websocket, mock_coordinator):
    """Create CallbackHandler with mocked dependencies."""
    handler = CallbackHandler(
        websocket=mock_websocket,
        session_id="test_session",
        request_coordinator=mock_coordinator,
        send_transcript=False,
    )
    # Mock the injected method
    handler._request_form_state_from_client = AsyncMock()
    return handler


class TestGetFormStatusCompact:
    """Test suite for compact get_form_status responses."""

    @pytest.mark.asyncio
    async def test_compact_format_with_mixed_statuses(self, callback_handler):
        """Test compact format with confirmed, unconfirmed, and empty fields."""
        # Mock form state with mixed statuses
        callback_handler._request_form_state_from_client.return_value = {
            "firstName": {"value": "John", "confirmed": True},
            "lastName": {"value": "Doe", "confirmed": False},
            "email": {"value": "", "confirmed": False},
        }

        response = await callback_handler.on_tool_call(
            tool_name="get_form_status",
            arguments={"field_ids": ["firstName", "lastName", "email"]}
        )

        # Verify compact format
        assert "state" in response
        state = response["state"]

        # Should contain fields with values (email is empty so omitted)
        assert "firstName:John:confirmed" in state
        assert "lastName:Doe:unconfirmed" in state
        # Empty field should NOT be in response
        assert "email" not in state

        # Verify pipe separator (2 fields means 1 pipe)
        assert state.count("|") == 1

    @pytest.mark.asyncio
    async def test_compact_format_all_confirmed(self, callback_handler):
        """All confirmed fields should use 'confirmed'."""
        callback_handler._request_form_state_from_client.return_value = {
            "field1": {"value": "value1", "confirmed": True},
            "field2": {"value": "value2", "confirmed": True},
        }

        response = await callback_handler.on_tool_call(
            tool_name="get_form_status",
            arguments={"field_ids": ["field1", "field2"]}
        )

        state = response["state"]
        assert "field1:value1:confirmed" in state
        assert "field2:value2:confirmed" in state
        # Should not have unconfirmed markers
        assert "unconfirmed" not in state

    @pytest.mark.asyncio
    async def test_compact_format_all_unconfirmed(self, callback_handler):
        """Filled but unconfirmed fields should use 'unconfirmed'."""
        callback_handler._request_form_state_from_client.return_value = {
            "field1": {"value": "val1", "confirmed": False},
            "field2": {"value": "val2", "confirmed": False},
        }

        response = await callback_handler.on_tool_call(
            tool_name="get_form_status",
            arguments={"field_ids": ["field1", "field2"]}
        )

        state = response["state"]
        assert "field1:val1:unconfirmed" in state
        assert "field2:val2:unconfirmed" in state

    @pytest.mark.asyncio
    async def test_compact_format_all_empty(self, callback_handler):
        """Empty fields should be omitted from response."""
        callback_handler._request_form_state_from_client.return_value = {
            "field1": {"value": None, "confirmed": False},
            "field2": {"value": "", "confirmed": False},
        }

        response = await callback_handler.on_tool_call(
            tool_name="get_form_status",
            arguments={"field_ids": ["field1", "field2"]}
        )

        state = response["state"]
        # All fields empty - should return "No fields filled"
        assert state == "No fields filled"

    @pytest.mark.asyncio
    async def test_token_efficiency(self, callback_handler):
        """Verify compact format uses fewer tokens than JSON."""
        # 5 fields - 4 with values, 1 empty (should be omitted)
        callback_handler._request_form_state_from_client.return_value = {
            "p1_line1_firstname": {"value": "John", "confirmed": True},
            "p1_line1_lastname": {"value": "Doe", "confirmed": True},
            "p1_line1_middlename": {"value": "", "confirmed": False},
            "p1_line1_aliennumber": {"value": "123456789", "confirmed": False},
            "p1_line1_ssn": {"value": "987-65-4321", "confirmed": True},
        }

        response = await callback_handler.on_tool_call(
            tool_name="get_form_status",
            arguments={"field_ids": ["p1_line1_firstname", "p1_line1_lastname",
                                      "p1_line1_middlename", "p1_line1_aliennumber", "p1_line1_ssn"]}
        )

        state = response["state"]

        # Compact format should be a single string
        assert isinstance(state, str)

        # Verify it contains data for filled fields
        assert "p1_line1_firstname:John:confirmed" in state
        assert "p1_line1_lastname:Doe:confirmed" in state
        assert "p1_line1_aliennumber:123456789:unconfirmed" in state
        assert "p1_line1_ssn:987-65-4321:confirmed" in state

        # Empty middlename should NOT be in response
        assert "p1_line1_middlename" not in state

        # Count separators (should be 3 pipes for 4 fields with values)
        assert state.count("|") == 3
