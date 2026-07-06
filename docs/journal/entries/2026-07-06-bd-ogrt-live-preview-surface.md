---
date: 2026-07-06
bead: polyglot-pdf-ogrt
title: "P1.2: live Preview surface -- field overlays + value painting"
sprint: 8
tags: [conventions, testing]
---

## Trigger

Third bead of the preview-mode epic (`polyglot-pdf-js7q`, sprint 8), on top of
the P1.1 view-mode shell (PR #338). This is the epic's core promise: the
user's answers paint onto the real PDF at their printed positions, live, as
the voice session fills them.

## What shipped

- **PDFViewer + FieldOverlay** (`frontend/src/pdf-view/`), ported
  copy-then-diverge from the schema editor. The divergence is substantive:
  the editor's overlay colors by metadata completeness and is clickable; the
  app's colors by FILL state -- empty (subtle gray), filled (blue), confirmed
  (green), current (orange) -- and is read-only (click-to-edit is phase 2).
- **valuePainting.ts** (unit-tested): what displays inside a rect -- fitted
  text (height-sized, width-shrunk, 6px floor), an X glyph for boolean
  checkboxes, and option VALUES resolved to their LABELS for
  radio/select/checkbox_group (labels join at the field-level rect until the
  phase-2 per-option rect backfill).
- **PreviewPane** upgraded from blank placeholder to the live surface. Fields
  with no usable `pdf_position` are console.debug-listed once per mount (the
  QA surface; 4 on the i-90).
- **Live updates**: rather than a second subscription in the pane, SchemaForm
  (already subscribed to `schemaFormStateChange`) passes fresh `fieldValues`
  props down each change -- same channel, one level up, one source of truth.
  SchemaForm also tracks `currentFieldId` from the next-field hint; Preview
  colors it, and the P1.3 snap camera keys on the same state.
- **Runtime type gap found + filed**: v2 form-kit schemas carry
  `checkbox_group` at runtime but the FE `FieldType` union stops at v1 and
  FieldRenderer has no route -- those two i-90 fields hit the unknown-type
  error block in Simplified view today (pre-existing). Filed as
  `polyglot-pdf-w146`; valuePainting handles it via a string-widened switch
  with a pointer comment.

Verified live on the local stack: values paint at their printed rects on the
real I-90 (comb-box A-number aligned inside its cells; confirmed names green;
an unconfirmed fill blue; current field orange); a `schemaFormStateChange`
while IN Preview mode repaints without reload; `copy_to` mirror fields paint
on later pages; 782 FE tests pass.

Fresh-eyes assess outcome: round 1 (sonnet, arm B picker) GAPS-FOUND(3), all
three correct and ADOPTED: (1) `fillStateFor` missed empty-array -- a cleared
checkbox_group painted filled/confirmed (now `[]` = empty, matching
validation.ts's convention, with new fillState.test.ts pinning it); (2) the
"once per mount" QA log actually re-fired per fill because `state.schema` gets
a fresh object identity on every state reload (deps now deliberately empty);
(3) `currentFieldId` was never cleared, leaving a confirmed field stuck orange
after the last hint (now confirmed clears the marker). It also filed
`polyglot-pdf-jq17` out-of-scope (single-option checkbox on f1040/w7 paints
the label instead of an X glyph; zero such fields on the i-90). All fixes
re-verified live. Final Opus clearing round: NO-GAPS -- it actively attacked
per-fill canvas render cost (PDFPage effect deps stable across fills -- only
the cheap overlay layer re-renders), coordinate alignment, the id-space of the
next-field hint, and the confirmed-clears effect (no loop; a one-frame orange
flash on same-step fill+confirm is cosmetic). Its three residual notes
(signature data-URL would paint as text -- unreachable today; a string 'false'
checkbox would border blue with no X -- not a live path; the flash) are
recorded here as accepted polish debt for the epic's later beads.

## Lessons

- **The linear form's change-listener gates on `state.lastUpdated`** -- a
  synthetic state write that skips it will NOT repaint (my first live-update
  test failed exactly there; real fills always bump it via `updateField`).
  When emulating the fill channel, be faithful to the whole write, not just
  `fieldValues`.
- **Copy-to mirrors come for free**: `updateField`'s copy_to handling means
  mirror fields on later pages paint without any preview-side logic -- a nice
  proof the paint layer is purely a projection of client state.

## Doc freshness

- `docs/components/schema-forms.md` reviewed: its preview-flag paragraph
  (added in the vxwj closeout) still accurately describes SchemaForm's role
  (toggle + lazy pane + modal); the pane's internals belong to the epic's
  P1.4 `docs/components/pdf-view.md`, so no bump needed this PR.
- The recurring pre-existing STALE set (backend-file worktree mtimes) left
  as-is again.

## Files touched

- `frontend/src/pdf-view/`: `PDFViewer.tsx`, `FieldOverlay.tsx`,
  `pdfCoordinates.ts`, `valuePainting.ts` (+ test), `PreviewPane.tsx`
  (rewrite), `pdf-view.css`
- `frontend/src/schema-forms/components/SchemaForm.tsx` (currentFieldId +
  pane props)
- this journal entry
