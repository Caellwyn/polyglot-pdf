---
date: 2026-06-12
bead: polyglot-pdf-yic2
title: "pr_review_watcher: quota-notice from Codex now classifies as ERROR, not CLEAN"
tags: [bugfix, harness, scripts]
---

## Trigger

Observed on PR #163 (2026-06-11): Codex replied "You have reached your Codex
usage limits for code reviews" -- a quota/usage-limit notice, not a review.
The classifier's no-inline-findings approval fallback treated it as a clean
approval (RESULT: CLEAN, exit 0). The --close-on-clean gate would have
auto-closed the bead on a quota error. Caught manually.

## Root cause

`_classify_issue_comment_round` and `_classify_reviewed` both guarded on
`body.startswith(profile.error_body_prefix)` ("Codex encountered an error").
The quota notice starts with "You have reached..." -- a different phrase -- so
the prefix check missed it and the body fell through to the step-6 approval
fallback (no new inline finding -> treating as approval).

## What shipped

Added `ReviewerProfile.error_body_substrings` -- a tuple of case-insensitive
substrings checked ANYWHERE in the body, before the approval fallback. Added
`_is_error_body()` helper combining the existing prefix check with the new
substring check. Both classification callsites now call `_is_error_body`.

CODEX_PROFILE gets two quota phrases (observed on PR #163):
- "reached your codex usage limits"
- "usage dashboard"

Six new tests cover: quota notice via issue comment, quota notice via formal
review, `_is_error_body` prefix match, substring match, case-insensitivity,
and clean comments correctly not matching.

## Stale-doc triage

`docs/components/beads-remote-bootstrap.md` and `docs/components/pdf-filling.md`
flagged STALE by doc-freshness (filesystem timestamps). Neither file was touched
in this commit (only `scripts/pr_review_watcher.py` and
`tests/test_pr_review_watcher.py` changed). The timestamps reflect other
in-flight worktree activity and are false positives for this PR. No doc update
needed.

## Pre-existing test failure noted

`test_close_on_clean_does_not_fire_on_non_clean_state[MERGED]` fails at
baseline (introduced by bd polyglot-pdf-rlpq, PR #173): that bead updated
`main()` to fire --close-on-clean on MERGED but didn't update the test.
Filed a bead to fix it; out of scope for yic2.
