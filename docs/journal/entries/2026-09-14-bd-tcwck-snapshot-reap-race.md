---
date: 2026-09-14
bead: polyglot-pdf-tcwck
title: "fix(kits): the local store's snapshot reaper spared only HIGHER in-flight claims -- a delayed lower claimant lost its directory"
tags: [hotfix, form-kits, concurrency, testing, ci-flake]
---

## Trigger

CI for PR #789 (bd `polyglot-pdf-fr20a`, a tests-only PR) failed twice in a
row on Linux in
`test_kit_draft_snapshots.py::test_CONCURRENT_snapshots_do_not_destroy_each_other`
with `FileExistsError` on `w7/_drafts/3` from inside the atomic JSON
writer's `mkdir(exist_ok=True)`. Every other recent branch was green, and
the same suite is green on Windows; the new PR adds ~44 tests earlier in
collection order and perturbs worker-thread timing enough to open the
window every time. Tests-only PRs cannot merge on red CI, so this became
a P1 fix of its own rather than a retry.

## Root cause

`pathlib`'s `mkdir(exist_ok=True)` tolerates `FileExistsError` only if the
path is still a directory on its re-check. Between a claimant's
`os.mkdir` of its snapshot dir and its `is_dir()` re-check, a CONCURRENT
`put_draft_snapshot`'s orphan reaper removed that still-empty dir. The
reaper's guard, `int(orphan) >= int(next_id)`, protects only claims
numbered HIGHER than the reaper's own; a LOWER claimant that has claimed
but not yet written (delayed in the anyio worker pool under load) looked
abandoned and was `rmdir`'d. Local store only: the GCS store that ships
uses `if_generation_match=0` compare-and-swap and is unaffected.

## What shipped

Built by a Sonnet builder in an isolated worktree. `LocalFormKitStore`
gains an in-process registry of in-flight claims (`_in_flight_claims`, a
set of `(kit_id, snapshot_id)` under a `threading.Lock`, because the
claim and write run on real worker threads). `_claim_snapshot_id`
registers at claim time; `put_draft_snapshot` clears in a `finally`
around the write; the reap loop skips any registered id. That is a third
guard beside the `>= next_id` bound and `_reap_if_still_empty`'s
last-instant re-check, each covering a different window. The registry
was chosen over an mtime grace window because it is exact for the only
case that exists: `get_form_kit_store()` is a cached singleton and the
image runs a single uvicorn worker.

Reproduction: `test_the_reaper_SPARES_a_LOWER_in_flight_claim` claims id
1, hooks `Path.is_dir` to fire exactly once on that directory (the spot
inside `mkdir`'s re-check) and runs a second saver's complete
`put_draft_snapshot` inside the hook. Red on the old code (WinError 183
on Windows, Errno 17 on Linux); green after; red again when the
registry clause is removed. The original concurrent test is unchanged
and still green.

## Review record

**Fresh-eyes (sonnet):** one round, GAPS-FOUND (2), both adopted. The registry clear in the
`finally` AFTER the write was claimed as load-bearing but unpinned (moving
it before the write left all 60 tests green, because the first
reproduction hand-drove the claim); a second test now drives claimant A
through the real `put_draft_snapshot` and goes red under that move. And
`_reap_if_still_empty`'s docstring counted the call-site guards as one;
there are now two. The prep suite also caught a `technical_guide.md`
citation that had drifted onto a blank line (`form_kits.py:324`);
re-anchored to the `put_schema` symbol names.

**Opus cross-surface review:** one round, NO-GAPS. Traced the registry, the claim/finally placement,
the reap-loop term, the untouched GCS store and the re-anchored
citations into their consumers; confirmed only one process ever writes
draft snapshots (cached singleton, single uvicorn worker, the admin
service only lists kits). Two beads filed, neither a gap in this PR: a
save cancelled between the claim and the write leaves its registry
entry behind and that empty dir is then never reaped (`polyglot-pdf-9kcis`,
low severity: dev-only store, an unwritten dir is never a ring member
and never blocks a claim); and eight other line-number citations in the
same `technical_guide.md` paragraph were already stale on dev
(`polyglot-pdf-ckrp4`).

**Housekeeping reviewed and left:** the stale-doc flags for files this
branch did not touch; `docs/components/pdf-filling.md` describes the
snapshot ring at feature level and never the reaper's guards, so no doc
claim changed.

## Lessons

- **A guard that protects "higher" ids assumes ordering the scheduler
  never promised.** Claim order and write order diverge the moment work
  crosses a thread pool; guards over concurrent claimants need the
  claimants' actual state, not their ids.
- **A tests-only PR can surface a production race.** Adding tests
  changed timing enough to make a latent race deterministic; the fix
  belongs in the racing code, never in the PR that revealed it.

## Doc freshness

Bumped: none. Reviewed and left: `docs/components/pdf-filling.md` (the
reaper's guards were never documented there; the code comment is the
current-state record).

## Files touched

- backend/services/form_kits.py -- in-flight claim registry; the reaper skips registered ids
- backend/tests/unit/test_kit_draft_snapshots.py -- deterministic interleaving reproduction
- docs/journal/entries/2026-09-14-bd-tcwck-snapshot-reap-race.md -- this entry
