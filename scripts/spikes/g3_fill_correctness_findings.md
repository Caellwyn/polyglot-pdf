# G3 fill-correctness gate: DTI+eviction vs full-SI baseline (bd polyglot-pdf-jnjj.7)

*The correctness arm of the Pillar-A flip (epic polyglot-pdf-jnjj exit
criterion 1). G2 measured tokens/dollars (DTI GO, jnjj.25/ctu8); this gate
measures whether the reduced-SI arm still fills the form RIGHT.*

## Verdict

**GO -- no correctness regression attributable to the SI reduction.** Per-field
fill accuracy is statistically indistinguishable between arms at this sample
size, and the error decomposition shows the two arms fail in the SAME dominant
mode (audio transcription, 9 misses each across n=2 runs/arm). The one
DTI-specific failure mode -- a late-session tool-call stall -- is filed for
investigation (bd polyglot-pdf-yipc) and is bounded in production by user
re-prompts, the GoAway session refresh, and the B-pillar validator net.

## What was measured

`scripts/spikes/measure_form_session_costs.py` (the jnjj.38/.39-hardened
instrument), real Gemini on Vertex (`gemini-live-2.5-flash-native-audio`),
real I-90 schema, the 30-question happy-path plan, `--questions 30`:

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
| DTI+eviction 5000/3500 (pre-migration schema, ctu8) | r1/r2 | 73.3% / 93.3% | costs_i90_2.5_dti_cont_comp_happy_20260706T021216Z / 022507Z |
| **DTI pooled (n=4)** | | **78.3%** | |

The 6.7-point mean gap on the current schema is 2 fields out of 30 --
well inside the observed run-to-run variance (baseline spread 13.4 points,
DTI spread 6.7-20 points). Pooled DTI (78.3%, n=4) vs baseline (80.0%, n=2)
is a wash.

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
  see the FakeClient spoken_to_fids comment). The 2026-07-11 runs made 0-1
  lookups (happy path does not force recall).
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
