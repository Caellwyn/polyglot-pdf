# Dependency-inventory bake (bd polyglot-pdf-btbi)

Recorded 2026-08-01. Backend: local `claude` CLI, `claude-opus-4-8`, $0 metered
(Gate-2: no Vertex spend; the only paid step, option-translation, is disabled).
Raw rows: `scripts/spikes/data/dependency_inventory_runs.jsonl`.

## Question

The maintainer's hypothesis (2026-07-26): the extractor's relationship failure
is a SEARCH-COVERAGE problem, not a reasoning problem -- so an intermediate
structured-reasoning step ("isolate which fields are conditional, group them,
build the dependency graph, then fill in each field") should lift recall.

Distinct from the already-falsified sprint-15 A2/A4 arms: those were REFINEMENT
passes (fix relationships AFTER extraction) and lost most of the gain. This is
a DERIVATION scaffold inside the SAME single call (maintainer decision
2026-08-01): the model must emit a `_dependency_inventory` key BEFORE the
fields array, so the inventory conditions the extraction rather than patching
it. The key is popped before scoring and never reaches a kit.

## Ground truth

The hand-verified W-7 (bd fjxe, PR #519: 53 fields, 19 show_if + 13 require_if
= 32 conditionals) PLUS the maintainer's 2026-08-01 `exp_date` fix (local root
at measurement time). This matters: the PREVIOUS W-7 gold documented only 20
conditionals, which inflated every earlier percentage.

**Re-baseline on the corrected gold (shipped pipeline, n=1):** field F1 99.1;
show_if 10/19; require_if 0/13; combined 10/32 = 31.2% presence AND
trigger-correct; spurious 0. Precision-perfect, recall-poor -- exactly the
profile the hypothesis targets.

## Result (n=7 per arm, W-7)

| metric | B0 control | B1 inventory scaffold | delta | permutation p |
|---|---|---|---|---|
| relationships found (of 32) | 15.4 mean (12-18) | **19.4 mean (13-23)** | **+4.0** | **0.040** |
| trigger-correct (of 32) | 15.4 (12-18) | 19.0 (12-22) | +3.6 | 0.071 (undecided) |
| spurious | 2.6 (2-5) | 7.9 (3-14) | +5.3 | 0.007 |

**Recall gain is real** (p=0.040) but modest: roughly +12 percentage points,
NOT the near-doubling the first n=1 pair suggested. That early read was
RETRACTED: the control arm alone swung 12->18 between runs, a spread as large
as the apparent effect. Any future comparison on this metric needs n>=5 per
arm; n=1 is worthless here.

## The spurious increase is mostly OUR schema gap, not hallucination

Adjudicated against the maintainer's field-by-field verdicts (encoded in
`scripts/spikes/adjudicate_w7_relationships.py`), per run:

| bucket | B0 | B1 |
|---|---|---|
| unexpressible (6f/6g exactly-one-of ITIN\|IRSN) | 0.6 | **4.1** |
| genuine extractor defects | 0.0 | 0.6 |
| gold was actually wrong (extractor caught it) | 0.0 | 0.4 |
| unadjudicated | 0.0 | 0.7 |

The scaffold's extra emissions are dominated by the ITIN/IRSN case: the form
DOES state that one of those groups is required, and our schema **cannot
express "exactly one of"** (bd memory `no-exactly-one-of-cross-field-
constraint`). Marking both `require_if` is technically wrong but is a faithful
reading of the printed form, not an invention. Genuine defects run 0.6/run --
the absolute-vs-conditional `required` confusion (bd `opjo`), where the model
downgrades an always-required field to conditionally-required.

The unadjudicated cases are all 1-of-7 flukes (`mailing_city_state_country`,
`date_of_entry_us`, `us_visa_type_number_expiration`) with no stable pattern.

## i-90 no-regression guard (n=2 per arm)

| metric | B0 | B1 |
|---|---|---|
| relationships found (of 19) | **19/19** both runs | **19/19** both runs |
| trigger-correct | 17-18/19 | 17/19 |
| field F1 | 96.7 / 97.1 | **99.2 / 99.2** |
| spurious | 5, 8 | 13+2, 15 |
| inventory entries | - | 21, 23 |

**No recall regression** on the saturated form (19/19 in all four runs), and
field extraction is actually BETTER with the scaffold (99.2 vs 96.7-97.1).
Trigger-correctness is unchanged within the known P5-consolidation artifact
(bd kfni's logged rubric amendment).

The spurious jump (5-8 -> 13-15) is the SAME class as W-7's, not a new defect:
**i-90 gold carries ZERO `require_if` anywhere** (19 show_if, 19
conditional_behavior, 0 require_if), so every conditional-requirement the model
identifies scores spurious BY CONSTRUCTION. The baseline already emits 5-8 of
them; the scaffold finds more of the same category. Spot-check: the most
frequent are `p1_line5a_familyname` / `p1_line5b_givenname` -- the "if you
checked yes, provide your other names" fields, which genuinely ARE required
once shown. NOT adjudicated field-by-field (i-90 has no maintainer verdict set
like W-7's), so this is reported as UNRESOLVED rather than counted either way:
it is plausibly the same gold-under-encoding pattern the maintainer confirmed
on W-7, but that is an inference, not a ruling.

## Why it works (visible in the model's own inventory)

The scaffold's inventory enumerated the printed cross-references the model
previously never surfaced -- the treaty a/f rule, the d/e name-and-SSN rule,
the 6d document block, the 6e yes/no branch -- 11-13 dependencies covering
~21 field rules. It still missed the student/college block, so the search
ceiling is real but much higher than the baseline's.

## Honest caveats

- **No clean held-out form.** W-7 is the tuning target; i-90 is the only other
  hand-verified kit (used as a no-regression guard, not a generalization test);
  f1040 is explicitly NOT trusted ground truth (bd memory
  `w7-f1040-gold-not-hand-verified`). This gain is measured on the form it was
  aimed at.
- **Variance is large** in both arms (~6-10 of 32 spread). Treat any single run
  as uninformative.
- **The scaffold is not shipped** by this bead: it lives in the research harness
  and patches a RESEARCH COPY of the contract. Shipping it is a separate
  decision, and should probably wait on bd `opjo` (teach absolute-vs-conditional
  required) so the shipped version does not carry the 0.6/run defect.

## Recommendation

The hypothesis is CONFIRMED at modest effect size. Ship-worthy, but sequence it
after `opjo`: fixing the absolute-vs-conditional confusion removes the only
genuine defect class the scaffold adds, and the two changes touch the same
contract text. Re-measure both together, n>=5, before grafting.
