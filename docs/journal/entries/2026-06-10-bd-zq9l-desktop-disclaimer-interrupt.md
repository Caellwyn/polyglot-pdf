---
date: 2026-06-10
bead: polyglot-pdf-zq9l
title: "Desktop interrupts disclaimer audio on Agree, matching mobile"
tags: [frontend, voice, ux, maintainer-decision]
---

## Trigger

Split from cd0 (item 2). cd0 item 1 shipped in PR #144; this item was deferred
because it needed a PRODUCT decision, not a mechanical fix: mobile's
`handleDisclaimerAgree` interrupts any still-playing disclaimer audio the instant
the user taps Agree (`sendActivityStart` + `flushAudioQueue`), while desktop let
the disclaimer finish playing. The two flows are otherwise identical, and the
activity bracket is balanced (not a bug), so it was a real UX call.

## Decision (maintainer)

**Adopt mobile's interrupt on desktop.** The user has already agreed, so finishing
the legal read aloud adds nothing -- both platforms should cut it off immediately.
Mobile is the reference behavior; desktop is brought in line.

## What shipped

`frontend/src/demo/VoiceOverlay.tsx` `handleDisclaimerAgree`: added the same two
steps mobile runs, right after `setShowDisclaimerModal(false)`:

1. `connectionManager?.sendActivityStart()` -- a no-op in native VAD (suppressed
   in connection.ts, bd 333); in manual VAD it opens the user turn that the
   existing `sendActivityEnd` (later in the same handler) closes, so the bracket
   stays balanced.
2. `flushAudioQueue()` -- the interrupt the user actually perceives (clears the
   buffered disclaimer audio).

The two overlays' `handleDisclaimerAgree` now match. Used a distinct local name
(`agreeAudioManager`) to avoid shadowing the existing `am` declared later in the
same function.

## Verification (browser, dev-local + Chrome MCP, desktop / innerWidth 1220)

Drove onboarding -> i-90 -> disclaimer modal -> clicked "I Agree". The console
showed the new sequence fire in order:
`Sending activity_start to interrupt Gemini` -> `Clearing audio queue on
disclaimer agreement` -> (existing) `switching to first section` -> `Resuming
audio playback` -> `Sending activity_end`. The WS layer showed no `activity_start`
frame -- expected, because native VAD suppresses it; the component-level interrupt
sequence still fired. No new console errors.

(One pre-existing connect-time warning, "SUSPICIOUS: Sending message without
type!" at webFormConnection.ts:1471, is unrelated to this change -- it fires
during connection setup, before Agree -- and was flagged separately.)

## Doc-freshness triage

`docs/standards/voice-and-vad.md` tracks `VoiceOverlay.tsx` and so was flagged.
Checked: it documents the activity-signal MECHANICS (native-vs-manual suppression,
ordering) -- all of which this change USES correctly and does NOT alter. The change
only adds a new *caller* of `sendActivityStart` at the disclaimer-agree site; no
documented behavior changes. The other ~11 flags are mtime-noise from backend
files this branch does not touch. No doc update warranted.

Closes polyglot-pdf-zq9l.
