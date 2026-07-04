---
date: 2026-07-02
bead: polyglot-pdf-g0mm
title: "CI test jobs are now required status checks on dev PRs; Defend Production found inert"
tags: [conventions, security]
---

## Trigger

Follow-up from the o0pc cleanup assessment: CI was informational -- a red run
did not block a merge to dev. Bead polyglot-pdf-g0mm: make the test jobs
required checks. Bundled bead polyglot-pdf-6oh0 (default branch) closed
already-done: the default branch was ALREADY dev when checked, so only the
stale scar memory needed updating.

## What shipped

**The ruleset change (GitHub-side, no code):** added a
`required_status_checks` rule to the "Defend Dev" ruleset (id 17131149) with
the three CI job names verified from a live run (PR #292): `backend pytest`,
`frontend vitest`, `schema-editor vitest`. Non-strict (a branch need not be
up to date with dev to merge). Verified effective via
`gh api repos/.../rules/branches/dev` -> the rule appears in dev's effective
rule set, and PR #292's merge box lists the three checks as required.

**Verification substitution (defended):** the bead's criterion asked for a
live failing-PR-blocked demonstration. Substituted the effective-rules API
check + a live green PR's merge requirements instead of opening a throwaway
red-test PR -- which would have burned a Codex auto-review and a CI cycle to
demonstrate GitHub's own documented enforcement semantics. If the maintainer
wants the full rehearsal it is one scratch PR away.

**Finding (filed, not fixed): "Defend Production" protects NOTHING.** All its
include patterns carry literal quote characters (`refs/heads/"main"` etc.)
that match no real ref; `main` has zero effective rules -- deletable,
force-pushable, no PR required. Not fixed here because correcting the
patterns would ACTIVATE the required_deployments->staging gate, which blocks
the dev->main promotion (bd m85) -- a maintainer decision. Filed as
bd polyglot-pdf-pidj with the options laid out. ("Defend Dev" had the same
junk patterns but works via its `~DEFAULT_BRANCH` entry.)

**Doc:** docs/doctrine/branch-protection-setup.md rewritten to actual
effective state -- it still described a "To Dev" ruleset with a
`copilot_code_review` rule (retired) and claimed the default branch was main.

## Lessons

- Ruleset ref patterns with quote characters silently match nothing; GitHub
  accepts them without warning. Verify protection with the EFFECTIVE-rules
  API (`/rules/branches/<branch>`), never by reading the ruleset definition.

## Doc freshness

- Bumped + edited: docs/doctrine/branch-protection-setup.md (see above).

Also folded in: docs/standards/testing.md's contract-dir row still called
test_websocket_protocol.py an "empty stub" -- stale since PR #291 filled it
with 79 tests; updated to current state (stamp not re-bumped: it already
reads 2026-07-02, and PR #292 edits the same stamp line -- avoiding a
same-line merge conflict).

## Files touched

- docs/doctrine/branch-protection-setup.md -- rewritten to effective state
  (fresh-eyes round-1 catch: the rewritten table had carried over
  `dismiss_stale_reviews_on_push: true` unverified; the API says false --
  fixed).
- docs/standards/testing.md -- contract-dir row updated (empty-stub claim
  stale since PR #291).
- docs/journal/telemetry/2026-07-03T00-44-26Z-0f62cf8a.json -- this PR's
  telemetry row (g0mm + 6oh0). A stray row for PR #292's bead 63zi that
  briefly rode this branch was removed by fresh-eyes round 1 and moved to
  its own PR's branch.
- GitHub ruleset "Defend Dev" -- required_status_checks rule added (not a
  repo file).
- bd memory worktree-branch-off-dev-not-default -- updated (default IS dev).
