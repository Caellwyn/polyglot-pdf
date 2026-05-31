# Voice & VAD (manual activity signals)

**Tracks:** backend/config.py backend/adapters/live_ai_gemini.py backend/routes/vad_config_routes.py backend/vad_config.json frontend/src/shared/connection.ts frontend/src/demo/useDemoVAD.ts frontend/src/vad-tuning

*Last updated: 2026-05-31*

The cross-cutting rules for voice turn-taking: who decides when the user is
speaking, how barge-in works, and the language distinction. The Gemini Live
adapter internals are in [voice-ai.md](../components/voice-ai.md); model selection
is in [ai-models.md](ai-models.md).

## Client-side VAD, not Gemini's

`DISABLE_GEMINI_VAD = True` in `backend/config.py` — and it's marked CRITICAL.
The backend turns **off** Gemini's automatic activity detection and instead sends
**manual** `activity_start` / `activity_end` signals driven by the frontend's own
energy-based VAD. Concretely, in the adapter's `connect()` config:

```python
if settings.DISABLE_GEMINI_VAD:
    vad_settings['disabled'] = True
config["realtime_input_config"] = {"automatic_activity_detection": vad_settings}
```

The frontend VAD (`useDemoVAD.ts`) decides speech boundaries and emits
`vad_activity_start` / `vad_activity_end` over the WebSocket; the backend relays
them as `LiveAIGemini.send_activity_start()` /
`send_activity_end()` →
`session.send_realtime_input(activity_start=types.ActivityStart())` (and
`ActivityEnd()`). **Ordering matters:** `activity_start` is sent *before* the audio
chunks for that utterance; `activity_end` flushes Gemini's buffer after.

> The Gemini-side VAD sensitivity knobs (`VAD_START_SENSITIVITY`,
> `VAD_END_SENSITIVITY`, `VAD_PREFIX_PADDING_MS`, `VAD_SILENCE_DURATION_MS` in
> config.py) are still wired into the connect config, but with
> `automatic_activity_detection.disabled = True` they're inert in the current
> default mode. They're kept for the fallback of re-enabling Gemini VAD.

## The energy-VAD tuning config

The client VAD's thresholds are NOT hardcoded — they live in
`backend/vad_config.json` and are served/updated through
`backend/routes/vad_config_routes.py` (`GET` / `PUT /api/vad-config`). Current
config:

| Param | Value | Meaning |
|-------|------:|---------|
| `energyThreshold` | 0.015 | RMS energy above which a frame counts as speech |
| `speechStartFrames` | 3 | consecutive speech frames to declare speech start |
| `speechEndFrames` | 10 | consecutive silence frames to declare speech end |
| `preBufferFrames` | 5 | frames of pre-speech audio to prepend |
| `gracePeriodFrames` | 8 | post-barge-in window (tool-call rejection guard) |

The `frontend/src/vad-tuning/` dashboard (`VADTuningDashboard.tsx`,
`VADControlPanel.tsx`, `useVADConfig.ts`) reads/writes this config live for tuning
on real hardware (e.g. the Fire HD tablet). Barge-in/latency metrics for tuning are
collected in `frontend/src/shared/metrics.ts` (local-only — see
[hipaa-pii-policy.md](hipaa-pii-policy.md)).

## Barge-in

When the user starts talking while Gemini is speaking, the frontend
(`connection.ts` `onVADSpeechStart`) immediately flushes its local audio queue for
instant UX, and the backend independently watches for Gemini's own
`server_content.interrupted` flag — on which it sends a `b"__INTERRUPT__"` sentinel
through the audio callback so the frontend flushes playback. **Push-to-talk mode**
(`setPushToTalkMode(true)`) disables the energy-based barge-in path entirely
(`onVADSpeechStart`/`End` early-return).

There's a barge-in **grace period**: tool calls arriving within ~150ms of a
barge-in are treated as hallucinations from the interrupted generation and rejected
(`metrics.recordToolCall` → `reject`; see `connection.ts onFieldUpdate`).

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

*Last updated: 2026-05-31*
