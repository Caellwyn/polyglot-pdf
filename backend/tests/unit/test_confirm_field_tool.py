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
from backend.services.form_filling_service import FormFillingService
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
        """Manual confirmation should mark the field confirmed.

        "manual" means the user edited AND verified it in the UI -- typing alone
        stopped being a confirmation in bd polyglot-pdf-uum5g. The TOOL contract
        here is unchanged: whatever the client asserts via confirm_field is
        recorded; what changed is which gestures cause the client to assert it."""
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
    async def test_none_coordinator_does_not_signal_completion(self, mock_websocket):
        """A None coordinator must NOT crash and must NOT report completion.

        request_coordinator is a required positional, so it is never None in
        production -- but a test or racing reconnect could pass None. UNDER wpw.2
        (the synchronous confirm round-trip), an absent coordinator means we cannot
        reach the frontend to VERIFY the confirm -- the same epistemic state as a
        confirm timeout. So the confirm reports success:false (not recorded), NOT
        success:true: claiming success without verification is exactly the
        silent-success this round-trip exists to kill. Either way it must never
        claim the form is complete (the failure class bd polyglot-pdf-tks guards)
        or leak a non-serializable sentinel onto the wire. (Originally added by bd
        polyglot-pdf-pen for the pre-wpw.2 fire-and-forget contract, where this
        returned success:true; updated to wpw.2's verify-or-fail contract.)
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

        # Cannot verify the confirm -> success:false (not recorded), and crucially
        # does NOT claim the form is complete, and does NOT leak the sentinel.
        assert response["success"] is False
        assert response["field_confirmed"] is None
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
        # no_value is NON-retryable: re-confirming the SAME empty field fails
        # identically and wedges the model in a confirm loop (the DTI stall, bd
        # polyglot-pdf-jnjj.40). The model must FILL, not retry the bare confirm.
        assert response["retryable"] is False
        # ...and the guidance must say so explicitly.
        assert "again" in response["message"].lower()  # "do NOT call confirm_field ... again"
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
        # A timeout IS retryable (re-asking can succeed) -- unlike the no_value case
        # (bd polyglot-pdf-jnjj.40). Pin the invariant so a future change to the
        # retryable param can't silently make the timeout path non-retryable.
        assert response["retryable"] is True
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


class TestConfirmSectionBoundarySkipsHint:
    """bd polyglot-pdf-njvh: on the LAST field of a section, the FE acks the confirm
    with section_complete:true (it is about to tear down the socket for
    switchToSection). The backend must then SKIP the next-field-hint request -- that
    request would race the teardown, time out, and make Gemini emit a spurious 'do
    NOT assume the form is complete' prompt right as the section auto-advances.
    """

    @pytest.mark.asyncio
    async def test_section_complete_ack_skips_next_field_hint(
        self, callback_handler, mock_coordinator
    ):
        """When the confirm ack carries section_complete, request_next_field_hint is
        NEVER called and the response is a clean 'section advancing' message (no
        timeout / 'do NOT assume complete' text)."""
        mock_coordinator.request_confirm_field = AsyncMock(
            return_value={"recorded": True, "reason": None, "section_complete": True}
        )

        response = await callback_handler.on_tool_call(
            tool_name="confirm_field",
            arguments={"field_id": "p1_line5c_middlename", "confirmation_method": "verbal"},
        )

        # The doomed hint round-trip must NOT fire at the boundary.
        mock_coordinator.request_next_field_hint.assert_not_called()
        # Clean success, no hint, no scary "do NOT assume" message.
        assert response["success"] is True
        assert response["field_confirmed"] == "p1_line5c_middlename"
        assert response["next_field_hint"] is None
        assert "do NOT assume" not in response["message"]
        assert "completes this section" in response["message"]

    @pytest.mark.asyncio
    async def test_non_boundary_confirm_still_requests_hint(
        self, callback_handler, mock_coordinator
    ):
        """A mid-section confirm (section_complete absent/false) STILL requests the
        next-field hint -- the skip is scoped to the boundary only."""
        mock_coordinator.request_confirm_field = AsyncMock(
            return_value={"recorded": True, "reason": None, "section_complete": False}
        )
        mock_coordinator.request_next_field_hint = AsyncMock(
            return_value="Next, please provide your date of birth"
        )

        response = await callback_handler.on_tool_call(
            tool_name="confirm_field",
            arguments={"field_id": "p1_line3a_familyname", "confirmation_method": "verbal"},
        )

        mock_coordinator.request_next_field_hint.assert_called_once()
        assert response["next_field_hint"] == "Next, please provide your date of birth"

    @pytest.mark.asyncio
    async def test_missing_section_complete_key_defaults_to_requesting_hint(
        self, callback_handler, mock_coordinator
    ):
        """Back-compat: an ack WITHOUT the section_complete key (older FE) behaves
        exactly as before -- the hint is requested."""
        mock_coordinator.request_confirm_field = AsyncMock(
            return_value={"recorded": True, "reason": None}  # no section_complete key
        )
        mock_coordinator.request_next_field_hint = AsyncMock(return_value="Next field")

        await callback_handler.on_tool_call(
            tool_name="confirm_field",
            arguments={"field_id": "p1_line3a_familyname", "confirmation_method": "verbal"},
        )

        mock_coordinator.request_next_field_hint.assert_called_once()


class TestStartSessionThreadsFormIds:
    """Regression test for bd polyglot-pdf-rwjy: start_session must pass
    form_id and form_session_id to CallbackHandler so the confirmation-audit
    guard (self._form_id and self._form_session_id) is truthy at runtime.
    Before the fix, CallbackHandler was constructed before form_id was
    extracted, leaving both attributes as None and silently disabling audit
    logging on every session."""

    @pytest.mark.asyncio
    async def test_start_session_threads_form_ids_into_callback_handler(self):
        """CallbackHandler built by start_session carries the schema's form_number
        and the provided form_session_id (bd rwjy)."""
        service = FormFillingService()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()

        schema = {
            "source": "web",
            "form_metadata": {"form_number": "I-90", "title": "I-90"},
            "fields": [{"id": "f1", "name": "Field 1", "type": "text"}],
        }

        with patch.object(service, "_live_ai", None):
            await service.start_session(
                websocket=ws,
                session_id="test-session",
                schema=schema,
                form_session_id="fss_rwjy_test",
            )

        assert service._callback_handler is not None
        assert service._callback_handler._form_id == "I-90"
        assert service._callback_handler._form_session_id == "fss_rwjy_test"

    @pytest.mark.asyncio
    async def test_start_session_uses_session_id_when_form_session_id_absent(self):
        """When form_session_id is not provided, CallbackHandler falls back to
        the ephemeral session_id so the guard is still truthy (bd rwjy)."""
        service = FormFillingService()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()

        schema = {
            "source": "web",
            "form_metadata": {"form_number": "I-90", "title": "I-90"},
            "fields": [],
        }

        with patch.object(service, "_live_ai", None):
            await service.start_session(
                websocket=ws,
                session_id="fallback-session",
                schema=schema,
                form_session_id=None,
            )

        assert service._callback_handler._form_id == "I-90"
        assert service._callback_handler._form_session_id == "fallback-session"


class TestConfirmFieldCoercion:
    """bd polyglot-pdf-h1bn: confirm_field coerces onto the current field when the
    model confirms a hallucinated/drifted/empty id, so it follows the coerced
    update_form_fields onto the same field (else the FE looks up the wrong id and
    the field is stranded). Gated on the SERVICE's injected USE_DTI (via _get_use_dti),
    NOT the global singleton (Codex PR #264) -- so tests just wire the getters,
    fully isolated, no module patching."""

    @staticmethod
    def _wire(handler, *, current_field_id, use_dti=True):
        handler._get_use_dti = lambda: use_dti
        handler._get_current_field_id = lambda: current_field_id

    @pytest.mark.asyncio
    async def test_confirm_coerced_to_current_field(self, callback_handler, mock_coordinator):
        self._wire(callback_handler, current_field_id="p1_line2_acctidentifier")
        await callback_handler._handle_confirm_field_tool(
            {"field_id": "p1_line2_uscis_account", "confirmation_method": "verbal"})
        # The FE was asked to confirm the CURRENT field, not the hallucinated id.
        assert mock_coordinator.request_confirm_field.call_args.args[0] == "p1_line2_acctidentifier"

    @pytest.mark.asyncio
    async def test_confirm_coercion_does_not_log_raw_id(self, callback_handler, mock_coordinator, monkeypatch):
        # P0 no-PII (Codex PR #264, Opus fallback): the CONFIRM coercion log must NOT
        # emit the raw model field_id (it can carry the user's answer) -- only the
        # schema-validated current field id. Symmetric with the update-side scrub.
        import backend.services.callback_handler as cbh
        calls = []

        class _FakeLog:
            def info(self, event, **kw): calls.append((event, kw))
            def warning(self, *a, **k): pass
            def __getattr__(self, _n): return lambda *a, **k: None
        monkeypatch.setattr(cbh, "_log", _FakeLog())
        self._wire(callback_handler, current_field_id="p1_line2_acctidentifier")
        await callback_handler._handle_confirm_field_tool(
            {"field_id": "my ssn is 123-45-6789", "confirmation_method": "verbal"})
        coerce_logs = [(e, kw) for (e, kw) in calls if e == "dti_confirm_coerced_to_current_field"]
        assert coerce_logs, "confirm coercion should have logged"
        blob = repr(coerce_logs)
        assert "sent_field_id" not in blob
        assert "123-45-6789" not in blob  # raw id (potential PII) never logged
        assert "p1_line2_acctidentifier" in blob

    @pytest.mark.asyncio
    async def test_confirm_coerced_for_empty_id(self, callback_handler, mock_coordinator):
        # Codex PR #264: an EMPTY confirm id (the tool schema allows '') must also
        # coerce -- symmetric with the update path, which coerces '' too. Otherwise the
        # FE gets confirm_field('') and the just-filled current field is stranded.
        self._wire(callback_handler, current_field_id="p1_line2_acctidentifier")
        await callback_handler._handle_confirm_field_tool(
            {"field_id": "", "confirmation_method": "verbal"})
        assert mock_coordinator.request_confirm_field.call_args.args[0] == "p1_line2_acctidentifier"

    @pytest.mark.asyncio
    async def test_confirm_matching_id_not_coerced(self, callback_handler, mock_coordinator):
        self._wire(callback_handler, current_field_id="p1_line1_aliennumber")
        await callback_handler._handle_confirm_field_tool(
            {"field_id": "p1_line1_aliennumber", "confirmation_method": "verbal"})
        assert mock_coordinator.request_confirm_field.call_args.args[0] == "p1_line1_aliennumber"

    @pytest.mark.asyncio
    async def test_confirm_known_but_different_id_is_honored(self, callback_handler, mock_coordinator):
        # bd polyglot-pdf-8vy3 (symmetric with the update-side gate): a RESOLVABLE
        # id is authoritative -- the model may legitimately confirm a PREVIOUS field
        # it just re-filled (a late correction after the pointer advanced). Only an
        # empty/unknown id coerces.
        self._wire(callback_handler, current_field_id="p1_checkbox4")
        callback_handler._is_known_field = lambda fid: fid == "p1_line3a_familyname"
        await callback_handler._handle_confirm_field_tool(
            {"field_id": "p1_line3a_familyname", "confirmation_method": "verbal"})
        assert mock_coordinator.request_confirm_field.call_args.args[0] == "p1_line3a_familyname"

    @pytest.mark.asyncio
    async def test_confirm_no_coercion_without_current_field(self, callback_handler, mock_coordinator):
        # current field unknown -> use the model's id as-is.
        self._wire(callback_handler, current_field_id=None)
        await callback_handler._handle_confirm_field_tool(
            {"field_id": "whatever", "confirmation_method": "verbal"})
        assert mock_coordinator.request_confirm_field.call_args.args[0] == "whatever"

    @pytest.mark.asyncio
    async def test_confirm_no_coercion_when_dti_off(self, callback_handler, mock_coordinator):
        # USE_DTI off (the SERVICE's injected value) -> model id authoritative, no coercion.
        self._wire(callback_handler, current_field_id="p1_line2_acctidentifier", use_dti=False)
        await callback_handler._handle_confirm_field_tool(
            {"field_id": "p1_line2_uscis_account", "confirmation_method": "verbal"})
        assert mock_coordinator.request_confirm_field.call_args.args[0] == "p1_line2_uscis_account"

    @pytest.mark.asyncio
    async def test_confirm_success_clears_current_field_pointer(self, callback_handler, mock_coordinator):
        # Codex PR #264: on a successful confirm the current field is DONE; the pointer
        # must be invalidated so a later update can't be coerced onto the just-confirmed
        # field if next-field delivery times out. The handler calls _clear_current_field.
        cleared = {"n": 0}
        callback_handler._clear_current_field = lambda: cleared.__setitem__("n", cleared["n"] + 1)
        self._wire(callback_handler, current_field_id="p1_line1_aliennumber")
        # next-field hint times out (default mock returns a hint; force timeout)
        from backend.services.request_coordinator import HINT_REQUEST_TIMEOUT
        mock_coordinator.request_next_field_hint = AsyncMock(return_value=HINT_REQUEST_TIMEOUT)
        await callback_handler._handle_confirm_field_tool(
            {"field_id": "p1_line1_aliennumber", "confirmation_method": "verbal"})
        assert cleared["n"] == 1, "confirm success must clear the current-field pointer"

    @pytest.mark.asyncio
    async def test_confirm_next_field_block_uses_injected_dti_not_global(self, callback_handler, mock_coordinator):
        # Opus fallback PR #264: the next-field re-merge must read the SAME injected
        # USE_DTI as the pointer-clear, not the global singleton. With injected DTI on
        # (global irrelevant here), a delivered next-field schema must be consumed +
        # merged (so the pointer is re-set), proving the block ran under the injected gate.
        self._wire(callback_handler, current_field_id="p1_line1_aliennumber", use_dti=True)
        merged = []
        callback_handler._merge_field_schema = lambda s: merged.append(s)
        callback_handler._clear_current_field = lambda: None
        next_schema = {"id": "p1_line2_acctidentifier", "name": "acct", "type": "text"}
        mock_coordinator.consume_pending_next_field_schema = lambda: next_schema
        await callback_handler._handle_confirm_field_tool(
            {"field_id": "p1_line1_aliennumber", "confirmation_method": "verbal"})
        # The next-field schema was consumed + merged -> the block ran under injected DTI.
        assert merged == [next_schema], "next-field re-merge must run under the injected USE_DTI gate"
