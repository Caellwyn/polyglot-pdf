# Voice AI (Gemini Live adapter)

**Tracks:** backend/adapters/live_ai_gemini.py backend/services/callback_handler.py frontend/src/shared/connection.ts frontend/src/shared/audioManager.ts

*Last updated: 2026-05-31*

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
- **`finalize_gemini_session()`**: closes ONLY the Gemini session (keeps the
  WebSocket alive) under `_task_lock`, setting `_intentional_shutdown = True` — used
  for the Level-3 farewell so the client can later `restart_gemini_session`.
- **`set_session_context(form_session_id, form_id, current_part_id)`**: injects the
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
  prompts Gemini to actually speak. Hint text is **never logged** (callers build it
  with field values — see bd `polyglot-pdf-hjo`); only its length is logged at
  DEBUG.

## Manual activity signals (VAD)

Gemini's own VAD is disabled (`DISABLE_GEMINI_VAD=True`); the adapter sends manual
`send_activity_start()` / `send_activity_end()` →
`session.send_realtime_input(activity_start=types.ActivityStart())` /
`ActivityEnd()`. Both guard on `self._current_session is None`. Full rationale,
ordering, and the energy-VAD tuning config are in
[../standards/voice-and-vad.md](../standards/voice-and-vad.md).

## Barge-in

In `_run_session_loop`, the adapter checks `server_content.interrupted`. On a true
interrupt it logs `GEMINI_INTERRUPTED`, sends a `b"__INTERRUPT__"` sentinel through
the `on_audio` callback (so the frontend flushes its playback queue), resets the
audio-chunk counter, and continues. The frontend also flushes locally the instant
its VAD fires, for sub-perceptual latency (see voice-and-vad).

## Tool calling

Tool calls are routed to `CallbackHandler` (`backend/services/callback_handler.py`):
`update_form_fields` (single field per call — hallucination mitigation) and
`confirm_field` (enum `verbal`/`manual`; see
[../standards/confirmation-and-audit.md](../standards/confirmation-and-audit.md)).
The `complete_section` tool was **removed** — section completion is frontend-driven
(see [websocket-routing.md](websocket-routing.md)).

## Cost tracking

Each response's `usage_metadata` is split by modality, priced via
`get_pricing_for_model(self._model_name)`, accumulated into
`self._session_total_cost` / `_session_total_tokens`, and (when session context is
set) written to `token_usage.jsonl`. Details + the re-billing cost concern in
[../standards/logging-and-cost.md](../standards/logging-and-cost.md).

## Scar tissue

- **`_intentional_shutdown` reset ordering** (above) — the section-switch crash.
- **Audio queue drops, never blocks** — control-channel liveness beats audio
  fidelity.
- **One adapter per connection** — sharing causes the
  `bg_task_already_running` callback-overwrite warning.
- **Never log transcript/hint text** — only lengths (bd `polyglot-pdf-hjo`).

*Last updated: 2026-05-31*
