---
date: 2026-06-04
bead: polyglot-pdf-333
title: "Native Gemini VAD smoke-test toggle (bypass custom VAD end to end)"
tags: [conventions, performance, testing]
---

## Trigger

`bd polyglot-pdf-333` (maintainer goal): for a round of smoke testing, bypass the
custom client-side (Silero) VAD + manual activity signals and let **Gemini's own
built-in automatic VAD** drive turn detection -- to evaluate whether the native
VAD has improved. Must stay fully functional in native mode and keep a **clean
single toggle** to revert. Maintainer decision: default native VAD **ON** for the
next demo deploy.

## What shipped

A single backend flag (`DISABLE_GEMINI_VAD`, now env-overridable, **default
`False` = native mode**) propagated to the frontend so BOTH ends switch together.
Every change is gated on the flag; the manual-VAD code paths are unchanged, so
revert is one flag flip.

**Backend:**
- `config.py`: `DISABLE_GEMINI_VAD = os.getenv("DISABLE_GEMINI_VAD","false")...`
  (default native; env-overridable for demo/prod + revert). The existing
  `VAD_*` sensitivity knobs (LOW/LOW/500/500) now ship to Gemini's detector.
- `websocket_routes.py`: `session_ready` carries `native_vad = not DISABLE_GEMINI_VAD`.
- `live_ai_gemini.py`: `send_activity_start/end` no-op when native VAD is on
  (belt-and-suspenders against the conflicting turn-taking state the
  `_build_vad_settings` docstring warns about). `_build_vad_settings` needed no
  change (it already handles the enabled branch + the 1007 either/or).

**Frontend (propagation via a new `onNativeVadMode` callback):**
- `webFormConnection.ts`: `ConnectionCallbacks.onNativeVadMode`; `handleSessionReady`
  reads `native_vad` and fires it before `onSessionReady`.
- `connection.ts`: a `nativeVad` closure flag (set from `onNativeVadMode`, which
  also calls `audioManager.setNativeVad`); `nativeVad` early-returns in the
  `sendActivityStart/End` wrappers (PTT path) and `onVADSpeechStart/End` (Silero
  path) -- all five manual-signal sites suppressed. New `isNativeVad()` getter.
- `audioManager.ts`: `setNativeVad(enabled)` + a worklet `onmessage` short-circuit
  that streams ALL audio ungated (bypassing the `inputMuted/vadActive` gate AND
  the all-zero silence skip). Crucially it ALSO bypasses the **audio worklet's RMS
  noise gate** by reusing the `setPTTMode` worklet message -- without this the
  worklet would zero sub-threshold audio before JS sees it, starving Gemini's VAD
  of silence. The bypass is re-applied on worklet (re)creation so a reconnect can't
  re-arm the gate.
- `VoiceOverlay.tsx` / `VoiceOverlayMobile.tsx`: the PTT effect/handler
  early-returns on `isNativeVad()` so a PTT toggle can't re-arm the noise gate or
  mute the (now continuous) stream.

**The worklet noise gate was the non-obvious linchpin** (caught by the Plan
agent, verified at `audio-processor.worklet.ts:131-143`): it zeros sub-threshold
audio whenever `pttMode` is false, so bypassing only the JS-side gate would still
have starved Gemini's VAD of the silence stream. The fix reuses the existing
`setPTTMode` worklet message; the worklet's internal `pttMode` and the JS
`pttModeEnabled` var are intentionally decoupled in native mode.

## Decisions

Defended autonomously: kept LOW/LOW/500/500 sensitivities (deterministic smoke
test); included the reconnect worklet-re-arm fix (a real bug otherwise); made the
audio layer self-defend against `muteInput()` (native branch ignores it).
Escalated to the maintainer (both confirmed): **guard the two overlay UI files**
against the worklet re-arm, and **accept the barge-in UX delta** (native mode
drops the instant client-side flush; Gemini owns interruption via
`server_content.interrupted`).

## Tests

- `test_live_ai_gemini.py`: activity signals suppressed in native VAD / fire in
  manual VAD (mock `_current_session`, patch `get_settings`).
- `test_websocket_ephemeral.py`: `session_ready.native_vad` asserted, plus a
  parametrized test proving it tracks `DISABLE_GEMINI_VAD` both ways.
- Backend suite 186 passed. Frontend `tsc` clean (24 baseline errors, **0 new**).
- Frontend behaviour has no closure-level test runner; PR ships a manual smoke
  checklist (native-VAD log; no `vad_activity_*` WS frames; continuous audio incl.
  silence; Gemini self-detects turns; flip flag -> manual signals resume).

## Doc freshness

`docs/standards/voice-and-vad.md` rewritten: the toggle is now the lead section,
added a "Native VAD mode (default)" subsection + the barge-in delta note, updated
the sensitivity callout, expanded the Tracks list (added websocket_routes.py,
audioManager.ts, webFormConnection.ts, VoiceOverlay.tsx), bumped Last-updated, and
removed a stale duplicate footer stamp. Other freshness flags were pre-existing
backend-mtime noise on files this change doesn't alter in a doc-relevant way.

## Files touched

backend: `config.py`, `routes/websocket_routes.py`, `adapters/live_ai_gemini.py`,
`tests/unit/test_live_ai_gemini.py`, `tests/integration/test_websocket_ephemeral.py`.
frontend: `webFormConnection.ts`, `shared/connection.ts`, `shared/audioManager.ts`,
`demo/VoiceOverlay.tsx`, `demo/VoiceOverlayMobile.tsx`.
docs: `standards/voice-and-vad.md`.
