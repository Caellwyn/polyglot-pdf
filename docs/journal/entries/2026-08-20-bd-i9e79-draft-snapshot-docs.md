---
date: 2026-08-20
bead: polyglot-pdf-i9e79
title: "docs(pdf-filling): document the draft-snapshot ring"
tags: [review]
---

## Trigger

Continuing the low-complication-bead sweep: `docs/components/pdf-filling.md`
had a dedicated "Revision archive" paragraph documenting the archive
mechanism (superseded published schemas at `_archive/<marker>/`), but no
equivalent entry for its sibling -- the draft-snapshot ring shipped in bd
y2l0p (PR #608), which keeps a bounded history of overwritten in-progress
drafts at `_drafts/<n>/`. The two mechanisms look similar (both snapshot
schemas to protect against overwrite) but are entirely separate
namespaces with different eviction and recovery semantics, which is
exactly the kind of distinction this doc exists to keep straight.

A sibling bead (`2hpkl`, also targeting this file) was found to have a
premise that isn't true yet -- it described HTTP archive-read routes and
a UI disclosure from bd qfyxr, but that bead's own PR (#617) is still
open, not merged into `dev`. Closed with no code change rather than
documenting routes that don't exist in the branch a reader would actually
be working from; re-file once #617 merges.

## What shipped

Added a "Draft snapshots" paragraph naming the three store methods
(`put_draft_snapshot` / `list_draft_snapshots` / `load_draft_snapshot`),
the `<kit_id>/_drafts/<n>/` storage layout, the `DRAFT_SNAPSHOT_LIMIT = 10`
ring bound, both routes (`GET .../draft-snapshots`,
`POST .../draft-snapshots/{id}/restore`), and the deliberate save-vs-restore
asymmetry: a plain save snapshots best-effort (a snapshot failure is
logged but never blocks the save), while a restore snapshots the current
draft and REFUSES if that snapshot fails (a restore knowingly destroys
the live draft, so declining when the safety net can't be laid down is
the honest failure). Every claim -- including the negative one, that draft
snapshots and archived revisions never mix -- was verified by reading the
actual store constants and both routes' try/except structure, not just
their docstrings.

Also added `backend/routes/editor_kit_routes.py` to the doc's
`**Tracks:**` line -- a file its existing archive/lifecycle/lock sections
already cite extensively, but which the freshness-check declaration had
never named.

## Lessons

The `2hpkl` false-premise case is the same shape as `ke3cd` and `z7joa`
from earlier in this session: a bead's description can describe work
that's genuinely landed on a feature branch and even closed its own
tracking bead, while the actual merge into `dev` is still pending.
Checking a cited bead's PR merge status directly (`gh pr view <N> --json
mergedAt,state`), not just its own "closed" status, is now a standing
habit worth keeping -- a bead can close itself at `/closeout` before its
PR is actually merged if the merge is a maintainer-ping case still
awaiting approval.

## Doc freshness

- `docs/components/pdf-filling.md` -- stamp rewritten (replaced, not
  appended, per prune-on-bump); `**Tracks:**` line gained
  `backend/routes/editor_kit_routes.py`. Live checker reports OK.

## Files touched

- `docs/components/pdf-filling.md` -- new "Draft snapshots" paragraph +
  Tracks line addition + stamp rewrite
