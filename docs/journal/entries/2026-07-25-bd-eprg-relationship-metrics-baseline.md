---
date: 2026-07-25
bead: polyglot-pdf-eprg
title: "R1: relationship metrics + trigger-side harvest accounting + baseline (sprint 15)"
tags: [extraction, testing]
---

## Trigger

First bead of the sprint-15 relationship-extraction epic (`polyglot-pdf-o2bs`):
build the measuring stick, record the true baseline, finalize the rubric bars.

## What shipped

- **`scripts/schema_score.py`**: (1) trigger-side residue accounting -- legacy
  `controls_fields`/`conditional_fields` edges still present in a scored draft
  are counted per action kind, split mirrorable vs unconvertible, with the
  action vocabulary test-pinned against
  `backend/services/controls_fields_mirror.py` (the scorer stays standalone;
  the pin forces it to follow if R4 moves an action between sets); (2) a
  **trigger-correctness** dimension on the condition-shaped keys
  (`show_if`/`require_if`): a recovered condition only counts correct when its
  extractor-invented trigger id resolves, via the field match, to the gold
  condition's trigger set. Presence is not correctness.
- **`scripts/authoring/eval_extraction.py`**: `sh/rq%` + `logic%` relationship
  columns in the one-command table; mirrored/unconverted harvest counts read
  from the repair report (`[ts Nm/Mu]` on the repair cell); combined summaries
  (incl. trigger-correct) in the JSON rows.
- Tests: 31 in `tests/test_schema_score_v2_dialect.py` +
  `tests/test_eval_extraction.py` (vocabulary sync pin, residue counting,
  correctness resolution incl. combinator trees, harvest bucketing, table
  rendering).

## Baseline (full numbers: docs/research/2026-07-25-eprg-relationship-baseline.md)

Fresh n=1 extractions, shipped pipeline, claude-opus-4-8: i-90 (tune) fieldF1
99.2, show_if 19/19 present / 17/19 trigger-correct, conditional_behavior
19/19; w7 (test) fieldF1 92.0, show_if 10/12, **require_if 0/9** -- combined
sh/rq 47.6% present, 42.9% trigger-correct. Residue 0 both. (n=1 per form;
historical run-to-run variance ~+-1 item -- an R3 bar met/missed within 1 item
warrants an n=2 re-run.)

**The headline finding: the stale June numbers (45-55% show_if, 0% logic) no
longer describe i-90** -- presence there is saturated (verified not few-shot
leakage; the exemplar is generic hand-authored vocabulary). The epic's real
gaps are cross-format generalization (w7's require_if collapse) and trigger
correctness. Bars re-anchored accordingly and logged on the epic bead
(strengthened, nothing softened): i-90 becomes no-regression + trigger-correct
>= 90%; w7 headline sh/rq presence >= 70% / trigger-correct >= 60% /
require_if > 0; F1 floors 96 (i-90) / 90 (w7).

## Notes

- Baseline runs stalled once on an expired local claude-CLI login (the
  extractor's default engine); maintainer re-authed mid-bead.
- The kit-bake option-translation step fail-opened during the eval extractions
  (no Vertex ADC in the eval env) -- irrelevant to relationship scoring, noted
  for anyone reading the eval logs.
- R2 (research bake) iterates on i-90 ONLY against these metrics; w7 is scored
  for reporting, never tuned against.
- closeout_prep's STALE tier-2 doc flags reviewed: all cite code files changed
  by other already-merged branches; this branch touches only eval/scoring
  scripts, their tests, and docs -- pre-existing drift, not caused here.
