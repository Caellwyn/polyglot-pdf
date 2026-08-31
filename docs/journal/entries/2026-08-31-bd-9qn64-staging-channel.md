---
date: 2026-08-31
bead: polyglot-pdf-9qn64
title: "feat(deploy): staging channel -- a test deploy that cannot break the investor demo"
tags: [doctrine, testing]
---

## Trigger

Maintainer, 2026-08-31: *"there are still some bugs that only show up after
deployment, so i don't want to break my site for demoing to others."*

The demo (`polyglot-demo-aa709.web.app`) was the ONLY deploy target and is also
the URL shown to investors and pilot firms. A whole class of bug is invisible
until deployed -- the Cloud Run WebSocket timeout (bd `9w5k`), Vertex model-id
resolution, the IAM envelope (CLAUDE.md scar #7, which cost a full outage past
3839 green tests), the Hosting `/api` rewrite, per-mode Vite builds. Finding any
of them meant risking the demo.

## What the investigation turned up first

Two things that reframed the task:

1. **There was no "production" to duplicate.** `deploy-production.sh` targets
   `polyglot-forms-919f2`, which does not appear in the maintainer's
   `gcloud projects list` at all; `deploy-all.sh`'s own comments, `auth.md`, and
   `bootstrap_firm.py` (which hard-refuses to touch it) all call it dead
   (bd `je6iy`). Its `.env.production` also ships an empty
   `VITE_FIREBASE_API_KEY`, so any frontend it built would die at launch. The
   repo looked like it had two channels; it had one, plus a trap.

2. **Two latent clobber bugs made the split impossible.** `deploy-all.sh`
   bare-assigned `BACKEND_SERVICE_NAME="polyglot-backend"` and hardcoded
   `--only hosting:app`. The first meant `deploy-production.sh` had been
   exporting `BACKEND_SERVICE_NAME` for its entire existence with **zero
   effect** -- a no-op nobody noticed because there was only ever one service.
   With a second channel, either bug deploys staging **over the live demo**:
   no error, clean `git status`, clean shell exit, and a deploy that genuinely
   succeeded -- at the wrong target. Exactly the silent-failure shape scar #3
   describes for `git reset --soft`.

## Decision: shared project, not a second one

Offered the maintainer separate-project vs. two-services-in-one-project. They
chose **one project** (`polyglot-demo-aa709`), separated by Cloud Run service
and Hosting site -- a second project would need its own IAM bootstrap, Auth user
pool, and enrolment run.

The tradeoff was stated before building, not discovered after: **staging
isolates broken CODE, not bad DATA.** Firestore, the form-kits bucket, and the
Auth user pool stay shared. That is the correct call for the stated problem (the
deploy-only bugs above are all code/config-shaped) but it is not blanket
protection, and the docs say so in those words.

## What shipped

| | staging | demo |
|---|---|---|
| script | `deploy-staging.sh` | `deploy-demo.sh` |
| Cloud Run | `polyglot-backend-staging` | `polyglot-backend` |
| Hosting target -> site | `app-staging` -> `polyglot-app-staging` | `app` -> `polyglot-demo-aa709` |

Flow is now worktree -> local -> `dev` -> **staging** -> **demo**.

- `deploy-all.sh`: `BACKEND_SERVICE_NAME` and the new `FRONTEND_HOSTING_TARGET`
  became `${VAR:-default}`, defaults unchanged so a bare run still means demo.
  `FRONTEND_SITE_NAME` is defaulted **after** `check_project()` -- defaulting it
  at the top would have baked in an empty site name on the gcloud-autodetect
  path.
- `firebase.json` / `.firebaserc`: a third hosting target whose `/api/**`
  rewrite points at the staging service. **That per-target rewrite is what binds
  a frontend to its backend**, which is why the target and `BACKEND_SERVICE_NAME`
  must always move as a pair.
- `deploy-staging.sh`: backend env **byte-identical** to the demo's, verified
  mechanically. A config difference would mean staging stops predicting demo
  behavior, and the bugs this exists to catch are precisely the config-shaped
  ones. Two deliberate asymmetries: a bare run does **not** publish form kits
  (shared bucket -> would change the DEMO's form list) and it **never** deploys
  `firestore.rules` (project-wide, not per-site).
- `deploy-production.sh`: kept as the record of the channel's shape but now
  `exit 1`s with a pointer to the two live channels. Left runnable it is the
  obvious wrong guess for "deploy the real one".

## Testing

`test_deploy_channel_isolation.py` pins the **set** of wiring that keeps the
channels apart (scar #8), not one instance of it: both clobber-prone variables
(parametrized), the parameterized hosting deploy, both `/api/**` rewrite
bindings, the staging script's two `BACKEND_SERVICE_NAME` exports, the
form-kits and rules abstentions, and the dead-prod refusal.

Every guard was mutation-verified against **the mutation that matters** (scar
#9) -- for the headline one, by restoring the exact clobbering assignment that
shipped, and confirming it goes red. Both parametrizations were verified
independently, not sampled. One mutation silently no-op'd (a backslash-escaping
failure in the edit); the occurrence count caught it, and it was redone by line
deletion -- a mutation that does not apply proves nothing.

Full backend suite after: **3100 passed, 31 skipped**, exit 0.

## What this does NOT fix

The **schema editor still shares the voice app's Cloud Run service** --
`backend/main.py` compiles `editor_kit_routes` + `editor_readiness_routes` into
the same FastAPI app, so there is one image and one deploy. An editor-only
backend change still forces a new revision of the service the demo runs on.
That is the hole left in this guarantee, filed as bd `polyglot-pdf-q64tv`
(maintainer's stated direction: give the editor its own backend).

Also filed: bd `polyglot-pdf-myc02`, an HTML deploy console -- five deployable
surfaces across three scripts (six after the editor split) is already past what
is comfortable to drive by hand, and the ordering/hazard rules currently live
only in prose.
