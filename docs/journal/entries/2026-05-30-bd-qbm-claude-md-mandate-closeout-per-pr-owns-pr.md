---
date: 2026-05-30
bead: polyglot-pdf-qbm
title: "CLAUDE.md: mandate /closeout per-PR (owns PR creation + copilot_watch + bead close)"
tags: [conventions, review]
---

## Trigger

`bd polyglot-pdf-qbm`. During the docs-reorg sprint, this session opened PRs
manually (`gh pr create`) and then hand-polled `gh api .../pulls/<n>/comments`
to find Copilot's review feedback. That manual loop **silently missed comments**
on PRs #18 and #20 (the maintainer had to point them out), and left beads open
longer than they should have been. Root cause: the full review-and-closeout
protocol -- and specifically `scripts/copilot_watch.py`, the script that watches
a PR for Copilot's review verdict and wakes the agent once with it classified --
is documented only in **pull-on-demand** surfaces (the `/closeout` skill body,
the doctrine docs). The **always-loaded** tier-1 doc (`CLAUDE.md`) named the
review *flow* ("parallel with Copilot") but neither made `/closeout` mandatory
nor mentioned the watcher, so the protocol was discoverable but not *surfaced*.

## What shipped

**`CLAUDE.md`** -- rewrote the "Sprint closeout" section (renamed to
"Closeout -- mandatory, once per PR"). The new section states, in always-loaded
context:

- **Every PR ships through `/closeout`; no PR is "done" until closeout has run
  it to clean.** The unit is the **PR, not the bead** -- a PR may resolve several
  beads, so run closeout once per PR and close all the beads it resolves. (This
  scoping matters: the repo bundles multiple beads into one PR.)
- **`/closeout` owns PR creation** -- finish + commit, *then* invoke it; do **not**
  `gh pr create` first (a manually-opened PR breaks the skill's parallel-review
  setup and invites hand-polling).
- **Copilot is watched by `scripts/copilot_watch.py` via `run_in_background`**,
  never by hand. **Never poll `gh api .../comments`** -- that's the exact
  expensive loop the watcher replaces, and it silently misses comments.
- Fresh-eyes runs in parallel; fix the combined findings, push once, **loop
  Copilot to CLEAN**; closeout then closes the bead(s) and pings the maintainer
  (never merges).

**Bead/PR contract (clarified after Copilot review).** Copilot's round-1 review
caught that "a PR may resolve several beads" contradicted the repo's existing
"one bead = one PR" doctrine (`workflow.md`, `promotion-tiers.md`, and the skill
closing a single `$1` bead). The maintainer resolved it: **a bead never spans
PRs (one bead = one PR), but a PR may bundle several whole beads when each is too
small to warrant its own cycle, and every PR closes at least one bead.** Aligned
all four surfaces in this PR so they agree: CLAUDE.md, `docs/doctrine/workflow.md`,
`docs/doctrine/promotion-tiers.md`, and the `/closeout` SKILL (resolve/close
**all** the PR's beads, not just `$1`). Also corrected scar-tissue #2 (it implied
fresh-eyes runs *before* the PR opens; closeout opens the PR first, then reviews
in parallel) and tightened the `copilot_watch` verdict wording (CLEAN/COMMENTS
both exit 0; ERROR=1; TIMEOUT=2 -- not four distinct codes).

The `/closeout` SKILL stays the source of truth for the checklist; the CLAUDE.md
section just makes running it **non-optional, once per PR**. Left scar-tissue #5
untouched to avoid conflicting with the unmerged `m3f` PR (#18).

**Dogfood:** this very change was shipped *through* `/closeout` (not hand-rolled).
The run proved the value immediately -- the background `copilot_watch.py` woke the
session once with `RESULT: COMMENTS` (the bead/PR contradiction above), exactly
the feedback the old hand-polling had been missing.

Nothing deferred.

## Lessons

- **A tool that isn't surfaced in always-loaded context effectively doesn't
  exist for the agent.** `copilot_watch.py` was available and purpose-built, but
  because it lived only in on-demand docs, the agent reinvented the manual
  polling it was designed to replace. When a capability must be used *every
  time*, its trigger belongs in the tier-1 doc, not a skill body that loads only
  when explicitly invoked. The fix for a discovery gap is promotion to the
  always-loaded surface, not more docs deeper in the tree.
- **Scope the workflow unit explicitly.** "Run closeout per bead" would have been
  wrong here -- PRs bundle beads. Naming the unit as the **PR** prevents both
  over-running (a closeout per bead in a multi-bead PR) and under-running.

## Doc freshness

`check_doc_freshness.py`: `docs/standards/stateless-architecture.md: OK -- all
tier-2 docs up to date` (that doc is present on this branch, having merged to
`dev` via #20 before this branch was cut). This change touches no
`**Tracks:**`-bearing doc -- only `CLAUDE.md` (tier-1) -- so nothing went stale;
the convention checks (no `Previously:`/history) pass. No stamp bump needed
(CLAUDE.md carries no `*Last updated:*` stamp by design). (The skill-load Step-2
auto-run printed "No docs to check" because it ran *before* the Step-6 rebase
pulled #20 into the branch; the post-rebase result above is the accurate one.)

## Files touched

- `CLAUDE.md` -- rewrote the closeout section: mandatory once per PR, closeout
  owns PR creation, `copilot_watch` not hand-polling, loop-to-clean, close beads.
- `docs/journal/entries/2026-05-30-bd-qbm-claude-md-mandate-closeout-per-pr-owns-pr.md`
  -- this entry.
