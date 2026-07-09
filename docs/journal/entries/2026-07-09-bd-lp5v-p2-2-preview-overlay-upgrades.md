---
date: 2026-07-09
bead: polyglot-pdf-lp5v
title: "P2.2: Preview overlay upgrades -- TS type sync, option-rect painting, show_if dimming"
sprint: 9
tags: [conventions, testing]
---

## Trigger

Second bead of the sprint-9 editable-Preview epic (`polyglot-pdf-oaiz`, plan
`docs/sprint_9_editable-preview_plan.md`), unblocked by P2.1 (bd 5f41, PR
#359) landing per-option `pdf_position` in the kit schemas. Preview mode
painted radio/checkbox selections as labels at the field-level rect; with
option rects available it can paint a mark at each selected option's printed
box, and conditionally-hidden (show_if) fields should read as inert rather
than painting like active fields.

## What shipped

- `selectedOptionRects(field, raw)` (`valuePainting.ts`): the rects to paint
  selection marks at -- one per SELECTED option carrying a usable
  `pdf_position`. Radio (single slug), checkbox/checkbox_group (array or
  backcompat comma-string). Selects are deliberately excluded: a dropdown's
  options are choice values of one shared widget, no printed boxes (mirrors
  the P2.1 backfill's dropdown-skip rule). Coverage is ALL-OR-NOTHING per
  selection (fresh-eyes round 1): any selected value without a usable
  same-page rect sends the whole selection to the label fallback -- partial
  marks would silently hide the uncovered selections, and a cross-page rect
  would paint inside the wrong page container (PDFViewer buckets overlays by
  the FIELD's page).
- `FieldOverlay`: when `selectedOptionRects` is non-empty, X marks render as
  sibling divs at each option's own rect and the field-level box paints no
  duplicate label; the box itself stays (it is the `data-field-id` snap-to
  anchor). Empty -> the previous label-at-field-rect fallback, unchanged.
- show_if dimming: `PDFViewer` computes `dimmed = !shouldShowField(field,
  fieldValues, fields)` per overlay (the wrapped map -- the evaluator unwraps
  internally), `FieldOverlay` renders dimmed as 0.35 opacity + dashed border
  via `pdf-field-overlay--dimmed` (border/background overrides ride inline
  because the fill-state styles are inline and would beat a class rule).
  `current` wins over dimmed -- the field the voice model is on is never
  dimmed. Dimmed overlays are not clickable (`pointer-events: none
  !important` pins it against P2.3's future click handler).
- TS type sync: frontend `FieldOption` gains `pdf_on_value` (stale vs backend
  since bd h76m.3) and `pdf_position`; schema-editor `FieldOption` gains
  `pdf_position` under its round-trip-does-not-strip contract.
- Tests: `selectedOptionRects` unit tests (rects, fallback, degenerate rects,
  select exclusion, unknown slugs); `FieldOverlay.test.tsx` (mark at scaled
  option rect, no duplicate label, fallback, dimming, current-wins,
  dimmed marks); `PDFViewer.dimming.test.tsx` (shouldShowField wiring, live
  flip via rerender, current-wins, not-clickable) with PDFPage mocked.

Verification: full frontend vitest 822 passed; frontend tsc clean;
schema-editor tsc clean + 612 tests passed (the suite's 15 reported errors
are pre-existing noise -- the unmodified dev checkout reports 16); flag-off
bundle unchanged in kind -- `vite build` keeps pdf-view in its own lazy
chunk and `dist/index.html` carries zero references to it.

Review record: (filled at closeout -- fresh-eyes + Opus outer review.)

## Lessons

- **RTL auto-cleanup needs vitest `globals: true`; this repo runs without
  it.** Multi-render component tests silently accumulate DOM across tests
  ("Found multiple elements") unless the file registers
  `afterEach(() => cleanup())` -- the repo's existing component tests all do
  this by hand; new test files must copy the pattern.
- **Inline styles beat CSS classes**: the dimmed state could not be a pure
  CSS override because fill-state border/background are inline; the
  component must branch inline styles AND add the class (the class carries
  opacity/pointer-events, which have no inline competitor).

## Doc freshness

- `docs/components/pdf-view.md` -- FieldOverlay section rewritten for
  option-rect marks + dimming; fidelity caveat updated; bumped.
- `docs/components/schema-forms.md` -- flagged because it tracks
  `frontend/src/schema-forms/types/schema.ts`; reviewed and left: it makes
  no claims about `FieldOption` or pdf plumbing, and the change is two
  optional type fields mirroring the backend model.
- Other docs flagged by the freshness gate track files this branch did not
  touch (stale before this branch); reviewed and left.

## Files touched

- frontend/src/schema-forms/types/schema.ts -- FieldOption pdf_on_value + pdf_position
- schema-editor/src/types/schema.ts -- FieldOption pdf_position
- frontend/src/pdf-view/valuePainting.ts -- selectedOptionRects helper
- frontend/src/pdf-view/FieldOverlay.tsx -- option marks + dimmed rendering
- frontend/src/pdf-view/PDFViewer.tsx -- shouldShowField dimming wiring
- frontend/src/pdf-view/pdf-view.css -- option-mark + dimmed rules
- frontend/src/pdf-view/valuePainting.test.ts -- selectedOptionRects tests
- frontend/src/pdf-view/FieldOverlay.test.tsx -- new component tests
- frontend/src/pdf-view/PDFViewer.dimming.test.tsx -- new wiring tests
- docs/components/pdf-view.md -- doc bump
