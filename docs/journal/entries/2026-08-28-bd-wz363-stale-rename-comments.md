---
date: 2026-08-28
bead: polyglot-pdf-wz363
title: "docs(schema-editor): fix rename comments that still claim the /label route can't be refused"
tags: [docs, schema-editor]
---

## Trigger

`bd polyglot-pdf-c63tu` added an edit-lock check to `POST
/api/editor/kits/{kit_id}/label`, so the route now 409s when a different
editor holds the kit's lock. Two comments in `RemoteCatalogue.tsx` and one
docstring in `formKitDirectory.ts` still asserted the OLD contract ("safe
for ANY selected kit" / "the local-mode mirror of the hosted /label
route") -- found by the Opus cross-surface review during c63tu's own
review pass, filed rather than folded into that PR since it's comment-only
and touches different lines.

## What shipped

- `RemoteCatalogue.tsx`'s two rename comments (lines ~549 and ~853): kept
  the still-true point (no parent-confirmed open needed, unlike the status
  actions), dropped the now-false "safe for ANY selected kit" claim, and
  added a note that the route can 409 on a lock conflict.
- `formKitDirectory.ts`'s `setKitLabel` docstring: changed "the local-mode
  mirror of the hosted /label route" to "counterpart" and explicitly named
  what no longer mirrors (the hosted route's edit-lock guard; local mode
  has no shared lock to check, so it always succeeds).

Comment-only, no behavior change -- verified by running the full
`RemoteCatalogue.test.tsx` suite (99/99 pass) and `tsc --noEmit` clean.

## Files touched

- `schema-editor/src/components/RemoteCatalogue.tsx` -- 2 comments corrected.
- `schema-editor/src/utils/formKitDirectory.ts` -- 1 docstring corrected.
