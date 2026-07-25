---
date: 2026-07-25
bead: polyglot-pdf-g0ka
title: "Verify judge reframed to the language-lock bar (intelligible, in-language)"
tags: [conventions, testing]
---

## Trigger

Maintainer reframing (2026-07-25, memory
`translations-are-drift-anchors-not-display`): the baked translations'
consumer is the VOICE MODEL -- effectively a fluent speaker -- and they
exist to prevent language drift (the live failure that started the epic: a
Spanish session slipping into English, once Portuguese). The verify judge
was optimizing semantic fidelity instead, producing V5's 87-entry worklist
of mostly word-choice quibbles (the cross-family audit accepted 80/81 of
its kept originals). Bead `polyglot-pdf-g0ka`, filed from the accepted
recommendations.

## What shipped

- `TextAIGemini._JUDGE_RULES` rewritten around the language-lock bar: a
  purpose preamble (voice-model consumer, never a displayed form,
  intelligible-and-in-language bar), "imperfect-but-intelligible word
  choice" added to NOT-drift, and WRONG LANGUAGE / mixed-language /
  unintelligible now LEADING the DRIFT list. Every V1-evidence clause
  survives verbatim (back-translation anchoring guard zh-g07,
  never-flag-your-own-proposal + conventional-rendering zh-g11, register,
  negation, option-mismatch, numbers). Byte-stable constant, pinned by
  `test_judge_rules_carry_the_language_lock_framing`.
- **Regression check (live, $0.41 across two runs):** the first probe
  re-run (Run 3, $0.21) turned out to exercise the OLD prompt -- the probe
  carried its own stale copy of the judge rules (fresh-eyes catch). The
  probe now IMPORTS the production adapter's `_JUDGE_RULES` (aliasing
  pinned by `test_probe_judges_with_the_production_rules`), and the real
  re-run (Run 4, $0.20) proves recall under the reframe: 14/14 plants at
  the same layers, es gold 15/15 clean, zh gold FP 1-2 (baseline range).
  Both runs recorded in `scripts/spikes/translation_gate_findings.md`.
- **FP-reduction measurement (live, ~$0.02):** the Pub-850 gold set is
  floor-FP and cannot show the over-flag drop, so a new spike
  (`scripts/spikes/translation_judge_quibble_ab.py`) judges the 14 V5
  judge-origin unresolved keeps that the cross-family audit certified
  acceptable: old prompt 14/14 flagged -> reframed prompt **9/14 and
  8/14 across two runs (-36% to -43%)**, committed artifact
  `scripts/spikes/data/quibble_ab_results.json`,
  with the residual flags substantive (omitted "first name" concepts,
  Suite->Office narrowing, the IRSN case bd c6td retires) rather than
  stylistic.
- Fresh-eyes triage: Opus round 1 -- GAPS-FOUND (2), both adopted: (1)
  the probe's stale local judge-rules copy invalidated the recall check
  (fixed by importing the adapter constant + aliasing pin + live Run 4);
  (2) the prompt pin missed several load-bearing V1 clauses (pin
  extended to all of them). Opus round 2 cleared. Rejected: none.

## Lessons

- A floor-FP gold corpus cannot measure a precision improvement -- the
  measurement set has to contain the false positives you are trying to
  eliminate. The V5 worklist (audit-certified keeps) was exactly that set,
  free.
- The exit criterion as filed assumed the probe's gold set would show the
  FP drop; reconciling a criterion against what the corpus CAN measure --
  and saying so -- beats gaming the number.

## Doc freshness

- `scripts/spikes/translation_gate_findings.md` -- Run 3 appended (the
  probe doc is the chronological audit trail for this probe by design).
- No tier-1/tier-2 doc tracks the judge prompt internals; reviewed and
  left as-is.

## Files touched

- `backend/adapters/text_ai_gemini.py` -- _JUDGE_RULES language-lock rewrite
- `backend/tests/unit/test_text_ai_gemini.py` -- prompt-framing pin
- `scripts/spikes/translation_judge_quibble_ab.py` -- new quibble-set FP spike
- `scripts/spikes/translation_gate_findings.md` -- Run 3 record
- `scripts/spikes/data/translation_gate_20260725T071117Z.csv/.meta.json` -- probe outputs
