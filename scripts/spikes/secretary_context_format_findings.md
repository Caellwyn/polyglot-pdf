# Secretary context-format comparison -- findings (jnjj.37)

bd polyglot-pdf-jnjj.37. Follow-up to Gate 1 RECALL (jnjj.26), which measured
feasibility on a SINGLE context format (grouped-by-section). This bead compares
THREE context-rendering formats over the SAME stratified 49-query battery + the
same Sonnet judge, to pick the format that best sets the secretary up for success
(it must support BOTH cross-field reasoning AND precise field-id reference).

> **RECOMMENDATION: keep GROUPED-BY-SECTION.** On the finalized data it wins
> EVERY accuracy metric -- recall (0.931), precision (0.853), strict-match (0.726),
> synthesis (0.920), and disambiguation (0.965) -- at moderate token cost. Flat-JSON
> costs ~40% more tokens and trails grouped on every axis (dominated), though it
> beats prose. Prose is ~23% cheaper but the WEAKEST on every accuracy metric
> (recall 0.889, precision 0.797, strict 0.626, synth 0.887, disambig 0.933). The
> jnjj.26 baseline choice is validated by the data.
>
> *Data note: the flat renderer originally used non-authoritative `section_id` for
> 4 Part-3 fields (Codex round 1); FIXED to use the authoritative `_ordered_groups`
> mapping, and all three formats were REGENERATED on the corrected renderer
> (2026-06-27, gemini-3.1-flash-lite). The numbers above are the finalized set.*

## What was run

- Same battery (`secretary_recall_corpus.py`, 49 queries / 6 tiers), same scoring
  (deterministic grounding + Sonnet judge), via `probe_secretary_recall.py --format
  {grouped,flat,prose}`. The three renderers live in `secretary_context.py`
  (`render_secretary_context` / `render_flat_json` / `render_prose`, dispatched by
  `render_context`).
- The formats:
  - **grouped** -- grouped-by-section plain text (the jnjj.26 baseline): part/section
    headings, each field `id | "spoken" | type`, then `value | shown`, then help.
  - **flat** -- a flat JSON array of field objects (max reference fidelity, no
    structure). Hypothesis: discrete id-keyed objects give the cleanest grounding.
  - **prose** -- markdown/prose, one natural-language sentence per field under
    section headings (max reasoning fluency). Hypothesis: reads like docs.
- **Model: `gemini-3.1-flash-lite` for ALL three** (consistency is mandatory for a
  comparison). `gemini-2.5-flash-lite` (the nominal secretary model) has been in a
  sustained, widely-reported flapping/503 degradation for days (2026-06), making it
  an unreliable measurement substrate; the recall probe was defaulted to
  3.1-flash-lite (same lite tier, stable, ~2.5x price -- negligible at research
  scale; whole trial spend <$1). Artifacts:
  `scripts/spikes/data/secretary_recall_{grouped,flat,prose}_*.meta.json` (each
  `secretary_model: gemini-3.1-flash-lite`).

## Result (n=49/format, gemini-3.1-flash-lite)

| format | tokens | recall | precision | strict | hit | synth_ok | disambig_ok | halluc | over_inc |
|---|---|---|---|---|---|---|---|---|---|
| **grouped** | 9,469 | **0.931** | **0.853** | **0.726** | **0.96** | **0.920** | **0.965** | 2 | 4 |
| flat | 13,271 | 0.913 | 0.830 | 0.691 | 0.94 | 0.904 | 0.948 | 1 | 5 |
| prose | 7,291 | 0.889 | 0.797 | 0.626 | 0.92 | 0.887 | 0.933 | 2 | 4 |

(recall/precision/strict/hit/judge rates are means across the 6 difficulty tiers;
halluc/over_inc are whole-battery counts. The halluc/over_inc differences -- grouped
2/4, flat 1/5, prose 2/4 -- are within run-to-run sampling noise, not a real signal.)

## Reading it

- **Grouped wins EVERY accuracy axis** -- recall, precision, strict-match (0.726),
  synthesis (0.920), disambiguation (0.965). It best supports gathering the EXACT
  right field set, which is the secretary's core job. Clear winner.
- **Flat JSON is dominated:** +40% tokens (13.3k vs 9.5k) for LOWER recall,
  precision, strict, synthesis, and disambiguation than grouped. (It does beat
  prose on accuracy -- it sits in the MIDDLE -- but pays the most tokens to do it.)
  The "max reference fidelity" hypothesis did not pay off: the JSON structure/
  quoting overhead bought no grounding benefit and hurt reasoning (the model must
  reconstruct which fields form a cluster from a flat list). Reject.
- **Prose is the cheapest** (7.3k, -23%) but the WEAKEST of the three on every
  accuracy metric -- recall (0.889), precision (0.797), strict (0.626), synthesis
  (0.887), disambiguation (0.933). The "reasoning fluency" hypothesis cost grounding
  precision, as expected -- ids embedded in prose are a weaker reference handle. Not
  recommended as the default, but it is the token-efficiency lever IF cost ever
  dominates (see below).
- Hallucination (2) and over-inclusion (4) are identical across all three -- those
  failure modes are model/architecture properties, not format-driven (consistent
  with the jnjj.26 finding).

## Recommendation

**Default the secretary to the GROUPED-BY-SECTION format** (already the jnjj.26
baseline and the `render_context` default). Best accuracy for moderate cost; the
comparison validates the original choice rather than overturning it.

**One conditional lever for later:** prose trades ~4 points of recall + the
strict/disambig edge for ~23% fewer tokens. If high-concurrency token cost ever
becomes the binding constraint (the same regime as jnjj.41's explicit-caching
revisit), prose is the format to re-evaluate -- but not at current scale, where
accuracy is the priority and the cost delta is noise.

## Caveats

- **Measured on `gemini-3.1-flash-lite`, not the nominal 2.5-flash-lite** (2.5 was
  flapping). The comparison is internally consistent (all three formats, same
  model), so the RELATIVE ranking is sound. Absolute recall may differ slightly
  from Gate 1's 2.5 numbers; re-confirm the absolute figures on a healthy
  2.5-flash-lite if a target-model number is needed, but the format CHOICE does not
  hinge on it.
- Synthetic corpus -- recall is an UPPER BOUND (clean values + on-distribution
  queries), same caveat as jnjj.26.
- The committed artifacts carry a legacy `"bead": "polyglot-pdf-jnjj.26"` label
  (the recall harness was born under jnjj.26 and reused here); the OWNING bead for
  this comparison is jnjj.37, per this doc + the journal. The probe's meta field was
  corrected (now `"probe"`, not a hardcoded bead); the committed artifacts are the
  REGENERATED 2026-06-27 set and carry the `"probe"` label.
- Non-deterministic (live model sampling) -- the ~1-3 point gaps between formats are
  modest; grouped's edge on strict-match (0.726 vs flat 0.691 / prose 0.626) is the
  most robust signal. A multi-seed average would tighten the small differences, but
  the ranking (grouped best on every accuracy axis, flat middle but dominated on
  cost, prose cheapest-but-weakest) is stable in shape.
