---
date: 2026-09-08
bead: polyglot-pdf-pmvrl
title: "PR #738 squash-merged a stale head and dropped its last three commits"
tags: [postmortem, review, testing]
---

## Trigger

PR #738 (the editor-publish fix, bd `polyglot-pdf-6p77c`) merged. Verifying the
deploy afterwards, the runtime fix was present in `dev` but the guard added later
in the same PR was not.

## What shipped

The three dropped commits, cherry-picked onto current `dev`:

  d4f2ef53  the required-vs-read_only guard
  32c0cfca  two fixes to that guard (dead carve-out; wrong lint remedy)
  d8b772ae  copy_to list hardening

The two touched files (`test_form_models_v2.py`, `schema_lint.py`) are
**byte-identical** to the versions that cleared ten adversarial review passes --
verified by diffing against `d8b772ae` rather than assuming the cherry-picks were
faithful. No re-review of their content was needed; what changed is the base.

### What actually happened

GitHub's PR object had `headRefOid` cached at `99230e20` while the branch ref had
advanced to `d8b772ae`. Both were checked directly:

  gh api .../git/refs/heads/<branch>   ->  d8b772ae   (the real tip)
  gh pr view --json headRefOid          ->  99230e20   (four commits behind)

The merge used the **cached** value. Because it was a squash, no commit from the
branch is an ancestor of `dev`, so ancestry checks are useless here -- the only
reliable test is content. By content: `dev` HAS `store_is_authoritative` in
`form_kit_routes.py`, and has ZERO occurrences of
`required_fields_are_not_read_only`.

The lag had already been visible earlier in the same PR: CI never fired on the
new commits at all. I worked around that with `gh workflow run --ref <branch>` to
get a green run against the real head, and confirmed it -- but I treated it as a
CI-reporting quirk. I did not draw the obvious inference that a merge would read
the same stale field.

### Why recovering it mattered rather than rewriting it

The guard is what FOUND bd `polyglot-pdf-nck2q`: a required field on the shipped
W-7 (`countries_of_citizenship`) that the voice model refuses to fill, because it
is marked read-only with nothing writing it and no unlock, against a PDF widget
that is not even locked. That is a live P1 on one of the two forms in the
deployed catalogue.

Without the guard in `dev`, nothing stops the next kit reintroducing that shape --
and `nck2q`'s own exit criterion 3 ("the guard passes for every tracked kit")
cannot be satisfied by a guard that does not exist.

## Lessons

**`--match-head-commit` is not ceremony -- it is the only thing that makes this
failure loud.** `gh pr merge --match-head-commit <sha>` refuses when the head has
moved, which is exactly this case. A merge performed by any path that does not
pass it -- the web UI included -- has no such protection, and the failure is
silent: green CI, a merged PR, a clean tree, and three commits quietly gone.

**When a PR's `headRefOid` disagrees with the branch ref, stop.** Do not merge
until they converge. The disagreement is cheap to check and is the whole tell.

**A workaround is a signal, not a solution.** I noticed the symptom (CI not
firing), routed around it, and verified the thing I was worried about. What I did
not do was ask what ELSE reads the field I had just proven was stale. Working
around a broken input without asking what else consumes it is how a known problem
becomes an unknown one.

**Ancestry proves nothing after a squash.** `git merge-base --is-ancestor`
returned "no" for every commit on the branch, including the ones that DID land --
which reads identically to "nothing merged". Only a content check
(`git show origin/dev:<file> | grep`) distinguishes the two.

## Doc freshness

No docs changed. The doc-freshness checker flags several `docs/components/*`
files as stale, but every one tracks files this branch does not touch -- this
change is confined to two backend files. Nothing to bump.

## Files touched

- `backend/tests/test_form_models_v2.py` -- the guard, its `copy_to` carve-out
  read from the raw schema dict, and the `_KNOWN_REQUIRED_READONLY` equality pin
  (currently `{"w7": ["countries_of_citizenship"]}`, tracking the live defect).
- `backend/services/schema_lint.py` -- the corrected
  `readonly-conditional-no-unlock` remedy, which no longer prescribes an unlock
  that silences the linter while leaving a required field unfillable.
