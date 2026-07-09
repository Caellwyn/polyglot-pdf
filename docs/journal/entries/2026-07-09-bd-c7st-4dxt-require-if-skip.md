---
date: 2026-07-09
bead: polyglot-pdf-c7st
also_closes: polyglot-pdf-4dxt
title: "Enforce require_if + force-skip for required fields"
tags: [schema-forms, validation, ui]
---

## Trigger

Codex flagged on the P6.2 PR (#346) that `require_if` (target-side conditional
required-ness) was DEFINED and unit-tested (`isFieldRequired` in validation.ts)
but never wired into the runtime -- the section-validity gate read the STATIC
`field.validation?.required`, so every conditionally-required field (f1040
designee name/phone/pin when "allow" is yes; w7 treaty fields) was never insisted
on. The maintainer directed wiring it up in its own bead, PAIRED with a
skip-placeholder: a required field must stay force-skippable (the user may defer
to a translator or have no answer), or enforcing it would trap them.

## Design decision (maintainer, 2026-07-09)

The "required but intentionally not answered" state is a SEPARATE `skipped`
boolean flag on `FieldValue` -- NOT a sentinel value string. The `value` stays
empty; the flag is the marker. A skipped required field (1) satisfies the
required gate, (2) renders visibly distinct ("Skipped -- needs follow-up", not
blank/falsely-complete), (3) fills BLANK on the PDF. Ship c7st + 4dxt together.
Rationale: separates "no value yet" from "deliberately skipped" and removes any
real-answer-vs-magic-word collision.

## Change

- **c7st:** `SchemaFormStateManager.isSectionValid` now evaluates required-ness
  via `isFieldRequired(field, fieldValues, fields)` (honors `require_if`) instead
  of the static flag, and only requires a field that is currently SHOWN
  (`shouldShowField`) -- a `require_if` on a `show_if`-hidden field can never be
  filled, so it must not block. A skipped field short-circuits as satisfied.
- **4dxt:** `FieldValue.skipped` flag + `SchemaFormStateManager.markFieldSkipped`
  (sets `skipped: true`, empty value, confirmed). SectionRenderer shows a "Skip
  for now" button under a shown/required/empty/not-yet-skipped field, and a
  "Skipped -- needs follow-up" badge once skipped. Styled in schema-form.css.
  PDF-fill needs no change: a skipped value unwraps to `null` and the backend
  filler skips `null`/`""`.

## Blast radius / what is NOT changed

`isSectionValid`'s only runtime consumer is the manual "Next section" button gate
(`SchemaForm.tsx`). The **voice apply-gate is untouched** -- it still reads the
static `validation?.required` (webFormConnection ~L1594), so c7st does not widen
the pre-existing "voice cannot skip a required field" gap. Wiring an AI "skip" of
a required field to `markFieldSkipped` is split to **bd polyglot-pdf-7yra** (it
needs an SI/tool-contract design decision on HOW the model signals a skip).

## Verification

8 new `isSectionValid`/skip tests in `schemaFormState.test.ts`: static-required
enforcement, `require_if` enforcement (required only when the condition holds),
skip satisfies the gate, skip keeps the value empty + marks confirmed, a real
value after a skip drops the flag, and a hidden required field does not block.
tsc clean; full frontend suite 47 files / 814 tests green.
