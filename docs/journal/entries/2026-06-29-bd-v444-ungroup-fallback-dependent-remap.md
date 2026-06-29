---
date: 2026-06-29
bead: polyglot-pdf-v444
title: "Ungroup fallback path: remap dependents of a hand-authored consolidated field"
sprint: 6
tags: [bug, conventions]
---

## Trigger

Opus fallback review of PR #256 (the group/ungroup feature, bd s4dp.1) finding 5.
`ungroupField`'s NO-STASH fallback branch -- the path taken when un-merging a
hand-authored consolidated field loaded from disk (e.g. I-90 `p3_race`), which
carries no in-session `_ungroup` stash -- reconstructed one standalone field per
option but did NOT rewrite OTHER fields whose `show_if` / `controls_fields` /
`copy_to` referenced the consolidated field id. After the split those dependents
kept pointing at the (now primary-only) consolidated id, so selecting a
NON-primary reconstructed option no longer revealed the dependent.

The in-editor merge -> ungroup (stash) path is lossless and was unaffected; this
only ever bit fields that were never merged in-session. Low frequency
(hand-authored consolidated fields with dependents are uncommon), hence P3.

## What shipped

A `remapFallbackDependent()` helper applied to every non-target field in the
fallback branch -- the inverse of `mergeFields`' `rewriteReferences`:

- **`show_if` `{field: C, operator: equals, value: <optValue>}`** -> the dependent
  fired when the consolidated radio held that option's value. After the split that
  option is its own standalone checkbox/radio, so this becomes `is_checked` on the
  reconstructed field for that value. This is the exact inverse of the forward
  rewrite (`is_checked on widget` -> `equals <optValue> on C`). A whole-group
  condition (`is_checked`/`is_not_empty` on `C` with no specific option) or an
  `equals` whose value matches no option is retargeted to the PRIMARY reconstructed
  field so it never dangles; other operators retarget but keep their operator.
- **`controls_fields` / `copy_to` target arrays containing `C`** are EXPANDED to
  all reconstructed split ids (the rule acted on the whole former group), de-duped.

The `value -> reconstructed-field-id` map is built during reconstruction, so it
correctly tracks the de-dup suffixing already in the fallback (an option value that
collides with a surviving field id reconstructs to `<value>_1`, and the dependent
remaps to that suffixed id, not the bare value).

## Why these semantics (not a bare id swap)

The consolidated field's RUNTIME value is the selected option's `value` (see
frontend `shouldShowField`: `equals` compares the trigger's scalar value). A bare
id swap would leave `equals <optValue>` pointing at a standalone checkbox whose
runtime value is `true`, which never equals the option string -- so the dependent
would never show. `is_checked` is the operator that fires on a selected standalone
widget. This mirrors the forward-merge reasoning already documented in
`fieldGrouping.ts`.

## Scope / non-goals

Stash (in-session merge) ungroup was already a lossless inverse and is untouched.
This is strictly the disk-loaded / hand-authored fallback. No backend or runtime
change -- purely an editor-side mutation in
`schema-editor/src/utils/fieldGrouping.ts`.

## Verification

`schema-editor` vitest: `fieldGrouping.test.ts` 39 tests pass (32 prior + 7 new
covering the exit criterion -- non-primary option remap, primary option remap,
whole-group fallback-to-primary, `controls_fields` expansion, `copy_to` expansion,
and the untouched-dependent no-op). Full editor suite green (20 files), `tsc
--noEmit` clean.

Env note: main's `schema-editor/node_modules` was missing transitive deps
(`@asamuzakjp/css-color`, `@babel/runtime`) so jsdom + testing-library failed to
load; `npm install` (NOT `npm ci`, which EPERM'd on a locked `esbuild.exe`)
reconciled them. Worktree runs the suite via the standard node_modules junction.
