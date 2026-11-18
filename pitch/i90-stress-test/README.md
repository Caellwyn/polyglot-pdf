# I-90 full-system stress test -- investor source material

Everything the pitch needs from the 2026-07-14 stress-test series, in one place.
Source of record for the numbers below is the epic `polyglot-pdf-00pt` run
artifacts; this folder is a copy for pitch compilation.

> **2026-11-18:** production now runs `gemini-3.8-live`. The figures below are the
> 2.5 record. Read the dated update at the end before quoting any number.

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

## 2026-11-18 update: the production model is now gemini-3.8-live

The numbers above were measured on **gemini-2.5 native audio**, the production model in July 2026. They stay here as the prior record. The production voice model is now `gemini-3.8-live`; 2.5 retires on Vertex on 2026-12-13.

Epic `polyglot-pdf-r3ham` re-measured on 3.8. What the pitch can and cannot say today:

- **There is no measured full-I-90 figure on 3.8 yet. Do not quote one.** All three 3.8 runs of the current I-90 kit stopped early, at questions 42, 36 and 23 of 57. The model fell out of step at the "same as mailing address" question (bd `polyglot-pdf-r3ham.10`), and once at the first Part 3 question (bd `polyglot-pdf-r3ham.16`). That is a fix to make, not a cost finding. The ~16 minutes and $2.44 above are 2.5 numbers.
- **On a like-for-like form, 3.8 costs about 30% more than 2.5.** The full 22-field W-7, ideal user, 3 runs each, same script:

  | | $ / form | Fields correct | First-audio latency p50 (LOCAL) |
  |---|---|---|---|
  | 3.8 | $0.905 ($0.87-0.94) | 21, 21, 21 of 22 | 1.16 s |
  | 2.5 | $0.697 ($0.67-0.74) | 19, 22, 21 of 22 | 1.31 s |

  The increase comes from three things: 3.8's higher text-input price (1.5x), its longer spoken replies, and its "thinking". Source: `scripts/spikes/3p8_cost_bench_findings.md`.
- **The I-90 estimate is an EXTRAPOLATION, not a measurement.** Applying the W-7 ratio to the $2.44 above gives about **$3.2 per full I-90 on 3.8**. That is an order-of-magnitude guide only, until a 3.8 I-90 completes.
- **Context compression fires on 3.8 as it did on 2.5** (12-16 trims per W-7). That is what kept 2.5's cost linear in form length; linear cost on a full 3.8 I-90 is NOT yet measured.
- **Multilingual still holds on 3.8.** A 14-question W-7 slice in Spanish, Chinese, Hindi, Russian and Arabic was spoken in the right language on every question, with 13-14 of 14 fields correct (`scripts/spikes/3p8_quirk_retest_findings.md`).
- **Error-catching:** the cheap helper model moved to `gemini-3.1-flash-lite` with no loss.
  - Planted-contradiction recall is 1.000 (68 of 68).
  - The form secretary's judged hallucinations went down: 1 of 49, against 5 before (`scripts/spikes/3p1_lite_revalidation_findings.md`).
- **Latency:**
  - Every number above is still LOCAL.
  - The first deployed 3.8 telemetry is one staging session (`scripts/spikes/3p8_deployed_telemetry_findings.md`). That is too few to quote, and the demo still runs 2.5.
  - Quote it as "about 1.2 s measured locally; deployed latency not yet measured on 3.8", or give no hard number.
