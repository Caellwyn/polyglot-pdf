---
date: 2026-08-18
bead: polyglot-pdf-3t190
title: "docs+test(freshness): fix DOC_DIRS enumeration drift, six review rounds deep"
tags: [conventions, testing]
---

## Trigger

Picking up follow-on beads from the prior stamp-chain-cleanup PR (#601):
`docs/doctrine` had been added to `check_doc_freshness.py`'s `DOC_DIRS`, but
three comment/docstring sites in the same file still enumerated the old
two-directory set. A small, single-file fix -- or so it looked at the start.

## What shipped

The direct fix was trivial: update the three stale sites. What made this
bead unusual is what happened next -- **six consecutive Opus outer-review
rounds, each finding one genuinely real gap**, all in the same ~15-line
region of one file:

1. **Round 1 (fresh-eyes, before the outer loop even started):** the
   finding-message text still hardcoded `'Previously:'`, and the new
   `docs/doctrine` `DOC_DIRS` membership was unpinned by any test.
2. **Round 2 (Opus):** bumping two chain-pruned stamps to today's date had
   silently cleared a real pre-existing staleness warning against backend
   files that moved after the original stamp date -- a chain-format fix is
   not a content re-verification. Also: the widened chain-detector regex
   false-positived on ordinary prose containing the bare word "bd".
3. **Round 3:** the pin test I wrote for round 1 was *itself* vacuous --
   `source.count(d) >= 2` was satisfied by the `DOC_DIRS` assignment plus
   two already-correct sites, so reverting all three intended sites at once
   left the test green. Also found a 4th stale enumeration site
   (`is_sprint_plan`'s docstring).
4. **Round 4:** the "fix" for round 3 -- bounding each site's window by the
   *next* anchor in a shared list -- broke down when anchors sit far apart:
   the module docstring's "next" anchor was ~29,000 characters away, so its
   window swallowed several already-correct sites and stayed vacuously
   green even when stale. Also found 2 more stale enumeration sites in
   `docs/doc-architecture.md`.
5. **Round 5:** redesigned to explicit per-site `(start_anchor, end_anchor)`
   pairs -- each site's boundary is now specific to that one paragraph,
   independent of any other site's position. This held. Found a 6th
   enumeration site: `is_sprint_plan`'s docstring, which an *earlier round
   of this same PR* had introduced while fixing round 3's finding (rephrased
   to "any DOC_DIRS subdirectory (components/ / standards/ / doctrine/)" --
   the parenthetical is exactly the shape that keeps desyncing).
6. **Round 6:** fixed by removing the hand-list entirely rather than pinning
   it, making the docstring structurally immune to this class of drift.
   Exhaustive re-derivation of every DOC_DIRS-related string in the file (13
   hits, categorized) found zero remaining unpinned hand-lists. **NO-GAPS.**

Every fix across all six rounds was independently mutation-verified --
revert exactly the site the round's finding named, confirm only that
site's test case goes red, restore, re-run the full suite.

## Lessons

- **"Mutation-verify per parametrization, not once" is not paranoia -- it is
  the exact mechanism that let a genuinely vacuous test ship and pass review
  twice in a row (rounds 3 and 4) before the isolated-mutation discipline
  caught it in round 5.** A whole-file or whole-batch mutation test can look
  rigorous while proving nothing about the individual cases it claims to
  guard; only reverting ONE site at a time and confirming ONLY that site's
  case fails actually pins the property.
- **A fix for one instance of a desync-prone pattern can introduce a NEW
  instance of the same pattern, in the same PR, while fixing the first
  one.** Round 3's fix (rephrasing `is_sprint_plan`'s docstring) created the
  hand-list round 5 later found stale. When a finding's shape is "prose
  hand-lists a set that can grow," the fix that actually closes the loop is
  removing the hand-list, not adding one more name to it -- a lesson visible
  only because the loop kept running instead of stopping after round 3's
  "fix."
- **A window/boundary abstraction (fixed-size, next-anchor, or otherwise)
  needs to be verified against the SPECIFIC data it will bound, not just
  "does it work for the cases I tried."** Both the 400-char window (round 3)
  and the next-anchor window (round 4) were reasonable-looking general
  strategies that failed for one specific site's real spacing. The fix that
  finally held (round 5) abandoned the general strategy for an explicit,
  per-site boundary -- more verbose, but not vulnerable to a strategy-level
  blind spot.
- **Six real rounds on one small bead is not proof the review process is
  broken -- it is the review process doing exactly its job on a genuinely
  tricky piece of self-referential tooling** (a test that pins a doc's
  claims about its own scanning behavior). The alternative was shipping a
  test that looked like it guarded against DOC_DIRS drift while actually
  guarding against nothing.

## Doc freshness

- **Bumped:** `docs/doc-architecture.md` (all remaining two-directory
  hand-lists fixed to include `docs/doctrine`, across two commits).
- **Reviewed and left:** `docs/doc-architecture.md:70`'s hand-listed scanned
  set -- verified CORRECT as written (not a gap; flagging a correct sentence
  because it shares a shape with the bug would have been the manufactured-
  finding trap the final round was explicitly warned against).

## Files touched

- `scripts/check_doc_freshness.py`
- `tests/test_doc_freshness.py`
- `docs/doc-architecture.md`
