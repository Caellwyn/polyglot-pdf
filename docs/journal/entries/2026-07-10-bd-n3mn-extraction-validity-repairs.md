---
date: 2026-07-10
bead: polyglot-pdf-n3mn
title: "Repair the strict-model validity artifacts fresh extraction drafts carry"
tags: [hotfix, testing]
---

## Trigger

The 6s71 paid verification (same day) landed all three fresh drafts lint
clean, but two printed extract-time [INVALID] against strict
FormSchema.model_validate: i-90 with 5 invented `overflow_to_supplement`
enum values + a contract-shaped supplements entry, f1040 with 37
lone-option checkboxes (v2 forbids options on a `checkbox` at all -- the
"missing label" errors were the shallower symptom). Filed as n3mn from
that run; the maintainer green-lit continuing on the surfaced issues.

## What shipped

- Root-cause find: the CONTRACT itself taught `supplements: [{id, label}]`
  while FormSupplement requires {id, name, purpose, fields} -- the LLM
  followed the contract faithfully and the model rejected the draft. The
  contract now teaches the full required shape; repair completes an
  incomplete entry (name <- label, purpose <- name, fields <- []) as the
  net for older drafts.
- Invented overflow_to_supplement strings alias to the enum's single
  member 'supplement_a' (same intent, invented name -- i-90's supplement
  IS its "Additional Information" part); non-strings drop. Both logged.
- New checkbox shape normalization, run FIRST (migrate Pass 1 parity): a
  single-option checkbox unwraps to the standalone boolean (pdf_field_name
  lifted, options dropped) with native `equals <old value>` conditions
  retargeted to is_checked (Pass 2 parity; only equals -- migrate leaves
  not_equals for human review and repair matches); a multi-option checkbox
  retypes to checkbox_group. The unwrap now FEEDS the controls_fields
  mirroring's standalone map, replacing the read-only scan c3y6 added.
- Deliberate behavior change, noted: is_selected/contains on a v1
  checkbox-with-options trigger now aliases to the group-canonical
  `includes` (previously `equals`, picked because the v1 type -- itself
  model-invalid -- was left in place). Three existing tests updated to the
  new expectations with comments explaining the shift.
- Option-label synthesis for group options missing the required label:
  dump /TU tooltip -> field's own name for a lone option -> humanized
  value slug -> "Option N".
- Replayed all three saved 6s71 drafts through the new repair (in-session
  scratch copies -- the drafts are transient artifacts, not committed, so
  this replay is recorded here rather than reproducible from the repo; the
  committed tests carry synthetic fixtures of the same shapes): every one
  passes FormSchema.model_validate with lint clean (i-90: 2 aliases + 1
  supplement completion; f1040: 37 unwraps; w7: untouched).
- 9 new tests (39 total in test_schema_repair.py); migrate 21/21 and
  contract-sync 12/12 unchanged/green.
- Fresh-eyes triage: (filled at closeout -- see below)

## Lessons

- When an LLM emits an "invalid" shape, check whether the prompt TAUGHT it
  that shape before blaming hallucination: the supplements failure was the
  contract's own drift from the model. Contract/model sync guards existed
  for operators but not for the top-level shape prose.

## Doc freshness

- No component doc tracks repair internals; nothing to bump. Pre-existing
  stale standards docs (tracking files this branch did not touch) reviewed
  and left per the "already stale before you" rule.

## Files touched

- backend/services/schema_repair.py
- scripts/bakeoff/schema_contract.py
- tests/test_schema_repair.py
- docs/journal/entries/2026-07-10-bd-n3mn-extraction-validity-repairs.md
