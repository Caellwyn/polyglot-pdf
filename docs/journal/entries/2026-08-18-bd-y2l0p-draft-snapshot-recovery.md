---
date: 2026-08-18
bead: polyglot-pdf-y2l0p
title: "feat(kits): draft saves are recoverable -- and what 13 review rounds cost"
tags: [kits, editor, storage, concurrency, review, testing]
---

## Trigger

Maintainer principle, 2026-08-08: "Editors should not ever be able to make
destructive actions. Their work should always be recoverable."

`PUT /api/editor/kits/{kit_id}/schema` is editor-gated and called
`store.put_schema` directly. The write-lock refuses only a COMPLETE or
UNPUBLISHED kit -- so a published revision was protected and a DRAFT was
overwritten in place with no copy anywhere. Editor A spends hours on a draft;
editor B, or A from a stale tab, saves over it, and the earlier contents are
gone. The in-editor undo stack does not help: it is cleared on load, so it
never survived a reload and never covered a cross-session overwrite.

## What shipped

A bounded ring of the last 10 saves per kit at `<kit_id>/_drafts/<n>/`, in both
the local store and GCS. Every editor save snapshots the current schema before
overwriting. Two routes list and restore, both editor-accessible.

Two maintainer decisions (2026-08-18): editors CAN restore (routing recovery
through an author means the person who lost the work cannot get it back
themselves), and the ring keeps the last 10.

The save/restore asymmetry is deliberate and documented at both sites. A
snapshot failure on SAVE must not block the save -- the editor's current work
matters most. A snapshot failure before a RESTORE must refuse it, because a
restore knowingly destroys the current draft; a recovery feature that loses
work is worse than one that declines.

## Why this took 13 inner rounds and 2 outer passes

Gap counts: 5, 3, 6, 4, 1, 1, 1, 5, 2, 2, 1, then two NO-GAPS. That is far more
than a copy-before-overwrite feature should need, and most of the cause was
mine. The pattern is worth recording because it generalises.

**Rounds 1-5 found holes in the FEATURE. Rounds 6-13 found holes in the
FIXES.** Every repair is new code carrying its own risk; that is the real cost
of a long review loop, not the token spend.

**Nearly every finding lived in the store that SHIPS, not the one I tested.**
The GCS ring was INERT for four rounds -- `_build_blob_path` drops an empty
part, so the listing prefix lost its trailing slash, no snapshot id ever
parsed, and every save overwrote snapshot 1 while listing returned nothing. All
18 local tests passed throughout. Criterion 2 ("recovery works identically in
GCS and local-folder mode") failed in three different ways across rounds 1, 3
and 4. **The store that ships is the one that has to be exercised**, and a
local-only suite cannot answer a criterion naming both modes.

**Six tests whose names outran their assertions.** A test asserting `_drafts`
is not a top-level kit, when `_drafts` is nested INSIDE the kit and could never
be one. An end-to-end GCS test that hand-replicated the route sequence instead
of calling the route -- attesting to the store, not the restore. A guard test
that hooked `Path.exists` to fire mid-check, which could never detect the
deletion of that very call. Each read as coverage and was not.

**Twice I filed a real data-loss race as a minor follow-up on REASONING rather
than measurement.** The concurrency race "cost one recovery point" until
someone ran it: 6 concurrent saves returned 200 and left ONE snapshot. When the
question is how bad a race is, the answer is a reproduction, not an argument --
four lines of `asyncio.gather` settled what three rounds of prose had not.

**I lost the entire implementation three times to `git checkout` in a mutation
loop over uncommitted work** -- the identical mistake from bd bdedm, about
which I had already written a commit message. Now: commit before mutating,
always, and assert every mutation anchor so a no-op reports itself instead of
masquerading as a survivor.

## The concurrency work (rounds 6-13)

The id was computed from a listing and then written to -- a TOCTOU. Measured: 4
concurrent snapshots returned ids `['1','1','1','1']` locally and
`['3','3','3','3']` on GCS, one surviving of four. Fixed by claiming the id
atomically: `os.mkdir` locally (atomic on POSIX and Windows), and
`if_generation_match=0` on GCS (compare-and-swap). The test fake had to learn
the precondition or the GCS tests would have proven nothing.

That fix needed its own reaper for abandoned claims, and the reaper then
deleted COMPLETED snapshots -- 85 silent losses in 360 trials, because my id
bound was on the wrong side (the endangered saver holds a LOWER id). Fixed with
a last-instant re-check plus `rmdir` rather than `rmtree`.

The reaper ended up with four guards, and I mis-described them twice:

1. The `schema.json` early return protects a completed snapshot's `meta.json`
   -- the unlink runs BEFORE `rmdir` is reached. I called this an optimization
   after testing "does the SCHEMA survive?" It does. Wrong question: the victim
   is the metadata, and `savedAt` is the only field distinguishing entries in a
   recovery list of bare counters.
2. Unlinking ONLY `meta.json` protects a saver mid-write, whose directory holds
   just `.schema.json.<pid>.<hex>.tmp`.
3. `rmdir` not `rmtree` protects a schema appearing after the check.
4. The caller's `>= next_id` bound protects HIGHER in-flight claims -- measured
   at 72 bound-only skips across 480 concurrent saves, and 11 failed writes in
   120 trials without it. I argued in round 11 that this bound never fires. It
   fires.

**The generalisable lesson: a guard can protect something other than the thing
you thought to check.** Testing one file and generalising to all files produced
two wrong conclusions in consecutive rounds, and one of them left a comment
inviting a future refactorer to delete a working guard.

## Cross-surface

The outer review found my "style" commit had corrupted two comments in
untouched code -- a bulk regex ate a nested parenthetical. Investigating showed
the edit was unprompted scope creep into other beads' comments, and that the
round-attribution narration it targeted is this file's EXISTING convention (29
instances on dev). Reverted entirely; there was nothing to fix.

That investigation also surfaced that the branch was 5 commits behind dev, so
the diff had been showing comments ADDED ON DEV as though I had deleted them.
Merged dev; the diff is now purely additive.

## Residual, accepted and documented

A stray blob placed BY HAND in the GCS bucket at `_drafts/<n>/meta.json` with
no `schema.json` lists as a recoverable snapshot and then 404s on restore.
Unreachable from any code path -- `put_draft_snapshot` writes the schema first
and never writes meta without it. Manual-gsutil-only, cosmetic.

## Follow-ups filed

polyglot-pdf-06u5o (`_drafts` needs the `.gitignore` + deploy-script exclusions
its sibling `_archive` has -- snapshots would otherwise be committed by the
bucket-sync workflow and ride along in deploys), uqti7 (restore does not
re-stamp readiness), suavr / tszhy (the other ~8 `put_schema` sites still
overwrite a draft with no snapshot -- pre-existing), 8bw19 (eviction can race a
mid-write), xddtl (store-level snapshot_id traversal), urtk0 (superseded by the
concurrency fix), i9e79 (component-doc paragraph), ubij3 (unpinned non-UTF-8
stamp branch).

## Not yet reachable by an editor

No frontend consumes the two routes yet, so recovery currently requires a
hand-rolled HTTP call with an editor token. The principle is MECHANICALLY
satisfied, not yet reachable by the people it protects. Backend-first is a
legitimate landing for this bead scope, but the gap is real and should be
stated plainly rather than discovered.
