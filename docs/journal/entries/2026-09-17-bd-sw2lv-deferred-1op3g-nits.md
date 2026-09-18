---
date: 2026-09-17
bead: polyglot-pdf-sw2lv
title: "chore(nits): deferred review nits from polyglot-pdf-1op3g"
sprint: 22
tags: [testing, review]
---

## Trigger

The fresh-eyes review of bd `polyglot-pdf-1op3g` (the A5 expiry-refund
credit ledger work) found two hygiene findings that were neither rubric-fails
nor blockers on that bead's exit criteria: a stale docstring on one of its
new tests, and a bead (`polyglot-pdf-o4h98`, filed by the same review for an
unrelated pre-existing test bug) that was itself missing the required
`## Exit criteria` section and `metadata` object mandated by the
filing-sequence rules. Per the closeout rule for deferred review findings,
both were filed together as `polyglot-pdf-sw2lv` and built here.

## What shipped

1. **Fixed the stale docstring on
   `test_the_refund_and_the_status_flip_commit_ATOMICALLY`**
   (`backend/tests/unit/test_credit_refunds.py`). The docstring claimed the
   test was "Proven by making the joined write explode and checking NEITHER
   side landed" -- a failure-injection plan the test's own body comment had
   already abandoned in favor of asserting only the positive case (both the
   balance bump and the status flip land after one `refund_expired_link()`
   call). Rewrote the docstring to describe what the test actually does, and
   to name a mutation it verifiably catches: deleting the
   `tx.set(links_ref, ...)` call inside `_mark_refunded_and_extra` (the
   `extra_writes` hook `_apply_entry_writes` invokes) leaves the links
   record at `status=minted` and the test goes red. Mutation-verified by
   making that exact deletion, watching the assertion fail
   (`assert 'minted' == 'refunded'`), then reverting.

   While mutation-verifying, found and documented a real (pre-existing, not
   newly introduced) blind spot: this test does **not** catch relocating the
   same status-flip write to run directly against `fake_db` outside the
   transaction (e.g. calling it right after `_txn(db.transaction())` returns
   instead of from inside the `extra_writes` hook). `fake_db`'s fake
   `_Transaction` has no rollback-on-exception simulation -- a write applied
   straight to the store lands identically to one buffered via `tx.set()`
   and committed, so the test stays green either way. This is now called out
   explicitly in the docstring rather than left as an implicit assumption
   the next reader could trip on. No production code changed --
   `backend/services/credit_ledger.py` is untouched by this bead.

2. **Backfilled `polyglot-pdf-o4h98`'s missing filing fields.** That bead
   (a pre-existing `test_bulk_ack_hint_counts_this_branch_not_the_whole_corpus`
   bug, unrelated to 1op3g's own fix) had no `## Exit criteria` section and
   no `metadata` object, making it invisible to any tier/work-class batching
   query. Investigated first rather than fixing blind: `o4h98` was already
   **closed** on 2026-09-09, as a duplicate of `polyglot-pdf-sisvg`, which
   landed the actual fix and both regression pins via PR #760 (also closed
   2026-09-09, confirmed with full metadata already present). `bd ready`
   only surfaces open issues, so a closed duplicate's missing metadata has
   no live batching-query consequence -- the nit's stated concern doesn't
   materialize here. Added the Exit criteria section and the three metadata
   keys (`surfaces`, `tier: sonnet`, `work_class: bugfix`) anyway, since it
   costs nothing and closes the letter of the finding, and appended a
   `STATUS: superseded` note to the bead body making clear this is
   retroactive paperwork on dead, already-fixed work -- not a claim that
   unimplemented work remains. Confirmed on `dev` (this branch fast-forwarded
   past 4 new commits before this bead's own commit) that `sisvg`'s
   merge-base-scoped fix is present in `tests/test_doc_freshness.py` and
   `scripts/check_doc_freshness.py`.

## Lessons

The worktree for this bead (`sw2lv-1op3g-nits`) already existed with
uncommitted changes from an earlier, interrupted session: the correct
docstring rewrite in the test file, but also a **live, uncommitted mutation
left in `backend/services/credit_ledger.py`** from that session's own
test-the-tests pass -- including one hunk that referenced an undefined
`links_ref` name inside `append_entry()` (a guaranteed `NameError`), clearly
a stray/broken experiment rather than intentional work. This is exactly the
"mutation-restore can revert real edits" trap: a prior session's
mutation-verify cycle did not complete before the session ended, leaving
broken production code sitting in the worktree looking like uncommitted
"real" work. Caught it by reading the full diff before touching anything
(not just the file the bead named) and running `git status`/`git diff`
before assuming the worktree was clean-but-idle. Reverted the production
file with `git checkout --`, re-ran my own mutation-verify cycle from
scratch, and confirmed the file matched `origin/dev` exactly before
committing only the test file. General lesson for future builders resuming
someone else's worktree: always diff the FULL worktree, not just the files
you expect to touch, before trusting its state.

## Doc freshness

No tier-2 doc bump needed. `docs/components/auth.md` and
`docs/standards/logging-and-cost.md` both track
`backend/services/credit_ledger.py`, but this bead did not change that
file -- only a docstring in its test file, which is not itself a
doc-tracked production surface.

## Files touched

- `backend/tests/unit/test_credit_refunds.py` -- rewrote
  `test_the_refund_and_the_status_flip_commit_ATOMICALLY`'s docstring to
  match what the test actually verifies, mutation-verified.
- `polyglot-pdf-o4h98` (bead body + metadata, not a repo file) -- added
  Exit criteria and the three required metadata keys; left `status: closed`
  unchanged.
