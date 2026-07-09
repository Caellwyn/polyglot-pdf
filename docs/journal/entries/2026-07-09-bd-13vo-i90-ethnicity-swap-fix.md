---
date: 2026-07-09
bead: polyglot-pdf-13vo
title: "Fix the swapped i-90 ethnicity checkbox mapping"
sprint: 9
tags: [hotfix, testing]
---

## Trigger

Found by the sprint-9 epic verification pass (bd 95q0): the new Preview
visual QA painted the "Not Hispanic or Latino" selection mark inside the
printed "Hispanic or Latino" box. The kit data was wrong, not the painting:
`form-kits/i-90/schema.json` mapped each ethnicity option to the OTHER
option's widget, so the authoritative fill (`POST /api/fill-pdf`) has been
ticking the opposite box on every downloaded/printed I-90 since the kit was
authored (LLM extraction error). P1 because it silently records wrong data
on a legal form.

## What shipped

- Swapped the two options' `pdf_field_name` (`hispanic_or_latino` ->
  `P3_checkbox6[1]`, `not_hispanic_or_latino` -> `P3_checkbox6[0]`), dropped
  their `pdf_position` (and the field-level rect, which follows option 1)
  and re-derived all three with `backfill_option_positions.py`; a second
  `--check` run exits 0. The dump's own /TU tooltips are the ground truth:
  `[0]` = "Select Not Hispanic or Latino" (on_value `N`), `[1]` = "Select
  Hispanic or Latino" (on_value `H`).
- End-to-end verification against the real backend (TestClient +
  local-stack HTTP): filling `hispanic_or_latino` sets AS `/H` on
  `P3_checkbox6[1]` and `/Off` on `[0]`; filling `not_hispanic_or_latino`
  sets `/N` on `[0]` and `/Off` on `[1]`; rendered page-3 crops show the X
  in the matching printed box BOTH ways. A headless-browser probe confirmed
  the Preview mark now paints in the "Not Hispanic or Latino" row (top
  187.24px = y 115.58 x scale 1.62).
- Audit (bead exit criterion 3): every option of all 19 option-bearing
  i-90 fields compared label-by-label against its claimed widget's dump
  tooltip. Ethnicity was the ONLY mis-pair. Three ambiguous rows were
  chased to full text: the two 14th-birthday reasons pair correctly
  (AFTER -> 2.G.1, BEFORE -> 2.G.2) and both abandonment/removal "Select
  Yes" options map to widgets whose tooltips carry "Select Yes".
- Full backend suite green (1758 passed).

## Lessons

- **The dump /TU tooltip is a per-widget ground truth the extractor never
  used for VERIFICATION.** Deterministic name/rect copying faithfully
  propagates a wrong claim; comparing option labels against the claimed
  widget's tooltip is a cheap authoring-time lint that would have caught
  this at extraction. (Candidate schema_lint rule -- noted in bd 13vo's
  description; not implemented here.)
- Widget order is not label order: `P3_checkbox6[0]` is the SECOND printed
  row. Index-based intuition about AcroForm kids is exactly how this class
  of bug gets authored.

## Doc freshness

- No component doc tracks `form-kits/*` data; nothing to bump. Docs flagged
  by the freshness gate track files this branch did not touch.

## Files touched

- form-kits/i-90/schema.json -- p3_ethnicity option pdf_field_name swap +
  rect re-derivation
- docs/journal/entries/2026-07-09-bd-13vo-i90-ethnicity-swap-fix.md
