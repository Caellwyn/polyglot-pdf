# Review-flow doctrine: parallel Copilot + fresh-eyes, looped to clean

*Last updated: 2026-06-01.*

How every change gets reviewed before merge. This is the procedure the
`/closeout` skill automates; it is the result of several iterations and the
rationale for each choice is preserved below so it is not re-litigated.

## The flow

```
clean tree
  -> judge review-worthiness              [orchestrator: does this diff warrant Copilot?]
  -> open a NORMAL (non-draft) PR         [if review-worthy: "@copilot please review" in BODY]
  -> spawn fresh-eyes reviewer            [ALWAYS; runs in PARALLEL with Copilot if requested]
  -> fix the COMBINED round-1 findings    [one batch -> one re-review]
  -> push, then post "@copilot please review"  [REQUESTS the re-review; auto-review is off]
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
  ONLY when the PR contains `@copilot please review`. Two consequences encoded
  below: we judge whether a PR is even worth a review, and we put the trigger in
  the PR BODY (not a comment) so requesting it costs zero extra Claude turns.
- **Review-worthiness gate.** The orchestrator decides per-PR whether the diff can
  contain a runtime/logic regression. Docs-only / `.beads`-only / journal-only /
  trivial PRs get NO trigger and skip the watch loop entirely -- reviewing them
  spends metered credits on content that can't regress. Source PRs (`backend/`,
  `frontend/src/`, scripts, runtime config) get the trigger. When genuinely
  ambiguous, request the review -- a wasted review is cheaper than a shipped bug,
  but the gate is not an excuse to dodge review of real code.
- **Parallel round 1 (for review-worthy PRs).** The body trigger requests Copilot
  on PR-open; fresh-eyes (a Sonnet subagent reading the REAL diff) runs at the
  same time. Total round-1 wait is max(copilot, fresh-eyes), not the sum. They
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
- **Loop Copilot until CLEAN.** With auto-review off, a fix-push does NOT
  re-trigger Copilot -- you MUST post "@copilot please review" to request each
  re-review (it is the trigger now, not a belt-and-suspenders backstop). Fresh-eyes
  is one pass (round 1 only); only Copilot loops.
- **Handle all four pr_review_watcher.py states.** CLEAN/COMMENTS (exit 0), ERROR
  (exit 1, surface to maintainer, no auto-retry -- a quota error will not clear
  for hours), TIMEOUT (exit 2, treat like ERROR -- NEVER interpret silence as
  CLEAN). An unhandled state must never fall through to "done."
- **Never run `gh pr merge`.** The merge is the maintainer's alone.

## Fresh-eyes specifics

The fresh-eyes reviewer is `.claude/agents/fresh-eyes-reviewer.md` (spawn by
type) or its prompt run as a one-off Sonnet subagent. It MUST read the real
`git diff origin/dev...HEAD`, never a summary -- bugs hide in the detail a
summary elides. It returns up to 8 findings with confidence + how-to-verify, and
ends with a STATUS line. Triage: high-confidence -> fix inline; the rest -> file
a bead; rejected -> record the reason in the PR body. The PR body's "Fresh-eyes
review" section is the audit log of adopt/reject/defer.
