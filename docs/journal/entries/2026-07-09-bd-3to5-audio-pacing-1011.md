---
date: 2026-07-09
bead: polyglot-pdf-3to5
title: "Pace audio to Gemini at real-time to stop the recurring 1011 churn; + handshake gate + not-listening ear; + pause-resume playback fix"
tags: [bugfix, voice-ai, frontend, audio, 1011]
---

## Trigger

Verifying an unrelated pause/resume playback fix on a local Vertex run surfaced the
voice session tearing down and reconnecting every ~60-90s. Each reconnect cost a
~4.5s Vertex handshake of dead air -- the "stall on question 2 + trouble-connecting
modal" the maintainer reported.

## Root cause (measured, not guessed)

The backend was streaming mic audio to Gemini/Vertex at **~2.2x real-time**, which
trips Gemini's `1011 "Input data processing failed - client sending data too fast"`
flow-control kill. Evidence from `backend/logs/gemini_*.jsonl`:

- INBOUND (client -> backend queue) was a clean **1.0x** real-time (32,000 B/s). The
  client sends correctly; the excess is manufactured inside the backend.
- OUTBOUND (backend -> Gemini) was a sustained **~2.2x** (68-74k B/s), through frame
  2300+ (not a connect-backlog artifact).
- The excess IS the gap-fill silence: in one 60s session, 3,300 of 10,200 sent
  frames were injected 640-byte silence vs 6,900 real 256-byte frames -> silence was
  **~54% of outbound bytes**.

The gap-fill (bd polyglot-pdf-7f7m, PR #348) waits only `AUDIO_GAPFILL_INTERVAL_MS`
(25ms) then injects a 20ms silence frame -- un-paced -- on every sub-interval gap
between the client's bursty 8ms frames. It fixed UNDERruns but never throttled
OVERruns, and actively manufactured this one. (The maintainer's "that fix may have
made it worse" was correct.) A second, smaller contributor: audio enqueued during
the ~4.5s Gemini connect (before any consumer exists) filled the maxsize=100 queue
and burst on drain -- because the backend's client-facing `session_ready` fires
~4.5s BEFORE the real Gemini session is ready.

Ruled out: NOT the pause button (continuous, both PTT + Auto), NOT client Silero VAD
(correctly off in native mode -- the `[pause] Pausing VAD` log is that), NOT an
AI-Studio fallback (100% Vertex, `gemini-live-2.5-flash-native-audio`), NOT a DTI
regression (continuous session is in place; reconnects resume the whole form).

## What shipped (one PR, bd 3to5)

1. **CORE -- real-time pacing** (`live_ai_gemini.py` `_audio_sender_loop`): a fixed
   `WS_CHUNK_MS` monotonic-clock tick over a byte accumulator re-chunked to 640-byte
   output frames. `next_send` advances by a FIXED interval, so the cadence is
   real-time and can never burst to catch up; if a send blocks past a tick,
   `next_send = now` (degrade to real-time-or-slower, NEVER faster). Silence is sent
   ONLY on a genuine underrun tick (native-VAD, gap-fill-enabled, not shutting down).
   The graceful-stop tail is paced too (drain buffered whole frames one per tick;
   drop the <640B remainder, <=19ms). Excess is bounded by `AUDIO_MAX_BUFFER_MS`
   (200ms, drop OLDEST frame-aligned). New `AUDIO_PACING_ENABLED` (default on) +
   `AUDIO_MAX_BUFFER_MS` config. Injected `_clock`/`_sleep` hooks make it
   deterministically unit-testable. The legacy un-paced gap-fill path is preserved
   behind `AUDIO_PACING_ENABLED=false` as a clean revert switch.
2. **Handshake readiness gate** (`live_ai_gemini.stream_audio`): drop audio while
   `not _session_ready` so no consumerless backlog forms during the connect window.
   Counted + rate-limited-logged; surfaced as `pre_ready_dropped` in the
   session-close rollup. Deliberately does NOT move the overloaded client-facing
   `session_ready` message.
3. **Not-listening ear UX** (`VoiceOverlay.tsx` + `VoiceOverlayMobile.tsx`): the
   overlay "ear" now shows CROSSED-OUT (`vff-listening--muted`, a CSS diagonal-strike
   pseudo-element on the existing U+1F442 glyph) during
   connecting/reconnecting/switching_section, so the not-listening window reads as
   such instead of the ear vanishing. `VoiceOverlayListeningIndicator.test.tsx`
   updated (the old switching/reconnecting HIDDEN assertions flip to PRESENT+muted).
4. **Pause-resume playback fix** (`connection.ts` `resume()`): `pause()` calls
   `flushAudioQueue()` (sets `playbackBlocked=true`); `resume()` never cleared it, so
   after pause->resume every AI audio chunk was silently dropped in `playAudio()` --
   the mic came back but the AI's voice never did. `resume()` now calls
   `resumePlayback()`. This was the session's original task; bundled here as it's the
   same voice-playback-reliability story.

## Verification (local Vertex + voice-harness)

- Outbound byte-rate held **1.00x real-time (~32,000 B/s)**, sustained (was ~2.2x).
- **Zero 1011**; one session ran 3000 contiguous paced frames (=60s) with no reset.
- Fill loop intact: harness injected the digits fixture -> field
  `p1_line1_aliennumber` filled `1234567` via `update_form_fields`, native VAD on
  (pacing did not break turn detection).
- Backend suite 991 passed (17 new pacing/gate tests in `test_audio_pacing.py`;
  the 6 legacy gap-fill tests run under `AUDIO_PACING_ENABLED=false`); frontend 850
  passed (updated listening-indicator + the resume() test).

## Doc review (stale-doc warnings)

closeout_prep flagged several tier-2 standards as stale by mtime (my edit touched
adjacent code). Reviewed: none document the audio sender-loop cadence or the
gap-fill config, so no current-state doc is made wrong by this change. The only doc
mentioning gap-fill is the tier-3 7f7m journal entry (historical, correct as-is).
No tier-1/tier-2 doc update needed; noting the review here per the prep protocol.

## Scar tissue

- `session_ready` is sent to the client ~4.5s before the backend's Gemini session
  can consume audio. The client (correctly) arms the mic on `connected`; the fix is
  backend-side (drop pre-ready audio + pace), NOT delaying the overloaded
  `session_ready` message.
- Audio pacing MUST be byte/duration based, not frame-count based: the frontend
  worklet emits 8ms/256-byte frames while gap-fill + config assume 20ms/640-byte, so
  the queue holds variable-size frames.
- A first draft discarded ALL buffered audio on the sentinel; the sentinel must
  drain the buffered whole frames (paced) before exiting, or trailing speech is lost.
