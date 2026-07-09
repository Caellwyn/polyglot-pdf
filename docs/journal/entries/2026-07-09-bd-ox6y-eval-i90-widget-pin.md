---
date: 2026-07-09
bead: polyglot-pdf-ox6y
title: "Pin i-90's P2_checkbox3 select-one group in the extraction eval benchmark"
tags: [extraction, harness, testing]
---

## Trigger

Bead 2 of the extractor-grouping fix (after qmxb flipped group-candidates
default-ON + added the completion safety net). The eval_extraction benchmark
had no i-90 entry, so the exact select-one group the fix targets (P2_checkbox3,
the bd 0nxh bug) was unmeasured -- a re-extraction that re-dropped it would not
fail the harness.

## What shipped

- Added an `i-90` entry to `eval_extraction._FORMS` (with its gold schema) pinning
  `widgets = P2_checkbox3[0..4]` -- the 5-widget "Reason for Application (select
  only one)" group. `check_widget_coverage` now asserts, on every i-90 re-extract,
  that all 5 widgets are claimed exactly once and land in ONE field
  (`consolidated`). The check is modeling-agnostic: a DROP or de-identification
  of any of the 5 fails it (RED -- the regression qmxb prevents); a clean split
  into 5 standalone checkboxes still passes but reports `consolidated=False`, so
  the row shows whether the group was recognized as one field.
- Chose P2_checkbox3 (not P2_checkbox2's 12-widget group) as the single pin: the
  harness takes one `widgets` list per form and `consolidated` expects one owner
  field, and P2_checkbox3 IS the specific group this whole arc fixes.
- Tests: `test_i90_pins_the_p2_checkbox3_select_one_group` (the pin + gold scores
  consolidated); updated `test_one_command_emits_the_multi_form_table` for the new
  5-form benchmark (i-90 row present, `PASS (5w, 1 group)` rendered, 5 rows).

## Verification

Gold-row eval (no paid call): `eval_extraction --form i-90` -> `PASS (5w, 1 group)`,
verdict OK. Full backend + tools suite 1750 passed.

Next: bd aw1u -- ONE paid Vertex re-extraction of i-90 with the new default, scored
by this now-i-90-aware harness, to confirm the fix end-to-end on a real AI run.

## Doc freshness

No tier-2 doc tracks scripts/authoring; this entry is the record.
