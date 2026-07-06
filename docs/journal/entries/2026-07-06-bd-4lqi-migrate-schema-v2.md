---
date: 2026-07-06
bead: polyglot-pdf-4lqi
title: "P6.1a migrate_schema_v2.py -- deterministic v1->v2 schema migration"
tags: [migration, conventions, testing]
---

## Trigger

Lane-1 bead of the schema-v2 epic `polyglot-pdf-h76m` (plan P6.1), the first of
three sub-beads P6.1 (`h76m.15`) was split into: **P6.1a** (this bead -- the
migration SCRIPT, pure tooling), P6.1b (`c5r8` -- apply to i-90 + equivalence +
demo QA, consequence-bearing), P6.1c (`w0eq` -- re-extract w7/f1040, paid
tokens). The split isolates the shipped-kit change and the paid re-extraction
from the deterministic tooling.

## What shipped

`scripts/migrate_schema_v2.py` -- `migrate(schema, dump=None) -> (migrated,
report)`, deterministic + idempotent. Transforms:

- **classify checkbox**: `>= 2` options -> `checkbox_group` (drops the field-level
  `pdf_field_name` -- v2 forbids it on a group); exactly `1` option -> standalone
  `checkbox` (lifts the option's `pdf_field_name` onto the field, drops
  `options[]` -- a one-option checkbox is a single boolean box, not a group).
- **mint option slugs** from labels (per-field old->new map); rewrite every
  `show_if`/`require_if`/`controls_fields` value that referenced an old option
  value to the new slug.
- **operator rewrites keyed on the trigger's POST-migration type**:
  equals/not_equals on a `checkbox_group` -> includes/not_includes; the
  `is_checked` DUAL FATE (kept as bool sugar on a standalone `checkbox`;
  rewritten to `is_not_empty` on ANY option-bearing trigger --
  checkbox_group/radio/select, the "option-bearing -> selection-exists"
  principle); the v1 `equals`/`not_equals ""` emptiness idiom ->
  `is_empty`/`is_not_empty` (value stripped).
- **fold `conditional_logic` into `conditional_behavior`**: keep `unlock_method`
  + `pdf_field_flag_change`; drop `show_method` (the one-line spike confirmed no
  reader -- consumers are `pdf_fill_routes.py` + `FieldRenderer.tsx`, which read
  only those two keys). The fold is load-bearing: in the i-90 gold the
  `pdf_field_flag_change` descriptor lives only on `conditional_logic`, so folding
  is what makes the read-only unlock actually fillable.
- **controls_fields**: drop an edge only when its targets already carry a
  mirroring `show_if`/`require_if` naming this trigger (v2 evaluates target-side);
  a trigger-side edge with an UNMIRRORED target is REPORTED (kept for human
  conversion), never silently dropped.
- **drop legacy `conditional_fields`** (v2 rejects it); stamp `schema_version 2`.
- **optional dump**: a v1 choice field with `< 2` options is invalid in v2. When
  a dump is supplied, a mis-typed option-less combobox (the i-90 height
  dropdowns, PDF comboboxes typed `radio` with 0 options in the gold) is retyped
  to `select` with options recovered from the widget's PDF choices (display ->
  label, minted slug -> value, raw choice -> `pdf_on_value`); without a dump it
  is left as-is and reported (`needs_options`) for the dump-bearing caller (P6.1b).

## The is_checked dual fate, by construction

The dual fate (standalone checkbox: keep; option-bearing: -> is_not_empty) is
pinned by the SHARED fixture `backend/tests/fixtures/is_checked_dual_fate.json`,
which the P1.1 validator tests (`test_form_models_v2.py`) ALSO consume. The
migration test reads the same fixture and asserts its rewrite matches -- so the
migration and the validator agree by construction, not by parallel maintenance
(a divergence turns one of the two suites red).

## i-90 latent defects surfaced

Applying migrate() to the real i-90 surfaced pre-existing v1 defects that v2
strictness rejects, all handled: (a) `p2_checkbox3` + three `p4_checkbox1*` are
single-option checkboxes -> standalone; (b) two `is_not_empty value=""` and an
`is_checked` on a `radio` trigger (`p4_checkbox1[1]`, a bracketed v1 field id) ->
the emptiness/selection-exists rewrites; (c) `p3_line8_heightfeet/inches` are PDF
comboboxes mis-typed as option-less radios -> retyped to `select` from the dump.

## Verification

Exit criteria: (1) idempotent + the migrated i-90 validates as v2, lints 0/0
(dump-aware), preserves 132 fields, and roundtrip-fills 100% CHOICE (28/28) +
100% TEXT (110/110) -- the P0 baseline's two load-bearing rows (the intentionally-
changed leaf-convention row is expected to drop, per the baseline doc). (2) the
dual fate matches the shared fixture; an unmirrored controls_fields edge is
reported not dropped. 11 tests; the P1.1 validator suite (shared fixture) stays
green.

## Unblocks

P6.1b (`c5r8`, apply to i-90 + equivalence + demo QA) and P6.1c (`w0eq`,
re-extract) both depend on this script; then P6.2.

## Doc-freshness note

closeout_prep flagged the usual tier-2 docs as STALE. Reviewed: this diff adds
only two NEW files (`scripts/migrate_schema_v2.py`, its test) that no doc tracks
-- pre-existing drift from other work's mtimes, left as-is.
