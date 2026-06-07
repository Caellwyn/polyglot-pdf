# Voice AI (Gemini Live adapter)

**Tracks:** backend/adapters/live_ai_gemini.py backend/services/callback_handler.py frontend/src/shared/connection.ts frontend/src/shared/audioManager.ts

*Last updated: 2026-06-07. See [journal/entries/2026-06-07-bd-kbf-gemini-io-logging.md](../journal/entries/2026-06-07-bd-kbf-gemini-io-logging.md) for the full Gemini I/O dev logging + interrupt `canceled_tool_names`, [journal/entries/2026-06-04-bd-333-native-vad-smoke-test.md](../journal/entries/2026-06-04-bd-333-native-vad-smoke-test.md) for the native-VAD activity-signal change, and [journal/entries/2026-06-04-bd-1g6-3p1-text-channel-1007.md](../journal/entries/2026-06-04-bd-1g6-3p1-text-channel-1007.md) for the 3.1 text-send (1007) fix.*

`LiveAIGemini` (`backend/adapters/live_ai_gemini.py`) is the single wrapper around
the Gemini Live API: it owns the bidirectional session, streams audio, routes tool
calls, and tracks cost. Model selection is in
[../standards/ai-models.md](../standards/ai-models.md); turn-taking / VAD in
[../standards/voice-and-vad.md](../standards/voice-and-vad.md); the WS protocol
that feeds it in [websocket-routing.md](websocket-routing.md).

## Session lifecycle

- **Construction** (`__init__`): takes `model` (passed `settings.MODEL_NATIVE` by
  `dependencies.py`), builds a `genai.Client` (Vertex AI by default), and assigns a
  unique `instance_id` for multi-tab debugging. Tests patch `genai.Client`.
- **`connect(model, config)`**: async context manager around
  `client.aio.live.connect(...)`. Handles both modern (async-CM) and older
  (awaitable) SDK shapes.
- **`set_callbacks(...)`**: registers the async `on_form_update` / `on_transcript`
  / `on_audio` / `on_tool_call` callbacks + system instruction + tool declarations,
  then lazily creates the audio queue (`maxsize=100`, ~2s) and text queue and
  starts the background `_run_session_loop()` task.
  - **CRITICAL:** it resets `self._intentional_shutdown = False` *before* checking
    task status — without that, a section-switch `finalize()` leaves the flag set
    and the freshly-started session immediately exits thinking it was
    intentionally shut down.
  - It warns `bg_task_already_running_callbacks_overwritten` if called while a task
    is live (a sign two connections are sharing one adapter).
- **`finalize()`** (the adapter method; the service wraps it as
  `finalize_gemini_session()`): closes ONLY the Gemini session (keeps the WebSocket
  alive) under `_task_lock`, setting `_intentional_shutdown = True` — used for the
  Level-3 farewell so the client can later `restart_gemini_session`.
- **`set_session_context(form_session_id, form_id, current_section_id)`**: injects the
  ids used for token logging (token events only fire when these are set — see
  [../standards/logging-and-cost.md](../standards/logging-and-cost.md)).

## Audio pipeline

- **Inbound (user → Gemini):** `stream_audio(chunk)` does a **non-blocking**
  `put_nowait` onto the bounded audio queue and **drops the frame if the queue is
  full** rather than blocking the WS control loop. Dropped-frame warnings are
  rate-limited to once / 5s. (Audio tolerates dropped frames; blocking the control
  channel would be worse.)
- **Outbound (Gemini → user):** audio chunks come back through the `on_audio`
  callback; the frontend (`connection.ts` → `audioManager`) plays them and detects
  end-of-playback via the audio source's `onended`, which drives the activity
  watchdog.
- **Text/hints:** `send_text_message()` queues hints; `send_client_content()`
  prompts Gemini to actually speak. The actual wire send is **model-conditional**
  via `_send_text_turn()` (bd `polyglot-pdf-1g6`): the **3.1 family** rejects
  `send_client_content()` text turns with close code **1007**, so its text goes
  via `session.send_realtime_input(text=...)`; **2.5 / others** keep
  `send_client_content()`. Hint text is **never logged** (callers build it with
  field values — see bd `polyglot-pdf-hjo`); only its length is logged at DEBUG.

## Activity signals (VAD modes)

Turn-taking depends on the `DISABLE_GEMINI_VAD` flag (bd polyglot-pdf-333; default
`False` = **native** Gemini VAD). In **manual** mode (`DISABLE_GEMINI_VAD=True`)
the adapter sends `send_activity_start()` / `send_activity_end()` →
`session.send_realtime_input(activity_start=types.ActivityStart())` /
`ActivityEnd()` (both guard on `self._current_session is None`). In **native**
mode these methods **no-op early** -- Gemini's own VAD drives turns, so forwarding
manual signals would create a conflicting turn-taking state. Full rationale, the
single-toggle revert, and the frontend continuous-audio requirement are in
[../standards/voice-and-vad.md](../standards/voice-and-vad.md).

## Barge-in

In `_run_session_loop`, the adapter checks `server_content.interrupted`. On a true
interrupt it logs `GEMINI_INTERRUPTED` (with the canceled tool-call ids AND names,
so a barge-in that kills an in-flight `update_form_fields` is visible), resets its
audio-chunk tracking (`_audio_chunk_count = 0`, `_first_audio_time = None`), and
`continue`s — skipping the rest of that event so no stale audio/tool-calls are
processed. The backend does **not** push a flush signal to the client; the actual
playback flush is **frontend-driven** — `connection.ts onVADSpeechStart` calls
`audioManager.flushAudioQueue()` the instant the local VAD fires, for
sub-perceptual latency (see [../standards/voice-and-vad.md](../standards/voice-and-vad.md)).

## Tool calling

Tool calls are routed to `CallbackHandler.on_tool_call`
(`backend/services/callback_handler.py`), which dispatches the five tools declared
in `backend/config.py`. The full call/response sequence (code expectation vs. the
actual wire payload) is mapped in [tool-call-flow.md](tool-call-flow.md); when
debugging tool reliability, the adapter captures FULL message bodies locally via
`_dev_log_io` (`.env.DEV`-gated, never in production) to
`backend/logs/gemini_<date>.jsonl`. The five tools:

- `update_form_fields` — single field per call (hallucination mitigation).
- `confirm_field` — enum `verbal`/`manual`; see
  [../standards/confirmation-and-audit.md](../standards/confirmation-and-audit.md).
- `get_form_status` (alias `get_form_state`) — compact field-state snapshot.
- `switch_section` — advance by `section_identifier`.
- `get_field_value` — look up a current value by `spoken_name`.

The `complete_section` tool was **removed** — section completion is frontend-driven
(see [websocket-routing.md](websocket-routing.md)).

## Cost tracking

Each response's `usage_metadata` is split by modality, priced via
`get_pricing_for_model(self._model_name)`, accumulated into
`self._session_total_cost` / `_session_total_tokens`, and (when session context is
set) written to `token_usage.jsonl`. Details + the re-billing cost concern in
[../standards/logging-and-cost.md](../standards/logging-and-cost.md).

## Response config

`_run_session_loop` builds the connect config with `response_modalities = ["AUDIO"]`
(audio-out only; native audio-to-audio). Input/output transcription
(`input_audio_transcription` / `output_audio_transcription`) is enabled **only** when
`enable_transcripts` is set. VAD config (`realtime_input_config`) is covered in
[../standards/voice-and-vad.md](../standards/voice-and-vad.md).

## Scar tissue

- **`_intentional_shutdown` reset ordering** (above) — the section-switch crash.
- **Audio queue drops, never blocks** — control-channel liveness beats audio
  fidelity.
- **One adapter per connection** — `dependencies.get_live_ai` builds a fresh
  `LiveAIGemini` per WebSocket (a CRITICAL bug-fix comment there) because a shared
  instance had its callbacks overwritten by the second connection, routing tool
  calls to the wrong tab. The adapter also warns `bg_task_already_running` if
  `set_callbacks` is called on a live task.
- **Never log transcript/hint text** — only lengths (bd `polyglot-pdf-hjo`).
- **Barge-in flush is frontend-side** — the backend only logs+skips on interrupt
  (no flush signal); don't expect a server sentinel.
