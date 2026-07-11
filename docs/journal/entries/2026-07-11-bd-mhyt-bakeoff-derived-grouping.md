---
date: 2026-07-11
bead: polyglot-pdf-mhyt
title: "Bake-off section-grouping scored on derived divisions for section_id-less arms"
sprint: 11
tags: [extractor, testing]
---

## Trigger

bd polyglot-pdf-6cfu.2 fallout: the extractor contract now instructs LLM arms
NOT to emit parts/sections/section_id (divisions are derived deterministically
post-extraction), but scripts/schema_score.py's _section_grouping_agreement
treats a field with no section_id as a singleton -- every LLM-native bake-off
arm silently scored ~0 on section grouping, making the column meaningless.
Picked up as a sprint-11 rider while the epic's C2 bead (p5h2) was
surface-blocked by parallel PRs (#403 + the luju/944q branch).

## What shipped

Option (a) from the bead -- grade grouping on the DERIVED divisions, the same
thing production ships: schema_score.score() gained derive_pdf_path; when the
draft carries NO section_id anywhere, derive_sections.derive_and_apply (the
exact entry point extract_form.py step 3e uses) runs on a DEEP COPY, and the
derived section_ids are then OVERLAID onto the ORIGINAL match's pairs by field
position (_overlay_derived_section_ids) -- deliberately NOT a re-match: the
matcher's Pass-2 fuzzy key bakes in section_id, so re-matching the derived
copy could pair a DIFFERENT field set (outer-review pass-B finding, fixed
before merge; the overlay keeps the pair set identical by construction).
Detection/attrs/relationships still grade the untouched original. Drafts with
their own section_id are unchanged. A derivation failure marks the metric n/a
with a reason (never a silent 0; _attr_avg already drops NaN/inapplicable
entries so the headline mean is not poisoned). run_bakeoff.py passes the
manifest's existing (unused) per-form "pdf" key through and the table/JSON
carry a legend-documented basis marker ("*" derived, "!" derivation-error).
Pinned by tests/test_schema_score_derivation.py (9 unit tests incl. two
overlay-invariant pins, no live model). Smoke: real I-90 fields with
section_id stripped now score a genuine non-zero grouping F1 (63.6-71.7
across probes, canon-detail dependent) instead of ~0.

Implementation delegated to a Sonnet subagent (decision fixed by the
orchestrator); orchestrator-reviewed: verified the derived-branch dict mirrors
score_fields' shape (union-formula applicable, F1-as-pct) and the NaN path.

Review record: fresh-eyes Opus clearing round NO-GAPS (1 dangling docstring
ref, fixed). Opus outer review round 1: pass A NO-GAPS (legend nit, fixed),
pass B NO-GAPS with a medium-confidence interaction finding treated as a
blocker (re-match vs overlay, above) -- fixed + two invariant tests added;
round 2: both independent passes re-cleared NO-GAPS on the final code commit,
pass A verifying end-to-end on the real I-90. Journal-only inaccuracies from
pass B corrected post-clear (docs-only, outside the reviewed code diff).

## Lessons

- When a pipeline moves a responsibility out of a model's output contract
  (sections moved from the LLM to a deterministic post-pass), every EVAL that
  scored the old output shape silently degrades -- sweep the scorers in the
  same change that moves the contract.

## Doc freshness

None to bump: bake-off scoring internals have no tier-2 doc; the sprint-11
docs bead (ft47) owns the continuous-DTI doc sweep and is untouched by this.

## Files touched

- scripts/schema_score.py (derive_divisions_for_grouping + score() basis wiring)
- scripts/bakeoff/run_bakeoff.py (pdf passthrough, basis marker, table legend)
- tests/test_schema_score_derivation.py (new)
- docs/journal/entries/2026-07-11-bd-mhyt-bakeoff-derived-grouping.md (this)
