---
date: 2026-08-28
bead: polyglot-pdf-2nikx
title: "measure: i90-v2 (57q) deployed vs naive session cost -- the long-form moat case"
tags: [harness, performance, testing]
---

## Trigger

Follow-on to the W-7 cost study (bd `polyglot-pdf-wiadk`, PR #661): the
maintainer's new I-90 kit (`form-kits/i-90_v2`, 34 sections / 94 fields,
pulled from the demo bucket via `pull-form-kits.sh`) is the long-form case
where the architecture's advantage should compound. Same methodology, same
$100 program cap.

## What shipped

- **The long-form comparison** (7 valid runs, replay-validated to $0.000004):
  deployed all-in happy $2.040/$2.072 (mean $2.06), unhappy $4.272/$4.046
  (mean $4.16) -- 57/57 confirmed, 48/57 correct (84%) on ALL FOUR runs;
  naive happy $6.017 (57/57, 82%, 2 platform force-trims). Naive unhappy ran
  TWICE by maintainer direction: without recovery it **DID NOT COMPLETE**
  ($5.91 over 35 minutes, 33/57 confirmed, model tool-silence, guard abort at
  q39; no server close -- and the documented 15-minute uncompressed cap never
  fired, a second docs-vs-reality divergence alongside 32k-vs-128k); WITH
  Gemini session resumption enabled it completed -- **$9.836, 40.0 minutes,
  51/57 confirmed, 40/57 correct (70%)**, one resume at THE SAME q39 (the
  collapse reproduces at the same question across two independent runs).
  Final unhappy multipliers, apples-to-apples: 2.37x raw dollars, 2.64x per
  confirmed field.
- **Session resumption shipped as the program's only production-code change**
  (maintainer-directed): `SESSION_RESUMPTION_ENABLED` (default OFF -- the
  June decline stands for production; the harness opts in for the naive arm),
  adapter captures SessionResumptionUpdate handles and can reconnect with
  one; the naive driver resumes instead of aborting (max 3), recording
  `session_resumes` in the run meta. Config-inertness pinned by
  mutation-verified tests.
- **The moat widens with form length**: happy multiplier 2.6x (W-7, 22q) ->
  2.9x (i90-v2, 57q); per-confirmed-field on the correction path $0.073 vs
  $0.193 (2.64x), with the naive arm needing a recovery feature a naive
  builder would first have to know to build. Program spend $53.73 of the
  $100 cap (per-run ledger + anomaly resolutions in the findings doc).
- **The tracked-kit reversal** (Opus round-1 findings): committing
  form-kits/i-90_v2 turned CI red (translation-coverage lint), armed an
  unintended next-deploy publish beside the existing I-90, and committed a
  booklet PDF against .gitignore's own rule -- the kit returned to untracked
  (schema sha256 pinned in the findings doc; kit-reading tests skip when it
  is absent; the lint sweep now pins tracked kits only). Publish/label/
  translation decisions parked in beads polyglot-pdf-9jb21/g3cj1; the
  metadata readiness flags contradicting the maintainer's completed review
  are an editor bug (bead polyglot-pdf-058kq).
- **Harness work bought with diagnostic dollars** (invalid runs committed as
  evidence, excluded from headline means): a realistic 57-question persona
  plan for the 94-field schema (37 schema-gated exclusions, pinned by a
  22-test completeness/option-label suite); an ASR-robustness fix (gTTS
  "0 0 9..." transcribed as "OON 9..." -> failed the strict 12-digit pattern
  -> whole-session desync); a two-condition derailment guard (6 tool-silent
  or 8 confirm-stagnant questions -> abort, meta-stamped, ~$0.3 cap on wedge
  spend); an adaptive confirm-gate (`_settle_confirm`: wait for each field to
  settle, max one nudge -- live-adapter only after the first draft turned a
  28s dry-run test into an hour); an offline dry-run test proving the DTI
  drip crosses section boundaries (refuting the by-reference-schema
  hypothesis); i90-v2 arms for the count-tokens script and the comparison
  plots.
- Findings doc extended with pre-registrations (graded honestly: naive-happy
  landed 0.4% ABOVE the band ceiling -- the pilot predated the confirm-gate;
  naive-unhappy graded wrong-mechanism/right-conclusion), method changes,
  ledger, and anomaly resolutions. Investor report gained the long-form
  section; adversarial docs review found 2 gaps (a spliced trim-value cell,
  an unsupported positional-clustering claim) -- both fixed.

## Lessons

- **Scripted voice sessions cannot self-repair an ASR mishearing.** One fused
  transcription ("0 0" -> "OON") against a strict-format field desynced 55
  questions. Personas for scripted runs should avoid leading zeros in long
  digit strings; and a run whose confirmations stagnate is derailed even
  while it keeps making (failing) tool calls -- guard on BOTH signals.
- **A fixed turn cadence outruns the model on long forms.** The correction
  cycle plus secretary/spell-back bursts need an extra turn sometimes; lag
  compounds one question per burst. The confirm-gate (wait-for-settle, one
  nudge) restored lock and is a no-op when confirms land in-cadence.
- **Test-speed trap: a live-pacing gate must be gated OFF for offline stubs**
  -- the first draft added ~32s x n_questions to a dry-run test; caught as a
  pytest timeout.
- The naive-collapse mode (tool-silence under trims + corrections at length)
  is a genuine product observation, measured once -- reported as such, never
  as a proven rate.

## Doc freshness

- `scripts/spikes/w7_naive_vs_deployed_findings.md` now carries both studies
  and is the canonical citation for current session-cost numbers.
- `docs/standards/logging-and-cost.md` reviewed and left: the MEASURED COST
  INVARIANT still holds on i90-v2 deployed runs (audio-in leads).
- Pre-existing stale-doc flags (same set as the wiadk closeout) track files
  this branch did not touch -- left per the closeout rule.

## Files touched

- `scripts/spikes/measure_form_session_costs.py` -- I90V2_QUESTIONS plan + schema registration, ASR-robust persona fix, derailment guard, confirm-gate
- `backend/tests/unit/test_measure_harness_i90v2_plan.py` -- new (22 tests)
- `tests/test_stress_harness_units.py` -- new offline drip-boundary dry-run test
- `scripts/spikes/count_naive_si_tokens.py` -- --schema generalization
- `scripts/spikes/plot_2nikx_comparison.py` -- i90-v2 + cross-form charts
- `scripts/spikes/w7_naive_vs_deployed_findings.md` -- i90-v2 sections
- `form-kits/i-90_v2/` -- the kit under measurement (bucket pull-review-commit flow; .gitignore line retired)
- `scripts/spikes/fixtures/audio_cache/` -- 84 new utterances
- `scripts/spikes/data/2nikx-{smoke,pilot,debug,full}/` -- run artifacts incl. committed diagnostics
- `pitch/ignored_pitch/` -- investor report + i90 charts (gitignored, local deliverable)
- `docs/journal/entries/2026-08-28-bd-2nikx-i90v2-deployed-vs-naive-cost.md` -- this entry
