---
date: 2026-07-25
bead: polyglot-pdf-dsbl
title: "R2: relationship-extraction bake -- dual-role clause + few-shot wins (sprint 15)"
tags: [extraction, experimentation]
---

## Trigger

Sprint-15 R2: pick, by measurement on I-90 (tune) generalizing to W-7 (test),
the approach that most lifts relationship recall + trigger-correctness in the
auto-pass. Run under the /experimentation gates.

## Gate 1 (prior-work audit) -- what it saved

No prior enriched/second-pass arm ever beat plain claude-hybrid on conditional
recall (7a9.12: plain 45.0 vs enriched 31.9), and per-signal enrichment
ablation (7a9.10) found no signal helped conditionals -- so "more (a) structure"
was ruled OUT before spending. `controls_fields` is a removed v1 key (can't be
an output). The June "conditional keys 0%" verdict is stale (pre-v2); i-90 now
recovers cond_behavior 19/19. Net: only a (b)-targeted change on the FIRST-PASS
prompt was worth baking, and the real gap is W-7's require_if 0/9.

Root-cause probe of that gap: W-7 gold gives several fields BOTH show_if AND
require_if on the same trigger ("appears AND must be filled"); the extractor
recovered show_if and OMITTED the parallel require_if. The contract never
stated the dual-role pattern.

## Gate 2 (cost) -- $0 metered

Backend is the local claude CLI (claude-opus-4-8), free in-env; option-
translation disabled (irrelevant, needs Vertex creds). 14 extraction runs across
two rounds = ~20 CLI calls (A2/A4 are 2-call arms: extraction + a relationship-
only second pass), no metered spend -> no paid go-ahead needed (recorded in the
findings doc's Gate-2 section).

## What shipped (research only -- no production file touched)

`scripts/spikes/relationship_bake.py` (+ raw rows under
`scripts/spikes/data/`), `scripts/spikes/relationship_bake_findings.md`. The
arm variants monkeypatch a RESEARCH COPY of the extractor's SCHEMA_CONTRACT and
restore it; the shipped prompt is untouched (maintainer decision 2026-07-25 to
isolate R2 from production; R3 grafts the winner).

## Result: A3 wins -- dual-role clause + generic few-shot, in the first pass

Four arms, then a variance-anchor round for n=2 on the contenders. Every
intervention lifted W-7 require_if off 0/9; A3 (an explicit "show_if !=
require_if; a conditionally-shown field is often also conditionally required by
the same trigger" clause PLUS a shape-only cross-form few-shot) led decisively:
W-7 require_if 6-7/9 with trigger-correctness (the only arm to get it),
combined W-7 sh/rq presence 90.5% / trigger-correct 81.0% / fieldF1 98.3 on its
representative run -- clearing every R3 bar from a 47.6% / 42.9% / 0-of-9
baseline.

Two things the variance-anchor round settled:
- The round-1 i-90 show_if dip on the clause arms (15/19) was VARIANCE -- A3
  rep1 holds i-90 19/19. The clause is safe on the tune form.
- A synthesis arm A4 (move the instruction into a relationship-only second pass
  instead of the first-pass contract) gave up most of the require_if gain
  (4/9, no trigger-correctness). The win comes from the model reasoning over
  the WHOLE form with the dual-role instruction in the first pass, not a
  bolt-on refinement call. So R3 grafts a first-pass CONTRACT change, not a
  new pipeline stage -- simpler and better.

Residual honesty: i-90 show_if trigger-correct stays 17/19 (89.5%, 0.5pt under
the 90% bar) -- unchanged from baseline; A3 doesn't fix those 2 wrong-trigger
cases but doesn't worsen them, within the +-1-item variance the bars allow. R3
runs the confirming n=2 and applies the within-1-item recheck rule.

## Notes

closeout_prep's STALE tier-2 doc flags reviewed: all cite code changed by other
already-merged branches; this branch adds only spike scripts + data + docs.
Pre-existing drift, not caused here.

## For R3

Graft two cross-form-safe additions into
`scripts/bakeoff/schema_contract.py`'s relationship section: the dual-role
emphasis clause and the shape-only dual-role few-shot example (both verbatim in
the bake as `_DUAL_ROLE_CLAUSE` / `_DUAL_ROLE_FEWSHOT`). No new pipeline stage.
