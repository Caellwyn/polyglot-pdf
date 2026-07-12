---
date: 2026-07-12
bead: polyglot-pdf-h1eo
title: "derive_sections name-convention: a sub-heading governs exactly one USCIS part; i-90 page-7 Part-8 rows no longer inherit the Name heading"
tags: [extractor, authoring, form-kits, testing]
---

## Trigger

A Sprint 10 follow-on bug (filed during the derived-divisions work). On i-90
page 7 the name-convention strategy mislabeled a whole block of fields: the
Part-8 "Additional Information" continuation rows (Page/Part/Item-Number +
Additional-Info, items 3.a-6.d) inherited the "Your Full Name" sub-heading that
governs the Part-1 name-reverification block printed just above them.

## Root cause

`scripts/authoring/derive_sections.py`'s name-convention `field_subhead()`
attached a field to the nearest level-2 sub-heading above it in the same column,
with a barrier that only fires when a level-1 PART heading falls BETWEEN the
sub-heading and the field. On i-90 page 7 the "Part 8" heading is ABOVE "Your
Full Name" (y 53.9 vs 187.4), not between it and the Part-8 rows below (y 336+),
so the barrier never fired and the Part-8 rows -- which have no sub-heading of
their own -- inherited "Your Full Name". The bucket key already separated them
by USCIS part (part 1 vs part 8), so they were a distinct SECTION; only the
LABEL was wrong (two page-7 sections both reading "Your Full Name").

## Fix

A sub-heading governs exactly ONE USCIS part: the part of the TOPMOST field
printed under it (smallest y; deterministic tie-break on x then fid). A later
field that geometrically falls under the same sub-heading but belongs to a
DIFFERENT part is not governed by it -- it falls through to its part-fallback
label ("Part 8. ..."). Implemented as a pre-pass building `subhead_part`
(heading identity -> governing part), gated in a thin `field_subhead(f, part)`
wrapper over the unchanged geometric `nearest_subhead(f)`. Heading identity is
keyed on (page, x, y, text) so two same-text sub-headings on a page stay
distinct.

Result on i-90 page 7: "Your Full Name" now holds only the Part-1 name-
reverification fields (p1_line1[1], p1_line3a..3c[1]); the Part-8 rows merge
into the correct "Part 8. Additional Information" section. Section count 28 ->
27 (the spurious duplicate-label split is gone). No other i-90 section changed.

## Also: regenerated the shipped i-90 kit

Fixing the tool without re-deriving the one affected kit would leave the
mislabel live in production, so the retrofit was re-applied to
`form-kits/i-90/schema.json` (the editor's "Regenerate divisions" workflow) and
its gitignored `frontend/public/form-kits/i-90/` copy refreshed. Divisions-only:
field content byte-identical to origin/dev apart from section_id (0 content
changes across all 132 fields); zero lint errors/warnings; FormSchema clean.

## Verification

- New regression test `test_i90_part8_repeat_rows_not_filed_under_name_subheading`
  in tests/test_extract_form_sections.py pins the fix (p8 rows land under
  "Part 8", the legitimate name rows keep "Your Full Name").
- Determinism (`--check`) byte-identical across two runs on ALL FIVE checked-in
  kits (f1040, i-90, w7, w7-2, w9-heldout) -- exit criterion 2.
- Only i-90 uses the name-convention strategy; the other four are
  printed-heading (untouched code path).
- Full backend suite green (see PR); the unfillable-field baseline is unaffected
  (fillability unchanged, only divisions).

## Files touched

- `scripts/authoring/derive_sections.py` (name-convention sub-heading governance)
- `form-kits/i-90/schema.json` (re-derived divisions; divisions-only)
- `tests/test_extract_form_sections.py` (regression test)
