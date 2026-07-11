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
exact entry point extract_form.py step 3e uses) runs on a DEEP COPY and the
grouping metric re-matches against that copy. Detection/attrs/relationships
still grade the untouched original. Drafts with their own section_id are
unchanged. A derivation failure marks the metric n/a with a reason (never a
silent 0; _attr_avg already drops NaN/inapplicable entries so the headline
mean is not poisoned). run_bakeoff.py passes the manifest's existing (unused)
per-form "pdf" key through and the table/JSON carry a basis marker
("*" derived, "!" derivation-error). Pinned by
tests/test_schema_score_derivation.py (7 unit tests, no live model). Smoke:
real I-90 fields with section_id stripped now score 63.6 F1 grouping instead
of ~0.

Implementation delegated to a Sonnet subagent (decision fixed by the
orchestrator); orchestrator-reviewed: verified the derived-branch dict mirrors
score_fields' shape (union-formula applicable, F1-as-pct) and the NaN path.

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
