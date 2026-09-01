---
date: 2026-08-31
bead: polyglot-pdf-c6t0e
title: "fix(frontend): fieldManager badges/reports success only on an actual match"
tags: [frontend, fieldManager]
---

## Trigger

`applyUpdates` set `data-vff-confirmed`, added the green checkmark badge,
and pushed the field into `results.success` UNCONDITIONALLY whenever an
element was resolved -- it never consulted whether the type-specific
handler (`handleSelect`, `handleSingleRadio`) actually applied a value.
When a select had no matching option (or, since bd `polyglot-pdf-jbek5`,
an ambiguous fuzzy match that deliberately selects nothing), the field was
left EMPTY but still decorated as AI-confirmed -- a misleading signal on a
legal intake form.

## Enumerate the set (CLAUDE.md scar tissue #7)

The bead named `handleSelect` and "the sibling radio/checkbox handlers."
Reading `applyUpdates` end to end found the actual set was structurally
TWO different bugs, not one:

1. **`handleSelect` and `handleSingleRadio`** both fall through to
   `applyUpdates`'s single blanket "if (element)" badge block, which never
   checked their outcome. `handleSingleRadio` additionally never applied
   its OWN badge on a real match either (unlike `handleRadioGroup`), so it
   depended entirely on that blanket block even in the success case.
2. **`handleRadioGroup` and `handleCheckboxGroup`** never reach that
   blanket block at all (their call sites `continue` immediately after) --
   they each had their OWN separate unconditional `results.success.push`
   in `applyUpdates`. For `handleRadioGroup` specifically this was
   arguably a WORSE variant: since `handleRadioGroup` only badges
   internally on a real match, a totally-unmatched radio group reported
   *success* while getting *no badge at all* -- neither the (wrong) green
   confirmation nor an honest failure signal reached the console summary.

Both classes needed fixing, at four call sites total, not one.

## What shipped

- `handleSelect`, `handleSingleRadio`, `handleRadioGroup`, and
  `handleCheckboxGroup` all now return `boolean` (previously `void`),
  reporting whether a value was actually applied. A clear (empty
  `newValue`) counts as handled for all four -- that is the AI's genuine
  intent, not a failed match.
- `applyUpdates`'s blanket badge block now gates on a new `matched`
  variable, set from `handleSelect`/`handleSingleRadio`'s return (and
  defaulted `true` for checkbox-toggle and plain text/textarea writes,
  which always do exactly what was asked and cannot silently fail to
  match).
- The two group-handler call sites now branch on their return value:
  `results.success` only on an actual match, `results.notFound` otherwise
  (previously always `results.success`, unconditionally).
- `handleCheckbox` and the plain text/textarea write path are UNCHANGED --
  neither can silently fail to apply the requested value the way a select
  or radio can (a checkbox toggle always sets exactly the boolean it was
  told to; a text write always writes the string verbatim), so they are
  not the same bug class.

## What's still out of scope

`handleCombobox` has the identical unconditional-success shape at its own
call site in `applyUpdates`, and its own body already admits "Combobox
filling not fully supported yet" -- it never reliably applies anything.
Left untouched: this is the bead's own stated scope (select + radio/
checkbox siblings only), and combobox filling is a materially different,
already-known-broken code path that deserves its own bead rather than a
drive-by partial fix here. Filed as `polyglot-pdf-az12y` (found by the
Opus cross-surface review, which also confirmed its premise against the
code rather than trusting this note).

Two more follow-ups filed during the review round, both pre-existing and
out of this bead's scope: `polyglot-pdf-lee9q` (the checked-in
`bookmarklet.bundle.js` build artifact is many beads stale against
`frontend/src/shared`, missing the `jbek5` fuzzy-match fix entirely, and
will not contain this bead's fix either) and `polyglot-pdf-gwnvs`
(`aiUpdatingFields` is never released on the group/combobox/not-found
`continue` exits, or on `destroy()` -- the same guard-leak shape as
`pg0m6`, just on different branches this bead didn't touch).

## A latent guard-lifetime inconsistency (bd polyglot-pdf-pg0m6), and getting the pinning test wrong twice

The Opus cross-surface review found the new no-match branch cleared
`aiUpdatingFields` SYNCHRONOUSLY, while the matched branch (unchanged by
this diff) defers the same clear by 50ms with the comment "allow events to
settle" -- because `handleSelect`/`handleSingleRadio` dispatch `change`/
`input` events, and `setupEditListener`'s `handleEdit` (registered on
`change`) is the only thing standing between an AI-dispatched event and a
false "manual edit" report. Applied the same 50ms deferral to the no-match
branch for consistency.

**First attempt at pinning it was wrong.** I asserted `onManualEdit` isn't
called after `applyUpdates` dispatches its OWN `change` event on the
no-match select -- but mutating the fix back to synchronous did NOT redden
that test. I concluded (wrongly) that no jsdom test could distinguish the
two orderings, since `dispatchEvent` is synchronous and `handleEdit`
always runs and returns early before either clear takes effect -- and
shipped a comment-only note instead of a test, per CLAUDE.md's
test-the-tests rule (better no test than a vacuous one).

**The Opus cross-surface re-review round caught that this reasoning
itself was wrong.** The actually-distinguishing case isn't the dispatch
*inside* `applyUpdates` -- it's a SECOND, LATER `change` event landing
after `applyUpdates` returns (a controlled re-render, or a genuinely
coincident user interaction in the same tick). With a synchronous clear,
`aiUpdatingFields` is already empty by then, so that second event IS
misread as manual; with the deferral, the guard is still up. Rewrote the
test to dispatch that second event and re-verified: it passes on the fix
and reddens on a synchronous-clear mutation (confirmed independently by
the reviewer with the identical test shape before I even wrote mine).

Two lessons stacked here: my own "untestable" conclusion needed the same
adversarial scrutiny as any other claim, and the review loop is what
caught a wrong negative (concluding a real bug can't be pinned) rather
than the more usual wrong positive (a vacuous test that looks like
coverage). Corrected the code comment to say the misfire is reachable
today, not merely hypothetical.

## A second regression from the fix itself (round 3): the manual-edit listener moved with the badge

A third review round found that hoisting the badge/success logic behind
`matched` had an unintended side effect: `setupEditListener` -- the call
that registers the `change`/`blur` listener `handleEdit` checks before
treating an edit as manual -- lived INSIDE the same `if (element &&
matched)` block. So a no-match fill now left the field with NO listener
at all, not just no badge.

That matters because `setupAllFieldListeners` (run once at
`createFieldManager` construction) only finds elements already in the DOM
at that moment; `SchemaForm` renders one section at a time, so for any
field not yet rendered when the manager was constructed, the call inside
`applyUpdates` is that field's ONLY chance to ever get a listener. Losing
it on a no-match fill means a later genuine manual correction on that
field would be silently dropped -- `onManualEdit` never fires, so the
correction never reaches `SchemaFormStateManager` or the AI. That is
arguably worse than the badge bug this whole change exists to fix: not a
misleading signal, but a real user action vanishing with no signal at
all.

Fixed by hoisting `setupEditListener` above the `matched` split so it
runs whenever `element` resolves, regardless of match outcome (matching
its pre-existing, correct behavior) -- badging and listener-attachment
are orthogonal concerns that had been coupled by accident. New test
constructs the manager before the field exists in the DOM (mirroring a
later-rendered section), fires a no-match update, then a genuine manual
edit past the guard window, and asserts `onManualEdit` still fires.
Mutation-verified: reverting the hoist (moving the call back inside the
matched branch) reddened exactly that one new test.

## Testing

New file `fieldManager.confirmOnMatch.test.ts`, 11 tests: a genuine match
(select / single radio / radio group / checkbox group) gets the badge and
reports success; a total non-match, an ambiguous fuzzy match, a radio
value-mismatch, an unmatched radio group, and an unmatched checkbox group
each get NO badge and report `notFound` instead of `success`; a same-tick
later `change` event after a no-match fill does not misfire
`onManualEdit` (bd `pg0m6`); a no-match fill on a field not yet in the DOM
at construction still gets its manual-edit listener attached, so a later
genuine correction is not silently dropped.

Mutation-verified in three rounds (matching the three distinct bugs
found): reverting the blanket-block gate (`if (element && matched)` ->
`if (element)`) reddened exactly the 3 select/single-radio badge tests;
reverting the two group-handler call sites to their old unconditional
`results.success.push` reddened exactly the 2 unmatched-group tests;
reverting the guard-clear deferral to synchronous reddened exactly the
`pg0m6` test; reverting the listener hoist back inside the matched branch
reddened exactly the round-3 listener test. Every mutation left the other
tests green. Restored all four and re-confirmed the full
`frontend/src/shared` suite green (270 tests).

## Files touched

- `frontend/src/shared/fieldManager.ts` -- 4 handlers now return `boolean`;
  `applyUpdates` gates the badge block and both group-handler success
  pushes on the actual match outcome; the no-match branch's guard-clear
  deferral matches the matched branch's; `setupEditListener` hoisted above
  the match split.
- `frontend/src/shared/fieldManager.confirmOnMatch.test.ts` -- new, 11 tests.
