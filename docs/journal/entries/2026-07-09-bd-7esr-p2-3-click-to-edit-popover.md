---
date: 2026-07-09
bead: polyglot-pdf-7esr
title: "P2.3: click-to-edit popover in Preview mode"
sprint: 9
tags: [conventions, testing]
---

## Trigger

Third bead of the sprint-9 editable-Preview epic (`polyglot-pdf-oaiz`, plan
`docs/sprint_9_editable-preview_plan.md`), strictly ordered after P2.2 (bd
lp5v, PR #361 -- shares the FieldOverlay/PDFViewer/css write surfaces).
Preview mode painted values but was read-only; spotting a wrong answer meant
switching back to Simplified and hunting for the field. This bead makes the
painted form itself the correction surface.

## What shipped

- New `frontend/src/pdf-view/FieldEditPopover.tsx`: absolutely positioned
  inside `.pdf-viewer__page-inner` (page coordinate space -- scrolls with
  the page, zero scroll listeners), below the clicked rect, flipped above
  near the page bottom, clamped horizontally; `min(340px, pageWidth-16)`
  wide, internal scroll. Hosts the SAME `FieldRenderer` the Simplified view
  uses -- one input widget per type, one validation path, `read_only` +
  `flip_readonly_bit` come free (plus a small "read-only" caption).
- Write flow: `PreviewPane` gains optional
  `validationErrors`/`onFieldChange`/`onFieldBlur` props wired by SchemaForm
  to its existing `handleFieldChange`/`handleFieldBlur` -- the single place
  stamping `{confirmed: true, confirmationMethod: 'manual_edit'}` and
  fanning out `copy_to`. Write-through on change (no Save button): overlays
  repaint live while typing, exact parity with Simplified-mode edits.
  Without the handlers the surface stays read-only (defensive default).
- Overlay clickability (`FieldOverlay.onClick`): `pointer-events: auto`,
  `cursor: pointer`, `role=button`, `tabIndex=0`, Enter/Space activation,
  hover tint (schema-editor FieldOverlay precedent). Option marks are extra
  hit targets for the SAME whole-field popover -- never a direct toggle
  (10px misclicks would silently change answers). Dimmed fields are never
  clickable (the lp5v CSS pins `pointer-events: none !important`; the
  component also skips the role/handlers).
- Dismissal: Esc, click-outside (`pointerdown`, so a drag starting outside
  dismisses), the X button, a voice advance (`currentFieldId` change -- the
  snap camera jumps away and write-through means nothing is lost), and zoom
  (scale change re-anchors everything). `PreviewPane` owns `editingFieldId`;
  clicking another overlay moves the editor there (pointerdown closes, click
  reopens).

Verification: full frontend vitest 831 passed (51 files); tsc clean;
`vite build` keeps the popover in the lazy `PreviewPane-*.js` chunk --
`dist/index.html` and the entry chunk carry zero pdf-view references
(grep for the `pdf-field-edit-popover` literal: only in the lazy chunk).

Tests: `SchemaForm.previewEdit.test.tsx` runs the REAL SchemaForm ->
PreviewPane -> PDFViewer -> FieldOverlay -> FieldEditPopover chain (only
pdfjs internals mocked): click -> popover -> typed change lands in
sessionStorage with confirmed + manual_edit + copy_to fan-out + live f2
repaint; Esc / click-outside / X / editor-moves-between-fields.
`PreviewPane.popover.test.tsx`: voice-advance dismissal,
dimmed-not-clickable, no-handlers read-only, keyboard activation.

Review record: (filled at closeout -- fresh-eyes + Opus outer review.)

## Lessons

- **React.lazy resolves async in jsdom too**: after toggling to the Preview
  tab, `getByTestId` on the pane's children fails until the lazy import
  settles -- use `findByTestId` (or await the suspense) before interacting.
- **pointerdown-then-click ordering does switching for free**: closing on
  `pointerdown` outside and opening on the subsequent `click` means
  "click another field while an editor is open" needs no special-case code.

## Doc freshness

- `docs/components/pdf-view.md` -- click-to-edit section added, Tracks line
  gains FieldEditPopover.tsx; bumped.
- Other docs flagged by the freshness gate track files this branch did not
  touch (stale before this branch); reviewed and left.
  `docs/components/schema-forms.md` tracks SchemaForm.tsx: reviewed and
  left -- this bead only passes three existing SchemaForm handlers down a
  prop boundary; no claim in the doc changes.

## Files touched

- frontend/src/pdf-view/FieldEditPopover.tsx -- new popover editor
- frontend/src/pdf-view/FieldOverlay.tsx -- onClick / keyboard / hover
- frontend/src/pdf-view/PDFViewer.tsx -- editing wiring + popover render
- frontend/src/pdf-view/PreviewPane.tsx -- editing state + dismissal effects
- frontend/src/pdf-view/pdf-view.css -- popover + clickable styles
- frontend/src/schema-forms/components/SchemaForm.tsx -- pass the 3 handlers
- frontend/src/schema-forms/components/SchemaForm.previewEdit.test.tsx -- new
- frontend/src/pdf-view/PreviewPane.popover.test.tsx -- new
- docs/components/pdf-view.md -- doc bump
