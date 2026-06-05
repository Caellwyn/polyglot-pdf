---
date: 2026-06-04
bead: polyglot-pdf-2gg
tags: [deploy, frontend, build, ops-script, self-heal]
files:
  - deploy-all.sh
---

# Self-heal frontend node_modules in deploy-all.sh (bd 2gg)

## What

`deploy-demo.sh --frontend` (which delegates to `deploy-all.sh --frontend`)
failed with `'tsx' is not recognized` during the frontend build. Added a
self-heal step that installs the frontend dependencies when they are missing,
before `npm run build`.

## Why it broke

`frontend/node_modules` is git-ignored. The maintainer reported running
`npm install` just before the deploy, yet `tsx` was still absent -- the
checkout's `frontend/node_modules` was empty (0 packages). The most likely
cause is running `npm install` from the **repo root** rather than from
`frontend/`, so the frontend's devDependencies (including `tsx`) never landed.
`deploy-all.sh` then ran `npm run build`, whose `prebuild` hook
(`form-kits:prepare`) invokes `tsx scripts/generate-form-manifest.ts`, which
is not on disk -> hard failure.

## The fix

In the frontend deploy block, after `cd "$FRONTEND_DIR"`:

```sh
if [ ! -x node_modules/.bin/tsx ]; then
    log_info "Frontend dependencies missing -- installing..."
    if [ -f package-lock.json ]; then
        npm ci
    else
        npm install
    fi
fi
```

Path safety was the maintainer's explicit concern (the deploy is launched from
the repo root). It is already handled: `FRONTEND_DIR="$SCRIPT_DIR/frontend"` is
derived from `BASH_SOURCE` (the script's own location), and the block `cd`s into
it before the guard runs -- so the install always targets the correct tree
regardless of the caller's cwd. The guard tests the actual `tsx` binary, not
just the directory, so it also catches partial installs. `npm ci` is preferred
when a lockfile is present (reproducible), with `npm install` as the fallback.

## Backend: no self-heal needed (by design)

The backend deploy builds a fresh image via Cloud Build on every run, and the
Dockerfile does `pip install --no-cache-dir -r requirements.txt` inside it.
There is no local `.venv` in the deploy path, so nothing local can go stale.
Added a one-line comment in the backend block recording this, so the asymmetry
with the frontend is self-explaining. (The local `backend/.venv` matters only
for running tests/dev locally, which is a separate concern from deployment.)

## Verification

Reproduced the failure in the worktree (its `frontend/node_modules` was empty):
the guard fired, selected `npm ci` (lockfile present), `npm ci` exited 0, `tsx`
landed in `node_modules/.bin/`, and the previously-failing
`tsx scripts/generate-form-manifest.ts` then ran clean and wrote the manifest.
`bash -n deploy-all.sh` passes; added lines are ASCII-only. Full backend test
suite: 186 passed, 2 skipped.

## Closeout triage notes (dismissed, not blockers)

- **Doc-freshness flagged 16 stale docs.** All are stale relative to *other*
  product-code edits made earlier the same day (backend/frontend, ~17:07), none
  of which this PR touches. This diff is `deploy-all.sh` only and touches zero
  documented surfaces -- no doc update is owed by this change.
- **Beads stale: `polyglot-pdf-hrn`.** That epic is intentionally held open by
  its billing marker child `.8` (use up prepaid Copilot credits before the
  review-provider migration). It is in_progress on purpose, not neglected, and
  is unrelated to this PR.
