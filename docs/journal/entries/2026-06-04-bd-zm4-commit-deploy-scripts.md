---
date: 2026-06-04
bead: polyglot-pdf-zm4
type: chore
surfaces: [config-deployment]
tags: [deploy, vertex, ai-studio, demo, vite, env]
files:
  - deploy-all.sh
  - deploy-demo.sh
  - deploy-production.sh
  - frontend/.env.production
  - frontend/.env.demo
  - .gitignore
  - docs/components/config-deployment.md
---

# Commit demo AI-Studio toggles + schema build mode (bd polyglot-pdf-zm4)

## Why

The deploy-script and `.env.production` edits that supported the demo voice fix
(bd `polyglot-pdf-jrl`, PR #89) were left **uncommitted on the working tree** --
PR #89 only carried the backend `.py` files + docs. Tracked-but-dirty deploy
scripts meant every `git pull` on the root repo was blocked by a dirty tree, and
the changes were at risk of being lost on any stash/reset. This commits them so
`dev` is the source of truth and the root stays clean.

## What

- **deploy-all.sh** -- `FRONTEND_BUILD_CMD` hook (default `npm run build:schema`)
  and `BACKEND_EXTRA_ENV` hook so channel wrappers append channel-specific Cloud
  Run env vars without editing the shared script.
- **deploy-demo.sh** -- demo backend runs `VERTEXAI=false,USE_PREMIUM_MODEL=true`
  (AI Studio + Gemini 3.1); demo frontend builds `build:schema:demo` so Vite
  loads `.env.demo`.
- **deploy-production.sh** -- prod frontend builds `build:schema` (`.env.production`).
- **frontend/.env.production** -- prod Firebase config block (empty placeholders +
  public, non-secret config values) so a prod build no longer ships an undefined
  Firebase config (`auth/invalid-api-key`).
- **config-deployment.md** -- updated the deploy section: frontend now builds via
  `FRONTEND_BUILD_CMD` (not bare `npm run build`); backend env includes the
  `BACKEND_EXTRA_ENV` channel vars.

- **frontend/.env.demo** -- committed (with a `!.env.demo` gitignore exception,
  mirroring the existing `!.env.production`). It was gitignored and existed only
  on the maintainer's machine, so `build:schema:demo` (which loads `.env.demo`)
  would silently ship a demo build with NO Firebase config on any fresh checkout
  / CI. It holds only public `VITE_*` values (channel WS URL + Firebase web
  config), so committing it makes the demo build reproducible. (Caught by
  fresh-eyes.)

No secrets committed: `GEMINI_API_KEY` stays in Secret Manager (`--set-secrets`);
the Firebase web config values in `.env.demo` / `.env.production` are public
client config (same class the repo already commits for `.env.production`).

## Known follow-up (not a defect in this PR)

`frontend/.env.production` ships with three Firebase fields still BLANK
(`VITE_FIREBASE_API_KEY`, `_MESSAGING_SENDER_ID`, `_APP_ID`) -- placeholders only.
A **prod** deploy will still `auth/invalid-api-key` until the maintainer pastes
the values from the `polyglot-forms-919f2` Firebase console (`firebase
apps:sdkconfig web --project polyglot-forms-919f2`). This is intentional and
owner-action-pending: that project is not reachable from this session, and the
demo (the live target) is fully configured via `.env.demo`. Fresh-eyes flagged
the blanks; recorded here so they are not mistaken for done.

## Decisions (defended)

- **Committed the deploy scripts rather than gitignoring them.** They are tracked
  files encoding real per-channel deploy config; the maintainer wants them shared
  and backed up on `dev`, not local-only. This also resolves the recurring
  "can't pull with a dirty tree" friction.
- **Folded the one stale doc line into this PR.** The frontend `npm run build`
  line in config-deployment.md is made stale *by this change*, so fixing it here
  keeps the doc honest in the same commit.
