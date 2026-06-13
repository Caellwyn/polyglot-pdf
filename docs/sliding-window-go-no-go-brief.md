# Go/no-go brief: sliding-window context management

*2026-06-12, bd polyglot-pdf-6x1y (epic hcsl). Written for the product owner.
Every number traces to the analysis notebook
([`scripts/spikes/cost_matrix_analysis.ipynb`](../scripts/spikes/cost_matrix_analysis.ipynb))
and its tidy data exports; the computation code passed a 3-round adversarial
review before any conclusion was written on top of it.*

## The question

Should we replace the section-by-section session restarts with one continuous
conversation that manages its own memory (Gemini's sliding-window compression)?

## What we now know (measured)

1. **Text input is the bill.** 95-98% of what we pay on the production model
   is the instruction text and accumulated conversation we re-send every turn.
   Audio is almost free by comparison. Your original cost finding, confirmed
   under controlled conditions.
2. **The compression feature works on both models** -- it evicts old
   conversation, costs nothing in responsiveness, and the old crash mystery is
   solved (our test setup, not the feature).
3. **But compression cannot touch the instruction text** -- and with today's
   full-form instruction (~8,200 tokens re-billed every turn), there is almost
   nothing left for it to evict. Measured at 20 questions: the sliding window
   saved ~0-2% vs doing nothing, while your section system saved ~45%.
4. **Compression also does not solve session lifetime.** A compressing session
   was still cut off by Google's ~13-15-minute duration limit; a whole-form
   session needs the reconnect-and-resume machinery (partly built) no matter
   what.

## What the modeling says (trusted code, best-case assumptions)

Projected to a full 174-question form (happy/unhappy 80/20, text-in, fast
model), keeping ~1,750 tokens of recent conversation in memory:

| Flow | Cost per form |
|---|---|
| No management at all (unbounded single session) | ~$13 |
| Sliding window over today's full instruction dump | ~$2.38 |
| **Your section system (today's production)** | **~$2.32** |
| Sliding window over the JIT manifest (already built, never measured live) | ~$1.34 |
| Sliding window with drip-fed schema (your proposal: discovery tools + evictable schema) | ~$0.86 |

Two design facts fall out of the elbow analysis:

- **Window size barely matters; the instruction size is everything.** Cost is
  nearly flat in how much memory you keep -- so choose memory for conversation
  quality (~1,500-2,000 tokens is roughly the last 3-6 exchanges), and spend
  the effort on the instruction diet.
- **The naive port loses.** A sliding window over today's full dump is no
  cheaper than sections at any scale. The window only wins TOGETHER WITH the
  lean schema feeding you proposed -- then it wins by 42-63% AND removes 14
  mid-form restart pauses from the user experience.

## Recommendation

**Go -- but on the lean-schema path, gated by one cheap measurement.**

1. First fix the silent field-save error on the fast model (bd `d24n`) -- it
   muddies every reliability number.
2. Run ONE measured cell of the JIT-manifest flow with a right-sized window
   (about trigger 7.3k / window 5.6k): it converts the $1.34 row from model to
   measurement and tests whether eviction fires reliably in that regime.
3. Add a recall check: after eviction, the model must look up forgotten
   answers with its tools instead of guessing.
4. If that cell lands near the model, plan the cutover epic (single session +
   JIT/drip feeding + window + the reconnect/resume work, which is needed
   regardless). If it lands near the unbounded line, keep sections -- they
   remain an excellent, measured baseline -- and bank the d24n fix and the
   session-lifetime work anyway.

The middle path also exists (fewer, larger sections with a window inside
each); it trades some savings for smaller change risk.

## Your decision

- **GO (lean-schema path):** I file the follow-up beads (d24n fix is already
  filed; JIT measurement cell; recall gate; then the cutover epic via
  /plan-epic).
- **NO-GO:** sections stay; d24n and the session-lifetime beads proceed on
  their own merits.
- Either way the decision gets recorded on the epic bead per the rubric.
