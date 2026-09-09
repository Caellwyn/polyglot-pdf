---
date: 2026-09-09
bead: polyglot-pdf-sisvg
title: "test(freshness): the bulk-ack hint test fails for any branch that adds the first .ack files to an ack-less base"
sprint: 22
tags: [testing, hotfix]
---

## Trigger

`tests/test_doc_freshness.py::TestFreshnessAcks::test_bulk_ack_hint_counts_this_branch_not_the_whole_corpus`
failed on CI for PR #754 (bd polyglot-pdf-1op3g), which committed the repo's
first two `.ack` files onto an ack-less base. This bead (a standalone bug
bead, not tied to a specific sprint-22 admin-console plan section) fixes
the test.

## What shipped

The test's own `committed_on_base` derivation was wrong, not the production
code. It computed:

```python
committed_on_base = [p for p in ack_dir.glob(...) if git_commit_time(p) is not None]
```

`git_commit_time` returns non-None for a file committed on the CURRENT
BRANCH, not just one already on the base -- `git log -1` walks everything
reachable from HEAD. So for PR #754 (corpus = 2, `branch_ack_count()` = 2,
both files committed only on the branch), `committed_on_base` came out
non-empty and the test asserted `branch < corpus or branch == 0` against
`2 < 2 or 2 == 0` -- false. The test's own comment ("this branch adds no
acks") was an assumption about the working tree at the time it was written,
not a property of the code under test.

`branch_ack_count()` in `scripts/check_doc_freshness.py` was verified
correct by hand before touching anything: it scopes via
`git diff --name-only merge_base HEAD -- docs/freshness`, which returns
only the branch's own additions regardless of whether the base has zero
acks or many. No production code changed.

Replaced the flawed real-repo integration test with two hermetic,
fixture-based tests in `tests/test_doc_freshness.py`, following the existing
`test_branch_ack_count_actually_reads_uncommitted_acks` fake-subprocess
pattern:

- `test_bulk_ack_hint_counts_this_branch_not_the_whole_corpus_first_acks`:
  a branch adding the first N acks to an ack-less base -> `branch == corpus`.
- `test_bulk_ack_hint_counts_this_branch_not_the_whole_corpus_incremental`:
  a branch adding one ack over a base that already holds M -> `branch == 1`,
  `branch < corpus`.

A shared `_fake_branch_ack_count` helper scripts `git merge-base`, the
scoped `git diff`, and `git status --porcelain -z -uall` so `branch_ack_count()`
runs end-to-end without touching the real repo's ack corpus (previously the
test read the real `docs/freshness/` directory, which made it depend on
whatever acks happened to exist in the working tree at test time).

## Lessons

Deriving "was this already true on the base" from "does this have ANY
commit" is a recurring trap once a repo has branches: a commit exists the
moment it lands on the branch, well before it reaches the base. The correct
question is always "is this file's content present in the base's TREE",
answerable via `git ls-tree <merge-base>` or (as used here) by making the
test's own fixture the source of truth for what the base holds, rather than
reading `git log` against the live repo and hoping the working tree matches
the test's assumption.

## Doc freshness

No tier-2 `docs/components/*.md` or `docs/standards/*.md` doc has a
`**Tracks:**` line covering `tests/test_doc_freshness.py` or
`scripts/check_doc_freshness.py` (confirmed by grep across all tier-1/tier-2
docs). No doc bump needed. Review outcomes recorded in the closeout ping.

## Files touched

- `tests/test_doc_freshness.py` -- replaced the flawed real-repo integration
  test with two hermetic fixture-based tests pinning both exit-criteria
  cases, mutation-verified.
