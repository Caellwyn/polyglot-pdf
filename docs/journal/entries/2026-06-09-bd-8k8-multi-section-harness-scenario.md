---
date: 2026-06-09
bead: polyglot-pdf-8k8
title: "WS-A: Demo-readiness harness + multi-section voice scenario (foundational)"
tags: [testing, harness]
---

## Trigger

The foundational bead (WS-A) of the voice round-trip hardening epic
(`polyglot-pdf-wpw`), per the finalized plan
(`please-check-out-the-serene-church.md`). The voice harness (`g8w`) proved a
single field round-trips, but the demo the epic is judged by is a multi-field,
multi-section voice session crossing at least one section boundary. WS-A builds
that scenario -- the demo rehearsal every later workstream verifies against --
and the deterministic specs that guard the contracts it depends on.

## What shipped

**The multi-section browser scenario** (`tests/e2e/voice-harness/harness.js`).
`runMultiSectionScenario` drives the real demo path: it seeds the non-target
section-1 fields confirmed, voice-fills + confirms the one numeric field
(`p1_line1_aliennumber`), and -- because that is now the last unconfirmed visible
field -- the frontend's REAL auto-advance fires and crosses into section 2, where
a second numeric field (`p1_line6f_zipcode`) is voice-filled. New helpers:
`seedFields`, `getCurrentSection`, `getCompletedSections`, `waitForSection`,
`waitForSectionGreeting`. `runCycle`'s confirm step is now ORDER-TOLERANT
(accepts an already-true `ssConfirmed` before the "yes" injection -- the 2.5
proactive-confirm finding, `par`/`tfz`), and advance is opt-out
(`requireAdvance`) for the last field before a boundary.

**The seed mechanism** (`frontend/src/shared/connection.ts`).
`__VFF_TEST_INJECT.seedFieldConfirmed` routes through the SAME
`SchemaFormStateManager.updateField({confirmed:true})` path a genuine confirm
uses, so seeded fields are indistinguishable from real confirms to
`readField`/`computeNextField`. A key schema discovery made this cheap: the three
`p1_line5*` name fields are `show_if`-gated on `p1_checkbox4 == "P1_checkbox4[0]"`,
so seeding `checkbox4` to a different option hides them -- the section-1
confirm-set shrinks to 5 seeds + 1 voice field, not the 9 the naive read implied.

**Deterministic specs.** `backend/tests/contract/test_tool_contracts.py` (was an
empty uov.14 stub) now holds an `@pytest.mark.external` SEQUENCE regression that
asserts the model emits `update_form_fields` THEN `confirm_field` in order --
the contract the probes only tallied. It A/Bs 2.5 (gate) vs 3.1 (xfail, known
tool-call skip). `test_activity_signal_delegation.py` gains a static guard that
the section-switch route<->service surface (`switch_to_section`,
`manual_section_switch`, `section_info_response`) stays wired -- the akn-class
bug for switching. New fixture `digits_12345.wav` (5-digit section-2 ZIP).

**Live verification (Chrome MCP, real Gemini 2.5).** Two valid runs, identical
pattern: seed PASS (5 fields, 0 failures), voice fill PASS (`1234567` in ~1.5-2.4s),
confirm FLAKY. The external sequence regression PASSED live (2.5 in-order; 3.1
xfail). The confirm flakiness is the known WS-E reliability defect (`wpw.2`):
2.5 native-audio fills but does not reliably call `confirm_field` after "yes".
The gate is working as designed -- it surfaces this as FLAKY rather than
false-passing, so a clean multi-section green is GATED on `wpw.2`. (A backend
120s `websocket_idle_timeout` invalidated a third run when manual-poll pacing
exceeded it; documented in the RUNBOOK and bead for future live runs.)

**Scope decision (recorded on the bead):** the y4a AI-initiated-switch red gate
is NOT bundled into the deterministic browser scenario -- its path is
non-deterministic AND depends on the unfixed `0c1`, so a flaky-by-design leg
would muddy the green/red demo readout. The RUNBOOK documents that known-red
path with a `bd 0c1` pointer; the external sequence regression is the
model-behavior net.

Fresh-eyes triage: recorded in the merge ping (this entry predates the review
rounds; the PR body is not re-edited after review per closeout doctrine).

## Lessons

- **Read the schema's conditional-display rules before assuming a section's
  field count.** The "crossing section 1 needs 9 confirms" premise was wrong --
  `show_if` gating cut it to 6 visible, 1 of them the voice target. A Plan agent
  caught this; it turned an awkward "seed 7 free-text fields" design into a clean
  5-seed one.
- **A test gate's job is to surface the defect, not to be green.** The
  multi-section scenario is FLAKY today because confirm reliability is unsolved
  (WS-E). That is the correct, honest signal -- the value is that it classifies
  the real failure precisely (fill PASS, confirm FLAKY) instead of a false PASS.
- **Mind the backend idle timeout when hand-driving a live harness.** 120s of
  socket silence closes the session; slow manual polling between turns can blow
  past it and invalidate a run that the code would otherwise have driven fine.

## Doc freshness

`check_doc_freshness.py` reported all tracked docs fresh. The voice-harness
RUNBOOK (not a tracked tier-2 doc -- it lives under `tests/`) was updated in this
PR to document the multi-section scenario and the known-red AI-switch path. No
CLAUDE.md or tier-2 component/standards docs track these surfaces, so none were
bumped.

## Files touched

- `tests/e2e/voice-harness/harness.js` -- multi-section scenario + helpers,
  order-tolerant confirm.
- `frontend/src/shared/connection.ts` -- `seedFieldConfirmed` inject hook + type.
- `tests/e2e/voice-harness/gen_fixtures.py` -- new `digits_12345.wav` utterance.
- `frontend/public/test-fixtures/digits_12345.wav` -- new fixture (committed).
- `backend/tests/contract/test_tool_contracts.py` -- external sequence regression
  (filled the uov.14 stub).
- `backend/tests/unit/test_activity_signal_delegation.py` -- section-switch
  surface guard.
- `tests/e2e/voice-harness/RUNBOOK.md` -- multi-section step + known-red path.
