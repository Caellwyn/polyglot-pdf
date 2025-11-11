"""
Callback handler for Gemini Live AI session events.

Handles callbacks for form updates, transcripts, audio, and tool calls.
Extracted from FormFillingService for better testability and separation of concerns.
"""
import json
from typing import Any, Dict, Optional
from fastapi import WebSocket
import structlog

from .request_coordinator import RequestCoordinator
from backend.utils.dev_file_logger import get_dev_logger

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
    ):
        """
        Initialize callback handler.
        
        Args:
            websocket: WebSocket connection to frontend
            session_id: Session ID for logging
            request_coordinator: Coordinator for async requests to frontend
            send_transcript: Whether to send transcript events to frontend
        """
        self._websocket = websocket
        self._session_id = session_id
        self._request_coordinator = request_coordinator
        self._send_transcript = send_transcript
        self._ws_audio_chunk_count = 0
        
        # Service methods will be injected
        self._handle_update_fields = None
        self._handle_switch_section = None
        self._handle_get_field_value = None
        self._handle_complete_section = None
        self._request_form_state_from_client = None
        self._get_next_field_schema_for_jit = None

    def set_tool_handlers(
        self,
        handle_update_fields,
        handle_switch_section,
        handle_get_field_value,
        handle_complete_section,
        request_form_state_from_client,
        get_next_field_schema_for_jit,
    ):
        """Inject tool handler methods from FormFillingService."""
        self._handle_update_fields = handle_update_fields
        self._handle_switch_section = handle_switch_section
        self._handle_get_field_value = handle_get_field_value
        self._handle_complete_section = handle_complete_section
        self._request_form_state_from_client = request_form_state_from_client
        self._get_next_field_schema_for_jit = get_next_field_schema_for_jit
    
    async def send_form_update(
        self,
        data: Optional[Dict[str, Any]],
        applied_fields: Optional[list] = None
    ) -> Optional[str]:
        """
        Send form state update to frontend.
        
        Sends the form state to the connected websocket client and includes
        the list of fields that were actually applied. Also requests next_field_hint
        in the same message to reduce round trips.
        
        Args:
            data: Form state data to send
            applied_fields: List of field IDs that were actually applied
            
        Returns:
            Next field hint string or None
        """
        if self._websocket and data is not None:
            payload = {"form_state": data}
            if applied_fields is not None:
                payload["applied_fields"] = applied_fields
            
            await self._websocket.send_json({"type": "form_updated", "data": payload})
            
            # Request next field hint via coordinator
            if self._request_coordinator:
                hint = await self._request_coordinator.request_next_field_hint()
                return hint
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
                    _log.info("📡 [WebSocket Audio] Sending first audio chunk to client", 
                             session_id=self._session_id, bytes=len(data))
                
                await self._websocket.send_bytes(data)
            except Exception as e:
                # Swallow errors to avoid crashing the session loop
                _log.warning("websocket_audio_send_failed", error=str(e), session_id=self._session_id)
    
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
        # Development (_dev_log): MAY log field values ONLY when VFF_DEV_LOGGING=true
        #   - Writes to local files: backend/logs/gemini_YYYY-MM-DD.jsonl
        #   - Never deployed to production
        #   - Used for local debugging only
        # ============================================================================

        # Production logging: Log tool name and argument KEYS only (no values)
        _log.info("🔧 tool_call_received",
                 tool_name=tool_name,
                 session_id=self._session_id,
                 arg_keys=list(arguments.keys()) if arguments else [])

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
        
        if normalized == "complete_section":
            return await self._handle_complete_section_tool()
        
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
        
        # Request next hint only if ALL fields were valid
        next_field_hint = None
        next_field_schema = None
        if not validation_errors and not unknown_fields and applied_fields:
            next_field_hint = await self.send_form_update(result.get("form_state"), applied_fields)
            _log.info("field_update_success", applied=len(applied_fields),
                     next_hint_length=len(next_field_hint) if next_field_hint else 0)

            # Get next field's schema for JIT loading (Phase 2.5: Token Reduction)
            if self._get_next_field_schema_for_jit and applied_fields:
                # Get the first (and only) applied field ID
                updated_field_id = applied_fields[0]
                next_field_schema = self._get_next_field_schema_for_jit(updated_field_id)
        else:
            await self.send_form_update(result.get("form_state"), applied_fields)

        # Build and return tool response
        tool_response = self._build_update_fields_response(
            validation_errors,
            unknown_fields,
            applied_fields,
            next_field_hint,
            next_field_schema,
            rejected_count=len(rejected_fields)
        )

        # Dev logging: Log tool response to daily file
        _dev_log.log_tool_response("update_form_fields", tool_response, session_id=self._session_id)
        
        return tool_response
    
    async def _handle_get_form_status_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get_form_status tool call."""
        field_ids = arguments.get("field_ids", []) if isinstance(arguments, dict) else []
        form_values = await self._request_form_state_from_client(field_ids)
        response = {
            "field_values": form_values,
            "message": f"Retrieved {len(form_values)} field value(s) from client.",
        }
        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", tool="get_form_status", field_count=len(form_values))
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
        _log.info("GEMINI TOOL RESPONSE", tool="get_field_value", 
                 spoken_name=spoken_name, found=response.get("found"))
        _log.info("-" * 80)
        return response
    
    async def _handle_complete_section_tool(self) -> Dict[str, Any]:
        """Handle complete_section tool call."""
        response = await self._handle_complete_section()
        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", tool="complete_section", success=response.get("success"))
        _log.info("-" * 80)
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
                    f"⚠️ IMPORTANT: You sent {rejected_count + len(applied_fields)} fields but can only update ONE field per call. "
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
                    # Extract just the 'value' from each option for display
                    # (valid_options is now a list of strings, not dict representations)
                    opts_sample = ", ".join(valid_options[:3])
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
            # All fields valid - include next_field_hint and schema (if JIT enabled)
            tool_response = {
                "success": True,
                "applied_fields": applied_fields,
                "message": next_field_hint or "Fields updated successfully.",
            }

            # Include next field schema if available (Phase 2.5: JIT schema loading)
            if next_field_schema:
                tool_response["next_field_schema"] = next_field_schema
        
        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", success=tool_response.get("success"), 
                 applied_count=len(tool_response.get("applied_fields", [])),
                 has_errors=bool(tool_response.get("validation_errors") or tool_response.get("unknown_fields")))
        _log.info("-" * 80)
        
        return tool_response
