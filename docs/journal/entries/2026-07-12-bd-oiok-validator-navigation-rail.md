---
date: 2026-07-12
bead: polyglot-pdf-oiok
title: "Validator->switch_to_field correction rail: steer instructs navigate + read-back + fix"
sprint: 11
tags: [doctrine, testing]
---

## Trigger

Sprint-11 epic polyglot-pdf-fc7t child C4, the marquee bead (approved decision
D2). The B5 steer named the conflicting fields and their reason but only said
"name the field(s) and ask the user to verify" -- nothing routed the model to
the flagged field, so a correction meant the model re-asking cold with no
navigation, no UI focus, no read-back. switch_to_field (PR #397) already does
the navigation half and returns the current value in its ack.

## What shipped

_compose_validator_steer (backend/services/form_filling_service.py) now labels
each flagged field with its exact field_id and instructs the rail: handle one
finding at a time -> call switch_to_field with the flagged field_id (its
response includes the current value) -> read the value back with the conflict
in one sentence -> ask which is correct -> on a correction, update and confirm.
The B5 bounds are untouched: the user-override escape hatch sentence is kept
verbatim, max-resteer suppression and fail-open behavior unchanged (all 13
existing steering tests pass unmodified). Prompt-level by design -- the model
stays the actor; nothing client-side auto-navigates on a validation result.
The rail is orthogonal to WHEN steers fire: today form_complete (continuous
mode's only trigger), wt6w's page-end triggers will reuse it unchanged.

Two new unit tests pin the rail text (switch_to_field + exact field_ids +
read-back instruction; one-finding-at-a-time sequencing on multi-conflict
verdicts, single injection).

Live E2E (exit criterion 1): new backend/scripts/probe_validator_rail.py --
deploy-faithful from the seeded state onward (real I-90 schema, REAL Vertex
flash-lite validator verdict on a seeded WV-state/Iowa-ZIP contradiction, REAL
steer composer, live session with the REAL DTI SI + continuous tool set +
adapter live-config, production ack shapes). 4/4 behavioral PASS across two
runs: navigate -> correct read-back voiced -> update_form_fields with the
correction -> confirm_field. One checker false-negative in run 1 (the model
corrected the state to "IA", the standard abbreviation; the assertion matched
only "iowa" -- checker widened, trace preserved in the artifact). ~$0.30 total.
Full method + variance notes: scripts/spikes/validator_rail_findings.md;
artifacts under scripts/spikes/data/validator_rail_*.json.

Experimentation-skill gates honored: prior-work audit found the steer
injection unit-proven (B5) and switch_to_field E2E-proven (jnjj.36) but the
model-ACTS-on-the-rail question unanswered; cost estimated upfront (~$0.25,
under the ask threshold; the run is the bead's approved exit criterion).
Also fixed in passing: the experimentation SKILL.md line calling
probe_secretary_recall.py AI-Studio-keyed (stale since PR #412 -- it is now the
Vertex reference conversion).

## Lessons

- A live-model checker must accept every correct SPELLING of the expected
  outcome (state abbreviation vs full name) -- assert on semantics, not one
  surface string, or a behavioral pass reads as a failure.
- The steer should carry exact field_ids, not just names: the tool prefers ids,
  and names alone force a spoken-name resolution round-trip.

## Doc freshness

.claude/skills/experimentation/SKILL.md: the stale probe-client note updated
(reference conversion, sweep bead rve5). No tier-2 docs bumped: the validator
component behavior docs are C8's (ft47) sweep; validation-delegation.md's
contract 3 (steer = in-band instruction naming fields + reasons) is unchanged
in shape by this steer-text extension.

## Files touched

- backend/services/form_filling_service.py (_compose_validator_steer)
- backend/tests/unit/test_validator_steering.py (2 rail tests)
- backend/scripts/probe_validator_rail.py (new)
- scripts/spikes/validator_rail_findings.md (new) + data artifacts
- .claude/skills/experimentation/SKILL.md (stale line)
- docs/journal/entries/2026-07-12-bd-oiok-validator-navigation-rail.md (this)
