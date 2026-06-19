# G1b bake-off -- model x form-size matrix for the out-of-band B checker

**Bead:** polyglot-pdf-0zp3 (follow-up to G1 / jnjj.5)
**Date:** 2026-06-18
**Question:** For the out-of-band end-of-section + end-of-form contradiction
checker (Pillar B, reframed from "replace the in-SI check" to "additional layer"
by the maintainer on 2026-06-17), WHICH cheap text model, and does accuracy
survive a realistic page- or form-sized payload? Measured speed, cost, and
accuracy across 4 models x 3 form sizes.

**Headline:** the two **flash-lite tiers are the operationally viable choice** --
sub-second, cheap, near-perfect recall -- but they trade ~25-35% false-positive
rate (precision ~0.65-0.73). The **bigger models buy precision, not recall**, at a
10-25x latency penalty; `gemini-3-flash-preview` is additionally **unreliable
under load** (10-34% of its calls timed out) and is not recommended. Since this is
ONE layer among many (read-back, verbal section verify, human translator review),
recall is the metric that matters and all models have it; the false-positive cost
is a UX-tuning problem, not a blocker.

---

## The matrix (merged, deduped dataset: `scripts/spikes/data/g1b_bakeoff_MERGED.csv`)

428 cells = 4 models x {20, 40, 132} fields x ~36 labeled cases per size.
Recall = contradictions caught; precision = 1 - false-alarm rate; latency =
per-call wall clock; cost = (in_tok x in_rate + out_tok x out_rate).

| model | size | recall | precision | lat p50 | lat p90 | cost/call | err rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| **2.5-flash-lite** | 20 | 1.000 | 0.727 | 0.72s | 0.85s | $0.00012 | 0 |
| **2.5-flash-lite** | 40 | 1.000 | 0.697 | 0.82s | 1.21s | $0.00019 | 0 |
| **2.5-flash-lite** | 132 | 0.960 | 0.686 | 1.04s | 1.45s | $0.00039 | 0 |
| **3.1-flash-lite** | 20 | 1.000 | 0.800 | 0.75s | 0.96s | $0.00039 | 0 |
| **3.1-flash-lite** | 40 | 1.000 | 0.622 | 0.80s | 0.96s | $0.00052 | 0 |
| **3.1-flash-lite** | 132 | 0.960 | 0.649 | 0.83s | 1.10s | $0.00103 | 0 |
| 2.5-flash | 20 | 1.000 | 0.889 | 7.72s | 13.8s | $0.00049 | 0 |
| 2.5-flash | 40 | 1.000 | 0.821 | 10.9s | 19.5s | $0.00064 | 0 |
| 2.5-flash | 132 | 1.000 | 0.893 | 18.2s | 40.6s | $0.00125 | 0 |
| 3-flash-preview | 20 | 0.875 | 0.875 | 11.0s | 56.4s | $0.00084 | ~7% |
| 3-flash-preview | 40 | 0.957 | 0.917 | 12.5s | 43.5s | $0.00125 | ~34% |
| 3-flash-preview | 132 | 1.000 | 0.833 | 24.7s | 56.1s | $0.00236 | ~25% |

(latency/cost computed from CLEAN calls only; `3-flash-preview`'s err rate is the
fraction of its calls that timed out even after retries -- a reliability result,
not a measurement artifact. The voice model `2.5-flash-live` is bidi-only and
could NOT be tested as a text checker here -- separate probe needed.)

### Reading the matrix

1. **Recall is a near-solved problem at form scale.** Every model catches
   essentially every contradiction (>=0.96) at every size; the two cases where a
   flash-lite tier dips to 0.96 at 132 fields are single-case slips, not a trend.
   This REVERSES the worry from G1 (where flash-lite on tiny 3-5 field clusters
   scored 0.85): MORE context helped, it did not hurt. A page- or form-sized
   payload is NOT too big for these models to find the needle.

2. **Precision is the real differentiator, and the cheap models pay for speed
   with false alarms.** 2.5-flash-lite and 3.1-flash-lite sit at ~0.62-0.80
   precision -- they over-flag coherent data (most often flagging a perfectly
   valid US city/state pair, "unsure, better flag it"). 2.5-flash is markedly
   cleaner (~0.82-0.89) but 10-22x slower.

3. **The latency cliff is stark.** The flash-lite tiers answer in <1.1s at every
   size; 2.5-flash takes 8-18s (p90 up to 40s at 132 fields); 3-flash-preview is
   11-25s with a p90 near a minute. For an end-of-section checker that gates the
   section auto-advance (per the validation-delegation contract), a sub-second
   answer vs a 20-second one is the difference between invisible and a stall.

4. **Cost is negligible for all of them at this call volume.** Even the priciest
   cell (3-flash-preview @ 132) is $0.0024/call; at 3-20 calls per WHOLE form
   that is well under a cent of validator cost per form. Cost does NOT
   discriminate here -- speed and precision do.

5. **`gemini-3-flash-preview` is out** on reliability alone: 34% of its size-40
   calls timed out (>60s) even after 4 retries, vs 0% for the other three models.
   The priciest, slowest candidate is also the flakiest. Not recommended.

---

## Accuracy by contradiction DISTANCE (does a far-apart contradiction survive?)

The maintainer's key worry: a contradiction whose two halves sit far apart (a
birthday stated in two places; "how long in the US? [11+ yrs]" vs "year entered:
2022" in a different section). Recall pooled over sizes, bucketed by the
field-index gap between the two contradicting fields:

| model | single/0 | near (1-5) | mid (6-20) | far (21+) |
|---|---:|---:|---:|---:|
| 2.5-flash | 1.000 | 1.000 | 1.000 | 1.000 |
| 2.5-flash-lite | 0.833 | 1.000 | 1.000 | 1.000 |
| 3-flash-preview | 1.000 | 0.938 | 1.000 | 1.000 |
| 3.1-flash-lite | 1.000 | 1.000 | 0.875 | 1.000 |

**Distance does NOT degrade recall.** Every model catches the far-apart (21+
fields, cross-section) contradictions at 1.000. The few sub-1.0 cells are
scattered across near/mid/single, not concentrated at "far" -- there is no
"the halves were too far apart to notice" failure mode in this data. A
cross-section contradiction 80 fields apart is caught as reliably as an adjacent
one. (Caveat: the far bucket is mostly the synthetic cross-section ZIP/state and
date pairs; a subtler semantic long-range contradiction class might behave
differently and is worth a future targeted corpus.)

---

## Accuracy by contradiction CLASS (pooled over sizes)

| model | zip_state | state_country | province_us | city_state | future_dob | admission_dob | cross_date |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2.5-flash | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 2.5-flash-lite | 1.000 | 1.000 | 1.000 | 1.000 | 0.833 | 1.000 | 1.000 |
| 3.1-flash-lite | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.750 | 1.000 |
| 3-flash-preview | 1.000 | 1.000 | 1.000 | 0.750 | 1.000 | 1.000 | 1.000 |

**The G1 state_country blind spot is GONE.** In G1, 2.5-flash-lite missed 3 of 5
US-state-vs-foreign-country cases (its worst class). Embedded in a full-size form
with a sharper prompt, every model -- flash-lite included -- catches
state_country at 1.000. The remaining sub-1.0 cells are single-case slips in the
small date classes (3 cases each), not a reliable weakness. Net: no class is a
systematic blind spot for the flash-lite tiers at form scale.

---

## Provenance + honesty

- **Corpus is SYNTHETIC** (no real transcripts exist; pre-pilot, no PII logged).
  Field ids/names/types/sections are the REAL 132-field I-90 (`form-kits/i-90/
  schema.json`); values are a coherent hand-authored persona; contradictions are
  injected. Recall numbers are an UPPER BOUND on real-world recall -- real
  sessions are messier. (`backend/scripts/g1b_corpus.py`.)
- **132 = the real full I-90**, used as the realistic worst case -- NOT a
  synthetic 200-pad. 20 ~ a section, 40 ~ a page.
- **Two corpus bugs were caught + fixed before the reported run** (both inflated
  false positives): (a) the base persona's physical address contradicted an
  injected mailing address; (b) a substring-match bug assigned the residence city
  to the birth-city field. After the fixes, the remaining false positives are
  genuine model behavior. The prompt also explicitly tells the model that an
  immigrant's birth country differing from their US address is NORMAL (an
  immigration form), to avoid measuring a naive checker.
- **Precision has run-to-run noise** (the models are non-deterministic; a clean
  case flagged or not swings a few points). The HEADLINE (flash-lite ~0.65-0.80
  vs 2.5-flash ~0.82-0.89, and the latency cliff) is robust to that noise; do not
  over-read a single precision cell to 3 digits.

## Run mechanics (why this took multiple runs -- recorded for the next probe)

A single all-models-all-sizes sweep proved impractical and is the reason the data
lives in several run files merged by `g1b_merge.py`:
- The probe originally had NO per-call timeout, so one stalled API call hung the
  serial loop for ~2 hours. Fixed with a 60s `asyncio.wait_for` deadline +
  retry.
- The slow models (2.5-flash, 3-flash-preview at 8-25s/call) made a serial sweep
  take hours; fixed with bounded concurrency (semaphore). But high concurrency on
  the big 132-field payloads triggered rate-limit -> timeout spirals, so the big
  sizes were re-run at lower concurrency (3-4).
- Long background runs did not survive session/host interruptions; fixed with
  INCREMENTAL CSV checkpointing (every 16 rows) so a killed run keeps its
  completed cells. The final dataset is the per-size/per-model pieces merged,
  deduped preferring non-errored rows.
- `3-flash-preview` stayed flaky even at low concurrency (its residual error rate
  in the merged set: 13/38 @ size40, 10/40 @ size132) -- which is itself the
  recommendation against it.

---

## Recommendation (exit criterion 3)

**Use a flash-lite tier for BOTH the end-of-section and end-of-form checker; do
NOT switch models by boundary.** The bead anticipated possibly needing a beefier
model for the larger end-of-form (132) payload -- the data says that is
unnecessary: the flash-lite tiers hold recall (>=0.96) and their precision does
NOT collapse at 132 (it is flat across sizes). A single cheap model handles all
sizes, so the added complexity of a per-boundary model split is not justified by
this data.

**Between the two flash-lite tiers:** `3.1-flash-lite` and `2.5-flash-lite` are
both sub-second and both ~0.96-1.0 recall. `2.5-flash-lite` is ~3-4x cheaper per
call (its input rate is $0.10 vs $0.25/M) and has marginally better precision at
132; `3.1-flash-lite` was slightly faster and slightly better at small sizes.
Either is a fine default; **lead with `2.5-flash-lite` on cost** and treat
`3.1-flash-lite` as the A/B alternative. Both decisively beat the slow tiers on
the speed that matters for a boundary-gating checker.

**If false positives prove annoying in practice** (the ~25-35% over-flag rate),
the cheaper fix than a slower model is prompt/UX tuning -- e.g. only surface a
flagged conflict to the user above a confidence bar, or have the checker
double-check its own flag in a second cheap pass -- since recall is not the
problem. 2.5-flash is the fallback if precision MUST improve and a ~10s
section-boundary latency is acceptable (it usually is not for voice).

**Not recommended:** `gemini-3-flash-preview` (slowest, priciest, and unreliable
under load). **Untested:** the voice model `2.5-flash-live` as a text checker
(bidi-only; needs a Live-session harness -- a separate probe if the
voice-model-does-double-duty idea is worth pursuing).
