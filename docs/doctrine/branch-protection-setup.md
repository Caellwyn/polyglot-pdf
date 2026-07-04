# Branch-protection setup: the GitHub rulesets

*Last updated: 2026-07-02 (bd polyglot-pdf-g0mm: the three CI test jobs are now REQUIRED status checks on `dev` PRs; documented that "Defend Production" is currently INERT -- quote-mangled patterns, zero effective rules on `main`, fix owned by bd polyglot-pdf-pidj -- and that the repo default branch is `dev`). Prior 2026-05-29; see [the journal entry](../journal/entries/2026-05-29-bd-xmf-github-branch-protection-rulesets.md) for the original setup.*

How `main` and `dev` are protected on `Caellwyn/polyglot-pdf`. This is the
GitHub side of the [promotion-tiers](promotion-tiers.md) flow. Ported from
`YourTurn-Group/yourturn-group` (its "Defend Production" + "To Dev" rulesets).

Protection is via **repository rulesets**, not classic branch protection.

## The two rulesets

The repo's **default branch is `dev`** (the working integration branch); `main`
is the promotion target with no active prod behind it.

### "Defend Production" (id 17055207) — currently INERT, protects nothing

Its include patterns all carry literal quote characters
(`refs/heads/"main"`, `refs/heads/"Prod"`, ...), which match no real ref:
`gh api repos/Caellwyn/polyglot-pdf/rules/branches/main` returns `[]` — `main`
has ZERO effective rules today (deletable, force-pushable, no PR required).
Its intended rules (deletion, non_fast_forward, `required_deployments` →
`staging`, pull_request) do not apply. **The fix is a maintainer decision**
(fixing the patterns would also ACTIVATE the staging-deploy gate, blocking the
dev→main promotion) — owned by bd `polyglot-pdf-pidj`.

### "Defend Dev" (id 17131149) — the effective ruleset on `dev`

Matches `dev` via its `~DEFAULT_BRANCH` entry (its literal `refs/heads/"dev"`
entries are the same quote-mangled junk as above and match nothing).
Effective rules, verified via `gh api repos/.../rules/branches/dev`:

| Rule | Effect |
|------|--------|
| `deletion` | `dev` cannot be deleted |
| `non_fast_forward` | no force-push to `dev` |
| `pull_request` | merging to `dev` requires a PR. `required_approving_review_count: 0`, `dismiss_stale_reviews_on_push: false`, `required_review_thread_resolution: false`, all merge methods allowed |
| `required_status_checks` | a PR into `dev` can only merge when the CI checks **`backend pytest`**, **`frontend vitest`**, and **`schema-editor vitest`** pass (bd polyglot-pdf-g0mm; non-strict — the branch need not be up to date with `dev`) |

Human approval is **not** required (count 0), and there is no ruleset-level
review gate — the review gate is procedural (the
[review-flow](review-flow.md): loop Codex to clean, then the maintainer drives
the merge). The CI status checks are the only mechanical merge blocker. This matches [review-flow.md](review-flow.md).

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

`.github/copilot-instructions.md` (Copilot) and the "If you are reviewing a PR"
section of [`AGENTS.md`](../../AGENTS.md) (Codex) govern the automated reviewers --
each bot reads only its own file. Key contract: **always post a top-level summary
comment on every round** (it's the author's polling-agent signal — a silent finish
hangs the agent), assign findings-bearing `dev` PRs to `@caellwynai-josh`, and
never commit directly (comment-only). The copilot instructions were tightened on
the zero-findings/LGTM case because Copilot had been finishing silently when work
was satisfactory. (Codex's review rules were consolidated into AGENTS.md and the
never-read `.github/codex-instructions.md` removed -- Codex discovers AGENTS.md,
not that file.)
