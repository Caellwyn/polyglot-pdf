---
date: 2026-06-09
bead: polyglot-pdf-8y7
title: "Undeclared-surface claims lock the whole next-bead board"
tags: [harness, doctrine]
---

## Trigger

Hit the same board-lock twice in one session. After PR #121 (and again after
opening PR #122, against the live `g8w` claim / PR #123), `/next-bead` reported
**0 AVAILABLE, all ~50 ready beads BLOCKED** -- each "blocked by" a single
in-progress claim that had declared no `metadata.surfaces`. The collision guard
treats an undeclared claim as UNKNOWN and conservatively collides it with
*everything*, so one under-declared claim freezes the whole board until it merges.
Both times the lock was a pure metadata artifact: the blocking claim's actual PR
diff did not overlap the beads it was blocking. The maintainer's call was explicit
-- "change that bug where beads with no surface coverage block everything" -- so
this is the root-cause fix, not a per-pick workaround.

## What shipped

`_bead_surfaces` now resolves a bead's change-surfaces in priority order
(`scripts/bd_safe.py`):

1. **Declared `metadata.surfaces`** -- authoritative when present (unchanged).
2. **Derived from the bead's open PR(s)** -- if it declared none, fetch the files
   its open PR actually changes (`gh pr view <n> --json files`, scoped by the same
   open-only, title-boundary match `_pr_collision` uses). This is the real
   mid-flight footprint, strictly better than UNKNOWN.
3. **`[]` (genuinely UNKNOWN)** -- only when there is neither a declaration nor an
   open PR. The conservative collide-with-everything policy in `_surfaces_overlap`
   still applies to this case, so the guard is **not weakened** -- it just stops
   firing on claims whose real footprint is knowable.

New helpers: `_pr_numbers_for_bead`, `_pr_changed_files`,
`_derive_surfaces_from_prs`. `_bead_surfaces` gained `derive_from_prs` (default
True) + `repo` params. `next_bead.py` passes `derive_from_prs=False` for
**candidates** (ready/open beads have no PR yet, so derivation would be ~50 wasted
`gh` calls) and keeps it ON for **active claims** (the side that needs the real
footprint). Updated the UNKNOWN-policy docstrings/comments to describe the
narrowed case.

Verified end-to-end: with the live `g8w` claim (PR #123, undeclared surfaces),
`next_bead.py` went from **0 AVAILABLE -> 4 AVAILABLE** (`uov.2`, `uov.3`, `o1s`,
`h2r.2`), all of whose declared surfaces are disjoint from #123's diff; beads that
genuinely overlap #123, or that declared no surfaces on their OWN side, stay
correctly blocked. 16 tests in `tests/test_bd_safe.py` cover the derivation paths
(after the review-driven hardening below); harness suite 396 passed.

Decisions (for the merge report): used the **PR-diff derivation** approach
(option 1 of the four in the bead) over requiring surfaces at claim time (option
2/4, more disruptive -- would reject existing undeclared claims) or a softer
UNKNOWN policy (option 3, weakens the guard). Claimed `8y7` with
`--no-surface-check` because the board was locked by exactly the bug being fixed
and I had verified from #123's diff there was zero real overlap with this bead's
surfaces (`scripts/next_bead.py`, `scripts/bd_safe.py`) -- a maintainer-directed,
verified-safe use of the override, not a routine bypass.

### Review (3 Codex rounds + fresh-eyes; all findings adopted)

The first cut of the derivation was too OPTIMISTIC -- it trusted partial/uncertain
data instead of blocking. Codex + fresh-eyes converged hard on one principle, which
the final code now follows everywhere: **any uncertainty in deriving a footprint
collapses to UNKNOWN (conservative block), never a partial footprint.**

- **Round 1 (Codex 4 P1s + fresh-eyes 2 SHOULD-FIX/3 NIT, all adopted):** a
  `bd show` failure must stay UNKNOWN (don't let a narrower PR diff override an
  unreadable-but-declared list); `gh pr view --json files` caps at 100 files -> a
  >=cap list may be truncated -> UNKNOWN; a failed lookup in a multi-PR union ->
  UNKNOWN, not a partial union; the helpers return `None` (couldn't-determine)
  vs `[]` (confident empty). Nits: claim-path skips derivation; comment wording;
  the now-misleading missing-metadata test asserts no gh call.
- **Round 2 (Codex 1 P1, adopted):** my round-1 "include the renamed old path" fix
  was WRONG -- `gh pr view --json files` exposes no previous filename (verified
  against the live API; the GraphQL `PullRequestChangedFile` schema has only
  `path`/`changeType`/counts). So a `changeType == RENAMED` entry -> UNKNOWN for
  that PR, since the old path it also writes is invisible.
- **Round 3 (Codex 2 P1s, adopted):** a MISSING/empty `changeType` also -> UNKNOWN
  (can't confirm it isn't a rename); and `gh pr list` defaults to `--limit 30`, so
  a >30-match search could page off the real PR -> scope the search to `in:title`
  (collapses matches to ~1) AND raise `--limit` to 200.
- **Ceiling note:** each round found a NEW, distinct, fully-fixed issue (not
  re-litigation), so the 3 rounds were convergence, not a loop. Past the
  `MAX_REVIEW_ROUNDS=2` ceiling the maintainer chose to merge rather than run a
  4th verification round -- the remaining theoretical edges (>30 matching PRs, an
  absent `changeType`) are now handled conservatively.

## Lessons

- **A conservative default that fires on MISSING data, not on EVIDENCE of
  conflict, will lock the system the moment anyone under-declares.** The fix
  wasn't to relax the conflict rule -- it was to find the evidence (the PR diff)
  before falling back to "assume the worst." Same shape applies anywhere an
  UNKNOWN-collides-everything policy gates a shared resource.
- **The candidate side still under-declares.** Ready beads with no surfaces are
  UNKNOWN on their own side and still block; PR-derivation can't help them (no PR
  yet). The durable fix is declaring surfaces at creation -- a doctrine nudge, not
  code. Noted, not in scope here.

## Doc freshness

No tier-2 doc `**Tracks:**` `scripts/bd_safe.py` or `scripts/next_bead.py`, so
nothing was invalidated by this change. The many stale docs the prep flagged
(`auth.md`, `voice-ai.md`, `config-deployment.md`, etc.) track backend/frontend
source touched by OTHER sessions on 06-07/06-08 -- not this diff -- and were
already stale before this branch; left as-is. `docs/standards/testing.md` is
current.

## Files touched

- `scripts/bd_safe.py` -- PR-diff surface derivation (3 new helpers +
  `_bead_surfaces` source-order rework + UNKNOWN-policy doc updates).
- `scripts/next_bead.py` -- `derive_from_prs=False` for candidates; comment on the
  active-claim derivation.
- `tests/test_bd_safe.py` -- 7 tests covering declared-wins, no-derive flag,
  derive-from-PR, no-PR-UNKNOWN, PR-view-failure, multi-PR dedup, and the
  disjoint-candidate unblock.
