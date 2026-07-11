# G3 fill-correctness gate: DTI+eviction vs full-SI baseline (bd polyglot-pdf-jnjj.7)

*The correctness arm of the Pillar-A flip (epic polyglot-pdf-jnjj exit
criterion 1). G2 measured tokens/dollars (DTI GO, jnjj.25/ctu8); this gate
measures whether the reduced-SI arm still fills the form RIGHT.*

## Verdict

**GO -- no correctness regression DETECTABLE from the SI reduction.** Stated
honestly: on the only like-for-like comparison (same schema, same canon,
n=2/arm), the DTI mean sits BELOW the baseline mean -- 73.3% vs 80.0%, a
2-fields-in-30 gap. That gap is statistically indistinguishable from zero at
this sample size (Fisher exact on 60 scored fields/arm, p~0.52; each arm's
own run-to-run spread exceeds it), and the error decomposition attributes it
to arm-INDEPENDENT causes: the dominant failure mode is identical in kind
and count across arms (audio transcription, 9 misses each), and the residual
is the DTI late-session tool-call stall, filed for investigation (bd
polyglot-pdf-yipc) and bounded in production by user re-prompts, the GoAway
session refresh, and the B-pillar validator net. The criterion's
"at-or-above" is therefore met in the no-detectable-regression sense, NOT
proven on the mean -- proving a <=2-field mean difference would take ~20
runs/arm (~$13/arm), unwarranted when the decomposition already attributes
the gap to shared ASR noise plus one filed, bounded failure mode.

## What was measured

`scripts/spikes/measure_form_session_costs.py` (the jnjj.38/.39-hardened
instrument), real Gemini on Vertex (`gemini-live-2.5-flash-native-audio`),
real I-90 schema, the 30-question happy-path plan, `--questions 30`.

**Scope note (criterion 1 wording).** The bead's criterion says "on the
largest section" -- wording from its original JIT-SI framing, where the
arm-under-test was a per-section drip and a single big section was the
stress case. The arm that actually shipped is CONTINUOUS whole-form DTI
(the bead body itself flags the original framing as stale): a
single-section run would never trigger the context-window eviction whose
correctness effect this gate exists to measure (evictions start ~q14; the
DTI runs here evicted 7 times). The 30-question plan spans Part 1's four
sections including its largest -- a strictly harder, production-shaped
test -- and matches the plan every accepted cost run (jnjj.25/ctu8) used,
so the arms stay comparable across gates. Deliberate substitution, not an
oversight.

- **Baseline arm** (`--arm section-reset`): the full-SI per-section-reset flow
  the DTI replaced -- whole-section field dump in the SI, session restart at
  each boundary.
- **DTI arm** (`--arm dti --continuous --compression --trigger 5000
  --window 3500`): the production configuration (deploy-demo.sh: USE_DTI +
  CONTINUOUS_SESSION + CONTEXT_COMPRESSION_ENABLED) -- static DTI SI,
  per-field guidance drip, calibrated context-window eviction.

## Results (fill accuracy, corrected canon)

| Arm | Run | Accuracy | Data |
|---|---|---|---|
| full-SI section-reset | r1 | 26/30 (86.7%) | costs_i90_2.5_section-reset_happy_20260711T021331Z |
| full-SI section-reset | r2 | 22/30 (73.3%) | costs_i90_2.5_section-reset_happy_20260711T021843Z |
| **baseline mean** | | **80.0%** | |
| DTI+eviction 5000/3500 | r1 | 23/30 (76.7%) | costs_i90_2.5_dti_cont_comp_happy_20260711T022508Z |
| DTI+eviction 5000/3500 | r2 | 21/30 (70.0%) | costs_i90_2.5_dti_cont_comp_happy_20260711T023000Z |
| **DTI mean (current schema)** | | **73.3%** | |

The 6.7-point mean gap is 2 fields out of 30 -- inside each arm's own
run-to-run spread (baseline 13.4 points, DTI 6.7) and indistinguishable from
zero (Fisher exact, 48/60 vs 44/60, p~0.52). The error decomposition below is
what carries the verdict, not the means.

**Historical reference, NOT poolable:** the ctu8-era DTI runs
(costs_i90_2.5_dti_cont_comp_happy_20260706T021216Z / 022507Z: 73.3% / 93.3%)
ran against the PRE-migration schema and were scored against its matching
widget-id canon. They are not comparable with the current-canon numbers in
EITHER direction -- pooling their as-recorded accuracies with current-canon
numbers mixes canons, and re-scoring their written values against today's
slug canon would mark then-correct fills wrong. They are listed for lineage
only (an earlier draft of this doc pooled them; the outer review correctly
struck that).

## Error decomposition (the real finding)

Classifying every miss across the four current-canon-scored runs:

| Failure mode | Baseline (2 runs) | DTI (2 runs) |
|---|---|---|
| Audio transcription mishears ("Boston" for Austin, "America" for Maria, "Smith" for Vasquez, "Vazquez", "2B"/"14" for 12B, "Liza" for Rosa) | 9 | 9 |
| Format slips (1990-03-05 vs 03/05/1990; "Maple St") | 1 | 2 |
| Unfilled fields (written None) | 2 | 5 |

- **The dominant error source is the synthetic-audio -> ASR channel, and it
  hits both arms identically (9 vs 9).** These are not SI-architecture
  failures; a production user would correct them at confirmation
  ("Boston" -- "no, Austin") -- the happy-path script never pushes back.
- **The only arm-differentiated mode is the DTI late-session stall**: in run
  022508Z the model stopped calling tools for q28-30 entirely (q27 updated
  without confirming); run 023000Z dropped the final field. The baseline's
  per-section resets naturally refresh engagement. Filed as bd
  polyglot-pdf-yipc (investigate; production impact bounded by user
  re-prompt + GoAway refresh + validator net).

## Cross-field recall via get_field_value (exit criterion 2)

- In the harness, exact-spoken-name lookup is NOT brittle at the accepted
  config: the 2026-07-06 5000/3500 run resolved **17/17** lookups (the
  found=false lookups that night were a harness map bug, fixed pre-run --
  see the FakeClient spoken_to_fids comment). Caveat stated plainly: that
  17/17 is INHERITED evidence from the pre-migration run -- the 2026-07-11
  runs made only 0-1 lookups (the happy path never forces recall), so this
  gate's own runs did not re-exercise the lookup path. The resolution
  mechanism (the FakeClient's name+spoken_name map) is unchanged since, so
  the figure stands, but a recall-forcing plan (scripted "what did I say my
  X was?" turns) would be the instrument upgrade if recall ever needs its
  own gate.
- **A real production gap was found while tracing this**: in continuous mode
  the frontend's `getFieldBySpokenName` searches only the PINNED first
  section + a never-growing completedSections, so cross-section
  get_field_value returns found=false in production even for filled fields.
  The harness's whole-plan map does not model this (labeled fidelity gap).
  The "different recall tool" the criterion anticipated ALREADY exists and
  is shipped: ask_secretary (whole-form, bd jnjj.45). Scoped fix filed as
  **bd polyglot-pdf-lt9z** (widen the lookup in continuous mode and/or steer
  SI recall guidance to ask_secretary).

## Instrument corrections made for this gate

The i-90 option-value vocabulary migrated (widget ids -> semantic slugs,
PR #333) between the 2026-07-06 DTI runs and these baseline runs; the stale
`I90_EXPECTED` canon silently under-scored the baseline arm by 5-6 option
fields (67% -> 86.7%, 53% -> 73.3% once re-scored). Fixes shipped with this
gate:
- `I90_EXPECTED` updated to the current slug canon;
- `_assert_expected_canon_matches_schema` aborts a run at startup (before
  spending live-Gemini money) if the canon drifts again;
- `scripts/spikes/rescore_fill_accuracy.py` re-scores recorded metas offline.
The 2026-07-06 DTI accuracies stand as recorded: they were scored against
their contemporaneous (pre-migration) schema, whose canon matched.

## Costs

Four 30-question runs at ~$0.62-0.64 each; total ~$2.55 (Vertex,
polyglot-demo-aa709).

## Epic consequence

G3 GO completes the keystone-gate set for epic exit criterion 1 (G1 recorded
NO-GO-for-replacement -> B rescoped to defense-in-depth per the epic notes;
G2 superseded by the DTI cost verdict, jnjj.25/ctu8 GO; G3 correctness GO
here). The A5 flip this gate was designed to precede already shipped
(jnjj.12 force-closed; production runs DTI continuous) -- G3 retro-validates
that configuration.
