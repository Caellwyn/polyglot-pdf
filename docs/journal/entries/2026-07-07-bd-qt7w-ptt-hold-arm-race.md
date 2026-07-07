---
date: 2026-07-07
bead: polyglot-pdf-qt7w
title: "Close the fresh-arm PTT-hold mute race in rehydrateAudio (qt7w)"
tags: [voice-ai, voice, frontend, bugfix, review]
---

## Trigger

Follow-up to z9bc (reconnect-audio consolidation). During z9bc's pre-PR
fresh-eyes review, both the fresh-eyes assessor and the two independent Opus
reviewers (Codex was quota-exhausted, so the bd dgoa two-Opus fallback ran)
independently flagged the SAME residual and agreed it was correctly out of scope:
a narrow race in `rehydrateAudio`'s fresh-arm branch. It was filed as qt7w rather
than expanding the z9bc PR.

## The race

`ConnectionManager.rehydrateAudio(reason)` (`frontend/src/shared/connection.ts`)
funnels every reconnect's audio re-arm. On the fresh-arm branch
(`wasRecording === false`) it does `await audioManager.startRecording(...)` -- a
real async span (`getUserMedia` + `audioWorklet.addModule`, tens-hundreds of ms)
-- then applies the PTT resting mute. If the user pressed push-to-talk DURING that
await, `VoiceOverlay.handlePushToTalkPress` had already called
`audioManager.unmuteInput()`, and rehydrateAudio's post-await `muteInput()` then
clobbered it, silently swallowing the press.

Why it was narrow (and not blocking z9bc): the fresh-arm branch only runs when the
mic is NOT already recording at a reconnect's ready-callback. The live-verified
self-healing paths (GoAway, auto-drop, warm restart) keep the mic recording, so
they take the already-recording branch (which never touches mute). Reaching the
fresh-arm branch at a ready-callback needs an unproven timing (e.g. a
resume-from-pause racing a reconnect).

## Fix

Thread PTT-hold state into the ConnectionManager instead of trying to observe the
overlay's component-local `isHoldingPushToTalk`:

- New `ConnectionManager.setPushToTalkHeld(held)` sets a `pushToTalkHeld` closure
  flag. `VoiceOverlay` and `VoiceOverlayMobile` call it `true` on PTT press and
  `false` on release, force-release (safety timeout / connection-lost /
  max-duration), and unmount -- everywhere they already flip mute/unmute.
- `rehydrateAudio`'s fresh-arm mute decision now reads that flag AFTER the arm
  await: `pushToTalkMode && !pushToTalkHeld -> mute, else unmute`. Because it is
  read last, whichever of (press, rehydrate) happens last wins correctly: a press
  during the await leaves the fresh mic unmuted; a press after still wins via its
  own `unmuteInput()`.

This composes with z9bc's already-recording skip (a reconnect that finds the mic
still live never touches mute), so no reconnect path -- fresh-arm or self-healing
-- can re-mute an active hold.

## Verification

A unit test holds `startRecording` open (deferred promise), fires
`setPushToTalkHeld(true)` mid-await, resolves the arm, and asserts the fresh mic
is left UNMUTED (verified: fails without the `!pushToTalkHeld` guard, passes with
it). A companion test asserts the no-press case still applies the resting mute (no
regression). Full frontend suite green (805); tsc clean.

## Scar / for next time

- Component-local React state (an overlay's `isHoldingPushToTalk`) is invisible to
  `connection.ts`. When a shared routine needs to respect a UI gesture, thread the
  intent DOWN into the ConnectionManager (a `set*` method the overlay calls), don't
  try to infer it. Read the threaded state at APPLY time (after any await) so
  last-write-wins resolves the race deterministically.
