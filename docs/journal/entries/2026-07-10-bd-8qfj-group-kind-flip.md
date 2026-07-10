---
date: 2026-07-10
bead: polyglot-pdf-8qfj
title: "fix(schema-editor): let an existing consolidated group flip checkbox_group <-> radio in place"
tags: [hotfix, testing]
---

## Trigger

User-reported editor bug: on W-7, "Reason for submitting Form W-7" was extracted
as a `checkbox_group` but should be a radio (choose exactly one), and the editor
offered no way to change it -- the Field Type dropdown was greyed out with the
hint "Group type is set by Merge (several = checkbox group, exactly one = radio)
and reversed by Ungroup."

Root cause: the Field Type picker is deliberately read-only for any field that
carries `options[]` (a "group"), and the only sanctioned way to SET a group's
kind was Merge -- which offers the radio-vs-checkbox_group choice ONLY when
combining two or more loose widgets. Once a group exists, its boxes are already
consolidated, so Merge is not offered, and the picker is disabled. That left a
group extraction produced as the wrong kind with NO reachable path to the other
kind. The maintainer's ask was explicitly to fix the editor, not just this form.

## What shipped

An in-place group-kind toggle. Flipping `checkbox_group <-> radio` is safe: the
two kinds share identical `options[]`, slugs, and per-option `pdf_field_name`;
the only runtime-meaningful difference is single- vs multi-select, which changes
how a dependent field references a selected option (membership
`includes`/`not_includes` for a checkbox_group vs equality `equals`/`not_equals`
for a radio). That is exactly the `membership` distinction the existing
merge/ungroup rewrite logic already models.

- `schema-editor/src/utils/fieldGrouping.ts`: new pure `changeGroupKind(schema,
  fieldId, kind)` -- sets `field.type` and rewrites every dependent's
  `show_if`/`require_if` atom that selects one of THIS group's option slugs
  across the membership boundary, walking both the legacy single condition and
  the v2 composite (`all_of`/`any_of`/`none_of`) shape. Whole-group operators
  (`is_checked`/`is_empty`, no option value) are kind-agnostic and left
  untouched; unrelated atoms (other fields) are untouched. No-op (same schema
  reference) when the field is not a group or is already the requested kind.
- `schema-editor/src/components/FieldEditor.tsx`: replaced the dead "reversed by
  Ungroup" hint with a live "Group behaves as" selector (author-tier). The base
  Field Type picker stays disabled for groups (raw-switching a group to a
  non-group type would strand the options).
- `schema-editor/src/App.tsx`: `handleChangeGroupKind` wires the flip through the
  schema commit/undo history; the group keeps its id, so the selection survives.

**Fresh-eyes gap (adopted, fixed inline).** The Sonnet assessor found that the
two kinds are NOT symmetric against the backend model. A *shared-name radio* (a
field-level `pdf_field_name` plus options carrying `pdf_on_value` but no
per-option `pdf_field_name` -- the shape extraction emits for a shared-name
AcroForm radio) has NO valid `checkbox_group` form: `form_models.py` forbids a
field-level `pdf_field_name` on a checkbox_group and requires every option to
carry its own `pdf_field_name`. My first cut flipped `type` unconditionally, so
that one direction would silently mint an un-promotable schema. Fixed by adding
`canChangeGroupKind(field, kind)`: flipping TO radio is always valid; flipping TO
checkbox_group is allowed only when there is no field-level `pdf_field_name` and
every option carries its own `pdf_field_name`. `changeGroupKind` now refuses an
invalid flip (no-op), and the FieldEditor disables the checkbox_group choice with
an explanation ("This group shares one PDF widget across its options, so it can
only be a radio...") when the target would be invalid.

**Second fresh-eyes gap (Opus round, adopted, fixed inline).** The Opus closing
round found a related asymmetry: a radio trigger can carry a list-valued
`in`/`not_in` dependent (value = an array of option slugs; the editor's
ConditionBuilder offers `in`/`not_in` on a radio), but a checkbox_group trigger
cannot -- the backend scopes `in`/`not_in` to scalar triggers and requires
membership on a checkbox_group. My first cut only handled the scalar quartet
(`equals`/`not_equals`/`includes`/`not_includes`), so a radio -> checkbox_group
flip stranded an `in`/`not_in` atom, minting a schema the backend rejects and one
the runtime mis-evaluates (it compares the list against an array trigger value).
Fixed: on a radio -> checkbox_group flip, a TOP-LEVEL legacy `in [a,b]` expands to
`any_of[includes a, includes b]` and `not_in` to `none_of[...]`. An `in`/`not_in`
atom already NESTED in a composite bucket cannot expand (v2 is one level), so
`canChangeGroupKind` refuses that flip (the same defensive stance as the
shared-name guard), and the UI disables + explains the checkbox_group target.

**Third fresh-eyes gap (Opus OUTER review, adopted, fixed inline).** The two
independent Opus outer reviews split: one cleared, the other found that the
top-level `in`/`not_in` expansion was only guarded for the NESTED case. A
top-level `in`/`not_in` whose value resolves to ZERO current option slugs (all
members stale/renamed) fell through and emitted a raw `in`/`not_in` on the flipped
checkbox_group -- backend-invalid; and a PARTIALLY-stale list silently dropped its
stale members (narrowing `in`, widening `not_in`'s `none_of`). Per "ambiguous =
blocker" this was adopted: `hasUnflippableListMembership` now ALSO refuses a
top-level `in`/`not_in` that is not losslessly expandable (non-array value, empty
list, or any stale member). A FULLY-LIVE top-level `in`/`not_in` still flips
(expands to `any_of`/`none_of` of `includes`). The UI's retarget hint already
covered this case.

Fresh-eyes triage across rounds: 3 blockers adopted + fixed inline (shared-name
fillability asymmetry, Sonnet assess; `in`/`not_in` list-membership asymmetry,
Opus assess; the reason-specific UI hint, Opus assess; and the top-level
stale-`in`/`not_in` guard, Opus outer review). Low-confidence findings rejected as
non-blocking: a self-referential group condition (no code path lets a group
reference its own id, and merge does not guard it either); the empty-string-slug
exclusion in `optionSlugs` (mirrors `mintOptionSlug`'s own guard); and a
non-PDF-source over-refusal (unreachable -- the editor is a PDF-form authoring
tool, and the over-refusal is safe, never minting an invalid schema). The Sonnet
assessor filed `polyglot-pdf-cv9x` for the shared-name blocker; since it was
in-scope against this bead's exit criterion 3 and fixed here, that bead was closed
as fixed inline. The Opus reviewers filed no beads (in-scope, reported inline).

Tests: net-new across `fieldGrouping.test.ts` (both flip directions, composite
rewrite, whole-group-operator preservation, no-op cases, `canChangeGroupKind`
validity, the shared-name-radio refusal, the `in`/`not_in` top-level expansion in
both directions, and the in-composite `in`/`not_in` refusal) and
`FieldEditor.groupkind.test.tsx` (the render -> select-change -> callback wiring,
the author-tier/handler gating, and the disabled+explained checkbox_group option
for a shared-name radio). Full schema-editor suite green (636 tests, 37 files).
`tsc --noEmit` clean.

## Lessons

Editor mutations that only change a field's `type` must be validated against the
backend's group-validity rules (`form_models.py`), because the two group kinds
are asymmetric on PDF-widget plumbing: a checkbox_group needs a distinct widget
per option, a radio can share one. A pure `type` flip that ignores that mints an
un-promotable schema with no in-editor signal. This is specific to the editor's
group model, not a codebase-wide rule, so it stays in this entry rather than a
`docs/standards/*.md` one-liner.

## Doc freshness

The schema editor has no tier-2 component doc (its details live in the journal,
tier 3), so there was no surface doc to bump. `closeout_prep.py` flagged a batch
of STALE docs under `docs/standards/*` plus `docs/technical_guide.md`; none of
them carry a `**Tracks:**` glob covering `schema-editor/**`, so they were already
stale before this branch and are left untouched (this change did not introduce
their staleness).

## Files touched

- `schema-editor/src/utils/fieldGrouping.ts` -- new `changeGroupKind` +
  `canChangeGroupKind`.
- `schema-editor/src/components/FieldEditor.tsx` -- "Group behaves as" selector,
  invalid-target disable + explanation.
- `schema-editor/src/App.tsx` -- `handleChangeGroupKind` wiring.
- `schema-editor/src/utils/fieldGrouping.test.ts` -- flip + validity tests.
- `schema-editor/src/components/FieldEditor.groupkind.test.tsx` -- new component
  test file.
