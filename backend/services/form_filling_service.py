from fastapi import WebSocket
from typing import Any, Dict, Optional, List
import json
from copy import deepcopy
import structlog
import os
from datetime import datetime

from backend.config import Settings, get_settings
from backend.ports.live_ai_port import ILiveAI
from .field_utils import (
    build_fields_from_schema,
    get_available_spoken_names,
    find_similar_field_names,
)
from .validation_handler import ValidationHandler
from .audio_handler import AudioHandler
from .request_coordinator import RequestCoordinator
from .callback_handler import CallbackHandler
from backend.utils.tool_call_logger import append_tool_call_log

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
        # Store callbacks for reuse during section switching
        self._on_form_update = None
        self._on_transcript = None
        self._on_audio = None
        self._on_tool_call = None
        self._send_transcript = False
        # Audio handler for streaming and activity signals
        self._audio_handler: Optional[AudioHandler] = None
        # Request coordinator for async request/response pattern
        self._request_coordinator: Optional[RequestCoordinator] = None
        # Callback handler for Gemini Live AI events
        self._callback_handler: Optional[CallbackHandler] = None

    def _build_fields_from_schema(self) -> list:
        """Build field list from schema on-demand (no caching).
        
        Used by web sessions to construct field objects for tool responses.
        Backend doesn't persist these - they're rebuilt each time.
        
        Delegates to field_utils.build_fields_from_schema for the actual logic.
        """
        return build_fields_from_schema(self._schema or {})

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
        
        # Initialize audio handler
        self._audio_handler = AudioHandler(self._live_ai, session_id=session_id)
        
        # Initialize request coordinator
        self._request_coordinator = RequestCoordinator(websocket=websocket, session_id=session_id)
        
        # Store schema for context generation
        self._schema = schema
        # Note: current_values are ignored by backend - client is source of truth
        
        if accept_connection:
            await self._websocket.accept()
        
        # Initialize callback handler
        self._callback_handler = CallbackHandler(
            websocket=websocket,
            session_id=session_id,
            request_coordinator=self._request_coordinator,
            send_transcript=send_transcript,
        )
        
        # Inject tool handler methods into callback handler
        self._callback_handler.set_tool_handlers(
            handle_update_fields=self.handle_update_fields_tool_call,
            handle_switch_section=self.handle_switch_section,
            handle_get_field_value=self.handle_get_field_value,
            handle_complete_section=self.handle_complete_section,
            request_form_state_from_client=self.request_form_state_from_client,
        )
        
        # Use web form tool declarations (stateless)
        tool_declarations = deepcopy(self._settings.TOOL_DECLARATIONS)

        if self._live_ai is not None:
            # Register callbacks with Gemini Live AI
            # System instruction is passed from caller and included in the initial
            # Gemini connection config.
            try:
                self._live_ai.set_callbacks(
                    on_form_update=self._callback_handler.on_form_update,
                    on_transcript=self._callback_handler.on_transcript,
                    on_audio=self._callback_handler.on_audio,
                    on_tool_call=self._callback_handler.on_tool_call,
                    system_instruction=system_instruction,
                    tool_declarations=tool_declarations,
                    enable_transcripts=bool(send_transcript),
                )
            except TypeError:
                # Adapter does not accept on_audio (older implementations); fall
                # back to previous behavior.
                try:
                    self._live_ai.set_callbacks(
                        on_form_update=self._callback_handler.on_form_update,
                        on_transcript=self._callback_handler.on_transcript,
                        on_tool_call=self._callback_handler.on_tool_call,
                        system_instruction=system_instruction,
                        tool_declarations=tool_declarations,
                    )
                except TypeError:
                    # If this also fails, give up silently — the adapter
                    # truly doesn't implement callback registration.
                    pass

    async def stream_audio(self, audio_chunk: bytes):
        """Stream audio chunk to Gemini. Delegates to AudioHandler."""
        if self._audio_handler:
            await self._audio_handler.stream_audio(audio_chunk)

    async def send_context_hint(self, hint_text: str):
        """Send context hint to Gemini. Delegates to AudioHandler."""
        if self._audio_handler:
            await self._audio_handler.send_context_hint(hint_text)

    async def send_manual_field_update(self, field_id: str, field_name: str, value: Any, next_field_hint: Optional[str] = None):
        """Notify Gemini of manual field update. Delegates to AudioHandler."""
        if self._audio_handler:
            await self._audio_handler.send_manual_field_update(
                field_id, field_name, value, next_field_hint
            )

    async def send_activity_start(self):
        """Send activity_start signal. Delegates to AudioHandler."""
        if self._audio_handler:
            await self._audio_handler.send_activity_start()

    async def send_activity_end(self):
        """Send activity_end signal. Delegates to AudioHandler."""
        if self._audio_handler:
            await self._audio_handler.send_activity_end()

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
        # CRITICAL: Always send initiating message to ensure Gemini speaks first in new section
        try:
            # Use provided hint, or fallback to generic prompt if section is complete
            hint = initial_field_hint or "the first unfilled field in this section"
            await self.send_initiating_message(self._spoken_language, hint)
            _log.info("section_switch_initiating_message_sent",
                     session_id=session_id,
                     spoken_language=self._spoken_language,
                     has_hint=bool(initial_field_hint))
        except Exception as exc:
            _log.error("failed_to_send_section_switch_initiating_message",
                      session_id=session_id,
                      error=str(exc))

    def handle_update_fields_tool_call(
        self, session_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Apply updates from the AI for web sessions (validation only, no persistence).
        
        Delegates to ValidationHandler for field matching and validation.
        """
        # Build field list on-demand from schema for validation
        # Values are not persisted - this is just for acknowledgment
        fields = self._build_fields_from_schema()
        
        # Use ValidationHandler to match and validate fields
        validator = ValidationHandler(session_id=session_id)
        return validator.validate_field_updates(fields, updates)

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
        
        Delegates to RequestCoordinator.
        
        Args:
            field_ids: Specific field IDs to request, or None/empty for all fields
            
        Returns:
            Dictionary of field_id -> value from the client
        """
        if not self._request_coordinator:
            _log.warning("request_form_state_no_coordinator", session_id=self._session_id)
            return {}
        
        return await self._request_coordinator.request_form_state(field_ids)

    def handle_form_state_response(self, request_id: str, field_values: Dict[str, Any]) -> None:
        """
        Handle form_state_response message from frontend.
        
        Delegates to RequestCoordinator.
        
        Args:
            request_id: ID matching the original request
            field_values: Dictionary of field_id -> value from client
        """
        if not self._request_coordinator:
            _log.warning("handle_form_state_response_no_coordinator", session_id=self._session_id)
            return
        
        self._request_coordinator.handle_form_state_response(request_id, field_values)

    async def request_next_field_hint(self) -> Optional[str]:
        """
        Request next field hint from the frontend client.
        
        Delegates to RequestCoordinator.
        
        Returns:
            Formatted hint string or None if request fails or no unfilled fields remain
        """
        if not self._request_coordinator:
            _log.warning("request_next_field_hint_no_coordinator", session_id=self._session_id)
            return None
        
        return await self._request_coordinator.request_next_field_hint()

    def handle_next_field_hint_response(self, request_id: str, hint: Optional[str]) -> None:
        """
        Handle next_field_hint_response message from frontend.
        
        Delegates to RequestCoordinator.
        
        Args:
            request_id: ID matching the original request
            hint: Formatted hint string or None if form is complete
        """
        if not self._request_coordinator:
            _log.warning("handle_next_field_hint_response_no_coordinator", session_id=self._session_id)
            return
        
        self._request_coordinator.handle_next_field_hint_response(request_id, hint)

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
        if not self._request_coordinator:
            _log.warning("switch_section_no_coordinator", session_id=self._session_id)
            return {"success": False, "message": "No connection to frontend."}
        
        # Request section info from frontend via coordinator
        _log.info("section_switch_info_requested", 
                 session_id=self._session_id,
                 identifier=section_identifier)
        
        section_info = await self._request_coordinator.request_section_info(section_identifier)
        
        if not section_info:
            return {"success": False, "message": "Section switch request failed or timed out."}
        
        try:
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
            
        except Exception as exc:
            _log.error("section_switch_failed", 
                      session_id=self._session_id,
                      identifier=section_identifier,
                      error=str(exc))
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
        if not self._request_coordinator:
            _log.warning("get_field_value_no_coordinator", session_id=self._session_id)
            return {"found": False, "message": "No connection to frontend."}
        
        # Request field value from frontend via coordinator
        result = await self._request_coordinator.request_field_value(spoken_name)
        
        # Build user-friendly response based on result
        if result.get("found"):
            value = result.get("value")
            
            # Field exists - distinguish between filled and empty
            if value is not None and str(value).strip() != '':
                # Field has a value
                return {
                    "found": True,
                    "value": str(value),
                    "message": f"The field '{spoken_name}' is filled with: {value}",
                }
            else:
                # Field exists but is empty/unfilled
                return {
                    "found": True,
                    "value": None,
                    "message": f"The field '{spoken_name}' exists but has not been filled yet. Ask the user if they would like to fill it now.",
                }
        else:
            # Field not found in schema - provide helpful suggestions
            # Build list of available spoken names from schema and previous sections
            available_names = self._get_available_spoken_names()
            
            # Try fuzzy matching to suggest alternatives
            suggestions = self._find_similar_field_names(spoken_name, available_names)
            
            if suggestions:
                # Provide "did you mean?" suggestions
                if len(suggestions) == 1:
                    suggestion_text = f"Did you mean '{suggestions[0]}'? Try asking about that field instead."
                else:
                    suggestion_list = ', '.join(f"'{s}'" for s in suggestions[:3])
                    suggestion_text = f"Did you mean one of these: {suggestion_list}? Try asking about one of those fields instead."
                
                return {
                    "found": False,
                    "message": f"Could not find a field called '{spoken_name}'. {suggestion_text}",
                    "suggestions": suggestions[:3],  # Include for potential tool extensions
                }
            else:
                # No close matches - list available fields
                if len(available_names) <= 5:
                    available_list = ', '.join(f"'{n}'" for n in available_names)
                    available_text = f"Available fields are: {available_list}."
                else:
                    available_list = ', '.join(f"'{n}'" for n in available_names[:5])
                    available_text = f"Available fields include: {available_list} (and {len(available_names) - 5} more)."
                
                return {
                    "found": False,
                    "message": f"Could not find a field called '{spoken_name}'. {available_text} Please ask about one of these fields by name.",
                }

    def handle_field_value_response(self, request_id: str, value: Any, found: bool) -> None:
        """
        Handle field_value_response message from frontend.
        
        Delegates to RequestCoordinator.
        
        Args:
            request_id: ID matching the original request
            value: The field value from client
            found: Whether the field was found
        """
        if not self._request_coordinator:
            _log.warning("handle_field_value_response_no_coordinator", session_id=self._session_id)
            return
        
        self._request_coordinator.handle_field_value_response(request_id, value, found)

    def handle_section_info_response(self, request_id: str, section_info: Dict[str, Any]) -> None:
        """
        Handle section_info_response message from frontend.
        
        Delegates to RequestCoordinator.
        
        Args:
            request_id: ID matching the original request
            section_info: Dictionary with schema, current_values, metadata, initial_field_hint
        """
        if not self._request_coordinator:
            _log.warning("handle_section_info_response_no_coordinator", session_id=self._session_id)
            return
        
        self._request_coordinator.handle_section_info_response(request_id, section_info)

    def _get_available_spoken_names(self) -> List[str]:
        """
        Get list of all available spoken field names from current schema.
        
        Returns:
            List of spoken names that can be queried via get_field_value
            
        Delegates to field_utils.get_available_spoken_names for the actual logic.
        """
        return get_available_spoken_names(self._schema)
    
    def _find_similar_field_names(self, query: str, available_names: List[str], max_suggestions: int = 3) -> List[str]:
        """
        Find similar field names using fuzzy matching.
        
        Uses rapidfuzz for high-quality fuzzy matching (same library used for PDF field normalization).
        
        Args:
            query: User's query string (e.g., "phone")
            available_names: List of valid field names
            max_suggestions: Maximum number of suggestions to return
            
        Returns:
            List of suggested field names, sorted by similarity
            
        Delegates to field_utils.find_similar_field_names for the actual logic.
        """
        return find_similar_field_names(query, available_names, max_suggestions)

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
