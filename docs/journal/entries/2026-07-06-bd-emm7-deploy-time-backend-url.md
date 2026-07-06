---
date: 2026-07-06
bead: polyglot-pdf-emm7
title: "Resolve the Cloud Run backend URL at deploy time (stop baking a fragile hash)"
tags: [hotfix, conventions]
---

## Trigger

The hosted schema editor's backend URL was a committed literal in
`schema-editor/.env.hosted` (`VITE_API_BASE_URL=https://polyglot-backend-<hash>-uc.a.run.app`).
That Cloud Run auto-URL `<hash>` is NOT stable: it drifted
`d3mhrrkwfq -> won24rgefq` on a service recreate, silently pointing the deployed
editor at a 404'd backend -- every access-code entry looked like a wrong password.
It was patched once by hand-editing the literal + redeploying, but the same
landmine would trip on the next recreate.

**Scope widened at implementation (maintainer decision 2026-07-06):** the SAME
fragility lived in the MAIN voice app -- `frontend/.env.demo` and
`frontend/.env.production` also hardcoded the hash (`.env.production` still held the
stale `d3mhrrkwfq` that now 404s), and nothing injected them dynamically; the
"correct" demo hash only ever got there via a past manual edit. This was directly
observed this session: the kl26 demo redeploy changed the backend hash, and the
live frontend happened to already carry the new one only because someone had
hand-updated `.env.demo`. The maintainer chose to fix all three in this PR rather
than editor-only.

## What shipped

Option 2 from the bead (deploy-time resolution, no new infra):

- **`deploy-editor.sh`**: before `npm run build:hosted`, resolve the live URL via
  `gcloud run services describe polyglot-backend --format 'value(status.url)'` and
  `export VITE_API_BASE_URL`. A caller-provided value (e.g. a localhost full-stack
  test) still wins; on resolution failure it warns and falls back to `.env.hosted`.
- **`deploy-all.sh`**: in the frontend section, reuse `BACKEND_URL` if the backend
  stage already resolved it this run, else resolve it fresh (for a `--frontend`-only
  run), then `export VITE_WS_URL="${BACKEND_URL/https:/wss:}/ws/fill"` before the
  build. Same warn-and-fallback on failure.
- **`.env.demo` / `.env.production` / `.env.hosted`**: the committed URL literals
  are now documented FALLBACK-ONLY values (comment explains deploy-time resolution
  overrides them). `.env.production`'s stale hash was replaced with an obvious
  `PLACEHOLDER` so it can't masquerade as live (prod is abandoned anyway).

The mechanism is standard Vite precedence: a shell `VITE_*` var overrides the
`.env.<mode>` file. `.env.demo` already documented this ("Can be overridden by
VITE_* variables passed on command line").

Verification:
- Resolution: `gcloud run services describe ... --format 'value(status.url)'`
  returns `https://polyglot-backend-won24rgefq-uc.a.run.app`, deriving
  `wss://.../ws/fill`.
- **Override precedence proven by build**: built the hosted editor with
  `VITE_API_BASE_URL=https://SENTINEL-OVERRIDE-test.a.run.app` and grepped the
  emitted bundle -- the SENTINEL is present (1 hit) and the `.env.hosted` literal
  `won24rgefq` is ABSENT (0 hits). So a redeploy after a URL change picks up the
  live URL with no manual .env edit (exit criterion 2).
- `bash -n` clean on both scripts; the sourced-helper test
  (`test_deploy_all_kit_gates_wrapper.py`) still runs (skips on this env), so the
  `BASH_SOURCE != $0` source-guard is intact -- my change sits after it in the
  executed flow.

Not done (deliberately): no custom-domain mapping (option 1) -- deploy-time
resolution is the low-effort durable fix the bead recommended; a custom domain can
be layered later if wanted.

## Lessons

Hit the worktree-vs-main write trap again (scar #3 / `write-tool-needs-worktree-
path-not-main`): the first `deploy-all.sh` edit landed in the MAIN checkout because
the Edit path was the main-repo absolute path. Caught by a `git status` on both
trees; recovered via `git diff > patch` in main, `git checkout` to revert main,
`git apply` into the worktree. Same recovery as the zb55 session -- worth a
standing habit of Edit-ing via the `.claude\worktrees\<name>\` path.

## Doc freshness

`docs/components/config-deployment.md` tracks `deploy-all.sh` (and
`frontend/src/shared/config.ts`), so it was updated to current state: the Frontend
build bullet now notes deploy-time `VITE_WS_URL` resolution; the hosted-editor
section notes `deploy-editor.sh` resolves `VITE_API_BASE_URL`; and the WS-URL
resolution-order list now marks step (2) `VITE_WS_URL` as the real production path
(deploy-injected) and step (3)'s hardcoded `PRODUCTION_WS_URL` (`d3mhrrkwfq`) as a
stale last-resort fallback. Stamp bumped. (`deploy-editor.sh` itself is not in any
doc's `**Tracks:**`.) The promotion-tiers doctrine describes the flow, not the
URL-baking mechanism, and is unaffected. Other freshness flags are pre-existing
staleness on files this branch did not touch.

## Files touched

- `deploy-editor.sh` -- resolve + export `VITE_API_BASE_URL` at deploy time.
- `deploy-all.sh` -- resolve + export `VITE_WS_URL` before the frontend build.
- `frontend/.env.demo` -- URL literal marked fallback-only.
- `frontend/.env.production` -- URL literal marked fallback-only; stale hash -> PLACEHOLDER.
- `schema-editor/.env.hosted` -- URL literal marked fallback-only.
- `docs/journal/entries/2026-07-06-bd-emm7-deploy-time-backend-url.md` -- this entry.
