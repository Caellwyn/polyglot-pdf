# Voice & VAD (turn-taking modes)

**Tracks:** backend/config.py backend/adapters/live_ai_gemini.py backend/routes/websocket_routes.py backend/main.py backend/routes/vad_config_routes.py backend/vad_config.json frontend/src/shared/connection.ts frontend/src/shared/audioManager.ts frontend/src/webFormConnection.ts frontend/src/demo/useDemoVAD.ts frontend/src/demo/VoiceOverlay.tsx frontend/src/vad-tuning

*Last updated: 2026-06-04. See [journal/entries/2026-06-04-bd-333-native-vad-smoke-test.md](../journal/entries/2026-06-04-bd-333-native-vad-smoke-test.md) for closeout details.*

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
calls `LiveAIGemini.send_activity_start()` /
`send_activity_end()` →
`session.send_realtime_input(activity_start=types.ActivityStart())` (and
`ActivityEnd()`). **Ordering matters:** `activity_start` is sent *before* the audio
chunks for that utterance; `activity_end` flushes Gemini's buffer after.

> The Gemini-side VAD sensitivity knobs (`VAD_START_SENSITIVITY`,
> `VAD_END_SENSITIVITY`, `VAD_PREFIX_PADDING_MS`, `VAD_SILENCE_DURATION_MS` in
> config.py) are sent **only when `DISABLE_GEMINI_VAD = False`** — i.e. in native
> mode (the current default). They currently ship as `LOW`/`LOW`/`500ms`/`500ms`
> (conservative, deterministic for the smoke test). In manual mode
> (`disabled = True`) the connect config sends **only** `{'disabled': True}` and
> omits these fields entirely. This is mandatory: the Live API rejects (1007) a
> config that sets `disabled = True` *and* any sensitivity/padding field together.

## Native VAD mode (default, bd polyglot-pdf-333)

When `DISABLE_GEMINI_VAD = False`, Gemini's own VAD drives turn-taking and the
frontend must get out of the way on **both** axes:

- **No manual activity signals.** The backend advertises `native_vad: true` in the
  `session_ready` handshake. `WebFormConnection.handleSessionReady` relays it to a
  new `ConnectionCallbacks.onNativeVadMode`, which sets a `nativeVad` flag in the
  `connection.ts` closure. That flag short-circuits all five activity-signal sites
  (the `sendActivityStart/End` wrappers used by the PTT button, and
  `onVADSpeechStart/End` used by Silero). Belt-and-suspenders: the adapter's
  `send_activity_start/end` also no-op server-side when native VAD is on, so a
  stray signal can't create the conflicting turn-taking state.
- **Continuous, ungated audio.** Gemini's VAD needs the full stream — including
  silence — to find turn boundaries. `audioManager.setNativeVad(true)` makes the
  worklet `onmessage` handler bypass the `inputMuted/vadActive` privacy gate AND
  the all-zero silence skip, and it reuses the `setPTTMode` worklet message to put
  the **audio worklet's RMS noise gate** into bypass (otherwise the worklet would
  zero sub-threshold audio before JS ever sees it). The bypass is re-applied
  whenever the worklet node is (re)created, so a reconnect can't silently re-arm
  the gate.
- **PTT button is inert.** In native mode the PTT effects in `VoiceOverlay.tsx` /
  `VoiceOverlayMobile.tsx` early-return on `connectionManager.isNativeVad()`, so a
  PTT toggle can't re-arm the noise gate or mute the (now continuous) stream.

Revert is the single flag: set `DISABLE_GEMINI_VAD=true` and every gate falls back
to the manual-VAD behavior described above — the non-native code paths are
unchanged.

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
