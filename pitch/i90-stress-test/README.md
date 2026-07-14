# I-90 full-system stress test -- investor source material

Everything the pitch needs from the 2026-07-14 stress-test series, in one place.
Source of record for the numbers below is the epic `polyglot-pdf-00pt` run
artifacts; this folder is a copy for pitch compilation.

## What's here

| File | What it is |
|---|---|
| `systems_stress_findings.md` | The full findings doc. **Start with its "Executive verdict" and "Investor-facing summary" sections** -- those are the pitch-ready synthesis. Data sections below them are the artifact-true backup. |
| `charts/e1_marginal_cost_per_question.svg` | The money chart: marginal cost per question is FLAT (~$0.021) across all 113 questions of a full I-90, 3 runs overlaid. |
| `charts/e1_cumulative_cost.svg` | Cumulative cost is LINEAR in form length (vs the super-linear curve before compression). |
| `data/*.summary.json` | All 25 runs' headline metrics (cost, fill accuracy, validator P/R, secretary/nav latency, error taxonomy). |
| `data_manifest.md` | Index of the 25 runs: which phase, path, language, cost, accuracy each is. |

## The five numbers most likely to matter for a pitch

1. **$2.44 +/- $0.04 all-in per full I-90** (voice + AI helpers), ideal user, 3 runs.
   Realistic session ~$3; worst-case (every answer corrected) ~$5.2-5.4.
2. **~16 minutes** to fill a complete I-90 by voice, hands-free.
3. **Flat marginal cost** ($0.021/question, questions 1 through 113) -> cost is
   LINEAR in form length. Longer forms cost proportionally, not exponentially, more.
4. **Multilingual holds:** Spanish fill accuracy 88.5% vs English 85.8% -- same,
   at the same cost. (One full Spanish run; more languages are a fixtures-only add.)
5. **Error-catching works:** the cheap validator caught 100% of planted near-form
   contradictions AND one real transcription error in the wild; the deep
   whole-form check (gemini-2.5-pro) costs $0.0045 and 6.6s.

## Honesty notes the pitch should carry (so claims survive scrutiny)

- Fill accuracy (~86%) is PRE-review: the user confirms every field by voice as
  they go, and the validator adds a cross-field net on top. It is not "86% of
  forms are perfect unattended."
- ~2-3 points of the reported miss rate are SCORER artifacts (date formats,
  "Houston, TX" vs "Houston, Texas"), not model errors -- true accuracy is
  slightly higher.
- **Latency in the findings doc is LOCAL and OVERSTATES the deployed product**
  (the deployed backend is co-located with the model in us-central1). Turn
  cadence was ~1.3s p50 LOCALLY; deployed is faster but the exact number is NOT
  yet captured -- the deployed demo verified GO (loads, connects, streams, no
  1011) but a full voice turn can't be driven headlessly (production build
  strips the test hooks; no mic in the measurement env). For a pitch: state
  latency as "~1.3s locally, faster in production" or omit a hard number until
  the deployed capture lands (follow-up bead). Do NOT quote local latency as
  the product's latency.
- Sample size is 3 runs per arm. Ranges, not just means, are in the data.

## Known issues found (not blockers, filed as beads)

The series found 9 fixable issues (bead ids in the findings doc's problem-case
inventory). The pitch-relevant framing: none are architectural -- they are model
prompting / scorer / kit-hygiene fixes, each with a measured baseline to verify
a fix against. The one with product consequence is a checkbox occasionally being
checked when the user declined it (bd cx23).
