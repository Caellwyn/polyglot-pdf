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

The `/closeout` SKILL stays the source of truth for the checklist; this section
just makes running it **non-optional, once per PR**. Touched only the closeout
section -- left scar-tissue #5 and everything else untouched to avoid conflicting
with the unmerged `m3f` PR (#18).

**Dogfood:** this very change was shipped *through* `/closeout` (not hand-rolled),
exercising the protocol end-to-end as the acceptance check.

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

`check_doc_freshness.py`: "No docs to check" (`docs/components/` + `docs/standards/`
empty on this branch -- the populated standards docs are on unmerged branches
#18/#20). The only doc changed is `CLAUDE.md` (tier-1); no `**Tracks:**`-bearing
doc was touched, and the convention checks (no `Previously:`/history) pass. No
stamp bump needed (CLAUDE.md carries no `*Last updated:*` stamp by design).

## Files touched

- `CLAUDE.md` -- rewrote the closeout section: mandatory once per PR, closeout
  owns PR creation, `copilot_watch` not hand-polling, loop-to-clean, close beads.
- `docs/journal/entries/2026-05-30-bd-qbm-claude-md-mandate-closeout-per-pr-owns-pr.md`
  -- this entry.
