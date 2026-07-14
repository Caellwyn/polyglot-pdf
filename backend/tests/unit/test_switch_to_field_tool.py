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
        it back (same Gemini trust boundary as ask_secretary)."""
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
    async def test_unknown_field_tells_model_to_use_spoken_name(
        self, callback_handler, mock_coordinator
    ):
        """An unresolved identifier with no secretary handler wired and no
        algorithmic candidates in the ack degrades to the bare clarify message
        (tier 4 of _switch_degrade_response; bd polyglot-pdf-y76q). This
        fixture's CallbackHandler has no handle_ask_secretary injected, so
        _resolve_field_via_secretary short-circuits to None and there is
        nothing to suggest."""
        mock_coordinator.request_switch_field.return_value = {
            "found": False, "reason": "unknown_field",
        }
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "no such thing"},
        )
        assert response["success"] is False
        assert "could not find" in response["message"].lower()
        assert "describe" in response["message"].lower()

    @pytest.mark.asyncio
    async def test_unknown_field_lists_candidate_spoken_names(
        self, callback_handler, mock_coordinator
    ):
        """When the ack carries nearest candidates, their spoken names are listed
        so the model can retry with one it can resolve exactly (bd
        polyglot-pdf-3vby)."""
        mock_coordinator.request_switch_field.return_value = {
            "found": False, "reason": "unknown_field",
            "candidates": [
                {"field_id": "p1_line6b_streetnumbername", "spoken_name": "mailing street address"},
                {"field_id": "p1_line6d_cityortown", "spoken_name": "mailing city"},
            ],
        }
        response = await callback_handler.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "mailing street"},
        )
        assert response["success"] is False
        assert "mailing street address" in response["message"]
        assert "mailing city" in response["message"]

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


class TestSwitchToFieldSecretaryResolution:
    """switch_to_field resolves vague prose via the secretary internally, then
    re-attempts the switch -- one voice turn, not three (bd polyglot-pdf-y76q).
    On an EXACT-resolver miss the handler asks the injected ask_secretary handler
    to identify the field, and degrades gracefully (never hangs, never a silent
    wrong-field fill) when it cannot."""

    def _handler(self, switch_side_effect, ask_secretary):
        ws = AsyncMock()
        coordinator = AsyncMock(spec=RequestCoordinator)
        coordinator.request_switch_field = AsyncMock(side_effect=switch_side_effect)
        h = CallbackHandler(
            websocket=ws, session_id="s1", request_coordinator=coordinator,
        )
        h.set_tool_handlers(
            handle_update_fields=MagicMock(),
            handle_switch_section=AsyncMock(),
            request_form_state_from_client=AsyncMock(return_value={}),
            handle_ask_secretary=ask_secretary,
        )
        return h, coordinator

    @pytest.mark.asyncio
    async def test_prose_miss_resolved_by_secretary_then_switches(self):
        """Exact resolver misses the prose; the secretary identifies the field;
        the handler re-attempts the switch with the exact id and succeeds -- in
        ONE tool call (one voice turn)."""
        # First call (the vague prose) misses; second call (the secretary's id) hits.
        switch = [
            {"found": False, "reason": "unknown_field", "candidates": []},
            {"found": True, "field_id": "p1_line2_acctidentifier",
             "spoken_name": "USCIS account number", "has_value": False},
        ]
        ask = AsyncMock(return_value={
            "status": "ok",
            "answer": "That's the USCIS account number.",
            "resolved": True,
            "sources": [{"field_id": "p1_line2_acctidentifier",
                         "spoken_name": "USCIS account number"}],
        })
        h, coordinator = self._handler(switch, ask)

        result = await h.on_tool_call(
            tool_name="switch_to_field",
            arguments={"field": "that government id thing with 12 digits"},
        )

        assert result["success"] is True
        assert "USCIS account number" in result["message"]
        # Two switch attempts: the prose (miss) then the secretary's exact id (hit).
        assert coordinator.request_switch_field.await_count == 2
        assert coordinator.request_switch_field.await_args_list[1].args[0] == \
            "p1_line2_acctidentifier"
        ask.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_secretary_pushback_degrades_to_clarify(self):
        """When the secretary deliberately cannot identify a field (resolved
        False), the handler voices the secretary's clarify prose -- no switch, no
        hang."""
        switch = [{"found": False, "reason": "unknown_field", "candidates": []}]
        ask = AsyncMock(return_value={
            "status": "ok",
            "answer": "I could not find a 12-digit government ID field.",
            "resolved": False,
            "sources": [],
        })
        h, coordinator = self._handler(switch, ask)

        result = await h.on_tool_call(
            tool_name="switch_to_field",
            arguments={"field": "the thing with twelve digits"},
        )

        assert result["success"] is False
        assert "could not find a 12-digit government ID field" in result["message"]
        assert "describe" in result["message"].lower()
        # Only the initial prose attempt -- no second switch on a pushback.
        assert coordinator.request_switch_field.await_count == 1

    @pytest.mark.asyncio
    async def test_secretary_multiple_candidates_degrades_to_did_you_mean(self):
        """Several plausible fields (a genuinely ambiguous 'go back to the name')
        that do not land directly -> a 'Did you mean ...?' pick-list."""
        # The secretary's top pick fails to navigate (e.g. raced hidden), so we
        # degrade to the candidate list rather than switching blindly.
        switch = [
            {"found": False, "reason": "unknown_field", "candidates": []},
            {"found": False, "reason": "hidden", "field_id": "p1_line3a_familyname"},
        ]
        ask = AsyncMock(return_value={
            "status": "ok",
            "answer": "Could be the family name or the given name.",
            "resolved": True,
            "sources": [
                {"field_id": "p1_line3a_familyname", "spoken_name": "family name"},
                {"field_id": "p1_line3b_givenname", "spoken_name": "given name"},
            ],
        })
        h, coordinator = self._handler(switch, ask)

        result = await h.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "the name"},
        )

        assert result["success"] is False
        assert "Did you mean" in result["message"]
        assert "family name" in result["message"]
        assert "given name" in result["message"]

    @pytest.mark.asyncio
    async def test_secretary_pending_degrades_to_algorithmic_candidates(self):
        """A secretary lookup that blows its deadline (status 'pending') loses the
        fields list, so the handler falls back to the frontend's algorithmic
        candidate matcher (the ack's candidates) -- 'Did you mean ...?'."""
        switch = [{
            "found": False, "reason": "unknown_field",
            "candidates": [
                {"field_id": "p1_line6d_cityortown", "spoken_name": "mailing city"},
                {"field_id": "p1_line6f_zipcode", "spoken_name": "mailing zip code"},
            ],
        }]
        ask = AsyncMock(return_value={"status": "pending", "answer": "", "sources": []})
        h, coordinator = self._handler(switch, ask)

        result = await h.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "the mailing thing"},
        )

        assert result["success"] is False
        assert "Did you mean" in result["message"]
        assert "mailing city" in result["message"]
        assert coordinator.request_switch_field.await_count == 1

    @pytest.mark.asyncio
    async def test_no_secretary_handler_still_degrades_to_candidates(self):
        """With no ask_secretary handler injected, an exact miss still degrades to
        the algorithmic candidate list -- the secretary path is optional."""
        switch = [{
            "found": False, "reason": "unknown_field",
            "candidates": [
                {"field_id": "p1_line6d_cityortown", "spoken_name": "mailing city"},
            ],
        }]
        ws = AsyncMock()
        coordinator = AsyncMock(spec=RequestCoordinator)
        coordinator.request_switch_field = AsyncMock(side_effect=switch)
        h = CallbackHandler(websocket=ws, session_id="s1",
                            request_coordinator=coordinator)
        # No set_tool_handlers -> _handle_ask_secretary stays None.
        result = await h.on_tool_call(
            tool_name="switch_to_field", arguments={"field": "the mailing thing"},
        )
        assert result["success"] is False
        assert "Did you mean" in result["message"]
        assert "mailing city" in result["message"]
