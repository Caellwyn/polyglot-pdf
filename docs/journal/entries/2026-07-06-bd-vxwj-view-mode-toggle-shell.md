---
date: 2026-07-06
bead: polyglot-pdf-vxwj
title: "P1.1: view-mode toggle + Preview pane shell (flag-gated)"
sprint: 8
tags: [conventions, testing]
---

## Trigger

Second bead of the preview-mode epic (`polyglot-pdf-js7q`, sprint 8 --
`docs/sprint_8_preview-mode_plan.md`), building on the P0.1 pdf.js foundation
merged in PR #336. The epic's design is dual user-switchable view modes over
the same client state: "Simplified" (the classic linear form) and "Preview"
(the PDF surface), everything behind the `?previewUi=1` opt-in until the
maintainer's explicit cutover.

## What shipped

- **View-mode state** (`frontend/src/pdf-view/viewMode.ts` + test): a
  `'simplified' | 'preview'` mode persisted per browser session in
  sessionStorage, deliberately OUTSIDE `SchemaFormState` (purely
  presentational; must never reach the WS handshake). Stored choice is honored
  only when the preview flag is on.
- **Flag-gated toggle** in `SchemaForm.tsx`: a two-button segmented control
  (role=tablist) above the form; live-switchable at any time. Default mode is
  Simplified at EVERY width -- the epic's phase-3 bead owns the desktop
  default decision -- which also satisfies the mobile-defaults-Simplified
  criterion by construction.
- **Session-safe container split**: the voice overlays and the
  ConnectionManager were already siblings of the form element; the view switch
  wraps only the form/pane, so toggling never remounts the overlay or touches
  the WS session. Verified live: toggling both ways kept the session
  "connected", no timeout modal, field values intact.
- **PreviewPane** (`frontend/src/pdf-view/PreviewPane.tsx`, lazy): the P1.1
  placeholder surface -- renders the blank form PDF (fit-width, page labels)
  with a banner pointing users at the true filled preview; the live overlays,
  value painting, and snap-to camera land in P1.2/P1.3 (`polyglot-pdf-ogrt`,
  `polyglot-pdf-35t0`) on this mount point.
- **Chunking**: with two lazy consumers (modal + pane), Rollup hoists pdfjs
  into a shared lazy `pdf-view-*.js` chunk. Verified: main chunk has zero
  pdfjs references and `dist/index.html` does not modulepreload the pdf-view
  chunk -- the flag-off bundle is unchanged.
- Rides along: the PR #336 closeout's telemetry row (that PR merged before the
  row could be committed).

Fresh-eyes assess outcome: (folded in after the Step-5.5 loop).

## Lessons

- **A second lazy consumer changes the chunk graph**: what was "pdfjs lives in
  the FilledPreviewModal chunk" silently became "pdfjs lives in a shared
  chunk both lazy entries import". The gating invariant survived, but only
  because the shared chunk is itself lazy -- re-verify the main chunk and the
  modulepreload list whenever a new consumer of a gated heavy dep appears.
- **Chrome MCP `resize_window` can silently not resize** (managed/maximized
  window: reports success, `innerWidth` unchanged). Simulating narrow width
  through the app's own resize handler (`Object.defineProperty(window,
  'innerWidth', ...)` + `dispatchEvent(new Event('resize'))`) exercises the
  real breakpoint logic instead.

## Doc freshness

- `docs/components/schema-forms.md` BUMPED again: SchemaForm now hosts the
  flag-gated view-mode toggle and conditionally renders the lazy PreviewPane.
- Other prep-flagged STALE docs track backend files this branch did not touch
  (same pre-existing worktree-mtime staleness as PR #336's closeout) -- left.
- `docs/components/pdf-view.md` still lands in P1.4 (`polyglot-pdf-f58l`).

## Files touched

- `frontend/src/pdf-view/viewMode.ts` (+ `viewMode.test.ts`),
  `frontend/src/pdf-view/PreviewPane.tsx`, `frontend/src/pdf-view/pdf-view.css`
- `frontend/src/schema-forms/components/SchemaForm.tsx`,
  `frontend/src/schema-forms/styles/schema-form.css`
- `docs/components/schema-forms.md`, this journal entry,
  `docs/journal/telemetry/2026-07-06T22-41-10Z-496b876e.json` (ride-along)
