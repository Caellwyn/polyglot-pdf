---
date: 2026-07-27
bead: polyglot-pdf-z3rs
title: "fix(translation): coverage gate counts value-quality, not key-presence (empty string no longer passes as covered)"
tags: [extractor, testing]
---

## Trigger

Surfaced by the Opus outer review of bd polyglot-pdf-783r (the Mark-complete
drift re-translation sweep). `translation_lint.coverage_findings` counted a
language as COVERED for an item whenever the language KEY was present in the
translations map -- it never inspected the value. That disagreed with
`option_translation._kit_translation`, which only accepts a NON-EMPTY string.
Pre-existing behavior (was a WARNING), but 783r wired coverage into a HARD
completion gate (`translation_coverage_summary` -> 409 refusal), so the
asymmetry became load-bearing: a hand-authored empty translation
(`{"spanish": ""}`) that the bake's fresh-value filter never fills would pass the
gate as "covered", shipping a form that speaks the ENGLISH label aloud in that
session.

## What shipped

- `backend/services/translation_lint.py::coverage_findings` -- the `resolved`
  covered-language set is now built only from keys whose value
  `isinstance(v, str) and v.strip()`, exact parity with
  `option_translation._kit_translation`. Empty / whitespace / non-string values
  no longer count. One-line-scope change; the only key-presence counter in the
  file (grep-confirmed).
- Because the whole-kit gate (`translation_coverage_summary`, bd 783r) is built
  on `coverage_findings(..., attempted=True)`, the fix flips it automatically:
  a present-but-empty translation now makes `summary.complete` False and the
  language appears in `incomplete_languages`, so Mark complete refuses until it
  is filled.

## Doc freshness

No tier-2 doc tracks `translation_lint.py` (its record is the journal). The
pre-existing STALE standards docs flagged by `check_doc_freshness.py` track
files this branch did not touch and were already stale -- left as-is (warn-only).

## Testing

- NEW `test_coverage_treats_a_present_but_empty_value_as_not_covered`
  (`backend/tests/unit/test_translation_lint.py`): an empty / whitespace / None /
  non-string french value drops french from covered (3/4, one coverage finding),
  for each bad value; and it flips the whole-kit `translation_coverage_summary`
  to incomplete with french in `incomplete_languages` (the 783r gate).
- Verified an identity-kept NON-empty value (`{"spanish": "Alabama"}`) still
  counts as covered -- the fix excludes only genuine non-values, not the
  sanctioned proper-noun identity translations.
- translation-lint + bake + editor-routes + option_translation suites green
  (211 across the four files).
