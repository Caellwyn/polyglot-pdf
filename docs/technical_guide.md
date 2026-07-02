# Technical guide -- polyglot-pdf

*Last updated: 2026-07-01. Added the token-gated `/api/editor/*` hosted-editor surface to the route table (bd polyglot-pdf-92qe.1). Prior: added the single-kit read routes (`/api/form-kits/{kit_id}/schema` and `.../pdf`) to the route table (bd polyglot-pdf-sbfk). The `USE_PREMIUM_MODEL` row now records the backend-aware standard-tier id (Vertex vs AI Studio) that `_resolve_model` selects (bd polyglot-pdf-a079); see [journal/entries/2026-06-15-bd-a079-demo-vertex-ai-switch.md](journal/entries/2026-06-15-bd-a079-demo-vertex-ai-switch.md). This guide lists the deploy flow + FORM_KITS_* env vars; per-channel model/auth config detail lives in [standards/ai-models.md](standards/ai-models.md) and [components/config-deployment.md](components/config-deployment.md).*

**Tracks:** `backend/main.py`, `backend/config.py`, `backend/routes/*.py`, `firebase.json`, `deploy-*.sh`

System-wide reference: routes/endpoints, cross-surface gotchas, environment
differences. CURRENT STATE ONLY -- chronological history goes in the journal
(see [`doc-architecture.md`](doc-architecture.md)). Per-surface detail lives in
[`components/`](components/); cross-cutting rules in [`standards/`](standards/).

The app is a stateless FastAPI backend (`backend/main.py`, title
"Web Form Voice Filler API") on Cloud Run + a React/Vite SPA on Firebase Hosting.
For the verified architecture overview, read the re-orientation brief
([`journal/entries/2026-05-30-bd-j2l-reorientation-brief.md`](journal/entries/2026-05-30-bd-j2l-reorientation-brief.md)).

## Environments

Promotion is worktree -> local test server (`scripts/dev-local.ps1`) -> `dev` ->
demo remote (`deploy-demo.sh`). Deploys are **local/manual** (`deploy-demo.sh`,
`deploy-production.sh` -> `deploy-all.sh`), NOT branch-triggered/CI, and there is
**no active prod** -- the demo remote (`polyglot-demo-aa709`) is the live target.
The agent may run `deploy-demo.sh` under the three-part gate (local-test-first +
per-instance permission + post-deploy test-drive); see
[`doctrine/promotion-tiers.md`](doctrine/promotion-tiers.md).

Two Firebase projects: demo and production (frontend picks the backend by the
Cloud Run host it's built against). Backend config is env-driven via
`backend/config.py` (`Settings`); the load-bearing vars:

| Env var | Default | Purpose |
|---------|---------|---------|
| `USE_PREMIUM_MODEL` | `false` | Picks the native audio-to-audio tier: `false` (default) -> 2.5 standard, `true` -> `gemini-3.1-flash-live-preview` (premium). The standard 2.5 id is **backend-aware** (`_resolve_model`): `gemini-live-2.5-flash-native-audio` on Vertex (`VERTEXAI=true`), `gemini-2.5-flash-native-audio-preview-12-2025` on AI Studio (`VERTEXAI=false`) -- each 1008s on the other backend. Both tool-call reliably; 2.5 is the default because it is ~170x faster per turn on the audio path. 3.1 is AI-Studio-only. See [ai-models.md](standards/ai-models.md). |
| `MODEL_NATIVE` | _(derived)_ | Resolved active native-audio model. Defaults from `USE_PREMIUM_MODEL`; set explicitly to pin an exact model string (overrides the flag). |
| `MODEL_LABELING` | `gemini-2.5-flash` | Field labeling/normalization model. |
| `GEMINI_API_KEY` | _(unset)_ | Gemini API key; `/health` reports only its presence, never the value. |
| `USE_JIT_SCHEMA` | `false` | Feature flag: JIT (manifest-only) system instruction vs. full schema. |
| `FORM_KITS_MODE` | `local` | Form-kit store backend (`local` FS vs. GCS/remote). |
| `FORM_KITS_GCS_BUCKET` / `FORM_KITS_REMOTE_*` | _(unset)_ | Remote form-kit store config (see `backend/services/form_kits.py`). |
| `VERTEXAI` | `true` | Route LLM/embedding calls through Vertex AI (`true`) vs. the Gemini API key path (`false`) -- a behavioral switch worth knowing when deploying. Env-overridable so demo/prod can flip without a code edit. |
| `DISABLE_GEMINI_VAD` | `false` | `false` (default) -> native mode (Gemini's automatic VAD is on); `true` -> manual mode (the frontend drives turn-taking with explicit `activity_start`/`activity_end`). Env-overridable. |

Non-env tunables also in `config.py` (code constants, **not** `getenv` -- change
them in source, not via environment):
`PROACTIVE_AUDIO=False` (deprecated), `AUDIO_IN_RATE=16000`,
`AUDIO_OUT_RATE=24000`, `WS_CHUNK_MS=20`, `MAX_UPLOAD_MB=5`,
`VAD_START_SENSITIVITY`/`VAD_END_SENSITIVITY` (`LOW`). The list is not
exhaustive -- additional WS/VAD tuning constants live in `config.py`. Also there:
`WS_IDLE_TIMEOUT_SEC` (`120`) -- the idle watchdog closes a WebSocket connection
after this many seconds with no received message (audio, ping, or control).

## Routes / endpoints

Routers are registered in `backend/main.py`. REST routers carry a `/api` prefix;
the `websocket_routes` router carries `/ws` and is mounted **twice** -- bare and
again under `/api` -- so both `/ws/fill` and `/api/ws/fill` resolve (see Gotchas).
Routes declared directly on `app` in `main.py` (`/ws/vad-config`, `/health`,
`/version`) are **not** part of that double-mount and have no `/api` mirror.

| Method | Path | Surface doc |
|--------|------|-------------|
| WS | `/ws/fill` (+ `/api/ws/fill`) | The voice form-fill session. `components/websocket-routing.md`, `components/voice-ai.md` |
| WS | `/ws/audio`, `/ws/echo` | Lower-level / debug audio sockets. `components/websocket-routing.md` |
| WS | `/ws/vad-config` | VAD config socket (declared on `app` directly in `main.py`). `standards/voice-and-vad.md` |
| POST | `/api/fill-pdf` | Render the filled PDF (PyMuPDF). `components/pdf-filling.md` |
| POST | `/api/disclaimer-acceptance` | Log disclaimer acceptance (anonymized). `standards/confirmation-and-audit.md` |
| GET | `/api/form-kits` | Form-kit manifest (metadata only; GCS/deployed manifest is complete-only, local mode lists any kit with a schema). `components/pdf-filling.md` |
| GET | `/api/form-kits/{kit_id}/schema` | A single kit's schema JSON, streamed from the store (works local + gcs; `no-store`). |
| GET | `/api/form-kits/{kit_id}/pdf` | A single kit's PDF bytes, streamed from the store. |
| GET | `/api/editor/session` | Hosted-editor access-code probe -> `{role}`. Token-gated (`X-Editor-Token`); the whole `/api/editor/*` surface is 503 when no token is configured. `components/pdf-filling.md` |
| GET | `/api/editor/kits` | Editor kit list INCLUDING drafts (from the storage listing, not the complete-only manifest). Token-gated. |
| GET | `/api/editor/kits/{kit_id}/schema`, `.../pdf` | Draft-capable single-kit reads for the hosted editor. Token-gated. |
| PUT | `/api/editor/kits/{kit_id}/schema` | Save an edited schema back to the store (lenient draft save). Token-gated. |
| POST | `/api/editor/kits/{kit_id}/status` | Flip draft/complete; promotion validates against the Pydantic `FormSchema` (the publish gate). Token-gated. |
| GET | `/health` | Liveness + reports active models, audio rates, limits, key-presence. |
| GET | `/version` | App version string. |

## Gotchas

- **WebSockets bypass Firebase Hosting rewrites.** `firebase.json` rewrites
  `/api/**` to Cloud Run, but Hosting doesn't proxy WebSocket upgrades, so the
  frontend connects to the Cloud Run host **directly**, not via the Hosting
  domain. The WS URL is resolved in `frontend/src/shared/config.ts`: the build-time
  `VITE_WS_URL` env var wins if set, else it falls back to `PRODUCTION_WS_URL`
  (the Cloud Run host) in prod or `ws://localhost:8000/ws/fill` in dev. The
  `/api`-prefixed WS mount exists for parity but the live client uses the direct URL.
- **Stateless backend; the client owns all field state.** Field values,
  confirmations, and section state live in the browser's `sessionStorage`; the
  backend rebuilds context from the WS handshake on every (re)connect. Never add
  server-side per-session field persistence, and never log field values/PII/PHI
  server-side. (Formalized in `standards/stateless-architecture.md` +
  `standards/hipaa-pii-policy.md`.)
- **VAD mode.** The default is `DISABLE_GEMINI_VAD=False` -- **native** mode, where
  Gemini's built-in VAD detects turn boundaries. Setting it `True` switches to
  **manual** mode, where the frontend drives turn-taking with explicit
  `activity_start`/`activity_end` messages instead; don't switch modes without
  revisiting the client signals. (See `standards/voice-and-vad.md`.)
- **Idle watchdog** closes a form-fill socket after `WS_IDLE_TIMEOUT_SEC` of no
  inbound traffic, sending a graceful `{"type":"idle_timeout"}` first.
- **"Sections" is canon; "parts" is legacy drift.** The internal section-state vars
  were renamed (`polyglot-pdf-gfb.4`); the only remaining `part` drift is on the
  wire/log format (token-log + handshake keys), deferred to `polyglot-pdf-zun`. Don't
  name new section state `part` (`standards/terminology.md`, `polyglot-pdf-m3f`).
