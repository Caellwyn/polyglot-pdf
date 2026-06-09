---
date: 2026-06-08
bead: polyglot-pdf-g8w
title: "Voice form-fill E2E harness: scripted audio drives the ask -> fill -> confirm cycle, no human mic"
tags: [testing, harness]
---

## Trigger

The voice form-fill loop -- Gemini asks for a field value, the user speaks it,
Gemini fills the field and asks to verify, the user confirms, Gemini advances --
was only testable by a human talking into a microphone. That made every iteration
on the voice path slow and unrepeatable. The maintainer asked for a tool that
drives the cycle with real scripted audio so the tool-call / field-fill / continued
engagement path is regression-testable without speaking.

## What shipped

An automated browser-E2E harness that injects committed audio fixtures into the
real app (against a local backend + real Gemini) and asserts on concrete outcomes.

- **App hook** (`frontend/src/shared/connection.ts`): a dev-gated
  `window.__VFF_TEST_INJECT` published inside `createConnectionManager`. It exposes
  `sendAudio` / `sendActivityStart` / `sendActivityEnd` / `isNativeVad` /
  `getLastNextField` -- thin pass-throughs to the closure the manager already has,
  so injected PCM takes the exact same path mic audio does (straight to the WS),
  bypassing getUserMedia + the worklet + the silence/noise gate. `onNextField` is
  wrapped to track `lastNextField` so "advanced to the next field" is assertable
  without scraping transcripts.
- **Gate** (`frontend/src/shared/config.ts`): `isTestHarnessEnabled()` requires
  BOTH `__VFF_LOCAL_DEV` and `__VFF_TEST_HARNESS`, read from window OR localStorage
  (so the gate survives the reload the harness does). Never true in production or
  normal local dev. The dev-override reads (`__VFF_BACKEND_URL` etc.) also gained
  the localStorage fallback.
- **Auth bypass** (`frontend/src/contexts/AuthContext.tsx`): same double-gate
  installs a mock user (no network, no Firestore) so the harness skips Firebase
  login -- an automated E2E that needs a human to log in is not automated.
- **Fixtures**: committed 16 kHz mono PCM16 WAVs
  (`frontend/public/test-fixtures/{digits_1234567,confirm_yes}.wav`), generated once
  by `tests/e2e/voice-harness/gen_fixtures.py` (gTTS -> librosa/soundfile).
- **Harness** (`tests/e2e/voice-harness/harness.js` -> `window.__VFF_HARNESS`):
  `loadFixture` (validates the WAV format), `injectUtterance` (VAD-aware chunked
  streaming), outcome waiters, and a high-level `runCycle` that returns a
  PASS/FAIL/FLAKY report.
- **RUNBOOK** + a **`voice-harness` skill** so a future session runs it without
  re-deriving the setup.

## Verified

Driven live in Chrome against a worktree backend (2.5 native-audio). The backend
dev log shows the full chain: injected 640-byte PCM frames -> Gemini transcribed
"one two three four five six seven" -> `update_form_fields` tool call -> the
Alien Registration Number field filled with `1234567` (green confirmed checkmark).
`runCycle` returned **PASS**: fill resolved in 1.6s, field confirmed.

## Scar tissue / decisions

- **Gate on OUTCOMES, not audio.** The first design waited on
  `vffOnAudioPlaybackEnd` (audio-silence). That signal is unreliable: Gemini streams
  many tiny chunks and an automated tab may never fire `onended` -- every
  `waitForGeminiQuestion` timed out even though the fill SUCCEEDED. The rewrite gates
  on concrete state (`waitForFieldValue`, `waitForConfirmOrAdvance`); the audio wait
  is kept for pacing only. The validated PASS run had zero audio signals.
- **Browser tooling.** The Claude Preview tool renders in an opaque-origin sandbox
  (`origin null`, storage denied) and cannot run this app (its state is
  `sessionStorage`). Drive it with the Chrome MCP. The frontend must run with
  `--mode demo` (Firebase config) on a CORS-allowed port (5173-5177), and the backend
  with `VFF_DISABLE_AUTH=true` (else the WS handshake times out verifying the token).
- **Bug the harness caught (bd polyglot-pdf-0ux):** on native-audio the
  `update_form_fields` FunctionResponse can be sent without an `id`, raising in
  `send_tool_response` (`live_ai_gemini.py:1569`) and crashing the receive loop AFTER
  the first fill -- so Gemini never advances. Filed separately; out of scope here.

## Notes for review

- This PR is **frontend-only**; it touches zero backend files. The one failing
  backend test in closeout prep (`test_activity_signals_suppressed_in_native_vad`)
  is pre-existing -- it came in with the dev merge (commit `0c5ac16`, bd
  polyglot-pdf-tks) and is unrelated to this change.
- The dev-merge also flagged many backend/voice docs as stale; those are the
  `tks`/dev changes, not this PR. The only doc-tracked source this PR touches is
  `connection.ts`, and the change there is a test-only hook, not a behavior change
  the voice-ai / websocket-routing docs describe.
