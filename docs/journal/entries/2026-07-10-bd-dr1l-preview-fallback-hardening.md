---
date: 2026-07-10
bead: polyglot-pdf-dr1l
title: "Preview-fallback hardening: dismiss parity, self-contained styles, reset regression test"
tags: [hotfix, testing]
---

## Trigger

The four cosmetic hardening notes deferred (arm-C convention) from the huer
error-boundary PR's review rounds: the modal-mount fallback lacked the real
modal's dismiss/a11y affordances; no test pinned that a tripped boundary
resets on reopen; no client error telemetry exists; and the fallback's CSS
classes live in the very lazy chunk whose failure triggers the fallback.

## What shipped

- New PdfPreviewFallback component with full dismiss/a11y parity with
  FilledPreviewModal: Escape keydown (effect + cleanup), backdrop click with
  inner-card stopPropagation, and the identical role/aria-modal/aria-label
  surface -- a screen reader hears the same dialog name in both the healthy
  and failed states.
- Fallback styles are inline and self-contained (both the modal fallback
  and the PreviewPane mount's inline notice): pdf-view.css is imported only
  by the LAZY chunk, so it is exactly unavailable when a fallback renders.
  Chunk classNames kept as secondary hooks.
- Regression test pinning reset-by-remount: recovery from a tripped
  boundary depends on the SchemaForm conditionals unmounting it; a refactor
  sharing one boundary instance across opens would silently break recovery.
- Telemetry (nit 3): confirmed NO client error sink exists anywhere in
  frontend/src (no Sentry, no logging endpoint, no window.onerror).
  Deliberately NOT invented inside this nits PR -- a sink is a new
  operational surface touching the PII policy and the stateless-backend
  invariant, so it was filed as an assess bead for the maintainer
  (polyglot-pdf-w4at, "assess: client-side error telemetry sink").
- Implementation delegated to a Sonnet subagent; diff reviewed by the
  orchestrator.
- 6 new tests; schema-forms + pdf-view suites 25 files / 601 tests green;
  tsc clean.
- Fresh-eyes triage: (filled at closeout -- see below)

## Lessons

- CSS that ships inside a lazy chunk cannot style that chunk's failure
  path. Any error fallback must carry its own styles (or main-bundle CSS).

## Doc freshness

- No component doc tracks these surfaces; nothing to bump. Pre-existing
  stale standards docs (tracking files this branch did not touch) reviewed
  and left per the "already stale before you" rule.

## Files touched

- frontend/src/schema-forms/components/PdfPreviewFallback.tsx (new, + .test.tsx)
- frontend/src/schema-forms/components/SchemaForm.tsx
- frontend/src/schema-forms/components/PdfViewErrorBoundary.test.tsx
- docs/journal/entries/2026-07-10-bd-dr1l-preview-fallback-hardening.md
