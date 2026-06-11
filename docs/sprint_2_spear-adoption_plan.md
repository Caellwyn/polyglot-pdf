# Sprint 2 plan -- SPEAR partial adoption (epic `polyglot-pdf-7dkb`)

*Status: approved 2026-06-11. Archive to `docs/archive/` at epic closeout.*

The first epic planned under the SPEAR protocol it introduces (the dry-run).
Research record: the SPEAR gap analysis
([journal entry](journal/entries/2026-06-10-bd-1crj-spear-workflow-proposal.md),
bd `polyglot-pdf-1crj`, PR #151) plus the maintainer's per-feature reframe in
the 2026-06-10/11 planning session.

## Why (L1 -- maintainer)

Move the software factory toward greater autonomy:

- **Tight scoping** to prevent scope drift.
- **Accountability to predetermined, measurable success criteria** -- every unit
  of work knows what "done" looks like before it starts.
- **Multi-agent cross-checking** -- no one agent determines all of plan,
  execution, and assessment; agents correct each other.
- **Token-efficient model tiering** -- the most capable models run at decision
  gates (plan, escalation, resolve) only; cheaper models do volume work.
  Expensive models never bug-hunt or grep.

## How (L2 -- collaborative, settled in the planning session)

SPEAR (Scope, Plan, Execute, Assess, Resolve) adopted **per-feature (epic), not
per-bead**:

- **Scope + Plan** happen at epic-planning time via a new `/plan-epic` skill,
  owned by the **orchestrator** (not a subagent -- subagents cannot converse
  with the maintainer, and the collaborative How, with a mandated
  orchestrator-pushback step, requires conversation access). Epic plans carry
  an **exit rubric**: 2-5 binary, SMART, outcome-based criteria.
- **Beads** become either MECE epic children (inheriting >= 1 parent criterion)
  or standalone tickets with 1-3 exit criteria. Criteria are written at
  **creation time** (the creator has the observational context); a
  **claim-time gate** is the backstop that lazily retrofits the legacy backlog.
- **Assess** becomes a recursive **adversarial fresh-eyes loop** run BEFORE the
  PR opens: the assessor's mandate is "find every place the changes do NOT meet
  the rubric criteria" (gap-exhaustion), never "check for approval". Loop until
  no gap is found (ceiling 3 rounds). Codex, when credits exist, stays as the
  outer post-PR review; while credits are exhausted (until ~2026-06-15) the
  fresh-eyes gap-free verdict is the review record. fresh-eyes also files
  out-of-scope bugs as new beads directly instead of escalating them.

## Exit rubric (epic `polyglot-pdf-7dkb`)

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | `/plan-epic` skill exists; a dry read-through yields the rubric format, MECE checklist, criteria-inheritance rule, and maintainer approval gate without referencing missing docs | Read `.claude/skills/plan-epic/SKILL.md` |
| 2 | `workflow.md` documents the exit-criteria convention (creation-time norm, claim-time backstop); `/next-bead` contains the claim-time gate | Read both files |
| 3 | `/closeout` contains the pre-PR Assess step (5.5) and the recursive adversarial fresh-eyes loop; the implementing PR's own body carries the criteria scorecard | Read the skill; check the PR body (self-demonstrating) |
| 4 | CLAUDE.md and `docs/INDEX.md` point at `docs/doctrine/planning.md`; `scripts/check_doc_freshness.py` passes | Run the script; check the links |

## Bead tree (MECE -- surfaces disjoint, every criterion covered)

```
polyglot-pdf-7dkb  EPIC: SPEAR partial adoption
|- polyglot-pdf-60et  /plan-epic skill                 -> criterion 1
|     surfaces: .claude/skills/plan-epic/
|- polyglot-pdf-n79l  planning doctrine + tier-1 ptrs  -> criterion 4
|     surfaces: docs/doctrine/planning.md, docs/INDEX.md, CLAUDE.md
|- polyglot-pdf-dz5q  exit-criteria convention + gate  -> criterion 2
|     surfaces: docs/doctrine/workflow.md, .claude/skills/next-bead/
`- polyglot-pdf-lxs7  adversarial assess loop          -> criterion 3
      surfaces: .claude/skills/closeout/, .claude/agents/fresh-eyes-reviewer.md,
                docs/doctrine/review-flow.md
```

All four children are **non-blocking siblings** (disjoint surfaces) and so
parallelizable in principle; in practice they will be executed in one session
and bundled into one PR (extending PR #151), which closes all four plus the
epic. No runtime code is touched.

## Out of scope (explicitly)

- Mechanical bead-body validation (`validate_bead_body.py`) -- convention
  first; file a bead if drift is observed.
- Separate service accounts per agent role -- not warranted at this project
  size; audit trail comes from branch/PR naming.
- A formal iteration cap parameter for builders -- the existing review-loop
  ceilings suffice.
- Retro-filling exit criteria across the ~250-bead backlog in bulk -- the
  claim-time gate retrofits lazily.
