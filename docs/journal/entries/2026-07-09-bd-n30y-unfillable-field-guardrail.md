---
date: 2026-07-09
bead: polyglot-pdf-n30y
title: "Guardrail: CI-inventory the 'field exists but unfillable' classes"
tags: [schema-lint, testing, form-kits]
---

## Trigger

Two form-kit bugs (bd 3fz7, 0nxh) looked i-90-specific. The maintainer asked to
fix the SYSTEM, not individual forms. Probing both failure modes across all 4
shipped kits showed they are symptoms of one systemic gap: **the promotion/lint
gate does not catch "a field/widget exists but can't be filled through the app."**
Two classes:

- **dump-widget-unclaimed** -- a real fillable PDF widget that NO schema field
  maps to (extraction dropped it). Present in i-90 (4: P2_checkbox3[1..4], bd
  0nxh) AND f1040 (12) -- so NOT i-90-specific.
- **readonly-conditional-no-unlock** -- a `read_only` field shown/required by a
  condition but with no `unlock_method`, so FieldRenderer leaves it permanently
  disabled when shown (i-90's 3 Part-4 accommodation checkboxes, bd 3fz7).

## What shipped (guardrail-first, per maintainer choice: WARNINGs, don't block)

- Rule (A) `dump-widget-unclaimed` already existed as a WARNING (bd w0eq/P6.1c).
- Rule (B) `readonly-conditional-no-unlock` added to `schema_lint.py` as a WARNING
  (a signature is read-only-by-nature and NOT conditional, so it does not trip).
- **CI-enforced inventory**: `test_kit_unfillable_field_inventory` (parametrized
  over all 4 kits, in the existing backend pytest job) pins each kit's count of
  both warning classes against a documented `_UNFILLABLE_BASELINE`
  (i-90: 0+3, w7: 0, w7-2: 0, f1040: 12+0 -- i-90's class-A count is 0 because bd
  0nxh landed first, modeling its 4 missing checkboxes; see below). A NEW
  regression (count up) fails CI; fixing a form's data (count down) also
  fails-loud, forcing a deliberate baseline update as the inventory shrinks
  toward zero.
- `test_shipped_kits_lint_clean` -> `test_shipped_kits_lint_error_free`: the
  promotion gate is zero ERRORs; the shipped kits now carry known WARNINGs, owned
  by the inventory test, not asserted away.

The extractor already FIXES class (A) going forward via the coverage backfill
(bd w0eq); this is the DETECTOR for already-committed kits that predate it (i-90
hand-curated; f1040 migrated-not-re-extracted).

Rule (B) precision (bd rsy3, folded in from the pre-PR review): `has_unlock`
counts ONLY `unlock_method == "flip_readonly_bit"`, not any truthy value --
FieldRenderer's `shouldUnlock` string-compares that exact value (on both the
canonical `conditional_behavior` key and the legacy `conditional_logic` alias),
so a `set_property` (or any other) unlock would lint clean yet stay locked at
runtime. Tests cover: non-flip unlock still warns, legacy-alias flip suppresses,
and the `require_if`-only branch. i-90's baseline is unchanged (its 16 unlockable
fields all use flip_readonly_bit; the stuck 3 have no unlock at all).

## Follow-up

Fix the underlying form data to lower the baseline. **0nxh is DONE** (i-90's 4
class-A checkboxes now modeled -- baseline lowered to 0 here). Remaining: 3fz7
(unlock i-90's 3 class-B accommodation checkboxes) and f1040's 12 class-A
uncovered widgets. Once all kits are clean, flip both rules to ERROR. Tracked on
bd n30y + the per-kit beads.

## Verification

47 lint tests pass (rule-B unit tests + the 4-kit inventory). Full backend suite
1728 passed. Purely additive: no ERROR added, no kit data changed, nothing blocks.
