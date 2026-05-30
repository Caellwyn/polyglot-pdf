# Branch-protection setup: the GitHub rulesets

*Last updated: 2026-05-29. See [the journal entry](../journal/entries/2026-05-29-bd-xmf-github-branch-protection-rulesets.md) for the setup.*

How `main` and `dev` are protected on `Caellwyn/polyglot-pdf`. This is the
GitHub side of the [promotion-tiers](promotion-tiers.md) flow. Ported from
`YourTurn-Group/yourturn-group` (its "Defend Production" + "To Dev" rulesets).

Protection is via **repository rulesets**, not classic branch protection.

## The two rulesets

### "Defend Production" — targets the default branch (`main`)

| Rule | Effect |
|------|--------|
| `deletion` | `main` cannot be deleted |
| `non_fast_forward` | no force-push to `main` |
| `required_deployments` → `staging` | a PR into `main` can only merge after a successful deploy to the **`staging`** environment |

`bypass_actors: []` — nobody bypasses. `~DEFAULT_BRANCH` targeting means it
follows the default branch automatically.

> **The `staging` gate blocks all merges to `main` until a deploy pipeline runs
> and a deployment to the `staging` environment succeeds.** The `staging`
> environment exists (empty); wiring the actual deploy is the maintainer's
> infra task. Until then, `dev` is the working integration branch and nothing
> lands on `main`.

### "To Dev" — targets `refs/heads/dev`

| Rule | Effect |
|------|--------|
| `deletion` | `dev` cannot be deleted |
| `non_fast_forward` | no force-push to `dev` |
| `pull_request` | merging to `dev` requires a PR. `required_approving_review_count: 0`, `dismiss_stale_reviews_on_push: true`, all merge methods allowed |
| `copilot_code_review` | Copilot reviews automatically — `review_on_push: true`, `review_draft_pull_requests: true` |

Human approval is **not** required (count 0); Copilot's review is the automated
gate, and the maintainer drives the merge. This matches
[review-flow.md](review-flow.md).

## Recreate / inspect

```bash
# list
gh api repos/Caellwyn/polyglot-pdf/rulesets --jq '.[] | .name + " (" + .enforcement + ")"'

# inspect one (replace ID)
gh api repos/Caellwyn/polyglot-pdf/rulesets/<id>

# the staging environment the prod ruleset depends on
gh api repos/Caellwyn/polyglot-pdf/environments --jq '.environments[].name'
```

To recreate from scratch, POST the JSON in the journal entry to
`repos/Caellwyn/polyglot-pdf/rulesets` (strip read-only fields: `id`,
`node_id`, `_links`, `created_at`, `updated_at`).

## Copilot / Codex review agents

`.github/copilot-instructions.md` and `.github/codex-instructions.md` govern the
automated reviewers. Key contract: **always post a top-level summary comment on
every round** (it's the author's polling-agent signal — a silent finish hangs
the agent), assign findings-bearing `dev` PRs to `@caellwynai-josh`, and never
commit directly (comment-only). The copilot instructions were tightened on the
zero-findings/LGTM case because Copilot had been finishing silently when work
was satisfactory.
