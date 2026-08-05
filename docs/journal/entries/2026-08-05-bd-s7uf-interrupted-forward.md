---
date: 2026-08-05
bead: polyglot-pdf-s7uf
title: "Forward Gemini interrupted to the client + drain stale playback (0rpu Stage 2)"
sprint: 18
tags: [voice, audio, websocket, bugfix]
---

## Trigger

The bd 0rpu desync attribution (six STT-scored harness runs, 2026-08-05)
established two facts about barge-in. First, the backend received Gemini's
`interrupted` event and used it only for logging/counters -- the client was
never told, so its session-lifetime playback cursor kept playing the dead
generation's already-received tail. This is why barge-in "did not work" on
auto-VAD from the user's standpoint: the model genuinely stopped, but the
speakers did not. Second, the interruption moment is exactly when the model's
NEWLY generated audio is most likely corrupted (every real audio/text
divergence in ~150 scored generations sat on a mid-generation interruption),
so the stale tail compounds the riskiest moment in the conversation.

## What shipped

The `interrupted` event now travels the same detect-and-forward chain as
`go_away`: adapter `_on_interrupted` callback (fired in the interrupted block
before counter resets, error-swallowed) -> `callback_handler.on_interrupted`
-> WS `{"type": "interrupted"}` (documented in ws-protocol.md; the contract
test caught the initially missing row) -> `webFormConnection` clears the
STAGING audioQueue and invokes `onInterrupted` -> `connection.ts` calls the
new `audioManager.resetPlaybackClock()`.

`resetPlaybackClock` is the old `flushAudioQueue` body minus
`playbackBlocked = true`: it stops scheduled sources and resets the playback
clock but never sets the block flag, so the model's next generation plays
normally -- structurally immune to the nm7z unpaired-block trap.
`flushAudioQueue` (pause/section-switch, always paired with `resumePlayback`)
sets the block and delegates the drain. Two client audio holds exist (staging
queue + scheduled sources); both are cleared.

Deliberately NOT flushed at `form_updated` (read-back audio does not exist yet
at that moment) or `turn_complete` (transcript-gated, races the playback tail).

## Verification

- 6 backend tests (adapter fires once / None-safe / callback-error swallowed;
  handler forwards / swallows send failure / no-websocket noop) + 6 vitest
  (dispatch clears queue + fires callback + no idle-timeout flag;
  resetPlaybackClock does NOT block the next chunk + resets the clock;
  flushAudioQueue still blocks until resumePlayback). Four mutations applied,
  each reddened exactly its guard, all restored to green.
- Full suites: backend 1600 passed (+ contract 89 after the ws-protocol row),
  frontend 1265/1265.
- Live E2E (the 0rpu RUDE barge-in harness arm on the patched stack): PASS
  15/15 fields; 27 interrupts fired, 27 forwarded, 0 send failures. Measured
  drain: playback backlog at field updates fell from mean 1.10s (6/15 over 1s,
  pre-fix run) to 0.27s (1/15) under identical barge-in pressure.

## Notes

The measurement instrumentation (WAV dump, backlog probe, W-7 sequence
driver with pacing arms) lives on the bd 0rpu experiment branch
(claude/voice-dev-knobs-0rpu, PR #543, held); this fix was E2E-verified there
via a local cherry-pick. The interrupt-triggered text re-anchor (the
generation-side half of the fix ladder) is a separate upcoming bead.
