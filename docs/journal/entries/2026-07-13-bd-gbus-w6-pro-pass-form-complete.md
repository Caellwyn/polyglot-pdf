---
date: 2026-07-13
bead: polyglot-pdf-gbus
title: "W6: whole-form gemini-2.5-pro pass at form_complete (sole end-of-form report)"
sprint: 12
tags: [performance, refactor, testing]
---

## Trigger

Sprint-12 epic 09da (decoupled async validator), final child W6 -- CONDITIONAL on
W5's GO. W5 (bd polyglot-pdf-g0w1) measured gemini-2.5-pro whole-form far-pair
recall = **1.000** (6/6) with thinking bounded to 512 -> **GO**. W6 wires that pass
at `form_complete` as the SOLE end-of-form report, catching the cross-page
(far-pair) contradictions the ~20-field lite windows structurally cannot see. W5
attached a **precision condition**: uncorrected whole-form precision was 0.750 (pro
over-flags the Part 5/6 preparer-interpreter certification block + bracketed-repeat
fields), so W6 must ship an anti-over-flag prompt.

## What shipped

`form_complete` no longer runs the flash-lite window pass; it runs ONE whole-form
gemini-2.5-pro contradiction pass. REPORT-ONLY like the lite windows -- its
conflicts ride the SAME `validation_result` -> `validatorFindingsQueue` ->
`drain_findings` -> steer path (W3), so **zero client changes**.

- **config.py:** `FORM_COMPLETE_PRO_VALIDATOR` (default-OFF), `VALIDATOR_PRO_MODEL`
  (gemini-2.5-pro), `VALIDATOR_PRO_THINKING_BUDGET` (512), `VALIDATOR_PRO_TIMEOUT_SEC`
  (20, ~2.5x W5 p90).
- **text_ai_gemini.py:** a `thinking_budget` constructor param threaded into
  `_generate` as `types.ThinkingConfig(thinking_budget=N)`. None (the lite default)
  sends no thinking_config -- the lite path is byte-for-byte unchanged.
- **validator_service.py:** `WHOLE_FORM_PRO_SI` -- the contradiction rules + the
  FAR-PAIR rule + the g1c anti-hedging/precision block + the W6 anti-over-flag items
  (Part 5/6 cert block; bracketed-repeat/continuation) + an `{adjudicated}` slot.
  `render_validator_payload`/`validate` gained `si` + `steered_field_ids` params.
- **form_filling_service.py:** `_text_ai_pro` + `handle_form_complete_pro` -- one
  whole-form pro call (fail-open timeout), fed the steered ids (prompt-layer), then
  DEDUPED against the steered markers via the shared `_suppress_already_steered`
  (authoritative not-re-flag guarantee), returning the report-only shape.
- **dependencies.py:** `get_text_ai_pro` -- returns None unless the flag is on;
  constructed with a bounded thinking budget AND an EMPTY fallback chain (a pro
  outage must fail-open clean, never silently downgrade to the lite tier and lose
  the far-pair recall).
- **websocket_routes.py:** `form_complete` arm -> `_spawn_pro_complete` (a tracked,
  crash-safe background runner pushing the same report-only `validation_result`).

**Decisions (autonomous, defended -- the plan + W5 GO authorize the wiring; these
are the rollout/shape calls the plan left open):**
- *`FORM_COMPLETE_PRO_VALIDATOR` default-OFF.* Wiring a pro-tier model into
  production `form_complete` is a new operational-cost dependency (~$0.0093/call),
  and its uncorrected precision (0.750) would surface spurious flags on ~6/10 clean
  forms. Default-off lands the code dark; flip on by env (mirrors the EXTRACTOR_MODEL
  doctrine, no redeploy) AFTER the precision re-measure confirms the anti-over-flag
  prompt lifts precision. Reversible; conservative.
- *Suppression-layer as the not-re-flag guarantee, no new client wire field.* The
  contract-2 `steered` markers already ride the form_complete payload;
  `_suppress_already_steered` over them is the deterministic guarantee (a test
  asserts a steered contradiction is dropped). The prompt-layer adjudicated feed is
  an additional precision aid, not the guarantee. Keeps the client untouched.
- *Live precision re-measure DEFERRED (Vertex spend, orchestrator-gated).* The code
  PR ships a deterministic prompt-content assertion (the anti-over-flag prose is
  present); the live re-measure that confirms precision lifted is a separate,
  per-instance spend decision. The W5 probe was extended with a `--prod-prompt` flag
  so the re-measure runs the SHIPPED `WHOLE_FORM_PRO_SI`; it is NOT run in this bead.
  The default-off gate depends on that re-measure passing.

## Lessons

Because W3 made `validation_result` a report-only envelope the client enqueues, a
whole new validator TIER (pro, whole-form) could be added at `form_complete` with
**zero client changes** -- it produces the same envelope the lite windows do and
rides the same queue/drain path. The report-only + client-owned-queue split (W3)
was the enabling abstraction: W6 is "swap which method the form_complete arm spawns
+ add the pro validator," not a new wire protocol.

## Doc freshness

- **Bumped** docs/standards/validation-delegation.md: the W6 note (form_complete =
  the whole-form pro pass, the sole end-of-form report; fed+deduped against steered;
  anti-over-flag prompt; default-off flag).
- W1/W2/W3/W4 docs already current on the async path; W6 only adds the pro tier at
  the form_complete boundary.

## Files touched

- backend/config.py -- FORM_COMPLETE_PRO_VALIDATOR + pro model/budget/timeout knobs.
- backend/adapters/text_ai_gemini.py -- thinking_budget -> ThinkingConfig.
- backend/services/validator_service.py -- WHOLE_FORM_PRO_SI + si/steered_field_ids
  params on render_validator_payload/validate.
- backend/services/form_filling_service.py -- _text_ai_pro + handle_form_complete_pro.
- backend/dependencies.py -- get_text_ai_pro (flag-gated, no fallback).
- backend/routes/websocket_routes.py -- form_complete -> _spawn_pro_complete.
- backend/tests/unit/test_form_complete_pro.py (new) -- wired/emits, not-re-flagged,
  context feed, fail-open (off/timeout/error), anti-over-flag prompt content.
- backend/tests/unit/test_text_ai_gemini.py -- thinking_config wired / not-wired.
- backend/tests/integration/test_proactive_complete_events.py -- form_complete now
  routes through handle_form_complete_pro (mock stub + cancel-on-disconnect test).
- backend/scripts/probe_g1b_model_size_bakeoff.py -- --prod-prompt (re-measure with
  the shipped SI; orchestrator-gated live run).
- docs/standards/validation-delegation.md -- W6 note + bump.
