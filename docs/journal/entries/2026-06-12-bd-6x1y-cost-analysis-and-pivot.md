---
date: 2026-06-12
bead: polyglot-pdf-6x1y
title: "Cost-analysis notebook + elbow analysis -> DECISION: shelve the sliding window, pivot to SI reduction via delegation"
sprint: 4
tags: [performance, postmortem, doctrine]
---

## Trigger

Final bead of the sprint-4 epic `polyglot-pdf-hcsl`. The maintainer asked for
the wyhh matrix as an interactive Jupyter notebook -- visual + prose analysis,
cost/benefit, recommendations -- with a HARD gate: all analysis code reviewed
by fresh-eyes BEFORE its outputs are trusted ("too many AIs base analysis on
broken analysis code"). The notebook is the decision surface for the epic's
go/no-go.

## What shipped

- **Analysis library** (`scripts/spikes/cost_matrix_lib.py`): all computation
  in reviewable functions -- tidy loaders with per-question validity rules
  (dead = all turns stalled), self-validating cost recomputation, a
  data-derived chars->tokens calibration, a best-case sliding-window cost model
  with a model-vs-measured honesty check, and a section-reset extrapolation
  over the real 15-section schema. **3 adversarial review rounds** (the
  maintainer's gate): round 1 caught a window-model formula error
  (29% understatement) + a mispaired calibration anchor; round 2 caught a
  sign-flipping comparison-span mismatch + a global-state leak; round 3
  verdict TRUSTED (one purity fix applied). A 4th pass on the notebook layer
  caught stale prose dollar figures from a pre-fix scratch run.
- **Notebook** (`scripts/spikes/cost_matrix_analysis.ipynb`, executed,
  outputs baked): interactive plotly dashboards (cost race, cost sources,
  context-length distributions, latency, window-model honesty check,
  whole-form what-if explorer with a retained-memory elbow + mix table, a
  live-kernel slider), prose analysis + recommendations.
- **Tidy exports** (`scripts/spikes/data/tidy_*.csv`) + the plain-language
  **go/no-go brief** (`docs/sliding-window-go-no-go-brief.md`).
- **Maintainer review of the notebook surfaced real defects** (a model
  feedback loop the gate is designed to catch), all fixed in the final commit:
  - The **section-4 chart mislabeled drops by ARM.** Replaced with a
    MECHANISM-based classifier (`_classify`, by where the drop lands vs the
    run's SI floor): `session_restart` / `audio_context_dip` (3.1-only) /
    `compression_eviction` / `billing_noise`. The reclassification is
    self-evident in the baked output: 2.5 has 0 audio dips, 3.1 has 56, and
    there are **ZERO real compression evictions anywhere** -- the 12k/9k
    window never fired.
  - **3.1's cost is re-billed AUDIO context (~50x 2.5 at peak), not thinking
    tokens** -- the part-2 prose was corrected (3.1 retains conversation audio
    in context; text-out is literally 0).
  - **Latency parity is a LOCAL-harness artifact**, not production: the harness
    measures activity-end -> first audio byte on injected audio over a local
    backend; the earlier live-demo "3.1 much slower" finding stands. Flagged
    loudly in the notebook.
  - **Schema scope stated:** the harness fills 3 of 15 sections (20 questions);
    whole-form figures are modeled extrapolations.

## The decision (maintainer, 2026-06-12)

**SHELVE the sliding window. PIVOT to system-instruction reduction via task
delegation.** Evidence, all from the notebook: text-in is 95-98% of 2.5 cost;
the SI is the lever and the window size is nearly irrelevant; the 12k/9k window
saved ~0-2% (vs section resets' ~45%) and never actually evicted; compression
cannot touch the SI and does not solve the ~13-15 min duration GoAway. Modeled
whole-form (174q, 80/20, text-in): sections ~$2.32, full-dump window ~$2.38
(no better), JIT window ~$1.34, drip window ~$0.86 -- the schema-feeding
strategy is the 2-5x lever, not the window.

The pivot direction (live model focused on the current field + a cheap
flash-lite-class model validating completed sections/forms, collapsing the SI
toward the drip-in floor) is consolidated for the next epic in the P0 planning
bead **`polyglot-pdf-pivot1`**; planning deferred to a strong-model session.
Recorded on the epic bead and in bd memory
`sliding-window-shelved-pivot-to-si-diet`.

## Lessons

- **The analysis-code review gate paid for itself five times.** Across the
  library and notebook, adversarial review caught a 29% formula error, a
  mispaired anchor, a sign-flip, a state leak, and a mislabeled headline chart
  -- every one of which would have put a wrong number or wrong picture in front
  of a decision. "Review the analysis code before trusting the analysis" is now
  a repo standard for any decision-grade notebook.
- **Classify by mechanism, not by container.** The arm-based drop label was
  plausible and wrong; only "where does the drop LAND" separated 3.1's intrinsic
  audio sawtooth from real restarts and (absent) evictions.
- **Name which cap you're lifting and which model you're measuring.** "3.1 is
  expensive because of thinking tokens" and "compression lifts the 15-min cap"
  were both confidently wrong; the data said audio-context re-billing and a
  separate duration wall.

## Doc freshness

- New: `docs/sliding-window-go-no-go-brief.md`,
  `docs/journal/entries/2026-06-12-bd-6x1y-cost-analysis-and-pivot.md` (this).
- `docs/components/context-compression.md` already carries the epic's measured
  findings (bumped under 4loz/wyhh); the shelve decision lives on the epic bead
  + the pivot1 planning bead + bd memory, not in a tier-1/2 doc (no current-
  state behavior changed -- the flag stays False).
- Pre-existing dev-side staleness (sprint-3 backend files this branch never
  touched) is out of scope, as recorded in the h04c/4loz entries.

## Files touched

- `scripts/spikes/cost_matrix_lib.py` (new) -- analysis library
- `scripts/spikes/cost_matrix_analysis.ipynb` (new) -- executed notebook
- `scripts/spikes/data/tidy_{questions,turns,curves,runs}.csv` (new)
- `docs/sliding-window-go-no-go-brief.md` (new)
- `docs/journal/entries/2026-06-12-bd-6x1y-cost-analysis-and-pivot.md` (this)
