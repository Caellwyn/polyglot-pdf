---
date: 2026-07-12
bead: polyglot-pdf-w7rg
title: "FieldEditor Section dropdown moves a field between section.fields[] arrays atomically (no more section_id-vs-listing drift)"
tags: [schema-editor, form-kits, testing]
---

## Trigger

A Sprint 10 follow-on bug (filed during the derived-divisions work). The schema
editor's FieldEditor "Section" dropdown patched only `field.section_id`; it never
updated the `section.fields[]` arrays. Since FieldList renders each section from
`section.fields[]` (not from `field.section_id`), a field moved via the dropdown
kept rendering under its OLD section and never appeared under the new one, until
some later op happened to reconcile it.

## Why it mattered

The editor keeps two representations of the same fact -- `section.fields[]` (the
listing) and `field.section_id` (the pointer) -- and the whole editor + backend
assume they stay in lockstep:

- FieldList renders from the listing; the dropdown drifted the pointer away, so
  the move was invisible in the UI.
- The section remove/merge ops (`sectionOps.removeSection`) trust
  `field.section_id` as the authoritative moved-set while healing the listing; a
  drifted schema could leave a field double-listed across two sections or
  stranded in none once a later op ran.
- The To-review amber highlight (FieldList) keys off the listing while the
  backend `to-review-pending` publish-lint gate and the client mirror key off
  the pointer -- so a drifted field could make the highlight silently disagree
  with the gate (gate blocks publish; nothing highlighted to explain why).

## Fix

New pure helper `moveFieldToSection(fields, sections, parts, fieldId, destId)`
in `sectionOps.ts`: sets `field.section_id` AND moves the id between the
`section.fields[]` arrays in one `{fields, sections}` patch. It strips the id
from EVERY section's listing first (defensive against pre-existing drift where a
field is double-listed), then appends it once to the destination -- so a move
also HEALS prior drift for the moved field. An already-consistent move returns
the inputs unchanged (no spurious undo step). `null` destination ("No section")
clears the pointer and every listing.

The FieldEditor "Section" dropdown routes through it and commits atomically via
the existing `onUpdateFields(fields, sections)` (one undo step, mirroring the
option-rename retarget path); it falls back to the single-field
`updateField({section_id})` only when `onUpdateFields` is absent. Parts are
unchanged by a within-schema field move, so the helper returns them untouched.
The Section `<select>` gained an `aria-label="Section"` (matching the file's
other selects) so the behavior is testable.

## Verification

- New `moveFieldToSection` unit tests (sectionOps.test.ts): both listings +
  section_id update; "No section" clears everything; already-consistent is a
  no-op (same references); pre-existing double-listing heals to one; and a
  FieldEditor-style move CHAINED into `removeSection` neither drops nor
  duplicates a field (exit criterion 2).
- New FieldEditor component tests (FieldEditor.section.test.tsx): rendering the
  dropdown and firing a change commits both arrays + section_id via
  onUpdateFields (exit criterion 1); "No section" clears; and the
  onUpdateFields-absent fallback still patches section_id.
- `tsc --noEmit` clean; full schema-editor vitest green (703 tests; the targeted
  two-file run is 25/25). The full-run "Timeout starting forks runner" lines are
  a known worktree-junction forks-startup artifact, not test failures (CI runs
  from the real checkout).

## Files touched

- `schema-editor/src/utils/sectionOps.ts` (moveFieldToSection helper)
- `schema-editor/src/components/FieldEditor.tsx` (Section dropdown wiring + aria-label)
- `schema-editor/src/utils/sectionOps.test.ts` (helper tests)
- `schema-editor/src/components/FieldEditor.section.test.tsx` (component tests)
