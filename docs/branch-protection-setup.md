# Branch-protection setup (one-time, agent-executable)

*Last updated: 2026-07-08. External code review is retired -- review is now entirely Claude-based (no `copilot_code_review` rule, no Codex GitHub app); see [`doctrine/review-flow.md`](doctrine/review-flow.md).*

This configures the GitHub rulesets the swarm workflow depends on. Run it once
per repo. An agent can execute it via the `gh` CLI (shown) or the GitHub MCP if
present -- the settings are the same either way; the kit does NOT assume the MCP
is connected.

## What you are creating

One branch ruleset that is load-bearing today, plus one optional guard:

1. **"To Dev"** -- targets `dev` (the integration branch). Requires PRs into `dev`.
   (This ruleset historically also enabled *Copilot* code review; that rule is
   RETIRED. There is NO external model reviewer at all now -- Copilot, then Codex,
   both retired (the maintainer's Codex subscription ended 2026-07-08). Review is
   entirely Claude-based and procedural, not a ruleset rule. Do NOT add a
   `copilot_code_review` rule. See step 2 below and
   [`doctrine/review-flow.md`](doctrine/review-flow.md).)
2. **"Defend Production"** -- targets `main`. OPTIONAL for this project: there is
   **no active production `main`** (this repo is a demo built for future investor
   demonstration, not a production app), so protecting `main` is not load-bearing.
   Kept here only for reference / a future prod tier.

And one repo setting: **`allow_auto_merge=false`**. This only disables GitHub's
merge-on-green auto-merge *feature*; it is NOT "the human merge gate." The actual
merge policy is the **auto-merge-vs-ping rule** (CLAUDE.md "Auto-merge vs.
maintainer merge", bd `polyglot-pdf-16pj`): closeout **auto-merges a routine
low-risk PR** that an adversarial reviewer cleared CLEAN (via an explicit
`gh pr merge`, which `allow_auto_merge=false` does not block), and **pings the
maintainer** for a consequence-bearing PR.

## Preflight

```
gh auth status                       # confirm you are authenticated
gh repo view <OWNER>/<REPO> --json nameWithOwner   # confirm the target repo
```

## 1. Disable GitHub auto-merge-on-green

```
gh api -X PATCH repos/<OWNER>/<REPO> -F allow_auto_merge=false
```

This disables GitHub's built-in "auto-merge when checks pass" feature so a PR never
merges itself on green. It does **not** stop the orchestrator's explicit
`gh pr merge` -- that is governed by the auto-merge-vs-ping rule (a routine
low-risk PR that reviewed CLEAN is merged autonomously; a consequence-bearing PR
pings the maintainer). Verify:

```
gh api repos/<OWNER>/<REPO> --jq .allow_auto_merge    # expect: false
```

## 2. Create the "To Dev" ruleset (PR required)

This ruleset requires PRs into `dev` and blocks deletion / force-pushes.

**Code review is NOT configured here, and there is NO external reviewer.** Review
is entirely Claude-based -- a fresh-eyes inner loop plus an Opus-4.8 outer review,
run as orchestrator-driven subagents by the closeout skill, not any GitHub app or
ruleset rule. The former `copilot_code_review` ruleset rule (and its successor, the
OpenAI Codex GitHub app) are both retired (bd `polyglot-pdf-hrn.8`/`hrn.9` for the
Copilot->Codex cutover; the maintainer's Codex subscription then ended
2026-07-08). Do NOT add a `copilot_code_review` rule. How the review loop works
lives in [`doctrine/review-flow.md`](doctrine/review-flow.md) and the closeout
skill, not in GitHub ruleset config. (The no-draft-PR convention still holds --
open normal PRs.)

Save this as `to-dev-ruleset.json`:

```json
{
  "name": "To Dev",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["refs/heads/dev"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["merge", "squash", "rebase"]
      } }
  ]
}
```

Create it:

```
gh api -X POST repos/<OWNER>/<REPO>/rulesets --input to-dev-ruleset.json
```

## 3. Create the "Defend Production" ruleset (OPTIONAL -- no active prod here)

**Skip this for the demo repo.** There is no active production `main` to defend
(the project is a demo for future investor demonstration, not a production app), so
this ruleset is not load-bearing. It is retained only as a reference for a future
prod tier. If you do create it, save as `defend-prod-ruleset.json`:

```json
{
  "name": "Defend Production",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["refs/heads/main"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["merge", "squash", "rebase"]
      } }
  ]
}
```

```
gh api -X POST repos/<OWNER>/<REPO>/rulesets --input defend-prod-ruleset.json
```

## 4. Verify

```
gh api repos/<OWNER>/<REPO>/rulesets --jq '.[] | {id, name, enforcement}'
gh api repos/<OWNER>/<REPO>/rulesets/<TO_DEV_ID> --jq '.rules[] | .type'
```

You should see the "To Dev" ruleset `active` with `pull_request`, `deletion`, and
`non_fast_forward` rules (no `copilot_code_review` -- that rule is retired).

## Notes

- **Code review is Claude-based and procedural, not a ruleset.** The fresh-eyes +
  Opus-4.8 outer review runs in the closeout skill; there is nothing to configure
  in a branch ruleset for it, and no external reviewer (Copilot and Codex both
  retired -- bd `polyglot-pdf-hrn.8`/`hrn.9`; Codex ended 2026-07-08). Do not add a
  `copilot_code_review` rule.
- **GitHub MCP path:** if a GitHub MCP server is connected, it can create these
  rulesets too -- pass the same JSON bodies. Do not assume the MCP exists; the
  `gh` CLI is the portable path.
- **`dev` and `main` must exist** before targeting them. Create `dev` off `main`
  first if needed: `git checkout -b dev main && git push -u origin dev`.
