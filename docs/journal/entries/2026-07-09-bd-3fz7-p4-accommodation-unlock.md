---
date: 2026-07-09
bead: polyglot-pdf-3fz7
title: "Unlock i-90 Part 4 accommodation checkboxes when shown"
tags: [form-kits, schema-forms, testing]
---

## Trigger

The P6.2 migration report (`migration_report.json`) flagged `p4_checkbox1[1]`'s
`unlocks` edge to `p4_checkbox1a/b/c` as an UNCONVERTED action needing human
review, but nobody had checked whether those three Part 4 disability-accommodation
checkboxes are actually fillable once shown. They are not.

## Root cause (verified against code + PDF, not assumed)

`p4_checkbox1a/b/c` (deaf/hard-of-hearing, blind/low-vision, other-disability
accommodation) are `read_only: true` with a `show_if` gating visibility on
`p4_checkbox1[1]` (`is_not_empty`), but carried NEITHER
`conditional_behavior.unlock_method` NOR `conditional_logic.unlock_method`.

- **Frontend:** `FieldRenderer.tsx` computes
  `isDisabled = shouldUnlock ? disabled : (disabled || field.read_only)`. With no
  `unlock_method`, `shouldUnlock` is always `false`, so `isDisabled` falls back to
  `field.read_only` UNCONDITIONALLY -- the checkbox renders but is permanently
  disabled, even when shown.
- **PDF:** the three backing widgets (`P4_checkbox1a/b/c[0]`) have the AcroForm
  read-only flag bit set (`field_flags = 1`), so the backend filler
  (`apply_field_flag_changes`) could not write them either.

Pre-existing latent bug (present in `origin/dev` before any P6.2 i-90 edit), not
introduced by the migration. The sibling accommodation textareas
(`p4_line1a/b/c_accomodationrequested`) already carry the correct unlock block --
the three checkboxes were the anomaly.

## Fix

Added `conditional_behavior.unlock_method = flip_readonly_bit` plus the matching
`pdf_field_flag_change {bit: 0, current_value: 1, required_value: 0}` to all three
checkboxes, identical to the sibling textareas and to the Part 2 reason radios.

Now: `shouldUnlock` is `true`, so FieldRenderer's `isDisabled` follows the passed
`disabled` prop (editable when shown); the backend flips each widget's read-only
bit 1 -> 0 before filling.

## Verification

- v2 model: 0 problems; `validate_all_references()`: 0 errors.
- Targeted PDF-fill check: each widget's read-only bit flips 1 -> 0 under the
  production `apply_field_flag_changes` semantics.
- `roundtrip_fill`: 100% CHOICE / 100% TEXT (unchanged).

## Regression guard

`test_shipped_kit_shown_readonly_fields_can_unlock` (parametrized over all 4
shipped kits) asserts every `read_only` + `show_if` field declares an
`unlock_method` -- the exact invariant this bug violated. All 4 kits pass (no other
instances). Also corrected the adjacent `test_shipped_kit_has_no_dangling_references`
comment, which had mischaracterized `p2_checkbox3[1..4]` as consolidated group
leaves (they were dead section refs; and `p2_checkbox3` is now a real 5-option
radio after bd 0nxh).
