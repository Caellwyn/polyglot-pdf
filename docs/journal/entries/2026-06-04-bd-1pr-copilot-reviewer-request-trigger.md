---
date: 2026-06-04
bead: polyglot-pdf-1pr
title: "Migrate Copilot review trigger from @copilot-please-review comment to reviewer-request API"
tags: [review, harness, doctrine, postmortem]
---

## Trigger

After PR #71 (the copilot-instructions rewrite) merged, the next code-review
request produced a frustrating replay: the bot "reviewed" by **committing to the
PR** (`1dd8b3f` on PR #73), then on later pings **declined** with *"Per your
rules, I should not reply to general comments."* The transcript showed it cloning
the repo and starting MCP servers (`runtime-tools`, `github-mcp-server`,
`playwright`).

## What shipped

**Root cause (confirmed by live probe on throwaway PR #74):** posting
`@copilot please review` as a PR **comment** invokes the Copilot **coding agent**
(the agentic worker that clones repos, runs MCP servers, and writes code) -- NOT
Copilot **code review**. They are two different products. The
`.github/copilot-instructions.md` "comment-only, never commit" rule governs code
review and never bound the coding agent, which is why the instructions rewrite
(PR #71) did nothing to stop the commits. The repo had been triggering the wrong
product all along; GitHub tightened the coding agent so the comment now mostly
misbehaves (commits or declines).

**The fix (verified on PR #74):** request the review bot as a **reviewer** via the
reviewer API instead of @-mentioning it:

```
gh api repos/{o}/{r}/pulls/{n}/requested_reviewers -X POST \
  -f 'reviewers[]=copilot-pull-request-reviewer[bot]'
```

Probe results (PR #74, now closed): the request lands a **formal review** on
`/pulls/{n}/reviews` (`state: COMMENTED`) within ~75s, makes **zero commits**, and
emits `review_requested` + `copilot_work_started` + `reviewed` timeline events --
which means the watcher's existing `COPILOT_PROFILE` (`uses_timeline=True`) path
**already works**, so no detection rework was needed (the riskiest part of the
original plan, eliminated by the probe). Re-POSTing `requested_reviewers` after a
push re-fired a **second** formal review (later `submitted_at`), so the
`MAX_COPILOT_ROUNDS` loop is preserved.

Changes (reviewer-agnostic so the staged Codex switch, bd hrn.9, is a config flip):
- `scripts/swarm_config.py`: new `review_reviewer_slug()` (env >
  `swarm.config.json` > fallback `copilot-pull-request-reviewer[bot]`).
- `scripts/closeout_finish.py`: `request_review()` POSTs `requested_reviewers`
  and captures a UTC `--since` floor (via `_utcnow()`) BEFORE the request -- there
  is no comment `created_at` anymore. Constant, dry-run plan, help text, and
  module docstring updated.
- `scripts/pr_review_watcher.py`: **docstring-only** (the timeline path already
  fires); the `_strip_quotes` machinery is kept as a legacy/Codex fallback.
- `.claude/skills/closeout/SKILL.md`, `CLAUDE.md`, `docs/doctrine/review-flow.md`,
  `.claude/agents/closeout-runner.md`: doc the reviewer-request trigger and the
  "why not a comment" root cause; this also fixed CLAUDE.md's pre-existing stale
  "put the trigger in the BODY" passage (a leftover wrong framing from hrn.10).
- `.github/copilot-instructions.md`: clean signal is now a formal **Approve**
  review (the watcher reads the approved state), with the exact `LGTM` body kept
  as a fallback. Still 3,613 chars (< 4000) and ASCII-clean.
- Tests: the skill's trigger assertion **inverted** -- it must NOT POST the
  `@copilot please review` comment and MUST re-request the reviewer; the
  `closeout_finish` review-worthy tests re-point to the reviewer-request call and
  pin a UTC floor.

**Fresh-eyes triage:** <!-- FRESH-EYES-PLACEHOLDER: filled at closeout -->

This PR is **review-worthy** (executable scripts + tests) and is the **first to
dogfood the new reviewer-request trigger** through closeout.

## Lessons

- **`@copilot please review` in a comment != Copilot code review.** It invokes the
  Copilot **coding agent** (clones the repo, runs MCP servers, commits). The
  canonical trigger for code review is requesting the bot as a **reviewer**
  (`POST .../pulls/{n}/requested_reviewers`, slug
  `copilot-pull-request-reviewer[bot]`). `gh pr edit --add-reviewer copilot`
  fails (`could not resolve user` -- Copilot is a Bot app, not a user login); use
  the REST `requested_reviewers` form. (Added to `docs/doctrine/review-flow.md` as
  durable doctrine; `bd remember` this too.)
- **The instructions file governs code review, not the coding agent.** Tightening
  `.github/copilot-instructions.md` cannot stop the coding agent from committing --
  only changing the *trigger* can.

## Doc freshness

- The freshness checker flagged several `docs/components/*` and `docs/standards/*`
  as STALE -- all track `backend/` files (live_ai_gemini.py, callback_handler.py)
  changed by OTHER work on 2026-06-03. **This PR touches no backend files** (only
  the review harness: scripts, skill, doctrine docs, tests), so per the closeout
  Step-2 rule they were stale before this branch and are left untouched.
- Bumped `docs/doctrine/review-flow.md` `*Last updated:*` to 2026-06-04 (it is the
  doc this change rewrites). CLAUDE.md scar #2 + the closeout section updated.

## Files touched

- `scripts/swarm_config.py` -- new `review_reviewer_slug()`.
- `scripts/closeout_finish.py` -- `request_review()` -> reviewer API + UTC floor.
- `scripts/pr_review_watcher.py` -- docstring updates only.
- `.claude/skills/closeout/SKILL.md` -- Steps 6/7 + hard rules retargeted.
- `.claude/agents/closeout-runner.md` -- drop the obsolete trigger caution.
- `CLAUDE.md` -- scar #2 + stale closeout passage rewritten.
- `docs/doctrine/review-flow.md` -- flow + rationale + date bump.
- `.github/copilot-instructions.md` -- Approve-when-clean signal.
- `tests/test_closeout_finish.py`, `tests/test_closeout_skill.py` -- updated/
  inverted assertions.
