# pdf-view -- the Preview-mode PDF surface

**Tracks:** frontend/src/pdf-view/featureFlag.ts frontend/src/pdf-view/viewMode.ts frontend/src/pdf-view/PreviewPane.tsx frontend/src/pdf-view/PDFViewer.tsx frontend/src/pdf-view/FieldOverlay.tsx frontend/src/pdf-view/valuePainting.ts frontend/src/pdf-view/useSnapToField.ts frontend/src/pdf-view/FilledPreviewModal.tsx frontend/src/pdf-view/usePDFDocument.ts frontend/src/pdf-view/PDFPage.tsx frontend/src/pdf-view/pdfWorker.ts frontend/src/pdf-view/pdfCoordinates.ts

*Last updated: 2026-07-07. See [../journal/entries/2026-07-07-bd-f58l-e2e-verify-pdf-view-doc.md](../journal/entries/2026-07-07-bd-f58l-e2e-verify-pdf-view-doc.md) for closeout details.*

`frontend/src/pdf-view/` renders the actual form PDF in the browser (pdf.js)
with the user's answers painted at their printed positions -- the "Preview"
half of the dual view modes (epic `polyglot-pdf-js7q`, sprint 8 plan
[`docs/sprint_8_preview-mode_plan.md`](../sprint_8_preview-mode_plan.md)).
Related: the linear form and its state layer are in
[schema-forms.md](schema-forms.md); server-side fill is in
[pdf-filling.md](pdf-filling.md).

## The gate: default-off until cutover

Every UI surface here renders only behind the opt-in flag
(`featureFlag.ts::isPreviewUiEnabled`): URL `?previewUi=1`, persisted in
sessionStorage for the browser session; `?previewUi=0` opts out; fail-closed.
With the flag off, the deployed UI is unchanged and NO pdf.js bytes are
fetched: `SchemaForm` reaches this module only through two `React.lazy`
boundaries (`FilledPreviewModal`, `PreviewPane`), so Rollup keeps pdfjs-dist in
a shared lazy `pdf-view-*.js` chunk that `index.html` does not modulepreload.
The only statically-imported files (`featureFlag.ts`, `viewMode.ts`) are
pdfjs-free -- keep them that way. Flipping the default is a maintainer-gated
cutover decision, not part of this module.

## View modes

`viewMode.ts`: `'simplified' | 'preview'`, sessionStorage-persisted,
deliberately OUTSIDE `SchemaFormState` (purely presentational; never in the WS
handshake). `initialViewMode(flagOn, stored, viewportWidth)` decides fresh
mounts: Simplified by default everywhere; a stored `'preview'` choice is
honored only flag-on at desktop width (mobile-width mounts always start
Simplified, epic rubric #5). SchemaForm renders the toggle and keeps the voice
overlays + ConnectionManager OUTSIDE the switched container, so toggling never
remounts them or disturbs the Gemini session.

## The live surface (PreviewPane -> PDFViewer -> FieldOverlay)

- `usePDFDocument` + `PDFPage` + `pdfWorker`: pdf.js loading and per-page
  canvas rendering (StrictMode-safe cancellation). **pdfjs-dist is pinned to
  4.10.38 and imported via the LEGACY build + `?url` worker import**: early
  4.x (incl. the schema editor's 4.0.379) carries a top-level await the app's
  es2020 Vite target rejects, and the raw `new URL()` worker form 403s under
  the worktree node_modules junction in dev.
- `pdfCoordinates.ts`: schema `pdf_position` values are top-left-origin PDF
  points (PyMuPDF widget rects), so screen position is a pure multiply by the
  render scale -- no Y-flip.
- `FieldOverlay`: one absolutely-positioned div per positioned field, colored
  by FILL state -- empty (gray outline), filled (blue), confirmed (green),
  current (orange) -- with the value painted inside (`valuePainting.ts`):
  fitted text, an X for boolean checkboxes, option values resolved to LABELS
  for radio/select/checkbox_group (labels paint at the field-level rect until
  per-option rects exist -- a phase-2 epic item). Read-only; click-to-edit is
  phase 2.
- `fillStateFor` (PDFViewer): `[]` and `false` count as empty (a cleared
  checkbox_group must not paint as filled); `current` wins over all.
- Live updates ride the existing `schemaFormStateChange` channel one level up:
  SchemaForm (already subscribed) passes fresh `fieldValues` props per change.
  The page CANVAS never re-renders per fill (its effect deps are stable);
  only the overlay layer does.
- QA surface: fields with no usable `pdf_position` are console.debug-listed
  once per pane mount (4 on the i-90).

## Snap-to camera

`useSnapToField`: on every `currentFieldId` CHANGE (SchemaForm tracks it from
`next_field_hint` and clears it when that field is confirmed), the pane snaps
instantly to the field's overlay via `scrollIntoView(block:'center',
behavior:'auto')` -- deliberately NO animated motion. The free-wander rule:
user scrolling is never fought; snaps fire only on a field change or the
toolbar's "Snap to current field" button. Two hardenings matter here: the
`isSnappable` short-circuit (unpositioned fields never poll) is held in a REF
so no caller's identity churn can re-fire the snap effect (state reloads churn
object identities per fill -- keying the effect on them re-snapped on every
fill), and the pane is its own scroll viewport (`max-height`) so the toolbar
stays visible.

## The true preview (FilledPreviewModal)

The "Preview Filled PDF" button POSTs current values through the SAME
`fillPDF()` / `/api/fill-pdf` (PyMuPDF) path as download/print and renders the
returned bytes -- the modal shows the backend's own output, so it matches a
download exactly. Client-side value painting in the live surface is an
approximation for feedback; this modal (and download) is the ground truth.

## Fidelity caveats (accepted, current)

- Client-painted text sizing approximates the PyMuPDF fill (comb spacing,
  font shrink); the FilledPreviewModal is the exact render.
- Radio/checkbox-group selections paint their labels at the field-level rect
  (tiny for 10px option boxes) until the per-option `pdf_position` backfill.
- `signature` fields DO get overlays (the i-90 has 4, w7/w7-2 have 2 each,
  all with valid `pdf_position`): a signature is not paintable as text, so if
  one ever carried a string value it would render as raw text in its rect.
  Simplified mode has no signature INPUT widget yet
  (`FieldRenderer` marks the type not-yet-implemented), but that is a
  widget gap, not a value/paint gap -- nothing restricts `update_form_fields`
  by field type, so the overlay path is live.
- Textarea width-fitting assumes a single line; long wrapped values clip.
