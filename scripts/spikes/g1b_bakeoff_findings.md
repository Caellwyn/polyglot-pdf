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
under load** (7-39% of its calls timed out) and is not recommended. Since this is
ONE layer among many (read-back, verbal section verify, human translator review),
recall is the metric that matters and all models have it; the false-positive cost
is a UX-tuning problem, not a blocker.

**The voice model itself (`gemini-2.5-flash-native-audio`) was added as a 5th
arm** (the model already running the session, driven text-in via a Live session
in tool-calling mode -- it cannot emit TEXT, so it reports the verdict through a
flat `report_conflicts` tool call; the deeply-nested tool schema first tried
triggered the native-audio 1011 "internal error", a malformed-tool-declaration
symptom, fixed by flattening). It matches 2.5-flash on recall (1.000
at ALL three sizes, after prefix-tolerant re-scoring -- see the matrix note),
precision ~0.76-0.80, and ~6-9s latency (faster than 2.5-flash, far slower than
the lites). It ran with ZERO errors once the tool schema was fixed.
**Rejected** for the checker role: the latency + the Live-session tech debt are not
worth it when a plain unary HTTP call is cheaper, faster, and simpler (full
rationale in the Recommendation). **`gemini-3.5-flash`** was also added (132 only,
the end-of-form sweep): recall 1.000, precision 0.86, but ~4x costlier than
2.5-flash at full rate with no precision gain -- also not preferred.

---

## The matrix (merged, deduped dataset: `scripts/spikes/data/g1b_bakeoff_MERGED.csv`)

575 cells: 4 text models x {20,40,132} + the voice model x {20,40,132} + 3.5-flash
x {132}, ~36 labeled cases per (model x size). Recall = contradictions caught;
precision = 1 - false-alarm rate; latency = per-call wall clock; cost =
(in_tok x in_rate + out_tok x out_rate).

| model | size | recall | precision | lat p50 | lat p90 | cost/call | err rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| **2.5-flash-lite** | 20 | 1.000 | 0.727 | 0.7s | 0.8s | $0.00012 | 0 |
| **2.5-flash-lite** | 40 | 1.000 | 0.688 | 0.8s | 1.1s | $0.00018 | ~3% |
| **2.5-flash-lite** | 132 | 0.960 | 0.686 | 1.0s | 1.4s | $0.00039 | 0 |
| **3.1-flash-lite** | 20 | 1.000 | 0.800 | 0.8s | 1.0s | $0.00039 | 0 |
| **3.1-flash-lite** | 40 | 1.000 | 0.622 | 0.8s | 1.0s | $0.00052 | 0 |
| **3.1-flash-lite** | 132 | 0.960 | 0.649 | 0.8s | 1.1s | $0.00103 | 0 |
| 2.5-flash | 20 | 1.000 | 0.889 | 7.7s | 13.8s | $0.00049 | 0 |
| 2.5-flash | 40 | 1.000 | 0.821 | 10.9s | 19.5s | $0.00064 | 0 |
| **2.5-flash** | 132 | 1.000 | 0.893 | 18.2s | 40.6s | $0.00125 | 0 |
| 3-flash-preview | 20 | 1.000 | 0.941 | 10.2s | 25.7s | $0.00088 | ~7% |
| 3-flash-preview | 40 | 1.000 | 1.000 | 12.9s | 38.3s | $0.00126 | ~39% |
| 3-flash-preview | 132 | 1.000 | 0.833 | 24.7s | 56.1s | $0.00236 | ~25% |
| 3.5-flash | 132 | 1.000 | 0.862 | 11.1s | 39.7s | $0.00553 | 0 |
| voice (2.5-flash-native-audio) | 20 | 1.000 | 0.800 | 6.0s | 8.4s | $0.00045* | 0 |
| voice (2.5-flash-native-audio) | 40 | 1.000 | 0.793 | 7.5s | 9.6s | $0.00068* | 0 |
| voice (2.5-flash-native-audio) | 132 | 1.000 | 0.758 | 9.3s | 15.1s | $0.00165* | 0 |

(latency/cost from CLEAN calls only. PRECISION is CASE-LEVEL: a clean case counts
as 1 false positive if it flags anything, and a contradiction case's EXTRA flagged
groups beyond the expected one are not counted -- so the user-visible spurious-PAIR
rate is HIGHER than (1 - precision) here; the models emit ~1.9-2.6 flagged groups
per correct catch. Read precision as "fraction of validated boundaries that fired
a false alarm," not "fraction of flagged pairs that were wrong." `3-flash-preview`'s
err rate is the fraction of its calls that timed out even after retries. `3.5-flash`
ran only at 132 (the end-of-form sweep) at full input rate (NO context caching
modeled); its list prices ($1.50/M in, ~$6/M out) are unverified. `voice` recall is
1.000 at every size; its detection was re-scored with PREFIX-TOLERANT field-id
matching because the native-audio tool call TRUNCATES ids (`p1_line6e` for
`p1_line6e_state`) -- exact-match scoring wrongly showed 0.875/0.957 at sizes 20/40,
a scoring artifact, not a real miss. `voice` cost `*` = INPUT-ONLY (the Live API
streamed no usable token usage AND the model emits AUDIO whose output tokens are
unmeasured -- true cost is HIGHER).)

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

3. **The latency cliff is stark.** The flash-lite tiers answer in <1.4s at every
   size; 2.5-flash takes 8-18s (p90 up to 40s at 132 fields); 3-flash-preview is
   10-25s (p90 26-56s). For an end-of-section checker that gates the section
   auto-advance (per the validation-delegation contract), a sub-second answer vs a
   20-second one is the difference between invisible and a stall.

4. **Cost is negligible for all of them at this call volume.** Even the priciest
   cell (3-flash-preview @ 132) is $0.0024/call; at 3-20 calls per WHOLE form
   that is well under a cent of validator cost per form. Cost does NOT
   discriminate here -- speed and precision do.

5. **`gemini-3-flash-preview` is out** on reliability alone: 39% of its size-40
   calls timed out (>60s) even after 4 retries, vs ~0% for the other text models.
   The priciest, slowest candidate is also the flakiest. Not recommended. (Its
   accuracy cells -- e.g. precision 1.000 at 40 -- are computed from the FEW calls
   that survived, so they are not reliable comparison numbers; the headline is the
   error rate, not the precision.)

---

## Accuracy by contradiction DISTANCE (does a far-apart contradiction survive?)

The maintainer's key worry: a contradiction whose two halves sit far apart (a
birthday stated in two places; "how long in the US? [11+ yrs]" vs "year entered:
2022" in a different section). Recall pooled over sizes, bucketed by the
field-index gap between the two contradicting fields:

| model | single/0 | near (1-5) | mid (6-20) | far (21+) |
|---|---:|---:|---:|---:|
| 2.5-flash | 1.000 | 1.000 | 1.000 | 1.000 |
| 2.5-flash-lite | 0.833 | 0.979 | 1.000 | 1.000 |
| voice (2.5-flash-native-audio) | 1.000 | 1.000 | 1.000 | 1.000 |
| 3-flash-preview | 1.000 | 1.000 | 1.000 | 1.000 |
| 3.1-flash-lite | 1.000 | 1.000 | 0.875 | 1.000 |
| 3.5-flash (132 only) | 1.000 | 1.000 | 1.000 | 1.000 |

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
| voice (2.5-flash-native-audio) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 3.1-flash-lite | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.750 | 1.000 |
| 3-flash-preview | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 3.5-flash (132 only) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

**The G1 state_country blind spot is GONE.** In G1, 2.5-flash-lite missed 3 of 5
US-state-vs-foreign-country cases (its worst class). Embedded in a full-size form
with a sharper prompt, EVERY model -- flash-lite included -- now catches
state_country at 1.000 (vs G1's 0.40). The only sub-1.0 cells are single-case
slips in the small 3-case date classes (2.5-flash-lite future_dob 0.833,
3.1-flash-lite admission_dob 0.750), not reliable weaknesses. Net: no class is a
systematic blind spot for the flash-lite tiers at form scale. (All recall numbers
EXCLUDE errored calls -- an API timeout is "no measurement", not a miss; the
voice model, 2.5-flash, and 3.5-flash are clean across all classes.)

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

## False-positive analysis (where the precision loss comes from)

The flash-lite false positives are NOT random -- they fall into a few diagnosable
buckets (read off the model's own `reason` text on flagged clean cases):

1. **City-in-state hedging (the dominant one).** The model flags a VALID US
   city/state pair, e.g. "the city 'New York' is not located in the state 'New
   York'." It happens on ~40-50% of coherent US addresses, across many city/state
   pairs (slightly worse when city and state share a name). It cannot reliably
   confirm a city belongs to a state, so it hedges by flagging. (Note the
   asymmetry: its RECALL on real city/state contradictions is perfect -- it flags
   aggressively in both directions.)
2. **Foreign address misread as a US-state-vs-foreign-country conflict.** Sees
   "Ontario / Canada" and flags "US state filled with a foreign country" -- but
   Ontario is a province, not a US state. The inverse-error of a real bug class.
3. **US territories.** "San Juan is not a city in Puerto Rico" (it is); "Puerto
   Rico is a US territory, not a foreign country" (a non-conflict). A knowledge gap.
4. **Corpus filler artifact (NOT a model fault) -- and it is NOT marginal at 132.**
   A generic filler put "TX" into a Yes/No radio field (`p3_checkbox4[1]`, because
   "United States" contains "state"); the model correctly flagged it as invalid
   for a Yes/No question. For 3.1-flash-lite at 132, 4 of its 13 FPs are
   SOLELY this artifact -- discounting them moves its precision 0.649 -> ~0.727,
   a ~8-point jump that actually FLIPS the lite ordering at 132 (artifact-corrected
   3.1-flash-lite 0.727 edges past 2.5-flash-lite 0.686). The A/B "lead with
   2.5-flash-lite" call rests on cost (3-4x cheaper input) and small-size precision,
   NOT this 132 precision number -- but the artifact should be fixed in the corpus
   before any precision figure is quoted as final. (The fix: type-aware filler that
   never puts a non-option value into a radio/checkbox field.) Filed into the
   follow-up bead.

Buckets 1-3 are exactly what prompt + few-shot tuning targets (the follow-up bead).
None is a recall problem; all are over-flagging, which is the safer failure
direction for a defense-in-depth layer.

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
  in the merged set: 15/38 @ size40, 10/40 @ size132) -- which is itself the
  recommendation against it.

---

## Recommendation (exit criterion 3)

**Two-tier UNARY HTTP design. Use a flash-lite for the per-section/page check and
`2.5-flash` for the end-of-form sweep. Drop the Live-API idea entirely.**

**Per-section / per-page -> a flash-lite over standard HTTP.** Sub-second
(<1.1s at every size), ~0.96-1.0 recall, negligible cost. Lead with
`2.5-flash-lite` on cost ($0.10/M in vs `3.1-flash-lite`'s $0.25/M, marginally
better precision at 132); `3.1-flash-lite` is the A/B alternative (slightly faster
+ better at small sizes). The precision gap (~0.65-0.80) is the known weakness --
addressed below.

**End-of-form (132) -> `2.5-flash` over standard HTTP.** On the 132 sweep it has
recall 1.000 AND the best precision in the set (0.89). It is slow (p50 18s, p90
40s) but the end-of-form pass happens ONCE, at submit, where a few seconds is
acceptable (unlike a section boundary that gates voice flow). **`3.5-flash` was
measured here and is NOT preferred:** same recall (1.00), slightly LOWER precision
(0.86), ~4x more expensive ($0.0055 vs $0.0013/call at full rate), and only
marginally faster at the median (p90 essentially tied at ~40s). 2.5-flash wins on
raw numbers. (Caveat: `3.5-flash`'s case rests on CONTEXT CACHING, which was not
modeled here -- caching could change the cost comparison, but it helps 2.5-flash
too. Worth a future measurement, not a blocker.)

**Precision is the residual problem, and it is promptable, not a model upgrade.**
The flash-lite false positives are CONCENTRATED and diagnosable (see the FP
analysis section): city-in-state hedging ("New York is not in New York"),
foreign-province-read-as-US-state, and US-territory confusion -- plus one corpus
filler artifact. The cheap fix is prompt + few-shot ("do NOT flag an abbreviation
mismatch unless certain"; an `NY -> New York` example), or a confidence gate /
cheap second-pass confirm -- since recall is NOT the problem. This is filed as its
own follow-up bead, not part of this measurement.

### Rejected: the Live API (voice model) as the checker

The voice model (`gemini-2.5-flash-native-audio`) WAS measured as a 5th arm,
driven text-in via a Live session in tool-calling mode (it cannot emit TEXT; it
reports through a flat `report_conflicts` tool call -- a nested tool schema first
triggered the native-audio 1011 "internal error", a malformed-declaration symptom,
fixed by flattening). Results: recall 1.000 at every size (matching 2.5-flash;
after prefix-tolerant re-scoring -- the tool call truncates field ids), precision
~0.76-0.80, **but 6-9s latency** -- ~8-10x slower
than the lites, no better than 2.5-flash on accuracy. **Rejected.** The 6-9s is a
cold per-call number (fresh websocket connect + full SI processing + audio
synthesis every call); a warm/cached session could lower it, BUT the engineering
overhead (holding sockets across the minutes-long idle gap between boundaries,
the ~30-60s Live idle timeout, history-token buildup, dropped-socket handling) is
real tech debt for a task that a plain unary HTTP call does cheaper, faster, and
with bulletproof state management. Forcing a stateful streaming pipeline to do
discrete batch validation is the wrong tool. Not pursued further.

**Not recommended:** `gemini-3-flash-preview` (slowest, priciest, AND unreliable
-- 7-39% of its calls timed out).

### Follow-ups filed (not part of this bead)

- Optimize **latency for 2.5-flash** (the end-of-form tier) and **precision for
  2.5-flash-lite** (the per-page tier) -- the two real residual levers.
- Measure **context caching** for the end-of-form tier (would offset 2.5-flash /
  3.5-flash cost; the production pattern).
- **Code Execution** for deterministic lookups (NY<->New York, ZIP tables) as a
  precision lever -- noted, deferred (a flavor of the deterministic-checker the
  maintainer set aside as too fragile for now).
