---
date: 2026-07-09
bead: polyglot-pdf-13vo
title: "Fix i-90 ethnicity options mapped to the opposite printed boxes"
tags: [form-kits, pdf-filling, correctness]
---

## Trigger

Surfaced by the sprint-9 Preview visual-QA pass (bd 95q0): the preview painted
the selection mark for "Not Hispanic or Latino" in the printed "Hispanic or
Latino" box on the rendered i-90 page 3. A data-correctness bug in the shipped
kit, not the painting.

## Root cause (verified against the AcroForm dump)

`form-kits/i-90/schema.json` `p3_ethnicity` mapped the two options to the WRONG
widgets. The dump's /TU tooltips + on-values are authoritative:
- `P3_checkbox6[0]` on=N, /TU "Select **Not** Hispanic or Latino" (lower row, y=115.6)
- `P3_checkbox6[1]` on=H, /TU "Select Hispanic or Latino" (upper row, y=100.6)

The schema had `hispanic_or_latino -> [0]` (the NOT box) and
`not_hispanic_or_latino -> [1]` (the Hispanic box) -- exactly swapped. Since the
authoritative fill (POST /api/fill-pdf) ticks the claimed widget, every filled
i-90 recorded the OPPOSITE ethnicity the user chose. A pre-existing LLM-extraction
authoring error; the per-option pdf_position backfill (bd 5f41) faithfully copied
the wrong widgets' rects, which is how the preview made it visible.

## Fix

Swapped the two options' `pdf_field_name` (and their matching `pdf_position`) in
`form-kits/i-90/schema.json`. Now:
- `hispanic_or_latino -> P3_checkbox6[1]` (on=H)
- `not_hispanic_or_latino -> P3_checkbox6[0]` (on=N)

Verified:
1. A real fill of each option ticks the correct widget (fill debug:
   hispanic -> P3_checkbox6[1]/H, not-hispanic -> P3_checkbox6[0]/N).
2. `backfill_option_positions.py --kit form-kits/i-90 --check` exits 0 (rects
   already follow the corrected names -- the manual position swap matched).
3. i-90 baseline test + full suite (1758) green; still validates v2, fills 100%,
   lint clean.

## Audit of the other option-bearing fields (exit criterion 3)

Ran a label-vs-/TU comparison over all 18 i-90 option-bearing fields (75
option-widget pairs). Only `p3_ethnicity` was actually swapped. Four heuristic
flags total; the other three -- `p1_checkbox4` (Yes/No/NA name-change),
`p7_checkbox7` (attorney / not-attorney), `p7_checkbox7extend` (extends /
does-not-extend, driven by a Yes/No option) -- are FALSE POSITIVES, verified
pair-by-pair against the full /TU tooltips (each option correctly claims its
matching widget). So the swap was isolated to ethnicity.

## The schema-editor "Gold Standard" sample had the same swap (bd eeuh, folded in)

Pre-PR fresh-eyes found the editor's bundled sample
`schema-editor/public/schemas/i-90/i-90_schema.json` -- served live as the "I-90
Gold Standard" via `schemaLoader.AVAILABLE_FORMS` -- carried the IDENTICAL
pre-fix ethnicity swap. That sample is meant to mirror the shipped kit (bd wvgh
refreshed it from canonical), but it had drifted (also missing the per-option
`pdf_position` from bd 5f41). Re-synced it from `form-kits/i-90/schema.json` (now
deep-equal to canonical), fixing the ethnicity swap AND restoring the
sample==canonical invariant so a contractor learning from the Gold Standard sees
correct, current data on every field. Closes bd eeuh.

## Follow-up

Filed bd polyglot-pdf-rqlr: a schema_lint WARNING comparing an option's label
against its claimed widget's /TU to catch this swap CLASS at promotion time. Kept
out of this fix because a naive comparison is noisy (3 of 4 flags here were false
positives needing human judgment) -- the rule needs tuning + WARNING severity.
