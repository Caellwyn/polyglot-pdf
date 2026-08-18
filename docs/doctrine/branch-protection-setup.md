# Branch-protection setup: the GitHub rulesets

*Last updated: 2026-08-18 (bd polyglot-pdf-wx7j: the two review-flow mentions
described the outer review as unconditionally Opus-5; reworded to name the
three-way fork -- Opus for a source diff, Haiku docs-reviewer for docs-only,
none for trivial.)*

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
[review-flow](review-flow.md): loop the one outer adversarial pass to clean —
Opus for a source diff, Haiku for docs-only, none for a trivial diff — then
apply the auto-merge-vs-ping rule — a routine low-risk PR cleared by the Opus
pass specifically with green checks is merged autonomously via `gh pr merge`,
while a consequence-bearing PR (or one only Haiku-cleared) is pinged to the
maintainer, whose merge it remains; see CLAUDE.md "Auto-merge vs. maintainer
merge", bd polyglot-pdf-16pj). The CI status checks are the only mechanical
merge blocker. This matches [review-flow.md](review-flow.md).

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

## External review agents (RETIRED 2026-07-08)

There is **no external model reviewer** anymore. The repo previously used GitHub
Copilot, then OpenAI Codex, as an automated PR reviewer; both are retired (the
maintainer's Codex subscription ended 2026-07-08). Review is now entirely
Claude-based -- a fresh-eyes inner loop plus one outer adversarial pass (Opus
for a source diff, Haiku for docs-only, none for trivial), run as
orchestrator-driven subagents (see
[`review-flow.md`](review-flow.md)) -- so no bot reads `.github/copilot-instructions.md`
or the "If you are reviewing a PR" section of [`AGENTS.md`](../../AGENTS.md); those
files are kept only as inert history. There is nothing to configure at the
branch-protection layer for review: the ruleset never gated on a bot, and the CI
status checks remain the only mechanical merge blocker.
