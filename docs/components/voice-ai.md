# Voice AI (Gemini Live adapter)

**Tracks:** backend/adapters/live_ai_gemini.py backend/services/callback_handler.py frontend/src/shared/connection.ts frontend/src/shared/audioManager.ts frontend/src/shared/spellbackPlayer.ts

*Last updated: 2026-08-26 (bd polyglot-pdf-kvrfq: the `name_spellback` bullet
now records the client-side stale-arrival guards and the wire-verified fact
that holding the tool response open does NOT park the model. Also current,
from bd polyglot-pdf-uxc6s: the speaking predicates are
now THREE, not two -- `isModelSpeaking()` is what every barge-in / flush site
reads, `isSpeaking()` is reserved for the VAD suspend/resume pair, and the
complete call-site classification is pinned by
`frontend/src/shared/speakingSignalCallSites.test.ts`. Also current: the
`ask_secretary` bullet now names all three shipped uses -- past-answer
recall, field identification for navigation, and official instruction text
quoted back -- plus the hedge-and-defer relay contract, matching
`backend/config.py`'s declaration (bd polyglot-pdf-9sz5y); synthesized clips
share the playback graph via the `attachClipElement` seam (bd
polyglot-pdf-s1iex.4, [journal
entry](../journal/entries/2026-08-14-bd-s1iex.4-sol-animates-during-clips.md));
`LIVE_VOICE_NAME` has a THIRD consumer -- the intro-clip route reuses
`resolve_spellback_voice`, at 0 dB rather than the per-voice gain (bd
polyglot-pdf-s1iex.3, [journal
entry](../journal/entries/2026-08-13-bd-s1iex.3-intro-tts-route.md)).)*

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
- **Synthesized CLIPS (spell-back; Sol's intro from bd `s1iex.5`) share that
  playback graph** (bd `polyglot-pdf-s1iex.4`). `audioManager.attachClipElement(el)`
  splices the clip's `<audio>` element in via `createMediaElementSource` → the
  same `getOutputAnalyser` node the model's PCM uses, so **one** energy source
  feeds the avatar; it returns an idempotent release the caller invokes on
  every settle path. The element MUST carry a **blob URL** — a cross-origin
  `src` taints it and Web Audio then outputs silence with no error. THREE
  predicates, deliberately distinct (bd polyglot-pdf-uxc6s) -- picking the
  wrong one is SILENT in both directions, so check which question your site
  asks:
  **`isModelSpeaking()`** is true whenever the model's PCM is scheduled, clip
  or no clip. Every flush site that is GATED on a speaking signal reads this
  one, as does the post-resume re-prompt guard: they ask "would flushing stop
  the model mid-utterance?", and a clip is irrelevant to that. (Several flush
  sites are deliberately UNGATED -- both disclaimer-agree handlers, desktop's
  PTT press, and `pause()` -- because there the flush is unconditional by
  design. Desktop and mobile currently disagree about whether the PTT press
  should be gated at all: bd `polyglot-pdf-2fyj7`.)
  **`isSpeaking()`** is the clip-SUPPRESSED variant
  (`geminiIsSpeaking && activeClipCount === 0`). ONLY the VAD suspend/resume
  pair reads it -- a clip lives inside the playback context, so counting one
  there would suspend it mid-word and never resume (the bd s1iex.4 deadlock).
  It CANNOT answer the barge-in question: `geminiIsSpeaking` is set by BOTH
  producers, so a model+clip overlap and a clip alone are the same state and
  both read false.
  **`isAnyAudioPlaying()`** is the union the avatar's `getOutputEnergy` gate
  wants.
  The complete call-site classification is pinned by
  `frontend/src/shared/speakingSignalCallSites.test.ts`, which fails on an
  unclassified or mis-pointed site. `isClipPlaying()` is the clip-only flag `deriveSolState` reads as
  `clipPlaying`, which bypasses the live-session gate because a clip is
  audible with **no** session (but still yields to `paused`/`offline`).
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

## Spoken delivery (pace + articulation)

Both SIs govern HOW the model speaks, not just what it says -- but they LABEL it
differently, which matters when you go to tune it:

- **DTI** (`DTI_SYSTEM_INSTRUCTION`, the production path): ONE `DELIVERY` block
  holds pace, sustain, articulation and the digit read-back together. There is no
  `SPEECH STYLE`, `ARTICULATION` or `PACE:` token in this constant -- grepping any
  of them finds nothing. Tune the DTI copy inside `DELIVERY`.
- **Legacy** (`SYSTEM_INSTRUCTION`, the deprecated fallback): still labelled
  `PACE:` + `ARTICULATION` inside `REGISTER`.

The two SIs' delivery prose is NO LONGER byte-identical and must NOT be edited
together: the DTI copy was rewritten in the v4 diet (bd polyglot-pdf-6a79) while
the legacy constant was left untouched. `test_articulation_text_is_identical_across_both_sis`
was retired for that reason; `test_legacy_articulation_block_is_self_consistent`
now pins the legacy block alone.

Three concerns, kept deliberately separate (bd polyglot-pdf-e1x9):

- **Pace** -- distinctly slower than natural conversational speed, erring on the
  side of too slow, plus a **sustain** rule (hold it from the first word to the
  last; never speed up mid-sentence or rush a sentence ending). Observed rushing
  was mid-sentence DRIFT, so the sustain rule is pinned separately from the pace
  itself -- tuning one must not silently drop the other. The old "about ten
  percent slower than the measured pace you would otherwise choose" target was
  RETIRED (maintainer, 2026-08-07: it asks the model to measure against a pace it
  cannot introspect).
- **Identifier read-back** (DTI) -- a number that is an IDENTIFIER (id/case
  numbers, dates, phone, ZIP, accounts) is read DIGIT BY DIGIT, never as a
  quantity; a real quantity is spoken normally. Letter-by-letter SPELL-BACK was
  removed from the DTI SI: spelling aloud desyncs the native-audio model's audio
  and text layers, and a dedicated TTS tool will own it.
- **Articulation** -- full sound through the END of each word, no
  slurring/swallowed syllables/mumbling, deliberate pauses between clauses, and
  no casual contractions or filler sounds. Written to generalize across the
  17+ session languages: it names the tonal / evenly-timed-syllable equivalent
  alongside inflectional word endings, since "word endings" alone is meaningless
  in Chinese, Vietnamese, Thai, or Japanese.

The articulation rules explicitly govern **delivery, not word choice** -- they
must not be read as overriding `REGISTER`'s warm, conversational register.

**"Speak slowly" does not imply "speak clearly."** The SI instructed pace long
before it instructed articulation, and the model hit an unhurried pace while
still slurring word endings. They are independent controls; instruct both.

A **voice** IS configured: `LIVE_VOICE_NAME` (default `Algieba` since
2026-08-11, "Smooth" -- it replaced `Iapetus`, "Clear", after Iapetus was heard
MISPRONOUNCING words in the live demo: "not applicable" spoken as "not a
pickle", bd polyglot-pdf-0rpu. Lowering `LIVE_TEMPERATURE` to 0.4 was the
standing hypothesis for that and was disconfirmed in production, which pointed
at the voice model rather than the sampling. Whether Algieba actually fixes it
is a by-ear judgment on the demo; Schedar/Achernar/Vindemiatrix are the next
candidates, all verified present in the Chirp3 en-US set) rides
`speech_config.voice_config.prebuilt_voice_config.voice_name`. Before this, no
voice was set and the API assigned its default -- documented as `Puck`
("Upbeat"), the wrong register for a stressful legal intake. Voice selection is
the **only documented lever on delivery**: Google's Live API docs describe no
pace, prosody, or style parameter for native audio, which is why two rounds of SI
pace/articulation prose did not stop the rushing (bd polyglot-pdf-9kj4). The SI
rules remain -- they are verified present in the live SI -- but they are not what
controls delivery.

The voice block **merges** into `speech_config`; the `language_code` block
assigns that key, so a bare assignment on either side would silently drop the
other (tests pin both orderings plus the empty-name fallback). Set
`LIVE_VOICE_NAME=""` to fall back to the API default.

**`LIVE_VOICE_NAME` has a SECOND and a THIRD consumer** (bd
polyglot-pdf-22h1f, reshaped by bd polyglot-pdf-44ywm; third: the intro clip,
bd s1iex.3): `spellback_tts.resolve_spellback_voice` uses it as the PERSONA
half of the spell-back clip's Cloud TTS voice, and the intro-clip route
(`intro_tts.py`) reuses the same resolution -- so both clips sound like the
same speaker; the Chirp 3 HD family carries the Live API's prebuilt voice
names. (Gain differs by surface: the spell-back clip takes the per-voice
measured gain, the intro clip pins 0 dB -- the measured gain clips ~90s
content.) The LOCALE half comes from the SESSION language, not from
`en-US`: a Spanish session derives `es-US-Chirp3-HD-<LIVE_VOICE_NAME>`. A
persona that has no twin in that locale can NOT break the clip -- the ladder
degrades (another Chirp3 persona in the same locale, then the locale's default
voice), so changing the Live voice never 502s the spell-back. See the
`name_spellback` bullet under Tool calling for the full ladder.
`LIVE_VOICE_NAME=""` drops the clip to the locale's default voice (still the
user's language, no longer the model's persona); pin the clip voice explicitly
via `SPELLBACK_TTS_VOICE` to decouple it from the Live voice entirely.

An unaccepted voice name is a hard `1007 Invalid voice name` at connect, not a
silent degrade -- it breaks EVERY session. **Connect-verify any new voice
locally before deploying**; it takes 30 seconds and local hits the SAME Vertex
Live endpoint as the demo, so this is not a deploy-time-only risk:

```
VERTEXAI=true backend/.venv/Scripts/python.exe backend/scripts/probe_voice_name.py Algieba
```

With no arguments it probes the configured `LIVE_VOICE_NAME`. It exits non-zero
if any voice is rejected (so it can gate a deploy) and always probes a bogus
name as a CONTROL -- a probe that accepts everything proves nothing. `Algieba`
and `Iapetus` are both verified ACCEPTED on
`gemini-live-2.5-flash-native-audio` (2026-08-11); `NotARealVoiceXYZ` is
correctly rejected. Rollback if one ever 1007s: `LIVE_VOICE_NAME=""` falls back
to the API default.

Connect-acceptance is all the probe can tell you. Whether a voice actually
fixes the diction is only answerable **by listening** -- `Iapetus` connected
fine and was still replaced, for mispronunciation.

**Changing `LIVE_VOICE_NAME` also changes the SPELL-BACK CLIP's voice** (bd
polyglot-pdf-44ywm: `resolve_spellback_voice` derives
`{locale}-Chirp3-HD-{persona}`), which is intended -- one speaker across both
surfaces. The clip's loudness gain is DERIVED FROM the persona rather than
configured beside it (`spellback_tts.spellback_gain_db`), because voices differ
in base loudness -- Iapetus's measured +7.0 dB CLIPS on Algieba (peak 1.025),
which is audibly worse than the quiet clip the leveling fixed. Deriving it
means an operator overriding `LIVE_VOICE_NAME` on Cloud Run cannot ship a
stale gain, and a FALLBACK persona (a locale without the configured voice) gets
its own value rather than the configured voice's. A persona with no recorded
measurement takes the conservative (quietest) end -- too quiet degrades, too
loud clips -- and a test fails until it is measured with
`scripts/spikes/measure_spellback_loudness.py`.

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
  prose (bd polyglot-pdf-jnjj.45). Three uses: (1) recall a past answer/value;
  (2) IDENTIFY which field the user means when the principal needs to
  navigate to a field it does not currently hold -- the response's `fields`
  list carries the exact `field_id` + `spoken_name` to pass to
  `switch_to_field`; (3) get the OFFICIAL INSTRUCTION TEXT quoted back when
  the current field's reference text does not cover something (bd
  polyglot-pdf-wsao.8). On an eligibility-shaped question ("do I qualify"),
  the secretary answers FROM the official text, flags the conditions that
  text puts on it, and defers the applicant's own situation to the firm or
  professional reviewing the form -- it never concludes their case, and the
  principal must relay all three parts rather than trim to a cleaner
  yes/no (this is the scrivener-not-advisor boundary
  `backend/tests/unit/test_secretary_scrivener_boundary.py` pins).
- `skip_field` -- force-skip a required field the user cannot answer right now
  (bd polyglot-pdf-7yra), DISTINCT from not-applicable (which stays the
  `update_form_fields ""` path). Maps to the frontend `markFieldSkipped` (the
  `skipped` flag); the SI requires a verbal confirm first.
- `name_spellback` -- `SPELLBACK_TOOL_ENABLED`, default ON since the cutover
  (bd polyglot-pdf-apkdl; the flag remains as a rollback -- bd
  polyglot-pdf-22h1f + 44ywm): deterministic spell-back for the current field.
  Takes NO arguments; the client resolves the current field, reads the stored
  value, fetches a Cloud TTS clip (`POST /api/tts/spellback`, carrying the
  value + the session language), mutes the mic in every input mode, plays it
  BLOCKING, and acks delivered/interrupted/error. The tool response is
  deliberately held open for the playback (90s coordinator cap) -- but
  holding it open does NOT park the model (bd polyglot-pdf-kvrfq,
  wire-verified 2026-08-26): under user barge-in pressure the native-audio
  model keeps emitting further `name_spellback` calls while earlier ones are
  unanswered, and because the tool callback runs inline on the receive loop,
  those calls QUEUE behind the in-flight round-trip and dispatch back-to-back
  once it settles (the incident: ten calls on one field, each read 3-9ms
  after the previous response went out). The client therefore refuses stale
  arrivals up front (`spellbackPlayer.ts` -- guards run before any mic hold
  or fetch): a request landing while PTT is held, or within the ~5s cooldown
  after a PTT interrupt of a clip, is acked `interrupted` with no playback
  and no mic hold (an unguarded arrival used to re-engage `setSpellbackHold`
  OVER an active press, silencing the user mid-answer); a value+language
  delivered within the last ~3s is acked `delivered` instead of replayed.
  While the flag is on the SI gets
  `DTI_SPELLBACK_SI_ADDENDUM` (BOTH SI modes) so the model never spells aloud
  itself. Declared via `_build_tool_declarations` from
  `SPELLBACK_TOOL_DECLARATION` (kept OUT of `TOOL_DECLARATIONS` until cutover),
  and the dispatch arm is flag-gated too so a hallucinated call while dark
  refuses in-band. Exists because the native-audio speech head re-emits the
  session's FIRST spelled name on ~10% of spelled read-backs (the bd 0rpu
  sticky-first-spelling attractor) while text + tool calls stay correct.
  - **The clip is PLAIN TEXT, never SSML, and carries the WHOLE verification
    question** ("You said J, O, S, E. Is that correct?"). Chirp 3 HD voices are
    LLM-based: they generate prosody from natural text, and SSML
    `say-as`/`break` markup renders mechanically (robotic, unevenly spaced).
    Measured: JOHNSON letters-only SSML 10.2s vs plain text WITH the question
    4.9s, synthesis 2.3s -> 0.9s. So the `delivered` tool response tells the
    model to STAY SILENT and listen -- the user has already been asked.
  - **Session language, language-first voice ladder**
    (`spellback_tts.resolve_spellback_voice`): frame + voice follow the
    session's spoken language through the same name->BCP-47 map as the ASR
    bias (`utils/language_codes.py`), so letters come out the way that
    language's speakers say them. The ladder keeps the LANGUAGE ahead of the
    persona: `{locale}-Chirp3-HD-{LIVE_VOICE_NAME}` -> any Chirp3 voice in
    that locale -> the locale's default voice -> en-US only when the language
    itself is unknown. (Live probe 2026-08-08: ru-RU carries 8 of the 30
    personas and no Iapetus; fil-PH/ur-PK/fa-IR/af-ZA carry none.) Availability
    is derived from `list_voices` at runtime, never a hand-pinned language
    list. Frames + per-language punctuation words are DATA
    (`backend/services/spellback_frames.json`, UTF-8).
- `switch_to_field` -- jump the form's focus to ONE specific field (correction/
  revisit path: "go back to my mailing city"), by field_id, spoken name, or a
  rough description; DISTINCT from `switch_section`, which moves whole
  sections and (in section mode) restarts the session (bd
  polyglot-pdf-jnjj.36). Declared in `backend/config.py`, dispatched in
  `CallbackHandler._handle_switch_to_field_tool`
  (`backend/services/callback_handler.py`); its frontend round-trip goes over
  the wire as `switch_field` / `switch_field_response`
  (`request_coordinator.py`, `websocket_routes.py`).

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
transcription block on by itself, and it is per-connect -- which is a natural fit,
since the spoken language is PINNED per session (bd polyglot-pdf-87a9,
[../standards/voice-and-vad.md](../standards/voice-and-vad.md)) and so the codes
are derived once, before the connect. Endpoint-verified
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
