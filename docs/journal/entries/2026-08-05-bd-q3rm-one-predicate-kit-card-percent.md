---
date: 2026-08-05
bead: polyglot-pdf-q3rm
title: "s18: kit card % computed by ONE predicate everywhere (catalogue drift fix)"
sprint: 18
tags: [schema-editor, testing]
---

## Trigger

Sprint-18 C1 (bd polyglot-pdf-o7y9) pinned THE count predicate
(reviewStatus.isCountedReviewed / reviewCounts) and switched App.liveStats to
it -- but the catalogue's own per-kit scans (RemoteCatalogue's refresh fetch and
formKitDirectory.readKitProgress) still ran the OLD predicate,
validation.getCompletionStats. The two disagree exactly where
checkFieldComplete ERRORs a field the pinned predicate counts (e.g. a
signed-off text field with no pdf_field_name: not a structural error under
isCountedReviewed -- the missing widget mapping is the lint layer's job -- but
an exclusion under checkFieldComplete). Visible symptom: open a kit and its
card caches the liveStats percentage; hit Refresh and the card drops to the
scan's percentage -- the number changes with no edit in between. Deferred out
of C1 as bd polyglot-pdf-q3rm, mechanically blocking C4 (bd polyglot-pdf-g687).

## What shipped

Both scans now compute `reviewCounts(schema.fields, undefined)` -- the pinned
predicate, honestly gate-blind on lint findings a scan does not have, exactly
like liveStats before a lint report arrives. That left getCompletionStats with
zero production consumers, so it is DELETED with its tests (keeping a second,
divergent predicate alive as dead code is precisely the drift this epic
exists to kill); checkFieldComplete stays, as the advisory WHY-list/icon
input it already was. Stale comments pointing at the deleted function
(guidanceStaleness's aggregation docs, the progress-test headers) updated.

Tests pin the fix from both sides, and both were mutation-verified (a
temporary revert of the scan predicate reddened exactly the two new tests):

- formKitDirectory.progress.test.ts: readKitProgress and App.liveStats must
  report the SAME percentage for a schema holding a reviewed_correct field
  with no pdf_field_name (the exit-criterion case), and that number is 100 --
  the old scan's 0% was the bug, not the live 100%.
- RemoteCatalogue.test.tsx: the rendered card shows 100% for that same
  schema (the component-level pin on the remote scan).

Full schema-editor suite: 1164 passed, typecheck clean.

Follow-up beads filed: polyglot-pdf-5uoj (live-browser pass over the s18
editor surfaces -- still undone; the dev port 3001 is held by session
infrastructure in Claude sessions, see the bead), polyglot-pdf-r7k4 (remove
the now-dead needsAckFieldIds aggregation, whose last documented consumer was
getCompletionStats's needsAck parameter).

Review record: filled in at closeout -- fresh-eyes loop + Opus outer review
per docs/doctrine/review-flow.md; see the PR for the scorecard.

## Lessons

- When a predicate is pinned as THE definition, grep for every OTHER
  computation of the same user-visible number in the SAME commit that pins
  it. C1 pinned isCountedReviewed for the strip and liveStats but left two
  scan call sites on the old function; the divergence was found by review,
  deferred, and cost a second bead.
- Deleting the losing predicate is cheaper than documenting the difference.
  getCompletionStats survived C1 as "the catalogue's definition" with a
  known-limitation note; the honest fix was routing its callers and removing
  it, which also surfaced dead code downstream (needsAckFieldIds).

## Doc freshness

No tier-1/2 doc tracks the catalogue percent computation by name; the
freshness checker's verdict at closeout governs. docs/components/ has no
schema-editor surface doc (pre-existing gap, unchanged here).

## Files touched

- schema-editor/src/components/RemoteCatalogue.tsx -- remote scan predicate swap
- schema-editor/src/utils/formKitDirectory.ts -- local scan predicate swap
- schema-editor/src/utils/validation.ts -- getCompletionStats deleted
- schema-editor/src/utils/guidanceStaleness.ts -- stale consumer comment updated
- schema-editor/src/components/RemoteCatalogue.test.tsx,
  schema-editor/src/utils/formKitDirectory.progress.test.ts -- divergence pins
  (mutation-verified)
- schema-editor/src/utils/validation.test.ts,
  schema-editor/src/utils/guidanceStaleness.test.ts -- dead tests removed /
  comments updated
