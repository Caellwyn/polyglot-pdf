---
date: 2026-09-03
bead: polyglot-pdf-f2a8k
title: "fix(schema-forms): a stored session meets the fresh schema in init() -- the stale-session guard"
tags: [schema-forms, state, testing]
---

## Trigger

PR 3c of the g2fpr epic (`polyglot-pdf-ps4hf`). The select migration turns
option values from export codes (`'AL'`) into slugs (`'alabama'`) while a
browser may still hold `'AL'` in sessionStorage. The plan's adversarial pass
found the consequence: the stored value matches no option, so the `<select>`
renders EMPTY, the field stays confirmed and is never re-asked, and the filler
writes `'AL'` verbatim -- right only because the old value happens to equal the
new `pdf_on_value`. Luck, not design.

## What shipped

`SchemaFormStateManager.reconcileSelectValues(state, freshSchema)`: for every
select whose stored value is not one of the fresh schema's option values, map
it to the option whose `pdf_on_value` it equals (lossless; confirmation kept),
or clear it and drop the confirmation so it is asked again. A code two options
claim is cleared, never guessed -- the same policy `/resume-form` applies.
Called from `init()`'s reuse branch and from the vanilla-JS path in
`shared/connection.ts`, which skips `init()` when a session exists.

## Lessons

**The plan put the guard in `load()`; the code put it where fresh meets
stored.** `load()` only ever sees the STORED blob -- schema and values from
the same moment, consistent with each other. The desync is created one call
later, when `init(schema)` reuses a session under an hour old and hands back
its STORED schema untouched; the fresh schema does not enter until fill time.
So the guard lives in the reuse branch of `init()`, and adopts the fresh
schema while it is there.

**Two entry points, not one.** The vanilla-JS harness path does
`load() || init(schema)` -- a stored session skips `init()` entirely and goes
straight to `restoreDOMFromSessionStorage`, which sets `<select>.value` to the
stored string. Grepping for every caller of `load()` before placing the guard
is what found it.

**A `deduplicateSections` copy defeats an identity assertion.** My "same object
when nothing changes" test compared against a schema that `init()` had already
cloned. The property is still worth pinning; it just has to be pinned against
the state's own schema.

**The vanilla path's load migration is lazy by contract, and a test pins it.**
My first cut re-persisted the reconciled state in `connection.ts`;
`connection.test.ts` failed with "expected undefined to be 'section-2a'" --
its comment says exactly why: "a future change that starts persisting the
migration fails here". The reconcile now lives in memory on that path, like
`load()`'s own key migrations; the next field write persists it. The full
suite found it in one run; the targeted state-manager tests could not, because
the contract belongs to the connection factory, not the manager.

**`init()`'s reuse used to keep a stale schema for an hour.** Pre-existing:
after any kit edit, a session under an hour old kept running on the old
schema. Adopting the fresh one on reuse is a small behaviour change made
deliberately here, because the reconcile is meaningless without it; noted for
review rather than hidden.

## Files touched

- `frontend/src/schema-forms/state/schemaFormState.ts` -- the helper; `init()` reuse
- `frontend/src/shared/connection.ts` -- the vanilla path
- `frontend/src/schema-forms/state/schemaFormState.selectreconcile.test.ts` (new)
