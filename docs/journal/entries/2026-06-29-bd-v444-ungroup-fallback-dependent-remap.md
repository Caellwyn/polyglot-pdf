---
date: 2026-06-29
bead: polyglot-pdf-v444
beads: [polyglot-pdf-v444, polyglot-pdf-cjby]
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

- **`show_if` referencing a SPECIFIC matched option** (its value resolves to a
  reconstructed field) -> the exact single-option inverse, targeting that option's
  field: `equals <optValue>` -> `is_checked`; `not_equals <optValue>` ->
  `not_equals true` (shown UNLESS that option is selected). This bead's second half
  (bd cjby, found by fresh-eyes) is the `not_equals` case: it must be `not_equals
  true`, NOT `is_empty` -- `shouldShowField`'s `is_empty` is true only for
  null/undefined/'' , so an EXPLICITLY unchecked checkbox (value `false`) reads as
  not-empty and the dependent would be permanently hidden once touched. `not_equals
  true` reads false===checked (hidden), true===unchecked-or-absent (shown).
- **A whole-group / unmatched `show_if`** (an operator testing the consolidated
  field's populated-ness, or a value matching no option) -> retargeted to the
  PRIMARY reconstructed field with its operator NORMALIZED so it still fires on a
  standalone boolean checkbox (`normalizeWholeGroupOperator`). Preserving the raw
  operator silently misfired: `not_equals ''` / `is_not_empty` on an unchecked
  checkbox (`false !== ''`) is always TRUE -> permanent show (real i-90 case:
  `p1_line6c_aptsteflrnumber`'s `not_equals ''` on the consolidated
  `p1_unit_type6c_unit`). The map: `is_not_empty`/`is_checked`/`not_equals <empty>`
  -> `is_checked`; `is_empty`/`equals <empty>` -> `is_empty`; a genuine
  `equals <non-empty-unmatched>` stays `equals` (unsatisfiable -> hidden, the
  correct "no such option"); `not_equals <non-empty-unmatched>` stays `not_equals`
  (always-true on a boolean, replicating the original always-show).
- **Empty-string option values are excluded** from the option map, so an
  `equals ''` / `not_equals ''` stays a whole-group check rather than mis-routing
  to a degenerate ''-valued option (fresh-eyes r3).
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

## Fresh-eyes loop (pre-PR Assess)

This bead took an unusually deep adversarial assess loop -- 4 fresh-eyes rounds
(Sonnet), each finding a distinct REAL bug in the operator semantics, converging:

1. **r1** -- the whole-group else-branch preserved the raw operator -> `not_equals
   ''` / `is_not_empty` permanently true on a boolean checkbox. Added
   `normalizeWholeGroupOperator`.
2. **r2** -- `not_equals <matched option>` fell to the whole-group branch and
   mapped to `is_empty` on the PRIMARY (wrong field + wrong operator). Filed as
   its own bead **cjby**; moved matched `equals`/`not_equals` into the
   specific-option branch.
3. **r3** -- the r2 `not_equals <matched> -> is_empty` was still wrong: `is_empty`
   is false for an explicitly-unchecked (`false`) checkbox, hiding the dependent
   forever. Fixed to `not_equals true`; excluded ''-valued options from the map;
   rewrote tests to assert RUNTIME behavior via a local `runtimeShowIf` oracle
   mirroring `shouldShowField` (the r2 tests pinned shape only, which is why the
   bug shipped to r3).
4. **r4** -- confirmation pass: **NO-GAPS**. Verified `not_equals true` against the
   real evaluator (false===checked, true===unchecked/absent) and the oracle's
   fidelity line-by-line. The journal test-count fix below is its only finding.

The loop legitimately converged (each round a real, fixed, runtime-verified
defect; r4 clean), so it terminated at NO-GAPS rather than escalating.

## Verification

`schema-editor` vitest: `fieldGrouping.test.ts` 48 tests pass (32 prior + 16 new
across both beads -- option remap for primary/non-primary/de-duped-collision, the
whole-group operator normalizations, the matched `not_equals -> not_equals true`
inverse with runtime-oracle checks for checked/unchecked/absent, the ''-option
exclusion, `controls_fields`/`copy_to` expansion, and the untouched-dependent
no-op). Full editor suite green (20 files), `tsc --noEmit` clean. The backend
pytest suite (495 passed) is unaffected -- this change is frontend-only.

Env note: main's `schema-editor/node_modules` was missing transitive deps
(`@asamuzakjp/css-color`, `@babel/runtime`) so jsdom + testing-library failed to
load; `npm install` (NOT `npm ci`, which EPERM'd on a locked `esbuild.exe`)
reconciled them. Worktree runs the suite via the standard node_modules junction.
Vitest's forks pool intermittently hangs on teardown ("Vite server won't exit")
AND once flaked with "Timeout starting forks runner" -- tests complete and pass
regardless; `--pool=threads` avoids both.

## Doc freshness / housekeeping

`check_doc_freshness.py` flagged many STALE tier-2 docs, but ALL track
`backend/` / `frontend/src/` files this branch did not touch (the diff is
`schema-editor/` + this journal entry only) -- they were stale before this branch
and are left as-is. Beads housekeeping surfaced a pre-existing orphan
(`jnjj.45`, the secretary epic, in-progress in a different workstream) and 4 stale
in-progress epics (`hrn`, `jf6w`, ...) -- none referenced by this branch's single
commit-line, all orthogonal to the editor work; left for their owners.
