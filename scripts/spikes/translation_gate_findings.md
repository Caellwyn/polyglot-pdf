# Translation-gate discrimination probe -- findings (V1, bd polyglot-pdf-i36i)

**Date:** 2026-07-24. **SDK:** google-genai 2.8+ (post-cutover). **Models:**
judge/rectify/ur-forward `gemini-2.5-pro` (thinking bounded 512), back-translate
`gemini-2.5-flash-lite`. Vertex (ADC). **Runner:**
`scripts/spikes/translation_gate_probe.py`; corpus
`scripts/spikes/data/translation-gate/gold.json`; raw run
`scripts/spikes/data/translation_gate_20260724T205304Z.{csv,meta.json}`.

**The question** (epic `polyglot-pdf-sekc` exit criterion 1; unanswered per the
Gate-1 audit -- W5/g1/g1c measured contradiction judges, never translation):
does mechanical lint -> independent lite back-translate -> bilingual pro judge
-> bounded pro rectify with full-loop re-entry catch PLANTED corruptions of
gold translations while NOT flagging the gold?

## GATE verdict: PROCEED to V3, with three named mitigations

- **(a) Planted corruptions caught: 14/14 (100%), every class, at the intended
  layer.** Judge-side plants (negation-flip, near-synonym/clean-round-trip
  trap, sibling-swap) caught by the judge in BOTH chunk arms in both
  languages; mechanical plants (numeral, DNT, mechanical+semantic) caught by
  the lint. Bonus: the es sibling-swap partner was caught by the glossary-PIN
  check before the judge ever saw it.
- **(b) Certified-good not flagged: es 15/15 clean (0 FP -- the language whose
  gold is directly Pub-850-verifiable). zh 13/15**; both zh flags are
  diagnosed below and drive the V3 mitigations. ur (observational, no gold):
  0 lint failures on live forward output -- the ASCII-digit pin and script
  check held on real Perso-Arabic text.
- **Cost: $0.2145 measured** (19 pro + 8 lite calls; 26.2k in / 9.2k out /
  8.9k thinking pro tokens) vs the $0.43 pre-run estimate and the plan's
  ~$0.25 authorization.

## Plants table (measure a)

| plant | class | layer intended | caught |
|---|---|---|---|
| es-p1 / zh-p1 | negation-flip | judge | judge, both arms |
| es-p2 / zh-p2 | near-synonym-swap (box->line; THE clean-round-trip trap) | judge | judge, both arms |
| es-p3 / zh-p3 (+partners) | sibling-swap | judge | judge both arms (es partner: PIN lint) |
| es-p4 / zh-p4 | numeral-alteration | lint | lint (digit-run) |
| es-p5 / zh-p5 | dnt-violation | lint | lint (DNT) |
| es-p6 / zh-p6 | mechanical+semantic | lint -> full-loop re-entry | lint; rectify restored BOTH halves (see measure c) |

The clean-round-trip trap behaved as theorized: p2's back-translation reads as
fluent plausible English ("Wages from Form W-2, line 1"); the judge caught it
from the original-vs-translation comparison, not the round-trip.

## The two zh flags, diagnosed (measure b)

1. **zh-g07 ("box 1" -> di-1-lan): back-translation-driven FP.** The chunk-50
   judge's own reason concedes the rendering "is a reasonable interpretation
   of 'box'" but anchors on the lite back-translation showing "line". This is
   EXACTLY the FP generator the plan pre-named ("suspect the back-translate
   layer first"). Mitigation (V3): harden the judge prompt's
   "back_translation is supporting evidence ONLY -- never flag on the
   back-translation when the translation itself is faithful" into an explicit
   NOT-drift bullet with an example; on a flagged string, re-verify with a
   one-tier-up back-translation before rectify (the plan's named fix).
2. **zh-g11 ("Dependent 1 first name" -> mingzi): unsatisfiable-criterion
   FP.** The judge rejected BOTH plausible renderings across two rectify
   rounds (mingzi -> ming -> mingzi), each time proposing the other. No zh
   rendering satisfies it. Mitigation (V3): the loop detects a FLIP-FLOP
   (rectify output equals a previously-rejected value -> stop, UNRESOLVED,
   one attempt saved) and the precision block gains "never flag a rendering
   you would yourself propose as the fix; do not flag conventional renderings
   as under-specific when no strictly better form exists."

Honesty note (the g1b corpus lesson): zh gold is model-seeded, not
agency-verified the way the es slice is; g07/g11 sit exactly on the two
renderings seeded with least confidence. The es slice -- the one directly
checkable against Pub 850 -- is the strongest evidence, and it is spotless in
both directions.

## Keep-rule readout (measure c) -- the review-round-3 collision, DECIDED

The planted half-success (p6: broken form number + flipped negation, rectify
given ONLY the mechanical reason) did NOT produce the collision: in both
languages rectify regenerated from the English original and fixed BOTH halves
in one attempt (lint-clean + judge-clean). Rectify sees the original, so it
re-derives; it does not minimally patch.

The collision materialized ANYWAY, unplanted, via zh-p4 (mechanical-origin:
digit 1->2): both rectify attempts were LINT-CLEAN (digit restored) but
judge-flagged on the unsatisfiable mingzi nit above -> UNRESOLVED. The two
candidate keeps:
- keep-ORIGINAL: ships "Dependent **2**'s name" -- the provably wrong digit;
- keep-LINT-CLEAN-RECTIFY: ships "Dependent 1's name" -- digit correct;
  the residual judge complaint is the diagnosed perfectionist nit (the
  rectify output equals the seeded gold).

**Decision (on this evidence): for MECHANICAL-origin flags that end
UNRESOLVED, keep the latest LINT-CLEAN rectify attempt when one exists;
otherwise keep the original. Judge-origin flags keep the ORIGINAL (unchanged
-- the original is merely suspected, and the twice-rejected rectify may be
appeasement drift).** Both cases still flag UNRESOLVED for human review.
Definition for V3 (fresh-eyes precision note): "origin" = how the item FIRST
entered the flag set (its initial lint result), tracked for the item's whole
multi-attempt trace -- the probe's attempt-2 `problem` field carries the
judge's reason, but that does not reclassify the item's origin.

## Chunk A/B (measure d)

Verdicts were IDENTICAL between the 25- and 50-item arms for every plant and
every gold string in both languages. At this corpus size (52 items/language)
chunking does not change judgment quality. **Pin chunk size 50 for V3** (half
the judge calls); revisit only if V5's full-kit batches (up to ~300 uniques
per language on i-90) surface arm divergence -- V5 can A/B once at full scale
if flag rates look odd.

## ur observational arm (the tail-language stress)

- Forward translation (translate_items-shaped prompt + glossary): 14 strings,
  **0 mechanical lint failures** -- ASCII digits held despite Urdu's
  native-numeral convention (the A.2(d) policy line worked), script check
  clean, DNT tokens intact.
- The judge caught a REAL forward-translation error on "Single" (filing
  status), and the loop CONVERGED in two attempts (attempt 1 "wahid"
  rejected; attempt 2 "ghair shadi shuda" accepted clean). The instability
  here is a CROSS-PASS VERDICT INVERSION, precisely stated (fresh-eyes
  correction on this bead's first draft, which mislabeled it a flip-flop):
  the initial judge pass argued "ghair shadi shuda" was the wrong sense and
  preferred "wahid"; the rectify-loop judge then demanded the opposite and
  accepted "ghair shadi shuda". Same-judge-different-pass disagreement on
  the same pair -- weaker evidence than zh-g11's true rejected-both
  oscillation (the flip-flop detector rests on zh-g11 alone), but real
  tail-language verdict noise, supporting the plan's low-resource-first
  review ordering for V5.

## What V3 inherits (the actionable list)

1. Judge prompt: NOT-drift bullet hardening on back-translation anchoring
   (zh-g07) + never-flag-your-own-proposal / conventional-rendering clauses
   (zh-g11, ur).
2. Loop: flip-flop detector (rectify output == previously rejected value ->
   UNRESOLVED early).
3. Keep rule: mechanical-origin unresolved -> latest lint-clean rectify;
   judge-origin unresolved -> original. Both UNRESOLVED-flagged.
4. Chunk size 50.
5. Flagged-string re-verification one tier up on the back-translate leg is
   OPTIONAL (plan's named fix) -- not triggered at es FP=0; hold until V5
   data says otherwise.

Verdict recorded per the epic rubric: criterion 1's probe evidence stands --
discrimination works in both directions on the verifiable slice; the FP class
found is diagnosed, mitigable, and concentrated where gold confidence was
lowest.
