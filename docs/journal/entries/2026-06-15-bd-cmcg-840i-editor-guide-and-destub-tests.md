---
date: 2026-06-15
beads: [polyglot-pdf-cmcg, polyglot-pdf-840i]
pr: TBD
tags: [testing, conventions]
---

# cmcg + 840i: EDITOR_GUIDE ConditionalControl + de-stub schema-editor tests

Two schema-editor housekeeping beads bundled. cmcg is the doc follow-on to the
y61i `ControlsFields` -> `ConditionalControl[]` rename (PR #215); 840i replaces fake
green test coverage flagged by the uov.16 re-audit. Same surface, both low-risk.

## cmcg -- EDITOR_GUIDE.md referenced a deleted type

`EDITOR_GUIDE.md:1077` still declared `controls_fields?: ControlsFields` -- the
single-object type deleted when y61i corrected the editor to the real array shape.
Fixed the FormField interface block to `controls_fields?: ConditionalControl[]` (a
LIST) and added a `ConditionalControl` shape block + an authoring-workflow section
(operator/value + the six target-id action lists), with an example and a note that
every referenced id must be a real field id (the y61i validator flags any that is
not, tolerating forward references). `grep ControlsFields EDITOR_GUIDE.md` now
returns nothing -- the cmcg exit criterion.

## 840i -- fake green coverage replaced with real assertions or honest deletion

The uov.16 re-audit found schema-editor tests that pass against nothing. Fixed each
per the bead's "real assertion OR delete-with-a-note" rule:

- **`PDFViewer.phase4.test.tsx` -- all 13 `expect(true)` stubs removed, then the
  file was REBUILT with a real suite (see "Codex round 1" below for why).** The
  original 13 tests were `expect(true).toBe(true)` comment blocks that ran zero
  production code. My first instinct was to delete the file outright as "covered by
  `FieldOverlay.test.tsx`" -- but Codex correctly showed that file only covers
  `FieldOverlay` IN ISOLATION (a directly-supplied `onClick`), NOT the PDFViewer
  wiring. So the file now holds two real tests: PDFViewer wires
  `onClick={() => onSelectField(id)}` to each overlay (click -> callback with the
  right id), and PDFViewer propagates `isSelected` from `selectedFieldId` (the
  selected overlay flips to a 4px border + blue glow). Final state: a real
  PDFViewer-to-FieldOverlay wiring suite, NOT a deletion.
- **`PDFViewer.phase5.test.tsx` -- 22 stubs removed, 5 real tests kept.** The kept
  tests assert observable behavior: the Fit Width / Fit Page buttons render, manual
  zoom changes the displayed percentage (100% -> 125%), and a preset click mid-zoom
  does not throw. The fit-width/fit-page scale-clamp MATH (the
  `(containerWidth - padding) / pageWidth` calc + 0.5..2.0 clamp) IS exercised
  under jsdom by stubbing the scroll container's `clientWidth`/`clientHeight` to
  non-zero values so the handlers run, then asserting the EXACT fitted percentage
  (Fit Width 153% / 200% upper-clamp / 50% lower-clamp; Fit Page 106%
  height-constrained / 104% width-constrained / 200% upper-clamp). (This is the
  final state; the Codex rounds below record how it got there -- an early pass left
  these as "does not throw" smoke tests before the container-size stub made the math
  observable.)
- **`PDFViewer.phase2.test.tsx` -- two fixes.** The "clamp page input" test fired a
  change event and asserted NOTHING; it now asserts the controlled input clamps to
  `'3'` (over-max) and `'1'` (below-min). The duplicate "scroll to page 2" test was
  collapsed into one, which now asserts the PAGE-SPECIFIC outcome: selecting
  `field-page2` drives `currentPage` to 2, so the page-number input reads `'2'`
  (plus the `scrollTo` call). The page NUMBER is observable in jsdom even though the
  scroll COORDINATE is 0 -- so this catches a page-routing regression (an earlier
  pass wrongly deferred the page target to a browser check; the Codex rounds below
  record the correction).
- **`usePDFDocument.test.ts` -- cleanup test fixed.** It asserted
  `expect(mockDoc).toBeTruthy()` (the test's own local, always true) and never
  checked the document was destroyed. It now waits for the load to resolve
  (`result.current.document === mockDoc`) then asserts the loaded doc's `destroy()`
  is called once on unmount (the real cleanup at `usePDFDocument.ts:87`).

After: no schema-editor test file is `expect(true)` stubs or act-without-assert.
Full schema-editor suite passes (run `npm run test:run` in `schema-editor/` for the
live count -- it grew through the Codex rounds below as fake stubs were replaced by
real wiring/fit/page-routing tests); tsc clean.

## The honest-vs-faked line (the uov.16 thesis)

The judgment call running through 840i: a green vitest run on a canvas/PDF UI does
NOT prove the UI works (the testing-standards doc says as much). The first instinct
was to split behavior into "observable in jsdom -> assert it" vs "rect-dependent ->
defer to a browser check." The Codex rounds below pushed that line MUCH further than
the first pass: much of what looked rect-dependent IS observable once the jsdom
environment is set up properly -- stub `clientWidth`/`clientHeight` on the scroll
container and the fit MATH + clamp produce exact, assertable percentages; the page
NUMBER (not the scroll coordinate) is observable, so page-routing is testable;
overlay click-to-select + selected styling are testable by rendering the full
viewer. So the FINAL suite asserts the fitted scale, the page target, and the
click/select wiring for real -- very little was genuinely deferred. The lesson:
"jsdom can't test this" is often "I haven't set jsdom up to test this yet." Deleting
a misleading stub AND replacing it with a real assertion is the coverage increase;
deleting alone (the first pass) only got partway.

## Pre-PR fresh-eyes

Sonnet, 1 round -> both criteria PASS (cmcg grep clean + ConditionalControl shape
field-for-field correct; 840i no stub/act-without-assert remaining, the phase4
deletion verified safe against FieldOverlay.test.tsx's 17 real tests). 3 findings,
all fixed: (1) the phase2 clamp test waited only for the spinbutton, racing the
page-ref registration `scrollToPage` depends on -> now waits for all 3 canvases
(flake fix); (2) the phase5 click tests asserted `toBeInTheDocument()` on the
just-found button (circular) -> now assert the `100%` scale readout survives the
click (catches an error-boundary unmount); (3) the EDITOR_GUIDE example's
`value: "P1_checkbox4[0]"` could mislead new authors -> added a note that `value` is
the controlling field's STORED value and the widget-name value is I-90-specific, not
a convention. Fresh-eyes also confirmed (out of scope, not fixed) a pre-existing
`ConditionalOperator` member gap between the editor and runtime type files -- noted,
not this bead's.

## Codex round 1 (5 P1) -- the de-stubbing was incomplete

Codex's outer review was the sharp one this PR: it found that the first pass at 840i
deleted/shrank fake tests but did NOT replace 3 of them with real coverage, and left
the guide asserting stale counts. All 5 P1s were correct:

1. **phase5 fit tests never ran the fit logic.** My "does not throw" tests didn't
   stub container dimensions, so `handleFitWidth`/`handleFitPage` early-returned --
   the assertion would have passed even if the button had no `onClick`. Root cause
   (found while fixing): `PDFPage.onPageLoad` (which populates `pageDimensions`, the
   page-size reference the fit math divides by) only fires when the canvas 2d context
   is non-null, and jsdom returns null. Stubbing `getContext` + defining non-zero
   `clientWidth`/`clientHeight` on the `.overflow-auto` node makes the math run; the
   tests now assert EXACT readouts (153% in-range, 200% upper clamp, 50% lower clamp,
   106% Fit-Page height-constrained), so deleting the handler body or a clamp fails.
2. **phase4 deletion left the wiring untested.** `FieldOverlay.test.tsx` only proves
   a directly-supplied `onClick` fires -- NOT that `PDFViewer` wires
   `onClick={() => onSelectField(field.id)}` to each overlay. My "covered elsewhere"
   claim was wrong. Recreated `PDFViewer.phase4.test.tsx` with a real test: render
   the full viewer, wait for the overlay to mount, click it, assert
   `onSelectField('field-click-me')`.
3. **phase2 scroll test asserted only "some scroll".** `currentPage` IS observable
   (set from `pdf_position.page`), so my "indistinguishable under jsdom" claim was
   wrong for the page NUMBER (only the scroll COORDINATE is 0). Now asserts the
   spinbutton reads `'2'` after selecting `field-page2`.
4. **EDITOR_GUIDE stale coverage claims.** The guide still said Phase 4 added 13
   tests / created the deleted file, Phase 5 was 578 lines / 27 tests, and
   "113/113 passing". Reconciled to current reality and replaced the brittle exact
   counts with "run `npm run test:run`" so they cannot rot again.
5. **EDITOR_GUIDE example mismatch.** The new example said "reveals and unlocks" but
   the JSON only used `unlocks`. Corrected to unlock-only with a note on
   `shows`/`hides` for hidden targets.

**Lesson (recorded):** "delete a fake test because it's covered elsewhere" demands
PROVING the elsewhere actually covers the SAME wiring -- an isolation test of a child
component does not cover the parent's wiring to it. And de-stubbing a doc-heavy area
means reconciling the doc's own coverage claims in the same change.

## Codex round 2 (3 P1) -- "covered N but not N+1"

Codex held the de-stubbing to the standard of the coverage the FAKE tests had
claimed, and found 3 completeness gaps:
- **Selected-state propagation (phase4):** my new click test proved `onSelectField`
  fires but not that PDFViewer passes `isSelected={id === selectedFieldId}` to the
  overlay -- the selected STYLING could break silently. Added a rerender-with-
  selection test asserting the overlay flips to the 4px border + blue selection
  box-shadow (status-independent selection signals; the border COLOR is driven by
  field status, not selection -- a wrong first assertion I corrected).
- **Fit Page width + upper clamp (phase5):** my Fit Page coverage was only
  height-constrained + lower-clamp. Added a width-constrained case (700x2000 ->
  104%, proving `min()` picks width not always height) and an upper-clamp case
  (3000x4000 -> 200%).
- **Stale guide block (EDITOR_GUIDE):** my round-1 edit left the Phase 5 section
  with a leftover "27 new tests" heading AND text saying the clamp math was "not
  observable under jsdom" -- directly contradicting the new exact-percentage
  assertions. Removed the heading, corrected the text to state the clamp IS covered
  via stubbed container dimensions.

Two Codex rounds (5 P1 then 3 P1) on a nominally-small bundle: the signal is that
de-stubbing a fake-coverage area is real test-writing, not a doc tweak -- the
placeholders had asserted a workflow (click -> select -> highlight, full fit-math
matrix) that had to be genuinely rebuilt. Looped past the usual 2-round budget
because every round surfaced a real coverage hole, not a nit.

## Codex round 3-4 (3 then 2 P1) -- incomplete fixes resurfacing

Rounds 3 and 4 were a different character than 1-2: not new coverage holes but the
internal CONSISTENCY of what I wrote, and -- the round-4 lesson -- my own
INCOMPLETE fixes resurfacing. Round 3 corrected a code comment that contradicted the
tests, hardened the page-ready helper (wait for an overlay = proof pageDimensions is
populated, not just a canvas), and reconciled the journal summary. Round 4 then
caught that the round-3 comment fix was incomplete: the wrong "0 clientWidth ->
early-return" claim appeared in THREE places and I had fixed only one, so the two
dupes came back as findings; and one test (manual-zoom+preset) still used the old
non-page-ready helper with a bare not.toThrow(), so it was rewritten to assert the
preset overrides the manual zoom (125% -> fitted 153% -> zoom-out 128%).

Lesson recorded: when correcting a wrong claim that lives in a COMMENT, grep for ALL
copies before declaring it fixed -- a partial fix reads as resolved but resurfaces.
And the deeper one (from rounds 1-2): de-stubbing fake tests is real test-writing,
because the placeholders asserted a whole workflow that has to be genuinely rebuilt.
Four Codex rounds on a "small" bundle is the honest cost of that, not churn -- every
round surfaced a real (if shrinking) gap, never a stylistic nit.

## Closeout notes

- **Doc-freshness:** 10 docs flagged STALE, all backend/voice-path tier-2 docs from
  other merged work; none track `EDITOR_GUIDE.md` or any schema-editor test file
  (only journal entries reference them, and those are not `**Tracks:**` docs).
  Nothing this PR is to bump. (`EDITOR_GUIDE.md` itself is a guide, not a
  freshness-tracked tier-2 doc, and it WAS updated here for cmcg.)
- **Beads slip:** the recurring `hrn` / `jf6w` stale IN_PROGRESS beads belong to
  other active sessions; left untouched.
