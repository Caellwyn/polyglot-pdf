---
date: 2026-07-25
bead: polyglot-pdf-za4p
title: "Lint/verify hardening bundle: wrong-language markers, coverage gaps, pin morphology, counts semantics"
tags: [conventions, testing]
---

## Trigger

Overnight follow-through on the maintainer's language-lock reframing
(2026-07-25, memory `translations-are-drift-anchors-not-display`): the
translated strings exist to keep the voice model locked to the session
language, so the pipeline's checks should weight language-lock failures over
fidelity quibbles. This PR bundles four whole beads on that seam --
`polyglot-pdf-za4p` (wrong-language lint) + `polyglot-pdf-x41u` (coverage
gaps) from the accepted recommendations, plus two known bugs in the same
files: `polyglot-pdf-m6w5` (pin-check morphology false positives) and
`polyglot-pdf-kpar` (verify_counts "undercount").

## What shipped

- **Wrong-language markers (za4p,** `translation_lint.py`**):** the script
  check cannot see a same-script neighbor-language string (a Portuguese
  string in a spanish slot passes the latin test) -- exactly the live
  failure class (a Spanish session slipping into Portuguese) that started
  the epic. New deterministic check `_check_wrong_language` flags
  characters that are standard orthography in a neighbor language but
  foreign to the expected one (`_FOREIGN_MARKERS`): pt a/o-tilde vs es,
  ru yery/e/hard-sign/yo vs uk (and inverse), Perso-Arabic pe/che/zhe/gaf
  + Urdu retroflex vs ar, sharp-s vs non-German Latin, etc.
  Precision-first: enye is NOT a marker for tagalog (Spanish loans are
  standard), urdu gets no marker set (its alphabet embeds both neighbors),
  identity-kept strings are skipped. Zero findings on all 4 committed kits.
- **Coverage gaps (x41u):** new rule `translation-coverage` -- one WARNING
  per language with incomplete coverage in an otherwise-translated kit
  (0-covered = the failed-batch case), because a missing translation falls
  back to the ENGLISH label mid-session, an English injection at the exact
  point the lock is held. Emitted by the kit-level sweep (full supported
  set) AND the bake report (scoped to the languages that bake addressed,
  so a deliberate `--languages spanish` run is not flagged for the other
  16). Bake-report findings persist to `_bakeoff` provenance and re-emit
  through schema lint into the editor ValidationPanel (rule added to
  `TRANSLATION_FLAG_RULES` + a friendly label).
- **Pin morphology (m6w5):** `_check_pins` now anchors the ENGLISH source
  term at ASCII-letter word boundaries -- "Refundable credit" no longer
  demands the pinned noun "reembolso" inside the correct adjectival
  "reembolsable". Measured effect: f1040's sweep findings drop 127 -> 123
  (4 real false alarms removed); no finding added anywhere.
- **Counts semantics (kpar):** root cause of the V5 artifact's apparent
  i-90 undercount: `verify_counts` tallies verified SOURCE STRINGS while
  the `flags` list carries one finding per KIT LOCATION -- fan-out
  duplicates a source at every field repeating it (i-90 repeats state
  names/colors; w7 repeats nothing flagged, hence its zero gap). Not a
  code bug; documented at every consumer surface (VerifyResult docstring,
  bake docstring, a `verify_counts_note` field in the CLI `--flags-out`
  artifact) and pinned by a fan-out test (1 verified source on 2 fields ->
  counts 1, findings 2). The bead's exit-criteria equality expectation was
  reconciled to the true invariant: equality after (rule, source) dedup.
- Tests: 3 pin-morphology pins, 7 wrong-language pins (flag + tolerate +
  identity-skip), 5 coverage pins (unit + kit-level + bake-level failed-
  language + fully-covered silence), the kpar fan-out pin; two existing
  tests updated where the coverage rule now legitimately fires on their
  partial synthetic kits. Full backend+scripts suites green (2173);
  schema-editor suite + tsc green; kit sweep re-run: i-90/w7 still 0.
- Fresh-eyes triage: (filled at closeout -- see PR.)

## Lessons

- **A "bug" between two derived numbers is often two different questions.**
  kpar's 26-entry "gap" dissolved once each number's denominator was named
  (strings verified vs locations to review). Before reconciling two
  metrics, state what each counts.
- Marker-based language identification is the cheap, high-precision slice
  of langid: full detection needs a model, but a dozen exclusive
  code points per language pair catches the catastrophic class (wrong
  language shipped as an anchor) with zero false positives on ~6,600 real
  baked strings.

## Doc freshness

- No tier-1/tier-2 doc tracks these modules' internals; the module
  docstrings carry the new check tolerances. Reviewed and left as-is.

## Files touched

- `backend/services/translation_lint.py` -- markers + wrong-language check, coverage_findings, pin word-boundary, docstring tolerances
- `backend/services/option_translation.py` -- coverage findings in the bake report + counts-vs-flags comment
- `backend/services/translation_verify.py` -- VerifyResult counts semantics docstring
- `backend/services/schema_lint.py` -- translation-coverage in TRANSLATION_FLAG_RULES
- `scripts/authoring/translate_option_labels.py` -- verify_counts_note in the artifact
- `schema-editor/src/components/ValidationPanel.tsx` -- coverage RULE_LABEL
- tests: `backend/tests/unit/test_translation_lint.py`, `backend/tests/unit/test_option_translation_bake.py`
