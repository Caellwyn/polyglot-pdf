"""
Request coordinator for async frontend communication.

Handles the async request/response pattern for stateless client-server
communication. Backend sends requests to frontend and awaits responses
via WebSocket with timeout handling.
"""
import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import WebSocket
import structlog

from .field_utils import strip_field_id_from_hint

_log = structlog.get_logger(module="request_coordinator")


# Sentinel distinguishing "the frontend did not answer the next-field-hint
# request in time" from a genuine None ("no fields left -- form complete").
# Both used to collapse to None, which let a slow round-trip masquerade as
# completion and make Gemini wrap the form up early (bd polyglot-pdf-tks).
# Callers that forward the hint to Gemini MUST treat this sentinel as "unknown,
# do NOT claim the form is done" rather than as a real hint.
HINT_REQUEST_TIMEOUT = object()


# Sentinel for "the frontend did not answer the confirm_field round-trip in time"
# (slow or disconnected client), distinct from a real ack. confirm_field is a
# synchronous round-trip (bd polyglot-pdf-wpw.2 / WS-E2): the frontend replies
# whether it actually RECORDED the confirmation, so the backend can return
# success:false to Gemini when a field has no value. A timeout must NEVER read as
# "confirmed" -- a slow/dead client that silently counted as a successful confirm
# is exactly the failure this round-trip exists to prevent. Callers MUST treat
# this sentinel as "not confirmed, do NOT advance / do NOT assume the form is
# done", same discipline as HINT_REQUEST_TIMEOUT.
CONFIRM_REQUEST_TIMEOUT = object()


class RequestCoordinator:
    """Coordinates async request/response cycles with the frontend.

    Pending requests are tracked in ONE map keyed by request_id (bd
    polyglot-pdf-bxw / WS-E1). The previous design used a single slot PER request
    TYPE (_pending_next_field_request etc.), so two overlapping requests of the
    same type clobbered each other: the second overwrote the first's slot, the
    first's future was orphaned (its caller hung to timeout), and the first
    response that arrived resolved whichever future currently held the slot --
    a cross-resolve. Keying by request_id gives every in-flight request its own
    future, so same-type concurrency is safe.
    """

    def __init__(self, websocket: Optional[WebSocket] = None, session_id: Optional[str] = None):
        """
        Initialize request coordinator.

        Args:
            websocket: WebSocket connection to frontend
            session_id: Optional session ID for logging context
        """
        self._websocket = websocket
        self._session_id = session_id

        # One slot per IN-FLIGHT request, keyed by request_id. Each entry is
        # {"future": asyncio.Future, "type": str, ...extras}. A request adds its
        # entry; the matching handler (or a timeout) pops it.
        self._pending: Dict[str, Dict[str, Any]] = {}

        # DTI (bd polyglot-pdf-jnjj.22): the next_field_hint_response may carry the
        # next field's FULL schema (the client owns it; the backend does not). The
        # hint future resolves to the hint string only, so the accompanying schema
        # is stashed here keyed by request_id and read out by request_next_field_hint
        # right after the future resolves. Keyed (not a single slot) so overlapping
        # hint requests never cross-deliver a schema.
        self._next_field_schemas: Dict[str, Any] = {}

    def set_websocket(self, websocket: WebSocket) -> None:
        """Update WebSocket connection."""
        self._websocket = websocket

    # --- Internal helpers (keyed-slot bookkeeping) -----------------------------

    def _register(self, request_type: str, **extras: Any) -> "tuple[str, asyncio.Future]":
        """Create a future for a new request, store it keyed by a fresh
        request_id, and return (request_id, future)."""
        request_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.Future()
        entry = {"future": future, "type": request_type}
        entry.update(extras)
        self._pending[request_id] = entry
        return request_id, future

    def _discard(self, request_id: str) -> None:
        """Drop a pending request (on send-failure / timeout / error). Safe if
        the id is already gone (a late timeout after the handler resolved it)."""
        self._pending.pop(request_id, None)

    def _resolve(self, request_id: str, expected_type: str, result: Any,
                 transform=None) -> bool:
        """Resolve the future for request_id with `result`, if the entry exists
        and is of the expected type. Returns True only when the future was
        actually set (not when it was already done/cancelled by a timeout race).
        Logs a stray (no-entry) or wrong-type response so it stays visible. Pops a
        matched entry.

        `transform`, when given, is applied to `result` AFTER the entry is
        validated -- so a parse/normalize step (e.g. strip_field_id_from_hint)
        NEVER runs on an unmatched/stale response. This is load-bearing: running
        the strip on a malformed unknown-id response could raise and tear down the
        WS path (Codex PR #136); the old per-slot guards returned before stripping.
        """
        entry = self._pending.get(request_id)
        if entry is None:
            # No pending request with this id (a stray or post-timeout-late
            # response). There is no "expected" type here -- log the id only.
            _log.warning(
                "unexpected_response_no_pending_request",
                session_id=self._session_id,
                request_id=request_id,
            )
            return False
        if entry.get("type") != expected_type:
            # A response whose id maps to a DIFFERENT request type -- never
            # cross-resolve it. (Practically unreachable since the wire response
            # type selects the handler, but a defensive guard against a future
            # mis-route.)
            _log.warning(
                "mismatched_response_type",
                session_id=self._session_id,
                request_id=request_id,
                expected_type=expected_type,
                actual_type=entry.get("type"),
            )
            return False
        # Validated -- now it is safe to apply any transform to the result.
        if transform is not None:
            result = transform(result)
        future = entry.get("future")
        self._pending.pop(request_id, None)
        if future is not None and not future.done():
            future.set_result(result)
            return True
        # The future was already resolved/cancelled (e.g. wait_for timed out and
        # cancelled it just before this late response arrived) -- nothing
        # delivered, so report no-op.
        return False

    # Request methods

    async def request_form_state(self, field_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Request current form state from the frontend client.

        This implements the async request/response pattern for stateless architecture.
        Backend sends a request to frontend and waits for response.

        Args:
            field_ids: Specific field IDs to request, or None/empty for all fields

        Returns:
            Dictionary of field_id -> value from the client
        """
        if not self._websocket:
            _log.warning("request_form_state_no_websocket", session_id=self._session_id)
            return {}

        request_id, future = self._register("form_state")

        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "get_form_state",
                "request_id": request_id,
                "field_ids": field_ids or [],
            })
        except Exception as exc:
            _log.error("failed_to_send_form_state_request", session_id=self._session_id, error_type=type(exc).__name__)
            self._discard(request_id)
            return {}

        # Wait for response with timeout
        # timing_coordinator_roundtrip checkpoint 7 (bd polyglot-pdf-cwsy).
        _t_coord_start = time.monotonic()
        try:
            result = await asyncio.wait_for(future, timeout=5.0)
            _coord_ms = round((time.monotonic() - _t_coord_start) * 1000)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="form_state",
                request_id=request_id,
                roundtrip_ms=_coord_ms,
                session_id=self._session_id,
            )
            return result
        except asyncio.TimeoutError:
            _coord_ms = round((time.monotonic() - _t_coord_start) * 1000)
            _log.error("form_state_request_timeout", session_id=self._session_id, request_id=request_id)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="form_state",
                request_id=request_id,
                roundtrip_ms=_coord_ms,
                timeout=True,
                session_id=self._session_id,
            )
            self._discard(request_id)
            return {}
        except Exception as exc:
            _log.error("form_state_request_error", session_id=self._session_id, error_type=type(exc).__name__)
            self._discard(request_id)
            return {}

    async def request_next_field_hint(self) -> Any:
        """
        Request next field hint from the frontend client.

        This implements the async request/response pattern for getting navigation hints.
        The frontend computes the next unfilled field and formats a hint for Gemini.

        Returns:
            - Formatted hint string (e.g., "Next field to fill is #3: 'email' ...")
              when the frontend has a next field.
            - None when the frontend answered and the form is genuinely complete.
            - HINT_REQUEST_TIMEOUT (the module sentinel) when the frontend did NOT
              answer in time / the request could not be sent. Callers must NOT treat
              this as completion (bd polyglot-pdf-tks).
        """
        if not self._websocket:
            _log.warning("request_next_field_hint_no_websocket", session_id=self._session_id)
            return HINT_REQUEST_TIMEOUT

        request_id, future = self._register("next_field")

        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "get_next_field_hint",
                "request_id": request_id,
            })
        except Exception as exc:
            _log.error("failed_to_send_next_field_request", session_id=self._session_id, error_type=type(exc).__name__)
            self._discard(request_id)
            return HINT_REQUEST_TIMEOUT

        # Wait for response with timeout
        # timing_coordinator_roundtrip checkpoint 7 (bd polyglot-pdf-cwsy).
        _t_coord_nf = time.monotonic()
        try:
            result = await asyncio.wait_for(future, timeout=2.0)
            _coord_nf_ms = round((time.monotonic() - _t_coord_nf) * 1000)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="next_field",
                request_id=request_id,
                roundtrip_ms=_coord_nf_ms,
                session_id=self._session_id,
            )
            return result
        except asyncio.TimeoutError:
            self._next_field_schemas.pop(request_id, None)
            _coord_nf_ms = round((time.monotonic() - _t_coord_nf) * 1000)
            _log.error("next_field_request_timeout", session_id=self._session_id, request_id=request_id)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="next_field",
                request_id=request_id,
                roundtrip_ms=_coord_nf_ms,
                timeout=True,
                session_id=self._session_id,
            )
            self._discard(request_id)
            return HINT_REQUEST_TIMEOUT
        except Exception as exc:
            _log.error("next_field_request_error", session_id=self._session_id, error_type=type(exc).__name__)
            self._discard(request_id)
            return HINT_REQUEST_TIMEOUT

    async def request_confirm_field(
        self, field_id: str, confirmation_method: str
    ) -> Any:
        """
        Ask the frontend to record a confirmation and report whether it took.

        confirm_field is a synchronous round-trip (bd polyglot-pdf-wpw.2 / WS-E2):
        the frontend owns all field state, so it -- not the backend -- is the
        source of truth for whether a field was actually confirmed. A field with
        no usable value cannot be confirmed (the 0y7 loop-breaker), and the
        frontend reports that back so the confirm_field tool can return
        success:false and Gemini re-asks in-band, instead of the old
        fire-and-forget send that always read as success.

        Returns:
            - A dict ``{"recorded": bool, "reason": Optional[str],
              "section_complete": bool}`` when the frontend answered. ``recorded``
              is whether the confirmation was recorded; ``reason`` is a fixed
              category token (e.g. "no_value") when it was not -- never a field
              value (PII-free); ``section_complete`` is True when this confirm
              completed a section that has a NEXT section to advance to, so the
              confirm handler skips the racing next-field-hint request (bd
              polyglot-pdf-njvh) -- defaults to False when the FE omits it.
            - CONFIRM_REQUEST_TIMEOUT (the module sentinel) when the frontend did
              NOT answer in time / the request could not be sent. Callers must NOT
              treat this as confirmed (bd polyglot-pdf-wpw.2).
        """
        if not self._websocket:
            _log.warning("request_confirm_field_no_websocket", session_id=self._session_id)
            return CONFIRM_REQUEST_TIMEOUT

        request_id, future = self._register("confirm_field", field_id=field_id)

        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "confirm_field",
                "request_id": request_id,
                "field_id": field_id,
                "confirmation_method": confirmation_method,
            })
        except Exception as exc:
            _log.error("failed_to_send_confirm_field_request",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT

        # Wait for response with timeout (same 2.0s budget as the next-field hint:
        # a slow client must not hang the receive loop).
        # timing_coordinator_roundtrip checkpoint 7 (bd polyglot-pdf-cwsy).
        _t_coord_cf = time.monotonic()
        try:
            result = await asyncio.wait_for(future, timeout=2.0)
            _coord_cf_ms = round((time.monotonic() - _t_coord_cf) * 1000)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="confirm_field",
                request_id=request_id,
                roundtrip_ms=_coord_cf_ms,
                session_id=self._session_id,
            )
            return result
        except asyncio.TimeoutError:
            _coord_cf_ms = round((time.monotonic() - _t_coord_cf) * 1000)
            _log.error("confirm_field_request_timeout",
                      session_id=self._session_id,
                      request_id=request_id)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="confirm_field",
                request_id=request_id,
                roundtrip_ms=_coord_cf_ms,
                timeout=True,
                session_id=self._session_id,
            )
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT
        except Exception as exc:
            _log.error("confirm_field_request_error",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT

    async def request_skip_field(self, field_id: str) -> Any:
        """
        Ask the frontend to force-skip a required field the user cannot answer
        (bd polyglot-pdf-7yra). The frontend owns all field state, so it -- not
        the backend -- records the skip (SchemaFormStateManager.markFieldSkipped:
        the field is marked skipped with an empty value, satisfying the section
        gate and printing blank on the PDF). This is a synchronous round-trip like
        request_confirm_field: the frontend acks whether the skip was recorded.

        Returns:
            - A dict ``{"recorded": bool, "reason": Optional[str],
              "section_complete": bool}`` when the frontend answered (same shape as
              request_confirm_field, so the skip handler can advance a completed
              section the same way). ``reason`` is a fixed category token, never a
              field value (PII-free).
            - CONFIRM_REQUEST_TIMEOUT (the module sentinel) when the frontend did
              NOT answer in time / the request could not be sent. Callers must NOT
              treat this as recorded.
        """
        if not self._websocket:
            _log.warning("request_skip_field_no_websocket", session_id=self._session_id)
            return CONFIRM_REQUEST_TIMEOUT

        request_id, future = self._register("skip_field", field_id=field_id)

        try:
            await self._websocket.send_json({
                "type": "skip_field",
                "request_id": request_id,
                "field_id": field_id,
            })
        except Exception as exc:
            _log.error("failed_to_send_skip_field_request",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT

        _t_coord_sf = time.monotonic()
        try:
            result = await asyncio.wait_for(future, timeout=2.0)
            _coord_sf_ms = round((time.monotonic() - _t_coord_sf) * 1000)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="skip_field",
                request_id=request_id,
                roundtrip_ms=_coord_sf_ms,
                session_id=self._session_id,
            )
            return result
        except asyncio.TimeoutError:
            _log.error("skip_field_request_timeout",
                      session_id=self._session_id,
                      request_id=request_id)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT
        except Exception as exc:
            _log.error("skip_field_request_error",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT

    async def request_switch_field(self, identifier: str) -> Any:
        """
        Ask the frontend to make a SPECIFIC field current (bd polyglot-pdf-
        jnjj.36 -- the switch_to_field tool). The frontend owns schema + field
        state, so it resolves the identifier (field_id or exact spoken name),
        pins the field for its next-field computation, moves UI focus, and
        acks with the target's hint + (DTI) schema. Synchronous round-trip
        like request_skip_field. The identifier is model-supplied and may name
        a field; it is sent to the client but never logged (no-PII policy).

        Returns:
            - The frontend's ack dict: ``{"found": bool, ...}`` where the
              extra keys vary by outcome -- success carries field_id /
              spoken_name / next_field_hint / already_confirmed / has_value
              (+ next_field_schema in DTI mode); failure carries a fixed
              ``reason`` token (unknown_field / hidden / other_section, the
              latter with section_label + section_order).
            - CONFIRM_REQUEST_TIMEOUT (the module sentinel) when the frontend
              did NOT answer in time / the request could not be sent.
        """
        if not self._websocket:
            _log.warning("request_switch_field_no_websocket", session_id=self._session_id)
            return CONFIRM_REQUEST_TIMEOUT

        request_id, future = self._register("switch_field")

        try:
            await self._websocket.send_json({
                "type": "switch_field",
                "request_id": request_id,
                "field": identifier,
            })
        except Exception as exc:
            _log.error("failed_to_send_switch_field_request",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT

        _t_coord_swf = time.monotonic()
        try:
            result = await asyncio.wait_for(future, timeout=2.0)
            _coord_swf_ms = round((time.monotonic() - _t_coord_swf) * 1000)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="switch_field",
                request_id=request_id,
                roundtrip_ms=_coord_swf_ms,
                session_id=self._session_id,
            )
            return result
        except asyncio.TimeoutError:
            _log.error("switch_field_request_timeout",
                      session_id=self._session_id,
                      request_id=request_id)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT
        except Exception as exc:
            _log.error("switch_field_request_error",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT

    # Wall-clock cap for the whole spell-back round-trip: model-audio drain
    # wait + TTS fetch + BLOCKING clip playback on the client. Generous
    # headroom rather than a tight fit: the plain-text Chirp3 clip (bd
    # polyglot-pdf-44ywm) runs ~5s for a typical name, and the CLIENT holds
    # itself to an 80s total budget (spellbackPlayer CLIENT_TOTAL_BUDGET_MS)
    # so it always settles first. Anything reaching 90s means the client died
    # mid-playback and the tool must return the error variant rather than
    # wedge the session.
    SPELLBACK_ROUNDTRIP_TIMEOUT = 90.0

    async def request_spellback(self) -> Any:
        """
        Ask the frontend to play the deterministic spell-back clip for the
        CURRENT field (bd polyglot-pdf-22h1f -- the name_spellback tool).

        The frontend owns all field state, so it resolves the current field
        client-side (computeNextField with the pin honored -- the NEXT-FIELD
        computation; NOTE this is a client-only resolution, distinct from
        confirm_field's backend-supplied-and-coerced field_id), reads the stored
        value, fetches the Cloud TTS clip from /api/tts/spellback (which
        speaks the letters one by one IN THE SESSION LANGUAGE and asks the
        verification question itself -- bd polyglot-pdf-44ywm), mutes the mic,
        plays the clip BLOCKING, and acks with the outcome. No field value
        ever crosses this WS message in either direction.

        Unlike every other coordinator round-trip, this one deliberately holds
        the Gemini receive loop for the playback duration -- that is the whole
        point: the model must not speak or hear anything until the clip
        finishes (maintainer design, 2026-08-07). Holding the tool response
        open does NOT park the model, though (bd polyglot-pdf-kvrfq,
        wire-verified 2026-08-26): under user barge-in pressure the
        native-audio model keeps emitting further name_spellback calls while
        earlier ones are unanswered, and because the tool callback runs
        inline on this receive loop, those calls QUEUE behind the in-flight
        round-trip and dispatch back-to-back once it settles (measured: ten
        calls on one field in one incident, each read 3-9ms after the
        previous response). See docs/components/voice-ai.md's
        `name_spellback` bullet for the full queueing behavior and the
        client-side stale-arrival guards that handle it.

        Returns:
            - The frontend's ack dict ``{"status": "delivered"|"interrupted"|
              "error", "reason": Optional[str], "playback_ms": Optional[int],
              "fetch_ms": Optional[int]}``. ``reason`` is a fixed category
              token (e.g. "no_value"), never a field value (PII-free);
              the timing fields feed the bead's latency exit criterion.
            - CONFIRM_REQUEST_TIMEOUT (the module sentinel) when the frontend
              did NOT answer in time / the request could not be sent. Callers
              must NOT treat this as delivered.
        """
        if not self._websocket:
            _log.warning("request_spellback_no_websocket", session_id=self._session_id)
            return CONFIRM_REQUEST_TIMEOUT

        request_id, future = self._register("spellback")

        try:
            await self._websocket.send_json({
                "type": "spellback",
                "request_id": request_id,
            })
        except Exception as exc:
            _log.error("failed_to_send_spellback_request",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT

        _t_coord_sb = time.monotonic()
        try:
            result = await asyncio.wait_for(
                future, timeout=self.SPELLBACK_ROUNDTRIP_TIMEOUT)
            _coord_sb_ms = round((time.monotonic() - _t_coord_sb) * 1000)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="spellback",
                request_id=request_id,
                roundtrip_ms=_coord_sb_ms,
                session_id=self._session_id,
            )
            return result
        except asyncio.TimeoutError:
            _log.error("spellback_request_timeout",
                      session_id=self._session_id,
                      request_id=request_id)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT
        except Exception as exc:
            _log.error("spellback_request_error",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return CONFIRM_REQUEST_TIMEOUT

    def handle_spellback_response(self, request_id: str, payload: Dict[str, Any]) -> None:
        """
        Handle spellback_response from the frontend (bd polyglot-pdf-22h1f).

        Completes the spell-back round-trip with the frontend's whole ack
        payload (status + reason/timing -- see request_spellback's docstring).
        """
        self._resolve(request_id, "spellback", dict(payload or {}))

    async def request_section_info(self, section_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Request section information from frontend.

        Used during section switching to get new section schema and metadata.

        DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
        continuous-DTI is the live flow. Kept as a fallback, not deleted.
        Do not extend.

        Args:
            section_identifier: Section number ('3'), ID, or label

        Returns:
            Dictionary with schema, current_values, metadata, initial_field_hint
            or None if request fails
        """
        if not self._websocket:
            _log.warning("request_section_info_no_websocket", session_id=self._session_id)
            return None

        request_id, future = self._register("section_info")

        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "prepare_section_switch",
                "request_id": request_id,
                "identifier": section_identifier,
            })
        except Exception as exc:
            _log.error("failed_to_send_section_info_request",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return None

        # Wait for response with timeout
        # timing_coordinator_roundtrip checkpoint 7 (bd polyglot-pdf-cwsy).
        _t_coord_si = time.monotonic()
        try:
            result = await asyncio.wait_for(future, timeout=5.0)
            _coord_si_ms = round((time.monotonic() - _t_coord_si) * 1000)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="section_info",
                request_id=request_id,
                roundtrip_ms=_coord_si_ms,
                session_id=self._session_id,
            )
            return result
        except asyncio.TimeoutError:
            _coord_si_ms = round((time.monotonic() - _t_coord_si) * 1000)
            _log.error("section_info_request_timeout",
                      session_id=self._session_id,
                      request_id=request_id)
            _log.info(
                "timing_coordinator_roundtrip",
                request_type="section_info",
                request_id=request_id,
                roundtrip_ms=_coord_si_ms,
                timeout=True,
                session_id=self._session_id,
            )
            self._discard(request_id)
            return None
        except Exception as exc:
            _log.error("section_info_request_error",
                      session_id=self._session_id,
                      error_type=type(exc).__name__)
            self._discard(request_id)
            return None

    # Response handlers

    def handle_form_state_response(self, request_id: str, field_values: Dict[str, Any]) -> None:
        """
        Handle form_state_response message from frontend.

        Completes the async request/response cycle by resolving the keyed future.

        Args:
            request_id: ID matching the original request
            field_values: Dictionary of field_id -> value from client
        """
        self._resolve(request_id, "form_state", field_values)

    def consume_pending_next_field_schema(self) -> Optional[Dict[str, Any]]:
        """Return and clear the most-recently delivered next-field schema (DTI,
        bd polyglot-pdf-jnjj.22). Called by the confirm_field handler immediately
        after request_next_field_hint() resolves -- the confirm flow is sequential
        per session, so 'most recent' is unambiguous. Returns None if the client
        sent no schema (e.g. legacy/non-DTI client, or form complete)."""
        if not self._next_field_schemas:
            return None
        # Drain to the single most-recent entry; clear the rest defensively so a
        # stale schema from an abandoned request can never be served later.
        _, schema = self._next_field_schemas.popitem()
        self._next_field_schemas.clear()
        return schema

    def handle_next_field_hint_response(
        self, request_id: str, hint: Optional[str],
        next_field_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Handle next_field_hint_response message from frontend.

        Completes the async request/response cycle by resolving the keyed future.

        Args:
            request_id: ID matching the original request
            hint: Formatted hint string or None if form is complete
            next_field_schema: (DTI, bd polyglot-pdf-jnjj.22) the next field's FULL
                schema, supplied by the client (which owns it). Stashed for the
                confirm handler to render into next_field_guidance. None for
                legacy/non-DTI clients.
        """
        # Strip the technical "(field_id: ...)" parenthetical here, at the single
        # point where the frontend's spoken hint enters the backend, so EVERY
        # consumer that forwards it to Gemini (the confirm_field tool response,
        # initiating/section-switch messages) gets a field_id-free hint and Gemini
        # never reads the raw field_id aloud (bd polyglot-pdf-dx7). The field_id
        # Gemini needs for update_form_fields comes from the system instruction's
        # FIELDS block, not this hint -- so stripping it here is safe.
        #
        # Pass the strip as a TRANSFORM so it runs ONLY after _resolve validates a
        # matching pending request -- a stale/malformed response (unknown id, or a
        # non-string hint) must not reach strip_field_id_from_hint and risk raising
        # on the WS path (Codex PR #136).
        resolved = self._resolve(request_id, "next_field", hint,
                                 transform=strip_field_id_from_hint)
        # Stash the DTI schema ONLY when _resolve matched a still-pending request.
        # A LATE response (its hint request already timed out -> future popped) must
        # NOT leave a stale schema in the stash, or the NEXT confirm's consume would
        # serve the wrong field's guidance (bd polyglot-pdf-jnjj.22 fresh-eyes).
        if resolved and next_field_schema and request_id:
            self._next_field_schemas[request_id] = next_field_schema

    def handle_confirm_field_response(
        self, request_id: str, recorded: bool, reason: Optional[str] = None,
        section_complete: bool = False,
    ) -> None:
        """
        Handle confirm_field_response message from frontend.

        Completes the synchronous confirm_field round-trip (bd polyglot-pdf-wpw.2)
        by resolving the keyed future with whether the frontend recorded the
        confirmation.

        Args:
            request_id: ID matching the original confirm_field request.
            recorded: True if the frontend actually recorded the confirmation.
            reason: Fixed category token when not recorded (e.g. "no_value"); never
                a field value (PII-free).
            section_complete: True when this confirm completed the section, so the FE
                is about to tear down the socket for switchToSection. The confirm
                handler uses this to SKIP the post-confirm next-field-hint request,
                which would otherwise race that teardown and time out (bd
                polyglot-pdf-njvh).
        """
        self._resolve(request_id, "confirm_field",
                      {"recorded": bool(recorded), "reason": reason,
                       "section_complete": bool(section_complete)})

    def handle_skip_field_response(
        self, request_id: str, recorded: bool, reason: Optional[str] = None,
        section_complete: bool = False,
    ) -> None:
        """
        Handle skip_field_response message from frontend (bd polyglot-pdf-7yra).

        Completes the synchronous skip_field round-trip by resolving the keyed
        future with whether the frontend recorded the skip. Same ack shape as
        confirm_field, so the skip handler can advance a completed section
        identically.

        Args:
            request_id: ID matching the original skip_field request.
            recorded: True if the frontend recorded the skip (markFieldSkipped).
            reason: Fixed category token when not recorded; never a field value.
            section_complete: True when the skip completed the section (the FE is
                about to switchToSection), so the handler skips the racing
                next-field-hint request.
        """
        self._resolve(request_id, "skip_field",
                      {"recorded": bool(recorded), "reason": reason,
                       "section_complete": bool(section_complete)})

    def handle_switch_field_response(
        self, request_id: str, payload: Dict[str, Any]
    ) -> None:
        """
        Handle switch_field_response from the frontend (bd polyglot-pdf-jnjj.36).

        Completes the synchronous switch_field round-trip with the frontend's
        whole ack payload (found + the outcome-specific keys -- see
        request_switch_field's docstring).
        """
        self._resolve(request_id, "switch_field", dict(payload or {}))

    def handle_section_info_response(self, request_id: str, section_info: Dict[str, Any]) -> None:
        """
        Handle section_info_response message from frontend.

        Completes the async request/response cycle for section switching.

        Args:
            request_id: ID matching the original request
            section_info: Dictionary with schema, current_values, metadata, initial_field_hint
        """
        self._resolve(request_id, "section_info", section_info)
