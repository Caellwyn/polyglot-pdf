---
date: 2026-08-01
bead: polyglot-pdf-btbi
title: "Dependency-inventory scaffold: recall +4.0 at p=0.040 on the corrected W-7"
tags: [extraction, experimentation]
---

## Trigger

Two things unblocked this: the maintainer hand-verified the W-7 gold (bd fjxe,
PR #519) after disclosing that neither W-7 nor f1040 had ever been fully
hand-tuned, and he proposed a specific fix direction -- an intermediate
structured-reasoning step ("isolate which fields are conditional, group them,
build a dependency graph, then fill in each field"), reasoning that
world-class models should manage a 2-page form's dependencies.

## The re-baseline came first, and it moved the goalposts

Against the CORRECTED gold (32 real conditionals, vs the old gold's 20), the
shipped pipeline scores: field F1 99.1, show_if 10/19, **require_if 0/13**,
combined 31.2% -- not the 47.6% we had been quoting. The old number was
inflated by a gold that documented only two thirds of the form's logic. The
true profile is PRECISION-PERFECT / RECALL-POOR: every rule the model finds is
correctly triggered and it invents nothing; it simply looks for a third of what
exists. That is a search-coverage failure -- exactly what the maintainer's
scaffold targets.

## What shipped (research only)

- `scripts/spikes/dependency_inventory_bake.py` -- the bake. The scaffold is a
  DERIVATION step inside the single extraction call (maintainer decision): the
  model must emit `_dependency_inventory` (every printed conditional sentence,
  with trigger/affected/effect) BEFORE the fields array, then reflect each
  entry in the fields it emits. Contract patched on a RESEARCH COPY only; the
  inventory key is popped before scoring and never reaches a kit. The harness
  also scores the inventory itself, separating "did it LOOK for more" from
  "did it write them down".
- `scripts/spikes/adjudicate_w7_relationships.py` -- the maintainer's
  field-by-field verdicts on W-7 spurious `require_if`, encoded so every run is
  scored the same way instead of re-litigated in prose.
- `scripts/spikes/analyze_dependency_inventory.py` -- per-arm distribution +
  permutation test (no scipy, no normality assumption).

## Result

n=7 per arm on W-7: recall **+4.0 of 32, p=0.040** (15.4 -> 19.4); spurious
+5.3, p=0.007; trigger-correctness +3.6, p=0.071 (undecided). Adjudicated, the
extra spurious is dominated by the ITIN/IRSN "exactly one of" case our schema
cannot express (4.1/run) plus real gold gaps (0.4/run); genuine defects are
0.6/run (the absolute-vs-conditional `required` confusion, bd `opjo`).

## Process lesson (recorded because it nearly shipped a wrong claim)

Round 1 was n=1 per arm and read as a near-doubling (37.5% -> 65.6%). I
reported that to the maintainer before confirming it. The n=2 round did not
reproduce it -- the CONTROL alone swung 12->18 of 32, a spread as large as the
apparent effect -- and I retracted the claim. At n=7 the real effect is a
third of what the first pair suggested. **On this metric, single runs are
worthless; n>=5 per arm is the floor.** The permutation-test script now makes
that verdict mechanical rather than a judgment call about numbers.

## Maintainer findings folded in

Adjudicating the "spurious" surfaced two modeling issues the maintainer
confirmed (both now beads + memories):
- `required` is TWO concepts sharing one word -- absolute
  (`validation.required`) vs conditional (`require_if`) -- and the editor's
  checkbox does not disambiguate them (bd `xx1t`). The extractor downgrades
  absolute to conditional (bd `opjo`).
- The schema cannot express "exactly one of these groups is required" (W-7
  lines 6f/6g). Marking both would wrongly force a user to fill both; the
  guidance belongs in help.instructions with the completion validator as the
  backstop.

Also: the extractor caught a genuine gold error (W-7 `exp_date` was not marked
required); the maintainer fixed it.

## i-90 no-regression guard

n=2 per arm: recall 19/19 in ALL four runs (no regression on the saturated
form), field F1 actually better with the scaffold (99.2 vs 96.7-97.1),
trigger-correctness unchanged. Spurious rises 5-8 -> 13-15, but i-90 gold
carries ZERO require_if anywhere, so every conditional requirement the model
finds scores spurious by construction -- the baseline already emits 5-8. Left
UNRESOLVED (no maintainer verdict set exists for i-90); plausibly the same
gold-under-encoding pattern confirmed on W-7, but that is an inference.

## Test-gate note (NOT caused by this branch)

closeout_prep's test gate fails on FIVE tests that also fail on clean
origin/dev (verified by checking dev out and running them): they pin the OLD
W-7 schema and broke when the hand-verified gold landed in PR #519 -- e.g.
test_scored_draft_carries_relationship_summaries hardcodes the old 21-total
(12 show_if + 9 require_if) where the real total is now 32. Filed as bd
polyglot-pdf-lzyi (P1); it blocks the test gate for every branch until fixed.
This research diff touches only scripts/spikes/ + this entry.

## Recommendation

Confirmed at modest effect size. Ship it AFTER `opjo` -- fixing the
absolute-vs-conditional confusion removes the only genuine defect class the
scaffold adds, and both changes touch the same contract text, so they should be
measured together (n>=5) before grafting. Note there is no clean held-out form
right now (W-7 is the tuning target, i-90 the no-regression guard, f1040
untrusted), so the gain is measured on the form it was aimed at.
