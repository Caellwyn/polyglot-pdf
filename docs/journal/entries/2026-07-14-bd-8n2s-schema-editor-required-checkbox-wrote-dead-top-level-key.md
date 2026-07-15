---
date: 2026-07-14
bead: polyglot-pdf-8n2s
title: "schema-editor 'Required' checkbox wrote a dead top-level required key; migrated the editor to validation.required"
tags: [bugfix, schema-editor, testing]
---

## Trigger

Fast-follow to bd polyglot-pdf-a1ql. That bead migrated the runtime + the i-90 kit
to the canonical `validation.required` shape and added a `required-top-level`
schema_lint ERROR so a drifted kit could not publish. But the schema-editor's own
authoring UI still wrote the OLD shape: the FieldEditor 'Required' checkbox called
`updateField({ required: e.target.checked })`, targeting a top-level
`FormField.required` that no runtime consumer reads.

The bug was invisible in the editor because the editor's own preview
(`conditionalVisibility.isFieldRequired`) read the SAME dead top-level key -- so a
maintainer checking 'Required' saw it "work" in the live preview (false
confidence), then saved a kit where `validation.required` was never set, then hit
the new lint ERROR at Mark-complete time with no UI control that set the field the
lint wanted. This reproduced, in the authoring tool, the exact bug class a1ql had
just fixed at runtime.

## What shipped

Chose option (a) from the bead -- migrate the editor's shape rather than add a
save-time translation -- because it removes the two-shape split entirely instead of
papering over it.

- `schema-editor/src/types/schema.ts`: removed `required: boolean` from `FormField`
  and added `required?: boolean` to `ValidationRules` (mirroring the backend
  `ValidationRules.required: Optional[bool]`).
- `FieldEditor.tsx`: the checkbox now reads `field.validation?.required` and writes
  `{ validation: { ...field.validation, required } }` -- the same spread pattern the
  sibling validation sub-fields (pattern, format_preset, min/max_length) already
  use, so other validation keys are preserved.
- `conditionalVisibility.ts`: `isFieldRequired` now reads `validation.required`,
  making the editor's preview logic structurally identical to the runtime frontend
  `isFieldRequired` (this removes a pre-existing divergence rather than adding one).
- `fieldGrouping.ts`: the `ungroupField` no-stash fallback reconstruction copies
  `validation: field.validation` instead of `required: field.required`, so a split
  field inherits the whole validation object (strictly more correct).
- Stripped inert `required: false` default noise from ~17 test fixtures (every
  stripped value was `false`; none was asserted on).

## Why the type-removal approach is safe

Removing a NON-optional field from `FormField` turns every stale writer/reader into
a compile error. `tsc --noEmit` is clean, which proves no schema-editor code path
still reads or writes a top-level `required`. The save paths
(`remoteKitStore.saveRemoteSchema`, the File System Access save, `schemaLoader`) all
serialize via `JSON.stringify(stripEditorState(schema))`, and `stripEditorState`
only deletes the internal stash key -- it never re-emits a top-level `required`.

Load asymmetry was considered and ruled a non-issue: `loadSchema` is a raw
`response.json()` with no field mapping, so a legacy kit carrying a top-level
`required: true` would render unchecked -- but every editor-loadable kit already
carries `required: false` on all fields (the runtime `form-kits/` are already fully
on `validation.required`), so there is no `true` value to drop. A hypothetical
`required: true` kit is already un-publishable via the a1ql lint (pre-existing
broken state, not introduced here).

## Tests

- `FieldEditor.required.test.tsx` (new): drives the checkbox, threads the patch back
  into the schema, and runs the field through the ACTUAL save serialization
  (`JSON.stringify(stripEditorState(schema))`), asserting `validation.required` is
  true and no top-level `required` key survives (exit criterion 1's "actual save
  path, not just in-memory shape").
- `fieldGrouping.test.ts` (added test): the `ungroupField` no-stash fallback path --
  the exact line this bead changed -- now pins that `validation.required` propagates
  onto every reconstructed field with no top-level key.

Both new tests were mutation-verified by the outer review (revert the fix -> the
tests fail on-point -> restore -> green). Full schema-editor suite: 709 tests, 43
files, green; backend schema_lint: 59 tests, green.
