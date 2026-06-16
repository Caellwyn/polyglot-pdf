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

- **`PDFViewer.phase4.test.tsx` -- DELETED.** All 13 tests were
  `expect(true).toBe(true)` with a comment block; the file documented the
  click/hover/select workflow but ran zero production code (it would stay green if
  the click+hover impl were deleted). The real behavior is covered with `fireEvent`
  in `FieldOverlay.test.tsx` (17 asserting tests, 0 stubs -- verified before
  deleting), so the file was pure redundant documentation-as-suite.
- **`PDFViewer.phase5.test.tsx` -- 22 stubs removed, 5 real tests kept.** The kept
  tests assert observable behavior: the Fit Width / Fit Page buttons render, manual
  zoom changes the displayed percentage (100% -> 125%), and a preset click mid-zoom
  does not throw. The fit-width/fit-page scale-clamp MATH (the
  `(containerWidth - padding) / pageWidth` calc + 0.5..2.0 clamp) depends on
  container rects, which are 0 under jsdom -- so it is documented in the file header
  as a real-browser check rather than faked with an `expect(true)` that asserts
  jsdom's 0-rect behavior.
- **`PDFViewer.phase2.test.tsx` -- two fixes.** The "clamp page input" test fired a
  change event and asserted NOTHING; it now asserts the controlled input clamps to
  `'3'` (over-max) and `'1'` (below-min). The duplicate "scroll to page 2" test was
  removed: under jsdom every rect is 0, so a page-1 target and a page-2 target
  produce identical (0) `scrollTo` coordinates -- the two tests were
  indistinguishable and would both pass even if page routing were reversed. The
  remaining scroll test asserts only what IS observable (a positioned field fires
  the scroll), with the page-specific target documented as a real-browser check.
- **`usePDFDocument.test.ts` -- cleanup test fixed.** It asserted
  `expect(mockDoc).toBeTruthy()` (the test's own local, always true) and never
  checked the document was destroyed. It now waits for the load to resolve
  (`result.current.document === mockDoc`) then asserts the loaded doc's `destroy()`
  is called once on unmount (the real cleanup at `usePDFDocument.ts:87`).

After: no schema-editor test file is `expect(true)` stubs or act-without-assert.
Full schema-editor suite 138 pass (down from 174 by the removed fake tests); tsc
clean.

## The honest-vs-faked line (the uov.16 thesis)

The judgment call running through 840i: a green vitest run on a canvas/PDF UI does
NOT prove the UI works (the testing-standards doc says as much). Where behavior is
observable in jsdom (button presence, controlled-input clamp, manual-zoom
percentage, destroy-on-unmount) I added a real assertion. Where it is NOT (the
fitted scale value, the per-page scroll target -- both rect-dependent) I deleted the
fake guarantee and pointed at the real-browser check rather than encode jsdom's
0-rect behavior as if it were the feature. Deleting a misleading test is a coverage
INCREASE, not a decrease: the suite no longer claims to cover what it cannot.

## Closeout notes

- **Doc-freshness:** 10 docs flagged STALE, all backend/voice-path tier-2 docs from
  other merged work; none track `EDITOR_GUIDE.md` or any schema-editor test file
  (only journal entries reference them, and those are not `**Tracks:**` docs).
  Nothing this PR is to bump. (`EDITOR_GUIDE.md` itself is a guide, not a
  freshness-tracked tier-2 doc, and it WAS updated here for cmcg.)
- **Beads slip:** the recurring `hrn` / `jf6w` stale IN_PROGRESS beads belong to
  other active sessions; left untouched.
