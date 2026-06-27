"""
Callback handler for Gemini Live AI session events.

Handles callbacks for form updates, transcripts, audio, and tool calls.
Extracted from FormFillingService for better testability and separation of concerns.
"""
import json
from typing import Any, Dict, Optional
from fastapi import WebSocket
import structlog

from .request_coordinator import (
    CONFIRM_REQUEST_TIMEOUT,
    HINT_REQUEST_TIMEOUT,
    RequestCoordinator,
)
from backend.config import get_settings
from backend.services.ai_context import render_field_guidance
from backend.utils.dev_file_logger import get_dev_logger
from backend.utils.confirmation_logger import log_field_confirmation

_log = structlog.get_logger().bind(module="callback_handler")
_dev_log = get_dev_logger()


class CallbackHandler:
    """Handles callbacks from Gemini Live AI session."""
    
    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        request_coordinator: RequestCoordinator,
        send_transcript: bool = False,
        form_id: Optional[str] = None,
        form_session_id: Optional[str] = None,
    ):
        """
        Initialize callback handler.

        Args:
            websocket: WebSocket connection to frontend
            session_id: Session ID for logging
            request_coordinator: Coordinator for async requests to frontend
            send_transcript: Whether to send transcript events to frontend
            form_id: Form type identifier (e.g., "I-90") for confirmation logging
            form_session_id: Persistent form session ID for confirmation logging
        """
        self._websocket = websocket
        self._session_id = session_id
        self._request_coordinator = request_coordinator
        self._send_transcript = send_transcript
        self._ws_audio_chunk_count = 0
        self._form_id = form_id  # For confirmation logging
        self._form_session_id = form_session_id  # For confirmation logging
        
        # Service methods will be injected
        self._handle_update_fields = None
        self._handle_switch_section = None
        self._handle_get_field_value = None
        self._request_form_state_from_client = None
        self._get_next_field_schema_for_jit = None
        self._merge_field_schema = None
        # Secretary (bd polyglot-pdf-jnjj.45c): async handler that runs the
        # ask_secretary lookup. Injected by FormFillingService; None until then.
        self._handle_ask_secretary = None

    def set_tool_handlers(
        self,
        handle_update_fields,
        handle_switch_section,
        handle_get_field_value,
        request_form_state_from_client,
        get_next_field_schema_for_jit,
        merge_field_schema=None,
        handle_ask_secretary=None,
    ):
        """Inject tool handler methods from FormFillingService."""
        self._handle_update_fields = handle_update_fields
        self._handle_switch_section = handle_switch_section
        self._handle_get_field_value = handle_get_field_value
        self._request_form_state_from_client = request_form_state_from_client
        self._get_next_field_schema_for_jit = get_next_field_schema_for_jit
        self._merge_field_schema = merge_field_schema
        self._handle_ask_secretary = handle_ask_secretary
    
    async def send_form_update(
        self,
        data: Optional[Dict[str, Any]],
        applied_fields: Optional[list] = None,
        next_field_schema: Optional[dict] = None,
        request_hint: bool = False,
    ) -> Optional[str]:
        """
        Send form state update to frontend.

        Args:
            data: Form state data to send
            applied_fields: List of field IDs that were actually applied
            next_field_schema: Schema for next field (JIT mode only)
            request_hint: If True, await a next_field_hint round-trip and return it.
                Callers on the update_form_fields path leave this False (the hint is
                always discarded there -- bd polyglot-pdf-vfb2); only callers that
                actually use the return value should pass True.

        Returns:
            Next field hint string or None
        """
        if self._websocket and data is not None:
            payload = {"form_state": data}
            if applied_fields is not None:
                payload["applied_fields"] = applied_fields
            if next_field_schema is not None:
                payload["next_field_schema"] = next_field_schema

            await self._websocket.send_json({"type": "form_updated", "data": payload})

            if request_hint and self._request_coordinator:
                hint = await self._request_coordinator.request_next_field_hint()
                return None if hint is HINT_REQUEST_TIMEOUT else hint
        return None
    
    async def on_form_update(self, data: dict) -> None:
        """
        Handle form update callback from Gemini.
        
        Legacy callback path: just forward updates to the websocket.
        
        Args:
            data: Form state data from Gemini
        """
        await self.send_form_update(data)
    
    async def on_transcript(self, text: str) -> None:
        """
        Handle transcript callback from Gemini.
        
        Send transcript to client if requested, and ALWAYS signal turn complete
        for activity watchdog timing.
        
        Args:
            text: Transcript text from Gemini
        """
        # Send transcript to client if requested
        if self._websocket and self._send_transcript:
            await self._websocket.send_json({"type": "transcript", "data": text})
        
        # ALWAYS signal turn complete for activity watchdog (regardless of send_transcript setting)
        # Transcript arrives after all audio chunks, indicating Gemini finished speaking
        # This is critical for Level 3 farewell disconnect timing
        if self._websocket:
            try:
                await self._websocket.send_json({"type": "turn_complete"})
            except Exception as e:
                _log.warning("failed_to_send_turn_complete", error=str(e), session_id=self._session_id)
    
    async def on_audio(self, data: bytes) -> None:
        """
        Handle audio callback from Gemini.
        
        Forward raw audio bytes from Gemini to the connected websocket client.
        The client is expected to handle raw PCM audio playback.
        
        Args:
            data: Raw PCM audio bytes from Gemini
        """
        if self._websocket:
            try:
                # Track audio chunks being sent to client
                self._ws_audio_chunk_count += 1
                
                if self._ws_audio_chunk_count == 1:
                    _log.info("[audio] [WebSocket Audio] Sending first audio chunk to client", 
                             session_id=self._session_id, bytes=len(data))
                
                await self._websocket.send_bytes(data)
            except Exception as e:
                # Swallow errors to avoid crashing the session loop
                _log.warning("websocket_audio_send_failed", error=str(e), session_id=self._session_id)

    async def on_go_away(self, time_left: Optional[str]) -> None:
        """Forward a Gemini Live GoAway to the client (bd polyglot-pdf-c5t).

        The Live server sends GoAway before terminating the connection; relaying
        it (with time_left, a duration string) lets the client pre-emptively
        reconnect ahead of the abrupt close. Distinct WS message type so the
        client can act on it without parsing the generic error/close path. The
        backend stores nothing -- the client owns the reconnect (stateless
        invariant holds). Errors are swallowed so a send failure never crashes
        the session loop (same discipline as on_audio/on_transcript).
        """
        # `is not None` (not a truthiness check): a Starlette WebSocket is
        # Mapping-like (__len__), so `if self._websocket:` is False for an empty
        # one -- and for a MagicMock(spec=WebSocket) in tests. We want "is a
        # websocket present", which is an identity check.
        if self._websocket is not None:
            try:
                await self._websocket.send_json(
                    {"type": "go_away", "time_left": time_left}
                )
            except Exception as e:
                _log.warning("websocket_go_away_send_failed",
                             error=str(e), session_id=self._session_id)

    async def on_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Handle tool call callback from Gemini.

        Routes tool calls to appropriate handlers and manages response formatting.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool

        Returns:
            Tool response dictionary for Gemini
        """
        # ============================================================================
        # LOGGING POLICY (HIPAA COMPLIANCE)
        # ============================================================================
        # Production (_log): NEVER log field values - only log:
        #   - Tool names
        #   - Argument KEYS (not values)
        #   - Counts (field count, error count)
        #   - Field IDs (not field values)
        #   - Session metadata
        #
        # Development (_dev_log): MAY log field values ONLY when the
        #   `backend/.env.DEV` marker file exists (DEV_LOGGING_ENABLED, gated in
        #   backend/utils/dev_file_logger.py). NOT VFF_DEV_LOGGING -- that env
        #   var is dead config (no code reads it; see docs/components/config-deployment.md).
        #   - Writes to local files: backend/logs/gemini_YYYY-MM-DD.jsonl
        #   - Never deployed to production
        #   - Used for local debugging only
        # ============================================================================

        # Production log: tool name + argument KEYS + count only -- NEVER the
        # argument VALUES (they include field values = PII/PHI; stdout -> Cloud
        # Run logs). The previous `print(f"Arguments: {arguments}")` here leaked
        # the full args (bd polyglot-pdf-oeq); full-arg capture for debugging is
        # the job of `_dev_log` below, which is gated behind .env.DEV.
        _log.info(
            "tool_call_received",
            tool_name=tool_name,
            arg_keys=sorted((arguments or {}).keys()),
            arg_count=len(arguments or {}),
            session_id=self._session_id,
        )

        # Dev logging: Log full arguments (includes field values - dev only!)
        _dev_log.log_tool_call(tool_name, arguments, session_id=self._session_id)

        if self._session_id is None:
            _log.error("tool_call_no_session", tool_name=tool_name)
            return None

        normalized = (tool_name or "").lower()

        # Route to appropriate tool handler
        if normalized == "update_form_fields":
            return await self._handle_update_form_fields_tool(arguments)
        
        if normalized in {"get_form_status", "get_form_state"}:
            return await self._handle_get_form_status_tool(arguments)
        
        if normalized == "switch_section":
            return await self._handle_switch_section_tool(arguments)
        
        if normalized == "get_field_value":
            return await self._handle_get_field_value_tool(arguments)

        # NOTE: no complete_section route -- that tool was removed; section
        # completion is auto-detected by the frontend when all fields confirm.

        if normalized == "confirm_field":
            return await self._handle_confirm_field_tool(arguments)

        if normalized == "ask_secretary":
            return await self._handle_ask_secretary_tool(arguments)

        # Unknown tool: acknowledge with empty payload so the model can continue
        return {}
    
    async def _handle_update_form_fields_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle update_form_fields tool call."""
        # Parse and normalize updates
        updates_payload = self._parse_update_arguments(arguments)
        normalized_updates = self._normalize_updates(updates_payload)
        
        # Validate: Reject empty tool calls
        if not normalized_updates:
            _log.warning("empty_tool_call_rejected", session_id=self._session_id)
            return self._build_empty_tool_call_error()
        
        # Handle multiple field updates: process first, reject rest
        rejected_fields = []
        if len(normalized_updates) > 1:
            _log.warning("multiple_fields_sent", field_count=len(normalized_updates), 
                        fields=list(normalized_updates.keys()), session_id=self._session_id)
            # Keep only the first field, track the rest as rejected
            first_field = next(iter(normalized_updates))
            rejected_fields = [k for k in normalized_updates.keys() if k != first_field]
            normalized_updates = {first_field: normalized_updates[first_field]}
        
        # Execute update via service
        result = self._handle_update_fields(self._session_id, normalized_updates)
        
        if result is None:
            # No updates applied
            await self.send_form_update({}, [])
            return {
                "form_state": {},
                "applied_fields": [],
                "unknown_fields": list(normalized_updates.keys()),
            }
        
        # Extract results
        validation_errors = result.get("validation_errors", [])
        unknown_fields = result.get("unknown_fields", [])
        applied_fields = result.get("applied_fields", [])
        
        # Add rejected fields to validation errors if multiple fields were sent
        if rejected_fields:
            for field_id in rejected_fields:
                validation_errors.append({
                    "field_id": field_id,
                    "field_name": field_id,
                    "value": updates_payload.get(field_id, ""),
                    "constraint": "single_field_only",
                    "message": "Rejected - only one field per call allowed"
                })
        
        # Send form update to frontend (no next field info - save tokens)
        # Next field info will be sent after confirm_field to reduce round trips
        if not validation_errors and not unknown_fields and applied_fields:
            await self.send_form_update(
                result.get("form_state"),
                applied_fields,
                None  # No next_field_schema - send after confirmation
            )
            _log.info("field_update_success", applied=len(applied_fields))
        else:
            # Validation failed - send empty form_state so frontend doesn't apply invalid values
            await self.send_form_update({}, [])

        # Build and return tool response (no next field info - reduces tokens)
        tool_response = self._build_update_fields_response(
            validation_errors,
            unknown_fields,
            applied_fields,
            None,  # No next_field_hint - send after confirmation
            None,  # No next_field_schema - send after confirmation
            rejected_count=len(rejected_fields)
        )

        # Dev logging: Log tool response to daily file
        _dev_log.log_tool_response("update_form_fields", tool_response, session_id=self._session_id)
        
        return tool_response
    
    async def _handle_get_form_status_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get_form_status tool call with minimal token response."""
        field_ids = arguments.get("field_ids", []) if isinstance(arguments, dict) else []
        form_values = await self._request_form_state_from_client(field_ids)

        # Convert to ultra-compact format: field_id:value:status|field_id:value:status
        # Only include fields with values. Empty fields are omitted.
        # Status: "confirmed" or "unconfirmed"
        # Example: "firstName:John:confirmed|lastName:Doe:unconfirmed"
        compact_lines = []
        for field_id, field_data in form_values.items():
            if isinstance(field_data, dict):
                value = field_data.get("value")

                # Skip empty fields (not in response = empty)
                if not value:
                    continue

                confirmed = field_data.get("confirmed", False)
                status = "confirmed" if confirmed else "unconfirmed"

                compact_lines.append(f"{field_id}:{value}:{status}")
            else:
                # Legacy format (shouldn't happen but handle it)
                if field_data:  # Only include if has value
                    compact_lines.append(f"{field_id}:{field_data}:unconfirmed")

        compact_state = "|".join(compact_lines) if compact_lines else "No fields filled"

        response = {
            "state": compact_state,
        }
        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", tool="get_form_status", field_count=len(compact_lines))
        _log.info("-" * 80)
        return response
    
    async def _handle_switch_section_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle switch_section tool call."""
        section_identifier = arguments.get("section_identifier", "") if isinstance(arguments, dict) else str(arguments)
        response = await self._handle_switch_section(section_identifier)
        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", tool="switch_section", 
                 success=response.get("success"), section=section_identifier)
        _log.info("-" * 80)
        return response
    
    async def _handle_get_field_value_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get_field_value tool call."""
        spoken_name = arguments.get("spoken_name", "") if isinstance(arguments, dict) else str(arguments)
        response = await self._handle_get_field_value(spoken_name)
        _log.info("-" * 80)
        # spoken_name is user-speech-derived (e.g. "first name"); per the PII
        # policy (docs/standards/hipaa-pii-policy.md) we log its length, never the
        # value, since it reaches stdout -> Cloud Run logs (bd polyglot-pdf-t1c).
        _log.info("GEMINI TOOL RESPONSE", tool="get_field_value",
                 spoken_name_length=len(spoken_name or ""), found=response.get("found"))
        _log.info("-" * 80)
        return response

    async def _handle_ask_secretary_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle ask_secretary tool call (bd polyglot-pdf-jnjj.45c).

        The principal asks a plain-language question about the form; the secretary
        (cheap text model) answers in prose. Delegates to the injected
        FormFillingService handler, which assembles the form context (cached full
        schema + a fresh values/shown tail from the client) and runs the BLOCKING
        TextAIGemini.ask() under a timeout. The tool response carries the prose
        answer back for the principal to voice.

        Fail-open: if no handler is wired or the lookup yields nothing (timeout /
        error / empty), tell the principal to ask the user directly rather than
        leaving it stuck. Never surfaces an exception to the model.

        PII: log the query LENGTH + answer length only -- never the query text or
        the answer prose (both reach stdout -> Cloud Run logs).
        """
        query = arguments.get("query", "") if isinstance(arguments, dict) else ""

        fallback = (
            "The secretary could not look that up right now. Ask the user directly "
            "for the information you need."
        )

        if not self._handle_ask_secretary:
            _log.warning("ask_secretary_no_handler", session_id=self._session_id)
            return {"answer": fallback, "available": False}

        try:
            answer = await self._handle_ask_secretary(query)
        except Exception as exc:  # noqa: BLE001
            # The handler is expected to fail-open internally, but guard here too so
            # a bug can never crash the tool-call path / session loop.
            _log.warning(
                "ask_secretary_handler_error",
                exc_type=type(exc).__name__,
                session_id=self._session_id,
            )
            answer = ""

        if not answer:
            response = {"answer": fallback, "available": False}
        else:
            response = {"answer": answer, "available": True}

        _log.info("-" * 80)
        _log.info(
            "GEMINI TOOL RESPONSE", tool="ask_secretary",
            query_length=len(query or ""),
            answer_length=len(response["answer"]),
            available=response["available"],
        )
        _log.info("-" * 80)
        # Dev logging (gated, may include content): mirrors the other tools.
        _dev_log.log_tool_response("ask_secretary", response, session_id=self._session_id)
        return response

    # NOTE: the complete_section tool handler was removed (section completion is
    # auto-detected by the frontend when all fields are confirmed).

    async def _handle_confirm_field_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle confirm_field tool call from Gemini."""
        field_id = arguments.get("field_id", "") if isinstance(arguments, dict) else ""
        confirmation_method = arguments.get("confirmation_method", "verbal") if isinstance(arguments, dict) else "verbal"

        # SYNCHRONOUS confirm round-trip (bd polyglot-pdf-wpw.2 / WS-E2). The
        # frontend owns all field state, so it -- not the backend -- is the source
        # of truth for whether a field was actually confirmed. Ask it and WAIT for
        # the ack instead of the old fire-and-forget send that always read as
        # success. A field with no value cannot be confirmed (3.1's confirm-without-
        # fill skip); the frontend reports that back and we tell Gemini success:false
        # so it re-asks IN-BAND, rather than confabulating a confirmation and losing
        # the user's value.
        # An absent coordinator (None) means we CANNOT reach the frontend to verify
        # the confirm -- which is the same epistemic state as a confirm timeout: we
        # do not know whether it was recorded, so under wpw.2 we must NOT report
        # success (that would be the silent-success this round-trip exists to kill).
        # Collapse it to the timeout path. (request_coordinator is a required
        # positional, so None only arises in a test or a racing reconnect -- mirrors
        # the send_form_update None-guard, bd polyglot-pdf-pen.)
        confirm_ack = CONFIRM_REQUEST_TIMEOUT
        if self._request_coordinator is not None:
            confirm_ack = await self._request_coordinator.request_confirm_field(
                field_id, confirmation_method
            )

        if confirm_ack is CONFIRM_REQUEST_TIMEOUT or not isinstance(confirm_ack, dict):
            # Slow/disconnected client (the sentinel), or -- defensively -- any
            # unexpected non-dict ack: never read a non-answer as confirmed. Do NOT
            # request the next-field hint (we did not advance) and do NOT log a
            # confirmation that did not happen. (request_confirm_field only ever
            # returns the sentinel or a {recorded, reason} dict; the isinstance guard
            # is belt-and-suspenders against a future resolve-path regression --
            # fresh-eyes PR #141.)
            return self._confirm_failure_response(
                field_id,
                "Could not record the confirmation right now (the form did not "
                "respond). Do NOT assume the field is confirmed or that the form is "
                "complete -- ask the user to confirm again, or call get_form_status.",
            )

        if not confirm_ack.get("recorded"):
            # The field has no usable value yet, so the confirm could not be
            # recorded (the 0y7 loop-breaker, reported in-band). `reason` is a fixed
            # category token, never the field value (PII-free).
            reason = confirm_ack.get("reason")
            if reason == "no_value":
                guidance = (
                    f"Field '{field_id}' has no value yet, so it cannot be "
                    f"confirmed. Do NOT call confirm_field for it again -- that "
                    f"will keep failing. Ask the user for the value and call "
                    f"update_form_fields to fill it; only THEN confirm. (Only if "
                    f"THIS field is OPTIONAL and the user has none may you fill it "
                    f"with an empty value via update_form_fields; for a REQUIRED "
                    f"field keep asking for a real value -- an empty value will be "
                    f"rejected. Never retry the bare confirm either way.)"
                )
                # no_value is NOT retryable: re-confirming the SAME empty field fails
                # identically and wedges the model in a confirm loop (the DTI stall,
                # bd polyglot-pdf-jnjj.40). The recovery is to FILL, not retry; mark
                # it non-retryable so the model redirects instead of re-attempting.
                return self._confirm_failure_response(
                    field_id, guidance, retryable=False)
            guidance = (
                f"Field '{field_id}' could not be confirmed. Ask the user for "
                f"the value and fill it with update_form_fields before "
                f"confirming again."
            )
            return self._confirm_failure_response(field_id, guidance)

        # Recorded -- the confirmation actually took. Log it (anonymized, no PII)
        # only now: we must not log a confirmation that did not happen.
        if self._form_id and self._form_session_id:
            # Get field name from schema for logging (we need to request this from frontend)
            # For now, just log the field_id
            log_field_confirmation(
                form_id=self._form_id,
                form_session_id=self._form_session_id,
                field_id=field_id,
                field_name=None,  # Will be enriched by frontend if needed
                confirmation_method=confirmation_method
            )

        # SECTION-BOUNDARY SHORT-CIRCUIT (bd polyglot-pdf-njvh). When this confirm
        # completed the section, the frontend signalled section_complete in the ack
        # and is ALREADY tearing down the socket for switchToSection. Requesting the
        # next-field hint now would race that teardown and time out (the coordinator
        # returns HINT_REQUEST_TIMEOUT on the closing socket), making Gemini emit a
        # spurious "do NOT assume the form is complete" prompt at the exact moment the
        # section IS correctly auto-advancing. So we SKIP the hint request entirely:
        # the new section's first-field hint arrives via the section-switch flow.
        # This log line is also the section-boundary observability the Gemini I/O
        # dev-log can't provide (it does not record the FE-driven section switches).
        section_complete = bool(confirm_ack.get("section_complete"))
        if section_complete:
            _log.info(
                "confirm_section_boundary_skip_hint",
                field_id=field_id,
                session_id=self._session_id,
            )
            next_hint = None
            next_field_schema = None
            next_field_guidance = None
            message = (
                f"Field '{field_id}' confirmed -- that completes this section. The "
                f"form is advancing to the next section; wait for the next field."
            )
        else:
            # Get next unconfirmed field hint.
            # request_next_field_hint() returns one of three things (bd polyglot-pdf-tks):
            #   - a hint string -> there is a next field
            #   - None          -> frontend answered: form is genuinely complete
            #   - HINT_REQUEST_TIMEOUT (sentinel) -> frontend did NOT answer in time
            # A timeout must NOT be reported to Gemini as "All fields confirmed" -- doing
            # so made a slow round-trip masquerade as completion and Gemini wrapped the
            # form up early. On timeout we tell Gemini the hint is temporarily unavailable
            # and to keep going, never that the form is done.
            #
            # Guard the coordinator the same way send_form_update does (bd polyglot-pdf-pen).
            # The constructor takes request_coordinator as a REQUIRED positional, so it is
            # never None in production -- but a test or racing reconnect that passes None
            # would AttributeError here. An absent coordinator means "next field unknown",
            # which is the TIMEOUT semantics (NOT "complete"): we must not let a missing
            # coordinator masquerade as completion, so collapse it into the timeout path.
            if self._request_coordinator is None:
                next_hint_result = HINT_REQUEST_TIMEOUT
            else:
                next_hint_result = await self._request_coordinator.request_next_field_hint()
            hint_timed_out = next_hint_result is HINT_REQUEST_TIMEOUT
            # The value forwarded to Gemini must be JSON-serializable: collapse the
            # sentinel to None for the wire, but keep the timeout distinction in the
            # message text below.
            next_hint = None if hint_timed_out else next_hint_result

            # Get next field schema for JIT mode (consolidated here to save tokens).
            # Skip on timeout: we don't know what the next field is.
            next_field_schema = None
            if self._get_next_field_schema_for_jit and next_hint:
                next_field_schema = self._get_next_field_schema_for_jit(field_id)

            # DTI (bd polyglot-pdf-jnjj.22): the next field's full guidance is
            # CLIENT-SUPPLIED -- the client owns the schema, so it rides the
            # next_field_hint_response and is stashed on the coordinator. Render it
            # (same render_field_guidance the DTI system instruction uses for field
            # 1) into next_field_guidance. Skip on timeout / no hint.
            next_field_guidance = None
            if get_settings().USE_DTI and next_hint and self._request_coordinator:
                client_next_schema = self._request_coordinator.consume_pending_next_field_schema()
                if client_next_schema:
                    next_field_guidance = render_field_guidance(client_next_schema)
                    # Merge the field into the backend's validation schema so the
                    # SUBSEQUENT update_form_fields for this field is not rejected as
                    # 'unknown' (in DTI/JIT mode _schema['fields'] holds only field 1;
                    # Codex PR #229). Schema only -- no user values.
                    if self._merge_field_schema:
                        self._merge_field_schema(client_next_schema)

            if hint_timed_out:
                message = (
                    f"Field '{field_id}' confirmed. (Could not determine the next field "
                    f"right now -- do NOT assume the form is complete; ask the user for "
                    f"the next piece of information or call get_form_status.)"
                )
            elif not next_hint:
                message = f"Field '{field_id}' confirmed. All fields confirmed."
            else:
                # Don't duplicate hint in message - Gemini sees next_field_hint separately
                message = f"Field '{field_id}' confirmed."

        response = {
            "success": True,
            "field_confirmed": field_id,
            "next_field_hint": next_hint,
            "message": message,
        }

        # Add next field schema if available (JIT mode)
        if next_field_schema:
            response["next_field_schema"] = next_field_schema

        # Add the rendered next-field guidance (DTI mode). This is the per-field
        # guidance the thin-principal SI points at ("use the LATEST confirm_field
        # response's next_field_guidance"); bd polyglot-pdf-jnjj.22.
        if next_field_guidance:
            response["next_field_guidance"] = next_field_guidance

        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", tool="confirm_field", field_id=field_id, confirmation_method=confirmation_method)
        _log.info("-" * 80)

        # Dev logging: Log full response (dev only!)
        _dev_log.log_tool_response("confirm_field", response, session_id=self._session_id)

        return response

    def _confirm_failure_response(self, field_id: str, message: str,
                                  retryable: bool = True) -> Dict[str, Any]:
        """Build the confirm_field tool response for a confirm that did NOT take
        (bd polyglot-pdf-wpw.2).

        Carries the WS-C2 structured-error keys (status/retryable/error -- bd
        polyglot-pdf-wpw.1) so the failure reads to Gemini as an actual tool
        failure (the documented Live API failure shape uses an ``error`` key),
        merged with the confirm-specific keys. The shape is duplicated here rather
        than imported from the adapter's private ``_tool_error_envelope`` so the
        services layer does not depend on adapter internals (and does not pull the
        heavy genai SDK module in at import time); the key set is kept in sync with
        WS-C2 deliberately. ``message`` is a fixed, caller-controlled string --
        never a field value (PII-free).

        ``retryable`` defaults True (a transient/timeout confirm -- re-ask is the
        right move) but is set False for the no_value case: re-confirming an empty
        field fails identically and wedges the model in a confirm loop, so the
        recovery is to FILL, not retry (bd polyglot-pdf-jnjj.40)."""
        response = {
            "success": False,
            "field_confirmed": None,
            "next_field_hint": None,
            "status": "error",
            "retryable": retryable,
            "error": message,
            "message": message,
        }
        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", tool="confirm_field", field_id=field_id, confirmed=False)
        _log.info("-" * 80)
        _dev_log.log_tool_response("confirm_field", response, session_id=self._session_id)
        return response

    # Helper methods

    def _parse_update_arguments(self, arguments: Any) -> Dict[str, Any]:
        """Parse raw update arguments into normalized dict.

        HALLUCINATION_REDUCTION (Oct 30, 2025): Now supports single-field format.
        New format: {"field_id": "firstName", "value": "Alice"}
        Old format: {"updates": {"firstName": "Alice", "lastName": "Smith"}} (commented out)
        """
        updates_payload: Dict[str, Any] = {}

        # NEW SINGLE-FIELD FORMAT: {"field_id": "...", "value": "..."}
        if isinstance(arguments, dict) and "field_id" in arguments:
            field_id = arguments.get("field_id")
            value = arguments.get("value")
            if field_id is not None:
                updates_payload = {str(field_id): value}
            return updates_payload

        # OLD MULTI-FIELD FORMAT (preserved for potential revert)
        # raw_updates: Any = arguments
        #
        # if isinstance(arguments, dict) and "updates" in arguments:
        #     raw_updates = arguments["updates"]
        #
        # if isinstance(raw_updates, str):
        #     try:
        #         updates_payload = json.loads(raw_updates)
        #     except json.JSONDecodeError:
        #         updates_payload = {}
        # elif isinstance(raw_updates, dict):
        #     updates_payload = raw_updates
        # elif isinstance(raw_updates, list):
        #     updates_payload = {}
        #     for item in raw_updates:
        #         if isinstance(item, dict):
        #             name = item.get("display_name") or item.get("name") or item.get("id")
        #             value = item.get("value")
        #             if name is not None:
        #                 updates_payload[str(name)] = value

        return updates_payload
    
    def _normalize_updates(self, updates_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize updates by unwrapping nested value objects."""
        normalized_updates: Dict[str, Any] = {}
        for key, value in updates_payload.items():
            if isinstance(value, dict) and "value" in value:
                normalized_updates[key] = value.get("value")
            else:
                normalized_updates[key] = value
        return normalized_updates
    
    def _build_empty_tool_call_error(self) -> Dict[str, Any]:
        """Build error response for empty tool calls."""
        error_response = {
            "success": False,
            "applied_fields": [],
            "validation_errors": [],
            "unknown_fields": [],
            "message": "ERROR: update_form_fields called with empty updates. You must provide at least one field to update. If the user hasn't provided information yet, ask them for the specific field value instead of calling this tool with no data."
        }
        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE (EMPTY TOOL CALL)", success=False, returning_error=True)
        _log.info("-" * 80)
        return error_response

    def _build_update_fields_response(
        self,
        validation_errors: list,
        unknown_fields: list,
        applied_fields: list,
        next_field_hint: Optional[str],
        next_field_schema: Optional[Dict[str, Any]] = None,
        rejected_count: int = 0
    ) -> Dict[str, Any]:
        """Build tool response for update_form_fields.

        Args:
            validation_errors: List of validation error objects
            unknown_fields: List of unknown field IDs
            applied_fields: List of successfully applied field IDs
            next_field_hint: Spoken name hint for next field
            next_field_schema: Full schema for next field (JIT loading - Phase 2.5)
            rejected_count: Number of fields rejected due to multi-field constraint

        Returns:
            Tool response dict for Gemini
        """
        if validation_errors or unknown_fields:
            # Build error response
            error_lines = []
            
            # Add warning for multiple fields if any were rejected
            if rejected_count > 0:
                error_lines.append(
                    f"IMPORTANT: You sent {rejected_count + len(applied_fields)} fields but can only update ONE field per call. "
                    f"First field was processed, others rejected. Call update_form_fields separately for each field."
                )
            
            # Format validation errors concisely
            for err in validation_errors:
                field_name = err.get("field_name", err.get("field_id"))
                value = err.get("value")
                constraint = err.get("constraint", "")
                constraint_value = err.get("constraint_value")
                valid_options = err.get("valid_options")
                
                parts = [f"{field_name}: '{value}'"]
                
                if constraint_value is not None:
                    parts.append(f"{constraint}={constraint_value}")
                elif valid_options:
                    # valid_options should already be a list of bare string values
                    # (the field validator extracts them from {value, label} dict
                    # options via _option_values). Coerce defensively anyway so a
                    # stray non-str option can never crash this error formatter --
                    # an unguarded join here raised "TypeError: sequence item 0:
                    # expected str instance, dict found" and the Live adapter
                    # swallowed it, silently failing the save (bd polyglot-pdf-jnjj.1
                    # / d24n).
                    opts_sample = ", ".join(str(o) for o in valid_options[:3])
                    if len(valid_options) > 3:
                        opts_sample += f"... ({len(valid_options)} total)"
                    parts.append(f"valid={opts_sample}")
                
                error_lines.append(" | ".join(parts))
            
            # Format unknown fields
            for field_id in unknown_fields:
                error_lines.append(f"{field_id}: unknown field")
            
            # Build message
            message_parts = []
            if error_lines:
                message_parts.append("ERRORS: " + "; ".join(error_lines))
            if applied_fields:
                message_parts.append(f"OK: {', '.join(applied_fields)}")
            
            tool_response = {
                "success": False,
                "applied_fields": applied_fields,
                "validation_errors": validation_errors,
                "unknown_fields": unknown_fields,
                "message": "\n".join(message_parts)
            }
        else:
            # All fields valid - include next_field_schema (if JIT enabled)
            # Don't put hint in message - it confuses Gemini since next_field_schema has different field
            tool_response = {
                "success": True,
                "applied_fields": applied_fields,
                "message": "Fields updated successfully.",
            }

            # Include next field schema if available (Phase 2.5: JIT schema loading)
            # This contains id, name, spoken_name, type - everything Gemini needs
            if next_field_schema:
                tool_response["next_field_schema"] = next_field_schema
        
        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", success=tool_response.get("success"), 
                 applied_count=len(tool_response.get("applied_fields", [])),
                 has_errors=bool(tool_response.get("validation_errors") or tool_response.get("unknown_fields")))
        _log.info("-" * 80)
        
        return tool_response
