---
date: 2026-06-08
bead: polyglot-pdf-9us
title: "Cap Codex review loop at 2 rounds (MAX_REVIEW_ROUNDS 3->2) to cut credit burn"
tags: [review, harness, doctrine]
---

## Trigger

The Copilot->Codex migration (PR #118, bd hrn.9 + nvd) shipped an aggressive
Codex review (broad P0/P1 redefinition). On its first real use it was clearly
valuable -- zero true nits across 11 findings, including two genuine bugs -- but
the maintainer burned a full week of Codex review credits in a single day. A
round-by-round value analysis of PR #118 showed the cost was the iteration count,
not the per-review depth.

## What shipped

Lowered the closeout review-loop ceiling **`MAX_REVIEW_ROUNDS` from 3 to 2** in
the closeout SKILL (it is a prose constant -- there is no code constant to change).
The doctrine is now: round 1 (Codex's auto-review on open) + ONE re-review after
fixes; if still not CLEAN, escalate to the maintainer instead of looping a third
time.

The change keeps Codex's aggressive per-review DEPTH (bd nvd) untouched -- the
lever pulled is purely the number of fix-and-recheck iterations. Rationale,
recorded inline in the SKILL's "Hard loop ceiling" section so it isn't
re-litigated: on PR #118, round 1 carried most of the critical value (both real
bugs), round 2 caught siblings of round-1 findings, and round 3+ was largely
re-litigation of earlier rounds' concerns -- spending credits for little marginal
gain. The PR that prompted this was itself a pathological case (it modified the
review tooling, so every fix created fresh review surface), but the front-loaded
value pattern is general.

Three edits in `.claude/skills/closeout/SKILL.md`: the ceiling definition
(`= 3` -> `= 2`, plus the "why 2 not 3" rationale and "rounds 2 and 3" ->
"round 2"), the arm-C control note ("ceiling 3" -> "ceiling 2"), and the loop
instruction ("hit `MAX_REVIEW_ROUNDS` (3)" -> "(2)").

Maintainer-approved the cap value (2) and the keep-depth/cut-iterations framing
on 2026-06-08. No fresh-eyes/Codex review on this PR -- it is a docs-only doctrine
change (review-skipped per the Step 6 gate), which also conveniently spends no
Codex credit, fitting the change's own spirit.

The maintainer's two other credit-saving ideas -- tightening which PRs warrant a
Codex review, and making fresh-eyes the primary reviewer with Codex as a backstop
-- were deliberately left as separate future levers, not folded in, so each can be
evaluated on its own.

## Lessons

- **Aggressive review depth and review COST are separable levers.** When an
  automated reviewer is finding real bugs but costing too much, cap the loop
  ITERATIONS before reaching for reduced depth -- the marginal value of late
  rounds drops off faster than the cost does. Recorded in the SKILL ceiling
  section.
- A PR that edits the review tooling itself is a worst-case for review loops:
  each fix creates new review surface, so the loop can spiral. Worth keeping in
  mind when self-modifying the closeout/review scripts.

## Doc freshness

- **Changed:** `.claude/skills/closeout/SKILL.md` (the ceiling doctrine). No
  tier-1/tier-2 `docs/` file references the ceiling NUMBER (verified by grep), so
  nothing else needed a bump. `docs/doctrine/review-flow.md` describes the loop
  qualitatively without pinning the count, so it stays accurate.
- No stale docs were introduced; the PR touches only the SKILL.

## Files touched

- `.claude/skills/closeout/SKILL.md` -- `MAX_REVIEW_ROUNDS` 3 -> 2 across the
  three references (ceiling definition + rationale, arm-C control note, loop
  instruction).
