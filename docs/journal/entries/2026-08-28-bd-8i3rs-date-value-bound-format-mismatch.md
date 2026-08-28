---
date: 2026-08-28
bead: polyglot-pdf-8i3rs
title: "fix(schema-forms): validateDateValue mixes UTC and local date parsing across a value/bound format split"
tags: [schema-forms, date-validation, timezone]
---

## Trigger

`validateDateValue` (frontend/src/schema-forms/utils/validation.ts) compared
a date value and its min/max bound via two `new Date()` calls, with no
regard for the two strings' different formats. Per the ECMAScript spec,
`new Date("2007-10-13")` (ISO, date-only) parses as UTC midnight while
`new Date("10/13/2007")` (slash form) parses as LOCAL midnight -- so a kit
whose value is authored MM/DD/YYYY but whose bound is authored ISO could
reject a value exactly equal to the bound, in any timezone west of UTC.
Latent today (no shipped kit combines a MM/DD/YYYY `help.format_hint` with
an ISO min/max bound), but newly plausible now that DateField renders a
text input honoring the kit's own layout (bd md20o) instead of forcing ISO.

## What shipped

Added `parseDateComponents`/`dateComponentsKey`/`formatDateComponents`:
parse a date string as either MM/DD/YYYY or ISO -- tried UNCONDITIONALLY,
not gated on the field's declared format (see below) -- and compare the
two `{year, month, day}` results with pure integer arithmetic; no `Date`
object, no timezone conversion, anywhere in the comparison path.
`validateDateValue`'s min/max checks now try this path first; if either
the value or the bound doesn't parse against either layout, it falls back
to the pre-existing `new Date()` comparison unchanged (an unusual layout
this narrower fix doesn't cover is no worse off than before).

Deliberately narrower than the backend's `_resolve_date_format` (which
also handles prose hints and a longer layout list): this covers only the
MM/DD/YYYY-vs-ISO case the bug and its exit criteria describe, not a full
port of the backend's format-resolution chain.

## Lessons

**A test parametrized over "both directions" can still be vacuous in one
direction, and only mutation-testing the specific case catches it.** The
first draft ran the SAME max-bound test under both a west-of-UTC and an
east-of-UTC timezone, since the exit criterion asked for "both east and
west." But the max-bound bug only manifests west of UTC (a positive local
midnight offset pushes the slash-form value's UTC instant later than the
ISO bound's); the mirror-image east-of-UTC failure only shows up on a
MIN bound, which had no test at all. The east-of-UTC max-bound test
therefore passed whether or not the fix existed -- a green assertion, but
not a pin. Fresh-eyes review caught this by mutating the new parsing
helper and observing that only 1 of the 2 "both directions" tests actually
reddened. Fixed by adding a genuine min-bound test pair under
east-of-UTC, and re-scoping the max-bound test to west-of-UTC only (with
a comment explaining why an east-of-UTC max-bound assertion would itself
be vacuous). Mutation-verifying confirmed both directions now redden
independently.

**Gating the fix on the field's OWN declared format missed the one real
field it needed to cover.** The first cross-surface-reviewed draft only
tried the MM/DD/YYYY parse when the field's declared layout (checked via
`help.format_hint`, then widened to also check the flat `format` key)
was literally "MM/DD/YYYY" -- reasoning that a field declaring ISO would
only ever hold ISO values. That's false: `DateField` renders a plain text
input with no format coercion (bd md20o), so a slash-form value can reach
a field whose SCHEMA says ISO. The one bounded date field the product
actually ships (`adult_intake_demo_schema.json`'s `dob`) declares
`format: "YYYY-MM-DD"` -- so a slash-form `dob` value still reproduced the
exact bug through two review rounds, caught only when the Opus
cross-surface reviewer traced the fix out to that real schema file and
executed it against the real field shape rather than a synthetic one.
Fixed by dropping the declared-format gate entirely: `parseDateComponents`
now tries BOTH layouts unconditionally on any string, since the two
patterns are structurally unambiguous (slashes vs. dashes). Re-verified
by pinning the real `dob` field shape directly and mutation-testing it.

Three narrow, non-blocking observations from the round-2 cross-surface
pass were filed as separate beads rather than folded in here (out of this
bead's scope): impossible calendar dates like Feb 30 parse without
rejection on both the old and new code paths (`polyglot-pdf-vdyhb`); a
DD/MM/YYYY-declared field would be misread as MM/DD/YYYY, since this fix
only recognizes the one slash layout (`polyglot-pdf-mul28`); and the
comment referencing removed code, fixed directly in this same PR since it
touched lines already in flight rather than left as `polyglot-pdf-5n59m`.

## Files touched

- `frontend/src/schema-forms/utils/validation.ts` -- new
  parseDateComponents/dateComponentsKey/formatDateComponents helpers;
  validateDateValue's min/max checks use them with a Date-based fallback.
- `frontend/src/schema-forms/utils/validation.test.ts` -- new test suite
  pinning the exact bug on BOTH bound directions: a max-bound case under a
  timezone west of UTC (the only direction that can wrongly reject a value
  equal to a MAX bound) and a min-bound case under a timezone east of UTC
  (the only direction for a MIN bound), plus a direct pin against the real
  `adult_intake_demo_schema.json` `dob` field shape (flat `format` key, no
  `help.format_hint`) with a slash-form value -- plus same-layout and
  no-declared-layout control cases. Mutation-verified per case.
