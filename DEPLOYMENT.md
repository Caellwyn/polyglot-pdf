# Deployment Scripts

## Channels: which script do I run?

There are **two live channels**, both in project `polyglot-demo-aa709`:

| | staging (test deploy) | demo (protected) |
|---|---|---|
| script | `./deploy-staging.sh` | `./deploy-demo.sh` |
| URL | https://polyglot-app-staging.web.app | https://polyglot-demo-aa709.web.app |
| Cloud Run service | `polyglot-backend-staging` | `polyglot-backend` |
| audience | you | investors, pilot firms |
| break it? | yes, freely | never |

**Always deploy to staging first, verify there, then promote to demo.** Some bugs
appear only once deployed (Cloud Run WebSocket timeouts, Vertex model-id
resolution, the IAM envelope, the Hosting rewrite, per-mode Vite builds); local
testing cannot surface them.

The two channels share the project, the form-kits bucket, Firestore, and the
Firebase Auth user pool. Staging protects against broken **code** reaching the
demo, not against bad **data** -- publishing a form kit or changing Firestore
rules affects the demo no matter which channel you ran it from. Full detail and
the one-time site setup: [`docs/doctrine/promotion-tiers.md`](docs/doctrine/promotion-tiers.md).

`deploy-production.sh` is **dead** and refuses to run -- its target project is
unreachable (bd `polyglot-pdf-je6iy`).

## Main Script

### `deploy-all.sh`
Unified deployment script that handles all deployment tasks:

```bash
# Deploy everything (backend + frontend + form-kits)
./deploy-all.sh

# Or deploy specific components
./deploy-all.sh --backend      # Backend only
./deploy-all.sh --frontend     # Frontend only  
./deploy-all.sh --form-kits    # Form-kits only
```

**What it deploys:**
- **Backend**: Cloud Run service (`polyglot-backend`)
- **Frontend**: Firebase Hosting
- **Form Kits**: GCS bucket with form schemas and PDFs

> `deploy-all.sh` is the shared engine, not the thing you normally run. Prefer
> `./deploy-staging.sh` or `./deploy-demo.sh`, which set the channel wiring for
> you. A bare `./deploy-all.sh` defaults to the **demo** service and site.

**Environment variables** (the channel scripts set these; listed for a bare run):
- `POLYGLOT_PROJECT_NAME` - GCP project ID (auto-detected if not set)
- `FORM_KITS_BUCKET` - GCS bucket for form kits (default: `polyglot-demo-aa709-form-kits`)
- `BACKEND_SERVICE_NAME` - Cloud Run service (default: `polyglot-backend`; staging sets `polyglot-backend-staging`)
- `FRONTEND_HOSTING_TARGET` - Hosting target from `.firebaserc` (default: `app`; staging sets `app-staging`)
- `FRONTEND_SITE_NAME` - site name used for the URL echoed on success (defaults to the project name)
- `FRONTEND_BUILD_CMD` - Vite build command selecting the `.env.<mode>` file
- `BACKEND_EXTRA_ENV` / `BACKEND_SERVICE_ACCOUNT` - Cloud Run env + runtime identity

The frontend build does **not** trust a committed backend URL: `deploy-all.sh`
resolves the live Cloud Run URL for `BACKEND_SERVICE_NAME` at deploy time and
injects it as `VITE_WS_URL`. That is what points a staging build at the staging
backend, so overriding `BACKEND_SERVICE_NAME` is load-bearing for both stages.

## Helper Scripts

### `backend/deploy-new.sh`
Standalone backend deployment script. Use when you only need to update the backend service.

```bash
cd backend
./deploy-new.sh [SERVICE_NAME] [PROJECT_ID]
```

### `scripts/deploy-form-kit.sh`
Standalone form-kits deployment script. Use when you only need to update form schemas/PDFs.

```bash
# Upload specific form kit
./scripts/deploy-form-kit.sh i-90

# Upload all form kits
./scripts/deploy-form-kit.sh --all

# Regenerate manifest only
./scripts/deploy-form-kit.sh --manifest
```

## Deprecated Scripts

The following scripts have been removed in favor of `deploy-all.sh`:
- ~~`backend/deploy-backend.sh`~~ (used old `VOICE_PROJECT_NAME` env var)
- ~~`frontend/deploy-demo.sh`~~ (used GCS instead of Firebase)

## Firebase Configuration

Frontend is deployed via Firebase Hosting. `firebase.json` defines three
hosting targets, mapped to sites in `.firebaserc`:

| target | site | `/api/**` rewrites to |
|---|---|---|
| `app` | `polyglot-demo-aa709` | `polyglot-backend` |
| `app-staging` | `polyglot-app-staging` | `polyglot-backend-staging` |
| `editor` | `polyglot-editor-demo` | (no rewrite -- calls Cloud Run directly) |

All three use public directory `frontend/dist` (`schema-editor/dist` for the
editor) and SPA fallback to `/index.html`. **The per-target rewrite is what binds
a frontend to its backend** -- deploying the `app` target ships a build to the
demo site regardless of which backend it was built against, so the target and
`BACKEND_SERVICE_NAME` must always be set as a pair. The channel scripts do this.

See `firebase.json` for full configuration.
