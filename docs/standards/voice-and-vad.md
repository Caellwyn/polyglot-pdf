# Voice & VAD (turn-taking modes)

**Tracks:** backend/config.py backend/adapters/live_ai_gemini.py backend/routes/websocket_routes.py backend/main.py backend/routes/vad_config_routes.py backend/vad_config.json frontend/src/shared/connection.ts frontend/src/shared/audioManager.ts frontend/src/webFormConnection.ts frontend/src/demo/useDemoVAD.ts frontend/src/demo/VoiceOverlay.tsx frontend/src/vad-tuning

*Last updated: 2026-07-05 (bd polyglot-pdf-mpoe staleness sweep: fixed a stale VAD-sensitivity default claim -- START was documented as `LOW` but config.py defaults it to `HIGH`; folded the `input_transcription` -> `on_user_activity` native-mode signal and the mic-energy-meter/send-gate relationship into the body from the old stamp chain). See [../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md](../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md).*

The cross-cutting rules for voice turn-taking: who decides when the user is
speaking, how barge-in works, and the language distinction. The Gemini Live
adapter internals are in [voice-ai.md](../components/voice-ai.md); model selection
is in [ai-models.md](ai-models.md).

## The VAD-mode toggle: `DISABLE_GEMINI_VAD`

A single env-overridable flag in `backend/config.py` chooses who detects
turn boundaries. **As of bd polyglot-pdf-333 the default is
`DISABLE_GEMINI_VAD = False` -> NATIVE mode** (Gemini's own automatic VAD drives
turns), a smoke test of the native VAD. Set `DISABLE_GEMINI_VAD=true` (env or the
default) to revert to MANUAL mode in one switch.

- **NATIVE mode (`DISABLE_GEMINI_VAD=False`, default):** Gemini's
  `automatic_activity_detection` is enabled with the `VAD_*` sensitivity knobs.
  The frontend **stops** sending manual `activity_start/end` and streams
  **continuous, ungated audio (incl. silence)** so Gemini's VAD has a stream to
  detect on. See "Native VAD mode" below.
- **MANUAL mode (`DISABLE_GEMINI_VAD=True`):** Gemini's VAD is off
  (`{'disabled': True}`) and turn-taking is driven by the frontend's client-side
  Silero VAD via manual `activity_start/end` signals (the rest of this section).

The flag flows to the frontend as `native_vad` in the `session_ready` handshake
(`websocket_routes.py`), and a backend guard on `send_activity_start/end`
(`live_ai_gemini.py`) drops any stray manual signal when native VAD is on -- so
the two ends can never land in the conflicting state below.

## Native-mode sensitivity: measured findings + chosen config (2026-06-11, bd 4sv7)

The demo's "short answers drop / rarely two turns in a row" bug was root-caused
by a measured A/B on the real audio path (SDK 2.8.0, the committed harness
fixtures incl. the short "yes that's correct" clip, continuous-silence
streaming; `scripts/spikes/diag_turn_reliability_4sv7.py`):

| model | VAD mode | turns registered |
|---|---|---|
| 2.5 native-audio | native, START=**LOW** (the old shipped config) | **14/20 (70%)** -- non-deterministic per session (4/8, 7/8, 3/4), exactly the live-demo feel |
| 2.5 native-audio | native, START=**HIGH** | **20/20**, plus a tool call on every turn |
| 2.5 / 3.1 | manual (activity signals) | 16/16 |
| 3.1 live-preview | native, LOW or HIGH | 16/16 (latency ~1.1-1.3 s vs 2.5's ~0.0-0.5 s) |

`START_SENSITIVITY_LOW` is the LESS sensitive setting: it misses short/quiet
utterance onsets entirely (no input transcription, no turn -- silence from the
user's perspective). **Chosen config: keep the 2.5 model + native VAD, set
`VAD_START_SENSITIVITY=HIGH`, keep `END=LOW` / `SILENCE_DURATION_MS=500`.**
The `VAD_*` settings in `backend/config.py` were hard-coded literals until bd
4sv7 made them env-overridable; the in-code default is now `START=HIGH`.
Zero `code=1011` closures were observed across ~24 sessions on 2026-06-11
(both models), consistent with bd `daa`'s "transient upstream outage" verdict.

Caveat: turn REGISTRATION is fixed by this; tool-call COMPLIANCE under the
app's full system instruction is a separate, pre-existing defect (2.5 hears the
"yes" but does not call `confirm_field`; 3.1 skips `update_form_fields`) --
tracked in bd `polyglot-pdf-i9q8` with the full E2E evidence.

## Manual mode: client-side VAD, not Gemini's

When `DISABLE_GEMINI_VAD = True` the backend turns **off** Gemini's automatic
activity detection and instead sends **manual** `activity_start` /
`activity_end` signals driven by the frontend's own client-side VAD (Silero, see
below). The adapter builds the config in
`LiveAIGemini._build_vad_settings(settings)` (called from `_run_session_loop`):

```python
# LiveAIGemini._build_vad_settings, schematic
if settings.DISABLE_GEMINI_VAD:
    return {'disabled': True}          # default mode: ONLY this key
# else: Gemini auto-VAD enabled — pass through the sensitivity / padding knobs
#       (start_of_speech_sensitivity, end_of_speech_sensitivity,
#        prefix_padding_ms, silence_duration_ms) that are set.
```

The return value is placed at
`config["realtime_input_config"]["automatic_activity_detection"]`.

The frontend VAD (`useDemoVAD.ts`) detects speech boundaries and fires
`connection.ts` `onVADSpeechStart` / `onVADSpeechEnd`, which relay
`vad_activity_start` / `vad_activity_end` over the WebSocket; the backend in turn
calls `LiveAIGemini.send_activity_start()` / `send_activity_end()`. **In native VAD
mode the frontend sends NEITHER signal** -- the `connection.ts` `sendActivityStart`
and `sendActivityEnd` wrappers both `if (nativeVad) return` (bd
`polyglot-pdf-zivv`); see the mutual-exclusion spec below. Only in **manual** mode
do they flow: `send_activity_start()` sends `activity_start=types.ActivityStart()`
and `send_activity_end()` sends `activity_end=types.ActivityEnd()`. **Ordering
matters (manual mode):** `activity_start` is sent *before* the audio chunks for
that utterance; the end signal flushes Gemini's buffer after.

> **Note on the backend `send_activity_end` native branch.** The backend adapter
> still contains a native-mode branch that would emit `audio_stream_end=True` (bd
> `polyglot-pdf-6vo`). That path is now effectively dead for the PTT flow because
> the frontend suppresses the signal before it reaches the backend (above). It is
> retained as a server-side guard but is **not** the turn-close mechanism under
> native VAD -- the trailing **silence stream** is (see the spec below).

> The Gemini-side VAD sensitivity knobs (`VAD_START_SENSITIVITY`,
> `VAD_END_SENSITIVITY`, `VAD_PREFIX_PADDING_MS`, `VAD_SILENCE_DURATION_MS` in
> config.py) are sent **only when `DISABLE_GEMINI_VAD = False`** — i.e. in native
> mode (the current default). They currently ship as `HIGH`/`LOW`/`500ms`/`500ms`
> (the measured config chosen in bd 4sv7 above -- START=HIGH for reliable turn
> registration, END=LOW/500ms kept conservative). In manual mode
> (`disabled = True`) the connect config sends **only** `{'disabled': True}` and
> omits these fields entirely. This is mandatory: the Live API rejects (1007) a
> config that sets `disabled = True` *and* any sensitivity/padding field together.

## SPEC: native VAD and manual turn signals are MUTUALLY EXCLUSIVE (bd polyglot-pdf-zivv)

**This is a hard invariant. Read it before touching any PTT or VAD signal path.**

Gemini's automatic (native) VAD and the manual turn signals
(`activity_start` / `activity_end` / `audio_stream_end`) are **two separate,
incompatible turn-taking systems**. You pick ONE per session:

- **Manual VAD** (`DISABLE_GEMINI_VAD=true`): the client runs Silero VAD and sends
  `activity_start` / `activity_end` to mark turn boundaries. Audio flows only
  during a detected turn.
- **Native VAD** (`DISABLE_GEMINI_VAD=false`, the demo default): Gemini's own VAD
  finds turn boundaries from a **continuous audio stream**. The client sends
  **NO manual turn signals at all** -- not `activity_start`, not `activity_end`,
  not `audio_stream_end`. Injecting any of them into the continuous stream
  interrupts/closes Gemini's in-flight turn mid-response. The live symptom was
  "**Gemini stops responding after I press PTT**": each PTT release was emitting a
  turn-end signal that killed the response.

**PTT under native VAD is ONLY a client-side audio gate -- never a turn signal.**
When the user holds PTT, the real mic audio flows; when released, PTT must:

1. **NOT send any activity/stream-end signal** (`connection.ts` `sendActivityStart`
   and `sendActivityEnd` both `if (nativeVad) return`).
2. **Keep the stream CONTINUOUS by sending SILENCE** while muted -- NOT stop
   sending. Native VAD needs trailing audio to detect the boundary; a dead stream
   leaves the turn open forever (the same silence-stall the test harness works
   around). `audioManager` substitutes a zeroed frame for the muted mic in native
   mode (`shouldSendAudioChunk` returns `true` for native VAD regardless of mute;
   the send path zeroes the chunk when `pttModeEnabled && inputMuted`).

So under native VAD the turn closes from the **trailing silence**, not from a
manual end signal. Under manual VAD, the signals are required and flow normally.
This supersedes the earlier bd-6vo/PR#119 approach (which forwarded
`audio_stream_end` on PTT release); that predated the silence-stream gate and was
the direct cause of the conflict.

## Native VAD mode (default, bd polyglot-pdf-333)

When `DISABLE_GEMINI_VAD = False`, Gemini's own VAD drives **turn-taking**, so the
frontend stops sending manual turn signals -- but **PTT survives as a client-side
audio gate** layered on top (bd polyglot-pdf-6vo), so the two concerns are
separated: Gemini owns *when a turn starts/ends*; PTT owns *which client bytes are
sent at all* (noisy-room support).

- **No manual activity signals.** The backend advertises
  `native_vad: true` in the `session_ready` handshake.
  `WebFormConnection.handleSessionReady` relays it to
  `ConnectionCallbacks.onNativeVadMode`, which sets a `nativeVad` flag in the
  `connection.ts` closure. That flag short-circuits ALL activity-signal sites: the
  `sendActivityStart` AND `sendActivityEnd` wrappers (both `if (nativeVad) return`
  -- bd zivv) and the `onVADSpeechStart/End` Silero callbacks. `shouldRunVAD` keeps
  client Silero VAD off in native mode. Belt-and-suspenders: the adapter's
  `send_activity_start/end` also no-op / are dead-pathed server-side. **PTT does
  not change this** -- PTT only gates the audio bytes; it emits no turn signal.
- **Continuous stream ALWAYS -- silence when PTT-muted.** Gemini's VAD needs the
  full stream -- including silence -- to find turn boundaries. The audio routing
  decision lives in the pure `shouldSendAudioChunk()` (`audioManager.ts`): in
  native mode it returns `true` **always** (the stream never stops). When PTT is on
  and the button is released (`inputMuted=true`), the send path substitutes a
  **zeroed (silence) frame** for the real mic so the stream stays continuous
  without leaking the muted mic (bd zivv -- stopping the stream here is what made
  Gemini go silent after release). `setNativeVad(true)` still puts the **worklet
  RMS noise gate** into bypass, and `setPTTMode` keeps that bypass active under
  native VAD regardless of PTT (`enabled || nativeVadEnabled`) -- so toggling PTT
  off does not re-arm the RMS gate and starve the stream. The bypass is re-applied
  whenever the worklet node is (re)created.
- **PTT is a live, always-available gate.** In native mode the Input-Mode toggle is
  **enabled** and the Hold-to-Talk button **renders** (the old `!nativeVad` /
  `isNativeVad()` early-returns were removed). Toggling drives `muteInput`/
  `unmuteInput`; the PTT press/release handlers own their own
  `flushAudioQueue`/`resumePlayback` pair, so they are safe under native VAD (the
  #110 hazard only applied to *forcing* `pushToTalkMode=false`, which would start
  Silero -- still prevented by `shouldRunVAD`). The label reads **PTT** (gated) or
  **Auto** (continuous); there is no longer a disabled "Native" state. The *backend*
  VAD mode is still set by `DISABLE_GEMINI_VAD` and is not client-switchable
  mid-session -- but PTT no longer needs to switch it.
- **Server-side "user is speaking" signal.** Under native VAD there is no manual
  `activity_start` to key off of, so the adapter's `on_user_activity` callback
  (`live_ai_gemini.py`) instead fires when Gemini's `server_content` carries a
  non-empty `input_transcription` -- the only reliable "the user said something"
  signal in this mode (background noise/silence never produce one). This single
  callback feeds two consumers: the idle watchdog (see below) and the
  thinking-indicator's `agent_processing` wire type (registered in
  [ws-protocol.md](ws-protocol.md)). Confirmed firing on the 2.5 native-audio
  model at `VAD_START_SENSITIVITY=HIGH` (the default) on the deployed Vertex
  model and live E2E (bd polyglot-pdf-fa4x).

Revert is the single flag: set `DISABLE_GEMINI_VAD=true` and turn-taking falls back
to client Silero VAD; PTT behaves the same in both backend modes.

## The client VAD thresholds (Silero)

The frontend VAD is **Silero** (ONNX), not a hand-rolled energy gate. Its tuned
defaults are `DEFAULT_VAD_CONFIG` in `frontend/src/demo/useDemoVAD.ts`:

| Param | Value | Meaning |
|-------|------:|---------|
| `positiveSpeechThreshold` | 0.85 | model confidence to *start* speech |
| `negativeSpeechThreshold` | 0.65 | hysteresis threshold to *end* speech |
| `minSpeechMs` | 250 | minimum speech duration to count |
| `redemptionMs` | 400 | grace before declaring speech ended |

These can be overridden per-session via `VADOptions.sensitivity`; the
`frontend/src/vad-tuning/` dashboard tunes them live and persists overrides in the
browser (`localStorage`), exporting a snapshot file for sharing. The post-barge-in
tool-call rejection window is a **separate** hardcoded constant —
`BARGE_IN_GRACE_PERIOD_MS = 150` in `frontend/src/shared/metrics.ts`. Barge-in /
latency metrics are collected in metrics.ts (local-only — see
[hipaa-pii-policy.md](hipaa-pii-policy.md)).

> **Two different "VAD configs" — don't conflate them.** `backend/vad_config.json`
> (`{startSensitivity, endSensitivity, prefixPadding, silenceDuration}`) holds
> *Gemini-side* automatic-VAD knobs — a **different** thing from the client Silero
> thresholds above. It's served by a WebSocket at `/ws/vad-config` (mounted in
> `main.py`, handler `vad_config_websocket`). **Caveat:** the live adapter reads its
> Gemini-VAD settings from `Settings` (the `VAD_*` env fields, next section), **not**
> from `vad_config.json`, and with `DISABLE_GEMINI_VAD=True` those Gemini-side knobs
> are inert anyway — so writing `vad_config.json` via that endpoint has no effect on
> the running session today. Cleanup tracked in bd `polyglot-pdf-9jv`.

## Barge-in

When the user starts talking while Gemini is speaking, the frontend
(`connection.ts` `onVADSpeechStart`) immediately flushes its local audio queue
(`audioManager.flushAudioQueue()`) for instant UX. The backend separately watches
Gemini's own `server_content.interrupted` flag, but on it the adapter only **logs
`GEMINI_INTERRUPTED`, resets its audio tracking, and skips the event** — it does
**not** send any flush signal back to the client (there is no server sentinel; the
flush is entirely frontend-side). See [voice-ai.md](../components/voice-ai.md#barge-in).
**Push-to-talk mode** (`setPushToTalkMode(true)`, the default in `VoiceOverlay`)
disables the energy-based barge-in path entirely (`onVADSpeechStart`/`End`
early-return).

> **Native VAD mode delta (bd polyglot-pdf-333).** In native mode
> (`DISABLE_GEMINI_VAD=False`, the default) `onVADSpeechStart` early-returns on the
> `nativeVad` flag, so the **instant client-side flush is disabled** — Gemini owns
> interruption via its own `server_content.interrupted`. Barge-in latency is then
> Gemini's interrupt round-trip rather than instant; this is an accepted UX delta
> for the smoke test.

There's a barge-in **grace period**: tool calls arriving within
`BARGE_IN_GRACE_PERIOD_MS` (150ms, a constant in
`frontend/src/shared/metrics.ts`) of a barge-in are treated as hallucinations from
the interrupted generation and rejected (`metrics.recordToolCall` → `reject`; see
`connection.ts onFieldUpdate`).

## Mic send gate (audio-up path)

Every mic-arming site (initial `startRecording`, `rearmAudioCapture`, and the
`startSection`/`switchToSection` re-arms) shares ONE send callback in
`frontend/src/shared/connection.ts`, gated by the pure function
`shouldSendMicChunk(status, socketOpen)` (bd polyglot-pdf-xroy):

- `connected` → always send.
- `switching_section` **with the WebSocket open** → send. Safe because the
  backend discards switch-window audio server-side on BOTH switch paths: the
  `drop_audio` flag in `websocket_routes.py` (manual switch), and
  `FormFillingService.stream_audio`'s `_switch_lock.locked()` backstop, which
  also covers the AI-initiated `switch_section` swap.
- Anything else (or socket closed) → **drop, never silently**: a rate-limited
  (~1/s) `console.warn` reports the status + socket state. Silent mic loss is
  what made the 2026-06-10 demo hang invisible.

The demo's mic-energy meter (visual level indicator, bd polyglot-pdf-s3zv) only
**reads** this same send gate to decide whether to animate -- it does not alter
`shouldSendMicChunk` or introduce a second gating path.

Every `WebFormConnection.status` transition is logged `old->new (reason)` so a
stranded status is visible in the console.

## fill-language vs spoken-language

Two independent language axes — don't conflate them:

- **fill-language** — the language values are written into the form in. Changed via
  `change_fill_language` (`service.change_fill_language`); defaults to `English`.
- **spoken-language** — the language Gemini *converses* in. Changed via
  `change_spoken_language`, which makes the backend send an *initiating message* so
  Gemini greets and resumes in the new language.

## Hallucination reduction

Two standing mitigations:
- **Single-field updates only.** `update_form_fields` takes ONE field per call;
  multi-field updates raised hallucination rates. (Marked HALLUCINATION_REDUCTION
  in config.py.)
- **No proactive audio.** Gemini's `proactive_audio` connect option is never set:
  enabling it made Gemini ignore dirty/choppy audio but also stop calling tools,
  so the adapter must not turn it on. (The old `PROACTIVE_AUDIO` config flag was
  removed as dead code — it was hardwired `False`.)
