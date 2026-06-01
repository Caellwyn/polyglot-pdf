# Voice & VAD (manual activity signals)

**Tracks:** backend/config.py backend/adapters/live_ai_gemini.py backend/main.py backend/routes/vad_config_routes.py backend/vad_config.json frontend/src/shared/connection.ts frontend/src/demo/useDemoVAD.ts frontend/src/vad-tuning

*Last updated: 2026-06-01. See [journal/entries/2026-06-01-bd-gfb.4-rename-section-state-vars-mis-named-part-to.md](../journal/entries/2026-06-01-bd-gfb.4-rename-section-state-vars-mis-named-part-to.md) for closeout details.*

The cross-cutting rules for voice turn-taking: who decides when the user is
speaking, how barge-in works, and the language distinction. The Gemini Live
adapter internals are in [voice-ai.md](../components/voice-ai.md); model selection
is in [ai-models.md](ai-models.md).

## Client-side VAD, not Gemini's

`DISABLE_GEMINI_VAD = True` in `backend/config.py` — and it's marked CRITICAL.
The backend turns **off** Gemini's automatic activity detection and instead sends
**manual** `activity_start` / `activity_end` signals driven by the frontend's own
client-side VAD (Silero, see below). The adapter builds the config in
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
> config.py) are sent **only when `DISABLE_GEMINI_VAD = False`** — i.e. when
> Gemini's automatic detection is enabled. In the current default mode
> (`disabled = True`) the connect config sends **only** `{'disabled': True}` and
> omits these fields entirely. This is mandatory: the Live API rejects (1007) a
> config that sets `disabled = True` *and* any sensitivity/padding field
> together. The knobs are kept for the fallback of re-enabling Gemini VAD (e.g.
> the native-VAD smoke test, bd `polyglot-pdf-333`).

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

*Last updated: 2026-06-01. See [journal/entries/2026-06-01-bd-gfb.4-rename-section-state-vars-mis-named-part-to.md](../journal/entries/2026-06-01-bd-gfb.4-rename-section-state-vars-mis-named-part-to.md) for closeout details.*
