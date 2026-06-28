# G1c checker tuning -- precision (prompt) + end-of-form model/latency

**Bead:** polyglot-pdf-08zv (follow-up to G1b / 0zp3, on the CLEAN corpus from G1d / wf3q)
**Date:** 2026-06-28
**Question:** With a trustworthy clean corpus (wf3q), tune the two residual levers
G1b surfaced -- per-section PRECISION (prompt) and end-of-form LATENCY -- and
recommend the config to ship for each tier.

**Harness:** `backend/scripts/probe_g1c_tuning.py` (precision + latency levers) +
`probe_g1b_model_size_bakeoff.py` (the voice-model run) over
`g1b_corpus.build_corpus` (clean answer key, `corpus_fp` stamped) scored by
`g1b_scoring`. Aggregate: `backend/scripts/g1c_aggregate.py`.

---

## Headline (two tiers)

| Tier | Model | Config to ship | Measured |
|------|-------|----------------|----------|
| **Per-section** (each section/page, ~20-40 fields) | **gemini-2.5-flash-lite** | the **tuned anti-hedging + few-shot prompt** (`PROMPT_TUNED`) | precision 0.77->0.96 @20, 0.89->0.97 @40; recall held; ~0.6s |
| **End-of-form** (the full 132-field sweep, once at submit) | **the native-audio VOICE model** (`gemini-2.5-flash-native-audio`) via a `report_conflicts` tool call | the baseline checker rules | recall 0.96, precision 1.00 @132; **p50 7.4s / p90 9.3s** |

Two premises from G1b were OVERTURNED by re-measuring on the clean corpus:
1. **"Cheap models miss far-apart contradictions -> need 3.5-flash"** was a
   CONTAMINATED-CORPUS ARTIFACT. On the clean corpus, 2.5-flash AND the voice model
   both catch the Part-1-vs-Part-8 cross-section contradictions.
2. **3.5-flash is rejected** -- too expensive ($1.50/$6.00 per M) and too slow
   (p50 ~8-13s and rising), with NO accuracy advantage over far cheaper models.

---

## Lever 2 -- PRECISION (per-section tier, gemini-2.5-flash-lite)

On the clean corpus the lite model's false positives concentrate in three
diagnosable buckets (G1b FP analysis, confirmed on the clean run
`g1b_bakeoff_20260627T135913`): FOREIGN addresses (city + foreign province +
postal + foreign country, no US state), US TERRITORIES (Puerto Rico / Guam / USVI +
their ZIPs), and DUAL addresses (a mailing + a separate physical address). All
three are coherent shapes the baseline prompt already says not to flag, but the
lite model hedges and flags them anyway.

`PROMPT_TUNED` adds an explicit ANTI-HEDGING rule ("only flag when one value makes
the other genuinely impossible; when uncertain, do not flag") + four FEW-SHOT
examples drawn from those exact buckets. Measured baseline vs tuned on
2.5-flash-lite, **pooled over 3 runs** (per-call cheap-model noise averaged out):

| prompt | size | recall | precision | tp | fn | fp |
|--------|-----:|-------:|----------:|---:|---:|---:|
| baseline | 20 | 0.979 | 0.770 | 47 | 1 | 14 |
| **tuned** | 20 | 0.958 | **0.958** | 46 | 2 | 2 |
| baseline | 40 | 0.889 | 0.889 | 56 | 7 | 7 |
| **tuned** | 40 | 0.921 | **0.967** | 58 | 5 | 2 |

(Scored probe-consistently: a `json_error` is a model-format failure = an empty
verdict = a miss, NOT excluded -- `g1c_aggregate.py`. The one `json_error` in the
tuned@20 runs is why tuned@20 recall is 0.958, not 0.979.)

**Result: at the per-section sizes (20/40) the tuned prompt is a decisive win** --
false positives drop ~7x (14->2 at size 20, 7->2 at size 40). Recall is held within
noise: at size 20 the 0.979->0.958 difference is a SINGLE case (one json_error, not
a missed contradiction); at size 40 recall improves (0.889->0.921). Exit criterion 2
met (precision lift + recall not regressed).

(At size 132 -- off-tier for the lite model -- the tuned prompt trades precision
for recall and is a wash; that does not bear on the per-section recommendation,
since the lite model runs on 20-40 field windows, and the 132 sweep is the voice
model's job.)

---

## Lever 1 -- END-OF-FORM (the 132-field sweep)

### Caching is INAPPLICABLE in practice (exit criterion 1 answer)

The bead's premise was "cache SI+rules+few-shot so only the form answers pay full
input rate." The key constraint: **caching only helps content that REPEATS
byte-identically across calls.** For the checker, the only cross-call-stable
content is the SI+rules prefix; the form payload is DIFFERENT every call (a
different applicant's answers), so it can never be a cache hit. Measured token
counts (`client.models.count_tokens`, 2026-06-27):

- checker SI+rules **prefix** (the only repeatable content) = **324 tokens**
- full 132-field prompt (prefix + this form's answers) = **2908 tokens**
- Gemini cache MINIMUMS: **2.5-flash 2048, 3.5-flash 4096**
  (ai.google.dev/.../caching, verified via gemini-docs MCP 2026-06-27)

The repeatable prefix (324 tokens) is far below BOTH minimums (2048 and 4096), so
neither implicit nor explicit caching of the prefix can engage on either model.
Note the full prompt (2908 tokens) DOES exceed the 2.5-flash 2048 minimum -- but
that is irrelevant, because the full prompt is unique per form and so never
produces a cache hit; only the 324-token prefix repeats, and it is too small to
cache. So caching cannot reduce billed input for this checker on EITHER model.
(`probe_g1c_tuning.py --lever latency` prints the prefix-token feasibility check.)

### Payload trim is a NET LOSS

Dropping field NAMES (id+value only) cut input ~25% but DROPPED precision
0.90 -> 0.79 (run `g1c_latency_20260627T194907`): the model needs the spoken names
to read field meaning. Not a usable latency lever.

### Model comparison @132 on the CLEAN corpus

| model | recall | precision | lat_p50 | lat_p90 | in/out $/M | verdict |
|-------|-------:|----------:|--------:|--------:|-----------|---------|
| gemini-3.5-flash | 1.000 | ~0.90-0.96 | ~8-23s | ~19-41s | 1.50 / 6.00 | REJECTED -- costly + slow, no accuracy edge |
| gemini-2.5-flash | 1.000 | 0.964 | 23.2s | 41.0s | 0.30 / 2.50 | accurate + cheap, but SLOW |
| **voice (native-audio)** | **0.963** | **1.000** | **7.4s** | **9.3s** | 0.50 / 2.00 | **SHIP** -- ~3x faster, cheaper than 3.5, 0 new deps |

The native-audio voice model (run `g1b_bakeoff_20260628T092129`) catches the
far-apart classes the tier exists for (cross_date 3/3, duration_year 2/3),
flags ZERO false positives @132, runs ~3x faster than 2.5-flash, costs less than
3.5-flash, and is ALREADY the connected live-session model -- so the end-of-form
check is a tool call on the existing session, not a new model dependency. Its old
"far 5/6" weakness (G1b) was a contaminated-corpus artifact.

---

## Recommendation (exit criterion 3)

- **Per-section checker:** `gemini-2.5-flash-lite` (HTTP) with `PROMPT_TUNED`
  (anti-hedging + foreign/territory/dual few-shots). ~0.6s, precision ~0.96-0.97 on
  20-40 field windows, recall held.
- **End-of-form checker:** the **native-audio voice model** via a `report_conflicts`
  tool call on the live session, with the baseline checker rules. recall 0.96,
  precision 1.00, ~7s p50 / ~9s p90 -- fast enough for a once-at-submit
  "reviewing your form" moment.
- **Do NOT** pursue context caching (prompt too small) or payload trimming (precision
  loss). **Drop 3.5-flash** from the design.

### CRITICAL production constraint -- FRESH session, never the connected one

The end-of-form check MUST run on a **brand-new, isolated Live session** carrying
ONLY the checker SI + the form payload -- NOT the user's already-connected
form-fill session. Reusing the connected session would re-bill the ENTIRE
conversation history (every prior voice turn) as input on the check call, turning
a ~2900-token check into a charge that grows with conversation length. The
measured cost/latency here assumes a fresh session and is only valid under it.

This is exactly how the probe measured it -- `_run_live` opens a new
`client.aio.live.connect(...)` per call with `system_instruction=_LIVE_SI` and the
payload as the sole turn (probe_g1b_model_size_bakeoff.py:299-300), and its
cost basis is `count_tokens([_LIVE_SI, payload])` only. The production wiring must
preserve this: spin up a SEPARATE ephemeral Live session for the check (its own
connect, checker SI, no history), get the `report_conflicts` tool call, and close
it -- never inject the check into the live form-fill session's turn stream.

### Caveats / follow-ups
- The hard far-apart classes (cross_date, duration_year) are still only 3 cases
  each; the voice model's 0.963@132 rests on a small sample. A LARGER hard-case
  corpus would firm up the end-of-form recall number (G1b already flagged this).
- The voice-model end-of-form check is measured here as a STANDALONE tool-call
  session (the probe's `_run_live`). Wiring it as an end-of-form trigger in
  production is a separate build (the validator-injection beads jnjj.16/jnjj.17),
  not this measurement bead -- and it MUST use a fresh session per the constraint
  above.
