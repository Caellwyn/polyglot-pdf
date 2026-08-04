---
date: 2026-08-03
bead: polyglot-pdf-3ave
title: "fix(form-kits): rebind f1040 page-1 income lines to their own printed rows + gate the error class"
tags: [extractor, testing, postmortem]
---

## Trigger

Next-bead pickup after PR #535. `polyglot-pdf-3ave` was the highest-priority
unclaimed item (P0): the shipped f1040 kit's page-1 amount column was shifted
by one printed row from Line 1e through Line 11a, so a filled return put
wage/interest/dividend amounts on the wrong tax lines. Silent by construction
-- every claim resolved to a real widget, so lint reported zero findings and
coverage read 100%.

The other P0 (`polyglot-pdf-z2is`, prod-readiness) was claimed by another
session six minutes before this pickup and was left alone. `polyglot-pdf-rdcq`
(CI failing repo-wide) was closed as resolved-by-time, not worked: the outage
signature was jobs failing in 2-10s with ZERO recorded steps, and every run
since 2026-08-01 is green while the last failure on record carries 8 recorded
steps -- a real test failure, not the infra break.

## What shipped

**3ave -- 24 page-1 rebinds, derived from the form, not from names.** The
correct map came from the PDF's own printed gutter markers via
`scripts/authoring/check_line_binding.py`'s primitives, then geometry for the
cases the row oracle cannot settle:

- `fld_1h_type` -> `f1_54` (the write-in at x344-475), NOT the `f1_55` amount
  box the row lookup proposed -- `fld_1h` (the amount) takes `f1_55`. Taking
  the oracle's row answer literally would have collided the pair.
- `fld_1i` -> `f1_56` (write-in, x410-482).
- `fld_4c_other` / `fld_5c_other` -> `f1_64` / `f1_67`, the "c Check if (see
  instructions) ... 1 Rollover 2 QCD/PSO 3" write-in rows, confirmed by
  reading the printed text at those y-bands. These are the checkbox rows
  interrupting the amount column that originated the miscount.
- The rebind also claims `f1_72`..`f1_75` -- the real Lines 8/9/10/11a boxes,
  the "displaced tail" nothing reached before.

Three oracle findings were rejected as FALSE POSITIVES rather than applied:
`fld_16_other`, `fld_28_check`, `fld_35a_form8888` are write-in/checkbox
fields whose correct widgets (`f2_07`, `c2_14`, `c2_15`) simply sit on
unmarked rows; the oracle sees only the amount box on that line. Applying its
suggestion would have overwritten three correct bindings onto their siblings'
widgets. A pre-write collision check caught this before anything was written.

**lha9 -- bundled, 4 lines.** `fld_1a`..`fld_1d` claimed the NON-EXISTENT
`f1_31`..`f1_34` (those names belong to `Table_Dependents`), so Lines 1a-1d
filled silently into nothing. They now bind to `f1_47`..`f1_50` -- the widgets
3ave freed. Bundled because it is a 4-line change into exactly the widgets
this PR liberated, in the same two files, and its criterion 3 is the same lint
baseline; a separate PR cycle for four lines would have wasted review.

**The new gate (`backend/tests/test_kit_line_binding.py`).** The bead's own
investigation named the real gap: NO gate measured widget-ASSIGNMENT
correctness. Existing gates catch unclaimed widgets and hallucinated claims --
a real widget belonging to the wrong line is invisible to all of them. Three
tests:

1. zero row-binding mismatches for kits with a printed gutter;
2. a per-kit FLOOR of verifiable fields, so a parser/PDF change that stops
   finding markers fails loudly instead of making test 1 vacuously true
   (the oracle abstains per-field, and abstention must never read as success);
3. an end-to-end round trip through the REAL `pdf_fill_routes.fill_pdf` with a
   distinct sentinel per income line, reading the output PDF back to ask the
   form which printed row each value landed on.

**`pdf_position` resynced (fresh-eyes finding, adopted in-PR).** The reviewer
caught that `pdf_field_name` and `pdf_position` are SIBLINGS describing the
same widget, and the rebind moved one without the other: all 28 stored
positions were 24-84pt away from their new widget (and `fld_1a`..`fld_1d` had
no position key at all). The fill path reads `pdf_field_name`, but the preview
overlay (`frontend/src/pdf-view/FieldOverlay.tsx` -> `pdfToScreenCoords`) reads
`pdf_position` and never re-derives it at runtime -- so a correct fill would
have coexisted with a highlight box on the wrong row. Rewritten from the PDF's
own widget rects; the WHOLE kit (167 positioned fields) now agrees. The
reviewer filed this as out-of-scope bead `polyglot-pdf-7yhy`; it was fixed
here instead and that bead closed, because this diff is what desynchronized
the pair and the correct values came from the same source of truth already in
hand. A new cross-kit guard
(`test_stored_pdf_position_agrees_with_the_claimed_widget`, running on f1040 /
i-90 / w7) makes the desync impossible to reintroduce silently.

**Verified:** oracle 20 mismatches -> 0 (56 fields verifiable, up from 52);
lint ERRORs 4 -> 0; `dump-widget-unclaimed` 12 -> 8; production fill round-trip
24/24 present, 0 errors, 0 misplaced. Full backend suite 1473 passed.
Mutation-verified against the shipped kit: the oracle test names all 20
misbindings, the round-trip names exactly `fld_1a`..`fld_1d` as never reaching
the PDF.

## Lessons

- **An unchanged metric can hide a real change.** Mid-fix, `dump-widget-unclaimed`
  stayed at 12 -- because the rebind CLAIMED four widgets and FREED four others.
  The count was identical while the set turned over completely. The baseline
  comment now says to read the set, not the number.
- **A row oracle cannot settle a row with two boxes.** Where a line has both an
  amount box and a write-in, "which widget is on line 1h?" has two answers and
  the oracle returns the one it can see. Geometry (the x-band) is what
  distinguishes them, and three of the oracle's 24 suggestions were outright
  wrong for exactly this reason. Check a proposed map for collisions BEFORE
  writing it -- that check is what surfaced all of them here.
- **The write-in/checkbox rows that interrupt a numeric column are where these
  shifts originate** (this bead, and bd ivh9 on w7 before it). Both times the
  cascade began at a widget the extractor did not model as part of the run.

## Doc freshness

Checked: no tier-2 doc's `**Tracks:**` globs cover the files this branch
touched (`form-kits/f1040/schema.json` + two test modules).
`docs/components/pdf-filling.md` tracks the filler routes/services, which are
unchanged -- reviewed and left as-is. The freshness checker's pre-existing
STALE set is unrelated to this diff.

## Files touched

- `form-kits/f1040/schema.json` -- 28 `pdf_field_name` rebinds (24 for 3ave,
  4 for lha9) plus the matching 28 `pdf_position` blocks resynced to the same
  widgets (24 rewritten, 4 inserted where the key was absent).
- `backend/tests/test_kit_line_binding.py` -- NEW: the widget-assignment gate
  (row oracle + verifiability floor + production fill round-trip + the
  cross-kit pdf_position/pdf_field_name agreement guard).
- `backend/tests/test_schema_lint.py` -- `_UNFILLABLE_BASELINE` f1040
  12 -> 8, with the swap-then-drop history recorded so the number is readable.
- `docs/journal/entries/2026-08-03-bd-3ave-f1040-line-binding.md` -- this entry.
