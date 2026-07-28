---
date: 2026-07-28
bead: polyglot-pdf-g63j
title: "Sprint-17 C3: green means a human said so + honest position diagnostics"
tags: [editor, frontend, ux]
---

## Trigger

Epic polyglot-pdf-did2 (sprint 17), C3. Two maintainer observations from the
W-7 session:

1. "The colors for un-reviewed and reviewed-correct are both green in the PDF
   view highlights and the field list marks. Un-reviewed should be amber."
2. The two mis-labeled W-7 "signature" fields showed no preview highlight and a
   MISLEADING error -- they read as phantoms when they were really the phone
   and printed-name widgets with wrong labels.

## What shipped

**(a) Green is human sign-off only.** `reviewStatus.effectiveStatus`'s
un-reviewed branch now returns 'review' (amber) unconditionally, instead of
falling through to the automatic derivation. `getCompletionStats` mirrors it:
`complete` counts ONLY reviewed_correct, so the progress bar answers "how much
has a person reviewed?" rather than "how much did the machine fail to fault".
The automatic `checkFieldComplete` result is NOT discarded -- its ERRORS still
win outright (red beats everything) and its reasons still populate the amber
WHY-list. It simply no longer grants green on its own. Because the FieldList
icon, the FieldOverlay border and the counters all already routed through these
two functions (bd u8t6 + the kd45 fix), every surface moved together.

**(b) Honest position diagnostics.** New `pdfCoordinates.overlayBlockReason`
names, in plain language, why a field would draw NO overlay -- distinguishing
three cases that used to be one silent void: no position recorded; a degenerate
rect (zero width/height); and a page number outside the document. Wired into
`checkFieldComplete` as an amber REASON (not a red error: the editor cannot
prove the field is unfillable, since the backend filler resolves widgets by
NAME, not by the schema rect). Crucially it never emits the false "Missing PDF
field name" for a field that HAS a name -- the message that made two correctly
named W-7 fields read as phantoms.

**(c) Page count plumbed to the diagnostics.** `checkFieldComplete` /
`effectiveStatus` / `isReviewTarget` take an optional `pageCount`; PDFViewer
reports its loaded document's page count upward (`onPageCountChange`) and App
threads it into FieldList and FieldEditor. The viewer already owns the
document, so reporting beats making App load the PDF a second time to count
pages. Absent count -> the page-range half stays silent (schema-only contexts
never invent a defect).

**(d) The FieldEditor banner now lists the amber reasons too.** It previously
showed only errors + lint findings, so a field flagged amber in the list gave
no explanation in the pane the author actually edits in.

Note on the 1-based convention: schema `pdf_position.page` is ONE-based (the
extraction pipeline converts the 0-based dump page with an explicit +1) and
PDFViewer renders pages 1..numPages, so `page: 0` -- a rect that never got that
conversion -- is out of range and invisible, not page one. Pinned by a test.

## Tests

- `pdfCoordinates` + `validation`: the three position cases, the page-range
  boundary, page-0, the schema-only silence, and the choice-field exemption
  (a consolidated group's field-level rect is legitimately absent).
- `FieldList.pagerange.test.tsx` (new): the diagnostics as the author sees them
  in the row tooltip, including the never-say-"Missing PDF field name" pin.
- `reviewStatus` / `validation` / `FieldOverlay` / `FieldList.review`: the
  amber-always semantics on all three surfaces, plus a new test that "Next to
  review" stays ENABLED while a clean field is un-reviewed.
- Fixture sweep: ~10 test fixtures represented "complete" as machine-clean;
  under g63j that now means signed off, so they carry `_review` (and, where the
  test asserts a clean banner/tooltip, a drawable position). No assertion was
  weakened -- each fixture was updated to still mean what its test says.
- Full schema-editor suite green (58 files, 838 tests after the review rounds);
  tsc clean.

## Review rounds

Three gaps and two nits found and fixed before the PR:

1. (blocker) The position check inherited the MAPPING check's `!isChoice` gate
   without re-deriving its scoping. Those answer different questions -- a
   consolidated group's field-level NAME is legitimately absent, but PDFViewer
   draws an overlay from `field.pdf_position` for ANY field that has one. The
   shipped i-90 carries several single-widget radios with real field-level
   rects, so this reproduced the bead's own target bug for that family.
2. (nit) `pdfPageCount` went stale across kit switches, judging a new kit's
   fields against the previous kit's page count. PDFViewer now publishes
   unconditionally including 0 = "unknown".
3. (nit) The amber icon was pinned only by ABSENCE elsewhere, so a regression
   mapping it to the green check would have passed the whole suite. Now pinned
   positively -- and the reviewer confirmed by mutation probe that both the
   amber logic and the icon mapping now fail tests when broken.
4. (nit) The scoping comment claimed named fields were always covered, but the
   code exempts a named CHOICE field with no field-level rect (a true
   shared-name radio group -- flagging it would fire on every real group).
   Comment corrected and the cell pinned.
5. (nit) A fractional page passed the range check yet can never match a
   rendered page. Now requires an integer.

A sweep of the three shipped kits confirmed this is not noisy: w7 and i-90
produce zero new position warnings; f1040 produces four, all true positives
(the same fields already filed as bd polyglot-pdf-lha9).

## Live verification

Ran the real modules from the dev server against the shipped i-90 schema:
un-reviewed clean field -> 'review'; signed off -> 'complete'; an off-page
field -> `PDF widget "P1_Line1_AlienNumber[0]": This field claims page 99, but
the form has 6 page(s) -- it can never appear on the preview`; a half-signed
two-field schema -> 50%.

## Follow-on

C4 (bd mzkw) adds the grey Ignored quarantine status, which will slot into the
same effectiveStatus precedence as a peer state.
