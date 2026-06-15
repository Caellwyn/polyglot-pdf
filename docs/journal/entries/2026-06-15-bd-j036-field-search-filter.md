---
date: 2026-06-15
bead: polyglot-pdf-j036
title: "A3: Field search/filter in the field list"
sprint: 5
tags: [testing]
---

## Trigger

`bd polyglot-pdf-j036`, Track A (A3) of sprint 5 / epic 7a9
(`docs/sprint_5_i90-authoring-loop_plan.md`, crit 4: "joyful editing -- the
universal wins"). Survey gap: forms with many fields had no way to find a field
by name in the schema editor's field list -- you scrolled the whole grouped tree
looking for an id / spoken_name / pdf_field_name. The plan's crit-4 drive script
is "search a field by name, edit it, undo, then add a controls_fields
relationship"; A3 supplies the search half.

## What shipped

A search/filter box at the top of `FieldList.tsx`:

- A text input (search icon + clear "x" button) above the scrollable tree.
- Case-insensitive substring filter matching a field's `id`, `spoken_name`, OR
  `pdf_field_name` (the three names a human would type).
- Section grouping is preserved while filtering: matching fields stay under their
  section headers, sections with zero matches are hidden, and matching sections
  auto-expand so results are always visible.
- An empty / whitespace query restores the full grouped list (the second exit
  criterion); the clear button does the same in one click.
- A "No fields match ..." message when nothing matches.
- Selecting a filtered result uses the existing `onSelectField`, so the PDF +
  editor sync is unchanged -- no new selection wiring.

**Exit-criteria scorecard** (both PASS):

1. Type part of a field name -> list filters to matches; selecting one selects it
   across panels. PASS -- `matchesQuery` over id/spoken_name/pdf_field_name
   (FieldList.tsx); selection delegates to the unchanged `onSelectField`.
2. Clearing the search restores the full grouped list. PASS -- empty query makes
   `matchesQuery` return true for all; clear button resets `searchQuery`.

**Verification:** new `FieldList.search.test.tsx` (6 tests: filter-by-id,
-by-spoken_name, -by-pdf_field_name, no-results, clear-restores, selection) all
pass; full schema-editor suite 166/166; `tsc --noEmit` clean. The backend suite
(prep Step 0) was already green (349 passed) and untouched by this FE-only change.

**Fresh-eyes assess:** (recorded at closeout -- see merge ping for round count).

## Lessons

- **A "force-expand while filtering" override is simpler than syncing expansion
  state.** Rather than mutating `expandedSections` when a query is present, the
  render reads `isExpanded = isFiltering || expandedSections.has(id)`. Filtering
  is a transient view, so deriving expansion from the query each render (instead
  of writing it into state) avoids a stale-state class of bug.

## Doc freshness

- FE-only change to the schema editor, which has no tier-2 component doc (noted
  also in the b0pe entry, 2026-06-15), so no doc to bump for this surface.
- `check_doc_freshness.py` flagged 6 stale docs
  (context-compression, tool-call-flow, websocket-routing,
  confirmation-and-audit, stateless-architecture), but every one tracks BACKEND
  files (`form_filling_service.py`, `callback_handler.py`,
  `request_coordinator.py`) or `frontend/src/shared/connection.ts` -- none track
  `schema-editor/`. They were stale before this branch and this branch does not
  touch their tracked files; left as-is per the doc-freshness rule.

## Files touched

- `schema-editor/src/components/FieldList.tsx` -- search input + `searchQuery`
  state; `matchesQuery` predicate; filtered `sectionedFields`; hide-empty +
  auto-expand-while-filtering section render; no-results message.
- `schema-editor/src/components/FieldList.search.test.tsx` -- NEW. 6 tests for the
  filter behavior + both exit criteria.
- `docs/journal/entries/2026-06-15-bd-j036-field-search-filter.md` -- THIS entry.
