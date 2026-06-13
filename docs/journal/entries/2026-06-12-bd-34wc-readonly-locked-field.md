---
date: 2026-06-12
bead: polyglot-pdf-34wc
title: "read_only fields are locked to the AI; locked-field message names the field once"
tags: [bugfix, frontend, webFormConnection]
---

## Trigger

Fresh-eyes filed this during the z6xs review: the z6xs fix removed the
duplicated field name only from the `hidden`-field fallback in
`webFormConnection.ts`. The `read_only` path in `evaluateFieldAvailability`
(`conditionalFieldCheck.ts`) still returned `"The field 'X' is read-only..."`,
which -- composed with the `"Cannot update 'X': "` prefix -- printed the field
name twice.

## What I found (scope expanded in service of the bead)

The duplication couldn't even fire. The locked-field gate in
`webFormConnection.ts` was:

    const isAvailable = !field.hidden && shouldShowField(field, fieldValues);

`shouldShowField` checks `hidden` + `show_if` only -- it never consults
`read_only`. So a visible `read_only` field evaluated `isAvailable = true`,
skipped the locked branch, and the AI value flowed into
`applyAiValueWithValidation` -- i.e. **the AI could write a read_only field**,
a worse bug than the message wording. The `read_only` `lockedReason` was dead
code from this consumer's view. The bead's exit criterion ("a read_only field's
message names it once") is only meaningful if read_only fields actually reach
the locked path, so fixing the gate is a prerequisite, not scope creep.

## What shipped

1. `webFormConnection.ts` gate now also calls `isFieldReadOnly(...)` (an existing
   but previously-unused helper in `validation.ts`), so a read_only field is
   treated as locked and reported back to the model instead of being written.
2. `conditionalFieldCheck.ts` `read_only` `lockedReason` is now a name-FREE
   clause (`'it is read-only and cannot be modified.'`), mirroring the z6xs
   `hidden` fallback. Composed with the prefix it reads
   `Cannot update 'Case Number': it is read-only and cannot be modified.` --
   the name once.

`webFormConnection.ts` is the only non-test consumer of
`evaluateFieldAvailability`, so dropping the name from the reason is safe.

Three regression tests added to `webFormConnection.aivalidation.test.ts`:
read_only fill routes to `completion_message` (not the dead `dependency_error`),
the spoken name appears exactly once, and the rejected value never leaks back
(PII-safe).
