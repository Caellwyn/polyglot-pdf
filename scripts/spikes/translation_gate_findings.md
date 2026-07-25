# Translation-gate discrimination probe -- findings (V1, bd polyglot-pdf-i36i)

**Date:** 2026-07-24. **SDK:** google-genai 2.8+ (post-cutover). **Models:**
judge/rectify/ur-forward `gemini-2.5-pro` (thinking bounded 512), back-translate
`gemini-2.5-flash-lite`. Vertex (ADC). **Runner:**
`scripts/spikes/translation_gate_probe.py`; corpus
`scripts/spikes/data/translation-gate/gold.json`; raw runs
`scripts/spikes/data/translation_gate_20260724T205304Z.{csv,meta.json}`
(run 1) + `..._20260724T212414Z.{csv,meta.json}` (run 2 -- the
per-language-accounting run, which doubles as a verdict-stability
replicate; see the Run 2 section).

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
- **Cost, measured per language (measure e; run 2, the accounting run):
  es $0.0698, zh $0.0882, ur $0.0523 -- total $0.2102** (19 pro + 8 lite
  calls; run 1, whose accumulator was per-model only, totaled $0.2145).
  ur's cost is dominated by the extra forward-translation pro call +
  thinking -- the per-language unit figures V5's 4-kit x 17-language
  projection needs. Pre-run estimate: ~$0.45 per run (this bead's own
  Gate-2 derivation, recorded in the probe docstring -- NOT a plan figure).
  **Spend disclosure vs the plan:** the plan's pre-authorization line
  reads "~$0.25"; the two-run total is **$0.4247, ~1.7x that figure**
  (run 2 was required to meet exit criterion 3's per-language measurement
  after run 1's accumulator proved per-model only). Each run individually
  sits under both Gate-2 ask anchors (a few dollars; ~50 live calls --
  27 calls/run), and the overage is surfaced to the maintainer in the PR
  merge report rather than silently absorbed.

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
   rendering satisfies it. Mitigation (V3): the loop detects a FLIP-FLOP,
   defined precisely as REJECTION RECURRENCE -- **the judge flags a value
   that already appears as a flagged value earlier in this item's trace ->
   stop, UNRESOLVED** (zh-g11's attempt-2 re-flagged the originally-flagged
   mingzi: fires correctly). NOT value recurrence alone: the ur trace is
   the counterexample the Opus review surfaced -- attempt 2 re-proposed the
   originally-rejected rendering and the judge ACCEPTED it (converged), so
   a value-identity detector would have converted a clean accept into a
   false UNRESOLVED. The precision block also gains "never flag a rendering
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
every gold string in both languages -- the VALIDATED set shows zero
divergence. **Full disclosure (Opus-review catch on this doc's first
draft): 5 of the ~54 unvalidated FILLER strings flipped verdict between
arms** (es kit012/kit015, zh kit024/kit028/kit029). Filler has no answer
key, so those divergences cannot be scored right-or-wrong -- they show
chunking perturbs borderline judgments on exactly the kind of ambiguous
string the filler contains, while leaving clear-cut cases (all 44 validated
items) stable. **Pin chunk size 50 for V3** (half the judge calls; the
validated evidence supports it and the perturbed cases are the borderline
class the judge is noisy on regardless of arm); V5 re-A/Bs once at full
kit scale (up to ~300 uniques per language) if flag rates look odd --
that run, with more data, is the right place to revisit.

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

## Run 2 (the accounting replicate)

Run 1's accumulator was per-model only; criterion 3 requires MEASURED
per-language cost (Opus-review catch), so the probe re-ran with a
per-(language, model) split -- and the second run is a free
verdict-stability sample:

- **Discrimination REPLICATED: 14/14 plants caught again, at the same
  layers, in both arms; es gold 15/15 clean again.**
- **zh-g07 (back-translation anchoring) REPRODUCED in both arms** --
  strengthening that diagnosis and its V3 prompt mitigation.
- **zh-g11 did NOT recur** (zh gold FPs 2 -> 1): the
  unsatisfiable-criterion case is borderline run-to-run judge noise, which
  is consistent with its diagnosis -- and exactly why the flip-flop
  detector converts that thrash into an honest UNRESOLVED rather than
  trusting any single verdict.
- **ur-o08 ("Single") flagged again** -- the tail-language forward
  weakness is stable, not a one-off.

## What V3 inherits (the actionable list)

1. Judge prompt: NOT-drift bullet hardening on back-translation anchoring
   (zh-g07) + never-flag-your-own-proposal / conventional-rendering clauses
   (zh-g11, ur).
2. Loop: flip-flop detector keyed on REJECTION RECURRENCE (the judge flags
   a value already flagged earlier in the item's trace -> UNRESOLVED
   early); never on value identity alone (the ur convergence
   counterexample).
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

## Run 3 (2026-07-25) -- INVALID as a reframe check; kept as an old-prompt replicate

Intended as the g0ka judge-reframe regression check, but the probe carried
its OWN stale copy of the judge rules, so this run silently exercised the
OLD prompt (caught by fresh-eyes on the g0ka closeout). Its numbers stand
only as a third old-prompt replicate: 14/14 plants, es gold 15/15 clean,
zh gold FP 1. Cost $0.21. The probe now IMPORTS the production adapter's
`_JUDGE_RULES` (aliasing pinned by unit test), so this divergence class is
closed.

## Run 4 (2026-07-25, the REAL g0ka reframe check)

Re-run with the probe reading the production LANGUAGE-LOCK prompt (bd
polyglot-pdf-g0ka: voice-model consumer, intelligible-and-in-language bar,
wrong/mixed language leads DRIFT, imperfect-but-intelligible word choice
explicitly NOT drift):

- **Discrimination PRESERVED under the reframe: 14/14 plants caught (7/7
  es + 7/7 zh), same layers.** es gold 15/15 clean; zh gold FP 2 at
  chunk 25 / 1 at chunk 50 (within the 1-2 old-prompt range). Cost $0.20.
- The Pub-850 gold set is a FLOOR-FP corpus (0-2 FPs under either prompt),
  so it cannot show the over-flag reduction the reframe targets. That is
  measured directly by the V5 QUIBBLE SET
  (`translation_judge_quibble_ab.py`): 14 V5 judge-origin unresolved keeps
  that the cross-family Claude audit certified acceptable -- old prompt
  14/14 flagged, reframed prompt **9/14 and 8/14 across two runs
  (-36% to -43%; committed artifact
  `scripts/spikes/data/quibble_ab_results.json`)**, and the residual flags
  are substantive (omitted 'first name' concepts in uk/ru/ko/it renderings,
  Suite->Office narrowing, the IRSN DNT case bd c6td retires) rather than
  stylistic. Spend ~$0.02.
