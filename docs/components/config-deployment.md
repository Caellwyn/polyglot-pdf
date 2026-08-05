# Config & deployment

**Tracks:** backend/config.py backend/main.py backend/utils/dev_file_logger.py backend/services/callback_handler.py Dockerfile .gcloudignore deploy-all.sh deploy-demo.sh deploy-production.sh backend/deploy-new.sh firebase.json .firebaserc frontend/src/shared/config.ts

*Last updated: 2026-08-05 (docs audit bd polyglot-pdf-2zk3: USE_DTI/CONTINUOUS_SESSION
default flipped to true, main.py load_dotenv line fix, jpe cleanup already shipped,
deploy-new.sh mentioned). Vertex is the only production path (bd polyglot-pdf-5e6a):
the ALLOW_AI_STUDIO override was removed; a deployed AI Studio path now fails
startup outright.*

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
in later phases" — that's stale; `main.py:10` already does it.) Because the result
is cached, a test that mutates `os.environ` and wants a fresh read must call
`get_settings.cache_clear()` (most tests instead monkeypatch the module attribute,
which bypasses the cache).

**Two classes of setting — only one is env-overridable:**

- **Env-overridable** (the field calls `os.getenv`): `USE_PREMIUM_MODEL`,
  `MODEL_NATIVE`, `MODEL_LABELING`, `GEMINI_API_KEY`, `VERTEXAI`,
  `DISABLE_GEMINI_VAD`, `USE_DTI`, `SECRETARY_TIMEOUT_S`,
  `FORM_KITS_MODE`, `FORM_KITS_LOCAL_ROOT`, `FORM_KITS_GCS_BUCKET`,
  `FORM_KITS_REMOTE_PREFIX`, `SCHEMA_EDITOR_TOKEN`, `SCHEMA_AUTHOR_TOKEN`,
  `CORS_EXTRA_ORIGINS`, `EXTRACTOR_MODEL`, `EXTRACTOR_TIMEOUT_SEC`,
  `EXTRACTOR_MAX_PDF_MB`, `VAD_START_SENSITIVITY` (default `HIGH`) /
  `VAD_END_SENSITIVITY` (default `LOW`).
- **Code constants** (plain field defaults — changing them needs a code edit, NOT
  an env var): the audio rates
  (`AUDIO_IN_RATE` 16000 / `AUDIO_OUT_RATE` 24000), the WS knobs
  (`WS_IDLE_TIMEOUT_SEC` 120, `WS_PING_INTERVAL_SEC` 15, `WS_CHUNK_MS` 20,
  `WS_MAX_AUDIO_FRAME_BYTES` 32000), `MAX_UPLOAD_MB` 5, and the prompt
  templates.

## Feature flags

| Flag | Default | Effect |
|------|---------|--------|
| `USE_PREMIUM_MODEL` | `false` | Flips the active native-audio model tier — `false` → 2.5 standard (default for its audio-path behavior), `true` → 3.1 premium (**LOCAL-ONLY**: 3.1 exists only on AI Studio, and the Vertex-only startup guard cannot catch this flip — the premium id resolves before the `VERTEXAI` branch, so a deployed service starts then `1008`s at connect. Deploy 3.1 only once GA on Vertex. Opt-in; now tool-call-reliable since the untyped-param fix, `bd polyglot-pdf-wpw.4`). See [ai-models.md](../standards/ai-models.md). |
| `MODEL_NATIVE` | _(derived)_ | Pin an exact model string; **non-empty wins** over `USE_PREMIUM_MODEL` (resolved in `Settings._resolve_model`). |
| `DISABLE_MODEL_THINKING` | `true` | Turn off model "thinking" tokens on the live session (the form-fill loop needs no chain-of-thought; thinking bills at the output rate). When on and the model is 2.5-family, the connect config carries `thinking_config={"thinking_budget": 0}`; 3.1 (different `thinking_level` field) is left at default. Effect on native-audio Live is unverified upstream, so safe-if-ignored. See [voice-ai.md](voice-ai.md). |
| `USE_DTI` | `true` | Dynamic Turn Injection -- the shipped reduced-SI mode (code default flipped to `true` by bd `polyglot-pdf-7872` on 2026-07-11; `deploy-demo.sh` no longer needs to set it). A thin-principal SI carrying only the static backbone; the CURRENT field's guidance rides the initiating message and each next field's guidance rides the `confirm_field` tool response, instead of dumping the section's fields into the SI. `false` -> the legacy full-SI fallback (`SYSTEM_INSTRUCTION` with the whole current-section field dump). DTI is carried over the manifest-first handshake transport (`handshake_jit` / `jit_mode`). See [schema-forms.md](schema-forms.md), [websocket-routing.md](websocket-routing.md), and [../standards/si-reduction.md](../standards/si-reduction.md). |
| `CONTINUOUS_SESSION` | `true` | Runs the whole form as one Gemini Live session bounded by context-window compression, instead of resetting the session per section (code default flipped to `true` alongside `USE_DTI` by bd `polyglot-pdf-7872`). Requires `USE_DTI`: if `CONTINUOUS_SESSION` is on and `USE_DTI` is off, `Settings` forces `USE_DTI` on and logs a warning rather than serve the inconsistent combination. `false` -> the legacy per-section-reset flow (used as the measurement-harness baseline). See [context-compression.md](context-compression.md). |
| `DISABLE_GEMINI_VAD` | `false` (env-overridable) | `false` → native mode (Gemini's automatic VAD detects turns); `true` → manual mode (the client drives turn-taking with `activity_start/end`). See [voice-and-vad.md](../standards/voice-and-vad.md). |

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
  AI-Studio-only as of 2026-06, so reaching it still requires `VERTEXAI=false`
  — which is a **LOCAL-ONLY** exercise: a deployed service refuses to start on
  that path (see the Vertex-only rule below). See
  [ai-models.md](../standards/ai-models.md).
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
  (`backend/services/auth.py`); returns a stub `dev_user`. Covers BOTH the
  `/ws/fill` gate and the bd-z2is HTTP gates (`require_auth` on
  `/api/fill-pdf` + form-kit list/schema reads). Auth canon:
  [auth.md](auth.md).
- **Vertex is the ONLY production path** (maintainer directive 2026-08-04, bd
  `polyglot-pdf-5e6a`). `VERTEXAI=false` on a DEPLOYED service (`K_SERVICE`
  present ⇒ Cloud Run) makes `Settings` fail startup, and there is **no
  override flag** — the former `ALLOW_AI_STUDIO` acknowledgment was removed
  because no legitimate deployed AI Studio use exists. Only Vertex's privacy
  agreement keeps client data out of Google's model training. AI Studio is
  permitted **locally only** (no `K_SERVICE`), for testing a model before it
  reaches Vertex GA. See [../standards/ai-models.md](../standards/ai-models.md).
- **`CONFIRMATION_FIRESTORE_ENABLED=true`** — mirrors the confirmation audit
  trail (metadata only, never values) to the `confirmation_events` Firestore
  collection; set in `deploy-all.sh`'s `BACKEND_ENV` because the file-only
  trail dies with the Cloud Run instance. Optional
  `CONFIRMATION_RETENTION_DAYS` stamps an `expire_at` for a TTL policy;
  `CONFIRMATION_LOG_DIR` still points the local JSONL (dev). See
  [../standards/confirmation-and-audit.md](../standards/confirmation-and-audit.md).
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
- **`EXTRACTOR_MODEL` / `EXTRACTOR_TIMEOUT_SEC` / `EXTRACTOR_MAX_PDF_MB`** — the
  hosted PDF->schema extraction knobs (bd `polyglot-pdf-92qe.3`, author tier).
  `EXTRACTOR_MODEL` defaults to `gemini-2.5-pro` and MUST be a `gemini-*` model
  on Cloud Run (the container has no `claude` CLI; authoring is one-off per form
  so quality beats per-call cost). Extraction runs
  `scripts/authoring/extract_form.py` as a subprocess — the image is built from
  the REPO ROOT (`Dockerfile` at the root; `backend/Dockerfile` is gone) so
  `scripts/authoring` + `scripts/bakeoff` ship in it; `.gcloudignore` keeps the
  Cloud Build upload lean. Needs `GEMINI_API_KEY` mounted (Secret Manager).
- **`OPTION_TRANSLATION_MODEL`** — the authoring-time option-label translation
  model (bd `polyglot-pdf-2h9j`; default `gemini-2.5-pro`, same one-off-per-form
  rationale). Read by the extraction post-pass (skippable via the extract
  request's `translate_options` flag / editor checkbox), the standalone
  `POST /api/editor/kits/{id}/translate-options` route, and
  `scripts/authoring/translate_option_labels.py`. Tier detail in
  [../standards/ai-models.md](../standards/ai-models.md).
- **`GENAI_WEBSOCKET_BASE`** — optional override of the genai SDK's Live WebSocket
  base (`backend/adapters/live_ai_gemini.py`), for pointing at a non-default
  endpoint.

> The legacy env doc (`ENV_VARIABLES.md`, now archived at
> [`../archive/ENV_VARIABLES.md`](../archive/ENV_VARIABLES.md)) is superseded by this
> doc; it predates the `.env.DEV` marker mechanism and describes `VFF_DEV_LOGGING` as the
> dev-logging switch. **`VFF_DEV_LOGGING` is dead config:** no code reads it (the
> only remaining reference is a stale comment in `callback_handler.py:194`); the
> real gate is the `.env.DEV` marker above. The comment at
> `callback_handler.py:445-448` already documents this correctly (it explicitly
> calls out `VFF_DEV_LOGGING` as dead config) -- fixed under bd `polyglot-pdf-jpe`.

## Deployment (local/manual — no CI)

Two Firebase/GCP projects, both running a Cloud Run service named
**`polyglot-backend`** in **`us-central1`**. Aliases live in `.firebaserc`:

| Channel | Project ID | Script | Frontend URL |
|---------|-----------|--------|--------------|
| **demo** | `polyglot-demo-aa709` | `deploy-demo.sh` | `https://polyglot-demo-aa709.web.app` |
| **production** | `polyglot-forms-919f2` (`.firebaserc` `default`/`prod`) | `deploy-production.sh` | `https://polyglot-forms-919f2.web.app` |

Both delegate to **`deploy-all.sh`** (`--backend`, `--form-kits`, `--frontend`
stages). `backend/deploy-new.sh` is a separate, one-off script for bootstrapping
a brand-new Cloud Run service by name -- not part of the regular update flow the
two channel scripts use.

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
  → `.env.demo`). Output `frontend/dist` → `firebase deploy --only hosting:app`. The
  bare `npm run build` is NOT used: it loads `.env.production` under the default
  Vite config, whose Firebase keys differ per channel — a demo built that way dies
  with `auth/invalid-api-key`. **Backend WS URL is resolved at deploy time** (bd
  `emm7`): before the build, `deploy-all.sh` resolves the live Cloud Run URL
  (`gcloud run services describe polyglot-backend --format 'value(status.url)'`)
  and exports `VITE_WS_URL` (which OVERRIDES the `.env.<mode>` `VITE_WS_URL` line —
  standard Vite precedence). The `VITE_WS_URL` values committed in `.env.demo` /
  `.env.production` are now documented FALLBACK-ONLY, because the Cloud Run auto-URL
  hash is not stable (it drifted on a service recreate and 404'd the deployed
  frontend).
- **Firestore rules** — `firebase deploy --only firestore:rules` ships
  `firestore.rules` (wired via `firebase.json`). This step lives in the
  **`deploy-demo.sh` / `deploy-production.sh` wrappers**, not `deploy-all.sh`, runs
  only on a frontend/full deploy, and runs **before** the frontend so the new
  frontend never goes live against stale rules. A project left on default-deny
  breaks email signup (the unauth `authorized_emails` read) and the `users/{uid}`
  profile sync -- see [auth.md](auth.md).

### Hosted schema editor (second Hosting site)

`firebase.json` `hosting` is an ARRAY of two named targets (bd `92qe.4`):
`app` (the voice app, `frontend/dist`, keeps its `/api` rewrite) and `editor`
(`schema-editor/dist`, SPA catch-all, **no** `/api` rewrite -- the editor calls
Cloud Run directly via `VITE_API_BASE_URL`; the Hosting rewrite's 60s cap would
kill minutes-long extraction). `.firebaserc` maps `editor` ->
`polyglot-editor-demo` on the demo project. **Because targets are named, a bare
`firebase deploy --only hosting` deploys BOTH sites** -- `deploy-all.sh` is
pinned to `--only hosting:app`, the `frontend/package.json` `deploy` /
`deploy:demo` shortcuts are pinned too (the unscoped prod one would
otherwise THROW -- prod maps no `editor` target -- and the demo one would
silently ship a stale editor build), and the editor ships only via
**`deploy-editor.sh`** (`npm run build:hosted` + `--only hosting:editor`; its
header is the one-time runbook: site create, `target:apply`, the two
access-code secrets attached once to Cloud Run with `--set-secrets`, and the
bucket `roles/storage.objectAdmin` grant the editor's writes need).
`deploy-editor.sh` also **resolves the live Cloud Run URL at deploy time** and
exports `VITE_API_BASE_URL` (overriding the `.env.hosted` fallback), same as the
voice app -- a committed hash there once drifted on a service recreate and made
every access-code entry hit a 404'd backend, looking like a wrong password (bd
`emm7`).
`deploy-demo.sh` carries `EXTRACTOR_MODEL` + `CORS_EXTRA_ORIGINS`
(SEMICOLON-separated origins -- commas are `--set-env-vars`' pair separator)
via `BACKEND_EXTRA_ENV`; the backend deploy runs `--memory=1Gi` (extraction
holds PDFs in memory + tmpfs). **Contractor round trip:**
`scripts/pull-form-kits.sh` rsyncs bucket kits DOWN into `form-kits/`
(index.json excluded; local-only kits preserved) so contractor work is
git-reviewable before the normal deploy republishes -- without it, a
bucket-only kit silently drops from the manifest on the next deploy.

### Frontend → backend wiring

`firebase.json` rewrites **`/api/**` → the `polyglot-backend` Cloud Run service**
(this is how the stateless PDF-fill HTTP call reaches the backend through Hosting),
plus a catch-all `** → /index.html` for SPA routing.

**WebSockets do NOT go through the Hosting rewrite** (Firebase Hosting can't proxy
WS). `frontend/src/shared/config.ts` `getBackendUrl()` resolves the WS URL in this
order: (1) local-dev override (`window.__VFF_LOCAL_DEV` → `window.__VFF_BACKEND_URL`,
default `ws://localhost:8000/ws/fill`); (2) `VITE_WS_URL` env var — **this is the
real production path**: the deploy injects the live Cloud Run URL here at build time
(bd `emm7`), so a deployed bundle carries the resolved URL, not a baked literal;
(3) a hardcoded `PRODUCTION_WS_URL` constant in `config.ts` when the page is HTTPS
and not localhost — a **stale last-resort fallback** (it still holds an old
`d3mhrrkwfq` hash that 404s; it only fires if `VITE_WS_URL` was somehow unset at
build, which the deploy no longer allows); (4) dev fallback `ws://localhost:8000/ws/fill`.
The `__VFF_*` dev overrides are read from `window` OR `localStorage` (so they
survive a reload). `config.ts` also exposes `isTestHarnessEnabled()` (true only
when both `__VFF_LOCAL_DEV` and `__VFF_TEST_HARNESS` are set) — a dev/test-only
gate used by the E2E voice harness; never true in production.

> **Promotion path** is worktree → local test server → `dev` → demo remote
> (`deploy-demo.sh`); deploys stay manual (local shell scripts, not CI) and there
> is **no active prod**. The agent may run the demo deploy under a three-part gate
> (local-test-first + per-instance permission + post-deploy test-drive). See
> [../doctrine/promotion-tiers.md](../doctrine/promotion-tiers.md).
