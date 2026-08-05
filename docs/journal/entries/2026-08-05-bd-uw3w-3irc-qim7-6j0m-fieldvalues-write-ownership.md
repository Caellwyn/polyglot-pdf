---
date: 2026-08-05
beads: [polyglot-pdf-uw3w, polyglot-pdf-3irc, polyglot-pdf-qim7, polyglot-pdf-6j0m, polyglot-pdf-tare, polyglot-pdf-6iwn]
tags: [frontend, schema-forms, state, voice, testing, flake]
surfaces:
  - frontend/src/schema-forms/utils/fieldValue.ts
  - frontend/src/webFormConnection.ts
  - docs/components/schema-forms.md
---

# One owner for `fieldValues`, and a test flake that fixed itself

Four beads. Three were one problem wearing three hats; the fourth turned out to
be already fixed by a merge that landed the day before.

## The real problem: two writers, no arbiter

`fieldValues` has two independent writers. `SchemaForm.tsx` (`handleFieldChange` /
`handleFieldSkip`) persists through `SchemaFormStateManager` and never touches
`WebFormConnection`'s in-memory `this.state`. The voice layer holds `this.state`
across turns. Any connection handler ending in `save(this.state)` therefore
persists its in-memory copy over whatever the UI wrote since the last sync.

An earlier fix (bd `pjws`) added a refresh to the confirm and skip handlers, but
merged the maps with a raw key union:

    fieldValues: { ...persistedAtEntry.fieldValues, ...this.state.fieldValues }

That makes the in-memory side win *unconditionally*. The author knew and said so
in the comments -- it was deliberately conservative, chosen so a language fix
would not also change which field VALUE wins, with the residue filed as these
three beads. So this work was picking up a hand-off, not correcting a mistake.

Three consequences, one root cause:

- **`uw3w`** -- a value the user CLEARED on screen was revived by a later
  `confirm_field`, and marked confirmed, so it never re-prompted and printed on
  the PDF. The opposite direction also failed: a value the user TYPED was masked
  by a stale in-memory empty, the skip handler's already-filled guard passed, and
  `markFieldSkipped` blanked a real answer.
- **`3irc`** -- a key union re-adds an `[]`-alias key that `updateField`
  deliberately DELETED on migration, so two live entries represented one field,
  breaking the `got6` one-entry invariant.
- **`qim7`** -- `handleSessionReady` never refreshed at all before three
  `save()`-ing mutators (`setSessionId` / `setJitMode` / `setContinuousSession`),
  so a routine reconnect persisted stale state over a concurrent UI write.

## The fix

One helper, `reconcileFieldValues`, called at all three handlers. It resolves
**per logical field** rather than per raw key: newer `lastModified` wins, a
stamped entry beats an unstamped one, `[]`-alias variants collapse into a single
decision (so a union can never resurrect a deleted variant), and an entry present
on only one side is kept -- which is what preserves the in-memory-only case the
original merge existed to protect.

`lastModified` turned out to be designed for exactly this: its type comment reads
"Timestamp for conflict resolution." Worth noting `confirmField` deliberately does
NOT stamp it, and that is correct -- confirming changes only confirmation metadata,
never the value, so the value's timestamp must stay put.

### The tie that mattered

The new tests passed alone and failed as a file, with the failing test changing
between runs. The cause was not shared state: `Date.now()` has millisecond
resolution, coarser than the gap between an AI write and the on-screen edit that
follows it, so both writes landed in the SAME millisecond and the tie-break
decided the winner.

That is a real production case, not a test artifact -- and the first
implementation resolved ties toward in-memory, i.e. toward the stale side in
exactly the scenario these beads are about.

The first correction used "meaningful entry wins" (the `readFieldEntryWithAlias`
precedent). **The pre-PR fresh-eyes review caught that this only fixes half the
problem**, and it was right: that rule covers `persisted 'Real Answer'` vs
`in-memory ''` (a skip would blank the answer), but NOT the reverse --
`persisted ''` (the user cleared it) vs `in-memory 'WRONG'`, where the stale side
is the meaningful one. That reverse tie is uw3w's case 1 exactly: a confirm would
revive the stale value and mark it confirmed, so it never re-prompts and prints
on the PDF. Reproduced before fixing.

Ties now go to the PERSISTED side outright -- it is the side written through
`SchemaFormStateManager`, the durable path both writers share, whereas
`this.state` is a per-object copy that goes stale precisely because the UI never
touches it. An in-memory-only entry is unaffected: it never reaches the tie
branch, since the one-sided case keeps it. The handler tests install a monotonic
`Date.now()` so they exercise the reconcile RULE instead of racing the clock.

### Scope call on `handleSessionReady`

The refresh there is deliberately `fieldValues`-only, not a whole-state adopt.
The field-1 opener diagnostic compares in-memory `disclaimerAccepted` against the
persisted value at entry to surface staleness (bd `xp4q`); adopting persisted
state wholesale would force those two to agree and silently destroy that signal.
`fieldValues` is the map with two writers, so it is the map that gets merged.

## Mutation verification

Three separate mutations, each isolating a different claim:

| Mutation | Result |
|---|---|
| revert `reconcileFieldValues` to the raw key union | **10 fail** -- all three beads' regressions |
| restore the asymmetric "meaningful entry wins" tie-break | **exactly 1 fails** -- the reverse-tie case |
| remove the `handleSessionReady` refresh | **exactly 1 fails** -- the `qim7` case |

The `pjws` in-memory-only test correctly stayed green under the first mutation
(the union preserves that direction), which is the evidence that the reconcile
did not simply invert the old bias.

## What the review rounds added

Three fresh-eyes rounds ran pre-PR, and each found something real. Worth recording
because the pattern is instructive: the first fix was correct in direction and
wrong in the details, twice.

- **Round 1** caught that the tie-break was asymmetric (see above) -- it protected
  the blank-a-typed-answer direction but not the revive-a-cleared-value one, which
  is uw3w's own case 1.
- **Round 2** caught a FOURTH `save(this.state)` site, `handleSectionSwitched`,
  with no reconcile. Folded in (bd `tare`): a section switch is a round-trip and an
  on-screen edit can land inside it. Round 2 also flagged that a tie between two
  DIFFERENT meaningful values resolves arbitrarily. That one was kept after
  tracing it: every connection write goes through a stamp-and-save step, so an
  equal stamp means both sides hold the same write. The rule stayed; the comment
  and doc were corrected, because they had overstated the guarantee.
- **Round 3** caught a FIFTH site, `handleDrainFindingsResult`, and this was the
  worst of them: `markFieldsSteered` REBUILDS the whole `fieldValues` map from
  `this.state`, so a field the connection object has never seen -- one typed on
  screen during the validator drain round-trip -- is dropped OUTRIGHT, not merely
  reverted to a stale value. The mutation test fails with `expected undefined to
  be defined`, which is the signature of total loss rather than staleness. Folded
  in as bd `6iwn`.

Round 3 also noticed that `markFieldsSteered` set `steered` WITHOUT stamping
`lastModified` -- which quietly broke the invariant the tie-break leans on, since
an unstamped write loses to any stamped one and the steer marker would be
discarded, defeating W4's re-arm bound. It now stamps.

- **Round 4** caught a SIXTH, `handleValidationResult` -> `enqueueValidatorFindings`,
  on an even wider window (the validator round-trip can take seconds).

At that point the per-round pattern was the real finding: four rounds, four more
sites. So instead of patching the sixth and waiting for a seventh, I enumerated
every persist path exhaustively. The honest picture is that **every**
`SchemaFormStateManager` mutator spread-replaces the whole state and saves, so
*any* of them on a stale `this.state` clobbers `fieldValues`. That turned up two
more unreconciled sites nobody had flagged (`pinField` in
`handleSwitchFieldRequest`, `markFieldSchemaLoaded` in `handleFormUpdated`) --
eight reconciled handlers in total.

The obvious consolidation -- reconcile inside `save()` itself -- was tried and
REJECTED on evidence: `confirmField` deliberately does not bump `lastModified`
(it changes only confirmation metadata, never the value), so a reconcile there
sees a tie, prefers the persisted entry, and silently drops `confirmed: true` on
every confirmation. Probed it; the flag vanished. That would have been far worse
than the bug being fixed.

So the durable guard is a source-level **allowlist** test
(`webFormConnection.persistsites.test.ts`) asserting the COMPLETE set of persist
sites. A newly-added one fails by default rather than waiting for a review round
to notice. Mutation-verified by adding a seventh site and watching it fail.

- **Round 5** then found a genuinely DIFFERENT shape, which that guard was blind
  to by construction: `switchToSection` does `load()` … `await
  waitForBufferDrain(1000)` … `switchToSection(snapshot)`. The staleness comes
  from the intervening await, not from an unrefreshed `this.state`, so the local
  snapshot is up to a second old when it is persisted — and the stale copy is
  also what gets sent to the backend as `current_values`. Fixed by re-reading
  after the await; mutation shows the same total-loss signature (`expected
  undefined to be defined`).

The guard now covers that shape too. Writing that second check was itself
instructive: the first version PASSED against known-bad code, because its
method-boundary regex also matched `if (` and reset the tracking one line after
the capture. A guard that silently passes is worse than no guard, so it is
mutation-verified in both directions — it fails on the reverted fix, naming the
exact line, and passes on the real source.

Both out-of-scope sites were folded in rather than left as filed beads: shipping a
change titled "one owner for `fieldValues`" while knowingly leaving more writers
unreconciled would have been misleading.

## `6j0m`: root cause found, no code change needed

The bead reported a whole cluster of overlay/schema-form tests failing only in
full-suite runs -- 9 failures on clean `dev`, a varying failing set, opaque
`Error: STACK_TRACE_ERROR` from `@vitest/runner`.

It does not reproduce. Measured on this branch and on clean `origin/dev`:
1271/1271 (1270 before the review round added a case) and 1257/1257 respectively, green across seven runs, plus
`--poolOptions.forks.singleFork=true` (which also **rules out cross-file
module-state bleed**, the bead's leading suspect) and `maxForks=22` (rules out
worker contention).

The cause is visible in `git show 9367c15a --stat` (bd `87a9`, PR #544, merged
the day after the measurements). Six of the exact named files each lost precisely
ONE line -- `changeSpokenLanguage: vi.fn(),` -- a mock of a `ConnectionManager`
method that bd `87a9` proved dead and deleted. `VoiceOverlay.tsx` (-65) and
`VoiceOverlayMobile.tsx` (-60) lost the dead `handleLanguageChange` those mocks
existed for: an `async` handler doing multiple React `setState` calls
(`setSelectedLanguage`, `setError`) after `await` points. That unmounted-component
async-state-write pattern is exactly what surfaces as an opaque runner-level
error under full-suite timing and not in isolation, and it matches every reported
property.

The original measurements were taken while `87a9` was still unmerged; the "clean
dev" baseline was reached by *stashing* that branch, which restored the stale
mocks and the dead handler -- so both measured configurations still contained the
defect.

The bead's practical warning -- that the frontend suite is not a trustworthy
pre-PR gate for those files -- is retired.

## Doc note

`docs/components/schema-forms.md` gained a "Two writers, one map" section and a
note that `lastModified` is load-bearing. The freshness checker also flags
`ws-protocol.md` and `technical_guide.md` as stale against `webFormConnection.ts`,
but this change touches no wire format -- verified: the diff contains no change to
any `type:`, `this.send(`, or `message.` line. Those two are stale from other
commits and were left alone.
