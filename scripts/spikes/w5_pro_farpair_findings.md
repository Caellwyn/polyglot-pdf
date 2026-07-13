# W5 -- gemini-2.5-pro whole-form far-pair recall on the 132-field I-90 corpus

**Bead:** polyglot-pdf-g0w1 (W5), child of the async-validator epic polyglot-pdf-09da
**Date:** 2026-07-13
**Model / SDK:** gemini-2.5-pro on Vertex (google-genai 2.8.x; ADC + GOOGLE_CLOUD_PROJECT=polyglot-demo-aa709)
**Run data:** `scripts/spikes/data/g1b_bakeoff_20260713T141057.csv` (+ `.meta.json`)
**Instrument:** `backend/scripts/probe_g1b_model_size_bakeoff.py` (the 6cfu.5 chunk-size
instrument), extended with a `gemini-2.5-pro` arm + a bounded thinking budget.

---

## Question

The epic's maintainer-preferred design for cross-page (far-pair) contradiction
coverage is ONE whole-form pro-tier pass at `form_complete`. But that pass was
UNMEASURED: the 6cfu.5 chunk-size run showed even `gemini-2.5-flash` whole-form
caught only **0.50** of far pairs (`2.5-flash-lite` 0.33). W5 measures whether
`gemini-2.5-pro` clears that bar, BEFORE any wiring work (W6). GO/NO-GO gate.

## Headline

**GO.** `gemini-2.5-pro` catches **6/6 far pairs (recall 1.000)** at whole-form
(132-field) scale on the controlled I-90 instrument -- including all 3
`duration_year` cases, the semantic far class the cheap 2.5-tier models miss (flash
1/3, lite 0/3 at whole-form in 6cfu.5). The GO rests on pro's OWN absolute recall
(1.000), which clears the bar outright. The cross-model FRAMING ("pro beats flash's
0.500") is NOT a controlled head-to-head -- the flash baseline ran under Vertex's
default DYNAMIC thinking budget while pro ran with a bounded one; see Honesty/limits
and the follow-up bd polyglot-pdf-hy5k. Cost with bounded thinking is **~$0.39 for
the full 42-call sweep** (~$0.0093/call), inside the epic's approved $0.30-0.50 band.

**One material caveat for W6:** whole-form precision is **0.750** (9 of 15 clean
cases false-flagged), driven by a systematic over-flag of the Part 5 / Part 6
preparer-and-interpreter certification block. Recall is not the problem; a
whole-form pro pass would ship a meaningful spurious-flag rate that W6 must
prompt-mitigate. This does not block the GO -- it scopes it.

---

## Method

- **Corpus:** `backend/scripts/g1b_corpus.py` `build_corpus(132)` -- 42 labeled
  cases (27 contradiction + 15 clean) over the REAL 132-field I-90 field
  structure, on the hand-validated coherent persona answer key (bd wf3q). SYNTHETIC
  injection; recall is an UPPER BOUND on real-world recall.
- **Far pairs** = the 6 genuine cross-section cases (distance >= 21 filled-field
  index gap), which exist ONLY at size 132: 3 `cross_date` (Part 1 DOB restated
  with a different year in a Part 8 free-text field) + 3 `duration_year` (a Part 8
  length-of-residence statement contradicting the Part 1 date of admission). These
  are the "a fact stated in two different places" contradictions a monster window
  is supposed to catch.
- **Sizes run:** size 132 ONLY. Far pairs do not exist at sizes 20/40 (0 far cases
  each -- verified), so the whole-form arm answers the far-pair question completely;
  running 20/40 would add 65 calls of zero far-pair signal. This is why the sweep
  is 42 calls, not 107.
- **Scoring:** unchanged from 6cfu.5 -- `backend/scripts/g1b_scoring.py` full-group
  detection (every field of an expected conflict must be flagged together;
  any-overlap matching is rejected as inflating far recall). Distance bucketing via
  `backend/scripts/g1b_analyze.py` (`far(21+)`). Model-format failures (non-JSON)
  score as misses; transport failures are excluded as no-measurement. Zero of
  either occurred this run (0 errors / 42 calls).
- **Thinking control (the W5 cost guard).** 2.5-pro thinks by DEFAULT on Vertex
  (dynamic budget, -1) and **cannot be turned off** (thinking_budget range is
  128..32768; budget=0 is rejected -- ai.google.dev/gemini-api/docs/thinking).
  Unbounded dynamic thinking dominated a prior day's Vertex bill. This arm is run
  with an explicit **`thinking_budget=512`** (`THINKING_BUDGET` in the probe), small
  because contradiction-checking is a classification task, not deep reasoning.
  Thinking tokens are billed at the OUTPUT rate and accounted as a SEPARATE cost
  line (see below). A single cheap pilot call ground-truthed the estimate before
  the full sweep (measured 317 thinking tok, confirming the budget is not the
  binding constraint).

## Results (size 132, gemini-2.5-pro, thinking_budget=512)

Recall by contradiction DISTANCE (this is the W5 metric):

| model | single/0 | near(1-5) | mid(6-20) | **far(21+)** |
|-------|---------:|----------:|----------:|-------------:|
| **gemini-2.5-pro** (bounded thinking=512) | 1.000 | 1.000 | 1.000 | **1.000 (6/6)** |
| gemini-2.5-flash (6cfu.5, DYNAMIC thinking) | -- | -- | -- | **0.500** |
| gemini-2.5-flash-lite (6cfu.5) | -- | -- | -- | **0.333** |

The flash/lite rows are the 6cfu.5 baseline and ran under Vertex's DEFAULT dynamic
thinking budget, not a bounded one -- so the pro-vs-flash gap is not a controlled
same-regime comparison (see Honesty/limits; bd polyglot-pdf-hy5k). Pro's own 1.000
is the number the GO rests on.

Recall by CLASS (all 1.000): admission_dob, city_state, cross_date,
duration_year, future_dob, province_us, state_country, zip_state. **The
`duration_year` semantic far class -- 0/3 for flash-lite, 1/3 for flash -- is
3/3 for pro.**

Headline cell:

| model | size | recall | precision | lat p50 | lat p90 | think_med | cost/call | err |
|-------|-----:|-------:|----------:|--------:|--------:|----------:|----------:|----:|
| gemini-2.5-pro | 132 | **1.000** (27/27) | **0.750** (9 FP) | 5.95s | 7.51s | 427 tok | $0.0093 | 0 |

### Cost breakdown (the thinking line, called out per the W5 guard)

Per call (medians): input 2,936 tok @ $1.25/M; answer output 129 tok @ $10/M;
**thinking output 427 tok @ $10/M**. Thinking is ~77% of the OUTPUT tokens and
~40% of per-call cost -- non-trivial, but BOUNDED (282-514 tok observed; a few
cases touched the 512 cap, most underflowed). Total measured sweep cost:
**$0.3924 / 42 calls**. Had thinking been left at the default (dynamic), a prior
incident showed it can 10-50x the answer tokens -- the bounded budget is what
keeps this in-band.

### Latency

p50 5.95s / p90 7.51s -- far better than `2.5-flash`'s whole-form p50 of ~29-56s
(6cfu.5 / 0zp3), because the bounded thinking budget also bounds the reasoning
time. For a once-per-form end-of-form pass this is comfortably tolerable (well
under a human-review cadence; the async validator is off the voice path).

## Precision caveat (scopes the GO; feeds W6)

Case-level precision is 0.750: **9 of 15 clean cases were false-flagged**. The
false positives are NOT random -- they cluster on the Part 5 / Part 6
**preparer-and-interpreter certification block** (`p5_checkbox1a`,
`p5_line1b_language`, `p6_language`, `p6_line1a_interpretersfamilyname`, ...):
2.5-pro reads the "an interpreter/preparer helped, in language X" certification as
contradicting the applicant's own answers, and also over-flags repeated
bracketed name fields (`p1_line3a_familyname` vs `p1_line3a_familyname[1]`, which
are legitimate continuation entries). One geographic over-flag also appears
(`city/state/destination` cluster). These are OVER-flags -- the safe failure
direction for a defense-in-depth layer -- and are promptable (the same
class of fix the flash-lite precision bead 08zv/g1c already applied to the cheap
tier, lifting lite precision 0.77->0.96). But at 0.750 uncorrected, a whole-form
pro pass shipped as-is would surface a spurious flag on roughly 6 of 10 clean
forms. W6 must carry an anti-over-flag prompt (explicitly: the preparer/interpreter
certification and bracketed-repeat fields are NOT contradictions) and re-measure
precision before the pass is trusted as the sole end-of-form report.

## Honesty / limits

- **Small far-pair N (6 cases).** The direction (pro 6/6 vs flash 3/6, lite 2/6)
  is unambiguous and matches the class view (duration_year 3/3 vs 0-1/3), but the
  exact fraction should not be over-read. A larger hard-case corpus is the standing
  follow-up (already filed generally under the 0zp3 lineage).
- **Single run, one form.** One run per cell on the one validated instrument (the
  i-90 corpus; a naive second-form key manufactures contradictions -- wf3q). A
  second validated form is bd polyglot-pdf-z2l9. Consistent with 6cfu.5's own
  single-run-per-cell basis.
- **Synthetic corpus.** No real transcripts; recall is an upper bound.
- **Baseline provenance.** The flash/lite far numbers this beats are the 6cfu.5
  Vertex run (2026-07-11, same instrument, same clean corpus). (The older 0zp3
  g1b_bakeoff_findings far numbers are pre-clean-corpus / AI-Studio and are not the
  comparison basis.)
- **Thinking-regime mismatch in the pro-vs-flash comparison (do NOT call it
  apples-to-apples).** The pro arm ran with an explicit BOUNDED thinking budget
  (512); the 6cfu.5 flash baseline (far recall 0.500) ran under Vertex's
  UNCONTROLLED default DYNAMIC thinking budget (6cfu.5's own note 4: flash there is
  "default thinking budget," p50 10-30s, and it flagged that a bounded flash number
  needs its own measurement). The 6cfu.5 CSV has no `think_tok` column, so the
  thinking regime behind flash's 0.500 is unauditable. This does NOT change pro's
  own measured 1.000 (6/6) -- pro clears the far-pair bar on its own absolute
  number -- but the "pro is the only 2.5-family model that clears the bar" FRAMING
  is not a controlled head-to-head: one side was bounded, the other dynamic. A
  controlled flash re-measure (bounded thinking, size 132) to settle whether flash
  would clear the bar under the SAME regime is filed as **bd polyglot-pdf-hy5k**;
  it does not block the GO (which rests on pro's own recall), only sharpens the
  comparison.

## Verdict: **GO** (with a precision condition on W6)

Wire the whole-form `gemini-2.5-pro` pass at `form_complete` (W6,
polyglot-pdf-gbus). It is the only 2.5-tier model that delivers full far-pair /
semantic-class recall at whole-form scale, at bounded, in-band cost
(~$0.0093/call, ~$0.39/full-form-equivalent-sweep) and tolerable latency (p50 6s)
once thinking is bounded to 512. **Condition:** W6 must include an anti-over-flag
prompt for the Part 5/6 certification block and bracketed-repeat fields and
re-measure precision -- the 0.750 uncorrected precision is the one number that
would hurt if shipped naively. Recall is solved; precision is the W6 work.

## Files touched

- `backend/scripts/probe_g1b_model_size_bakeoff.py` -- added the `gemini-2.5-pro`
  arm (in/out text rates), a per-model bounded `THINKING_BUDGET` (+ per-model
  timeout override) wired into the text `generate_content` config, separate
  `think_tok` capture (thoughts_token_count) + a `think_med` matrix column, and
  thinking-tokens-at-output-rate in `_cost`. Baseline arms unchanged (no
  thinking_config -> API default), so they stay comparable to 6cfu.5.
- `scripts/spikes/data/g1b_bakeoff_20260713T141057.csv` + `.meta.json` -- run data.
- this findings doc.
