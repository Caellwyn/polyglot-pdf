---
date: 2026-06-11
bead: polyglot-pdf-x52p
title: "Sprint 3: google-genai 2.8.0 cutover + voice turn-reliability root cause (VAD start sensitivity)"
sprint: 3
tags: [refactor, testing, harness]
---

## Trigger

Maintainer kickoff (2026-06-11): voice round trips with Gemini have never
worked well on the demo -- short answers ("yes") drop, two successful turns in
a row are rare, reconnects re-greet. First move: update the `google-genai` SDK
(pinned 1.38.0, ~40 releases behind 2.8.0), then consolidate the scattered
voice-reliability beads under one SPEAR plan and orchestrate whatever fixes the
evidence demands. Plan: `docs/sprint_3_voice-roundtrip-reliability_plan.md`
(epic `polyglot-pdf-1cnn` + beads 4sv7/vmxx/wq9y/95uy). Maintainer
pre-authorized autonomous execution; Codex quota exhausted, so the internal
adversarial fresh-eyes loop is the review record for this PR.

## What shipped

- **SDK cutover 1.38.0 -> 2.8.0 (x52p).** An empirical install-and-diff of both
  versions (recorded on bd 1cnn) found exactly ONE breaking change for this
  codebase: 2.x re-raises receive-path WebSocket closures as
  `google.genai.errors.APIError` instead of `ConnectionClosed`. The adapter's
  graceful-close handler and the 1011 diagnostic now catch both. Everything
  else (client construction, raw-dict Live config, send methods, types,
  pattern-matches, wire encoding) verified unchanged. Suite: 270->279 passed
  (no regressions; 9 new tests).
- **Live verification on 2.8.0 (4td1, absorbs a7k).** Extracted
  `_build_live_config()` from the session loop; the contract smoke test now
  drives the DEFAULT model with the adapter's real config (passes live on both
  2.5 and 3.1 in ~4-5 s). A/B probe on both SDK versions confirmed the known
  3.1 update_form_fields skip is model behavior, not an SDK regression.
- **Vendored docs refreshed to 2.8.0 (c9fy)** -- including the receive()/
  APIError pattern and the additive 2.8 surface (explicit VAD signal,
  transcription language_codes), marked not-yet-endpoint-verified.
- **Turn-reliability root cause (4sv7, bead stays open pending demo deploy).**
  New spike `scripts/spikes/diag_turn_reliability_4sv7.py` drives real audio
  (the committed fixtures, incl. the failing short "yes") per model x VAD mode.
  Result: the shipped `START_SENSITIVITY_LOW` registered 14/20 turns across 3
  sessions (4/8, 7/8, 3/4 -- the demo's non-deterministic feel) while
  `START_SENSITIVITY_HIGH` registered 20/20 with a tool call every turn. The
  `VAD_*` settings were also hard-coded literals (deploy env could not tune
  them); now env-overridable, default `START=HIGH`. Documented in
  `docs/standards/voice-and-vad.md`. Zero 1011s in ~24 sessions (bd daa's
  transient-outage verdict holds).
- **Silent resume on reconnect (vmxx, stays open pending live demo verify) +
  legacy handshake `type` (wq9y).** Handshake now carries `resume:true` on any
  reconnect after first open; the backend selects a RESUME initiating message
  and appends a no-greeting override to the per-connect system instruction.
- **Voice-harness continuous-silence fix (95uy)** + a headless Playwright
  driver (`tests/e2e/voice-harness/driver_playwright.mjs`) replacing the
  Chrome-MCP-by-hand procedure. Verified live: the injected "yes" is now
  transcribed and the turn closes -- the 95uy stall signature is gone.
- **Deferred/filed:** bd `polyglot-pdf-i9q8` (P1) -- with the audio path fixed,
  the E2E cycle isolated a pre-existing tool-call-compliance defect under the
  app's full ~3850-char system instruction: 2.5 hears the "yes" but never calls
  confirm_field; 3.1 never calls update_form_fields. Direct probes with a short
  explicit SI get reliable tool calls from both models, so the SI is the prime
  suspect. Full timeline + driver logs in the bead.
- **Fresh-eyes triage:** see PR body scorecard (this entry is written pre-loop;
  the loop's adopt/reject/defer outcome is recorded in the merge ping).

## Lessons

- **Empirical SDK diffs beat changelog reading.** The scary headlines (2.0.0
  breaking changes, vertexai->enterprise rename) were Interactions-only and
  docs-only respectively; the one real break (receive() error type) appears in
  no summary we found. Installing both versions and diffing
  signatures/model_fields settled in minutes what speculation had inflated into
  a stepped migration plan.
- **"Env-tunable" settings must be proven env-tunable.** `VAD_*` looked like
  config but were literals -- a deploy-env experiment (VAD_START_SENSITIVITY=
  HIGH) silently did nothing until the code was checked. Same family as bd 9jv
  (vad_config.json route reads nothing).
- **Fix the instrument before trusting the experiment.** The 95uy harness
  artifact (dead air after a fixed 500 ms tail) masked everything downstream;
  with continuous silence streaming, the REAL per-mode registration rates
  became measurable and the SI compliance bug became visible and isolable.

## Doc freshness

- Bumped with content: `docs/components/voice-ai.md` (SDK 2.8 + config-builder
  extraction), `docs/components/websocket-routing.md` (handshake `resume` +
  legacy `type`), `docs/standards/voice-and-vad.md` (sensitivity findings +
  chosen config), `docs/genai_docs/*` (2.8.0 surface), `docs/INDEX.md` (sprint
  3 plan row).
- Reviewed and left as-is (tracked files changed but their concerns did not):
  `ai-models.md` (no model selection change), `hipaa-pii-policy.md`,
  `logging-and-cost.md`, `risk-rating.md`, `stateless-architecture.md` (the
  resume flag is client-signaled; the backend still stores nothing),
  `terminology.md`, `testing.md`, `technical_guide.md`,
  `schema-forms.md`, `context-compression.md`.

## Files touched

- `backend/requirements.txt` -- google-genai pin 1.38.0 -> 2.8.0
- `backend/adapters/live_ai_gemini.py` -- APIError catch; `_build_live_config`
  extraction; VAD docstring correction
- `backend/config.py` -- env-overridable VAD_*, default START=HIGH;
  RESUME_INITIATING_MESSAGE
- `backend/routes/websocket_routes.py`, `backend/services/
  form_filling_service.py`, `backend/services/ai_context.py` -- resume flag
- `backend/tests/unit/test_resume_reconnect.py` -- new (9 tests)
- `backend/tests/contract/test_live_ai_gemini_integration.py` -- real-config
  smoke test (a7k)
- `frontend/src/webFormConnection.ts`, `frontend/src/schema-forms/state/
  schemaFormState.ts` (+ test) -- resume + legacy handshake type
- `tests/e2e/voice-harness/harness.js`, `RUNBOOK.md`,
  `driver_playwright.mjs` (new) -- continuous silence, yes-retry, headless driver
- `scripts/spikes/diag_turn_reliability_4sv7.py` (new),
  `scripts/spikes/diag_native_audio_1011.py` -- reliability matrix; 2.x catch
- `docs/genai_docs/*`, `docs/components/voice-ai.md`,
  `docs/components/websocket-routing.md`, `docs/standards/voice-and-vad.md`,
  `docs/INDEX.md`, `docs/sprint_3_voice-roundtrip-reliability_plan.md` (new)
- `frontend/public/shared/audio-processor.worklet.js` -- stale build artifact
  synced with source
