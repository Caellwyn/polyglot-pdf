# Technical guide -- polyglot-pdf

*Last updated: 2026-08-20 (bd polyglot-pdf-xwlt: Surface contracts entry 6 gains `firm_id` on the confirmation record plus the two session records the voice path now writes -- see [the xwlt journal entry](journal/entries/2026-08-20-bd-xwlt-firm-telemetry.md). Same week, bd polyglot-pdf-qfyxr: the archive read routes -- four route-table rows, two client-tier firm-scoped + two editor token-gated -- see [the qfyxr journal entry](journal/entries/2026-08-19-bd-qfyxr-kit-history-ui.md). Same week, bd polyglot-pdf-xg0pm: Surface contracts section 1's
`editor_kit_routes.py` line citations re-verified against the current file --
draft save, the publish-gate `FormSchema.model_validate` + lint gate, and both
schema read paths had all drifted; also fixed the adjacent `form_kits.py`
`put_schema` citations in the same paragraph while re-verifying it. Same day,
bd polyglot-pdf-vf48u: the translate-options route row's "409 on complete
kits" wording widened to name the write-locked set (complete OR unpublished),
matching the `/status` row's phrasing. Same day, bd polyglot-pdf-1bsuq: the
extract route row now states the same write-locked-kit 409 gate. Same day,
bd polyglot-pdf-5guak added Surface contracts entry 8 (the intro agree-label
mirror) and bd polyglot-pdf-qfak0 added entry 9 (the `LIVE_VOICE_NAME`
two-consumer coupling). Same day, bd polyglot-pdf-s1iex.7: the
disclaimer-acceptance record now carries `script_version`, and
`/api/tts/intro` returns the matching `X-Intro-Script-Version` header -- both
surfaced in the route table below. Also same day, bd polyglot-pdf-kkos: the
static bundle now ships only complete AND public kits, so Surface contracts
entry 7's rewrite paragraph is a shipped security boundary -- see [the kkos
journal entry](journal/entries/2026-08-19-bd-kkos-static-bundle-scoping.md)).
The Surface contracts section is the code-derived cross-surface data-contract
map for blast-radius review (bd polyglot-pdf-n18q). Continuous-DTI is the
production default (`USE_DTI` / `CONTINUOUS_SESSION` /
`CONTEXT_COMPRESSION_ENABLED` all default true, bd polyglot-pdf-7872;
section-reset is the deprecated fallback, bd polyglot-pdf-55jg). This guide
lists the deploy flow + env vars; per-channel model/auth config detail lives
in [standards/ai-models.md](standards/ai-models.md) and
[components/config-deployment.md](components/config-deployment.md).*

**Tracks:** `backend/main.py`, `backend/config.py`, `backend/routes/*.py`, `backend/models/form_models.py`, `backend/services/form_kits.py`, `backend/services/callback_handler.py`, `backend/services/request_coordinator.py`, `backend/adapters/live_ai_gemini.py`, `frontend/src/webFormConnection.ts`, `frontend/src/schema-forms/state/schemaFormState.ts`, `firebase.json`, `deploy-*.sh`

System-wide reference: routes/endpoints, cross-surface gotchas, environment
differences. CURRENT STATE ONLY -- chronological history goes in the journal
(see [`doc-architecture.md`](doc-architecture.md)). Per-surface detail lives in
[`components/`](components/); cross-cutting rules in [`standards/`](standards/).

The app is a stateless FastAPI backend (`backend/main.py`, title
"Web Form Voice Filler API") on Cloud Run + a React/Vite SPA on Firebase Hosting.
For where the surfaces meet -- and what breaks when one side of a contract moves
without the other -- see [Surface contracts](#surface-contracts) below.

## Environments

Promotion is worktree -> local test server (`scripts/dev-local.ps1`) -> `dev` ->
demo remote (`deploy-demo.sh`). Deploys are **local/manual** (`deploy-demo.sh`,
`deploy-production.sh` -> `deploy-all.sh`), NOT branch-triggered/CI, and there is
**no active prod** -- the demo remote (`polyglot-demo-aa709`) is the live target.
The agent may run `deploy-demo.sh` under the three-part gate (local-test-first +
per-instance permission + post-deploy test-drive); see
[`doctrine/promotion-tiers.md`](doctrine/promotion-tiers.md).

One live Firebase project: the demo, `polyglot-demo-aa709` (the former
production project is dead and unreachable; reference purge tracked in bd
`polyglot-pdf-je6iy`). Backend config is env-driven via
`backend/config.py` (`Settings`); the load-bearing vars:

| Env var | Default | Purpose |
|---------|---------|---------|
| `USE_PREMIUM_MODEL` | `false` | Picks the native audio-to-audio tier: `false` (default) -> 2.5 standard, `true` -> `gemini-3.1-flash-live-preview` (premium). **`true` is LOCAL-ONLY**: 3.1 exists only on AI Studio, and the Vertex-only startup guard does NOT catch this flip (the premium id resolves before the `VERTEXAI` branch), so a deployed service starts and then `1008`s at connect. The standard 2.5 id is **backend-aware** (`_resolve_model`): `gemini-live-2.5-flash-native-audio` on Vertex (`VERTEXAI=true`), `gemini-2.5-flash-native-audio-preview-12-2025` on AI Studio (`VERTEXAI=false`) -- each 1008s on the other backend. Both tool-call reliably; 2.5 is the default because it is ~170x faster per turn on the audio path. 3.1 is AI-Studio-only. See [ai-models.md](standards/ai-models.md). |
| `MODEL_NATIVE` | _(derived)_ | Resolved active native-audio model. Defaults from `USE_PREMIUM_MODEL`; set explicitly to pin an exact model string (overrides the flag). |
| `MODEL_LABELING` | `gemini-2.5-flash` | Field labeling/normalization model. |
| `GEMINI_API_KEY` | _(unset)_ | Gemini API key; `/health` reports only its presence, never the value. |
| `USE_DTI` | `true` | Continuous-DTI is the production law of the land (bd polyglot-pdf-7872): the thin static SI + per-field guidance injection. Set `false` for the deprecated legacy full-schema SI (the section-reset fallback, bd polyglot-pdf-55jg). |
| `CONTINUOUS_SESSION` | `true` | The whole form runs as ONE Gemini session bounded by context-window compression (production default). `false` -> the deprecated section-reset flow (fresh session per section). Implies `USE_DTI`. |
| `CONTEXT_COMPRESSION_ENABLED` | `true` | Sliding-window context compression that bounds the continuous session (production default; validated by the jnjj.25 cost gate + G3 correctness gate). `false` disables it. See [components/context-compression.md](components/context-compression.md). |
| `FORM_KITS_MODE` | `local` | Form-kit store backend (`local` FS vs. GCS/remote). |
| `FORM_KITS_GCS_BUCKET` / `FORM_KITS_REMOTE_*` | _(unset)_ | Remote form-kit store config (see `backend/services/form_kits.py`). |
| `VERTEXAI` | `true` | Route LLM/embedding calls through Vertex AI (`true`) vs. the Gemini API key path (`false`). **Vertex is the ONLY production path** (bd 5e6a): its privacy agreement is what keeps client data out of Google's model training. On Cloud Run (`K_SERVICE` set), `false` **fails startup outright -- there is no override flag**. AI Studio is permitted for LOCAL dev only (e.g. pre-GA model testing); a model like 3.1 deploys only once GA on Vertex. |
| `CONFIRMATION_FIRESTORE_ENABLED` | `false` (deploys set `true`) | Mirror the confirmation audit trail (metadata only) to the `confirmation_events` Firestore collection -- the durable sink; the local JSONL dies with the Cloud Run instance. Optional `CONFIRMATION_RETENTION_DAYS` stamps `expire_at`. Retrieval: `scripts/read_confirmations.py`. See `standards/confirmation-and-audit.md` (bd z2is). |
| `DISABLE_GEMINI_VAD` | `false` | `false` (default) -> native mode (Gemini's automatic VAD is on); `true` -> manual mode (the frontend drives turn-taking with explicit `activity_start`/`activity_end`). Env-overridable. |
| `FIRMS_FIRESTORE_ENABLED` | `false` (deploys set `true`) | Enables the firms-store READ path (`backend/services/firms.py`, bd lo88): the `firms/{firm_id}` collection holding firm profiles + allowed-kits, consumed by the form-kit routes' firm-scoped visibility filter (bd vccy). Reads FAIL CLOSED to `[]` when off/broken, so an outage hides private kits rather than exposing them. Set in `deploy-all.sh`'s `BACKEND_ENV`; the `deploy-form-kit.sh` drop-list hint enumerates it (pinned by `tests/test_deploy_form_kit_hints.py`). Firm records are created by `scripts/bootstrap_firm.py`; see `components/auth.md` (Firm identity). |

Non-env tunables also in `config.py` (code constants, **not** `getenv` -- change
them in source, not via environment):
`AUDIO_IN_RATE=16000`,
`AUDIO_OUT_RATE=24000`, `WS_CHUNK_MS=20`, `MAX_UPLOAD_MB=5`. The VAD
sensitivity knobs ARE env-overridable: `VAD_START_SENSITIVITY` (default
`HIGH`) / `VAD_END_SENSITIVITY` (default `LOW`). The list is not
exhaustive -- additional WS/VAD tuning constants live in `config.py`. Also there:
`WS_IDLE_TIMEOUT_SEC` (`120`) -- the idle watchdog closes a WebSocket connection
after this many seconds with no received message (audio, ping, or control).

## Routes / endpoints

Routers are registered in `backend/main.py`. REST routers carry a `/api` prefix;
the `websocket_routes` router carries `/ws` and is mounted **twice** -- bare and
again under `/api` -- so both `/ws/fill` and `/api/ws/fill` resolve (see Gotchas).
Routes declared directly on `app` in `main.py` (`/health`, `/version`) are
**not** part of that double-mount and have no `/api` mirror.

| Method | Path | Surface doc |
|--------|------|-------------|
| WS | `/ws/fill` (+ `/api/ws/fill`) | The voice form-fill session. Requires `?token=<Firebase idToken>`. `components/websocket-routing.md`, `components/voice-ai.md` |
| WS | `/ws/audio`, `/ws/echo` | Lower-level / debug audio sockets. **Dev-only**: handshake rejected unless the `backend/.env.DEV` marker exists (same gate as `/dev/console-log`; bd polyglot-pdf-puu8). `components/websocket-routing.md` |
| POST | `/api/fill-pdf` | Render the filled PDF (PyMuPDF). **Auth-gated** (`Authorization: Bearer <idToken>` via `require_auth`; bd z2is) + **firm-scoped** (bd vy6id: the body's caller-supplied `kit_id` runs the same visibility gate as the kit reads -- a private kit 404s for non-members). `components/pdf-filling.md` |
| POST | `/api/disclaimer-acceptance` | Log disclaimer acceptance (anonymized; client IP deliberately NOT logged, bd z2is). Records `script_version` -- the hash of the exact script the user saw and heard, echoed from the intro route's `X-Intro-Script-Version` so the record names WHICH text was agreed to; `None` on the legacy model-read path (bd s1iex.7). `standards/confirmation-and-audit.md` |
| POST | `/api/tts/spellback` | Deterministic spell-back verification clip (Cloud TTS, session language + persona voice; the value is PII -- never logged, lengths only; 60-char input cap). **Auth-gated**; 503 unless `SPELLBACK_TOOL_ENABLED` (bd 22h1f/44ywm). `backend/routes/tts_routes.py`, `backend/services/spellback_tts.py` |
| POST | `/api/tts/intro` | Sol's scripted intro+disclaimer clip (sprint 20, bd s1iex.3). KEYED route: `{form_number, language}` resolve against server-side tables only (`intro_tts.KNOWN_FORMS` + `intro_script.json` + `intro_agree_labels.json`) so caller text never enters synthesis; unknown form -> 400, unknown language -> English fallback. In-process cache per `(language, form, script_hash)`; `Cache-Control: private` + ETag with If-None-Match 304, plus `X-Intro-Script-Version` (the script hash the acceptance record echoes, bd s1iex.7 -- both headers need CORS `expose_headers` to be readable cross-origin); 0 dB gain (the spell-back +4 dB clips ~90s clips). **Auth-gated**; 503 unless `INTRO_TTS_ENABLED`. `backend/services/intro_tts.py` |
| GET | `/api/form-kits` | Form-kit manifest (metadata only; GCS/deployed manifest is complete-only, local mode lists any kit with a schema). **Auth-gated** (bd z2is) + **firm-scoped** (bd vccy): PRIVATE kits appear only for callers whose `firm_id` claim resolves to an allowlist containing them, with paths rewritten to the authenticated backend routes. `components/pdf-filling.md` |
| GET | `/api/form-kits/{kit_id}/schema` | A single kit's schema JSON, streamed from the store (works local + gcs; `no-store`). **Auth-gated** (bd z2is) + **firm-scoped** (bd vccy: a private kit 404s for non-members). |
| GET | `/api/form-kits/{kit_id}/pdf` | A single kit's PDF bytes, streamed from the store. **Public for PUBLIC kits** (their blank-template bytes ship in the static bundle regardless -- bd z2is); a PRIVATE kit needs a bearer token whose firm allowlist contains it, else 404 (bd vccy; invalid token degrades to anonymous -- existence is the secret). |
| GET | `/api/form-kits/{kit_id}/archive` | A kit's superseded revisions, newest-first by the archived snapshot's `published_at`. **Auth-gated + firm-scoped** (bd qfyxr: same gates as the schema read -- history is visible exactly when the kit is). |
| GET | `/api/form-kits/{kit_id}/archive/{marker}/schema` | One archived revision's schema, READ-ONLY (no write counterpart exists -- superseded bytes are what the audit trail names). **Auth-gated + firm-scoped** (bd qfyxr); marker validated to `encode_marker`'s contract. |
| GET | `/api/editor/session` | Hosted-editor access-code probe -> `{role}`. Token-gated (`X-Editor-Token`); the whole `/api/editor/*` surface is 503 when no token is configured. `components/pdf-filling.md` |
| GET | `/api/editor/kits` | Editor kit list INCLUDING drafts (from the storage listing, not the complete-only manifest). Token-gated. |
| GET | `/api/editor/kits/{kit_id}/schema`, `.../pdf` | Draft-capable single-kit reads for the hosted editor. Token-gated. |
| GET | `/api/editor/kits/{kit_id}/archive`, `.../archive/{marker}/schema` | The editor's archive reads (bd qfyxr): superseded revisions newest-first + one revision's schema, READ-ONLY (returning to an old revision goes through draft/publish, never the archive). Token-gated. |
| PUT | `/api/editor/kits/{kit_id}/schema` | Save an edited schema back to the store (lenient draft save). Token-gated. |
| POST | `/api/editor/lint`, `/api/editor/kits/{kit_id}/lint` | Lint the POSTED (possibly-unsaved) schema over the single Python ruleset (`backend/services/schema_lint.py`). The kit-scoped form additionally loads the kit's persisted `acroform.json` dump -- the SAME inputs as the `/status` promotion gate -- so the editor strip sees the dump-gated widget-claim rules live (sprint-18 C1, bd o7y9); the dumpless form remains for schemas with no kit identity. Token-gated. |
| POST | `/api/editor/kits/{kit_id}/status` | Set `draft` \| `submitted` \| `complete` \| `unpublished`. **THE ROLE DEPENDS ON THE TRANSITION, not the route** (bd polyglot-pdf-hqztg): an EDITOR may `draft -> submitted` ("I believe this is ready") and reopen their own submission, but publishing (`-> complete`) and reaching back into a LIVE kit (`complete -> draft`) are AUTHOR-ONLY -- editors are subcontractors, so marking a form ready must not release it. `submitted` is write-locked like complete, or an author would review one version and publish another; the editor reopens it deliberately via Revert to draft, which CLEARS any author version (a submitted kit was never live, so no confirmation record names it). Promotion validates against the Pydantic `FormSchema` AND requires zero schema-lint ERRORs (`backend/services/schema_lint.py`; violations 409 naming the findings -- bd h76m.5). `unpublished` retires a superseded revision: hidden like a draft but WRITE-LOCKED like complete, and never revertible to draft (bd polyglot-pdf-6dz0). Optional `replaces_kit_id` retires another live kit for the same form as part of this publish, archiving it first. A kit whose schema has no `form_metadata.edition_date` must supply `author_version` to publish -- the refusal is a 422 prefixed `AUTHOR_VERSION_REQUIRED:`, which the editor keys on to open its version dialog; the value is normalized server-side and IMMUTABLE once published (bd polyglot-pdf-xzw5). Token-gated. |
| GET | `/api/editor/kits/{kit_id}/retire-candidates` | Live kits that plausibly serve the SAME FORM as this one, so the publish modal can ask which older version to retire (bd polyglot-pdf-bdedm). A SUGGESTION -- it retires nothing; the author ticks one and it rides the publish as `replaces_kit_id`. AUTHOR-ONLY, matching the publish it feeds. Matches on `form_number` first (a declared mismatch DECIDES -- it never falls through to the label, or an identical label would override two different numbers and offer I-130A when publishing I-130), then EXACT normalised label equality. Deliberately conservative: real form families differ by a one-character suffix and several variants are supplements filed ALONGSIDE their base, so a missed suggestion costs one manual retire while a wrong one asks an author to retire a live form. Each candidate carries kit id, label, form number and whichever revision marker it actually has (`edition_date` > `author_version` > `published_at`), plus WHY it matched, so a human can tell two same-numbered kits apart. Reads one schema per live kit -- confined to this route so the cost lands only when an author is publishing, never on a catalogue render. Token-gated. |
| POST | `/api/editor/kits/{kit_id}/lock` | Take a kit for editing (bd polyglot-pdf-hqztg). An AUTHOR can always take a lock back from an editor; the reverse 409s. That preemption IS the stale-lock release -- there is no timer, because a clock that steals from someone actively working is worse than a human deciding to take it. ROLE-scoped, not user-scoped: the editor API has only two shared tokens, so two editors sharing one still collide with each other (bd polyglot-pdf-ijntk lifts that). Same-role contention is allowed rather than pretended about. Returns `{ok, kitId, heldBy, preempted}`. Token-gated. |
| DELETE | `/api/editor/kits/{kit_id}/lock` | Release a kit. An author may release anyone's lock; an editor cannot evict an author -- that is the stale-lock escape when someone closes their laptop. Token-gated. |
| DELETE | `/api/editor/kits/{kit_id}` | **AUTHOR ONLY** -- permanently remove a kit and everything under it, ARCHIVES INCLUDED (bd polyglot-pdf-6x1j). The guard has THREE outcomes, not two: confirmation records name the kit -> 409 offering unpublish; no records and the check SUCCEEDED -> deleted; the check could not run -> 409 refusing. That last case is why this is safe -- the record sink is Firestore (`CONFIRMATION_FIRESTORE_ENABLED`, default false, set by `deploy-all.sh`), and its local JSONL fallback dies with the instance, so silence there is not evidence of absence. Editors are refused server-side, not merely hidden from in the UI. |
| POST | `/api/editor/kits/{kit_id}/readiness` | Recompute + persist the kit's readiness stamp for the POSTED schema (the local-save stamp refresher, sprint-18 C4b bd na1zy; same `_stamp_readiness` as the hosted save). 409 on write-locked kits (submitted, complete or unpublished) -- a published revision's stamp only changes through the publish flow. Token-gated. `backend/routes/editor_readiness_routes.py`. |
| POST | `/api/editor/kits` | Author-tier onboarding: multipart PDF upload -> new draft kit in the store. Author token only. |
| POST | `/api/editor/kits/{kit_id}/extract` | Author-tier hosted extraction: runs the PDF->schema pipeline server-side (EXTRACTOR_MODEL, minutes-long, serialized per instance). 409 on any write-locked kit -- complete OR unpublished -- with a revert-first message (`force=true` would overwrite the published schema in place, bd polyglot-pdf-w3zw). Author token only. `translate_options` form flag (default true) also bakes option label_translations (bd 2h9j). |
| POST | `/api/editor/kits/{kit_id}/translate-options` | Author-tier standalone option-label translation bake (OPTION_TRANSLATION_MODEL, in-process, idempotent; `?force=true` retranslates after label renames; 409 on any write-locked kit -- complete OR unpublished -- bd 2h9j). Returns the verify/rectify gate's `flags` and persists them at `_bakeoff.authoring.option_translation`, where schema-lint re-emits them as WARNINGs for the editor ValidationPanel (bd 9djc). Author token only. |
| GET | `/health` | Liveness + reports active models, audio rates, limits, key-presence. |
| GET | `/version` | App version string. |
| POST | `/dev/console-log` | Dev-only console-log ingest (404 in prod; no `/api` prefix). `frontend/src/shared/devConsoleCapture.ts`, `backend/routes/dev_console_routes.py`. |

## Gotchas

- **WebSockets bypass Firebase Hosting rewrites.** `firebase.json` rewrites
  `/api/**` to Cloud Run, but Hosting doesn't proxy WebSocket upgrades, so the
  frontend connects to the Cloud Run host **directly**, not via the Hosting
  domain. The WS URL is resolved in `frontend/src/shared/config.ts`: the build-time
  `VITE_WS_URL` env var wins if set, else it falls back to `PRODUCTION_WS_URL`
  (the Cloud Run host) in prod or `ws://localhost:8000/ws/fill` in dev. The
  `/api`-prefixed WS mount exists for parity but the live client uses the direct URL.
- **The prod frontend build has a single HTML entry (`index.html`).**
  `frontend/vite.config.ts` declares no multi-page `rollupOptions.input`, so
  `vad-tuning.html` and `schema-form-demo.html` are **dev-server-only** pages
  (served by `vite dev`, absent from the deployed bundle); wire them into
  `rollupOptions.input` if a deployed variant is ever wanted. Static assets
  from `frontend/public/` (e.g. `thank-you.html`) ARE copied verbatim into
  `dist/` by the build (`publicDir`), so the deployed bundle is index.html +
  public assets -- not literally one file.
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
- **"Sections" is canon; "parts" is a distinct level, not a synonym.** The internal
  section-state vars and the token-log/handshake keys are section-canonical
  (`polyglot-pdf-gfb.4` + `polyglot-pdf-zun`). The handshake **manifest `parts` key
  keeps its name because it IS the backend wire contract** -- and its entries are
  SECTION-shaped, not `FormPart` objects (see Surface contracts, contract 2). Don't
  name new section state `part` (`standards/terminology.md`, `polyglot-pdf-m3f`).

## Surface contracts

The cross-surface data-contract map for blast-radius review: every place two
surfaces must agree on a payload shape, with the PRODUCER and CONSUMER code
site for each, and what silently breaks if they disagree. Derived from code
(bd polyglot-pdf-n18q); when this section and the code disagree, the code wins --
fix this section. **The system-wide theme: almost none of these contracts are
pinned by a shared type.** Both WS legs and the fill payload are hand-typed
dicts/object literals matched by convention; renames fail silently at runtime,
which is why every entry below names both ends.

### 1. Kit schema: editor -> store -> voice/UI

The canonical shape is Pydantic `FormSchema` (`backend/models/form_models.py:883`;
`FormField` :502, `FieldOption` :401, `FormSection` :662), with the v2 strictness
rules in `_collect_v2_problems` (:786) enforced on every `model_validate`.

- **Validation happens ONLY at the publish gate.** Draft saves
  (`save_editor_kit_schema`, `backend/routes/editor_kit_routes.py:1617-1700`)
  check just that `fields` is a list and write the raw dict via the store
  (`FormKitStore.put_schema`, `backend/services/form_kits.py:324` abstract /
  `LocalFormKitStore.put_schema` :605 local / `GCSFormKitStore.put_schema`
  :1172 GCS). The one chokepoint is "mark complete":
  `FormSchema.model_validate` at `editor_kit_routes.py:2809` plus the
  zero-ERROR schema-lint gate
  (`lint_schema`, `backend/services/schema_lint.py:833`, checked at
  `editor_kit_routes.py:2841-2852`). Every read path streams the raw stored
  dict unvalidated (`get_form_kit_schema`,
  `backend/routes/form_kit_routes.py:233-257`; `get_editor_kit_schema`,
  `editor_kit_routes.py:1567-1568`). *Breaks if bypassed:* a hand-edited or
  draft kit reaching the voice path carries whatever shape it has -- e.g. a
  field without `pdf_field_name` is silently never written to the output PDF.
- **The frontend type is a hand-maintained mirror.**
  `frontend/src/schema-forms/types/schema.ts:325` (`interface FormSchema`)
  mirrors `form_models.py` with no codegen or sync check, and the SPA casts the
  fetched JSON without runtime validation
  (`frontend/src/schema-forms/SchemaFormDemo.tsx:173`). *Breaks if drifted:* the
  TS side reads `undefined` where the backend added/renamed a key -- no error,
  just missing UI behavior.
- **Load-bearing keys** (producer = `form_models.py` field; consumers listed).
  Bare filenames below are the `backend/` paths named earlier in this contract --
  note two of them have same-named siblings elsewhere in the repo:
  `form_models.py` is `backend/models/` (NOT
  `scripts/bakeoff/prior_extractor/`), and `secretary_context.py` is
  `backend/services/` (NOT `backend/scripts/`):
  - `id`: keyed into the secretary index
    (`backend/services/secretary_context.py:69`) and the frontend
    manifest-generation lookup
    (`frontend/src/schema-forms/utils/manifestUtils.ts:63`,
    `schema.fields.find` by id). Duplicate ids silently drop a field (dict
    overwrite); an unknown id returns `undefined`.
  - `pdf_field_name` (field- and option-level): consumed only by the fill route
    (`backend/routes/pdf_fill_routes.py:115-117`, options :434-442). Missing =
    field silently absent from the filled PDF.
  - `name` vs `spoken_name`: guidance builds speak
    `spoken_name || name || id` (`backend/services/manifest_service.py:125`).
    Swapped/empty values degrade to reading raw labels aloud, no error.
  - `options[]`: the model-facing path SANITIZES options to
    `value/label/spoken_label` only (`manifest_service.py:26-46`) -- the
    PDF-facing keys (`pdf_field_name`, `pdf_on_value`) are deliberately hidden
    from the voice model and consumed only by `pdf_fill_routes.py`. The two
    consumers read disjoint key sets of the same objects.
  - `help.instructions/format_hint/details`: consumed by
    `manifest_service.py:114-153` and `secretary_context.py:186-188`.
    `help.details` is model-facing ONLY, never rendered on-screen
    (`form_models.py:386-394`) -- an author who mistakes it for screen help ships
    invisible-to-UI text straight to the model.
  - `label_translations` / `spoken_name_translations`: baked keyed on
    **lowercase spoken-language name** (`backend/services/option_translation.py:209`),
    read back at session time via `_kit_translation` (:110), which also tolerates
    the language's short code and full BCP-47 code, case-insensitively (:89-107).
    The drift that DOES silently revert a string to English is a key outside that
    tolerated set -- e.g. a bare ISO-639-1 code whose BCP-47 stem differs
    (`zh` for Chinese, whose accepted stem is `cmn`). Applied in
    `manifest_service.py`: spoken-name overrides at :126-127, option-label
    overrides at :165-166 (deliberately AFTER `_sanitize_options`, so they hit
    the model-facing dicts).
  - `show_if`/`require_if` conditions: normalized by TWIN implementations --
    Python `iter_condition_atoms` (`form_models.py:345`) and TS
    `normalizeToComposite`
    (`frontend/src/schema-forms/utils/normalizeToComposite.ts:73`, hand-duplicated
    again into `schema-editor/src/utils/`). No build-time guard; a one-sided
    patch makes editor preview and live form diverge on show/hide.
  - `form_metadata` (`form_number`, `edition_date`, `details`, `booklet_text`):
    consumed by the secretary reference block (`secretary_context.py:220-243`)
    and the audit-trail edition marker
    (`backend/services/form_filling_service.py:362-368`). The key is
    `form_metadata`, NOT `metadata` -- the wrong name no-ops the whole reference
    block with zero signal (in-source note at `secretary_context.py:227-230`).
  - Legacy `controls_fields`/`conditional_fields`: REMOVED from the model and
    `extra="ignore"`-dropped by Pydantic (`form_models.py:942-957`); only
    schema-lint (`schema_lint.py:891-902`) errors on them. A stale kit that skips
    lint publishes with its trigger-side behavior silently deleted.

### 2. WS handshake: client -> backend (`/ws/fill` first frame)

Producer: `getHandshakePayload` (legacy, `frontend/src/schema-forms/state/schemaFormState.ts:955`)
/ `getJITHandshakePayload` (DTI, :999), sent by `frontend/src/webFormConnection.ts:641`.
Consumer: `fill_form_from_schema` (`backend/routes/websocket_routes.py:993`;
handshake keys parsed :1061-1185).
**No Pydantic model or TS interface pins this shape** -- every key is read with
`.get()` and a default, so a renamed key silently degrades (e.g. a dropped
`form_metadata.form_number` logs `form_id="unknown"` in the audit trail; a
dropped `kit_id` instead degrades to `kit_id=None`, a separate field).

- Key keys: `type` (`handshake` vs `handshake_jit` switches the whole parse,
  :1061), `manifest`/`first_field_schema`/`loaded_field_ids` (JIT, :1076-1078),
  `current_values` (:1149), `fill_language`/`spoken_language` (:1150/:1158),
  `kit_id`/`form_number`/`edition_date` (:1072/:1090/:1099 -- the audit-trail
  identity), `resume` (:1185).
- `full_schema` (sent at `schemaFormState.ts:979`/`:1054`): type-checked
  `isinstance(dict)` only (`websocket_routes.py:1169-1170`), cached in
  `form_filling_service.py:296` (preserved across internal restarts), then read
  by `handle_ask_secretary` (`form_filling_service.py:1612`, schema read at
  `:1666`) and rendered into the secretary catalog by
  `render_static_catalog(schema)` in `text_ai_gemini.py:302`, the edition fingerprint
  (`resolve_edition_marker` call at `form_filling_service.py:396`), the injection
  budget (`form_filling_service.py:513-514`), and runtime translation overrides
  (`_maybe_start_option_translation` call at `form_filling_service.py:464` ->
  `option_translation.py`). *Breaks if malformed:* each consumer degrades
  independently and silently (secretary falls back to per-section schema, audit
  edition falls back to a fingerprint, translations revert to English).
- The JIT `manifest.parts` key is the wire contract and its entries are
  SECTION-shaped (`frontend/src/schema-forms/utils/manifestUtils.ts:38-41`;
  consumed at `websocket_routes.py:1110` (synthesized schema) and `:1139`
  (session-start log line)). Do not "fix" the name and do not expect
  `FormPart` objects in it.

### 3. WS control messages: client <-> backend (post-handshake)

Client->server: one `if mtype == ...` switch at `websocket_routes.py:476-965`.
Server->client: one dispatch switch at `frontend/src/webFormConnection.ts:659-854`.
Message senders are object literals; a renamed `type` logs
`unknown_control_message_type` (or falls to the TS `default`) and a renamed
sub-key reads as absent. The request/response pairs ride
`backend/services/request_coordinator.py` with a `request_id` round-trip:
`get_form_state`/`form_state_response` (`request_form_state` :151 /
`handle_form_state_response` :661),
`get_next_field_hint`/`next_field_hint_response` (`request_next_field_hint`
:214 / `handle_next_field_hint_response` :687),
`confirm_field`/`confirm_field_response` (`request_confirm_field` :279 /
`handle_confirm_field_response` :725),
`skip_field`/`skip_field_response` (`request_skip_field` :364 /
`handle_skip_field_response` :751),
`switch_field`/`switch_field_response` (`request_switch_field` :427 /
`handle_switch_field_response` :775),
`spellback`/`spellback_response` (bd polyglot-pdf-22h1f; flag-gated, the ONE
round-trip that deliberately holds the pending tool response for the client's
blocking TTS clip playback, 90s cap). Client reply builders:
`webFormConnection.ts:3197` (`sendConfirmFieldResponse`) / :3318
(`sendSkipFieldResponse`), :2502 (`sendSwitchFieldResponse`), :3295
(`sendSpellbackResponse`).

Known traps (all deliberate, all pinned only by comments):
- The frontend still carries a dead `case "field_update"`
  (`webFormConnection.ts:664-666`, expecting an `updates: Record<name, value>`
  shape) with **no live backend producer** -- field updates ride `form_updated`
  (`backend/services/callback_handler.py:242`) with a different
  `data.form_state`/`data.applied_fields` shape. Never reintroduce a
  `field_update` producer against the old shape.
- `change_spoken_language` is a wire-compat misnomer -- it re-asserts the pinned
  session language, it does not change it (`websocket_routes.py:709` arm).
- `validation_result` carries `conflicts` only; the Python-side `result_type`
  label is deliberately never serialized (`websocket_routes.py:337-367`,
  contract pinned in `standards/validation-delegation.md`).
- The `session_ready` message's `native_vad` flag (`websocket_routes.py:1226-1245`)
  must agree with the backend's `DISABLE_GEMINI_VAD` -- the client picks its
  activity-signal behavior from it (`webFormConnection.ts:864,951` ->
  `onNativeVadMode` at `frontend/src/shared/connection.ts:535`).

### 4. Backend <-> Gemini Live (tools + session config)

Tool names + arg schemas have ONE source of truth:
`Settings.TOOL_DECLARATIONS` (`backend/config.py:588-816`), deep-copied into the
live config by `form_filling_service.py:222-228` (which drops `switch_section`
in continuous mode -- the session ships 6 declarations, not 7 -- and appends
the flag-gated `SPELLBACK_TOOL_DECLARATION` as a 7th only while
`SPELLBACK_TOOL_ENABLED`, bd polyglot-pdf-22h1f) and declared to
Gemini in `_build_live_config` (`backend/adapters/live_ai_gemini.py:1722`;
tools assembled at :1752). Gemini's tool
calls come back through the adapter (`self._on_tool_call(...)` call sites at
`live_ai_gemini.py:2736` and `:2917`)
into `CallbackHandler.on_tool_call` (`backend/services/callback_handler.py:448`),
which dispatches to the `form_filling_service` handlers that emit the Leg-A
client messages above. The coupling table (tool -> handler -> client message):

| Gemini tool (args) | Handler (`callback_handler.py`, dispatch branch) | Client message |
|---|---|---|
| `update_form_fields` (`field_id`, `value`) | :507 | `form_updated` |
| `get_form_status` (`field_ids`) | :510 | `get_form_state` round-trip |
| `confirm_field` (`field_id`, `confirmation_method`) | :522 | `confirm_field` round-trip |
| `skip_field` (`field_id`) | :525 | `skip_field` round-trip |
| `switch_to_field` (`field`) | :531 | `switch_field` round-trip -- **the tool name and the wire type differ on purpose** |
| `ask_secretary` (`query`) | :534 | none -- answered server-side from the cached `full_schema` |
| `switch_section` (deprecated; dropped in continuous mode) | :516 | internal session restart + `section_switched` |
| `name_spellback` (no args; FLAG-GATED `SPELLBACK_TOOL_ENABLED`, declared only while on via `SPELLBACK_TOOL_DECLARATION`) | `_handle_name_spellback_tool` | `spellback` round-trip + client HTTP `POST /api/tts/spellback` (bd polyglot-pdf-22h1f) |

Field values never cross to Gemini as structured data -- they are rendered into
guidance prose by `ai_context.render_field_guidance`
(`backend/services/ai_context.py:79`); the contract there is between the SI
templates and the prose, not key names. System instruction:
`form_filling_service.build_form_context_message`
(`form_filling_service.py:1214`) ->
`ai_context.build_form_context` (:444).

### 5. Fill round-trip: sessionStorage -> `/api/fill-pdf` -> AcroForm

Producer: client state `SchemaFormState.fieldValues`
(`frontend/src/schema-forms/state/schemaFormState.ts:27`, persisted :248-263).
THREE call sites assemble the request -- download and print
(`frontend/src/schema-forms/components/SchemaForm.tsx:610-646` and :650-678)
plus the in-browser preview
(`frontend/src/pdf-view/FilledPreviewModal.tsx:62`, with its own unwrap loop
:57-60). All run every value through `unwrapFieldValue`
(`frontend/src/schema-forms/utils/fieldValue.ts:369`) --
**dropping `confirmed`/`skipped`/`steered` flags entirely** -- and POST
`{kit_id, pdf_filename, field_values, form_schema}`
(`frontend/src/schema-forms/utils/pdfFiller.ts:98-103`). A payload-shape change
made against only one call site silently misses the other two.
Consumer: `PDFFillRequest` (`backend/routes/pdf_fill_routes.py:35-41`).

- **The backend fills from the CLIENT-SUBMITTED `form_schema`**, typed
  `Dict[str, Any]` -- no `FormSchema` validation runs at fill time, the kit
  store is consulted only for the PDF bytes (:68), and the extraction-time
  `acroform.json` ledger is never read on this path -- its readers all live on
  the editor/publish surface (`_load_kit_dump`,
  `backend/routes/editor_kit_routes.py:687`, with 7 call sites across the
  lint routes; the mark-complete promotion gate's call is inside
  `set_editor_kit_status` at :2451, feeding the pure-function
  checks in `backend/services/widget_picker.py`). *Breaks:* a stale or
  mutated client schema fills a wrong/blank field into a PDF that completes
  "successfully" -- the exact reassembles-without-error failure mode.
- Field-id -> `pdf_field_name` mapping with a two-pass `[]`-alias resolution,
  exact id always winning (`pdf_fill_routes.py:107-131`); widget dispatch by
  `field_type` (`pdf_fill_routes.py:409-681`):
  text via `fill_widget` (:217-277) with cosmetic-only Comb overflow handling
  (:157-215), checkboxes via `get_button_on_state` (:136-152, defaults to
  `"Yes"` when the widget's on-state is unreadable), v2 shared-name radios via
  direct `xref_set_key` writes (:475-476, within the wider :459-495 branch).
- A skipped field arrives as bare `null` (the `skipped` flag was unwrapped away)
  and is indistinguishable from never-asked -- both are silently omitted
  (`pdf_fill_routes.py:410-412`).
- `NeedAppearances` is deliberately NOT set (`pdf_fill_routes.py:691-697`); appearance regeneration
  is left to the viewer. Verify checkbox/radio fixes by RENDERING the page, not
  by reading values back.

### 6. Confirmation audit trail

The chain: Gemini `confirm_field` tool -> backend request
(`request_coordinator.py:279`, `request_confirm_field`) -> client verifies it
has a usable value and acks (`webFormConnection.ts:1924`,
`handleConfirmFieldRequest`; reply built by `sendConfirmFieldResponse` at
:3197 -- `reason` is a fixed category token, never a field value) -> backend
logs ONLY on a positive ack (the `recorded` guard at
`callback_handler.py:961`; the `log_field_confirmation` call it protects at
:1000-1009). Event shape (NO PII, no `value` key anywhere):
`backend/utils/confirmation_logger.py:341-356` --
`{timestamp, event, form_id, kit_id, edition_date, firm_id, form_session_id,
field_id, field_name, confirmation_method}` (`firm_id` joined under bd
polyglot-pdf-xwlt -- the CUSTOMER FIRM from the verified token claim, never a
client identifier). Sinks: structured log (:363-366), local
JSONL (`_write_confirmation_to_file` :374-389, dies with the instance),
Firestore `confirmation_events` (`_firestore_write` :88-117, gated by
`CONFIRMATION_FIRESTORE_ENABLED`, optional `expire_at` TTL). The
identity keys (`kit_id`, `form_number`, `edition_date`) originate in the
handshake -- sent by the JIT builder at `schemaFormState.ts:1075` (form_number),
`:1088` (kit_id), `:1089` (edition_date), read at
`websocket_routes.py:1090`/`:1072`/`:1099` respectively -- see contract 2. The
`edition_date` COLUMN carries whichever revision marker won
`resolve_edition_marker`'s three-rank precedence: the government
`edition_date`, else the author's `author_version`, else a `sha256:` shape
fingerprint (bd polyglot-pdf-xzw5) -- so the name is narrower than the values
it holds. The SAME sink also carries two SESSION records per voice session
(`form_session_started` / `form_session_ended`, wired from
`_handle_fill_session` under bd polyglot-pdf-xwlt), keyed on the same
`firm_id` + `kit_id` so per-firm usage spans sessions and confirmations in one
equality query; the end record carries a confirmed-field COUNT, never values.
*Known gap:* a
lost/timed-out ack leaves NO audit record for a confirmation the user saw
succeed on screen (by design -- never log a confirmation that didn't happen).

### 7. Firm-scoped kit visibility (bd polyglot-pdf-vccy)

Four coupled contracts make a PRIVATE kit invisible outside its firm yet fully
usable inside it. The gates live in **`backend/services/kit_gates.py`**,
shared by EVERY client-tier kit read -- the set is exactly four sites (the
catalogue list, the schema GET, the pdf GET, and `POST /api/fill-pdf`'s kit
read; bd polyglot-pdf-vy6id caught the fourth ungated), and
`test_http_route_auth.py::test_every_client_tier_kit_read_is_visibility_gated`
pins the SET so a fifth read site fails CI instead of shipping ungated
(`/api/editor/*` is deliberately outside it -- contractor tooling behind role
tokens, not the client tier):

- **Kit metadata keys** `visibility: "public" | "private"` + `owner_firm_id`
  (snake_case in `metadata.json`; absence = public, anything but the exact
  string `"private"` coerces public). Producer: the kit's `metadata.json`
  (hand-authored / future publish UI). Consumers: the gates read LIVE
  metadata -- ONE `load_live_metadata` read per request feeds both the
  publish and visibility gates (`kit_gates.py:28`; visibility coercion
  `kit_visibility` `:84`; the manifest copy is deploy-time stale in GCS) --
  and the store passes normalized `visibility` / `ownerFirmId` through both
  manifest paths (`form_kits.py:226` normalize, `:516` local synthesis).
  `owner_firm_id` is bookkeeping for the firm write path (bd z6bk9), NOT the
  read gate.
- **The firm allowlist**: `firms/{firm_id}.allowed_kits` (producer:
  `scripts/bootstrap_firm.py`) -> `firms.get_allowed_kits`
  (`backend/services/firms.py:55`, fail-closed `[]`) -> resolved per request
  off the `firm_id` ID-token claim (`kit_gates.py:67`, `firm_allowed_kits`;
  run off the event loop) -> enforced by `require_visible` (`:99`, 404 =
  invisibility) on the schema + pdf + fill reads
  (`pdf_fill_routes.py:82`) and by the list filter inside `list_form_kits`
  (`form_kit_routes.py:127`). The pdf route parses its bearer token
  OPTIONALLY (`:293`); an invalid token degrades to anonymous rather
  than 401.
- **The private-path rewrite**: `list_form_kits` (`form_kit_routes.py:193`)
  rewrites a private kit's `schema_path`/`pdf_path` to the authenticated
  backend routes (`/api/form-kits/<id>/schema|pdf`) because the static
  Hosting bundle excludes private kits (bd kkos:
  `kitPublishFilter.isPubliclyServable` ships only complete AND
  demonstrably-public -- absence or the exact string `"public"`;
  deliberately stricter than the routes' anything-but-"private" coercion,
  because this surface's failure is an irreversible public leak).
  Consumers: `SchemaFormDemo`'s schema fetch
  and `usePDFDocument`'s pdf fetch resolve `/api/` paths against the backend
  base and attach the Bearer token (`usePDFDocument.ts:60` fetch-to-blob;
  `resolveKitAssetUrl`, `pdfFiller.ts:59` -- a relative `/api/` fetch works on
  Hosting via the rewrite but not against the Vite dev server).
- **Explicit filenames** `schema_file`/`pdf_file` on `FormKitInfo`
  (`form_kit_routes.py:117`): under rewritten paths the URL's last segment is
  a literal route word, so the client must STOP deriving filenames by URL
  split. Consumers: `SchemaFormDemo.tsx:114`/`:116` (manifest mapping) and
  `fillPDF`'s explicit `pdfFile` param (`pdfFiller.ts:117` -- the fill POST's
  `pdf_filename` feeds `store.load_pdf_bytes`, contract 5). Breaking either
  half strands a private kit's fill/download while every public-kit test
  stays green.

### 8. Intro agree-label mirror (bd polyglot-pdf-s1iex.3)

Producer: `backend/services/intro_agree_labels.json` (18 language ->
agree-label entries). Consumer: `BUTTON_TRANSLATIONS` in
`frontend/src/schema-forms/components/DisclaimerModal.tsx:38`. The backend
label is INTERPOLATED INTO SPOKEN AUDIO -- `intro_tts.build_intro_text`
replaces the `[AGREE LABEL]` placeholder (`intro_tts.py:76`) with the
backend's copy of the label -- so a drift means Sol speaks a button name
that is not the one on screen. Pinned by
`backend/tests/unit/test_intro_route.py::TestIntroTables::test_agree_labels_match_frontend_mirror`.

### 9. `LIVE_VOICE_NAME` two-consumer coupling (bd polyglot-pdf-22h1f/44ywm)

`Settings.LIVE_VOICE_NAME` (`backend/config.py:360`) has TWO independent
consumers in different surfaces, so changing the env var moves both at
once:

- `backend/adapters/live_ai_gemini.py:1866` -- the Gemini Live session's
  `speech_config.voice_config.prebuilt_voice_config.voice_name`. An
  unaccepted name is a hard `1007 Invalid voice name` at connect that
  breaks EVERY session.
- `backend/services/spellback_tts.py:269`
  (`resolve_spellback_voice`) -- the PERSONA half of the spell-back clip's
  Cloud TTS voice (`{locale}-Chirp3-HD-{persona}`), which in turn selects
  the clip's loudness gain via `spellback_gain_db` /
  `_MEASURED_GAIN_DB` (`spellback_tts.py:91-98`).

Full detail: [`components/voice-ai.md`](components/voice-ai.md), which has
its own "`LIVE_VOICE_NAME` has a SECOND consumer" section.
