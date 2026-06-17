---
date: 2026-06-17
beads: [polyglot-pdf-zivv]
pr: TBD
tags: [voice-ai, voice-and-vad, frontend]
---

# zivv: native VAD and PTT are mutually exclusive (the real "Gemini stops responding after PTT" fix)

## The real bug (and the false start)

Maintainer report: in native VAD, **pressing PTT makes Gemini stop responding.**
Native VAD alone works; PTT alone (manual mode) works; the two together break.

My first pass at this bead (earlier same session) read the code, found that the
backend `send_activity_end` already maps `activity_end` to `audio_stream_end` in
native mode (bd 6vo), concluded "works as designed," and closed zivv as not-a-bug.
**That was wrong.** The maintainer pushed back with the live symptom, and the
Cloud Run logs settled it: on every PTT release the frontend sent `vad_activity_end`
-> backend `audio_stream_end` -> **`GEMINI_INTERRUPTED`**, three times in nine
seconds, each killing the response. Reopened.

## Root cause: two incompatible turn-taking systems, used at once

Gemini's automatic (native) VAD and the manual turn signals
(`activity_start` / `activity_end` / `audio_stream_end`) are **mutually exclusive**.
Native VAD finds turn boundaries from a *continuous stream*; the manual signals
mark boundaries explicitly. Mixing them corrupts turn management. PTT was emitting
manual signals into a native-VAD session. Two compounding faults:

1. **`connection.ts` `sendActivityEnd` forwarded the end signal in native VAD**
   (the bd-6vo `audio_stream_end` path). `sendActivityStart` already suppressed in
   native VAD; `sendActivityEnd` did not. So every PTT release injected a
   turn-close into the continuous stream -> interrupt.
2. **`audioManager` STOPPED the stream when PTT was muted in native VAD.**
   `shouldSendAudioChunk` returned `false` for native+PTT-muted, so on release the
   client sent *nothing*. Native VAD then had no trailing audio to detect the
   boundary -> the turn never closed -> silence. (This is the same silence-stall
   the bd-6vo `audio_stream_end` was originally added to paper over -- but the
   right fix is silence, not a manual signal.)

## The fix

PTT under native VAD is **only a client-side audio gate** -- never a turn signal:

- **`connection.ts` `sendActivityEnd`**: add `if (nativeVad) return` (mirrors
  `sendActivityStart`). Under native VAD the client sends NO manual turn signal.
- **`audioManager`**: native VAD now ALWAYS streams (`shouldSendAudioChunk`
  returns `true` for native VAD regardless of mute); when PTT is muted
  (`pttModeEnabled && inputMuted`) the send path substitutes a **zeroed silence
  frame** for the real mic. The stream stays continuous (so native VAD finds the
  boundary from the trailing silence) without leaking the muted mic.

So the turn closes from the trailing silence, not a manual signal. This supersedes
bd-6vo/PR#119's `audio_stream_end`-on-release, which predated the silence-stream
gate and caused the conflict. The backend native `audio_stream_end` branch is left
in place as a dead-pathed server guard.

## Spec

Documented as a hard invariant in
[`docs/standards/voice-and-vad.md`](../../standards/voice-and-vad.md) -- new
section "SPEC: native VAD and manual turn signals are MUTUALLY EXCLUSIVE." Read it
before touching any PTT/VAD signal path.

## Verification

- **Live (the decisive one):** local stack on Vertex + native VAD; called the
  exact PTT code path (`connectionManager.sendActivityStart()` /
  `sendActivityEnd()` via the test-inject hook) and confirmed the backend received
  **zero** `vad_activity_*` events (pre-fix, the same `sendActivityEnd` sent
  `vad_activity_end` -> `audio_stream_end` -> interrupt). `isNativeVad()` was true.
- **Unit:** `audioGate.test.ts` + `connection.test.ts` flipped to assert the new
  contract (native VAD: `sendActivityEnd` suppressed; `shouldSendAudioChunk`
  always-true; caller substitutes silence) + a new manual-mode `activity_end`
  regression test. Full FE suite: 401 passed; tsc clean.

## Lesson

Before touching PTT/VAD signal paths, trace `activity_end` ->
`audio_stream_end` vs `activity_end` in the backend AND confirm against the LIVE
symptom -- not just the code's stated intent. I closed this as not-a-bug once by
trusting a stale code comment over the reported behavior. The live logs are the
arbiter.
