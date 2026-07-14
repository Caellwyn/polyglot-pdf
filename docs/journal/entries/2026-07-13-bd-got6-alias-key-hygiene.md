---
date: 2026-07-13
bead: polyglot-pdf-got6
title: "Fix []-alias migration leaving a stale steered/value entry (updateField)"
sprint: 12
tags: [refactor, testing]
---

## Trigger

Surfaced by the W4 (bd polyglot-pdf-ny4s) Opus outer review as a PRE-EXISTING
defect (filed, not fixed inline, to keep W4 scoped). A field's value can migrate
between the `[]`-alias key variants (Gemini inconsistently adds/drops the trailing
brackets): stored under `field-1`, later re-written under `field-1[]`, or
vice-versa. `SchemaFormStateManager.updateField` wrote the new FieldValue under the
LITERAL incoming key but left the OLD entry -- with its stale value AND stale
`steered:true` marker -- in place under the other variant. Both keys then coexisted
in `fieldValues`.

The consequence bit W4's re-arm: `buildValidatorFields`'s `valueFor` reads the exact
schema-id key FIRST and only falls back to the `[]`-variant when it is absent. After
a migration the exact key could hold the STALE entry, so the validator payload
carried the old value + `steered:true` -- NOT the corrected, re-armed value under the
other variant. A correction did not actually re-enter the validator net.

## What shipped

`updateField` now removes the stale variant on a cross-variant migration, so exactly
ONE entry represents the field:
- Capture WHICH key the prior entry lived under (`priorKey`: the exact `fieldId` if
  present, else the `[]`-alias variant). This reuses the alias resolution already
  there for the steered-carry/re-arm read.
- After writing the new value under the incoming `fieldId`, if `priorKey` differs
  from `fieldId`, `delete` the stale key from the new `fieldValues` map.

A same-key rewrite (the common case) has `priorKey === fieldId`, so the cleanup
never fires -- normal edits are untouched.

## Lessons

An alias/dual-key scheme needs a single WRITE canonicalization point, not just
alias-aware READS. This code had alias-aware reads everywhere (markFieldsSteered,
the W4 prior-value read, valueFor) but the write always keyed the literal incoming
id, so a migration silently created a second entry the reads then had to
disambiguate -- and one reader's exact-key-first preference picked the wrong one.
Removing the stale key at the write is simpler and more robust than making every
reader migration-aware.

## Doc freshness

No doc change: this is an internal write-path invariant (one entry per field), not a
wire contract or documented behavior. The validation-delegation.md `steered`/re-arm
note (W4) already describes the intended behavior this fix restores.

## Files touched

- frontend/src/schema-forms/state/schemaFormState.ts -- `updateField` drops the
  stale variant key on a cross-variant migration (+ `priorKey` capture).
- frontend/src/schema-forms/state/schemaFormState.test.ts -- 3 got6 regression tests
  (forward migration, reverse migration, same-key rewrite is untouched).
