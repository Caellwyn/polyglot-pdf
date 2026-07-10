from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
import json
import asyncio
import os
import time
from ..config import get_settings
from ..dependencies import get_form_filling_service
from ..utils.dev_file_logger import DEV_LOGGING_ENABLED
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
	section_id: str | None = None,  # Current section ID (for token-log context, bd polyglot-pdf-tb7)
	section_number: int | None = None,  # Phase 3: Current section (1-indexed)
	section_label: str | None = None,  # Phase 3: Section label
	total_sections: int | None = None,  # Phase 3: Total sections
	previous_spoken_names: list | None = None,  # Phase 3: Spoken names from completed sections
	initial_field_hint: str | None = None,  # Initial field hint from frontend (pre-computed)
	form_session_id: str | None = None,  # Persistent form session ID from frontend
	is_reconnect: bool = False,  # True when handshake carries resume:true (mid-section reconnect)
) -> None:
	log = _log.bind(session_id=session_id, form_session_id=form_session_id)
	
	# Build system instruction BEFORE starting session
	# System instruction goes in Gemini config
	system_instruction = None
	
	# Store resume flag on the service so send_initiating_message can select
	# the correct template (bd polyglot-pdf-vmxx).
	service._is_resume_session = is_reconnect

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
	# the watchdog, the receive loop, AND the native-VAD user-activity callback all
	# mutate the SAME value without nonlocal threading across the callback boundary.
	# CRITICAL: this is reset on MEANINGFUL activity only -- control messages and a
	# real user turn -- NOT on raw inbound audio frames. In native VAD mode the
	# client streams continuous audio incl. silence, so resetting on audio bytes
	# would mean a walk-away with the mic open never times out and burns Gemini's
	# 15-min audio session. Background noise streams as audio but does NOT produce
	# a native-VAD input transcription, so it does not keep the session alive.
	last_rx = [time.time()]

	# Register the user-activity callback BEFORE start_session so it is wired into
	# the adapter during set_callbacks. Fired when Gemini's native VAD transcribes a
	# real user utterance (see live_ai_gemini on_user_activity). No PHI crosses here
	# -- it only bumps the liveness clock.
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
			current_section_id=section_id,  # Current section for token-log context (bd polyglot-pdf-tb7)
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
		
		while True:
			msg = await websocket.receive()

			if isinstance(msg, dict) and msg.get("type") == "websocket.disconnect":
				break

			if "bytes" in msg and msg["bytes"] is not None:
				# NOTE (bd polyglot-pdf-l3a.4): inbound audio frames deliberately do
				# NOT bump the idle clock. In native VAD mode the client streams
				# continuous audio incl. silence, so counting audio as activity made
				# the idle timeout un-fireable on a walk-away. The watchdog now resets
				# on a real user turn (the native-VAD on_user_activity callback) and on
				# control messages below -- not on raw mic bytes.
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
				elif mtype == "field_value_response":
					# Frontend responds to a previous get_field_value request from backend
					request_id = obj.get("request_id")
					value = obj.get("value")
					found = obj.get("found", False)
					if not request_id:
						await websocket.send_json({"type": "error", "code": "invalid_response", "reason": "request_id_required"})
					else:
						# Synchronous handler will resolve the waiting future in the service
						try:
							service.handle_field_value_response(request_id, value, bool(found))
						except Exception as e:
							_log.error("field_value_response_handling_failed", error=str(e), request_id=request_id)
					# No acknowledgment needed - completes async cycle
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

							await service.send_disclaimer_message(spoken_language, disclaimer_text)
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
				elif mtype == "vad_activity_start":
					# Frontend VAD detected user started speaking
					# Send activity_start signal before audio chunks
					_log.info("[mic] [WebSocket] Received vad_activity_start from frontend", session_id=session_id)
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
					# Frontend requests to change the spoken conversation language
					# Backend sends initiating message to Gemini to switch language and greet user
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
					# `fields` payload (validation-delegation.md). B5 (jnjj.17) runs the
					# cheap-model validator over `fields`, injects a steer into the Live
					# session on a surviving conflict, and pushes a `validation_result`
					# envelope to the client for EVERY boundary (incl. clean) -- the
					# deterministic clean->resume signal the FE switch-gate needs
					# (contract 1). Distinct from the legacy reactive `section_completed`.
					proactive_section_id = obj.get("section_id")
					proactive_fields = obj.get("fields", [])
					# PII (contract 6): log the COUNT only -- NEVER `fields`/values.
					_log.info(
						"section_complete_received",
						section_id=proactive_section_id,
						field_count=len(proactive_fields) if isinstance(proactive_fields, list) else 0,
						session_id=session_id,
					)
					verdict = await service.handle_validation_boundary(proactive_fields)
					await websocket.send_json({
						"type": "validation_result",
						"conflicts": verdict.get("conflicts", []),
					})
					await websocket.send_json({"type": "section_complete_ack"})
					continue
				elif mtype == "form_complete":
					# B4 (bd polyglot-pdf-jnjj.16) emits this once when the whole form is
					# confirmed (re-emitted after a post-completion edit). Carries the
					# WHOLE-form contract-2 payload. B5 (jnjj.17) runs the full-form
					# validator pass + pushes the `validation_result` envelope (there is
					# no section switch to gate on the last boundary; the client still
					# uses the result to set its per-field `steered` markers).
					proactive_fields = obj.get("fields", [])
					# PII (contract 6): log the COUNT only -- NEVER `fields`/values.
					_log.info(
						"form_complete_received",
						field_count=len(proactive_fields) if isinstance(proactive_fields, list) else 0,
						session_id=session_id,
					)
					verdict = await service.handle_validation_boundary(proactive_fields)
					await websocket.send_json({
						"type": "validation_result",
						"conflicts": verdict.get("conflicts", []),
					})
					await websocket.send_json({"type": "form_complete_ack"})
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
		await service.end_session()


from ..services.auth import verify_token

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
			verify_token(token)
		except Exception as e:
			log.warning("websocket_auth_failed", error=str(e))
			await websocket.close(code=1008, reason="Authentication failed")
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

	# Extract handshake data
	# Check for JIT mode (manifest-based) vs legacy mode (full schema)
	handshake_type = handshake.get("type", "handshake")
	is_jit_mode = handshake_type == "handshake_jit"

	# Extract persistent form session ID (frontend-managed, survives reconnects)
	form_session_id = handshake.get("form_session_id")

	if is_jit_mode:
		# JIT mode: Extract manifest and first field schema
		manifest = handshake.get("manifest")
		first_field_schema = handshake.get("first_field_schema")
		loaded_field_ids = handshake.get("loaded_field_ids", [])
		# Form title rides on the JIT handshake so {form_title} in the SI is the
		# real form, not the literal "Form" (bd polyglot-pdf-jnjj.9, gap O: the JIT
		# schema dict has no form_metadata, so ai_context fell back to "Form").
		jit_form_title = handshake.get("form_title")

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
		if jit_form_title:
			schema["form_metadata"] = {"title": jit_form_title}
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
	print(f"JIT Mode: {is_jit_mode}")
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
		# Native-VAD mode toggle (bd polyglot-pdf-333): when True, Gemini's own VAD
		# drives turns -- the frontend must stop sending manual activity signals and
		# stream continuous audio. Mirror of the backend DISABLE_GEMINI_VAD flag.
		"native_vad": not settings.DISABLE_GEMINI_VAD,
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
		section_id=section_id,  # Current section ID for token-log context (bd polyglot-pdf-tb7)
		section_number=section_number,  # Phase 3: Current section
		section_label=section_label,  # Phase 3: Section label
		total_sections=total_sections,  # Phase 3: Total sections
		previous_spoken_names=previous_spoken_names,  # Phase 3: Completed sections lookup
		initial_field_hint=initial_field_hint,  # Computed by frontend before connection
		form_session_id=form_session_id,  # Persistent ID from frontend (survives reconnects)
		is_reconnect=is_reconnect,  # Suppresses greeting on mid-section reconnect (bd polyglot-pdf-vmxx)
	)
