---
date: 2026-07-25
beads: [polyglot-pdf-ce62, polyglot-pdf-wsao]
tags: [authoring, extraction, instructions, secretary, planning]
---

# Sprint 16 planned: instructions enrichment (bd ce62; epic wsao)

## What happened

A maintainer-driven audit of the form schemas' `help.instructions` property,
followed by a two-round design discussion and an adversarial review round,
produced the sprint-16 plan-of-record
(`docs/sprint_16_instructions-enrichment_plan.md`) and the epic
`polyglot-pdf-wsao` with 7 dependency-wired children.

## Key recon findings (verified against code, not briefs)

- **The extraction LLM is never asked for instructions.** The FIELD SHAPE
  contract (`scripts/bakeoff/schema_contract.py` ~L240-276) has no `help`
  key; all shipped guidance comes from the /TU tooltip copy + the optional
  shallow booklet substring match (bd s4dp.3), whose deep-ingestion follow-up
  was explicitly deferred.
- **Coverage is bimodal for mechanical reasons:** i-90 132/132 (rich /TU on
  all 195 widgets; median 75 chars; at least one factual error -- the
  `p3_line9_heightinches3` text says "weight in pounds"); w7 **0/59** (zero
  /TU; the booklet enrichment never ran despite
  `form-kits/w7/w7-instructions.pdf` sitting in the kit dir).
- **No lint, judge, or metric for guidance quality exists anywhere.**
- `help.instructions` rides the spoken ask-hint verbatim (bo4m "Context to
  briefly convey when asking") -- so guidance length directly shapes every
  ask turn, which drove the depth-model design.

## The decision (see the plan's decision record for the full trail)

Decoupled storage/delivery: extraction always emits BOTH a short synthesized
`help.instructions` and a new verbatim `help.details` excerpt channel
(booklet-containment lint makes it zero-trust); v1 delivery injects both
inline for the current field (compression makes the cost transient), the
ask-hint carries only the short text, and the secretary catalog gets details
plus a whole-booklet floor for form-level questions. Secretary-mediated
delivery (hooks + widened ask_secretary) is pre-designed phase 2, gated on a
voice-harness attention measurement (wsao.2) that runs BEFORE the enrichment
engine is built.

## Scar / notes

- The adversarial review caught two load-bearing gaps worth remembering:
  a field-keyed guidance design silently drops the booklet's FORM-level
  content (eligibility, documents, where-to-mail) unless something holds the
  whole booklet; and a "no provenance record => human-owned" no-clobber rule
  makes any legacy-kit refresh a silent no-op without a bootstrap pass.
- Sprint-15 (relationship extraction, epic o2bs) and this epic share the
  W-7 box-h interlock territory: machine-actionable conditionality is o2bs;
  spoken guidance is wsao. Both plans cross-reference.
