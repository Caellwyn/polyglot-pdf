# Config & deployment

**Tracks:** backend/config.py backend/main.py admin_backend/main.py admin_backend/services/admin_auth.py admin_backend/services/audit_log.py admin_backend/services/promotion_gate.py admin_backend/routes/whoami.py admin_backend/routes/config_routes.py admin_backend/routes/audit_routes.py scripts/bootstrap_admin_user.py backend/utils/dev_file_logger.py backend/services/callback_handler.py Dockerfile .gcloudignore cloudbuild.yaml deploy/channels/ scripts/deploy_preflight.sh scripts/setup-cloud-build.sh scripts/record_build_check.py scripts/record_deployment.py scripts/promotion_gate.py scripts/verify_service_reachable.py scripts/deploy_build_targets.sh scripts/write_kits_manifest.py scripts/audit/infra_posture.sh deploy-all.sh deploy-admin.sh deploy-admin-console.sh deploy-editor.sh deploy-demo.sh deploy-staging.sh deploy-production.sh backend/deploy-new.sh firebase.json .firebaserc admin-console/ frontend/src/shared/config.ts firestore.rules frontend/vite.config.schema.ts

*Last updated: 2026-09-16 (bd polyglot-pdf-oqtm7 outer cross-surface review round 4: the ONE ENGINE claim is scoped to the `deploy-*.sh` wrappers and the admin console, and the two surviving LOCAL engines -- `npm run deploy:demo` and `scripts/deploy-form-kit.sh` -- are named as the ungated exceptions (bd polyglot-pdf-1qzr8 owns their fate); `--set-secrets` no longer claims a caller-side `BACKEND_SECRETS` override, which the bash engine took with it.) (bd polyglot-pdf-oqtm7 outer cross-surface review round 3: the form-kits rows say what the target actually does -- it reads the BUILD's checkout, no kit is tracked there, so it cannot succeed and no wrapper selects it implicitly any more (bd polyglot-pdf-wm7ga owns the source question); the contractor round-trip note no longer claims a local pull feeds the next deploy.) (bd polyglot-pdf-oqtm7 outer cross-surface review round 2: the post-deploy reachability check is named by its module, `scripts/verify_service_reachable.py` -- the `verify_service_publicly_reachable()` bash function it replaced no longer exists in any file.) (bd polyglot-pdf-oqtm7 outer cross-surface review round: the Cloud Build SA's role list gains `roles/datastore.indexAdmin` -- the `firestore-rules` target's index half is not covered by `roles/firebaserules.admin` (rules only) or by `roles/datastore.user` (read only).) (bd polyglot-pdf-oqtm7, E4.6: every `deploy-*.sh` is
now a THIN wrapper that runs Cloud Build triggers -- the inline `gcloud run
deploy` / `firebase deploy` / `gcloud builds submit --tag` stages are deleted,
and `scripts/deploy_build_targets.sh` is the shared runner. `deploy-all.sh`
keeps a sourced helper half (the channel-file parser `cloudbuild.yaml` uses).
Two behaviours moved rather than being lost: the `firestore-rules` target now
ships the composite INDEXES alongside the rules, and
`deploy/channels/admin.env` gains `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL`, which
previously reached the service only through `deploy-admin.sh`'s inline env
assembly.)*

*Last updated: 2026-09-16 (bd polyglot-pdf-bwevj, sprint 23 C2: the access-log paragraph -- the credential left the URL; the flag stays load-bearing through the one-deploy deprecation; `deploy/channels/*.env` CORS lists gained the voice app's Hosting origins for the socket's Origin check.)*

*Last updated: 2026-09-16 (bd polyglot-pdf-j29z1, sprint 23 E2: the "Hosting security headers" section -- one header block on all five Hosting targets, the CSP in report-only mode with its connect-src inventory, and self-hosted fonts via scripts/fetch_fonts.py.)*

*Last updated: 2026-09-16 (bd polyglot-pdf-wfgjz, sprint 23 B1a: the "Deployed verbosity floors" bullet -- LOG_LEVEL clamped to INFO, the two dump knobs forced off, SEND_TRANSCRIPT ignored and the token file unwritten with K_SERVICE set; both apps install the value-free 422 handler from backend/utils/validation_errors.py at import.)*

*Last updated: 2026-09-15 (bd polyglot-pdf-ikdnd, sprint 23 F1: the root `Dockerfile` pins `python:3.12-slim` by digest, creates the non-root `app` user (uid 10001) that owns `/app/backend/logs` and `/app/logs/confirmations` before `USER app`, and installs `backend/requirements.txt` alone -- test tooling now lives in `backend/requirements-dev.txt`, which `cloudbuild.yaml`'s verify target installs. Pinned by `tests/test_dockerfile_app_module.py` and `tests/test_ci_security_job.py`.)*

*Last updated: 2026-09-15 (bd polyglot-pdf-3bsyv: `frontend/vite.config.schema.ts`'s
`base` is now `'/'` (absolute), not `'./'` -- see "Asset base MUST be
absolute" under Frontend deploy below. No env var or deploy step changed.)*

*Last updated: 2026-09-15 (bd polyglot-pdf-m1dlv, sprint 23 workstream D: new `scripts/audit/infra_posture.sh` -- a read-only, operator-run runbook that verifies the live `polyglot-demo-aa709` project against this doc and the offline IAM pins in `test_deployed_iam_envelope.py`/`test_admin_sa_iam_envelope.py`. No env var, deploy step, or config key changed; see "Live infrastructure posture (read-only)" below.)*

*Last updated: 2026-09-16 (bd polyglot-pdf-jub5f, E4.4: the staging-before-demo
promotion gate is finished end to end -- `admin_backend/services/
promotion_gate.py::staging_verified` is the one pure predicate,
`scripts/promotion_gate.py` is the build-step CLI `cloudbuild.yaml`'s
`staging-verified-gate`/`admin-service-staging-gate` steps call, and
`POST /admin/deploys` calls the same predicate for its own early refusal.
Full explanation, including the no-recency decision and why the admin
service is excluded from the route's early check, lives in
[`../doctrine/promotion-tiers.md`](../doctrine/promotion-tiers.md#the-staging-before-demo-promotion-gate)
rather than duplicated here. No config key or env var changed.)*


How the backend is configured (settings, feature flags, env vars) and how both
surfaces ship. Config lives in `backend/config.py` (`Settings`, a pydantic
`BaseModel`); deployment runs on **Cloud Build, from a pushed commit** — the
`deploy-*.sh` scripts are thin wrappers that start a build, and the admin console
starts the same builds. The two AI-model env vars surface here, but the canonical model
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
  `USE_DTI`, `SECRETARY_TIMEOUT_S`,
  `FORM_KITS_MODE`, `FORM_KITS_LOCAL_ROOT`, `FORM_KITS_GCS_BUCKET`,
  `FORM_KITS_REMOTE_PREFIX`,
  `CORS_EXTRA_ORIGINS`, `EXTRACTOR_MODEL`, `EXTRACTOR_TIMEOUT_SEC`,
  `EXTRACTOR_MAX_PDF_MB`, `RESUME_FORM_PARSE_TIMEOUT_S` (default `8.0` --
  wall-clock cap on `/api/resume-form`'s `fitz.open` + structural-comparison
  parse, run in a thread so the cap can actually interrupt it; see
  [pdf-filling.md](pdf-filling.md)).
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
| `SPELLBACK_TOOL_ENABLED` | `true` | Deterministic spell-back verification clip (bd 22h1f/44ywm): declares the `name_spellback` tool, appends the DTI spell-back addendum to the SI, and un-503s `POST /api/tts/spellback`. See [voice-ai.md](voice-ai.md) and the routes table in [../technical_guide.md](../technical_guide.md). |
| `INTRO_TTS_ENABLED` | `false` | Sol's scripted intro+disclaimer clip (sprint 20, bd s1iex.3): un-503s `POST /api/tts/intro`. The BACKEND half of the epic's two-flag design -- the frontend flag is `VITE_INTRO_CLIP_ENABLED` (below), and the two can skew across the two-surface deploy (skew matrix in `docs/sprint_20_sol-intro-tts_plan.md`; deploy backend first, frontend second). |

**Frontend build-time flag (not a `Settings` field).**
`VITE_INTRO_CLIP_ENABLED` (default off; `frontend/src/shared/config.ts`
`isIntroClipEnabled()`, bd `polyglot-pdf-s1iex.5`) is the CLIENT half of that
pair. It cannot be a backend flag delivered in `session_ready` the way
`jit_mode_enabled` is, because it decides whether the client connects
**before Agree at all** -- a decision made before any connection exists. It gates the AUDIO only. ON,
the modal plays the synthesized clip; OFF, the model reads the disclaimer via
`read_disclaimer`. It does NOT gate the disclaimer TEXT: since bd
`polyglot-pdf-nsb4y` the modal renders the canonical scripted paragraphs
UNCONDITIONALLY, and the model-read path speaks those same paragraphs, so a
reader and a listener accept identical terms in either state. (The flag used
to gate the text too, which put the advisory `p1/p2/p3` on screen while the
clip spoke an undertaking -- two legal registers behind one Agree button.) A window/localStorage override
(`__VFF_INTRO_CLIP`) exists for manual testing; unlike `isTestHarnessEnabled`
it is **not** localhost-gated, because it gates no security-sensitive path.
The ON/OFF skew quadrant (modal renders, route 503s, no audio, Agree still
connects, and NO fallback to `read_disclaimer`) is pinned by
`frontend/src/demo/introFlagQuadrant.test.ts`.

## Form-kit storage (`FORM_KITS_MODE`)

The schema+PDF store backing PDF fill ([pdf-filling.md](pdf-filling.md)):

- **`local`** (default, local dev) — reads `<FORM_KITS_LOCAL_ROOT>/<kit_id>/`;
  `FORM_KITS_LOCAL_ROOT` defaults to `<repo>/form-kits`.
- **`gcs`** (what deploys use) — reads
  `gs://<FORM_KITS_GCS_BUCKET>/<FORM_KITS_REMOTE_PREFIX>/<kit_id>/...`. The
  `--set-env-vars` that pins `FORM_KITS_MODE=gcs` + the bucket is computed by
  **`cloudbuild.yaml`'s `backend-deploy` step** (and its `admin-service`
  sibling), not by any wrapper.

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
  the Vertex path, which is what the demo runs. A credential belongs in **Secret
  Manager**, never in a plaintext env var — but note this key is **not bound by
  any deploy script today**: `--set-secrets` existed only in comments until bd
  `polyglot-pdf-hvui4`, and the channel files bind `LINK_TOKEN_SECRET`
  alone. Add it to the `[SET_SECRETS]` section of BOTH
  `deploy/channels/staging.env` and `deploy/channels/demo.env` if a channel
  ever needs the AI Studio path -- the parity test requires the two secret
  lists to be identical.
- **`backend/.env.DEV` marker file** — this **file's existence** (NOT an env var)
  flips `DEV_LOGGING_ENABLED` in `backend/utils/dev_file_logger.py`, which is the
  **single gate** for *both* dev-logging paths: the `DevFileLogger` itself **and**
  the field-value `_dev_log` calls in `backend/services/callback_handler.py`
  (`_dev_log` is just `get_dev_logger()`, whose `enabled` is `DEV_LOGGING_ENABLED`).
  Present only in local dev (gitignored + dockerignored), so prod never logs
  PII/PHI. The marker is looked for at exactly one location — `backend/.env.DEV`,
  resolved from `dev_file_logger.py`'s own `__file__`, **not** the process cwd —
  so whether dev logging turns on never depends on which directory the backend
  was launched from (bd `polyglot-pdf-b5nmq`; the local launchers now start
  uvicorn from `backend/` to scope its reload watch). The same applies to where
  the logs are written: `DevFileLogger`'s `log_dir` and the `live_ai_gemini`
  debug dumps resolve against the repo root via `__file__`, so they land in
  `backend/logs/` regardless of cwd. This is the HIPAA guard — see
  [hipaa-pii-policy.md](../standards/hipaa-pii-policy.md) and bd `polyglot-pdf-hjo`.
- **`VFF_DISABLE_AUTH=true`** — dev bypass for Firebase token verification
  (`backend/services/auth.py`); returns a stub `dev_user`. Covers BOTH the
  `/ws/fill` gate and the bd-z2is HTTP gates (`require_auth` on
  `/api/fill-pdf`, the client resume upload `/api/resume-form` and the free
  safety-notice speech `/api/tts/notice`
  (bd `polyglot-pdf-dft1`), the archived-revision
  reads `/api/form-kits/{kit_id}/archive` + `.../archive/{marker}/schema`
  (bd `polyglot-pdf-qfyxr`), the firm retire write path
  `POST /api/form-kits/{kit_id}/retire` (bd `polyglot-pdf-z6bk9`), and both TTS routes
  `/api/tts/spellback` + `/api/tts/intro`; plus `require_signin` on the
  form-kit list/schema reads, which need a valid sign-in but NOT voice-app
  enrolment -- selecting a form is how the app is used, so it must stay
  reachable for a magic-link user with no firm claim). **LOCAL ONLY, fail-closed on
  deploy** (bd `polyglot-pdf-knmp`): with `K_SERVICE` set, `Settings` refuses
  to start and `verify_token` ignores the flag — no override exists. Auth
  canon: [auth.md](auth.md).
- **Vertex is the ONLY production path** (maintainer directive 2026-08-04, bd
  `polyglot-pdf-5e6a`). `VERTEXAI=false` on a DEPLOYED service (`K_SERVICE`
  present ⇒ Cloud Run) makes `Settings` fail startup, and there is **no
  override flag** — the former `ALLOW_AI_STUDIO` acknowledgment was removed
  because no legitimate deployed AI Studio use exists. Only Vertex's privacy
  agreement keeps client data out of Google's model training. AI Studio is
  permitted **locally only** (no `K_SERVICE`), for testing a model before it
  reaches Vertex GA. See [../standards/ai-models.md](../standards/ai-models.md).
- **Deployed verbosity floors** (bd `polyglot-pdf-wfgjz`, sprint 23 B1a). With
  `K_SERVICE` set, no env knob can raise log volume into payload territory:
  `LOG_LEVEL` below INFO is clamped to INFO by `configure_logging`;
  `LIVE_DEV_TRANSCRIPTS` / `LIVE_DEV_AUDIO_DUMP` are forced off by `Settings`;
  the `SEND_TRANSCRIPT` harness knob in `websocket_routes.py` is ignored; and
  `backend/logs/token_usage.jsonl` is never written. All four stay free
  locally (no `K_SERVICE`). Pinned by `backend/tests/unit/test_deployed_verbosity_floor.py`
  and `test_token_usage_local_only.py`.
- **`CONFIRMATION_FIRESTORE_ENABLED=true`** — mirrors the confirmation audit
  trail (metadata only, never values) to the `confirmation_events` Firestore
  collection; set in the build's `BACKEND_ENV` because the file-only
  trail dies with the Cloud Run instance. Optional
  `CONFIRMATION_RETENTION_DAYS` stamps an `expire_at` for a TTL policy;
  `CONFIRMATION_LOG_DIR` still points the local JSONL (dev). See
  [../standards/confirmation-and-audit.md](../standards/confirmation-and-audit.md).
- **`FIRMS_FIRESTORE_ENABLED=true`** — enables the firms-store READ path
  (`backend/services/firms.py`, bd `polyglot-pdf-lo88`): the `firms/{firm_id}`
  Firestore collection holding firm profiles + allowed-kits, consumed by the
  form-kit routes' firm-scoped visibility filter (bd `polyglot-pdf-vccy`).
  Set in the build's `BACKEND_ENV`; the `deploy-form-kit.sh` drop-list
  hint names it and `tests/test_deploy_form_kit_hints.py` pins that
  enumeration. Reads fail CLOSED (`[]`) when unset or broken, so an outage
  hides private kits rather than exposing them. Firm records are created by
  `scripts/bootstrap_firm.py`; see [auth.md](auth.md) (Firm identity).
- **CLIENT MAGIC LINKS (bd `polyglot-pdf-ugm6`) -- FOUR variables, and a
  partial configuration is the hazard.** A live link is an unauthenticated
  door to a paid Gemini session, so read all four together:
  - **`LINK_MINTING_ENABLED`** — THE INTERLOCK. `POST /api/links/mint` 404s
    while it resolves false, which is the default anywhere it has never been
    set. What it guarded -- the per-jti/per-firm limits and the session cost
    ceiling (bd `polyglot-pdf-ik7e`) -- **has shipped**, so enabling it is
    legitimate wherever the ceiling is enforced.
    **This is now a RUNTIME setting (bd `polyglot-pdf-bg313`), read at CALL
    TIME.** `LINK_MINTING_ENABLED` -- along with `LINK_COST_CEILING_USD` and
    `LINK_FIRM_CAP` -- resolves through `app_config/{channel}` in Firestore
    (`backend/services/runtime_config.py`, TTL-cached), with the deploy-time
    environment variable of the SAME name as the fallback for a channel that
    has never had a value written to Firestore (or is mid-blip): if the
    Firestore doc has no value and nothing was ever read successfully on this
    process, `runtime_config.py` reads `os.getenv("LINK_MINTING_ENABLED")`
    itself, parsed the same way the pre-bg313 call site parsed it, before
    falling back further to the compiled `false`. `deploy/channels/demo.env`
    and `deploy/channels/staging.env` still carry `LINK_MINTING_ENABLED=true`
    in `[SET_ENV_VARS]` (predating bg313) and that line is exactly what keeps
    a freshly deployed process minting-enabled with no `app_config/{channel}`
    doc seeded yet -- an operator can override it per channel either through
    the admin service's `PUT /admin/config/{channel}` (bd
    `polyglot-pdf-li9x0`), which validates the key and the value before
    writing and records the change in the audit log inside the SAME Firestore
    transaction, or with `scripts/set_runtime_config.py`, the un-audited
    break-glass CLI that needs no deployed admin service. See
    [`technical_guide.md`](../technical_guide.md) contract 14 for the full
    fallback order and call-site details. The GLOBAL `LINK_COST_CEILING_USD`
    is runtime-config-backed; the ceiling actually in force at a client
    connect is the signed link token's own `cap_usd` claim when present,
    else that global (`link_budget.cost_ceiling_usd_for_claims`, bd
    `polyglot-pdf-ah5d3` / Epic 2 A4, closing `polyglot-pdf-4tjt7`) -- the
    socket now passes the resolved ceiling into `check_budget`. A kit's own
    `link_cost_ceiling_usd` reaches a token's `cap_usd` only once Epic 2 bead
    A3's mint-time resolve lands, so per-form caps stay bounded by the global
    until then.
  - **`LINK_TOKEN_SECRET`** — the HMAC signing key (>=32 chars). Fails CLOSED
    and loudly: minting and verification both refuse without it, deliberately
    rather than defaulting (a default key would be forgeable by anyone
    reading the source; a per-process random one would silently kill every
    outstanding link on each restart, stranding a client mid-intake).
    **Rotating it invalidates every unopened link**, so rotate only with that
    understood.
  - **`LINK_CHANNEL`** — which channel this backend is (`demo` / `staging`).
    Minted into every token as the `aud` claim and checked on open, so a
    staging-minted link is refused on the demo and vice versa (bd
    `polyglot-pdf-3q9qn`); it also selects the redemption collection
    (`link_redemptions` for the demo, `link_redemptions_<channel>` elsewhere),
    so the two channels cannot burn each other's links. Defaults to `demo` —
    the safe side, since an unconfigured deploy then behaves exactly as
    before — but both deploy scripts set it explicitly. **Renaming a channel
    orphans its redemption ledger and invalidates its outstanding links.**
    Note the BILLING counter is firm-scoped, not channel-scoped: staging must
    also use its own mock firm (`scripts/bootstrap_firm.py`) or it bills the
    real one.
  - **`LINK_BASE_URL`** — origin the minted URL points at (e.g.
    `https://forms.example.com`; the route appends `/f#t=<token>`).
    Configured, never derived from the Host header -- trusting the header
    would let a caller mint links pointing at a domain THEY control while
    carrying our valid signature. Minting 503s when unset.
  - **`LINK_REDEMPTIONS_FIRESTORE_ENABLED=true`** — the `link_redemptions`
    collection enforcing ONE completion per link. Fails CLOSED by REFUSING
    THE OPEN (note the opposite polarity to the firms read, which fails
    closed by returning an empty list): unable to confirm a link is
    unredeemed, we must not admit it, because the failure being guarded is a
    replayed link starting a second paid session.

  The token rides in the URL FRAGMENT so it never reaches access, referrer,
  or proxy logs. See [auth.md](auth.md) (Client magic links).

  **Per-SESSION cost, for whoever sizes bd `polyglot-pdf-ik7e`.** The socket
  redeems once per CONNECTION. Under the shipped default
  (`CONTINUOUS_SESSION=true`) that is roughly ONE read per session, not one
  per section -- an earlier version of this note said ~27 for an I-90 and was
  wrong by that factor. Reconnects (the 120s idle timeout, network drops)
  each add one; a deployment running `CONTINUOUS_SESSION=false` reverts to
  per-section connects and the count rises accordingly.

  Per client HTTP request, additionally: ONE uncached Firestore READ -- the
  firm-allowlist read, whenever the visibility gate fires on a private kit.
  `require_auth` does NOT redeem (retrieval must not burn the client's own
  document), so it costs no redemption read. The redemption WRITES belong to
  the paid doors: **TWO on the first open of a link** (`open_link` creates
  the redemption record, then the usage-rollup helper adds a second write to
  the firm-month doc's `links_opened` counter -- bd `polyglot-pdf-w828m`),
  and on **session completion**, **one READ plus two WRITES**
  (`complete_link` updates the redemption record, reads it back for the
  rollup's firm_id, then writes `links_completed`). Every connection
  teardown adds its own **one READ plus one-or-two WRITES** regardless of
  whether the link was ever opened (`firm_kind()`'s read, plus
  `record_session_end`'s batched commit -- one write when there is no
  kit_id, two when there is). Writes cost more than reads, so size from the
  full set above, not from the redemption reads alone. None of it is
  cached, deliberately: caching a revocation check reopens the replay
  window the redemption gate closes.
- **The `/api/editor/*` surface takes NO shared secret.** Access is per-person:
  a Firebase ID token on `Authorization: Bearer`, carrying this surface's own
  `schema_editor_role` claim (`backend/services/editor_auth.py`, bd
  `polyglot-pdf-hn0jq`). The two tiers survive as claim VALUES -- *editor* =
  polish provided kits; *author* = editor + PDF onboarding/hosted extraction --
  but they are granted per account with `scripts/bootstrap_editor_user.py`, not
  handed out as codes. There is no env var to set and no 503 fail-closed state:
  the surface is always on, and an unlisted account gets 403. The former
  `SCHEMA_EDITOR_TOKEN` / `SCHEMA_AUTHOR_TOKEN` are deleted (bd
  `polyglot-pdf-rhc2v`); if either is still attached to a deployed service, it
  is inert and can be dropped at the next deploy.
- **`CORS_EXTRA_ORIGINS`** — semicolon- (or comma-) separated extra browser
  origins appended to the local dev list (`backend/config.py`
  `LOCAL_BROWSER_ORIGINS`; `browser_origins()` is the ONE list `main.py`'s CORS
  middleware AND `/ws/fill`'s Origin allowlist use, sprint 23 C2). It must name
  the hosted schema-editor site (which calls Cloud Run directly rather than
  through the Hosting `/api` rewrite — the rewrite's 60s cap would kill
  minutes-long extraction requests) AND the channel's own voice-app Hosting
  site (the WebSocket is opened from it directly; a missing app origin refuses
  every voice session with "Origin not allowed"). Each channel names its own
  app site only; `deploy/channels/*.env` carry the values, pinned by
  `backend/tests/unit/test_ws_first_frame_credential.py`.
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
  `scripts/authoring` + `scripts/bakeoff` ship in it, alongside `backend/` and
  `admin_backend/`; `.gcloudignore` keeps the Cloud Build upload lean. Needs `GEMINI_API_KEY` on the AI Studio path — which
  no deploy script binds today (`--set-secrets` carries `LINK_TOKEN_SECRET`
  alone); the deployed channels run Vertex, where the key is unused.
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
> dev-logging switch. **`VFF_DEV_LOGGING` is dead config:** no code reads it, and
> the real gate is the `.env.DEV` marker above. The one surviving mention is the
> "LOGGING POLICY" comment inside `callback_handler.py`'s `on_tool_call`,
> which documents this correctly (it explicitly calls out `VFF_DEV_LOGGING`
> as dead config and points back here).

## Rate limiting on the unauthenticated doors (sprint 23 PF-5, bd `polyglot-pdf-o2fub`)

Two controls, decided by the maintainer on 2026-09-17 with Cloud Armor deferred
until abuse is observed:

- **A per-instance limiter** (`backend/utils/rate_limit.py`) on the three
  unauthenticated write doors: `POST /api/links/open`, `POST /api/signup/check`
  and `POST /api/disclaimer-acceptance`. Two token buckets per door, both
  keyed from the END of the `X-Forwarded-For` chain (a caller can seed the
  front of that list; every proxy appends the address it saw, so only the
  tail is trustworthy). In production every browser call reaches Cloud Run
  through the Hosting `/api/**` rewrite, so the chain ends
  `..., browser, hosting-egress`; a direct call to the run.app host ends
  `..., caller`. The CLIENT bucket is keyed on the last two hops
  (`RATE_LIMIT_BUDGET`, default 30, per `RATE_LIMIT_WINDOW_SEC`, default 60):
  per browser through Hosting, unforgeable by the browser. The CONNECTION
  bucket is keyed on the last hop alone (`RATE_LIMIT_SHARED_BUDGET`, default
  600): shared by everyone behind one Hosting egress, and the backstop that
  caps a direct caller who rotates forged hops. A call the client bucket
  refuses never draws on the connection bucket, so one abuser behind
  Hosting cannot drain it for everyone. `RATE_LIMIT_ENABLED=false` turns the
  limiter off (the test suite does). The per-door maps are LRU-bounded.
  An over-budget caller on the two oracle-sensitive doors gets the door's own
  404 phrase, byte-identical to a wrong token or a miss; on the disclaimer door
  a plain 429. The refusal log line (`rate_limited`) carries the door and the
  budget, never the address. Pinned by `backend/tests/unit/test_rate_limit.py`,
  whose set test derives the door list from the access matrix's deliberately-
  ungated routes so a new unauthenticated write door fails CI until it is
  limited. Known weakness, accepted in the decision: the bucket lives in one
  instance, resets on autoscale, and a distributed caller spreads around it.
- **A spend ceiling**: `--max-instances=10` on the backend deploys and
  `--max-instances=3` on the admin service in `cloudbuild.yaml`, pinned by
  `tests/test_cloudbuild_yaml.py`. A ceiling is not a limiter -- it bounds the
  worst-case bill, not one abuser -- but with the limiter above it closes the
  unbounded-cost hole.

## Deployment (Cloud Build, from a pushed commit)

**ONE ENGINE behind the `deploy-*.sh` wrappers and the admin console.** Every
deploy started from either of those is a Cloud Build build of `cloudbuild.yaml`
at an explicit commit, selected by the `_TARGET` substitution, started through a
manual trigger named `polyglot-<target>`. The wrappers and the console are two
ways to press the same button; neither builds or deploys locally any more. What
that buys: the gates live in the BUILD, so neither of those two routes can skip
them. The per-SHA `verify` record, the reachability check, the kits manifest
validation and the staging-before-demo promotion gate are all build steps -- a
bash-started build is gated exactly like a console-started one.

**Two LOCAL engines survive outside that, and they are NOT gated.** Read the
paragraph above as a statement about the wrappers and the console, not about
the repo as a whole:

- `frontend/package.json`'s `npm run deploy:demo` (and `npm run deploy`, aimed
  at the dead prod project) still runs `firebase deploy --only hosting:app`
  against the DEMO Hosting site from whatever is in the working tree. It skips
  `scripts/deploy_preflight.sh`'s dirty/unpushed refusal, the per-SHA `verify`
  record, the staging-before-demo gate, the `deployments` row, and the build's
  live `VITE_WS_URL` / `VITE_APP_CHANNEL` injection.
- `scripts/deploy-form-kit.sh` uploads kits straight into the shared,
  project-wide form-kits bucket with no build and no gate. It is currently the
  only working kit-publish path (the `form-kits` build target reads
  `form-kits/` from git, where no kit is tracked -- bd `polyglot-pdf-wm7ga`).

Whether these are removed, made to refuse, or kept as sanctioned exceptions is
decided for all three sites together in bd `polyglot-pdf-1qzr8` (open). Until then,
prefer the wrappers or the console for anything that reaches a live surface.

**Running a wrapper is still a maintainer-gated deploy.** Only the engine
changed: each wrapper keeps its flags and still needs its own per-instance
"yes" before it is run (CLAUDE.md "Deployment / promotion").

**Two LIVE channels, one project.** Both run in `polyglot-demo-aa709` in
**`us-central1`**, separated by Cloud Run SERVICE and Hosting SITE (bd
`polyglot-pdf-9qn64`). Aliases and target mappings live in `.firebaserc`:

| Channel | Cloud Run service | Hosting target -> site | Script | Frontend URL |
|---------|-------------------|------------------------|--------|--------------|
| **staging** (test deploy) | `polyglot-backend-staging` | `app-staging` -> `polyglot-app-staging` | `deploy-staging.sh` | `https://polyglot-app-staging.web.app` |
| **demo** (protected) | `polyglot-backend` | `app` -> `polyglot-demo-aa709` | `deploy-demo.sh` | `https://polyglot-demo-aa709.web.app` |

Staging is the disposable target for finding deploy-only bugs; the demo is what
investors and pilot firms see. Promote staging -> demo, never straight to demo.
The two SHARE the project, form-kits bucket, Firestore, and Auth user pool, so
staging isolates broken CODE, not bad DATA -- see
[../doctrine/promotion-tiers.md](../doctrine/promotion-tiers.md).

**`production` is DEAD.** `deploy-production.sh` targets `polyglot-forms-919f2`,
which is unreachable -- bd `polyglot-pdf-je6iy`. The script now refuses to run.
`.firebaserc` no longer carries a `default` or `prod` alias for it (bd
`polyglot-pdf-xsp5b`): they were REMOVED rather than repointed, so a `firebase`
command with no `--project` now errors instead of silently resolving to a dead
project -- and is not quietly aimed at the live demo either. Every scripted
`firebase` call passes `--project` explicitly, so nothing depends on an alias.

**What each wrapper runs** (bd `polyglot-pdf-oqtm7`, 4.6). Every one refuses a
dirty or unpushed tree, then runs its targets' triggers in order at
`git rev-parse HEAD`, streams each build's log, and exits non-zero on the first
failed build. `scripts/deploy_build_targets.sh` is the whole bash side --
`run_build_target` starts one trigger and reads the build's FINAL STATUS from
`gcloud builds describe` (never the log reader's exit code), and
`run_build_targets` runs a list and stops at the first failure.

| Wrapper | Targets, in order |
|---|---|
| `deploy-staging.sh` | `verify` (only when this commit has no `build_checks` record), `backend-staging`, `form-kits` with `--form-kits`, `frontend-staging` |
| `deploy-demo.sh` | `backend-demo`, `form-kits` with `--form-kits`, `firestore-rules`, `frontend-demo` |
| `deploy-editor.sh` | `editor` |
| `deploy-admin.sh` | `admin-service` |
| `deploy-admin-console.sh` | `admin-console-candidate`, or `admin-console` with `--live` |
| `backend/deploy-new.sh` | the target for the service named on the command line; an unknown name is REFUSED, never guessed (a new service needs its own channel file and target first) |
| `deploy-all.sh` | `DEPLOY_CHANNEL`'s targets -- it has no default channel, because guessing one would guess "demo", the protected target |

`deploy-all.sh` also keeps a LIBRARY half, above its sourcing guard:
`cloudbuild.yaml`'s backend and admin-service steps run `source ./deploy-all.sh`
and call its `read_channel_section` / `read_channel_value`, so bash and the
build share one parser for `deploy/channels/*.env` rather than restating the
format in yaml. Pinned by `tests/test_deploy_channel_parity.py`.

**The reachability gate is ONE module, `scripts/verify_service_reachable.py`**
(bd `polyglot-pdf-ywxoh`, 4.2), called from `cloudbuild.yaml`'s
`backend-reachability-gate`, `editor-reachability-warn` and
`admin-console-reachability-warn` steps. It once existed as a byte-identical
bash copy in four deploy scripts, each of which deployed a service itself; none
does now, so the module has exactly one kind of caller.
`tests/test_verify_service_reachable.py` exercises it directly via dependency
injection, and `tests/test_deploy_wrappers.py` pins that no wrapper
reintroduces a bash copy.

The module spawns `gcloud` through `shutil.which` (bd `polyglot-pdf-o4f7c`):
on Windows, a bare `gcloud` resolves only to a `gcloud.exe` that the Cloud
SDK does not ship (it ships `gcloud.cmd`), so the spawn raised `WinError 2`
and, under the wrappers' `set -e`, aborted a stage whose deploy had already
succeeded. A spawn that fails outright now counts as an INCONCLUSIVE IAM
read: the module warns and returns success at BOTH severities, because
being unable to check is not proof of breakage (the same rule the bash
gate always had for a failing `gcloud` call) -- never a crash. Both
properties are pinned in `tests/test_verify_service_reachable.py`.

The gate's SEVERITY differs by step: a target that just CREATED the service
aborts, while one binding a PRE-EXISTING backend (the editor, the admin
console) passes `warn` -- refusing to ship over someone else's IAM state would
be the gate crying wolf.

- **Backend** — the `backend-<channel>` target: `docker build` + `docker push`
  to `gcr.io/<project>/polyglot-backend:<sha>`, then
  `gcloud run deploy ... --allow-unauthenticated --timeout=3600 --set-env-vars=`.

  **The env block is assembled in two layers (bd `polyglot-pdf-1s3ko`).** The
  build step computes what only it can know -- `GOOGLE_CLOUD_PROJECT`, the
  `FORM_KITS_*` trio, `APP_MODULE` and `GIT_SHA` (the commit being built) --
  and then appends the channel's settings read from
  **`deploy/channels/<channel>.env`**, selected by the `_CHANNEL` substitution
  the trigger fixes.

  **Why a file rather than a bash string.** A Cloud Build step cannot read a
  variable assembled inside `deploy-staging.sh`, so before the channel files
  the build would have had to RESTATE the config -- and a restated config is
  exactly the drift `tests/test_deploy_channel_parity.py` exists to catch,
  reintroduced at a second site. The build **sources `deploy-all.sh` and calls
  its own `read_channel_section`**, so the file has one parser as well as one
  copy.

  **Format.** Plain `KEY=value` under three section headers, no shell
  expansion: `[SET_ENV_VARS]`, `[SET_SECRETS]`, `[SERVICE_ACCOUNT]`, each
  mapped to its own `gcloud run deploy` flag. `deploy/channels/README.md` is
  the format reference. `SERVICE_ACCOUNT` is explicit and versioned here for
  the first time -- it used to be an inline `SA_EMAIL` constant in each
  wrapper. An empty `[SET_ENV_VARS]` section is REFUSED rather than deployed:
  `--set-env-vars` replaces the whole block, so an empty file would silently
  strip every setting off the service.

  **Parity.** `staging.env` and `demo.env` must agree key-for-key and
  value-for-value except for `LINK_BASE_URL`, `LINK_CHANNEL`, `GIT_SHA` and
  `CORS_EXTRA_ORIGINS` (each channel names its own app site; `CHANNEL_SPECIFIC`
  in the parity test). Change staging FIRST, verify there,
  then promote. `admin.env` is deliberately outside that pair -- there is ONE
  admin service backing both channels' data, so it carries
  `admin-backend-sa`, `APP_MODULE=admin_backend.main:app`,
  `CORS_EXTRA_ORIGINS`, and the THREE Scheduler/Pub-Sub caller identities the
  admin routes' OIDC gates allowlist (`SWEEP_SCHEDULER_SA_EMAIL`,
  `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL`, `PUBSUB_PUSH_SA_EMAIL`). It is the ONLY
  copy: `deploy-admin.sh` restates none of it (bd `polyglot-pdf-oqtm7`, 4.6,
  which is also when the monthly top-up identity moved here -- it had reached
  the service only through that script's inline env assembly, and a key
  missing from the file is a key REMOVED from the running service at the next
  deploy, since `--set-env-vars` replaces the whole block).
  `tests/test_deploy_admin_sweep_env_vars.py` derives the required set from
  the `*_SA_EMAIL` vars the routes actually read, so a fourth caller identity
  is required here the day its route reads it.
  `admin.env` deliberately omits `ADMIN_SERVICE_URL` and `BACKEND_URLS_JSON`
  (its own `[SET_ENV_VARS]` comment) because both need a live `gcloud run
  services describe` lookup at deploy time; `cloudbuild.yaml`'s
  `admin-service-deploy-tagged` step does those lookups before its own
  `gcloud run deploy` and appends them, for the same reason -- omitting either
  would silently disable the refund sweep's OIDC audience or blank
  `GET /admin/health`'s channel fan-out.

  **The build's own identity, `polyglot-cloudbuild-sa`** (bd
  `polyglot-pdf-p4ale`, E4.5), is separate from every SA above -- it is who
  the BUILD runs as, not who a deployed service runs as. Provisioned by
  `scripts/setup-cloud-build.sh` (sibling of `scripts/setup-admin-service.sh`),
  which now does three things instead of just creating triggers: creates the
  SA, grants it a role per class of build step (`roles/run.admin` to deploy
  Cloud Run revisions, `roles/firebasehosting.admin` for the Hosting targets,
  `roles/firebaserules.admin` for `firestore-rules`' RULES half and
  `roles/datastore.indexAdmin` for its COMPOSITE-INDEX half -- the rules role
  does not cover indexes and `roles/datastore.user` carries only the read
  (`datastore.schemas.list`), so the index deploy needs its own grant --
  `roles/artifactregistry.
  writer` to push the image, `roles/logging.logWriter`, `roles/datastore.user`
  to write `build_checks`/`deployments`), and grants `roles/storage.
  objectAdmin` on the form-kits bucket ONLY (same scope, same role, as
  `admin-backend-sa`'s own grant). Every trigger the same script creates
  passes `--service-account` naming this identity, never the legacy default
  Cloud Build SA (which historically holds project Editor).

  **actAs, not just run.admin.** `gcloud run deploy --service-account
  $RUNTIME_SA` additionally requires the CALLER to hold
  `roles/iam.serviceAccountUser` ON that runtime SA -- "deploy a revision
  running as X" is itself privileged on X. The build deploys revisions as
  BOTH `polyglot-backend-sa` and `admin-backend-sa`, so
  `scripts/setup-cloud-build.sh` grants this role on each, resource-scoped
  (`gcloud iam service-accounts add-iam-policy-binding`, never
  `gcloud projects add-iam-policy-binding` -- a project-wide grant would let
  the build identity impersonate every SA in the project). The SAME script
  also grants the Pub/Sub service agent (`service-<PROJECT_NUMBER>@gcp-sa-
  pubsub.iam.gserviceaccount.com`) `roles/iam.serviceAccountTokenCreator`, so
  it can mint the OIDC token the `cloud-builds` topic's push subscription
  presents to the admin service's future build-status webhook (bead 4.3) --
  keeping the whole deploy-plane IAM surface in one script and one pin
  (`admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py`).

  **The reverse direction: `admin-backend-sa` gains actAs on
  `polyglot-cloudbuild-sa`** (also resource-scoped, granted by
  `scripts/setup-admin-service.sh`'s own `CLOUD_BUILD_SA_ROLES` array), so
  the admin service's future trigger route (bead 4.3,
  `admin_backend/services/cloud_build.py`) can submit a build that runs AS
  the build identity. `roles/run.admin` and `roles/firebasehosting.admin`
  are NOT granted to `admin-backend-sa` -- the build does the deploying, the
  admin service only submits it -- so both are deleted (not merely
  deferred) from that script's `DEFERRED_ROLES` pin; only
  `roles/cloudbuild.builds.editor` (the `builds.create` call itself) still
  awaits bead 4.3. See [admin-service.md](admin-service.md)'s IAM table for
  the admin-SA side of this same pin.

  **`--set-secrets`** comes from the channel file's `[SET_SECRETS]` section and
  from nowhere else -- the build reads that section into `CHANNEL_SECRETS` and
  passes it verbatim; there is no caller-side override. A channel that sets
  none produces an invocation identical to before the flag existed. It
  **REPLACES the service's entire secret block** — gcloud's own help says "All
  existing secrets will be removed first" — so a channel must list every
  binding it wants to survive, not just the one it is adding. The
  container (the ROOT `Dockerfile`: `python:3.12-slim` pinned by digest, runtime
  requirements only, running as the non-root `app` user) runs
  `uvicorn ${APP_MODULE:-backend.main:app}` on `$PORT` (8080) -- see
  **One image, two services** below for why the module is a runtime variable.
  `--timeout=3600` (the Cloud Run maximum)
  is load-bearing for `/ws/fill`: Cloud Run kills any request at the timeout,
  live WebSockets included, and the 300s default terminated every voice session
  at exactly 5 minutes (bd polyglot-pdf-9w5k).

  **Deploy preflight (bd `polyglot-pdf-1s3ko`).** EVERY wrapper sources
  `scripts/deploy_preflight.sh` and calls
  `deploy_preflight` BEFORE anything else. It refuses a **dirty** tree
  (`git status --porcelain` non-empty, untracked files included) and a commit
  **no remote branch contains**. Both refusals protect the same claim: a Cloud
  Build build runs from a COMMIT and `build_checks/{sha}` vouches for that
  commit's test run, so a tree that does not match the named commit makes the
  record true about something other than what shipped. The unpushed check asks
  `git branch -r --contains HEAD` rather than testing ancestry against one
  branch, because a commit on a pushed FEATURE branch is perfectly deployable
  -- that is the normal shape of a staging deploy. Pinned behaviourally by
  `tests/test_deploy_preflight.py`, which runs the helper under bash against
  real temporary repositories.

  **Reachability gate (bd `polyglot-pdf-pidtg`).** After the deploy, the
  `backend-reachability-gate` step
  reads the service's IAM policy and **fails the build if there is no
  `allUsers` invoker binding.** `--allow-unauthenticated` REQUESTS that binding but
  the request can be REFUSED while the deploy still succeeds and exits 0 -- which is
  exactly what happened on the first deploy of `polyglot-backend-staging`: the
  domain-restricted-sharing org policy rejected `allUsers`, gcloud warned
  non-fatally, and the service 403'd every request at Cloud Run's gate *before any
  application code ran*. An EXISTING service never shows this (its binding predates
  the policy and is not retroactively stripped), so the failure surfaces only when
  standing up a NEW service. If the IAM read itself fails (no permission, transient
  error) the gate WARNS instead of aborting -- being unable to check is not proof the
  service is broken.
- **Form-kits** — the `form-kits` target uploads the **complete** kits it finds
  in the build's own `form-kits/` tree (i.e. the GIT CHECKOUT of the commit
  being built)
  to `gs://<bucket>/<prefix>/` plus an `index.json` manifest written and
  validated by `scripts/write_kits_manifest.py`. Demo bucket
  `polyglot-demo-aa709-form-kits`. There is no per-channel split, so this
  publishes to the DEMO's form list whichever wrapper started it. A kit is
  uploaded (and listed in the manifest) only when its `metadata.json` has
  `status: complete` — the gate skips
  draft, submitted, unmarked, AND unpublished (retired) kits, so in-progress
  or no-longer-live forms never reach the voice
  app (bd polyglot-pdf-b0pe). Both the upload loop and the manifest loop are
  gated, so a non-`complete` kit is absent from GCS *and* the served
  manifest.
  **This target cannot currently succeed, and no wrapper selects it
  implicitly.** Kits are BUCKET-canonical and none is tracked in git (CLAUDE.md
  scar #10), so a connected-repo build sees a `form-kits/` tree with no
  `status: complete` kit in it at all: the upload loop uploads nothing and
  `write_kits_manifest.py` exits 1 rather than write the empty manifest that
  would blank the demo's form list. Only an explicit `--form-kits` puts the
  target in a wrapper's list (bare runs and `--all` no longer do, on either
  channel), so a normal deploy no longer stops here with `firestore-rules` and
  the frontend unrun. Reconciling the target's SOURCE with the bucket-canonical
  storage model is a maintainer direction call, filed as bd
  `polyglot-pdf-wm7ga`; publishing through the hosted schema editor is the
  working path meanwhile.
- **Frontend** — the `frontend-<channel>` target: `npm ci`, then
  `npm run build:schema:demo` (mode `demo` for BOTH channels — they share one
  Firebase project and therefore one set of client-side keys), then
  `npx firebase-tools deploy --only hosting:<target>` (`app` for demo,
  `app-staging` for staging). The
  bare `npm run build` is NOT used: it loads `.env.production` under the default
  Vite config, whose Firebase keys differ per channel — a demo built that way dies
  with `auth/invalid-api-key`. **Backend WS URL is resolved at deploy time** (bd
  `emm7`): the `frontend-resolve-urls` step resolves the live Cloud Run URL
  (`gcloud run services describe <service> --format 'value(status.url)'`)
  and hands it forward through `/workspace` for the build step to export as
  `VITE_WS_URL`. **That resolution is what binds a frontend build to
  its channel's backend**, and it is a separate STEP rather than a substitution
  because substitutions are fixed at trigger time, before the build can look
  anything up. It OVERRIDES the `.env.<mode>` `VITE_WS_URL` line (standard Vite
  precedence); the values committed in `.env.demo` /
  `.env.production` are documented FALLBACK-ONLY, because the Cloud Run auto-URL
  hash is not stable (it drifted on a service recreate and 404'd the deployed
  frontend). An unresolvable backend URL ABORTS the build rather than falling
  back — both fallbacks name a DEMO backend, so warning-and-continuing would
  ship a staging site driving the live demo backend (pinned by
  `backend/tests/unit/test_deploy_channel_isolation.py`).
  **`VITE_ADMIN_API_BASE_URL` is resolved the SAME way**
  (bd `polyglot-pdf-z4ljj`, C0): the same step resolves
  the live `polyglot-admin` Cloud Run URL (ONE admin service backs both
  channels) and the build step exports it,
  binding the main app's firm-console pages (`frontend/src/console/*`) to the
  admin service. An unresolvable admin URL aborts too, and for a sharper
  reason: the build step exports whatever the resolve step wrote,
  UNCONDITIONALLY, so an empty export would override the committed fallback and
  turn every firm-console call into a relative path that Hosting's `/api/**`
  rewrite sends to the VOICE backend. Pinned by
  `tests/test_deploy_admin_url_injection.py`. **This is a
  SECOND producer of the `VITE_ADMIN_API_BASE_URL` name** — the
  `admin-console-*` targets (see "Admin console" below) also
  resolve and export it, for a DIFFERENT Vite app/build; the two builds
  never run together, so there is no collision, only a shared name for the
  same kind of value.

  **`VITE_APP_CHANNEL`** (bd `polyglot-pdf-z4ljj`) tells the built frontend
  which channel it IS — required because every firm-scoped admin-service
  route takes an explicit `?channel=` (the admin service has no channel
  identity of its own; it is one Cloud Run service serving both channels'
  Firestore data). This can NOT be derived from Vite's own `MODE`: both
  channels build mode `demo` (above), so
  `import.meta.env.MODE` reads `demo` for a staging build too. The build step
  exports `VITE_APP_CHANNEL="${_CHANNEL}"` — the channel the TRIGGER fixes, so
  it cannot disagree with the Hosting target or the backend service the same
  substitution selected.
  `frontend/src/shared/config.ts`'s `getAppChannel()` reads it, falling back
  to `'demo'` on an unset OR unrecognized value — the same "unset means demo"
  convention as `link_channel()` and every bucket default in this repo — so a
  local dev build or a bare `vite build` never silently claims to be
  `staging`, and a typo'd value never mints a `channel` the admin service's
  own `KNOWN_CHANNELS` check would 404.
- **Asset base MUST be absolute (`base: '/'`), never relative** (bd
  `polyglot-pdf-3bsyv`). `frontend/vite.config.schema.ts` used to set
  `base: './'`, so `index.html` referenced `./assets/...` — resolved by the
  browser against the CURRENT PATH, not the site root. This app is always
  served from a Hosting site ROOT (`app`/`app-staging` in the table above) or
  from dev-local's root, never from a subdirectory, so the relative form was
  never correct: a cold load at any path carrying a segment
  (`/console/links`, `/console/employees`)
  asked for `/console/assets/...`, which does not exist, and the `**` ->
  `/index.html` catch-all rewrite (`firebase.json`, same file referenced
  above) answered with HTML — the browser then refuses the module script
  ("Expected a JavaScript-or-Wasm module script but the server responded
  with a MIME type of text/html"). Only the site root ever worked on a cold
  load; client-side navigation FROM the root hid the bug (no asset re-fetch),
  which is why it shipped undetected. Pinned by
  `frontend/src/shared/buildAbsoluteAssetBase.test.ts` (a static read of the
  config's `base` value plus a real production build asserting the emitted
  `index.html` references `/assets/` absolutely). `schema-editor/vite.config.ts`
  and `admin-console/vite.config.ts` carry no `base` override at all, so both
  already default to Vite's own absolute `/` — this bug was unique to this
  app's config.
- **Firestore rules** — the `firestore-rules` target ships BOTH
  `firestore.rules` and the composite `firestore.indexes.json` (wired via
  `firebase.json`), in that order. `deploy-demo.sh` runs it
  only on a frontend/full deploy, and **before** the frontend target so the new
  frontend never goes live against stale rules. Index builds are ASYNCHRONOUS:
  the build reports success before a new index is READY, so a freshly added
  filter can still fail for a few minutes afterwards. **`deploy-staging.sh`
  deliberately never runs this target**: rules and indexes are project-wide,
  not per-site, so a staging rules deploy would apply to the live demo. A
  project left on default-deny breaks the `users/{uid}` profile sync -- see
  [auth.md](auth.md); email signup no longer depends on a client-readable
  rule (the allowlist check is server-side since sprint 23 C3,
  `POST /api/signup/check`).

### One image, two services (`APP_MODULE`)

The root `Dockerfile` copies BOTH top-level Python packages -- `backend/` (the
public voice app) and `admin_backend/` (the privileged admin API, bd
`polyglot-pdf-pnoik`) -- and its `CMD` picks which one to serve at RUNTIME:

```
CMD uvicorn ${APP_MODULE:-backend.main:app} --host 0.0.0.0 --port ${PORT} --no-access-log
```

**`--no-access-log` is load-bearing for privacy** (bd `polyglot-pdf-6rj0j`,
sprint 23 B0). uvicorn's access line prints the full request target at
INFO, and until sprint 23 C2 `/ws/fill` carried its credential in the
query string (`?token=<Firebase ID token or magic-link token>`), so with
the access log on, every voice connection wrote a live, replayable token
into the container's stdout and Cloud Logging. C2 moved the credential
into the first WebSocket frame; `?token=` is still honoured for one deploy
cycle, so the flag stays load-bearing until that branch is removed (and
the request-log exclusion filter from B0 matches nothing once every
client sends the new frame). `configure_logging()`
(`backend/utils/logging.py`) also caps the `uvicorn.access` logger at
WARNING, so a uvicorn started WITHOUT the flag (the local launchers)
drops the line too; the two guards are pinned separately
(`tests/test_dockerfile_app_module.py`, `tests/test_logging_access_log.py`).
The cost is diagnostic: there is no per-connection access line in the
app stream. Cloud Run's own request log (`run.googleapis.com/requests`)
still records status and latency per request -- and, until the WS
credential moves out of the URL (sprint 23 bead C2), the URL itself.
That request-log copy is NOT mitigated by this flag; an interim Cloud
Logging exclusion on `httpRequest.requestUrl` is a separate live-change
ask tracked on bd `polyglot-pdf-6rj0j`, applied only when the maintainer
approves it.

**Why a runtime env var and not a build arg.** ONE image backs both Cloud Run
services, and which app it serves is a per-SERVICE fact, not a per-image one --
an `ARG` would freeze at its default in every image while the deploy-time value
was silently ignored. `APP_MODULE` rides in through `gcloud run deploy
--set-env-vars` instead, read from `deploy/channels/<channel>.env`.

Rules the pin test `tests/test_dockerfile_app_module.py` enforces:

- **The default is `backend.main:app`.** Every existing deploy passes no
  `APP_MODULE` at all, so an unset value must keep serving the public backend.
- **`:-`, not `-`.** A deploy that passes an EMPTY `APP_MODULE` (a real shape
  when a bash variable is unset inside a `--set-env-vars` block) must fall back
  too, or the container crash-loops with an empty uvicorn target.
- **No `ENV APP_MODULE=`.** An `ENV` default satisfies the `:-` expansion with
  its own value, making the fallback dead code and hiding exactly the
  empty-string case above.
- **No build `ARG`s**, and **both packages copied**, since `APP_MODULE` can only
  point at a package the image actually contains.

The two services differ in IDENTITY, not in image: `polyglot-backend` runs as
the narrow `polyglot-backend-sa`, `polyglot-admin` as `admin-backend-sa`
(provisioned by `scripts/setup-admin-service.sh`, role list pinned offline by
`admin_backend/tests/unit/test_admin_sa_iam_envelope.py`). Shipping both
packages in one image is safe because the deployed service account -- not what
is present on disk -- is what actually gates a privileged call
(CLAUDE.md scar #7). `admin_backend/` imports `backend.services.*` and `backend.config` but
**never `backend.routes`**: the services share business logic, not HTTP
surface, and that direction is pinned by the same test. The **reverse**
direction -- `backend/` importing `admin_backend` -- is pinned separately by
`backend/tests/unit/test_deployed_iam_envelope.py`, because that is the one
that would put a privileged call under the NARROW service account in a file
the scar-#7 scan never opens.

The admin service's `/health` reports the `app_module` it is actually running,
because a service pointed at the wrong module otherwise looks perfectly healthy
while serving the wrong app. It resolves an EMPTY `APP_MODULE` to the default,
matching the `:-` expansion above -- a plain `os.getenv(name, default)` would
report an empty string in exactly that case. `scripts/verify_service_reachable.py`
itself still never calls this route -- it reads the Cloud Run IAM policy, not
HTTP -- but the `admin-service` target's tagged flow (below) DOES issue a real
`GET .../health` against this exact route and gates the traffic shift on its
response, so it is no longer true that this route has no deploy-time behavioral
coverage; that coverage exists only on the admin service's own target, not on
the `backend-<channel>` ones.

**`GET /version` on both services** (bd `polyglot-pdf-9hzod`) returns
`{"version": app.version, "git_sha": ...}`. `git_sha` reads the `GIT_SHA`
runtime env var, falling back to `"unknown"` on the SAME two shapes
`APP_MODULE` guards above -- unset, and set-but-empty (`os.getenv("GIT_SHA")
or "unknown"`, not a plain getenv default, for the same `--set-env-vars`
reason). Nothing sets `GIT_SHA` on a deployed service yet -- that wiring
(`--set-env-vars GIT_SHA=$(git rev-parse HEAD)` in the deploy bridge) is bead
1.3; until it lands, every deployed `/version` reports `"unknown"`. Cloud
Build's `$COMMIT_SHA` supersedes the bash-computed value in Epic 4. The admin
console's "what is live per channel" view (bead 1.7) reads this field on
both services via a Vite define carrying the same value at console build
time.

Cloud Run runs `polyglot-admin` with `--allow-unauthenticated`, so the
app-level gate on every OTHER route is the whole access control.
`admin_backend/services/admin_auth.py` mirrors
`backend/services/editor_auth.py`: a boolean `app_admin` custom claim,
`require_app_admin` (dev bypass refused on `K_SERVICE`, `verify_id_token` with
`check_revoked` deliberately off, a 401/403 split with a machine-readable
`NO_ADMIN_ACCESS:` prefix on the "no admin claim at all" 403). The gate's
first route was `GET /admin/whoami`; bd `polyglot-pdf-li9x0` added
`GET /admin/audit` and `GET`/`PUT /admin/config/{channel}` behind the same
gate, and with them the audit log every mutating admin route must write
(`admin_backend/services/audit_log.py`; see
[`technical_guide.md`](../technical_guide.md) contract 15). The same module
also holds `require_app_admin_or_owning_manager` (bd `polyglot-pdf-dmjl5`),
the composite gate on the four `/admin/users` routes: an app admin names the
firm they act on, a firm manager's comes from their token and a request that
names one is refused.
`admin_backend/tests/unit/test_admin_route_auth.py`
derives the registered route set from the live app and asserts every
business route (everything but `/health` and `/version`) carries exactly one
of four gate names. ALL FOUR now exist: `require_app_admin`,
`require_app_admin_or_owning_manager`, and `require_firm_manager` (which
lives on the PUBLIC backend, `backend/services/auth.py`, over the shared
rule `backend/services/firms.py::manager_firm_id`), plus
`require_google_oidc` (bd `polyglot-pdf-8vgfh`), which gates Google-managed
service callers (Cloud Scheduler, and Epic 4's Pub/Sub push route later) by
OIDC token + an allowlisted caller email rather than a human sign-in. It
shipped with its first consuming route, `POST /admin/links/sweep-expired`
(see [`admin-service.md`](admin-service.md) for the route table and the
sweep's own deploy-time env vars). A FIFTH dependency,
`require_app_admin_or_owning_manager_or_employee` (bd
`polyglot-pdf-scaig`), exists beside these four for a small, named set of
routes (`GET /admin/firms/{firm_id}/links`; plus, from bd `polyglot-pdf-62o4d`,
`GET /admin/firms/{firm_id}/alerts` and the widened
`PATCH /admin/alerts/{alert_id}/acknowledge`) and is deliberately outside the
four-gate vocabulary `test_admin_route_auth.py` enforces -- see
[`admin-service.md`](admin-service.md) for the full shape. No deploy-time
env var or config key changed for it. The FIRST
admin account is stamped by `scripts/bootstrap_admin_user.py`
(`--email`/`--revoke`/`--list`, `--project` required with the same
deterministic-project-pin + dead-project-refusal machinery as
`scripts/bootstrap_firm.py`) -- there is no other way to create one.

**The `admin-service` target (bd `polyglot-pdf-3l2vp`, sprint-22 plan bead
1.3)** is how the admin backend ships, and `deploy-admin.sh` is the one-line
wrapper that starts it. Its env, secrets and runtime identity come from
`deploy/channels/admin.env` (above); the target deploys a **no-traffic tagged
revision** (`--no-traffic --tag candidate`) instead of shifting traffic
immediately, verifies the tag's own stable URL's `/health` first (that URL is
built by inserting `candidate---` ahead of the service's base host -- `gcloud
run services describe` reports no revision-scoped address of its own), and only
then runs `gcloud run services update-traffic --to-latest`. A failed health
check fails the step, so the shift never runs and the previous revision stays
live. This exists because there is ONE admin service backing BOTH channels'
data -- a bad admin deploy would otherwise take the control plane down for
staging and the demo at once, and this sequence is that service's own staging
tier. Every backend-family target also passes `GIT_SHA=<the built commit>` as
runtime env, which is what `GET /version` reports. Step order (record the
success row, then the staging gate, then the traffic shift) is pinned by
`tests/test_cloudbuild_yaml.py`. **What this target does NOT do:** deploy the
admin-console Vite app -- that is `admin-console-candidate` / `admin-console`;
running `deploy-admin.sh` alone stands the API up with no UI in front of it,
which is a legitimate intermediate state.

### Hosted schema editor (second Hosting site)

`firebase.json` `hosting` is an ARRAY of FIVE named targets (bd `92qe.4`,
extended by `stgenv`, extended by `b6943`): `app` (the voice app,
`frontend/dist`, `/api` rewrite -> `polyglot-backend`), `app-staging` (same
build dir, `/api` rewrite -> `polyglot-backend-staging`), `editor`
(`schema-editor/dist`, SPA catch-all, **no** `/api` rewrite -- the editor calls
Cloud Run directly via `VITE_API_BASE_URL`; the Hosting rewrite's 60s cap would
kill minutes-long extraction), and `admin` + `admin-candidate` (both
`admin-console/dist`, both SPA catch-all with **no** `/api` rewrite for the same
reason -- see "Admin console (two more Hosting sites)" below). `.firebaserc`
maps `editor` -> `polyglot-editor-demo`, `app-staging` -> `polyglot-app-staging`,
`admin` -> `polyglot-admin-demo`, and `admin-candidate` ->
`polyglot-admin-candidate`, all on the demo project. **Because targets are
named, a bare `firebase deploy --only hosting` deploys ALL FIVE sites** --
every build target names its own (`--only hosting:<target>`, resolved from
`_CHANNEL` or fixed per target), the `frontend/package.json` `deploy` /
`deploy:demo` shortcuts are pinned too (the unscoped prod one would
otherwise THROW -- prod maps no `editor` target -- and the demo one would
silently ship a stale editor build), and the editor ships only via
the **`editor`** target (`npm run build:hosted` + `--only hosting:editor`),
which `deploy-editor.sh` starts; that script's
header is the one-time runbook: site create, `target:apply`, granting each
person editor access with `scripts/bootstrap_editor_user.py`, adding the
editor's domain to Firebase Auth's authorized domains, and the bucket
`roles/storage.objectAdmin` grant the editor's writes need.
The `editor` target also **resolves the live Cloud Run URL at build time** and
exports `VITE_API_BASE_URL` (overriding the `.env.hosted` fallback), same as the
voice app -- a committed hash there once drifted on a service recreate and made
every request 404 against the backend, looking like a broken deploy rather
than a stale URL (bd `emm7`).
`deploy/channels/demo.env` carries `EXTRACTOR_MODEL` + `CORS_EXTRA_ORIGINS`
(SEMICOLON-separated origins -- commas are `--set-env-vars`' pair separator)
in `[SET_ENV_VARS]`; the backend deploy runs `--memory=1Gi` (extraction
holds PDFs in memory + tmpfs). **Contractor round trip:**
`scripts/pull-form-kits.sh` rsyncs bucket kits DOWN into `form-kits/`
(index.json excluded; local-only kits preserved) so contractor work is
reviewable locally. NOTE that the pulled tree is no longer what a deploy
publishes: kits are never committed, and the `form-kits` build target reads
the commit's checkout rather than an operator's working tree, so a local pull
now feeds local inspection and the schema editor only (bd
`polyglot-pdf-wm7ga`).

### Hosting security headers (all five sites, bd `polyglot-pdf-j29z1`)

Every Hosting target in `firebase.json` carries one `headers` block on `**`:
HSTS (`max-age=31536000; includeSubDomains; preload` -- inert on the shared
`web.app` / `firebaseapp.com` parents, which Google already preloads; revisit
before attaching a custom domain), `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, a
`Permissions-Policy` that allows the microphone to the site itself and denies
camera/geolocation/payment/usb/interest-cohort, and a Content Security Policy.

The CSP is **one policy shared by all five sites** and ships as
`Content-Security-Policy-Report-Only`: `firebase.json` is a single file for
every site, so the staging soak cannot be staging-only, and enforcing on the
demo without a soak is the wrong risk. Browsers write violations to the devtools
console; the staging test-drive reads it, and renaming the header to
`Content-Security-Policy` is a separate, reviewed change; the live posture
runbook (`scripts/audit/infra_posture.sh`, check 10) reads the report-only
header as PASS with the mode named, so the soak does not read as a missing
header, and no longer requires `X-Frame-Options`. The policy's
`connect-src` is built from what the apps actually contact: the three Cloud Run
services (demo backend, staging backend, admin; https + wss, project-hashed
hostnames), Firebase Auth (`identitytoolkit`, `securetoken`,
`www.googleapis.com` is NOT listed -- the shipped SDK never contacts it),
Firestore (https + wss), and `https://cdn.jsdelivr.net`: the voice overlay's
speech detector (`@ricky0123/vad-web`, `frontend/src/demo/useDemoVAD.ts`)
fetches its model and audio worklet from there and `onnxruntime-web` its WASM
runtime. `script-src` is `'self'` plus `https://apis.google.com` (the gapi
loader the Firebase Auth SDK injects as a `<script>` before it can open the
sign-in popup), the same CDN (the worklet is script) and `'wasm-unsafe-eval'`
-- which covers WASM *compilation* only. The ONNX glue the app currently
selects (`ort-wasm-simd-threaded.jsep.mjs`) also calls `new Function`, which
only `'unsafe-eval'` would permit and this policy deliberately does not
grant; whether that path is reached for the Silero model is what the soak
must watch for (an `EvalError: Refused to evaluate a string as JavaScript`
report). Executable code from a third-party CDN is the largest remaining
browser egress; the prerequisite for switching the CSP to enforcing is bd
`polyglot-pdf-18o7c`: self-host those assets AND select the non-jsep ORT
build, which contains no `new Function`; `style-src` allows inline (React style attributes);
`worker-src` and `media-src` allow `blob:` (pdf.js, spellback audio);
`frame-src` names the auth domain and Google's account chooser;
`frame-ancestors 'none'`. **There is deliberately NO `X-Frame-Options`:** the
`app` site is also the project's auth domain, so it serves Firebase Auth's
reserved `/__/auth/iframe`, which every `signInWithPopup` on our own pages
frames; `X-Frame-Options` cannot carve out a path, so framing is governed by
`frame-ancestors` alone, and a second block on `/__/auth/**` (listed after the
catch-all so it wins) allows exactly our five sites, both hostnames each, as
ancestors. A third block gives `/fonts/**` a week of `Cache-Control`. A new
Cloud Run hostname or a new external endpoint MUST be added to the policy or
the app breaks silently under report-only and loudly once enforced -- and the
Cloud Run hash is the one value this repo has seen drift (bd `emm7`), so
`tests/test_hosting_headers.py` also asserts every `a.run.app` host the three
apps' env files name is in `connect-src`. The same test pins every target,
every header, every required origin, the `/__/auth/**` ancestor list, the
fonts cache, and no `'unsafe-eval'`/`http:`/wildcard host.

Fonts are self-hosted: `scripts/fetch_fonts.py` regenerates
`frontend/public/fonts/` (Inter + Outfit in every unicode-range subset Google
serves -- latin, latin-ext, cyrillic, cyrillic-ext, greek, greek-ext,
vietnamese; 45 woff2 files + `fonts.css`)
and `frontend/index.html` links that stylesheet, so the browser contacts no
third-party font host.

### Admin console (two more Hosting sites, bd `b6943`)

`admin-console/` mirrors `schema-editor/` closely -- same Vite + React +
Tailwind skeleton, same `fsAllowList` worktree fix and `.claude/worktrees`
watch exclusion in `vite.config.ts`, same two-gate `SignInGate.tsx` (Firebase
sign-in, then a server-side probe -- here of `GET /admin/whoami` rather than
the editor's `/api/editor/session`), same `.env.hosted` / build:hosted split,
and the same "grant access, never self-serve signup" posture
(`scripts/bootstrap_admin_user.py` in place of
`scripts/bootstrap_editor_user.py`). `admin-console/vite.config.ts` also bakes
the CONSOLE's own build-commit SHA into the bundle via a Vite `define`
(`__ADMIN_CONSOLE_GIT_SHA__`, read at `git rev-parse HEAD` build time, falling
back to `'unknown'`) -- distinct from `GET /version`'s `git_sha`, which reports
the ADMIN SERVICE's commit, a separate deploy this app calls over HTTP.

UNLIKE the editor (one Hosting site), the console ships to **two**: `admin`
(`polyglot-admin-demo`, the live site every admin actually uses) and
`admin-candidate` (`polyglot-admin-candidate`, deployed FIRST on every run).
The reason is architectural, not caution for its own sake: the admin service
has NO channel of its own (`admin_backend/main.py` -- it serves BOTH staging's
and the demo's data), so there is no cheap staging channel in front of it the
way `deploy-staging.sh` protects the voice app. The candidate site is the
console's substitute -- `./deploy-admin-console.sh` (no flag) runs ONLY the
`admin-console-candidate` target; `./deploy-admin-console.sh --live` runs
`admin-console`, the same commit to the live site, after a human checks the
candidate. Both targets share the identical
Cloud Run-URL-resolution + reachability-gate pattern the `editor` target uses
(`VITE_ADMIN_API_BASE_URL` resolved from the live `polyglot-admin` service at
build time, `scripts/verify_service_reachable.py` called in WARN mode since
the admin service is pre-existing from this target's point of view -- see
Surface contracts in `technical_guide.md`). A preview channel
(`firebase hosting:channel:deploy`) is DELIBERATELY NOT used for either site --
its random-hash URLs would have to be re-added to Firebase Auth's authorized
domains and the admin service's `CORS_EXTRA_ORIGINS` on every single deploy; a
fixed candidate site is authorized once, like `polyglot-admin-demo`.
`deploy/channels/admin.env`'s `CORS_EXTRA_ORIGINS` already lists both sites'
`.web.app` and `.firebaseapp.com` domains.

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

**The admin service is a THIRD, separate destination** (bd `polyglot-pdf-z4ljj`,
C0) — neither the `/api/**` Hosting rewrite (which points only at the voice
backend) nor the WS path reach it. `config.ts`'s `getAdminApiBaseUrl()` reads
`VITE_ADMIN_API_BASE_URL` directly with NO fallback chain (an empty string when
unset, meaning "no admin backend configured" — there is no runtime-detection
equivalent to `getBackendUrl()`'s production-URL guess, because a wrong guess
here would point firm-console pages at a plausible-looking but wrong Cloud Run
URL rather than failing visibly). `getAppChannel()` reads `VITE_APP_CHANNEL`
(falling back to `'demo'`), giving `frontend/src/console/adminApi.ts` the two
things every firm-scoped admin-service call needs: the resolved base URL and
the `?channel=` query param the admin service's routes require. See "Frontend"
above for how both env vars are injected at deploy time, and Surface contract
22 in `technical_guide.md` for the producer/consumer wiring.

> **Promotion path** is worktree → local test server → `dev` → staging remote
> (`deploy-staging.sh`) → demo remote (`deploy-demo.sh`); every deploy is a
> Cloud Build build of a PUSHED commit, started either from those wrappers or
> from the admin console, and there is **no active prod**. The agent may run a
> deploy under a three-part gate (local-test-first + per-instance permission +
> post-deploy test-drive). See
> [../doctrine/promotion-tiers.md](../doctrine/promotion-tiers.md).

## Live infrastructure posture (read-only)

`scripts/audit/infra_posture.sh --project <PROJECT_ID>` is the recurring,
read-only runbook for verifying the LIVE deployed environment matches this
doc and the repo's offline IAM pins (sprint 23 security-audit workstream D,
bd `polyglot-pdf-m1dlv`). Under the operator's own `gcloud`/`bq` ADC — never
a service-account key, and never a mutating call — it checks the
project IAM policy, both runtime service accounts' roles against
`backend/tests/unit/test_deployed_iam_envelope.py` and
`admin_backend/tests/unit/test_admin_sa_iam_envelope.py`, every Cloud Run
service's env vars (no secret-shaped value, no dev/bypass flag, no verbosity
knob) and secret bindings, the form-kits bucket's IAM and access-prevention
settings, whether the deployed Firestore rules match the repo file (read via
the Firebase Rules REST API directly, `curl` + the operator's own access
token — the `firebase` CLI ships no subcommand for reading a ruleset's
content), Cloud Logging retention/sinks/exclusions, BigQuery ACLs, Firebase
Auth settings (read the same way, via the Identity Toolkit Admin REST API),
Hosting response headers per site, container scan status, Cloud Build log
content, and the Vertex/Cloud-TTS third-party-processor opt-out settings.
Every check ends `PASS`, `FAIL`, or `N/A: <reason>` — never a silent skip —
so a permission gap or a broken local tool (e.g. this operator's `bq` CLI)
reports its own reason rather than aborting the run. `tests/test_infra_posture_script.py`
pins the script's shipped check list the same way
`tests/test_setup_monitoring_script.py` pins that script's metrics/policies.
