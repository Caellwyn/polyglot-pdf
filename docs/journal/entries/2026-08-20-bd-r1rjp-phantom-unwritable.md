---
date: 2026-08-20
bead: polyglot-pdf-r1rjp
title: "fix(store-handshake): drop the phantom reason=unwritable from the backend contract"
tags: [review, conventions]
---

## Trigger

Continuing the low-complication-bead sweep. Two backend comments and one
frontend TypeScript type claimed the store-handshake route can return
`reason="unwritable"`. It cannot: the handler returns exactly
`not-a-local-store`, `mismatch`, or `stale`.

This mattered more than a normal comment nit because of provenance. bd
polyglot-pdf-abn4o had just corrected the same wrong claim in
`docs/technical_guide.md` -- and that row had been written FROM these
comments. Fixing the doc while leaving its source wrong is how the same
error gets re-derived by the next reader.

## What shipped

Three sites, all comment/type-only:

1. `editor_kit_routes.py` `StoreHandshakeResponse.reason` field comment --
   now names the three real values. The old text was also wrong about the
   MEANING: it glossed "unwritable" as "the backend cannot read its own
   root", when it is about the EDITOR failing to write its marker.
2. `editor_kit_routes.py` handler docstring -- claimed a read-only store
   reports `reason="unwritable"`; the actual no-marker branch returns
   `mismatch`. This was the one genuine factual error, not just a naming
   slip.
3. `remoteKitStore.ts` `StoreHandshake.reason` -- dropped `'unwritable'`
   from the wire type, which had widened the backend contract by a value
   the server cannot produce.

`FolderCheck` (`formKitDirectory.ts:457`) legitimately keeps `'unwritable'`
and was left untouched: that is where the value actually lives, minted from
the catch on the marker WRITE, returning before the backend is called at
all (pinned by `formKitDirectory.handshake.test.ts:70`).

## Lessons

**A type that mirrors a wire contract can drift wider than the producer,
and nothing catches it.** Adding a union member the server cannot emit is
invisible to every test and to the typechecker -- the extra member is
simply never constructed. The only way it surfaces is a human reading the
type and believing it. That makes a mirrored type a doc-like surface: it
needs the same "verify against the producer" discipline as prose, because
it has none of prose's tells.

The outer review surfaced the structural fact that made the change provably
safe, and it was not visible in the diff: **the backend's `reason` is read
by nothing.** `runHandshake`'s asker parameter is typed
`(nonce) => Promise<{ sameFolder, backendRoot }>` -- there is no `reason`
slot, so `stale` and `not-a-local-store` are already dropped on the floor
today, and the client mints its own `mismatch` for every backend failure.
Narrowing an unread field cannot change runtime behavior. Worth recording
because "is this consumed at all?" answered the safety question faster and
more decisively than enumerating call sites did.

Also worth noting for the sweep: two of this round's candidates
(`polyglot-pdf-tym9x`, and `2hpkl` earlier) were already fixed or not yet
true on `dev`. Checking a bead's premise against current `dev` before
touching anything keeps paying for itself.

## Doc freshness

- No doc stamps bumped. `docs/technical_guide.md`'s routes table has no row
  for `/api/editor/store-handshake` at all (verified), so this diff neither
  fixes nor creates staleness there. The related doc claim was already
  corrected by bd polyglot-pdf-abn4o.

## Files touched

- `backend/routes/editor_kit_routes.py` -- field comment + handler docstring
- `schema-editor/src/utils/remoteKitStore.ts` -- narrowed `StoreHandshake.reason`
