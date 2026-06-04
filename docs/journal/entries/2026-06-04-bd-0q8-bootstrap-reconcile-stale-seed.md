---
date: 2026-06-04
bead: polyglot-pdf-0q8
title: "Remote bootstrap froze on a stale JSONL seed: reconcile the working branch onto the ref"
tags: [postmortem, harness]
---

## Trigger

`bd polyglot-pdf-0q8`, filed mid-session after `bd dolt pull` and `bd dolt push`
both failed in this remote container with `merge origin/main: no common
ancestor`. The maintainer's prompt sharpened it: "the beads are not appropriately
syncing and hydrating from the remote -- daa is long since completed, why?" That
reframed a sync error into a hydration-correctness bug worth root-causing.

## What was actually wrong

The container was running on a **stale 30-issue snapshot from 2026-05-30** while
the canonical remote (`refs/dolt/data`) held **124 issues** across 388 commits of
real history. Downloading the `dolt` CLI and inspecting both stores directly made
it unambiguous:

- The local working branch (`main`) had a fresh `Initialize data repository` root
  -> wisp-table creation -> migrations -> only this session's edits. Not a clone of
  the remote's history -- a fresh init.
- The fetched ref WAS present, as the remote-tracking branch `origin/main` (124
  issues, the real 388-commit lineage).
- The 30 local issues matched `.beads/issues.jsonl` exactly (30 issues, last
  committed 2026-05-30 in PR #18).
- Sample cross-check: `9np`/`cg7`/`y3l` are **closed** on `origin/main` but showed
  **open** locally; `daa` is **open** on both (its *code* mitigation shipped under
  `4p0`/`4cm`, but the *bead* was never closed in the canonical tracker).

So `bd bootstrap` had fetched the ref into `origin/main` but **seeded the working
branch from the stale committed JSONL** -- because the freshly cloned history
can't open until the dolt-ignored `wisps` tables are repaired, bd fell back to a
JSONL rebuild for the working branch. `main` and `origin/main` then sat on
**unrelated roots**: no common ancestor, so every `bd dolt pull`/`push` aborted,
and the container was permanently frozen on the snapshot. The hydration marker
made it worse: it is written after `bd bootstrap` returns and the freshness guard
only checks `issue_count > 0`, so the stale 30-issue seed satisfied it and every
subsequent session reported "already hydrated; refresh skipped" -- the exact
stale-snapshot trap the marker was supposed to prevent, defeated because the
marker certifies *that* a hydrate ran, not *what* the working branch points at.

## What shipped

A **reconcile step** in `scripts/beads_remote_bootstrap.py`
(`reconcile_working_branch_onto_ref`): after bd opens a populated DB, compare the
working branch's issue count to the fetched ref (`origin/main`); if the working
branch is a stale seed (fewer issues, unrelated root), `dolt reset --hard
origin/main` rebases it onto the real history. The dolt-IGNORED wisp tables are
local working state, so they **survive the reset** -- bd stays open and no wisp
re-repair is needed. Wired into `main()` (run before the marker is written, so the
marker can never again certify a stale seed) and into the already-hydrated
`refresh_remote_and_pull()` path (so a container hydrated *before* this fix
self-heals on its next session when its pull fails with "no common ancestor").
The reconcile no-ops when the working branch already holds the ref's data (count
>= ref), so a healthy container is never disturbed.

This was validated against the live store on a throwaway copy (the maintainer
chose the script fix only, not an in-place recovery of this container):

- raw dolt: `dolt reset --hard origin/main` -> 124 issues, wisp tables intact;
- `bd stats` opens the reset DB (124 issues); `bd dolt pull` -> "Pull complete.";
- the new helpers via direct import: stale 33 -> reset -> 124, and a second call
  correctly no-ops (124 >= 124).

### Fresh-eyes triage

Pending at time of writing -- fresh-eyes runs at closeout against the real diff;
its findings and the adopt/reject/defer breakdown go in the merge ping.

## Doc freshness

`docs/components/beads-remote-bootstrap.md` bumped to current state: the
stale-snapshot-trap section now records that the marker alone was insufficient,
and the "What the script does" list gains the reconcile step (step 4) with the
mark moved to step 5 (written only after reconcile).

## Files touched

- `scripts/beads_remote_bootstrap.py` -- new `_remote_tracking_ref`,
  `_issue_count`, `reconcile_working_branch_onto_ref`; `main()` consolidated to
  reconcile-then-mark; `refresh_remote_and_pull()` self-heals on divergence.
- `docs/components/beads-remote-bootstrap.md` -- current-state doc bump.

## Lessons

- **A marker that records *that* an action ran is not a marker that the action
  produced the right state.** The freshness guard must verify the working branch
  descends from the ref (issue-count parity against `origin/main`), not merely that
  `bd` opens something populated.
- **`dolt reset --hard` does not touch `dolt_ignore`d tables** -- that is exactly
  why the wisp tables survive the rebase, and why reconciling is cheap (no
  re-repair). Worth remembering for any future dolt-branch surgery here.
