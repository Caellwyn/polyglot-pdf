---
date: 2026-07-24
bead: polyglot-pdf-i36i
title: "V1 probe: translation-gate discrimination pilot -- planted corruptions, es/zh/ur (GATE for V3)"
sprint: 14
tags: [testing, conventions]
---

## Trigger

V1 of the translation-quality-gate epic (`polyglot-pdf-sekc`) -- the probe
gate the plan requires before V3 builds the production verify/rectify loop.
The Gate-1 prior-work audit confirmed the question was unmeasured (W5/g1/g1c
measured contradiction judges, never translation drift); Gate-2 estimate
~$0.45 against the plan's ~$0.25 pre-authorization -- measured actual
**$0.4247 across two runs** (run 1 $0.2145; run 2 $0.2102, the
per-language-accounting run added after the Opus review caught that
criterion 3's "per-language token cost" was unmet by run 1's per-model
accumulator: es $0.0698 / zh $0.0882 / ur $0.0523). Run 2 doubled as a
verdict-stability replicate: 14/14 plants + clean es gold REPLICATED;
zh-g07 reproduced (hardening its diagnosis); zh-g11 did not recur
(borderline judge noise, consistent with its diagnosis).

## What shipped

- `scripts/spikes/translation_gate_probe.py` -- the standalone spike driving
  the full loop (V2's real lint + glossary, spike-local judge/rectify/
  back-translate prompts) on gold + planted corruptions, with the g1b-style
  cost accounting (bounded pro thinking 512, thoughts billed separately).
- `scripts/spikes/data/translation-gate/gold.json` -- es/zh gold seeded from
  Pub 850/official renderings + 6 deterministic plants per language across
  judge-side and lint-side classes (incl. the clean-round-trip trap and the
  mechanical+semantic half-success plant); ur observational set.
- `scripts/spikes/translation_gate_findings.md` + raw run artifacts
  (`data/translation_gate_20260724T205304Z.{csv,meta.json}`).

**Results (full table in the findings doc):** plants 14/14 caught at the
intended layers in BOTH chunk arms; es gold 15/15 clean; zh gold 13/15 with
both flags diagnosed (one back-translation-anchoring FP -- the plan's
pre-named FP generator, caught in the act; one unsatisfiable-criterion
flip-flop where the judge rejected both possible renderings); ur forward
output survived the lint (ASCII-digit pin held on live Perso-Arabic) and the
judge caught a real forward-translation error there.

**GATE verdict: PROCEED to V3** with three inherited mitigations (judge
prompt hardening, flip-flop detector, chunk 50). **The review-round-3
keep-rule collision was DECIDED on live evidence**: the collision
materialized unplanted (zh numeral plant: rectify twice lint-clean but
judge-flagged on the unsatisfiable nit) -- keep-original would have shipped
the provably wrong digit, so mechanical-origin unresolved now keeps the
latest lint-clean rectify; judge-origin unresolved keeps the original. Plan
doc updated in place; V3's bead notes carry the readout.

## Lessons

- **Rectify regenerates, it does not minimally patch.** Given the English
  original plus only a mechanical failure reason, rectify fixed the
  semantic corruption too -- the planted half-success case cannot easily be
  forced when the rectifier sees the source. The real collision came from
  judge perfectionism instead.
- **Judge appeasement loops are real and detectable.** zh-g11 is a true
  rejected-both oscillation (mingzi -> ming -> mingzi, every rendering
  refused); ur showed the weaker cousin, a cross-pass verdict inversion
  that CONVERGED on attempt 2 (the first draft mislabeled it a flip-flop
  -- fresh-eyes corrected it; the flip-flop detector rests on zh-g11
  alone, and the ur convergence is the COUNTEREXAMPLE that fixed the
  detector's spec: it fires on REJECTION RECURRENCE -- the judge re-flags
  an already-flagged value -- never on value identity alone, or it would
  have converted ur's clean accept into a false UNRESOLVED (Opus-review
  catch). A one-line loop guard that saves a pro call and converts thrash
  into an honest UNRESOLVED.
- **FP risk concentrates where gold confidence is lowest** (the g1b corpus
  lesson transposed): the es slice (agency-verifiable) was spotless; both
  zh flags sat on the two renderings seeded with least confidence. For V5,
  read UNRESOLVED lists low-resource-first AND expect flags to mix judge
  error with genuine gold weakness.

## Doc freshness

- `docs/sprint_14_translation-quality-gate_plan.md` updated in place: the
  keep-rule collision paragraph now records the decided rule + V3
  inheritances (plan-of-record, exempt from current-state-only).
- No component/standards docs affected (spike-only code; no production
  surfaces touched).

## Files touched

- `scripts/spikes/translation_gate_probe.py` -- NEW (the spike).
- `scripts/spikes/data/translation-gate/gold.json` -- NEW (corpus).
- `scripts/spikes/translation_gate_findings.md` -- NEW (findings).
- `scripts/spikes/data/translation_gate_20260724T205304Z.{csv,meta.json}`
  + `..._20260724T212414Z.{csv,meta.json}` -- NEW (raw artifacts, runs
  1 + 2).
- `docs/sprint_14_translation-quality-gate_plan.md` -- keep-rule readout.
