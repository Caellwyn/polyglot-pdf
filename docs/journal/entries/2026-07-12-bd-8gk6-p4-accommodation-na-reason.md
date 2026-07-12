---
date: 2026-07-12
bead: polyglot-pdf-8gk6
title: "g1b answer key: correct the p4 accommodation NA_REASON text (checkboxes are shown-but-unchecked, only the detail textareas are hidden)"
tags: [testing, form-kits]
---

## Trigger

A verification bead filed while independently reviewing the p5 fix (bd
polyglot-pdf-b7ln). The g1b answer-key persona's NA_REASON entries for the
Part-4 accommodation fields claimed they were hidden because "p4_checkbox1 =
No" -- but the schema's own show_if logic says otherwise.

## What the schema actually does (verified against i-90/schema.json + the
frontend evaluator)

- `p4_checkbox1[1]` is the accommodation radio; the persona answers `select_no`.
- `p4_checkbox1a/1b/1c` (the accommodation-TYPE checkboxes) have
  `show_if: {field: p4_checkbox1[1], operator: is_not_empty}`. The frontend
  `is_not_empty` evaluator (validation.ts) returns TRUE for any non-empty
  string, and `"select_no"` is non-empty -- so these checkboxes are SHOWN
  whenever the radio was answered AT ALL (Yes or No). They are NA only because
  the persona leaves them unchecked (requests no accommodation), i.e. NA as a
  VALUE, not because they are hidden.
- `p4_line1a/1b/1c_accomodationrequested` (the detail textareas) have
  `show_if: {field: p4_checkbox1a, operator: is_checked}`. Since the checkbox
  above is unchecked, `is_checked` is false -> these ARE hidden -> NA because
  the gate is unsatisfied.

So the old "gate p4_checkbox1 = No -> hidden" reasoning was wrong for all six
fields: the three checkboxes are shown (not hidden), and the three textareas
are hidden by a DIFFERENT gate (their own checkbox being unchecked, not the
radio being No).

## Fix

Documentation-of-reasoning only -- no field VALUE changed (all six stay None;
`validate_answer_key()` still reports "132 fields = 73 filled + 59 NA"). Updated
the three surfaces that carried the wrong reasoning:

- the persona prose comment (the Part-4 bullet),
- the inline `# NA` comments on the ANSWER_KEY entries,
- the `NA_REASON` strings (checkboxes: "shown ... but persona requests no
  accommodation -> unchecked"; textareas: "hidden: gate p4_checkbox1a is_checked
  unsatisfied").

This mirrors the persona-grounds correction the p5 fields already got under bd
polyglot-pdf-b7ln.

## Verification

- `validate_answer_key()` VALID (every None still has an NA_REASON; the diff
  changed no value -- ANSWER_KEY value-diff old-vs-dev is empty).
- `test_g1b_answer_key_coherence.py` green (15 passed) -- it asserts
  `na_fields == set(NA_REASON)` structurally, unaffected by the text.
- ASCII-only.

## Files touched

- `backend/scripts/g1b_answer_key.py` (NA_REASON text + comments; no value change)
