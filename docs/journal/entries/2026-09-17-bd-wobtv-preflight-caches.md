---
date: 2026-09-17
bead: polyglot-pdf-wobtv
title: "fix(deploy): preflight refuses every real deploy -- tracked Firebase cache + untracked scratch files count as dirty"
sprint: 22
tags: [hotfix, testing, doctrine]
---

## Trigger

Seen 2026-09-14 on the first `deploy-staging.sh` run after bd `polyglot-pdf-1s3ko`'s
preflight (`scripts/deploy_preflight.sh`) landed: the check refused every real
deploy attempt because the working tree was never actually clean in practice.
Two independent causes, filed as bd `polyglot-pdf-wobtv` (sprint 22
admin-console plan, Epic 4 "Cloud Build layout"):

1. `firebase deploy` regenerates `.firebase/hosting.<target>.cache` on every
   run, and three of those cache files were tracked in git -- so every
   Hosting deploy dirtied the tree that the preflight's next run then
   refused.
2. The preflight's dirty check counted untracked files, and this repo's
   checkouts are essentially never free of untracked scratch (`Claude
   outputs/`, `*.bak.py`, `prep-*.txt` left by other sessions).

## What shipped

**Untracked the cache, for good.** `git rm --cached` on the three tracked
`.firebase/hosting.*.cache` files and added `.firebase/` to `.gitignore` so a
future `firebase deploy` followed by `git add -A` cannot re-track it.
`.firebaserc` (the project/target mapping, not a cache) is a different file
and stays tracked.

**Narrowed the dirty check to tracked paths.** `deploy_preflight.sh`'s dirty
check now runs `git status --porcelain --untracked-files=no` instead of the
bare `--porcelain`. This is not a weakening for its own sake: deploy no
longer works the way the original rationale assumed. The two wrappers now run
`gcloud builds triggers run --sha=<sha>` (bd `polyglot-pdf-oqtm7`, Cloud Build
migration), which fetches ONLY the named commit from the connected GitHub
repository -- an untracked file is categorically never part of that fetch, so
it cannot make the deployed tree differ from the named commit. The original
untracked-file check dated to when deploy uploaded a local tarball
(`gcloud builds submit`), where an untracked file genuinely would ship. That
path is gone.

Untracked files are still surfaced -- `git ls-files --others
--exclude-standard`, printed to stderr as a `[NOTE]` -- so an operator
mid-deploy still sees what is lying around uncommitted; they just no longer
block the deploy over it. Chose this over the doc's alternative (b)
(gitignoring every known scratch pattern) because the untracked case has no
mechanism by which it can reach a Cloud-Build-triggered deploy at all, making
(a) the correct model of the system rather than a workaround.

**Tests** (`tests/test_deploy_preflight.py`):
- Replaced `test_an_untracked_file_is_refused` (pinned the removed behavior)
  with `test_an_untracked_file_alone_does_not_refuse` (exit 0, path named in
  the NOTE) and added `test_an_untracked_file_alongside_a_dirty_tracked_file_still_refuses`
  so the untracked carve-out cannot swallow a real tracked-file refusal.
- Added `test_no_path_under_dot_firebase_is_tracked` (`git ls-files
  .firebase` is empty) and `test_gitignore_covers_dot_firebase`
  (`git check-ignore` matches a probe path), pinning both halves of the fix.

All four new tests mutation-verified: reverted `--untracked-files=no` to
`--porcelain` (first test fails, mixed-dirty test still correctly passes);
simulated an over-broad carve-out that cleared `dirty` whenever anything
untracked existed (second test catches it); force-re-tracked one `.firebase`
cache file (tracking-pin test fails); removed the `.firebase/` line from
`.gitignore` (gitignore-pin test fails). All restored and re-verified green.

**Collateral fix**: `tests/test_deploy_wrappers.py`'s
`test_a_dirty_tree_is_still_refused_before_any_trigger` used an untracked
scratch file as its "dirty tree" fixture. The full root test suite caught
this directly: with the untracked-file carve-out in place, the fixture no
longer produced a dirty tree at all, so the wrapper actually ran the deploy
and the test's `assert proc.returncode != 0` failed for real (not a false
green -- a genuine, expected regression from the behavior change above).
Switched the fixture to an uncommitted edit of a tracked wrapper file, which
still must refuse. Mutation-verified (mutated the preflight's `dirty`
variable to always be empty; test correctly failed).

**Docs**: `docs/doctrine/promotion-tiers.md`'s "Deploy preflight" section
updated to current state (untracked files noted not refused, why; the
tracked-cache half of the bug and its fix) plus the fresh-detached-worktree
(with a `node_modules` junction) deploy pattern the bead asked to record, per
CLAUDE.md's "current state only" doc rule.

## Lessons

A preflight rationale needs re-checking whenever the mechanism it protects
changes underneath it. The untracked-file refusal was correct when deploy
uploaded a local tarball; it became a false positive with zero remaining
upside the moment deploy moved to fetching a named commit from GitHub, but
nothing forced that re-check -- the check kept "working" (refusing) right up
until it refused everything. Worth watching for elsewhere: any check whose
comment cites a specific transport mechanism (upload, submit, fetch) is worth
re-reading after that mechanism changes, not just when the check itself is
touched.

## Doc freshness

`docs/doctrine/promotion-tiers.md` bumped (current-state edit to the existing
"Deploy preflight" section, stamp bumped to 2026-09-17 with a bd
`polyglot-pdf-wobtv` note appended to the running parenthetical log per this
doc's existing convention). No `**Tracks:**` line on this doc, so
`check_doc_freshness.py` does not check it mechanically; reviewed by hand.

`scripts/check_doc_freshness.py` flagged several *other* tier-2 docs as stale
against files whose mtimes reflect this worktree's checkout from `origin/dev`,
not any edit made in this bead (`docs/standards/ai-models.md`,
`docs/standards/bead-tiers.md`, `docs/standards/hipaa-pii-policy.md`,
`docs/standards/logging-and-cost.md`, `docs/standards/security-posture.md`,
`docs/standards/terminology.md`, `docs/standards/testing.md`,
`docs/standards/ws-protocol.md`, `docs/technical_guide.md`). None of their
tracked files were touched by this bead; left as-is per the closeout triage
rule (pre-existing staleness, noted here rather than fixed in this PR).

Review outcomes recorded in the closeout ping.

## Files touched

- `.gitignore` -- added `.firebase/` ignore rule with rationale comment.
- `.firebase/hosting.ZnJvbnRlbmRcZGlzdA.cache`,
  `.firebase/hosting.ZnJvbnRlbmRcZGlzdFxzY2hlbWEtZm9ybXM.cache`,
  `.firebase/hosting.c2NoZW1hLWVkaXRvclxkaXN0.cache` -- untracked (`git rm --cached`).
- `scripts/deploy_preflight.sh` -- dirty check narrowed to tracked paths;
  untracked files reported as a `[NOTE]`, not fatal; header comments updated.
- `tests/test_deploy_preflight.py` -- untracked-file test flipped to pin the
  new behavior; added a mixed-dirty test and two `.firebase/` tracking pins.
- `tests/test_deploy_wrappers.py` -- fixed one test's fixture to use a dirty
  tracked file instead of an untracked one.
- `docs/doctrine/promotion-tiers.md` -- "Deploy preflight" section updated to
  current state; fresh-detached-worktree deploy pattern recorded.
