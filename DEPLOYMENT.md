# Deployment Scripts

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

**Environment variables:**
- `POLYGLOT_PROJECT_NAME` - GCP project ID (auto-detected if not set)
- `FORM_KITS_BUCKET` - GCS bucket for form kits (default: `polyglot-demo-aa709-form-kits`; `deploy-production.sh` overrides this to the prod bucket explicitly)

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

Frontend is deployed via Firebase Hosting with the following setup:
- Public directory: `frontend/dist`
- API routes (`/api/**`) rewrite to Cloud Run service `polyglot-backend`
- SPA fallback to `/index.html`

See `firebase.json` for full configuration.
