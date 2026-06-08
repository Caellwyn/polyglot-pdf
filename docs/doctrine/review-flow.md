# Review-flow doctrine: parallel Codex + fresh-eyes, looped to clean

*Last updated: 2026-06-07. See [the hrn.9 journal entry](../journal/entries/) for the Copilot->Codex cutover details.*

How every change gets reviewed before merge. This is the procedure the
`/closeout` skill automates; it is the result of several iterations and the
rationale for each choice is preserved below so it is not re-litigated.

## The flow

```
clean tree
  -> judge review-worthiness              [orchestrator: does this diff warrant Codex?]
  -> open a NORMAL (non-draft) PR         [if review-worthy: `@codex review` line in the PR BODY; Codex auto-reviews on open]
  -> spawn fresh-eyes reviewer            [ALWAYS; runs in PARALLEL with Codex's auto-review]
  -> fix the COMBINED round-1 findings    [one batch -> one re-review]
  -> push, then COMMENT `@codex review`     [round 2+ needs an explicit comment]
  -> loop: watch Codex -> fix -> push -> re-comment   [until Codex reports CLEAN]
  -> close bead + ping the maintainer to merge
```

The maintainer's only gate is the **final manual merge**. Everything up to the
ping is autonomous. A review-skipped PR (docs/beads/journal-only) runs fresh-eyes
only and has no Codex loop.

## Why each choice

- **The reviewer is OpenAI Codex; it AUTO-REVIEWS on PR open (bd hrn.8/hrn.9).**
  The prepaid GitHub Copilot credits were exhausted, so the repo cut over to
  OpenAI Codex (`chatgpt-codex-connector[bot]`). Codex reviews a PR automatically
  when it opens, so ROUND 1 needs no explicit trigger -- we just put an `@codex
  review` line in the PR BODY as a belt-and-suspenders nudge. ROUND 2+ re-reviews
  (after a fix-push) DO need an explicit `@codex review` issue comment, posted as
  the gh-authenticated user. Never use the GitHub reviewer API
  (`requested_reviewers`) -- that fires Copilot, which is retired here. The
  round-1 watch floor is the PR-open time (the auto-review lands after it); each
  re-review's floor is its trigger comment's `created_at`.
- **The trigger string is EXACTLY `@codex review`.** A different phrasing such as
  `@codex please commit ...` would invoke Codex's commit path (it can push to the
  PR), not a review -- see the "If you are reviewing a PR" section of `AGENTS.md`,
  which is the file Codex actually reads for its review etiquette (approve via a
  👍 reaction; always post a summary comment).
- **Codex's CLEAN signal is a 👍 (`+1`) reaction** on its summary comment (the
  canonical, language-independent approval), with "Didn't find any major issues"
  text or an exact `LGTM` as fallbacks. The watcher
  (`scripts/pr_review_watcher.py --reviewer codex`, now the default) classifies
  all three; an inline finding always outranks a 👍, so a thumbs-up can't mask a
  real ask.
- **Review-worthiness gate.** The orchestrator decides per-PR whether the diff can
  contain a runtime/logic regression. Docs-only / `.beads`-only / journal-only /
  trivial PRs get NO trigger and skip the watch loop entirely -- reviewing them
  spends review effort on content that can't regress. Source PRs (`backend/`,
  `frontend/src/`, scripts, runtime config) get the trigger. When genuinely
  ambiguous, trigger the review -- a wasted review is cheaper than a shipped bug,
  but the gate is not an excuse to dodge review of real code.
- **Parallel round 1 (for review-worthy PRs).** Codex auto-reviews the moment the
  PR opens; fresh-eyes (a Sonnet subagent reading the REAL diff) runs at the same
  time. Total round-1 wait is max(codex, fresh-eyes), not the sum. They catch different bug classes -- Codex is good at local
  correctness, fresh-eyes at "what did the author's own priorities blind them to."
  Fresh-eyes runs even when Codex is skipped.
- **Combine both reviewers' fixes into ONE push.** Fixing fresh-eyes and Codex
  findings separately would mean two Codex re-review rounds of overlapping content.
  Batch them so one re-trigger covers all of it.
- **NO draft PRs.** A draft adds a pointless state flip. The "cannot merge" safety
  a draft provides is already guaranteed by allow_auto_merge=false (see
  promotion-tiers.md), which makes the manual merge the only gate regardless of
  draft state. Always open normal.
- **Loop Codex until CLEAN.** A fix-push does NOT re-trigger Codex -- you MUST post
  a fresh `@codex review` comment (capturing its `created_at` as the next round's
  `--since` floor) to request each re-review. Fresh-eyes is one pass (round 1
  only); only Codex loops.
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
