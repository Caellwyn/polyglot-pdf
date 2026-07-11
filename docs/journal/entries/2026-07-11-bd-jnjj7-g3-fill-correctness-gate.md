---
date: 2026-07-11
bead: polyglot-pdf-jnjj.7
title: "G3: fill-correctness gate -- JIT-SI vs full-SI voice-fill accuracy (GATES A correctness)"
tags: [extractor, testing, postmortem]
---

## Trigger

The last unmet keystone gate of the SI-reduction epic (`polyglot-pdf-jnjj`,
exit criterion 1): with the whole-form field dump gone from the Live model's
system instruction, does the voice model still fill the form CORRECTLY?
Production already runs the reduced-SI arm (DTI + continuous + compression,
deploy-demo.sh) because the A5 flip bead was force-closed as obsolete -- so
this gate retro-validates the deployed configuration against the full-SI
section-reset baseline it replaced. The bead had been claimed 2026-06-18 and
stalled after its harness dependency (jnjj.38) shipped; the stale branch was
fully merged (PR #244), deleted, and the bead re-claimed.

## What shipped

- **The measurement** (the bead's deliverable): 4 fresh 30-question
  happy-path runs on the real I-90 via `measure_form_session_costs.py` on
  Vertex -- full-SI section-reset baseline x2 (86.7% / 73.3% fill accuracy)
  vs DTI+eviction at the production 5000/3500 window x2 (76.7% / 70.0%),
  ~$2.55 total. (Criterion 1's "on the largest section" wording is from the
  bead's stale JIT framing; the shipped arm is continuous whole-form, where
  a single-section run would never trigger eviction -- the 4-section
  30-question plan is the deliberate, harder substitution; defended in the
  findings doc.) **Verdict: GO** -- the arms are indistinguishable at this
  sample size, and the error decomposition shows both fail in the SAME
  dominant mode (audio-transcription mishears, 9 vs 9); the SI reduction
  itself has no correctness signature. Full analysis:
  `scripts/spikes/g3_fill_correctness_findings.md`; run CSVs/metas committed
  under `scripts/spikes/data/`.
- **A stale-canon bug in the instrument, found and fixed**: the i-90
  option-value vocabulary migrated (widget ids -> semantic slugs, PR #333)
  between the July-6 DTI runs and these baselines, and the stale
  `I90_EXPECTED` silently under-scored the baseline arm by 5-6 option fields
  (67% -> 86.7% re-scored). Fixed the canon, added
  `_assert_expected_canon_matches_schema` (aborts a run BEFORE spending
  live-Gemini money on drift), and added
  `scripts/spikes/rescore_fill_accuracy.py` (offline re-scoring of recorded
  metas, so canon fixes never require re-spending).
- **Cross-field-recall brittleness scoped** (exit criterion 2): harness
  lookups are NOT brittle at the accepted config (17/17 resolved in the
  July-6 5000/3500 run; that night's found=false lookups were a harness map
  bug fixed pre-run). Tracing the production path found a REAL gap: in
  continuous mode `getFieldBySpokenName` searches only the pinned first
  section + never-growing completedSections, so cross-section
  get_field_value returns not-found in production -- filed as
  **bd polyglot-pdf-lt9z** (the criterion's anticipated "different recall
  tool" -- ask_secretary, whole-form -- already shipped in jnjj.45).
- **A DTI-specific failure mode filed**: late-session tool-call stall (the
  model stops calling tools in the final questions of a ~30q continuous run;
  2 of 4 DTI runs, worst case 3 questions) -- **bd polyglot-pdf-yipc**.
  Distinct from the closed early-session stall (jnjj.40); bounded in
  production by user re-prompt, GoAway session refresh, and the B-pillar
  validator.

## Lessons

- **A measurement canon is code that rots**: any expected-values table keyed
  to schema vocabulary must assert against the live schema at startup, or a
  vocabulary migration silently corrupts every later run (this one turned a
  86.7% baseline into a reported 67%). The drift guard + offline re-scorer
  are the durable fix shape.
- Store per-field WRITTEN values in measurement artifacts (jnjj.38 did):
  it made re-scoring after the canon fix free instead of ~$1.30 of reruns.
- On A/B verdicts from small n: decompose errors by failure mode before
  comparing means -- the 9-vs-9 transcription tie was far more informative
  than the 80%-vs-73% means.

## Doc freshness

No tier-2 doc tracks `scripts/spikes/`. `docs/standards/logging-and-cost.md`
(the measured-cost invariant) is unaffected -- this gate measured
correctness, not cost. Stale docs flagged by prep all track surfaces this
branch did not touch (pre-existing; left as-is).

## Files touched

- `scripts/spikes/measure_form_session_costs.py` -- I90_EXPECTED slug canon,
  startup drift guard
- `scripts/spikes/rescore_fill_accuracy.py` -- NEW: offline re-scorer
- `scripts/spikes/g3_fill_correctness_findings.md` -- NEW: the gate's
  findings + verdict (GO)
- `scripts/spikes/data/costs_i90_2.5_section-reset_happy_20260711T*.{csv,meta.json}` -- baseline runs
- `scripts/spikes/data/costs_i90_2.5_dti_cont_comp_happy_20260711T*.{csv,meta.json}` -- DTI runs
- Beads filed: polyglot-pdf-lt9z (continuous-mode recall scoping),
  polyglot-pdf-yipc (late-session stall investigation)
