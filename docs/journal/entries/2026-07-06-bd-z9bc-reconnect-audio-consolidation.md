---
date: 2026-07-06
bead: polyglot-pdf-z9bc
title: "Reconnect-path audio: proved self-healing, consolidated onto one rehydrate routine (z9bc)"
tags: [voice-ai, voice, refactor, frontend, webFormConnection, review]
---

## Trigger

z9bc was reframed (maintainer, 2026-07-06) from a one-line audio re-arm patch
into a "consolidation + correctness" bead: reconnect smoothness is a prerequisite
for the continuous-session paradigm (x8rt), where the hardwired Gemini Live
max-session cap (~9-10 min on Vertex) makes GoAway-driven reconnects the primary
mid-form event. A prior session's fix (draft PR #339) was parked as WRONG: it
added a `reArmAudio()` guarded by `audioManager.isRecording()`, but on the
automatic reconnect paths it targets (GoAway `handleGoAwayReconnect`, auto-drop
`attemptReconnect`) nothing resets the `recording` flag, so the guard
short-circuited and the re-arm never ran on its own target paths. The bead
required a LIVE repro (real mic; the scripted harness gates the audio path off)
to settle EMPIRICALLY what actually breaks before any fix.

## What we found (live repro)

Ran a Vertex backend (`VERTEXAI=true`, `polyglot-demo-aa709`) + the real SPA in
Chrome with the test-harness flag cleared, so the real audio path ran. Probed the
WebSocket (outbound mic frames / inbound AI-audio frames) and the `AudioContext`
(playback-buffer starts) BELOW the app closures, drove the I-90 form to a live
connected session, then forced each target path and measured continuity across
the socket swap:

- **Auto-drop** (`socket.close(4999)` -> `handleClose` -> `attemptReconnect`): new
  socket opened; mic kept sending (+1571 chunks after the drop); AI audio resumed
  (+23 inbound frames, +23 playback starts).
- **GoAway** (injected `{type:"go_away"}` -> `handleGoAwayReconnect`, the exact
  client code path): signature `OPEN-req -> close 1005 -> open`; mic kept sending
  (+1714); AI audio continued playing across the swap (+24 inbound, +24 playback
  starts, captured mid-greeting). Multiple further cycles self-healed the mic
  every time; UI stayed connected with exactly ONE open socket (no leak).

**Conclusion: z9bc does NOT reproduce -- audio self-heals on both paths.** On
GoAway/auto-drop nothing calls `stopRecording()`/`destroy()`, so the mic worklet +
recording `AudioContext` + playback `AudioContext` all survive the socket swap.
`sendMicChunkToBackend` -> `connection.sendAudio()` reads the LIVE `this.ws`, and
`playAudio` resumes the context per-chunk, so both directions re-route to the new
socket with no re-arm. This is exactly why #339's `isRecording()`-guarded re-arm
would have (correctly) no-op'd -- no re-arm was ever needed.

## What shipped

The maintainer chose (2026-07-06) to still do the consolidation as proactive
x8rt cleanup, treating it as behavior-neutral since audio already works:

1. **In-flight arming guard** (salvaged from #339, the one correct part):
   `audioManager.startRecording` now holds an `arming` promise so two concurrent
   callers on the same tick await one setup instead of racing two `getUserMedia`
   calls that clobber `nodes.source`/`workletNode`. A plain `if (recording)
   return` cannot catch this because `recording` is set true only at the END of
   the await chain. Pinned by `audioManager.startRecording.race.test.ts` (verified
   to fail without the guard, pass with it).

2. **One shared rehydration routine**: `ConnectionManager.rehydrateAudio(reason)`
   centralizes the "arm mic + re-sync PTT" logic that was duplicated across
   `resume`, `startSection`, `switchToSection`, and `rearmAudioCapture`, and wires
   it into `onSessionReady` + `onSessionRestarted` -- the callbacks the automatic
   reconnects (GoAway, auto-drop, warm restart) surface through and which re-armed
   nothing before. It is idempotent: no-op under the harness and while paused,
   skips the arm when already recording (backed by the arming guard), always
   re-applies PTT/mute. Deliberately NOT the `isRecording()`-guarded
   skip-the-whole-arm that made #339 wrong: the whole routine runs on every ready
   event; it just does not duplicate `getUserMedia`.

Verified live post-refactor: a GoAway mid-greeting logs `rehydrateAudio: arming
mic (onSessionReady)`, mic keeps streaming, UI stays connected; a second GoAway
with the mic already live is the idempotent no-op path. 4 new `connection.test.ts`
cases pin arm / no-op-when-recording / warm-restart / paused-skip. Full suite
green (929 backend+frontend); tsc clean.

## Doc-freshness note

`docs/standards/voice-and-vad.md` had a now-stale enumeration of mic-arming sites
(updated to describe the single `rehydrateAudio` funnel). `docs/components/voice-ai.md`
was flagged stale by mtime only (it Tracks `connection.ts`/`audioManager.ts`) but
has no content the consolidation invalidates -- its GoAway description still holds;
reviewed, no change needed.

## Scar / for next time

- **"Mic dead after reconnect" is not automatically a re-arm bug.** The worklet
  and both AudioContexts survive a socket swap; only `stopRecording()`/`destroy()`
  tears them down, and those fire only on section-switch / pause / disconnect. A
  reconnect that merely swaps `this.ws` self-heals because the send/play callbacks
  read live state. Verify against a LIVE repro before adding a re-arm.
- **The harness cannot exercise this** (`isTestHarnessEnabled()` gates the mic
  path off); the real vs mock `isRecording()` state was the whole question. Clear
  `__VFF_TEST_HARNESS` in localStorage + run a Vertex backend to get the real path.
