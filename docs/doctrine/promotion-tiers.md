# Promotion-tiers doctrine: worktree -> local -> dev -> demo

*Last updated: 2026-07-04.*

How code promotes from a working branch to the running demo. **This project has
NO active production environment** -- the demo remote is the live, outward-facing
target. (An earlier version of this doc described a `dev -> staging -> main -> prod`
auto-deploy topology; that was carried over from a different project and never
applied here. Deploys here are LOCAL/MANUAL via shell scripts, not branch-triggered.)

## The tiers

```
worktree (feature branch)        one bead's work; where the agent commits
        |  PR (reviewed: Codex + fresh-eyes, looped to clean)
        v
dev                              integration branch + PR base; maintainer merges
        |  deploy-demo.sh (front + backend; gated -- see below)
        v
demo remote server               the live demo (polyglot-demo-aa709); NO prod beyond this
```

- **Feature branches** always branch off freshly-pulled `dev`. A bead never spans
  PRs (one bead = one branch = one PR); a PR may bundle several small whole beads
  and closes at least one. See [`workflow.md`](workflow.md#bead-lifecycle).
- **`dev`** is the integration branch and the PR base. A PR -> `dev` merge is the
  maintainer's `gh pr merge` (see "The merge gate"). The agent MAY autonomously
  **sync the local root checkout to `dev`** (pull / fast-forward to `origin/dev`)
  -- that is not a merge.
- **The demo remote** is the live target. Promotion to it is `deploy-demo.sh`,
  gated as below. There is no `main`/prod tier.

## The merge gate

The repo's GitHub ruleset sets **allow_auto_merge=false**, so a PR cannot merge
*itself* on green -- someone must run the merge. Who runs it depends on the
**auto-merge rule** (autonomy increase 2026-07-04; CLAUDE.md "Auto-merge vs.
maintainer merge"): a routine, low-risk PR that an **adversarial** reviewer cleared
CLEAN with green checks is **merged autonomously** (`gh pr merge`) at the end of the
review flow; a **consequence-bearing** PR (affects operational cost / user-facing
features / downstream disruption / substantial multi-surface rework / an approved
plan) is instead **pinged to the maintainer**, who clicks merge. The consequence
line is the same as the step-2 escalation line; when unsure, ping. Full flow:
[`review-flow.md`](review-flow.md).

## The demo-deploy gate (autonomy increase 2026-06-10)

`deploy-demo.sh` deploys BOTH the frontend (Firebase Hosting) and backend
(Cloud Run) to the demo project `polyglot-demo-aa709`. The agent is authorized to
RUN it -- it is no longer on the NEVER list -- but only with ALL THREE guardrails,
in order:

1. **Local test FIRST.** Run the local stack (`scripts/dev-local.ps1`, via the
   `/run-local` skill: backend uvicorn :8000 + frontend vite :5173) and actually
   EXERCISE the specific change working there. Behavioral verification, not just
   "the server starts." If the change isn't demonstrably working locally, it is
   not a deploy candidate.
2. **Explicit per-instance permission.** Ping the maintainer and get a "yes"
   BEFORE each `deploy-demo.sh` run. This is per-deploy, every time -- NOT a
   standing pre-authorization. The agent may run the deploy; running it without
   that specific yes is the violation.
3. **Post-deploy test-drive.** After the deploy completes, test-drive the LIVE
   demo to confirm the change actually works on the remote. The deploy is not
   "done" until the running demo is verified; a failed test-drive is surfaced to
   the maintainer immediately.

`deploy-production.sh` exists in the tree but has **no live prod target** for this
project; do not run it without explicit maintainer direction (it is not covered by
the demo-deploy authorization above).

## Environment detection

Use ONE canonical signal for "which environment am I in" (e.g. a single
`IS_STAGING` / `APP_ENV` variable read through one helper), not ad-hoc hostname
or env-string checks scattered across the code. If the topology grows, migrate
the one helper; call sites keep working.

## Demo specifics

- **Project:** `polyglot-demo-aa709` (GCP + Firebase, both under the one project).
- **Backend:** Cloud Run (`polyglot-backend`), co-located with Gemini. NEVER logs
  full PII bodies -- see [`../standards/hipaa-pii-policy.md`](../standards/hipaa-pii-policy.md).
- **Frontend:** Firebase Hosting (the Personal/Portfolio channel; `deploy-demo.sh`
  header calls it that).
- **Account:** `deploy-demo.sh` checks for the `caellwyn@gmail.com` gcloud account
  and re-auths if needed.

_(Document the demo URL + any basic-auth here as it stabilizes. Keep secrets out
of the doc -- reference names, not values.)_
