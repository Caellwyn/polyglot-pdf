"""
Unit tests for confirm_field tool handler.

Tests that the confirm_field tool:
1. Marks fields as confirmed in frontend state
2. Logs confirmation events (anonymized, no PII)
3. Returns next field hint
4. Handles both verbal and manual confirmation methods
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import RequestCoordinator


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def mock_coordinator():
    """Mock RequestCoordinator."""
    coordinator = AsyncMock(spec=RequestCoordinator)
    coordinator.request_next_field_hint = AsyncMock(return_value="Next, please provide your last name")
    return coordinator


@pytest.fixture
def callback_handler(mock_websocket, mock_coordinator):
    """Create CallbackHandler with mocked dependencies."""
    handler = CallbackHandler(
        websocket=mock_websocket,
        session_id="test_session_123",
        request_coordinator=mock_coordinator,
        send_transcript=False,
        form_id="I-90",
        form_session_id="fss_test_12345"
    )
    return handler


class TestConfirmFieldTool:
    """Test suite for confirm_field tool handler."""

    @pytest.mark.asyncio
    async def test_verbal_confirmation_success(self, callback_handler, mock_websocket, mock_coordinator):
        """Verbal confirmation (user said 'yes') should mark field as confirmed."""
        response = await callback_handler.on_tool_call(
            tool_name="confirm_field",
            arguments={
                "field_id": "p1_line1_firstname",
                "confirmation_method": "verbal"
            }
        )

        # Verify tool response to Gemini
        assert response["success"] is True
        assert response["field_confirmed"] == "p1_line1_firstname"
        assert "next_field_hint" in response
        assert response["next_field_hint"] == "Next, please provide your last name"

        # Verify WebSocket message sent to frontend
        mock_websocket.send_json.assert_called()
        calls = mock_websocket.send_json.call_args_list
        confirm_call = [call for call in calls if call[0][0]["type"] == "confirm_field"]
        assert len(confirm_call) > 0
        assert confirm_call[0][0][0]["field_id"] == "p1_line1_firstname"
        assert confirm_call[0][0][0]["confirmation_method"] == "verbal"

        # Verify next field hint was requested
        mock_coordinator.request_next_field_hint.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_confirmation_success(self, callback_handler, mock_websocket):
        """Manual confirmation (user edited field) should mark field as confirmed."""
        response = await callback_handler.on_tool_call(
            tool_name="confirm_field",
            arguments={
                "field_id": "p1_line1_lastname",
                "confirmation_method": "manual"
            }
        )

        # Verify tool response
        assert response["success"] is True
        assert response["field_confirmed"] == "p1_line1_lastname"

        # Verify WebSocket message
        calls = mock_websocket.send_json.call_args_list
        confirm_call = [call for call in calls if call[0][0]["type"] == "confirm_field"]
        assert confirm_call[0][0][0]["confirmation_method"] == "manual"

    @pytest.mark.asyncio
    async def test_confirmation_logging_called(self, callback_handler, mock_websocket):
        """Confirmation should be logged with form_id and form_session_id."""
        with patch('backend.services.callback_handler.log_field_confirmation') as mock_log:
            await callback_handler.on_tool_call(
                tool_name="confirm_field",
                arguments={
                    "field_id": "p1_line1_aliennumber",
                    "confirmation_method": "verbal"
                }
            )

            # Verify logging was called with correct parameters
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1] if mock_log.call_args[1] else {}
            call_args = mock_log.call_args[0] if mock_log.call_args[0] else ()

            # Check either positional or keyword args
            if call_kwargs:
                assert call_kwargs["form_id"] == "I-90"
                assert call_kwargs["form_session_id"] == "fss_test_12345"
                assert call_kwargs["field_id"] == "p1_line1_aliennumber"
                assert call_kwargs["confirmation_method"] == "verbal"
            else:
                assert "I-90" in call_args
                assert "fss_test_12345" in call_args
                assert "p1_line1_aliennumber" in call_args
                assert "verbal" in call_args

    @pytest.mark.asyncio
    async def test_next_field_hint_returned(self, callback_handler, mock_coordinator):
        """Response should include next_field_hint from coordinator."""
        mock_coordinator.request_next_field_hint = AsyncMock(
            return_value="Next, please provide your date of birth"
        )

        response = await callback_handler.on_tool_call(
            tool_name="confirm_field",
            arguments={
                "field_id": "p1_line1_middlename",
                "confirmation_method": "verbal"
            }
        )

        assert response["next_field_hint"] == "Next, please provide your date of birth"

    @pytest.mark.asyncio
    async def test_all_fields_confirmed_message(self, callback_handler, mock_coordinator):
        """When next_field_hint is None, message should indicate all fields confirmed."""
        mock_coordinator.request_next_field_hint = AsyncMock(return_value=None)

        response = await callback_handler.on_tool_call(
            tool_name="confirm_field",
            arguments={
                "field_id": "p1_line1_signature",
                "confirmation_method": "verbal"
            }
        )

        assert response["success"] is True
        assert "All fields confirmed" in response["message"]

    @pytest.mark.asyncio
    async def test_none_coordinator_does_not_signal_completion(self, mock_websocket):
        """A None coordinator must NOT crash and must NOT report completion.

        request_coordinator is a required positional, so it is never None in
        production -- but a test or racing reconnect could pass None. An absent
        coordinator means "next field unknown", which is the timeout semantics
        (NOT "All fields confirmed") -- reporting completion here would let Gemini
        wrap the form up early (the failure class bd polyglot-pdf-tks guards).
        Mirrors the existing send_form_update guard (bd polyglot-pdf-pen).
        """
        handler = CallbackHandler(
            websocket=mock_websocket,
            session_id="test_session",
            request_coordinator=None,  # the guarded condition
            send_transcript=False,
            form_id="I-90",
            form_session_id="fss_test_12345",
        )

        response = await handler.on_tool_call(
            tool_name="confirm_field",
            arguments={
                "field_id": "p1_line1_firstname",
                "confirmation_method": "verbal",
            },
        )

        # Confirms the field, but does NOT claim the form is complete, and does
        # NOT leak a non-serializable sentinel onto the wire.
        assert response["success"] is True
        assert response["field_confirmed"] == "p1_line1_firstname"
        assert "All fields confirmed" not in response["message"]
        assert response["next_field_hint"] is None  # sentinel collapsed for the wire

    @pytest.mark.asyncio
    async def test_no_logging_without_form_ids(self, mock_websocket, mock_coordinator):
        """Confirmation logging should not crash if form_id/form_session_id are missing."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            session_id="test_session",
            request_coordinator=mock_coordinator,
            send_transcript=False,
            form_id=None,  # Missing form_id
            form_session_id=None  # Missing form_session_id
        )

        with patch('backend.services.callback_handler.log_field_confirmation') as mock_log:
            response = await handler.on_tool_call(
                tool_name="confirm_field",
                arguments={
                    "field_id": "test_field",
                    "confirmation_method": "verbal"
                }
            )

            # Should still succeed but logging should not be called
            assert response["success"] is True
            mock_log.assert_not_called()
