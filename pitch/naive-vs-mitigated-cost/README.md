# Naive vs. mitigated cost curve -- full I-90 form fill (113 questions)

**Headline: $2.66 mitigated vs. $18.74 naive -- a 7.1x cost reduction.**

> **2026-11-18:** the default voice model is now `gemini-3.8-live`. The investor demo
> still serves 2.5 until it is redeployed. The figures below are the 2.5 record. Read the dated update at the end before quoting any number.

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

## 2026-11-18 update: repricing for gemini-3.8-live

The curves above are from a **gemini-2.5 native audio** run, the July 2026 production model, and stay as the measured record. The default voice model is now `gemini-3.8-live`; the investor demo still serves 2.5 until it is redeployed. 3.8 list prices are $0.75 per 1M tokens for text input (2.5: $0.50) and $4.50 for text output (2.5: $2.00). Audio rates are unchanged.

**The same conversation repriced at 3.8 rates:**

| | Mitigated | Naive | Reduction |
|---|---|---|---|
| 2.5 rates (measured run, above) | $2.66 | $18.74 | 7.1x |
| 3.8 rates, SAME token counts | $3.05 | $27.17 | 8.9x |

- **The ratio grows on 3.8.** The naive baseline is mostly re-sent text, and text input is the line 3.8 made more expensive. Mitigation matters more on 3.8, not less.
  - How the naive line was split: the Methodology above says the naive curve reuses the measured run's per-question voice-in, voice-out and text-out. So its text-input cost is the remainder, about 90% of the naive total, and only that part was repriced.
  - The script that built the naive curve is not in the repo. This split is inferred from the method as described, not re-derived. Question 1, where nothing has accumulated yet, is consistent with it: naive $0.0086 vs mitigated $0.0086.
- **This is a REPRICING, not a 3.8 run.** It holds every token count from the 2.5 run fixed and changes only the prices. Two things on 3.8 add cost that repricing cannot see:
  - it speaks about twice as much audio per form;
  - it reports thinking tokens, priced at the output rate. The one reconciled 3.8 billing day did NOT show thinking as billed text output (n=1, `scripts/spikes/3p8_deployed_telemetry_findings.md`), so treat that line as an upper bound.
- **How big the gap is, and what a measured 3.8 I-90 would likely cost.**
  - Repricing alone raises this I-90 run about 15% ($2.66 -> $3.05). The run is audio-heavy, and audio prices did not change.
  - On the like-for-like W-7, repricing the 2.5 cost split in `scripts/spikes/3p8_cost_bench_findings.md` gives about +23%, while the measured 3.8 cost is about +30%. The extra ~6% is 3.8's behavior.
  - A measured 3.8 mitigated I-90 would therefore likely land between **about $3.2** ($3.05 plus that ~6%) and **about $3.5** ($2.66 plus W-7's full +30%). Treat that range as an extrapolation.
- **Why the I-90 README says about $3.2.** It applies the full +30% to a different base run:
  - here, this single SPANISH-language 2.5 run ($2.66 all-in; the helper models add only $0.002);
  - there, the 3-run mean of the English stress-test series ($2.44 all-in).
- **There is no measured full-I-90 run on 3.8 yet.** The current I-90 kit does not complete on 3.8 (bd `polyglot-pdf-r3ham.10`), so this chart cannot be re-drawn from a 3.8 run until it does.
- The same caveats as above apply. The naive curve is a model, and both curves move with Google's price list.
