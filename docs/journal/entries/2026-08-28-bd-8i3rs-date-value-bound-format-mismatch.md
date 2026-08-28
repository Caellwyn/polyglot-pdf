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
parse a date string against the field's declared layout (MM/DD/YYYY) or
ISO, and compare the two `{year, month, day}` results with pure integer
arithmetic -- no `Date` object, no timezone conversion, anywhere in the
comparison path. `validateDateValue`'s min/max checks now try this path
first; if either the value or the bound doesn't parse against either
layout, it falls back to the pre-existing `new Date()` comparison
unchanged (an unusual layout this narrower fix doesn't cover is no worse
off than before).

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

## Files touched

- `frontend/src/schema-forms/utils/validation.ts` -- new
  parseDateComponents/dateComponentsKey/formatDateComponents helpers;
  validateDateValue's min/max checks use them with a Date-based fallback.
- `frontend/src/schema-forms/utils/validation.test.ts` -- new test suite
  pinning the exact bug on BOTH bound directions: a max-bound case under a
  timezone west of UTC (the only direction that can wrongly reject a value
  equal to a MAX bound) and a min-bound case under a timezone east of UTC
  (the only direction for a MIN bound) -- plus same-layout and
  no-format-hint control cases. Mutation-verified per direction.
