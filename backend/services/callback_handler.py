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
from backend.services.ai_context import render_field_guidance
from backend.utils.dev_file_logger import get_dev_logger
from backend.utils.confirmation_logger import log_field_confirmation

_log = structlog.get_logger().bind(module="callback_handler")
_dev_log = get_dev_logger()

# Consecutive wholly-unknown update_form_fields rejections at which the tool
# response escalates to an explicit stop-retrying instruction
# (bd polyglot-pdf-b1gj; a live session looped 338 rejected updates).
UNKNOWN_REJECTION_LOOP_THRESHOLD = 3


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
        kit_id: Optional[str] = None,
        edition_date: Optional[str] = None,
        firm_id: Optional[str] = None,
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
            kit_id: Kit identifier (e.g., "w7") -- the UNIQUE kit key, since two
                kits can share a form_id (bd polyglot-pdf-47r3)
            firm_id: The customer FIRM this session runs under, from the staff
                token's firm_id claim (bd polyglot-pdf-xwlt). None when no firm
                claim rode the session; identifies the firm, never the client.
            edition_date: The form's government edition (e.g., "12/2024"), so the
                audit record names which edition was confirmed against
        """
        self._websocket = websocket
        self._session_id = session_id
        self._request_coordinator = request_coordinator
        self._send_transcript = send_transcript
        self._ws_audio_chunk_count = 0
        # "Agent processing" (thinking-indicator) signal state (bd polyglot-pdf-wpw.5).
        # True from a real user turn (on_user_activity, which fires in BOTH native and
        # manual VAD on input transcription) until the agent's FIRST response audio of
        # that turn -- the processing gap the frontend shows a calm indicator for.
        # Backend-driven so it works in native-VAD mode too, where the client has no
        # turn-end signal of its own. _ws_audio_chunk_count is session-cumulative, so
        # this flag (not the count) marks "first audio AFTER a start" as the clear edge.
        self._processing_active = False
        self._form_id = form_id  # For confirmation logging
        self._form_session_id = form_session_id  # For confirmation logging
        self._kit_id = kit_id  # Audit trail: which KIT (bd polyglot-pdf-47r3)
        self._edition_date = edition_date  # Audit trail: which EDITION
        self._firm_id = firm_id  # Telemetry: which FIRM (bd polyglot-pdf-xwlt)
        # Confirmed-field count for the session-end record (bd
        # polyglot-pdf-xwlt). Incremented at the ONE place a confirmation is
        # known to have actually taken -- the same `recorded` guard that gates
        # log_field_confirmation -- so the count can never exceed the events.
        self._confirmed_count = 0
        
        # Service methods will be injected
        self._handle_update_fields = None
        self._handle_switch_section = None
        self._request_form_state_from_client = None
        self._merge_field_schema = None
        # Secretary (bd polyglot-pdf-jnjj.45c): async handler that runs the
        # ask_secretary lookup. Injected by FormFillingService; None until then.
        self._handle_ask_secretary = None
        # Liveness callback chained from on_user_activity (bd polyglot-pdf-wpw.5):
        # on_user_activity now ALSO emits the processing-start signal, so it owns the
        # adapter's user-activity hook and calls this inner callback (the WS-route
        # idle-watchdog bump) through. None until injected.
        self._on_user_activity_inner = None
        # Live getter for the current fill language (bd polyglot-pdf-uogm): a getter,
        # not a snapshot, so a mid-session change_fill_language is reflected in the
        # next field's guidance without a second source of truth to go stale.
        self._get_fill_language = None
        # Live getter for the current SPOKEN language (bd polyglot-pdf-ghv4): rides
        # a "Speak <lang> aloud" segment on every injected guidance block so the
        # conversation language is re-anchored per turn, not only at session start.
        self._get_spoken_language = None
        # Live getter for the session-language option-label overrides (bd
        # polyglot-pdf-ow1e): a getter, not a snapshot, because the background
        # translation task publishes them AFTER session start -- renders before
        # that see an empty dict and fall back to English labels.
        self._get_option_label_overrides = None
        # Same live-getter contract for field spoken-name overrides (bd tupu.2).
        self._get_spoken_name_overrides = None
        # Live getter for the current field id (bd polyglot-pdf-h1bn): so confirm_field
        # can be coerced onto the current field when the model confirms a hallucinated /
        # drifted id (mirrors the update_form_fields coercion). Getter, not snapshot.
        self._get_current_field_id = None
        # Live getter for USE_DTI from the SERVICE's settings (bd polyglot-pdf-h1bn,
        # Codex PR #264): the confirm gate must read the same injected settings the
        # update-side coercion uses (self._settings.USE_DTI), NOT the global
        # get_settings() singleton -- a harness/test that builds the service with a
        # non-global Settings(USE_DTI=True) would otherwise coerce updates but not
        # confirms, stranding the field.
        self._get_use_dti = None
        # Live getter for SPELLBACK_TOOL_ENABLED (bd 22h1f) -- see
        # set_tool_handlers. None/absent reads as disabled (fail closed).
        self._get_spellback_enabled = None
        # Invalidates the service's current-field pointer (bd polyglot-pdf-h1bn, Codex
        # PR #264): on a successful confirm the current field is DONE, so the pointer is
        # cleared until fresh next-field guidance is delivered. Otherwise, if the
        # next-field hint/schema times out, a later update_form_fields would be coerced
        # onto the JUST-CONFIRMED field, overwriting it. merge_field_schema re-sets the
        # pointer when the new field's schema arrives.
        self._clear_current_field = None
        # Resolver for "does this id name a field the session has seen?" -- gates
        # the confirm-side coercion (known ids are authoritative, bd 8vy3).
        self._is_known_field = None
        # Consecutive update_form_fields calls rejected wholly as unknown-field
        # (bd polyglot-pdf-b1gj): a model stuck targeting an inactive/invented id
        # retried 338 times in one live session. Reset on any applied update or
        # a plain validation error (those are working paths); at
        # UNKNOWN_REJECTION_LOOP_THRESHOLD the tool response escalates to a
        # stop-retrying instruction.
        self._consecutive_unknown_rejections = 0

    def set_tool_handlers(
        self,
        handle_update_fields,
        handle_switch_section,
        request_form_state_from_client,
        merge_field_schema=None,
        handle_ask_secretary=None,
        get_fill_language=None,
        get_spoken_language=None,
        get_current_field_id=None,
        get_use_dti=None,
        clear_current_field=None,
        is_known_field=None,
        get_option_label_overrides=None,
        get_spoken_name_overrides=None,
        get_spellback_enabled=None,
    ):
        """Inject tool handler methods from FormFillingService."""
        self._handle_update_fields = handle_update_fields
        self._handle_switch_section = handle_switch_section
        self._request_form_state_from_client = request_form_state_from_client
        self._merge_field_schema = merge_field_schema
        self._handle_ask_secretary = handle_ask_secretary
        self._get_fill_language = get_fill_language
        self._get_spoken_language = get_spoken_language
        self._get_option_label_overrides = get_option_label_overrides
        self._get_spoken_name_overrides = get_spoken_name_overrides
        self._get_current_field_id = get_current_field_id
        self._get_use_dti = get_use_dti
        self._clear_current_field = clear_current_field
        self._is_known_field = is_known_field
        # Live getter for SPELLBACK_TOOL_ENABLED from the SERVICE's settings
        # (bd 22h1f; same injected-settings principle as _get_use_dti). Gates
        # the name_spellback dispatch: the declaration is flag-gated, but a
        # hallucinated call while dark must be a fast in-band refusal, not a
        # full round-trip (mic hold + receive-loop block + a PII value POSTed
        # to a 503 route) -- Opus cross-surface review, bd polyglot-pdf-dtywl.
        self._get_spellback_enabled = get_spellback_enabled

    def _option_overrides(self):
        """The current session-language option-label overrides, or None (bd
        polyglot-pdf-ow1e). None/empty keeps render_field_guidance byte-identical
        to the pre-translation behavior (English labels)."""
        overrides = (self._get_option_label_overrides()
                     if self._get_option_label_overrides else None)
        return overrides or None

    def _spoken_overrides(self):
        """The current session-language spoken-name overrides, or None (bd
        tupu.2; same contract as _option_overrides)."""
        overrides = (self._get_spoken_name_overrides()
                     if self._get_spoken_name_overrides else None)
        return overrides or None

    def _translate_spoken(self, name):
        """A single spoken name in the session language; miss/None -> as-is.
        For the direct echo channels (switch success/candidates, secretary
        fields) that speak a field name without going through
        render_field_guidance (bd tupu.2)."""
        overrides = self._spoken_overrides()
        if overrides and isinstance(name, str):
            return overrides.get(name) or name
        return name

    def _translate_hint(self, hint, field_schema=None):
        """Substitute the quoted ENGLISH field name inside a next-field hint
        with the session-language spoken name (bd tupu.2). The hint is built by
        the frontend around field.name in single quotes; a translation miss or
        absent schema leaves the hint untouched."""
        overrides = self._spoken_overrides()
        if not (overrides and hint and isinstance(field_schema, dict)):
            return hint
        en_name = field_schema.get("name") or ""
        translated = overrides.get(field_schema.get("spoken_name") or en_name)
        if en_name and translated and f"'{en_name}'" in hint:
            # First occurrence only: the frontend embeds the quoted name once;
            # free-form instruction text later in the hint must not be touched.
            return hint.replace(f"'{en_name}'", f"'{translated}'", 1)
        return hint

    async def send_form_update(
        self,
        data: Optional[Dict[str, Any]],
        applied_fields: Optional[list] = None,
        request_hint: bool = False,
    ) -> Optional[str]:
        """
        Send form state update to frontend.

        Args:
            data: Form state data to send
            applied_fields: List of field IDs that were actually applied
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

        # turn_complete is a safety CLEAR for the processing indicator (bd
        # polyglot-pdf-wpw.5): the transcript arrives after all audio, so the agent
        # has finished -- if first-audio somehow did not clear it (e.g. a text-only
        # turn with no audio), clear it here so it can never stick on.
        await self._set_processing(False)

    def set_user_activity_inner(self, callback) -> None:
        """Inject the inner liveness callback that on_user_activity chains to (bd
        polyglot-pdf-wpw.5). The adapter's on_user_activity hook points at THIS
        handler's on_user_activity (which emits the processing-start signal); that
        method then calls this inner callback (the WS-route idle-watchdog bump)."""
        self._on_user_activity_inner = callback

    async def _set_processing(self, active: bool) -> None:
        """Emit the agent_processing signal to the client when it changes (bd
        polyglot-pdf-wpw.5). Dedups same-value calls. The client shows/hides a calm
        'thinking' indicator. PII-free: a bare boolean, no transcript/values."""
        if self._processing_active == active:
            return
        self._processing_active = active
        # `is not None`, not truthiness: a Starlette WebSocket (and a
        # MagicMock(spec=WebSocket)) is Mapping-like, so `if self._websocket:` is
        # False for an empty one (same trap as on_go_away).
        if self._websocket is not None:
            try:
                await self._websocket.send_json(
                    {"type": "agent_processing", "processing": active}
                )
            except Exception as e:
                _log.warning("failed_to_send_agent_processing",
                             error=str(e), active=active, session_id=self._session_id)

    async def on_processing_done(self) -> None:
        """The agent's turn ended (interrupt OR a real server turn_complete) -- clear
        the thinking indicator (bd polyglot-pdf-wpw.5). The fast clear is on_audio
        (first response chunk); this covers the no-audio turn-end cases that would
        otherwise leave _processing_active stuck True -- which also deduped the NEXT
        turn's processing:true (Codex PR #273). Idempotent (dedup), so calling it
        alongside on_audio on a normal turn is harmless."""
        await self._set_processing(False)

    async def signal_processing_start(self) -> None:
        """Emit processing-start WITHOUT the liveness chain (bd polyglot-pdf-wpw.5).
        Used by the manual/PTT path (send_activity_end), where the turn-end signal is
        the client's vad_activity_end and liveness is handled separately on that path.
        on_user_activity (native VAD) is the variant that ALSO bumps liveness."""
        await self._set_processing(True)

    async def on_user_activity(self) -> None:
        """A real user turn occurred (input transcription) -- the agent is now
        processing (bd polyglot-pdf-wpw.5). Emit processing-start, then chain to the
        injected liveness callback (the idle-watchdog bump). PII-free: no text crosses
        here (the adapter passes none).

        SCOPE (bd polyglot-pdf-fa4x): this fires on Gemini input_transcription, the
        native-VAD turn-start signal. In practice the gemini-live native-audio model
        emits NO input_transcription on Vertex, so in native VAD this currently does
        not fire and the indicator only works in manual/PTT mode (driven by
        signal_processing_start via send_activity_end). The native-VAD START signal is
        the fa4x follow-up. The CLEAR path (first response audio / turn_complete)
        already works in both modes."""
        await self._set_processing(True)
        if self._on_user_activity_inner is not None:
            try:
                res = self._on_user_activity_inner()
                if res is not None and hasattr(res, "__await__"):
                    await res
            except Exception:
                # Liveness must never crash the receive loop.
                _log.warning("on_user_activity_inner_error", session_id=self._session_id)

    async def on_audio(self, data: bytes) -> None:
        """
        Handle audio callback from Gemini.
        
        Forward raw audio bytes from Gemini to the connected websocket client.
        The client is expected to handle raw PCM audio playback.
        
        Args:
            data: Raw PCM audio bytes from Gemini
        """
        # First response audio of the turn -> the agent has started replying, so the
        # processing window is over (bd polyglot-pdf-wpw.5). _processing_active is the
        # per-turn edge (it was set True by on_user_activity and is cleared here on the
        # first chunk that follows); _set_processing dedups, so later chunks are no-ops.
        if self._processing_active:
            await self._set_processing(False)

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

    async def on_interrupted(self) -> None:
        """Forward a Gemini barge-in interruption to the client (bd polyglot-pdf-s7uf).

        Gemini stops generating the moment the user barges in, but the client
        schedules received audio on a session-lifetime playback cursor -- without
        this relay it keeps playing the dead generation's unplayed tail, which is
        why barge-in feels broken on auto-VAD. The client flushes its playback
        queues on this message. No payload: the event itself is the signal.
        Errors are swallowed so a send failure never crashes the session loop
        (same discipline as on_go_away).
        """
        # Identity check, not truthiness -- see on_go_away.
        if self._websocket is not None:
            try:
                await self._websocket.send_json({"type": "interrupted"})
            except Exception as e:
                _log.warning("websocket_interrupted_send_failed",
                             error=str(e), session_id=self._session_id)

    async def on_session_dropped(self) -> None:
        """Forward a spontaneous Gemini drop to the client (bd polyglot-pdf-ppfy).

        Unlike GoAway (a pre-close warning), this fires AFTER the Gemini session
        has already died unexpectedly (e.g. a 1011 "Input data processing failed").
        The client-facing WS is still open behind a now-dead Gemini, so without this
        relay the client freezes on "connected" and the user's audio is silently
        dropped. Relaying a distinct `gemini_session_dropped` message lets the client
        drive its existing reconnect path. The backend stores nothing (stateless
        invariant); errors are swallowed (the WS may already be closing from an idle
        timeout race) so a failed forward never crashes teardown -- same discipline
        as on_go_away.
        """
        if self._websocket is not None:
            try:
                await self._websocket.send_json({"type": "gemini_session_dropped"})
            except Exception as e:
                _log.warning("websocket_session_dropped_send_failed",
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
        
        # DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
        # continuous-DTI is the live flow. Kept as a fallback, not deleted.
        # Do not extend.
        if normalized == "switch_section":
            return await self._handle_switch_section_tool(arguments)

        # NOTE: no complete_section route -- that tool was removed; section
        # completion is auto-detected by the frontend when all fields confirm.

        if normalized == "confirm_field":
            return await self._handle_confirm_field_tool(arguments)

        if normalized == "skip_field":
            return await self._handle_skip_field_tool(arguments)

        if normalized == "name_spellback":
            return await self._handle_name_spellback_tool(arguments)

        if normalized == "switch_to_field":
            return await self._handle_switch_to_field_tool(arguments)

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
        
        # Execute update via service. Tell it whether this was a COLLAPSED multi-field
        # call (rejected_fields non-empty) so DTI coercion is skipped -- the collapsed
        # first value may belong to a different field and must NOT be re-pointed onto
        # the current field (Codex PR #264 P0).
        result = self._handle_update_fields(
            self._session_id, normalized_updates, multi_field_call=bool(rejected_fields)
        )
        
        if result is None:
            # Validation itself errored (exception inside validate_field_updates).
            # Report the keys as unknown THROUGH the same formatter as the normal
            # path so the model still gets an actionable message, and advance the
            # loop-breaker counter -- otherwise a repeated exception-path failure
            # could loop unbounded with a bare, message-less response
            # (bd polyglot-pdf-b1gj, Opus fresh-eyes finding 2).
            await self.send_form_update({}, [])
            self._consecutive_unknown_rejections += 1
            if self._consecutive_unknown_rejections >= UNKNOWN_REJECTION_LOOP_THRESHOLD:
                # Same telemetry signal as the normal path -- a runaway loop
                # through the exception path must not be invisible to cost
                # telemetry (Opus outer-review finding 2, bd polyglot-pdf-b1gj).
                _log.warning(
                    "unknown_field_loop_breaker_fired",
                    consecutive=self._consecutive_unknown_rejections,
                    session_id=self._session_id,
                )
            return self._build_update_fields_response(
                [],  # validation_errors
                list(normalized_updates.keys()),  # unknown_fields
                [],  # applied_fields
                None,
                known_inactive_fields=[
                    fid for fid in normalized_updates
                    if self._is_known_field and self._is_known_field(fid)
                ],
                consecutive_unknown_rejections=self._consecutive_unknown_rejections,
            )
        
        # Extract results
        validation_errors = result.get("validation_errors", [])
        unknown_fields = result.get("unknown_fields", [])
        applied_fields = result.get("applied_fields", [])

        # Split unknown ids into "real field, just not active" vs "no such field"
        # (bd polyglot-pdf-b1gj). In DTI mode the validation pool holds only the
        # current field, so a REAL field elsewhere in the form (a manifest-known
        # id the secretary handed back) is rejected as unknown; the recovery for
        # those is switch_to_field, and the response must say so or the model
        # retries the same rejected update indefinitely (338x in one live session).
        known_inactive_fields = [
            fid for fid in unknown_fields
            if self._is_known_field and self._is_known_field(fid)
        ]

        # Loop-breaker counter (bd polyglot-pdf-b1gj): a call rejected WHOLLY as
        # unknown-field advances the stuck counter; any applied field or a plain
        # validation error (a working path the model should keep retrying with a
        # corrected VALUE) resets it.
        if unknown_fields and not applied_fields:
            self._consecutive_unknown_rejections += 1
            if self._consecutive_unknown_rejections >= UNKNOWN_REJECTION_LOOP_THRESHOLD:
                _log.warning(
                    "unknown_field_loop_breaker_fired",
                    consecutive=self._consecutive_unknown_rejections,
                    session_id=self._session_id,
                )
        else:
            self._consecutive_unknown_rejections = 0

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
            await self.send_form_update(result.get("form_state"), applied_fields)
            _log.info("field_update_success", applied=len(applied_fields))
        else:
            # Validation failed - send empty form_state so frontend doesn't apply invalid values
            await self.send_form_update({}, [])

        # Echo the CANONICAL stored value back to the model (bd polyglot-pdf-h7wx):
        # form_state carries the post-normalization value (e.g. "A-12345678" ->
        # "12345678"), which is what the client actually stores. The model reads its
        # confirmation read-back from THIS echo instead of its own (possibly
        # compression-evicted) memory -- live sessions confirmed values that were
        # never in the field. Values go to the model only; never into _log.* calls.
        _form_state = result.get("form_state") or {}
        applied_values = {
            fid: _form_state[fid] for fid in applied_fields if fid in _form_state
        }

        # Build and return tool response (no next field info - reduces tokens)
        tool_response = self._build_update_fields_response(
            validation_errors,
            unknown_fields,
            applied_fields,
            None,  # No next_field_hint - send after confirmation
            rejected_count=len(rejected_fields),
            known_inactive_fields=known_inactive_fields,
            consecutive_unknown_rejections=self._consecutive_unknown_rejections,
            applied_values=applied_values,
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
        # Only ANSWERED fields are included; unanswered (value None/missing) are
        # omitted. Falsy answers are still answers -- a standalone checkbox stored
        # as False, a numeric 0, or an explicit empty string ("not applicable")
        # must stay visible to the model (bd polyglot-pdf-gihj).
        # Status: "confirmed" or "unconfirmed"
        # Example: "firstName:John:confirmed|lastName:Doe:unconfirmed"
        compact_lines = []
        for field_id, field_data in form_values.items():
            if isinstance(field_data, dict):
                value = field_data.get("value")

                # Skip unanswered fields (not in response = empty). Only None /
                # missing counts as unanswered -- never falsy values.
                if value is None:
                    continue

                confirmed = field_data.get("confirmed", False)
                status = "confirmed" if confirmed else "unconfirmed"

                compact_lines.append(f"{field_id}:{value}:{status}")
            else:
                # Legacy format (shouldn't happen but handle it)
                if field_data is not None:  # Only include if answered
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
        """Handle switch_section tool call.

        DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
        continuous-DTI is the live flow. Kept as a fallback, not deleted.
        Do not extend.
        """
        section_identifier = arguments.get("section_identifier", "") if isinstance(arguments, dict) else str(arguments)
        response = await self._handle_switch_section(section_identifier)
        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", tool="switch_section", 
                 success=response.get("success"), section=section_identifier)
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

        Fail-open with an APOLOGY, not a re-ask: if no handler is wired or the
        lookup yields nothing (timeout / error / empty), the tool returns an
        instruction telling the principal to APOLOGIZE for an internal error --
        NOT to repeat the user's question back at them (a bare "ask the user
        directly" makes the assistant echo "What WAS your previous last name?",
        which sounds like a knock-knock joke; maintainer 2026-06-27). The failure
        is also logged at ERROR level (PII-free) so a secretary outage is VISIBLE
        to us, not silently absorbed. Never surfaces an exception to the model.

        PII: log the query LENGTH + answer length only -- never the query text or
        the answer prose (both reach stdout -> Cloud Run logs).
        """
        query = arguments.get("query", "") if isinstance(arguments, dict) else ""

        # The fail-open instruction the principal voices: an apology for an
        # internal error, explicitly NOT a verbatim re-ask of the user's question.
        fallback = (
            "INTERNAL ERROR: the secretary lookup failed. Apologize to the user, in "
            "the user's language, for a technical problem and say you could not "
            "retrieve that information right now. Do NOT simply repeat their "
            "question back to them. You may offer to continue, or ask them to "
            "provide the information directly ONLY after acknowledging the error."
        )

        # The PENDING instruction when the lookup blew the deadline (bd jnjj.43): the
        # answer is being retrieved and WILL be delivered as a follow-up turn. Tell
        # the principal to acknowledge briefly WITHOUT answering or re-asking, then
        # wait -- the delayed answer arrives via send_client_content. No spoken
        # "one moment" filler is required (the wpw.5 thinking indicator covers the
        # wait visually); a terse natural acknowledgement is fine, silence is fine.
        pending = (
            "The secretary is still looking that up; the answer will arrive in a "
            "moment as a follow-up. Do NOT answer the question yet and do NOT repeat "
            "it back to the user. Either say nothing or give a brief natural "
            "acknowledgement in the user's language, then continue -- the answer "
            "will be delivered to you shortly."
        )

        if not self._handle_ask_secretary:
            # An outage worth our attention, not a routine miss -> ERROR.
            _log.error("ask_secretary_unavailable", reason="no_handler",
                       session_id=self._session_id)
            return {"answer": fallback, "available": False}

        # The handler returns a status dict (bd jnjj.43): ok / pending / failed.
        # Default to a failed-shaped result so any unexpected return fail-opens.
        result: Dict[str, Any] = {"status": "failed", "answer": ""}
        already_logged = False
        try:
            handler_result = await self._handle_ask_secretary(query)
            if isinstance(handler_result, dict):
                result = handler_result
        except Exception as exc:  # noqa: BLE001
            # The handler is expected to fail-open internally, but guard here too so
            # a bug can never crash the tool-call path / session loop. This already
            # logs the failure at ERROR -- set a flag so the failed branch below does
            # NOT log a SECOND ERROR for the same failure event (which would double
            # the secretary error rate for the exception case).
            _log.error(
                "ask_secretary_handler_error",
                exc_type=type(exc).__name__,
                session_id=self._session_id,
            )
            already_logged = True

        status = result.get("status", "failed")
        answer = result.get("answer", "") or ""

        if status == "ok" and answer:
            response = {"answer": answer, "available": True}
            # Pass through the resolved field sources (bd polyglot-pdf-2af7/3vby) so
            # the principal can hand an EXACT field id + spoken name to
            # switch_to_field instead of guessing one from memory. Only included
            # when non-empty and well-formed -- never on pending/failed.
            sources = result.get("sources", [])
            if isinstance(sources, list) and sources:
                clean_sources = [
                    {"field_id": str(s["field_id"]),
                     "spoken_name": self._translate_spoken(str(s["spoken_name"]))}
                    for s in sources
                    if isinstance(s, dict) and s.get("field_id") and s.get("spoken_name")
                ]
                if clean_sources:
                    response["fields"] = clean_sources
        elif status == "pending":
            # Not a failure -- the answer is coming asynchronously. available stays
            # True (the model is NOT told to apologize); INFO, not ERROR.
            _log.info("ask_secretary_pending",
                     query_length=len(query or ""), session_id=self._session_id)
            response = {"answer": pending, "available": True}
        else:
            # failed (or ok-but-empty): the apology path -> ERROR so it surfaces for
            # us to investigate. Skip if the except block above already logged it.
            if not already_logged:
                _log.error(
                    "ask_secretary_failed",
                    query_length=len(query or ""),
                    session_id=self._session_id,
                )
            response = {"answer": fallback, "available": False}

        _log.info("-" * 80)
        _log.info(
            "GEMINI TOOL RESPONSE", tool="ask_secretary",
            query_length=len(query or ""),
            answer_length=len(response["answer"]),
            available=response["available"],
            status=status,
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

        # DTI current-field coercion (bd polyglot-pdf-h1bn): the update_form_fields for
        # this turn was coerced onto the current field if the model used a hallucinated/
        # drifted/EMPTY id; the confirm MUST follow it onto the same field, or the client
        # looks up the wrong id, reports not-confirmed, and the field is stranded. A
        # DTI turn confirms the field it just filled = the current field, so coerce ANY
        # non-matching confirm id -- including an empty/missing one (the tool schema does
        # not enforce minLength, so '' can arrive; the update path coerces '' too, and
        # the two must stay symmetric -- Codex PR #264) -- onto it. Gate reads the
        # SERVICE's injected USE_DTI (via _get_use_dti), NOT the global get_settings()
        # singleton, so a harness with a non-global Settings(USE_DTI=True) coerces
        # confirms exactly as it coerces updates (Codex PR #264). Matching-id is a no-op.
        use_dti = self._get_use_dti() if self._get_use_dti else False
        if use_dti and self._get_current_field_id is not None:
            current_field_id = self._get_current_field_id()
            # A RESOLVABLE id is authoritative (bd polyglot-pdf-8vy3, symmetric with
            # the update-side gate): the model may legitimately confirm a PREVIOUS
            # field it just re-filled (a late correction). Only an empty or UNKNOWN
            # id -- the hallucination mode -- is coerced onto the current field.
            sent_is_known = bool(field_id) and (
                self._is_known_field(field_id) if self._is_known_field else False)
            if current_field_id and field_id != current_field_id and not sent_is_known:
                # Log ONLY the schema-validated current field id, NEVER the raw model
                # field_id -- it is raw tool input and can carry the user's answer if
                # the model swaps args (Codex PR #264 P0, no-PII policy). Symmetric with
                # the update-side scrub in _coerce_dti_update_to_current_field.
                _log.info("dti_confirm_coerced_to_current_field",
                         session_id=self._session_id,
                         current_field_id=current_field_id)
                field_id = current_field_id

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
            self._confirmed_count += 1
            log_field_confirmation(
                form_id=self._form_id,
                form_session_id=self._form_session_id,
                field_id=field_id,
                field_name=None,  # Will be enriched by frontend if needed
                confirmation_method=confirmation_method,
                kit_id=self._kit_id,  # bd polyglot-pdf-47r3
                edition_date=self._edition_date,
                firm_id=self._firm_id,  # bd polyglot-pdf-xwlt
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
            # Clear the current-field coercion pointer here too (Opus fallback, PR #264):
            # the field is confirmed and the section is ending, so the old pointer must
            # not linger. start_session resets it on the section switch, but clearing now
            # closes the brief window before that where an update could coerce onto the
            # old section's last field. Symmetric with the else-branch clear below.
            if self._clear_current_field:
                self._clear_current_field()
            next_hint = None
            next_field_guidance = None
            client_next_schema = None
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

            # DTI (bd polyglot-pdf-jnjj.22): the next field's full guidance is
            # CLIENT-SUPPLIED -- the client owns the schema, so it rides the
            # next_field_hint_response and is stashed on the coordinator. Render it
            # (same render_field_guidance the initiating message uses for field 1)
            # into next_field_guidance, carrying the live fill_language so fields
            # 2..N also tell the model the value language (bd polyglot-pdf-uogm).
            # Skip on timeout / no hint.
            # The field just confirmed is DONE -- invalidate the current-field coercion
            # pointer NOW (bd polyglot-pdf-h1bn, Codex PR #264). If a fresh next-field
            # schema is delivered below, merge_field_schema re-sets the pointer to that
            # new field; if the hint/schema times out, the pointer STAYS cleared so a
            # later update_form_fields can't be coerced onto (and overwrite) the
            # just-confirmed field. Cleared unconditionally on every confirm success.
            if self._clear_current_field:
                self._clear_current_field()

            # Read the SERVICE's injected USE_DTI (via _get_use_dti), the SAME source as
            # the coercion gate + pointer-clear above -- NOT the global get_settings()
            # singleton. Otherwise, in a non-global Settings(USE_DTI=True) harness, the
            # clear (ungated) would fire but this re-merge (global False) would skip, so
            # the pointer strands at None and the next update's coercion no-ops --
            # reintroducing the unknown_fields bug the coercion fixes (Opus fallback,
            # PR #264). The clear and the re-set MUST read the same settings source.
            next_field_guidance = None
            client_next_schema = None
            use_dti_next = self._get_use_dti() if self._get_use_dti else False
            if use_dti_next and next_hint and self._request_coordinator:
                client_next_schema = self._request_coordinator.consume_pending_next_field_schema()
                if client_next_schema:
                    fill_language = self._get_fill_language() if self._get_fill_language else None
                    spoken_language = self._get_spoken_language() if self._get_spoken_language else None
                    next_field_guidance = render_field_guidance(
                        client_next_schema, fill_language=fill_language,
                        spoken_language=spoken_language,
                        option_label_overrides=self._option_overrides(), spoken_name_overrides=self._spoken_overrides()
                    )
                    # Merge the field into the backend's validation schema so the
                    # SUBSEQUENT update_form_fields for this field is not rejected as
                    # 'unknown' (in DTI mode, on the manifest-first handshake,
                    # _schema['fields'] holds only field 1; Codex PR #229). Schema
                    # only -- no user values. (Re-sets the current-field pointer
                    # cleared just above.)
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
            # Session-language hint (bd tupu.2): the quoted English field name
            # inside the client-built hint is substituted when a translation
            # exists; miss -> untouched.
            "next_field_hint": self._translate_hint(next_hint, client_next_schema),
            "message": message,
        }

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

    async def _handle_skip_field_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle skip_field tool call from Gemini (bd polyglot-pdf-7yra).

        Force-skip a REQUIRED field the user cannot answer right now (distinct from
        marking a field not-applicable, which stays the update_form_fields '' path).
        The frontend owns state, so it records the skip (markFieldSkipped) over a
        synchronous round-trip -- mirroring confirm_field. A skipped field satisfies
        the section, so on success this advances exactly like a confirm (next-field
        hint, or the section-boundary short-circuit).
        """
        field_id = arguments.get("field_id", "") if isinstance(arguments, dict) else ""

        # DTI current-field coercion (bd polyglot-pdf-h1bn), symmetric with the
        # confirm/update paths: a hallucinated/empty id is coerced onto the current
        # field; a RESOLVABLE id is authoritative (the user may skip a specific
        # earlier field). Only an empty/unknown id -- the hallucination mode -- is
        # coerced. Log ONLY the schema-validated current field id, never the raw
        # model field_id (no-PII policy).
        use_dti = self._get_use_dti() if self._get_use_dti else False
        if use_dti and self._get_current_field_id is not None:
            current_field_id = self._get_current_field_id()
            sent_is_known = bool(field_id) and (
                self._is_known_field(field_id) if self._is_known_field else False)
            if current_field_id and field_id != current_field_id and not sent_is_known:
                _log.info("dti_skip_coerced_to_current_field",
                         session_id=self._session_id,
                         current_field_id=current_field_id)
                field_id = current_field_id

        # Synchronous skip round-trip. An absent coordinator (None) means we cannot
        # reach the frontend to record the skip -- the same epistemic state as a
        # timeout, so we must NOT report success (collapse to the timeout path).
        skip_ack = CONFIRM_REQUEST_TIMEOUT
        if self._request_coordinator is not None:
            skip_ack = await self._request_coordinator.request_skip_field(field_id)

        if skip_ack is CONFIRM_REQUEST_TIMEOUT or not isinstance(skip_ack, dict):
            return self._skip_failure_response(
                field_id,
                "Could not record the skip right now (the form did not respond). "
                "Do NOT assume the question was skipped -- ask the user to confirm "
                "the skip again, or continue.",
            )

        if not skip_ack.get("recorded"):
            reason = skip_ack.get("reason")
            if reason == "already_filled":
                # The field already holds a value -- skipping would blank it. Tell
                # the model to CLEAR it intentionally (update_form_fields "") only
                # if the user really wants it removed; otherwise it is already
                # answered. Non-retryable: re-skipping fails identically.
                guidance = (
                    f"Field '{field_id}' already has a value, so it was NOT skipped "
                    f"(skipping would erase the answer). If the user wants to remove "
                    f"it, call update_form_fields with an empty value; otherwise it "
                    f"is already answered -- move on. Do NOT retry skip_field."
                )
                return self._skip_failure_response(field_id, guidance, retryable=False)
            guidance = (
                f"Field '{field_id}' could not be skipped ({reason or 'unknown'}). "
                f"Ask the user whether they want to skip it or provide a value."
            )
            return self._skip_failure_response(field_id, guidance)

        # Recorded -- the skip took. Advance exactly like a confirm: a skipped field
        # satisfies the section, so run the SAME section-boundary / next-field-hint
        # logic. (No confirmation-logging: a skip is intentionally not a value.)
        section_complete = bool(skip_ack.get("section_complete"))
        if section_complete:
            _log.info(
                "skip_section_boundary_skip_hint",
                field_id=field_id,
                session_id=self._session_id,
            )
            if self._clear_current_field:
                self._clear_current_field()
            next_hint = None
            next_field_guidance = None
            client_next_schema = None
            message = (
                f"Field '{field_id}' skipped -- that completes this section. The "
                f"form is advancing to the next section; wait for the next field."
            )
        else:
            if self._request_coordinator is None:
                next_hint_result = HINT_REQUEST_TIMEOUT
            else:
                next_hint_result = await self._request_coordinator.request_next_field_hint()
            hint_timed_out = next_hint_result is HINT_REQUEST_TIMEOUT
            next_hint = None if hint_timed_out else next_hint_result

            # The skipped field is DONE -- clear the coercion pointer (symmetric with
            # the confirm path); merge_field_schema re-sets it for the next field.
            if self._clear_current_field:
                self._clear_current_field()

            next_field_guidance = None
            client_next_schema = None
            use_dti_next = self._get_use_dti() if self._get_use_dti else False
            if use_dti_next and next_hint and self._request_coordinator:
                client_next_schema = self._request_coordinator.consume_pending_next_field_schema()
                if client_next_schema:
                    fill_language = self._get_fill_language() if self._get_fill_language else None
                    spoken_language = self._get_spoken_language() if self._get_spoken_language else None
                    next_field_guidance = render_field_guidance(
                        client_next_schema, fill_language=fill_language,
                        spoken_language=spoken_language,
                        option_label_overrides=self._option_overrides(), spoken_name_overrides=self._spoken_overrides()
                    )
                    if self._merge_field_schema:
                        self._merge_field_schema(client_next_schema)

            if hint_timed_out:
                message = (
                    f"Field '{field_id}' skipped. (Could not determine the next field "
                    f"right now -- do NOT assume the form is complete; ask the user for "
                    f"the next piece of information or call get_form_status.)"
                )
            elif not next_hint:
                message = f"Field '{field_id}' skipped. All fields addressed."
            else:
                message = f"Field '{field_id}' skipped."

        response = {
            "success": True,
            "field_skipped": field_id,
            # Session-language hint (bd tupu.2), same substitution as confirm.
            "next_field_hint": self._translate_hint(next_hint, client_next_schema),
            "message": message,
        }
        if next_field_guidance:
            response["next_field_guidance"] = next_field_guidance

        _log.info("GEMINI TOOL RESPONSE", tool="skip_field", field_id=field_id)
        _dev_log.log_tool_response("skip_field", response, session_id=self._session_id)

        return response

    async def _handle_name_spellback_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle name_spellback tool call from Gemini (bd polyglot-pdf-22h1f).

        Deterministic spell-back: the CLIENT resolves the current field, reads
        the stored value, fetches a Cloud TTS clip that spells it out in the
        SESSION language and asks the verification question (bd 44ywm), and
        plays it BLOCKING (mic muted, model parked on this pending response) --
        the model's speech path never carries the spelling, which is the fix
        for the sticky-first-spelling audio defect (bd 0rpu). The tool takes NO
        arguments on purpose (any model-supplied argument is ignored): the
        current field is the only spellable target, so there is no id for the
        model to hallucinate and no value path from model memory (bd h7wx).

        Three response variants, each an explicit behavioral instruction so the
        model's post-tool generation stays letter-free:
        - delivered: say NOTHING and wait -- the clip already asked the
          verification question in the session language (bd 44ywm), so the
          model neither re-asks nor repeats the letters;
        - interrupted (user pressed PTT mid-clip): listen to what the user is
          saying now -- their audio follows this response;
        - error/timeout: apologize and re-ask for the spelling; NEVER fall back
          to spelling from memory (that would reintroduce the defect exactly
          where it hurts).
        """
        del arguments  # No-argument tool; anything sent is deliberately ignored.

        # Flag gate (Opus cross-surface review, bd polyglot-pdf-dtywl): the
        # DECLARATION is flag-gated, so a call arriving while the flag is off
        # is a hallucinated/undeclared tool call. Refuse in-band immediately --
        # running the round-trip anyway would hold the mic, block the receive
        # loop, and POST a PII field value to a route that 503s.
        enabled = (self._get_spellback_enabled()
                   if self._get_spellback_enabled else False)
        if not enabled:
            return {
                "success": False,
                "status": "error",
                "message": (
                    "The name_spellback tool is not available in this "
                    "session. Do not call it again. Verify the value with "
                    "the user according to your instructions."
                ),
            }

        ack = CONFIRM_REQUEST_TIMEOUT
        if self._request_coordinator is not None:
            ack = await self._request_coordinator.request_spellback()

        if ack is CONFIRM_REQUEST_TIMEOUT or not isinstance(ack, dict):
            response = {
                "success": False,
                "status": "error",
                "message": (
                    "The spelling audio could not be played. Tell the user, in "
                    "the session language, that there was a technical problem "
                    "reading the spelling back, and ask them to spell the value "
                    "again so you can re-check it. Do NOT speak the spelling "
                    "yourself under any circumstances."
                ),
            }
        else:
            status = ack.get("status")
            if status == "delivered":
                # bd 44ywm: the clip carries the WHOLE verification question
                # ("You said J, O, S, E. Is that correct?" in the session
                # language), so the model's job now is to WAIT, not to ask.
                response = {
                    "success": True,
                    "status": "delivered",
                    "message": (
                        "The user has ALREADY heard the stored spelling and "
                        "been asked whether it is correct. Do NOT ask again, "
                        "do NOT repeat or spell the value, and do NOT speak "
                        "now -- stay silent and listen for their yes or no."
                    ),
                }
            elif status == "interrupted":
                response = {
                    "success": True,
                    "status": "interrupted",
                    "message": (
                        "The user interrupted the spelling playback and is "
                        "speaking now. Listen and respond to what they say. Do "
                        "NOT speak the spelling yourself; if the user wants to "
                        "hear it again, call name_spellback again."
                    ),
                }
            else:
                reason = ack.get("reason")
                if reason == "no_value":
                    detail = (
                        "There is no stored value to spell for the current "
                        "field yet. Fill the field with update_form_fields "
                        "first, then call name_spellback."
                    )
                else:
                    detail = (
                        "Tell the user, in the session language, that there "
                        "was a technical problem reading the spelling back, "
                        "and ask them to spell the value again so you can "
                        "re-check it."
                    )
                response = {
                    "success": False,
                    "status": "error",
                    "message": detail + (
                        " Do NOT speak the spelling yourself under any "
                        "circumstances."
                    ),
                }

        # Timing fields (playback_ms / fetch_ms) feed the bead's latency exit
        # criterion; they carry no PII.
        if isinstance(ack, dict):
            _log.info(
                "GEMINI TOOL RESPONSE",
                tool="name_spellback",
                status=ack.get("status"),
                reason=ack.get("reason"),
                playback_ms=ack.get("playback_ms"),
                fetch_ms=ack.get("fetch_ms"),
            )
        else:
            _log.info("GEMINI TOOL RESPONSE", tool="name_spellback", status="timeout")
        _dev_log.log_tool_response("name_spellback", response, session_id=self._session_id)

        return response

    async def _handle_switch_to_field_tool(
        self,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle switch_to_field tool call from Gemini (bd polyglot-pdf-jnjj.36).

        Field-level navigation: jump the form's focus to ONE specific field --
        the principal's half of the secretary architecture (ask_secretary
        identifies a field via its `fields` list; this navigates to it -- bd
        polyglot-pdf-3vby) and the "change my earlier answer" correction path.
        The frontend owns all field state, so it resolves the
        identifier (field_id or exact spoken name), pins the field for its
        next-field computation (UI focus follows), and acks with the target's
        hint + (DTI) schema over a synchronous round-trip -- mirroring
        skip_field. Unlike switch_section, the Gemini session is NOT restarted:
        the jump only changes which field is current.

        The model-supplied identifier may be a spoken name; it is passed to the
        client but NEVER logged (no-PII policy). Only the schema-validated
        field_id the client resolves is logged.
        """
        if isinstance(arguments, dict):
            identifier = str(arguments.get("field") or "").strip()
        else:
            identifier = str(arguments or "").strip()
        if not identifier:
            return {
                "success": False,
                "message": (
                    "switch_to_field needs the target field: pass its exact "
                    "field_id (preferred) or its exact spoken name."
                ),
            }

        ack = await self._request_switch_ack(identifier)
        if ack is None:
            return {
                "success": False,
                "message": (
                    "Could not switch fields right now (the form did not "
                    "respond). Do NOT assume the jump happened -- continue "
                    "with the current field, or try again."
                ),
            }

        # Direct hit: the frontend resolved the identifier EXACTLY. The common,
        # zero-secretary path ("go back to my mailing city").
        if ack.get("found"):
            return self._switch_success_response(ack)

        reason = ack.get("reason")
        # other_section / hidden are real, specific outcomes -- not "which field?"
        # ambiguity, so they never go through the secretary resolver.
        if reason == "other_section":
            label = ack.get("section_label") or "another section"
            order = ack.get("section_order")
            where = f"section {order} ('{label}')" if order else f"'{label}'"
            return self._switch_miss_log(reason, {
                "success": False,
                "message": (
                    f"That field is in {where}, not the current section. "
                    f"Call switch_section to go there first, then switch_to_field."
                ),
            })
        if reason == "hidden":
            return self._switch_miss_log(reason, {
                "success": False,
                "message": (
                    "That field is currently hidden by the form's conditional "
                    "logic (an earlier answer keeps it inactive), so it cannot be "
                    "navigated to. If the user disagrees, revisit the controlling "
                    "answer instead."
                ),
            })

        # unknown_field: the frontend's EXACT resolver missed. Rather than bounce
        # the whole thing back to the voice model (a wasted turn + an id-guess
        # risk), ask the secretary to identify the field from the (possibly vague)
        # prose, then re-attempt the switch with the exact id it returns -- one
        # voice turn, not three (bd polyglot-pdf-y76q). Fuzzy matching lives in the
        # secretary (a model reasoning over the catalog), never in the exact
        # frontend resolver, so no silent mis-fill.
        resolved = await self._resolve_field_via_secretary(identifier)
        if resolved is not None and resolved.get("field_id"):
            ack2 = await self._request_switch_ack(resolved["field_id"])
            if isinstance(ack2, dict) and ack2.get("found"):
                return self._switch_success_response(ack2)
            # The secretary's id did not navigate (hidden / other-section / raced
            # away). Fall through to the clarify/candidate degrade below.

        return self._switch_degrade_response(identifier, ack, resolved)

    async def _request_switch_ack(self, identifier: str):
        """Ask the frontend to resolve+pin `identifier` (exact match) and return
        its ack dict, or None if the coordinator is absent or timed out. The
        identifier may be a spoken name; it is passed to the client but NEVER
        logged (no-PII policy)."""
        if self._request_coordinator is None:
            return None
        ack = await self._request_coordinator.request_switch_field(identifier)
        if ack is CONFIRM_REQUEST_TIMEOUT or not isinstance(ack, dict):
            return None
        return ack

    def _switch_miss_log(self, reason, response: Dict[str, Any]) -> Dict[str, Any]:
        """Log a non-navigable switch outcome (no PII) and pass the response
        through."""
        _log.info("switch_to_field_not_navigable",
                 reason=reason or "unknown_field",
                 session_id=self._session_id)
        return response

    async def _resolve_field_via_secretary(self, identifier: str):
        """Ask the secretary to identify the field the (possibly vague) `identifier`
        names, for navigation (bd polyglot-pdf-y76q). Returns:
          {"field_id", "spoken_name", "candidates": [...]}  -- a confident single
              match to re-attempt the switch with (candidates carries any extras);
          {"pushback": <prose>}  -- the secretary deliberately could NOT identify a
              field (resolved False); the prose asks the user to clarify;
          None  -- no secretary handler, a pending/failed lookup, or a timeout (the
              caller degrades to the algorithmic candidate matcher).
        The identifier is passed in the query but never logged (no-PII)."""
        if not self._handle_ask_secretary:
            return None
        query = f"Which field does this refer to, for navigation: {identifier}"
        try:
            # deliver_late=False: this is an INTERNAL query (no user question is
            # pending), so a deadline-blown lookup must NOT be voiced as a spurious
            # follow-up turn -- we degrade in-turn instead (bd polyglot-pdf-y76q).
            result = await self._handle_ask_secretary(query, deliver_late=False)
        except Exception as exc:  # noqa: BLE001
            _log.warning("switch_secretary_resolve_error",
                        exc_type=type(exc).__name__, session_id=self._session_id)
            return None
        if not isinstance(result, dict) or result.get("status") != "ok":
            # pending (deadline blown) / failed -> degrade to the candidate matcher.
            return None
        # Deliberate pushback: the secretary answered but could not identify a field.
        if result.get("resolved") is False:
            return {"pushback": str(result.get("answer") or "")}
        sources = result.get("sources")
        clean = [
            {"field_id": str(s["field_id"]),
             "spoken_name": self._translate_spoken(str(s["spoken_name"]))}
            for s in sources
            if isinstance(s, dict) and s.get("field_id") and s.get("spoken_name")
        ] if isinstance(sources, list) else []
        if not clean:
            return None
        _log.info("switch_secretary_resolved",
                 candidate_count=len(clean), session_id=self._session_id)
        return {"field_id": clean[0]["field_id"],
                "spoken_name": clean[0]["spoken_name"],
                "candidates": clean}

    def _switch_degrade_response(
        self, identifier: str, ack: Dict[str, Any], resolved
    ) -> Dict[str, Any]:
        """Build the graceful-degrade tool response for an unresolved switch (bd
        polyglot-pdf-y76q). Never hangs, never navigates a guessed field -- lands
        on a clarify prompt or a 'did you mean...?' pick-list. Order of preference:
          1. secretary semantic pushback -> voice the secretary's clarify prose;
          2. secretary candidates (>=2, or a single that failed to navigate) ->
             'Did you mean X or Y?';
          3. the frontend's algorithmic candidate matcher (word-overlap) ->
             'Did you mean ...?';
          4. a bare clarify ask."""
        # 1. Secretary pushback (it could not find a match and said so).
        if isinstance(resolved, dict) and resolved.get("pushback"):
            return self._switch_miss_log("secretary_pushback", {
                "success": False,
                "message": (
                    resolved["pushback"]
                    + " Ask the user to describe the field more specifically, then "
                    "try switch_to_field again."
                ),
            })

        def _did_you_mean(names):
            uniq = []
            for n in names:
                if n and n not in uniq:
                    uniq.append(n)
            return uniq

        def _did_you_mean_msg(names, prefix=""):
            """A 'Did you mean X?' clarify line, singular or plural."""
            if len(names) == 1:
                head = f"Did you mean '{names[0]}'?"
            else:
                head = "Did you mean one of these? " + "; ".join(names) + "."
            return (
                prefix + head + " Ask the user which, then call switch_to_field "
                "with that exact spoken name."
            )

        # 2. Secretary candidates the switch could not land on directly.
        if isinstance(resolved, dict) and resolved.get("candidates"):
            # NOT re-translated: _resolve_field_via_secretary already translated
            # these candidates' spoken names (fresh-eyes round 2 -- a double
            # pass is a latent collision trap, never a correct second mapping).
            names = _did_you_mean(
                [c.get("spoken_name") for c in resolved["candidates"]])
            if names:
                return self._switch_miss_log("secretary_candidates", {
                    "success": False,
                    "message": _did_you_mean_msg(names),
                })

        # 3. The frontend's algorithmic (word-overlap) candidate matcher.
        candidates = ack.get("candidates") if isinstance(ack, dict) else None
        if isinstance(candidates, list) and candidates:
            names = _did_you_mean(
                [self._translate_spoken(c.get("spoken_name"))
                 for c in candidates
                 if isinstance(c, dict)])
            if names:
                return self._switch_miss_log("algorithmic_candidates", {
                    "success": False,
                    "message": _did_you_mean_msg(
                        names, prefix="I could not find that field. "),
                })

        # 4. Nothing to suggest -- a bare clarify ask.
        return self._switch_miss_log("unknown_field", {
            "success": False,
            "message": (
                "I could not find a field matching that. Ask the user to describe "
                "which field they mean, then call switch_to_field again."
            ),
        })

    def _switch_success_response(self, ack: Dict[str, Any]) -> Dict[str, Any]:
        """Build the switch_to_field success tool response from a found ack: merge
        the target's schema (re-point the coercion pointer), render its guidance,
        and describe where the model landed + the field's state. The current value
        rides the response (same Gemini trust boundary as ask_secretary) but is
        never logged."""
        field_id = ack.get("field_id")
        # Session-language name for the "Now on field ..." message (bd tupu.2).
        spoken_name = self._translate_spoken(ack.get("spoken_name")) or field_id

        # DTI: the ack carries the target's full schema -- record it for validation
        # AND re-point the current-field coercion pointer at the target
        # (merge_field_schema does both), then render its guidance.
        field_guidance = None
        field_schema = ack.get("next_field_schema")
        if field_schema:
            if self._merge_field_schema:
                self._merge_field_schema(field_schema)
            fill_language = self._get_fill_language() if self._get_fill_language else None
            spoken_language = self._get_spoken_language() if self._get_spoken_language else None
            field_guidance = render_field_guidance(
                field_schema, fill_language=fill_language,
                spoken_language=spoken_language,
                option_label_overrides=self._option_overrides(), spoken_name_overrides=self._spoken_overrides()
            )

        if ack.get("already_confirmed"):
            state_note = (
                "It already has a confirmed answer -- read the current value back "
                "and ask what the user wants to change it to."
            )
        elif ack.get("has_value"):
            state_note = (
                "It already holds an unconfirmed value -- read it back and verify "
                "it with the user."
            )
        else:
            state_note = "It is currently unanswered -- ask the user for it."
        message = f"Now on field '{spoken_name}'. {state_note}"

        response: Dict[str, Any] = {"success": True, "message": message}
        if "value" in ack:
            response["current_value"] = ack.get("value")
        if field_guidance:
            response["field_guidance"] = field_guidance

        _log.info("GEMINI TOOL RESPONSE", tool="switch_to_field",
                 field_id=field_id)
        _dev_log.log_tool_response("switch_to_field", response,
                                   session_id=self._session_id)
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

    def _skip_failure_response(self, field_id: str, message: str,
                               retryable: bool = True) -> Dict[str, Any]:
        """Build the skip_field tool response for a skip that did NOT take (bd
        polyglot-pdf-7yra). Same WS-C2 structured-error shape as
        _confirm_failure_response, but with skip-specific keys/labels
        (``field_skipped`` + ``tool="skip_field"``) so the response and dev-log are
        not mislabeled as a confirm. ``message`` is a fixed, caller-controlled
        string -- never a field value (PII-free)."""
        response = {
            "success": False,
            "field_skipped": None,
            "next_field_hint": None,
            "status": "error",
            "retryable": retryable,
            "error": message,
            "message": message,
        }
        _log.info("GEMINI TOOL RESPONSE", tool="skip_field", field_id=field_id, skipped=False)
        _dev_log.log_tool_response("skip_field", response, session_id=self._session_id)
        return response

    # Helper methods

    def _parse_update_arguments(self, arguments: Any) -> Dict[str, Any]:
        """Parse raw update arguments into normalized dict.

        HALLUCINATION_REDUCTION: only the single-field format is accepted --
        {"field_id": "firstName", "value": "Alice"}. Anything else returns an
        empty payload (the update is rejected).
        """
        updates_payload: Dict[str, Any] = {}

        # Single-field format: {"field_id": "...", "value": "..."}
        if isinstance(arguments, dict) and "field_id" in arguments:
            field_id = arguments.get("field_id")
            value = arguments.get("value")
            if field_id is not None:
                updates_payload = {str(field_id): value}
            return updates_payload

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
        rejected_count: int = 0,
        known_inactive_fields: Optional[list] = None,
        consecutive_unknown_rejections: int = 0,
        applied_values: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build tool response for update_form_fields.

        Args:
            validation_errors: List of validation error objects
            unknown_fields: List of unknown field IDs
            applied_fields: List of successfully applied field IDs
            next_field_hint: Spoken name hint for next field
            rejected_count: Number of fields rejected due to multi-field constraint
            applied_values: field_id -> CANONICAL stored value for each applied
                field (post-normalization, bd polyglot-pdf-h7wx). Echoed back as
                stored_values ONLY on the success path (bd polyglot-pdf-f7h7) so
                the model reads its confirmation read-back from the authoritative
                stored value, never from its own (possibly evicted) memory. On the
                error branch it is deliberately NOT echoed -- send_form_update
                carried nothing to the client there, so an echo would diverge.
                Model-facing only -- must never be logged.
            known_inactive_fields: Subset of unknown_fields that ARE real fields
                the session has seen (manifest/merge-known) but are not the active
                field -- their rejection message points at switch_to_field
                (bd polyglot-pdf-b1gj)
            consecutive_unknown_rejections: Running count of update calls rejected
                wholly as unknown-field; at UNKNOWN_REJECTION_LOOP_THRESHOLD the
                message escalates to a stop-retrying instruction

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

            # A rejected value must DIE with its rejection (bd polyglot-pdf-djnk):
            # observed live (6mzi hi run), a value that failed options-validation
            # on the current field was silently re-used as the fill for the NEXT
            # field, overriding what the user actually said there. Tell the model
            # explicitly to discard it and re-ask.
            if validation_errors:
                error_lines.append(
                    "DISCARD the rejected value(s) above -- they are not pending "
                    "answers. Never reuse a rejected value on another field or on "
                    "the next field. Ask the user again for the current field and "
                    "fill exactly what THEY say."
                )

            # Format unknown fields. Two distinct failure modes with distinct
            # recoveries (bd polyglot-pdf-b1gj):
            # - a REAL field that is not the active one -> the exit ramp is
            #   switch_to_field (retrying the update fails identically forever);
            # - a nonexistent id -> the model invented it; it must copy the id
            #   from the latest guidance block or navigate by the user's words.
            known_inactive = set(known_inactive_fields or [])
            for field_id in unknown_fields:
                if field_id in known_inactive:
                    error_lines.append(
                        f"{field_id}: this field exists but is NOT the active field, "
                        f"so it cannot be filled right now. Do NOT retry "
                        f"update_form_fields with it -- that will keep failing. Call "
                        f"switch_to_field (with this field or the user's own words) "
                        f"to navigate to it first; once it is the active field, fill it."
                    )
                else:
                    error_lines.append(
                        f"{field_id}: unknown field -- no field with this id exists. "
                        f"Never invent or guess field ids. Copy the exact field_id "
                        f"from the latest guidance block, or call switch_to_field "
                        f"with the user's own words to locate the right field."
                    )

            # Loop-breaker escalation (bd polyglot-pdf-b1gj): after N consecutive
            # wholly-unknown rejections the model is stuck (observed live: 338
            # retries until idle-timeout disconnect). Lead with an explicit STOP.
            if (
                unknown_fields
                and not applied_fields
                and consecutive_unknown_rejections >= UNKNOWN_REJECTION_LOOP_THRESHOLD
            ):
                error_lines.insert(0, (
                    f"STOP RETRYING: {consecutive_unknown_rejections} update attempts "
                    f"in a row have been rejected. Do NOT call update_form_fields "
                    f"again with this target. Briefly tell the user, in their "
                    f"language, that you are finding the right place on the form; "
                    f"then call switch_to_field to navigate to the field they are "
                    f"answering (or get_form_status to see where you are), and "
                    f"continue from there."
                ))

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
            # NO stored_values echo on the error branch (bd polyglot-pdf-f7h7):
            # reaching this branch means the caller took send_form_update's else
            # path and sent send_form_update({}, []) -- the client stored NOTHING.
            # A collapsed multi-field call DOES leave applied_values populated
            # (its first field validated), but that value was still never carried
            # to the client, so echoing it as "stored" tells the model to read
            # back a value client and model do not agree on -- exactly the
            # confabulation-confirm divergence h7wx set out to kill, on the error
            # path. The echo belongs only on the true success path below, where
            # send_form_update actually delivered the value.
        else:
            # All fields valid. Next-field guidance is sent after confirm_field
            # (DTI), not on the update response, to reduce round trips.
            # stored_values echoes the CANONICAL saved value (bd polyglot-pdf-h7wx):
            # the SI directs the model to read its confirmation read-back from this
            # echo -- the authoritative stored value -- never from its own memory,
            # which compression eviction can have emptied (live sessions confirmed
            # values that were never in the field). The message repeats it inline
            # because message text is what the model most reliably attends to.
            tool_response = {
                "success": True,
                "applied_fields": applied_fields,
                "message": "Fields updated successfully.",
            }
            if applied_values:
                tool_response["stored_values"] = applied_values
                stored_str = "; ".join(
                    f"{fid} = {val!r}" for fid, val in applied_values.items()
                )
                tool_response["message"] = (
                    f"Fields updated successfully. Stored value: {stored_str}. "
                    f"Read THIS stored value back to the user for confirmation."
                )

        _log.info("-" * 80)
        _log.info("GEMINI TOOL RESPONSE", success=tool_response.get("success"), 
                 applied_count=len(tool_response.get("applied_fields", [])),
                 has_errors=bool(tool_response.get("validation_errors") or tool_response.get("unknown_fields")))
        _log.info("-" * 80)
        
        return tool_response
