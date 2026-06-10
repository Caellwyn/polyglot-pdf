---
date: 2026-06-10
bead: polyglot-pdf-ala0
title: "Skip activity_end on the disclaimer-agree reconnect path"
tags: [frontend, voice, bug, testing]
---

## Trigger

Fresh-eyes flagged this pre-existing hazard on PR #146 (zq9l). It was filed (not
fixed inline, out of scope for zq9l) and the maintainer delegated the technical
call to me.

## The bug

`handleDisclaimerAgree` (both VoiceOverlay.tsx and VoiceOverlayMobile.tsx, identical
structure) sends `sendActivityStart()` near the top to interrupt the disclaimer
audio. If the connection went stale during the long disclaimer read, it reconnects
via `handleConnect()` -- a BRAND-NEW connection that never received that
`activity_start`. It then unconditionally sent `sendActivityEnd()` on the new
connection: an unmatched signal. In native VAD the backend converts `activity_end`
into `audio_stream_end`, so this lands as a spurious stream-end on a turn that
never opened.

## The fix (option b: skip activity_end on reconnect)

Added a `reconnected` flag set true when the stale-connection branch calls
`handleConnect()`, and guarded the Step-4 `sendActivityEnd()` with
`if (!reconnected)`. Mirrored in both overlays.

`resumePlayback` and `switchToFirstSection` still run on both paths; the common
(non-reconnect) path is unchanged.

**Why (b) and not (a) re-send-activity_start-after-reconnect:** on reconnect we are
about to call `switchToFirstSection` -> `startSection`, which RESTARTS the Gemini
session (closes the current one, starts fresh, sends the initiating message). A
turn-close on a session that is about to be torn down and replaced is meaningless,
so *not sending it* is the cleaner model than re-opening a turn just to close it.

## Tests

Extended VoiceOverlay.disclaimer.test.tsx (the ovi6 harness) with 2 reconnect
cases (desktop + mobile). The component auto-connects on mount, so the mock
exposes a `__forceStale()` hook called AFTER mount but BEFORE the Agree click to
model a connection that dropped during the disclaimer read. The tests assert
`connect()` ran (reconnect happened), `switchToFirstSection` ran, and
`sendActivityEnd` was NOT called.

Proven meaningful: `git stash` of just the two source files makes BOTH reconnect
tests fail (the unguarded `sendActivityEnd` fires), while the 2 happy-path ordering
tests still pass.

## Verification

- 4 tests in VoiceOverlay.disclaimer.test.tsx pass (2 ordering + 2 reconnect);
  full frontend suite 254 pass.
- The reconnect test console confirms the branch is exercised ("Connection stale
  ... reconnecting" -> "Reconnected" -> "switching to first section", with NO
  "Sending activity_end").
- My added lines are ASCII (the overlays' other non-ASCII is pre-existing emoji
  in console.log, untouched).
- Browser repro judged unnecessary: forcing a mid-disclaimer-read disconnect in a
  real browser is flaky and adds nothing over the deterministic test that
  exercises the exact branch.

## Review

Codex is out of quota (per the maintainer), so this PR is reviewed by a fresh-eyes
model instead of the Codex watcher.

## Doc-freshness triage

`voice-and-vad.md` was flagged (it tracks VoiceOverlay.tsx). Checked: it documents
the activity-signal MECHANICS (native-vs-manual suppression, ordering) -- which this
fix USES but does not change; it adds a conditional skip of one `activity_end`
call, no change to the documented signal semantics, and does not mention the
disclaimer-agree / reconnect flow at all. Other flags are mtime-noise from untouched
backend files. The beads `hrn` staleness is the long-running active P1 epic
(documented recurring false-positive). No doc update warranted.

Closes polyglot-pdf-ala0.
