# jnjj.25: DTI principal cost vs section-reset baseline (real I-90)

*Date: 2026-06-18. Epic: polyglot-pdf-jnjj. Instrument:
`scripts/spikes/measure_form_session_costs.py` (`--schema i90 --arm {section-reset,dti}`).
Model 2.5 (`gemini-2.5-flash-native-audio-preview-12-2025`), live Gemini,
GEMINI_API_KEY. 25-question plan over the first 3 real I-90 sections. 4/4 cells ran.
Data: `scripts/spikes/data/costs_i90_2.5_*_20260618T0205*.csv` + `.meta.json`.*

## Verdict: QUALIFIED NO-GO on DTI-as-built (without eviction)

DTI's per-turn system instruction (SI) is **34% smaller** than the section-reset
full-SI baseline (3786 vs 5718 chars on the I-90), but that does **NOT** convert
to a comparable run-cost reduction: DTI is a **wash on the happy path** and only a
**~2% win on the unhappy path**. The big SI-size reduction is eaten by per-field
guidance ACCUMULATING within a section. **DTI-as-built (no eviction) is NOT the
cost win the SI-size reduction implied.** The fix is measured-but-untested
(calibrated eviction; see "Why" below) -- this is a NO-GO on shipping DTI for cost
*as-is*, and a GO on the next step being the eviction experiment, not abandoning
DTI.

## The matrix (25 questions; happy = 2 turns/q, unhappy = 4 turns/q)

| arm | path | SI chars | run $ | total tokens | confirmed | text-in share |
|---|---|---:|---:|---:|---:|---:|
| section-reset (full-SI baseline) | happy | 5718 | **$0.2219** | 278,673 | 17/25 | 95.7% |
| section-reset (full-SI baseline) | unhappy | 5718 | **$0.5596** | 756,874 | 24/25 | 96.0% |
| dti (Dynamic Turn Injection) | happy | 3786 | **$0.2378** | 278,363 | 14/25 | 95.3% |
| dti (Dynamic Turn Injection) | unhappy | 3786 | **$0.5490** | 730,241 | 20/25 | 95.9% |

DTI vs baseline: **+7% on happy ($0.2378 vs $0.2219), -2% on unhappy ($0.5490 vs
$0.5596)**. Both within run-to-run noise. text-in is still ~95-96% of cost in BOTH
arms -- the cost-composition invariant holds; the SI just isn't the only thing in
text-in.

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

The happy path (fewer turns/section) barely amortizes the boundary saving -> wash.
The unhappy path (4 turns/q, more restarts relative to fills) amortizes it a bit
more -> a modest 2% net win.

**This empirically confirms the plan's Gate-1.5 hypothesis: the SI-size reduction
only converts to a cost win if the accumulated per-field guidance is EVICTED
(context-window compression) rather than replayed every turn.** DTI without
eviction is structurally a wash.

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

- **NO-GO on DTI for cost as-is.** Shipping DTI today (USE_DTI) would shrink the SI
  but not the bill -- the per-field guidance accumulation cancels the saving.
- **The next experiment is calibrated eviction, NOT abandoning DTI.** The data
  points directly at it: DTI + a compression window sized to ~the static SI would
  evict the accumulated per-field guidance turn-over-turn, so DTI's boundary saving
  is no longer given back mid-section. That is the untested arm that could flip this
  to a real win. (The harness has a `sliding-window` arm; a `dti + compression`
  cell is the natural follow-up.)
- **The secretary is still the bigger lever.** DTI alone caps the principal at a
  per-section restart cost; the secretary (deferred to jnjj.33) is what lets the
  principal carry NO catalog at all. DTI's value is as the principal HALF of the
  principal/secretary architecture, not as a standalone cost play.

## Caveats

- Live-Gemini run; numbers carry run-to-run variance (the +7%/-2% deltas are within
  it). The robust signal is the per-turn text-in DECOMPOSITION (boundary saving vs
  mid-section accumulation), not the single-run totals.
- The harness's per-section-restart flow is shared by both arms, so the comparison
  is apples-to-apples on that axis.
- Supersedes the jnjj.6 (G2) measurement, which was invalidated (demo schema,
  starved payload, JIT drip bug). This ran on the REAL I-90 with the help-context
  fix (jnjj.23) and the working DTI principal (jnjj.22).
