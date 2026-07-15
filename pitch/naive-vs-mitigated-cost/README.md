# Naive vs. mitigated cost curve -- full I-90 form fill (113 questions)

**Headline: $2.66 mitigated vs. $18.74 naive -- a 7.1x cost reduction.**

## What this shows

Cumulative dollar cost of filling out the full I-90 immigration form by voice,
question by question, comparing two scenarios:

- **Mitigated** -- the actual, measured cost of the current production
  pipeline. Real numbers from a live 113-question run on Gemini 2.5 (native
  audio), happy path.
- **Naive** -- what the same conversation would have cost with no cost
  mitigation at all: the full form schema and system instruction resent in
  full on every turn, and the entire conversation history accumulating
  without ever being trimmed. This scenario was never actually run at full
  scale (it would be needlessly expensive to run for real), so it is
  **derived**, not measured -- see Methodology below for exactly how.

Cost mitigation techniques are treated as proprietary and are intentionally
not named or described here or in the chart.

## Files

- `charts/naive_vs_mitigated_cost.html` -- standalone interactive chart
  (open directly in a browser, no server needed).
- `data/naive_vs_mitigated_cost_curve.csv` -- per-question and cumulative
  cost for both curves, 113 rows.
- `data/source_mitigated_run_raw.csv` / `source_mitigated_run_summary.json`
  -- the underlying real run this analysis is built from (copied from
  `scripts/spikes/data/`).

## Methodology

**Mitigated curve:** directly measured. Copied per-question costs from a
real 113-question happy-path I-90 session (`gemini-2.5-flash-native-audio`),
computed at run time from each turn's actual `usage_metadata` token counts
and Google's published per-token rates ($0.50 / $3.00 / $2.00 / $12.00 per 1M
tokens for text-in / voice-in / text-out / voice-out). Cumulative = running
sum of per-question cost.

**Naive curve:** derived from three real, measured inputs, not invented:

1. **The actual spoken conversation.** Per-question voice-in, voice-out, and
   text-out token counts are taken from the *same* real run above, so the
   conversation content is identical between the two curves -- only the
   context-management strategy differs.
2. **A full-form (132-field) system instruction size**, fit from real
   measured data: full (non-mitigated) system-instruction character counts
   were measured across 12 form sections of varying field count (a
   different schema), giving a strong linear fit --
   `chars = 117.51 x fields + 3234.75` (R-squared = 0.998) -- applied to the
   I-90's 132 fields: ~18,746 chars, ~4,687 tokens. This is the one
   **estimated** (not directly measured) input; see Caveats.
3. **The same real per-token billing rates** as the mitigated curve.

The naive per-turn cost model: on turn *n*, the billed prompt = the full
system instruction/tooling floor (~5,342 tokens, constant, resent every
turn) **plus every prior turn's spoken content** (nothing is ever evicted).
Cost = tokens x rate, summed cumulatively across all 113 questions.

## Caveats (read before citing the dollar figures externally)

- The naive baseline is a **model, not a live measurement**. No one has run
  the full 132-field I-90 with zero mitigation end-to-end (it isn't a
  configuration worth spending real API budget on). Treat $18.74 as a
  defensible estimate, not an audited number.
- The full-SI-size-vs-field-count relationship (point 2 above) was measured
  on a *different* form schema (a mental-health intake form, not the I-90's
  own sections) and extrapolated to the I-90's field count. The fit quality
  is very strong (R-squared = 0.998) but it is still an extrapolation across
  forms.
- The 7.1x reduction is for the **happy path only** (no corrections, no
  detours). The unhappy path (user corrections, backtracking) is typically
  costlier in both scenarios and was not modeled here.
- Both curves use the same live-Gemini pricing snapshot; if Google changes
  per-token rates, both numbers move together and the ratio is unaffected,
  but the absolute dollar figures would need updating.
