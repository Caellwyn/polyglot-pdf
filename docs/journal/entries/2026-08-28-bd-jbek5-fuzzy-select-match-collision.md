---
date: 2026-08-28
bead: polyglot-pdf-jbek5
title: "fix(voice): fieldManager fuzzy select match collides on short PDF export codes"
tags: [voice, fieldManager]
---

## Trigger

`fieldManager.ts`'s `handleSelect` falls back to a bidirectional substring
fuzzy match when no exact option match is found. This was written when a
select's `option.value` was a long minted slug (`'wyoming'`), where
accidental containment was unlikely. Since bd `4we6j`, a select's
`option.value` is often the PDF's own short export code (`'AL'`, `'AK'`),
and short codes collide readily: `'al'` is a substring of both `'alaska'`
and `'alabama'` by TEXT containment, and the old first-hit-wins loop
silently picked whichever option came first in the DOM, writing a wrong
answer onto a legal form with no warning.

## What shipped

Two changes to `handleSelect`'s match tiers:

1. A new case-insensitive EXACT-match tier, inserted between the existing
   exact match and the fuzzy fallback: an export code equal to an option's
   value/text (ignoring case) is a real, unambiguous signal and must win
   even though it also happens to be a text substring of other options
   (`'AL'` vs. `'al'`/`'AK'`/etc).
2. The fuzzy substring tier now collects every candidate match first and
   only applies it when the match is UNIQUE. An ambiguous value selects
   nothing and logs the same "no match" warning a genuinely unmatched
   value gets, rather than silently picking the wrong option.

## Lessons

The design took one real correction: a pure "require uniqueness across
all substring matches" approach (the first draft) would have made the
fuzzy tier itself ambiguous on inputs like `'al'` (a text-substring of
both `'alaska'` and `'alabama'`), with no way to break the tie. The
case-insensitive exact-match tier fixes that class of case (an export
code that equals an option's own value/text once case-folded).

Fresh-eyes review then caught that the test file's own pinning tests
didn't prove what they claimed: the bead's headline worked example
(`'AL'` against `[AL/Alabama, AK/Alaska, CA/California]`) is satisfied
by the pre-existing case-SENSITIVE exact-match tier (`'AL' === 'AL'`),
not the new tier -- it would stay green even with the new logic deleted
entirely. Likewise the original "genuinely unique fuzzy match" test used
`'united states'` against option text `'United States'`, which is exact
match case-folded, so it never reached the tier-3 fuzzy branch at all.
Both were rewritten to use inputs that can only resolve via the tier
under test (verified by asserting on the tier-specific console.log
message, and by reordering options so a jsdom selected-index default
would read back as the WRONG state), and both were mutation-verified
again after the rewrite. Lesson: a pinning test for tier N must be
constructed so it cannot be secretly satisfied by tier N-1 or an
environment default -- assert on the tier's own log line, not just the
final value, whenever multiple code paths could produce the same
answer.

## Files touched

- `frontend/src/shared/fieldManager.ts` -- new case-insensitive exact-match
  tier; fuzzy substring tier now gated on match uniqueness.
- `frontend/src/shared/fieldManager.selectFuzzyMatch.test.ts` -- new test
  file: the exit criterion's exact scenario, case-insensitivity (tier-2
  specific, log-asserted), ambiguous collision (both option orders),
  genuine-unique-fuzzy-match (tier-3 specific, log-asserted), exact-match
  precedence, and the unchanged clear path. Mutation-verified per tier.

## Follow-up

`handleRadioGroup` and `handleCheckboxGroup` (same file) have the
identical bidirectional-substring collision bug, left unfixed here since
it's out of this bead's stated scope (`handleSelect` only) -- filed as
`polyglot-pdf-1kd39`.
