# Config & deployment

**Tracks:** backend/config.py backend/main.py backend/utils/dev_file_logger.py backend/services/callback_handler.py backend/Dockerfile deploy-all.sh deploy-demo.sh deploy-production.sh firebase.json .firebaserc frontend/src/shared/config.ts

*Last updated: 2026-06-01*

How the backend is configured (settings, feature flags, env vars) and how both
surfaces ship. Config lives in `backend/config.py` (`Settings`, a pydantic
`BaseModel`); deployment is **local/manual** via the `deploy-*.sh` scripts — there
is no CI deploy. The two AI-model env vars surface here, but the canonical model
rules live in [../standards/ai-models.md](../standards/ai-models.md); VAD flags are
explained in [../standards/voice-and-vad.md](../standards/voice-and-vad.md).

## Settings & how env vars reach them

`Settings` is instantiated per-call by `get_settings()`. **`.env` is auto-loaded:**
`backend/main.py` calls `load_dotenv()` *before* importing config, so any
`backend/.env` populates `os.environ`, and the `Settings` fields that call
`os.getenv(...)` pick it up. (The `get_settings` docstring still says ".env in
later phases" — that's stale; `main.py:7` already does it.)

**Two classes of setting — only one is env-overridable:**

- **Env-overridable** (the field calls `os.getenv`): `USE_PREMIUM_MODEL`,
  `MODEL_NATIVE`, `MODEL_LABELING`, `GEMINI_API_KEY`, `USE_JIT_SCHEMA`,
  `FORM_KITS_MODE`, `FORM_KITS_LOCAL_ROOT`, `FORM_KITS_GCS_BUCKET`,
  `FORM_KITS_REMOTE_BASE_URL`, `FORM_KITS_REMOTE_PREFIX`,
  `FORM_KITS_REMOTE_TIMEOUT_SEC`.
- **Code constants** (plain field defaults — changing them needs a code edit, NOT
  an env var): `VERTEXAI`, `DISABLE_GEMINI_VAD`, `PROACTIVE_AUDIO`, the audio rates
  (`AUDIO_IN_RATE` 16000 / `AUDIO_OUT_RATE` 24000), the WS knobs
  (`WS_IDLE_TIMEOUT_SEC` 120, `WS_PING_INTERVAL_SEC` 15, `WS_CHUNK_MS` 20,
  `WS_MAX_OUTBOX` 100, `WS_MAX_AUDIO_FRAME_BYTES` 32000), `MAX_UPLOAD_MB` 5, the
  `VAD_*` sensitivity knobs, `PARSER_VERSION`, and the prompt templates.

## Feature flags

| Flag | Default | Effect |
|------|---------|--------|
| `USE_PREMIUM_MODEL` | `true` | Flips the active native-audio model tier — `true` → 3.1 premium (the reliable default), `false` → 2.5 standard (cheaper). See [ai-models.md](../standards/ai-models.md). |
| `MODEL_NATIVE` | _(derived)_ | Pin an exact model string; **non-empty wins** over `USE_PREMIUM_MODEL` (resolved in `Settings._resolve_model`). |
| `USE_JIT_SCHEMA` | `false` | Send a field **manifest** + load each full field schema just-in-time (token reduction), using `JIT_SYSTEM_INSTRUCTION` instead of `SYSTEM_INSTRUCTION`. See [schema-forms.md](schema-forms.md). |
| `DISABLE_GEMINI_VAD` | `True` (code constant, CRITICAL) | Turns off Gemini auto-VAD; the client drives turn-taking with manual `activity_start/end`. See [voice-and-vad.md](../standards/voice-and-vad.md). |
| `PROACTIVE_AUDIO` | `False` (code constant) | DEPRECATED — Gemini stops calling tools when on. See [voice-and-vad.md](../standards/voice-and-vad.md#hallucination-reduction). |

## Form-kit storage (`FORM_KITS_MODE`)

The schema+PDF store backing PDF fill ([pdf-filling.md](pdf-filling.md)):

- **`local`** (default, local dev) — reads `<FORM_KITS_LOCAL_ROOT>/<kit_id>/`;
  `FORM_KITS_LOCAL_ROOT` defaults to `<repo>/form-kits`.
- **`gcs`** (what deploys use) — reads
  `gs://<FORM_KITS_GCS_BUCKET>/<FORM_KITS_REMOTE_PREFIX>/<kit_id>/...`. The
  `--set-env-vars` that pins `FORM_KITS_MODE=gcs` + the bucket lives in
  **`deploy-all.sh`**; the `deploy-demo.sh` / `deploy-production.sh` wrappers only
  set the shell vars (project, bucket name) and delegate to it.

## Required & dev-only env vars

- **`GEMINI_API_KEY`** — required (Google AI Studio / Vertex AI key). The `VERTEXAI`
  field (a **code constant**, default `True`) makes the adapter also resolve
  credentials via `GOOGLE_CLOUD_PROJECT` + ADC; the deploy scripts set
  `GOOGLE_CLOUD_PROJECT`. (Changing `VERTEXAI` needs a code edit, not an env var.)
- **`backend/.env.DEV` marker file** — this **file's existence** (NOT an env var)
  flips `DEV_LOGGING_ENABLED` in `backend/utils/dev_file_logger.py`, which is the
  **single gate** for *both* dev-logging paths: the `DevFileLogger` itself **and**
  the field-value `_dev_log` calls in `backend/services/callback_handler.py`
  (`_dev_log` is just `get_dev_logger()`, whose `enabled` is `DEV_LOGGING_ENABLED`).
  Present only in local dev (gitignored + dockerignored), so prod never logs
  PII/PHI. This is the HIPAA guard — see
  [hipaa-pii-policy.md](../standards/hipaa-pii-policy.md) and bd `polyglot-pdf-hjo`.
- **`VFF_DISABLE_AUTH=true`** — dev bypass for Firebase token verification
  (`backend/services/auth.py`); returns a stub `dev_user`. Auth canon lives in the
  planned `auth.md` (bd `polyglot-pdf-y3l`).
- **`GENAI_WEBSOCKET_BASE`** — optional override of the genai SDK's Live WebSocket
  base (`backend/adapters/live_ai_gemini.py`), for pointing at a non-default
  endpoint.

> The legacy env doc (`ENV_VARIABLES.md`, now archived at
> [`../archive/ENV_VARIABLES.md`](../archive/ENV_VARIABLES.md)) is superseded by this
> doc; it predates the `.env.DEV` marker mechanism and describes `VFF_DEV_LOGGING` as the
> dev-logging switch. **`VFF_DEV_LOGGING` is dead config:** no code reads it (the
> only remaining reference is a stale comment in `callback_handler.py:194`); the
> real gate is the `.env.DEV` marker above. The stale comment is tracked for
> cleanup under bd `polyglot-pdf-jpe`.

## Deployment (local/manual — no CI)

Two Firebase/GCP projects, both running a Cloud Run service named
**`polyglot-backend`** in **`us-central1`**. Aliases live in `.firebaserc`:

| Channel | Project ID | Script | Frontend URL |
|---------|-----------|--------|--------------|
| **demo** | `polyglot-demo-aa709` | `deploy-demo.sh` | `https://polyglot-demo-aa709.web.app` |
| **production** | `polyglot-forms-919f2` (`.firebaserc` `default`/`prod`) | `deploy-production.sh` | `https://polyglot-forms-919f2.web.app` |

Both delegate to **`deploy-all.sh`** (`--backend`, `--form-kits`, `--frontend`
stages):

- **Backend** — `gcloud builds submit` to `gcr.io/<project>/polyglot-backend`, then
  `gcloud run deploy ... --allow-unauthenticated --set-env-vars=` with
  `GOOGLE_CLOUD_PROJECT`, `FORM_KITS_MODE=gcs`, `FORM_KITS_GCS_BUCKET`,
  `FORM_KITS_REMOTE_PREFIX`. The container (`backend/Dockerfile`, `python:3.12-slim`)
  runs `uvicorn backend.main:app` on `$PORT` (8080).
- **Form-kits** — uploads the local `form-kits/` tree to
  `gs://<bucket>/<prefix>/` plus an `index.json` manifest. Demo bucket
  `polyglot-demo-aa709-form-kits`; prod bucket `polyglot-pdf-form-kits`.
- **Frontend** — `npm run build` (output `frontend/dist`) → `firebase deploy --only
  hosting`.

### Frontend → backend wiring

`firebase.json` rewrites **`/api/**` → the `polyglot-backend` Cloud Run service**
(this is how the stateless PDF-fill HTTP call reaches the backend through Hosting),
plus a catch-all `** → /index.html` for SPA routing.

**WebSockets do NOT go through the Hosting rewrite** (Firebase Hosting can't proxy
WS). `frontend/src/shared/config.ts` `getBackendUrl()` resolves the WS URL in this
order: (1) local-dev override (`window.__VFF_LOCAL_DEV` → `window.__VFF_BACKEND_URL`,
default `ws://localhost:8000/ws/fill`); (2) `VITE_WS_URL` env var; (3) production —
the hardcoded `PRODUCTION_WS_URL` (`wss://polyglot-backend-d3mhrrkwfq-uc.a.run.app/ws/fill`)
when the page is HTTPS and not localhost; (4) dev fallback `ws://localhost:8000/ws/fill`.

> **Promotion path** is feature → `dev` (staging) → `main` (prod); deploys
> themselves stay manual. See [../doctrine/promotion-tiers.md](../doctrine/promotion-tiers.md).

*Last updated: 2026-06-01*
