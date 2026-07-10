---
date: 2026-07-10
bead: polyglot-pdf-vj3x
title: "bd_safe.py dep-add --epic/--child broken by bd validation (epics can only block other epics)"
tags: [harness, doctrine]
---

## Trigger

The installed bd now rejects `bd dep add <epic> <child>` (a task-blocks-epic
blocks edge) with "epics can only block other epics, not tasks", so the
documented epic-wiring path -- `bd_safe.py dep-add --epic/--child` and the
/plan-epic skill's step-4 instruction -- failed outright. Sprint-8 (js7q) and
sprint-9 (oaiz) had already switched to the working convention by hand:
epic-child is a parent-child edge (`bd dep add <child> <epic> -t parent-child`),
sibling ordering stays a plain blocks edge. This PR also bundles
polyglot-pdf-xrf4, a stale-docs chore from the 97mu fresh-eyes pass.

## What shipped

- `scripts/bd_safe.py cmd_dep_add`: the `--epic/--child` form now emits
  `bd dep add <child> <epic> -t parent-child` (child gains PARENT = epic) with
  a matching done-message; `--blocked/--prereq` keeps the plain blocks form.
  Docstrings + argparse help updated to the new semantics.
- `tests/test_bd_safe.py`: the epic/child direction test now asserts the
  parent-child command shape (child first, epic second, `-t parent-child`).
- Doc sweep of the stale convention: `.claude/skills/plan-epic/SKILL.md`
  (step 4), `.claude/skills/closeout/SKILL.md` (Step 1 detail), and
  `docs/doctrine/workflow.md` all now document the parent-child form.
- Live-verified against the current bd: created two throwaway beads, ran the
  worktree's `bd_safe.py dep-add --epic/--child`, confirmed `bd show <child>`
  reports PARENT = epic, then deleted both scaffold beads and pushed.
- xrf4: `docs/sprint_1_harness-tuning_plan.md` no longer references the
  nonexistent "closeout Step 8.5"; the telemetry step is Step 7, with the row
  written by `closeout_finish.py` in Step 6.
- Fresh-eyes triage: round 1 (sonnet) NO-GAPS; required Opus final round
  NO-GAPS. Nothing adopted/rejected/deferred (zero findings); no beads filed.
  Outer review (Step 5.6): primary Opus NO-GAPS + second independent Opus
  NO-GAPS on the identical final diff, one round each.

## Lessons

- When a vendored tool (bd) tightens validation, the wrapper scripts AND every
  skill/doctrine doc that spells out the old command must move in one sweep --
  the broken instruction lived in three docs beyond the script itself. Grep for
  the old command shape before calling the fix done.

## Doc freshness

- `.claude/skills/plan-epic/SKILL.md`, `.claude/skills/closeout/SKILL.md`,
  `docs/doctrine/workflow.md` updated as part of the fix (current-state only).
- `docs/sprint_1_harness-tuning_plan.md` step refs fixed (bd xrf4).
- Prep flagged several `docs/standards/*` + `docs/technical_guide.md` as stale,
  but every tracked file they point at was changed on dev by earlier PRs, not
  this branch (this branch touches only tooling/skills/docs above) --
  reviewed and left per the "already stale before you" rule.

## Files touched

- scripts/bd_safe.py
- tests/test_bd_safe.py
- .claude/skills/plan-epic/SKILL.md
- .claude/skills/closeout/SKILL.md
- docs/doctrine/workflow.md
- docs/sprint_1_harness-tuning_plan.md
- docs/journal/entries/2026-07-10-bd-vj3x-dep-add-parent-child.md
