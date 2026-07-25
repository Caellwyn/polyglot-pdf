---
date: 2026-07-25
bead: polyglot-pdf-6fr5
title: "Sprint 15 planned: relationship extraction (successor to epic 7a9)"
tags: [planning, extraction]
---

## Trigger

Maintainer asked for a first draft plan for the extraction epic's next phase
(7a9 is 22/24 complete; its sprint-5 rubric is met on criteria 1-4). The
initial broad draft (instructions + relationships + form onboarding +
hardening) was narrowed by the maintainer in review to ONE target:
relationship extraction. `help.instructions` is owned by a parallel session;
I-589/big-form stays indefinitely parked; no form-coverage expansion; i-90
stays the gold standard (tune set) and w7 the cross-format test set.

## What shipped

- `docs/sprint_15_relationship-extraction_plan.md` -- the approved plan: Why
  (best arm recovers ~45-55% of show_if; conditional_logic/
  conditional_behavior 0% across all arms, per the 7a9.5 recommendation), a
  4-criterion exit rubric (metrics+baselines; i-90 bars; w7 generalization
  with no tuning; zero silent drops), and the R1-R4 bead tree. INDEX.md
  Active-sprint row added.
- Epic `polyglot-pdf-o2bs` + children filed and wired (parent-child via
  bd_safe.py; ordering R1->R2->R3; R4 parallelizable): `eprg` (R1 metrics +
  baselines), `dsbl` (R2 research bake, i-90-only tuning, /experimentation
  gates), `kfni` (R3 ship), `xbfm` (R4 harvest completeness in the
  controls_fields mirror). Epic carries `plan:` + `sprint: 15` metadata.

## Key planning finding

"Bidirectional relationships" resolved against code ground truth: the v2
schema stores relationships TARGET-SIDE only (`controls_fields` was deleted
at the P6.2 flip, bd d9lz; `scripts/schema_score.py:496-506` excludes it),
but `backend/services/controls_fields_mirror.py` already canonicalizes
trigger-side draft emissions (shows -> show_if, makes_required ->
require_if). The four unconvertible actions (hides/locks/unlocks/
makes_optional) are exactly the conditional_logic/conditional_behavior
territory scoring 0% -- so the epic frames "bidirectional" as harvest-and-
canonicalize with zero silent drops, not trigger-side storage.

## Decisions defended

- New epic + sprint 15 rather than re-scoping 7a9 (one epic = one approved
  plan; 7a9's open children ue5s/7a9.19 unaffected).
- Research-then-ship split (R2 picks on i-90 only; w7 never iterated
  against) mirroring the 7a9 bake pattern.
- Provisional rubric bars (i-90 show_if+require_if >= 70%, logic keys >=
  50%, w7 >= 60% or +20 points) finalized at R1 baseline time and logged on
  the epic bead, per planning.md's rubric rule (changes are logged on the
  epic bead).

## Doc-freshness note

closeout_prep flagged ~16 STALE tier-2 docs; reviewed against this branch's
diff: every flagged doc cites code files changed by OTHER already-merged
branches (dates 2026-07-05..2026-07-25, all predating or unrelated to this
docs-only branch, which touches only the sprint-15 plan, the INDEX row, and
this entry). Pre-existing drift, not caused here; left to the owning
surfaces' next code PRs.
