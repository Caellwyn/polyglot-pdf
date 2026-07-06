---
date: 2026-07-06
bead: polyglot-pdf-z9bc
title: "Re-arm audio on the automatic/internal reconnects (GoAway, auto-drop)"
tags: [hotfix, voice-ai]
---

## Trigger

"No voice audio after a reconnect." The bead was originally scoped to a manual
reconnect on a non-first section and hypothesized 6job (the section-switch race
fix) had resolved it. Recon this session (verified against the code) showed the
hypothesis was WRONG for the paths that matter: audio re-arm coverage splits by
reconnect CAUSE, and the automatic ones were uncovered.

Audio (mic capture + the playback AudioContext that plays the AI's voice) is armed
only by `audioManager.startRecording` (which also reuses+resumes the playback
context). `ConnectionManager.connect()` never calls it -- each reconnect path
relies on its caller. Coverage before this fix:
- user-initiated (manual reconnect button), `pause->resume`, and
  `startSection`/`switchToSection` -> re-armed by their own callers. WORKED.
- GoAway pre-emptive resume (`handleGoAwayReconnect`, bd l3a.2) and auto-reconnect
  on a dropped socket (`attemptReconnect`) -> reconnect INTERNALLY in
  `webFormConnection.ts` by opening a FRESH socket, so they surface via the
  `onSessionReady` callback, which did NOT re-arm. BROKEN: the AI stayed silent and
  the mic dead after those reconnects, even though the WS + Gemini session had
  resumed. (`onSessionRestarted` is a SEPARATE, user-triggered path -- the warm
  `restart_gemini_session` over the same socket when only Gemini closed; the fix
  arms it too, but no automatic reconnect currently reaches it.)

That is why the section-switch-focused bead looked "maybe fixed by 6job" (the
section-switch path was always a WORKING path) while the reconnect-heavy future
(GoAway l3a.2 + the continuous-session cutover x8rt) would silently break.

## What shipped

A shared `reArmAudio(reason)` helper in `connection.ts`, called from BOTH
session-ready callbacks (`onSessionReady`, `onSessionRestarted`), so EVERY
reconnect cause re-arms audio -- not just the user-initiated ones. It:
- no-ops under the test harness (audio is injected, no mic);
- no-ops when `audioManager.isRecording()` is already true (so the manual /
  section-switch paths that armed just before the ready event never double-arm --
  and `audioManager.startRecording`'s own `if (recording) return` is a second
  guard);
- calls `audioManager.startRecording` (which re-arms mic AND reuses+resumes the
  playback AudioContext -- the part that actually restores the AI's voice);
- re-applies the stored PTT/mute state after arming.

`rearmAudioCapture` (the overlay-remount entry, bd nlfc) was refactored to
delegate to the same helper -- one source of truth for the guard + PTT re-sync.

Verification: 4 new tests in `connection.test.ts` drive the captured
`onSessionReady`/`onSessionRestarted` callbacks and assert re-arm fires, is
idempotent (no double-arm when already recording), and re-applies PTT/mute.
Full frontend suite 767 passed; tsc clean. The pre-existing
`VoiceOverlayResizeFlip` remount test (which exercises the refactored
`rearmAudioCapture`) still passes.

Fresh-eyes round 1 caught a REAL race the first cut introduced: on initial connect,
`onSessionReady` now calls `reArmAudio` -> `startRecording` while the overlay's
status-poll independently calls `startRecording` too; the old `if (recording)
return` guard doesn't stop a SECOND call that arrives while the first is still
awaiting getUserMedia/worklet setup (recording is set true only at the end). Fixed
at the source in `audioManager.startRecording` with an IN-FLIGHT `arming` promise
guard: a concurrent call awaits the in-flight setup instead of starting a duplicate
getUserMedia. Pinned by `audioManager.startRecording.race.test.ts` (two concurrent
starts -> getUserMedia called ONCE).

Known-residual (accepted, low-risk):
- `reArmAudio`'s `isRecording()` guard reflects MIC state, not the playback
  AudioContext's suspend state; if a reconnect leaves the mic worklet alive but the
  browser suspended the playback context, reArmAudio skips the resume. Mitigated:
  `playAudio` independently resumes a suspended playback context on every incoming
  chunk, so the AI's voice self-heals on its first post-reconnect utterance.
- `isRecording()` tracks the JS flag, not the underlying MediaStreamTrack liveness
  (no `track.onended` listener -- pre-existing). If the OS kills the track mid-outage
  the flag can read stale-true; not introduced here, but this fix leans on the flag
  over a longer window. Left as-is (out of scope; would want a track-liveness signal).

NOT done here (residual manual verification): a true live GoAway test needs a real
microphone + either the ~9-10 min Vertex session cap or a forced GoAway on the
demo -- the scripted voice-harness cannot exercise this path because `reArmAudio`
is (correctly) gated off under the test harness. Recommend a live demo test-drive
(force a reconnect, confirm the AI's voice plays) as the final confirmation of
exit criterion 2.

## Lessons

Re-arm-on-reconnect logic must live in a reconnect-cause-AGNOSTIC place (the shared
session-ready callback), not in the individual reconnect callers -- otherwise a new
reconnect path (GoAway, continuous-session) silently misses it. The tell: audio
worked on the reconnects a human triggers and broke on the ones the system
triggers automatically.

## Doc freshness

`docs/standards/voice-and-vad.md` tracks `connection.ts` and already described the
mic-arming sites; added a "Reconnect audio re-arm" subsection (the cause-split +
the idempotent shared helper), extended the mic-arming-sites list, and bumped the
stamp.

## Files touched

- `frontend/src/shared/connection.ts` -- shared `reArmAudio` helper; called from
  `onSessionReady` + `onSessionRestarted`; `rearmAudioCapture` delegates to it.
- `frontend/src/shared/audioManager.ts` -- in-flight `arming` guard in
  `startRecording` so a concurrent call awaits the in-flight setup (fresh-eyes r1).
- `frontend/src/shared/connection.test.ts` -- audioManager mock gains
  setPTTMode/muteInput/unmuteInput; 4 reconnect-audio-re-arm tests.
- `frontend/src/shared/audioManager.startRecording.race.test.ts` -- pins the
  concurrent-arming guard (getUserMedia called once).
- `docs/standards/voice-and-vad.md` -- reconnect audio re-arm subsection + stamp.
- `docs/journal/entries/2026-07-06-bd-z9bc-reconnect-audio-rearm.md` -- this entry.
