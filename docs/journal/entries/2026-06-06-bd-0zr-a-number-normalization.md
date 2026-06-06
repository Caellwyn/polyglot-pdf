---
date: 2026-06-06
bead: polyglot-pdf-0zr
title: "A-Number field unfillable: normalize the 'A' prefix instead of rejecting it"
tags: [testing]
---

## Trigger

`bd polyglot-pdf-0zr`. In the demo, Gemini correctly understood and read back the
user's Alien Registration Number, the field highlighted blue, but **no value ever
entered the field**, and the session then spun in an infinite confirm/next-field
loop (the symptom tracked separately as `bd polyglot-pdf-0y7`).

## Root cause

Two parts of the app disagreed on what a valid A-Number is, making the field
**unfillable by construction**:

- Backend schema (`form-kits/i-90/schema.json`) + PDF comb field: `pattern
  ^\d{7,9}$`, `max_length 9` -- bare digits, no "A". A backend test
  (`test_a_number_with_letter_prefix_returns_error`) had even **locked in**
  rejecting the "A" prefix.
- Frontend `a_number` format_preset (`validation.ts`): `^A\d{8,9}$` -- required a
  leading "A".

These are mutually exclusive. An A-Number is spoken/written as "A" + 7-9 digits
(the field's own help text says it "begins with an 'A'"), so whatever Gemini sent
with the "A" passed the frontend but **failed the backend pattern**. On a backend
validation failure, `callback_handler` deliberately sends an EMPTY `form_state` to
the client (so invalid values never land) and returns an error to Gemini. Result:
the value never reached `fieldValues`, so `SchemaFormStateManager.confirmField`
no-op'd (it early-returns when the field has no value), `computeNextField` kept
returning the same unconfirmed field, and the frontend kept answering the
backend's confirm/next-field requests with it forever -- the loop. The blue
outline was just the next-field FOCUS highlight, unrelated to a value being set.

## What shipped

Per the maintainer's call (normalize & accept the "A"), `a_number` is now a
**normalize-then-validate** preset, with client and server agreeing on the
canonical stored form = **bare 7-9 digits** (the "A" is display sugar; the comb
field has only 9 cells, so "A" + 9 digits would not fit).

- **Backend** `backend/utils/field_validator.py`: new `normalize_value(field,
  value)` strips a leading A/a and all non-digits for `a_number`; `validate_updates`
  normalizes BEFORE validating and stores the normalized value in `form_state`.
- **Backend** `backend/services/validation_handler.py`: pass `format_preset`
  through `_convert_fields_to_dicts` (it was dropped, so normalization never ran).
- **Frontend** `validation.ts`: new exported `normalizeFieldValue` (mirrors the
  backend); `validateField` normalizes before validating; the `a_number` preset
  regex changed from `^A\d{8,9}$` to the canonical `^\d{7,9}$`.
- **Frontend** `schemaFormState.ts`: `updateField` normalizes the raw value before
  storing, so manual edits store the same canonical value AI fills do (idempotent
  for already-canonical values).
- **Tests:** replaced the now-obsolete "reject the A" backend test with a real
  (non-mocked) `TestANumberNormalization` against `validate_updates` (accepts
  A/a/dash/space-formatted input, stores bare digits, still rejects wrong digit
  counts); added a matching frontend `validation.test.ts` (16 cases).

Verification: now `A12345678`, `A-12345678`, `A 1234 5678`, `a12345678`, and bare
digits all APPLY and store canonical digits; `A1234` (too short after strip) and
overlong input are still rejected.

## Lessons

A field can be **unfillable by construction** when two validators on the two sides
of the wire encode contradictory rules for the same field -- and the failure is
invisible (the client shows a focus highlight, the value silently never lands). A
generalized rule worth keeping: **any `format_preset` must mean the same thing on
the client and the backend, and "accept what the user naturally says, store one
canonical form" beats "reject anything not already canonical."** Added a one-liner
to `docs/standards/` is NOT warranted (no such cross-cutting doc tracks validation
presets yet); captured here instead.

## Doc freshness

`docs/components/schema-forms.md` tracks `validation.ts` and `schemaFormState.ts`
and shows as STALE, but it was already stale (last updated 2026-06-01, from prior
work) and describes validation only generically ("Validation runs on blur
(`validateField`)") -- it documents neither the format_preset/normalization
contract nor the field-value-shape this change touched, so this change does NOT
make it factually wrong. Reviewed and left (bumping its date would falsely claim I
reconciled all its other untouched drift). No tier-1/2 doc tracks the
A-Number/format_preset contract specifically. Other pre-existing stale docs from
earlier 2026-06-04 backend work remain stale, independent of this change.

## Relationship to bd polyglot-pdf-0y7

The infinite confirm/next-field loop (`0y7`, blocked-by `0zr`) was a downstream
symptom of this root cause: with the value now landing and confirmation sticking,
that loop cannot recur for this reason. `0y7` additionally asks for a
cause-agnostic loop-breaker guard; that defense-in-depth is left to its own bead
(out of scope here).

## Files touched

- `backend/utils/field_validator.py` -- normalize_value + normalize-before-validate.
- `backend/services/validation_handler.py` -- pass format_preset through.
- `backend/tests/unit/test_field_validation_responses.py` -- real normalization tests.
- `frontend/src/schema-forms/utils/validation.ts` -- normalizeFieldValue + preset fix.
- `frontend/src/schema-forms/utils/validation.test.ts` -- new (16 cases).
- `frontend/src/schema-forms/state/schemaFormState.ts` -- normalize on store.
