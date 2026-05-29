# Review-flow doctrine: parallel Copilot + fresh-eyes, looped to clean

*Last updated: <DATE>.*

How every change gets reviewed before merge. This is the procedure the
`/closeout` skill automates; it is the result of several iterations and the
rationale for each choice is preserved below so it is not re-litigated.

## The flow

```
clean tree
  -> open a NORMAL (non-draft) PR        [Copilot round 1 fires on open]
  -> spawn fresh-eyes reviewer            [runs in PARALLEL with Copilot]
  -> fix the COMBINED round-1 findings    [one batch -> one re-review]
  -> push (+ "@copilot please review")    [re-triggers Copilot]
  -> loop: watch Copilot -> fix -> push   [until Copilot has NO comments]
  -> close bead + ping the maintainer to merge
```

The maintainer's only gate is the **final manual merge**. Everything up to the
ping is autonomous.

## Why each choice

- **Parallel round 1.** Copilot reviews on PR-open; fresh-eyes (a Sonnet
  subagent reading the REAL diff) runs at the same time. Total round-1 wait is
  max(copilot, fresh-eyes), not the sum. They catch different bug classes --
  Copilot is good at local correctness, fresh-eyes at "what did the author's own
  priorities blind them to."
- **Combine both reviewers' fixes into ONE push.** Fixing fresh-eyes and Copilot
  findings separately would trigger two Copilot re-reviews of overlapping
  content. Batch them so the next push gets one review.
- **NO draft PRs.** A draft seems safer ("cannot merge"), but the draft->ready
  flip is ITSELF a Copilot trigger with no ruleset off-switch -- so a draft costs
  a SECOND full Copilot review of already-approved content. Copilot review tokens
  are scarce. A normal PR has no flip event, so the redundant review is
  structurally impossible. The "cannot merge" safety a draft provides is already
  guaranteed by allow_auto_merge=false (see promotion-tiers.md), which makes the
  manual merge the only gate regardless of draft state.
- **Loop Copilot until CLEAN.** A fix-push auto-re-triggers Copilot
  (review_on_push, ~4 min); ALSO post "@copilot please review" as a
  belt-and-suspenders re-trigger (push-triggering is reliable but the mention
  guarantees it). Fresh-eyes is one pass (round 1 only); only Copilot loops.
- **Handle all four copilot_watch states.** CLEAN/COMMENTS (exit 0), ERROR
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
