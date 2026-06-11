# Planning doctrine: SPEAR, exit rubrics, and model tiering

*Last updated: 2026-06-11.*

How a feature gets scoped, planned, executed, assessed, and resolved here. This
doc is the conceptual home; three skills are its mechanical encodings --
[`/plan-epic`](../../.claude/skills/plan-epic/SKILL.md) (Scope + Plan),
[`/next-bead`](../../.claude/skills/next-bead/SKILL.md) (the claim-time
exit-criteria backstop), and [`/closeout`](../../.claude/skills/closeout/SKILL.md)
(the pre-PR Assess + Resolve). Read this for the *why*; read the skills for the
*steps*.

We adopt **SPEAR** (Scope, Plan, Execute, Assess, Resolve) **per-feature (epic),
not per-bead.** A whole feature is scoped and planned once, up front, with an
exit rubric; the beads underneath inherit that rubric and execute against it. The
research record is the [SPEAR gap analysis](../journal/entries/2026-06-10-bd-1crj-spear-workflow-proposal.md)
(bd `polyglot-pdf-1crj`); the first epic planned under it is bd `polyglot-pdf-7dkb`.

## L1 / L2 / L3 ownership (Why / How / What)

Every unit of work separates three levels, and they have different owners. This
is the same split as the escalation doctrine in
[`CLAUDE.md`](../../CLAUDE.md) -- planning just names it explicitly.

| Level | Question | Owner | Notes |
|-------|----------|-------|-------|
| **L1 -- Why** | What outcome, and why does it matter? | **Maintainer** (product owner) | Time-invariant. The orchestrator probes until it is crisp but never invents it. |
| **L2 -- How** | What approach / architecture? | **Collaborative** | The maintainer brings an initial How; **orchestrator pushback is expected and welcomed** -- name blind spots and better paths at planning time, not mid-execution. A cross-cutting commitment beyond the bead still escalates (CLAUDE.md step 2). |
| **L3 -- What** | What implementation? | **Orchestrator**, maintainer approves the plan | Module/function decomposition, naming, helper reuse -- yours to decide (CLAUDE.md step 3). The *plan* (bead tree + rubric) gets one approval gate; the implementation within it does not. |

The single most load-bearing rule: **the orchestrator must challenge the How at
planning time.** A blind spot named before execution costs one sentence; named
after costs a re-do. Silent agreement with a flawed approach is the failure mode
planning exists to prevent.

## The exit rubric

Every epic (and every standalone ticket) carries an **exit rubric**: a small set
of criteria that define "done" *before* work starts, so no agent has to infer
what success means.

**Format:**
- **2-5 criteria** for an epic; **1-3** for a standalone ticket.
- Each criterion is **binary** (PASS/FAIL, no "mostly"), **measurable**
  (a named file to read, a script to run, a behavior to observe), and
  **outcome-based** (what the user/maintainer can verify), **SMART-style**
  (specific, measurable, achievable, relevant, with a clear verify step).
- Pair each criterion with its **verify** step -- the exact read/run/observe
  that settles PASS vs FAIL.

**Rules:**
- **Outcomes, not proxies.** "The mic streams seamlessly across a breakpoint
  crossing" -- not "the reconnect handler was refactored." A proxy can pass while
  the outcome fails.
- **Never softened because it is hard.** If a criterion is the right bar, it
  stays even when it is inconvenient to meet. Lowering the bar to pass is
  self-defeating.
- **Changes are logged on the epic bead.** A rubric may legitimately change as
  understanding improves -- but the change is recorded (what changed, why) on the
  bead, never silently.
- **Translate to tests where feasible.** A criterion that can be a test should
  be (test-first encouraged); the test then *is* the verify step.

## Bead taxonomy

Two kinds of beads carry exit criteria:

- **Epic child** -- a bead under an epic. It is **MECE** with its siblings
  (mutually exclusive surfaces, collectively exhaustive of the epic's criteria)
  and **inherits >= 1 epic criterion**, named in its own `## Exit criteria`
  section. The child's job is to satisfy the criteria it inherits.
- **Standalone ticket** -- a bead with no epic. It carries its **own 1-3 exit
  criteria** written at creation time. **If a ticket's work clusters into more
  than ~3 distinct criteria, that is a signal to split it into multiple beads**
  (or promote it to an epic) -- one bead should not sprawl across many unrelated
  outcomes.

Exit criteria are written at **creation time** -- the creator has the
observational context to state what "done" looks like; a `/next-bead`
**claim-time gate** is the backstop that lazily retrofits the legacy backlog.
The convention and the gate live in
[`workflow.md`](workflow.md#bead-creation-requirements).

## MECE decomposition

When `/plan-epic` decomposes an epic into children, the bead tree must pass an
explicit checklist:

- **No surface overlap** -- two children never declare the same
  `metadata.surfaces` write target (the change-surface collision guard in
  [`workflow.md`](workflow.md) enforces disjointness at claim time; the plan
  makes it true by construction).
- **Every criterion covered** -- each epic exit criterion is inherited by
  **>= 1** child. A criterion no child owns is an unplanned gap.
- **No "etc." items** -- every child is concrete; a decomposition that needs
  "...and other cleanup" is not yet MECE.
- **Non-blocking siblings flagged parallelizable** -- children with disjoint
  surfaces and no ordering dependency can run concurrently.

## Model tiering

The expensive models run at **decision gates only**; cheaper models do the
volume work. Expensive models **never bug-hunt or grep.**

| Tier | Models | Where |
|------|--------|-------|
| **Decision gates** | Fable / Opus | **Plan** (scope, rubric, MECE decomposition, the How-pushback), **Assess** (the orchestrator's pre-PR rubric scorecard + gap/nit triage), **escalation + Resolve judgment** (the orchestrator's judgment calls and the merge-ping handoff). |
| **Execution** | Sonnet | Building a bead's changes; the fresh-eyes assessor pass. |
| **Search + mechanical** | Haiku / Explore | Codebase ground-truth fan-out, file location, mechanical glue (the `closeout-runner` tail). |

The orchestrator **never greps** -- it delegates search to Explore/Haiku and
keeps the conclusion, not the file dumps. Spending Opus tokens on a `grep` is the
exact waste the tiering exists to prevent.

## Parallel execution

Non-blocking sibling beads (disjoint surfaces, no ordering edge) can be executed
concurrently:

- Spawn the builders with `run_in_background` and collect their results as they
  finish.
- Concurrency is **bounded by the orchestrator session's lifetime** -- a
  backgrounded agent does not outlive the session that launched it, so plan the
  fan-out to complete within one working session.
- The **change-surface collision guard already enforces surface disjointness**
  (see [`workflow.md`](workflow.md)) -- so two concurrent builders that would
  write the same file are refused at claim time, not discovered at merge. Plan
  the MECE split so this never fires in the first place.

## Assess + Resolve

Assess is a **recursive adversarial fresh-eyes loop run BEFORE the PR opens**
(not after), scoring the produced changes against the rubric. The assessor's
mandate is gap-exhaustion -- "find every place the changes do NOT meet the
criteria" -- never approval-seeking. The full procedure (the closeout Step 5.5
scorecard, the inner fresh-eyes loop, the Codex outer review and its no-credits
fallback) lives in [`review-flow.md`](review-flow.md). Resolve is the maintainer's
merge, unchanged.
