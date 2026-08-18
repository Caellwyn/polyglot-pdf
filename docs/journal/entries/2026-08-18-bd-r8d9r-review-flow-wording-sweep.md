---
date: 2026-08-18
bead: polyglot-pdf-r8d9r
title: "docs(review-flow): fix stale unqualified-Opus wording + doc-architecture stamp"
tags: [review, doctrine]
---

## Trigger

bd polyglot-pdf-saxh (2026-08-05) split the pre-PR outer adversarial review
into a three-way fork: the Opus `cross-surface-reviewer` for a source diff,
the new Haiku `docs-reviewer` for a docs-only diff, and no outer pass at all
for a genuinely trivial diff. That rework swept CLAUDE.md,
`docs/doctrine/workflow.md`, `docs/doctrine/planning.md`,
`docs/doctrine/review-flow.md`, and `.claude/skills/closeout/SKILL.md`, but
several files outside that sweep's scope still described the outer review as
unconditionally "Opus-5 outer review" -- silently teaching the retired
two-way (source XOR skip) framing to anyone who read them next. Five small
beads (wx7j, vreq, opak, qia8, d2bm) were filed against the individual stale
sites; a sixth (r8d9r) covered an unrelated but similarly small
`docs/doc-architecture.md` defect discovered in passing. All six were
low-complication docs-nit beads, bundled into one PR per CLAUDE.md's
bead/PR contract (several small beads too tiny to each warrant a full review
cycle).

## What shipped

Reworded every unqualified "Opus-5 outer review/loop" site to name the
three-way fork:
- `docs/branch-protection-setup.md` (2 sites) + `docs/doctrine/branch-protection-setup.md`
  (2 sites) + `scripts/swarm_config.py` (1 site) -- bd wx7j
- `scripts/closeout_finish.py` (module docstring + a module-level comment) -- bd vreq
- `AGENTS.md:12` -- bd opak
- `docs/doctrine/planning.md`'s model-tiering table, placing the Haiku
  `docs-reviewer` arm in the "Search + mechanical" tier row per the exit
  criterion -- bd qia8
- `docs/doctrine/promotion-tiers.md`'s tier diagram -- bd d2bm

Separately, bd r8d9r fixed two things in `docs/doc-architecture.md`:
1. Its `*Last updated:*` stamp had drifted into stacking two bead clauses
   ("bd lmcgz ... Also current: ... bd 6dn2n") instead of replacing the
   prior one -- exactly the history-chain shape the file's own
   current-state-only rule bans (it evaded `PREVIOUSLY_CHAIN_RE` only
   because the connective was "Also current:", not "Previously:"/"Prior:"/
   "Earlier:"). Re-pruned to name only the change this commit makes.
2. The file was not itself covered by the mechanical convention scan --
   deliberately excluded from `TIER1_DOCS` because its own body quotes real
   `**Tracks:**` example syntax that would collide with `TRACKS_RE` and try
   to freshness-check nonexistent globs. But it's the file that *defines*
   the current-state-only rule, so it should still be scanned for chains and
   history sections even though it skips freshness-staleness. Added a new
   `CONVENTION_ONLY_DOCS` list, wired only into `check_doc_conventions()`'s
   target union (`TIER1_DOCS + CONVENTION_ONLY_DOCS`), leaving the
   freshness/`TRACKS_RE` path (`find_docs()`/`find_tier1_docs()`) untouched.

## Lessons

The outer cross-surface review caught two further defects in this same
bundle, both in the SAME sentence of `docs/doc-architecture.md` (the "Sprint
plans are exempt" paragraph), across two consecutive review rounds:

1. Round 1's fix for the r8d9r stamp-chain removed the stale stamp but left
   an adjacent sentence -- the one enumerating the convention-scanned set as
   a hand-listed union -- now stale, because `CONVENTION_ONLY_DOCS` widened
   that set and the sentence didn't mention it. **This diff made a
   previously-true claim false**, which is exactly the class of gap that a
   reviewer following changed contracts OUT of the diff is built to catch.
2. Round 2's fix for that gap swapped the stale hand-list for a claim that
   `is_sprint_plan()` was the mechanism doing the excluding -- but
   `find_docs()` never globs `docs/` root at all (where sprint plans live),
   so they're never in the scanned set to begin with; `is_sprint_plan()` is
   a defensive backstop for a case (a plan force-added to `TIER1_DOCS`) that
   doesn't currently occur. The reviewer verified this by *executing*
   `find_docs()` and `is_sprint_plan()` against the real repo tree rather
   than reasoning from the docstring alone -- confirming the "verify claims
   against code, not the brief" discipline extends to a reviewer's own
   proposed fix, not just the original diff.

The generalizable lesson: rewording a doc sentence to fix one factual claim
can silently falsify an adjacent claim in the same sentence or paragraph,
especially when the two claims describe the same mechanism from different
angles ("what's excluded" vs. "how it's excluded"). A one-line fix to a
dense multi-clause sentence deserves the same "did this line's *other*
assertions survive" check as a code diff gets for its changed contracts --
and confirming a fix is correct sometimes requires running the code, not
just reading it, exactly as CLAUDE.md scar tissue #8 already prescribes for
tests.

## Doc freshness

- `docs/doc-architecture.md` -- stamp re-pruned to a single bead reference;
  the file is now itself covered by the mechanical convention scan via the
  new `CONVENTION_ONLY_DOCS` list.
- `docs/doctrine/branch-protection-setup.md`, `docs/branch-protection-setup.md`
  -- stamps bumped; both re-verified against `gh api` output as part of the
  wording fix (no drift beyond the wording itself).
- `docs/doctrine/promotion-tiers.md`, `docs/doctrine/planning.md` -- stamps
  bumped for the tier-diagram / model-tiering-table wording fixes.
- `AGENTS.md`, `scripts/swarm_config.py`, `scripts/closeout_finish.py` --
  no `*Last updated:*` stamp convention; no stamp change needed.
- `tests/test_doc_freshness.py` gained two new tests
  (`test_doc_architecture_is_in_convention_only_docs`,
  `test_doc_architecture_is_convention_scanned`), mutation-verified: the
  positive assertion reddens when `CONVENTION_ONLY_DOCS` is emptied (its own
  built-in negative control), and reintroducing a `Previously:`-style
  stacked stamp in `docs/doc-architecture.md` reddens
  `test_no_history_chains_in_current_state_docs` exactly as bd r8d9r's exit
  criterion 2 specifies (confirmed by hand, then restored).

## Files touched

- `AGENTS.md` -- reworded review description (bd opak)
- `docs/branch-protection-setup.md` -- reworded 2 sites + stamp bump (bd wx7j)
- `docs/doc-architecture.md` -- stamp de-stacked; "Sprint plans are exempt"
  paragraph fixed twice more per outer-review rounds (bd r8d9r)
- `docs/doctrine/branch-protection-setup.md` -- reworded 2 sites + stamp
  bump (bd wx7j)
- `docs/doctrine/planning.md` -- model-tiering table reworded + stamp bump
  (bd qia8)
- `docs/doctrine/promotion-tiers.md` -- tier diagram reworded + stamp bump
  (bd d2bm)
- `scripts/check_doc_freshness.py` -- new `CONVENTION_ONLY_DOCS` list, wired
  into `check_doc_conventions()`'s target union (bd r8d9r)
- `scripts/closeout_finish.py` -- reworded docstring + comment (bd vreq)
- `scripts/swarm_config.py` -- reworded docstring (bd wx7j)
- `tests/test_doc_freshness.py` -- 2 new tests for `CONVENTION_ONLY_DOCS`
  coverage (bd r8d9r)
