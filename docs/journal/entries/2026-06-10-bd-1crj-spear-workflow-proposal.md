---
date: 2026-06-10
bead: polyglot-pdf-1crj
title: "SPEAR workflow model -- gap analysis and partial-adoption proposal"
tags: [harness, doctrine]
---

## Context

Ryan Waliany's Software Factory harness (softwarefactoryharness.md) introduces
the SPEAR loop: Scope -> Plan -> Execute -> Assess -> Resolve. This entry maps
it against the current beads-based workflow, identifies genuine gaps, and
proposes the minimum-overhead changes that would capture the most value.

Source document: uploaded 2026-06-10 by the maintainer (caellwyn@gmail.com).

---

## Phase-by-phase mapping

| SPEAR phase | Current equivalent | Fit |
|---|---|---|
| **Scope** -- Task Brief + rubric + Seven Circumstances, written by the human BEFORE work starts | Bead body (free-form description, no required structure) | WEAK -- no rubric, no scope gate |
| **Plan** -- Fable MECE-decomposes into parallel non-overlapping threads; writes sub-checklists with proof-of-work | /next-bead claim + implicit orchestrator reasoning | PARTIAL -- collision guard exists; no formal decomposition or proof requirements |
| **Execute** -- Builders run threads; escalate to Fable only | Main sprint execution (orchestrator + targeted subagents) | STRONG -- single-actor model differs from multi-Builder, but the role separation (orchestrator/subagent) and escalation doctrine are direct analogs |
| **Assess** -- Separate Assessor scores each thread against rubric independently; Builder never self-assesses | fresh-eyes (post-PR, round 1) + Codex loop | PARTIAL -- fresh-eyes IS the Assessor; it runs after the PR opens, not before; and with no rubric to score against, it scores style/correctness, not outcome-fitness |
| **Resolve** -- Human reviews Fable's all-clear + rubric evidence, merges | /closeout + maintainer merge | STRONG -- the human gate (manual merge, per-deploy permission) is the same philosophy |

### Role mapping

| Software Factory role | Current analog | Notes |
|---|---|---|
| Human | Maintainer | Direct -- maintains scope/rubric, merges PRs |
| Fable (Orchestrator) | Claude orchestrator (this session) | Direct -- never writes code, holds plan, handles escalations |
| Builder | Targeted subagents (Explore, Plan, general-purpose, fresh-eyes) | Direct -- one MECE thread each |
| Assessor | fresh-eyes subagent | Direct -- independent, read-only, scores the diff |
| Recipe | Skills (/next-bead, /closeout, /run-local, /voice-harness) | Direct -- durable SOPs for a class of work, already in use |
| Flywheel | CLAUDE.md scar-tissue + journal | Direct -- every defect becomes a lesson; less formalized than the SPEAR flywheel |

The L1/L2/L3 taxonomy (Why/How/What) also maps directly onto the escalation
doctrine in CLAUDE.md:

| Level | SPEAR | CLAUDE.md equivalent |
|---|---|---|
| L1 -- Why | Human writes, time-invariant | Step-2 escalation domain: product/direction calls |
| L2 -- How | Human writes approach; orchestrator escalates if it's a cross-cutting commitment | Step-2 for architecture beyond the bead; step-3 for internal structure |
| L3 -- What | Agent writes (implementation) | Step-3: yours to decide |

---

## Genuine gaps (in priority order)

### Gap 1: No rubric at Scope time (highest value)

The core SPEAR insight is: "write the rubric before the agent starts." A rubric
is 2-5 binary, outcome-based, machine-verifiable criteria. Without one, the agent
must infer what "done" means, which causes:

- Silent scope drift (doing more or less than intended)
- Avoidable Codex loops (the reviewer can't know the intended behavior either)
- Over-escalation ("is this what you wanted?")

Currently, bead bodies are free-form. A P1/P2 bead with code changes can be
claimed with a one-sentence description and nothing about what passes.

### Gap 2: Assess step runs after the PR, not before

fresh-eyes runs when the PR opens. That is too late to catch a gap the agent
introduced during Execute -- by then the branch is committed, the PR is open,
and fixing it means another push + another Codex round.

An explicit Assess step before /closeout -- a brief self-score against the rubric
-- catches "I didn't address criterion 3 at all" before review starts.

### Gap 3: No structured Seven Circumstances gate on bead creation

The full 7-gate (What/Who/Where/When/Why/How/How much) is heavyweight for a
small bead, but the subset {What, Why, Where, How much (scope limits)} would
catch ambiguous beads at creation time rather than mid-sprint.

### Gap 4: No MECE decomposition checklist for multi-surface beads (lower priority)

The change-surface collision guard enforces non-overlap between CONCURRENT beads.
It does not enforce non-overlap WITHIN a single bead's plan. For large epics with
3+ surfaces, a Builder quietly touching an unplanned surface is the gap failure
mode. Currently this relies on the orchestrator's implicit discipline.

---

## What NOT to adopt

**Separate service accounts per role (bot-fable, bot-builder, bot-assessor).**
Valuable for multi-team concurrent execution; not warranted for a one-maintainer
project. Audit trail already comes from branch/PR naming + commit history.

**26-iteration cap as a formal parameter.** The Codex loop already terminates by
signal (CLEAN/COMMENTS/ERROR/TIMEOUT). An explicit cap adds overhead for a failure
mode that has not occurred here.

**The plan.md per-task file as a parallel artifact.** The bead IS the plan. A
separate plan.md would duplicate state and drift. The bead body + skills already
cover the checklist function.

**The full Task Brief template (all sections) on every bead.** Too heavyweight
for a "fix one-line typo" bead. Reserve structure for beads that warrant it.

---

## Proposal: partial adoption

Two changes capture ~80% of the SPEAR value with minimal overhead.

### Change A -- Rubric section in bead creation (Scope gate)

For any bead that involves code changes, the bead body SHOULD include a
`## Rubric` section before work is claimed:

```markdown
## Rubric
- [ ] [Binary pass/fail criterion -- user-facing outcome, not proxy]
- [ ] [Binary pass/fail criterion]
- [ ] [Scope limit -- what explicitly is NOT changing]
```

Rules (matching SPEAR's rubric rules):
- Criteria describe what the user or system experiences, not what the code does.
  "Auth endpoint returns 200" is a proxy. "User can log in with valid credentials"
  is an outcome.
- A criterion may be modified if the scope legitimately changes -- document it
  in the bead comments.
- A criterion is never softened just because it is hard to pass.

This is NOT a hard gate today (not every existing bead has one). File as a
"should" in the bead creation convention, enforced by the agent claiming it: if
a bead has no rubric, write one before touching any file (2-3 criteria, 5
minutes, makes the rest of the bead cheaper).

### Change B -- Pre-closeout Assess step

Before running /closeout, score the work against the bead's rubric:

1. Re-read the rubric from the bead body.
2. For each criterion: PASS or FAIL with one-line evidence.
3. If any criterion FAILS: fix it before opening the PR. This is the gap the
   Codex loop cannot catch -- reviewers don't know the intended behavior.
4. If rubric was missing at bead start: write a retrospective rubric from the
   bead description, score against it, note any gaps found.

This step takes < 5 minutes on a small bead and prevents a class of "fix-push
that closes a thing Codex flagged but the rubric would have caught earlier."

The /closeout skill does not currently have an explicit Assess step; it moves
directly from tests to PR. The pre-PR sequence would become:

```
clean tree -> closeout_prep.py -> [NEW] Assess (rubric self-score) -> journal -> PR
```

### Change C -- Lightweight scope prompt on new P1/P2 beads (deferrable)

When creating a bead for a P1/P2 code change, include a one-line answer to:
- Why: what breaks or is missing for the user?
- Where: which files/surfaces?
- How much: what is explicitly out of scope?

This is a softer version of the Seven Circumstances gate tuned to our bead size.
Lower priority than A and B; file a follow-on bead if the maintainer wants it.

---

## Verdict

**Adopt-partially.** The SPEAR model's role structure (Orchestrator/Builder/
Assessor) and its flywheel concept are already well-instantiated in this project.
The genuine gaps are scoped to two workflow additions:

- Change A (rubric at Scope time) -- recommend adopting now, as a convention.
- Change B (pre-closeout Assess step) -- recommend adopting now, as a /closeout
  skill addition.
- Change C (scope prompt on creation) -- defer; file a bead to wire it in when
  the convention has proven out.

To carry these out: file one bead for the /closeout skill edit (Change B), and
update the bead-creation convention in `docs/doctrine/workflow.md` (Change A).
The maintainer's call on whether to proceed.

Closes polyglot-pdf-1crj (research phase).
