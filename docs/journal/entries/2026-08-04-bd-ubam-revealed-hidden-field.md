---
date: 2026-08-04
beads: [polyglot-pdf-ubam]
tags: [navigation, voice, conditional-visibility, completion, validator-cost]
surfaces: [frontend/src/navigation.ts, frontend/src/webFormConnection.ts, frontend/src/schema-forms/state/schemaFormState.ts, frontend/src/schema-forms/utils/validation.ts]
---

# Seven copies of one predicate, and the field that fell through all of them

## The shape

`shouldShowField` returns `!field.hidden` **only** when a field has no
`show_if`. With a *satisfied* `show_if` it returns the condition's result -- the
static `hidden` flag stops mattering. That is deliberate: `FieldRenderer` calls
`shouldShowField` alone, so a `hidden: true` field whose condition is met
**renders**, and `isSectionValid` **requires** it.

Seven call sites had each independently written the visibility test as
`field.hidden || !shouldShowField(...)`. For every other field that extra term is
a no-op -- which is exactly why it survived so long. For this one shape it
inverts the answer.

| Site | What it broke |
|---|---|
| `navigation.ts` `isFormComplete` | form reads COMPLETE with the field empty |
| `navigation.ts` `computeNextField` (x2) | never offered as the next field |
| `navigation.ts` `resolveLivePin` | a pin on it dropped as "stale" |
| `navigation.ts` `getFormProgress` | unfiltered denominator (dead code) |
| `webFormConnection.ts` `handleFieldUpdate` | reported to the model as unavailable |
| `webFormConnection.ts` `switch_field` | refused with `reason: 'hidden'` |
| `schemaFormState.ts` `suggestNavigationCandidates` | omitted from suggestions |

## Two user-visible bugs

**(a) False completion.** `isFormComplete` skipped the field, so the form
declared itself done with a visibly empty **required** field on screen. As of
PR #539 that also costs money: completion fires the now-default-ON end-of-form
pro validator (~$0.0093/call) against an incomplete snapshot -- and would burn
one of the two runs `polyglot-pdf-nvqr` intends to allow.

**(b) Unreachable by voice.** Every navigation path refused it. In a voice-first
product this is the worse half: a required question the user could not answer the
intended way, on a field sitting visible on their screen. Combined with (a),
voice would report the form complete while the web UI showed an empty required
field.

Dormant today -- no shipped kit uses `hidden` + `show_if` together -- hence a
synthetic fixture. It goes live the first time a kit author adds a
conditionally-revealed field that is also statically hidden, which is a natural
thing to author and nothing warns against.

## The fix

All seven call `shouldShowField` **alone**. The real fix is in its docstring:
the "call this ALONE, never add a `hidden` check" warning now lives at the one
place someone would reach to re-add the term. Seven correct-looking copies of a
predicate is not redundancy, it is seven chances to diverge -- and three
different answers were live in one tree at once.

`getFormProgress` has no production caller (test-only) but was aligned rather
than deleted or left as a third divergent progress formula.

## Test-authoring note: the pin test was vacuous on first write

`expect(computeNextField(pinnedState)?.id).toBe("revealed")` passed **with the
bug reintroduced** -- because `computeNextField`'s PRIORITY-2 scan returns that
field anyway, pin or no pin. The assertion never touched the code path it named.

Caught only by mutation-testing it. The rewrite adds an earlier competing empty
field so the scan has a *different* answer, and asserts both directions: without
the pin the scan returns `early`; with it, `revealed`. Now the pin path is the
only thing that can produce the expected result.

That is the third vacuous-or-spelling-pinned test found in two days (see
`2026-08-03-bd-3t3l...`). The pattern: **a test that passes both with and
without the fix is worse than no test**, because it converts "untested" into
"falsely confirmed." Mutation-testing each new assertion is the only reliable
way to tell the difference, and it takes seconds.

**And the same review caught the lesson only half-applied.** The first cut of
this fix mutation-tested the five *pure-function* sites but left the two
**WebSocket** sites -- `handleFieldUpdate`'s availability gate and the
`switch_field` handler -- with no assertion at all. Reverting either left the
whole 1236-test suite green. Those two are precisely the "unreachable by voice"
half of the bug, so the untested sites were the ones that mattered most to the
product.

The gap had a structural cause worth naming: the pure functions are trivially
callable, so they attract tests, while the WS gates need a mock socket and a
driven message. **Ease of testing had quietly decided what got tested.**
`webFormConnection.revealedhidden.test.ts` now drives both through the real
message path (not by calling private methods, so it survives a refactor), and
both mutations are caught.

## Lessons

1. **A term that is a no-op for every case but one is the most durable kind of
   bug.** `field.hidden ||` looked redundant-but-harmless at all seven sites, so
   nobody questioned it -- and it was, until the one shape where it inverted the
   answer.
2. **When N call sites answer the same question, the predicate belongs in one
   place and the warning belongs in its docstring.** Fixing seven copies without
   documenting *why* the obvious-looking extra check is wrong just resets the
   clock.
3. **Mutation-test every new assertion, including the ones that look trivially
   correct.** The vacuous pin test read perfectly and proved nothing.
