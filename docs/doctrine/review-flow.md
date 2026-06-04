# Review-flow doctrine: parallel Copilot + fresh-eyes, looped to clean

*Last updated: 2026-06-04.*

How every change gets reviewed before merge. This is the procedure the
`/closeout` skill automates; it is the result of several iterations and the
rationale for each choice is preserved below so it is not re-litigated.

## The flow

```
clean tree
  -> judge review-worthiness              [orchestrator: does this diff warrant Copilot?]
  -> open a NORMAL (non-draft) PR         [if review-worthy: chain a REVIEWER REQUEST (requested_reviewers) into the create call]
  -> spawn fresh-eyes reviewer            [ALWAYS; runs in PARALLEL with Copilot if requested]
  -> fix the COMBINED round-1 findings    [one batch -> one re-review]
  -> push, then RE-REQUEST the reviewer   [re-POST requested_reviewers; re-fires a fresh formal review]
  -> loop: watch Copilot -> fix -> push -> re-request   [until Copilot has NO comments]
  -> close bead + ping the maintainer to merge
```

The maintainer's only gate is the **final manual merge**. Everything up to the
ping is autonomous. A review-skipped PR (docs/beads/journal-only) runs fresh-eyes
only and has no Copilot loop.

## Why each choice

- **Copilot review is OPT-IN (since 2026-06-01).** GitHub changed Copilot pricing
  to per-token metering against a finite monthly credit pool -- no more unlimited
  tier. We disabled automatic review-on-open in repo settings; a review now fires
  when we **request the review bot as a reviewer** (`POST .../pulls/$PR/requested_reviewers`
  with `reviewers[]=copilot-pull-request-reviewer[bot]`). Two consequences encoded
  below: we judge whether a PR is even worth a review, and we CHAIN the reviewer
  request into the same Bash call as `gh pr create` (capturing a UTC timestamp
  *before* it as the watch `--since` floor) so requesting it costs zero extra
  Claude turns.
- **Why a REVIEWER REQUEST, not an `@copilot please review` COMMENT (bd
  polyglot-pdf-1pr).** An `@copilot` comment invokes the Copilot **coding agent**
  -- the agentic worker that clones the repo, starts MCP servers, and **commits to
  the PR** (or declines with "per your rules") -- NOT Copilot code review. The two
  are different products. Confirmed on throwaway PR #74: requesting
  `copilot-pull-request-reviewer[bot]` as a reviewer fires a real code review that
  lands as a formal review (state COMMENTED/APPROVED/CHANGES_REQUESTED) with zero
  commits, and emits the `copilot_work_started`/`reviewed` timeline events the
  watcher already keys on. The slug is reviewer-agnostic config
  (`swarm_config.review_reviewer_slug()`), so the staged Codex switch (bd hrn.9) is
  a config change. (This corrects the earlier body-vs-comment framing from hrn.10,
  which was itself wrong: the comment was never code review at all.)
- **Review-worthiness gate.** The orchestrator decides per-PR whether the diff can
  contain a runtime/logic regression. Docs-only / `.beads`-only / journal-only /
  trivial PRs get NO trigger and skip the watch loop entirely -- reviewing them
  spends metered credits on content that can't regress. Source PRs (`backend/`,
  `frontend/src/`, scripts, runtime config) get the trigger. When genuinely
  ambiguous, request the review -- a wasted review is cheaper than a shipped bug,
  but the gate is not an excuse to dodge review of real code.
- **Parallel round 1 (for review-worthy PRs).** The chained trigger comment requests
  Copilot the moment the PR opens; fresh-eyes (a Sonnet subagent reading the REAL
  diff) runs at the same time. Total round-1 wait is max(copilot, fresh-eyes), not the sum. They
  catch different bug classes -- Copilot is good at local correctness, fresh-eyes
  at "what did the author's own priorities blind them to." Fresh-eyes runs even
  when Copilot is skipped (it costs no credit).
- **Combine both reviewers' fixes into ONE push.** Fixing fresh-eyes and Copilot
  findings separately would mean two Copilot re-review requests of overlapping
  content. Batch them so one re-request covers all of it.
- **NO draft PRs.** With auto-review off the draft->ready flip no longer triggers
  Copilot, but a draft still adds a pointless state flip and risks a future
  settings change re-arming flip-triggered reviews. The "cannot merge" safety a
  draft provides is already guaranteed by allow_auto_merge=false (see
  promotion-tiers.md), which makes the manual merge the only gate regardless of
  draft state. Always open normal.
- **Loop Copilot until CLEAN.** A fix-push does NOT re-trigger Copilot -- you MUST
  RE-REQUEST the review bot as a reviewer (re-POST `requested_reviewers`) to
  request each re-review. Re-requesting an already-completed reviewer re-fires a
  fresh formal review (verified on PR #74). Fresh-eyes is one pass (round 1 only);
  only Copilot loops.
- **Handle all four pr_review_watcher.py states.** CLEAN/COMMENTS (exit 0), ERROR
  (exit 1, surface to maintainer, no auto-retry -- a quota error will not clear
  for hours), TIMEOUT (exit 2, treat like ERROR -- NEVER interpret silence as
  CLEAN). An unhandled state must never fall through to "done."
- **Resolve mechanical merge conflicts inline; escalate only structural ones.**
  When the loop's rebase hits a conflict, the orchestrator decides it -- it is not
  an automatic escalation. **Mechanical / ordering** conflicts (append-only journal
  or ledger rows, changelog interleaving, independent additions to the same
  list/table) are resolved inline by **keeping both sides** in a sensible order,
  then re-reading the merged region to confirm both intents survived. **Escalate
  (STOP and ask) only on genuine structural incompatibility** -- the two sides
  change the same logic/contract incompatibly so keeping both is wrong and
  choosing is a design call; ambiguous counts as structural. On escalation, abort
  the rebase first so the branch is left clean. Full procedure + the inline-vs-
  escalate boundary: the closeout skill's Step-7 "Merge-conflict resolution in the
  loop" (bd polyglot-pdf-hrn.6).
- **Never run `gh pr merge`.** The merge is the maintainer's alone.

## Fresh-eyes specifics

The fresh-eyes reviewer is `.claude/agents/fresh-eyes-reviewer.md` (spawn by
type) or its prompt run as a one-off Sonnet subagent. It MUST read the real
`git diff origin/dev...HEAD`, never a summary -- bugs hide in the detail a
summary elides. It returns up to 8 findings with confidence + how-to-verify, and
ends with a STATUS line. Triage: high-confidence -> fix inline; the rest -> file
a bead; rejected -> record the reason in the PR body. The PR body's "Fresh-eyes
review" section is the audit log of adopt/reject/defer.
