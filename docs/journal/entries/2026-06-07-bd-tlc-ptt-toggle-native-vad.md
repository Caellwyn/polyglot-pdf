---
date: 2026-06-07
bead: polyglot-pdf-tlc
title: "PTT Input-Mode toggle now reflects native-VAD mode instead of being a dead control"
tags: [conventions]
---

## Trigger

`polyglot-pdf-tlc` (P1 bug): in the demo, the push-to-talk Input-Mode toggle in
the voice overlay did not respond -- the user could not turn PTT off and could not
tell they were in native Gemini VAD mode. The user wants to A/B native VAD.

## What shipped

**Root cause.** `DISABLE_GEMINI_VAD` defaults to `false`, so the `session_ready`
handshake reports `native_vad: true` -- the demo starts in native-VAD mode by
default. `handlePushToTalkToggle` (and the PTT sync effect) correctly early-return
on `connectionManager.isNativeVad()` (bd polyglot-pdf-333: in native mode Gemini's
VAD drives turns on a continuous, ungated audio stream, so a PTT toggle must NOT
re-arm the worklet noise gate or mute input). But the React state `pushToTalkMode`
still defaulted to `true`, so the UI showed the "PTT" label + the PTT button while
native VAD was actually running, and clicking the toggle silently no-op'd. Net
symptom: a slider that looked active, did nothing, and hid the fact that the user
was already in native VAD.

**Fix (both `VoiceOverlay.tsx` and `VoiceOverlayMobile.tsx`).** Added reactive
`nativeVad` state, synced from `connectionManager.isNativeVad()` in an effect that
runs once connected (the handshake fires `onNativeVadMode` BEFORE flipping status
to `connected`, so the read is reliable). When native VAD is on: force the
displayed mode off PTT (`setPushToTalkMode(false)` -- so the PTT button hides and
the label is truthful), disable the toggle input, label it **"Native"**, and add a
tooltip explaining the mode is backend-controlled. Updated the desktop mode label
to `nativeVad ? 'Native' : (pushToTalkMode ? 'PTT' : 'Auto')`.

**Why disable rather than make the toggle "work".** Native-vs-manual VAD is set by
the backend `DISABLE_GEMINI_VAD` flag at `session_ready` and there is no
client->backend path to change it mid-session (verified: `connection.ts` only ever
sets `nativeVad` from the handshake). So a client toggle genuinely cannot switch
modes live; disabling it with a clear reason is the honest UX, versus a control
that silently ignores clicks.

**Scope decision (defended below).** The bead's goal was "unblock the toggle OR a
way to start in native-VAD mode." Native VAD is now the default AND clearly
surfaced, satisfying the latter. A client-side *live* VAD-mode switcher would
require a new client->backend control message (a new wire contract) -- that is a
step-2 commitment beyond this bug, so it is NOT included here; the existing A/B
path stays "flip `DISABLE_GEMINI_VAD` (env / `dev-local.ps1`) and reconnect"
(voice-and-vad.md). Manual-VAD mode (`native_vad=false`) is unchanged: the toggle
still switches PTT <-> client-VAD ("Auto").

## Lessons

When a control is intentionally inert in some mode (the bd-333 guard), the inertness
must be SURFACED (disabled + relabeled), not silent -- a guard that early-returns
without touching the UI leaves the control lying about state. Generalizes to any
mode-gated UI; captured here and in the voice-and-vad doc rather than a standards
one-liner (it is a UX principle, not a codebase rule).

## Doc freshness

- **Bumped** `docs/standards/voice-and-vad.md` -- rewrote the "PTT button is inert"
  bullet to describe the new disabled-and-labeled behavior + added this entry to
  the stamp.
- **Reviewed and left** the other docs the freshness checker flagged: stale only on
  pre-existing mtimes (backend `config.py` / `callback_handler.py` from earlier
  PRs), none describe the PTT toggle.

## Verification

- Frontend typecheck (`tsc --noEmit`): **0 new errors** -- 24 pre-existing errors,
  identical count with and without this change (confirmed by stashing the edits and
  re-running). The pre-existing errors are schema-forms type drift, out of scope.
- `vitest run`: **115/118 pass**; the 3 failures are the pre-existing DisclaimerModal
  regex-getByText bug (bd polyglot-pdf-pwt), unrelated to this change.
- NOT browser-verifiable: the toggle only renders inside a live WebSocket voice
  session (backend + microphone + Gemini), which the static preview cannot exercise.
- Note: the worktree has no `frontend/node_modules`; the toolchain was run by
  temporarily linking the main repo's install (gitignored, not committed).

## Beads housekeeping

The housekeeping audit again flagged `polyglot-pdf-hrn` (P1 harness epic) as stale
in_progress; unrelated to this bead and owned by another active track -- left as-is
(noted, not transitioned), same call as the prior closeouts.

## Files touched

- `frontend/src/demo/VoiceOverlay.tsx` -- reactive `nativeVad` state + sync effect; disable toggle + "Native" label + tooltip in native mode.
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- same fix for the mobile overlay.
- `docs/standards/voice-and-vad.md` -- "PTT button is inert" bullet rewritten to the disabled-and-labeled behavior; stamp bumped.
