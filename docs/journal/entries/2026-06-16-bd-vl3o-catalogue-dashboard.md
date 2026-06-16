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

**Verification:** 11 new tests (8 metric/aggregate units, 3 dashboard component);
full schema-editor suite 198/198; `tsc --noEmit` clean. Backend suite untouched
(FE-only) and green from prep.

**Fresh-eyes assess (Sonnet, arm B picker, 2 rounds to NO-GAPS):** both rubric
criteria PASS; round 1 found four in-scope robustness gaps, all adopted:
(1) a structurally-malformed-but-parseable schema (no `fields` array) threw inside
`getCompletionStats`, which would reject the catalogue-wide `Promise.all` and wipe
every progress bar -- wrapped `readKitProgress`'s stats call in try/catch ->
null; (2) `summarizeCatalogue`'s complete-vs-no-schema ordering for a
`status:complete`+`hasSchema:false` kit (initially flipped to status-first, then
CORRECTED below by Codex); (3) a stale-folder race where a slow progress load from
a prior folder could overwrite the current one -- added a monotonic refresh token
guard; (4) clarified/locked that a 0-field schema reports 0% (bar renders),
distinct from a no-schema kit (no bar). Round 2 returned NO-GAPS.

**Codex outer review (PR #224):** round 1 raised three P1s, all adopted as
blockers: (a) it CORRECTED fresh-eyes gap (2) -- `deploy-all.sh` skips a
schema-less kit BEFORE the complete check, so a complete-marked kit with no schema
is NOT deployable and must count as "awaiting extraction", not complete. Codex's
deploy-flow evidence overrode fresh-eyes' metadata-only reasoning; reverted to
hasSchema-first ordering. (b) the catalogue % went stale after an in-editor
edit/save (only computed on folder-scan) -- added a `liveProgress` prop fed from
App's in-memory schema (same `getCompletionStats`) so the open kit's bar tracks
unsaved edits, preserving the "can't disagree with the in-editor %" guarantee.
(c) a present-but-unreadable schema collapsed into the same null as no-schema --
added a `schemaError` flag so the card shows "Schema present but unreadable"
instead of silently hiding the row.
Round 2 caught three follow-ons of those fixes, all adopted: (d) `liveProgress`
matched the open kit by bare id, so after a Change-folder a same-named kit in the
new folder could inherit the old form's % -- added an `onFolderChange` callback
that clears the open-kit state before the new folder loads; (e) the card title's
complete/total hover counts still came from the disk scan while `pct` was
live-overridden -- `liveProgress` now carries `complete`/`total` so the bar and
its detail share one source; (f) the malformed-schema guard relied on
`getCompletionStats` throwing, but an iterable-but-invalid `fields` (e.g.
`"abc"`) would not throw and reported a bogus % -- added an explicit
`Array.isArray(schema.fields)` check that surfaces `schemaError` instead.

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
  computation after list (monotonic refresh-token guard vs the stale-folder
  race); aggregate overview header; per-card review bar + %; `liveProgress` prop
  override for the open kit; "schema present but unreadable" notice.
- `schema-editor/src/App.tsx` -- passes `liveProgress` (the open kit's live
  in-memory review %) to FormCatalogue so the bar tracks unsaved edits.
- `schema-editor/src/utils/formKitDirectory.ts` adds a `schemaError` flag to
  KitProgress (present-but-broken vs no-schema).
- `schema-editor/src/utils/formKitDirectory.progress.test.ts` -- NEW. 8 unit
  tests (aggregate counts incl. complete-without-schema, percent from completion,
  null for no/unparseable/malformed schema, 0% for empty schema).
- `schema-editor/src/components/FormCatalogue.test.tsx` -- 3 new dashboard tests
  (aggregate overview, per-form %, 0%-bar-vs-no-bar distinction).
- `docs/journal/telemetry/2026-06-16T05-11-51Z-1639d1bb.json` -- carried-forward
  telemetry row for PR #216 (bd bjwy), recorded after that PR had merged; rides
  this PR for completeness.
- `docs/journal/entries/2026-06-16-bd-vl3o-catalogue-dashboard.md` -- THIS entry.
