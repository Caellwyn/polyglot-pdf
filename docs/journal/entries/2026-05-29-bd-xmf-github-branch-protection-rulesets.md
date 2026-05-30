---
date: 2026-05-29
bead: polyglot-pdf-xmf
title: "Rename default branch to main, add dev, port yourturn-group rulesets + review-agent instructions"
tags: [conventions, review]
---

## Trigger

`bd polyglot-pdf-xmf`. The repo's default branch was the legacy
`shared-audio-stream` — a leftover reference the owner was tired of — and GitHub
had **no branch protection at all** (empty rulesets, no PR gate). The owner
wants a `dev`/`main` setup with PRs into `dev` only, matching the protection on
`YourTurn-Group/yourturn-group`, plus that repo's Copilot/Codex review-agent
instructions (with the Copilot LGTM-signal wording tightened, since Copilot had
been finishing silently when work was satisfactory).

## What shipped

**Branch restructure (remote):**
- Pushed the 5 local-only commits (prior closeouts done under the old
  local-merge protocol) to `origin/shared-audio-stream` so remote = local first.
- Renamed `shared-audio-stream` → `main` via
  `POST .../branches/shared-audio-stream/rename` (preserves history + open-PR
  redirects). Set `main` as default.
- Created `dev` off `main`.
- Created the `staging` deployment environment (empty — the prod ruleset depends
  on it).

**Rulesets (ported from yourturn-group, matched exactly):**

`Defend Production` → `~DEFAULT_BRANCH` (main):
```json
{
  "name": "Defend Production", "target": "branch", "enforcement": "active",
  "conditions": { "ref_name": { "exclude": [], "include": ["~DEFAULT_BRANCH"] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "required_deployments",
      "parameters": { "required_deployment_environments": ["staging"] } }
  ],
  "bypass_actors": []
}
```

`To Dev` → `refs/heads/dev`:
```json
{
  "name": "To Dev", "target": "branch", "enforcement": "active",
  "conditions": { "ref_name": { "exclude": [], "include": ["refs/heads/dev"] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request", "parameters": {
        "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": true,
        "required_reviewers": [], "require_code_owner_review": false,
        "require_last_push_approval": false, "required_review_thread_resolution": false,
        "allowed_merge_methods": ["merge", "squash", "rebase"] } },
    { "type": "copilot_code_review",
      "parameters": { "review_on_push": true, "review_draft_pull_requests": true } }
  ],
  "bypass_actors": []
}
```

**Review-agent instructions:** added `.github/copilot-instructions.md` and
`.github/codex-instructions.md`. Codex's is a near-verbatim port (review-only,
never-commit, assign-on-findings). Copilot's was **tightened on the
zero-findings case** — the change the owner asked for: made the top-level
LGTM-signal comment emphatically mandatory on *every* round including when the
code is perfect, with an explicit "satisfactory is not a reason to stay silent"
framing and a canonical first-line phrase (`LGTM` / `No further suggestions` /
`Approved`) for the author's polling agent to grep.

**Docs:** created `docs/doctrine/branch-protection-setup.md` (was referenced by
promotion-tiers.md but missing); updated `planning_documents/PROJECT_CONTEXT.md`
and `TECHNICAL_GUIDE.md` off `shared-audio-stream`. Left `archived/` copies as
historical snapshots.

Nothing deferred.

## Lessons

- **Going-forward workflow change:** the repo moves from local-merge-to-default
  to **real PRs into `dev`**. The closeout skill's `origin/dev` assumptions now
  hold. The stale "merged to main locally, not pushed" guidance lives in the
  **bd-prime hook output** (the SESSION CLOSE PROTOCOL block), not in any
  tracked repo file — CLAUDE.md itself already describes the correct
  feature → dev → main flow. Updating the hook text is a beads/hook-config task,
  filed separately (it can't be fixed from the repo tree).
- The `required_deployments` rule on `main` is a **hard merge block** until a
  deploy to `staging` actually succeeds. Intentional (owner is wiring deploys),
  but worth knowing before anyone tries to promote `dev → main`.
- The `branches/{b}/rename` API + a follow-up `PATCH default_branch` is the
  clean way to move a default branch; `gh repo view` caches the old default, so
  verify against `gh api repos/{r} --jq .default_branch`, not the CLI view.

## Doc freshness

`check_doc_freshness.py` tracks only `docs/components/` + `docs/standards/`
(empty starter skeleton) — nothing flagged. The docs I touched
(`docs/doctrine/*`, `planning_documents/*`) are outside its globs; updated by
hand. CLAUDE.md's local-merge note is stale but lives in tier-1 — left for a
focused follow-up rather than bundled here.

## Files touched

- `.github/copilot-instructions.md` — new; tightened LGTM-signal review rules.
- `.github/codex-instructions.md` — new; review-only / never-commit rules.
- `docs/doctrine/branch-protection-setup.md` — new; documents the two rulesets + recreate commands.
- `docs/journal/entries/2026-05-29-bd-xmf-github-branch-protection-rulesets.md` — this entry.
- `planning_documents/PROJECT_CONTEXT.md` — branches section → main/dev.
- `planning_documents/TECHNICAL_GUIDE.md` — noted shared-audio-stream → main rename.
