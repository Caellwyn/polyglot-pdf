---
date: 2026-07-11
bead: polyglot-pdf-7872
title: "Flip continuous-DTI code defaults to production values + section-reset residue inventory"
sprint: 11
tags: [conventions, testing]
---

## Trigger

Sprint-11 epic polyglot-pdf-fc7t child C1 (plan:
docs/sprint_11_continuous-dti-law_plan.md). Section-based sessions are retired
as a product matter, but the code defaults still said section-reset: USE_DTI,
CONTINUOUS_SESSION, CONTEXT_COMPRESSION_ENABLED all defaulted false, and
continuous mode was live only because deploy-demo.sh set env vars. A fresh
deployment (or local dev) silently ran the retired flow.

## What shipped

- backend/config.py: USE_DTI, CONTINUOUS_SESSION, CONTEXT_COMPRESSION_ENABLED
  default ON; CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS default 1500 (the
  ctu8-validated production value -- post-Vertex-clamp the margin selects the
  window: 5000 - 1500 = the validated 3500; the old 600 derived an untested
  4400). Env vars remain the escape hatch; comments state the current law.
- deploy-demo.sh: the four now-redundant vars dropped; comment documents the
  three-flag emergency fallback (CONTINUOUS_SESSION alone force-couples
  USE_DTI back on, so a legacy fallback must set all three false).
- scripts/spikes/measure_form_session_costs.py `_make_settings`: every arm now
  PINS its full mode explicitly (USE_DTI/CONTINUOUS_SESSION/COMPRESSION false
  base, arm overrides on top) so a default flip can never silently relabel an
  arm's measured configuration (the el92 mislabeled-cost-data failure class).
  Historical comparability preserved: arms measure exactly what they always
  measured.
- Tests: new test_continuous_dti_is_the_default_configuration pins the four
  flipped defaults (epic exit criterion 1). 14 tests that implicitly assumed
  legacy defaults updated honestly to REQUEST legacy mode explicitly:
  test_ai_context.py (11 tests, autouse fixture -- the whole file tests the
  legacy full-SI renderer, a harness-only survivor), test_dti.py
  _service_with_settings helper (section-mode initiating-message shape),
  test_live_ai_gemini.py _compression_settings fixture, and
  test_section_switching.py's SI-content test (service settings + the
  ai_context module get_settings patch -- the SI builder reads the module's
  lru_cached get_settings, not the injected service settings).

## Section-reset residue inventory (exit criterion 3 -- the C7/55jg deletion checklist)

RETIREMENT CANDIDATES (production-facing, delete in bd polyglot-pdf-55jg):
- switch_section tool: declaration backend/config.py:374-386 (+ SI text at
  config.py:573/576/597 -- legacy SYSTEM_INSTRUCTION section lines), dispatch
  backend/services/callback_handler.py:408-409 + _handle_switch_section_tool
  :556-564, handler form_filling_service.py:1807 handle_switch_section +
  prepare_section_switch coordination (request_coordinator.py:585).
- Frontend section-switch machinery (frontend/src/webFormConnection.ts):
  handlePrepareSectionSwitchRequest :1280, proceedSectionSwitch :2096,
  switchToSection :3665, completeSection :3792, the non-continuous handshake
  branch :3614-3663, pendingSectionSwitch park/resume/cancel :2231-2253.
- schemaFormState.ts markSectionComplete :346 / switchToSection :559 /
  buildHandshakeManifest (manifestUtils.ts:108) where production-only.
- Legacy-default test files that pin the deleted paths retire WITH the paths
  (test_section_switching.py bulk, FE switchdurability.test.ts,
  VoiceOverlay.disclaimer.test.tsx switchToFirstSection asserts, voice-harness
  multi-section leg).

KEEP (shared with continuous or harness-consumed -- documented survivors):
- service.switch_to_section (form_filling_service.py:992): the continuous
  GoAway/1011 reconnect path AND the harness baseline arm drive it directly.
- Legacy full-SI renderer branch (ai_context.py:381-404 section_list, 471-486
  format branch): consumed by measure_form_session_costs.py --arm
  section-reset (the baseline instrument) and --arm dti (non-continuous).
- The manifest-first "jit" transport (handshake_jit / jit_mode /
  buildContinuousManifest): DTI's carrier, not legacy.
- ai_context.py:468 `or schema.get("jit_mode")` rollback route.
- All tools except switch_section (continuous drops exactly one tool, pinned
  by test_dti.py test_continuous_session_drops_switch_section_tool).

FLAG-READ MAP (for C7's reference): USE_DTI reads at ai_context.py:468,
websocket_routes.py:953-954 (handshake), live_ai_gemini.py:1643 (derive gate),
form_filling_service.py:425/573/841/1170/1178, callback_handler.py via
injected getter :86-92/718-719/891-893. CONTINUOUS_SESSION reads at
websocket_routes.py:958 (handshake), form_filling_service.py:196-197 (drops
switch_section) + :607-613 (suppresses section metadata); frontend receives it
via handshake (webFormConnection.ts:773-775 + gated branches :1290/:2020/
:2102/:3609/:3798, navigation.ts:163). CONTEXT_COMPRESSION_ENABLED reads at
live_ai_gemini.py:1631 (whole compression block) + config.py:303 (validator
clamp).

## Lessons

- CONTINUOUS_SESSION force-couples USE_DTI at CONSTRUCTION (config.py
  model_validator), so with continuous defaulting on, `Settings(USE_DTI=False)`
  alone no longer yields a non-DTI config -- every legacy consumer (tests,
  fallback env sets) must set BOTH flags false. Three test fixtures were bitten
  by exactly this.
- ai_context reads its own module's lru_cached get_settings, not the service's
  injected settings -- a test injecting legacy Settings into
  FormFillingService still gets the DTI SI unless it also patches
  backend.services.ai_context.get_settings (existing memory scar, re-confirmed).
- A defaults flip is a semantic change for every `Settings()` constructed bare:
  the harness's baseline arm would have silently measured the continuous
  config while labeling it "section-reset". Instruments must pin their full
  mode explicitly, never inherit defaults.

## Doc freshness

No tier-2 docs bumped: the continuous-DTI doc alignment is the epic's own C8
bead (ft47), deliberately sequenced after the C7 deletion so docs state
post-deletion truth. (si-reduction.md's "default false" line and
context-compression.md's "default off" framing are now stale as of this PR --
both are already named in ft47's scope.) Pre-existing stale-doc warnings from
closeout prep track files this branch did not touch -- reviewed and left.

## Files touched

- backend/config.py (four defaults + comments)
- deploy-demo.sh (dropped redundant vars, fallback comment)
- scripts/spikes/measure_form_session_costs.py (_make_settings explicit pins)
- backend/tests/unit/test_dti.py (defaults test rewritten + new pin test +
  helper continuous pin)
- backend/tests/unit/test_ai_context.py (legacy-mode autouse fixture)
- backend/tests/unit/test_live_ai_gemini.py (_compression_settings continuous pin)
- backend/tests/unit/test_section_switching.py (explicit legacy settings +
  ai_context patch)
- docs/journal/entries/2026-07-11-bd-7872-flip-continuous-dti-defaults.md (this)
