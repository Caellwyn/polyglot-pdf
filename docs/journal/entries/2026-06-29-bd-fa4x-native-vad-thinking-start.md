---
date: 2026-06-29
bead: polyglot-pdf-fa4x
title: "Thinking indicator native-VAD START -- premise disproven, already works"
tags: [voice, vad, testing, conventions]
---

## Trigger

bead polyglot-pdf-fa4x, the wpw.5 follow-up. wpw.5 shipped the thinking indicator
working in MANUAL/PTT VAD but two live real-mic tests showed it did NOT fire in
NATIVE VAD (the deployed default). The reported root cause: the
`gemini-live-2.5-flash-native-audio` model emits no `input_transcription`, so the
indicator's native-VAD START trigger (`on_user_activity`, which rides
`input_transcription`) never fires. fa4x was filed to add the missing native START
(options: get input_transcription firing / output-cadence heuristic / client
approximation).

## What we found (the premise was wrong)

**`input_transcription` DOES fire in native VAD -- the wpw.5 finding was measured
under the old `VAD_START_SENSITIVITY=LOW` config.** A focused probe
(`scripts/spikes/diag_input_transcription_fa4x.py`) drove the committed audio
fixtures through the EXACT production config (native VAD, START=HIGH/END=LOW,
response AUDIO, complete TOOL_DECLARATIONS) and recorded, per turn, whether a
non-empty `input_transcription` arrived:

- **Deployed Vertex model `gemini-live-2.5-flash-native-audio`: 8/8 turns**, first
  signal of every turn, latency ~1.0-1.9 s (before the agent's audio).
- AI Studio `gemini-2.5-flash-native-audio-preview-12-2025`: also fires (the
  odd/even miss pattern there is a probe turn-segmentation artifact in
  continuous-silence mode, not a model miss).

The 4sv7 A/B (2026-06-11) had already replaced START=LOW -> HIGH as the in-code
default, BUT it measured turn REGISTRATION by ANY signal (model_turn / audio /
turn_complete / tool_call / input_transcription), so it never isolated whether
`input_transcription` SPECIFICALLY fires. This probe did, and it does.

Consequence: **fa4x Option 1 needs ZERO new code.** The existing
`input_transcription` -> `on_user_activity` -> `signal_processing_start` ->
`agent_processing` path already works in native VAD on `dev` (the wpw.5 wiring is
present at session start AND restart; Codex PR #273's `turn_complete` clear closes
the dedup-stuck path). The maintainer chose "automated harness verify + docs" once
the premise was shown disproven.

## What shipped

- **Probe** `scripts/spikes/diag_input_transcription_fa4x.py` -- the deploy-fidelity
  isolation test above (AI Studio + `--vertex`). Committed as the reusable evidence.
- **Harness observability** -- the E2E voice harness now records the backend
  `agent_processing` signal via a new dev-only `window.vffOnAgentProcessing` hook
  (`webFormConnection.ts`, fired in the existing `agent_processing` handler; declared
  on the harness Window interface in `connection.ts`). `runCycle` resets the observer
  per cycle and records `report.thinking = {sawStart, sawClearAfterStart, count}` --
  OBSERVATIONAL, never flips the verdict. The hook is undefined in production (a
  single always-false `if` on the hot path; zero behavior change).
- **Docs** -- registered the `agent_processing` (backend->frontend) and
  `clear_thinking` (frontend->backend) wire types in `ws-protocol.md` (deferred from
  wpw.5 until the native START was whole); corrected `voice-ai.md`'s Response-config
  section (`input_audio_transcription` is enabled when `on_user_activity` is
  registered OR transcripts are on, and DOES fire at START=HIGH); reviewed
  `voice-and-vad.md` for the native START.

## Verification

Three independent lines of evidence that the native-VAD START signal works:

1. **Vertex probe** -- `input_transcription` fires 8/8 on the deployed model.
2. **AI Studio probe** -- `input_transcription` fires.
3. **Live E2E** (local stack, real 2.5 native-audio model, native VAD START=HIGH,
   real frontend via Chrome MCP + the voice harness): `thinkingObserved()` returned
   `{sawStart:true, sawClearAfterStart:true, count:4}` across two turns -- the
   indicator armed and cleared in native VAD. The field filled correctly; the
   backend log showed a clean turn (update_form_fields applied, first response audio,
   no errors). This DIRECTLY refutes the wpw.5 "0 agent_processing sends in native
   mode" finding. (The confirm/advance stalled -- the known bd polyglot-pdf-95uy
   native-VAD FLAKY quirk, NOT fa4x.)

Backend callback tests 32/32; full frontend suite 447/447 (incl. a new test that the
`vffOnAgentProcessing` hook fires on each `agent_processing` message).

## Lessons

- **A live-test diagnosis is only as good as the config it pinned.** wpw.5's "native
  audio emits no input_transcription" was true under START=LOW and false under the
  START=HIGH default the app actually ships. Re-confirm a model-behavior claim
  against the ACTUAL deployed config (model id AND VAD sensitivity), not a prior live
  test whose knobs you did not control. The 4sv7 default flip (LOW->HIGH) had already
  mooted the premise three weeks earlier.
- **gcloud ADC is available locally** (project `polyglot-demo-aa709`), so a Vertex
  probe -- not just AI Studio -- can settle a deployed-model question in-session.
  This is the highest-fidelity cheap check for a native-audio behavior fork.
- **"Already works" is a legitimate bead outcome.** The honest delivery here is
  verify + document, not a heuristic built to fix a non-problem. Options 2/3 (output
  cadence / client approximation) would have added fragile code for nothing.

## Doc freshness

- **Updated:** `ws-protocol.md` (registered `agent_processing` + `clear_thinking`),
  `voice-ai.md` (Response-config correction), `voice-and-vad.md` (native-START
  review). All three pass the freshness gate.
- **Reviewed and LEFT (pre-existing stale on surfaces fa4x did not change):**
  `stateless-architecture.md` lists `webFormConnection.ts`/`connection.ts`, which
  this branch touched ONLY with the test-only `vffOnAgentProcessing` hook -- no
  stateless-contract change, so nothing to correct. `hipaa-pii-policy.md`,
  `logging-and-cost.md`, `risk-rating.md`, `si-reduction.md`, `terminology.md`,
  `technical_guide.md` track backend files (config/adapter/models/manifest) this
  branch did not meaningfully change; they were stale before this branch and are out
  of fa4x scope -- left for their own beads.

## Beads housekeeping

Closeout prep found no orphans. Three pre-existing stale `in_progress` beads
(`hrn`, `jf6w`, `ue5s`) are maintainer-owned long-running epics/tasks unrelated to
fa4x -- not transitioned (their state is the maintainer's product call, not a fa4x
closeout action).

## Files touched

- `scripts/spikes/diag_input_transcription_fa4x.py` -- NEW probe.
- `frontend/src/webFormConnection.ts` -- fire `window.vffOnAgentProcessing` in the
  `agent_processing` handler (test-only).
- `frontend/src/shared/connection.ts` -- declare `vffOnAgentProcessing` on the
  harness Window interface.
- `frontend/src/webFormConnection.thinking.test.ts` -- +1 test for the hook.
- `tests/e2e/voice-harness/harness.js` -- thinking observer + `report.thinking` +
  `resetThinkingObserver`/`thinkingObserved` API.
- `tests/e2e/voice-harness/RUNBOOK.md` -- step 6a (assert the indicator armed).
- `docs/standards/ws-protocol.md`, `docs/components/voice-ai.md`,
  `docs/standards/voice-and-vad.md` -- wire-type registry + corrections.
