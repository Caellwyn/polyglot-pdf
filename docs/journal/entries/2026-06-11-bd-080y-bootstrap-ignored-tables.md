---
date: 2026-06-11
bead: polyglot-pdf-080y
tags: [harness]
---

## Trigger

While closing out the SPEAR PR (#153) from a fresh remote container, `bd import`
and `bd close` failed with `table not found: wisps` even though `bd ready` / `show`
/ `list` worked -- the beads store could be READ but not WRITTEN. The maintainer
asked for the root cause and a durable fix so it does not recur. Bead
`polyglot-pdf-080y`.

## What shipped

A fix to `scripts/beads_remote_bootstrap.py`, the script that hydrates the beads
(Dolt) DB in fresh remote/web containers. Certain tables are registered in Dolt's
`dolt_ignore` (`wisps` / `wisp_*`, `local_metadata`, `repo_mtimes`), so they are
absent from `refs/dolt/data` and never arrive on a clone; the script recreates
them locally post-clone. Two bugs:

1. **Mis-gated.** The repair ran only when `is_hydrated()` (a READ check:
   `bd stats` total_issues > 0) was false. The original assumption -- a wisp-less
   clone cannot open, so "not hydrated" implies "tables missing" -- no longer
   holds: the current `bd` OPENS a fresh clone for reads without the tables, so
   `is_hydrated()` returns true and the repair was skipped. But every WRITE that
   recomputes is_blocked (`bd import`/`create`/`close`, and so `/closeout`) then
   dies on the missing `wisps`. The script printed `hydrated ... Done.` over a
   write-broken store -- a silent failure.
2. **Incomplete.** The old repair recreated only `wisp%`. `local_metadata`
   (also dolt-ignored) stayed missing, so `bd create` / `bd migrate` hit
   `table not found: local_metadata`.

Fix: generalize `repair_wisps` -> `repair_ignored_tables`, which reads
`dolt_ignore`, expands its (glob) patterns against a throwaway `bd init`, and
recreates EVERY such table missing from the clone (idempotent, FK checks off,
local-only commit -- never pushed). Gate it on a new `_ignored_tables_need_repair()`
table-presence check (not `is_hydrated()`), in BOTH the fresh-clone and the
early-return/cached paths. When no `dolt` CLI can be obtained, WARN that writes
may fail instead of a silent success.

Verified end-to-end in this remote container: a forced re-hydration recreated all
8 dolt-ignored tables; `bd migrate status`, an is_blocked-recomputing write, and a
round-tripped close all succeed; and the early-return path repaired a dropped
table on the next run.

## Lessons

- **A read-availability check is not a usable-store check.** `is_hydrated()`
  (reads work) silently passed a store whose write path was broken. Any "did the
  setup succeed?" gate that only exercises the read path can certify a half-working
  state; the gate must touch the capability it is actually guaranteeing (here: the
  tables a write needs). Generalizes to other bootstrap/health checks.
- **Self-assessment caught the partial fix.** The adversarial fresh-eyes loop (the
  process shipped in #153, used here for the first time on real code) flagged that
  the cached/early-return path still reported a silent success when no `dolt` CLI
  was available -- the exact silent-failure class the fix existed to kill,
  reintroduced in the second code path. Round 1 found it; round 2 confirmed the
  fix. Codex was unavailable, so repeated fresh-eyes rounds were the review of
  record (per the maintainer's instruction).

## Doc freshness

- `docs/components/beads-remote-bootstrap.md` updated (it `**Tracks:**` this
  script): point 3 and step 3 now describe the read-opens / write-needs-the-tables
  behavior and the presence-gated, all-ignored-tables repair; stamp bumped to
  2026-06-11.

## Files touched

- `scripts/beads_remote_bootstrap.py`
- `docs/components/beads-remote-bootstrap.md`
- `docs/journal/entries/2026-06-11-bd-080y-bootstrap-ignored-tables.md` (this entry)
