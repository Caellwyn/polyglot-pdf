---
date: 2026-06-01
bead: polyglot-pdf-x8o
title: "copilot_watch: classify issue-comment rounds by inline findings, not change-ask prose (kill false-COMMENTS)"
tags: [review, conventions]
---

## Trigger

The maintainer, mid-closeout on PR #48, hit the false-COMMENTS babysitting again
and asked "how do I prevent this from happening again?" On PR #48 round 2, Copilot
posted a no-findings acknowledgment and `copilot_watch` classified it COMMENTS — a
false positive (zero new inline findings that round).

**The root cause, pinned during review** (initial theory was wrong): Copilot's
re-review issue comment opens by **echoing the trigger as a blockquote** —
`> @copilot please review` — and the quoted **"please"** tripped
`_has_change_ask`. It was never Copilot's own prose asking for a change; it was our
own trigger, quoted back. (The initial fix — gating the change-ask fallback on
inline-comment history — was a wrong turn that fresh-eyes correctly flagged as a
false-CLEAN regression; see What shipped.)

## What shipped

Two changes to `_classify_issue_comment_round`:

1. **Quote-stripping (the actual fix).** New `_strip_quotes()` removes `>`-prefixed
   blockquote lines before any prose analysis (change-ask *and* approval), so the
   echoed `> @copilot please review` trigger can't masquerade as Copilot asking for
   a change. This is what fixes the PR #48 case at its root.
2. **Inline-findings-first ordering.** A NEW actionable inline finding this round is
   the primary COMMENTS trigger (checked before the prose heuristics), since a real
   "please change X" from Copilot is an inline comment on the diff regardless of the
   summary wording. Final order: ERROR → new inline finding → exact-LGTM/approval →
   change-ask prose (quote-stripped, **ungated**) → else CLEAN.

**The review caught a wrong turn.** My first attempt gated the change-ask fallback
on `_has_any_copilot_inline` (only let prose decide if Copilot had never left an
inline comment). Fresh-eyes (PR #49) flagged this as a **false-CLEAN**: a genuine
round-2 prose ask ("please also fix the off-by-one") on a PR with prior-round
inline comments would be suppressed → read CLEAN. Correct, and dangerous. Removed
the gate entirely — once quote-stripping fixes the real cause, the change-ask path
can stay ungated (safe default: a real prose ask is always COMMENTS). This also
moots Copilot's separate note about the gate's redundant API call.

Verified both directions on PR #48's **real** round-2 body: the quoted-trigger
acknowledgment → change-ask false after stripping → **CLEAN**; a genuine
quote-prefixed prose ask → change-ask true → **COMMENTS**. Tests: the quoted-
trigger regression, `_strip_quotes` unit cases, inline-beats-prose, the
false-CLEAN guard (genuine prose ask + stale inline → COMMENTS), and the
prose-only-ask fallback. Full `tests/test_copilot_watch.py`: 75 passing.

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

- `scripts/copilot_watch.py` — new `_strip_quotes()` (drop echoed-trigger
  blockquotes before prose analysis); inline-findings-first, ungated change-ask
  `_classify_issue_comment_round`
- `tests/test_copilot_watch.py` — tests for the quoted-trigger regression,
  `_strip_quotes`, inline-beats-prose, the false-CLEAN guard, prose-only fallback
- `docs/journal/entries/2026-06-01-bd-x8o-copilot-watch-classify-issue-comment-rounds-by.md` — this entry
