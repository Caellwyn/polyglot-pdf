---
date: 2026-07-06
bead: polyglot-pdf-w0eq
title: "P6.1c redirected: fix the extractor's silent widget-coverage loss"
tags: [extraction, schema-lint, testing, authoring]
---

## Trigger

P6.1c (`w0eq`) began as "re-extract w7/w7-2/f1040 under the v2 pipeline + commit
the outputs." The first re-extraction of w7-2 came out MISSING one AcroForm
widget, and re-running just moved the gap to a different widget. When surfaced,
the maintainer REDIRECTED the bead (2026-07-06): "Don't worry about getting
accurate copies of w7-2 and f1040. Worry about fixing the extraction problem."
-- and asked the key diagnostic question: w7 and w7-2 are the same form, so why
would one extract fully and the other not?

## Diagnosis

The extractor had NO widget-coverage guarantee. The strong-LLM pass enumerates
the form's fields from the dump + PDF, but does so STOCHASTICALLY -- on any given
sample it may omit ~1 field entirely.

- **w7 and w7-2 are byte-identical PDFs** (same md5, same 69-widget set). The
  only reason one "worked" was sampling luck: across runs the drop lands on a
  different widget (`f1_16[0]`, `f1_25[0]`, ...), and a w7 run drops one too. Not
  form-specific -- pure model sampling variance.
- **The safety net missed it.** `schema_lint`'s dump-claim rule flagged only
  OVER-claim (one widget claimed by >1 field) -- never UNDER-claim (a dump widget
  NO field maps to). So a dropped field passed lint 0/0, silently.

Found alongside: the LLM stochastically mistypes a consolidated run of DISTINCT
checkbox widgets as `radio` (single-select) instead of `checkbox_group` -- e.g.
the W-7 "reason for submitting" boxes `c1_2[0]..c1_9[0]` (8 separate checkbox
widgets, logical_type=checkbox in the dump; a radio is one field whose kids share
a name -- these are not that).

## Fixes (all deterministic, all unit-tested; no API dependency)

1. **Lint under-claim WARNING** (`schema_lint._check_dump_claims` +
   `_dump_logical_type`): a fillable dump widget claimed by zero fields is now a
   `dump-widget-unclaimed` WARNING. Fillable only -- decorative buttons
   (logical_type=button) are excluded. WARNING, not ERROR, so it never breaks the
   store-with-issues exit code; a clean extraction (post-backfill) emits none.
2. **Deterministic coverage backfill** (`extract_form._backfill_unclaimed_widgets`,
   pipeline step 3e): after the LLM pass, any unclaimed fillable dump widget is
   appended as a basic field -- typed from its dump `logical_type`, positioned
   from the dump rect, filed into the section covering its page (else the last
   section); a recovered checkbox/radio gets a groups-of-one self-option so it is
   fillable + lint-accepted. Coverage is now deterministic regardless of LLM
   omissions. The recovered field is functional-but-plain (placeholder label); a
   human editor refines it -- the point is that NO widget silently vanishes.
3. **Group-checkbox retype** (`extract_form._correct_group_checkbox_type`, step
   3d): a consolidated 2+-option field whose EVERY member widget is
   logical_type=checkbox in the dump is retyped `radio` -> `checkbox_group`. This
   satisfies the original P2.2 assertion (the W-7 reason group: 8 options,
   `c1_2[0]..c1_9[0]`, distinct slugs) DETERMINISTICALLY, not by sampling luck. A
   genuine radio (logical_type=radio) or any unresolved member leaves the field
   untouched (conservative).

## Verification

- The under-claim computation exactly identifies the dropped widgets on the two
  divergent w7-2 samples (`f1_16[0]`, `f1_25[0]`); the backfill closes each gap to
  0-unclaimed, valid + lint-clean; the retype turns the mistyped W-7 reason group
  into a passing P2.2 checkbox_group (all 6 consolidated groups confirmed all-
  checkbox against the dump, which has zero radios).
- Tests: `backend/tests/test_schema_lint.py` (+3 under-claim),
  `tests/test_extract_form_backfill.py` (+4 retype, +5 backfill).
- Full backend + tools suite: 1684 passed, 3 skipped, 0 failures.

## Scope note

The redirect deprioritized committing accurate re-extractions of w7-2/f1040 (they
stay on their hand-verified shipped v1 schemas); this bead now delivers the
extractor FIX. The original P2.2 structural assertion is met deterministically by
fix 3. Actually re-extracting + committing the three kits, if still wanted, is a
clean follow-up now that the pipeline guarantees coverage.
