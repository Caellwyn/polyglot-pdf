---
date: 2026-07-06
bead: polyglot-pdf-vfkv
title: "P0.1: pdf.js foundation + true filled-PDF preview modal (flag-gated)"
sprint: 8
tags: [conventions, testing]
---

## Trigger

First bead of the preview-mode epic (`polyglot-pdf-js7q`, sprint 8 --
`docs/sprint_8_preview-mode_plan.md`). The maintainer wants the app's visible
surface to evolve toward an interactive rendering of the actual PDF ("Preview
mode") alongside the existing linear form ("Simplified mode"), with a HARD
default-off gate: nothing may change the deployed UI until an explicit cutover
okay. Phase 0 delivers the cheapest trust win first -- a "true preview" modal
showing the user's current values filled into the real PDF by the backend --
while establishing the pdf.js foundation the live Preview mode (P1.x beads)
builds on.

## What shipped

- **`frontend/src/pdf-view/`** -- new module, ported copy-then-diverge from the
  schema editor: `usePDFDocument` (pdf.js loading hook, StrictMode-safe),
  `PDFPage` (canvas page renderer; editor's Tailwind classes swapped for
  `pdf-view.css` since the main app has no Tailwind), `pdfWorker` (worker
  setup), plus the new `featureFlag.ts` and `FilledPreviewModal.tsx`.
- **Feature flag** (`isPreviewUiEnabled()`): URL param `?previewUi=1` opts in,
  persisted in sessionStorage for the browser session; `?previewUi=0` opts out;
  fail-closed on storage errors. Every UI surface of the epic renders only
  behind it.
- **FilledPreviewModal**: POSTs current values through the SAME `fillPDF()` /
  `/api/fill-pdf` path the download/print buttons use and renders the returned
  bytes with pdf.js -- the preview IS PyMuPDF's own output, so it matches a
  download exactly (byte-identity across calls does NOT hold -- PDF generation
  embeds timestamps/IDs -- but content does). Fit-width zoom on first page,
  zoom controls, all pages in a scroll column, Escape/click-away close.
- **Chunking**: the modal is a `React.lazy` boundary; pdfjs-dist (408 kB) and
  the worker (1.4 MB) live only in that chunk. Verified the production main
  chunk has zero pdfjs references -- flag-off users fetch nothing new.
- **pdfjs-dist 4.10.38** (not the editor's 4.0.379): 4.0.379's modern AND
  legacy builds carry a top-level await that the app's es2020 Vite target
  rejects at build time; 4.10.38's legacy build is TLA-free and also drops the
  heavy optional native-canvas dep (lockfile adds only pdfjs-dist +
  per-platform `@napi-rs/canvas` stubs, the esbuild-style pattern CI handles).
- Sprint 8 plan doc + INDEX row bundled here (the epic's `plan:` pointer
  target; a docs-only PR can close no bead, so bundling was the right shape).

Verified on the local stack (Chrome-driven): flag-off = no button, no modal, no
pdfjs fetch; flag-on = preview renders the real I-90 (7 pages) with the test
values visible at their printed positions on page 1; voice session stayed
connected across modal open/close; 767 frontend tests pass; `build:schema`
green.

Fresh-eyes assess outcome: (folded in after the Step-5.5 loop below).

## Lessons

- **pdf.js 4.x + Vite es2020: use a TLA-free version and the `?url` worker
  import.** Early 4.x (incl. 4.0.379) uses top-level await even in the legacy
  build, which any `build.target` below es2022 rejects; later 4.x (4.10.38)
  removed it. And in dev, `new URL('pdfjs-dist/...worker...', import.meta.url)`
  403s under the worktree node_modules junction (Vite fs allowlist) -- the
  `?url` asset import serves through the module pipeline and works in both dev
  and prod.
- **A lockfile diff is CI-safe when it is purely additive and platform packages
  are all enumerated** (the `@napi-rs/canvas-*` per-platform stubs mirror the
  esbuild pattern) -- checked against the schema editor's lock, whose identical
  shape already passes CI.
- **Two dev backends can fight over port 8000 silently**: an orphaned
  uvicorn multiprocessing child (parent killed) kept serving stale code with a
  500ing `/api/form-kits` while the new backend failed to bind. Symptom:
  "healthy" `/health` + broken API. `wmic process ... get commandline` finds
  the orphan; kill the CHILD, not just the parent PID.

## Doc freshness

New tier-2 doc for the pdf-view surface is deliberately deferred to the epic's
P1.4 bead (`polyglot-pdf-f58l` -- `docs/components/pdf-view.md`), which lands
after the live Preview surface exists; a component doc for a modal-only module
would be churn. No existing tier-1/2 doc tracks `frontend/src/pdf-view/` yet.
`docs/INDEX.md` gained the sprint-8 active-plan row.

## Files touched

- `frontend/src/pdf-view/` (new): `featureFlag.ts` (+ test), `pdfWorker.ts`,
  `usePDFDocument.ts`, `PDFPage.tsx`, `FilledPreviewModal.tsx`, `pdf-view.css`
- `frontend/src/schema-forms/components/SchemaForm.tsx` (flag-gated button +
  lazy modal mount)
- `frontend/package.json` / `package-lock.json` (pdfjs-dist 4.10.38)
- `docs/sprint_8_preview-mode_plan.md` (new), `docs/INDEX.md` (plan row)
- `docs/journal/entries/2026-07-06-bd-vfkv-pdfjs-foundation-preview-modal.md`
  (this entry)
