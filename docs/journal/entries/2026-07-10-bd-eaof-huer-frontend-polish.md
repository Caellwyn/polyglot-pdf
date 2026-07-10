---
date: 2026-07-10
bead: polyglot-pdf-eaof
title: "Dynamic required '*' for require_if fields + error boundary around the lazy pdf-view chunks"
tags: [hotfix, testing]
---

## Trigger

Two small deferred frontend findings bundled into one PR:

- polyglot-pdf-eaof (fresh-eyes finding on the c7st+4dxt require_if PR): a
  require_if-required field is functionally required at the section gate and
  gets a "Skip for now" button, but its label showed no '*' -- the asterisk
  came from static validation.required only.
- polyglot-pdf-huer (deferred robustness nit from the PR #336 fallback
  review): SchemaForm's lazy pdf-view mounts had Suspense but no error
  boundary, so a failed pdfjs chunk fetch (network blip, stale deploy hash)
  crashed the whole SchemaForm render including the live voice-session UI.
  Only reachable flag-on (previewUi=1).

## What shipped

- eaof: SectionRenderer's already-computed isFieldRequired result now flows
  as an optional `required` prop through FieldRenderer into all six field
  components; each renders '*' from `(required ?? validation.required)`.
  FieldEditPopover (pdf-view) intentionally left unchanged -- it omits the
  prop, so it keeps the static behavior.
- huer: new generic PdfViewErrorBoundary (class component) wraps BOTH lazy
  mounts, outside the Suspense: PreviewPane gets an inline notice fallback;
  FilledPreviewModal gets a dismissible overlay fallback wired to the same
  setShowPDFPreview(false) close path. The boundary unmounts with its
  conditional, so re-opening the preview mounts a fresh (untripped)
  instance. Kept generic for future pdf-view surfaces (epic js7q).
- Implementation delegated to a Sonnet subagent (model-tiering: execution
  tier), diff reviewed by the orchestrator before commit.
- Tests: asterisk override/fallback/static-fallback cases (TextField,
  RadioField), SectionRenderer require_if trigger met/unmet, and
  PdfViewErrorBoundary tests including a rejecting React.lazy import inside
  Suspense. Full schema-forms + pdf-view vitest run: 24 files / 595 tests
  green; tsc --noEmit clean.
- Fresh-eyes triage: (filled at closeout -- see below)

## Lessons

- When a renderer already computes the correct dynamic state for one
  affordance (the skip button), a sibling affordance (the '*') silently
  reading the static config is the inconsistency to look for.

## Doc freshness

- No component doc tracks these presentational details; nothing to bump.
  Pre-existing stale standards docs (tracking files this branch did not
  touch) reviewed and left per the "already stale before you" rule.

## Files touched

- frontend/src/schema-forms/components/FieldRenderer.tsx
- frontend/src/schema-forms/components/SectionRenderer.tsx (+ .test.tsx)
- frontend/src/schema-forms/components/SchemaForm.tsx
- frontend/src/schema-forms/components/PdfViewErrorBoundary.tsx (new, + .test.tsx)
- frontend/src/schema-forms/components/fields/TextField.tsx (+ .test.tsx)
- frontend/src/schema-forms/components/fields/TextAreaField.tsx
- frontend/src/schema-forms/components/fields/RadioField.tsx (+ .test.tsx)
- frontend/src/schema-forms/components/fields/CheckboxField.tsx
- frontend/src/schema-forms/components/fields/DateField.tsx
- frontend/src/schema-forms/components/fields/SelectField.tsx
- docs/journal/entries/2026-07-10-bd-eaof-huer-frontend-polish.md
