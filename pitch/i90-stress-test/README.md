# I-90 full-system stress test -- investor source material

Everything the pitch needs from the 2026-07-14 stress-test series, in one place.
Source of record for the numbers below is the epic `polyglot-pdf-00pt` run
artifacts; this folder is a copy for pitch compilation.

> **2026-11-20:** the voice model is now `gemini-3.8-live`, on the investor demo too
> since its 2026-11-20 (UTC) redeploy at commit 0c41754c1 (Cloud Build 019f3587, SUCCESS). The figures below are the 2.5 record. Read the 3.8
> section at the end before quoting any number.

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

## gemini-3.8-live figures (measured 2026-11-18 to 2026-11-20)

The numbers above were measured on **gemini-2.5 native audio**, the production model in July 2026. They stay here as the prior record. The voice model is now `gemini-3.8-live`, and the investor demo has served it since its 2026-11-20 (UTC) redeploy at commit 0c41754c1 (Cloud Build 019f3587, SUCCESS). 2.5 retires on Vertex on 2026-12-13.

Epic `polyglot-pdf-r3ham` and bd `polyglot-pdf-15j9v` re-measured on 3.8. What the pitch can say today:

- **A full I-90 on 3.8 costs about $3.55 and completes.** Measured with a simulated applicant who listens, answers and corrects, n=3: **$3.55 per I-90 ($3.28-3.87)**. All 57 fields were filled and confirmed in every run, and 54-57 of 57 matched the answer sheet exactly. That is about $0.06 per correct field. Two of the five misses were formatting only ("the Philippines" for "Philippines"). Source: `scripts/spikes/sim_user_findings.md`.
  - **This is the current 57-question I-90 kit (`i-90_v2`), not the 113-question form of the 2.5 stress test above.** So do not set $3.55 against $2.44, the flat $0.021 per question, or the earlier "about $3.2 on 3.8" extrapolation (which was built from the 113-question figures). The closest 2.5 reference on the current kit is **$2.06 per I-90** (bd `polyglot-pdf-2nikx`, 2026-08-28, fixed-script user). That is still not like-for-like: the user model differs, three months of code changes sit between the runs, and its accuracy was scored by an older, lenient scorer, so do not compare accuracy figures.
  - An earlier fixed-script user never let a 3.8 I-90 finish. That user always said yes and never answered a spelling request, so the failures were mostly the script's, not the model's. With a responsive user, the "same as mailing address" question (bd `polyglot-pdf-r3ham.10`) costs 3-8 extra turns but no longer derails the session.
  - The ~16 minutes and $2.44 above are 2.5 numbers. Do not quote a 3.8 I-90 duration from these runs: the simulated user's own thinking and speech time inflate the wall clock.
- **Per form, with the same simulated applicant (3.8, n=3 each):**

  | Form | $ / form | Fields correct |
  |---|---|---|
  | W-7 (22 fields), happy path | $1.06 ($1.03-1.10) | 22, 22, 22 of 22 |
  | W-7, every answer wrong once, then corrected | $1.57 ($1.39-1.72) | 22, 22, 22 of 22 |
  | I-90 (57 fields), happy path | $3.55 ($3.28-3.87) | 55, 57, 54 of 57 |

  Every correction a user made was caught and fixed. Corrections cost about 50% more than a smooth session.
- **On a like-for-like form, 3.8 costs about 30% more than 2.5.** The full 22-field W-7, fixed-script user, 3 runs each, same script:

  | | $ / form | Fields correct | First-audio latency p50 (LOCAL) |
  |---|---|---|---|
  | 3.8 | $0.905 ($0.87-0.94) | 21, 21, 21 of 22 | 1.16 s |
  | 2.5 | $0.697 ($0.67-0.74) | 19, 22, 21 of 22 | 1.31 s |

  The increase comes from three things: 3.8's higher text-input price (1.5x), its longer spoken replies, and its "thinking" (about 3%). Thinking is priced from the model's reported token counts. The one reconciled 3.8 billing day did NOT show thinking as billed text output (n=1, `scripts/spikes/3p8_deployed_telemetry_findings.md`), so treat that line as an upper bound. Source: `scripts/spikes/3p8_cost_bench_findings.md`.
  - The responsive applicant costs more per W-7 than the fixed script ($1.06 vs $0.905), because fuller answers and answered spelling requests add audio. Quote the simulated-applicant figures as the realistic ones, and the fixed-script table only for the 3.8-vs-2.5 comparison.
- **Open accuracy defects to know about before a demo** (both filed):
  - Once in 45 spelling read-backs, the model spoke an internal instruction aloud (bd `polyglot-pdf-r3ham.23`).
  - In 3 of the 171 I-90 fields, the model stored a different value than the user said, and it was confirmed (bd `polyglot-pdf-r3ham.24`). One was a phone number whose spoken read-back and on-screen transcript disagreed.
  - Both are I-90-only so far, and the reviewing professional sees the draft before filing.
- **Context compression fires on 3.8, about twice as often as on 2.5** (12-16 trims per W-7 vs 6), because 3.8's longer speech fills the window faster. That is what kept 2.5's cost linear in form length. On 3.8, with the simulated applicant, the 57-question I-90 costs about 3.4x the 22-field W-7, for 2.6x the fields, and audio-in is a larger share of it (~50% vs ~42%). Why it grows faster than the field count is not decomposed yet.
- **Multilingual still holds on 3.8.** A 14-question W-7 slice in Spanish, Chinese, Hindi, Russian and Arabic was spoken in the right language on every question, with 13-14 of 14 fields correct (`scripts/spikes/3p8_quirk_retest_findings.md`).
- **Error-catching:** the cheap helper model moved to `gemini-3.1-flash-lite` with no quality regression. The trade-offs are small: about 0.15 s slower at the median, about 2.6x the cost per secretary call of the earlier `gemini-2.5-flash-lite` (still below the `gemini-2.5-flash` that deployed helper calls actually ran on before), and occasional HTTP 429 rate-limit replies under load, which the app treats as transient.
  - Planted-contradiction recall is 1.000 (68 of 68).
  - The form secretary's judged hallucinations went down: 1 of 49, against 5 before (`scripts/spikes/3p1_lite_revalidation_findings.md`).
- **Latency:**
  - Every number above is still LOCAL.
  - Local first-audio latency is unchanged by a realistic user: 1.16-1.20 s median and 1.34-1.47 s p90 across all three simulated-applicant groups.
  - The first deployed 3.8 telemetry is one staging session (`scripts/spikes/3p8_deployed_telemetry_findings.md`). That is too few to quote.
  - Quote it as "about 1.2 s measured locally; deployed 3.8 latency so far comes from one staging session, too few to quote", or give no hard number.
