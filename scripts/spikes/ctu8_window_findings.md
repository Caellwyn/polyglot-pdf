# Continuous DTI + compression-window findings (bd polyglot-pdf-ctu8)

*2026-07-06. Written for the product owner. Recommends a production compression
window for the continuous-DTI I-90 flow and the exact knob to set it.*

## The question

We want compression windows to REPLACE the section-reset mechanism: one
continuous DTI voice session that manages its own memory with a sliding window,
instead of chopping the form into sections and restarting the AI at each
boundary. Two things had to be true to recommend the switch: it must cost no more
than sections, and it must keep the conversation coherent. This measures the
window size on the real I-90.

## Recommendation

**Go -- use a compression window of ~3500 tokens (trigger fixed at 5000).** On the
measured I-90 it is both the most coherent window tested AND cheaper than the
section-reset flow it replaces. Set it in production via
`CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS = 1500` (see "The knob" below) -- NOT
the headroom knob.

## What we measured (continuous DTI, real Gemini on Vertex, I-90, happy path)

| Window | Fill accuracy | Projected $/174-q form | Notes |
|---|---|---|---|
| 3000 | 47% (16/34, 1 run) | ~$1.35 | tighter window evicts too hard -- strips guidance, fill drops |
| **3500** | **73% (22/34) + 93% (28/30), mean 83%** | **~$1.15** | live-validated; coherent across 7-8 evictions, zero errors |
| (section resets, prior measure) | -- | ~$2.32 | the incumbent this replaces (go/no-go brief, bd 6x1y) |

(The two 3500 runs differ in question count -- one ran the full 34-question plan,
one the 30-question plan from the DTI-fix session; both are continuous DTI +
compression at 5000/3500. The spread 73-93% reflects real run-to-run variance on
a ~30-question fill, not a config difference.)

**IMPORTANT comparison caveat (not apples-to-apples).** The window costs above are
measured on the HAPPY path only. The ~$2.32 section-reset baseline is an 80/20
happy/unhappy MIX (go/no-go brief, bd 6x1y). Unhappy turns cost more (more turns
per question), so the honest happy-vs-happy baseline is LOWER than $2.32 -- the
real cost advantage is smaller than the raw $1.15-vs-$2.32 (~2x) suggests. The GO
direction still holds (window is cheaper on any like-for-like basis, and by a wide
margin at 20 questions in the brief's own data), but do NOT quote "2x cheaper" as
a clean figure. To close this, measure an unhappy-path window run and recompute an
80/20 window number before the flag flip -- a cheap follow-up, not a blocker for
the demo test-drive.

All runs: trigger pinned at 5000 (the Vertex API floor -- see below), one
continuous session (verified: `schema_scope=continuous-full-plan`, prompt curve
never resets to base), full 34-question I-90.

### The counterintuitive result

A SMALLER window is not cheaper here. Squeezing to 3000 made eviction so
aggressive that it stripped the model's own field guidance -- fill accuracy fell
to 47% -- while cost did NOT drop (its churn actually raised the steady-state
context). 3500 sits in the sweet spot: enough recent context to stay coherent,
tight enough to hold cost near half the section-reset baseline. So "remember less
to save money" backfires below ~3500; 3500 is the floor of the coherent band, not
a point on a smooth cost-vs-memory tradeoff.

## The two hard constraints that shaped this

1. **Vertex floors the trigger at 5000 tokens.** The Live API rejects any
   compression `trigger_tokens` below 5000 at connect (wire-verified 1007). The
   I-90's DTI instruction floor is only ~1978 tokens, so the "tight trigger just
   above the floor" idea from earlier calibration is dead on Vertex -- the trigger
   is pinned at 5000, and we tune only the window beneath it. (Fixed in the
   adapter by clamping + re-tuning; bd choa/ezg2/8vy3, PR #321.)
2. **The window must stay above the ~1978 instruction floor.** Evict below it and
   you start stripping the model's own guidance -- exactly the 3000-window
   degradation above. So the usable window band is ~1978 < window < 5000, and 3500
   sits comfortably inside it.

## The knob (this is the trap -- get it right)

Production derives the window per form. For the I-90 the derived trigger (~3177)
is BELOW the 5000 Vertex floor, so the clamp ALWAYS fires and RE-TUNES the window
to `trigger - margin = 5000 - CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS`.
Therefore:

- **`CONTEXT_COMPRESSION_WINDOW_HEADROOM_TOKENS` does NOT set the window here.** It
  only affects the pre-clamp derived window, which the re-tune overwrites. Setting
  it is a no-op for any form whose trigger is clamped (the I-90 always is).
- **To land the window at 3500, set `CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS =
  5000 - 3500 = 1500`.** (Or bypass derivation and pin
  `CONTEXT_COMPRESSION_WINDOW_TOKENS=3500` with `DERIVE_FROM_SI_FLOOR=False`.)
- Caveat for a future form whose UNCLAMPED trigger already exceeds 5000: the clamp
  does not fire, and there the HEADROOM knob is the lever. The correct knob is
  form-dependent; the I-90 is always-clamped, so margin is the lever.

## Method + honesty check

- Driver: `scripts/spikes/measure_form_session_costs.py --arm dti --continuous
  --compression --trigger 5000 --window <W> --schema i90 --vertex`.
- Analysis: `scripts/spikes/analyze_continuous_window.py` -- reads the continuous
  runs (which the 20-question `cost_matrix_lib` cannot ingest), fits per-question
  growth + post-eviction steady level from the CSV's MEASURED per-question text-in
  series, and projects to full form length with a saturating-ramp model.
- Honesty check: each projection reports the modeled-vs-measured ratio at the
  run's own length. The 3500 cell fits at ratio 1.00 (trustworthy); the 3000 cell
  at 1.19 (single noisy run -- treat its cost as indicative, its 47% fill as the
  real signal).

## Confidence + limits

- The 3500 recommendation rests on 2 live-validated runs (83% fill, 0 errors,
  ratio 1.00) plus the clean 30-q reliability run from the DTI-fix work. Solid for
  a demo rollout; not a large sample.
- 4000 (a looser window) was NOT measured -- deferred per the budget decision to
  stop at 3500. If a coherence issue shows up in the demo, 4000 is the first thing
  to try (more recent context, at somewhat higher cost).
- A pre-clamp 2800/2200 cell (3 runs, committed with the DTI-fix work before the
  Vertex trigger clamp shipped) is excluded from the recommendation: its trigger
  2800 is below the 5000 API floor, so 2 of its 3 runs died with connection errors
  and never evicted -- obsolete under the current always-5000-trigger architecture.
  The analyzer surfaces it but flags its fit as untrustworthy (honesty ratio 2.40).
- Second gold form (beyond the I-90) is a separate follow-up; this establishes the
  I-90 number + the method.

## Rollout status

- GoAway/reconnect for continuous sessions: DONE (bd l3a.2, PR #331 -- silent
  pre-emptive resume). The full-form continuous demo is no longer gated on the
  ~9-10 min Vertex cap.
- Remaining to activate on demo: set the window knob (margin=1500), flip
  `CONTEXT_COMPRESSION_ENABLED` + `USE_DTI`, local test, then the gated
  `deploy-demo.sh` (per-instance maintainer yes + post-deploy test-drive).
- Do NOT remove the section-reset machinery in the same change that flips the
  flag -- validate the continuous flow on the demo first, retire sections second.
