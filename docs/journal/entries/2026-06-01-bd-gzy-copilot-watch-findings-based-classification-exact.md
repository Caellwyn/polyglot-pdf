---
date: 2026-06-01
bead: polyglot-pdf-gzy
title: "copilot_watch: findings-based classification + exact-LGTM pin (end approval-phrase whack-a-mole)"
pr: "45"
tags: [review, conventions]
---

## Trigger

Bundled into the docs-audit PR #45 after the maintainer hit the recurring
"Copilot invented yet another approval phrasing" problem during that PR's review
loop. On PR #45 round 2, Copilot's no-findings re-review landed as the free-text
issue comment *"the two prior reviewer findings are already addressed in
bff9399"* — which matched none of `copilot_watch.py`'s `_APPROVAL_PATTERNS`, so the
watcher saw no recognizable verdict and exited **TIMEOUT**. This is the same
whack-a-mole that beads `fau`, `ztk`, and PRs #42/#43/#44 had each chased with one
more allowlist phrase.

## What shipped

First, a settings investigation (maintainer asked "can Copilot produce a real
approval state?"): **no.** The reviewer actor is `copilot-pull-request-reviewer[bot]`
and has emitted `COMMENTED` on every review across PRs #40–45 — never `APPROVED`.
GitHub's built-in Copilot reviewer is advisory-only (no repo/org toggle; the
`repos/.../copilot/settings` endpoint 404s), and a *bot* approval wouldn't satisfy
a ruleset's `required_approving_review_count` anyway. So a deterministic
text-based signal is the only viable path.

The fix has three layers:

1. **Findings-based classification** (the deterministic backstop).
   `_classify_issue_comment_round` no longer treats "Copilot said something
   unrecognized" as COMMENTS. Order of checks: ERROR body → exact-`LGTM`/known
   approval phrase → explicit change-ask prose → **new actionable inline finding
   this round** → else CLEAN. Approval is now the *absence* of an actionable
   finding, so novel approval wording can't cause a false COMMENTS/TIMEOUT. A new
   actionable finding = a Copilot inline comment on the current diff (non-null
   `position`) created at/after the round floor — a fact independent of summary
   prose. Also: the `COMMENTED` review's summary body (the always-present
   "## Pull request overview") and a neutral issue comment are no longer counted
   as findings — only a change-ask body is.

2. **Exact-LGTM pin** (the fast path). `.github/copilot-instructions.md` now
   instructs Copilot to reply with a body that is *exactly* `LGTM` (one word,
   alone) when it has no suggestions — collapsing the prior three-phrase menu
   (`LGTM`/`No further suggestions`/`Approved`) that gave it room to drift.
   `_is_exact_lgtm` matches that deterministically (tolerating `**LGTM**` /
   `> LGTM` wrappers), bypassing every heuristic.

3. **Resolves `polyglot-pdf-ztk`** (residual exception-clause / multi-paragraph
   false-CLEANs). Added an approval-*shape* guard (`_is_approval_shaped`: short,
   single-paragraph, no list/numbered items) so a body that merely *opens* with an
   approval phrase but appends a finding can't ride the allowlist, plus
   exception-connector change-ask signals (`beyond `, `other than`, `except `,
   `aside from`, `apart from`) for the single-sentence carve-out form
   ("no outstanding findings **beyond** the race condition in X").

Tests: 21 new cases (exact-LGTM matrix, the PR-#45 "already addressed" regression,
findings-based inversion, ztk's exception/multi-block exploits) + fixed a stale
`test_exit_code_map` that pre-dated this branch (it omitted the `MERGED` state).
Full `tests/test_copilot_watch.py` suite: **57 passing**; closeout tests
(`test_closeout_*`): 23 passing.

Residual risk (documented, accepted): a substantive finding delivered *only* as
summary prose with none of the change-ask signal words and no inline comment would
read CLEAN. In practice Copilot's actionable findings are inline, and the
independent fresh-eyes review + the human manual-merge gate are two further
backstops — a missed finding must evade all three.

## Lessons

When an external tool's free-text output is load-bearing, don't classify it by
matching its prose — classify it by a *structural fact it can't reword away*. Here
that fact is "did Copilot leave an inline comment on the current diff." The
phrase-allowlist was effectively an unbounded-NL denylist (ztk's point) that could
never be complete; inverting to default-clean-unless-a-finding-exists removed the
treadmill. Pin the cooperative fast-path (exact `LGTM`) on top for speed, but never
*depend* on the tool saying the right words.

## Doc freshness

No `docs/components` or `docs/standards` doc tracks `copilot_watch.py` /
`copilot-instructions.md` (these are closeout tooling, governed by
`.claude/skills/closeout/SKILL.md` + `docs/doctrine/review-flow.md`, which describe
the review *flow*, not the classifier internals — reviewed and left as-is, still
accurate). The freshness checker is unaffected.

## Files touched

- `scripts/copilot_watch.py` — findings-based `_classify_issue_comment_round`;
  `_is_exact_lgtm` / `_has_change_ask` / `_is_approval_shaped` helpers;
  exception-connector change-ask signals; summary-body no longer auto-counted
- `.github/copilot-instructions.md` — pin the no-findings reply to exactly `LGTM`
- `tests/test_copilot_watch.py` — 21 new tests; fixed stale `test_exit_code_map`
- `docs/journal/entries/2026-06-01-bd-gzy-copilot-watch-findings-based-classification-exact.md` — this entry
