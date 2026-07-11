"""
Unit tests for the switch_to_field tool handler (bd polyglot-pdf-jnjj.36).

switch_to_field is FIELD-level navigation: the principal jumps focus to one
specific field (the correction path, and the "act on an ask_secretary answer
that named a field" path). It mirrors skip_field's synchronous round-trip:
the frontend resolves the identifier (field_id or exact spoken name), pins
the field for its next-field computation, and acks with the target's hint +
(DTI) schema. Unlike switch_section the Gemini session is NOT restarted.

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
    # Default: the FE resolved + pinned the field. Failure-path tests override.
    coordinator.request_switch_field = AsyncMock(
        return_value={
            "found": True,
            "field_id": "p1_line6f_zipcode",
            "spoken_name": "mailing zip code",
            "next_field_hint": "Next field to fill is #9: 'mailing zip code'",
            "already_confirmed": False,
            "has_value": False,
        }
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


class TestSwitchToFieldTool:
    @pytest.mark.asyncio
    async def test_success_names_the_field_and_prompts_to_ask(
        self, callback_handler, mock_coordinator
    ):
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field",
            arguments={"field": "p1_line6f_zipcode"},
        )
        mock_coordinator.request_switch_field.assert_awaited_once_with(
            "p1_line6f_zipcode")
        assert response["success"] is True
        assert "mailing zip code" in response["message"]
        assert "unanswered" in response["message"]

    @pytest.mark.asyncio
    async def test_success_with_value_carries_current_value(
        self, callback_handler, mock_coordinator
    ):
        """A jump onto a filled field returns the value so the model can read
        it back (same Gemini trust boundary as get_field_value)."""
        mock_coordinator.request_switch_field.return_value = {
            "found": True, "field_id": "p1_line6f_zipcode",
            "spoken_name": "mailing zip code",
            "already_confirmed": True, "has_value": True, "value": "73701",
        }
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "mailing zip code"},
        )
        assert response["success"] is True
        assert response["current_value"] == "73701"
        assert "confirmed answer" in response["message"]

    @pytest.mark.asyncio
    async def test_dti_schema_renders_guidance_and_repoints_validation(
        self, callback_handler, mock_coordinator
    ):
        """In DTI mode the ack carries the target's schema: the handler must
        merge it (validation + current-field coercion pointer) and return its
        rendered guidance so the model asks about THAT field."""
        merge = MagicMock()
        callback_handler.set_tool_handlers(
            handle_update_fields=MagicMock(),
            handle_switch_section=AsyncMock(),
            handle_get_field_value=AsyncMock(),
            request_form_state_from_client=AsyncMock(),
            merge_field_schema=merge,
        )
        mock_coordinator.request_switch_field.return_value = {
            "found": True, "field_id": "p1_line6f_zipcode",
            "spoken_name": "mailing zip code",
            "already_confirmed": False, "has_value": False,
            "next_field_schema": {
                "id": "p1_line6f_zipcode", "name": "mailing zip code",
                "type": "text",
            },
        }
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "p1_line6f_zipcode"},
        )
        assert response["success"] is True
        merge.assert_called_once()
        assert merge.call_args[0][0]["id"] == "p1_line6f_zipcode"
        assert response.get("field_guidance")  # rendered, non-empty

    @pytest.mark.asyncio
    async def test_empty_identifier_fails_without_round_trip(
        self, callback_handler, mock_coordinator
    ):
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "  "},
        )
        assert response["success"] is False
        mock_coordinator.request_switch_field.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_timeout_is_not_reported_as_success(
        self, callback_handler, mock_coordinator
    ):
        """A frontend timeout must NOT read as a completed jump -- the model is
        told to continue with the current field."""
        mock_coordinator.request_switch_field.return_value = CONFIRM_REQUEST_TIMEOUT
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "p1_line6f_zipcode"},
        )
        assert response["success"] is False
        assert "did not respond" in response["message"]

    @pytest.mark.asyncio
    async def test_unknown_field_suggests_secretary(
        self, callback_handler, mock_coordinator
    ):
        mock_coordinator.request_switch_field.return_value = {
            "found": False, "reason": "unknown_field",
        }
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "no such thing"},
        )
        assert response["success"] is False
        assert "ask_secretary" in response["message"]

    @pytest.mark.asyncio
    async def test_other_section_names_the_section_and_suggests_switch_section(
        self, callback_handler, mock_coordinator
    ):
        """Section-scoped modes: an out-of-section target is unreachable in the
        current session; the model is pointed at switch_section (sections and
        fields stay distinct units, CLAUDE.md scar #5)."""
        mock_coordinator.request_switch_field.return_value = {
            "found": False, "reason": "other_section",
            "field_id": "p6_line1_familyname",
            "section_label": "Interpreter's Name", "section_order": 6,
        }
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "p6_line1_familyname"},
        )
        assert response["success"] is False
        assert "switch_section" in response["message"]
        assert "Interpreter's Name" in response["message"]

    @pytest.mark.asyncio
    async def test_hidden_field_is_not_navigable(
        self, callback_handler, mock_coordinator
    ):
        mock_coordinator.request_switch_field.return_value = {
            "found": False, "reason": "hidden", "field_id": "p1_line5a",
        }
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "p1_line5a"},
        )
        assert response["success"] is False
        assert "hidden" in response["message"]


class TestRequestSwitchFieldCoordinator:
    @pytest.mark.asyncio
    async def test_round_trip_resolves_with_payload(self, mock_websocket):
        coordinator = RequestCoordinator(mock_websocket, session_id="s1")
        import asyncio

        async def respond_soon():
            await asyncio.sleep(0.01)
            sent = mock_websocket.send_json.call_args[0][0]
            assert sent["type"] == "switch_field"
            assert sent["field"] == "mailing zip code"
            coordinator.handle_switch_field_response(
                sent["request_id"],
                {"found": True, "field_id": "p1_line6f_zipcode"},
            )

        task = asyncio.ensure_future(respond_soon())
        result = await coordinator.request_switch_field("mailing zip code")
        await task
        assert result == {"found": True, "field_id": "p1_line6f_zipcode"}

    @pytest.mark.asyncio
    async def test_no_websocket_is_timeout_sentinel(self):
        coordinator = RequestCoordinator(None, session_id="s1")
        result = await coordinator.request_switch_field("anything")
        assert result is CONFIRM_REQUEST_TIMEOUT

    @pytest.mark.asyncio
    async def test_send_failure_is_timeout_sentinel(self, mock_websocket):
        mock_websocket.send_json = AsyncMock(side_effect=RuntimeError("closed"))
        coordinator = RequestCoordinator(mock_websocket, session_id="s1")
        result = await coordinator.request_switch_field("anything")
        assert result is CONFIRM_REQUEST_TIMEOUT
