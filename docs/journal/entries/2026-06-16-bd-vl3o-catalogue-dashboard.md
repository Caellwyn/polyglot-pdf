---
date: 2026-06-16
bead: polyglot-pdf-vl3o
title: "D3: catalogue dashboard -- per-form review progress + completion overview"
sprint: 5
tags: [testing]
---

## Trigger

`bd polyglot-pdf-vl3o`, Track D (D3) of sprint 5 / epic 7a9
(`docs/sprint_5_i90-authoring-loop_plan.md`). The maintainer wanted richer
monitoring of the form catalogue: see all forms at a glance -- which have
extractions, which are in-progress vs complete, and what percent of the human
review is done per form. The catalogue (D1, b0pe) listed kits with a status badge
but had no progress signal, and the bead noted that "review progress" was not yet
a defined metric -- so step one was defining it.

## What shipped

**The metric (defined + written down):** per-form "review progress" is the
percentage of fields that are *complete* -- exactly `getCompletionStats(schema).
percentage`, the same field-completion signal the editor shows per field
(green/yellow/red) and the ValidationPanel already aggregates. Reusing that one
definition (rather than inventing a second) means the catalogue % and the
in-editor % can never disagree. A field is complete per `checkFieldComplete`:
has id/type/pdf_field_name, a spoken_name, and non-placeholder help.

**The computation** (`formKitDirectory.ts`):
- `readKitProgress(entry)` -- loads a kit's schema and returns
  `{ reviewPercent, completeFields, totalFields }`; `reviewPercent` is null for a
  kit with no schema (PDF-only, pre-extraction) or an unparseable one.
- `summarizeCatalogue(entries)` -- aggregate counts: total / complete (metadata
  status, the same flag the deploy gate uses) / in-progress (has schema, not
  complete) / awaiting-extraction (no schema).

**The dashboard UI** (`FormCatalogue.tsx`): an aggregate overview header ("N forms
- X complete - Y in progress - Z awaiting extraction") and, on each kit card, a
review progress bar + % (green at 100, yellow below; hidden when there's no
schema). Progress is computed after the list renders (loads each schema) so the
catalogue appears immediately and the bars fill in.

**Exit-criteria scorecard** (both PASS):

1. A defined, computed per-form review-progress metric, shown per form. PASS --
   metric = `getCompletionStats.percentage`, documented in code + here; rendered
   as a per-card bar/% (`FormCatalogue.tsx`); unit-tested
   (`formKitDirectory.progress.test.ts`).
2. At-a-glance overview: each form's status + review %, plus aggregate complete
   vs in-progress counts. PASS -- `summarizeCatalogue` header + per-card status
   badge and %; component-tested (`FormCatalogue.test.tsx`).

**Verification:** 7 new tests (5 metric/aggregate units, 2 dashboard component);
full schema-editor suite 194/194; `tsc --noEmit` clean. Backend suite untouched
(FE-only) and green from prep.

**Fresh-eyes assess (recorded at closeout -- see merge ping for round count).**

## Lessons

- **Reuse the one metric, don't mint a parallel one.** "Review progress" could
  have been a fresh calculation, but the editor already had a field-completion %
  (`getCompletionStats`) shown in the ValidationPanel. Deriving the catalogue
  number from the same function guarantees the two surfaces agree; a second
  definition would have drifted the first time `checkFieldComplete` changed.

## Doc freshness

- FE-only change to the schema editor, which has no tier-2 component doc, so no
  doc to bump for this surface.
- `check_doc_freshness.py` flagged a number of stale docs (auth,
  context-compression, schema-forms, ai-models, confirmation-and-audit,
  hipaa-pii-policy, logging-and-cost, risk-rating, stateless-architecture,
  terminology, validation-delegation), but every one tracks `backend/` or
  `frontend/src/` files changed by OTHER recent work merged to dev -- none track
  `schema-editor/`, which this branch is confined to. They were stale before this
  branch; left as-is per the doc-freshness rule.

## Files touched

- `schema-editor/src/utils/formKitDirectory.ts` -- `KitProgress`,
  `readKitProgress`, `CatalogueSummary`, `summarizeCatalogue`; import
  `getCompletionStats`.
- `schema-editor/src/components/FormCatalogue.tsx` -- per-kit progress state +
  computation after list; aggregate overview header; per-card review bar + %.
- `schema-editor/src/utils/formKitDirectory.progress.test.ts` -- NEW. 5 unit
  tests (aggregate counts, percent from completion, null for no/unparseable
  schema).
- `schema-editor/src/components/FormCatalogue.test.tsx` -- 2 new dashboard tests
  (aggregate overview, per-form %).
- `docs/journal/telemetry/2026-06-16T05-11-51Z-1639d1bb.json` -- carried-forward
  telemetry row for PR #216 (bd bjwy), recorded after that PR had merged; rides
  this PR for completeness.
- `docs/journal/entries/2026-06-16-bd-vl3o-catalogue-dashboard.md` -- THIS entry.
