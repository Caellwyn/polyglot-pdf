# G1b bake-off -- model x form-size matrix for the out-of-band B checker

> **PRECISION UPDATE (bd wf3q, 2026-06-27):** the "clean" corpus this report's
> precision was measured on was rebuilt on a HAND-VALIDATED coherent I-90 answer
> key (`backend/scripts/g1b_answer_key.py`), removing the unlabeled-contradiction
> contamination Codex round 3 found. A clean-corpus re-measure on the two cheap
> text models (run `g1b_bakeoff_20260627T111636`) gives TRUSTWORTHY precision:
> 2.5-flash 0.88-1.00, 2.5-flash-lite 0.71-0.88, with every residual false
> positive a genuine over-flag on a coherent foreign/territory/dual address (NOT a
> corpus artifact; the full validated persona baseline is 0/6 flagged). The RECALL
> findings below are unaffected (recall was always measured on labeled
> contradictions). See `docs/journal/entries/2026-06-27-bd-wf3q-...md`.

**Bead:** polyglot-pdf-0zp3 (follow-up to G1 / jnjj.5)
**Date:** 2026-06-26 (corrected re-run after two rounds of Codex methodology review)
**Question:** For the out-of-band end-of-section + end-of-form contradiction
checker (Pillar B, reframed from "replace the in-SI check" to "an additional
safety layer" by the maintainer on 2026-06-17), WHICH cheap model, and does
accuracy survive a realistic page- or form-sized payload -- including a
contradiction whose two halves sit far apart? Measured speed, cost, and accuracy
across 6 models (5 text + the voice model) x up to 3 form sizes.

> **This is the CORRECTED report** (two Codex review rounds). A first pass
> concluded "distance does not degrade recall." Codex round 1 found the
> far-distance cases were unsound (applicant state vs a DIFFERENT person's ZIP),
> the "same fact twice" class duplicated another, `duration_year` was never
> generated, size-132 transmitted only ~84 fields (empty clusters dropped), and a
> filler bug injected invalid values. Round 2 (after the rebuild + first re-run)
> found MORE filler contamination (non-Yes/No controls filled with "No";
> signatures all the applicant's name; clean addresses keeping a Houston street),
> plus scoring/latency bugs (partial-group flags credited as catches; model-format
> failures excluded instead of scored as misses; latency timed only the final
> retry). All fixed, corpus rebuilt twice, sweep re-run twice. **The corrected data
> REVERSES the original headline finding** (see below) and is stable across both
> re-runs.

**Headline:** at form scale the models split into TWO groups on the hard cases.
On the easy, local contradictions (zip-vs-state, dates adjacent, city-in-state)
ALL models do well. But on **far-apart, cross-section contradictions** -- the
realistic "a fact stated in two different places" case -- the **cheap text models
(2.5-flash, 2.5-flash-lite, 3.1-flash-lite) miss roughly half** (far recall
4/6, 2/5, 4/6), and on the **`duration_year` class** (e.g. "I have lived in the US
for 20 years" in a later section vs an admission date of 2020) the cheap tier
catches **0-1 of 3** (2.5-flash-lite ZERO). The models that hold up on the hard
cases are **3-flash-preview** (duration 3/3, far 6/6), **3.5-flash**, and the
**voice model** (both duration 2/3, far 5/6). So "a cheap flash-lite handles
everything" does NOT survive the corrected test: the cheap tier is fine for
per-section local checks but unreliable for the end-of-form, cross-section pass.

---

## The matrix (merged, deduped dataset: `scripts/spikes/data/g1b_bakeoff_MERGED.csv`)

577 cells: 5 text models x {20,40,132} + the voice model x {20,40,132} + 3.5-flash
x {132}, ~36 labeled cases per (model x size). Recall = contradictions caught
(full-group: every field of an expected conflict must be flagged together);
precision = 1 - false-alarm rate; latency = per-call wall clock; cost =
(in_tok x in_rate + out_tok x out_rate). Errored (timeout / 5xx) calls are
EXCLUDED from accuracy -- an API failure is "no measurement", not a miss.

| model | size | recall | precision | lat p50 | lat p90 | cost/call | err rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2.5-flash-lite | 20 | 1.000 | 0.727 | 2.9s | 9.1s | $0.00013 | 0 |
| 2.5-flash-lite | 40 | 1.000 | 0.656 | 3.2s | 7.9s | $0.00021 | 0 |
| 2.5-flash-lite | 132 | 0.840 | 0.656 | 7.2s | 21.2s | $0.00055 | ~10% |
| 3.1-flash-lite | 20 | 0.875 | 0.933 | 0.8s | 1.2s | $0.00038 | 0 |
| 3.1-flash-lite | 40 | 1.000 | 0.955 | 0.8s | 1.0s | $0.00053 | 0 |
| 3.1-flash-lite | 132 | 0.593 | 0.800 | 0.9s | 1.0s | $0.00131 | 0 |
| 2.5-flash | 20 | 1.000 | 0.667 | 10.7s | 19.1s | $0.00067 | 0 |
| 2.5-flash | 40 | 1.000 | 0.677 | 21.4s | 50.8s | $0.00093 | 0 |
| 2.5-flash | 132 | 0.926 | 0.862 | 56.3s | 167.7s | $0.00175 | ~2% |
| 3-flash-preview | 20 | 1.000 | 0.667 | 12.1s | 47.4s | $0.00104 | 0 |
| 3-flash-preview | 40 | 1.000 | 0.583 | 31.6s | 79.9s | $0.00166 | 0 |
| 3-flash-preview | 132 | 1.000 | 0.643 | 41.6s | 58.5s | $0.00349 | 0 |
| 3.5-flash | 132 | 0.963 | 0.634 | 12.8s | 25.6s | $0.00822 | 0 |
| voice (2.5-flash-native-audio) | 20 | 1.000 | 0.842 | 6.8s | 9.4s | $0.00048* | 0 |
| voice (2.5-flash-native-audio) | 40 | 1.000 | 0.724 | 9.6s | 12.9s | $0.00080* | 0 |
| voice (2.5-flash-native-audio) | 132 | 0.963 | 0.765 | 11.5s | 16.7s | $0.00241* | 0 |

Notes: precision is CASE-LEVEL (a clean case flagging anything = 1 FP; extra
flagged groups on a contradiction case are not counted). LATENCY is END-TO-END
including failed-attempt retries + backoff (so the 2.5-flash@132 p90 of 167.7s is
real user-visible time when calls retried through the API waves -- not a single
clean call). The voice model emits AUDIO + reports via a tool call; its `*` cost
is INPUT-ONLY (audio-output tokens unmeasured), so its true cost is higher.
Model-format failures (non-JSON / no-tool-call) are SCORED as misses; only
transport failures (timeout / 5xx) are excluded as no-measurement. `3.5-flash`
list prices ($1.50/M in, ~$6/M out) are unverified. **A sustained Google 5xx
(ServerError) wave hit 2.5-flash-lite at size 132** (~10% errored even after a
second run); the merge's prefer-non-errored dedup recovered 38/42 cells.

### Reading the matrix

1. **Local contradictions: everyone is good.** At distance <= 20 fields
   (adjacent or same-section), every model catches essentially every
   contradiction. The split is entirely on the FAR cases (next section).
2. **Recall drops at size 132** for the cheap text models (2.5-flash-lite 0.840,
   3.1-flash-lite 0.593; 2.5-flash holds better at 0.926) -- mostly the
   far/duration cases that only exist at 132.
3. **Precision is the flash-lites' weakness** -- they sit at ~0.66-0.80 (they
   over-flag valid US city/state pairs, and flag the applicant's mailing-vs-physical
   addresses as a conflict even when both are valid). After the corpus-coherence
   fixes (Codex round 2) the precision numbers are CLEANER/higher than the prior
   pass -- the earlier low ~0.55 was partly corpus contamination, not model
   behavior. 2.5-flash is the best at 132 (0.862).
4. **Latency: only 3.1-flash-lite stays sub-1.5s at every size.** 2.5-flash is the
   slowest by far at 132 (p50 56s, p90 168s -- end-to-end including the retry
   waves it hit); 3-flash-preview 42s p50; 3.5-flash 13s p50. For a per-section
   gate, sub-2s matters; for a once-at-submit end-of-form pass, 13-40s is
   tolerable (but 2.5-flash's tail is not).
5. **Cost is small for all** (well under a cent per call even at 132); it does not
   discriminate. Speed and (cross-section) accuracy do.

---

## Accuracy by contradiction DISTANCE (the corrected far-distance test)

The maintainer's key worry: a contradiction whose two halves sit far apart -- a
fact stated in two different sections (a birthday restated later; "how long in the
US?" vs a stated entry year). The far(21+) cases are now GENUINE cross-section
pairs: a Part-1 field vs a Part-8 additional-information textarea, ~85-96 fields
apart. Recall (detected/total, errors excluded), pooled over sizes:

| model | single/0 | near (1-5) | mid (6-20) | far (21+) |
|---|---:|---:|---:|---:|
| 2.5-flash | 6/6 | 48/48 | 4/4 | **4/6** |
| 2.5-flash-lite | 6/6 | 47/47 | 3/4 | **2/5** |
| 3.1-flash-lite | 6/6 | 39/48 | 2/4 | **4/6** |
| voice (2.5-flash-native-audio) | 6/6 | 48/48 | 4/4 | **5/6** |
| 3-flash-preview | 6/6 | 48/48 | 4/4 | **6/6** |
| 3.5-flash | 3/3 | 16/16 | 2/2 | **5/6** |

**Distance DOES degrade recall -- for the cheap text models.** The cheap tier
(2.5-flash, 2.5-flash-lite, 3.1-flash-lite) catches only 2-4 of ~6 far cases,
while 3-flash-preview catches ALL of them and the voice model + 3.5-flash catch
5/6. This is the REVERSE of the (flawed) first pass, and it holds on the
round-2-corrected corpus. The far bucket is small (5-6 cases per model), so do not
over-read the exact fraction -- but the direction is consistent and matches the
class breakdown below. (Caveat: the far cases all use the Part-8 free-text
restatement device; a different far-contradiction construction might behave
differently and is worth a future targeted corpus.)

## Accuracy by contradiction CLASS

Recall (detected/total, errors excluded), pooled over sizes:

| model | zip_state | state_country | province_us | city_state | future_dob | admission_dob | cross_date | duration_year |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.5-flash | 15/15 | 12/12 | 9/9 | 12/12 | 6/6 | 4/4 | 3/3 | **1/3** |
| 2.5-flash-lite | 15/15 | 12/12 | 9/9 | 11/11 | 6/6 | 3/4 | 2/2 | **0/3** |
| 3.1-flash-lite | 15/15 | 10/12 | 4/9 | 10/12 | 6/6 | 2/4 | 3/3 | **1/3** |
| voice (2.5-flash-native-audio) | 15/15 | 12/12 | 9/9 | 12/12 | 6/6 | 4/4 | 3/3 | **2/3** |
| 3-flash-preview | 15/15 | 12/12 | 9/9 | 12/12 | 6/6 | 4/4 | 3/3 | **3/3** |
| 3.5-flash | 5/5 | 4/4 | 3/3 | 4/4 | 3/3 | 2/2 | 3/3 | **2/3** |

**`duration_year` is the discriminator.** It states a length-of-residence in a
Part-8 textarea ("I have lived in the United States for over 20 years.") that
contradicts the `date of admission` (e.g. 2020) -- a semantic, far-apart, requires-
arithmetic check. **2.5-flash-lite catches 0 of 3; 2.5-flash and 3.1-flash-lite 1
of 3.** 3-flash-preview catches all 3; the voice model and 3.5-flash 2 of 3. The
genuine `cross_date` class (DOB restated with a different year in Part 8) is caught
by everyone -- a date contradiction is more salient than a fuzzy duration. So the
cheap models' far-distance failure is concentrated in the duration/semantic class,
not all long-range checks. (3.1-flash-lite is also notably weaker than its siblings
on `state_country` 10/12, `province_us` 4/9, and `admission_dob` 2/4 -- it is the
least reliable of the three cheap models despite similar headline recall.)

---

## Provenance + honesty

- **Corpus is SYNTHETIC** (no real transcripts exist; pre-pilot, no PII logged).
  Field ids/names/types/sections are the REAL 132-field I-90; values are a
  coherent hand-authored persona; contradictions are injected. Recall numbers are
  an UPPER BOUND on real-world recall. (`backend/scripts/g1b_corpus.py`.)
- **132 = the real full I-90**, and after the Codex fixes the size-132 payload
  genuinely transmits ~122 filled fields (the remaining ~10 are legitimately-empty
  optional fields -- foreign-province lines blank for a US address, the two
  no-option height radios). 20 ~ a section, 40 ~ a page.
- **Small per-cell N on the hard classes** (cross_date / duration_year / far are
  3-6 cases each, and only exist at size 132). The DIRECTION (cheap models miss
  duration/far) is robust and consistent across the distance and class views; the
  exact fractions are not precise. A larger hard-case corpus is the obvious
  follow-up.
- **Precision has run-to-run noise** (models are non-deterministic) and is
  CASE-LEVEL; the user-visible spurious-PAIR rate is higher.

## False-positive analysis (where the precision loss comes from)

The flash-lite false positives are diagnosable (model `reason` text on flagged
clean cases):
1. **City-in-state hedging** -- flags a VALID US city/state pair ("New York is not
   in New York"); it cannot reliably confirm a city belongs to a state, so hedges.
2. **Mailing-vs-physical** -- the corpus fills BOTH a mailing and a
   separate-but-coherent physical (Austin) address, and the cheap models flag
   "your mailing city differs from your physical city" as a conflict even though
   two different valid addresses are allowed. A real failure mode for a checker.
3. **Foreign address misread** as a US-state-vs-foreign-country conflict (Ontario
   read as a US state).
4. **US territories** -- "San Juan is not in Puerto Rico" (it is).

All are OVER-flagging (the safe failure direction for a defense-in-depth layer)
and are promptable; filed to the follow-up bead (08zv).

## Run mechanics

The sweep ran in pieces (per-size / per-model run files merged + deduped). Lessons
carried from the prior runs: a per-call timeout (a hung call once froze a run for
~2h), bounded concurrency tuned per size (high concurrency on big 132-field
payloads triggers a rate-limit/timeout spiral -- 132 runs at concurrency 3-4),
incremental CSV checkpointing (a killed run keeps completed cells), and a
merge/dedup that prefers non-errored rows (so a cell that 5xx'd in one run is
filled by another). `3-flash-preview` stays flaky; a sustained Google 5xx wave on
`2.5-flash-lite` during this sweep was the reason for the second flash-lite run.

---

## Recommendation (exit criterion 3)

**Two-tier UNARY HTTP, but with the model split driven by the corrected data:**

**Per-section / per-page (LOCAL contradictions) -> a flash-lite over HTTP.** On
the local classes (zip/state, city/state, adjacent dates) the flash-lite tiers are
essentially perfect and (for 3.1-flash-lite) sub-2s. Lead with **2.5-flash-lite**
on cost, OR **3.1-flash-lite** if its sub-2s latency is needed and its slightly
weaker state_country/province recall is acceptable. This tier does NOT need to
catch far/duration contradictions -- those don't occur within one section.

**End-of-form (CROSS-SECTION pass) -> NOT a flash-lite.** This is the corrected
finding: the cheap models miss ~half the far cases and ALL of the duration_year
class, which is exactly what an end-of-form pass exists to catch. Use a model that
held up on the hard cases:
- **2.5-flash** is borderline -- only 1/3 duration_year and 4/6 far, and it is the
  SLOWEST model at 132 (p50 56s, p90 168s). Not the end-of-form pick.
- **3.5-flash** (recall 0.963 at 132, far 5/6, duration 2/3, p50 13s) or the
  **voice model via its Live tool-calling path** (far 5/6, duration 2/3) catch the
  cross-section contradictions far better than the cheap tier. 3.5-flash is the
  simplest (plain HTTP, fastest of the accuracy-tier models); it is the priciest
  text model ($0.008/call uncached) but context caching (untested here) would cut
  that, and at a handful of end-of-form calls per submission the absolute cost is
  tiny.
- **3-flash-preview** has the BEST hard-case recall (far 6/6, duration 3/3) but is
  the slowest+priciest and historically flaky (it behaved this run at concurrency
  3, but earlier sweeps saw 17-28% timeouts) -- not recommended as the primary.

**So the corrected recommendation is: 2.5-flash-lite (or 3.1-flash-lite) for the
per-section local check, and 3.5-flash for the end-of-form cross-section pass --
a genuine per-boundary model split, which the FIRST (flawed) pass wrongly said was
unnecessary.** The precision gap (cheap models over-flag ~30-45%) is a separate,
promptable problem (follow-up bead 08zv).

### The Live API (voice model) -- best hard-case recall, but still rejected as the checker

The voice model has strong hard-case recall (far 5/6, duration 2/3 -- on par with
3.5-flash) AND the best precision of the lot at the smaller sizes (0.84/0.72),
AND it is the model already in the session. But it is driven over a Live session
in tool-calling mode (it cannot emit TEXT), at 7-12s per-call latency, with the
Live-session tech debt (sockets held across idle gaps past the ~30-60s timeout,
history-token buildup, dropped-socket handling). For an out-of-band batch check a
plain HTTP call to 3.5-flash gets comparable hard-case recall without that
overhead. So the voice model stays rejected as the checker -- but its strong
hard-case recall + precision is a data point if the "voice model does double-duty"
idea is ever revisited.

### Follow-ups filed (bead polyglot-pdf-08zv + new)

- Optimize **2.5-flash-lite per-page PRECISION** (anti-hedging prompt + few-shot;
  the FPs are concentrated: city-in-state, mailing-vs-physical, territories).
- Optimize **end-of-form LATENCY/COST** via context caching for the chosen
  accuracy-tier model (3.5-flash).
- **Larger hard-case corpus**: the far/duration/cross_date classes are 3-6 cases
  each; the per-boundary-split recommendation rests on a small (but consistent)
  sample and deserves a bigger labeled set before it ships as policy.
- Code Execution for deterministic lookups (NY<->New York, ZIP tables) as a
  precision lever -- noted, deferred.
