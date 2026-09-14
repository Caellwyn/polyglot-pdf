---
date: 2026-09-14
bead: polyglot-pdf-jpy7t
title: "fix(test): applyResume.test.ts read the untracked form-kits/w7 -- frontend CI red for every PR since #780"
tags: [hotfix, testing, ci-flake, form-kits]
---

## Trigger

PR #780 (bd `nck2q`, "no form lives in git any more") untracked
`form-kits/w7/` and merged to `dev` at 21:57 UTC on 2026-09-14 with its own
CI run red. From then on every PR's `frontend vitest` job failed at
`frontend/src/schema-forms/applyResume.test.ts:27` with `ENOENT` on
`form-kits/w7/schema.json`: the test read the real shipped W-7 from disk at
module load, deliberately (its comment explains that an invented fixture
had once hidden a real bug). #780 froze the other W-7 reader
(`hiddenFieldCounting.test.ts`) but missed this one, and it kept passing
locally because the untracked scratch copy of the kit still sits on the
maintainer's disk. Found while merging PRs #789 and #791, which both went
red on this job after rebasing onto #780.

## What shipped

`frontend/src/schema-forms/__fixtures__/w7_schema_frozen.json`: a
byte-for-byte copy of the last git-tracked `form-kits/w7/schema.json`
(commit 09cf20754). The test imports it instead of reading the path. The
comment keeps the original warning about invented fixtures and adds the
scar #10 rule (kits live in the bucket; freeze the specimen). Verified in
a clean worktree with no `form-kits/w7/` present: the original test fails
with the CI error, the fixed one passes (13 tests); typecheck clean. The
other two apps' tests reference `form-kits` only as URL strings; the
backend W-7 readers are skip-guarded on the PDF's presence (silently
dead in CI, a weaker state than frozen -- part of the `1mgkq` debt).

## Review record

**Fresh-eyes (sonnet):** one round, NO-GAPS. Verified the fixture byte-identical to the last tracked schema, the section-landing assertions non-vacuous (8 real sections), and no remaining filesystem read of a kit path in any CI-collected test tree. Noted for later: nothing mechanically pins "no test reads form-kits/ by path"; that folds into the kit-coupled-tests debt (bd `1mgkq`) rather than a new bead.

**Opus cross-surface review:** one round, NO-GAPS -- run because the
auto-merge rule requires that gate and two reviewed PRs were waiting on
this merge. It verified byte-identity three ways (same git blob id as
the last tracked file), that the fixture cannot reach a shipped bundle,
and that the `pretest:run` manifest generator still finds a `form-kits/`
directory on a clean checkout. Two nits recorded, not adopted: the
fixture carries no in-file provenance key (keeping it byte-identical to
the tracked blob IS the provenance; the test comment names the commit),
and the wording below about the backend readers.

## Lessons

- **A test that passes on the author's disk and fails on a clean checkout
  is the untracked-scratch-copy trap.** The tell is an absolute or
  repo-relative path read in a test; the fix is the frozen fixture, the
  guard is scar #10.
- **Merging over a red CI run costs everyone the next day.** Two unrelated
  PRs paid for it within the hour.

## Doc freshness

Bumped: none (no doc describes this test).

## Files touched

- frontend/src/schema-forms/applyResume.test.ts -- imports the frozen schema
- frontend/src/schema-forms/__fixtures__/w7_schema_frozen.json -- the specimen
- docs/journal/entries/2026-09-14-bd-jpy7t-applyresume-frozen-w7.md -- this entry
