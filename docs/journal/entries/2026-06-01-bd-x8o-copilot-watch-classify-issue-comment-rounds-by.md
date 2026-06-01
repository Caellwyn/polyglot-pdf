---
date: 2026-06-01
bead: polyglot-pdf-x8o
title: "copilot_watch: classify issue-comment rounds by inline findings, not change-ask prose (kill false-COMMENTS)"
tags: [review, conventions]
---

## Trigger

The maintainer, mid-closeout on PR #48, hit the false-COMMENTS babysitting again
and asked "how do I prevent this from happening again?" On PR #48 round 2, Copilot
posted a no-findings **acknowledgment** — *"the two issues the reviewer **raised**
were already addressed in c0e8b86… all tests pass"* — and `copilot_watch`
classified it COMMENTS. The verdict was a false positive: zero new inline findings
existed that round; the watcher only tripped because the acknowledgment prose
contained a `_CHANGE_ASK_SIGNALS` word (`raised`). This is the same unbounded-NL
whack-a-mole the earlier `gzy`/`ztk` work moved off the approval *allowlist* — it
had just relocated to the change-ask *denylist*.

## What shipped

Re-ordered `_classify_issue_comment_round` to be **inline-findings-first**: the
verdict now rests on the structural fact Copilot can't reword away — *did it leave
a new actionable inline comment on the current diff this round?* — instead of
matching prose. New order:

1. ERROR body → ERROR.
2. **a NEW actionable inline finding this round → COMMENTS** (the only primary
   COMMENTS trigger).
3. exact `LGTM` / known approval phrase → CLEAN (fast path).
4. **fallback, only when Copilot left NO inline comments at all on the PR**:
   change-ask prose → COMMENTS (a genuine prose-only "please fix X" with no
   anchor is still caught).
5. else → CLEAN (approval by absence of any actionable finding).

The key change vs the prior version: the change-ask-prose check used to run
*before* the inline check and short-circuited to COMMENTS, so an acknowledgment
with a stray change-ask word never reached the inline check. Now inline findings
lead, and prose only decides in the narrow case where Copilot reviews entirely via
prose (no inline comments anywhere) — gated by a new `_has_any_copilot_inline`
helper so a *stale prior-round* inline comment doesn't let this round's prose
re-open a clean round.

Verified end-to-end by replaying PR #48's **real** round-2 acknowledgment (with the
real round-1 inline finding floored out by `--since`): old logic → COMMENTS, new
logic → **CLEAN**. 4 new tests (the acknowledgment regression, inline-beats-prose,
stale-inline-doesn't-reopen, and the legitimate prose-only-ask fallback). Full
`tests/test_copilot_watch.py`: 74 passing.

No findings deferred.

## Lessons

This is the third time the lesson has bitten: **when an external tool's free-text
output gates an automated loop, classify on a structural fact, not on its prose.**
The approval allowlist (`gzy`), then its mirror the change-ask denylist (this
bead) — both were endless. The durable design makes the inline-comment stream the
verdict and treats *all* prose as advisory. Captured as a standing preference in
agent memory (`copilot-watch-classify-by-inline-findings`); the
`docs/doctrine/review-flow.md` already describes the loop at the right altitude, so
no doctrine edit was needed.

## Doc freshness

No tier-1/tier-2 doc tracks `copilot_watch.py` (closeout tooling, governed by
`.claude/skills/closeout/SKILL.md` + `docs/doctrine/review-flow.md` at the flow
level, not the classifier internals — reviewed, still accurate). Freshness checker
unaffected.

## Files touched

- `scripts/copilot_watch.py` — inline-findings-first `_classify_issue_comment_round`;
  new `_has_any_copilot_inline` helper gating the prose fallback
- `tests/test_copilot_watch.py` — 4 new tests for the acknowledgment regression +
  fallback gating
- `docs/journal/entries/2026-06-01-bd-x8o-copilot-watch-classify-issue-comment-rounds-by.md` — this entry
