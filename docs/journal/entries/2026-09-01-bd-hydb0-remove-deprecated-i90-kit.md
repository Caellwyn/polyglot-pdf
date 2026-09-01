---
date: 2026-09-01
bead: polyglot-pdf-hydb0
title: "chore(form-kits): remove deprecated i-90 kit files left uncommitted in root repo"
tags: [testing, refactor, harness]
---

## Trigger

The maintainer asked for help pulling `origin/dev` into the root repo checkout,
which was blocked by local uncommitted changes. Among them: the entire
`form-kits/i-90/` directory (7 files) was already deleted from disk but never
committed. Confirmed with the maintainer: this version of the I-90 kit is
deprecated in favor of a new one (`form-kits/i-90_v2`, deliberately
gitignored/untracked, pulled locally via `scripts/pull-form-kits.sh`). This
bead commits that deletion properly, through the normal branch/PR flow rather
than pushing straight to `dev`.

## What shipped

- Removed `form-kits/i-90/` (`form.pdf`, `i-90-annotated.pdf`,
  `i-90_schema_backup.json`, `metadata.json`, `migration_report.json`,
  `schema.json`, `schema_archived.json`).
- The deletion broke test collection/execution across **both** `pytest.ini`
  testpaths (`backend/tests/` and the top-level `tests/`) -- enumerated the
  full set (CLAUDE.md scar #8) rather than fixing one failure at a time:
  - Two backend test files crashed at COLLECTION (not just test-time): a
    module-level import chain (`g1b_answer_key.py` -> `g1b_corpus.py` ->
    `probe_g1b_model_size_bakeoff.py` -> `probe_g1c_tuning.py`) reads the i-90
    schema at import time. `pytest.mark.skipif` cannot save a crash that
    happens in the import statement itself -- fixed with a pre-import
    `pytest.skip(..., allow_module_level=True)` guard instead.
  - `g1b_answer_key.ANSWER_KEY` is a 645-line hand-authored corpus keyed to
    the OLD i-90's 132 field ids (`p1_line1_aliennumber`, ...). Checked
    `i-90_v2`'s actual schema: 94 fields, different ids (`a_number`, ...) --
    genuinely incompatible, not a path repoint. Left skipped, not repointed;
    re-authoring that corpus is real work, tracked as a documented follow-up
    rather than guessed at here.
  - Several more backend tests hardcoded `["i-90", "w7", "f1040"]`-shaped
    kit-enumeration lists/assertions (`test_form_models_v2.py`,
    `test_translation_lint.py`) -- dropped i-90 from the expected set.
  - Several more pinned behavior against the REAL i-90 schema on disk
    (`test_date_format_resolution.py`, `test_dti_si_voice_rules.py`,
    `test_field_validation_responses.py`) -- added skip-if-missing guards
    matching the pre-existing pattern in `test_ai_context.py`, splitting
    loop-based tests so a still-present kit's (w7/f1040) half of the pin
    keeps running.
  - The outer cross-surface review (2 rounds) then caught that the FIRST
    fix pass only covered `backend/tests/` -- the second pytest testpath,
    `tests/`, was never re-run and had 34 more failures:
    `scripts/authoring/eval_extraction.py`'s `_FORMS` benchmark manifest
    hardcoded an i-90 entry (fixed: removed from the manifest, its one
    genuinely i-90-specific pin now reads the schema directly with its own
    guard); `scripts/spikes/full_form_script.py`'s `load_schema()` is read
    unconditionally by ~31 tests in `tests/test_stress_harness_units.py`,
    reached via 2 shared client-builder fixtures and ~14 direct call sites
    -- guarded each rather than skipping the whole module, since ~13 of 42
    tests in that file are genuinely schema-agnostic and would have gone
    silently vacuous under a blanket skip.
  - The same review also caught a PRE-EXISTING bug it was not asked to look
    for: `test_pdf_structure_verify.py`, `test_resume_form_route.py`, and
    `test_extract_form_sections.py` each gated an entire module on
    `not A.exists() or not B.exists()` -- multiple kits OR-ed into one
    switch. Once i-90 disappeared this silently disabled ~70 tests that only
    ever touched w7/f1040, including the bd dft1 hostile-upload/
    prompt-injection SECURITY guards -- the worst failure mode here, since a
    security suite went vacuous with a green, benign-looking skip reason.
    Filed as bd polyglot-pdf-cj8mg by the reviewer; fixed directly in this
    PR (small once traced) rather than left as a follow-up, and the bead
    closed. Re-gated each file to the kit every test actually needs, with
    per-test/per-parametrization guards for the kit-specific cases.
  - A third review round caught 3 tier-2 doc claims made stale by the
    deletion (`docs/technical_guide.md`, `docs/components/pdf-view.md` x2)
    stating i-90 as a currently-shipped/deployed kit -- corrected to the
    real current kit set, with `pdf-view.md`'s own "Last updated" stamp
    bumped.
- `tests/e2e/voice-harness/`'s SKILL.md/RUNBOOK.md UI-navigation step AND
  `harness.js`'s default field-id expectations (`p1_line1_aliennumber`,
  `p1_line2_acctidentifier`) both target the deleted kit -- this is a real
  test-design decision (picking a field that plays the same structural role
  on a different kit), not a doc fix, so it was NOT guessed at here. Flagged
  with a clear warning block at the top of SKILL.md and filed as
  bd polyglot-pdf-tcemw.
- Also deferred, filed by the reviewer as a docs-nit (not blocking): stale
  i-90 examples in `docs/components/auth.md`, `scripts/deploy-form-kit.sh`,
  `scripts/bootstrap_firm.py`, and two historical measurement citations --
  bd polyglot-pdf-umb5o.

## Lessons

- **A deletion's blast radius can hide behind a SECOND test-collection root.**
  `pytest.ini` declares two testpaths (`backend/tests/` and the top-level
  `tests/`); fixing only the first looked complete (fresh-eyes cleared it)
  but left 34 failures in the second undetected until the outer
  cross-surface review explicitly ran the combined suite. Generalizes: when
  a repo has more than one test root, "the suite is green" claims must name
  which root(s) were actually run.
- **A module-level `pytest.mark.skipif` cannot save a crash inside the
  IMPORT statement itself** -- pytest evaluates the marker only after the
  module successfully imports. When the crash is in module-level code
  (a corpus fingerprint computed at import time, a shared fixture called at
  class/module scope), the skip check must run and `pytest.skip(...,
  allow_module_level=True)` BEFORE the offending import, not as a
  `pytestmark`.
- **Coupled multi-resource skip gates (`not A.exists() or not B.exists()`)
  are a standing trap independent of any single deletion.** They read as
  "skip if the fixtures aren't ready" but actually mean "skip everything in
  this file if ANY ONE of several unrelated resources goes missing" -- and
  the failure mode is silent and green, not loud. This is the worst version
  of it when the disabled tests are security guards. Worth a grep sweep
  elsewhere in the repo if a similar deletion happens again (this pass found
  and fixed all 3 instances that existed at the time).

## Doc freshness

- `docs/technical_guide.md`: fixed one factually-wrong sentence (kit count
  for `link_cost_ceiling_usd`); left the file's overall stale flag as-is
  (mechanically confirmed to be driven by unrelated files -- routes/,
  deploy scripts -- that predate this branch).
- `docs/components/pdf-view.md`: corrected 3 current-state claims naming
  i-90 as a shipped/deployed kit; bumped its "Last updated" stamp.
  `check_doc_freshness.py` now reports it OK.
- `.claude/skills/voice-harness/SKILL.md`: added a warning block (not a
  silent fix) since the real repoint is a test-design decision, not prose.

## Files touched

- `form-kits/i-90/*` (7 files) -- deleted.
- `backend/tests/unit/test_g1b_answer_key_coherence.py` -- pre-import skip
  guard.
- `backend/tests/unit/test_g1c_parse_conflicts.py` -- pre-import skip guard.
- `backend/tests/test_form_models_v2.py` -- dropped i-90 from parametrize
  lists + docstring.
- `backend/tests/unit/test_translation_lint.py` -- dropped i-90 from
  expected-kit assertions.
- `backend/tests/unit/test_date_format_resolution.py` -- skip-if-missing
  guard on the one i-90-specific test.
- `backend/tests/unit/test_dti_si_voice_rules.py` -- skip guards on 4
  i-90-dependent tests/cases, splitting loops so the surviving kit's half
  still runs.
- `backend/tests/unit/test_field_validation_responses.py` -- skip guards on
  the i-90-schema-reading tests/helper.
- `backend/tests/test_pdf_structure_verify.py` -- re-gated module skip to
  w7-only; scoped i-90 guard on the one test that needs it.
- `backend/tests/test_resume_form_route.py` -- re-gated module skip to
  w7-only; scoped guards on the i-90-specific tests/inputs.
- `scripts/authoring/eval_extraction.py` -- dropped i-90 from `_FORMS`.
- `tests/test_eval_extraction.py` -- updated row-count/name-list
  expectations; the i-90 pin now reads the schema directly with its own
  guard.
- `tests/test_stress_harness_units.py` -- `needs_i90` marker + shared
  `_skip_if_no_i90()` helper, applied across ~31 tests/2 shared fixtures.
- `tests/test_extract_form_sections.py` -- re-gated module skip to
  w7-only; scoped guards on the i-90/f1040-specific tests.
- `docs/technical_guide.md` -- corrected a stale kit-count claim.
- `docs/components/pdf-view.md` -- corrected 3 stale "shipped kit" claims;
  bumped the Last-updated stamp.
- `.claude/skills/voice-harness/SKILL.md` -- added a "currently broken"
  warning block pointing at bd polyglot-pdf-tcemw.
