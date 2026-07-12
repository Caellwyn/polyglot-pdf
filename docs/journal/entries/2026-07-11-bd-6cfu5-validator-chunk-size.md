---
date: 2026-07-11
bead: polyglot-pdf-6cfu.5
title: "Validator accuracy vs chunk size: keep windows section-sized (~20 fields); big windows do not buy cross-section coverage"
tags: [extractor, performance, testing]
---

## Trigger

Sprint 10, re-scoped by maintainer direction 2026-07-10: with the validator
being DECOUPLED from display sections (async, corrections queued for page
end -- bd polyglot-pdf-wt6w, now a sprint-11 child), the question is no
longer "re-test at the new section boundaries" but "what CHUNK SIZE should
the validator see, independent of sections?" Measured with the existing
validated instrument: the i-90 g1b corpus (hand-authored coherent persona
key, bd wf3q) through `backend/scripts/probe_g1b_model_size_bakeoff.py`,
re-run 2026-07-11 on Vertex (ADC; AI Studio credits remain depleted -- the
probe gained an env-gated `VERTEXAI=true` client path, default unchanged).
Run: 2 models x 3 sizes x 29/36/42 cases = 214 calls, zero transport errors.
Data: `scripts/spikes/data/g1b_bakeoff_20260711T113352.csv` (+ meta).

## Results (recall r / precision p; latency p50; mean cost per call)

| model | 20 fields (~section) | 40 (~page) | 132 (whole form) |
|-------|----------------------|------------|-------------------|
| gemini-2.5-flash-lite (deployed) | r 1.000 / p 0.889 / 0.54s / $0.0001 | r 0.810 / p 0.944 / 0.58s / $0.00016 | r 0.778 / p 0.955 / 0.60s / $0.00033 |
| gemini-2.5-flash | r 1.000 / p 1.000 / 10.4s | r 1.000 / p 1.000 / 15.5s | r 0.889 / p 0.960 / 29.4s |

Recall by contradiction DISTANCE (pooled): lite catches near pairs well
(0.896 at distance 1-5, 1.000 at 6-20) but FAR pairs (21+ apart) only 0.333;
flash only 0.500. The `duration_years` class is caught by NEITHER model
(0.000) -- a known-hard class, unchanged from June.

Versus the June baseline (AI Studio, merged multi-run): lite PRECISION
improved sharply at every size (0.73/0.66/0.66 -> 0.89/0.94/0.955) while
PAGE-SIZE recall regressed (1.00 -> 0.81 at 40); section-size recall is 1.00
in both datasets; whole-form recall slipped slightly (0.840 -> 0.778, June
scored under the probe's transport-error-excluding rule). Reading: the serving
path/model refresh shifted lite toward conservatism -- fewer false flags,
more misses in bigger payloads. (Caveats: today = one run per cell vs the
baseline's pooled repeats; June = AI Studio vs today = Vertex.)

## Recommendation (feeds wt6w's page-end design)

1. **Keep validator payloads section-sized (~20 fields) on the deployed
   flash-lite tier.** It is the only cell with recall 1.00 in both datasets,
   at p50 0.54s (fits the 4s backend timeout with margin) and $0.0001/call.
2. **Page-end triggering should still SEND ~20-field windows** -- trigger at
   the page boundary, but chunk the page payload into <=2 windows and make
   two calls (cost is negligible, calls parallelize). A single page-sized
   window costs ~19% recall on the deployed tier.
3. **Do not buy cross-section coverage with bigger windows** -- far-pair
   recall is 0.33 (lite) / 0.50 (flash) even given the whole form. Layered
   defense (read-back, human review) or targeted pair-checks are the honest
   mechanisms for far-apart contradictions, not a monster window.
4. **Do not "just upgrade to flash" at the boundary**: on Vertex today its
   p50 is 10-30s (default thinking budget), far beyond the 4s validator
   timeout and the 6s frontend gate. If flash is ever wanted here, it needs
   an explicit thinking-budget=0 measurement first.

## Deviation from the re-scoped criteria (defended)

The re-scope note said ">=3 chunk sizes on >=2 forms"; this ran 3 sizes on
ONE form. The i-90 corpus is the only validated instrument (the wf3q lesson:
a naive second-form key manufactures contradictions and corrupts precision).
The size-curve question -- the decision wt6w needs -- is answered decisively
on the controlled instrument; a second form controls for form-specific
artifacts and is filed as its own bead (`polyglot-pdf-z2l9`,
second-form answer key) rather than blocking this measurement on days of
key-authoring.

## Files touched

- `backend/scripts/probe_g1b_model_size_bakeoff.py` (env-gated Vertex client
  path; AI Studio default unchanged)
- `scripts/spikes/data/g1b_bakeoff_20260711T113352.csv` + `.meta.json` (run
  data, committed per the spike-data convention)
- this journal entry
