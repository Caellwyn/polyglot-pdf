---
date: 2026-09-01
bead: polyglot-pdf-8ewxs
title: "types(resume): fieldValues declares the full union now, matching what the backend actually returns"
tags: [frontend]
---

## Trigger

`ResumePayload.fieldValues` and `ResumeResult.fieldValues` were both
declared `Record<string, string>`, but `/api/resume-form` actually
returns `Dict[str, str | list[str] | bool]` -- a checkbox_group answer
comes back as a list, and a standalone checkbox restores as a real
Python `bool` (the client's own `True`, not the PDF's on-state).
`tsc` never caught this because the value enters through
`await response.json()` (typed `any`), so the declared type was never
checked against reality.

Not a runtime bug -- traced the full path: `FieldValue.value` is
widened by `as unknown` reads, `unwrapFieldValue` returns arrays as-is,
`CheckboxField`'s group branch already does `Array.isArray`, and
`validateOptionMembership` already handles arrays. A checkbox_group
answer already round-tripped correctly through a resume. The risk was
purely that a future reader trusting the declared type (`payload.
fieldValues[id].trim()`) would get a green `tsc` and a runtime crash on
a resumed multi-select.

## Fix

Widened the three types that were understating reality:
- `ResumeResult.fieldValues` (`ResumeUpload.tsx`)
- `ResumePayload.fieldValues` (`applyResume.ts`)
- `FieldValue.value` (`types/schema.ts`) -- already admitted `boolean`;
  needed only `string[]` added, to satisfy exit criterion 1 ("tsc still
  passes"): `applyResume.ts` assigns the raw resume value directly into
  a `FieldValue`, so widening only the two Resume-specific types left a
  real `tsc` error at the assignment site.

`FieldValue` is used across 19 files; ran a full `tsc --noEmit` after
the widening and it passed clean everywhere -- the type change is purely
additive (every real consumer already handled arrays defensively at
runtime, confirming the bead's own "not a runtime bug" analysis).

## A real gap the Opus cross-surface review caught

My first pass only widened the two Resume types to `string | string[]`,
missing that the SAME backend route also returns a plain Python `bool`
for a standalone checkbox (`pdf_fill_routes.py`: "restores as the
client's own TRUE, not the PDF's on-state"). The review proved this with
a direct `tsc` probe (`{fieldValues: {agrees: true}, ...}` failed
`TS2322` against my first-draft union), and separately caught that my
new code comments stated only the two-shape union, contradicting
`docs/components/pdf-filling.md`'s own three-shape table (the doc was
right, my comments were wrong). Both fixed in this same diff: the union
is now `string | string[] | boolean`, and the comments in both files now
match the doc's three-shape table exactly. Added a matching new test
(a standalone checkbox answer survives as a real `boolean`, not a
stringified `"true"`).

## Testing

Two new tests in `applyResume.test.ts`:
- a checkbox_group answer (array) in the same payload as a scalar
  answer survives the merge as an array (`toEqual`, `Array.isArray`),
  with the scalar sibling unaffected;
- a standalone checkbox answer (boolean) survives as a real `boolean`
  (`typeof === 'boolean'`), not a stringified `"true"`.

Mutation-verified per exit criterion 2's own suggestion (simulate
"collapsing the group to a scalar"): mutated `applyResume.ts` to
`raw.join(',')` an array value, confirmed exactly the array test
reddens (the collapsed string fails the array equality check), all
other tests stay green. Restored.

Full frontend suite: 1880 tests. Repeated runs (including one by the
Opus cross-surface reviewer) varied between 0 and 3 failures per run,
every single one confined to the already-tracked pre-existing flaky test
(`SchemaForm.previewEdit.test.tsx`, bd `polyglot-pdf-x95xl`) -- never to
any file this diff touches. The exact count is inherently non-reproducible
for a timing flake; the qualitative conclusion (unrelated to this change)
held up under independent re-runs.
