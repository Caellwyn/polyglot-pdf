# Voice AI (Gemini Live adapter)

**Tracks:** backend/adapters/live_ai_gemini.py backend/services/callback_handler.py frontend/src/shared/connection.ts frontend/src/shared/audioManager.ts

*Last updated: 2026-07-16 (bd polyglot-pdf-f7h7: the stored-value echo is success-branch-only -- a collapsed multi-field update_form_fields call no longer echoes stored_values on its error branch, where the client stored nothing. Same-day: bd polyglot-pdf-yo5t/h7wx/oqkj/y25o voice-misfire batch: ASR language bias on the transcription configs + the stored-value echo on update_form_fields + the debounced post-unpause re-prompt caller in connection.ts -- see [../journal/entries/2026-07-16-bd-yo5t-voice-misfire-batch.md](../journal/entries/2026-07-16-bd-yo5t-voice-misfire-batch.md)). Prior: 2026-07-15 (bd polyglot-pdf-b1gj + ghv4: actionable unknown-field rejections + the STOP-RETRYING loop-breaker on update_form_fields; per-injection spoken-language re-anchor and the no-quoted-English rule for prompts/tool descriptions -- see the tool-calling section). Prior: 2026-07-12 (continuous-DTI is the production law; switch_section is a deprecated section-reset-fallback tool, bd polyglot-pdf-55jg). Prior: 2026-07-09 (bd polyglot-pdf-7yra: added the seventh tool `skip_field` -- voice skip of a required field, distinct from N/A -- to the tool-calling section). Prior: 2026-07-05 (bd polyglot-pdf-mpoe staleness sweep: added the sixth tool `ask_secretary` to the tool-calling section, added the `on_processing_done` callback to session lifecycle + barge-in, noted `send_client_content()`'s bool return). See [../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md](../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md).*

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
  / `on_audio` / `on_tool_call` / `on_go_away` / `on_user_activity` /
  `on_processing_done` callbacks + system instruction + tool declarations, then
  lazily creates the audio queue (`maxsize=100`, ~2s) and text queue and starts the
  background `_run_session_loop()` task. `on_go_away` is optional: the receive loop
  reads `event.go_away` (a `LiveServerGoAway` with a `time_left` string) and fires
  it so the client can pre-emptively reconnect before the server-initiated close
  (bd polyglot-pdf-c5t); detection is best-effort and never breaks the loop.
  `on_user_activity` is optional and fires on a native-VAD input transcription (see
  Response config below). `on_processing_done` is optional (bd polyglot-pdf-wpw.5):
  it fires when the agent's turn ends -- on a barge-in interrupt AND on a real
  `turn_complete`/`generation_complete` with no output audio -- so a UI "thinking"
  indicator clears even when there is no audio reply to key off.
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
  `send_client_content()` returns a **bool**: `True` only if the turn was actually
  handed to the live session this call, `False` if it was queued (session not
  ready), dropped (no session), or the send raised (bd `polyglot-pdf-jnjj.17`) --
  callers that need to know whether Gemini actually got the text (e.g. the
  validator-steer hold) check the return instead of assuming success.

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
audio-chunk tracking (`_audio_chunk_count = 0`, `_first_audio_time = None`), fires
`on_processing_done` if registered (an interrupted turn produces no audio/
transcript, so the thinking indicator would otherwise stay set until its
max-duration timer, bd polyglot-pdf-wpw.5), and `continue`s -- skipping the rest of
that event so no stale audio/tool-calls are processed. The backend does **not**
push a flush signal to the client; the actual playback flush is **frontend-driven**
-- `connection.ts onVADSpeechStart` calls `audioManager.flushAudioQueue()` the
instant the local VAD fires, for sub-perceptual latency (see
[../standards/voice-and-vad.md](../standards/voice-and-vad.md)).

## Tool calling

Tool calls are routed to `CallbackHandler.on_tool_call`
(`backend/services/callback_handler.py`), which dispatches the tools declared
in `backend/config.py`. The full call/response sequence (code expectation vs. the
actual wire payload) is mapped in [tool-call-flow.md](tool-call-flow.md); when
debugging tool reliability, the adapter captures FULL message bodies locally via
`_dev_log_io` (`.env.DEV`-gated, never in production) to
`backend/logs/gemini_<date>.jsonl`. `get_field_value` was retired (bd
polyglot-pdf-p5h2): in continuous mode (the only production path) recall is
`ask_secretary`'s job. The tools:

- `update_form_fields` — single field per call (hallucination mitigation).
- `confirm_field` — enum `verbal`/`manual`; see
  [../standards/confirmation-and-audit.md](../standards/confirmation-and-audit.md).
- `get_form_status` (alias `get_form_state`) — compact field-state snapshot.
- `switch_section` — advance by `section_identifier`. **DEPRECATED**: dropped
  from the declared tool set in production continuous mode; belongs to the
  section-reset fallback (bd polyglot-pdf-55jg).
- `ask_secretary` -- a plain-language question routed to a cheap text-model
  helper that holds the whole form catalog + current answers and replies in
  prose (bd polyglot-pdf-jnjj.45); the principal uses it instead of trying to
  recall a past answer or another field itself.
- `skip_field` -- force-skip a required field the user cannot answer right now
  (bd polyglot-pdf-7yra), DISTINCT from not-applicable (which stays the
  `update_form_fields ""` path). Maps to the frontend `markFieldSkipped` (the
  `skipped` flag); the SI requires a verbal confirm first.

The `complete_section` tool was **removed** — section completion is frontend-driven
(see [websocket-routing.md](websocket-routing.md)).

An `update_form_fields` rejection is ACTIONABLE, not bare (bd polyglot-pdf-b1gj):
an id that names a real-but-not-active field (manifest/merge-known) is told to
navigate with `switch_to_field` first; an unresolvable id is told never to invent
ids. Three consecutive wholly-unknown rejections escalate the response to an
explicit STOP-RETRYING instruction (`UNKNOWN_REJECTION_LOOP_THRESHOLD`, logged as
`unknown_field_loop_breaker_fired`) -- a live Spanish session had looped 338
rejected updates with the old bare "unknown field" text.

Every injected guidance block also re-anchors the SESSION LANGUAGE with a
"Speak <lang> aloud" segment (bd polyglot-pdf-ghv4): `render_field_guidance`
takes `spoken_language` from a live getter on the service (the client-sent,
user-chosen language from the app-start modal -- never a hardcoded language),
mirroring the `Fill language:` segment. Recovery prompts and tool descriptions
carry NO quoted English utterances (they get spoken verbatim in English
otherwise).

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
(audio-out only; native audio-to-audio). **Output** transcription
(`output_audio_transcription`) is enabled only when `enable_transcripts` is set.
**Input** transcription (`input_audio_transcription`) is enabled when EITHER
`enable_transcripts` is set OR an `on_user_activity` callback is registered (bd
polyglot-pdf-l3a.4): it is the native-VAD turn-start signal -- a non-empty
`server_content.input_transcription` fires `on_user_activity`, which drives both the
idle watchdog and the thinking-indicator START (bd polyglot-pdf-wpw.5 / fa4x). It
DOES fire on the 2.5 native-audio model at `VAD_START_SENSITIVITY=HIGH` (the
production default; verified on the deployed Vertex model). Requesting it never
forwards the text to the client (PHI stays server-side, bd hjo). VAD config
(`realtime_input_config`) is covered in
[../standards/voice-and-vad.md](../standards/voice-and-vad.md).

**ASR language bias** (bd polyglot-pdf-y25o): when `TRANSCRIPTION_LANGUAGE_HINT_ENABLED`
(default true) and the service has set codes via
`set_transcription_language_codes(...)` (derived in `FormFillingService.start_session`
from the handshake's `spoken_language` through
`backend/utils/language_codes.py`), the requested transcription blocks carry
`language_codes` (BCP-47, e.g. `["es-US"]`) so the ASR listens FOR the session
language -- the SI steers only the LLM's output language, and unbiased
multilingual ASR can transcribe a mumbled session-language word as a neighboring
language and drag the model's auto-detect with it. The hint never turns a
transcription block on by itself, and it is per-connect: a mid-session language
change takes effect at the next session (re)establishment. Endpoint-verified
ACCEPTED on the Vertex 2.5 native-audio default tier
(`scripts/spikes/transcription_lang_codes_findings.md`); the AI-Studio 3.1
premium tier is unverified -- the env flag is the kill-switch.

**Stored-value echo** (bd polyglot-pdf-h7wx): a successful `update_form_fields`
tool response carries `stored_values` (field_id -> the post-validator CANONICAL
value) and repeats it in the `message`; the DTI SI directs the model to read its
confirmation read-back from that echo -- never from its own conversational
memory, which the compression window can have evicted (live sessions confirmed
values that were never in the field). The echo is model-facing only; production
structlog calls still log counts, never values. The echo fires ONLY on the
success branch (bd polyglot-pdf-f7h7): the error branch sends
`send_form_update({}, [])` (the client stores nothing), so a collapsed
multi-field call -- whose first field validates but is never carried to the
client -- must NOT echo `stored_values`, or the model reads back a value client
and model never agreed on.

Model **thinking** is turned off by default: when `DISABLE_MODEL_THINKING` is set
(default on) and the active model is 2.5-family, the config carries
`thinking_config = {"thinking_budget": 0}`. The form-fill turn loop needs no
chain-of-thought, and thinking tokens bill at the output rate. The 3.1 family uses
a different `thinking_level` field and is left at its default (the 2.5-only
`thinking_budget` form is not sent to it). Whether the flag does anything on
native-audio Live is unverified upstream ([../genai_docs/live-api-best-practices.md](../genai_docs/live-api-best-practices.md)),
so this is safe-if-ignored rather than guaranteed.

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
