# Voice & VAD (turn-taking modes)

**Tracks:** backend/config.py backend/adapters/live_ai_gemini.py backend/routes/websocket_routes.py backend/main.py backend/routes/vad_config_routes.py backend/vad_config.json frontend/src/shared/connection.ts frontend/src/shared/audioManager.ts frontend/src/webFormConnection.ts frontend/src/demo/useDemoVAD.ts frontend/src/demo/VoiceOverlay.tsx frontend/src/vad-tuning

*Last updated: 2026-06-12 (tool-call-compliance note: i9q8 resolved, both models
reliable). See [journal/entries/2026-06-11-bd-wpw.4-untyped-tool-param.md](../journal/entries/2026-06-11-bd-wpw.4-untyped-tool-param.md) for the untyped-param fix, [journal/entries/2026-06-10-bd-xroy-voice-surface-investigation-and-hardening.md](../journal/entries/2026-06-10-bd-xroy-voice-surface-investigation-and-hardening.md) for the mic send-gate hardening, [journal/entries/2026-06-08-bd-6vo-ptt-gate-over-native-vad.md](../journal/entries/2026-06-08-bd-6vo-ptt-gate-over-native-vad.md) for PTT-as-a-client-gate over always-on native VAD, and [journal/entries/2026-06-04-bd-333-native-vad-smoke-test.md](../journal/entries/2026-06-04-bd-333-native-vad-smoke-test.md) for the native-VAD smoke test.*

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

Note: the VAD work here fixes turn REGISTRATION. Tool-call COMPLIANCE is
separate and reliable on both models -- each emits `update_form_fields` +
`confirm_field` every turn (A/B on native-hi: 8/8 turns + 4/4 short-"yes"
confirms per model). See [ai-models.md](ai-models.md) for the model rationale.

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
calls `LiveAIGemini.send_activity_start()` / `send_activity_end()`. The signal
`send_activity_end()` emits is **mode-dependent**: in **native** mode (the default,
`DISABLE_GEMINI_VAD=False`) it sends `session.send_realtime_input(audio_stream_end=True)`
— the realtime signal compatible with automatic VAD; sending a raw `ActivityEnd()`
there conflicts with Gemini's own VAD and can leave the turn open (bd
`polyglot-pdf-6vo`). Only in **manual** mode does it send
`activity_end=types.ActivityEnd()`. `send_activity_start()` sends
`activity_start=types.ActivityStart()` in manual mode and is a no-op in native
mode. **Ordering matters (manual mode):** `activity_start` is sent *before* the
audio chunks for that utterance; the end signal flushes Gemini's buffer after.

> The Gemini-side VAD sensitivity knobs (`VAD_START_SENSITIVITY`,
> `VAD_END_SENSITIVITY`, `VAD_PREFIX_PADDING_MS`, `VAD_SILENCE_DURATION_MS` in
> config.py) are sent **only when `DISABLE_GEMINI_VAD = False`** — i.e. in native
> mode (the current default). They currently ship as `LOW`/`LOW`/`500ms`/`500ms`
> (conservative, deterministic for the smoke test). In manual mode
> (`disabled = True`) the connect config sends **only** `{'disabled': True}` and
> omits these fields entirely. This is mandatory: the Live API rejects (1007) a
> config that sets `disabled = True` *and* any sensitivity/padding field together.

## Native VAD mode (default, bd polyglot-pdf-333)

When `DISABLE_GEMINI_VAD = False`, Gemini's own VAD drives **turn-taking**, so the
frontend stops sending manual turn signals -- but **PTT survives as a client-side
audio gate** layered on top (bd polyglot-pdf-6vo), so the two concerns are
separated: Gemini owns *when a turn starts/ends*; PTT owns *which client bytes are
sent at all* (noisy-room support).

- **No manual activity signals (unchanged).** The backend advertises
  `native_vad: true` in the `session_ready` handshake.
  `WebFormConnection.handleSessionReady` relays it to
  `ConnectionCallbacks.onNativeVadMode`, which sets a `nativeVad` flag in the
  `connection.ts` closure. That flag short-circuits all five activity-signal sites
  (the `sendActivityStart/End` wrappers and `onVADSpeechStart/End` used by Silero),
  and `shouldRunVAD` keeps client Silero VAD off in native mode. Belt-and-suspenders:
  the adapter's `send_activity_start/end` also no-op server-side when native VAD is
  on. **PTT does not change this** -- a PTT press still calls `sendActivityStart`,
  which is a no-op in native mode; PTT only gates the audio bytes.
- **Continuous stream by default, PTT-gatable.** Gemini's VAD needs the full stream
  -- including silence -- to find turn boundaries. The audio routing decision lives
  in the pure `shouldSendAudioChunk()` (`audioManager.ts`): in native mode it streams
  continuously **unless PTT is on**, in which case it sends only while the button is
  held (`inputMuted=false`). `setNativeVad(true)` still puts the **worklet RMS noise
  gate** into bypass, and `setPTTMode` keeps that bypass active under native VAD
  regardless of PTT (`enabled || nativeVadEnabled`) -- so toggling PTT off does not
  re-arm the RMS gate and starve the stream. The bypass is re-applied whenever the
  worklet node is (re)created.
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

Two standing mitigations (both marked HALLUCINATION_REDUCTION in config.py):
- **Single-field updates only.** `update_form_fields` takes ONE field per call;
  multi-field updates raised hallucination rates.
- **`PROACTIVE_AUDIO = False`.** Enabling it made Gemini ignore dirty/choppy audio
  but also stop calling tools — deprecated, left off.
