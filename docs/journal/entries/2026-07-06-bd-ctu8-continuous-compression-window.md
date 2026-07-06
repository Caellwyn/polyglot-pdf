---
date: 2026-07-06
bead: polyglot-pdf-ctu8
title: "Continuous DTI compression-window research: recommend window 3500, replaces section resets"
tags: [performance, conventions]
---

## Trigger

With the DTI reliability bugs fixed (choa/ezg2/8vy3, PR #321), a continuous DTI
voice session finally fills the I-90 cleanly with no section resets. ctu8 asks:
what compression window replaces the section-reset mechanism -- cheaper AND
coherent? Compression windows and section resets both bound the ~quadratic
per-turn cost growth; the hypothesis is that one continuous session + a window is
simpler and more coherent than chopping the form into sections.

## What shipped

A research finding + the analysis tooling to reach it (no runtime code changed):

- **Recommendation: compression window ~3500 (trigger pinned at 5000).** On the
  real I-90 (Vertex, continuous DTI, happy path) 3500 is both the most coherent
  window tested (73-93% fill, mean 83%, 2 runs, zero errors, 7-8 evictions each)
  AND cheaper (~$1.15 projected per 174-question form) than the section-reset
  baseline it replaces (~$2.32, go/no-go brief bd 6x1y). GO on window-replaces-
  sections.
- **The counterintuitive elbow:** a TIGHTER 3000 window is NOT cheaper -- it
  evicts so aggressively it strips the DTI per-field guidance (fill drops to 47%)
  while cost does not fall. 3500 is the floor of the coherent band, not a point on
  a smooth memory-vs-cost tradeoff.
- **The production knob (the trap):** for the always-clamped I-90, set the window
  via `CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS = 5000 - W = 1500`, NOT
  `WINDOW_HEADROOM_TOKENS`. The Vertex trigger clamp (>=5000) re-tunes the window
  to `trigger - margin`, so headroom is a no-op on any form whose derived trigger
  is below 5000. (Headroom IS the lever on a future form whose unclamped trigger
  already exceeds 5000 -- the correct knob is form-dependent.)
- **`scripts/spikes/analyze_continuous_window.py`** (new): the stock
  `cost_matrix_lib.load_matrix` cannot ingest the continuous runs -- it hard-
  requires exactly 20 questions (these are 30-34) and keys runs by
  (model,arm,path) so it collides every window cell. The new analyzer reads the
  `dti_cont_comp` runs keyed by (trigger,window), fits per-question growth +
  post-eviction steady level from the CSV's MEASURED per-question text-in series
  (NOT the per-event prompt_curve, which over-projects ~1.4-1.6x), and projects
  cost-per-form with a saturating-ramp model. Reuses `cml.RATES` for pricing.
- **`scripts/spikes/ctu8_window_findings.md`** (new): the product-owner writeup.

Fresh-eyes assess: (recorded at closeout).

Spend discipline: built + validated the whole pipeline on the 5 already-committed
runs (zero API cost), then spent ONE new live run (~$0.65) to add the 3000 point.
Per maintainer budget call ("stop now, recommend 3500"), did NOT measure a 4000
point or re-measure the section-reset baseline on current code -- the go decision
is a 2-point curve, well-supported but not a full 3-point elbow.

## Lessons

- **A projection needs a model-vs-measured honesty check or it lies.** The first
  cost projection over-read by 1.4x because it reconstructed per-question cost
  from the per-event prompt curve instead of the CSV's already-summed per-question
  text-in. The fix: fit growth + steady-state directly from the measured
  per-question series, and print the modeled-vs-measured ratio at the run's own
  length (3500 fits at 1.00; the pre-clamp 2800/2200 cell self-flags at 2.40
  because only 1/3 runs evicted). Never trust an extrapolation whose base doesn't
  reproduce the measurement it came from.
- **Reuse has a shape contract.** "Reuse cost_matrix_lib" looked free but its 20-
  question / arm-keyed ingest layer was built for the old section matrix and could
  not read continuous window-swept runs at all. The projection MATH was reusable;
  the ingest layer was not. Verify the contract before planning on the reuse.

## Doc freshness

`check_doc_freshness.py` flagged `voice-ai.md`, `ws-protocol.md`, and
`technical_guide.md` STALE. These went stale from the DTI-fix + GoAway commits on
`dev` (PR #321/#331, 2026-07-05), whose tracked files (`live_ai_gemini.py`,
`websocket_routes.py`, `webFormConnection.ts`, `config.py`) this branch did NOT
touch -- so they are out of scope for this PR (the closeout rule: a stale doc
tracking files your branch didn't change was already stale before you). This
branch changed only `scripts/spikes/` (untracked by any doc). No doc bump owed
here.

## Files touched

`scripts/spikes/analyze_continuous_window.py` (new),
`scripts/spikes/ctu8_window_findings.md` (new),
`scripts/spikes/data/costs_i90_2.5_dti_cont_comp_happy_20260706T044639Z.{csv,meta.json}`
(the one new run), this journal entry. No backend/frontend runtime code.
