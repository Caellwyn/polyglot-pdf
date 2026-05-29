# Branch-protection setup (one-time, agent-executable)

*Last updated: <DATE>.*

This configures the GitHub rulesets the swarm workflow depends on. Run it once
per repo. An agent can execute it via the `gh` CLI (shown) or the GitHub MCP if
present -- the settings are the same either way; the kit does NOT assume the MCP
is connected.

## What you are creating

Two branch rulesets:

1. **"To Dev"** -- targets `dev` (the integration branch). Enables Copilot code
   review and requires PRs. This is what makes Copilot review on PR-open and
   re-review on push.
2. **"Defend Production"** -- targets `main`. Blocks direct pushes / force-pushes
   / deletion so production only advances by fast-forward promotion from `dev`.

And one repo setting: **`allow_auto_merge=false`** -- the single human merge gate.

## Preflight

```
gh auth status                       # confirm you are authenticated
gh repo view <OWNER>/<REPO> --json nameWithOwner   # confirm the target repo
```

## 1. Disable auto-merge (the merge gate)

```
gh api -X PATCH repos/<OWNER>/<REPO> -F allow_auto_merge=false
```

This is load-bearing: it is what lets the review flow run autonomously up to the
ping while still requiring the maintainer to click merge. Verify:

```
gh api repos/<OWNER>/<REPO> --jq .allow_auto_merge    # expect: false
```

## 2. Create the "To Dev" ruleset (Copilot review + PR required)

The `copilot_code_review` rule has exactly two parameters -- `review_on_push`
and `review_draft_pull_requests`. There is NO parameter for the draft->ready
trigger (that is built into GitHub and not configurable), which is WHY the
review flow avoids draft PRs (see `doctrine/review-flow.md`).

Set `review_draft_pull_requests` to your preference:
- `false` (recommended, matches the no-draft flow) -- Copilot reviews on PR-open
  and on push; no draft reviews.
- `true` -- Copilot also reviews drafts (only useful if you deliberately use
  drafts, which the kit flow does not).

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
      } },
    { "type": "copilot_code_review",
      "parameters": { "review_on_push": true, "review_draft_pull_requests": false } }
  ]
}
```

Create it:

```
gh api -X POST repos/<OWNER>/<REPO>/rulesets --input to-dev-ruleset.json
```

## 3. Create the "Defend Production" ruleset

Save as `defend-prod-ruleset.json`:

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
gh api repos/<OWNER>/<REPO>/rulesets/<TO_DEV_ID> --jq '.rules[] | select(.type=="copilot_code_review")'
```

You should see both rulesets `active`, and the `copilot_code_review` rule with
your chosen parameters.

## Notes

- **Copilot code review must be enabled for the repo/org** (a GitHub Copilot
  Enterprise/Business feature) for the `copilot_code_review` rule to take effect.
  If `gh api` rejects the rule type, Copilot review is not available on the plan.
- **GitHub MCP path:** if a GitHub MCP server is connected, it can create these
  rulesets too -- pass the same JSON bodies. Do not assume the MCP exists; the
  `gh` CLI is the portable path.
- **`dev` and `main` must exist** before targeting them. Create `dev` off `main`
  first if needed: `git checkout -b dev main && git push -u origin dev`.
