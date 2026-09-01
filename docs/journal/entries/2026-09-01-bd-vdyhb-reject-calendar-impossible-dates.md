---
date: 2026-09-01
bead: polyglot-pdf-vdyhb
title: "fix(schema-forms): validateDateValue accepts calendar-impossible dates"
tags: [frontend]
---

## Trigger

`validateDateValue` (`frontend/src/schema-forms/utils/validation.ts`)
accepted calendar-impossible dates like Feb 30 or Apr 31. Root cause: the
function's first gate is `new Date(value)` / `isNaN(dateValue.getTime())`
-- but the JS `Date` constructor ROLLS an out-of-range day over into the
next month instead of returning `NaN`:

    new Date("02/30/2020")  -> 2020-03-01 (not NaN)
    new Date("2020-02-30")  -> 2020-03-01 (not NaN)
    new Date("04/31/2020")  -> 2020-05-01 (not NaN)

So a hand-typed impossible date passed the client gate and could land in
`sessionStorage` / the PDF, while the SAME value from the voice model was
rejected server-side: the backend's `_validate_date`
(`backend/utils/field_validator.py:331`) uses
`datetime.strptime`, which raises on Feb 30. A genuine FE/BE divergence.

Note: month-out-of-range (e.g. month 13) was already caught by `new
Date()` itself -- verified empirically (`isNaN(new
Date("13/01/2020").getTime())` is already `true`). Only DAY-overflow
within a real month needed a new guard.

## Fix

Added `daysInMonth(year, month)` (the Gregorian leap rule: divisible by 4,
except centuries unless divisible by 400) and `isValidCalendarDate(c)`.
Called from `validateDateValue` immediately, using
`parseDateComponents(value)` (already existing, from bd `polyglot-pdf-8i3rs`)
-- if the value matches one of the two recognized layouts (MM/DD/YYYY,
ISO) but fails calendar validity, reject immediately, before the
pre-existing `new Date()` check ever runs. A value in some other layout
falls through to the unchanged pre-existing behavior.

## Testing

13 new tests: the bead's four named impossible-date cases (Feb 30, Apr
31, month 13) in both layouts; a valid leap day (02/29/2020) accepted; a
non-leap-year Feb 29 (2021) rejected; the century-exception leap rule
specifically (2100 rejected, 2000 accepted); an ordinary valid date still
accepted; and an impossible date with a max bound configured still
rejected (not silently waved through by the bound-comparison branch).

Mutation-verified: removing the new early-reject gate reddens exactly the
day-overflow and leap-year-mismatch cases (month-13 cases correctly stay
green, since `new Date()` already catches those independently).
Separately mutated the leap-year rule to a simplified `year % 4 === 0`
(missing the century exception) -- reddened exactly the 2100 test, none
of the others.

Full frontend suite: ~1804 tests. `SchemaForm.previewEdit.test.tsx`
(tracked by the still-open bd `polyglot-pdf-x95xl`, "flaky under
full-suite load") failed intermittently across repeated runs, on BOTH
this diff applied and this diff stashed out -- confirmed genuinely
pre-existing and unrelated to this change (not a fixed pass/fail count;
it is a timing flake either way, and the Opus cross-surface review
independently reproduced the same non-determinism on the base state).
