# Relationship-extraction bake (bd polyglot-pdf-dsbl, sprint 15 R2)

Status: IN PROGRESS. Method + Gate-1 audit + Gate-2 estimate recorded before
any live run; measured numbers appended per arm as runs complete.

## Question

Which prompt/pipeline change most lifts relationship recall + trigger-
correctness on the auto-pass, tuned on I-90 ONLY, generalizing to W-7 (the
differently-formatted test form, never tuned against)? Baseline (bd eprg,
2026-07-25): I-90 saturated (show_if 19/19, cond_behavior 19/19, 17/19
trigger-correct); W-7 the real gap -- combined show_if+require_if 47.6%
present / 42.9% trigger-correct, **require_if 0/9**.

## Gate 1 -- prior-work audit (done 2026-07-25)

Full audit delegated; key conclusions and why they don't already answer this:

- **No prior "enriched/second-pass" arm ever beat plain claude-hybrid on
  conditional recall** (7a9.12: plain b.cond 45.0 vs enriched 31.9 on I-90;
  7a9.11 I-589 enriched ~0 vs plain 41.5, confounded by consolidation). BUT
  every prior second-pass BUNDLED field extraction -- a **relationship-ONLY**
  second pass (no field-list re-emission) is genuinely unmeasured.
- **Per-signal enrichment ablation (7a9.10) found NO signal reliably helped
  conditionals; row_cluster HURT** (dropped, already off). So more (a)
  structure is not the lever -- a (b)-targeted change is.
- **Trigger-side `controls_fields` is a REMOVED v1 key** (v2 flip, bd h76m.16 /
  c3y6); the contract forbids emitting it and the model already emits target-
  side directly (baseline residue 0). So arm (b) "elicit trigger-side then
  mirror" is re-scoped: it can only be an INTERNAL reasoning step, and whether
  it beats direct target-side elicitation is unmeasured.
- **Few-shot from I-90's OWN gold is barred** (training on the tune set); the
  harness enforces cross-form few-shot for exactly this reason. A generic
  hand-authored relationship exemplar already ships
  (`scripts/authoring/fewshot/v2_new_vocabulary_exemplar.json`).
- **The June "conditional_logic/behavior 0%" verdict is STALE** (pre-SDK-2.8-
  cutover 2026-06-11, pre-v2-flip): the current v2 pipeline already recovers
  cond_behavior 19/19 on I-90. Not the gap.
- All 7a9.5/.9/.7 numbers are pre-cutover -> stale hypotheses, superseded by
  the eprg baseline. Anchor to eprg + July v2 beads only.

**Root-cause diagnosis of the W-7 require_if 0/9** (probed the saved baseline
draft against gold, 2026-07-25):
- **Dual-role omission (the dominant mode).** W-7 gold gives several fields
  BOTH show_if AND require_if with the SAME condition (relationship_d,
  itin_part1/2/3: "when reason D checked / previously-received-ITIN = yes,
  this field both appears AND is required"). The extractor recovered show_if
  and OMITTED the parallel require_if -- it doesn't know that a conditionally-
  shown field on this form is often also conditionally required.
- **Genuinely missed (the rest).** us_person_name / treaty_country /
  treaty_article carry require_if with a broader (any_of) condition the model
  never produced; reason_h didn't match a draft field at all.

The contract (`scripts/bakeoff/schema_contract.py:257-299`) defines show_if
and require_if separately but NEVER states the dual-role pattern or how to tell
"must-fill" from "may-appear." That gap is the arm-1 hypothesis.

## Arms (tuned on I-90; W-7 scored, never iterated against)

Backend: local `claude` CLI, `claude-opus-4-8` (the shipped default; free
in-env). Each arm = a prompt/pipeline variant vs the shipped plain baseline.

- **A0 -- baseline reprint.** Shipped plain prompt. Re-run for a clean same-
  session control (the eprg baseline is the reference; A0 confirms no drift).
- **A1 -- contract dual-role clause.** Add an explicit require_if-vs-show_if
  clause to SCHEMA_CONTRACT: define conditional REQUIREDNESS distinct from
  conditional VISIBILITY, and state that a conditionally-shown field is often
  also conditionally required by the SAME trigger -- emit both when the printed
  instruction says the field must be completed. Pure prompt text; cheapest arm.
- **A2 -- relationship-only second pass.** After the main extraction, a SECOND
  claude call sees ONLY {field list with ids + printed conditional text +
  the current draft's relationship keys} and is asked to add/correct
  show_if/require_if/behavior WITHOUT touching field identity. The unmeasured
  "relationship-only" second pass; more expensive (2 calls/form).
- **A3 -- generic relationship few-shot.** Extend the shipped hand-authored
  exemplar with a generic dual-role example (a show_if+require_if-same-trigger
  field) -- cross-form-safe (not I-90/W-7 content). Prompt text only.

Prune after round 1: drop any arm that regresses I-90 or doesn't move W-7.

## Gate 2 -- cost estimate

Backend is the local Claude CLI under the maintainer's subscription -- **$0
metered Vertex/API cost** for the extraction calls (the CLI's cost fields are
in-env accounting artifacts, not real spend; bd 7a9.9). The only paid
dependency in the pipeline is the option-translation bake (gemini-2.5-pro),
which is IRRELEVANT to relationship scoring and fail-opens with no Vertex ADC
-- so the bake can run it disabled / ignore its failure (as the eprg baseline
did). No pilot needed: the eprg baseline already ground-truthed the per-form
extraction (i-90 ~2-3 min, w7 ~1-2 min, single call, no metered tokens).

Call budget: 4 arms x 2 forms x (1 or 2 calls) x 1-2 repeats <= ~40 CLI calls,
all free-in-env. **No paid go-ahead required** (no Vertex spend). If any arm is
later moved to a paid Gemini backend for comparison, THAT is a separate per-
instance ask.

## Results

Two rounds, `claude-opus-4-8`, local CLI (free in-env). Raw rows:
`scripts/spikes/data/relationship_bake_runs.jsonl`. Numbers are recovered/total.

### Round 1 (all 4 arms x 2 forms, n=1)

| arm | i-90 show_if (tc) | i-90 cond_beh | w7 show_if (tc) | **w7 require_if (tc)** | w7 F1 |
|-----|------------------:|--------------:|----------------:|-----------------------:|------:|
| A0 baseline | 19/19 (17) | 19/19 | 11/12 (9) | **0/9 (0)** | 92.0 |
| A1 clause | 15/19 (13) | 15/19 | 12/12 (9) | 3/9 (0) | 92.0 |
| A2 2nd-pass | 19/19 (17) | 19/19 | 12/12 (9) | 4/9 (0) | 92.0 |
| A3 clause+fewshot | 15/19 (13) | 17/19 | 12/12 (9) | **6/9 (3)** | 92.0 |

Round-1 read: every intervention lifts w7 `require_if` off 0 and w7 `show_if`
to 12/12; the whole w7 gap is `require_if` (dual-role omission, as diagnosed).
A3 leads w7 require_if AND is the only arm with require_if trigger-correctness.
Apparent i-90 show_if dip on the contract-clause arms (A1/A3: 15/19) -- carried
into round 2 as a variance re-check on the CONTENDER (A3). A1 was not re-run:
it is dominated by A3 on the w7 target in round 1 (require_if 3/9 vs A3's 6/9,
no trigger-correctness), so it loses on w7 regardless of whether its i-90 dip is
variance or real -- re-running it could not change the pruning decision. A3's
re-check (below) resolves whether the clause itself is safe on i-90; A2
(contract untouched) already holds i-90 perfectly, isolating any first-pass
perturbation to the contract text.

### Round 2 (finalist A4 + A2/A3 variance anchor, gives n=2 on contenders)

| arm | run | i-90 show_if (tc) | w7 require_if (tc) | w7 F1 |
|-----|-----|------------------:|-------------------:|------:|
| A2 2nd-pass | rep1 | 19/19 (18) | 3/9 (0) | 92.0 |
| A3 clause+fewshot | rep1 | **19/19 (17)** | **7/9 (7)** | 98.3 |
| A4 2nd-pass+fewshot | rep0 | 19/19 (17) | 4/9 (0) | 92.0 |

**The round-1 i-90 A3 "regression" was VARIANCE, not the clause:** A3 rep1
holds i-90 show_if 19/19. A4 (the synthesis -- A2's architecture carrying A3's
few-shot) confirms that moving the instruction into a second pass gives up most
of the require_if gain (4/9 vs A3's 6-7/9) and never gets trigger-correctness:
the win comes from the FIRST-PASS contract clause reasoning over the full form,
not a bolt-on refinement call.

### Verdict: A3 wins (dual-role clause + generic dual-role few-shot, in the
first-pass contract)

A3 vs the R3 exit bars, representative run (rep1):
- **w7 (test, never tuned against):** sh/rq presence 90.5% (bar >=70), combined
  trigger-correct 81.0% (bar >=60), require_if 7/9 (bar >0), fieldF1 98.3 (bar
  >=90). ALL CLEARED, most by a wide margin -- from a 47.6% / 42.9% / 0-of-9
  baseline.
- **i-90 (tune):** sh/rq presence 100% (bar >=95), cond_behavior 19/19 (bar
  >=95), fieldF1 96.7 (bar >=96). show_if trigger-correct 17/19 = 89.5% --
  0.5pt under the 90% bar, but IDENTICAL to baseline (A3 neither fixes nor
  worsens those 2 wrong-trigger cases) and within the stated +-1-item variance
  (18/19 = 94.7%). R3 ships A3 and runs the confirming n=2; a within-1-item
  result triggers the recheck rule.

The change to graft in R3 is TWO cross-form-safe additions to
`scripts/bakeoff/schema_contract.py`'s relationship section: (1) the dual-role
emphasis clause (`_DUAL_ROLE_CLAUSE` here) stating show_if != require_if and
that a conditionally-shown field is often also conditionally required by the
same trigger; (2) the shape-only dual-role few-shot example
(`_DUAL_ROLE_FEWSHOT`). Neither references I-90 or W-7 content.

Pruned: A1 (dominated by A3 -- same clause, no few-shot, weaker w7). A4
(architecture-only; loses the require_if gain). A2 kept as the i-90 safety
reference (proves the clause, not the harness, drives both the win and the
round-1 variance).

### Model/SDK provenance

`claude-opus-4-8` via the local claude CLI; scored with the sprint-15
`schema_score.py` metrics (post-eprg). Dated 2026-07-25, post the 2026-06-11
google-genai 2.8 cutover and post the v2 schema flip -- current, not a stale
pre-cutover hypothesis.
