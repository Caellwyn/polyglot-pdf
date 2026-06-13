---
date: 2026-06-12
bead: polyglot-pdf-34wc
beads: [polyglot-pdf-34wc, polyglot-pdf-2ip6]
title: "read_only fields are locked to the AI; locked-field message names the field once + fits the lock kind"
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

3. (Folded in: **polyglot-pdf-2ip6**, fresh-eyes finding 1.) The guidance in the
   `completion_message` now fits the lock kind, PER FIELD. The original single
   fixed suffix ("...until the prerequisite fields are completed.") is correct for
   a dependency-gated field but wrong for a read_only one -- a read_only field has
   no prerequisite, so that instruction would send the model chasing upstream
   fields that don't exist. A first attempt branched the whole message on an
   `allReadOnly` flag, but fresh-eyes round 2 caught that a MIXED batch (one
   read_only + one dependency-gated field in the same `field_update`) would still
   mis-guide the read_only field (`allReadOnly` false -> blanket prerequisite
   suffix). The final form drops the blanket suffix entirely: each locked field's
   sentence carries its own directive -- read_only -> "It is system-managed and
   cannot be filled; do not attempt to fill it again."; dependency-gated -> "Do
   not attempt to fill it again until the prerequisite is completed." (the reason
   already names the trigger field). A mixed batch is now correct field-by-field.
   This bug only became reachable for read_only fields because of fix #1 (the
   gate), so it belonged in the same change.

Four regression tests added to `webFormConnection.aivalidation.test.ts`:
read_only fill routes to `completion_message` (not the dead `dependency_error`)
AND the value does not land (onFieldUpdate never fires for it -- proving the gate
rejects it, not just that a message was sent); the spoken name appears exactly
once and the guidance is read-only-appropriate (no "prerequisite", contains
"system-managed"); the rejected value never leaks back (PII-safe); and a MIXED
batch (read_only + dependency-gated in one update) gives each field its own
correct directive (the read_only sentence carries "system-managed" and NOT
"prerequisite").
