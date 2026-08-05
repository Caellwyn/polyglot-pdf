# Sprint 8 -- Preview mode: dual view modes (live PDF + Simplified)

**Epic:** `polyglot-pdf-js7q` · **Approved:** 2026-07-06 (maintainer) ·
**Origin:** exploration session 2026-07-06 (plan file
`~/.claude/plans/i-d-like-to-explore-wise-newell.md`, approved with maintainer
edits: dual modes, snap-to camera, translation correction).

## Why

Users of the voice form-filler see an abstract linear web form and must trust it
maps to the real PDF they will print and sign. This sprint adds a user-switchable
**Preview mode** -- the actual PDF rendered client-side (pdf.js) with fields
painting in live as the voice session fills them -- alongside the existing linear
form (**Simplified mode**). Users see real progress on the real document (trust,
verification); we gain a visual QA surface where a mispositioned or missing field
is instantly obvious (debugging). The section-navigation UX (a relic of retired
section session resets) gives way to the page as the spatial unit in Preview
mode; sections remain as data grouping (WS wire contract and AI context
unchanged).

## HARD CONSTRAINT: default-off until explicit cutover

Maintainer directive (2026-07-06): **nothing in this sprint may change the
current deployed UI until the maintainer explicitly okays cutover.** All new UI
ships behind an opt-in flag: URL query param `?previewUi=1`, persisted in
sessionStorage for that browser session. Flag off (the default) = zero new UI
elements, no new network fetches (no pdfjs chunk), behavior identical to today
-- safe to merge and deploy at any point. Flag on = the full new UI is
explorable, including on the live demo. The cutover default-flip is a separate,
maintainer-gated change outside this sprint.

## Exit rubric

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | At any point in a session the user can open a "true preview" showing current values filled into the real PDF by the backend (`/api/fill-pdf`), matching what download would produce. | Local stack: fill fields, open preview, download PDF, compare values + placement. |
| 2 | Switching between Simplified and Preview modes at any time loses no field values and does not disrupt an active voice session. | Local stack: voice session active, fill fields, toggle both ways -- values persist, WS stays connected, voice continues. |
| 3 | In Preview mode every filled field with coordinates paints its value at the correct rect on the correct page as it fills, color-coded filled/confirmed/current. | Voice-harness i-90 fill; spot-check painted positions against `form-kits/i-90/i-90-annotated.pdf`. |
| 4 | On voice-model advance the Preview viewport snaps to the new field instantly (no animation); the user can scroll/zoom away freely and a snap-back button returns to the current field. | Local voice session: observe snap, wander, press snap-back. |
| 5 | On a mobile-width viewport the app defaults to Simplified mode with Preview still switchable. | preview_resize mobile (~375px): default Simplified; toggle works. |
| 6 | With the flag off (default) the app's UI and behavior are unchanged from today -- no toggle, no preview button, no new network calls. With `?previewUi=1` the new UI is reachable. | Load app without the param: UI identical to current deploy. Load with param: new UI present. |

## Bead tree

| Bead | Title | Surfaces (writes) | Inherits | Order |
|------|-------|-------------------|----------|-------|
| `polyglot-pdf-js7q` | Epic | -- | all | -- |
| `polyglot-pdf-vfkv` | P0.1: pdf.js foundation + true filled-PDF preview modal (flag-gated) | `frontend/src/pdf-view/` (usePDFDocument, PDFPage, pdfWorker, featureFlag, FilledPreviewModal), `frontend/package.json` | 1, 6 | first (READY) |
| `polyglot-pdf-vxwj` | P1.1: view-mode toggle + shell (flag-gated, mobile defaults Simplified) | `frontend/src/schema-forms/components/SchemaForm.tsx`, `frontend/src/schema-forms/styles/schema-form.css` | 2, 5, 6 | after vfkv (needs the flag helper) |
| `polyglot-pdf-ogrt` | P1.2: live Preview surface -- viewer port + overlays + value painting | `frontend/src/pdf-view/` (PDFViewer, FieldOverlay, pdfCoordinates, valuePainting) | 3 | after vxwj |
| `polyglot-pdf-35t0` | P1.3: snap-to camera + snap-back button | `frontend/src/pdf-view/` (useSnapToField + PDFViewer integration) | 4 | after ogrt |
| `polyglot-pdf-f58l` | P1.4: E2E verification (voice-harness i-90) + `docs/components/pdf-view.md` | docs only | 3, 4, 6 | last |

MECE notes: no two concurrently-workable beads share a write surface (ogrt/35t0
touch `pdf-view/` in distinct files and are strictly ordered); every rubric
criterion is inherited by at least one child; the chain is deliberately linear
-- no parallel execution this sprint (vxwj consumes vfkv's flag helper).

## Reused existing assets (do not rebuild)

- Schema editor viewer stack (port sources, copy-then-diverge):
  `schema-editor/src/components/{PDFViewer,PDFPage,FieldOverlay}.tsx`,
  `schema-editor/src/utils/{pdfCoordinates,pdfWorker}.ts`,
  `schema-editor/src/hooks/usePDFDocument.ts`.
- Coordinate data: every form-kit field carries `pdf_position` (top-left-origin
  PDF points; i-90: 128/132 positioned).
- Endpoints (no backend changes this sprint): `GET /api/form-kits/{kit_id}/pdf`,
  `GET /api/form-kits/{kit_id}/schema`, `POST /api/fill-pdf` (via
  `frontend/src/schema-forms/utils/pdfFiller.ts::fillPDF`).
- State channel: `SchemaFormStateManager` + the `schemaFormStateChange` custom
  event (`frontend/src/schema-forms/state/schemaFormState.ts`); the existing
  `next_field_hint` current-field path in SchemaForm.

## Out of scope (explicit)

Click-to-edit popovers on the PDF; option-level coordinate backfill (schema
model + extractor change -- needed before radio/checkbox choices can display at
their own boxes; Phase-1 fallback paints selected labels at the field rect);
dimming of `show_if`-hidden fields; the desktop default-mode decision; mobile
Preview pinch-zoom polish; accessibility pass; XFA (f1040) render verification;
rendered text translation (voice carries translation today); the cutover
default-flip itself.
