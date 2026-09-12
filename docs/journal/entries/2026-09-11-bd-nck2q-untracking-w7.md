---
date: 2026-09-11
bead: polyglot-pdf-nck2q
title: "Untracking the W-7: CI was testing a form the app does not serve"
tags: [testing, doctrine, conventions]
---

## Trigger

The W-7 half of bd `polyglot-pdf-nck2q` was fixed in the schema editor by the
maintainer and verified working in the demo voice app. Closing the bead meant
emptying `_KNOWN_REQUIRED_READONLY`, the guard's known-offenders allowlist,
because an entry there is a live defect and the defect was gone.

That did not work, and the reason was the interesting part.

## What shipped

### The tracked copy had drifted from the published one

Emptying the allowlist made the guard fail. The published kit was fixed; the
**git-tracked** kit was not. Measured:

| | fields | `read_only` | agent block |
|---|---|---|---|
| bucket (canonical, what the app serves) | 46 | 0 | removed |
| git (what CI tests) | 53 | 9 | present |

So CI was asserting against a form the application does not serve, and had been
since the maintainer's edits landed. The guard could not be tightened while that
was true: the allowlist was not pinning a live defect, it was pinning a stale
artifact.

That is the same failure as bd `polyglot-pdf-6p77c`, one layer over. There the
divergence broke the deployed I-90; here it silently misdirected the test suite.
A kit committed to git forks the canonical copy, and the fork is invisible until
something asserts against the wrong side of it.

### The decision: untrack w7

Maintainer's call, offered three options (refresh the tracked copy from the
bucket, untrack it, or defer into `polyglot-pdf-q3u5r`). Untracking is the only
one that does not re-fork on the next republish -- refreshing would have been
correct for exactly as long as it took to publish again.

`.gitignore`'s own comment had already specified the migration: *"publish to the
bucket, then untrack."* W-7 was published, so it was ready.

Verified before removing anything -- every tracked file present in the bucket,
`status: complete`, 46/46 reviewed, `verified: true`. Nothing was lost;
`scripts/pull-form-kits.sh` brings it back.

**`f1040` stays tracked, and that is not an inconsistency.** It is NOT in the
bucket, so git is its only copy -- untracking it would delete it. It goes the
same way once published.

### The allowlist is a real check again

`_KNOWN_REQUIRED_READONLY` is now `{}`, and the guard still has one kit
(`f1040`) to run against, so it is not vacuous -- the non-vacuity assertion in
`discovered_kits()` is what keeps that honest.

Mutation-verified rather than assumed: planting the exact defect the guard exists
to catch (a required field marked `read_only` with nothing writing it) into
`f1040` reddens it; restoring passes. Before this change, that same regression
would have been waved through for `w7` by the allowlist entry.

### The claims that went stale with it

Untracking is a contract change, and several current-state claims asserted the
old arrangement:

- `CLAUDE.md` scar #10 -- "`w7`/`f1040` remain tracked" -- tier 1, auto-loaded.
- `backend/tests/test_form_models_v2.py`'s own docstring -- "git tracks only w7
  and f1040" -- and its narrowness note, which is now thinner by one kit.
- `docs/components/pdf-filling.md` and `pdf-view.md` -- each described w7 as "the
  git-tracked" kit. The MEASUREMENTS there are still valid (47/47 resolution,
  the backfilled option rects); only the tracked-vs-bucket classification moved,
  so the fix was to re-attribute, not to re-measure.
- `.gitignore` -- the rationale block, and a now-dead
  `!form-kits/w7/w7-instructions.pdf` exception that could never fire once the
  whole directory was ignored.

Journal entries naming w7 as tracked were left alone: tier 3 is the
chronological record and was correct when written.

## Lessons

**A test allowlist can pin a stale artifact instead of a live defect.** The
entry said "known-outstanding violation, shrink as fixed". It was fixed -- in
the only copy that matters -- and the allowlist kept the test green against a
copy nobody serves. When an allowlist will not empty after the underlying fix,
suspect the specimen before suspecting the fix.

**Untracking is a contract change; enumerate its consumers.** The mechanical part
was two `.gitignore` lines and a `git rm --cached`. The rest was four files
asserting the old arrangement, one of them tier-1 and auto-loaded into every
session. Grep for the CLAIM ("tracked"), not just the identifier.

**A local suite cannot prove this one.** The worktree still has `w7` on disk, so
every kit-reading test keeps passing here while CI sees nothing. Only a clean
clone shows the truth -- the same check that should have caught two earlier
misses (`verify-in-a-clean-clone-not-your-worktree`).

## Doc freshness

- `CLAUDE.md` -- scar #10 updated (tier 1, no stamp convention).
- `docs/components/pdf-filling.md`, `docs/components/pdf-view.md` -- re-attributed
  w7 from "git-tracked" to plain; measurements unchanged, so the stamps were not
  bumped for a re-measure that did not happen.
- `.gitignore` -- rationale rewritten, dead booklet exception removed.

## Files touched

- `.gitignore` -- w7 exception removed; rationale records why and how to restore.
- `form-kits/w7/` -- six files untracked (still on disk locally, still in the
  bucket).
- `backend/tests/test_form_models_v2.py` -- `_KNOWN_REQUIRED_READONLY` emptied;
  docstring corrected.
- `CLAUDE.md`, `docs/components/pdf-filling.md`, `docs/components/pdf-view.md` --
  stale tracking claims.
