---
date: 2026-06-28
bead: polyglot-pdf-cn0e
title: "a_number normalization no-op'd: normalize_value read format_preset from the wrong nesting level"
tags: [hotfix, testing]
---

## Trigger

A live production bug (the maintainer hit it independently during DTI use): an
Alien Registration Number entered as "A12345678" failed validation. An A-Number is
spoken/written as "A" + 7-9 digits, but the PDF comb field stores bare digits
(pattern `^\d{7,9}$`), so `normalize_value` is supposed to strip the leading "A"
before the pattern check. It wasn't -- "A12345678" passed through unchanged and the
digits-only pattern rejected it, stalling the field update.

## Root cause

`backend/utils/field_validator.py::normalize_value` gated on
`field.get("format_preset")` -- the TOP-LEVEL key. But the schema
(form-kits/i-90/schema.json) and the FormField model nest it under
`validation.format_preset`. So for a field shaped like the real schema, the lookup
returned `None`, the digit-preset branch never ran, and normalization silently
no-op'd.

The production WS path (`validation_handler.py`) happened to FLATTEN
`validation.format_preset` to a top-level `format_preset` before calling
`normalize_value`, so it worked there -- which is why the bug was intermittent
(it bit any caller that passed a raw schema / FormField-shaped dict instead of the
flattened one).

Why it shipped: every pre-existing a_number test used a fixture with a TOP-LEVEL
`format_preset` (the already-working flattened shape), so none exercised the nested
schema shape that actually fails.

## What shipped

- **`backend/utils/field_validator.py`** -- added `_resolve_format_preset(field)`:
  reads `validation.format_preset` (canonical; tolerant of `validation` being a
  dict OR a Pydantic model) with a top-level fallback for callers that pre-flatten.
  `normalize_value` now uses it, so normalization runs regardless of which dict
  shape the caller passes. (The `validation_handler` flattening is now
  belt-and-suspenders -- harmless, left in place.)
- **`backend/tests/unit/test_field_validation_responses.py`** -- new
  `TestANumberNestedFormatPreset` class: parametrized cases on a schema-shaped
  field (nested `validation.format_preset`) proving "A12345678" -> "12345678" and
  validates, PLUS a test that loads the REAL i-90 schema field and asserts the same
  (with a guard confirming the schema really nests it). This closes the coverage
  gap that let the bug ship.

## Audit (exit criterion 3)

Checked every other `format_preset` reader for the same top-level-vs-nested
assumption:
- `services/ai_context.py:67` -- reads `validation["format_preset"]` (nested). OK.
- `services/manifest_service.py:202` -- reads `validation["format_preset"]`. OK.
- `services/validation_handler.py:197` -- reads `validation.format_preset`
  (canonical) and flattens it for the legacy reader. OK.
`field_validator.py::normalize_value` was the ONLY reader with the wrong
assumption.

## Verification

- `normalize_value` on the real i-90 A-Number field: "A12345678" -> "12345678"
  (was unchanged before the fix); pre-flattened dicts, uscis_account punctuation
  strip, and non-preset passthrough all still correct.
- Validation test file: 34 passed (5 new).
- No SyntaxWarning (reworded a docstring that contained a bare `\d`); ASCII-clean.

## Doc freshness

`docs/standards/validation-delegation.md` tracks `field_validator.py`. The fix is a
bug fix to existing behavior (format_preset resolution), not a contract/behavior
change the doc describes, so no current-state update is needed; reviewed and left.

## Files touched

- `backend/utils/field_validator.py` -- `_resolve_format_preset` + `normalize_value`.
- `backend/tests/unit/test_field_validation_responses.py` -- `TestANumberNestedFormatPreset`.
