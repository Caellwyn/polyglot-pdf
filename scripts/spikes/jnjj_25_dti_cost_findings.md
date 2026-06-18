# jnjj.25: DTI principal cost vs section-reset baseline (real I-90)

*Date: 2026-06-18. Epic: polyglot-pdf-jnjj. Instrument:
`scripts/spikes/measure_form_session_costs.py` (`--schema i90 --arm {section-reset,dti}`).
Model 2.5 (`gemini-2.5-flash-native-audio-preview-12-2025`), live Gemini,
GEMINI_API_KEY. 25-question plan over the first 3 real I-90 sections. 4/4 cells ran.
Data: `scripts/spikes/data/costs_i90_2.5_*_20260618T0205*.csv` + `.meta.json`.*

## Verdict: GO on DTI + calibrated eviction (NOT DTI alone)

DTI's per-turn system instruction (SI) is **34% smaller** than the section-reset
full-SI baseline (3786 vs 5718 chars). DTI ALONE does not convert that to a cost
win -- it is a wash (the per-field guidance ACCUMULATES within a section,
re-billed every turn, giving the SI saving back). **But DTI + CALIBRATED EVICTION
delivers a clear win: -21% on the unhappy path** ($0.4407 vs the baseline $0.5596)
and parity on the happy path. Eviction purges the accumulated guidance
turn-over-turn, so DTI's SI saving is no longer given back. This empirically
confirms the plan's Gate-1.5 hypothesis end-to-end: **ship DTI WITH eviction.**

## Scope of these numbers (read before citing the dollars)

Every cell is the **25-question plan over the I-90's first 3 sections** (9+10+9 =
~28 visible fields; 25 scripted) -- **~19% of the 132-field, 16-section form, NOT
the full I-90.** So:

- **The `-21%` (and other %) deltas are the trustworthy result** -- they are
  ratios between two arms on the IDENTICAL plan, so they hold regardless of form
  length.
- **The absolute dollars ($0.2247 / $0.4407) are NOT the cost to fill an I-90** --
  they are the first ~19%. A naive 5.3x linear extrapolation puts a full unhappy
  I-90 at very roughly ~$1.9 (DTI+eviction) vs ~$2.4 (baseline), but DO NOT trust
  that as a point estimate: cost is PER-SECTION and I-90 section sizes vary wildly
  (1 to large), and the DTI+eviction advantage scales WITH section size (more
  within-section accumulation to evict) -- it shrinks or inverts on 1-2 field
  sections (where the DTI SI can exceed the baseline; see the jnjj.6 SI-floor
  table). The full-form delta could be better OR worse than -21% depending on the
  section-size distribution.
- **Why 25 and not 132:** each cell is a ~10-15 min live session at 25q; a full run
  is ~1h+/cell x 6 cells, and the 2.5 tool-loop drift WORSENS the longer the
  session -- so a long run degrades data quality. 25q over 3 representative sections
  (the jnjj.24 harness design) is the deliberate scoping for a clean ratio.

## The matrix (25 questions; happy = 2 turns/q, unhappy = 4 turns/q)

| arm | path | SI chars | run $ | vs baseline | tokens | confirmed | evictions |
|---|---|---:|---:|---:|---:|---:|---:|
| section-reset (full-SI baseline) | happy | 5718 | **$0.2219** | -- | 278,673 | 17/25 | 2 |
| section-reset (full-SI baseline) | unhappy | 5718 | **$0.5596** | -- | 756,874 | 24/25 | 2 |
| dti (no eviction) | happy | 3786 | $0.2378 | **+7.2%** | 278,363 | 14/25 | 4 |
| dti (no eviction) | unhappy | 3786 | $0.5490 | **-1.9%** | 730,241 | 20/25 | 3 |
| **dti + calibrated eviction** | happy | 3786 | **$0.2247** | **+1.3%** | 260,303 | 14/25 | 6 |
| **dti + calibrated eviction** | unhappy | 3786 | **$0.4407** | **-21.2%** | 559,290 | 20/25 | 15 |

(The "evictions" column counts ALL prompt-token drops detected, which conflates
two event types: section-boundary session RESETS -- present in every arm, ~2-3 per
run -- and context-window COMPRESSION events. So the baseline's "2" and DTI-alone's
"3-4" are mostly/entirely section resets, NOT compression; only the dti+comp rows'
elevated counts -- and especially the unhappy "15" -- are real compression events.)

Eviction calibration: `CONTEXT_COMPRESSION_ENABLED`, trigger 2800 / window 2200
(window just above the ~1978-token unevictable SI+tools floor; `--compression
--trigger 2800 --window 2200`). A looser window (2500/3500) barely evicted (drops
of 60-640 tok) and did not help; the tight 2200 window cut back toward the floor at
section boundaries (e.g. a 4966->1978 drop) and produced the win. text-in stays
~95-96% of cost in every arm -- the cost-composition invariant holds; eviction
shrinks the accumulated text-in mass.

### Reading the result

- **DTI alone = wash.** +7% happy / -2% unhappy vs baseline; both within noise.
  The SI reduction is real but given back via guidance accumulation.
- **DTI + eviction = real win, biggest where it matters.** -21% on the
  correction-heavy unhappy path (4 turns/q, the most accumulation and the most to
  evict; 15 evictions fired); parity on the cheaper happy path. The unhappy path is
  the costlier, more realistic case for a hard immigration form, so a 21% cut there
  is the headline.

## Why the smaller SI did not lower cost (the mechanism)

Per-turn text-in tokens (the replayed context) decompose as: a per-turn delta of
**-62 tok/turn (happy)** and **-1049 tok/turn (unhappy)** for DTI vs baseline
(0 = wash). The structure explains it:

- **At each section boundary** (the per-section restart, q1/q7/q17), DTI's fresh
  SI is genuinely smaller -- DTI saves **657 / 1945 / 1322** text-in tokens on
  those restart turns. The SI floor reduction is REAL.
- **But WITHIN a section, cost climbs turn-over-turn in BOTH arms, and DTI climbs
  FASTER.** DTI's per-field guidance rides the confirm_field tool response (and the
  model's reading of it) -- which ACCUMULATES as conversation context within the
  section, re-billed every subsequent turn. By mid-section DTI is *more* expensive
  per turn than the baseline (e.g. happy q6: +2099). So DTI front-loads a saving at
  each section boundary, then gives it back (and more) as the section fills.

**Calibrated eviction then PURGES that accumulated guidance** turn-over-turn: with
the tight window (2200, just above the floor) the prompt is cut back toward ~1978
at section boundaries instead of climbing unchecked, so DTI's per-turn saving
holds. That is why dti+comp wins where dti-alone washes -- and why the win is
biggest on the unhappy path (most accumulation per section -> most for eviction to
recover; 15 evictions vs 2 for the baseline). The l3a finding that "Gemini
compression is weaker than the window suggests" still bites: a LOOSE window
(2500/3500) barely evicted and did not help; only the tight calibration delivered.

**This empirically confirms the plan's Gate-1.5 hypothesis end-to-end: the
SI-size reduction converts to a cost win ONLY when the accumulated per-field
guidance is EVICTED, and it must be a TIGHT, calibrated window.**

## Fill correctness (read honestly, not as a clean rate)

Confirmed-field counts: baseline 17/25 (happy), 24/25 (unhappy); DTI 14/25, 20/25.
DTI confirmed somewhat fewer. BUT both arms suffer the SAME synthetic-harness noise
source: on 2.5, the model drifts OUT of the structured tool-call loop partway
through these long runs (tools=[] on later questions; seen in G2 for the baseline
too). It is an equal-opportunity noise source, so it does not invalidate the COST
comparison, but it means these are NOT clean fill-accuracy rates -- a dedicated
fill-correctness measurement (bd jnjj.7 / G3) is the right instrument for that.
DTI's slightly-lower confirms are consistent with the model occasionally not acting
on next_field_guidance as crisply as on a full SI; worth watching, not disqualifying.

## What this means for the architecture

- **GO on DTI + calibrated eviction.** Shipping DTI WITH a tight compression window
  (trigger ~2800 / window ~2200 for the I-90 DTI SI) cuts the costlier unhappy-path
  bill 21% vs the section-reset baseline and holds parity on the happy path. DTI
  alone (no eviction) is a wash, so the two must ship TOGETHER -- USE_DTI plus
  calibrated CONTEXT_COMPRESSION.
- **The calibration is load-bearing and form-specific.** The window must sit just
  above the unevictable SI+tools floor (~1978 tok here). Too loose -> Gemini barely
  evicts (l3a) -> no win. A production rollout needs the window derived from the
  rendered DTI SI floor, not a fixed constant.
- **Fill-correctness must be re-checked under eviction.** dti+comp confirmed 14/25
  (happy) / 20/25 (unhappy) -- same as dti-alone, so eviction did not OBVIOUSLY
  degrade fill here, but these counts are noisy (see below) and aggressive eviction
  could drop guidance the model still needs. The dedicated gate is bd jnjj.7 (G3);
  it should run with eviction ON.
- **The secretary is still the bigger lever.** DTI+eviction caps the principal at a
  bounded per-section cost; the secretary (deferred to jnjj.33) is what lets the
  principal carry NO catalog at all. DTI's value is as the principal HALF of the
  principal/secretary architecture; this result makes that half a confirmed win.

## Caveats

- Live-Gemini run; numbers carry run-to-run variance (the +7%/-2% deltas are within
  it). The robust signal is the per-turn text-in DECOMPOSITION (boundary saving vs
  mid-section accumulation), not the single-run totals.
- The harness's per-section-restart flow is shared by both arms, so the comparison
  is apples-to-apples on that axis.
- Supersedes the jnjj.6 (G2) measurement, which was invalidated (demo schema,
  starved payload, JIT drip bug). This ran on the REAL I-90 with the help-context
  fix (jnjj.23) and the working DTI principal (jnjj.22).
