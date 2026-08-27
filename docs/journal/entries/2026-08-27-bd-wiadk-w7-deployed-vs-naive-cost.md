---
date: 2026-08-27
bead: polyglot-pdf-wiadk
title: "measure: W-7 deployed vs naive session cost (moat numbers, bd-89mt refresh + first true naive baseline)"
tags: [harness, performance, testing]
---

## Trigger

The maintainer needed current, defensible numbers for an investor meeting: (A)
what a real W-7 voice session costs on the deployed config, and (B) how much
the architecture (continuous DTI + derived compression + secretary) reduces
that cost versus a NAIVE build -- the full form schema plus the official IRS
instruction booklet pasted into the system instruction, one session, no
compression, no secretary. The cost gap is part of the product moat. The prior
W-7 measurement (bd `polyglot-pdf-89mt`, $0.59/$1.25) was stale: the shipped
SI grew and the spell-back cutover (PR #642) changed name-field turn structure,
and no true naive baseline had ever been run in this repo. Budget: $100 cap
with pre-registered stop rules; actual live spend ~$10.17.

## What shipped

- **The measured comparison** (all 6 full runs replay-validated to within
  $0.000003; artifacts in `scripts/spikes/data/wiadk-full/`): deployed all-in
  happy $0.702/$0.724 (mean $0.71), unhappy $1.406/$1.329 (mean $1.37), 22/22
  fields correct+confirmed on all four runs; naive happy $1.839 (21/22),
  naive unhappy $3.282 (21/22 filled, 20/22 confirmed). Multipliers 2.6x happy
  / 2.4x unhappy; ~61%/58% cost reduction. Full numbers, estimator grading,
  and caveats: `scripts/spikes/w7_naive_vs_deployed_findings.md`. An
  investor-deck source report (plain language) went to `pitch/ignored_pitch/`
  (deliberately gitignored, per the 89mt precedent).
- **Headline discovery: the Live API force-trims native-audio sessions at
  ~32k context tokens.** The naive arm's "unbounded" session is not billable-
  unbounded -- the platform silently discards oldest history at ~32k (measured
  drops 31,876->27,910 and 31,821->27,979), with no error and no client
  signal. The naive arm's accuracy failures and answer/field divergences
  cluster after trims. Deployed compression is a *curated* window; the
  platform fallback is a *blind* one.
- **Harness additions** (`scripts/spikes/measure_form_session_costs.py`):
  cherry-picked the five bd-89mt commits from the stranded local branch
  `claude/certification-denylist` (one pick amended to strip 11 run artifacts
  that violated its code-only premise), then added `--arm naive` (legacy
  full-schema SI + booklet appended harness-side, 5-tool naive catalog,
  spell-back off, single-session guard), a spell-back fake-client ack (the
  deployed arm stalls on name fields without it), a divergence counter, and
  `count_naive_si_tokens.py` (exact naive payload: 27,923 SI + 737 tools
  tokens). `analyze_naive_vs_deployed.py` + `plot_wiadk_comparison.py` do the
  replay accounting and the 5 comparison charts.
- **Tests**: `backend/tests/unit/test_measure_harness_naive_arm.py` (27) +
  `test_replay_arithmetic.py` (8), all mutation-verified, including an
  allowlist pin on the naive tool catalog and a June-artifact exact-match
  replay test that doubles as the cherry-pick canary.
- **Pre-registration discipline**: the pilot-based prediction ($2.27, band
  $1.90-2.63) was written into the findings doc BEFORE the full naive run;
  actual $1.839 -- 19% below the point, $0.06 below the band floor, recorded
  honestly with the reason (the projection could not know about the 32k trim
  or the drop in orientation calls after q12).
- **Review**: two orchestration workflows (maintainer-directed); the docs
  review pass found 4 real gaps in the pitch report (a wrong confirmation
  claim, a stale run count, an overreach on billing verification, a missing
  pending-reconciliation caveat) -- all fixed. Fresh-eyes/outer review ran at
  closeout per the standard flow.
- **Deferred**: Cloud Billing console reconciliation over the 2026-08-27
  quiet-day window (exports lag same-day traffic) -- pre-registered follow-up
  in the findings doc.

## Lessons

- **"Unbounded" Live sessions are platform-capped at ~32k context on native
  audio, with silent blind truncation.** Any future cost model of an
  uncompressed arm must cap per-event prompt at ~32k, and any correctness
  claim must account for silent memory loss. (Recorded via `bd remember`.)
- **A naive baseline must not declare the app's architecture tools.** The
  first naive smoke measured the model calling `ask_secretary` and burning a
  ~29k-token context re-send on the fail-open -- a harness artifact a skeptic
  could pin the whole naive number on. Filter declarations to what the
  measured persona would actually have; pin the set with an allowlist test.
- **The multi-module get_settings trap struck again** in
  `count_naive_si_tokens.py`: built without the patch, it silently counted
  the WRONG SI (DTI + booklet, 26,009 tok) instead of the legacy-SI + booklet
  payload (28,660 tok). The tell was an SI count that did not move when the
  SI changed. Same scar as CLAUDE.md/jnjj.25; the fix is the same patch the
  harness itself applies.
- **Replaying a cross-arm trace is a bad estimator; same-arm projection is a
  good one.** Estimator A (deployed-unhappy trace re-billed under naive
  rules) missed by +159%/-59% depending on trim assumptions; Estimator B
  (naive-happy trace projected to unhappy turn structure) landed +12%.
  Extrapolate from a trace whose turn structure matches the target arm.

## Doc freshness

- `docs/standards/logging-and-cost.md` MEASURED COST INVARIANT: fresh deployed
  modality shares (48.1%/46.8% happy, 57.8%/38.4% unhappy audio-in/text-in)
  land within 1-2.4pp of the documented table with the same ordering --
  reviewed and left as-is (CONFIRMED, no restatement needed).
- `scripts/spikes/w7_naive_vs_deployed_findings.md` is the new canonical
  citation for current W-7 session cost (supersedes the bd-89mt close-reason
  numbers).
- The doc-freshness checker's other STALE flags (testing.md,
  validation-delegation.md, voice-and-vad.md, ws-protocol.md,
  technical_guide.md, schema_format.md) all track files this branch did NOT
  touch -- pre-existing staleness, reviewed and left per the closeout rule.

## Files touched

- `scripts/spikes/measure_form_session_costs.py` -- cherry-picked 89mt support + naive arm, spell-back ack, divergence counter, session guard
- `scripts/spikes/count_naive_si_tokens.py` -- new; exact naive SI+tools token count (Vertex count_tokens)
- `scripts/spikes/analyze_naive_vs_deployed.py` -- new; replay accounting, naive re-billing, unhappy projection, text-sidecar pricing reuse
- `scripts/spikes/plot_wiadk_comparison.py` -- new; 5 comparison charts
- `scripts/spikes/plot_w7_cost.py` -- extracted from certification-denylist tip
- `scripts/spikes/w7_naive_vs_deployed_findings.md` -- new findings doc (methods, results, estimator grades, caveats, budget ledger)
- `scripts/spikes/data/wiadk-{smoke,pilot,full}/` -- committed raw run artifacts + plots
- `backend/tests/unit/test_measure_harness_naive_arm.py` -- new (27 tests)
- `backend/tests/unit/test_replay_arithmetic.py` -- new (8 tests)
- `pitch/ignored_pitch/w7-cost-comparison-2026-08-27.md` + `plots/` -- investor-deck source report (gitignored, local deliverable)
- `docs/journal/entries/2026-08-27-bd-wiadk-w7-deployed-vs-naive-cost.md` -- this entry
