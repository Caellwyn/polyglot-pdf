---
date: 2026-06-11
bead: polyglot-pdf-7dkb
sprint: 2
tags: [doctrine, harness, review]
---

## Trigger

Continue implementation of the sprint-2 SPEAR-adoption plan
([`docs/sprint_2_spear-adoption_plan.md`](../../sprint_2_spear-adoption_plan.md),
epic `polyglot-pdf-7dkb`) -- the first feature planned under the SPEAR (Scope,
Plan, Execute, Assess, Resolve) protocol it introduces. The plan was approved
2026-06-11; this PR builds all four MECE children in one session and bundles them
(plus the epic) into one PR, as the plan anticipated. No runtime code is touched.

## What shipped

The four children, each mapping to one epic exit criterion:

- **`polyglot-pdf-n79l` (criterion 4) -- planning doctrine.** New
  [`docs/doctrine/planning.md`](../../doctrine/planning.md): L1/L2/L3
  (Why/How/What) ownership table, exit-rubric format + rules (binary, outcome-
  based, SMART, never softened), bead taxonomy (epic-child inherits vs standalone
  1-3), model-tiering policy (Fable/Opus at decision gates only; never bug-hunt or
  grep), and the parallel-execution note. Tier-1 pointers added: a CLAUDE.md
  trigger-read row + a new "Planning + model tiering (SPEAR)" critical-rule block,
  and a `docs/INDEX.md` doctrine row.
- **`polyglot-pdf-60et` (criterion 1) -- `/plan-epic` skill.** New
  `.claude/skills/plan-epic/SKILL.md` encoding Scope+Plan: L1 intake + the
  *mandated* How-challenge step, research fan-out to cheap subagents (orchestrator
  never greps), exit-rubric draft, MECE decomposition, and the maintainer approval
  gate. The rubric format, MECE checklist, criteria-inheritance rule, and approval
  gate are all inlined so a dry read-through is self-contained.
- **`polyglot-pdf-dz5q` (criterion 2) -- exit-criteria convention + gate.**
  `workflow.md` gains a "Bead creation requirements" section (creation-time norm,
  claim-time backstop, mechanical validation deliberately deferred); `/next-bead`
  gains a Step 4 claim-time gate that reads the bead body and writes 1-3 criteria
  before any edit when they're missing.
- **`polyglot-pdf-lxs7` (criterion 3) -- adversarial assess loop.**
  `fresh-eyes-reviewer.md` gains the gap-exhaustion (not approval) mandate, a
  rubric scorecard + gap verdict on its STATUS line, and out-of-scope bead-filing.
  `/closeout` gains Step 5.5 (pre-PR rubric scorecard + recursive adversarial
  fresh-eyes loop, ceiling 3), and Steps 6/7 become the Codex *outer* review (the
  two layers are serial, not parallel). `review-flow.md` documents the two-layer
  flow and the no-Codex-credits fallback.

**Self-demonstrating closeout (the assess loop reviewing its own PR).** This PR
ran the new Step 5.5 on itself. Fresh-eyes (Sonnet, adversarial, rubric passed
in) found **6 gaps in round 1** -- all restructure-induced stale cross-references
(a dead "fresh-eyes-race" handoff path, a "Step 6.3" that no longer exists, a
pre-PR gap wrongly routed to the post-PR nit convention, a double-meaning
"Resolve" in planning.md, a review-flow triage that "filed" rubric gaps instead
of fixing them, and a Step-8 line implying the old parallel model). After fixing
all 6, **round 2** confirmed those held and caught **3 more** (CLAUDE.md's
always-loaded scar-tissue + Closeout sections still described the old parallel
fresh-eyes+Codex flow; a vestigial "deferred fresh-eyes finding" in the Step-7
nit rule; and this missing journal entry). After fixing those, **round 3 (the
ceiling round) returned `NO-GAPS`** against all four rubric criteria -- the loop
terminated cleanly. Round 3 additionally noted **2 pre-existing, out-of-scope
residuals** on `dev` (the `bd prime` override `.claude/prime-closeout-override.md`
and a "dual review loop" phrase in CLAUDE.md still naming the retired Copilot /
old parallel flow); the tracker being unavailable to file them, and the fix being
the same class as the in-scope CLAUDE.md edits, I folded both in so every
always-loaded surface now agrees with the new serial flow. Fresh-eyes triage:
**adopt 11, reject 0, defer 0**; out-of-scope beads filed: **none** (tracker
unavailable -- see Lessons). This is the loop working exactly as intended -- the
adversarial framing caught eleven real inconsistencies the author's own eyes
missed across three rounds, before the PR ever opened.

## Lessons

- **Restructuring a load-bearing skill leaves stale cross-references in tier-1,
  always-loaded docs.** Moving fresh-eyes from a post-PR parallel reviewer to a
  pre-PR inner loop required edits not just in `closeout/SKILL.md` but in
  CLAUDE.md's scar-tissue (#2) and Closeout sections and across `review-flow.md`
  and `planning.md`. The first two rounds of self-assessment existed precisely to
  flush these out -- a single-pass review would have shipped a tier-1 doc
  contradicting the skill it describes. Generalizes: when a flow changes, grep the
  always-loaded surface (CLAUDE.md) for the old flow's vocabulary
  ("parallel", "both reviewers", old step numbers) as part of the change.
- **Beads filed from a remote container before the dolt-push fix (PR #152) never
  reached `refs/dolt/data`.** The five SPEAR beads (`7dkb` + four children) were
  created in PR #151's session, which predated the `BEADS_GITHUB_TOKEN`
  direct-github dolt push -- so they live only in the committed
  `.beads/issues.jsonl` snapshot, not the live tracker. This container's hydrated
  dolt store is also incomplete (missing `wisps`/`local_metadata` tables despite
  reporting schema v49), so `bd import`/`migrate` of those five fails and they
  cannot be claimed or closed through `bd` here. The implementation is unaffected;
  only the tracker bookkeeping is blocked. **Action: the five beads remain open and
  must be closed from a session with a healthy store** (or by the maintainer). I
  did not push the broken local store over the shared remote.

## Doc freshness

- Bumped `*Last updated:*` to 2026-06-11 on `workflow.md` and `review-flow.md`
  (both edited this PR); `planning.md` is new (a pure-doctrine doc with no
  `**Tracks:**` line, so it is not freshness-scanned).
- `scripts/check_doc_freshness.py` exits 0. The STALE docs it lists
  (`standards/risk-rating.md`, `stateless-architecture.md`, `terminology.md`,
  `voice-and-vad.md`, `technical_guide.md`) track backend/frontend code this branch
  did NOT touch -- they were stale before this branch, from prior `dev` work, and
  are left as-is per the closeout doc-freshness rule.
- Sprint-archive protocol clean: `sprint_2_spear-adoption_plan.md` stays at root,
  listed in INDEX's active-plans row, to be archived at epic closeout.

## Files touched

- `docs/doctrine/planning.md` (new), `.claude/skills/plan-epic/SKILL.md` (new),
  `docs/journal/entries/2026-06-11-bd-7dkb-spear-adoption.md` (this entry, new)
- `docs/doctrine/workflow.md`, `docs/doctrine/review-flow.md`
- `.claude/skills/next-bead/SKILL.md`, `.claude/skills/closeout/SKILL.md`,
  `.claude/agents/fresh-eyes-reviewer.md`, `.claude/prime-closeout-override.md`
- `CLAUDE.md`, `docs/INDEX.md`
