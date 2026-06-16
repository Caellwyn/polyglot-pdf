"""Integration coverage for the adapter's parts-path tool-call sequence through a
REAL CallbackHandler, plus the duplicate-FunctionResponse dedup (bd polyglot-pdf-ux15).

The existing PR #121 regression tests inject a BARE on_tool_call lambda, so they
lock the adapter's append/echo logic but bypass CallbackHandler entirely. These
tests instead drive a REAL CallbackHandler (its on_tool_call) and then run the
result through the adapter's actual wire-build helpers (_build_function_response +
_dedupe_responses_by_id) -- the same sequence the model_turn.parts path runs at
backend/adapters/live_ai_gemini.py -- so the
adapter -> CallbackHandler -> coordinator -> response-body -> FunctionResponse chain
is locked end to end (the call id echoed, the body well-formed, no duplicates).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import WebSocket

from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import RequestCoordinator
from backend.adapters.live_ai_gemini import (
    _build_function_response,
    _dedupe_responses_by_id,
)


@pytest.fixture
def real_callback_handler():
    """A REAL CallbackHandler with a mocked coordinator + tool handlers (mirrors the
    fixtures in test_callback_handler.py)."""
    ws = MagicMock(spec=WebSocket)
    ws.send_json = AsyncMock()
    ws.send_bytes = AsyncMock()

    coordinator = MagicMock(spec=RequestCoordinator)
    coordinator.request_next_field_hint = AsyncMock(return_value="last name")
    coordinator.request_confirm_field = AsyncMock(
        return_value={"recorded": True, "reason": None}
    )

    handler = CallbackHandler(
        websocket=ws,
        request_coordinator=coordinator,
        session_id="test-parts-path",
    )
    handler.set_tool_handlers(
        handle_update_fields=MagicMock(return_value={
            "form_state": {"firstName": "Ada"},
            "applied_fields": ["firstName"],
            "unknown_fields": [],
            "validation_errors": [],
        }),
        handle_switch_section=AsyncMock(return_value={"success": True}),
        handle_get_field_value=AsyncMock(return_value={"found": True, "value": "x"}),
        request_form_state_from_client=AsyncMock(return_value={}),
        get_next_field_schema_for_jit=MagicMock(return_value=None),
    )
    return handler


def _parts_path_emit(handler_result, call_id):
    """Reproduce the model_turn.parts tail: a recorded tool result becomes a
    FunctionResponse echoing the call id (live_ai_gemini.py:_build_function_response),
    collected into the per-event responses list, then deduped before the flush."""
    responses = []
    if handler_result is None:
        handler_result = {}
    # The parts path appends for any named tool (tks: every named call gets a response).
    responses.append(_build_function_response("update_form_fields", handler_result, call_id))
    deduped, dropped = _dedupe_responses_by_id(responses)
    return deduped, dropped


class TestPartsPathThroughRealCallbackHandler:
    @pytest.mark.asyncio
    async def test_update_via_real_handler_builds_response_with_echoed_id(self, real_callback_handler):
        # Drive the REAL CallbackHandler exactly as the parts path does.
        result = await real_callback_handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"field_id": "firstName", "value": "Ada"},
        )

        # The handler produced a real, well-formed tool response body.
        assert result["success"] is True
        assert "firstName" in result["applied_fields"]

        # That body flows through the adapter's wire-build with the call id echoed.
        responses, dropped = _parts_path_emit(result, "function-call-abc123")
        assert dropped == []
        assert len(responses) == 1
        fr = responses[0]
        assert fr.name == "update_form_fields"
        assert fr.id == "function-call-abc123"  # bd 0ux: AI-Studio REQUIRES the echoed id
        assert fr.response["success"] is True

    @pytest.mark.asyncio
    async def test_unknown_tool_via_real_handler_still_emits_a_response(self, real_callback_handler):
        # tks invariant: even an unknown tool gets a (non-dropping) FunctionResponse,
        # so Gemini never blocks waiting on an unanswered call.
        result = await real_callback_handler.on_tool_call(
            tool_name="not_a_real_tool",
            arguments={},
        )
        responses, dropped = _parts_path_emit(result, "function-call-zzz")
        assert dropped == []
        assert len(responses) == 1
        assert responses[0].id == "function-call-zzz"


class TestDedupeResponsesById:
    def test_drops_a_second_response_for_the_same_call_id(self):
        # The defended-against case: one call id reaching BOTH adapter paths.
        a = _build_function_response("update_form_fields", {"success": True}, "id-1")
        b = _build_function_response("update_form_fields", {"success": True}, "id-1")
        deduped, dropped = _dedupe_responses_by_id([a, b])
        assert len(deduped) == 1
        assert deduped[0] is a  # first wins
        assert dropped == ["id-1"]

    def test_distinct_ids_are_all_kept(self):
        a = _build_function_response("update_form_fields", {}, "id-1")
        b = _build_function_response("confirm_field", {}, "id-2")
        deduped, dropped = _dedupe_responses_by_id([a, b])
        assert len(deduped) == 2
        assert dropped == []

    def test_id_less_responses_are_never_deduped(self):
        # A genuinely id-less call cannot be a duplicate-by-id -> always kept.
        a = _build_function_response("update_form_fields", {}, None)
        b = _build_function_response("update_form_fields", {}, None)
        deduped, dropped = _dedupe_responses_by_id([a, b])
        assert len(deduped) == 2
        assert dropped == []

    def test_empty_list_is_safe(self):
        deduped, dropped = _dedupe_responses_by_id([])
        assert deduped == []
        assert dropped == []
