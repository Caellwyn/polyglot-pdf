---
date: 2026-06-08
bead: polyglot-pdf-6vo
title: "PTT becomes a client-side audio gate layered on always-on native VAD"
tags: [conventions]
---

## Trigger

Blocking demo bug reported by the maintainer: the Input-Mode toggle did nothing
when clicked, the PTT / Hold-to-Talk button was missing, and **Gemini did not hear
the user at all** -- both input avenues blocked. Screenshots showed the toggle
rendered (mic icon, "PTT" label) but unresponsive on both desktop and mobile.

## Root cause

The default backend mode is native Gemini VAD (`DISABLE_GEMINI_VAD=false`). Prior
work (bd-tlc / bd-333 / PR #110) made native VAD and PTT **mutually exclusive**:

- The PTT button was hidden in native mode (`pushToTalkMode && isConnected &&
  !nativeVad`), the toggle disabled (`disabled={nativeVad}`), and
  `handlePushToTalkToggle` early-returned on `connectionManager.isNativeVad()`.
- **State desync made the toggle look alive but dead:** the handler keyed on
  `connectionManager.isNativeVad()` -- a `connection.ts` closure var set once from
  the `session_ready` handshake and **never reset** -- while the `disabled`/label
  used the React `nativeVad` state (gated on `status === 'connected'`). When
  disconnected/idle, the React state read `false` (toggle enabled-looking) but the
  handler still early-returned (looks active, does nothing). This is exactly the
  screenshot symptom.
- **audioManager defeated PTT outright:** its native-VAD path streamed ALL audio
  and `return`ed *before* the `inputMuted` check, so even a wired-up PTT mute could
  not gate audio in native mode.

## What shipped (per maintainer direction)

Keep native VAD **always on** at the backend, but layer PTT as a **client-side audio
gate** on top -- useful in noisy rooms so background noise does not trip Gemini's
VAD. The two concerns are now separated: **Gemini owns turn-taking** (when a turn
starts/ends); **PTT owns which client bytes are sent at all**.

- **`audioManager.ts`** -- extracted the routing decision into a pure, exported
  `shouldSendAudioChunk({ nativeVadEnabled, pttModeEnabled, inputMuted, vadActive })`.
  Native mode now streams continuously **unless PTT is on**, in which case it sends
  only while the button is held (`inputMuted=false`). `setPTTMode` keeps the worklet
  RMS noise gate bypassed under native VAD regardless of PTT (`enabled ||
  nativeVadEnabled`), so toggling PTT off does not re-arm the gate and starve
  Gemini's stream.
- **`VoiceOverlay.tsx` + `VoiceOverlayMobile.tsx`** -- removed the `isNativeVad()`
  early-returns in `handlePushToTalkToggle` and the PTT-sync effect; the PTT button
  and toggle are now always available; relabeled to **PTT** (gated) / **Auto**
  (continuous) with no dead "Native"/disabled state.

**What was deliberately KEPT** (so Gemini still owns turn detection): all five
manual-activity-signal suppressions in `connection.ts` (`sendActivityStart/End`,
`onVADSpeechStart/End`) stay guarded on `nativeVad`, and `shouldRunVAD` still keeps
client Silero VAD off in native AND PTT mode. A PTT press still calls
`sendActivityStart`, which is a no-op in native mode -- PTT only decides which bytes
flow, never the turn boundaries.

## Why the #110 hazard does not bite

PR #110 found that *forcing* `pushToTalkMode=false` in native mode would start
Silero, whose `onSpeechStart` flushes playback with no matching resume (the resume
path no-ops on `nativeVad`) -- permanently blocking Gemini's audio. That hazard is
**not** reintroduced here: `shouldRunVAD` still includes `!nativeVad`, so Silero
never runs. And the PTT press/release handlers own their OWN
`flushAudioQueue`/`resumePlayback` pair (press flushes, release resumes), so PTT's
barge-in is self-contained and safe under native VAD.

## Verification

- New `frontend/src/shared/audioGate.test.ts` (5 cases) covers the three-way routing,
  including the core fix: **native + PTT-on + muted -> withhold audio** (the bug was
  that native streamed unconditionally).
- Full frontend suite: **125 pass** + the 3 pre-existing DisclaimerModal failures
  (Chinese-text `getByText`, bd polyglot-pdf-pwt).
- Typecheck unchanged at the **24-error pre-existing baseline** (zero new errors).
- **NOT yet runtime-verified on the live mic + Gemini stack.** This changes the
  audio pipeline's gating, which unit tests cover at the logic level but cannot
  prove end-to-end. A manual smoke test (does Gemini hear continuous audio with PTT
  off; does press-to-talk gate with PTT on; does the toggle flip live) is the gate
  before merge.
- Note: the worktree has no `frontend/node_modules`; the toolchain ran via a
  temporary junction to the main repo's install (not committed).

## Files touched

- `frontend/src/shared/audioManager.ts` -- pure `shouldSendAudioChunk` gate; native mode honors PTT mute; worklet gate bypass keyed on `pttMode || nativeVad`.
- `frontend/src/demo/VoiceOverlay.tsx` -- removed native-VAD PTT early-returns; PTT button + toggle always available; PTT/Auto label.
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- same decoupling for the mobile overlay.
- `frontend/src/shared/audioGate.test.ts` -- NEW: 5 routing-gate tests.
- `docs/standards/voice-and-vad.md` -- rewrote the native-VAD section for the PTT-as-a-gate model; stamp bumped.
