---
date: 2026-06-10
bead: polyglot-pdf-ovi6
title: "First VoiceOverlay component test: disclaimer-agree interrupt ordering"
tags: [frontend, testing, voice]
---

## Trigger

Codex's round-1 finding on PR #146 (zq9l) asked for automated coverage of the
desktop disclaimer-agree interrupt, so CI catches a future regression of the
ordering. It was deferred from #146 (the first VoiceOverlay component test needs a
non-trivial mock surface, well beyond zq9l's one-line change) and tracked here.
The maintainer directed picking it up after #146 merged.

## What shipped

`frontend/src/demo/VoiceOverlay.disclaimer.test.tsx` -- the FIRST
@testing-library/react component test for VoiceOverlay, parametrized over BOTH
VoiceOverlay and VoiceOverlayMobile (they share the sequence after zq9l).

It renders the real component, forces the disclaimer modal open
(`initialLanguage="English"` + a mocked `SchemaFormStateManager.load` returning
`disclaimerAccepted:false`), clicks the real "I Agree" button (which invokes the
real `handleDisclaimerAgree` via `onAgree`), and asserts the call ORDER: the
interrupt (`sendActivityStart` -> `flushAudioQueue`) must fire BEFORE the
turn-completion / section switch (`resumePlayback` -> `sendActivityEnd` ->
`switchToFirstSection`).

Mock surface (browser-heavy / infra deps only -- the real handler runs):
`useDemoVAD` (getUserMedia/WASM), `getBackendHttpUrl` + global `fetch` (the
acceptance POST), `createConnectionManager` (we inject our own recording mock as
the `connectionManager` prop), and `sessionStorage`. A full
ConnectionManager/AudioManager mock records call order into a shared array.

The reconnect branch is skipped (`getStatus()` returns `'connected'`) and is
scoped to bd polyglot-pdf-ala0 (the pre-existing unmatched-activity_end hazard on
that path).

## Verification

- 2 tests pass (desktop + mobile); full frontend suite 204 pass (14 files); the
  module-scoped `vi.mock`s do not leak.
- **Proven meaningful**, not just green: temporarily removing the source
  `sendActivityStart` made the desktop test FAIL; restoring it passed.
- ASCII-clean (.tsx, scar #6).

## Review

Reviewed by a fresh-eyes model (Codex is out of quota, per the maintainer).
0 blockers; all 4 of its NIT improvements adopted, strengthening the test:
1. assert `resumePlayback` ordering (it was tracked but unchecked);
2. an empty-`calls` canary before the click (guards `indexOf`-first-occurrence
   against a spurious mount-time call);
3. `switchToFirstSection.toHaveBeenCalledWith('English')` (catches a language-arg
   regression, not just "was called");
4. `mockImplementation` returning a FRESH state object per call instead of
   `mockReturnValue` (the handler mutates the loaded state).

## Doc-freshness triage

Flagged ~11 docs STALE; all false positives. This branch adds ONLY a test file,
which no tier-1/2 doc tracks. The one flag naming a frontend file
(`voice-and-vad.md` -> `VoiceOverlay.tsx`) traces to PR #146's already-merged
change, not this branch. The beads audit's `hrn` staleness is the long-running
active P1 epic from other sessions (documented recurring false-positive); not
owned here. No doc update warranted.

Closes polyglot-pdf-ovi6.
