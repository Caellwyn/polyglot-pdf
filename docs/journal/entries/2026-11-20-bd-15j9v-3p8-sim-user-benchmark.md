---
date: 2026-11-20
bead: polyglot-pdf-15j9v
title: "3.8 cost and accuracy re-measured with a simulated user (W-7 happy, W-7 self-correcting, I-90 v2; n=3 each)"
tags: [harness, performance, testing]
---

## Trigger

The 2026-11-18 3.8 benchmark (bd `e72on`) drove the model with a fixed-script
user, which tainted several results:
- every I-90 run derailed;
- a wrong stored value was never corrected;
- a spelling request was never answered.

The maintainer dropped 2.5 from the sim-user work (it is being sunset). They
asked to redo the tainted 3.8 groups with the sim user, so the 3.8 cost and
performance picture is accurate.

## What was measured

Nine benchmark runs on `gemini-3.8-live` at production config, in three
groups of 3:
- W-7 happy;
- W-7 with every answer slipped once, then corrected;
- I-90 v2.

Findings: `scripts/spikes/sim_user_findings.md`. Raw data:
`scripts/spikes/data/sim_user/bench/`, indexed in `RUNS.md`. Spend was about
$32.80 against a $35 cap.

- **Every run completed the form.** All 303 fields were filled and
  confirmed. Strict accuracy was 22/22 on every W-7 and 54-57/57 on the I-90.
- **Cost per form:**
  - W-7 happy: $1.055 (+17% over the fixed script; a responsive user answers
    more fully and answers spelling requests);
  - W-7 self-correcting: $1.565;
  - I-90 v2: $3.554.
- **The measured invariant holds.** Text-in and audio-in are 86-90%, thinking
  2-3%.
- **Verdicts on the open defect beads, from the sim-user runs:**
  - r3ham.9 was a harness artifact.
  - r3ham.11, .13 and .16 did not reproduce.
  - r3ham.10 is real but mild: the model leaves the physical address blank
    "because it is the same as mailing", which matches the kit's own wording.
- **New model defects filed:** r3ham.23 (an internal instruction spoken
  aloud, 1 in 45 spellbacks) and r3ham.24 (3 wrong stored values confirmed;
  one phone number read-back where the transcript and the audio disagreed).
- **Docs updated:** the measured cost invariant in
  `docs/standards/logging-and-cost.md`, its one-line restatement in
  CLAUDE.md, and the 3.8 sections of both pitch READMEs. The pitch updates
  are consequence-bearing, so the maintainer merges this PR.

## Lessons

- **Check that a comparison is the same FORM before quoting it.** The first
  draft said the measured $3.55 I-90 "lands in the pitch's $3.2-3.5
  estimate". That estimate came from the older 113-question I-90. The run was
  the current 57-question kit, whose 2.5 reference is $2.06 (bd `2nikx`). The
  number matched by coincidence. The tell was a figure that agreed too
  neatly with an extrapolation from a different base.
- **Audit every override a deterministic judge makes, not a sample.** The
  per-turn audit of all 14 referee overrides found the one wrong one (a
  two-read-back window). It became the PR #938 abstain rule.
- **A free TTS endpoint is a single point of failure for a 30-minute live
  run.** It killed two sessions until the retry (bd `ya4vi.5`).

## Doc freshness

- `docs/standards/logging-and-cost.md`: the invariant prose and the stamp
  are updated. It still carries 6 older stacked stamps, a pre-existing
  violation the checker flags; this branch did not add them.
- CLAUDE.md: one clause in the token/cost trigger row is updated.
- The other stale docs `closeout_prep` reports track files this branch does
  not touch.

## Files touched

- `scripts/spikes/sim_user_findings.md` (new).
- `scripts/spikes/data/sim_user/bench/` (new; 11 runs, 55 files).
- `scripts/spikes/data/sim_user/RUNS.md`.
- `docs/standards/logging-and-cost.md`, `CLAUDE.md`.
- `pitch/i90-stress-test/README.md`, `pitch/naive-vs-mitigated-cost/README.md`.
