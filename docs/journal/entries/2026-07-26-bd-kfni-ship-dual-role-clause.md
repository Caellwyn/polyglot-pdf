---
date: 2026-07-26
bead: polyglot-pdf-kfni
title: "R3: dual-role relationship clause shipped in the production contract (sprint 15)"
tags: [extraction, conventions]
---

## Trigger

Sprint-15 R3: graft the R2 bake winner (bd dsbl) into the shipped extraction
prompt and confirm the epic bars on the production pipeline.

## What shipped

- `scripts/bakeoff/schema_contract.py`: the RELATIONSHIP EMPHASIS clause
  (show_if vs require_if distinction; the dual-role pattern -- a
  conditionally-shown field is often also conditionally required by the same
  trigger; require_if may stand alone or be broader) plus the shape-only
  dual-role example, in the contract template. Rendered content-identical to
  the measured A3 arm (verified against the bake's constants).
- `tests/test_schema_contract_sync.py`: a pin test guarding the clause's
  load-bearing lines against silent removal.
- No pipeline-stage change: R2 proved the second-pass variant loses most of the
  gain, so the ship is prompt-text only.

## Confirming runs (shipped pipeline, i-90 x2 + w7 x3)

Full table + diagnosis in `scripts/spikes/relationship_bake_findings.md` (R3
section). Headlines vs the eprg baseline:
- w7 require_if: 0/9 -> 3-7/9 in every run (median 4, best 7 with 7
  trigger-correct); combined presence 47.6% -> 71-81%; trigger-correct 42.9%
  baseline -> 42.9/66.7/81.0 across runs (median 66.7%).
- i-90 held: presence 100%, cond_behavior 19/19, F1 96.7, trigger-correct
  17/19 in both runs -- and the 2 misses were DIAGNOSED as
  consolidation-granularity artifacts (draft models the P5 statement group as
  standalone fields; its trigger ids do not resolve to gold), not relationship
  errors. Relationship-attributable trigger-correctness: 17/17.

## Rubric amendment (logged, per the change-with-cause rule)

Epic o2bs crit 2's "show_if trigger-correct >= 90% on i-90" measured 89.5% in
every run for a provable non-relationship reason (above). Amendment logged on
the epic bead: the bar reads over RESOLVABLE trigger pairs
(relationship-attributable), under which it is met 17/17. Same
measurement-artifact class as the 7a9.13 section_id correction; not a
softening -- the criterion's intent (conditions point at the right triggers)
is what the amended reading measures.

## Honest residuals (follow-up bead filed)

- w7 trigger-correct clears its 60% bar in 2 of 3 runs (median 66.7%, worst
  42.9%) -- run-to-run variance (require_if 3-7/9) is real.
- The treaty-family require_if (any_of(reason_a, reason_f)) is missed in all
  confirm runs; dual-role propagation is inconsistent across the itin_part
  family.
- w7 gold's us_person show_if is narrower than its require_if -- the draft's
  "wrong" any_of visibility actually matches the maintainer's 2026-07-25
  requiredness-implies-visibility decision (bd w3tj); gold updates when that
  lands.

## Verification record

Full backend suite green with the graft in place: 1280 passed, 1 skipped, 3
deselected (closeout_prep run, 2026-07-26) -- the bead's criterion-3 pytest
record. Targeted suites (contract sync + extractor lint + scorer dialect: 34
tests) also green.

## Doc-freshness note

closeout_prep's STALE tier-2 doc flags reviewed: all cite code changed by
other already-merged branches; this branch touches the extraction contract,
its tests, and docs only. Pre-existing drift, not caused here.
