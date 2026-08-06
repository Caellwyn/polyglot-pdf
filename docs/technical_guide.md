# Technical guide -- polyglot-pdf

*Last updated: 2026-08-06 (bd polyglot-pdf-n18q: the Surface contracts section --
the code-derived cross-surface data-contract map for blast-radius review).
Continuous-DTI is the production default (`USE_DTI` / `CONTINUOUS_SESSION` /
`CONTEXT_COMPRESSION_ENABLED` all default true, bd polyglot-pdf-7872;
section-reset is the deprecated fallback, bd polyglot-pdf-55jg). This guide lists
the deploy flow + env vars; per-channel model/auth config detail lives in
[standards/ai-models.md](standards/ai-models.md) and
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

Two Firebase projects: demo and production (frontend picks the backend by the
Cloud Run host it's built against). Backend config is env-driven via
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
| POST | `/api/fill-pdf` | Render the filled PDF (PyMuPDF). **Auth-gated** (`Authorization: Bearer <idToken>` via `require_auth`; bd z2is). `components/pdf-filling.md` |
| POST | `/api/disclaimer-acceptance` | Log disclaimer acceptance (anonymized; client IP deliberately NOT logged, bd z2is). `standards/confirmation-and-audit.md` |
| GET | `/api/form-kits` | Form-kit manifest (metadata only; GCS/deployed manifest is complete-only, local mode lists any kit with a schema). **Auth-gated** (bd z2is). `components/pdf-filling.md` |
| GET | `/api/form-kits/{kit_id}/schema` | A single kit's schema JSON, streamed from the store (works local + gcs; `no-store`). **Auth-gated** (bd z2is). |
| GET | `/api/form-kits/{kit_id}/pdf` | A single kit's PDF bytes, streamed from the store. **Deliberately public** (no frontend consumer loads this route -- the viewer fetches the STATIC `/form-kits/...` copy; the same public-form bytes ship in the static bundle regardless -- bd z2is). |
| GET | `/api/editor/session` | Hosted-editor access-code probe -> `{role}`. Token-gated (`X-Editor-Token`); the whole `/api/editor/*` surface is 503 when no token is configured. `components/pdf-filling.md` |
| GET | `/api/editor/kits` | Editor kit list INCLUDING drafts (from the storage listing, not the complete-only manifest). Token-gated. |
| GET | `/api/editor/kits/{kit_id}/schema`, `.../pdf` | Draft-capable single-kit reads for the hosted editor. Token-gated. |
| PUT | `/api/editor/kits/{kit_id}/schema` | Save an edited schema back to the store (lenient draft save). Token-gated. |
| POST | `/api/editor/lint`, `/api/editor/kits/{kit_id}/lint` | Lint the POSTED (possibly-unsaved) schema over the single Python ruleset (`backend/services/schema_lint.py`). The kit-scoped form additionally loads the kit's persisted `acroform.json` dump -- the SAME inputs as the `/status` promotion gate -- so the editor strip sees the dump-gated widget-claim rules live (sprint-18 C1, bd o7y9); the dumpless form remains for schemas with no kit identity. Token-gated. |
| POST | `/api/editor/kits/{kit_id}/status` | Flip draft/complete; promotion validates against the Pydantic `FormSchema` AND requires zero schema-lint ERRORs (`backend/services/schema_lint.py`; violations 409 naming the findings -- bd h76m.5). Token-gated. |
| POST | `/api/editor/kits` | Author-tier onboarding: multipart PDF upload -> new draft kit in the store. Author token only. |
| POST | `/api/editor/kits/{kit_id}/extract` | Author-tier hosted extraction: runs the PDF->schema pipeline server-side (EXTRACTOR_MODEL, minutes-long, serialized per instance). Author token only. `translate_options` form flag (default true) also bakes option label_translations (bd 2h9j). |
| POST | `/api/editor/kits/{kit_id}/translate-options` | Author-tier standalone option-label translation bake (OPTION_TRANSLATION_MODEL, in-process, idempotent; `?force=true` retranslates after label renames; 409 on complete kits -- bd 2h9j). Returns the verify/rectify gate's `flags` and persists them at `_bakeoff.authoring.option_translation`, where schema-lint re-emits them as WARNINGs for the editor ValidationPanel (bd 9djc). Author token only. |
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
  (`backend/routes/editor_kit_routes.py:602-646`) check just that `fields` is a
  list and write the raw dict via the store (`backend/services/form_kits.py:353`
  local / :565 GCS). The one chokepoint is "mark complete":
  `FormSchema.model_validate` at `editor_kit_routes.py:1530` plus the zero-ERROR
  schema-lint gate (`backend/services/schema_lint.py:776`, checked at
  `editor_kit_routes.py:1571-1600`). Every read path streams the raw stored dict
  unvalidated (`backend/routes/form_kit_routes.py:194`,
  `editor_kit_routes.py:553`). *Breaks if bypassed:* a hand-edited or draft kit
  reaching the voice path carries whatever shape it has -- e.g. a field without
  `pdf_field_name` is silently never written to the output PDF.
- **The frontend type is a hand-maintained mirror.**
  `frontend/src/schema-forms/types/schema.ts:325` (`interface FormSchema`)
  mirrors `form_models.py` with no codegen or sync check, and the SPA casts the
  fetched JSON without runtime validation
  (`frontend/src/schema-forms/SchemaFormDemo.tsx:173`). *Breaks if drifted:* the
  TS side reads `undefined` where the backend added/renamed a key -- no error,
  just missing UI behavior.
- **Load-bearing keys** (producer = `form_models.py` field; consumers listed):
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

Producer: `getHandshakePayload` (legacy, `frontend/src/schema-forms/state/schemaFormState.ts:929`)
/ `getJITHandshakePayload` (DTI, :973), sent by `frontend/src/webFormConnection.ts:595`.
Consumer: `fill_form_from_schema` (`backend/routes/websocket_routes.py:976`;
handshake keys parsed :1044-1168).
**No Pydantic model or TS interface pins this shape** -- every key is read with
`.get()` and a default, so a renamed key silently degrades (e.g. a dropped
`kit_id` logs `form_id="unknown"` in the audit trail).

- Key keys: `type` (`handshake` vs `handshake_jit` switches the whole parse,
  :1044), `manifest`/`first_field_schema`/`loaded_field_ids` (JIT, :1059-1061),
  `current_values` (:1132), `fill_language`/`spoken_language` (:1133/:1141),
  `kit_id`/`form_number`/`edition_date` (:1055/:1073/:1082 -- the audit-trail
  identity), `resume` (:1168).
- `full_schema` (sent at :953/:1028): type-checked `isinstance(dict)` only
  (`websocket_routes.py:1152-1154`), cached in
  `form_filling_service.py:289-290` (preserved across internal restarts), then
  consumed by the secretary catalog (:1617 ->
  `secretary_context.py:246`), the edition fingerprint (:367-368), the injection
  budget (:478-479), and runtime translation overrides (:678 ->
  `option_translation.py`). *Breaks if malformed:* each consumer degrades
  independently and silently (secretary falls back to per-section schema, audit
  edition falls back to a fingerprint, translations revert to English).
- The JIT `manifest.parts` key is the wire contract and its entries are
  SECTION-shaped (`frontend/src/schema-forms/utils/manifestUtils.ts:38-41`;
  consumed at `websocket_routes.py:1093-1122`). Do not "fix" the name and do not
  expect `FormPart` objects in it.

### 3. WS control messages: client <-> backend (post-handshake)

Client->server: one `if mtype == ...` switch at `websocket_routes.py:476-956`.
Server->client: one dispatch switch at `frontend/src/webFormConnection.ts:612-782`.
Message senders are object literals; a renamed `type` logs
`unknown_control_message_type` (or falls to the TS `default`) and a renamed
sub-key reads as absent. The request/response pairs ride
`backend/services/request_coordinator.py` with a `request_id` round-trip:
`get_form_state`/`form_state_response` (:172/:566),
`get_next_field_hint`/`next_field_hint_response` (:237/:592),
`confirm_field`/`confirm_field_response` (:314/:630),
`skip_field`/`skip_field_response` (:390/:656),
`switch_field`/`switch_field_response` (:454/:680). Client reply builders:
`webFormConnection.ts:2908-2950` (confirm/skip), :2290 (switch).

Known traps (all deliberate, all pinned only by comments):
- The frontend still carries a dead `case "field_update"`
  (`webFormConnection.ts:617-619`, expecting an `updates: Record<name, value>`
  shape) with **no live backend producer** -- field updates ride `form_updated`
  (`backend/services/callback_handler.py:231`) with a different
  `data.form_state`/`data.applied_fields` shape. Never reintroduce a
  `field_update` producer against the old shape.
- `change_spoken_language` is a wire-compat misnomer -- it re-asserts the pinned
  session language, it does not change it (`websocket_routes.py:692-723`).
- `validation_result` carries `conflicts` only; the Python-side `result_type`
  label is deliberately never serialized (`websocket_routes.py:336-361`,
  contract pinned in `standards/validation-delegation.md`).
- The `session_ready` message's `native_vad` flag (`websocket_routes.py:1209-1229`)
  must agree with the backend's `DISABLE_GEMINI_VAD` -- the client picks its
  activity-signal behavior from it (`frontend/src/shared/connection.ts:508-516`).

### 4. Backend <-> Gemini Live (tools + session config)

Tool names + arg schemas have ONE source of truth:
`Settings.TOOL_DECLARATIONS` (`backend/config.py:456-674`), deep-copied into the
live config by `form_filling_service.py:219-229` (which drops `switch_section`
in continuous mode -- the session ships 6 declarations, not 7) and declared to
Gemini in `_build_live_config` (`backend/adapters/live_ai_gemini.py:1632`;
tools assembled at :1645). Gemini's tool
calls come back through the adapter (`live_ai_gemini.py:2398-2585` and :2592+)
into `CallbackHandler.on_tool_call` (`backend/services/callback_handler.py:418`),
which dispatches to the `form_filling_service` handlers that emit the Leg-A
client messages above. The coupling table (tool -> handler -> client message):

| Gemini tool (args) | Handler (`callback_handler.py`) | Client message |
|---|---|---|
| `update_form_fields` (`field_id`, `value`) | :507 | `form_updated` |
| `get_form_status` (`field_ids`) | :648 | `get_form_state` round-trip |
| `confirm_field` (`field_id`, `confirmation_method`) | :840 | `confirm_field` round-trip |
| `skip_field` (`field_id`) | :1098 | `skip_field` round-trip |
| `switch_to_field` (`field`) | :1239 | `switch_field` round-trip -- **the tool name and the wire type differ on purpose** |
| `ask_secretary` (`query`) | :710 | none -- answered server-side from the cached `full_schema` |
| `switch_section` (deprecated; dropped in continuous mode) | :692 | internal session restart + `section_switched` |

Field values never cross to Gemini as structured data -- they are rendered into
guidance prose by `ai_context.render_field_guidance`
(`backend/services/ai_context.py:79`); the contract there is between the SI
templates and the prose, not key names. System instruction:
`form_filling_service.build_form_context_message` (:1165) ->
`ai_context.build_form_context` (:444).

### 5. Fill round-trip: sessionStorage -> `/api/fill-pdf` -> AcroForm

Producer: client state `SchemaFormState.fieldValues`
(`frontend/src/schema-forms/state/schemaFormState.ts:25`, persisted :250-270).
THREE call sites assemble the request -- download and print
(`frontend/src/schema-forms/components/SchemaForm.tsx:601-638` and :640-670)
plus the in-browser preview
(`frontend/src/pdf-view/FilledPreviewModal.tsx:62`, with its own unwrap loop
:58-61). All run every value through `unwrapFieldValue`
(`frontend/src/schema-forms/utils/fieldValue.ts:77-82`) --
**dropping `confirmed`/`skipped`/`steered` flags entirely** -- and POST
`{kit_id, pdf_filename, field_values, form_schema}`
(`frontend/src/schema-forms/utils/pdfFiller.ts:98-129`). A payload-shape change
made against only one call site silently misses the other two.
Consumer: `PDFFillRequest` (`backend/routes/pdf_fill_routes.py:35-45`).

- **The backend fills from the CLIENT-SUBMITTED `form_schema`**, typed
  `Dict[str, Any]` -- no `FormSchema` validation runs at fill time, the kit
  store is consulted only for the PDF bytes (:68), and the extraction-time
  `acroform.json` ledger is never read on this path -- its readers all live on
  the editor/publish surface (`_load_kit_dump`,
  `backend/routes/editor_kit_routes.py:393-396`, called from the lint routes
  and the mark-complete promotion gate at :1571, feeding the pure-function
  checks in `backend/services/widget_picker.py`). *Breaks:* a stale or
  mutated client schema fills a wrong/blank field into a PDF that completes
  "successfully" -- the exact reassembles-without-error failure mode.
- Field-id -> `pdf_field_name` mapping with a two-pass `[]`-alias resolution,
  exact id always winning (:92-134); widget dispatch by `field_type` (:409-681):
  text via `fill_widget` (:217-277) with cosmetic-only Comb overflow handling
  (:157-215), checkboxes via `get_button_on_state` (:136-152, defaults to
  `"Yes"` when the widget's on-state is unreadable), v2 shared-name radios via
  direct `xref_set_key` writes (:459-495).
- A skipped field arrives as bare `null` (the `skipped` flag was unwrapped away)
  and is indistinguishable from never-asked -- both are silently omitted
  (:410-413).
- `NeedAppearances` is deliberately NOT set (:691-697); appearance regeneration
  is left to the viewer. Verify checkbox/radio fixes by RENDERING the page, not
  by reading values back.

### 6. Confirmation audit trail

The chain: Gemini `confirm_field` tool -> backend request
(`request_coordinator.py:314-319`) -> client verifies it has a usable value and
acks (`webFormConnection.ts:1705+`, reply built :2908-2927 -- `reason` is a fixed
category token, never a field value) -> backend logs ONLY on a positive ack
(the `recorded` guard at `callback_handler.py:914`; the `log_field_confirmation`
call it protects at :944-956). Event shape (NO PII, no
`value` key anywhere): `backend/utils/confirmation_logger.py:270-285` --
`{timestamp, event, form_id, kit_id, edition_date, form_session_id, field_id,
field_name, confirmation_method}`. Sinks: structured log (:290-293), local JSONL
(:301-317, dies with the instance), Firestore `confirmation_events` (:88-119,
gated by `CONFIRMATION_FIRESTORE_ENABLED`, optional `expire_at` TTL). The
identity keys (`kit_id`, `form_number`, `edition_date`) originate in the
handshake (`schemaFormState.ts:1049-1063`) -- see contract 2. *Known gap:* a
lost/timed-out ack leaves NO audit record for a confirmation the user saw
succeed on screen (by design -- never log a confirmation that didn't happen).
