# Config & deployment

**Tracks:** backend/config.py backend/main.py backend/utils/dev_file_logger.py backend/services/callback_handler.py backend/Dockerfile deploy-all.sh deploy-demo.sh deploy-production.sh backend/deploy-new.sh firebase.json .firebaserc frontend/src/shared/config.ts

*Last updated: 2026-07-01. Added the hosted schema-editor access env vars (`SCHEMA_EDITOR_TOKEN`, `SCHEMA_AUTHOR_TOKEN`, `CORS_EXTRA_ORIGINS`, bd polyglot-pdf-92qe.1). The demo runs on Vertex AI (`VERTEXAI=true`,`USE_PREMIUM_MODEL=false`); `_resolve_model` is backend-aware so the standard tier picks the Vertex native-audio id (`gemini-live-2.5-flash-native-audio`) without a `MODEL_NATIVE` pin (bd polyglot-pdf-a079). Form-kit deploy is gated on `metadata.json status: complete` (`kit_is_complete` in deploy-all.sh) -- only complete kits reach GCS + the manifest. See [../journal/entries/2026-06-15-bd-a079-demo-vertex-ai-switch.md](../journal/entries/2026-06-15-bd-a079-demo-vertex-ai-switch.md). 2026-06-27: added the `SECRETARY_TIMEOUT_S` env knob (secretary blocking-call guard) and the `ask_secretary` tool (jnjj.45); see [../journal/entries/2026-06-27-bd-jnjj.45-secretary-build.md](../journal/entries/2026-06-27-bd-jnjj.45-secretary-build.md).*

How the backend is configured (settings, feature flags, env vars) and how both
surfaces ship. Config lives in `backend/config.py` (`Settings`, a pydantic
`BaseModel`); deployment is **local/manual** via the `deploy-*.sh` scripts — there
is no CI deploy. The two AI-model env vars surface here, but the canonical model
rules live in [../standards/ai-models.md](../standards/ai-models.md); VAD flags are
explained in [../standards/voice-and-vad.md](../standards/voice-and-vad.md).

## Settings & how env vars reach them

`Settings` is built once by `get_settings()`, which is `@lru_cache(maxsize=1)`
so all callers share a single instance (it was rebuilt per call before
`polyglot-pdf-efd`). **`.env` is auto-loaded:** `backend/main.py` calls
`load_dotenv()` *before* importing config, so any `backend/.env` populates
`os.environ` ahead of that first cached build, and the `Settings` fields that
call `os.getenv(...)` pick it up. (The `get_settings` docstring still says ".env
in later phases" — that's stale; `main.py:7` already does it.) Because the result
is cached, a test that mutates `os.environ` and wants a fresh read must call
`get_settings.cache_clear()` (most tests instead monkeypatch the module attribute,
which bypasses the cache).

**Two classes of setting — only one is env-overridable:**

- **Env-overridable** (the field calls `os.getenv`): `USE_PREMIUM_MODEL`,
  `MODEL_NATIVE`, `MODEL_LABELING`, `GEMINI_API_KEY`, `VERTEXAI`,
  `DISABLE_GEMINI_VAD`, `USE_JIT_SCHEMA`, `SECRETARY_TIMEOUT_S`, `FORM_KITS_MODE`,
  `FORM_KITS_LOCAL_ROOT`, `FORM_KITS_GCS_BUCKET`, `FORM_KITS_REMOTE_BASE_URL`,
  `FORM_KITS_REMOTE_PREFIX`, `FORM_KITS_REMOTE_TIMEOUT_SEC`,
  `SCHEMA_EDITOR_TOKEN`, `SCHEMA_AUTHOR_TOKEN`, `CORS_EXTRA_ORIGINS`.
- **Code constants** (plain field defaults — changing them needs a code edit, NOT
  an env var): `PROACTIVE_AUDIO`, the audio rates
  (`AUDIO_IN_RATE` 16000 / `AUDIO_OUT_RATE` 24000), the WS knobs
  (`WS_IDLE_TIMEOUT_SEC` 120, `WS_PING_INTERVAL_SEC` 15, `WS_CHUNK_MS` 20,
  `WS_MAX_OUTBOX` 100, `WS_MAX_AUDIO_FRAME_BYTES` 32000), `MAX_UPLOAD_MB` 5, the
  `VAD_*` sensitivity knobs, `PARSER_VERSION`, and the prompt templates.

## Feature flags

| Flag | Default | Effect |
|------|---------|--------|
| `USE_PREMIUM_MODEL` | `false` | Flips the active native-audio model tier — `false` → 2.5 standard (default for its audio-path behavior), `true` → 3.1 premium (opt-in; now tool-call-reliable since the untyped-param fix, `bd polyglot-pdf-wpw.4`). See [ai-models.md](../standards/ai-models.md). |
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

- **`VERTEXAI`** (env, default `true`) — picks the auth/service mode. `true` →
  Vertex AI via `GOOGLE_CLOUD_PROJECT` + service-account ADC (no key needed;
  keeps request data private). `false` → Gemini Developer API (**AI Studio**),
  which authenticates **only** via `GEMINI_API_KEY` (no ADC/SA path). The demo
  runs `VERTEXAI=true` (the privacy path). The standard native-audio model id
  differs by backend, so `_resolve_model` is backend-aware: on Vertex the
  standard tier resolves to `gemini-live-2.5-flash-native-audio` (the AI Studio
  id 1008s on Vertex), so a Vertex deploy needs no `MODEL_NATIVE` pin. 3.1 is
  AI-Studio-only as of 2026-06, so reaching it still requires `VERTEXAI=false`.
  See [ai-models.md](../standards/ai-models.md).
- **`GEMINI_API_KEY`** — required when `VERTEXAI=false` (AI Studio key); unused on
  the Vertex path. On the demo Cloud Run service it is injected via **Secret
  Manager** (`--set-secrets`), never as a plaintext env var.
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
- **`SCHEMA_EDITOR_TOKEN` / `SCHEMA_AUTHOR_TOKEN`** — shared-secret access codes
  for the token-gated `/api/editor/*` surface the hosted schema editor uses
  (`backend/routes/editor_kit_routes.py`, bd `polyglot-pdf-92qe.1`). Two tiers:
  *editor* = polish provided kits (list/read drafts, save schemas, flip status);
  *author* = editor + PDF onboarding/hosted extraction (bd 92qe.3). Neither set →
  the surface is disabled (503 fail-closed). On Cloud Run inject via Secret
  Manager (`--set-secrets`), never plaintext env.
- **`CORS_EXTRA_ORIGINS`** — comma-separated extra CORS origins appended to the
  hardcoded localhost list in `backend/main.py` (e.g. the hosted schema-editor
  site, which calls Cloud Run directly rather than through the Hosting `/api`
  rewrite — the rewrite's 60s cap would kill minutes-long extraction requests).
  List explicit origins only; do NOT set `*` — the app runs
  `allow_credentials=True`, and browsers reject the wildcard+credentials
  combination, so `*` silently breaks CORS instead of opening it.
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
  `gcloud run deploy ... --allow-unauthenticated --timeout=3600 --set-env-vars=` with
  `GOOGLE_CLOUD_PROJECT`, `FORM_KITS_MODE=gcs`, `FORM_KITS_GCS_BUCKET`,
  `FORM_KITS_REMOTE_PREFIX`, plus any channel-specific vars the wrapper passes via
  `BACKEND_EXTRA_ENV` (demo: `VERTEXAI=true,USE_PREMIUM_MODEL=false`). The
  container (`backend/Dockerfile`, `python:3.12-slim`) runs `uvicorn
  backend.main:app` on `$PORT` (8080). `--timeout=3600` (the Cloud Run maximum)
  is load-bearing for `/ws/fill`: Cloud Run kills any request at the timeout,
  live WebSockets included, and the 300s default terminated every voice session
  at exactly 5 minutes (bd polyglot-pdf-9w5k).
- **Form-kits** — uploads the **complete** kits from the local `form-kits/` tree
  to `gs://<bucket>/<prefix>/` plus an `index.json` manifest. Demo bucket
  `polyglot-demo-aa709-form-kits`; prod bucket `polyglot-pdf-form-kits`. A kit is
  uploaded (and listed in the manifest) only when its `metadata.json` has
  `status: complete` — the `kit_is_complete` gate in `deploy-all.sh` skips draft
  / unmarked kits so in-progress forms stay local + git-backed and never reach the
  voice app (bd polyglot-pdf-b0pe). Both the upload loop and the manifest loop are
  gated, so a draft is absent from GCS *and* the served manifest.
- **Frontend** — built via `FRONTEND_BUILD_CMD` (set by the wrapper: prod
  `npm run build:schema` → `.env.production`; demo `npm run build:schema:demo`
  → `.env.demo`). Output `frontend/dist` → `firebase deploy --only hosting`. The
  bare `npm run build` is NOT used: it loads `.env.production` under the default
  Vite config, whose Firebase keys differ per channel — a demo built that way dies
  with `auth/invalid-api-key`.
- **Firestore rules** — `firebase deploy --only firestore:rules` ships
  `firestore.rules` (wired via `firebase.json`). This step lives in the
  **`deploy-demo.sh` / `deploy-production.sh` wrappers**, not `deploy-all.sh`, runs
  only on a frontend/full deploy, and runs **before** the frontend so the new
  frontend never goes live against stale rules. A project left on default-deny
  breaks email signup (the unauth `authorized_emails` read) and the `users/{uid}`
  profile sync -- see [auth.md](auth.md).

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
The `__VFF_*` dev overrides are read from `window` OR `localStorage` (so they
survive a reload). `config.ts` also exposes `isTestHarnessEnabled()` (true only
when both `__VFF_LOCAL_DEV` and `__VFF_TEST_HARNESS` are set) — a dev/test-only
gate used by the E2E voice harness; never true in production.

> **Promotion path** is worktree → local test server → `dev` → demo remote
> (`deploy-demo.sh`); deploys stay manual (local shell scripts, not CI) and there
> is **no active prod**. The agent may run the demo deploy under a three-part gate
> (local-test-first + per-instance permission + post-deploy test-drive). See
> [../doctrine/promotion-tiers.md](../doctrine/promotion-tiers.md).
