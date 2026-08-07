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
from backend.services import guidance_contract
from backend.utils.confirmation_logger import (
    resolve_edition_marker as _resolve_edition_marker,
)
from backend.utils.language_codes import bcp47_codes_for_spoken_language
from .field_utils import (
    build_fields_from_schema,
    strip_field_id_from_hint,
)
from .ai_context import render_field_guidance, render_section_metadata
from .option_translation import get_translation_overrides
from .validation_handler import ValidationHandler
from .audio_handler import AudioHandler
from .request_coordinator import RequestCoordinator
from .callback_handler import CallbackHandler
from .validator_service import ValidatorService, WHOLE_FORM_PRO_SI

# Logger for service-level diagnostics
_log = structlog.get_logger().bind(service="FormFillingService")


class FormFillingService:
    """Orchestrates the logic for filling form fields based on AI tool calls (web forms only)."""

    def __init__(
        self,
        live_ai: Optional[ILiveAI] = None,
        settings: Optional[Settings] = None,
        text_ai: Optional[Any] = None,
        text_ai_pro: Optional[Any] = None,
    ):
        # AI adapter is optional for unit tests that only exercise form logic
        self._live_ai = live_ai
        self._settings = settings or get_settings()
        # Cheap text model behind the secretary (bd polyglot-pdf-jnjj.45c). Optional
        # so unit tests that exercise only form logic need not wire it; the
        # ask_secretary handler fail-opens when it is None.
        self._text_ai = text_ai
        # W6 (bd polyglot-pdf-gbus): the gemini-2.5-pro whole-form validator for the
        # end-of-form pro pass. None unless FORM_COMPLETE_PRO_VALIDATOR is on (the
        # dependency wires it only when the flag is set), so handle_form_complete_pro
        # no-ops when the pro pass is disabled. The flag DEFAULTS ON since
        # 2026-08-03, so this is normally wired.
        self._text_ai_pro = text_ai_pro
        self._websocket = None
        self._session_id = None
        # Web session state - schema only (no field caching)
        self._schema: Optional[Dict[str, Any]] = None  # Schema for context only
        # Full-form catalog for the secretary (bd polyglot-pdf-p68s / jnjj.45d).
        # self._schema is the per-section schema that drives the live-model SI; the
        # secretary's render_static_catalog needs the WHOLE form (all
        # parts/sections/fields). Kept SEPARATE so the per-section SI path is never
        # disturbed. Schema only, no PII; rebuilt from the handshake on every
        # (re)connect, so the stateless invariant holds. None until the first
        # handshake supplies it (older clients omit it -> secretary falls back to
        # self._schema). Survives section switches (preserved unless a switch's
        # start_session supplies a fresh full_schema).
        self._full_schema: Optional[Dict[str, Any]] = None
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
        # Runtime option-label translation (bd polyglot-pdf-ow1e):
        # {english_label: translated_label} for the session's spoken language,
        # assigned by the background task fired in start_session. Empty until
        # (and unless) the translation lands -- renders in that window fall back
        # to English labels, covered by the SI's translate-on-the-fly rule.
        # Schema data only (labels, no user values); the stateless invariant holds.
        self._option_translations: Dict[str, str] = {}
        # Field spoken-name + section-label translations (bd polyglot-pdf-tupu.2),
        # same build/publish/fallback contract as the option labels above:
        # {english_spoken_name: translated} / {english_section_label: translated}.
        self._spoken_name_translations: Dict[str, str] = {}
        self._section_label_translations: Dict[str, str] = {}
        # Strong ref to the in-flight translation task so it isn't GC'd and can
        # be cancelled on end_session (the shared per-process build it awaits is
        # shielded and keeps running for other sessions).
        self._option_translation_task: Optional[asyncio.Task] = None
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
        # Kit identity + government edition for the audit trail (bd
        # polyglot-pdf-47r3), stored for the same reason as _form_session_id.
        self._kit_id: Optional[str] = None
        self._edition_date: Optional[str] = None
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
        # Strong refs to in-flight async secretary-deliver tasks (bd
        # polyglot-pdf-jnjj.43). When an ask_secretary lookup blows SECRETARY_DEADLINE_S,
        # the tool returns a "pending" result (no spoken filler -- the gap-based wpw.5
        # thinking indicator covers the wait) and the still-running lookup is detached
        # here so the answer can be delivered on a LATER turn (send_client_content)
        # when it lands. A set (not a single slot) because the user could trigger a
        # second lookup while the first is still resolving; tasks self-remove on
        # completion. Cancelled in end_session so a disconnect never leaves an orphaned
        # deliver pushing into a dead session.
        self._secretary_deliver_tasks: set = set()
        # Rate-limit stamp for the switch-window audio-drop log (stream_audio).
        self._last_switch_drop_log: float = 0.0

    def _build_fields_from_schema(self) -> list:
        """Build field list from schema on-demand (no caching).

        Used by web sessions to construct field objects for tool responses.
        Backend doesn't persist these - they're rebuilt each time.

        Delegates to field_utils.build_fields_from_schema for the actual logic.

        In DTI mode (on the manifest-first handshake) self._schema['fields'] holds
        only the first field, so the client-supplied fields recorded via
        merge_field_schema (DTI, bd polyglot-pdf-jnjj.22) are folded in here for
        validation -- WITHOUT mutating
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

    def _is_known_field_id(self, field_id: str) -> bool:
        """True when field_id resolves to a field this session has seen -- the
        handshake schema, a client-delivered merge, or the handshake MANIFEST
        (bd polyglot-pdf-8vy3).

        Used by the DTI coercion gates: a RESOLVABLE id is authoritative (the
        model may legitimately target a PREVIOUS field -- a late correction after
        its confirm advanced the pointer); only an UNRESOLVABLE id (the jnjj.46
        hallucination mode) is re-pointed at the current field.

        The MANIFEST check matters on a DTI reconnect (GoAway / mid-section): the
        fresh handshake carries only field 1's full schema and start_session
        cleared _dti_extra_fields, so previously-delivered fields survive only as
        manifest field_id entries. Without it, a legitimate post-reconnect
        correction to an earlier field would read as "unknown" and be coerced
        onto the current field -- the exact corruption this gate exists to
        prevent (Codex PR #321 P1). A manifest-known-but-unmerged id is honored
        here and then cleanly REJECTED by update validation if its full schema is
        absent -- an in-band error the model can recover from, never a silent
        misfile."""
        if not field_id:
            return False
        if field_id in self._dti_extra_fields:
            return True
        schema = self._schema or {}
        if any(f.get("id") == field_id for f in schema.get("fields", [])):
            return True
        manifest_fields = ((schema.get("manifest") or {})
                           .get("current_section") or {}).get("fields") or []
        return any(mf.get("field_id") == field_id for mf in manifest_fields)

    def _build_tool_declarations(self):
        """Tool declarations for this session (a deepcopy so callers never mutate
        the shared settings list). In continuous-session mode (bd
        polyglot-pdf-x8rt) the switch_section tool is dropped: the whole form is
        one session, so there is nothing to switch to, and offering the tool would
        let a stray model call reset the session we are deliberately keeping open.
        """
        declarations = deepcopy(self._settings.TOOL_DECLARATIONS)
        if getattr(self._settings, "CONTINUOUS_SESSION", False):
            declarations = [d for d in declarations if d.get("name") != "switch_section"]
        # Deterministic spell-back tool (bd polyglot-pdf-22h1f): declared only
        # while the flag is on -- the tool lands dark and the cutover PR moves
        # it into TOOL_DECLARATIONS proper. Kept as a separate constant so the
        # default declared contract stays byte-identical with the flag off.
        if getattr(self._settings, "SPELLBACK_TOOL_ENABLED", False):
            declarations.append(deepcopy(self._settings.SPELLBACK_TOOL_DECLARATION))
        return declarations

    async def start_session(
        self,
        websocket: WebSocket,
        session_id: str,
        send_transcript: bool = False,
        *,
        accept_connection: bool = True,
        schema: Optional[Dict[str, Any]] = None,
        full_schema: Optional[Dict[str, Any]] = None,
        current_values: Optional[Dict[str, Any]] = None,
        system_instruction: Optional[str] = None,
        form_session_id: Optional[str] = None,
        kit_id: Optional[str] = None,
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
            full_schema: Full-form catalog for the secretary (bd polyglot-pdf-p68s);
                the whole form (all parts/sections/fields), distinct from the
                per-section `schema`. The client sends it on every handshake
                (including section switches), so it is normally non-None here. When
                None (an older client, or an internal restart that does not thread
                it), the previously-cached value is preserved rather than cleared.
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
        # Cache the full-form catalog for the secretary (bd polyglot-pdf-p68s).
        # Only overwrite when the caller supplies one: the INTERNAL section-switch
        # restart (_switch_to_section_locked -> start_session) does NOT thread
        # full_schema (the form is unchanged across sections), so preserving the
        # existing value keeps the secretary's catalog intact across that restart.
        # A client (re)connect handshake -- including a manual section switch, which
        # re-handshakes through websocket_routes -- always supplies it (or None for
        # a legacy client that predates this key).
        if full_schema is not None:
            self._full_schema = full_schema
        # Note: current_values are ignored by backend - client is source of truth

        # Reset the DTI validation extras on every (re)start, INCLUDING a section
        # switch (which calls start_session with the new section's schema). Otherwise
        # client-supplied field schemas from a PREVIOUS section would linger and let
        # the validator wrongly accept a stale cross-section field id (fresh-eyes
        # substitute review, Codex PR #229).
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
        # Kit identity + government EDITION for the audit trail (bd
        # polyglot-pdf-47r3). form_id alone identifies neither which KIT was used
        # (two kits can share a form number) nor which EDITION the client
        # confirmed against (agencies revise forms and enforce edition dates).
        # edition_date rides form_metadata like form_number; kit_id is not a
        # form_metadata key (it names the kit, not the form) so it arrives as an
        # argument. Both stored so _switch_to_section_locked can thread them into
        # the rebuilt CallbackHandler without re-deriving them.
        # A CUSTOM form (a firm's own intake sheet -- the firm-tier epic's case)
        # has no government edition date, so resolve_edition_marker falls back to
        # a fingerprint of the kit's field structure: not a date, but stable per
        # revision and changing when the form changes, which is what a disputed
        # filing needs. Prefer the FULL schema for the fingerprint -- the
        # per-section/JIT `schema` carries only one field, so hashing it would
        # yield a different marker per section of the same form.
        # PRESERVE both across the internal section-switch restart, exactly as
        # _full_schema does above (fresh-eyes on 47r3). _switch_to_section_locked
        # re-enters start_session with the NEW SECTION's schema and NO kit_id /
        # full_schema. Overwriting here reset kit_id to None and recomputed the
        # fingerprint from a single-field section schema -- the marker CHANGED
        # mid-session, the opposite of "pins a revision", and every confirmation
        # after section 1 lost its kit.
        #
        # The edition marker is computed ONLY on a client (re)connect -- the one
        # caller that supplies full_schema. Guarding merely on "not already set"
        # would NOT be enough: the section schema still yields a fingerprint from
        # its own single section, which would overwrite the session's real
        # whole-form marker. A reconnect recomputes from the same full schema and
        # so yields the same marker (pinned by
        # test_edition_marker_is_stable_across_a_reconnect).
        #
        # A session that never receives a full_schema (a pre-p68s client) keeps
        # edition_date None rather than pinning a section-derived digest --
        # deliberate: "not recorded" is honest, a one-section fingerprint
        # masquerading as the form's revision is not (bd polyglot-pdf-n41r).
        if kit_id is not None:
            self._kit_id = kit_id
        if full_schema is not None:
            # Look for the government edition in the per-section schema FIRST
            # (where a 47r3-aware client puts it via the handshake key), then in
            # full_schema (bd polyglot-pdf-kdrz). A currently-deployed pre-47r3
            # client sends no top-level edition_date but DOES send full_schema
            # with the real "12/2024" inside -- reading only the former threw
            # away an agency edition we were handed and recorded a fingerprint
            # instead, which is strictly weaker evidence. The fingerprint stays
            # the last resort, for kits that genuinely have no edition.
            # Both reads are isinstance-guarded: a malformed payload whose
            # form_metadata is a string/list would otherwise raise AttributeError
            # inside .get() and kill the WS session. websocket_routes only
            # validates that full_schema itself is a dict, never the nested key.
            def _declared_edition(source: dict | None) -> str | None:
                metadata = source.get("form_metadata") if isinstance(source, dict) else None
                value = metadata.get("edition_date") if isinstance(metadata, dict) else None
                return value if isinstance(value, str) and value.strip() else None

            declared_edition = _declared_edition(schema) or _declared_edition(full_schema)
            self._edition_date = _resolve_edition_marker(declared_edition, full_schema)
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
            # The PRESERVED values (self._*), not the local args: on the internal
            # section-switch restart the args are None, and passing them would
            # rebuild the handler without the kit/edition the session started
            # with -- same reason form_session_id is threaded from self.
            kit_id=self._kit_id,
            edition_date=self._edition_date,
        )

        # Inject tool handler methods into callback handler
        self._callback_handler.set_tool_handlers(
            handle_update_fields=self.handle_update_fields_tool_call,
            handle_switch_section=self.handle_switch_section,
            request_form_state_from_client=self.request_form_state_from_client,
            merge_field_schema=self.merge_field_schema,
            handle_ask_secretary=self.handle_ask_secretary,
            # Live getter so fields 2..N's guidance carries the CURRENT fill language
            # even after a mid-session change_fill_language (bd polyglot-pdf-uogm).
            get_fill_language=lambda: self._fill_language,
            # Live getter so every injected guidance block re-anchors the SPOKEN
            # language ("Speak <lang> aloud") -- long non-English sessions drifted
            # into English with only the session-start anchor (bd polyglot-pdf-ghv4).
            get_spoken_language=lambda: self._spoken_language,
            # Live getter so confirm_field can coerce onto the current field when the
            # model confirms a hallucinated/drifted id (bd polyglot-pdf-h1bn).
            get_current_field_id=lambda: self._current_field_id,
            # Gate confirm coercion on the SERVICE's injected USE_DTI (not the global
            # singleton) so it is symmetric with the update-side coercion even when the
            # service is built with a non-global Settings (Codex PR #264).
            get_use_dti=lambda: getattr(self._settings, "USE_DTI", False),
            # Gates the name_spellback dispatch (bd 22h1f): same injected-
            # settings source as the declaration builder, so a session whose
            # declarations omitted the tool also refuses a hallucinated call.
            get_spellback_enabled=lambda: getattr(
                self._settings, "SPELLBACK_TOOL_ENABLED", False),
            # Invalidate the current-field pointer on a successful confirm so a later
            # update can't be coerced onto the just-confirmed field if next-field
            # delivery times out (Codex PR #264).
            clear_current_field=self._clear_current_field_id,
            # Resolvable ids are authoritative -- only an unknown id is coerced
            # (bd polyglot-pdf-8vy3; symmetric with the update-side gate).
            is_known_field=self._is_known_field_id,
            # Live getter so fields 2..N's guidance carries the session-language
            # option labels once the background translation lands (bd
            # polyglot-pdf-ow1e). Empty dict -> render falls back to English.
            get_option_label_overrides=lambda: self._option_translations,
            # Same live-getter contract for field spoken names (bd tupu.2).
            get_spoken_name_overrides=lambda: self._spoken_name_translations,
        )

        # Runtime option-label translation (bd polyglot-pdf-ow1e): fire the
        # background build now -- _spoken_language is already seeded pre-connect
        # from the handshake (bd y25o) and _full_schema was cached above. Never
        # blocks the session; failure/slow paths leave English labels.
        self._maybe_start_option_translation(form_id)

        # Use web form tool declarations (stateless)
        tool_declarations = self._build_tool_declarations()

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

            # ASR language bias (bd polyglot-pdf-y25o): derive the BCP-47 hint
            # from the session's spoken language (set from the handshake BEFORE
            # this runs -- the Live config is per-connect) so the adapter can
            # bias input/output transcription toward the chosen language.
            try:
                self._live_ai.set_transcription_language_codes(
                    bcp47_codes_for_spoken_language(self._spoken_language)
                )
            except AttributeError:
                # Adapter (or a test double) without the setter: no bias.
                pass

            # Register callbacks with Gemini Live AI
            # System instruction is passed from caller and included in the initial
            # Gemini connection config.
            # on_user_activity now routes through the callback handler so a real user
            # turn ALSO emits the agent_processing (thinking-indicator) signal (bd
            # polyglot-pdf-wpw.5); the WS-route liveness bump is chained as the inner
            # callback.
            self._callback_handler.set_user_activity_inner(self._on_user_activity)
            # The largest per-field inline guidance injection this form can
            # produce (clamped help.details, bd wsao.8) -- the compression
            # window derivation must leave room for it or a details-bearing
            # initiating message 1007s at session assemble (wsao.2 finding).
            # full_schema (the secretary catalog) sees every field; the DTI
            # minimal schema may not.
            injection_budget = guidance_contract.inline_injection_budget_tokens(
                self._full_schema or self._schema or {})
            try:
                self._live_ai.set_callbacks(
                    on_form_update=self._callback_handler.on_form_update,
                    on_transcript=self._callback_handler.on_transcript,
                    on_audio=self._callback_handler.on_audio,
                    on_tool_call=self._callback_handler.on_tool_call,
                    on_go_away=self._callback_handler.on_go_away,
                    on_interrupted=self._callback_handler.on_interrupted,
                    on_session_dropped=self._callback_handler.on_session_dropped,
                    on_user_activity=self._callback_handler.on_user_activity,
                    on_processing_done=self._callback_handler.on_processing_done,
                    system_instruction=system_instruction,
                    tool_declarations=tool_declarations,
                    enable_transcripts=bool(send_transcript),
                    injection_budget_tokens=injection_budget,
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

    async def send_manual_field_update(self, field_id: str, field_name: str, value: Any,
                                       next_field_hint: Optional[str] = None,
                                       next_field_schema: Optional[Dict[str, Any]] = None):
        """Notify Gemini of manual field update. Delegates to AudioHandler."""
        # A manual edit is auto-confirmed by the frontend, so the field the DTI
        # current-field pointer names is now DONE. Invalidate the pointer (Codex PR
        # #264 P0): otherwise the next spoken answer -- which is for the field
        # next_field_hint points at, NOT this manually-edited one -- would be coerced
        # by update_form_fields onto the just-edited+confirmed field, overwriting it.
        self._current_field_id = None
        # Re-establish the pointer for the NEXT field (bd polyglot-pdf-ezg2): a
        # manual edit does not trigger the confirm_field next-field-hint round-trip
        # (the usual merge_field_schema carrier), so without this the pointer strands
        # at None and the immediately-following voice answer is neither coerced nor
        # (if the field was never merged) accepted. The client sends the next field's
        # schema alongside the hint; merge it exactly like the confirm path does --
        # this both re-points the coercion and adds the field to the validation pool.
        if (getattr(self._settings, "USE_DTI", False)
                and isinstance(next_field_schema, dict) and next_field_schema.get("id")):
            self.merge_field_schema(next_field_schema)
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
        """Send activity_end signal. Delegates to AudioHandler.

        Also emits the thinking-indicator processing-start (bd polyglot-pdf-wpw.5):
        in manual / push-to-talk VAD the client sends vad_activity_end when the user
        stops, which is the RELIABLE turn-end boundary in that mode (native VAD instead
        rides on_user_activity / input_transcription). The first response audio clears
        it. Guarded so a missing handler is a no-op.

        ORDER MATTERS (Codex PR #273): emit processing-start BEFORE awaiting the
        activity_end send. That await yields to the receive loop, so on a fast reply
        the first audio could run on_audio's clear while _processing_active is still
        False (clear skipped) and THEN this would set it True after the reply already
        began -- leaving the indicator stuck on. Setting it first makes the
        start-then-first-audio-clear ordering correct regardless of reply speed.
        """
        if self._callback_handler is not None:
            await self._callback_handler.signal_processing_start()
        if self._audio_handler:
            await self._audio_handler.send_activity_end()

    async def clear_processing_state(self) -> None:
        """Reset the thinking-indicator processing state (bd polyglot-pdf-wpw.5).
        Called when the client's max-duration safety timer fires (the reply never
        arrived): keeps backend and client in sync so the next turn's
        processing:true is not deduped against a stale True. No-op without a handler.
        """
        if self._callback_handler is not None:
            await self._callback_handler.on_processing_done()

    async def send_disclaimer_message(
        self, spoken_language: str, disclaimer_text: str,
        agree_button_label: Optional[str] = None,
    ):
        """
        Send disclaimer initiating message to Gemini.

        This is triggered when user first selects a language. Gemini will read
        the disclaimer aloud in the selected language.

        Args:
            spoken_language: Language for Gemini to speak (e.g., "Spanish", "French")
            disclaimer_text: The full translated disclaimer text to read verbatim
            agree_button_label: The TRANSLATED on-screen agree-button label the
                client displays (bd polyglot-pdf-s863) so the model names the
                button the user actually sees; falls back to 'I Agree' when the
                client omits it (old clients)
        """
        if not self._live_ai:
            _log.warning("send_disclaimer_message_no_ai", session_id=self._session_id)
            return

        message = self._settings.DISCLAIMER_INITIATING_MESSAGE.format(
            spoken_language=spoken_language,
            disclaimer_text=disclaimer_text,
            agree_button_label=agree_button_label or "I Agree",
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

    def _maybe_start_option_translation(self, form_id: str) -> None:
        """Fire the background option-label translation task (bd polyglot-pdf-ow1e).

        Skips entirely when: the flag is off; the session language is unset,
        English, or not code-backed (labels are already English / nothing to
        pin); no text model is wired; or there is no schema to read labels from.
        SESSION-START ONLY -- mid-session language changes are not a supported
        flow (maintainer 2026-07-16); see the note in send_initiating_message.
        An internal section-switch restart re-enters here with the same form +
        language and dedupes onto the process-level cached build.
        """
        if not getattr(self._settings, "RUNTIME_OPTION_TRANSLATION_ENABLED", False):
            return
        language = self._spoken_language
        if not language or language.strip().lower() == "english":
            return
        if not bcp47_codes_for_spoken_language(language):
            return
        if self._text_ai is None:
            return
        schema = self._full_schema or self._schema
        if not schema:
            return
        # Cache-key form id: prefer the form_number of the schema the labels are
        # actually collected from (the full-form catalog). The passed-in form_id
        # comes from the PER-SECTION schema; since bd polyglot-pdf-n0em the
        # manifest-first handshake DOES carry form_metadata.form_number, so it
        # normally resolves correctly -- but an older client omitting the key
        # still yields "unknown", and two different forms must never share a
        # cache entry, so the full-schema number stays the preferred source.
        translation_form_id = (
            (schema.get("form_metadata") or {}).get("form_number") or form_id
        )
        # An internal restart (section switch) re-enters here while an earlier
        # awaiter may still be in flight -- cancel it so the reference we are
        # about to overwrite never becomes an unjoinable orphan (fresh-eyes,
        # this PR). Cancelling the awaiter never cancels the SHARED build
        # (get_option_label_overrides shields it); the replacement task awaits
        # the same cached build.
        if (self._option_translation_task is not None
                and not self._option_translation_task.done()):
            self._option_translation_task.cancel()
        self._option_translation_task = asyncio.create_task(
            self._run_option_translation(translation_form_id, schema, language)
        )

    async def _run_option_translation(
        self, form_id: str, schema: Dict[str, Any], language: str
    ) -> None:
        """Await the (process-cached) translation build and publish the result
        (bd tupu.2: option labels + field spoken names + section labels in one
        build). Fail-open by construction: get_translation_overrides returns
        EMPTY_OVERRIDES on any failure/timeout, and this wrapper never lets an
        exception escape the task -- the session simply keeps English text."""
        try:
            overrides = await get_translation_overrides(
                form_id, schema, language, self._text_ai
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 -- belt-and-suspenders fail-open
            _log.warning("option_translation_task_error",
                         session_id=self._session_id,
                         exc_type=type(exc).__name__)
            return
        if overrides:
            self._option_translations = overrides.option_labels
            self._spoken_name_translations = overrides.spoken_names
            self._section_label_translations = overrides.section_labels
            _log.info("option_translation_applied",
                      session_id=self._session_id,
                      language=language,
                      override_count=len(overrides.option_labels),
                      spoken_name_count=len(overrides.spoken_names),
                      section_label_count=len(overrides.section_labels))

    async def send_initiating_message(
        self,
        spoken_language: str,
        next_field_hint: str,
        force_resume: bool = False,
    ):
        """
        Send initiating message to Gemini to prompt conversation in specific language.

        Triggered on a RECONNECT/section switch -- the client's opener re-asserting
        the session's PINNED spoken language on a fresh Gemini session. It is NOT a
        language switch: mid-conversation switching is unsupported (bd
        polyglot-pdf-87a9, docs/standards/voice-and-vad.md).
        Uses session.send_client_content() to initiate Gemini's response.

        Args:
            spoken_language: Language for Gemini to speak (e.g., "Spanish", "French")
            next_field_hint: Next unfilled field hint (e.g., "firstName (First Name)")
            force_resume: When True, use RESUME_INITIATING_MESSAGE regardless of
                _is_resume_session (bd polyglot-pdf-bhem). restart_gemini_session
                passes this after a Level-3 farewell reconnect: the ORIGINAL
                connection may have been a fresh (non-resume) start, so
                _is_resume_session alone would pick the greeting template and
                re-greet the user after a restart they didn't initiate. Does not
                touch _is_resume_session itself, which build_form_context_message
                also reads (as is_reconnect) to gate the SI's RESUME override note
                -- that is a separate concern from this bead's scope.
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return

        # Store spoken language for section switching (persists across sections).
        # This is an idempotent re-write under current policy: the spoken language
        # is PINNED per session (bd polyglot-pdf-87a9,
        # docs/standards/voice-and-vad.md), and the only caller of this path is the
        # client's reconnect opener re-asserting the SAME pinned language -- so
        # option-label translation correctly builds once, at session start
        # (bd polyglot-pdf-ow1e). Changing language means a NEW session, which
        # rebuilds the overrides from scratch.
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
        # this same opener fires on a mid-form RECONNECT (where the current field is
        # field N, not the handshake's field 1), and on a full-section
        # handshake schema["fields"][0] is merely the positional first field, not the
        # client's computeNextField selection (Codex PR #254). The id is NOT stripped
        # here: this block is CONTEXT the model acts on (and copies the id verbatim
        # from), not text to read aloud. If the id cannot be resolved to a known
        # field schema, render NOTHING rather than a wrong field. Non-DTI modes leave
        # it empty so legacy/JIT output is unchanged (their SI still carries field data).
        current_field_guidance = ""
        # Give the translation build a short, bounded head start (bd tupu.2):
        # the greeting + field-1 guidance render RIGHT NOW, and the async build
        # publishing a moment later left field 1 English (observed live: the
        # greeting spoke the English section title). With the kits fully baked
        # the build is kit-covered and resolves in milliseconds -- await it up
        # to 2s and fail open (English + the SI translate-yourself rule) on a
        # slow/failed build, preserving the never-blocks contract.
        task = self._option_translation_task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except Exception:  # noqa: BLE001 -- fail-open (TimeoutError included;
                # CancelledError still propagates: BaseException, not Exception)
                pass

        # Reset BEFORE resolution so an unresolved-field call never echoes a
        # stale value into the hint_translated log (fresh-eyes, this PR).
        self._hint_translated = False
        section_metadata_block = ""
        if getattr(self._settings, "USE_DTI", False):
            field = self._resolve_hint_field_schema(next_field_hint)
            if field:
                # Track the current field for update_form_fields coercion (bd
                # polyglot-pdf-h1bn): this opener fires at session/section start
                # (field 1) and on a mid-form RECONNECT (field N); in every case
                # `field` is the field the model is about to fill.
                if field.get("id"):
                    self._current_field_id = field["id"]
                # fill_language rides the field render (bd polyglot-pdf-uogm) so the
                # model writes VALUES in the configured language; the static SI no
                # longer carries it.
                current_field_guidance = (
                    "\n\nCURRENT FIELD (copy this field_id verbatim; do NOT read it aloud):\n"
                    + render_field_guidance(
                        field, fill_language=self._fill_language,
                        # Session-language option labels when the background
                        # translation has landed (bd polyglot-pdf-ow1e); empty
                        # -> None -> English labels, byte-identical render.
                        option_label_overrides=self._option_translations or None,
                        # Session-language field name (bd tupu.2), same contract.
                        spoken_name_overrides=self._spoken_name_translations or None,
                    )
                )
                # Session-language hint (bd tupu.2): the frontend-built hint
                # embeds the ENGLISH field name in quotes; substitute the
                # translated spoken name so the templated ask does not leak
                # English into a non-English greeting. Quoted-name-only
                # replacement -- a miss leaves the hint untouched.
                if self._spoken_name_translations:
                    _en_name = field.get("name") or ""
                    _translated = self._spoken_name_translations.get(
                        field.get("spoken_name") or _en_name)
                    if _en_name and _translated and f"'{_en_name}'" in spoken_hint:
                        # First occurrence only (parity with _translate_hint):
                        # free-form instruction text later in the hint may echo
                        # the field's own quoted name and must not be touched.
                        spoken_hint = spoken_hint.replace(
                            f"'{_en_name}'", f"'{_translated}'", 1)
                        self._hint_translated = True

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
            # Continuous-session mode (bd polyglot-pdf-x8rt): the whole form is one
            # session with no sections to navigate, so suppress the "Section N of M"
            # progress line -- telling the model it is on "section 1 of 8" with no
            # switch_section tool is confusing. Keep the form title + previous-names
            # (still useful context); only the section counters are dropped.
            continuous = getattr(self._settings, "CONTINUOUS_SESSION", False)
            block = render_section_metadata(
                form_title=form_title,
                section_number=None if continuous else sm.get("section_number"),
                total_sections=None if continuous else sm.get("total_sections"),
                section_label=None if continuous else sm.get("section_label"),
                previous_spoken_names=sm.get("previous_spoken_names"),
                # Session-language section label + completed-field names
                # (bd tupu.2); empty -> None -> English, byte-identical.
                section_label_overrides=self._section_label_translations or None,
                spoken_name_overrides=self._spoken_name_translations or None,
            )
            if block:
                section_metadata_block = "\n\n" + block

        # On mid-section reconnects use the resume template so Gemini skips
        # the greeting and section re-introduction (bd polyglot-pdf-vmxx).
        # force_resume overrides _is_resume_session for restart_gemini_session's
        # Level-3-farewell restart, where the ORIGINAL connection may have been a
        # fresh (non-resume) start (bd polyglot-pdf-bhem).
        use_resume_template = force_resume or self._is_resume_session
        template = (
            self._settings.RESUME_INITIATING_MESSAGE
            if use_resume_template
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
                 is_resume=use_resume_template,
                 message_length=len(message),
                 # Observability only (bd tupu.2): did the quoted-name hint
                 # substitution fire? Boolean, never the text (no-PII).
                 hint_translated=getattr(self, "_hint_translated", None),
                 spoken_name_override_count=len(self._spoken_name_translations))

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
        tool_declarations = self._build_tool_declarations()

        # Re-register the same callbacks used at session creation
        # (form_filling_service.py:155). set_callbacks is synchronous -- do not
        # await it. on_transcript is always passed; whether transcripts are
        # actually emitted is gated by enable_transcripts. on_user_activity routes
        # through the callback handler so the agent_processing signal (bd
        # polyglot-pdf-wpw.5) survives a session restart too.
        self._callback_handler.set_user_activity_inner(self._on_user_activity)
        self._live_ai.set_callbacks(
            on_form_update=self._callback_handler.on_form_update,
            on_transcript=self._callback_handler.on_transcript,
            on_audio=self._callback_handler.on_audio,
            on_tool_call=self._callback_handler.on_tool_call,
            on_go_away=self._callback_handler.on_go_away,
            on_interrupted=self._callback_handler.on_interrupted,
            on_session_dropped=self._callback_handler.on_session_dropped,
            on_user_activity=self._callback_handler.on_user_activity,
            on_processing_done=self._callback_handler.on_processing_done,
            system_instruction=system_instruction,
            tool_declarations=tool_declarations,
            enable_transcripts=bool(self._send_transcript),
            # Re-thread the inline-details window budget on RESTART too (bd
            # wsao.8 fresh-eyes): set_callbacks resets the adapter's budget,
            # so omitting it here re-derived the compression window WITHOUT
            # details headroom and a reconnect whose current field carries
            # large help.details 1007'd at assemble -- the exact wsao.2
            # failure, back on the routine reconnect path.
            injection_budget_tokens=guidance_contract.inline_injection_budget_tokens(
                self._full_schema or self._schema or {}),
        )

        # Verify session is now active
        is_active_after = self._live_ai.is_session_active()
        _log.info("gemini_session_restarted",
                 session_id=self._session_id,
                 session_active_after=is_active_after)

        # DTI: the rebuilt SI is fully static (epic polyglot-pdf-13w7), so unlike the
        # legacy full-SI it carries NO field data -- after a restart (e.g. Level-3
        # farewell reconnect) the model would have no current-field guidance and no
        # form/section metadata until the next confirm. Fire the initiating message
        # so the current field's guidance + the metadata block reach Gemini, exactly
        # as the section-switch and session-start paths do (bd polyglot-pdf-h1bn,
        # closing the gap the fu1h audit flagged). send_initiating_message resolves the
        # field from the hint's id; with no hint it falls back gracefully (renders no
        # guidance block rather than a wrong field). force_resume=True always selects
        # the RESUME template here (bd polyglot-pdf-bhem): a restart is always a
        # continuation from the user's perspective, even when the ORIGINAL connection
        # was a fresh (non-resume) start and _is_resume_session is still False --
        # without this, that case would re-greet the user after the restart. Non-DTI
        # restarts are unaffected (block empty).
        if getattr(self._settings, "USE_DTI", False):
            try:
                await self.send_initiating_message(
                    self._spoken_language,
                    next_field_hint or "the first unfilled field",
                    force_resume=True,
                )
            except Exception as exc:
                _log.error("restart_gemini_session_initiating_message_failed",
                          session_id=self._session_id, error=str(exc))

    async def change_fill_language(self, new_language: str):
        """
        Change the language used for filling form field values mid-session.

        Updates self._fill_language, then prompts Gemini to acknowledge the
        change to the user. In DTI mode the per-turn field-guidance render
        reads the live value (see callback_handler -- bd polyglot-pdf-uogm),
        so subsequent turns pick up the new language without a reset. In
        legacy mode (USE_DTI=false) the active session keeps its original
        system instruction, so the new language reliably applies only from the
        next section switch or reconnect.

        Args:
            new_language: The new language to use (e.g., "Spanish", "French", "Japanese")
        """
        if self._live_ai is None:
            # No-op when live AI is not configured (used in unit tests)
            return

        old_language = self._fill_language
        self._fill_language = new_language

        _log.info("change_fill_language",
                 old_language=old_language,
                 new_language=new_language,
                 session_id=self._session_id)

        acknowledgment_prompt = f"Acknowledge the language change to {new_language} naturally to the user."
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
        await self._cancel_secretary_deliver_tasks()
        # Cancel this session's option-translation awaiter (bd polyglot-pdf-ow1e).
        # The underlying per-process build is shielded, so it keeps running and
        # later sessions still hit the cache; only THIS session's publish stops.
        if (self._option_translation_task is not None
                and not self._option_translation_task.done()):
            self._option_translation_task.cancel()
            try:
                await self._option_translation_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._live_ai is not None:
            await self._live_ai.finalize()
        self._websocket = None
        self._session_id = None

    async def _cancel_secretary_deliver_tasks(self) -> None:
        """Cancel + drain all in-flight async secretary-deliver tasks (bd
        polyglot-pdf-jnjj.43).

        Called before ANY session teardown/swap that finalizes the live model --
        end_session (disconnect) AND _switch_to_section_locked (section switch) --
        so a late secretary answer from the OUTGOING session can never push a turn
        into a torn-down or freshly-swapped session. Without this on the switch
        path, a slow section-N lookup could deliver into section N+1
        (cross-section PHI contamination, fresh-eyes finding).

        Cancel the LOOKUP first and drain it HERE: this coroutine has no pending
        cancel of its own, so the await actually unwinds the inner wait_for task --
        doing it inside the (cancelled) deliver task does not, which would leak
        "Task was destroyed but it is pending". Then cancel + drain the deliver.
        Snapshot the set first: the deliver done-callback mutates it.
        """
        for deliver, lookup in list(self._secretary_deliver_tasks):
            if not lookup.done():
                lookup.cancel()
                try:
                    await lookup
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            if not deliver.done():
                deliver.cancel()
                try:
                    await deliver
                except (asyncio.CancelledError, Exception):
                    pass

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

        # 0. Kill any in-flight secretary-deliver task from the OUTGOING section
        # (bd polyglot-pdf-jnjj.43, fresh-eyes): a slow section-N lookup must not
        # deliver its (section-N PHI) answer into the section-N+1 session we are
        # about to start -- send_client_content would queue it and fire it into the
        # new section once it is ready. Cancel BEFORE finalize, same as end_session.
        await self._cancel_secretary_deliver_tasks()

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
        self, session_id: str, updates: Dict[str, Any], multi_field_call: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Apply updates from the AI for web sessions (validation only, no persistence).

        Delegates to ValidationHandler for field matching and validation.

        multi_field_call: True when the CALLER (CallbackHandler) collapsed a
        multi-field tool call to its first key before this call -- coercion is then
        SKIPPED (the collapsed first value may belong to a different field; let it be
        rejected, don't re-point it onto the current field). Codex PR #264 P0.
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
        # field + a single-field (non-collapsed) update; non-DTI / multi-field /
        # matching-id paths are untouched.
        updates = self._coerce_dti_update_to_current_field(updates, multi_field_call=multi_field_call)

        # Build field list on-demand from schema for validation
        # Values are not persisted - this is just for acknowledgment
        fields = self._build_fields_from_schema()

        # Use ValidationHandler to match and validate fields. In DTI mode ids are
        # EXACT-ONLY (strict_ids): the protocol has the model copy ids verbatim,
        # the pool holds only 1-2 fields, and unresolvable ids are already handled
        # by the coercion gate above -- letting the validator's fuzzy name-match
        # run here would silently re-point a mismatched id onto whatever is in
        # the tiny pool (the PR #251 mis-fill trap; Codex PR #321).
        validator = ValidationHandler(session_id=session_id)
        return validator.validate_field_updates(
            fields, updates,
            strict_ids=getattr(self._settings, "USE_DTI", False),
            # Lets the rejection log name a real SIBLING id (the oaiv diagnostic)
            # while redacting anything else -- a rejected key is raw model input
            # and can carry the user's answer on an arg swap (Codex PR #264 P0).
            # Session-wide on purpose: `fields` here is the tiny active pool, so
            # a pool-scoped check would redact the very case this surfaces.
            is_known_field=self._is_known_field_id)

    def _coerce_dti_update_to_current_field(
        self, updates: Dict[str, Any], multi_field_call: bool = False
    ) -> Dict[str, Any]:
        """Re-point a single DTI update onto the current field when the model's id
        does not match it (bd polyglot-pdf-h1bn). Returns updates unchanged outside
        the gated case. See handle_update_fields_tool_call for the rationale."""
        if not getattr(self._settings, "USE_DTI", False):
            return updates
        current = self._current_field_id
        if not current:
            return updates
        # One-field-per-turn invariant. The caller (CallbackHandler) COLLAPSES a
        # multi-field tool call to its first key BEFORE we see it, so len(updates) is
        # always 1 here -- we cannot detect "the model sent several fields" ourselves
        # (Codex PR #264 P0). The caller passes multi_field_call=True in that case; do
        # NOT coerce then, or the collapsed first value (which may belong to a
        # different field) would be silently re-pointed onto the current field,
        # corrupting it. Leave it to be rejected as the caller intended.
        if multi_field_call or len(updates) != 1:
            return updates
        sent_id, value = next(iter(updates.items()))
        if sent_id == current:
            return updates  # normal path -- model named the right field
        # A RESOLVABLE id is AUTHORITATIVE (bd polyglot-pdf-8vy3, live-run evidence
        # 2026-07-05): the model legitimately targets a PREVIOUS field when the user
        # corrects it after its confirm already advanced the pointer -- the blanket
        # coercion re-pointed those corrections onto the CURRENT field, silently
        # corrupting it (a 30q continuous run misfiled 5 fields this way while the
        # model's ids were right every single time). So only an id that resolves to
        # NO known field -- the jnjj.46 hallucination mode -- is re-pointed.
        if self._is_known_field_id(sent_id):
            return updates
        # Log ONLY the schema-validated target id (current); NEVER sent_id -- it is raw
        # model input and can carry the user's answer if the model swaps args (Codex
        # PR #264 P0, no-PII policy). "coerced=True" + the real id is enough signal.
        _log.info("dti_update_coerced_to_current_field",
                  session_id=self._session_id, current_field_id=current)
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

    async def handle_ask_secretary(
        self, query: str, deliver_late: bool = True
    ) -> Dict[str, Any]:
        """Run an ask_secretary lookup (bd polyglot-pdf-jnjj.45c, tail guard jnjj.43).

        Assembles the secretary's context -- the form catalog (self._full_schema,
        the full-form catalog the client supplies at handshake; bd polyglot-pdf-p68s
        / jnjj.45d) plus the client's CURRENT values + applicability (a fresh
        round-trip) -- and runs the BLOCKING TextAIGemini.ask().

        deliver_late (default True): when a lookup blows SECRETARY_DEADLINE_S it is
        detached to deliver its answer on a LATER turn (the user asked a question;
        the answer is worth voicing whenever it lands). For an INTERNAL query where
        no user question is pending -- switch_to_field's field-resolution
        (bd polyglot-pdf-y76q) -- pass deliver_late=False: a deadline-blown lookup
        is drained (never leaked) but its result is DISCARDED, never voiced as a
        spurious "answer to your earlier question" turn. The caller degrades to its
        own in-turn fallback on the returned "pending".

        Returns a status dict the dispatch maps to a tool response:
          {"status": "ok",  "answer": <prose>, "sources": [...], "resolved": bool}
              -- answered within the deadline. `sources` is the resolved
              {field_id, spoken_name} list (bd polyglot-pdf-2af7/3vby) the answer was
              grounded in -- lets the voice model hand an EXACT id to switch_to_field
              for navigation. `resolved` is False when the secretary deliberately
              could not identify a requested navigation target (semantic pushback,
              bd polyglot-pdf-y76q); True otherwise.
          {"status": "pending", "answer": "", "sources": []}       -- the lookup blew
              SECRETARY_DEADLINE_S; it has been DETACHED to deliver its answer on a
              later turn (see _deliver_secretary_answer_later). The principal must NOT
              keep its turn open waiting; the gap-based thinking indicator (bd wpw.5)
              covers the wait visually -- no spoken filler turn is spent.
          {"status": "failed",  "answer": "", "sources": []}       -- no adapter / no
              schema / the client form-state round-trip errored; fail-open (the
              dispatch voices an apology).

        Tail-latency design (jnjj.43): Gate 2 (jnjj.27) measured median ~1s but spikes
        to 8.5s / 20s. The synchronous tool call only waits SECRETARY_DEADLINE_S
        (~2.5s); past that the model's turn is freed and the answer is delivered
        asynchronously. SECRETARY_TIMEOUT_S is the HARD CAP on the model call itself
        (sync wait + detached lookup both bounded by it).

        PII: logs ids/counts/latency/status only -- never the query, the values, or
        the answer (callback_handler PII discipline).
        """
        if self._text_ai is None:
            _log.warning("ask_secretary_no_text_ai", session_id=self._session_id)
            return {"status": "failed", "answer": "", "sources": []}

        # Prefer the full-form catalog the client supplies at handshake (bd
        # polyglot-pdf-p68s): the secretary must see the WHOLE form, not just the
        # current section. Fall back to the per-section self._schema for a legacy
        # client that did not send full_schema, so the handler still answers about
        # the visible section rather than failing outright.
        schema = self._full_schema or self._schema or {}
        if not schema.get("fields"):
            _log.warning("ask_secretary_no_schema", session_id=self._session_id)
            return {"status": "failed", "answer": "", "sources": []}

        # Fresh full form state from the client (all fields). Shape:
        # {field_id: {"value": ..., "confirmed": ..., ["shown": bool]}} -- the
        # renderers read the value out of that wrapper directly; `shown` (added by
        # jnjj.45d) feeds the shown_map (default True until then).
        try:
            form_state = await self.request_form_state_from_client(None)
        except Exception as exc:  # noqa: BLE001
            _log.warning("ask_secretary_form_state_error",
                         exc_type=type(exc).__name__, session_id=self._session_id)
            return {"status": "failed", "answer": "", "sources": []}
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

        deadline_s = getattr(self._settings, "SECRETARY_DEADLINE_S", 2.5)
        timeout_s = getattr(self._settings, "SECRETARY_TIMEOUT_S", 8.0)
        # The lookup runs as ONE task bounded by the HARD cap; we race it against the
        # shorter sync deadline. If the deadline wins, we DETACH the same task (no
        # second call -- never double-bill the model) to deliver the answer later.
        lookup = asyncio.ensure_future(
            asyncio.wait_for(self._text_ai.ask(query, context), timeout=timeout_s)
        )
        # If THIS handler is cancelled during the sync wait (e.g. a WS disconnect in
        # the ~2.5s window -> end_session -> finalize -> receive-task cancel), the
        # lookup is not yet tracked in _secretary_deliver_tasks (that only happens in
        # the deadline-blown branch below). asyncio.wait does NOT cancel its futures
        # when the waiter is cancelled, so without this the lookup would orphan -- a
        # billable model call running past teardown + a "Task was destroyed" leak
        # (Opus fallback review, PR #269). Cancel + drain it, then propagate.
        try:
            done, _pending = await asyncio.wait({lookup}, timeout=deadline_s)
        except asyncio.CancelledError:
            if not lookup.done():
                lookup.cancel()
                try:
                    await lookup
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            raise

        if lookup in done:
            # Resolved within the deadline -- the common path.
            try:
                answer, sources, resolved = lookup.result()
            except asyncio.TimeoutError:
                _log.warning("ask_secretary_timeout", timeout_s=timeout_s,
                             session_id=self._session_id)
                return {"status": "failed", "answer": "", "sources": []}
            except Exception as exc:  # noqa: BLE001
                _log.warning("ask_secretary_ask_error",
                             exc_type=type(exc).__name__, session_id=self._session_id)
                return {"status": "failed", "answer": "", "sources": []}
            _log.info(
                "ask_secretary_complete",
                field_count=len(form_state),
                shown_count=len(shown_map),
                answer_len=len(answer or ""),
                source_count=len(sources) if isinstance(sources, list) else 0,
                resolved=resolved,
                session_id=self._session_id,
            )
            # Treat an all-whitespace answer as empty (the model occasionally returns
            # blanks) so the dispatch fail-opens instead of voicing whitespace.
            if not (answer or "").strip():
                return {"status": "failed", "answer": "", "sources": []}
            # `resolved` False = the secretary deliberately could not identify a
            # navigation target (semantic pushback, bd polyglot-pdf-y76q); it rides
            # the ok dict so the switch handler can degrade to a clarify prompt.
            return {"status": "ok", "answer": answer,
                    "sources": sources or [], "resolved": bool(resolved)}

        # Deadline blown. For an INTERNAL query (deliver_late=False, e.g.
        # switch_to_field's field resolution) there is no user question waiting, so
        # do NOT voice a late answer -- just DRAIN the still-running lookup so it
        # neither leaks (a billable call past the turn / "Task was destroyed") nor
        # surfaces as a spurious follow-up turn (bd polyglot-pdf-y76q). The caller
        # degrades to its own in-turn fallback on this "pending".
        if not deliver_late:
            _log.info("ask_secretary_pending_no_deliver",
                      deadline_s=deadline_s, field_count=len(form_state),
                      session_id=self._session_id)
            drain = asyncio.ensure_future(self._drain_secretary_lookup(lookup))
            # Register as a (drain, lookup) PAIR so teardown handles it exactly like
            # a deliver pair (cancel + drain both) -- _cancel_secretary_deliver_tasks
            # unpacks pairs. The drain self-removes the pair on finish.
            entry = (drain, lookup)
            self._secretary_deliver_tasks.add(entry)
            drain.add_done_callback(
                lambda _t: self._secretary_deliver_tasks.discard(entry))
            return {"status": "pending", "answer": "", "sources": []}

        # DETACH the still-running lookup to deliver its answer asynchronously
        # (jnjj.43). Track a strong ref so it isn't GC'd mid-flight; the deliver
        # coroutine self-removes on finish.
        _log.info("ask_secretary_pending_async_deliver",
                  deadline_s=deadline_s, field_count=len(form_state),
                  session_id=self._session_id)
        deliver = asyncio.ensure_future(
            self._deliver_secretary_answer_later(lookup, len(form_state), len(shown_map))
        )
        # Track the (deliver, lookup) PAIR: end_session cancels BOTH, and cancels the
        # lookup directly (not via the deliver) so the lookup task is drained from a
        # context with no pending cancellation of its own -- cancelling a task that is
        # itself awaiting another does not reliably drain the inner task ("Task was
        # destroyed but it is pending"). The deliver self-removes the pair on finish.
        entry = (deliver, lookup)
        self._secretary_deliver_tasks.add(entry)
        deliver.add_done_callback(lambda _t: self._secretary_deliver_tasks.discard(entry))
        return {"status": "pending", "answer": "", "sources": []}

    async def _deliver_secretary_answer_later(
        self, lookup: "asyncio.Future", field_count: int, shown_count: int
    ) -> None:
        """Await a detached secretary lookup and DELIVER its answer on a follow-up
        turn (bd polyglot-pdf-jnjj.43).

        The synchronous ask_secretary tool returned "pending" because the lookup
        blew SECRETARY_DEADLINE_S. The lookup task is still running (bounded by the
        SECRETARY_TIMEOUT_S hard cap inside it). When it lands, push the answer to
        the live model via send_client_content so the principal voices it -- the
        delayed answer arrives as its own turn. The gap-based wpw.5 thinking
        indicator is shown until that turn's first audio arrives.

        Drop silently (no push) when: the lookup errors / times out / returns empty,
        or the live session is no longer active (the user disconnected or moved on).
        A failed late lookup does NOT get an apology turn -- the user has already
        been waiting; injecting "sorry I couldn't" out of nowhere is worse than
        letting it go. PII: never log the answer text; counts/status only.
        """
        try:
            answer, _sources, _resolved = await lookup
        except asyncio.TimeoutError:
            _log.warning("ask_secretary_async_timeout", session_id=self._session_id)
            return
        except asyncio.CancelledError:
            # A teardown/swap cancelled us via _cancel_secretary_deliver_tasks (called
            # from BOTH end_session and _switch_to_section_locked). That helper also
            # cancels + drains the underlying lookup directly, so we just propagate.
            raise
        except Exception as exc:  # noqa: BLE001
            _log.warning("ask_secretary_async_error",
                         exc_type=type(exc).__name__, session_id=self._session_id)
            return

        if not (answer or "").strip():
            _log.info("ask_secretary_async_empty", session_id=self._session_id)
            return

        # Only deliver into a LIVE session. If the model session is gone (disconnect,
        # section-switch teardown, farewell), pushing would error or leak into a dead
        # loop -- drop it.
        if self._live_ai is None or not self._live_ai.is_session_active():
            _log.info("ask_secretary_async_dropped_session_inactive",
                     session_id=self._session_id)
            return

        # The delivery instruction the principal acts on. The answer is the
        # secretary's prose (PHI inside the Gemini trust boundary, like every turn);
        # NEVER logged. Tell the model this is the now-ready answer to the user's
        # earlier question so it voices it naturally rather than treating it as a new
        # user utterance.
        message = (
            "SECRETARY RESULT (now ready): the answer to the user's earlier question "
            "is: " + str(answer) + " -- share this with the user naturally now, as a "
            "follow-up to what they asked a moment ago."
        )
        try:
            await self._live_ai.send_client_content(message)
            _log.info(
                "ask_secretary_async_delivered",
                field_count=field_count,
                shown_count=shown_count,
                answer_len=len(answer or ""),
                session_id=self._session_id,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("ask_secretary_async_deliver_failed",
                         exc_type=type(exc).__name__, session_id=self._session_id)

    async def _drain_secretary_lookup(self, lookup: "asyncio.Future") -> None:
        """Await a detached secretary lookup purely to drain it (bd
        polyglot-pdf-y76q), DISCARDING its result. Used for an internal
        (deliver_late=False) query -- switch_to_field's field resolution -- that
        blew the deadline: the switch already degraded in-turn, so the late result
        must NOT be voiced. Awaiting here (not inside a cancelled task) lets the
        inner wait_for unwind cleanly rather than leaking "Task was destroyed".
        Never raises; never voices anything."""
        try:
            await lookup
        except (asyncio.CancelledError, asyncio.TimeoutError):
            return
        except Exception as exc:  # noqa: BLE001
            _log.warning("ask_secretary_drain_failed",
                         exc_type=type(exc).__name__, session_id=self._session_id)

    async def handle_validation_boundary(self, fields: list) -> dict:
        """B5 (bd polyglot-pdf-jnjj.17): run the cheap-model contradiction validator
        at a section/form boundary (the B4 events carry the contract-2 `fields`
        payload), and -- on a SURVIVING conflict -- inject a steering directive into
        the Live session so the voice model sends the user back to verify.

        Returns the SURVIVING contract-1 verdict ({"conflicts": [...]}, POST-
        suppression). The caller pushes it to the client as the `validation_result`
        envelope; the client gates the section switch on it (a conflict holds the
        section, an empty list resumes) and sets per-field `steered` markers from the
        conflicts it receives (the marker is client-owned -- the backend is stateless,
        contract 2). A SUPPRESSED conflict is omitted (returned as clean): no steer
        fires for it AND the switch must proceed -- its fields are already steered
        client-side, so nothing is lost, and returning it would trap a user who used
        the override escape hatch (the inline note at the return below has the full
        rationale).

        Max-resteer bound (contract 3, invariant 2): a conflict referencing an
        already-`steered: true` field (PER-FIELD: any of its field_ids steered) is
        dropped from the STEER -- the user already adjudicated that field once. The
        marker rides IN the payload from the client, so the stateless backend reads
        it rather than remembering.

        Fail-OPEN (contract 6): ValidatorService.validate is fail-open; a dead Live
        session drops the steer. Never blocks the boundary. PII: logs counts only --
        never values / reasons (the reason rides the in-band steer, which is NOT a
        log sink).
        """
        if self._text_ai is None:
            # No validator wired (unit/form-only paths) -- all-clear, no steer.
            return {"conflicts": []}

        safe_fields = fields if isinstance(fields, list) else []
        conflicts = await self._validate_one_window(safe_fields)

        surviving = self._suppress_already_steered(conflicts, safe_fields)
        # Only return conflicts whose STEER ACTUALLY REACHED the Live session. If the
        # steer is dropped (dead session) or fails to deliver, returning the conflict
        # would make the client hold the section with NO voiced guidance -- the same
        # trap as a suppressed conflict (Codex PR #275). A steered conflict holds the
        # section (the model will voice it); an un-delivered one reads as clean so the
        # switch proceeds unchecked (fail-OPEN). Suppressed conflicts (already
        # adjudicated) are never in `surviving`, so they too read as clean.
        delivered = await self._inject_validator_steer(surviving, safe_fields) if surviving else []
        return {"conflicts": delivered}

    async def _validate_one_window(self, window_fields: list) -> list:
        """Run the cheap-model contradiction check over ONE window's contract-2
        field list and return its raw conflicts (contract-1, PRE-suppression).

        Fail-OPEN per window (contract 6): a timeout / error / bad shape yields an
        EMPTY conflict list -- one dead window never blocks the others or the
        boundary. The per-window hard bound is VALIDATOR_TIMEOUT_SEC. PII: logs
        exc type only, never values.
        """
        safe_fields = window_fields if isinstance(window_fields, list) else []
        try:
            verdict = await asyncio.wait_for(
                ValidatorService(self._text_ai).validate(safe_fields),
                timeout=self._settings.VALIDATOR_TIMEOUT_SEC,
            )
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001 -- fail-OPEN
            _log.warning("validator_window_fail_open",
                         exc_type=type(exc).__name__, session_id=self._session_id)
            return []
        return verdict.get("conflicts", []) if isinstance(verdict, dict) else []

    async def handle_validation_windows(self, windows: list) -> dict:
        """W1 (bd polyglot-pdf-xbl2) + W3 (bd polyglot-pdf-pr3i): the ASYNC,
        multi-window validator boundary. REPORT-ONLY since W3.

        Called from a BACKGROUND task (asyncio.create_task) spawned off the WS
        receive loop -- NOTHING in the voice/tool path awaits it. Runs one
        flash-lite call PER WINDOW concurrently (bounded by
        VALIDATOR_MAX_CONCURRENT_WINDOWS, each with its own fail-open +
        VALIDATOR_TIMEOUT_SEC), DEDUPES conflicts across the whole batch by their
        field-id SET (overlapping windows -- size ~20, stride ~10 -- make the same
        conflicting pair appear in multiple windows; the duplication is structural,
        not exceptional), suppresses the already-steered markers, and returns the
        surviving contract-1 conflicts for the caller to push as the
        `validation_result` envelope.

        W3 report-cadence revision: this method NO LONGER injects the steer. The
        client OWNS the finding queue (stateless-backend invariant + it owns the
        steered-marker + W4 re-arm lifecycle): a `validation_result` carrying
        surviving conflicts is a CANDIDATE list the client enqueues, and the client
        drains it via a `drain_findings` round-trip that composes+injects the steer
        (handle_drain_findings). A CLEAN result (no surviving conflict) enqueues
        nothing, so no voice turn is spent on an all-clear. See
        docs/standards/validation-delegation.md + the sprint-12 plan.

        `windows` is a list of contract-2 field lists (each list is one window).
        The steered-marker suppression + the returned conflicts operate over the
        UNION of every window's fields (a field's `steered` flag rides its entry in
        whatever window(s) contain it; the client owns the marker).

        Fail-OPEN throughout (contract 6): a bad `windows` shape, a dead window, or
        no text-ai wired all reduce to an empty verdict; the background task's own
        exception guard lives at the call site so a raise here can never crash the
        receive loop. PII: logs counts only, never values.
        """
        if self._text_ai is None:
            return {"conflicts": []}

        safe_windows = [w for w in windows if isinstance(w, list)] if isinstance(windows, list) else []
        if not safe_windows:
            return {"conflicts": []}

        # Bound the concurrent flash-lite fan-out; windows past the cap queue.
        sem = asyncio.Semaphore(
            max(1, int(self._settings.VALIDATOR_MAX_CONCURRENT_WINDOWS))
        )

        async def _run(window_fields: list) -> list:
            async with sem:
                return await self._validate_one_window(window_fields)

        per_window = await asyncio.gather(
            *(_run(w) for w in safe_windows), return_exceptions=True
        )

        # Flatten, discarding any window that raised (gather with
        # return_exceptions surfaces the raise as a value -- fail-open per window).
        all_conflicts: list = []
        for result in per_window:
            if isinstance(result, list):
                all_conflicts.extend(result)

        deduped = self._dedupe_conflicts_by_field_set(all_conflicts)

        # The union of every window's fields carries the steered markers + the
        # id->name map for the steer. A field can appear in more than one window;
        # last-wins on collision is fine (windows carry the same value for a field).
        union_fields = self._union_window_fields(safe_windows)

        surviving = self._suppress_already_steered(deduped, union_fields)
        _log.info(
            "validator_windows_complete",
            window_count=len(safe_windows),
            raw_conflict_count=len(all_conflicts),
            deduped_conflict_count=len(deduped),
            surviving_conflict_count=len(surviving),
            session_id=self._session_id,
        )
        # W3: REPORT-ONLY. Return the surviving conflicts for the client to ENQUEUE;
        # the steer is injected later on the client-driven drain_findings round-trip
        # (handle_drain_findings), never here. A field's `name` rides each conflict's
        # entry so the client can compose the drain payload without re-deriving it;
        # attach it from the union fields (id -> name).
        name_by_id = {
            f.get("field_id"): f.get("name")
            for f in union_fields
            if isinstance(f, dict) and f.get("field_id")
        }
        reported = []
        for c in surviving:
            if not isinstance(c, dict):
                continue
            ids = c.get("field_ids", [])
            reported.append({
                "field_ids": ids,
                "reason": c.get("reason", ""),
                # id -> name map for just this conflict's fields, so the client's
                # drain_findings payload carries the names the steer composer needs.
                "field_names": {i: name_by_id.get(i) for i in ids if isinstance(i, str)},
            })
        return {"conflicts": reported}

    async def handle_form_complete_pro(self, fields: list) -> dict:
        """W6 (bd polyglot-pdf-gbus): the WHOLE-FORM gemini-2.5-pro contradiction
        pass at form_complete -- the SOLE end-of-form report. It catches cross-page
        (far-pair) contradictions the ~20-field lite windows cannot see (W5 measured
        recall 1.000). REPORT-ONLY, like the lite windows: it returns the surviving
        conflicts (each with a field_names rider) for the client to ENQUEUE and drain
        via the same finding-driven path (validation_result -> validatorFindingsQueue
        -> drain_findings); it does NOT inject a steer.

        Runs one whole-form pro call with WHOLE_FORM_PRO_SI (the far-pair rule + the
        g1c anti-hedging block + the W6 anti-over-flag items for the Part 5/6
        certification block and bracketed-repeat fields -- the precision condition
        W5 attached to the GO). The pass is FED the already-steered field ids so it
        does not re-report an adjudicated contradiction, and its conflicts are then
        DEDUPED against those same steered markers (_suppress_already_steered) -- the
        authoritative "not re-flagged" guarantee (exit criterion 2). Prompt-layer +
        dedupe-layer both key on the steered markers riding the contract-2 payload.

        Fail-OPEN + off the receive loop: no pro wired (flag off) -> {"conflicts":[]}
        no-op; a timeout (VALIDATOR_PRO_TIMEOUT_SEC) or any error returns clean, never
        blocks form_complete. The spawn at the call site runs it as a background task.
        PII: logs counts only.
        """
        if self._text_ai_pro is None:
            # Pro pass disabled (FORM_COMPLETE_PRO_VALIDATOR off) -- clean no-op.
            return {"conflicts": []}

        safe_fields = fields if isinstance(fields, list) else []
        if not safe_fields:
            return {"conflicts": []}

        steered_ids = [
            f.get("field_id")
            for f in safe_fields
            if isinstance(f, dict) and f.get("steered") and f.get("field_id")
        ]
        try:
            verdict = await asyncio.wait_for(
                ValidatorService(self._text_ai_pro).validate(
                    safe_fields, si=WHOLE_FORM_PRO_SI, steered_field_ids=steered_ids
                ),
                timeout=self._settings.VALIDATOR_PRO_TIMEOUT_SEC,
            )
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001 -- fail-OPEN
            _log.warning("validator_pro_fail_open",
                         exc_type=type(exc).__name__, session_id=self._session_id)
            return {"conflicts": []}
        conflicts = verdict.get("conflicts", []) if isinstance(verdict, dict) else []

        # DEDUPE against already-steered fields -- the authoritative not-re-flag
        # guarantee (belt to the prompt's suspenders). Reuses the same per-field
        # suppression the lite path uses; the steered markers ride the payload.
        surviving = self._suppress_already_steered(conflicts, safe_fields)

        name_by_id = {
            f.get("field_id"): f.get("name")
            for f in safe_fields
            if isinstance(f, dict) and f.get("field_id")
        }
        reported = []
        for c in surviving:
            if not isinstance(c, dict):
                continue
            ids = c.get("field_ids", [])
            reported.append({
                "field_ids": ids,
                "reason": c.get("reason", ""),
                "field_names": {i: name_by_id.get(i) for i in ids if isinstance(i, str)},
            })
        _log.info(
            "validator_pro_complete",
            field_count=len(safe_fields),
            raw_conflict_count=len(conflicts),
            reported_conflict_count=len(reported),
            session_id=self._session_id,
        )
        return {"conflicts": reported}

    async def handle_drain_findings(self, conflicts: list) -> dict:
        """W3 (bd polyglot-pdf-pr3i): the FINDING-DRIVEN drain. The client sends this
        (drain_findings) the moment its `validatorFindingsQueue` is non-empty --
        carrying the queued conflicts it wants voiced -- and this composes ONE steer
        via the SHIPPED oiok composer (_compose_validator_steer -- navigate/
        read-back/correct, one finding at a time) and injects it into the Live
        session. Returns the DELIVERED conflicts (contract-1 shape) so the client
        marks those fields `steered` and consumes them from the queue; an
        un-delivered steer (dead session / send failed) returns [] so the client
        keeps the finding queued to retry on a later drain (fail-OPEN, never blocks).

        Each conflict carries `field_ids`, `reason`, and a `field_names` id->name map
        (attached by handle_validation_windows so the client need not re-derive it);
        the composer's `fields` arg is reconstructed from those maps. PII: logs counts
        only; the reason/names ride the in-band steer, never a log sink (contract 6).
        """
        safe_conflicts = [c for c in conflicts if isinstance(c, dict)] if isinstance(conflicts, list) else []
        # Reconstruct the composer's `fields` list (id -> name) from every conflict's
        # field_names map. The composer only reads field_id + name, so this minimal
        # projection is sufficient; a missing name falls back to the id in the steer.
        fields: list = []
        seen_ids: set = set()
        for c in safe_conflicts:
            names = c.get("field_names", {}) if isinstance(c.get("field_names"), dict) else {}
            for fid in c.get("field_ids", []):
                if not isinstance(fid, str) or fid in seen_ids:
                    continue
                seen_ids.add(fid)
                fields.append({"field_id": fid, "name": names.get(fid) or fid})
        # Normalize to the {field_ids, reason} shape the composer/inject path expects
        # (drop the client-only field_names rider).
        steer_conflicts = [
            {"field_ids": c.get("field_ids", []), "reason": c.get("reason", "")}
            for c in safe_conflicts
            if c.get("field_ids")
        ]
        _log.info(
            "drain_findings_received",
            conflict_count=len(steer_conflicts),
            session_id=self._session_id,
        )
        if not steer_conflicts:
            return {"conflicts": []}
        delivered = await self._inject_validator_steer(steer_conflicts, fields)
        return {"conflicts": delivered}

    @staticmethod
    def _union_window_fields(windows: list) -> list:
        """Union every window's contract-2 field entries into one de-duplicated list
        (by field_id), preserving first-seen order. Overlapping windows repeat a
        field; the suppression + steer-compose helpers want each field once. A field
        marked steered in ANY window is treated as steered (the OR is the safe side:
        it only suppresses re-steering an already-adjudicated field)."""
        by_id: dict = {}
        for window in windows:
            if not isinstance(window, list):
                continue
            for f in window:
                if not isinstance(f, dict):
                    continue
                fid = f.get("field_id")
                if not fid:
                    continue
                existing = by_id.get(fid)
                if existing is None:
                    by_id[fid] = dict(f)
                elif f.get("steered"):
                    # Preserve a steered:true seen in any window (OR semantics).
                    existing["steered"] = True
        return list(by_id.values())

    @staticmethod
    def _dedupe_conflicts_by_field_set(conflicts: list) -> list:
        """W1: collapse conflicts that name the SAME set of field_ids to a single
        entry (overlapping windows make one real contradiction surface once per
        window that spans it). Keys on the FROZENSET of field_ids so order does not
        matter ('A,B' == 'B,A'). First occurrence wins (keeps its reason). Malformed
        entries (no field_ids) are dropped -- they cannot be suppressed or steered."""
        seen: set = set()
        out: list = []
        for c in conflicts:
            if not isinstance(c, dict):
                continue
            ids = c.get("field_ids", [])
            if not isinstance(ids, list) or not ids:
                continue
            key = frozenset(str(i) for i in ids)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    @staticmethod
    def _suppress_already_steered(conflicts: list, fields: list) -> list:
        """Drop any conflict that (a) references an already-steered field (contract 3,
        invariant 2 -- PER-FIELD suppression) OR (b) references a field NOT present in
        this boundary's payload (a hallucinated / misspelled id the client cannot mark
        steered, which would trap the user with no suppressible marker -- Codex PR
        #275). The `steered` flag rides in each contract-2 field entry; the client owns
        + persists it."""
        known_ids = {
            f.get("field_id")
            for f in fields
            if isinstance(f, dict) and f.get("field_id")
        }
        steered_ids = {
            f.get("field_id")
            for f in fields
            if isinstance(f, dict) and f.get("steered")
        }
        surviving = []
        for c in conflicts:
            ids = c.get("field_ids", []) if isinstance(c, dict) else []
            if not ids:
                continue  # malformed -> fail-open (drop)
            if any(fid not in known_ids for fid in ids):
                continue  # references a field not in this payload -> unsuppressible
            if any(fid in steered_ids for fid in ids):
                continue  # at least one field already adjudicated -> suppress
            surviving.append(c)
        return surviving

    async def _inject_validator_steer(self, conflicts: list, fields: list) -> list:
        """Compose + inject the steering directive for the surviving conflicts into
        the Live session as a text turn (contract 3). Only into a LIVE session --
        mirrors the secretary async-deliver guard. Returns the conflicts whose steer
        ACTUALLY DELIVERED (so the caller holds the section only when the model was
        told to voice the correction -- Codex PR #275); returns [] if the session is
        dead or the send failed. The reason MAY quote values; it is an in-band model
        instruction, never logged (contract 6)."""
        if self._live_ai is None or not self._live_ai.is_session_active():
            _log.info("validator_steer_dropped_session_inactive",
                      session_id=self._session_id)
            return []

        message = self._compose_validator_steer(conflicts, fields)
        try:
            # send_client_content returns True only if the turn actually reached the
            # live session (False if queued / no session / send raised). The adapter
            # SWALLOWS its own send exceptions (Opus PR #275), so the bool -- not a
            # raise -- is the real delivery signal. A steer that did not actually reach
            # the model must NOT hold the section (the user would be stuck with nothing
            # voiced), so treat not-delivered as no surviving conflict.
            delivered = await self._live_ai.send_client_content(message)
            if delivered:
                _log.info("validator_steer_delivered",
                          conflict_count=len(conflicts), session_id=self._session_id)
                return conflicts
            _log.info("validator_steer_not_delivered_fail_open",
                      conflict_count=len(conflicts), session_id=self._session_id)
            return []
        except Exception as exc:  # noqa: BLE001 -- a steer failure must never block
            _log.warning("validator_steer_deliver_failed",
                         exc_type=type(exc).__name__, session_id=self._session_id)
            return []

    @staticmethod
    def _compose_validator_steer(conflicts: list, fields: list) -> str:
        """Build the in-band steering instruction (contract 3). NAMES the fields
        with their field_ids (criterion 1) and carries the user-override escape
        hatch verbatim from the legacy in-SI ADDRESS CONSISTENCY prose
        (criterion 2) so B is never stricter than the prose it supplements -- a
        possible conflict, not a block.

        The correction RAIL (bd polyglot-pdf-oiok, sprint-11 D2): the steer
        instructs the model to NAVIGATE via switch_to_field -- whose response
        returns the field's current value for read-back and moves UI focus --
        rather than re-asking cold. Prompt-level by design: the model stays the
        actor; nothing client-side auto-navigates on a validation result. The
        rail is orthogonal to WHEN steers fire (today: form_complete in
        continuous mode; wt6w's page-end triggers reuse it unchanged)."""
        name_by_id = {
            f.get("field_id"): f.get("name")
            for f in fields
            if isinstance(f, dict)
        }
        lines = [
            "VALIDATOR FINDING (second-pass check): a possible conflict was found "
            "between fields the user already gave. This is NOT a block -- it is a "
            "prompt to double-check.",
        ]
        for c in conflicts:
            ids = c.get("field_ids", []) if isinstance(c, dict) else []
            labeled = [
                f"{name_by_id.get(i) or i} (field_id: '{i}')" for i in ids
            ]
            reason = str(c.get("reason", "")) if isinstance(c, dict) else ""
            named = " and ".join(labeled) if labeled else "the fields involved"
            lines.append(f"- Fields: {named}. {reason}")
        lines.append(
            "Handle one finding at a time: call switch_to_field with the first "
            "flagged field's field_id -- its response includes that field's "
            "current value. Read the value back to the user, explain the "
            "possible conflict in one sentence, and ask which is correct. If "
            "the user gives a correction, update the field and confirm it. "
            "Accept the user's answer if they confirm both are intentional -- "
            "do not insist or re-ask once they confirm. Then move to the next "
            "flagged field, if any."
        )
        return "\n".join(lines)

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

    def handle_skip_field_response(
        self, request_id: str, recorded: bool, reason: Optional[str] = None,
        section_complete: bool = False,
    ) -> None:
        """
        Handle skip_field_response message from frontend (bd polyglot-pdf-7yra).

        Delegates to RequestCoordinator -- completes the synchronous skip_field
        round-trip.

        Args:
            request_id: ID matching the original skip_field request.
            recorded: True if the frontend recorded the skip (markFieldSkipped).
            reason: Fixed category token when not recorded; never a field value.
            section_complete: True when the skip completed the section; the skip
                handler then skips the racing next-field-hint request.
        """
        if not self._request_coordinator:
            _log.warning("handle_skip_field_response_no_coordinator", session_id=self._session_id)
            return

        self._request_coordinator.handle_skip_field_response(
            request_id, recorded, reason, section_complete)

    def handle_switch_field_response(
        self, request_id: str, payload: Dict[str, Any]
    ) -> None:
        """
        Handle switch_field_response from the frontend (bd polyglot-pdf-jnjj.36).

        Delegates to RequestCoordinator -- completes the synchronous
        switch_field (field-level navigation) round-trip with the frontend's
        whole ack payload.
        """
        if not self._request_coordinator:
            _log.warning("handle_switch_field_response_no_coordinator", session_id=self._session_id)
            return

        self._request_coordinator.handle_switch_field_response(request_id, payload)

    def handle_spellback_response(
        self, request_id: str, payload: Dict[str, Any]
    ) -> None:
        """
        Handle spellback_response from the frontend (bd polyglot-pdf-22h1f).

        Delegates to RequestCoordinator -- completes the deterministic
        spell-back round-trip with the frontend's ack payload (status +
        reason/timing; never a field value).
        """
        if not self._request_coordinator:
            _log.warning("handle_spellback_response_no_coordinator", session_id=self._session_id)
            return

        self._request_coordinator.handle_spellback_response(request_id, payload)

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

        DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
        continuous-DTI is the live flow. Kept as a fallback, not deleted.
        Do not extend.

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

        DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
        continuous-DTI is the live flow. Kept as a fallback, not deleted.
        Do not extend.

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

    # NOTE: the complete_section tool/handler was removed. Section completion is
    # auto-detected by the frontend (handleConfirmFieldRequest) when all fields
    # are confirmed, which then triggers a section switch via manual_section_switch.


# Note: factory for FormFillingService lives in backend.dependencies to avoid
# circular imports. The service implementation should remain importable without
# pulling in FastAPI dependency providers.
