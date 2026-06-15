# Voice AI (Gemini Live adapter)

**Tracks:** backend/adapters/live_ai_gemini.py backend/services/callback_handler.py frontend/src/shared/connection.ts frontend/src/shared/audioManager.ts

*Last updated: 2026-06-15 (bd polyglot-pdf-daa: 2.5 native-audio 1011 = incomplete tool declaration x tool solicitation, wire-verified; corrected the scar-tissue note. bd s3zv: audioManager gains setEnergyCallback -- forwards the worklet's existing RMS energy (already posted per frame, previously dropped) to an opt-in UI subscriber, tagged with whether the frame passed the send gate. No change to audio routing / adapter behavior; the demo overlays render it as a mic-energy meter). bd np64: non-ASCII -> ASCII in connection.ts / audioManager.ts code comments + console strings (cosmetic, no adapter behavior change). bd rwjy+vfb2: CallbackHandler gains form_id/form_session_id (confirmation audit); send_form_update adds request_hint opt-in (no behavior change). bd 0tgc: onStopCapture/onFormComplete wired in createConnectionManager. bd b6k4: createMicDropWarn extracted/exported from connection.ts. No adapter behavior change. Prior: bd polyglot-pdf-c5t (on_go_away callback: GoAway detection in the receive loop). See [../journal/entries/2026-06-12-bd-c5t-goaway-handling.md](../journal/entries/2026-06-12-bd-c5t-goaway-handling.md) for the GoAway path, [../journal/entries/2026-06-10-bd-0c1-cooperative-receive-loop-shutdown.md](../journal/entries/2026-06-10-bd-0c1-cooperative-receive-loop-shutdown.md) for the cooperative receive-loop shutdown (begin_graceful_shutdown + the finalize self-call guard, closed y4a), [../journal/entries/2026-06-09-bd-0ux-tool-response-missing-id.md](../journal/entries/2026-06-09-bd-0ux-tool-response-missing-id.md) for the FunctionResponse id echo, and [journal/entries/2026-06-04-bd-1g6-3p1-text-channel-1007.md](../journal/entries/2026-06-04-bd-1g6-3p1-text-channel-1007.md) for the 3.1 text-send (1007) fix.*

`LiveAIGemini` (`backend/adapters/live_ai_gemini.py`) is the single wrapper around
the Gemini Live API: it owns the bidirectional session, streams audio, routes tool
calls, and tracks cost. As of bd polyglot-pdf-x52p the SDK is `google-genai`
**2.8.0** (empirical 1.38.0-vs-2.8.0 diff on the 1cnn epic): the one behavioral
break is that 2.x re-raises receive-path WebSocket closures as
`google.genai.errors.APIError`, so the receive loop's graceful-close handler
catches `(ConnectionClosed, genai_errors.APIError)`; the Live connect config is
now built by `_build_live_config(settings)` (extracted from `_run_session_loop`
so the contract smoke test and probes drive the REAL config shape, bd 4td1/a7k). Model selection is in
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
  / `on_audio` / `on_tool_call` / `on_go_away` callbacks + system instruction + tool
  declarations, then lazily creates the audio queue (`maxsize=100`, ~2s) and text
  queue and starts the background `_run_session_loop()` task. `on_go_away` is
  optional: the receive loop reads `event.go_away` (a `LiveServerGoAway` with a
  `time_left` string) and fires it so the client can pre-emptively reconnect before
  the server-initiated close (bd polyglot-pdf-c5t); detection is best-effort and
  never breaks the loop.
  - **CRITICAL:** it resets `self._intentional_shutdown = False` AND
    `self._close_after_flush = False` *before* checking task status — without that,
    a section-switch teardown leaves a flag set and the freshly-started session
    immediately exits thinking it was shut down. It also binds a fresh per-session
    `_closed_event` and attaches a task done-callback that sets it on EVERY exit
    path (the cooperative-shutdown handshake, bd polyglot-pdf-0c1).
  - It warns `bg_task_already_running_callbacks_overwritten` if called while a task
    is live (a sign two connections are sharing one adapter).
- **`begin_graceful_shutdown()`** (bd polyglot-pdf-0c1 / y4a): synchronous,
  lock-free, and safe to call from a tool callback running ON the receive task
  (e.g. `switch_section`). Sets `_close_after_flush` so the receive loop flushes
  its pending tool responses and then breaks cleanly — instead of the self-cancel
  that orphaned the `switch_section` response. Returns the per-session
  `_closed_event` so the caller can await the old loop's exit before restarting.
- **`finalize()`** (the adapter method; the service wraps it as
  `finalize_gemini_session()`): closes ONLY the Gemini session (keeps the WebSocket
  alive). Sets `_intentional_shutdown = True` and clears the session-ready/pending
  state INSIDE `_task_lock` (the shutdown-flag race), then cancels + awaits the bg
  task. Used for the Level-3 farewell so the client can later
  `restart_gemini_session`. A **self-call guard** downgrades a (mis)call from the
  receive task itself to `begin_graceful_shutdown()` — the y4a self-cancel can
  never be reintroduced.
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
- **Dev test injection:** `connection.ts` publishes a dev-gated
  `window.__VFF_TEST_INJECT` (only when `isTestHarnessEnabled()` — both
  `__VFF_LOCAL_DEV` and `__VFF_TEST_HARNESS` set) that pushes scripted PCM straight
  into `sendAudio`, bypassing the mic/worklet. Used by the E2E voice harness
  (`tests/e2e/voice-harness/`); a no-op in production and normal dev.
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

Every tool call gets a `FunctionResponse` that **echoes the call's `id`** back
(`_build_function_response`). The SDK's AI-Studio (`VERTEXAI=false`) path requires
the id and crashes the receive loop without it (bd polyglot-pdf-0ux); the Vertex
path tolerates a missing id.

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
- **2.5 native-audio `1011`s at an early turn boundary on an INCOMPLETE tool declaration under
  tool-soliciting prompts** (bd `polyglot-pdf-daa`/`h04c`; wire-verified isolation
  experiment, `scripts/spikes/diag_native_audio_1011_tools.py`, 2026-06-15). On
  `gemini-2.5-flash-native-audio-preview-12-2025` the early-turn `1011` (after the 1st or 2nd clean turn) needs BOTH: a
  `function_declaration` that is present but malformed (a `name` with **no
  `parameters` schema**) AND a system-instruction/prompts that solicit tool use.
  It is a RATE (~80% for one name-only declaration over N=30), not deterministic.
  - **DO** declare tools COMPLETELY — every `function_declaration` gets a real
    typed `parameters` schema. The production `TOOL_DECLARATIONS` are complete, so
    the real adapter path is safe; a probe/spike that drives 2.5 must pass the same
    complete declarations (deploy-fidelity rule, `docs/standards/testing.md`).
  - **DON'T** send a `name`-only / parameter-less declaration to 2.5 — that is the
    actual hazard (a fallback stub, a placeholder, or a wrapper that injects a
    name-only tool). It is WORSE than sending no tools.
  - **DON'T** assume you must "pass an empty tools list." Omitting `tools`, sending
    `tools=[]`, and sending `tools=[{functionDeclarations: []}]` ALL survive (0%).
    The trigger is a malformed declaration, not the absence of one. (Caveat: a
    typed `LiveConnectConfig(tools=[])` is erased to no-tools by the SDK before the
    wire — `live.py` `model_copy(update={'tools': None})` + falsy `[]` — so you
    can't even send a true `[]` through the typed config; both are safe anyway.)
  - **DON'T** chalk a 2.5 early-turn `1011` up to "transient Google-side" — it is
    reproducible and config-driven (the old bd `daa` "transient/untestable" framing
    was the misdiagnosis). A *separate* lower-rate intermittent no-audio/close on
    2.5 is real and NOT addressed by getting tool shape right.
  - **DON'T** confuse with the *untyped-`value`* defect (bd `polyglot-pdf-i9q8`):
    that hit **3.1** (rejected an untyped *required param*), not 2.5. Different
    model, different cause; same fix direction (type your params).
  - Verified NOT fixed/changed by `api_version=v1alpha`, the `-latest`/`-09-2025`
    aliases, or compression config. Full report:
    `scripts/spikes/gemini-2p5-1011-tool-declarations-report.md`.
- **Barge-in flush is frontend-side** — the backend only logs+skips on interrupt
  (no flush signal); don't expect a server sentinel.
