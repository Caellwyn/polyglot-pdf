from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
import json
import asyncio
import os
import time
from ..config import get_settings
from ..dependencies import get_form_filling_service
from ..utils.dev_file_logger import DEV_LOGGING_ENABLED
from ..utils.confirmation_logger import (
	log_form_session_start,
	log_form_session_end,
)
import structlog

# Structured logger for websocket routes
_log = structlog.get_logger().bind(router="websocket_routes")


router = APIRouter(prefix="/ws", tags=["websocket"])
settings = get_settings()

@router.websocket("/echo")
async def ws_echo(
	ws: WebSocket,
	ping_interval: int | None = Query(default=None),
	idle_timeout: int | None = Query(default=None),
):
	if not DEV_LOGGING_ENABLED:
		# Dev-only debug socket: reject the handshake in production, same
		# backend/.env.DEV marker gate as the dev console-log route.
		await ws.close(code=1008)
		return
	await ws.accept()
	ping_iv = ping_interval or settings.WS_PING_INTERVAL_SEC
	idle_to = idle_timeout or settings.WS_IDLE_TIMEOUT_SEC
	last_rx = time.monotonic()
	hello_seen = False

	async def ping_task():
		while True:
			await asyncio.sleep(ping_iv)
			try:
				await ws.send_json({"type": "server_ping", "ts": int(time.time() * 1000)})
			except Exception:
				break

	async def watchdog_task():
		while True:
			await asyncio.sleep(1)
			if time.monotonic() - last_rx > idle_to:
				try:
					await ws.close(code=1001)
				finally:
					break

	ptask = asyncio.create_task(ping_task())
	wtask = asyncio.create_task(watchdog_task())
	try:
		await ws.send_json({"type": "welcome", "message": "connected"})
		while True:
			msg = await ws.receive_text()
			last_rx = time.monotonic()
			try:
				data = json.loads(msg)
			except Exception:
				data = {"type": "text", "message": msg}

			if not isinstance(data, dict):
				await ws.send_json({"type": "error", "code": "bad_message", "message": "payload must be object or text"})
				continue

			mtype = data.get("type")
			if mtype == "hello":
				hello_seen = True
				await ws.send_json({"type": "hello_ack"})
				continue

			if not hello_seen:
				await ws.send_json({"type": "error", "code": "handshake_required", "message": "send hello first"})
				continue

			if mtype == "ping":
				await ws.send_json({"type": "pong", "ts": data.get("ts")})
			elif mtype == "text":
				await ws.send_json({"type": "echo", "data": data})
			else:
				await ws.send_json({"type": "error", "code": "unknown_type", "message": f"unknown type: {mtype}"})
	except WebSocketDisconnect:
		pass
	finally:
		ptask.cancel()
		wtask.cancel()


@router.websocket("/audio")
async def ws_audio(ws: WebSocket, idle_timeout: int | None = Query(default=None)):
	if not DEV_LOGGING_ENABLED:
		# Dev-only debug socket: reject the handshake in production, same
		# backend/.env.DEV marker gate as the dev console-log route.
		await ws.close(code=1008)
		return
	await ws.accept()
	idle_to = idle_timeout or settings.WS_IDLE_TIMEOUT_SEC
	last_rx = time.monotonic()
	total_frames = 0
	total_bytes = 0

	async def watchdog_task():
		while True:
			await asyncio.sleep(1)
			if time.monotonic() - last_rx > idle_to:
				try:
					await ws.close(code=1001)
				finally:
					break

	wtask = asyncio.create_task(watchdog_task())
	try:
		await ws.send_json({"type": "welcome", "message": "audio"})
		while True:
			msg = await ws.receive()
			if isinstance(msg, dict) and msg.get("type") == "websocket.disconnect":
				break
			last_rx = time.monotonic()
			if "bytes" in msg and msg["bytes"] is not None:
				data: bytes = msg["bytes"]
				if len(data) > settings.WS_MAX_AUDIO_FRAME_BYTES:
					await ws.send_json({"type": "error", "code": "frame_too_large", "max": settings.WS_MAX_AUDIO_FRAME_BYTES})
					continue
				# Parse header: 8 bytes => magic(4) 'AFRM', version(1)=1, reserved(1)=0, sample_count(2 LE)
				if len(data) < 8:
					await ws.send_json({"type": "error", "code": "bad_header", "reason": "too_short"})
					continue
				magic = data[0:4]
				version = data[4]
				sample_count = int.from_bytes(data[6:8], "little", signed=False)
				if magic != b"AFRM" or version != 1:
					await ws.send_json({"type": "error", "code": "bad_header", "reason": "magic_or_version"})
					continue
				payload = data[8:]
				expected_bytes = sample_count * 2  # PCM16 mono
				if len(payload) != expected_bytes:
					await ws.send_json({"type": "error", "code": "length_mismatch", "expected": expected_bytes, "got": len(payload)})
					continue
				total_frames += 1
				total_bytes += len(payload)
				# Acknowledge every N frames (e.g., every 10) to show liveness
				if total_frames % 10 == 0:
					await ws.send_json({"type": "ack", "frames": total_frames, "bytes": total_bytes})
			elif "text" in msg and msg["text"] is not None:
				# JSON control channel on same socket
				try:
					obj = json.loads(msg["text"]) if msg["text"] else {}
				except Exception:
					obj = {}
				if obj.get("type") == "ping":
					await ws.send_json({"type": "pong", "ts": obj.get("ts")})
				elif obj.get("type") == "stats":
					await ws.send_json({"type": "stats", "frames": total_frames, "bytes": total_bytes})
				else:
					await ws.send_json({"type": "error", "code": "unknown_control"})
			else:
				await ws.send_json({"type": "error", "code": "bad_frame"})
	except WebSocketDisconnect:
		pass
	finally:
		wtask.cancel()


def _form_number_of(schema: dict | None) -> str:
	"""form_number from a schema, defensively (bd polyglot-pdf-xwlt).

	isinstance-guarded at both levels: a malformed/legacy client can send a
	non-dict form_metadata, and the session-START call site sits OUTSIDE the
	handler's try, so an AttributeError there would kill the session
	ungracefully (the bd polyglot-pdf-ypk4 crash class; fresh-eyes round 1).
	"""
	if not isinstance(schema, dict):
		return "unknown"
	meta = schema.get("form_metadata")
	if not isinstance(meta, dict):
		return "unknown"
	number = meta.get("form_number")
	return number if isinstance(number, str) and number else "unknown"


def should_log_session_start(form_session_id: str | None, is_reconnect: bool) -> bool:
	"""Log a session START only on a FIRST connection for this form session.

	form_session_id survives reconnects, so re-logging on a resume would
	inflate a per-firm session count with what is one session to the user
	(bd polyglot-pdf-xwlt).
	"""
	return bool(form_session_id) and not is_reconnect


def should_log_session_end(form_session_id: str | None, is_reconnect: bool) -> bool:
	"""Log a session END on EVERY connection teardown -- reconnects included.

	Deliberately NOT gated on is_reconnect (fresh-eyes round 1 caught that):
	that flag describes the connection that just OPENED, not the one closing,
	so gating on it dropped the real end record for any session that ever
	reconnected AND emitted a false "abandoned" for the connection that was
	about to resume. The backend cannot tell a mid-form reconnect from a real
	exit at teardown -- the protocol has no terminal-close signal -- so these
	are per-CONNECTION rows and a per-firm SESSION count is a distinct count
	over form_session_id. `is_reconnect` is accepted (unused) to keep the
	pair's call shape symmetric and the asymmetry documented where it lives.
	"""
	return bool(form_session_id)


async def _handle_fill_session(
	websocket: WebSocket,
	session_id: str,
	service,
	send_transcript: bool,
	*,
	accept_connection: bool,
	schema: dict | None = None,  # For web forms
	full_schema: dict | None = None,  # Full-form catalog for the secretary (bd polyglot-pdf-p68s)
	current_values: dict | None = None,  # For reconnect
	fill_language: str = "English",  # Language for AI to use
	spoken_language: str | None = None,  # App-start SPOKEN language choice (ASR bias, bd polyglot-pdf-y25o)
	section_id: str | None = None,  # Current section ID (for token-log context, bd polyglot-pdf-tb7)
	section_number: int | None = None,  # Phase 3: Current section (1-indexed)
	section_label: str | None = None,  # Phase 3: Section label
	total_sections: int | None = None,  # Phase 3: Total sections
	previous_spoken_names: list | None = None,  # Phase 3: Spoken names from completed sections
	initial_field_hint: str | None = None,  # Initial field hint from frontend (pre-computed)
	form_session_id: str | None = None,  # Persistent form session ID from frontend
	kit_id: str | None = None,  # Kit identity for the audit trail (bd polyglot-pdf-47r3)
	firm_id: str | None = None,  # Firm identity from the token claim (bd polyglot-pdf-xwlt)
	is_reconnect: bool = False,  # True when handshake carries resume:true (mid-section reconnect)
	# The CLIENT-LINK jti, when this session was opened with a magic link
	# (bd polyglot-pdf-ugm6). None for a staff session. Passed explicitly
	# rather than read from an outer scope -- the decoded claims live in
	# fill_form_from_schema, a DIFFERENT function, and reaching for them here
	# is a NameError at runtime that no import check catches.
	link_jti: str | None = None,
	# The staff member who SENT the link (bd polyglot-pdf-ugm6). Rides the
	# session records so a CLIENT session satisfies the telemetry requirement
	# -- firm, form, AND originating employee -- with no account anywhere.
	# Contractually None for a staff session -- see log_form_session_start's
	# docstring ("they are their own originator"). Do NOT widen this one for
	# usage-event attribution; use usage_employee_id below instead.
	link_employee_id: str | None = None,
	# Usage-event employee attribution ONLY (bd polyglot-pdf-cjifh, E3.2
	# live-voice plumbing) -- DISTINCT from link_employee_id above. A client
	# session carries the same value as link_employee_id (the link's
	# employee_id); a STAFF session carries the staff uid here instead of
	# None, so a live-voice usage event always attributes to a person. See the
	# caller (fill_form_from_schema) for the derivation.
	usage_employee_id: str | None = None,
) -> None:
	log = _log.bind(session_id=session_id, form_session_id=form_session_id)
	
	# Build system instruction BEFORE starting session
	# System instruction goes in Gemini config
	system_instruction = None
	
	# Store resume flag on the service so send_initiating_message can select
	# the correct template (bd polyglot-pdf-vmxx).
	service._is_resume_session = is_reconnect

	# Seed the spoken language from the handshake BEFORE start_session (bd
	# polyglot-pdf-y25o): start_session derives the per-connect transcription
	# language bias from service._spoken_language, and the client's
	# change_spoken_language announcement only arrives after session_ready.
	# Leave the service default ("English") untouched when the client omits it.
	if spoken_language:
		service._spoken_language = spoken_language

	if schema:
		# Update schema with fill_language
		service.update_schema(schema, current_values or {}, fill_language)

		# Seed the section metadata on the service so the DTI initiating message's
		# form/section metadata block (bd polyglot-pdf-uogm) has a source at SESSION
		# START -- not just after a section switch (which sets it at
		# _switch_to_section_locked). Sourced from the handshake, NOT schema["manifest"]
		# (bd polyglot-pdf-fu1h F1). Also benefits restart_gemini_session, which already
		# reads _last_section_metadata. Navigation state only -- no field values.
		service._last_section_metadata = {
			"section_id": section_id,
			"section_number": section_number,
			"total_sections": total_sections,
			"section_label": section_label,
			"previous_spoken_names": previous_spoken_names or [],
		}

		# Build full form context system instruction
		# Phase 3: Include section metadata
		# EXPERIMENTAL: Pass next_field_hint to system instruction for initiation directive
		system_instruction = service.build_form_context_message(
			schema,
			current_values or {},
			section_number=section_number,
			section_label=section_label,
			total_sections=total_sections,
			previous_spoken_names=previous_spoken_names,
			next_field_hint=initial_field_hint
		)
		
		# Removed verbose logging - just track session start below
	
	# Idle-watchdog activity timestamp (bd polyglot-pdf-l3a.4). A 1-element list so
	# the watchdog, the receive loop, AND the user-activity callback all mutate the
	# SAME value without nonlocal threading across the callback boundary.
	# CRITICAL: this is reset on MEANINGFUL activity only -- control messages and a
	# real user turn -- NOT on raw inbound audio frames, so a walk-away with the mic
	# open still times out instead of burning Gemini's 15-min audio session.
	# Under push-to-talk (the only input mode, bd polyglot-pdf-v1m8g) the turn
	# brackets arrive as CONTROL messages, which is what bumps this.
	last_rx = [time.time()]

	# Register the user-activity callback BEFORE start_session so it is wired into
	# the adapter during set_callbacks. Fired when Gemini transcribes a real user
	# utterance (see live_ai_gemini on_user_activity) -- a secondary liveness source;
	# the PTT control brackets are the primary one. No PHI crosses here -- it only
	# bumps the liveness clock.
	def _on_user_activity_sync():
		last_rx[0] = time.time()

	async def _on_user_activity():
		_on_user_activity_sync()

	service._on_user_activity = _on_user_activity

	# Start session with system instruction
	# This accepts WebSocket and starts Gemini connection
	await service.start_session(
		websocket,
		session_id,
			send_transcript=send_transcript,
			accept_connection=accept_connection,
			schema=schema,  # Form schema for AI context
			full_schema=full_schema,  # Full-form catalog for the secretary (bd polyglot-pdf-p68s)
			current_values=current_values,  # Pre-filled values for reconnect
			system_instruction=system_instruction,  # Include in initial Gemini config
			form_session_id=form_session_id,  # Persistent ID from frontend
			kit_id=kit_id,  # Kit identity for the audit trail (bd polyglot-pdf-47r3)
			firm_id=firm_id,  # Firm identity for per-firm telemetry (bd polyglot-pdf-xwlt)
			current_section_id=section_id,  # Current section for token-log context (bd polyglot-pdf-tb7)
			# Usage-event attribution (bd polyglot-pdf-cjifh, E3.2 live-voice
			# plumbing). link_jti already existed on THIS function's own
			# signature (see the module comment above it) but was never
			# threaded past this call. employee_id here is usage_employee_id,
			# NOT link_employee_id -- the usage event needs a person for BOTH
			# session shapes (staff uid when there is no link), while
			# link_employee_id stays reserved for the confirmation-audit
			# "who sent the link" meaning (None for staff; see that param's
			# docstring above).
			link_jti=link_jti,
			employee_id=usage_employee_id,
		)

	# DTI field-1 opener (epic polyglot-pdf-13w7, bd polyglot-pdf-j748): the static
	# DTI SI carries no field data, so field 1's guidance must ride the initiating
	# message. That opener is driven by the CLIENT, not a server-side trigger here:
	# after the disclaimer the client tears down + re-handshakes (switchToFirstSection
	# -> startSection), and handleSessionReady auto-sends `change_spoken_language`
	# with the user's SPOKEN language + the computeNextField-selected hint, which
	# calls service.send_initiating_message (it renders field-1 guidance from the
	# hint's field_id). A server-side trigger here would (a) fire BEFORE the
	# disclaimer is read on the initial connect, (b) double up with the client opener
	# on reconnect, and (c) use fill_language as the spoken language -- so it is
	# deliberately absent (Codex PR #254).

	# Session-start telemetry (bd polyglot-pdf-xwlt). These two functions
	# shipped with bd z2is but had NEVER been called; this is their first
	# caller. Guarded on form_session_id like the confirmation records are --
	# without it there is no session key to correlate on. A RECONNECT
	# deliberately does not re-log a start: form_session_id survives
	# reconnects, so re-logging would inflate a per-firm session count with
	# what is one session to the user.
	if should_log_session_start(form_session_id, is_reconnect):
		log_form_session_start(
			form_id=_form_number_of(schema),
			form_session_id=form_session_id,
			section_id=section_id,
			firm_id=firm_id,
			kit_id=kit_id,
			# The START row is the ONE-PER-SESSION record, so it needs the
			# join key MORE than the end row does (which fires per
			# connection). Omitting it here left a client who abandons
			# mid-form with a start row the firm cannot join on -- while the
			# docs claimed both records carried it (Opus cross-surface r2).
			link_jti=link_jti,
			employee_id=link_employee_id,
		)

	# Set when the client reports the WHOLE form confirmed (the form_complete
	# message below), so the session-end record can say "completed" honestly
	# instead of guessing from a socket close (bd polyglot-pdf-xwlt). Bound at
	# FUNCTION scope, not inside the try: the finally reads it on every exit
	# path, including one that fails before the try is entered.
	session_completed = False

	try:
		# Flag to drop audio during section switch
		drop_audio = False

		# Start watchdog to close connection after idle timeout.
		# (get_settings is imported at module scope; do NOT re-import it function-locally
		# -- that shadows the module name for the whole function and UnboundLocalErrors
		# any earlier reference -- bd polyglot-pdf-j748.)
		local_settings = get_settings()
		idle_timeout = local_settings.WS_IDLE_TIMEOUT_SEC

		async def watchdog_task():
			while True:
				await asyncio.sleep(5)  # Check every 5 seconds
				if time.time() - last_rx[0] > idle_timeout:
					log.warning("websocket_idle_timeout",
					           idle_seconds=int(time.time() - last_rx[0]),
					           timeout_threshold=idle_timeout)
					try:
						# Send idle_timeout message to frontend (graceful shutdown)
						# This tells frontend to stop auto-reconnecting and show "Reconnect" button
						await websocket.send_json({
							"type": "idle_timeout",
							"idle_seconds": int(time.time() - last_rx[0]),
							"message": "Connection timed out due to inactivity"
						})
						# Give frontend time to receive message before closing
						await asyncio.sleep(0.5)
						# Close WebSocket with idle timeout code
						await websocket.close(code=1000, reason="Idle timeout")
					except Exception as e:
						log.warning("idle_timeout_cleanup_error", error=str(e))
					break
		
		watchdog = asyncio.create_task(watchdog_task())

		# W1 (bd polyglot-pdf-xbl2): the validator now runs OFF the receive loop.
		# A validation trigger acks the client immediately and spins the actual
		# flash-lite pass into a tracked background task; the receive loop never
		# awaits it, so a slow/hung validator adds ZERO voice-turn latency. Tasks
		# are tracked so they can be cancelled on disconnect (a lingering task must
		# not push to a closed socket).
		validation_tasks: set[asyncio.Task] = set()

		async def _run_validation_and_push(
			windows: list, result_type: str
		) -> None:
			"""Background runner: validate the window batch, then push ONE
			`validation_result` envelope. Fail-OPEN and CRASH-SAFE -- every
			exception (incl. the validator's own) is caught + logged here so a
			background-task failure can NEVER propagate into the receive loop
			(exit criterion 3). A send to an already-closed socket is swallowed
			(the client is gone; nothing to deliver)."""
			try:
				verdict = await service.handle_validation_windows(windows)
				# Envelope shape is UNCHANGED from the shipped B5 contract
				# ({type, conflicts}) -- W1 changed WHEN this is pushed (async, after
				# the ack), not its shape. `result_type` is a LOG label only, never
				# put on the wire (validation-delegation.md contract 1 is pinned).
				await websocket.send_json({
					"type": "validation_result",
					"conflicts": verdict.get("conflicts", []),
				})
			except Exception as exc:  # noqa: BLE001 -- background task must never crash the loop
				_log.warning(
					"async_validation_task_failed",
					result_type=result_type,
					exc_type=type(exc).__name__,
					session_id=session_id,
				)

		def _spawn_validation(windows: list, result_type: str) -> None:
			"""Fire-and-forget the validation runner, tracked for disconnect
			cleanup. The done-callback discards the task from the set so it does
			not leak; exceptions are already handled inside the runner."""
			task = asyncio.create_task(_run_validation_and_push(windows, result_type))
			validation_tasks.add(task)
			task.add_done_callback(validation_tasks.discard)

		async def _run_drain_and_push(conflicts: list) -> None:
			"""W3 (bd polyglot-pdf-pr3i): background runner for the finding-driven
			drain. Composes + injects ONE steer for the client's queued conflicts,
			then pushes a `drain_findings_result` carrying the DELIVERED conflicts so
			the client marks those fields steered + consumes them from its queue.
			Crash-safe + fail-OPEN like the validation runner: any exception is caught
			+ logged so it can never propagate into the receive loop, and an
			un-delivered steer (dead session) reports [] so the client keeps the
			finding queued to retry.

			ALWAYS pushes a drain_findings_result, even on an exception in
			handle_drain_findings (delivered=[] then). The client's drainInFlight guard
			only clears on this result, so a missing result would stall the client's
			queue until reconnect (Opus outer-review finding). If handle_drain_findings
			raised, the result is empty -> the client keeps the finding queued to retry
			but is unblocked. The send itself failing (dead socket) is fine: the client
			is gone and a reconnect re-arms the guard."""
			delivered: list = []
			try:
				verdict = await service.handle_drain_findings(conflicts)
				delivered = verdict.get("conflicts", []) if isinstance(verdict, dict) else []
			except Exception as exc:  # noqa: BLE001 -- background task must never crash the loop
				_log.warning(
					"async_drain_task_failed",
					exc_type=type(exc).__name__,
					session_id=session_id,
				)
			try:
				await websocket.send_json({
					"type": "drain_findings_result",
					"conflicts": delivered,
				})
			except Exception as exc:  # noqa: BLE001 -- a dead-socket send must not crash the loop
				_log.warning(
					"async_drain_result_send_failed",
					exc_type=type(exc).__name__,
					session_id=session_id,
				)

		def _spawn_drain(conflicts: list) -> None:
			task = asyncio.create_task(_run_drain_and_push(conflicts))
			validation_tasks.add(task)
			task.add_done_callback(validation_tasks.discard)

		async def _run_pro_complete_and_push(fields: list) -> None:
			"""W6 (bd polyglot-pdf-gbus): background runner for the whole-form
			gemini-2.5-pro pass at form_complete. Pushes the SAME report-only
			`validation_result` envelope the client already consumes, so the pro
			conflicts ride the existing validatorFindingsQueue -> drain_findings ->
			steer path with ZERO client changes. Crash-safe + fail-open: no pro wired
			(flag off) returns clean, and any exception is caught + logged so it can
			never propagate into the receive loop."""
			try:
				verdict = await service.handle_form_complete_pro(fields)
				await websocket.send_json({
					"type": "validation_result",
					"conflicts": verdict.get("conflicts", []),
				})
			except Exception as exc:  # noqa: BLE001 -- background task must never crash the loop
				_log.warning(
					"async_pro_complete_task_failed",
					exc_type=type(exc).__name__,
					session_id=session_id,
				)

		def _spawn_pro_complete(fields: list) -> None:
			task = asyncio.create_task(_run_pro_complete_and_push(fields))
			validation_tasks.add(task)
			task.add_done_callback(validation_tasks.discard)

		while True:
			msg = await websocket.receive()

			if isinstance(msg, dict) and msg.get("type") == "websocket.disconnect":
				break

			if "bytes" in msg and msg["bytes"] is not None:
				# NOTE (bd polyglot-pdf-l3a.4): inbound audio frames deliberately do
				# NOT bump the idle clock: counting audio as activity would make the
				# idle timeout un-fireable on a walk-away with an open mic. The
				# watchdog resets on a real user turn and on the control messages
				# below -- which is where push-to-talk's activity brackets arrive --
				# not on raw mic bytes.
				# Drop audio frames during section switch to avoid backlog
				if drop_audio:
					continue
				# Process audio in background to avoid blocking control messages
				audio_bytes = msg["bytes"]
				# Log first audio frame to verify flow (throttle to avoid spam)
				if 'first_audio_logged' not in locals():
					_log.info("[mic] [WebSocket] First audio frame received", bytes=len(audio_bytes))
					first_audio_logged = True
				asyncio.create_task(service.stream_audio(audio_bytes))
				continue

			# Any non-audio message (control/text: ping, form_state, hint, etc.) is
			# explicit client interaction -> bump the idle clock (bd polyglot-pdf-l3a.4).
			last_rx[0] = time.time()

			if "text" in msg and msg["text"] is not None:
				try:
					obj = json.loads(msg["text"]) if msg["text"] else {}
				except Exception:
					obj = {}

				mtype = obj.get("type")
				
				if mtype == "ping":
					await websocket.send_json({"type": "pong", "ts": obj.get("ts")})
				elif mtype == "stats":
					await websocket.send_json({"type": "stats", "message": "ok"})
				elif mtype == "form_state":
					fields = obj.get("fields")
					if not isinstance(fields, list):
						await websocket.send_json({"type": "error", "code": "invalid_form_state", "reason": "fields_list_required"})
					else:
						result = service.update_form_state(fields)
						# Note: Backend doesn't return form_state - client is source of truth
						await websocket.send_json({
							"type": "form_state_ack",
							"applied_fields": result.get("applied_fields", []),
						})
					continue
				elif mtype == "next_field_hint":
					# Frontend sends next field hint after computing navigation
					# Backend forwards this to Gemini as a text message
					hint_text = obj.get("hint")
					if not hint_text or not isinstance(hint_text, str):
						await websocket.send_json({"type": "error", "code": "invalid_hint", "reason": "hint_text_required"})
					else:
						# Forward hint to Gemini via service
						await service.send_context_hint(hint_text)
						await websocket.send_json({"type": "hint_ack"})
					continue
				elif mtype == "form_state_response":
					# Frontend responds to get_form_state request from backend
					request_id = obj.get("request_id")
					field_values = obj.get("field_values", {})
					if not request_id:
						await websocket.send_json({"type": "error", "code": "invalid_response", "reason": "request_id_required"})
					else:
						service.handle_form_state_response(request_id, field_values)
						# No acknowledgment needed - this completes the async request cycle
					continue
				elif mtype == "next_field_hint_response":
					# Frontend responds to get_next_field_hint request from backend
					request_id = obj.get("request_id")
					hint = obj.get("hint")  # Can be None if form is complete
					# DTI (bd polyglot-pdf-jnjj.22): the client may also send the next
					# field's FULL schema (it owns the schema; the backend does not).
					# Absent for legacy/non-DTI clients -> None, no behavior change.
					next_field_schema = obj.get("next_field_schema")
					if not request_id:
						await websocket.send_json({"type": "error", "code": "invalid_response", "reason": "request_id_required"})
					else:
						service.handle_next_field_hint_response(request_id, hint, next_field_schema)
						# No acknowledgment needed - this completes the async request cycle
					continue
				elif mtype == "confirm_field_response":
					# Frontend responds to a confirm_field request: whether it actually
					# recorded the confirmation (bd polyglot-pdf-wpw.2 / WS-E2).
					request_id = obj.get("request_id")
					recorded = obj.get("recorded", False)
					reason = obj.get("reason")  # fixed category token (e.g. "no_value"), never PII
					# True only when this confirm completed the section, so the FE is
					# tearing down the socket for switchToSection -- the backend skips the
					# doomed next-field-hint round-trip (bd polyglot-pdf-njvh).
					section_complete = bool(obj.get("section_complete", False))
					if not request_id:
						await websocket.send_json({"type": "error", "code": "invalid_response", "reason": "request_id_required"})
					else:
						try:
							service.handle_confirm_field_response(request_id, bool(recorded), reason, section_complete)
						except Exception as e:
							# Log the exception TYPE, not str(e): an exception string can embed
							# PII and this reaches Cloud Logging in production (the p84m principle,
							# applied uniformly -- fresh-eyes PR #141).
							_log.error("confirm_field_response_handling_failed", error_type=type(e).__name__, request_id=request_id)
						# No acknowledgment needed - this completes the async request cycle
					continue
				elif mtype == "skip_field_response":
					# Frontend responds to a skip_field request: whether it recorded the
					# skip (markFieldSkipped, bd polyglot-pdf-7yra). Same ack shape as
					# confirm_field_response so a section-completing skip advances too.
					request_id = obj.get("request_id")
					recorded = obj.get("recorded", False)
					reason = obj.get("reason")  # fixed category token, never PII
					section_complete = bool(obj.get("section_complete", False))
					if not request_id:
						await websocket.send_json({"type": "error", "code": "invalid_response", "reason": "request_id_required"})
					else:
						try:
							service.handle_skip_field_response(request_id, bool(recorded), reason, section_complete)
						except Exception as e:
							_log.error("skip_field_response_handling_failed", error_type=type(e).__name__, request_id=request_id)
						# No acknowledgment needed - this completes the async request cycle
					continue
				elif mtype == "switch_field_response":
					# Frontend responds to a switch_field request (field-level
					# navigation, bd polyglot-pdf-jnjj.36): found + the outcome
					# keys (field_id/hint/schema on success; a fixed reason
					# token on failure). The whole payload minus type/request_id
					# rides to the coordinator; values inside are never logged.
					request_id = obj.get("request_id")
					if not request_id:
						await websocket.send_json({"type": "error", "code": "invalid_response", "reason": "request_id_required"})
					else:
						payload = {k: v for k, v in obj.items()
						           if k not in ("type", "request_id")}
						try:
							service.handle_switch_field_response(request_id, payload)
						except Exception as e:
							_log.error("switch_field_response_handling_failed", error_type=type(e).__name__, request_id=request_id)
						# No acknowledgment needed - this completes the async request cycle
					continue
				elif mtype == "spellback_response":
					# Frontend responds to a spellback request (bd polyglot-pdf-22h1f):
					# the deterministic spell-back clip's outcome (delivered /
					# interrupted / error + timing). Carries no field value in
					# either direction.
					request_id = obj.get("request_id")
					if not request_id:
						await websocket.send_json({"type": "error", "code": "invalid_response", "reason": "request_id_required"})
					else:
						payload = {k: v for k, v in obj.items()
						           if k not in ("type", "request_id")}
						try:
							service.handle_spellback_response(request_id, payload)
						except Exception as e:
							_log.error("spellback_response_handling_failed", error_type=type(e).__name__, request_id=request_id)
						# No acknowledgment needed - this completes the async request cycle
					continue
				elif mtype == "manual_field_update":
					# Frontend notifies backend when user manually edits a field
					# Backend forwards this to Gemini to keep context synchronized
					field_id = obj.get("field_id")
					field_name = obj.get("field_name")
					value = obj.get("value")
					next_field_hint = obj.get("next_field_hint")  # Optional hint for next field
					# DTI (bd polyglot-pdf-ezg2): the next field's schema rides along so the
					# backend can re-establish the current-field coercion pointer + the
					# validation entry (a manual edit skips the confirm_field round-trip
					# that normally carries it). Optional; absent from legacy clients.
					next_field_schema = obj.get("next_field_schema")
					if not field_id or field_name is None:
						await websocket.send_json({"type": "error", "code": "invalid_update", "reason": "field_id_and_name_required"})
					else:
						await service.send_manual_field_update(field_id, field_name, value, next_field_hint,
						                                       next_field_schema=next_field_schema)
						# No acknowledgment needed - fire-and-forget notification
					continue
				elif mtype == "read_disclaimer":
					# Frontend sends this when user first selects language
					# Backend sends disclaimer message to Gemini using the proven initiating message pattern
					spoken_language = obj.get("spoken_language")
					disclaimer_text = obj.get("disclaimer_text", "")

					if not spoken_language or not isinstance(spoken_language, str):
						await websocket.send_json({"type": "error", "code": "invalid_language", "reason": "spoken_language_required"})
					else:
						try:
							if not disclaimer_text:
								_log.warning("missing_disclaimer_text", session_id=session_id)
								disclaimer_text = "Please read the disclaimer."

							# Translated on-screen agree-button label (bd polyglot-pdf-s863);
							# optional -- the service falls back to 'I Agree' when absent.
							agree_button_label = obj.get("agree_button_label")
							await service.send_disclaimer_message(
								spoken_language, disclaimer_text,
								agree_button_label=agree_button_label)
							await websocket.send_json({"type": "disclaimer_read_initiated", "language": spoken_language})
							_log.info("disclaimer_read_initiated", session_id=session_id, language=spoken_language)
						except Exception as e:
							_log.error("read_disclaimer_failed", session_id=session_id, error=str(e))
							await websocket.send_json({"type": "error", "code": "disclaimer_read_failed", "message": str(e)})
					continue
				elif mtype == "completion_message":
					# Frontend sends completion message for prompts that should trigger Gemini response
					# (e.g., form completion goodbyes)
					completion_text = obj.get("message")
					if not completion_text or not isinstance(completion_text, str):
						await websocket.send_json({"type": "error", "code": "invalid_completion", "reason": "message_required"})
					else:
						# Use send_prompt which calls send_client_content() to trigger Gemini response
						# This is different from send_context_hint which just adds context without expecting response
						await service.send_prompt(completion_text)
						await websocket.send_json({"type": "completion_ack"})
					continue
				elif mtype == "recovery_prompt":
					# Frontend sends recovery prompt when conversation stalls (activity watchdog)
					# Backend translates level + optional next_field_hint into configured prompt
					level = obj.get("level")  # 1, 2, or 3
					next_field_hint = obj.get("next_field_hint")  # Optional, for level 1
					
					if not level or not isinstance(level, int) or level not in (1, 2, 3):
						await websocket.send_json({"type": "error", "code": "invalid_recovery_prompt", "message": "Invalid level (must be 1, 2, or 3)"})
					else:
						try:
							# Send recovery prompt via service
							await service.send_recovery_prompt(level, next_field_hint)
							await websocket.send_json({"type": "recovery_prompt_ack"})
						except Exception as e:
							_log.error("recovery_prompt_failed", error=str(e), level=level)
							await websocket.send_json({"type": "error", "code": "recovery_prompt_failed", "message": str(e)})
					continue
				elif mtype == "voice_mode":
					# Manual/voice mode toggle (bd polyglot-pdf-wurj8). "manual"
					# suppresses the model's proactive speech while the session
					# stays live and the mic stays usable; "voice" restores it.
					# An unrecognised value is treated as VOICE: the failure mode
					# of a silent assistant is a user who thinks the app is
					# broken, so a malformed toggle must not be able to mute.
					mode = obj.get("mode")
					if mode not in ("manual", "voice"):
						await websocket.send_json({"type": "error", "code": "invalid_voice_mode", "reason": "mode_must_be_manual_or_voice"})
					else:
						service.set_voice_muted(mode == "manual")
						await websocket.send_json({"type": "voice_mode_ack", "mode": mode})
					continue
				elif mtype == "vad_activity_start":
					# Frontend VAD detected user started speaking
					# Send activity_start signal before audio chunks
					_log.info("[mic] [WebSocket] Received vad_activity_start from frontend", session_id=session_id)
					# A PTT press is an unambiguous request FOR the assistant, so it
					# leaves manual mode without the user hunting for the toggle (bd
					# polyglot-pdf-wurj8, exit criterion 2). Done BEFORE
					# send_activity_start so the turn the user is opening is not the
					# one still being suppressed. The client flips its own toggle to
					# match; this is the authoritative half.
					service.set_voice_muted(False)
					await service.send_activity_start()
					# No acknowledgment needed - fire-and-forget signal
					continue
				elif mtype == "vad_activity_end":
					# Frontend VAD detected user stopped speaking
					# Send activity_end signal to flush Gemini's audio buffer
					_log.info("[mic-off] [WebSocket] Received vad_activity_end from frontend", session_id=session_id)
					await service.send_activity_end()
					# No acknowledgment needed - fire-and-forget signal
					continue
				elif mtype == "clear_thinking":
					# Frontend's thinking-indicator max-duration safety timer fired (bd
					# polyglot-pdf-wpw.5, Codex PR #273): the reply never arrived, so the
					# client cleared its own UI. Reset the backend processing state too,
					# or it would stay stuck True and DEDUP the next turn's
					# processing:true (the two-sided desync Codex flagged). Fire-and-forget.
					await service.clear_processing_state()
					continue
				elif mtype == "change_fill_language":
					# Frontend requests to change the language used for filling form fields
					new_language = obj.get("language")
					if not new_language or not isinstance(new_language, str):
						await websocket.send_json({"type": "error", "code": "invalid_language", "reason": "language_string_required"})
					else:
						# Update fill language and notify Gemini
						await service.change_fill_language(new_language)
						await websocket.send_json({"type": "language_changed", "language": new_language})
					continue
				elif mtype == "change_spoken_language":
					# MISNOMER, kept for wire compatibility: this does NOT switch the
					# session's language. The spoken language is PINNED for the whole
					# form -- chosen once before the form starts, carried into the
					# per-connect Gemini config + SI, and held for every turn; changing
					# it requires a NEW session ("clear form" -> language modal). See
					# docs/standards/voice-and-vad.md ("the spoken language is pinned
					# per session") and bd polyglot-pdf-87a9.
					#
					# The ONLY live sender is the frontend's reconnect opener, which
					# RE-ASSERTS the same pinned language after a socket teardown (a
					# section switch or reconnect drops the Gemini session). So the work
					# here is re-establishing the language + current field on a fresh
					# Gemini session, which is exactly what the initiating message does.
					spoken_language = obj.get("spoken_language")
					next_field_hint = obj.get("next_field_hint")
					if not spoken_language or not isinstance(spoken_language, str):
						await websocket.send_json({"type": "error", "code": "invalid_spoken_language", "reason": "spoken_language_string_required"})
					elif not next_field_hint or not isinstance(next_field_hint, str):
						await websocket.send_json({"type": "error", "code": "invalid_next_field_hint", "reason": "next_field_hint_required"})
					else:
						try:
							# Send initiating message to Gemini
							await service.send_initiating_message(spoken_language, next_field_hint)
							await websocket.send_json({"type": "spoken_language_changed", "language": spoken_language})
							_log.info("spoken_language_changed",
							         session_id=session_id,
							         spoken_language=spoken_language)
						except Exception as e:
							_log.error("change_spoken_language_failed", session_id=session_id, error=str(e))
							await websocket.send_json({"type": "error", "code": "spoken_language_change_failed", "message": str(e)})
					continue
				elif mtype == "end_gemini_session":
					# Frontend requests to close Gemini session (Level 3 farewell)
					# Backend closes Gemini connection but keeps WebSocket alive
					_log.info("end_gemini_session_requested", session_id=session_id)
					await service.finalize_gemini_session()
					await websocket.send_json({"type": "gemini_session_ended"})
					_log.info("gemini_session_ended", session_id=session_id)
					continue
				elif mtype == "restart_gemini_session":
					# Frontend requests to restart Gemini session (reconnect after Level 3)
					# Backend restarts Gemini with existing schema/values
					# Frontend should include next_field_hint for smooth progression
					next_field_hint = obj.get("next_field_hint")
					_log.info("restart_gemini_session_requested", 
					         session_id=session_id,
					         has_hint=bool(next_field_hint))
					try:
						await service.restart_gemini_session(next_field_hint=next_field_hint)
						await websocket.send_json({"type": "gemini_session_restarted"})
						_log.info("gemini_session_restarted", session_id=session_id)
					except Exception as e:
						_log.error("restart_gemini_session_failed", session_id=session_id, error=str(e))
						await websocket.send_json({"type": "error", "code": "restart_failed", "message": str(e)})
					continue
				elif mtype == "section_info_response":
					# Frontend responds with section info for section switching
					drop_audio = False  # Resume processing audio
					request_id = obj.get("request_id")
					section_info = obj.get("section_info")
					_log.info("section_info_response_received", 
					         request_id=request_id, 
					         has_section_info=bool(section_info),
					         session_id=session_id)
					if request_id and section_info:
						service.handle_section_info_response(request_id, section_info)
					else:
						_log.warning("section_info_response_invalid", 
						           has_request_id=bool(request_id),
						           has_section_info=bool(section_info),
						           session_id=session_id)
					# No acknowledgment needed - async request/response pattern
					continue
				elif mtype == "manual_section_switch":
					# Frontend manually triggers section switch (user clicked in UI)
					drop_audio = True  # Stop processing audio during section switch
					identifier = obj.get("identifier")
					section_info = obj.get("section_info")  # Embedded info (no round-trip needed)
					_log.info("manual_section_switch_received", 
					         identifier=identifier, 
					         has_embedded_info=bool(section_info),
					         session_id=session_id)
					if identifier and section_info:
						try:
							# Use embedded section info to switch immediately
							result = await service.switch_to_section(
								section_schema=section_info["schema"],
								section_values=section_info["current_values"],
								section_metadata=section_info["metadata"],
								initial_field_hint=section_info.get("initial_field_hint"),
							)
							_log.info("manual_section_switch_completed", 
							         identifier=identifier, 
							         session_id=session_id,
							         success=True)
							drop_audio = False  # Resume audio processing
						except Exception as e:
							drop_audio = False  # Resume audio even on error
							_log.error("manual_section_switch_failed", identifier=identifier, session_id=session_id, error=str(e))
							import traceback
							_log.error("manual_section_switch_traceback", traceback=traceback.format_exc())
							await websocket.send_json({"type": "error", "code": "section_switch_failed", "message": str(e)})
					else:
						drop_audio = False  # Resume audio if invalid request
						_log.warning("manual_section_switch_missing_data", 
						           has_identifier=bool(identifier),
						           has_section_info=bool(section_info),
						           session_id=session_id)
					# No acknowledgment needed - backend will send section_switched when complete
					continue
				elif mtype == "section_completed":
					# Frontend auto-detected that all fields in the section are
					# confirmed, marked the section complete, and advanced. (There is
					# no backend complete_section tool; the frontend drives this.)
					next_section = obj.get("next_section")
					_log.info("section_completed_response", 
					         next_section=next_section,
					         session_id=session_id)
					# Acknowledge receipt (optional - frontend doesn't wait for this)
					await websocket.send_json({"type": "section_completed_ack"})
					continue
				elif mtype == "section_complete":
					# B4 (bd polyglot-pdf-jnjj.16) emits this when the last field of the
					# current section is confirmed; it carries section_id + the contract-2
					# `fields` payload (validation-delegation.md). W1 (bd polyglot-pdf-xbl2)
					# moved the validator OFF the receive loop: ack IMMEDIATELY, spin the
					# flash-lite pass into a tracked background task, and let it push the
					# `validation_result` envelope when it lands (a one-window batch). The
					# receive loop no longer awaits the validator, so a slow/hung pass adds
					# zero voice-turn latency. W3 (bd polyglot-pdf-pr3i) made that result
					# REPORT-ONLY: it does NOT inject a steer and does NOT set the steered
					# markers here -- the client ENQUEUES the surviving conflicts and drains
					# them via `drain_findings` (which composes+injects). The FE gate
					# (VALIDATOR_GATE_TIMEOUT_MS) still fails open if the async result is
					# slow/absent and resolves on an arriving clean result. Distinct from
					# the legacy reactive `section_completed`.
					proactive_section_id = obj.get("section_id")
					proactive_fields = obj.get("fields", [])
					# PII (contract 6): log the COUNT only -- NEVER `fields`/values.
					_log.info(
						"section_complete_received",
						section_id=proactive_section_id,
						field_count=len(proactive_fields) if isinstance(proactive_fields, list) else 0,
						session_id=session_id,
					)
					_spawn_validation([proactive_fields], "section_complete")
					await websocket.send_json({"type": "section_complete_ack"})
					continue
				elif mtype == "form_complete":
					# B4 (bd polyglot-pdf-jnjj.16) emits this once when the whole form is
					# confirmed (re-emitted after a post-completion edit). Carries the
					# WHOLE-form contract-2 payload. W6 (bd polyglot-pdf-gbus): form_complete
					# is the SOLE end-of-form report -- it runs the whole-form gemini-2.5-pro
					# pass (catching cross-page far pairs the lite windows miss), NOT the lite
					# window pass. Ack immediately + run the pro pass in the background; it
					# pushes the REPORT-ONLY `validation_result` envelope (W3 shape) so the
					# conflicts ride the existing enqueue -> drain_findings -> steer path.
					# The pro pass no-ops (clean) when FORM_COMPLETE_PRO_VALIDATOR is off, so
					# this is a safe fallback; the flag DEFAULTS ON since 2026-08-03. COST: the client's
					# maybeEmitFormComplete dirty-snapshot guard only re-emits on a real value
					# change, so a static complete form never re-fires the pro spend.
					proactive_fields = obj.get("fields", [])
					# PII (contract 6): log the COUNT only -- NEVER `fields`/values.
					_log.info(
						"form_complete_received",
						field_count=len(proactive_fields) if isinstance(proactive_fields, list) else 0,
						session_id=session_id,
					)
					session_completed = True  # bd polyglot-pdf-xwlt
					_spawn_pro_complete(proactive_fields)
					await websocket.send_json({"type": "form_complete_ack"})
					continue
				elif mtype == "validate_windows":
					# W1 (bd polyglot-pdf-xbl2): the async STRIDE validator trigger. W2
					# (bd polyglot-pdf-kxkw) emits this from the client on the confirm/skip/
					# edit seam, carrying the OVERLAPPING windows (size ~20, stride ~10 over
					# SCHEMA FIELD ORDER) whose fields have all SETTLED. PAGE-AGNOSTIC
					# (report-cadence revision 2026-07-13): the client keys the trigger on
					# schema order + the settled flags, NEVER pdf_position.page, so a
					# source:"web" / pageless form emits identically to a paginated one.
					# Ack immediately, then run every window's flash-lite pass concurrently
					# in the background, dedupe conflicts across the batch by field-id set,
					# suppress already-steered markers, and push the surviving conflicts as
					# a `validation_result`. W3 (bd polyglot-pdf-pr3i): this is REPORT-ONLY
					# -- it does NOT inject the steer. The client ENQUEUES the surviving
					# conflicts and drains them via `drain_findings` (below), which composes
					# + injects. Nothing in the voice path waits on any of it.
					windows = obj.get("windows", [])
					safe_windows = windows if isinstance(windows, list) else []
					# PII (contract 6): log COUNTS only -- never the windows/values.
					_log.info(
						"validate_windows_received",
						window_count=len(safe_windows),
						field_count=sum(
							len(w) for w in safe_windows if isinstance(w, list)
						),
						session_id=session_id,
					)
					_spawn_validation(safe_windows, "validate_windows")
					await websocket.send_json({"type": "validate_windows_ack"})
					continue
				elif mtype == "drain_findings":
					# W3 (bd polyglot-pdf-pr3i): the FINDING-DRIVEN drain. The client sends
					# this the moment its validatorFindingsQueue is non-empty, carrying the
					# queued conflicts (each with field_ids, reason, field_names) it wants
					# voiced. Ack immediately, then compose + inject ONE steer in the
					# background and push a `drain_findings_result` with the DELIVERED
					# conflicts so the client marks them steered + consumes them from the
					# queue. An un-delivered steer (dead session) reports [] so the client
					# keeps the finding queued to retry. Nothing in the voice path waits.
					drain_conflicts = obj.get("conflicts", [])
					safe_conflicts = drain_conflicts if isinstance(drain_conflicts, list) else []
					# PII (contract 6): COUNT only -- never the conflicts/reasons/values.
					_log.info(
						"drain_findings_arm_received",
						conflict_count=len(safe_conflicts),
						session_id=session_id,
					)
					_spawn_drain(safe_conflicts)
					await websocket.send_json({"type": "drain_findings_ack"})
					continue
				elif mtype == "client_diagnostic":
					# One-way, PII-free client-side diagnostics (bd polyglot-pdf-xp4q:
					# the field-1 opener skipped silently in every observed real-auth
					# live session, and nothing server-side could say WHICH of the
					# client's gate conditions failed). WHITELIST the fields -- the
					# payload is raw client input, so nothing outside these named,
					# coerced keys may reach the log line (no-PII policy; same rule
					# as the unknown-field-id redaction in validation_handler.py).
					# No ack: the client fires and forgets.
					# STRICT token allowlist for the one non-boolean field: str() on a
					# dict/list would render its CONTENT verbatim (an {"event":
					# {"ssn": ...}} payload fits under any length cap), so only known
					# literal tokens pass; everything else logs as "invalid" (Opus
					# outer review finding).
					_diag_event = obj.get("event")
					if _diag_event not in ("field1_opener_skipped", "section_switch_watchdog_timeout"):
						_diag_event = "invalid"
					_log.warning(
						"client_diagnostic",
						diagnostic_event=_diag_event,
						was_section_switch=bool(obj.get("was_section_switch")),
						disclaimer_accepted=bool(obj.get("disclaimer_accepted")),
						has_selected_language=bool(obj.get("has_selected_language")),
						has_next_field_hint=bool(obj.get("has_next_field_hint")),
						# Disambiguates the benign completed-form reconnect (hint
						# correctly empty) from a genuinely broken opener.
						is_form_complete=bool(obj.get("is_form_complete")),
						# In-memory vs persisted disclaimer flag: a divergence
						# names the state-staleness hypothesis in one glance.
						storage_disclaimer_accepted=bool(obj.get("storage_disclaimer_accepted")),
						# Which scoping applies to has_next_field_hint (section
						# vs whole-form) -- mode context for reading the line.
						continuous_session=bool(obj.get("continuous_session")),
						session_id=session_id,
					)
					continue
				else:
					# Log unknown message type for debugging
					_log.warning("unknown_control_message_type",
					           message_type=mtype,
					           session_id=session_id,
					           available_keys=list(obj.keys()) if isinstance(obj, dict) else None)
					await websocket.send_json({"type": "error", "code": "unknown_control"})
					continue

			# If we get here, message was neither bytes nor text
			await websocket.send_json({"type": "error", "code": "bad_frame"})
	except WebSocketDisconnect:
		pass
	finally:
		watchdog.cancel()
		# W1 (bd polyglot-pdf-xbl2): cancel any in-flight async validation tasks so
		# a lingering pass does not try to push to a closed socket after teardown.
		# `validation_tasks` may be unbound if we failed before the receive loop set
		# it up (e.g. an early handshake error) -- guard with locals().
		for task in list(locals().get("validation_tasks", ())):
			task.cancel()
		# Session-end telemetry (bd polyglot-pdf-xwlt). Fires on EVERY
		# connection teardown, including the disconnect that precedes a
		# reconnect -- deliberately, because at teardown the backend cannot
		# know whether this is the end of the form or the middle of a
		# reconnect: the protocol has no terminal-close signal, and
		# is_reconnect describes the CONNECTION THAT JUST OPENED, not the one
		# closing (gating on it logged a false "abandoned" for the connection
		# that reconnected AND dropped the real end record -- fresh-eyes
		# round 1).
		#
		# So the record carries the truth instead of guessing it:
		# completion_status is "completed" only on an explicit client
		# form_complete, and `connection_ended` marks these as per-CONNECTION
		# rows. A per-firm SESSION count is therefore a distinct-count over
		# form_session_id (the id survives reconnects), never a row count --
		# stated in standards/confirmation-and-audit.md so the query is
		# written correctly.
		if should_log_session_end(form_session_id, is_reconnect):
			try:
				log_form_session_end(
					link_jti=link_jti,
					employee_id=link_employee_id,
					form_id=_form_number_of(schema),
					form_session_id=form_session_id,
					completion_status="completed" if session_completed else "abandoned",
					total_fields_confirmed=service.confirmed_field_count(),
					firm_id=firm_id,
					kit_id=kit_id,
				)
			except Exception as e:
				log.error("session_end_telemetry_failed", error=str(e))

		# BURN THE LINK -- but only on a real completion (bd polyglot-pdf-ugm6,
		# fresh-eyes r1 finding 2). Nothing called complete_link before this,
		# so a link could never actually become "used" and the one-time
		# guarantee could never take effect.
		#
		# ONLY on session_completed, deliberately: a dropped connection, a
		# closed laptop, or a client coming back after lunch must NOT consume
		# their one chance at the form. Abandoning is the common case on a
		# 40-minute immigration form, and burning the link there would strand
		# a client mid-intake with no recourse but to phone the firm.
		# complete_link is best-effort by design -- failing to RECORD a
		# completion costs at most one extra reopen of a form already
		# finished, while failing to BLOCK an open costs a second paid
		# session, so the risky direction is the one that refuses.
		if session_completed and link_jti:
			try:
				await asyncio.to_thread(complete_link, link_jti)
			except Exception as e:
				log.error("link_complete_failed", jti=link_jti, error=str(e))

		# BANK THIS CONNECTION'S SPEND against the link (bd polyglot-pdf-ik7e).
		# On EVERY teardown, not only a completed one: the expensive case is
		# precisely the client who keeps reconnecting, and skipping the
		# abandoned ones would let an unbounded session hide behind reconnects.
		#
		# Read the cost BEFORE end_session() -- ending the session is what
		# finalises the adapter, and reading after it would race the teardown
		# for the number we are trying to record.
		await _bank_link_spend(link_jti, service, log)

		await service.end_session()


from ..services.auth import verify_token
from ..services.link_tokens import LinkTokenError, verify_link_token
from ..services.link_redemptions import (
	LinkAlreadyUsed,
	LinkWindowElapsed,
	RedemptionUnavailable,
	complete_link,
	enforce_link_redemption,
)
from ..services.link_spend import (
	LinkBudgetExhausted,
	check_budget,
	record_spend,
)
from ..services.link_budget import (
	KIT_COST_CEILING_KEY,
	cost_ceiling_usd_for_claims,
)
from ..services import links_store as _links_store


def _mirror_budget_exhausted(jti) -> None:
	"""Best-effort TELEMETRY mirror on links[_<channel>]/{jti}.status, written
	when a socket tears down on LinkBudgetExhausted (Epic 2 bead A5, plan:
	"Socket teardown on LinkBudgetExhausted writes the budget_exhausted
	mirror").

	NO LEDGER ENTRY here, on purpose: whether a budget-exhausted link earns a
	refund, and whether a client's REPLACEMENT link (bd polyglot-pdf-1uyof)
	costs a fresh credit, are both maintainer pricing calls the plan lists as
	undecided (Epic 2's "Maintainer calls needed before the marked beads
	ship" -- "recommendation: no refund, replacement costs a credit"). Until
	that lands, this write only updates the `status` field the admin console
	and a firm's link listing read; it never touches balance_credits or the
	ledger, and credit_ledger.refund_expired_link() never runs from here.

	READ-BEFORE-WRITE, ON PURPOSE: this must NEVER create a links doc. The
	mint-route rewrite that calls links_store.record_mint() (Track A bead A3,
	polyglot-pdf-jecrl) has not landed, so today NOTHING writes a links doc
	before this mirror can run -- and .set(..., merge=True) on a missing doc
	CREATES it (google-genai vendored SDK: document.py's merge docstring is
	explicit that merge creates when the document does not exist). An
	orphan doc here would have no expire_at, so the TTL policy
	(scripts/setup-firestore-ttl.sh) never reaps it, AND it would carry
	status=budget_exhausted forever -- a status the A3 "open requires a mint
	record" gate (plan: refuse when the record is missing or
	revoked/refunded, allow every other status through) would read as an
	extant, non-revoked record for a jti that was never actually minted.
	Skip silently (not an error -- no record existing is the expected case
	pre-A3, and is a plain "nothing to mirror" case even after) when there
	is no existing doc to update.

	NEVER RAISES, and never blocks the close it runs alongside. A failure to
	write a status label used only for a listing must not affect the socket
	teardown that is already in flight for a real reason (the client hit
	their spend ceiling); the close proceeds either way.

	Runs on the SAME sync Admin SDK write path links_store.py already uses --
	callers on the event loop must wrap it in asyncio.to_thread, exactly like
	every other Firestore call on this route.
	"""
	if not isinstance(jti, str) or not jti:
		return
	try:
		doc_ref = _links_store._collection().document(jti)
		snap = doc_ref.get()
		if not snap.exists:
			return
		doc_ref.set(
			{"status": _links_store.STATUS_BUDGET_EXHAUSTED}, merge=True)
	except Exception as exc:  # noqa: BLE001 -- telemetry only, never raises
		_log.error("link_budget_exhausted_mirror_failed", jti=jti,
					error=str(exc))


async def _bank_link_spend(link_jti, service, log) -> float:
	"""Add this CONNECTION's AI spend to the link's running total.

	Extracted from the teardown so it can be tested directly: the teardown
	itself lives inside a receive loop, and a test that drives the whole loop
	to reach it proves less about this logic than it costs to build. Returns
	the banked amount (0.0 when nothing was banked) so a caller -- or a test --
	can see what happened.

	Called on EVERY teardown, not only a completed one: the expensive case is
	precisely the client who keeps reconnecting, and skipping abandoned
	sessions would let an unbounded session hide behind reconnects.

	Must run BEFORE end_session(): ending the session finalises the adapter,
	and reading the cost after would race the teardown for the number.

	Never raises. Accounting must not break a teardown -- record_spend is
	already best-effort internally, and this catches the READ too.
	"""
	if not link_jti:
		return 0.0          # staff session: no link, nothing to bank
	try:
		ai = getattr(service, "live_ai", None)
		cost = 0.0
		if ai is not None and hasattr(ai, "session_cost_usd"):
			cost = float(ai.session_cost_usd() or 0.0)
		if cost > 0:
			await asyncio.to_thread(record_spend, link_jti, cost)
			return cost
		return 0.0
	except Exception as e:
		log.error("link_spend_record_failed", jti=link_jti, error=str(e))
		return 0.0


def _verify_ws_credential(token: str) -> dict:
	"""Resolve a WS credential to claims: a client LINK token or a staff
	Firebase ID token (bd polyglot-pdf-ugm6).

	Returns a claims dict either way. For a link, the claims are the ones WE
	signed -- firm_id, kit_id, employee_id, jti -- so the telemetry
	requirement (firm + form + originating employee) is satisfied for client
	sessions without the client ever holding an account.

	Dispatch is on SHAPE, not on a caller-supplied hint: a link token has one
	dot, a Firebase JWT has two. A caller cannot opt into the weaker check by
	labelling their token, and a Firebase JWT can never be parsed as a link.
	Raises on failure, which the caller turns into a 1008 close.
	"""
	if isinstance(token, str) and token.count(".") == 1:
		payload = verify_link_token(token)   # raises LinkTokenError
		claims = {
			"uid": None,                     # a client has NO account
			"firm_id": payload["firm_id"],
			"link_kit_id": payload["kit_id"],
			"employee_id": payload["employee_id"],
			"jti": payload["jti"],
			"cw": payload["cw"],          # completion window, enforced at the socket
			"is_client_link": True,
		}
		# cap_usd IS OPTIONAL on the payload (bd polyglot-pdf-ah5d3 / A4) --
		# only carried through when the token actually has one, so
		# cost_ceiling_usd_for_claims sees a claims dict shaped exactly like
		# the verified payload (no synthetic `cap_usd: None` that would need
		# its own carve-out downstream).
		if "cap_usd" in payload:
			claims["cap_usd"] = payload["cap_usd"]
		return claims
	return verify_token(token)

@router.websocket("/fill")
async def fill_form_from_schema(
	websocket: WebSocket,
	token: str = Query(...),
	send_transcript: bool = Query(default=False),
	service = Depends(get_form_filling_service),
):
	"""
	Stateless web form filling endpoint.
    ...
	"""
	# Debug aid (bd polyglot-pdf-2m9): allow forcing input/output transcription on
	# via env without a frontend change, so the dev log captures what Gemini HEARD
	# from the user's audio. Only RAISES the flag (never lowers a query=true), and
	# is a no-op in prod (env unset). Safe for native-audio: enable_transcripts only
	# adds *_audio_transcription config, never response_modalities=TEXT (which 1007s).
	if not send_transcript and os.getenv("SEND_TRANSCRIPT", "false").lower() == "true":
		send_transcript = True

	log = _log.bind(endpoint="fill_from_schema")
	
	try:
		# Verify Auth Token
		try:
			# KEEP the decoded claims: the firm_id custom claim (bd
			# polyglot-pdf-lo88) rides this verification, and the telemetry
			# below keys session + confirmation records on it (bd
			# polyglot-pdf-xwlt). Discarding the return value was why the
			# WS path could not see firm identity at all.
			#
			# TWO CREDENTIAL KINDS REACH THIS SOCKET (bd polyglot-pdf-ugm6):
			# a firm STAFF member's Firebase ID token, or a CLIENT's signed
			# magic-link token. A client has no Firebase account and must
			# never have one, so without this branch the client tier could
			# not open the voice socket at all -- the feature would be
			# unreachable in exactly the case it exists for.
			#
			# The two formats are structurally distinct (a link token has ONE
			# dot, a Firebase JWT has two), so neither verifier can silently
			# accept the other's token. We try the LINK shape first and only
			# by that shape; anything else goes to Firebase verification
			# unchanged. Both paths end with claims we SIGNED or Firebase
			# signed -- the handshake is never trusted for identity.
			#
			# NO check_revoked ON THE STAFF PATH (kept from #644, and
			# _verify_ws_credential's Firebase branch is a plain
			# verify_token(token) for exactly this reason). check_revoked
			# forces a Firebase USER-RECORD FETCH needing
			# firebaseauth.users.get -- a permission polyglot-backend-sa
			# deliberately does NOT have, so deployed, EVERY handshake failed
			# with INSUFFICIENT_PERMISSION and the app could not connect at
			# all. It is STRUCTURALLY INVISIBLE locally and in tests:
			# VFF_DISABLE_AUTH returns earlier, and every test stubs the
			# Firebase SDK, so the failure exists only against real Firebase
			# with the real service account. Cost of dropping it: revoking an
			# account takes effect when its token expires (up to an hour)
			# rather than immediately -- the maintainer chose that over
			# widening the deployed backend's permissions (2026-08-26).
			claims = _verify_ws_credential(token)
		except Exception as e:
			# Distinguish "not enrolled" from "bad token". This diff INTRODUCED
			# the enrolment requirement, so collapsing both into
			# "Authentication failed" would leave someone locked out of an app
			# they can sign into, with nothing pointing at the remedy
			# (scripts/bootstrap_voice_dev.py). Same 401-vs-403 distinction the
			# HTTP side draws, carried onto the surface where it actually bites.
			not_enrolled = getattr(e, "status_code", None) == 403
			log.warning("websocket_auth_failed", error=str(e),
						not_enrolled=not_enrolled)
			reason = ("This account is not enrolled for the voice application"
					  if not_enrolled else "Authentication failed")
			await websocket.close(code=1008, reason=reason)
			return

		await websocket.accept()
	except RuntimeError as e:
		# WebSocket already in wrong state (likely already accepted/closed)
		log.error("websocket_accept_failed", error=str(e))
		return
	
	try:
		first_frame = await websocket.receive_text()
	except WebSocketDisconnect:
		return
	except Exception as e:
		log.error("handshake_failed", error=str(e))
		try:
			await websocket.send_json({"type": "error", "code": "invalid_handshake", "reason": "text_required"})
			await websocket.close(code=1003)
		except:
			pass
		return

	try:
		handshake = json.loads(first_frame)
	except json.JSONDecodeError as e:
		log.error("json_decode_failed", error=str(e))
		await websocket.send_json({"type": "error", "code": "invalid_handshake", "reason": "json_decode"})
		await websocket.close(code=1007)
		return

	if not isinstance(handshake, dict):
		log.error("handshake_not_object", type=type(handshake).__name__)
		await websocket.send_json({"type": "error", "code": "invalid_handshake", "reason": "not_object"})
		await websocket.close(code=1007)
		return

	# Extract handshake data.
	# The manifest-first TRANSPORT ("handshake_jit") vs the legacy full-schema
	# handshake. The "jit" name is historical -- this transport is DTI's carrier,
	# NOT the removed JIT SI mode (bd polyglot-pdf-en2j): the backend builds a
	# minimal per-section schema from the manifest, and ai_context renders the DTI
	# static SI (or legacy full-SI when USE_DTI is off) from it.
	handshake_type = handshake.get("type", "handshake")
	is_jit_mode = handshake_type == "handshake_jit"

	# Extract persistent form session ID (frontend-managed, survives reconnects)
	form_session_id = handshake.get("form_session_id")
	# Kit identity for the audit trail (bd polyglot-pdf-47r3). Read at the SHARED
	# scope, not inside the JIT branch: kit_id identifies the KIT (not the form),
	# so unlike form_number/edition_date it is not a form_metadata key and cannot
	# ride the schema dict -- both transports thread it separately. Two kits can
	# share a form_number (a standard W-7 and a firm-specific variant), and only
	# kit_id distinguishes them in the confirmation record.
	kit_id = handshake.get("kit_id")
	# Firm identity comes from the verified TOKEN, never the handshake: the
	# handshake is client-controlled, and a firm id a client could type is
	# not an identity (bd polyglot-pdf-xwlt). isinstance-guarded because the
	# dev-bypass stub and any legacy account carry no firm claim.
	_firm_claim = claims.get("firm_id") if isinstance(claims, dict) else None
	firm_id = _firm_claim if isinstance(_firm_claim, str) and _firm_claim else None

	# A CLIENT LINK NAMES ONE FORM (bd polyglot-pdf-ugm6). The handshake's
	# kit_id is client-controlled, so a link holder who edits it could
	# otherwise fill a DIFFERENT form of the same firm -- including one they
	# were never sent. Enforce the token's kit_id over the handshake's, and
	# refuse rather than silently substituting: a mismatch means the client is
	# not filling the form they were given, and quietly swapping it would
	# produce a record naming a form the client never saw.
	if isinstance(claims, dict) and claims.get("is_client_link"):
		# REDEEM VIA THE SHARED GATE (bd polyglot-pdf-ugm6). This block used to
		# hand-roll the redemption + completion-window checks, and
		# require_auth hand-rolled nothing at all -- so the HTTP door accepted
		# a burned link for the rest of its ~48h exp (Opus cross-surface r1).
		# ONE helper now serves both doors: two copies of a security check
		# drift, and the drift is silent.
		try:
			await asyncio.to_thread(enforce_link_redemption, claims)
		except (LinkAlreadyUsed, LinkWindowElapsed, RedemptionUnavailable) as exc:
			# Same refusal for already-used, window-closed, store-
			# unreachable, and NO USABLE MINT RECORD: the socket must not
			# be an oracle either, and an unreachable store FAILS CLOSED
			# (the guarded failure is a replayed link starting a second
			# paid session).
			#
			# The mint-record refusal (bd polyglot-pdf-jecrl) arrives here
			# as LinkNotMinted, a SUBCLASS of RedemptionUnavailable, so
			# this tuple already catches it -- deliberately, so the
			# socket's paid gate could not be left admitting a revoked
			# link by an omission at this one call site.
			log.warning("ws_link_redeem_refused", jti=claims.get("jti"),
						error=str(exc))
			await websocket.close(code=1008, reason="Authentication failed")
			return

		# SPEND CEILING (bd polyglot-pdf-ik7e). Checked HERE -- after the
		# link is proven valid, before any Gemini session exists -- because the
		# point is to refuse the session, not to discover afterwards that it
		# should have been refused.
		#
		# A DISTINCT close code and reason, deliberately NOT the 1008
		# "Authentication failed" above: a client who used their allowance has
		# a perfectly good link, and telling them authentication failed sends
		# them to the firm with the wrong problem. 1013 ("try again later") is
		# the honest code, and the reason token is on the wire for a client
		# that wants to branch on it.
		#
		# The frontend BRANCHES ON THE REASON (bd polyglot-pdf-cke6v, shipped):
		# webFormConnection.handleClose returns early on "budget_exhausted",
		# setting a terminal status of the same name -- no retries -- and the
		# overlay shows a modal with no RECOVERY action. "budget_unavailable" is
		# deliberately NOT matched there: it means THIS spend store was
		# unreachable, which IS transient, so it keeps the ordinary retry path.
		# The two tokens are matched by STRING COMPARE across the wire, with no
		# shared constant, so renaming either one here silently restores the old
		# broken behavior -- keep them in step with that branch.
		#
		# The client keeps everything else: retrieval never redeems, so their
		# download, print and preview still work and they can finish the
		# remaining fields by typing (maintainer, 2026-08-27).
		#
		# THE TOKEN'S OWN CEILING, NOT A PER-CONNECT KIT READ (bd
		# polyglot-pdf-ah5d3 / A4, closing polyglot-pdf-4tjt7). Precedence is
		# token `cap_usd` > the global default, and NOTHING ELSE:
		# `cost_ceiling_usd_for_claims` reads the claim A3's mint route
		# resolves once (from the kit's price commercial) and signs into the
		# token, so a per-connect Firestore kit load is never needed --
		# after the open-requires-a-mint-record cutover, every token that can
		# reach this line already carries `cap_usd` for a kit that has one.
		# A token minted before that (or for a kit with no resolvable
		# ceiling) carries no claim and falls through to the global, the same
		# safe default a malformed value gets.
		#
		# Two kits declare a per-form ceiling today (w7 and i-90 at $3, bd
		# polyglot-pdf-gob8l), but A3 -- the mint-time resolve-from-kit-
		# metadata step that would actually put `cap_usd` on their tokens --
		# is still open and blocked by this bead. Until A3 lands, w7/i-90
		# links carry no `cap_usd` claim and stay bounded by the $10 global,
		# exactly like any other uncapped token.
		#
		# `check_budget`'s own parameter is `kit_metadata` (it calls
		# `cost_ceiling_usd_for_kit` under the KIT_COST_CEILING_KEY name) --
		# reusing that SAME key here, with the value already resolved by
		# `cost_ceiling_usd_for_claims`, means check_budget's re-parse is a
		# no-op idempotent pass over an already-good number rather than a
		# second, divergent resolution path.
		#
		# BOTH resolved inside the SAME to_thread call (Opus cross-surface,
		# bd polyglot-pdf-ah5d3 finding 1). `cost_ceiling_usd_for_claims`
		# falls through to `default_cost_ceiling_usd()` for every token until
		# A3 lands, which on a cold runtime_config cache (45s TTL) is a
		# blocking sync Admin-SDK Firestore read -- the exact hazard
		# link_routes.py:141-147 and auth.py:293-296 document for this same
		# runtime_config call. Calling it directly on the event loop (as
		# opposed to inside the thread below, where check_budget's own
		# resolution already lived pre-A4) would stall every OTHER concurrent
		# request on this Cloud Run instance, in-flight audio included, for
		# every token that has no cap_usd claim.
		def _resolve_ceiling_and_check_budget() -> float:
			ceiling_usd = cost_ceiling_usd_for_claims(claims)
			return check_budget(
				claims.get("jti"), {KIT_COST_CEILING_KEY: ceiling_usd},
				firm_id=claims.get("firm_id"),
			)

		try:
			await asyncio.to_thread(_resolve_ceiling_and_check_budget)
		except LinkBudgetExhausted as exc:
			log.warning("ws_link_budget_exhausted", jti=claims.get("jti"),
						firm_id=claims.get("firm_id"), error=str(exc))
			# Best-effort TELEMETRY mirror only (bd polyglot-pdf-1op3g / A5) --
			# no ledger entry, no refund. Off the event loop for the same
			# reason every other Firestore call on this route is: a sync
			# Admin SDK write on the shared Cloud Run loop would stall every
			# concurrent connection. Never awaited for success -- a failed
			# mirror write must not delay or block the close below.
			await asyncio.to_thread(_mirror_budget_exhausted, claims.get("jti"))
			await websocket.close(code=1013, reason="budget_exhausted")
			return
		except RedemptionUnavailable as exc:
			# FAILS CLOSED, same polarity as the redemption gate: if we cannot
			# tell how much this link has spent, we do not start an unbounded
			# paid session on it.
			log.warning("ws_link_budget_unavailable", jti=claims.get("jti"),
						error=str(exc))
			await websocket.close(code=1013, reason="budget_unavailable")
			return

		_link_kit = claims.get("link_kit_id")
		if isinstance(kit_id, str) and kit_id and kit_id != _link_kit:
			log.warning("ws_link_kit_mismatch", link_kit_id=_link_kit,
						handshake_kit_id=kit_id, jti=claims.get("jti"))
			await websocket.close(code=1008, reason="Authentication failed")
			return
		# Absent/blank handshake kit_id: the token's is authoritative anyway.
		kit_id = _link_kit

	if is_jit_mode:
		# Manifest-first transport: extract the manifest + first field schema.
		manifest = handshake.get("manifest")
		first_field_schema = handshake.get("first_field_schema")
		loaded_field_ids = handshake.get("loaded_field_ids", [])
		# Form title rides on the manifest-first handshake so {form_title} in the
		# legacy SI is the real form, not the literal "Form" (bd polyglot-pdf-jnjj.9,
		# gap O: the minimal schema dict has no form_metadata, so ai_context fell
		# back to "Form").
		jit_form_title = handshake.get("form_title")
		# The form NUMBER ("W-7") is what the confirmation audit trail logs as
		# form_id (bd polyglot-pdf-n0em). It rides the handshake separately from
		# the human-facing title because the minimal JIT schema has no
		# form_metadata to derive it from -- without it every confirmation event
		# recorded form_id="unknown" and the liability record could not name the
		# form. An older client that omits the key still degrades to "unknown".
		jit_form_number = handshake.get("form_number")
		# The government EDITION for the audit trail (bd polyglot-pdf-47r3): a
		# form NUMBER does not say which revision the client confirmed against,
		# and agencies revise forms and enforce edition dates. Rides the
		# handshake for the same reason form_number does -- the minimal JIT
		# schema has no form_metadata to derive it from.
		# (kit_id is NOT read here: it identifies the KIT rather than the form,
		# so it is not a form_metadata key and is read once at the shared scope
		# above, where BOTH transports can thread it.)
		jit_edition_date = handshake.get("edition_date")

		# Build minimal schema from manifest for validation
		# The manifest contains field_id|spoken_name pairs, we'll use it for context
		schema = {
			"source": "web",
			"fields": [first_field_schema] if first_field_schema else [],
			"manifest": manifest,  # Store manifest for JIT context building
			"loaded_field_ids": loaded_field_ids,
			"jit_mode": True,
			# Copy parts array from manifest for section list building
			"parts": manifest.get("parts", []) if manifest else []
		}
		# Carry the form title through form_metadata so ai_context.build_form_context
		# renders it unchanged (same key the legacy full-schema path uses).
		# form_number rides the same dict so the confirmation audit trail's
		# schema.form_metadata.form_number lookup resolves on this transport too
		# (bd polyglot-pdf-n0em) -- built even when only one of the two is present.
		# edition_date joins them so the audit trail can name the EDITION the
		# client actually confirmed against (bd polyglot-pdf-47r3). kit_id is
		# NOT a form_metadata key -- it identifies the kit, not the form -- so it
		# is threaded separately below.
		if jit_form_title or jit_form_number or jit_edition_date:
			schema["form_metadata"] = {}
			if jit_form_title:
				schema["form_metadata"]["title"] = jit_form_title
			if jit_form_number:
				schema["form_metadata"]["form_number"] = jit_form_number
			if jit_edition_date:
				schema["form_metadata"]["edition_date"] = jit_edition_date
		# manifest_field_count reads the REAL section field list
		# (manifest.current_section.fields), not a non-existent top-level
		# manifest.fields that always logged 0 (gap E).
		_jit_section_fields = (
			(manifest.get("current_section") or {}).get("fields", []) if manifest else []
		)
		log.info("jit_handshake_received",
		         manifest_field_count=len(_jit_section_fields),
		         has_first_field=bool(first_field_schema),
		         has_form_title=bool(jit_form_title),
		         parts_count=len(manifest.get("parts", [])) if manifest else 0)
	else:
		# Legacy mode: Full schema provided
		schema = handshake.get("schema")
		if not schema or not isinstance(schema, dict):
			log.error("schema_missing_or_invalid", schema_type=type(schema).__name__)
			await websocket.send_json({"type": "error", "code": "invalid_schema", "reason": "schema_required"})
			await websocket.close(code=1007)
			return

	current_values = handshake.get("current_values") or {}
	fill_language = handshake.get("fill_language", "English")  # Default to English

	# The user's app-start SPOKEN language choice (bd polyglot-pdf-y25o). Needed
	# at handshake time -- before the Gemini connect -- because the transcription
	# language bias is per-connect Live config; the change_spoken_language message
	# the client auto-sends after session_ready arrives too late for that.
	# Optional: an older client that omits it gets no ASR bias (None -> service
	# keeps its "English" default for SI purposes only once the client announces).
	spoken_language = handshake.get("spoken_language")
	if not isinstance(spoken_language, str) or not spoken_language.strip():
		spoken_language = None

	# Full-form schema for the secretary catalog (bd polyglot-pdf-p68s / jnjj.45d).
	# `schema` above is the per-section schema that drives the live-model SI; the
	# secretary needs the WHOLE form (all parts/sections/fields). The client sends
	# it on every (re)connect handshake; the backend caches it in-session (schema
	# only, no PII -- the stateless invariant holds, it is rebuilt from the
	# handshake on reconnect). Optional: a legacy/older client that omits it leaves
	# the secretary falling back to the per-section schema.
	full_schema = handshake.get("full_schema")
	if not isinstance(full_schema, dict):
		full_schema = None

	# Extract section metadata (schema-agnostic)
	section_id = handshake.get("section_id")  # Section ID from schema (e.g., "part_1_2_addresses")
	section_number = handshake.get("section_number")  # Section order number (1-indexed)
	section_label = handshake.get("section_label")  # Display label
	total_sections = handshake.get("total_sections")
	previous_spoken_names = handshake.get("previous_spoken_names") or []

	# Extract initial field hint (computed by frontend before connection)
	initial_field_hint = handshake.get("initial_field_hint")  # Can be None if form is complete

	# Resume flag: True when the frontend is reconnecting mid-section (not a fresh start).
	# Suppresses the greeting/section-intro in send_initiating_message (bd polyglot-pdf-vmxx).
	is_reconnect = bool(handshake.get("resume", False))

	source = str(schema.get("source") or "web").lower().strip() or "web"
	# Accept both "web" and "pdf" sources - PDF schemas can be voice-filled via web interface
	if source not in ("web", "pdf"):
		log.error("invalid_source", source=source)
		await websocket.send_json({"type": "error", "code": "invalid_schema", "reason": "source_must_be_web_or_pdf"})
		await websocket.close(code=1008)
		return

	# Generate session ID for logging correlation only
	# Connection-scoped, not persisted server-side
	import secrets
	ephemeral_id = f"web_{secrets.token_urlsafe(8)}"
	log = log.bind(
		session_id=ephemeral_id,
		form_session_id=form_session_id,  # Persistent ID from frontend (survives reconnects)
		field_count=len(schema.get("fields", [])),
		has_prefilled=bool(current_values),
		fill_language=fill_language,
		section_id=section_id,
		section_number=section_number,
		total_sections=total_sections,
		is_reconnect=is_reconnect,
	)
	log.info("web_session_starting",
	         ephemeral_id=ephemeral_id,
	         form_session_id=form_session_id,
	         is_reconnect=is_reconnect)

	print(f"\n{'='*80}")
	print(f"[session] NEW FORM SESSION")
	print(f"{'='*80}")
	print(f"Form Session ID: {form_session_id}")
	print(f"Ephemeral ID: {ephemeral_id}")
	print(f"Section: {section_id} ({section_number}/{total_sections}) - {section_label}")
	print(f"Manifest-first transport: {is_jit_mode}")
	print(f"Resume: {is_reconnect}")
	print(f"{'='*80}\n")

	# Acknowledge handshake
	await websocket.send_json({
		"type": "session_ready",
		"session_id": ephemeral_id,
		"ephemeral": True,  # Signal to client this is stateless
		# DTI uses the manifest-first handshake shape (manifest + first_field_schema),
		# so signal jit_mode when DTI is on so the frontend builds that handshake. The
		# jit_mode_enabled flag names the manifest-first TRANSPORT, which survives the
		# JIT SI-mode removal (bd polyglot-pdf-en2j); the JIT SI mode itself is gone.
		# dti_mode_enabled additionally tells the client to send each next field's full
		# schema on next_field_hint_response (bd polyglot-pdf-jnjj.22).
		"jit_mode_enabled": settings.USE_DTI,  # Signal manifest-first handshake transport
		"dti_mode_enabled": settings.USE_DTI,  # Signal Dynamic Turn Injection (client supplies next-field schema)
		# Continuous-session mode (bd polyglot-pdf-x8rt): tell the client to build a
		# single whole-form handshake and stop advancing sections, so the whole form
		# runs as one compression-bounded session.
		"continuous_session_enabled": settings.CONTINUOUS_SESSION,
		# NOTE: `native_vad` is GONE from this payload (bd polyglot-pdf-v1m8g).
		# It told the client whether Gemini's own VAD was driving turns; that mode
		# no longer exists, so there is nothing to signal -- push-to-talk is the
		# only input mode and the client always brackets turns with manual
		# activity signals. The client-side reader was removed in the same change.
	})

	# Start form filling session with schema and current values
	await _handle_fill_session(
		websocket,
		ephemeral_id,
		service,
		send_transcript,
		accept_connection=False,
		schema=schema,  # Form schema for AI context
		full_schema=full_schema,  # Full-form catalog for the secretary (bd polyglot-pdf-p68s)
		current_values=current_values,  # Pre-filled values for reconnect
		fill_language=fill_language,  # Language for AI to use
		spoken_language=spoken_language,  # App-start language choice for the ASR bias (bd polyglot-pdf-y25o)
		section_id=section_id,  # Current section ID for token-log context (bd polyglot-pdf-tb7)
		section_number=section_number,  # Phase 3: Current section
		section_label=section_label,  # Phase 3: Section label
		total_sections=total_sections,  # Phase 3: Total sections
		previous_spoken_names=previous_spoken_names,  # Phase 3: Completed sections lookup
		initial_field_hint=initial_field_hint,  # Computed by frontend before connection
		form_session_id=form_session_id,  # Persistent ID from frontend (survives reconnects)
		kit_id=kit_id,  # Kit identity for the confirmation audit trail (bd polyglot-pdf-47r3)
		firm_id=firm_id,  # Firm identity from the token claim (bd polyglot-pdf-xwlt)
		is_reconnect=is_reconnect,  # Suppresses greeting on mid-section reconnect (bd polyglot-pdf-vmxx)
		# The client-link jti, so a COMPLETED session burns the link
		# (bd polyglot-pdf-ugm6). None for a staff session.
		link_jti=(claims.get("jti")
				  if isinstance(claims, dict) and claims.get("is_client_link")
				  else None),
		link_employee_id=(claims.get("employee_id")
						  if isinstance(claims, dict)
						  and claims.get("is_client_link")
						  else None),
		# Usage-event employee attribution ONLY (bd polyglot-pdf-cjifh) --
		# DISTINCT from link_employee_id above, which is the confirmation-audit
		# "who SENT the link" field and is contractually None for a staff
		# session (log_form_session_start's docstring: "they are their own
		# originator"). The usage event has a different requirement: BOTH
		# session shapes must attribute to a person, so a staff session's usage
		# events carry the STAFF UID here while the audit trail's
		# link_employee_id stays None for that same session. A client-link
		# session carries the same value on both (its employee_id IS the
		# link's employee_id either way).
		usage_employee_id=(claims.get("employee_id")
						   if isinstance(claims, dict) and claims.get("is_client_link")
						   else (claims.get("uid") or claims.get("sub"))
						   if isinstance(claims, dict)
						   else None),
	)
