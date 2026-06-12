---
name: plan-epic
description: Scope + Plan a whole feature (epic) under the SPEAR protocol BEFORE any code is written -- probe the maintainer's Why until crisp, challenge the How, fan out research to cheap subagents, draft a 2-5 criterion exit rubric, MECE-decompose into child beads that each inherit >= 1 criterion, and gate on maintainer approval before writing the sprint plan + filing the beads. Orchestrator-owned (a subagent cannot converse with the maintainer). Use at the START of a feature, before /next-bead. Optional argument: a one-line feature description to seed the L1 intake.
---

# Plan an epic (SPEAR: Scope + Plan)

You are scoping and planning a whole feature up front. This skill encodes the
**Scope + Plan** half of SPEAR (the doctrine lives in
[`docs/doctrine/planning.md`](../../../docs/doctrine/planning.md)); the **Execute /
Assess / Resolve** half is each child bead's normal cycle through `/next-bead`
and `/closeout`.

> **Orchestrator-owned -- never delegate this skill to a subagent.** Steps 1, 3,
> and 5 require a real back-and-forth with the maintainer (probing the Why,
> confirming the rubric, the approval gate), and subagents cannot converse with
> the maintainer. You (the orchestrator) run this skill yourself; you delegate
> only the Step-2 *research* to cheap subagents.

> **Model tiering.** This is a decision-gate skill: run it on the strong model
> (Fable/Opus). The orchestrator **never greps** -- Step 2 fans research out to
> Explore/Haiku and keeps the conclusion. (See the model-tiering table in
> `planning.md`.)

`$1` (optional) is a one-line seed for the feature -- weave it into Step 1; it
does not skip the intake.

## Step 1 -- L1 intake + challenge the How (with the maintainer)

1. **Pin down the Why (L1).** The maintainer owns the outcome. Probe until it is
   crisp: who is it for, what changes for them, why now. Do NOT invent the Why;
   if it is vague, ask. Write it as one short paragraph you can read back.
2. **MANDATED -- challenge the How (L2).** Before planning the decomposition,
   **name the blind spots and better paths in the maintainer's proposed
   approach.** This is the single most load-bearing step: a flawed approach
   named at planning time costs one sentence; named mid-execution costs a re-do.
   Silent agreement is the failure mode this step exists to prevent. State your
   pushback plainly and let the maintainer respond -- the How is collaborative
   (planning.md L1/L2/L3 table), so disagreement here is expected, not
   insubordinate.

Do not proceed to research until the Why is crisp and you have surfaced your How
concerns.

## Step 2 -- Research fan-out (cheap subagents; you never grep)

Establish codebase ground truth for the decomposition. **Delegate every search**
to `Explore` (or a Haiku `general-purpose`) subagent -- you hold the plan, not
the file dumps. Ask them for: which files/surfaces the feature touches, existing
patterns to reuse, and any landmine the plan must route around. Run independent
searches concurrently (one message, several Agent calls). Collect conclusions.

## Step 3 -- Draft the exit rubric (confirm with the maintainer)

Draft the epic's **exit rubric** and confirm with the maintainer that it captures
success **from the user's perspective**.

**Format (inline -- do not rely on any other doc to apply it):**
- **2-5 criteria** for an epic.
- Each is **binary** (PASS/FAIL, no "mostly"), **measurable** (a named file to
  read, a script to run, or a behavior to observe), **outcome-based** (what the
  user/maintainer can verify), and **SMART-style**.
- Pair each criterion with its **Verify** step -- the exact read/run/observe that
  settles PASS vs FAIL.

**Rubric rules (inline):**
- **Outcomes, not proxies** -- "the mic streams across a breakpoint crossing,"
  not "the reconnect handler was refactored." A proxy can pass while the outcome
  fails.
- **Never softened because it is hard** -- if a criterion is the right bar it
  stays, even when inconvenient to meet.
- **Changes logged on the epic bead** -- a rubric may change as understanding
  improves, but record what changed and why on the bead; never silently.

Write the rubric as a numbered table (`# | Criterion | Verify`).

## Step 4 -- MECE decomposition into child beads

Decompose the epic into child beads. Each child:
- declares its **`metadata.surfaces`** (the files/dirs it will MODIFY -- the
  change-surface collision guard keys on this);
- gets a **parent-child dep** wired with `scripts/bd_safe.py dep-add --epic
  <epic-id> --child <child-id>` (direction-safe: the epic is blocked BY its
  children);
- carries a **`## Exit criteria`** section in its body **inheriting >= 1 epic
  criterion** (the criteria-inheritance rule: every child names which epic
  criterion/criteria it is on the hook for).

**MECE checklist (inline -- the decomposition must pass all four):**
1. **No surface overlap** -- no two children declare the same write surface.
2. **Every criterion covered** -- each epic exit criterion is inherited by
   **>= 1** child (a criterion no child owns is an unplanned gap).
3. **No "etc." items** -- every child is concrete; "...and other cleanup" means
   it is not yet MECE.
4. **Non-blocking siblings flagged parallelizable** -- children with disjoint
   surfaces and no ordering edge are noted as concurrently executable.

## Step 5 -- Approval gate, THEN write the plan + file the beads

**Present** the epic brief (the Why), the exit rubric, and the proposed bead tree
to the maintainer. **Stop here for approval** -- this is the one planning gate.

**Only after the maintainer approves:**
1. Write `docs/sprint_<N>_<slug>_plan.md` capturing the Why, the rubric table,
   the bead tree (with each child's surfaces + inherited criterion), and an
   explicit "out of scope" list. Add its row to the "Active sprint plans" line in
   [`docs/INDEX.md`](../../../docs/INDEX.md).
2. File the beads with **pull/push-bracketed `bd create`** -- `bd_safe.py` has no
   `create` subcommand, so bracket the raw `bd create` yourself:
   `bd dolt pull && bd create ... && bd dolt push`. Set each child's
   `--metadata '{"surfaces":[...]}'` and write its `## Exit criteria` into the
   body at creation time (the creation-time norm -- see
   [`workflow.md`](../../../docs/doctrine/workflow.md#bead-creation-requirements)).
   Wire the parent-child deps with `bd_safe.py dep-add --epic/--child`.
3. **Set the epic's `plan:` metadata pointer** to the plan file just written
   (`bd update <epic-id> --set-metadata plan=docs/sprint_<N>_<slug>_plan.md`,
   plus `--set-metadata sprint=<N>`). This is the machine-readable bead->plan link
   that **plan-traceability** rests on -- every action a child takes must be
   derivable from this plan or it escalates (see
   [`planning.md`](../../../docs/doctrine/planning.md#plan-traceability)). An epic
   with no `plan:` pointer is an incomplete filing.

Filing without an approved rubric, or before the gate, defeats the purpose --
the rubric is the contract every child executes against.

## What this skill never does

- **Never executes a bead** -- it only scopes, plans, and files. Execution is
  each child's `/next-bead` -> build -> `/closeout` cycle.
- **Never files beads before maintainer approval** of the rubric + tree.
- **Never greps** -- search is delegated to Explore/Haiku in Step 2.
