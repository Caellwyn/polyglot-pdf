---
date: 2026-06-30
bead: polyglot-pdf-1dvp
title: "Fix reversed 'listening' indicator in voice overlay (shows when paused, not when listening)"
tags: [hotfix, refactor]
---

## Trigger

Maintainer-reported bug: the voice overlay's "listening" cue was reversed --
it did NOT show while the app was actually listening, but DID light up when
the session was paused or disconnected. Screenshots confirmed it was the green
"Listening" pill on the desktop overlay's status row.

## What shipped

Root cause: the green "Listening" badge (`vff-vad-indicator`) was gated on
`vad.userSpeaking && !pushToTalkMode && !nativeVad` -- a leftover from the
client-side Silero-VAD turn-taking path. The app's deployed config runs in
NATIVE VAD mode (Gemini detects turns server-side; see
[voice-and-vad.md](../../standards/voice-and-vad.md)), so the `!nativeVad`
clause gated the badge OFF entirely in the dominant mode, and `vad.userSpeaking`
was an unreliable proxy that could read true across a pause/disconnect. The net
effect matched the report: lit at the wrong times, dark when actually listening.

The fix replaces that badge with a single, language-neutral indicator gated on
a dedicated `isListening` flag = a steady `connected` session ONLY. The broader
`isConnected` (which keeps the status dot lit through `reconnecting`) is NOT
used, and the transient turn-taking states are deliberately excluded:
`reconnecting` drops all mic audio, and `switching_section` can precede the
socket reopening on the reconnecting `startSection()` path -- in both windows a
"listening" cue would be misleading. Keeping the gate a pure function of
`status` (no per-render socket probe) also lets the mic-energy-meter effect
share the exact same visibility condition. See the Codex-rounds note below.

- An **ear glyph (U+1F442, written as an ASCII-safe `'\u{1F442}'` escape so the
  .tsx source stays ASCII per AGENTS.md)** paired with the existing live
  mic-energy meter, wrapped in one `.vff-listening` element. Shown only while
  connected, hidden when paused/disconnected/reconnecting/switching -- the
  reverse of the old
  behavior.
- **Combined the two cues** so the previously-standalone mic-energy bar now
  carries meaning: grey bar = mic alive but audio gated (PTT-muted / silence),
  green (`--sending`) = audio actually reaching the backend.
- **Language-neutral by design:** the ear glyph replaces the English word
  "Listening" so the cue reads the same across all 18 spoken languages the app
  supports (the same rationale as the existing thinking-indicator dots).

Applied to BOTH overlays: `VoiceOverlay.tsx` (desktop) and
`VoiceOverlayMobile.tsx` (mobile expanded panel). The dead
`.vff-vad-indicator` / `.vff-vad-label` / `.vff-vad-light` CSS and its
`@keyframes vff-vad-pulse` were removed from the desktop overlay; the mobile
`vff-vad-pulse` keyframe was kept because it still drives the FAB speech-dot
(`.vff-fab-vad-dot`). That FAB speech-dot was left unchanged here because it is a
SEPARATE element outside this bead's status-row scope -- but note it carries the
SAME reversed/dead gate (`vad.userSpeaking && !pushToTalkMode && !nativeVad`) that
this bead fixed in the status row, so in native-VAD mode it is permanently dark.
That is filed as out-of-scope follow-up bead `polyglot-pdf-8v53`, not "correctly
gated."

The indicator is gated on a dedicated `isListening` flag = a steady `connected`
session ONLY, NOT the broader `isConnected` (which stays true through
`reconnecting` for the status dot) and NOT the transient `switching_section` /
`reconnecting` windows where the mic send gate can drop audio.

Verified live via Chrome MCP against the local stack (Form I-90, English):
connected -> indicator present (ear + meter nested inside); paused -> indicator
hidden; old badge absent in every state. TypeScript clean; demo overlay tests
pass (21/21 incl. the new gate test).

Fresh-eyes assess (Sonnet, 2 rounds -> NO-GAPS): round 1 found one dead-CSS gap
(a `.vff-mic-meter--sending` rule left in the mobile overlay), fixed before the
PR. Two genuinely out-of-scope, pre-existing bugs were filed as separate beads:
`polyglot-pdf-8v53` (the mobile FAB speech-dot has the same reversed gate) and
`polyglot-pdf-bxng` (mobile `isConnected` is narrower than desktop). Codex outer
review (PR #278) ran three rounds and drove the gate to its final shape: it
flagged the `reconnecting` leak (round 1), then -- once `switching_section` was
briefly included -- a nested-meter freeze and a no-socket switch window (rounds
2-3), which is why the final gate is `connected*`-only. Codex also caught the
raw-emoji ASCII violation (fixed via a `'\u{1F442}'` escape), two journal
inaccuracies (corrected here), a leftover 5s connect-timer in the render tests
(fixed with fake timers), and a narrow-phone layout overflow of the mobile badge
(fixed by letting the status cell + badge shrink/truncate).

## Lessons

A render gate that hard-codes a now-non-default mode (`!nativeVad`) silently
becomes dead-or-inverted code once the default flips. The old badge keyed on a
turn-taking signal (`vad.userSpeaking`) that only exists in the manual-VAD path;
in native VAD the right "are we listening?" signal is simply the connection
state plus the send gate (`isConnected` + `micSending`), which the mic-energy
meter already read. Prefer gating user-facing status on connection/send state
over an internal VAD-path flag. (Did not rise to a standards/ one-liner -- it is
specific to the overlay indicators, not a cross-cutting rule.)

## Doc freshness

`docs/standards/voice-and-vad.md` was flagged STALE by the freshness checker
because it `Tracks:` `frontend/src/demo/VoiceOverlay.tsx`, which this branch
touched. **Reviewed and left as-is:** this change is purely a visual indicator
(ear glyph + meter rendering) and alters no VAD path, turn signal, or send gate.
The doc already notes "the mic-energy meter (bd s3zv) reads the send gate, it
does not alter it," which remains accurate. Bumping it would imply a behavioral
change that did not occur.

All other STALE docs flagged by prep (ai-models, terminology, stateless-
architecture, etc.) track BACKEND files this branch did not touch -- they were
already stale before this sprint and are out of scope here.

## Files touched

- `frontend/src/demo/VoiceOverlay.tsx` -- replaced the reversed `vff-vad-indicator`
  "Listening" badge with the `vff-listening` ear+meter indicator (ear via a
  `'\u{1F442}'` ASCII escape) gated on a new `isListening` flag (`connected*`
  only, not `isConnected`); removed the dead vad-indicator CSS + `vff-vad-pulse`
  keyframe; re-pointed the `--sending` green-bar rule to `.vff-listening--sending`;
  narrowed the desktop energy-meter effect's `meterVisible` to `connected*` so its
  rAF loop matches the badge's visibility (no per-frame work while
  reconnecting/switching).
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- same ear+meter indicator in the
  expanded panel's status row, gated on the same `connected*`-only `isListening`;
  added `.vff-listening` CSS (kept the `vff-vad-pulse` keyframe, still used by the
  FAB speech-dot); kept the meter subscription's `meterVisible` at `connected*` to
  match; made the status cell + badge + meter shrink/truncate so the badge cannot
  overflow the 2-column status cell into the adjacent controls on narrow phones.
- `frontend/src/demo/VoiceOverlayListeningIndicator.test.tsx` -- new render test
  pinning the gate (connected -> shown; switching_section / paused / disconnected
  / reconnecting -> hidden) for both overlays; uses fake timers so the overlay's
  connect-poll loop cannot leak past the assertions.
