---
date: 2026-07-07
bead: polyglot-pdf-h76m.16
title: "P6.2 schema-v2 strictness flip + hack retirement (epic capstone)"
tags: [schema-editor, schema-forms, migration, conventions, testing, voice-ai]
---

## Trigger

The final bead of the schema-v2 epic `polyglot-pdf-h76m` (plan P6.2). Flips the
schema layer to v2-only and retires the compatibility hacks that let v1 and v2
coexist through the epic. CONSEQUENCE-BEARING: removes v1 support across the whole
stack and re-migrates all four shipped kits (i-90 is live on the demo).

## Precondition: migrate the last three kits

P6.2 requires every stored kit to be v2. Only i-90 was (P6.1b); w7/w7-2/f1040 were
still v1 because P6.1c was redirected to fixing the extractor bug rather than
producing v2 kits. The deterministic `migrate_schema_v2.py` converts all three
cleanly (validate + lint 0 + fill preserved: w7/w7-2 100/100, f1040 100/96.6 --
96.6 is a pre-existing f1040 text characteristic, identical pre/post). The
migration also RESOLVES the shipped f1040 duplicate-option-value bug (unique slugs
per field). v1 originals are archived to `schema_archived.json`.

## The flip

- **Backend model** (`form_models.py`): `_enforce_v2_rules` applies to EVERY schema
  now (the `schema_version != '2'` bypass is gone). DELETED `group_kind`/`GroupKind`,
  `controls_fields`/`ConditionalControl`, `conditional_fields`. The dict-based
  migration script is unaffected (it never `model_validate`s v1). Dead
  controls_fields handling removed from `schema_lint.py` + `schema_repair.py`.
- **Both evaluators** (`frontend/.../validation.ts`, `schema-editor/.../conditionalVisibility.ts`):
  deleted the vq4m equals-means-membership hack, the comma-split tolerance, and the
  `group_kind` gate. `equals`/`not_equals` are PURE scalar; membership lives ONLY in
  `includes`/`not_includes` over a `string[]` (the voice comma string is converted
  to an array at the single ingress boundary before storage). A checkbox group is
  identified by TYPE (v2 `checkbox_group`, or legacy `checkbox` with options[]).
- **Shared vectors** + the editor FieldEditor controls_fields UI + the frontend/
  editor `ConditionalControl` TYPE removed. `checkbox_group` added to the frontend
  `FieldType` union (it was missing).

## controls_fields is MIRRORED, not dropped (the hard part)

v2 has no trigger-side conditional logic, so each `controls_fields` edge is
MIRRORED into the target's `show_if` (from `shows`) / `require_if` (from
`makes_required`), then removed. Multiple triggers gating one target merge via
`any_of` (OR). `unlocks`/`locks`/`hides`/`makes_optional` have no clean target-side
equivalent and are REPORTED as unconverted -- in the shipped kits these are all
`unlocks`, redundant with the target's `conditional_behavior.unlock_method=
flip_readonly_bit`. i-90 ends up byte-identical to its shipped form except its 2
redundant-unlock edges are gone.

Three pre-PR fresh-eyes rounds each hardened this:
1. The first pass STRIPPED all controls_fields, silently losing 14 fields'
   show/require behavior. Fixed: mirror, don't drop. (roundtrip_fill can't catch
   this -- it measures widget-write, not require_if correctness.)
2. The "already mirrored?" check was KEY-BLIND (scanned both show_if AND
   require_if), so a target's pre-existing show_if wrongly suppressed a
   makes_required mirror -- dropping require_if on 15 w7/w7-2 fields. Fixed:
   `_target_has_condition(target, key, want)` checks the MATCHING bucket only.
3. Behavior verified correct via independent ground-truth reconstruction; the
   regression tests were hardened to reproduce the real SAME-trigger shape (a
   show_if and a makes_required from the same trigger/value on one target).

## Downstream fallout

- `eval_extraction`: the v1 widget-leaf value-convention gate is skipped for v2
  schemas (v2 slugs "violate" it by design); f1040 now scores OK (its dup bug is
  resolved). The multi-form table is all-green -> exit 0.
- editor two-gate-seam tests: v2 strictness now catches dup-option / bad-ref
  defects at the PARSE gate (422), not the lint gate (409).
- `i90MigrationEquivalence.test.ts` removed: it compared new-evaluator(migrated) vs
  new-evaluator(v1-archive), which requires the evaluator to support BOTH v1 and v2
  semantics -- exactly what the flip removes. i-90's correctness is pinned by
  `tests/test_i90_migrated_baseline.py`.

## Deferred (filed beads)

- `wvgh`: fully excise controls_fields from the schema-editor INTERNALS
  (fieldGrouping/PreviewPane/validation/types) -- dead-but-harmless (controls_fields
  is always absent now), kept to avoid destabilizing the merge feature; tsc-clean.
- `3fz7`: pre-existing i-90 p4_checkbox1a/b/c lack unlock_method (predates this PR).
- `dghy`: migration doesn't report a controls_fields edge whose target id is
  dangling (unreachable in the 4 shipped kits).

## Verification

All four kits promote under the strict gate (validate + lint 0). Suites green:
backend 1694, frontend 768, schema-editor 35 files. Both exit criteria met.
