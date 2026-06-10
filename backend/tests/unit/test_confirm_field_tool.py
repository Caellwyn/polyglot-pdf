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
from backend.services.request_coordinator import (
    CONFIRM_REQUEST_TIMEOUT,
    RequestCoordinator,
)


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
    # confirm_field is now a synchronous round-trip (bd polyglot-pdf-wpw.2): the FE
    # acks whether it recorded the confirmation. Default to "recorded" so the
    # success-path tests below exercise the happy path; failure-path tests override.
    coordinator.request_confirm_field = AsyncMock(
        return_value={"recorded": True, "reason": None}
    )
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

        # The confirm request now flows through the coordinator round-trip
        # (bd polyglot-pdf-wpw.2), not a fire-and-forget websocket.send_json.
        mock_coordinator.request_confirm_field.assert_called_once_with(
            "p1_line1_firstname", "verbal"
        )

        # Verify next field hint was requested (recorded path advances)
        mock_coordinator.request_next_field_hint.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_confirmation_success(self, callback_handler, mock_websocket, mock_coordinator):
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

        # The confirm request flows through the coordinator with the method.
        mock_coordinator.request_confirm_field.assert_called_once_with(
            "p1_line1_lastname", "manual"
        )

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


class TestConfirmFieldFailsWhenNotRecorded:
    """The synchronous confirm round-trip (bd polyglot-pdf-wpw.2 / WS-E2): when the
    frontend reports the confirm was NOT recorded (empty field) -- or never answers
    -- the tool must return success:false so Gemini re-asks IN-BAND, instead of the
    old always-success that let 3.1's confirm-without-fill skip lose the value.

    RED-FIRST: against the pre-wpw.2 backend, an empty-field confirm returned
    success:True; these assert the opposite.
    """

    @pytest.mark.asyncio
    async def test_empty_field_confirm_returns_failure(self, callback_handler, mock_coordinator):
        """FE acks recorded:false (no_value) -> success:false + corrective message,
        and the next-field hint is NOT requested (we did not advance)."""
        mock_coordinator.request_confirm_field = AsyncMock(
            return_value={"recorded": False, "reason": "no_value"}
        )

        response = await callback_handler.on_tool_call(
            tool_name="confirm_field",
            arguments={"field_id": "p1_line1_firstname", "confirmation_method": "verbal"},
        )

        assert response["success"] is False
        assert response["field_confirmed"] is None
        # WS-C2 envelope shape so Gemini reads it as a real failure.
        assert response["status"] == "error"
        assert response.get("error")
        # Corrective guidance tells Gemini to collect the value first.
        assert "no value" in response["message"].lower()
        assert "update_form_fields" in response["message"]
        # We did NOT advance -- no next-field hint requested on a failed confirm.
        mock_coordinator.request_next_field_hint.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_timeout_returns_failure_not_completion(self, callback_handler, mock_coordinator):
        """A slow/disconnected client (CONFIRM_REQUEST_TIMEOUT) must read as
        not-confirmed + keep-going, NEVER as a successful confirm or completion."""
        mock_coordinator.request_confirm_field = AsyncMock(
            return_value=CONFIRM_REQUEST_TIMEOUT
        )

        response = await callback_handler.on_tool_call(
            tool_name="confirm_field",
            arguments={"field_id": "p1_line1_firstname", "confirmation_method": "verbal"},
        )

        assert response["success"] is False
        assert response["status"] == "error"
        # Must NOT claim the form is done.
        assert "do not assume" in response["message"].lower()
        mock_coordinator.request_next_field_hint.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_confirm_does_not_log_confirmation(self, callback_handler, mock_coordinator):
        """A confirmation that did not happen must NOT be logged."""
        mock_coordinator.request_confirm_field = AsyncMock(
            return_value={"recorded": False, "reason": "no_value"}
        )

        with patch('backend.services.callback_handler.log_field_confirmation') as mock_log:
            await callback_handler.on_tool_call(
                tool_name="confirm_field",
                arguments={"field_id": "p1_line1_firstname", "confirmation_method": "verbal"},
            )
            mock_log.assert_not_called()
