"""
Tests for request_coordinator module.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

# Import via the SAME package path the runtime uses (backend.services.*) so the
# HINT_REQUEST_TIMEOUT singleton is the identical object the production code
# compares against. The bare `services.request_coordinator` path resolves to a
# DIFFERENT module object under pytest's pythonpath, which would make every
# `is HINT_REQUEST_TIMEOUT` identity check silently false (fresh-eyes, PR #121).
from backend.services.request_coordinator import (
    CONFIRM_REQUEST_TIMEOUT,
    HINT_REQUEST_TIMEOUT,
    RequestCoordinator,
)


class TestRequestCoordinatorInit:
    """Tests for RequestCoordinator initialization."""
    
    def test_init_with_websocket(self):
        """Should initialize with provided websocket."""
        mock_ws = MagicMock()
        coordinator = RequestCoordinator(websocket=mock_ws, session_id="test-session")
        
        assert coordinator._websocket is mock_ws
        assert coordinator._session_id == "test-session"
        # bd polyglot-pdf-bxw: pending requests now live in ONE keyed map.
        assert coordinator._pending == {}
    
    def test_init_without_websocket(self):
        """Should initialize with None websocket."""
        coordinator = RequestCoordinator()
        
        assert coordinator._websocket is None
        assert coordinator._session_id is None
    
    def test_set_websocket(self):
        """Should update websocket connection."""
        coordinator = RequestCoordinator()
        mock_ws = MagicMock()
        
        coordinator.set_websocket(mock_ws)
        
        assert coordinator._websocket is mock_ws


class TestRequestFormState:
    """Tests for request_form_state method."""
    
    @pytest.mark.asyncio
    async def test_request_form_state_no_websocket(self):
        """Should return empty dict when no websocket."""
        coordinator = RequestCoordinator()
        
        result = await coordinator.request_form_state()
        
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_request_form_state_sends_message(self):
        """Should send get_form_state message with request_id."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        # Simulate response in background
        async def send_response():
            await asyncio.sleep(0.01)
            # Get the request_id from the sent message
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_form_state_response(request_id, {"field1": "value1"})
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_form_state()
        
        # Verify message sent
        assert mock_ws.send_json.called
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["type"] == "get_form_state"
        assert "request_id" in sent_message
        assert sent_message["field_ids"] == []
        
        # Verify result
        assert result == {"field1": "value1"}
    
    @pytest.mark.asyncio
    async def test_request_form_state_with_field_ids(self):
        """Should send specific field_ids when provided."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_form_state_response(request_id, {"email": "test@example.com"})
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_form_state(field_ids=["email", "phone"])
        
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["field_ids"] == ["email", "phone"]
        assert result == {"email": "test@example.com"}
    
    @pytest.mark.asyncio
    async def test_request_form_state_timeout(self):
        """Should return empty dict on timeout."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        # Don't send response, let it timeout
        result = await coordinator.request_form_state()
        
        assert result == {}
        assert coordinator._pending == {}
    
    @pytest.mark.asyncio
    async def test_request_form_state_send_error(self):
        """Should handle send_json errors."""
        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("Connection error")
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        result = await coordinator.request_form_state()
        
        assert result == {}
        assert coordinator._pending == {}


class TestRequestNextFieldHint:
    """Tests for request_next_field_hint method."""
    
    @pytest.mark.asyncio
    async def test_request_next_field_hint_no_websocket(self):
        """No websocket -> timeout sentinel, not None.

        None means "form genuinely complete"; an unanswerable request must be
        distinguishable so confirm_field never reports the form done by mistake
        (bd polyglot-pdf-tks).
        """
        coordinator = RequestCoordinator()

        result = await coordinator.request_next_field_hint()

        assert result is HINT_REQUEST_TIMEOUT
    
    @pytest.mark.asyncio
    async def test_request_next_field_hint_sends_message(self):
        """Should send get_next_field_hint message."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_next_field_hint_response(request_id, "Next field: email")
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_next_field_hint()
        
        assert mock_ws.send_json.called
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["type"] == "get_next_field_hint"
        assert "request_id" in sent_message
        assert result == "Next field: email"
    
    @pytest.mark.asyncio
    async def test_request_next_field_hint_no_more_fields(self):
        """Should handle None hint when form is complete."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_next_field_hint_response(request_id, None)
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_next_field_hint()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_request_next_field_hint_timeout(self):
        """Timeout -> sentinel, NOT None (a None would read as 'form complete').

        bd polyglot-pdf-tks: the frontend not answering in 2s must not masquerade
        as completion.
        """
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)

        result = await coordinator.request_next_field_hint()

        assert result is HINT_REQUEST_TIMEOUT
        assert coordinator._pending == {}


class TestRequestFieldValue:
    """Tests for request_field_value method."""
    
    @pytest.mark.asyncio
    async def test_request_field_value_no_websocket(self):
        """Should return not found when no websocket."""
        coordinator = RequestCoordinator()
        
        result = await coordinator.request_field_value("email")
        
        assert result == {"found": False, "value": None}
    
    @pytest.mark.asyncio
    async def test_request_field_value_sends_message(self):
        """Should send get_field_value message with spoken_name."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_field_value_response(request_id, "test@example.com", True)
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_field_value("email")
        
        assert mock_ws.send_json.called
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["type"] == "get_field_value"
        assert sent_message["spoken_name"] == "email"
        assert "request_id" in sent_message
        assert result == {"value": "test@example.com", "found": True}
    
    @pytest.mark.asyncio
    async def test_request_field_value_not_found(self):
        """Should handle field not found response."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_field_value_response(request_id, None, False)
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_field_value("nonexistent")
        
        assert result == {"value": None, "found": False}
    
    @pytest.mark.asyncio
    async def test_request_field_value_timeout(self):
        """Should return not found on timeout."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        result = await coordinator.request_field_value("email")
        
        assert result == {"found": False, "value": None}
        assert coordinator._pending == {}


class TestRequestSectionInfo:
    """Tests for request_section_info method."""
    
    @pytest.mark.asyncio
    async def test_request_section_info_no_websocket(self):
        """Should return None when no websocket."""
        coordinator = RequestCoordinator()
        
        result = await coordinator.request_section_info("3")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_request_section_info_sends_message(self):
        """Should send prepare_section_switch message."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        section_data = {
            "schema": {"field1": {}},
            "current_values": {},
            "metadata": {"section_number": 3},
            "initial_field_hint": "Start with field1"
        }
        
        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_section_info_response(request_id, section_data)
        
        asyncio.create_task(send_response())
        
        result = await coordinator.request_section_info("3")
        
        assert mock_ws.send_json.called
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["type"] == "prepare_section_switch"
        assert sent_message["identifier"] == "3"
        assert "request_id" in sent_message
        assert result == section_data
    
    @pytest.mark.asyncio
    async def test_request_section_info_timeout(self):
        """Should return None on timeout."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        result = await coordinator.request_section_info("3")
        
        assert result is None
        assert coordinator._pending == {}


def _seed(coordinator, request_id, request_type, **extras):
    """Place a keyed pending entry, mirroring _register's shape (bd bxw)."""
    future = asyncio.Future()
    entry = {"future": future, "type": request_type}
    entry.update(extras)
    coordinator._pending[request_id] = entry
    return future


class TestResponseHandlers:
    """Tests for response handler methods."""

    def test_handle_form_state_response_no_pending(self):
        """Should warn (not raise) when there is no pending request for the id."""
        coordinator = RequestCoordinator()

        # Should not raise, just log warning
        coordinator.handle_form_state_response("test-id", {})

    def test_handle_form_state_response_mismatched_id(self):
        """A response for an UNKNOWN id must not resolve a different pending future."""
        coordinator = RequestCoordinator()
        future = _seed(coordinator, "correct-id", "form_state")

        coordinator.handle_form_state_response("wrong-id", {})

        # The genuine pending future is untouched.
        assert not future.done()
        assert "correct-id" in coordinator._pending

    def test_stale_next_field_response_with_bad_hint_does_not_raise(self):
        """Codex PR #136: a next_field_hint_response for an UNKNOWN id carrying a
        non-string hint must be ignored, NOT crash -- the strip transform runs
        only AFTER _resolve validates a matching pending request. Pre-fix the
        strip ran before validation and could raise on the WS path."""
        coordinator = RequestCoordinator()
        # No pending request at all; hint is a non-string (e.g. a stray object).
        # Must log + return without raising (strip is never reached).
        coordinator.handle_next_field_hint_response("unknown-id", {"oops": "object"})
        assert coordinator._pending == {}

    def test_next_field_strip_still_applies_on_a_matched_request(self):
        """The strip transform still runs for a MATCHED next_field request, so the
        field_id parenthetical is removed before the future resolves (dx7)."""
        coordinator = RequestCoordinator()
        future = _seed(coordinator, "rid", "next_field")
        # The strip regex requires the single-quoted, end-anchored field_id form.
        coordinator.handle_next_field_hint_response(
            "rid", "Next field: email (field_id: 'p1_email', type: text)")
        assert future.done()
        # The "(field_id: ...)" parenthetical is stripped.
        assert "field_id" not in future.result()
        assert "email" in future.result()

    def test_handle_response_wrong_type_does_not_cross_resolve(self):
        """bd polyglot-pdf-bxw: if a response's id maps to a DIFFERENT request
        type, it must NOT resolve that future -- the exact clobber this removes."""
        coordinator = RequestCoordinator()
        future = _seed(coordinator, "id-1", "next_field")

        # A form_state response arrives carrying id-1 (which is a next_field req).
        coordinator.handle_form_state_response("id-1", {"field1": "value1"})

        assert not future.done()           # the next_field future is NOT resolved
        assert "id-1" in coordinator._pending

    def test_handle_form_state_response_resolves_future(self):
        coordinator = RequestCoordinator()
        future = _seed(coordinator, "test-id", "form_state")

        coordinator.handle_form_state_response("test-id", {"field1": "value1"})

        assert future.done()
        assert future.result() == {"field1": "value1"}
        assert coordinator._pending == {}

    def test_handle_next_field_hint_response_resolves_future(self):
        coordinator = RequestCoordinator()
        future = _seed(coordinator, "test-id", "next_field")

        coordinator.handle_next_field_hint_response("test-id", "Next: email")

        assert future.done()
        assert future.result() == "Next: email"
        assert coordinator._pending == {}

    def test_handle_field_value_response_resolves_future(self):
        coordinator = RequestCoordinator()
        future = _seed(coordinator, "test-id", "field_value")

        coordinator.handle_field_value_response("test-id", "test@example.com", True)

        assert future.done()
        assert future.result() == {"value": "test@example.com", "found": True}
        assert coordinator._pending == {}

    def test_handle_section_info_response_resolves_future(self):
        coordinator = RequestCoordinator()
        future = _seed(coordinator, "test-id", "section_info")

        section_data = {"schema": {}, "current_values": {}}
        coordinator.handle_section_info_response("test-id", section_data)

        assert future.done()
        assert future.result() == section_data
        assert coordinator._pending == {}


class TestMultipleConcurrentRequests:
    """Tests for handling multiple concurrent requests."""
    
    @pytest.mark.asyncio
    async def test_concurrent_different_request_types(self):
        """Should handle different request types concurrently."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)
        
        async def send_responses():
            await asyncio.sleep(0.01)
            # Respond to both requests
            calls = mock_ws.send_json.call_args_list
            for call in calls:
                message = call[0][0]
                request_id = message["request_id"]
                if message["type"] == "get_form_state":
                    coordinator.handle_form_state_response(request_id, {"field1": "value1"})
                elif message["type"] == "get_next_field_hint":
                    coordinator.handle_next_field_hint_response(request_id, "Next: email")
        
        asyncio.create_task(send_responses())
        
        # Make concurrent requests of different types
        form_state_task = coordinator.request_form_state()
        next_hint_task = coordinator.request_next_field_hint()
        
        results = await asyncio.gather(form_state_task, next_hint_task)

        assert results[0] == {"field1": "value1"}
        assert results[1] == "Next: email"

    @pytest.mark.asyncio
    async def test_concurrent_same_type_requests_do_not_cross_resolve(self):
        """THE clobber regression (bd polyglot-pdf-bxw): two overlapping requests
        of the SAME type must each resolve to ITS OWN caller. Under the old single-
        slot-per-type design the second request overwrote the first's slot, so the
        first hung to timeout and the responses cross-resolved. With keyed slots,
        each request_id has its own future."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)

        # Two next_field_hint requests in flight at once.
        t1 = asyncio.create_task(coordinator.request_next_field_hint())
        t2 = asyncio.create_task(coordinator.request_next_field_hint())
        await asyncio.sleep(0.01)  # let both send

        # Both must be tracked simultaneously (the old design held only one).
        assert len(coordinator._pending) == 2

        # Pull the two distinct request_ids and answer them with DIFFERENT payloads
        # (echoing the id) to prove each future resolves to ITS OWN id -- without
        # trusting any positional task<->call ordering (fresh-eyes PR #136).
        sent = [c[0][0] for c in mock_ws.send_json.call_args_list]
        ids = [m["request_id"] for m in sent if m["type"] == "get_next_field_hint"]
        assert len(ids) == 2 and ids[0] != ids[1]

        for rid in ids:
            coordinator.handle_next_field_hint_response(rid, f"Hint for {rid}")

        r1, r2 = await asyncio.gather(t1, t2)
        # Both distinct hints were delivered (one per caller), and no future got
        # the other's id -- the set of results equals the set of per-id hints.
        assert {r1, r2} == {f"Hint for {rid}" for rid in ids}
        assert r1 != r2
        assert coordinator._pending == {}


class TestRequestConfirmField:
    """Tests for request_confirm_field -- the synchronous confirm round-trip
    (bd polyglot-pdf-wpw.2 / WS-E2)."""

    @pytest.mark.asyncio
    async def test_request_confirm_field_no_websocket(self):
        """No websocket -> CONFIRM_REQUEST_TIMEOUT (never read as confirmed)."""
        coordinator = RequestCoordinator()

        result = await coordinator.request_confirm_field("email", "verbal")

        assert result is CONFIRM_REQUEST_TIMEOUT

    @pytest.mark.asyncio
    async def test_request_confirm_field_sends_message_and_records(self):
        """Sends a confirm_field request and resolves with the FE ack (recorded)."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)

        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_confirm_field_response(request_id, True)

        asyncio.create_task(send_response())

        result = await coordinator.request_confirm_field("email", "verbal")

        assert mock_ws.send_json.called
        sent_message = mock_ws.send_json.call_args[0][0]
        assert sent_message["type"] == "confirm_field"
        assert sent_message["field_id"] == "email"
        assert sent_message["confirmation_method"] == "verbal"
        assert "request_id" in sent_message
        assert result == {"recorded": True, "reason": None}

    @pytest.mark.asyncio
    async def test_request_confirm_field_not_recorded_with_reason(self):
        """A not-recorded ack carries the fixed reason token (no PII)."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)

        async def send_response():
            await asyncio.sleep(0.01)
            call_args = mock_ws.send_json.call_args[0][0]
            request_id = call_args["request_id"]
            coordinator.handle_confirm_field_response(request_id, False, "no_value")

        asyncio.create_task(send_response())

        result = await coordinator.request_confirm_field("email", "verbal")

        assert result == {"recorded": False, "reason": "no_value"}

    @pytest.mark.asyncio
    async def test_request_confirm_field_timeout(self):
        """No FE answer in time -> CONFIRM_REQUEST_TIMEOUT + slot cleaned up.

        A slow/disconnected client must NEVER read as a successful confirm -- the
        whole reason the round-trip exists.
        """
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)

        # Patch the wait to time out fast instead of blocking the suite 2s.
        import backend.services.request_coordinator as rc_mod
        original_wait_for = rc_mod.asyncio.wait_for

        async def fast_timeout(awaitable, timeout):
            # Cancel the underlying future and raise as a real timeout would.
            if hasattr(awaitable, "cancel"):
                awaitable.cancel()
            raise asyncio.TimeoutError()

        rc_mod.asyncio.wait_for = fast_timeout
        try:
            result = await coordinator.request_confirm_field("email", "verbal")
        finally:
            rc_mod.asyncio.wait_for = original_wait_for

        assert result is CONFIRM_REQUEST_TIMEOUT
        assert coordinator._pending == {}

    @pytest.mark.asyncio
    async def test_confirm_field_does_not_clobber_concurrent_next_field(self):
        """A confirm_field request and a next_field_hint request in flight at the
        same time resolve to their own callers (keyed slots, bd bxw)."""
        mock_ws = AsyncMock()
        coordinator = RequestCoordinator(websocket=mock_ws)

        t_confirm = asyncio.create_task(coordinator.request_confirm_field("email", "verbal"))
        t_hint = asyncio.create_task(coordinator.request_next_field_hint())
        await asyncio.sleep(0.01)

        sent = [c[0][0] for c in mock_ws.send_json.call_args_list]
        confirm_id = next(m["request_id"] for m in sent if m["type"] == "confirm_field")
        hint_id = next(m["request_id"] for m in sent if m["type"] == "get_next_field_hint")
        assert confirm_id != hint_id

        coordinator.handle_confirm_field_response(confirm_id, True)
        coordinator.handle_next_field_hint_response(hint_id, "Next field hint")

        confirm_result = await t_confirm
        hint_result = await t_hint
        assert confirm_result == {"recorded": True, "reason": None}
        assert hint_result == "Next field hint"
        assert coordinator._pending == {}
