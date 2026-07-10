---
date: 2026-07-10
bead: polyglot-pdf-6s71
title: "Paid verification: fresh i-90/w7/f1040 extractions land 0 legacy-trigger-side-logic errors"
tags: [harness, testing]
---

## Trigger

The remaining exit criterion of bd polyglot-pdf-6s71 after the c3y6 split
(implementation shipped in PR #387): prove on a REAL paid run that a fresh
extraction with the new default (the c3y6 contract prohibition + repair
mirroring) produces 0 legacy-trigger-side-logic lint errors. The maintainer
sanctioned the paid run on the morning of 2026-07-10.

## What was run

Three `extract_form.py` passes (i-90, w7, f1040) via Vertex `gemini-2.5-pro`
(ADC, project polyglot-demo-aa709), run from the c3y6 branch (the code the
maintainer merged as PR #387 the same morning), each scored by
`eval_extraction.py` against its gold pair.

## Result -- criterion met, and the fix worked at the SOURCE

| form  | verdict | lint E/W | choice% | text% | fieldF1 | structural |
|-------|---------|----------|---------|-------|---------|------------|
| i-90  | OK      | 0/0      | 100     | 100   | 99.6    | PASS (5w, 1 group) |
| w7    | OK      | 0/0      | 100     | 100   | 93.9    | PASS (8w, 1 group) |
| f1040 | OK      | 0/0      | 100     | 100   | 93.0    | -          |

- **Zero controls_fields emitted in any draft** (grep + per-field scan): the
  contract prohibition alone stopped the emission -- the repair-side
  mirroring safety net did not need to fire. Conditionality arrived
  target-side (17 / 17 / 6 show_if fields). Same pattern as the aw1u
  grouping fix: the prompt solves it, the deterministic net is the backstop.
- i-90 flipped RED (aw1u baseline: lint 12/0 from controls_fields on 12
  fields) -> OK, with field-F1 up 98.5 -> 99.6 and the P2_checkbox3 group
  still fully consolidated.

## What the paid run ALSO surfaced (out of scope -> filed)

Two drafts printed extract-time [INVALID] against strict
FormSchema.model_validate (independent of conditional logic; eval verdicts
still OK): i-90 -- 5 errors, `overflow_to_supplement:
'additional_information'` where the enum allows only 'supplement_a'; f1040 --
37 errors, checkbox option dicts missing the required `label` key. w7
validated clean. Filed as **bd polyglot-pdf-n3mn**.

## Doc freshness

- Verification-only run; no code changed, no component doc tracks it.

## Files touched

- docs/journal/entries/2026-07-10-bd-6s71-paid-verification.md (this record)
- (extraction drafts were transient scratch artifacts, not committed)
