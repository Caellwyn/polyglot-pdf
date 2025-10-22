from fastapi import WebSocket
from typing import Any, Dict, Optional, List
import json
from copy import deepcopy

from backend.config import Settings, get_settings
from ..ports.live_ai_port import ILiveAI
import structlog
import os
from datetime import datetime


def _ensure_logs_dir():
    try:
        logs_dir = os.path.join(os.getcwd(), ".logs")
        os.makedirs(logs_dir, exist_ok=True)
        return logs_dir
    except Exception:
        return None


def _append_tool_call_log(entry: dict):
    try:
        logs_dir = _ensure_logs_dir()
        if not logs_dir:
            return
        path = os.path.join(logs_dir, "gemini_tool_calls.log")
        ts = datetime.utcnow().isoformat() + "Z"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(ts + " " + json.dumps(entry, default=str) + "\n")
    except Exception:
        pass

# Logger for service-level diagnostics
_log = structlog.get_logger().bind(service="FormFillingService")


class FormFillingService:
    """Orchestrates the logic for filling form fields based on AI tool calls (web forms only)."""

    def __init__(
        self,
        live_ai: Optional[ILiveAI] = None,
        settings: Optional[Settings] = None,
    ):
        # AI adapter is optional for unit tests that only exercise form logic
        self._live_ai = live_ai
        self._settings = settings or get_settings()
        self._websocket = None
        self._session_id = None
        # Web session state - schema only (no field caching)
        self._schema: Optional[Dict[str, Any]] = None  # Schema for context only
        self._fill_language: str = "English"  # Default fill language
        self._spoken_language: str = "English"  # Default spoken conversation language (persists across sections)
        # Pending form state requests (for async request/response pattern)
        self._pending_form_state_request: Optional[Dict[str, Any]] = None
        self._pending_next_field_request: Optional[Dict[str, Any]] = None
        self._pending_field_value_request: Optional[Dict[str, Any]] = None
        # Store callbacks for reuse during section switching
        self._on_form_update = None
        self._on_transcript = None
        self._on_audio = None
        self._on_tool_call = None
        self._send_transcript = False

    def _build_fields_from_schema(self) -> list:
        """Build field list from schema on-demand (no caching).
        
        Used by web sessions to construct field objects for tool responses.
        Backend doesn't persist these - they're rebuilt each time.
        """
        from backend.models.form_models import FormField, Rect
        
        fields = []
        schema = self._schema or {}
        
        for field_data in schema.get("fields", []):
            # Build FormField-like object from schema
            # Web forms don't have physical rectangles, use dummy rect
            dummy_rect = Rect(x0=0, y0=0, x1=100, y1=20)
            
            field = FormField(
                id=field_data.get("id"),
                name=field_data.get("name"),
                spoken_name=field_data.get("name"),  # Use same for web
                spoken_aliases=[],
                page_index=field_data.get("page_index", 0),
                rect=dummy_rect,  # Web forms need dummy rect for validation
                field_type=field_data.get("type", "text"),
                type=field_data.get("type", "text"),
                value=field_data.get("value"),
                options=field_data.get("allowed_values") or field_data.get("options") or [],
                meta={},  # Backend doesn't track meta for web
            )
            fields.append(field)
        
        return fields

    async def start_session(
        self,
        websocket: WebSocket,
        session_id: str,
        send_transcript: bool = False,
        *,
        accept_connection: bool = True,
        schema: Optional[Dict[str, Any]] = None,
        current_values: Optional[Dict[str, Any]] = None,
        system_instruction: Optional[str] = None,
    ):
        """Start a voice form filling session (web forms only).
        
        Initializes the session and registers callbacks with system instruction
        included in the initial Gemini connection config.
        
        Args:
            websocket: WebSocket connection
            session_id: Ephemeral session ID for logging
            send_transcript: Whether to send transcript events
            accept_connection: Whether to accept the WebSocket connection
            schema: Form schema (stored for context generation, not for state)
            current_values: Pre-filled values (ignored by backend - client is source of truth)
            system_instruction: System instruction to include in initial Gemini config
        """
        self._websocket = websocket
        self._session_id = session_id
        self._send_transcript = send_transcript  # Store for reuse in section switching
        
        # Store schema for context generation
        self._schema = schema
        # Note: current_values are ignored by backend - client is source of truth
        
        if accept_connection:
            await self._websocket.accept()

        def _ordered_fields() -> list[Any]:
            """Build field list from schema on-demand (no caching)."""
            from backend.models.form_models import FormField, Rect
            fields = []
            
            # Use instance variable for schema
            current_schema = self._schema or {}
            for field_data in current_schema.get("fields", []):
                # Build FormField-like object from schema
                # Web forms don't have physical rectangles, use dummy rect
                dummy_rect = Rect(x0=0, y0=0, x1=100, y1=20)
                
                field = FormField(
                    id=field_data.get("id"),
                    name=field_data.get("name"),
                    spoken_name=field_data.get("name"),  # Use same for web
                    spoken_aliases=[],
                    page_index=field_data.get("page_index", 0),
                    rect=dummy_rect,  # Web forms need dummy rect for validation
                    value=field_data.get("value"),
                    field_type=field_data.get("type"),
                    options=field_data.get("options", []),
                    normalized_options=field_data.get("options", []),
                    group_id=None,
                    section_id=None,
                    meta=field_data.get("meta", {}),
                )
                
                # Note: We don't apply current_values here - backend is stateless
                # Client sends values in form_state messages which are proxied to Gemini
                # Field values remain at schema defaults (usually None/empty)
                
                fields.append(field)
            
            return fields

        def build_form_metadata() -> list[Dict[str, Any]]:
            """Build field metadata with optional current values from client.
            
            Backend doesn't store values - they're passed through from client
            when provided in current_values parameter.
            """
            metadata: list[Dict[str, Any]] = []
            filled_count = 0
            
            for idx, field in enumerate(_ordered_fields(), start=1):
                # Prefer the spoken_name produced by the LLM normalizer for
                # AI-facing labels. Fall back to the field name or id.
                ai_label = getattr(field, "spoken_name", None) or field.name or field.id
                field_id = field.id
                
                # Check if client provided a current value for this field
                has_value = False
                value_status = "(empty)"
                if current_values and field_id in current_values:
                    value = current_values.get(field_id)
                    if value:  # Non-empty value
                        has_value = True
                        value_status = f"(FILLED: '{value}')"
                        filled_count += 1
                
                metadata.append(
                    {
                        "order": idx,
                        "display_name": ai_label,
                        "field_id": field_id,
                        "type": field.field_type or field.type,
                        "page_index": field.page_index,
                        "allowed_values": list(field.options or []),
                        "status": value_status,  # Show if already filled
                    }
                )
            
            # Log pre-filled status for debugging
            if filled_count > 0:
                _log.info("prefilled_fields_detected", 
                         session_id=session_id,
                         filled=filled_count, 
                         total=len(metadata))
            
            return metadata

        # system_instruction is now passed as parameter
        # and included in the initial Gemini connection config (not sent as updates)
        # DO NOT shadow the parameter here!

        async def send_form_update(data: dict | None, applied_fields: list | None = None):
            # Send the form state to the connected websocket client and
            # include the list of fields that were actually applied when
            # available. This helps the frontend decide which fields to mark
            # confirmed instead of naïvely treating every field in the
            # payload as confirmed.
            # 
            # Also request next_field_hint in the same message to reduce round trips
            if self._websocket and data is not None:
                payload = {"form_state": data}
                if applied_fields is not None:
                    payload["applied_fields"] = applied_fields
                
                # Generate request ID for next field hint
                import uuid
                request_id = str(uuid.uuid4())
                payload["request_next_field_hint"] = True
                payload["request_id"] = request_id
                
                # Create future for the hint response
                import asyncio
                future = asyncio.Future()
                self._pending_next_field_request = {
                    "request_id": request_id,
                    "future": future,
                }
                
                await self._websocket.send_json({"type": "form_updated", "data": payload})
                
                # Wait for response with hint
                try:
                    hint = await asyncio.wait_for(future, timeout=2.0)
                    return hint
                except asyncio.TimeoutError:
                    _log.error("next_field_hint_timeout_after_update", session_id=self._session_id)
                    self._pending_next_field_request = None
                    return None
                except Exception as exc:
                    _log.error("next_field_hint_error_after_update", session_id=self._session_id, error=str(exc))
                    self._pending_next_field_request = None
                    return None
            return None

        async def on_form_update(data: dict):
            # Legacy callback path: just forward updates to the websocket.
            await send_form_update(data)

        async def on_transcript(text: str):
            # Send transcript to client if requested
            if self._websocket and send_transcript:
                await self._websocket.send_json({"type": "transcript", "data": text})
            
            # ALWAYS signal turn complete for activity watchdog (regardless of send_transcript setting)
            # Transcript arrives after all audio chunks, indicating Gemini finished speaking
            # This is critical for Level 3 farewell disconnect timing
            if self._websocket:
                try:
                    await self._websocket.send_json({"type": "turn_complete"})
                except Exception as e:
                    _log.warning("failed_to_send_turn_complete", error=str(e), session_id=session_id)

        async def on_audio(data: bytes):
            """Forward raw audio bytes from Gemini to the connected websocket client.

            The client is expected to handle raw PCM audio playback. We send the
            bytes as a binary WebSocket frame to avoid logging or JSON encoding.
            """
            if self._websocket:
                try:
                    # Track audio chunks being sent to client
                    if not hasattr(self, '_ws_audio_chunk_count'):
                        self._ws_audio_chunk_count = 0
                    self._ws_audio_chunk_count += 1
                    
                    if self._ws_audio_chunk_count == 1:
                        _log.info("📡 [WebSocket Audio] Sending first audio chunk to client", 
                                 session_id=self._session_id, bytes=len(data))
                    
                    await self._websocket.send_bytes(data)
                except Exception as e:
                    # Swallow errors to avoid crashing the session loop; the
                    # websocket may have closed concurrently.
                    _log.warning("websocket_audio_send_failed", error=str(e), session_id=self._session_id)

        async def on_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            """Handle tool calls originating from the live AI session."""
            
            # Dev logging: Clear, readable output for debugging
            from backend.utils.dev_logger import log_tool_call
            log_tool_call(tool_name, arguments, session_id=self._session_id)

            _log.info("=" * 80)
            _log.info("GEMINI TOOL CALL", tool=tool_name, arg_keys=list(arguments.keys()) if isinstance(arguments, dict) else "non-dict")
            _log.info("=" * 80)
            
            if self._session_id is None:
                _log.error("tool_call_no_session", tool_name=tool_name)
                return None

            normalized = (tool_name or "").lower()

            if normalized in {"update_form_fields"}:
                updates_payload: Dict[str, Any] = {}
                raw_updates: Any = arguments
                if isinstance(arguments, dict) and "updates" in arguments:
                    raw_updates = arguments["updates"]

                if isinstance(raw_updates, str):
                    try:
                        updates_payload = json.loads(raw_updates)
                    except json.JSONDecodeError:
                        updates_payload = {}
                elif isinstance(raw_updates, dict):
                    updates_payload = raw_updates
                elif isinstance(raw_updates, list):
                    updates_payload = {}
                    for item in raw_updates:
                        if isinstance(item, dict):
                            name = item.get("display_name") or item.get("name") or item.get("id")
                            value = item.get("value")
                            if name is not None:
                                updates_payload[str(name)] = value

                # Some models wrap values in nested objects (e.g., {"Full Name": {"value": "Jane"}})
                normalized_updates: Dict[str, Any] = {}
                for key, value in updates_payload.items():
                    if isinstance(value, dict) and "value" in value:
                        normalized_updates[key] = value.get("value")
                    else:
                        normalized_updates[key] = value
                
                # Validate: Reject empty tool calls
                if not normalized_updates:
                    _log.warning("empty_tool_call_rejected", session_id=self._session_id)
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
                
                result = self.handle_update_fields_tool_call(self._session_id, normalized_updates)
                
                if result is not None:
                    validation_errors = result.get("validation_errors", [])
                    unknown_fields = result.get("unknown_fields", [])
                    applied_fields = result.get("applied_fields", [])
                    
                    # Only request next field hint if ALL fields were valid
                    next_field_hint = None
                    if not validation_errors and not unknown_fields and applied_fields:
                        # All fields valid - request next hint
                        next_field_hint = await send_form_update(result.get("form_state"), applied_fields)
                        _log.info("field_update_success", applied=len(applied_fields), next_hint_length=len(next_field_hint) if next_field_hint else 0)
                    else:
                        # Validation errors present - send form update without requesting hint
                        await send_form_update(result.get("form_state"), applied_fields)
                        _log.warning("field_update_errors", 
                                   validation_errors=len(validation_errors),
                                   unknown_fields=len(unknown_fields),
                                   applied=len(applied_fields))
                    
                    try:
                        # Redact field values from log - only log field names/IDs and counts
                        _append_tool_call_log({
                            "event": "tool_call_update_applied",
                            "session_id": self._session_id,
                            "applied_count": len(result.get("applied_fields", [])),
                            "applied_field_ids": result.get("applied_fields", []),
                            "unknown_count": len(result.get("unknown_fields", [])),
                            "unknown_field_ids": result.get("unknown_fields", []),
                            "validation_error_count": len(result.get("validation_errors", [])),
                            "validation_error_field_ids": [e.get("field_id") or e.get("field_name") for e in result.get("validation_errors", [])],
                            # DO NOT LOG: arguments (contains field values), validation_errors (contains values)
                        })
                    except Exception:
                        pass
                    
                    # Build tool response with validation errors if present
                    validation_errors = result.get("validation_errors", [])
                    unknown_fields = result.get("unknown_fields", [])
                    applied_fields = result.get("applied_fields", [])
                    
                    # If there are validation or unknown field errors, include them in response
                    if validation_errors or unknown_fields:
                        error_lines = []
                        
                        # Format validation errors concisely with constraint info
                        for err in validation_errors:
                            field_name = err.get("field_name", err.get("field_id"))
                            value = err.get("value")
                            constraint = err.get("constraint", "")
                            constraint_value = err.get("constraint_value")
                            valid_options = err.get("valid_options")
                            
                            # Build concise error: field: value -> constraint: constraint_value
                            parts = [f"{field_name}: '{value}'"]
                            
                            if constraint_value is not None:
                                parts.append(f"{constraint}={constraint_value}")
                            elif valid_options:
                                # Show first 3 options as examples
                                opts_sample = ", ".join(valid_options[:3])
                                if len(valid_options) > 3:
                                    opts_sample += f"... ({len(valid_options)} total)"
                                parts.append(f"valid={opts_sample}")
                            
                            error_lines.append(" | ".join(parts))
                        
                        # Format unknown fields
                        for field_id in unknown_fields:
                            error_lines.append(f"{field_id}: unknown field")
                        
                        # Concise response (NO next_field_hint when there are errors)
                        message_parts = []
                        if error_lines:
                            message_parts.append("ERRORS: " + "; ".join(error_lines))
                        if applied_fields:
                            message_parts.append(f"OK: {', '.join(applied_fields)}")
                        
                        tool_response = {
                            "success": False,  # Always false when there are errors
                            "applied_fields": applied_fields,
                            "validation_errors": validation_errors,
                            "unknown_fields": unknown_fields,
                            "message": "\n".join(message_parts)
                        }
                    else:
                        # All fields valid - include next_field_hint
                        tool_response = {
                            "success": True,
                            "applied_fields": applied_fields,
                            "message": next_field_hint or "Fields updated successfully.",
                        }
                    
                    # REDACT: Don't log tool_response content (contains field values/errors with values)
                    _log.info("-" * 80)
                    _log.info("GEMINI TOOL RESPONSE", success=tool_response.get("success"), 
                             applied_count=len(tool_response.get("applied_fields", [])),
                             has_errors=bool(tool_response.get("validation_errors") or tool_response.get("unknown_fields")))
                    _log.info("-" * 80)
                    
                    # Dev logging: Show full response for debugging
                    from backend.utils.dev_logger import log_tool_response
                    log_tool_response(tool_name, tool_response, session_id=self._session_id)
                    
                    return tool_response
                else:
                    # No updates applied: still forward an empty response and an
                    # empty applied_fields list so the client doesn't incorrectly
                    # mark fields confirmed.
                    await send_form_update({}, [])
                    return {
                        "form_state": {},
                        "applied_fields": [],
                        "unknown_fields": list(normalized_updates.keys()),
                    }

            if normalized in {"get_form_status", "get_form_state"}:
                # Request current form state from frontend (stateless architecture)
                field_ids = arguments.get("field_ids", []) if isinstance(arguments, dict) else []
                form_values = await self.request_form_state_from_client(field_ids)
                response = {
                    "field_values": form_values,
                    "message": f"Retrieved {len(form_values)} field value(s) from client.",
                }
                # REDACT: Don't log response (contains field values)
                _log.info("-" * 80)
                _log.info("GEMINI TOOL RESPONSE", tool="get_form_status", field_count=len(form_values))
                _log.info("-" * 80)
                return response

            if normalized == "switch_section":
                # Navigate to different section by number or name
                section_identifier = arguments.get("section_identifier", "") if isinstance(arguments, dict) else str(arguments)
                response = await self.handle_switch_section(section_identifier)
                # REDACT: Response may contain section metadata but should be safe
                _log.info("-" * 80)
                _log.info("GEMINI TOOL RESPONSE", tool="switch_section", 
                         success=response.get("success"), section=section_identifier)
                _log.info("-" * 80)
                return response

            if normalized == "get_field_value":
                # Look up field value by spoken name from any section
                spoken_name = arguments.get("spoken_name", "") if isinstance(arguments, dict) else str(arguments)
                response = await self.handle_get_field_value(spoken_name)
                # REDACT: Don't log response (contains field value)
                _log.info("-" * 80)
                _log.info("GEMINI TOOL RESPONSE", tool="get_field_value", 
                         spoken_name=spoken_name, found=response.get("found"))
                _log.info("-" * 80)
                return response

            if normalized == "complete_section":
                # Mark current section complete and advance to next
                response = await self.handle_complete_section()
                # REDACT: Response should be safe (just status)
                _log.info("-" * 80)
                _log.info("GEMINI TOOL RESPONSE", tool="complete_section", success=response.get("success"))
                _log.info("-" * 80)
                return response

            # Unknown tool: acknowledge with empty payload so the model can continue.
            return {}

        # Use web form tool declarations (stateless)
        tool_declarations = deepcopy(self._settings.TOOL_DECLARATIONS)

        if self._live_ai is not None:
            # Register callbacks including audio so incoming Gemini audio is
            # forwarded to the websocket client without being logged.
            # `on_audio` is optional and will be ignored by adapters that do not
            # implement it.
            # System instruction is passed from caller and included in the initial
            # Gemini connection config.
            try:
                self._live_ai.set_callbacks(
                    on_form_update=on_form_update,
                    on_transcript=on_transcript,
                    on_audio=on_audio,
                    on_tool_call=on_tool_call,
                    system_instruction=system_instruction,
                    tool_declarations=tool_declarations,
                    enable_transcripts=bool(send_transcript),
                )
            except TypeError:
                # Adapter does not accept on_audio (older implementations); fall
                # back to previous behavior.
                # Call the older signature without on_audio/enable_transcripts
                try:
                    self._live_ai.set_callbacks(
                        on_form_update=on_form_update,
                        on_transcript=on_transcript,
                        on_tool_call=on_tool_call,
                        system_instruction=system_instruction,
                        tool_declarations=tool_declarations,
                    )
                except TypeError:
                    # If this also fails, give up silently — the adapter
                    # truly doesn't implement callback registration.
                    pass

    async def stream_audio(self, audio_chunk: bytes):
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return
        # Log first audio chunk to verify flow
        if not hasattr(self, '_first_service_audio_logged'):
            _log.info("🎤 [Service] First audio chunk forwarding to LiveAI", bytes=len(audio_chunk))
            self._first_service_audio_logged = True
        await self._live_ai.stream_audio(audio_chunk)

    async def send_context_hint(self, hint_text: str):
        """
        Send a context hint (e.g., next field to fill) to Gemini as a text message.
        
        This is sent asynchronously after tool responses, allowing frontend to
        provide navigation guidance without blocking tool call latency.
        
        Args:
            hint_text: Text message to send to Gemini (e.g., "Next unfilled field is 'email'")
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return
        # No logging - too verbose for recovery prompts
        await self._live_ai.send_text_message(hint_text)

    async def send_manual_field_update(self, field_id: str, field_name: str, value: Any):
        """
        Notify Gemini when user manually updates a field.
        
        Keeps Gemini's context synchronized with manual user edits so it doesn't
        ask about fields the user has already filled.
        
        Args:
            field_id: Technical field identifier
            field_name: Human-readable field label
            value: The value the user entered
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return
        
        # Skip notification if value is empty/falsy (e.g., user clicked in/out without typing)
        # This prevents unnecessary model responses for fields that weren't actually filled
        if not value or (isinstance(value, str) and not value.strip()):
            _log.debug("send_manual_field_update_skipped", field_id=field_id, field_name=field_name, 
                      reason="empty_value", session_id=self._session_id)
            return
        
        # Format as natural language notification
        value_str = str(value)
        message = f"User manually updated field '{field_name}' with value: {value_str}"
        
        # REDACT: Do not log field values (PHI)
        _log.info("send_manual_field_update", field_id=field_id, field_name=field_name, session_id=self._session_id)
        await self._live_ai.send_text_message(message)

    async def send_activity_start(self):
        """
        Send activity_start signal to Gemini (user started speaking).

        Signals the beginning of user speech before sending audio chunks.
        Called when frontend VAD detects speech start.
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return

        _log.info("🎤 [Service] Sending activity_start to Gemini", session_id=self._session_id)
        await self._live_ai.send_activity_start()

    async def send_activity_end(self):
        """
        Send activity_end signal to Gemini (user stopped speaking).

        Signals the end of user speech and flushes Gemini's cached audio buffer.
        Called when frontend VAD detects speech end.
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return

        _log.info("🤐 [Service] Sending activity_end to Gemini", session_id=self._session_id)
        await self._live_ai.send_activity_end()

    async def send_initiating_message(self, spoken_language: str, next_field_hint: str):
        """
        Send initiating message to Gemini to prompt conversation in specific language.

        This is triggered when user changes spoken language or when switching sections.
        Uses session.send_client_content() to initiate Gemini's response.

        Args:
            spoken_language: Language for Gemini to speak (e.g., "Spanish", "French")
            next_field_hint: Next unfilled field hint (e.g., "firstName (First Name)")
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return

        # Store spoken language for section switching (persists across sections)
        self._spoken_language = spoken_language

        # Format initiating message template
        message = self._settings.INITIATING_MESSAGE.format(
            spoken_language=spoken_language,
            next_field_hint=next_field_hint
        )

        _log.info("send_initiating_message",
                 session_id=self._session_id,
                 spoken_language=spoken_language,
                 message=message)

        # Send to Gemini via session.send_client_content()
        await self._live_ai.send_client_content(message)

    async def send_recovery_prompt(self, level: int, next_field_hint: str | None = None):
        """
        Send recovery prompt to Gemini when conversation stalls (activity watchdog).

        Translates frontend level (1, 2, 3) into configured prompt from backend/config.py.
        These prompts are SCRIPTS for Gemini to read aloud, not commands.

        Args:
            level: Escalation level (1=field re-prompt, 2=are you there, 3=goodbye)
            next_field_hint: Optional hint for level 1 (e.g., "firstName (First Name)")
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return

        # Only log Level 3 (farewell) - other levels are too noisy
        if level == 3:
            _log.info("🚪 recovery_prompt_level_3_farewell", session_id=self._session_id)

        # Get configured prompt based on level
        if level == 1:
            # Level 1: Re-prompt for same field
            prompt = self._settings.RECOVERY_PROMPT_LEVEL_1
        elif level == 2:
            prompt = self._settings.RECOVERY_PROMPT_LEVEL_2
        elif level == 3:
            prompt = self._settings.RECOVERY_PROMPT_LEVEL_3
        else:
            _log.warning("send_recovery_prompt_invalid_level", level=level)
            return

        # Send as context hint (same mechanism as completion_message)
        await self.send_context_hint(prompt)

    async def finalize_gemini_session(self):
        """
        Close Gemini session only (keep WebSocket alive).
        
        Called when Level 3 farewell completes. This allows frontend to stay connected
        to backend while cleaning up the expensive Gemini connection.
        """
        if self._live_ai is None:
            _log.warning("finalize_gemini_session_no_live_ai", session_id=self._session_id)
            return
        
        _log.info("finalize_gemini_session_start", session_id=self._session_id)
        try:
            await self._live_ai.finalize()
            _log.info("🚪 gemini_session_closed", session_id=self._session_id)
        except Exception as exc:
            _log.error("failed_to_finalize_gemini_session", 
                      session_id=self._session_id,
                      error=str(exc))

    async def restart_gemini_session(self, next_field_hint: Optional[str] = None):
        """
        Restart Gemini session after it was closed (e.g., after Level 3 farewell).
        
        Reuses existing schema, values, and session configuration.
        Similar to start_session but doesn't accept WebSocket (already connected).
        
        Args:
            next_field_hint: Hint for next field to ask (e.g., "firstName (First Name)")
        """
        if self._live_ai is None:
            _log.error("restart_gemini_session_no_live_ai", session_id=self._session_id)
            raise RuntimeError("No live AI adapter available")
        
        # Check if session is already active
        is_active = self._live_ai.is_session_active()
        _log.info("🔍 restart_gemini_session_check", 
                 session_id=self._session_id,
                 session_active=is_active)
        
        if is_active:
            _log.warning("restart_gemini_session_already_active", session_id=self._session_id)
            return  # Already connected, no-op
        
        if self._websocket is None:
            _log.error("restart_gemini_session_no_websocket", session_id=self._session_id)
            raise RuntimeError("No WebSocket connection available")
        
        if self._schema is None:
            _log.error("restart_gemini_session_no_schema", session_id=self._session_id)
            raise RuntimeError("No schema available - cannot restart")
        
        _log.info("🔄 restart_gemini_session_start", 
                 session_id=self._session_id,
                 has_next_field_hint=bool(next_field_hint))
        
        # Build system instruction from existing schema
        # Note: Backend doesn't store current_values (client is source of truth)
        # For restart, we use empty dict since frontend will sync values if needed
        system_instruction = self.build_form_context_message(
            self._schema,
            {}  # Empty values - frontend maintains state
        )
        
        # Restart Gemini session (doesn't re-accept WebSocket)
        await self._live_ai.set_callbacks(
            on_form_update=self.handle_form_update,
            on_transcript=self.handle_transcript if self._send_transcript else None,
            on_audio=self.handle_audio,
            on_tool_call=self.handle_tool_call,
            system_instruction=system_instruction,
            tool_declarations=self._settings.GEMINI_TOOLS,
            enable_transcripts=self._send_transcript,
        )
        
        # Verify session is now active
        is_active_after = self._live_ai.is_session_active()
        _log.info("✅ gemini_session_restarted", 
                 session_id=self._session_id,
                 session_active_after=is_active_after)

    async def change_fill_language(self, new_language: str):
        """
        Change the language used for filling form field values.
        
        This sends a system instruction update to Gemini to change the language
        requirement for field values, then prompts it to acknowledge the change.
        
        Args:
            new_language: The new language to use (e.g., "Spanish", "French", "Japanese")
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return
        
        # Update internal state
        old_language = self._fill_language
        self._fill_language = new_language
        
        # Send system instruction update to change the language requirement
        system_update = (
            f"LANGUAGE UPDATE:\n"
            f"The form field fill language has been changed from {old_language} to {new_language}.\n"
            f"From now on, you MUST fill ALL form field values in {new_language}.\n"
            f"You can still converse with the user in any language they speak, but all field values "
            f"must be in {new_language} when you call update_form_fields."
        )
        
        _log.info("change_fill_language_sending_system_update", 
                 old_language=old_language,
                 new_language=new_language,
                 session_id=self._session_id)
        
        # NOTE: System instruction updates are no longer sent during active sessions.
        # To change languages, we would need to reset the connection and create a new session.
        # For now, this method is deprecated. The language should be set at session creation time.
        # TODO: Implement proper language switching by resetting the Gemini connection with new system instructions.
        
        # Send a prompt for Gemini to acknowledge the change to the user
        acknowledgment_prompt = f"Acknowledge the language change to {new_language} naturally to the user."
        
        _log.info("change_fill_language_sending_acknowledgment_prompt", 
                 new_language=new_language,
                 session_id=self._session_id)
        
        await self._live_ai.send_text_message(acknowledgment_prompt)

    def build_form_context_message(
        self, 
        schema: dict, 
        current_values: dict,
        section_number: Optional[int] = None,
        section_label: Optional[str] = None,
        total_sections: Optional[int] = None,
        previous_spoken_names: Optional[List[str]] = None,
        next_field_hint: Optional[str] = None
    ) -> str:
        """Build form context system instruction to send to Gemini.
        
        This provides complete form schema and current state to the AI.
        Called by websocket_routes.py after start_session.
        
        Phase 3: Accepts section metadata for section-based flow.
        """
        from backend.services.ai_context import build_form_context
        
        return build_form_context(
            schema, 
            current_values, 
            self._fill_language,
            section_number=section_number,
            total_sections=total_sections,
            section_label=section_label,
            previous_spoken_names=previous_spoken_names,
            next_field_hint=next_field_hint
        )

    def update_schema(self, schema: dict, current_values: dict, fill_language: str = "English"):
        """Update session schema and language settings."""
        self._schema = schema
        self._fill_language = fill_language
        # Note: current_values are client-managed, we don't store them

    async def end_session(self):
        if self._live_ai is not None:
            await self._live_ai.finalize()
        self._websocket = None
        self._session_id = None

    async def switch_to_section(
        self,
        section_schema: Dict[str, Any],
        section_values: Dict[str, Any],
        section_metadata: Dict[str, Any],
        initial_field_hint: Optional[str] = None,
    ) -> None:
        """Switch to a new section by restarting the Gemini session with new context.
        
        This properly flushes Gemini's context (forgets old section fields) without
        disconnecting the WebSocket connection to the frontend.
        
        Args:
            section_schema: Schema for the new section
            section_values: Current values for fields in the new section
            section_metadata: Section metadata (section_number, total_sections, etc.)
            initial_field_hint: Initial field hint for the new section
        """
        if self._live_ai is None:
            _log.warning("switch_to_section_no_ai", session_id=self._session_id)
            return
        
        section_number = section_metadata.get("section_number", 1)
        total_sections = section_metadata.get("total_sections", 1)
        
        _log.info("switching_section", 
                 session_id=self._session_id,
                 section_number=section_number,
                 total_sections=total_sections)
        
        # 1. Close current Gemini session (flushes context)
        try:
            await self._live_ai.finalize()
            _log.info("gemini_session_closed_for_section_switch", session_id=self._session_id)
        except Exception as exc:
            _log.error("failed_to_close_gemini_session", 
                      session_id=self._session_id,
                      error=str(exc))
        
        # 2. Restart session with new section schema/values/context
        # Build system instruction from section metadata
        system_instruction = self.build_form_context_message(
            section_schema,
            section_values,
            section_number=section_number,
            section_label=section_metadata.get("section_label", f"Section {section_number}"),
            total_sections=total_sections,
            previous_spoken_names=section_metadata.get("previous_spoken_names", [])
        )
        
        # Restart session using the same logic as initial connection
        websocket = self._websocket
        session_id = self._session_id
        send_transcript = self._send_transcript
        
        await self.start_session(
            websocket=websocket,
            session_id=session_id,
            send_transcript=send_transcript,
            accept_connection=False,  # Don't send connection_accepted again
            schema=section_schema,
            current_values=section_values,
            system_instruction=system_instruction,
        )
        
        # 3. Notify frontend that section switch is complete
        if websocket:
            try:
                await websocket.send_json({
                    "type": "section_switched",
                    "section_number": section_number,
                    "total_sections": total_sections,
                    "section_label": section_metadata.get("section_label", f"Section {section_number}"),
                })
                _log.info("section_switched_confirmation_sent", session_id=session_id)
            except Exception as exc:
                _log.error("failed_to_send_section_switched",
                          session_id=session_id,
                          error=str(exc))

        # 4. Send initiating message to Gemini with current spoken language
        # This prompts Gemini to greet the user in the selected language and ask for the first field
        if initial_field_hint:
            try:
                await self.send_initiating_message(self._spoken_language, initial_field_hint)
                _log.info("section_switch_initiating_message_sent",
                         session_id=session_id,
                         spoken_language=self._spoken_language)
            except Exception as exc:
                _log.error("failed_to_send_section_switch_initiating_message",
                          session_id=session_id,
                          error=str(exc))

    def handle_update_fields_tool_call(
        self, session_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Apply updates from the AI for web sessions (validation only, no persistence)."""

        # Build field list on-demand from schema for validation
        # Values are not persisted - this is just for acknowledgment
        try:
            fields = self._build_fields_from_schema()
            
            # Step 1: Match field IDs (exact or fuzzy)
            matched_updates = {}  # field_id -> value (with actual field IDs)
            unknown_fields = []
            field_map = {}  # field_id -> field object
            
            for field_key, value in (updates or {}).items():
                # Try exact match by field ID first
                matched_field = next((f for f in fields if f.id == field_key), None)
                
                # If no exact match, try fuzzy matching by name
                if not matched_field:
                    from backend.utils.fuzzy_field_matcher import fuzzy_match_hint
                    match_result = fuzzy_match_hint(field_key, fields)
                    if match_result.status == "resolved" and match_result.top_candidate:
                        matched_field = match_result.top_candidate.field
                        _log.debug("fuzzy_matched_field", 
                                  model_key=field_key, 
                                  matched_id=matched_field.id,
                                  matched_name=matched_field.name,
                                  score=match_result.top_candidate.score,
                                  session_id=session_id)
                
                if matched_field:
                    matched_updates[matched_field.id] = value
                    field_map[matched_field.id] = matched_field
                else:
                    unknown_fields.append(field_key)
            
            # Step 2: Validate matched fields against schema constraints
            from backend.utils.field_validator import validate_updates
            
            # Convert field objects to dicts for validator
            field_dicts = []
            for field_obj in fields:
                field_dict = {
                    "id": field_obj.id,
                    "name": field_obj.name,
                    "type": field_obj.type,
                }
                # Add constraint fields if present
                if hasattr(field_obj, 'min') and field_obj.min is not None:
                    field_dict["min"] = field_obj.min
                if hasattr(field_obj, 'max') and field_obj.max is not None:
                    field_dict["max"] = field_obj.max
                if hasattr(field_obj, 'format') and field_obj.format:
                    field_dict["format"] = field_obj.format
                if hasattr(field_obj, 'pattern') and field_obj.pattern:
                    field_dict["pattern"] = field_obj.pattern
                if hasattr(field_obj, 'minLength') and field_obj.minLength is not None:
                    field_dict["minLength"] = field_obj.minLength
                if hasattr(field_obj, 'maxLength') and field_obj.maxLength is not None:
                    field_dict["maxLength"] = field_obj.maxLength
                if hasattr(field_obj, 'options') and field_obj.options:
                    field_dict["options"] = field_obj.options
                
                field_dicts.append(field_dict)
            
            validation_result = validate_updates(field_dicts, matched_updates)
            
            applied_fields = validation_result["valid_fields"]
            validation_errors = validation_result["validation_errors"]
            form_state = validation_result["form_state"]
            
            result = {
                "applied_fields": applied_fields,
                "unknown_fields": unknown_fields,
                "validation_errors": validation_errors,
                "form_state": form_state,
            }
            
            # Log validation failures concisely
            if validation_errors or unknown_fields:
                _log.warning("validation_failures", 
                           error_count=len(validation_errors), 
                           unknown_count=len(unknown_fields))
            
            return result
            
        except Exception as exc:
            _log.exception("update_validation_error", session_id=session_id, error=str(exc))
            return None

    def update_form_state(self, field_updates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Acknowledge client-provided form state updates for web sessions.
        
        NOTE: Backend does NOT cache these values. This method just validates
        the message format and returns an acknowledgment. The client remains
        the single source of truth for all form state.
        
        Args:
            field_updates: List of field update objects from client
            
        Returns:
            Acknowledgment with field IDs that were accepted
        """
        applied: List[str] = []

        if not field_updates:
            return {"applied_fields": applied}

        # Validate field IDs against schema (don't cache values)
        schema_field_ids = {f.get("id") for f in (self._schema or {}).get("fields", [])}
        
        for item in field_updates:
            if not isinstance(item, dict):
                continue

            field_id = item.get("field_id") or item.get("id")
            if not field_id or field_id not in schema_field_ids:
                continue

            # Just acknowledge - don't cache
            applied.append(field_id)

        return {"applied_fields": applied}

    async def request_form_state_from_client(self, field_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Request current form state from the frontend client.
        
        This implements the async request/response pattern for stateless architecture.
        Backend sends a request to frontend and waits for response.
        
        Args:
            field_ids: Specific field IDs to request, or None/empty for all fields
            
        Returns:
            Dictionary of field_id -> value from the client
        """
        import asyncio
        
        if not self._websocket:
            _log.warning("request_form_state_no_websocket", session_id=self._session_id)
            return {}
        
        # Generate request ID for matching response
        import uuid
        request_id = str(uuid.uuid4())
        
        # Create future to await response
        future = asyncio.Future()
        self._pending_form_state_request = {
            "request_id": request_id,
            "future": future,
        }
        
        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "get_form_state",
                "request_id": request_id,
                "field_ids": field_ids or [],
            })
        except Exception as exc:
            _log.error("failed_to_send_form_state_request", session_id=self._session_id, error=str(exc))
            self._pending_form_state_request = None
            return {}
        
        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=5.0)
            return result
        except asyncio.TimeoutError:
            _log.error("form_state_request_timeout", session_id=self._session_id, request_id=request_id)
            self._pending_form_state_request = None
            return {}
        except Exception as exc:
            _log.error("form_state_request_error", session_id=self._session_id, error=str(exc))
            self._pending_form_state_request = None
            return {}

    def handle_form_state_response(self, request_id: str, field_values: Dict[str, Any]) -> None:
        """
        Handle form_state_response message from frontend.
        
        This completes the async request/response cycle by resolving the pending future.
        
        Args:
            request_id: ID matching the original request
            field_values: Dictionary of field_id -> value from client
        """
        if not self._pending_form_state_request:
            _log.warning("unexpected_form_state_response", session_id=self._session_id, request_id=request_id)
            return
        
        if self._pending_form_state_request.get("request_id") != request_id:
            _log.warning("mismatched_form_state_response", 
                        session_id=self._session_id,
                        expected=self._pending_form_state_request.get("request_id"),
                        received=request_id)
            return
        
        # Resolve the future with the field values
        future = self._pending_form_state_request.get("future")
        if future and not future.done():
            future.set_result(field_values)
        
        self._pending_form_state_request = None

    async def request_next_field_hint(self) -> Optional[str]:
        """
        Request next field hint from the frontend client.
        
        This implements the async request/response pattern for getting navigation hints.
        The frontend computes the next unfilled field and formats a hint for Gemini.
        
        Returns:
            Formatted hint string (e.g., "Next field to fill is #3: 'email' (type: text, required)")
            or None if request fails or no unfilled fields remain
        """
        import asyncio
        
        if not self._websocket:
            _log.warning("request_next_field_hint_no_websocket", session_id=self._session_id)
            return None
        
        # Generate request ID for matching response
        import uuid
        request_id = str(uuid.uuid4())
        
        # Create future to await response
        future = asyncio.Future()
        self._pending_next_field_request = {
            "request_id": request_id,
            "future": future,
        }
        
        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "get_next_field_hint",
                "request_id": request_id,
            })
        except Exception as exc:
            _log.error("failed_to_send_next_field_request", session_id=self._session_id, error=str(exc))
            self._pending_next_field_request = None
            return None
        
        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=2.0)
            return result
        except asyncio.TimeoutError:
            _log.error("next_field_request_timeout", session_id=self._session_id, request_id=request_id)
            self._pending_next_field_request = None
            return None
        except Exception as exc:
            _log.error("next_field_request_error", session_id=self._session_id, error=str(exc))
            self._pending_next_field_request = None
            return None

    def handle_next_field_hint_response(self, request_id: str, hint: Optional[str]) -> None:
        """
        Handle next_field_hint_response message from frontend.
        
        This completes the async request/response cycle by resolving the pending future.
        
        Args:
            request_id: ID matching the original request
            hint: Formatted hint string or None if form is complete
        """
        if not hasattr(self, '_pending_next_field_request') or not self._pending_next_field_request:
            _log.warning("unexpected_next_field_response", session_id=self._session_id, request_id=request_id)
            return
        
        if self._pending_next_field_request.get("request_id") != request_id:
            _log.warning("mismatched_next_field_response", 
                        session_id=self._session_id,
                        expected=self._pending_next_field_request.get("request_id"),
                        received=request_id)
            return
        
        # Resolve the future with the hint
        future = self._pending_next_field_request.get("future")
        if future and not future.done():
            future.set_result(hint)
        
        self._pending_next_field_request = None

    def get_form_status_for_ai(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Handles the 'get_form_status' tool call by providing the current form schema.
        
        For web sessions: Returns schema-based field list with empty values.
        Client maintains actual values - backend only has schema for context.

        Args:
            session_id: The ID of the current user session.

        Returns:
            A dictionary of {field_name: None} for the AI, or empty dict if no schema.
        """
        # Web sessions: Return empty status since client is source of truth
        # Backend doesn't cache field values for web forms
        schema = self._schema or {}
        status = {}
        for field_data in schema.get("fields", []):
            field_name = field_data.get("name") or field_data.get("id")
            status[field_name] = None  # Backend doesn't track values
        return status

    async def handle_switch_section(self, section_identifier: str) -> Dict[str, Any]:
        """
        Handle switch_section tool call from AI.
        
        Requests section info from frontend, then switches Gemini session to new section.
        This keeps WebSocket alive but properly flushes Gemini's context.
        
        Args:
            section_identifier: Section number ('3'), ID, or label from AI
            
        Returns:
            Success response for AI
        """
        if not self._websocket:
            _log.warning("switch_section_no_websocket", session_id=self._session_id)
            return {"success": False, "message": "No connection to frontend."}
        
        import asyncio
        import uuid
        
        # Generate request ID for async request/response
        request_id = str(uuid.uuid4())
        
        # Create future to await section info
        future = asyncio.Future()
        self._pending_section_switch = {
            "request_id": request_id,
            "future": future,
        }
        
        try:
            # Request section info from frontend (non-blocking send)
            asyncio.create_task(self._websocket.send_json({
                "type": "prepare_section_switch",
                "identifier": section_identifier,
                "request_id": request_id,
            }))
            _log.info("section_switch_info_requested", 
                     session_id=self._session_id,
                     identifier=section_identifier)
            
            # Wait for frontend to send section info (5s timeout for large forms)
            section_info = await asyncio.wait_for(future, timeout=5.0)
            
            # Switch Gemini session to new section
            await self.switch_to_section(
                section_schema=section_info["schema"],
                section_values=section_info["current_values"],
                section_metadata=section_info["metadata"],
                initial_field_hint=section_info.get("initial_field_hint"),
            )
            
            return {
                "success": True,
                "message": f"Switched to section {section_info['metadata']['section_number']}: {section_info['metadata']['section_label']}",
            }
            
        except asyncio.TimeoutError:
            _log.error("section_switch_timeout", session_id=self._session_id)
            self._pending_section_switch = None
            return {"success": False, "message": "Section switch timed out."}
        except Exception as exc:
            _log.error("section_switch_failed", 
                      session_id=self._session_id,
                      identifier=section_identifier,
                      error=str(exc))
            self._pending_section_switch = None
            return {"success": False, "message": f"Failed to switch section: {str(exc)}"}

    async def handle_get_field_value(self, spoken_name: str) -> Dict[str, Any]:
        """
        Handle get_field_value tool call from AI.
        
        Requests field value from frontend using spoken name.
        Frontend will lookup in spokenNameToFieldId map and return value.
        
        Args:
            spoken_name: The spoken name of the field (e.g., 'phone number')
            
        Returns:
            Dictionary with field value or not found message
        """
        import asyncio
        import uuid
        
        if not self._websocket:
            _log.warning("get_field_value_no_websocket", session_id=self._session_id)
            return {"found": False, "message": "No connection to frontend."}
        
        # Generate request ID for matching response
        request_id = str(uuid.uuid4())
        
        # Create future to await response
        future = asyncio.Future()
        self._pending_field_value_request = {
            "request_id": request_id,
            "future": future,
        }
        
        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "get_field_value",
                "request_id": request_id,
                "spoken_name": spoken_name,
            })
        except Exception as exc:
            _log.error("failed_to_send_get_field_value", 
                      session_id=self._session_id,
                      spoken_name=spoken_name,
                      error=str(exc))
            self._pending_field_value_request = None
            return {"found": False, "message": "Failed to request field value."}
        
        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=2.0)
            if result.get("found"):
                return {
                    "found": True,
                    "value": result.get("value"),
                    "message": f"The value for '{spoken_name}' is: {result.get('value')}",
                }
            else:
                return {
                    "found": False,
                    "message": f"Could not find field '{spoken_name}'. It may not have been filled yet.",
                }
        except asyncio.TimeoutError:
            _log.error("get_field_value_timeout", 
                      session_id=self._session_id,
                      spoken_name=spoken_name,
                      request_id=request_id)
            self._pending_field_value_request = None
            return {"found": False, "message": "Request timed out."}
        except Exception as exc:
            _log.error("get_field_value_error", 
                      session_id=self._session_id,
                      spoken_name=spoken_name,
                      error=str(exc))
            self._pending_field_value_request = None
            return {"found": False, "message": "Error retrieving field value."}

    def handle_field_value_response(self, request_id: str, value: Any, found: bool) -> None:
        """
        Handle field_value_response message from frontend.
        
        Completes the async request/response cycle for get_field_value.
        
        Args:
            request_id: ID matching the original request
            value: The field value from client
            found: Whether the field was found
        """
        if not hasattr(self, '_pending_field_value_request') or not self._pending_field_value_request:
            _log.warning("unexpected_field_value_response", 
                        session_id=self._session_id,
                        request_id=request_id)
            return
        
        if self._pending_field_value_request.get("request_id") != request_id:
            _log.warning("mismatched_field_value_response", 
                        session_id=self._session_id,
                        expected=self._pending_field_value_request.get("request_id"),
                        received=request_id)
            return
        
        # Resolve the future with the response
        future = self._pending_field_value_request.get("future")
        if future and not future.done():
            future.set_result({"value": value, "found": found})
        
        self._pending_field_value_request = None

    def handle_section_info_response(self, request_id: str, section_info: Dict[str, Any]) -> None:
        """
        Handle section_info_response message from frontend.
        
        Completes the async request/response cycle for section switching.
        
        Args:
            request_id: ID matching the original request
            section_info: Dictionary with schema, current_values, metadata, initial_field_hint
        """
        if not hasattr(self, '_pending_section_switch') or not self._pending_section_switch:
            _log.warning("unexpected_section_info_response", 
                        session_id=self._session_id,
                        request_id=request_id)
            return
        
        if self._pending_section_switch.get("request_id") != request_id:
            _log.warning("mismatched_section_info_response", 
                        session_id=self._session_id,
                        expected=self._pending_section_switch.get("request_id"),
                        received=request_id)
            return
        
        # Resolve the future with the section info
        future = self._pending_section_switch.get("future")
        if future and not future.done():
            future.set_result(section_info)
        
        self._pending_section_switch = None

    async def handle_complete_section(self) -> Dict[str, Any]:
        """
        Handle complete_section tool call from AI.
        
        Sends message to frontend to mark current section complete and advance.
        Frontend will update state and switch to next section.
        
        Returns:
            Success response for AI
        """
        if not self._websocket:
            _log.warning("complete_section_no_websocket", session_id=self._session_id)
            return {"success": False, "message": "No connection to frontend."}
        
        try:
            await self._websocket.send_json({
                "type": "complete_section",
            })
            _log.info("complete_section_request_sent", session_id=self._session_id)
            return {
                "success": True,
                "message": "Section marked complete. Moving to next section.",
            }
        except Exception as exc:
            _log.error("failed_to_send_complete_section", 
                      session_id=self._session_id,
                      error=str(exc))
            return {"success": False, "message": "Failed to complete section."}


# Note: factory for FormFillingService lives in backend.dependencies to avoid
# circular imports. The service implementation should remain importable without
# pulling in FastAPI dependency providers.
