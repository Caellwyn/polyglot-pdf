---
date: 2026-06-28
bead: polyglot-pdf-h1bn
title: "Static-SI edge cases + measure/verify (reconnect, switch, >=10 live runs, voice E2E)"
sprint: 7
tags: [testing, refactor, postmortem]
---

## Trigger

Child D (the capstone) of the fully-static DTI system-instruction epic
(polyglot-pdf-13w7). After 1ac3 (static SI), j748 (field-1 via injection), and uogm
(remaining values via injection), this bead closes the edge cases and runs the
live verification that formally closes the original field_id hallucination bug
(jnjj.46) + the abandoned-fuzzy-matcher bug (kahz). Carries the fu1h audit's F3/F4
edge-case notes + the restart_gemini_session gap (the closed-dup 88m6).

## What shipped

**Two code changes:**
- **restart_gemini_session DTI injection.** A Level-3-farewell reconnect rebuilds
  the (static) SI but never re-delivered field guidance. Now it fires the initiating
  message after set_callbacks (DTI-gated), so the current field's guidance + metadata
  reach the restarted session -- the gap the fu1h audit flagged.
- **Deterministic current-field coercion (the headline).** The model's field_id on
  update_form_fields / confirm_field is now ADVISORY, not authoritative. A DTI turn
  is scoped to one field (cross-field intent goes to the secretary, never
  update_form_fields), so when the model targets a DIFFERENT id than the current
  field -- a HALLUCINATED id (the residual jnjj.46 disobedience) or a VALID-but-wrong
  id (the 8vy3 ordering drift) -- the value is re-pointed onto the known current
  field. The current field is tracked as a transient per-turn id
  (self._current_field_id), set from the field-1 hint at session/section start and
  from each delivered next-field schema on confirm. This is per-turn ROUTING
  metadata (a single id, overwritten each turn, no user values), NOT persisted field
  state -- the stateless invariant holds. update_form_fields coerces in the service
  (handle_update_fields_tool_call); confirm_field coerces in callback_handler via an
  injected get_current_field_id getter, so the confirm follows the coerced update
  onto the same field (else the FE looks up the wrong id and strands it). Gated on
  USE_DTI + a known current field + a single-field update; non-DTI / multi-field /
  matching-id paths are untouched.

**Design path (why coercion, not a "did you mean" nudge).** The maintainer pushed on
the residual: 2/77 in testing is a nightmare at 10k interactions/hour. The first
idea was to add a nearest-id suggestion to the unknown-field error so the model's
retry self-corrects -- but that still trusts the model. The maintainer's better
framing: the whole turn is deterministically scoped to one field, and cross-field
navigation is the secretary's job, so DON'T require the model to get the id right --
the stateful frontend already owns field state + computes the current field. The
backend already consumes+merges the current-field schema each turn (so coercion
reads per-turn data it already holds, not new persistent state). That made backend
coercion the small, invariant-respecting fix.

**Live verification (criterion-defining):**
- **Criterion 1 (>=10 runs, wrong-id ~0): PASS.** Pre-fix 10x baseline = 2/77 fill
  calls stranded as unknown_fields (2/10 runs, all on p1_line2_acctidentifier;
  correct id verifiably delivered -- model disobedience, not a delivery gap).
  POST-FIX 10x = **0/91 stranded**; the model still hallucinated/drifted on 4/10 runs
  (logged: p1_line1_uscis, p1_line6b_streetaddress, an 8vy3 drift, etc.) and coercion
  caught EVERY one -- update + confirm together. Deterministically ~0, stronger than
  the plan's "8/10 perfect" target.
- **Criterion 2a (voice-harness E2E happy path): PASS** (2/2 clean runs through the
  real frontend + backend + Gemini with USE_DTI: fill -> confirm -> advance, field 1
  -> field 2). One extra field-2 attempt went FLAKY (never-filled = documented
  audio-end non-determinism, not a code defect).
- **Criterion 2b (non-English honors language, no regression): PASS** (Spanish
  fill_language: UI localized, disclaimer "Estoy de Acuerdo", field filled + confirmed
  + advanced).

Fresh-eyes adversarial assess: <FRESH_EYES_PLACEHOLDER -- filled at closeout>.

## Lessons

A test caught a shared-singleton mutation in my OWN new test: `get_settings()` is
lru_cached, so `service._settings.USE_DTI = True` in one test leaked into the next
(which then saw DTI on and failed). Fix: build a FRESH `Settings()` per test when
toggling a flag, never mutate the cached singleton. Generalizes: any test that
mutates a flag on a service built from `get_settings()` is mutating shared state --
construct an isolated Settings.

The deeper lesson (recorded for the epic): when a model intermittently disobeys a
correctly-delivered instruction, the robust fix is often to remove the model's
authority over the thing entirely (make its output advisory + deterministically
resolve server/client-side) rather than to coax better obedience. Here that also
killed an unrelated bug (8vy3) for free.

## Doc freshness

My branch changed backend/services/{form_filling_service,callback_handler}.py +
test files. The freshness checker flagged ~20 tier-2 docs as stale-and-tracking
those files, but as across the whole 13w7 epic, none document the DTI
coercion/injection internals this change touches, so none has prose this change
invalidates -- they are stale from the cumulative epic + secretary commits.
Reviewed and left. Refreshing the SI-shape contract docs (si-reduction.md et al.)
to describe the now-fully-static DTI arm + its injection/coercion channels is a
worthwhile epic-wide docs fast-follow; filed as a follow-up rather than bolted onto
this verification bead. (websocket-routing.md is stale only from an unrelated
websocket_routes touch, not this branch.)

## Beads housekeeping

No orphans I introduced. jnjj.46 + kahz are CLOSED by this PR (the epic's bug
resolution). Stale in_progress beads hrn / jf6w / ue5s are pre-existing,
maintainer-owned, unrelated -- left. jnjj.45 (secretary) shows in_progress but was
merged on its own PRs (#256/#257); its closeout owns it, not this bead -- left.
(Prep's beads check timed out once with a nonsensical negative duration -- a
transient clock glitch as the date rolled to 2026-06-28; re-ran standalone clean.)

## Files touched

- `backend/services/form_filling_service.py` -- restart_gemini_session fires the DTI initiating message; `_current_field_id` tracking (init + merge_field_schema + send_initiating_message); `_coerce_dti_update_to_current_field` + the coercion in handle_update_fields_tool_call; wire get_current_field_id into set_tool_handlers.
- `backend/services/callback_handler.py` -- `_get_current_field_id` getter; confirm_field coercion onto the current field.
- `backend/tests/unit/test_restart_gemini_session.py` -- DTI restart fires/non-DTI doesn't (with isolated Settings).
- `backend/tests/unit/test_dti.py` -- update coercion (hallucinated / valid-but-different / matching / non-DTI / no-current-field / multi-field) + `_current_field_id` set by merge.
- `backend/tests/unit/test_confirm_field_tool.py` -- confirm coercion (coerced / matching / no-current-field).
