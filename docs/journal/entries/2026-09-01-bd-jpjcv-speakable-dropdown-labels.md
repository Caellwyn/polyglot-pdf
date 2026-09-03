---
date: 2026-09-01
bead: polyglot-pdf-jpjcv
title: "fix(authoring): a dropdown label a voice model can SAY -- and the predicate that would have broken height_feet"
tags: [authoring, voice, pdf-view, testing, review]
---

## Trigger

Caused by bd `polyglot-pdf-hmkas`, not found ambiently. hmkas told the model to
omit a select's options entirely (it only ever sees a truncated 12-item sample),
which made the deterministic backfill the ONLY path -- and that path fell back to
the PDF's /Opt display string, which for the i-90's state widgets is the export
code again. So a fresh extraction yields `{'value': 'AL', 'label': 'AL'}` and the
voice guidance reads `[AA, AE, AK, AL, ...]`. The user says "Alabama"; the model
must map that onto `AL` from a list carrying no state names.

Reproduced before fixing, through the real backfill.

## What shipped

A closed US state/territory/military code table, plus an `unspeakable` report
for anything it cannot expand -- printed to stderr AND persisted as
`_bakeoff.authoring.dropdown_labels_unspeakable`, because a stderr line is lost
on a batch extraction. Precedence: a model-written label wins, then a real PDF
display string, then the table, then the bare code + a report.

The VALUE is never touched. It is the export code that prints.

## Lessons

**The obvious predicate would have caused a bug.** `label == value` looks like
the rule and is not. Surveying the shipped kits first:

    i-90_v2 mail_state    n=62  bare=0   ('AK' -> 'Alaska (AK)')
    i-90_v2 height_feet   n=7   bare=7   ('5'  -> '5')

The state dropdowns were already correct; the fully-bare fields are the HEIGHT
ones, where `label == value` is RIGHT -- the label for the number 5 is "5". A
"no bare labels" rule would flag those and invite an editor to turn a number
into prose. The real test is SPEAKABILITY: a digit is speakable as itself, an
alphabetic code is not. Pinned from both directions, since crying wolf on
legitimate data is its own failure.

**A test had pinned the defect as correct.** `test_a_model_label_for_the_SAME_
code_is_preserved` asserted `{"value": "WY", "label": "WY"}` with the comment
`# no prior label -> code` -- describing the bug rather than questioning it. The
tell is a degraded expected value with a comment that explains rather than
justifies.

**I stated one rule in two places and they disagreed.** The helper had no length
limit; the caller gated the report at `len <= 3`. So a 4-letter code shipped
bare with NO report -- exactly the failure the report exists to surface. The
same split produced a dead branch (`if not isalpha() or len > 3: return None`
above an unconditional `return None`) which made the caller's copy look
redundant rather than contradictory. One `_is_speakable_as_itself` now.

**An exit criterion named a fixture that no longer existed.** Criterion 2
required driving `form-kits/i-90/form.pdf`; PR #705 had deleted that kit. And no
tracked kit replaces it -- f1040, w7 and w9-heldout contain ZERO ComboBox/ListBox
widgets between them and zero selects, so a "shipped kits" assertion could only
ever be vacuous. My first draft was exactly that, and **its own non-vacuity floor
caught it** at `checked == 0`. Replaced with a test that BUILDS a combobox PDF.
Recording the correction on the bead at claim time, before building, is what made
it a scope call rather than a quiet narrowing.

**My fix caused a regression in a surface I had not touched.** Speakable labels
overflow the preview overlay: measured against the shipped `fittedFontSize`,
"Armed Forces Americas (AA)" needs ~86px at the 6px floor in a 36px state box,
where "AA" sat crisp at 11px. The cross-surface reviewer found it and correctly
filed it non-blocking; the maintainer chose to fix it here, because it is a
regression THIS diff causes on the exact form they are completing.

**And my rationale for that fix was weaker than the real invariant.** I justified
painting the value as "the value is an export code by construction (hmkas)". The
reviewer showed that is not universally true -- a dump-less kit lints clean with
slug-valued selects. What actually licenses it: `pdf_fill_routes` has NO select
branch, so a select falls through to the text path and whatever its value is IS
what prints. Correct unconditionally, and in the slug case it honestly previews
`wyoming` clipping to `wyomin` instead of hiding it behind a label.

**A test's title claimed coverage it did not have.** "resolves radio/select
option values to their labels" only ever BUILT a radio, so it never pinned the
select behaviour I changed. Renaming it was as important as adding the new tests.

## Files touched

- `scripts/authoring/extract_form.py` -- the table, the shared predicate, the report
- `frontend/src/pdf-view/valuePainting.ts` -- a select paints its VALUE
- `tests/test_extract_form_backfill.py`, `frontend/src/pdf-view/valuePainting.test.ts`
- `docs/components/pdf-view.md` -- made false by my own overlay fix

## Follow-ups (filed by the reviewers, still open)

- `polyglot-pdf-o9o3n` -- the editor extract route reports the LAST stderr line as
  its success detail; pre-existing, this diff adds one more stderr source.
- `polyglot-pdf-bxjck` -- g1b's answer key maps full-name state slugs, but the
  extractor writes export codes.
- `polyglot-pdf-8c0ik` -- a real-i-90-PDF test that has skipped permanently since #705.
