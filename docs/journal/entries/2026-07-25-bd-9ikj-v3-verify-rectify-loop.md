---
date: 2026-07-25
bead: polyglot-pdf-9ikj
title: "V3: the verify/rectify loop in the bake -- default-ON, V1-decided rules baked in"
sprint: 14
tags: [testing, conventions]
---

## Trigger

V3 of the translation-quality-gate epic (`polyglot-pdf-sekc`), unblocked by
the V1 probe's GATE=PROCEED (bd i36i, PR #469). Builds the production
verify/rectify loop the probe validated, with every V1-decided rule
(keep rules, rejection-recurrence flip-flop detector, chunk 50, hardened
judge prompt) baked in.

**Split at claim time (rubric change logged on the bead):** the bead as
filed spanned two PRs' worth -- the loop AND the forward-path migration
onto `translate_items`. Per the bead/PR contract the forward-path half was
split to a new bead (`polyglot-pdf-alry`, wired epic-child + blocked by
this one; V5 now also blocked by it). Exit criterion 3's
`build_translation_overrides` clause moved with it.

## What shipped

- **`ITextAI` verify trio** (`backend/ports/text_ai_port.py` +
  `backend/adapters/text_ai_gemini.py`): `back_translate` (LITE-tier
  independence leg), `judge_translations` (chunked bilingual verdicts;
  the V1-hardened precision rules are a byte-stable adapter constant --
  back-translation-is-supporting-evidence-only, never-flag-your-own-
  proposal, conventional-rendering clauses, register conformance),
  `rectify_translations`. All temperature 0.0, JSON-mime, shape-validated,
  `None`-fail-open, counts-only logging, non-abstract port defaults.
- **`backend/services/translation_verify.py`**: the loop orchestration --
  lint -> back-translate -> judge (chunk 50) -> bounded rectify (2) with
  full-loop re-entry (re-lint + fresh back-translate + provenance-stripped
  re-judge). Keep rules: replace only on verified-clean; unresolved
  mechanical-origin keeps the latest lint-clean rectify, judge-origin
  keeps the original; both flag UNRESOLVED. Flip-flop detector fires on
  REJECTION RECURRENCE only. Fail-open: any model-leg failure returns the
  originals byte-untouched (available=false) while the deterministic lint
  flags still stand.
- **Bake wiring** (`backend/services/option_translation.py`): the gate
  runs on FRESHLY TRANSLATED strings only (idempotent re-runs stay
  call-free), corrections land before fan-out, flags resolve to kit paths
  post-fan-out (one WARNING `LintFinding` per location,
  `field_id_of`-parsable) into `report["flags"]` + per-language
  `verify` counts. All three call sites get this with ZERO per-site
  plumbing (they already consume the report). With the gate off the
  report is byte-identical to its pre-gate shape.
- **Config**: `TRANSLATION_VERIFY_ENABLED` default-ON (authoring-time
  spend only; documented against the wire-dark pattern) +
  `TRANSLATION_VERIFY_BT_MODEL` (flash-lite).
- **Tests**: 17 new pins in `test_translation_verify.py` (loop bound,
  both keep rules, provenance-stripped re-judge, flip-flop firing AND the
  ur-convergence non-firing case, mechanical-skips-judge, every fail-open
  leg leaving the kit byte-identical, chunk 50, bake integration incl.
  default-ON settings read and multi-location fan-out of corrected
  values); 7 new adapter tests; the legacy bake pins run gate-off via one
  autouse fixture (documented in-file).

## Lessons

- **Split early, on the bead/PR contract, not late on reviewer pushback.**
  The forward-path migration was separable by interface (the loop verifies
  (source, translation) pairs regardless of forward method); splitting at
  claim time kept this PR reviewable.
- **A probe's decided rules translate almost verbatim into production
  pins** -- the V1 findings doc's "What V3 inherits" list became the test
  list for this bead nearly 1:1. Writing probe findings as actionable
  inheritances pays off.

## Doc freshness

- `docs/standards/validation-delegation.md` BUMPED: the verify trio +
  the bake gate recorded in the contract-5 section.
- `docs/components/config-deployment.md` NOT bumped: the two new env vars
  are authoring-time only; V4 (the surfacing bead) touches the
  CLI/editor surfaces that doc tracks and can carry the line -- noted
  here so the closeout doc-freshness check has the record.

## Files touched

- `backend/config.py` -- TRANSLATION_VERIFY_ENABLED +
  TRANSLATION_VERIFY_BT_MODEL.
- `backend/ports/text_ai_port.py` -- back_translate / judge_translations /
  rectify_translations defaults.
- `backend/adapters/text_ai_gemini.py` -- the three methods + the
  byte-stable judge rules constant.
- `backend/services/translation_verify.py` -- NEW: the loop.
- `backend/services/option_translation.py` -- verify gate wiring + flag
  path resolution + lite-adapter builder.
- `backend/tests/unit/test_translation_verify.py` -- NEW (17 tests).
- `backend/tests/unit/test_text_ai_gemini.py` -- +7 verify-method tests.
- `backend/tests/unit/test_option_translation_bake.py` -- gate-off
  autouse fixture.
- `docs/standards/validation-delegation.md` -- contract bump.
