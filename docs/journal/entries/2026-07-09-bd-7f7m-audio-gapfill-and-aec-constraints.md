---
date: 2026-07-09
bead: polyglot-pdf-7f7m
title: "fix(voice): backend audio-cadence gap-filling + centralized mic AEC constraints (1011 mitigation)"
tags: [performance, refactor, testing]
---

## Trigger

Two beads from the 1011-mitigation landscape (the intermittent Gemini Live
`1011 internal error` disconnects), both aimed at keeping the native-VAD audio
path healthy:

- **polyglot-pdf-7f7m** (P1): the backend forwarded audio to Gemini by blocking
  indefinitely on the send queue, so a client-side stutter produced a real GAP on
  the wire. Native-VAD mode needs a CONTINUOUS PCM stream; a gap can starve
  Gemini's keepalive and trip a 1011.
- **polyglot-pdf-gnmo** (P2): strengthen client-side acoustic echo cancellation
  so Gemini's own playback does not leak into the mic, get read as a barge-in, and
  desync the turn state into a 1011.

Both were bundled into one PR (opposite sides of the WebSocket, different
languages, zero shared code -- so no shared "audio service", but both are small
and serve the same 1011-reduction goal, so one review cycle).

## What shipped

**Backend gap-filling (7f7m).** The audio sender loop was lifted from an inline
closure inside `_handle_session` to a testable method
`LiveAIGemini._audio_sender_loop(session)`. The indefinite `queue.get()` is
replaced by `asyncio.wait_for(get(), timeout=AUDIO_GAPFILL_INTERVAL_MS)` -- but
ONLY after the first real chunk has streamed. On timeout it sends ONE synthetic
all-zero PCM16 frame (`rate * chunk_ms/1000 * 2` bytes = 640B at 16kHz/20ms) so
the wire cadence never breaks. Gated OFF unless native VAD is on (manual/PTT mode
brackets audio with activity_start/end, so injecting silence between turns is
wrong), before first real audio (nothing to keep alive yet), and once
`_close_after_flush`/`_intentional_shutdown` is set (the drain path owns the socket
+ the `None` sentinel then; on that path a timeout falls back to a blocking `get()`
so the sentinel still exits cleanly). New env-overridable config:
`AUDIO_GAPFILL_ENABLED` (default true) + `AUDIO_GAPFILL_INTERVAL_MS` (default 25ms
= one 20ms chunk + jitter margin, so the worst-case wire gap stays within ~one
chunk interval).

Coverage: `backend/tests/unit/test_audio_gapfill.py` (6 tests) -- real passthrough
+ sentinel exit; gap -> silence while streaming; no silence before first chunk; no
silence after the shutdown flag; disabled = legacy blocking; gap-fill gated off in
manual VAD. Existing adapter suites green after the closure -> method refactor;
full backend suite green (941 passed, 2 skipped).

**Client AEC constraints (gnmo) -- SCOPE NARROWED after code verification.** The
bead's original premise (from a pasted Gemini-chat analysis) was that the two
separate browser AudioContexts DEFEAT echo cancellation and must be merged. Reading
the actual code refuted that for our setup: there is NO WebRTC anywhere -- playback
is pure Web Audio (`AudioContext -> destination`), `echoCancellation: true` is
already set on `getUserMedia`, and Chrome's browser AEC cancels the SYSTEM audio
output at the DEVICE level regardless of the separate 24kHz playback context. So
basic AEC very likely already works; merging a 16kHz capture context with a 24kHz
playback context is a real regression risk against reconnect stability
(bd z9bc/qt7w). Per the repo's verify-before-building rule, a true AEC-coupling fix
needs a LIVE echo-leak measurement, which cannot be done headlessly.

Shipped the confident, low-risk part: the `getUserMedia` audio constraints were
duplicated across 4 call sites with drift (some omitted `channelCount`).
Centralized them into one canonical `frontend/src/shared/audioConstraints.ts`
(`MIC_AUDIO_CONSTRAINTS`) and wired the 3 PRODUCTION sites (`audioManager.ts`,
`schema-forms/SchemaForm.tsx`, `demo/useDemoVAD.ts`) to it. Deliberately used ONLY
standard spec'd constraints -- REJECTED the legacy Chrome `goog*` echo hints
(removed/ignored in modern Chrome, risk `OverconstrainedError` = a capture
regression for a speculative gain). Left the dev-only `VADTuningDashboard.tsx`
untouched (not a user path). `tsc` clean; audio FE tests green.

**Deferred (filed, not shipped blind):** stronger client AEC (graph coupling or
software echo suppression) is tracked on **polyglot-pdf-oin7**, gated on a live
echo-leak measurement, linked `related` to gnmo.

**Assess.** Exit-criteria scorecard (both beads) scored PASS; gnmo's rubric was
reconstructed retrospectively because its shipped scope differs from the original
graph-coupling premise. Fresh-eyes loop: Sonnet round 1 found 1 nit (the
`audioConstraints.ts` docstring overclaimed "all four call sites consume the
constant" when the dev-only `VADTuningDashboard.tsx` keeps its inline copy) --
fixed inline. Opus clearing round returned NO-GAPS on the rubric and surfaced 2
minor non-blocking latent findings, both ADOPTED: (1) gap-fill is now gated on
native-VAD mode (`not DISABLE_GEMINI_VAD`) so it can never inject un-bracketed
silence between manual/PTT turns -- a keepalive is only meaningful for native VAD's
continuous stream; new test `test_gapfill_off_in_manual_vad_mode`; (2) the send
blob mime-type is now derived from `AUDIO_IN_RATE` (`f"audio/pcm;rate={_in_rate}"`)
instead of a hardcoded `rate=16000`, so a future rate change stays consistent with
the computed silence-frame length.

## Lessons

The pasted third-party analysis (Gemini chat) was authoritative-sounding but its
central claim ("separate AudioContexts defeat AEC") was WRONG for a non-WebRTC Web
Audio app -- browser AEC works at the device level, not per-graph. Reading the
actual audio path (no `RTCPeerConnection`, `echoCancellation: true` already present)
was what caught it. This is the standing verify-before-building scar applied to a
capability CLAIM rather than an SDK type: do not build a risky rewrite on an
unverified external assertion; probe (here, a live echo measurement) first. Filed
the risky part as a measurement-gated follow-up rather than shipping it or dropping
it.

## Doc freshness

`docs/standards/voice-and-vad.md` (the doc most relevant to the VAD/audio path):
reviewed, reported OK by the freshness checker -- left as-is (it describes VAD
turn-taking, not the sender-loop internals or getUserMedia constraints, which this
change did not alter contractually). `docs/components/voice-ai.md`: NOT flagged
stale -- the sender-loop refactor is internal and does not change the documented
adapter contract. The 10 STALE docs the checker listed are all `2026-07-05`-stamped
and were made stale by OTHER commits (2026-07-06/07) NOT on this branch -- left
untouched per the doc-maintenance rule (only bump docs whose tracked files THIS
branch changed); noted here rather than bumped.

## Files touched

- `backend/config.py` -- new `AUDIO_GAPFILL_ENABLED` / `AUDIO_GAPFILL_INTERVAL_MS` knobs.
- `backend/adapters/live_ai_gemini.py` -- audio sender lifted to `_audio_sender_loop` method with gap-fill.
- `backend/tests/unit/test_audio_gapfill.py` -- NEW, 6 gap-fill tests.
- `frontend/src/shared/audioConstraints.ts` -- NEW, canonical `MIC_AUDIO_CONSTRAINTS`.
- `frontend/src/shared/audioManager.ts` -- consume shared constraints.
- `frontend/src/schema-forms/components/SchemaForm.tsx` -- consume shared constraints.
- `frontend/src/demo/useDemoVAD.ts` -- consume shared constraints.
