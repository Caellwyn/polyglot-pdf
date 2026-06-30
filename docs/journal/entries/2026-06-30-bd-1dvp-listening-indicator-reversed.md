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
`isConnected`:

- An **ear glyph (U+1F442)** paired with the existing live mic-energy meter,
  wrapped in one `.vff-listening` element. Shown only while connected (i.e.
  actually listening), hidden when paused/disconnected -- the reverse of the old
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

The indicator is gated on a dedicated `isListening` flag (the send-capable states
`connected` / `switching_section`, matching `shouldSendMicChunk`), NOT the broader
`isConnected` -- so it stays hidden while `reconnecting`, where `isConnected` is
still true but the mic gate drops all audio (Codex finding, PR #278).

Verified live via Chrome MCP against the local stack (Form I-90, English):
connected -> indicator present (ear + meter nested inside); paused -> indicator
hidden; old badge absent in every state. TypeScript clean; 12/12 demo overlay
tests pass.

Fresh-eyes assess (Sonnet, 2 rounds -> NO-GAPS): round 1 found one dead-CSS gap
(a `.vff-mic-meter--sending` rule left in the mobile overlay), fixed before the
PR. Two genuinely out-of-scope, pre-existing bugs were filed as separate beads:
`polyglot-pdf-8v53` (the mobile FAB speech-dot has the same reversed gate) and
`polyglot-pdf-bxng` (mobile `isConnected` is narrower than desktop, excluding
`switching_section`/`reconnecting`). Codex outer review (PR #278) then flagged the
`reconnecting` gap fixed above, the two journal-accuracy corrections in this entry,
and a test-coverage gap (a focused render test for the new `isListening` gate was
added).

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
  "Listening" badge with the `vff-listening` ear+meter indicator gated on
  `isConnected`; removed the dead vad-indicator CSS + `vff-vad-pulse` keyframe;
  re-pointed the `--sending` green-bar rule to `.vff-listening--sending`.
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- same ear+meter indicator in the
  expanded panel's status row; added `.vff-listening` CSS (kept the
  `vff-vad-pulse` keyframe, still used by the FAB speech-dot).
