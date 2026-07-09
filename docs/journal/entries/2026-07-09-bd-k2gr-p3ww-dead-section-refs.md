---
date: 2026-07-09
bead: polyglot-pdf-k2gr
also_closes: polyglot-pdf-p3ww
title: "Remove dead section.fields references in i-90 + w7-2"
tags: [form-kits, testing]
---

## Trigger

Fresh-eyes on the P6.2 flip (bd h76m.16) surfaced two pre-existing form-kit data
bugs of the same class: a section's `fields[]` array naming field ids that don't
exist in `schema.fields`, so `FormSchema.validate_all_references()` reports errors.
Neither was introduced by P6.2 (both present in origin/dev before it) and neither
is caught by the promotion lint (which checks show_if/require_if references, not
section.fields).

- **i-90 (k2gr):** the "Part 2 - Application Type" section listed the real
  `p2_checkbox3` group AND `p2_checkbox3[1..4]` -- the individual widget leaves that
  were consolidated INTO that checkbox_group. The `[1..4]` are dead refs.
- **w7-2 (p3ww):** the `sec_agent` section listed 5 real agent_* fields PLUS
  `agent_company`/`agent_ein`/`agent_ptin`/`agent_office_code` -- phantom ids never
  extracted as fields. Verified against the AcroForm dump: w7-2's schema covers ALL
  69 PDF widgets (0 uncovered), so these are not fields the extraction missed;
  there are no fillable widgets behind them.

## Fix

Removed the 8 dead refs (4 per kit) from the section `fields[]` arrays. Strictly
behavior-preserving: the refs pointed at nothing, so nothing rendered for them; the
real fields are untouched. Both kits: model validates, `validate_all_references()`
0 errors, lint 0 errors, roundtrip_fill unchanged (both 100% CHOICE / 100% TEXT).

## Regression guard

Added `test_shipped_kit_has_no_dangling_references` (parametrized over all 4 shipped
kits) in `test_form_models_v2.py`: `validate_all_references().errors == []`. This
class of bug slips the promotion lint, so a dedicated kit-level assertion is the
guard. Full backend suite 1721 passed.
