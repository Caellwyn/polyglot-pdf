from fastapi import WebSocket
from typing import Any, Dict, Optional, List
import asyncio
import json
import re
import time
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
    strip_field_id_from_hint,
)
from .ai_context import render_field_guidance, render_section_metadata
from .validation_handler import ValidationHandler
from .audio_handler import AudioHandler
from .request_coordinator import RequestCoordinator
from .callback_handler import CallbackHandler
from .manifest_service import get_next_field_schema, should_include_schema_in_response

# Logger for service-level diagnostics
_log = structlog.get_logger().bind(service="FormFillingService")


class FormFillingService:
    """Orchestrates the logic for filling form fields based on AI tool calls (web forms only)."""

    def __init__(
        self,
        live_ai: Optional[ILiveAI] = None,
        settings: Optional[Settings] = None,
        text_ai: Optional[Any] = None,
    ):
        # AI adapter is optional for unit tests that only exercise form logic
        self._live_ai = live_ai
        self._settings = settings or get_settings()
        # Cheap text model behind the secretary (bd polyglot-pdf-jnjj.45c). Optional
        # so unit tests that exercise only form logic need not wire it; the
        # ask_secretary handler fail-opens when it is None.
        self._text_ai = text_ai
        self._websocket = None
        self._session_id = None
        # Web session state - schema only (no field caching)
        self._schema: Optional[Dict[str, Any]] = None  # Schema for context only
        # Last section metadata seen via switch_to_section. Navigation state (NOT
        # field values/PII), retained for the connection lifetime so a mid-session
        # restart (restart_gemini_session, e.g. after a Level-3 farewell) can rebuild
        # the system instruction WITH the user's section position + previously-spoken
        # field names -- otherwise the restart defaults to "section 1 of 1" and loses
        # access to earlier-section lookups (bd polyglot-pdf-umv). None until the first
        # section switch (single-section forms never switch, so None is correct there).
        self._last_section_metadata: Optional[Dict[str, Any]] = None
        self._fill_language: str = "English"  # Default fill language
        self._spoken_language: str = "English"  # Default spoken conversation language (persists across sections)
        # JIT schema loading: Track which field schemas have been sent to Gemini
        self._loaded_field_ids: set = set()  # Prevents duplicate schemas in context
        # DTI (bd polyglot-pdf-jnjj.22): client-supplied field schemas merged for
        # VALIDATION only -- kept SEPARATE from self._schema['fields'] so the DTI SI
        # branch's "fields[0] is the current field" assumption is never disturbed by
        # accumulated fields (Codex PR #229). Schema only, no values.
        self._dti_extra_fields: Dict[str, Dict[str, Any]] = {}
        # DTI current-field routing pointer (bd polyglot-pdf-h1bn): the id of the
        # field the model is currently on -- set from the field-1 hint at session/
        # section start and from each delivered next-field schema on confirm. Used to
        # COERCE update_form_fields onto the current field when the model sends a
        # hallucinated / drifted id (the value is right, only the target id is wrong;
        # cross-field intent goes to the secretary, never update_form_fields). A
        # single transient id, overwritten each turn, no user values -- per-turn
        # routing metadata, not persisted field state (stateless invariant holds).
        self._current_field_id: Optional[str] = None
        # Store callbacks for reuse during section switching
        self._on_form_update = None
        self._on_transcript = None
        self._on_audio = None
        self._on_tool_call = None
        # Optional liveness callback (bd polyglot-pdf-l3a.4): the WS route sets this
        # before start_session so a native-VAD user turn (input transcription) bumps
        # the idle watchdog. Per-connection liveness wiring, not form state -- the
        # stateless invariant holds (nothing about the user's data is persisted).
        # Stored so the section-switch re-registration (set_callbacks) keeps it.
        self._on_user_activity = None
        self._send_transcript = False
        # Audio handler for streaming and activity signals
        self._audio_handler: Optional[AudioHandler] = None
        # Request coordinator for async request/response pattern
        self._request_coordinator: Optional[RequestCoordinator] = None
        # Callback handler for Gemini Live AI events
        self._callback_handler: Optional[CallbackHandler] = None
        # Persistent form session ID (survives section switches; stored so
        # _switch_to_section_locked can thread it into the rebuilt CallbackHandler
        # without needing to re-derive it from the handshake -- bd rwjy).
        self._form_session_id: Optional[str] = None
        # Resume flag: True when the handshake carried resume:true (mid-section
        # reconnect). Suppresses the greeting in send_initiating_message so Gemini
        # resumes silently rather than re-introducing the form/section.
        self._is_resume_session: bool = False
        # Section-switch serialization (bd polyglot-pdf-0c1). _switch_lock
        # serializes switch_to_section so a manual switch (WS route) and an
        # AI-initiated switch (switch_section tool) can't restart the session
        # concurrently. _switch_task holds a strong ref to the detached swap task
        # spawned by handle_switch_section, so it isn't garbage-collected mid-swap.
        self._switch_lock = asyncio.Lock()
        self._switch_task: Optional[asyncio.Task] = None
        # Rate-limit stamp for the switch-window audio-drop log (stream_audio).
        self._last_switch_drop_log: float = 0.0

    def _build_fields_from_schema(self) -> list:
        """Build field list from schema on-demand (no caching).

        Used by web sessions to construct field objects for tool responses.
        Backend doesn't persist these - they're rebuilt each time.

        Delegates to field_utils.build_fields_from_schema for the actual logic.

        In DTI/JIT mode self._schema['fields'] holds only the first field, so the
        client-supplied fields recorded via merge_field_schema (DTI, bd
        polyglot-pdf-jnjj.22) are folded in here for validation -- WITHOUT mutating
        self._schema (which the SI builder reads for the current field).
        """
        schema = self._schema or {}
        if not self._dti_extra_fields:
            return build_fields_from_schema(schema)
        present = {f.get("id") for f in schema.get("fields", [])}
        merged = {
            **schema,
            "fields": list(schema.get("fields", [])) + [
                f for fid, f in self._dti_extra_fields.items() if fid not in present
            ],
        }
        return build_fields_from_schema(merged)

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
        form_session_id: Optional[str] = None,
        current_section_id: Optional[str] = None,
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
            form_session_id: Persistent form session ID from frontend (survives reconnects)
            current_section_id: Current section ID, threaded into token-logging context
                so token events carry the active section (bd polyglot-pdf-tb7)
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

        # Seed the JIT schema de-dup set from the handshake's loaded_field_ids --
        # the field schemas the client has ALREADY delivered to Gemini (this list
        # survives reconnects on the client). Without this, a mid-session reconnect
        # reset the set to empty and re-sent schemas Gemini already had
        # (bd polyglot-pdf-jnjj.9 gap L). Idempotent: a fresh connect sends [].
        if schema:
            self._loaded_field_ids = set(schema.get("loaded_field_ids", []))

        # Reset the DTI validation extras on every (re)start, INCLUDING a section
        # switch (which calls start_session with the new section's schema). Otherwise
        # client-supplied field schemas from a PREVIOUS section would linger and let
        # the validator wrongly accept a stale cross-section field id (fresh-eyes
        # substitute review, Codex PR #229). Parallels the _loaded_field_ids reseed.
        self._dti_extra_fields = {}
        # Clear the current-field coercion pointer too (bd polyglot-pdf-h1bn): the new
        # section's field 1 sets it when send_initiating_message fires after this
        # restart, but clear it now so it can never point at the PREVIOUS section's
        # field in the (practically-unreachable, pre-greeting) window before that
        # (fresh-eyes Finding 3 -- defensive, matches the _dti_extra_fields reset).
        self._current_field_id = None

        if accept_connection:
            await self._websocket.accept()
        
        # Extract form_id here so it can be passed to CallbackHandler (confirmation
        # audit logging guard requires both ids at construction time, bd rwjy).
        form_id = schema.get("form_metadata", {}).get("form_number", "unknown") if schema else "unknown"
        # Store the resolved form_session_id so _switch_to_section_locked can thread
        # it into the rebuilt CallbackHandler without re-deriving it (fresh-eyes gap).
        self._form_session_id = form_session_id or session_id

        # Initialize callback handler
        self._callback_handler = CallbackHandler(
            websocket=websocket,
            session_id=session_id,
            request_coordinator=self._request_coordinator,
            send_transcript=send_transcript,
            form_id=form_id,
            form_session_id=self._form_session_id,
        )

        # Inject tool handler methods into callback handler
        self._callback_handler.set_tool_handlers(
            handle_update_fields=self.handle_update_fields_tool_call,
            handle_switch_section=self.handle_switch_section,
            handle_get_field_value=self.handle_get_field_value,
            request_form_state_from_client=self.request_form_state_from_client,
            get_next_field_schema_for_jit=self.get_next_field_schema_for_jit,
            merge_field_schema=self.merge_field_schema,
            handle_ask_secretary=self.handle_ask_secretary,
            # Live getter so fields 2..N's guidance carries the CURRENT fill language
            # even after a mid-session change_fill_language (bd polyglot-pdf-uogm).
            get_fill_language=lambda: self._fill_language,
            # Live getter so confirm_field can coerce onto the current field when the
            # model confirms a hallucinated/drifted id (bd polyglot-pdf-h1bn).
            get_current_field_id=lambda: self._current_field_id,
            # Gate confirm coercion on the SERVICE's injected USE_DTI (not the global
            # singleton) so it is symmetric with the update-side coercion even when the
            # service is built with a non-global Settings (Codex PR #264).
            get_use_dti=lambda: getattr(self._settings, "USE_DTI", False),
            # Invalidate the current-field pointer on a successful confirm so a later
            # update can't be coerced onto the just-confirmed field if next-field
            # delivery times out (Codex PR #264).
            clear_current_field=self._clear_current_field_id,
        )

        # Use web form tool declarations (stateless)
        tool_declarations = deepcopy(self._settings.TOOL_DECLARATIONS)

        if self._live_ai is not None:
            # Set session context for token logging
            _log.info("Setting token logging context",
                     form_id=form_id,
                     session_id=session_id,
                     form_session_id=form_session_id)
            try:
                self._live_ai.set_session_context(
                    form_session_id=form_session_id or session_id,  # Use persistent ID if available
                    form_id=form_id,
                    current_section_id=current_section_id,
                )
                _log.info("Token logging context set successfully",
                         form_session_id=form_session_id or session_id)
            except AttributeError as e:
                # Older adapters may not have this method
                _log.warning("set_session_context not available on adapter", error=str(e))

            # Register callbacks with Gemini Live AI
            # System instruction is passed from caller and included in the initial
            # Gemini connection config.
            try:
                self._live_ai.set_callbacks(
                    on_form_update=self._callback_handler.on_form_update,
                    on_transcript=self._callback_handler.on_transcript,
                    on_audio=self._callback_handler.on_audio,
                    on_tool_call=self._callback_handler.on_tool_call,
                    on_go_away=self._callback_handler.on_go_away,
                    on_user_activity=self._on_user_activity,
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
                    # If this also fails, give up silently -- the adapter
                    # truly doesn't implement callback registration.
                    pass

    async def stream_audio(self, audio_chunk: bytes):
        """Stream audio chunk to Gemini. Delegates to AudioHandler.

        Dropped while a section switch is in flight: _switch_lock is held for
        the ENTIRE swap on BOTH switch paths (manual switch_to_section and the
        AI-initiated _complete_section_switch), so this is the server-side
        backstop that keeps mic audio captured during 'switching_section' from
        leaking into the NEW Gemini session before the client has been told the
        switch completed. The manual path is additionally guarded by the WS
        loop's drop_audio flag; the AI path has only this guard (fresh-eyes
        round 2, PR #150).
        """
        if self._switch_lock.locked():
            now = time.monotonic()
            if now - self._last_switch_drop_log >= 1.0:
                self._last_switch_drop_log = now
                _log.info("audio_dropped_switch_in_progress",
                          session_id=self._session_id,
                          bytes=len(audio_chunk))
            return
        if self._audio_handler:
            await self._audio_handler.stream_audio(audio_chunk)

    async def send_context_hint(self, hint_text: str):
        """Send context hint to Gemini. Delegates to AudioHandler."""
        if self._audio_handler:
            await self._audio_handler.send_context_hint(hint_text)

    async def send_manual_field_update(self, field_id: str, field_name: str, value: Any, next_field_hint: Optional[str] = None):
        """Notify Gemini of manual field update. Delegates to AudioHandler."""
        if self._audio_handler:
            # AudioHandler appends next_field_hint to the spoken message, so strip
            # the "(field_id: ...)" parenthetical here too (bd polyglot-pdf-dx7).
            await self._audio_handler.send_manual_field_update(
                field_id, field_name, value, strip_field_id_from_hint(next_field_hint)
            )

    async def send_activity_start(self):
        """Send activity_start signal. Delegates to AudioHandler."""
        if self._audio_handler:
            await self._audio_handler.send_activity_start()

    async def send_activity_end(self):
        """Send activity_end signal. Delegates to AudioHandler."""
        if self._audio_handler:
            await self._audio_handler.send_activity_end()

    async def send_disclaimer_message(self, spoken_language: str, disclaimer_text: str):
        """
        Send disclaimer initiating message to Gemini.

        This is triggered when user first selects a language. Gemini will read
        the disclaimer aloud in the selected language.

        Args:
            spoken_language: Language for Gemini to speak (e.g., "Spanish", "French")
            disclaimer_text: The full translated disclaimer text to read verbatim
        """
        if not self._live_ai:
            _log.warning("send_disclaimer_message_no_ai", session_id=self._session_id)
            return

        message = self._settings.DISCLAIMER_INITIATING_MESSAGE.format(
            spoken_language=spoken_language,
            disclaimer_text=disclaimer_text
        )

        _log.info("sending_disclaimer_message", session_id=self._session_id, language=spoken_language)
        await self._live_ai.send_client_content(message)

    def _resolve_hint_field_schema(self, next_field_hint: Optional[str]) -> Optional[Dict[str, Any]]:
        """Resolve the CURRENT field's full schema from a next_field_hint, for DTI
        initiating-message guidance (bd polyglot-pdf-j748).

        The hint embeds the field_id as a quoted parenthetical
        ("... (field_id: '<id>', ...)"); extract it and look the id up among the
        field schemas this stateless service knows: the handshake's
        self._schema['fields'] (field 1 at session/section start) plus
        self._dti_extra_fields (fields 2..N, recorded from next_field_hint_response).
        Returns the raw field dict, or None if the hint has no field_id or it does
        not resolve to a known schema -- callers then render NO guidance block rather
        than guessing a wrong field.
        """
        if not next_field_hint:
            return None
        m = re.search(r"field_id:\s*'([^']*)'", next_field_hint)
        if not m:
            return None
        field_id = m.group(1)
        if not field_id:
            return None
        for field in (self._schema or {}).get("fields") or []:
            if field.get("id") == field_id:
                return field
        return self._dti_extra_fields.get(field_id)

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

        # Strip the technical "(field_id: ...)" parenthetical so Gemini doesn't
        # read the raw field_id aloud (bd polyglot-pdf-dx7). The field_id is still
        # delivered to Gemini -- in DTI mode via the current-field guidance block
        # below; in legacy/JIT via the system instruction's FIELDS block.
        spoken_hint = strip_field_id_from_hint(next_field_hint)

        # DTI current-field channel (epic polyglot-pdf-13w7, bd polyglot-pdf-j748):
        # the static DTI SI carries no field data, so the CURRENT field's exact
        # field_id + guidance must ride the initiating message, rendered by the SAME
        # render_field_guidance that delivers fields 2..N in the confirm_field
        # response. The current field is whatever next_field_hint points at -- resolve
        # it by the field_id embedded in the UNSTRIPPED hint, NOT schema["fields"][0]:
        # this same opener fires on a mid-form spoken-language change (where the
        # current field is field N, not the handshake's field 1), and on a full-section
        # handshake schema["fields"][0] is merely the positional first field, not the
        # client's computeNextField selection (Codex PR #254). The id is NOT stripped
        # here: this block is CONTEXT the model acts on (and copies the id verbatim
        # from), not text to read aloud. If the id cannot be resolved to a known
        # field schema, render NOTHING rather than a wrong field. Non-DTI modes leave
        # it empty so legacy/JIT output is unchanged (their SI still carries field data).
        current_field_guidance = ""
        section_metadata_block = ""
        if getattr(self._settings, "USE_DTI", False):
            field = self._resolve_hint_field_schema(next_field_hint)
            if field:
                # Track the current field for update_form_fields coercion (bd
                # polyglot-pdf-h1bn): this opener fires at session/section start
                # (field 1) and on a spoken-language change (field N); in every case
                # `field` is the field the model is about to fill.
                if field.get("id"):
                    self._current_field_id = field["id"]
                # fill_language rides the field render (bd polyglot-pdf-uogm) so the
                # model writes VALUES in the configured language; the static SI no
                # longer carries it.
                current_field_guidance = (
                    "\n\nCURRENT FIELD (copy this field_id verbatim; do NOT read it aloud):\n"
                    + render_field_guidance(field, fill_language=self._fill_language)
                )

            # DTI form/section metadata channel (bd polyglot-pdf-uogm): the static SI
            # carries no form/session state, so the title/section/progress/previous-
            # names/confirmation-policy block rides the initiating message at session
            # AND section start. Source is self._last_section_metadata (seeded at
            # session start + set on every switch) + the stored schema's form title --
            # NOT schema["manifest"], which is absent on a section-switch handshake
            # (bd polyglot-pdf-fu1h F1; a manifest-sourced block would be empty on
            # sections 2..N).
            sm = self._last_section_metadata or {}
            # Pass the REAL title or None (not a "Form" default) so render_section_metadata's
            # "nothing substantive -> return ''" guard can fire on a metadata-less session.
            form_title = (self._schema or {}).get("form_metadata", {}).get("title") or None
            block = render_section_metadata(
                form_title=form_title,
                section_number=sm.get("section_number"),
                total_sections=sm.get("total_sections"),
                section_label=sm.get("section_label"),
                previous_spoken_names=sm.get("previous_spoken_names"),
            )
            if block:
                section_metadata_block = "\n\n" + block

        # On mid-section reconnects use the resume template so Gemini skips
        # the greeting and section re-introduction (bd polyglot-pdf-vmxx).
        template = (
            self._settings.RESUME_INITIATING_MESSAGE
            if self._is_resume_session
            else self._settings.INITIATING_MESSAGE
        )
        # Append the DTI metadata block AFTER the formatted template (not a new
        # placeholder) so non-DTI output is byte-identical (block is "" there).
        message = template.format(
            spoken_language=spoken_language,
            next_field_hint=spoken_hint,
            current_field_guidance=current_field_guidance
        ) + section_metadata_block

        # Never log the rendered message text: it embeds next_field_hint, which is
        # derived from form field data (no-PII policy, docs/standards/hipaa-pii-policy.md).
        # Log only its length so the redacted form passes the never-logged guard
        # (bd polyglot-pdf-uov.15).
        _log.info("send_initiating_message",
                 session_id=self._session_id,
                 spoken_language=spoken_language,
                 is_resume=self._is_resume_session,
                 message_length=len(message))

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
            _log.info("recovery_prompt_level_3_farewell", session_id=self._session_id)

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

    async def send_prompt(self, prompt: str):
        """
        Send a prompt to Gemini that should trigger an audio response.

        Uses send_client_content() to initiate Gemini's response, unlike
        send_context_hint() which only adds context without expecting a response.

        The prompt is reformatted as an imperative command to override the
        "wait for user to speak first" behavior in the system instruction.

        Used for disclaimer reading, manual prompts, etc.

        Args:
            prompt: Text prompt to send to Gemini (should contain the text to read and language)
        """
        if self._live_ai is None:
            return

        # Reformat as imperative command to trigger immediate response
        # The system instruction says "detect language from first utterance"
        # so we need to override that with a direct command
        formatted_prompt = f"SYSTEM OVERRIDE: {prompt} Respond immediately in audio without waiting for user input."

        await self._live_ai.send_client_content(formatted_prompt)

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
            _log.info("gemini_session_closed", session_id=self._session_id)
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
        _log.info("restart_gemini_session_check",
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

        if self._callback_handler is None:
            _log.error("restart_gemini_session_no_callbacks", session_id=self._session_id)
            raise RuntimeError("No callback handler available - cannot restart")

        _log.info("restart_gemini_session_start",
                 session_id=self._session_id,
                 has_next_field_hint=bool(next_field_hint))
        
        # Build system instruction from existing schema
        # Note: Backend doesn't store current_values (client is source of truth)
        # For restart, we use empty dict since frontend will sync values if needed.
        # Thread the retained section metadata (bd polyglot-pdf-umv) so the rebuilt SI
        # keeps the user's section position + previously-spoken field names. Without
        # it, a mid-section restart defaults to "section 1 of 1" with no prior history,
        # so Gemini loses its place and can re-ask earlier-section fields. None for
        # single-section forms / before any switch, which yields the original behavior.
        sm = self._last_section_metadata or {}
        sm_number = sm.get("section_number")
        # Mirror switch_to_section's label EXPRESSION exactly (line ~573):
        # `.get("section_label", f"Section {n}")` -- the default fires only on a MISSING
        # key, so a present-but-None label passes through as None (build_form_context then
        # falls back to form_title). Using the same expression here keeps a restart's
        # label identical to the switch's, including that present-None edge (fresh-eyes
        # PR #82). When there was no prior switch, sm is {} -> label is None -> default
        # non-sectioned behavior, which is correct.
        sm_label = sm.get("section_label", f"Section {sm_number}") if sm_number is not None else None
        system_instruction = self.build_form_context_message(
            self._schema,
            {},  # Empty values - frontend maintains state
            section_number=sm_number,
            total_sections=sm.get("total_sections"),
            section_label=sm_label,
            previous_spoken_names=sm.get("previous_spoken_names"),
        )
        
        # Restart Gemini session (doesn't re-accept WebSocket)
        # Use deepcopy to avoid mutating the original declarations
        tool_declarations = deepcopy(self._settings.TOOL_DECLARATIONS)

        # Re-register the same callbacks used at session creation
        # (form_filling_service.py:155). set_callbacks is synchronous -- do not
        # await it. on_transcript is always passed; whether transcripts are
        # actually emitted is gated by enable_transcripts.
        self._live_ai.set_callbacks(
            on_form_update=self._callback_handler.on_form_update,
            on_transcript=self._callback_handler.on_transcript,
            on_audio=self._callback_handler.on_audio,
            on_tool_call=self._callback_handler.on_tool_call,
            on_go_away=self._callback_handler.on_go_away,
            on_user_activity=self._on_user_activity,
            system_instruction=system_instruction,
            tool_declarations=tool_declarations,
            enable_transcripts=bool(self._send_transcript),
        )

        # Verify session is now active
        is_active_after = self._live_ai.is_session_active()
        _log.info("gemini_session_restarted",
                 session_id=self._session_id,
                 session_active_after=is_active_after)

        # DTI: the rebuilt SI is fully static (epic polyglot-pdf-13w7), so unlike the
        # legacy/JIT SI it carries NO field data -- after a restart (e.g. Level-3
        # farewell reconnect) the model would have no current-field guidance and no
        # form/section metadata until the next confirm. Fire the initiating message
        # so the current field's guidance + the metadata block reach Gemini, exactly
        # as the section-switch and session-start paths do (bd polyglot-pdf-h1bn,
        # closing the gap the fu1h audit flagged). send_initiating_message resolves the
        # field from the hint's id; with no hint it falls back gracefully (renders no
        # guidance block rather than a wrong field). It uses whichever template
        # _is_resume_session selects -- which is the GREETING template on a
        # first-connect Level-3 restart (the resume flag was set at the original fresh
        # connect), so the user hears a re-greeting; refining that to the resume
        # template is bd polyglot-pdf-bhem. Non-DTI restarts are unaffected (block empty).
        if getattr(self._settings, "USE_DTI", False):
            try:
                await self.send_initiating_message(
                    self._spoken_language,
                    next_field_hint or "the first unfilled field",
                )
            except Exception as exc:
                _log.error("restart_gemini_session_initiating_message_failed",
                          session_id=self._session_id, error=str(exc))

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

        # The system instruction's "ask for: {next_field_hint}" directive is what
        # Gemini speaks at session start (the initial_field_hint from the
        # handshake) and after a section switch. Strip the "(field_id: ...)"
        # parenthetical here so that directive never carries the raw field_id into
        # Gemini's spoken greeting (bd polyglot-pdf-dx7). This is the system-
        # instruction sibling of the runtime-hint strip in request_coordinator.
        # timing_sysinstruction_build checkpoint 2 (bd polyglot-pdf-cwsy):
        # measure build duration and log size_bytes. Call site logged at INFO so
        # a log scan for "timing_sysinstruction_build" shows how long context
        # assembly takes relative to the connect latency.
        _t_si_start = time.monotonic()
        result = build_form_context(
            schema,
            current_values,
            self._fill_language,
            section_number=section_number,
            total_sections=total_sections,
            section_label=section_label,
            previous_spoken_names=previous_spoken_names,
            next_field_hint=strip_field_id_from_hint(next_field_hint),
            is_reconnect=self._is_resume_session,
        )
        _si_ms = round((time.monotonic() - _t_si_start) * 1000)
        try:
            _log.info(
                "timing_sysinstruction_build",
                build_ms=_si_ms,
                size_bytes=len(result.encode("utf-8")) if result else 0,
                session_id=self._session_id,
            )
        except Exception:
            # Measurement must never alter this method's return path
            # (fresh-eyes round 2, PR #150).
            pass
        return result

    def update_schema(self, schema: dict, current_values: dict, fill_language: str = "English"):
        """Update session schema and language settings."""
        self._schema = schema
        self._fill_language = fill_language
        # Note: current_values are client-managed, we don't store them

    async def end_session(self):
        # Cancel any in-flight detached AI section-switch BEFORE teardown (Codex
        # PR #135): otherwise, if the client disconnects while _complete_section_switch
        # is waiting on closed_event, it would later restart Gemini via start_session
        # against a cleared WebSocket -- an orphaned backend session after the user
        # is gone. The task's CancelledError handler exits without restarting.
        if self._switch_task is not None and not self._switch_task.done():
            self._switch_task.cancel()
            try:
                await self._switch_task
            except (asyncio.CancelledError, Exception):
                pass
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

        Serialized by _switch_lock (bd polyglot-pdf-0c1, absorbed from WS-D): both
        the manual switch (websocket_routes manual_section_switch) and the
        AI-initiated switch (via _complete_section_switch) call this method, and a
        concurrent click-during-AI-switch must not restart the session twice. The
        lock makes the finalize()->start_session restart atomic per switch.
        """
        async with self._switch_lock:
            await self._switch_to_section_locked(
                section_schema=section_schema,
                section_values=section_values,
                section_metadata=section_metadata,
                initial_field_hint=initial_field_hint,
            )

    async def _switch_to_section_locked(
        self,
        section_schema: Dict[str, Any],
        section_values: Dict[str, Any],
        section_metadata: Dict[str, Any],
        initial_field_hint: Optional[str] = None,
    ) -> None:
        """The actual section restart, run under _switch_lock (see switch_to_section).

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

        # Retain section metadata so a later restart_gemini_session can rebuild the
        # system instruction with this position instead of defaulting to section 1
        # (bd polyglot-pdf-umv). Navigation state only -- no field values stored.
        # Shallow-copy so a later mutation of the caller's dict (it arrives via JSON
        # through the request coordinator) can't silently change what a restart rebuilds
        # (fresh-eyes PR #82 -- latent aliasing, no current trigger but cheap to close).
        self._last_section_metadata = dict(section_metadata)

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
            # Persist the form_session_id across section switches so the rebuilt
            # CallbackHandler keeps the same audit-log key (bd rwjy fresh-eyes gap).
            form_session_id=self._form_session_id,
            # Thread the new section id into token-log context (bd polyglot-pdf-tb7)
            current_section_id=section_metadata.get("section_id"),
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
        # DTI current-field coercion (bd polyglot-pdf-h1bn): a DTI turn is scoped to
        # ONE field -- the model is answering the guidance for self._current_field_id,
        # and cross-field intent goes to the secretary, never update_form_fields. So
        # when the model targets a DIFFERENT id than the current field -- a
        # hallucinated id (e.g. 'p1_line2_uscis_account' for 'p1_line2_acctidentifier',
        # the residual jnjj.46 model-disobedience) OR a valid-but-wrong id (the 8vy3
        # ordering drift) -- the VALUE is right but the TARGET is wrong. Deterministically
        # re-point the value at the known current field so the field still fills,
        # rather than rejecting it as unknown / filling the wrong field. The model's
        # field_id is advisory, not authoritative. Gated on DTI + a known current
        # field + a single-field update (the one-field-per-turn invariant); non-DTI /
        # multi-field / matching-id paths are untouched.
        updates = self._coerce_dti_update_to_current_field(updates)

        # Build field list on-demand from schema for validation
        # Values are not persisted - this is just for acknowledgment
        fields = self._build_fields_from_schema()

        # Use ValidationHandler to match and validate fields
        validator = ValidationHandler(session_id=session_id)
        return validator.validate_field_updates(fields, updates)

    def _coerce_dti_update_to_current_field(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Re-point a single DTI update onto the current field when the model's id
        does not match it (bd polyglot-pdf-h1bn). Returns updates unchanged outside
        the gated case. See handle_update_fields_tool_call for the rationale."""
        if not getattr(self._settings, "USE_DTI", False):
            return updates
        current = self._current_field_id
        if not current:
            return updates
        # One-field-per-turn invariant: only coerce a single-field update. A
        # multi-field call is already an error the caller's guard handles; don't
        # silently merge them onto one field.
        if len(updates) != 1:
            return updates
        sent_id, value = next(iter(updates.items()))
        if sent_id == current:
            return updates  # normal path -- model named the right field
        _log.info("dti_update_coerced_to_current_field",
                  session_id=self._session_id,
                  sent_field_id=sent_id, current_field_id=current)
        return {current: value}

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

    async def handle_ask_secretary(self, query: str) -> str:
        """Run an ask_secretary lookup (bd polyglot-pdf-jnjj.45c).

        Assembles the secretary's context -- the form catalog (self._schema, the
        full-form catalog the client supplies at handshake; bd jnjj.45d) plus the
        client's CURRENT values + applicability (a fresh round-trip) -- and runs the
        BLOCKING TextAIGemini.ask() under a timeout so a slow lookup cannot hang the
        conversation. Returns the secretary's prose answer, or "" on any failure
        (no adapter / no schema / timeout / error) so the caller fail-opens and the
        principal asks the user directly.

        The timeout here is the INTERIM tail-latency guard (Gate 2 measured
        occasional multi-second spikes); the graceful "please hold" filler is
        jnjj.43. Note it bounds ONLY the model call -- the preceding client
        form-state round-trip has its own ~5s coordinator timeout, so the
        worst-case total blocking wait is ~SECRETARY_TIMEOUT_S + 5s.

        PII: logs ids/counts/latency/timeout only -- never the query, the values,
        or the answer (callback_handler PII discipline).
        """
        if self._text_ai is None:
            _log.warning("ask_secretary_no_text_ai", session_id=self._session_id)
            return ""

        schema = self._schema or {}
        if not schema.get("fields"):
            _log.warning("ask_secretary_no_schema", session_id=self._session_id)
            return ""

        # Fresh full form state from the client (all fields). Shape:
        # {field_id: {"value": ..., "confirmed": ..., ["shown": bool]}} -- the
        # renderers read the value out of that wrapper directly; `shown` (added by
        # jnjj.45d) feeds the shown_map (default True until then).
        try:
            form_state = await self.request_form_state_from_client(None)
        except Exception as exc:  # noqa: BLE001
            _log.warning("ask_secretary_form_state_error",
                         exc_type=type(exc).__name__, session_id=self._session_id)
            return ""
        form_state = form_state or {}

        shown_map = {}
        for fid, entry in form_state.items():
            if isinstance(entry, dict) and "shown" in entry:
                shown_map[fid] = bool(entry.get("shown"))

        context = {
            "schema": schema,
            "field_values": form_state,
            "shown_map": shown_map,
        }

        timeout_s = getattr(self._settings, "SECRETARY_TIMEOUT_S", 8.0)
        try:
            answer = await asyncio.wait_for(
                self._text_ai.ask(query, context), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            _log.warning("ask_secretary_timeout", timeout_s=timeout_s,
                         session_id=self._session_id)
            return ""
        except Exception as exc:  # noqa: BLE001
            _log.warning("ask_secretary_ask_error",
                         exc_type=type(exc).__name__, session_id=self._session_id)
            return ""

        _log.info(
            "ask_secretary_complete",
            field_count=len(form_state),
            shown_count=len(shown_map),
            answer_len=len(answer or ""),
            session_id=self._session_id,
        )
        return answer or ""

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

    def handle_next_field_hint_response(
        self, request_id: str, hint: Optional[str],
        next_field_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Handle next_field_hint_response message from frontend.

        Delegates to RequestCoordinator.

        Args:
            request_id: ID matching the original request
            hint: Formatted hint string or None if form is complete
            next_field_schema: (DTI, bd polyglot-pdf-jnjj.22) the next field's full
                schema supplied by the client; None for legacy/non-DTI clients.
        """
        if not self._request_coordinator:
            _log.warning("handle_next_field_hint_response_no_coordinator", session_id=self._session_id)
            return

        self._request_coordinator.handle_next_field_hint_response(
            request_id, hint, next_field_schema)

    def handle_confirm_field_response(
        self, request_id: str, recorded: bool, reason: Optional[str] = None,
        section_complete: bool = False,
    ) -> None:
        """
        Handle confirm_field_response message from frontend.

        Delegates to RequestCoordinator -- completes the synchronous confirm_field
        round-trip (bd polyglot-pdf-wpw.2).

        Args:
            request_id: ID matching the original confirm_field request
            recorded: True if the frontend actually recorded the confirmation
            reason: Fixed category token when not recorded (e.g. "no_value")
            section_complete: True when this confirm completed the section (bd
                polyglot-pdf-njvh); the confirm handler then skips the racing
                next-field-hint request.
        """
        if not self._request_coordinator:
            _log.warning("handle_confirm_field_response_no_coordinator", session_id=self._session_id)
            return

        self._request_coordinator.handle_confirm_field_response(
            request_id, recorded, reason, section_complete)

    def _clear_current_field_id(self) -> None:
        """Invalidate the current-field coercion pointer (bd polyglot-pdf-h1bn).

        Called on a successful confirm: the field just confirmed is DONE, so the
        pointer must not keep naming it -- otherwise, if the next-field hint/schema
        delivery times out, a later update_form_fields would be deterministically
        coerced onto the just-confirmed field, overwriting it (Codex PR #264).
        merge_field_schema re-sets the pointer when the next field's schema arrives.
        """
        self._current_field_id = None

    def merge_field_schema(self, field_schema: Dict[str, Any]) -> None:
        """Record a CLIENT-SUPPLIED field schema for VALIDATION (DTI, bd
        polyglot-pdf-jnjj.22; Codex PR #229).

        In JIT/DTI mode self._schema['fields'] holds only the first field, so
        update_form_fields validation (build_fields_from_schema) would reject every
        later field as 'unknown'. The client delivers each next field's full schema
        on next_field_hint_response; we record it here (SCHEMA ONLY -- no user
        values) so _build_fields_from_schema can validate it.

        Stored in a SEPARATE dict, NOT appended to self._schema['fields']: the
        handshake's schema['fields'][0] is the session/section's first field, and
        keeping later fields out of that list avoids polluting it (e.g. a recovery
        restart's context build, Codex PR #229 round-2 follow-up). The DTI initiating
        message resolves the CURRENT field by the hint's field_id, looking it up in
        self._schema['fields'] PLUS this dict (_resolve_hint_field_schema, bd
        polyglot-pdf-j748), so recorded later fields are reachable for guidance
        without being positional. Idempotent by field id.
        """
        if not field_schema or not field_schema.get("id"):
            return
        fid = field_schema["id"]
        if fid not in self._dti_extra_fields:
            self._dti_extra_fields[fid] = field_schema
            _log.debug("dti_recorded_field_for_validation", field_id=fid,
                       total_extra=len(self._dti_extra_fields))
        # Track the CURRENT field (bd polyglot-pdf-h1bn): each next-field schema the
        # client delivers (on confirm of the prior field) IS the field the model is
        # about to fill, so record its id as the current-field routing pointer for
        # update_form_fields coercion. Transient per-turn metadata (a single id,
        # overwritten each turn, no user values, re-established by the client on
        # reconnect) -- NOT persisted field state, so the stateless invariant holds.
        self._current_field_id = fid

    def get_next_field_schema_for_jit(self, updated_field_id: str) -> Optional[Dict[str, Any]]:
        """
        Get next field's full schema for JIT loading (Phase 2.5: Token Reduction).

        Called after successful field update to include next field schema in tool response.
        Tracks loaded_field_ids to prevent duplicate schemas in Gemini context.

        Args:
            updated_field_id: ID of the field that was just updated

        Returns:
            Next field's complete schema dict, or None if no next field
        """
        if not self._settings.USE_JIT_SCHEMA:
            return None

        if not self._schema:
            return None

        # Get current part data from schema
        # For now, assume single part/section - in future this could be enhanced
        # to handle multi-part forms by tracking current part
        part_data = self._schema

        # Get next field schema using manifest service
        next_schema = get_next_field_schema(part_data, updated_field_id)

        if next_schema and next_schema.get('id'):
            next_id = next_schema['id']
            # ACTUALLY gate on the de-dup set before returning. The set was being
            # populated but never checked, so a repeat confirm_field on the same
            # field (the no-value retry path) -- or a reconnect -- re-delivered a
            # schema Gemini already has, the exact duplication JIT exists to avoid
            # (bd polyglot-pdf-jnjj.9 gaps G/L, bug polyglot-pdf-h2ii;
            # should_include_schema_in_response was dead code).
            if not should_include_schema_in_response(next_id, self._loaded_field_ids):
                _log.debug("jit_schema_deduped", field_id=next_id,
                           total_loaded=len(self._loaded_field_ids))
                return None
            # First delivery: mark as sent so the next call de-dups it.
            self._loaded_field_ids.add(next_id)
            _log.debug("jit_schema_sent", field_id=next_id,
                      total_loaded=len(self._loaded_field_ids))

        return next_schema

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

        # KEYSTONE y4a FIX (bd polyglot-pdf-0c1): this handler runs ON the Gemini
        # receive task (the switch_section tool callback). Awaiting switch_to_section
        # here would await finalize(), which cancels that very task BEFORE the
        # FunctionResponse we return below reaches the wire -- orphaning the
        # switch_section response on the session that issued it. Instead:
        #   1. ask the adapter for a COOPERATIVE shutdown (flush-then-exit, no
        #      self-cancel) and grab the Event that fires when the old loop is done;
        #   2. perform the actual session swap on a DETACHED task that awaits that
        #      Event first (so the old loop is fully wound down -- no two live loops
        #      sharing callbacks);
        #   3. RETURN the success payload now. That return value is the
        #      FunctionResponse the receive loop sends on the OLD session before it
        #      breaks (the cooperative flush point), so the call is answered on the
        #      session that made it -- the Live API contract y4a violated.

        # Guard: refuse a second switch while one is already in flight, so a manual
        # click during an AI switch (or vice versa) can't start two swaps.
        if self._switch_task is not None and not self._switch_task.done():
            return {"success": False, "message": "A section switch is already in progress."}

        if self._live_ai is None:
            return {"success": False, "message": "No AI session to switch."}

        closed_event = self._live_ai.begin_graceful_shutdown()
        # timing_section_switch_total checkpoint 8 (bd polyglot-pdf-cwsy):
        # capture the monotonic timestamp at begin_graceful_shutdown so the
        # detached swap task can measure total switch duration end-to-end.
        _t_switch_start = time.monotonic()
        self._switch_task = asyncio.create_task(
            self._complete_section_switch(closed_event, section_info, _t_switch_start)
        )

        return {
            "success": True,
            "message": f"Switched to section {section_info['metadata']['section_number']}: {section_info['metadata']['section_label']}",
        }

    async def _complete_section_switch(
        self, closed_event, section_info: Dict[str, Any],
        t_switch_start: Optional[float] = None,
    ) -> None:
        """Finish an AI-initiated section switch on a DETACHED task (bd 0c1).

        Holds _switch_lock for the ENTIRE swap -- including the wait for the old
        loop to close -- so a concurrent MANUAL switch (websocket_routes ->
        switch_to_section, which also takes _switch_lock) cannot interleave and
        leave the user on the wrong section (Codex/fresh-eyes PR #135: the
        is-in-progress guard alone didn't cover the AI-vs-manual overlap, because
        the manual path does not consult _switch_task). Because we hold the lock,
        we call the INNER _switch_to_section_locked directly -- re-acquiring the
        non-reentrant lock via the public switch_to_section would deadlock.

        A detached task MUST NOT swallow exceptions silently -- the catch-all logs
        and notifies the frontend so a failed swap surfaces instead of leaving the
        user on a dead session.
        """
        try:
            async with self._switch_lock:
                # Wait for the old loop to finish flushing + exit. The 5s bound is a
                # backstop: switch_to_section's own finalize() hard-cancels as a
                # fallback if the cooperative exit somehow stalls, so we proceed
                # either way -- but normally the event fires in well under a second.
                try:
                    await asyncio.wait_for(closed_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    _log.warning("section_switch_graceful_close_timeout",
                                session_id=self._session_id)

                await self._switch_to_section_locked(
                    section_schema=section_info["schema"],
                    section_values=section_info["current_values"],
                    section_metadata=section_info["metadata"],
                    initial_field_hint=section_info.get("initial_field_hint"),
                )
                # timing_section_switch_total checkpoint 8 (bd polyglot-pdf-cwsy):
                # _switch_to_section_locked has returned -- the new session is ready
                # and the initiating message has been sent. Measure total switch time
                # from begin_graceful_shutdown to here.
                if t_switch_start is not None:
                    try:
                        _sw_ms = round((time.monotonic() - t_switch_start) * 1000)
                        _log.info(
                            "timing_section_switch_total",
                            switch_total_ms=_sw_ms,
                            section_number=section_info.get("metadata", {}).get("section_number"),
                            session_id=self._session_id,
                        )
                    except Exception:
                        pass
        except asyncio.CancelledError:
            # The WS closed mid-swap and end_session cancelled this task (Codex
            # PR #135). Do NOT restart Gemini against a dead socket -- just exit.
            _log.info("section_switch_cancelled", session_id=self._session_id)
            raise
        except Exception as exc:
            _log.error("section_switch_failed",
                      session_id=self._session_id,
                      error=str(exc))
            # Surface the failure to the frontend in a shape it HANDLES: the FE
            # message switch handles `error` (and ignores unknown types), so use
            # the error envelope, not a bespoke section_switch_failed type
            # (Codex PR #135).
            if self._websocket is not None:
                try:
                    await self._websocket.send_json({
                        "type": "error",
                        "code": "section_switch_failed",
                        "message": f"Failed to switch section: {str(exc)}",
                    })
                except Exception:
                    _log.error("section_switch_failed_notify_failed",
                              session_id=self._session_id)

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

    # NOTE: the complete_section tool/handler was removed. Section completion is
    # auto-detected by the frontend (handleConfirmFieldRequest) when all fields
    # are confirmed, which then triggers a section switch via manual_section_switch.


# Note: factory for FormFillingService lives in backend.dependencies to avoid
# circular imports. The service implementation should remain importable without
# pulling in FastAPI dependency providers.
