---
date: 2026-06-15
bead: polyglot-pdf-bjwy
title: "A4: controls_fields editing UI"
sprint: 5
tags: [testing, conventions]
---

## Trigger

`bd polyglot-pdf-bjwy`, the last open child of Track A (the "Joyful schema-editor"
umbrella `hid`) in sprint 5 / epic 7a9
(`docs/sprint_5_i90-authoring-loop_plan.md`, crit 4). Survey gap: the schema
supports `controls_fields` -- a field whose value propagates show/unlock/required
(etc.) actions to dependent fields -- but the editor had NO UI for it; only the
reactive `show_if` was editable. Authoring or fixing a `controls_fields`
relationship meant hand-editing JSON, which crit 4 ("find, edit, and author a
controls_fields relationship without leaving the tool") explicitly rules out.

## What shipped

A "Controls Fields" section in `FieldEditor.tsx`, modelled on the existing
`show_if` block:

- A list of control entries. Each has an **operator** dropdown + a **trigger
  value** input, and a per-action target-field picker for each of the six action
  kinds: shows / hides / unlocks / locks / makes_required / makes_optional.
- Add a control ("+ Add Control"), remove a control, and toggle target fields
  per action via checkboxes. The current field is excluded from its own target
  lists. Empty action keys and an empty control list are pruned on write so the
  exported JSON stays minimal.

**A stale-type correction the rubric forced.** The frontend `ControlsFields` type
was wrong: a single object `{ when_value, shows?, unlocks?, makes_required? }`.
The canonical shape -- backend `ConditionalControl`
(`backend/models/form_models.py`) AND the real `form-kits/i-90` data -- is a
`List[ConditionalControl]`, each control carrying an `operator`/`value` and the
six action arrays (no `when_value`). Because the editor saves the schema verbatim
(`JSON.stringify`, no load-time normalization) and `validation.ts` read
`.shows`/`.unlocks` off what is actually an array, the reference check was
**silently broken on real list-shaped data**. Fixing the type (`schema.ts`,
extending `ConditionalOperator` to the full backend enum) and rewriting
`validation.ts` to iterate the list across all six action arrays is what makes
exit criterion 2 ("ValidationPanel reference check stays consistent") true rather
than vacuous.

**Exit-criteria scorecard** (both PASS):

1. Author a `controls_fields` relationship via the UI (target field(s) + control
   kind) and it round-trips into the correct shape. PASS -- the UI writes
   `controls_fields: ConditionalControl[]` (operator + value + action arrays)
   matching backend/i-90 data; `FieldEditor.controls.test.tsx` asserts the exact
   emitted object on add + target-select.
2. Editing/removing an existing entry works and the ValidationPanel reference
   check stays consistent. PASS -- edit operator/value in place, remove a control,
   prune empty keys; `validation.ts` iterates the list; tests cover edit/remove +
   a valid multi-array control passing and a ghost ref failing.

**Verification:** new `FieldEditor.controls.test.tsx` (10 tests); full
schema-editor suite 178/178; `tsc --noEmit` clean. Backend suite untouched
(FE-only) and green from prep.

**Fresh-eyes assess (Sonnet, arm B picker, 2 rounds to NO-GAPS):** both rubric
criteria scored PASS. Adopted: tightened the `CONTROL_ACTIONS` /
`toggleControlTarget` typing from `keyof ConditionalControl` to a new
`ControlActionKey` union (the six action keys only -- the old type let
operator/value through, runtime-safe but too wide), and added a serialization
test asserting a pruned action key is ABSENT from the exported JSON (undefined,
not null -- the backend action fields are `Optional[List]=None`). Out-of-scope
filed by fresh-eyes: `polyglot-pdf-cmcg` (stale `ControlsFields` type name in
`schema-editor/EDITOR_GUIDE.md`).

**Codex outer review (PR #216, 2 rounds to CLEAN):** round 1 raised two real P1
findings, both adopted as blockers:
(1) extending `ConditionalOperator` with `in`/`not_in` made them selectable in
the show_if + controls editors, whose `value` is a plain-text (scalar) input --
so authoring `in` would save a string the runtime (which expects an array) never
matches. Fix: exclude `in`/`not_in` from the dropdown (they stay in the
type/schema so existing data loads + validates); filed `polyglot-pdf-jplx` for a
future array-value editor.
(2) the new list-shaped controls validation checked references while the field-id
set was still being built incrementally, so forward references (trigger before
targets, the i-90 ordering) were spuriously flagged on the live form. Fix: build
the COMPLETE field-id set in a first pass, then check references (fixes show_if
too); this resolves the pre-filed `polyglot-pdf-y61i`, now CLOSED, with a
regression test.

## Lessons

- **The backend Pydantic model is the source of truth for wire/JSON shape; the
  FE TypeScript types have drifted from it before.** Here the FE `controls_fields`
  type had diverged to a shape that matched neither the backend nor any real
  form-kit data, and a downstream consumer (validation) silently mis-read live
  data. When adding editor UI for a schema feature, diff the FE type against
  `backend/models/form_models.py` and a real form-kit sample first. (Generalizes,
  but the schema-editor has no tier-2/standards doc to host the one-liner; kept in
  this entry + recalled via local memory rather than forced into an unrelated
  standards doc.)

## Doc freshness

- FE-only change to the schema editor, which has no tier-2 component doc, so no
  component doc to bump for this surface.
- Any backend/frontend-shared docs flagged stale by `check_doc_freshness.py`
  track files this branch did not touch (this branch is confined to
  `schema-editor/`) -- left as-is per the doc-freshness rule (recorded here).

## Files touched

- `schema-editor/src/types/schema.ts` -- `controls_fields` retyped to
  `ConditionalControl[]`; new `ConditionalControl` interface (operator + value +
  six action arrays); new `ControlActionKey` union (the six action keys);
  `ConditionalOperator` extended to the full backend enum (added greater_than /
  less_than / in / not_in).
- `schema-editor/src/utils/validation.ts` -- iterate the controls LIST and check
  references across all six action arrays; restructured into two passes (build
  the full field-id set, THEN check references) so forward refs are not flagged.
- `schema-editor/src/components/FieldEditor.tsx` -- "Controls Fields" editing
  section + controls list helpers; operator dropdown excludes `in`/`not_in`
  (need an array value the scalar editor can't author).
- `schema-editor/src/components/FieldEditor.controls.test.tsx` -- NEW. 10 tests
  (authoring round-trip, target add/remove, empty-key pruning, edit-in-place,
  JSON-serialization-omits-pruned-key, no in/not_in operators offered, validation
  flags ghost ref / passes valid multi-array control / passes forward refs).
- `docs/journal/entries/2026-06-15-bd-bjwy-controls-fields-ui.md` -- THIS entry.

## Follow-ups filed

- `polyglot-pdf-y61i` -- `validateSchema` reference checks were order-dependent
  (id set built incrementally inside the check loop -> forward refs falsely
  flagged). Initially filed as out-of-scope/pre-existing, but Codex showed it
  was a live regression on the i-90 form via this PR's list-loop, so FIXED here
  (two-pass) and CLOSED.
- `polyglot-pdf-cmcg` -- stale `ControlsFields` type name in
  `schema-editor/EDITOR_GUIDE.md` (the type was renamed/restructured this bead).
  Filed by fresh-eyes; out-of-scope docs fix.
- `polyglot-pdf-jplx` -- array-value editor for the `in`/`not_in` operators
  (excluded from the authoring dropdown until a list-value input exists). Filed
  from a Codex finding; P3 enhancement.
