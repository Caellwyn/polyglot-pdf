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

## Pre-PR fresh-eyes fixes (folded in)

The pre-PR fresh-eyes pass caught a real correctness bug and three lesser issues,
all fixed before the PR opened:

1. **Barcode false-positive (blocking).** On the real shipped i-90 kit the
   under-claim rule flagged 7 hidden `PDF417BarCode1[0]` widgets, and the backfill
   would have injected 7 bogus `PDF417BarCode1_*` text fields. `logical_type` +
   `read_only` can't discriminate: a barcode is a read-only MULTILINE text widget,
   and this project deliberately fills 20 real read-only-text fields (and real
   read-only checkboxes) via `flip_readonly_bit`. Fixed with a shared
   `schema_lint.is_fillable_widget(dump, name)` -- the single source of truth for
   BOTH the lint rule and the backfill -- that excludes buttons AND machine
   barcodes (name/TU markers `barcode` / `pdf417` / `qrcode`). Verified against the
   real i-90 PDF: the 7 barcodes are now silent, only the 4 genuinely-missing
   `P2_checkbox3[1..4]` checkboxes remain flagged. Regression-pinned by a NEW
   dump-aware test (the existing shipped-kits test passed no dump, so the rule
   never ran on a real kit in CI).
2. **Empty-sections orphan.** If the LLM emits no sections, `_section_for_page`
   returned None and the recovered field got `section_id=""` -- valid + lint-clean
   but unreachable via section navigation (re-hiding it). Fixed: a
   `recovered_fields` bucket section is created so no recovered field is orphaned.
3. **Duplicated claim logic.** The backfill reimplemented lint's suffix-aware
   claim match; now it imports `_match_dump_names` (+ `is_fillable_widget`) from
   schema_lint so the two can never desync.
4. **Empty-leaf label.** A widget name ending in `.` yielded a blank
   name/spoken_name; now falls back to the minted id.

Also caught by the round-trip re-validation while fixing #1: a recovered checkbox
was emitted `type=checkbox` WITH a self-option -- a v1 idiom that v2 REJECTS (a v2
checkbox is a boolean; options are forbidden). Fixed: a backfilled standalone
checkbox carries its widget in `pdf_field_name` with NO options; only a radio
keeps a self-option.

## Pre-PR fresh-eyes round 2 (folded in)

A second fresh-eyes pass on the round-1 fixes caught one more blocking gap + two
nits, all fixed:

1. **Backfilled radio failed v2 validation (blocking).** A lone recovered radio
   widget got 1 self-option, but v2 requires a radio to have >=2 options
   (`FormSchema.model_validate` raised "radio requires at least 2 options"). Same
   class for combo/list -> select. Fixed: `_LOGICAL_TO_FIELD_TYPE` now maps radio
   -> checkbox (a lone recovered radio widget is a boolean toggle) and combo/list
   -> text; the backfill mints ONLY zero-option-valid types (checkbox/text), never
   an options-bearing type. New test `test_backfilled_fields_always_validate_as_v2`
   round-trips a mixed dump through `FormSchema.model_validate` (the test that
   would have caught this).
2. **Bucket page_numbers didn't grow** across orphans on different pages -- fixed
   to accumulate (guarded by a `had_original_sections` flag so a real section set
   still routes to `sections[-1]`).
3. **Backfill's backend import** lacked the `sys.path.insert(0, _REPO)` guard its
   three sibling imports in the same file have -- added, so it no longer relies on
   an unrelated module's transitive side effect.

## Pre-PR fresh-eyes round 3 (folded in; also closes f31h)

Round 3 found two producer/consumer string-mismatch gaps, both fixed:

1. **Buttons never actually excluded (closes bd f31h).** `acroform_dump._TYPE_NAMES`
   had no entry for `fitz.PDF_WIDGET_TYPE_BUTTON`, so a real push-button widget got
   `logical_type="unknown(1)"`, never the literal `"button"` that
   `is_fillable_widget` checks -- so the "buttons excluded" guarantee was dead
   against real PDFs (a real button would be backfilled as a bogus text field).
   Fixed at the source: added `PDF_WIDGET_TYPE_BUTTON: "button"` to the dumper.
   None of the 4 shipped kits have a button widget, so zero impact on them; this is
   forward-looking robustness. New test pins the producer/consumer contract
   (asserts the dumper emits "button"), not just a synthetic fixture.
2. **Dead combo/list keys.** `_LOGICAL_TO_FIELD_TYPE` used `"combo"`/`"list"` but
   the dumper emits `"combobox"`/`"listbox"`/`"signature"`. Harmless today (both
   fell through to the text default) but misleading; fixed to the real strings +
   added `signature` -> text. New test drives the real dumper strings.

## Scope note

The redirect deprioritized committing accurate re-extractions of w7-2/f1040 (they
stay on their hand-verified shipped v1 schemas); this bead now delivers the
extractor FIX. The original P2.2 structural assertion is met deterministically by
fix 3. Actually re-extracting + committing the three kits, if still wanted, is a
clean follow-up now that the pipeline guarantees coverage.
