# Relationship-extraction baseline (bd polyglot-pdf-eprg, sprint 15)

Recorded 2026-07-25. Pipeline: the shipped one-command auto-pass
(`scripts/authoring/extract_form.py`), model `claude-opus-4-8` (local claude
CLI), plain prompt, defaults; n=1 fresh extraction per form. Scored post-repair
with `scripts/authoring/eval_extraction.py` (which now carries the sprint-15
relationship metrics). Historical run-to-run variance on relationship counts is
~+-1 item -- an R3 bar met/missed within 1 item warrants an n=2 re-run.

## Numbers

| form | fieldF1 | show_if present | show_if trigger-correct | require_if present | conditional_behavior present | copy_to | trigger-side residue |
|------|--------:|----------------:|------------------------:|-------------------:|-----------------------------:|--------:|---------------------:|
| i-90 (tune) | 99.2 | 19/19 (100%) | 17/19 (89.5%) | n/a (0 in gold) | 19/19 (100%) | 3/4 | 0 |
| w7 (test)  | 92.0 | 10/12 (83.3%) | 9/12 (75.0%) | **0/9 (0%)** | n/a (0 in gold) | n/a | 0 |

Combined sprint-15 headline (show_if + require_if): i-90 100% present; w7
**47.6%** present (10/21), **42.9%** trigger-correct (9/21).

- "present" = the gold field's matched draft field carries the same key at all
  (the historical recall metric).
- "trigger-correct" = the recovered condition also points at the right
  trigger field(s), resolved through the field match (new in R1; operator/
  value fidelity deliberately not scored -- slug dialects differ).

## Readings

1. **The stale June picture (45-55% show_if, 0% logic keys) no longer holds on
   i-90.** A month of pipeline work (v2 vocabulary exemplar, grouping +
   backfill fixes) saturated presence on the tune form. Verified NOT leakage:
   the few-shot exemplar is hand-authored generic vocabulary, never the target
   form's gold (`scripts/authoring/fewshot/README.md`,
   `scripts/bakeoff/arm_llm_native.py:16`), and the eval path passes no
   few-shot at all.
2. **The real gaps are cross-format generalization and correctness.** w7's
   `require_if` collapses to 0/9 -- the extractor never emits the key on a
   form whose conditional text is phrased differently -- and 2 of 19 i-90
   show_if point at the wrong trigger.
3. **Trigger-side residue is 0 on both baselines** -- the current model emits
   target-side directly; the harvest path (R4) guards regressions when R2
   starts eliciting trigger-side expressions.

## Finalized rubric bars (logged on epic `polyglot-pdf-o2bs`)

Re-anchored from the plan's provisional bars (which assumed the stale June
baseline); nothing softened -- the saturated i-90 presence bar became a
no-regression bar plus a new trigger-correctness bar, and the headline moved
to w7:

- **Crit 2 (i-90, tune):** show_if+require_if presence >= 95%; show_if
  trigger-correct >= 90%; conditional_behavior presence >= 95%; field F1 >= 96.
- **Crit 3 (w7, test -- never tuned against):** combined show_if+require_if
  presence >= 70%; combined trigger-correct >= 60%; require_if presence > 0;
  field F1 >= 90.
- **Crit 4:** zero silent drops (unchanged).
