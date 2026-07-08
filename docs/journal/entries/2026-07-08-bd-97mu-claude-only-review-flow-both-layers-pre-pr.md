---
date: 2026-07-08
bead: polyglot-pdf-97mu
title: "chore(process): Claude-only review flow, both layers pre-PR (retire external reviewer)"
tags: [review, doctrine, harness]
---

## Trigger

Maintainer directive (2026-07-08): "My codex subscription has ended. Please
update guidance to use only Claude-based reviewers now. That's a sonnet/haiku
inner loop, and then an opus outer loop. We currently do not have any external
model reviewers." A follow-up clarified the ordering is a real flow change, not
just a relabel: the inner loop cycles to NO-GAPS, THEN the outer loop cycles to
clean, and BOTH happen BEFORE the PR opens and the bead closes -- so the
automated scripts had to change too.

## What shipped

The review flow is now entirely Claude-based, and both review layers run PRE-PR
on the local branch:

  - inner: a Sonnet/Haiku fresh-eyes assess loop, looped to `NO-GAPS`
    (unchanged; it was already pre-PR);
  - outer: an Opus-4.8 review (two independent clearing passes on the identical
    local diff, `origin/dev...HEAD`), moved from POST-PR to PRE-PR.

Only after both loops clear does one `closeout_finish.py` run open the PR AND
close the bead(s), and closeout then auto-merges or pings. There is no external
reviewer, no post-PR review step, and no bot watcher.

**Scripts (the real change this round).** Because both reviews now clear before
`closeout_finish.py` runs, the script got SIMPLER:

  - dropped the `--review-worthy` / `--skip-review` gate entirely;
  - deleted `request_review()`, the `CODEX_REVIEW_TRIGGER` constant, and the
    `WATCH_CMD` / `TS` outputs (no bot to trigger or watch);
  - a normal run now opens the PR AND closes the bead(s) in one run
    (`main()` forces `--close-beads` on; `steps()` unconditionally appends the
    close). The old two-call `--close-only` watcher pattern is retired to a
    standalone recovery tool. `RESULT` sentinel collapsed from
    `OPENED-REVIEW`/`OPENED-NOREVIEW`/`CLOSED-ONLY` to `OPENED-CLOSED` (+ the
    recovery `CLOSED-ONLY`). Verified end-to-end via `--dry-run`.

**Tests.** `test_closeout_finish.py` and `test_closeout_skill.py` had several
tests pinning the retired gate/watcher/`@codex` behavior; rewrote them to the new
open-and-close-together, Claude-only, pre-PR contract, and added regression
guards that the retired symbols (`CODEX_REVIEW_TRIGGER`, `request_review`, the
gate flags, live `@codex`/`pr_review_watcher` in the SKILL) are gone. The skill
test `test_outer_review_loops_until_clean` caught a genuine leftover -- a live
`pr_review_watcher.py` example in the SKILL's `$WT`-vs-`$R` explanation -- which I
then removed.

**Docs reordered to pre-PR** (the first-pass edits in the prior session had the
outer review post-PR; this pass moved it): the closeout SKILL was restructured to
Step 5.5 (inner) -> Step 5.6 (outer Opus, pre-PR, on the local diff) -> Step 6
(open PR + close bead(s) + merge, one `closeout_finish.py` run) -> Step 7
(telemetry). Matching updates to `review-flow.md` (flow diagram + every
post-PR/pushed-diff reference), `CLAUDE.md` (scar tissue #2 + the Closeout
section), `prime-closeout-override.md`, the `fresh-eyes-reviewer` and
`closeout-runner` agent files, and `AGENTS.md` (the Codex reviewer-etiquette
section marked retired/inert). The deferred-nit bead convention was re-keyed off
the bead id instead of a PR number, since review now happens before any PR
exists.

Fresh-eyes / Opus outer review triage: recorded in this closeout's own run
(adopt/reject breakdown folded in at merge time). No out-of-scope beads filed.

Rubric scorecard (bead exit criteria):
  1. closeout_finish.py has no gate, opens PR + closes bead(s) in one run, no
     WATCH_CMD/@codex, --close-beads default-on, tests assert retired symbols
     gone -- PASS.
  2. SKILL / review-flow / CLAUDE.md / agents describe both layers pre-PR, PR
     opens only after both clear, no post-PR step, no external reviewer -- PASS.
  3. Full suite green -- PASS.

## Lessons

Reordering a review layer from post-PR to pre-PR has a non-obvious ripple: any
convention keyed on a PR number (here, the deferred-nit bead title
`... from PR #<n>`) breaks, because there is no PR at review time. When moving a
step earlier in a pipeline, grep for artifacts the step used to produce
downstream (PR number, pushed ref, watch floor) and re-anchor them.

## Doc freshness

`check_doc_freshness.py` flagged `docs/standards/testing.md` and
`docs/standards/validation-delegation.md` as STALE, but both track files this
branch did NOT touch (`frontend/package.json`, `live_ai_gemini.py`,
`config.py`) -- they were stale before this work. Left as-is per the Step 2 rule
(only bump docs whose tracked globs cover files this branch changed). All the
process docs this change DID touch (review-flow, CLAUDE.md, workflow, planning,
promotion-tiers, branch-protection, INDEX) were updated in-place with their
`*Last updated:*` stamps bumped to 2026-07-08.

## Files touched

- `scripts/closeout_finish.py` -- drop review gate + WATCH_CMD/@codex; open PR +
  close bead(s) in one run; RESULT `OPENED-CLOSED`; `--close-only` -> recovery
  tool.
- `tests/test_closeout_finish.py` -- rewrite gate/watcher tests to the unified
  open-and-close contract; retired-symbol regression guards.
- `tests/test_closeout_skill.py` -- assert the Claude-only pre-PR flow; guard
  against live `@codex`/`requested_reviewers`/`pr_review_watcher` re-appearing.
- `.claude/skills/closeout/SKILL.md` -- restructure to Steps 5.5 -> 5.6 -> 6 ->
  7; outer review pre-PR on the local diff; one-run open+close.
- `docs/doctrine/review-flow.md` -- flow diagram + prose to both-layers-pre-PR,
  Claude-only.
- `CLAUDE.md` -- scar tissue #2 + Closeout section to the new flow.
- `.claude/prime-closeout-override.md` -- both layers pre-PR.
- `.claude/agents/fresh-eyes-reviewer.md` -- outer-review caller reads the local
  diff, pre-PR.
- `.claude/agents/closeout-runner.md` -- brief drops the review-worthiness flag /
  two-call close; one-run open+close.
- `AGENTS.md`, `docs/INDEX.md`, `docs/doctrine/workflow.md`,
  `docs/doctrine/planning.md`, `docs/doctrine/promotion-tiers.md`,
  `docs/branch-protection-setup.md`, `docs/doctrine/branch-protection-setup.md`
  -- retire external-reviewer references.
