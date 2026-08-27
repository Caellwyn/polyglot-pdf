# Technical guide -- polyglot-pdf

*Last updated: 2026-08-27 (bd polyglot-pdf-vdcm4: every drifted
`websocket_routes.py:<line>` / `confirmation_logger.py:<line>` citation in
contracts 2, 3, and 6 re-anchored to a symbol/arm name instead of a line
number -- all had drifted 60-140 lines past their real targets. The editor
rows describe per-user Firebase claims, not shared tokens, per bd
polyglot-pdf-hn0jq; the lock rows are person-scoped, per bd
polyglot-pdf-5tuas.)*

The [Surface contracts](#surface-contracts) section is the code-derived
cross-surface data-contract map for blast-radius review. Continuous-DTI is the
production default (`USE_DTI` / `CONTINUOUS_SESSION` /
`CONTEXT_COMPRESSION_ENABLED` all default true; section-reset is the deprecated
fallback). This guide lists the deploy flow + env vars; per-channel model/auth
config detail lives in [standards/ai-models.md](standards/ai-models.md) and
[components/config-deployment.md](components/config-deployment.md).

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

Rows are sorted by **path, then method**, and the set is pinned against the
live app by `tests/test_technical_guide_routes_table.py`, keyed on
`(path, method)`: a shipped route with no row -- including a NEW METHOD on an
already-listed path, which needs its own row -- a row for a route that no
longer ships, and an out-of-order row each fail that test. The sort is not
cosmetic: it gives every row exactly one correct position, so two PRs adding
different routes edit different lines instead of colliding over the same
insertion point.

| Method | Path | Surface doc |
|--------|------|-------------|
| POST | `/api/disclaimer-acceptance` | Record disclaimer acceptance DURABLY (bd polyglot-pdf-0dsv4: the `confirmation_events` Firestore collection + the per-session file, keyed on `form_session_id`, not a log line -- fail-open, so a sink outage cannot block an Agree click). UNAUTHENTICATED by design (Agree fires before any session exists), so `firm_id` is always `None` here and the `form_session_id` is validated as a single safe path segment before it becomes a filename. One acceptance per `form_session_id` -- a duplicate POST is dropped silently, not errored -- except PLACEHOLDER ids (`unknown`/`undefined`/`null`/`none`/empty), which are deliberately NOT deduped (bd polyglot-pdf-g3kui: `confirmation_logger._claim_first_acceptance`); every request field is bounded at the Pydantic model so an oversized body 422s before reaching the sink. Anonymized; client IP deliberately NOT logged, bd z2is. Records `script_version` -- the hash of the exact script the user saw and heard, echoed from the intro route's `X-Intro-Script-Version` so the record names WHICH text was agreed to; `None` on the legacy model-read path -- a known audit gap, since that path still serves deterministic scripted text (bd s1iex.7, bd polyglot-pdf-pyebx). `standards/confirmation-and-audit.md` |
| GET | `/api/editor/kits` | Editor kit list INCLUDING drafts (from the storage listing, not the complete-only manifest). Token-gated. |
| POST | `/api/editor/kits` | Author-tier onboarding: multipart PDF upload -> new draft kit in the store. Author token only. |
| DELETE | `/api/editor/kits/{kit_id}` | **AUTHOR ONLY** -- permanently remove a kit and everything under it, ARCHIVES INCLUDED (bd polyglot-pdf-6x1j). The guard has THREE outcomes, not two: confirmation records name the kit -> 409 offering unpublish; no records and the check SUCCEEDED -> deleted; the check could not run -> 409 refusing. That last case is why this is safe -- the record sink is Firestore (`CONFIRMATION_FIRESTORE_ENABLED`, default false, set by `deploy-all.sh`), and its local JSONL fallback dies with the instance, so silence there is not evidence of absence. Editors are refused server-side, not merely hidden from in the UI. |
| GET | `/api/editor/kits/{kit_id}/archive`, `.../archive/{marker}/schema` | The editor's archive reads (bd qfyxr): superseded revisions newest-first + one revision's schema, READ-ONLY (returning to an old revision goes through draft/publish, never the archive). Token-gated. |
| POST | `/api/editor/kits/{kit_id}/derive-divisions` | Regenerate the kit's parts/sections deterministically (bd 6cfu.3) -- re-runs `derive_sections.derive_and_apply` on the STORED schema + PDF (widget-name conventions -> printed headings -> page fallback) and re-files every field's `section_id`. **DESTRUCTIVE to manual division edits by design**; the editor fronts it with a confirm dialog, field content untouched. Author-only; 409 on complete or on a kit with no PDF; a corrupt/0-page PDF is a 422 data defect, not a 500. |
| GET | `/api/editor/kits/{kit_id}/draft-snapshots` | Prior saved states of this kit's draft, newest-first (bd polyglot-pdf-y2l0p). EDITOR-accessible by deliberate maintainer decision (2026-08-18): routing recovery through an author means the person who lost the work cannot get it back themselves. 404 (not an empty list) for a kit that does not exist -- "no earlier versions" and "no such form" are different answers. Token-gated. |
| POST | `/api/editor/kits/{kit_id}/draft-snapshots/{snapshot_id}/restore` | Put a snapshot's schema back as the live draft. Snapshots what it REPLACES first, so restoring the wrong version is one more restore away rather than a second loss -- that is what makes it safe without an author. Refused on a write-locked kit (complete/unpublished), same as a save. Non-numeric snapshot ids 400 before reaching the store. Token-gated. |
| POST | `/api/editor/kits/{kit_id}/extract` | Author-tier hosted extraction: runs the PDF->schema pipeline server-side (EXTRACTOR_MODEL, minutes-long, serialized per instance). 409 on any write-locked kit -- complete OR unpublished -- with a revert-first message (`force=true` would overwrite the published schema in place, bd polyglot-pdf-w3zw). Author token only. `translate_options` form flag (default true) also bakes option label_translations (bd 2h9j). |
| POST | `/api/editor/kits/{kit_id}/label` | Rename a kit's DISPLAY label (bd polyglot-pdf-15ic), preserving every other metadata key (the read-merge-write shape of the status flip). Pure display -- the catalogue and form picker render it, nothing keys on it; kit identity is the immutable `kit_id`/storage path and is deliberately NOT renameable here. Exists because onboarding derives labels from PDF filenames, so nameless uploads collide into "Form", "Form 2", ... Token-gated. |
| DELETE | `/api/editor/kits/{kit_id}/lock` | Release a kit. An author may release anyone's lock; an editor may release only a lock THEY hold (bd polyglot-pdf-5tuas) -- they can neither evict an author nor free another editor's kit. Author preemption is the stale-lock escape when someone closes their laptop. Token-gated. |
| POST | `/api/editor/kits/{kit_id}/lock` | Take a kit for editing (bd polyglot-pdf-hqztg). An AUTHOR can always take a lock back from an editor; the reverse 409s. That preemption IS the stale-lock release -- there is no timer, because a clock that steals from someone actively working is worse than a human deciding to take it. USER-scoped (bd polyglot-pdf-5tuas): the lock stores the holder's uid, so a second editor is refused 409 and the refusal NAMES the holder. Re-taking your OWN lock is not a steal. A pre-5tuas lock has no uid, so same-role contention falls back to ALLOW for it rather than stranding anyone. `heldBy` stays a ROLE on the wire; `heldByLabel` carries the person. Returns `{ok, kitId, heldBy, preempted}`. Token-gated. |
| POST | `/api/editor/kits/{kit_id}/readiness` | Recompute + persist the kit's readiness stamp for the POSTED schema (the local-save stamp refresher, sprint-18 C4b bd na1zy; same `_stamp_readiness` as the hosted save). 409 on write-locked kits (submitted, complete or unpublished) -- a published revision's stamp only changes through the publish flow. Token-gated. `backend/routes/editor_readiness_routes.py`. |
| POST | `/api/editor/kits/{kit_id}/regenerate-guidance` | Re-author field guidance from the kit's instruction booklet (bd polyglot-pdf-cpiw) -- the costly half of the staleness gate, opposite "acknowledge". Optional `fieldIds` scopes the rewrite (the natural call from the staleness banner); omitted means every askable field. Guidance a HUMAN edited is never clobbered (per-channel hashes vs. provenance). A successful rewrite re-stamps `identity_sha1`, which is what CLEARS the staleness flag. Author-only (spends model tokens + rewrites the schema); 409 on complete. |
| POST | `/api/editor/kits/{kit_id}/repair` | One-click Repair-all for a stored draft (bd polyglot-pdf-zgln): runs the SAME deterministic `backend/services/schema_repair.repair()` the CLI extraction pass runs, against the schema + its persisted `acroform.json` dump, so the result equals CLI repair on the same input. Reports what changed plus POST-repair lint counts. **Author-only** (it mutates the stored schema). A draft referencing nonexistent PDF widgets is a 422 naming them, not a 500 -- repair cannot invent mappings. 409 on a complete kit. |
| GET | `/api/editor/kits/{kit_id}/retire-candidates` | Live kits that plausibly serve the SAME FORM as this one, so the publish modal can ask which older version to retire (bd polyglot-pdf-bdedm). A SUGGESTION -- it retires nothing; the author ticks one and it rides the publish as `replaces_kit_id`. AUTHOR-ONLY, matching the publish it feeds. Matches on `form_number` first (a declared mismatch DECIDES -- it never falls through to the label, or an identical label would override two different numbers and offer I-130A when publishing I-130), then EXACT normalised label equality. Deliberately conservative: real form families differ by a one-character suffix and several variants are supplements filed ALONGSIDE their base, so a missed suggestion costs one manual retire while a wrong one asks an author to retire a live form. Each candidate carries kit id, label, form number and whichever revision marker it actually has (`edition_date` > `author_version` > `published_at`), plus WHY it matched, so a human can tell two same-numbered kits apart. Reads one schema per live kit -- confined to this route so the cost lands only when an author is publishing, never on a catalogue render. Token-gated. |
| GET | `/api/editor/kits/{kit_id}/schema`, `.../pdf` | Draft-capable single-kit reads for the hosted editor. Token-gated. |
| PUT | `/api/editor/kits/{kit_id}/schema` | Save an edited schema back to the store (lenient draft save). Token-gated. |
| POST | `/api/editor/kits/{kit_id}/status` | Set `draft` \| `submitted` \| `complete` \| `unpublished`. **THE ROLE DEPENDS ON THE TRANSITION, not the route** (bd polyglot-pdf-hqztg): an EDITOR may `draft -> submitted` ("I believe this is ready") and reopen their own submission, but publishing (`-> complete`) and reaching back into a LIVE kit (`complete -> draft`) are AUTHOR-ONLY -- editors are subcontractors, so marking a form ready must not release it. `submitted` is write-locked like complete, or an author would review one version and publish another; the editor reopens it deliberately via Revert to draft, which CLEARS any author version (a submitted kit was never live, so no confirmation record names it). Promotion validates against the Pydantic `FormSchema` AND requires zero schema-lint ERRORs (`backend/services/schema_lint.py`; violations 409 naming the findings -- bd h76m.5). `unpublished` retires a superseded revision: hidden like a draft but WRITE-LOCKED like complete, and never revertible to draft (bd polyglot-pdf-6dz0). Optional `replaces_kit_id` retires another live kit for the same form as part of this publish, archiving it first. A kit whose schema has no `form_metadata.edition_date` must supply `author_version` to publish -- the refusal is a 422 prefixed `AUTHOR_VERSION_REQUIRED:`, which the editor keys on to open its version dialog; the value is normalized server-side and IMMUTABLE once published (bd polyglot-pdf-xzw5). Token-gated. |
| POST | `/api/editor/kits/{kit_id}/translate-options` | Author-tier standalone option-label translation bake (OPTION_TRANSLATION_MODEL, in-process, idempotent; `?force=true` retranslates after label renames; 409 on any write-locked kit -- complete OR unpublished -- bd 2h9j). Returns the verify/rectify gate's `flags` and persists them at `_bakeoff.authoring.option_translation`, where schema-lint re-emits them as WARNINGs for the editor ValidationPanel (bd 9djc). Author token only. |
| GET | `/api/editor/kits/{kit_id}/unclaimed-widgets` | The kit's PDF button widgets that no field/option claims (bd nivy), powering the "Add from PDF widgets" picker when the extractor missed a checkbox/radio. Read from the persisted `acroform.json` dump; a pre-dump kit returns an empty list. Author-only (it feeds an author-only PDF-mapped option edit). |
| POST | `/api/editor/lint`, `/api/editor/kits/{kit_id}/lint` | Lint the POSTED (possibly-unsaved) schema over the single Python ruleset (`backend/services/schema_lint.py`). The kit-scoped form additionally loads the kit's persisted `acroform.json` dump -- the SAME inputs as the `/status` promotion gate -- so the editor strip sees the dump-gated widget-claim rules live (sprint-18 C1, bd o7y9); the dumpless form remains for schemas with no kit identity. Token-gated. |
| GET | `/api/editor/session` | Hosted-editor access-code probe -> `{role}`. Per-user Firebase identity (bd polyglot-pdf-hn0jq): the ID token rides either `Authorization: Bearer` or `X-Editor-Token`. 401 for a token that does not verify, 403 for a valid account without the `schema_editor_role` claim. There is no unconfigured-surface 503 -- there is no shared secret left to omit. Grant access with `scripts/bootstrap_editor_user.py`. `components/pdf-filling.md` |
| POST | `/api/editor/store-handshake` | Confirm the editor and the backend are looking at the SAME local folder: the editor writes a nonce file into the folder the human picked, this reads it from the backend's own root and reports whether it matches. Read-only on the backend side -- it never creates or deletes the marker, so an unwritable store simply reports no match rather than failing. The `reason` values it actually returns are `not-a-local-store` (GCS; hosted mode never calls it), `mismatch` (no marker observed -- the editor, having just attempted the write, picks the user-facing message) and `stale` (a marker from an earlier session in a different folder). Token-gated. |
| POST | `/api/fill-pdf` | Render the filled PDF (PyMuPDF). **Auth-gated** (`Authorization: Bearer <idToken>` via `require_auth`; bd z2is) + **firm-scoped** (bd vy6id: the body's caller-supplied `kit_id` runs the same visibility gate as the kit reads -- a private kit 404s for non-members). `components/pdf-filling.md` |
| GET | `/api/form-kits` | Form-kit manifest (metadata only; GCS/deployed manifest is complete-only, local mode lists any kit with a schema). **Auth-gated** (bd z2is) + **firm-scoped** (bd vccy): PRIVATE kits appear only for callers whose `firm_id` claim resolves to an allowlist containing them, with paths rewritten to the authenticated backend routes. `components/pdf-filling.md` |
| GET | `/api/form-kits/{kit_id}/archive` | A kit's superseded revisions, newest-first by the archived snapshot's `published_at`. **Auth-gated + firm-scoped** (bd qfyxr + polyglot-pdf-65hgz: firm-visibility gate identical to the schema read, but the status gate is WIDER -- complete OR unpublished, so a firm keeps its history after retiring the form). |
| GET | `/api/form-kits/{kit_id}/archive/{marker}/schema` | One archived revision's schema, READ-ONLY (no write counterpart exists -- superseded bytes are what the audit trail names). **Auth-gated + firm-scoped** (bd qfyxr); marker validated to `encode_marker`'s contract. |
| GET | `/api/form-kits/{kit_id}/pdf` | A single kit's PDF bytes, streamed from the store. **Public for PUBLIC kits** (their blank-template bytes ship in the static bundle regardless -- bd z2is); a PRIVATE kit needs a bearer token whose firm allowlist contains it, else 404 (bd vccy; invalid token degrades to anonymous -- existence is the secret). |
| POST | `/api/form-kits/{kit_id}/retire` | Retire a form THIS FIRM owns (status -> `unpublished`), archiving the revision first. **Auth-gated + firm-scoped**, and authorization is three further checks (bd `polyglot-pdf-z6bk9`): `firm_role=manager` AND `owner_firm_id` == the caller's firm AND `visibility=private` -- so a firm can never retire a shared/government kit, nor one it merely licenses. EVERY refusal is 404, never 403 (existence is the secret). Not a delete: hard delete stays staff-only and guarded. No UI ships yet -- the button belongs to the firm console (bd `polyglot-pdf-gob8l`). `components/auth.md` |
| GET | `/api/form-kits/{kit_id}/schema` | A single kit's schema JSON, streamed from the store (works local + gcs; `no-store`). **Auth-gated** (bd z2is) + **firm-scoped** (bd vccy: a private kit 404s for non-members). |
| POST | `/api/links/mint` | Mint a ONE-TIME client link for a form the firm may use. **Auth-gated** (per-user Firebase; the employee's `uid` becomes the link's `employee_id`, so every session traces to who sent it) + firm-scoped (the kit must be in the firm's allowlist, else 404). Returns the URL and the `jti` -- the firm's JOIN KEY for matching their client to our pseudonymous record. **404 unless `LINK_MINTING_ENABLED`**, which stays false until the spend ceiling lands (bd `polyglot-pdf-ik7e`). `components/auth.md` |
| POST | `/api/links/open` | Redeem a client link. **UNAUTHENTICATED BY DESIGN** -- a client has no account, so the signed token IS the credential (bd `polyglot-pdf-ugm6`). Enforces one-time use, the open/complete windows, and re-checks firm entitlement at open rather than trusting the mint-time snapshot. EVERY failure returns the same 404 so the response cannot be used as an oracle. `components/auth.md` |
| POST | `/api/tts/intro` | Sol's scripted intro+disclaimer clip (sprint 20, bd s1iex.3). KEYED route: `{form_number, language}` resolve against server-side tables only (`intro_tts.KNOWN_FORMS` + `intro_script.json` + `intro_agree_labels.json`) so caller text never enters synthesis; unknown form -> 400, unknown language -> English fallback. In-process cache per `(language, form, script_hash)`; `Cache-Control: private` + ETag with If-None-Match 304, plus `X-Intro-Script-Version` (the script hash the acceptance record echoes, bd s1iex.7 -- both headers need CORS `expose_headers` to be readable cross-origin); 0 dB gain (the spell-back +4 dB clips ~90s clips). **Auth-gated**; 503 unless `INTRO_TTS_ENABLED`. `backend/services/intro_tts.py` |
| POST | `/api/tts/spellback` | Deterministic spell-back verification clip (Cloud TTS, session language + persona voice; the value is PII -- never logged, lengths only; 60-char input cap). **Auth-gated**; 503 unless `SPELLBACK_TOOL_ENABLED` (default ON since bd polyglot-pdf-apkdl; bd 22h1f/44ywm). `backend/routes/tts_routes.py`, `backend/services/spellback_tts.py` |
| POST | `/dev/console-log` | Dev-only console-log ingest (404 in prod; no `/api` prefix). `frontend/src/shared/devConsoleCapture.ts`, `backend/routes/dev_console_routes.py`. |
| GET | `/health` | Liveness + reports active models, audio rates, limits, key-presence. |
| GET | `/version` | App version string. |
| WS | `/ws/audio`, `/ws/echo` | Lower-level / debug audio sockets. **Dev-only**: handshake rejected unless the `backend/.env.DEV` marker exists (same gate as `/dev/console-log`; bd polyglot-pdf-puu8). `components/websocket-routing.md` |
| WS | `/ws/fill` (+ `/api/ws/fill`) | The voice form-fill session. Requires `?token=<Firebase idToken>`. `components/websocket-routing.md`, `components/voice-ai.md` |

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
    (`pdf_fill_routes.py`'s field-mapping build loop and, for radio options, the
    `field_type == "radio"` branch's `option.get("pdf_field_name")` read).
    Missing = field silently absent from the filled PDF.
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
Consumer: `fill_form_from_schema` (`backend/routes/websocket_routes.py`'s
`@router.websocket("/fill")` handler; handshake keys parsed in its
`handshake_type`/JIT-branch block).
**No Pydantic model or TS interface pins this shape** -- every key is read with
`.get()` and a default, so a renamed key silently degrades (e.g. a dropped
`form_metadata.form_number` logs `form_id="unknown"` in the audit trail; a
dropped `kit_id` instead degrades to `kit_id=None`, a separate field).

- Key keys: `type` (`handshake` vs `handshake_jit` switches the whole parse,
  the `is_jit_mode = handshake_type == "handshake_jit"` check),
  `manifest`/`first_field_schema`/`loaded_field_ids` (JIT branch reads),
  `current_values` (post-JIT-branch read), `fill_language`/`spoken_language`
  (immediately after), `kit_id`/`form_number`/`edition_date` (the audit-trail
  identity -- `kit_id` read before the JIT branch, `form_number`/`edition_date`
  inside it as `jit_form_number`/`jit_edition_date`), `resume` (the
  `is_reconnect` check, near the end of handshake parsing).
- `full_schema` (sent at `schemaFormState.ts:979`/`:1054`): type-checked
  `isinstance(dict)` only (the `full_schema` type-check right after handshake
  parsing), cached in
  `form_filling_service.py:296` (preserved across internal restarts), then read
  by `handle_ask_secretary` (`form_filling_service.py`'s
  `self._full_schema or self._schema` read) and rendered into the secretary catalog by
  `render_static_catalog(schema)` in `text_ai_gemini.py:302`, the edition fingerprint
  (`resolve_edition_marker` call at `form_filling_service.py:396`), the injection
  budget (`form_filling_service.py:513-514`), and runtime translation overrides
  (`_maybe_start_option_translation` call at `form_filling_service.py:464` ->
  `option_translation.py`). *Breaks if malformed:* each consumer degrades
  independently and silently (secretary falls back to per-section schema, audit
  edition falls back to a fingerprint, translations revert to English).
- The JIT `manifest.parts` key is the wire contract and its entries are
  SECTION-shaped (`frontend/src/schema-forms/utils/manifestUtils.ts:38-41`;
  consumed in websocket_routes.py's synthesized-schema build (the `"manifest":
  manifest` dict entry) and its session-start JIT log line). Do not "fix" the
  name and do not expect `FormPart` objects in it.

### 3. WS control messages: client <-> backend (post-handshake)

Client->server: one `if mtype == ...` switch in `websocket_routes.py`'s
`/ws/fill` receive loop.
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
  session language, it does not change it (websocket_routes.py's
  `change_spoken_language` arm).
- `validation_result` carries `conflicts` only; the Python-side `result_type`
  label is deliberately never serialized (`_run_validation_and_push` in
  websocket_routes.py, contract pinned in `standards/validation-delegation.md`).
- The `session_ready` message's `native_vad` flag (websocket_routes.py's
  `session_ready` payload send) must agree with the backend's
  `DISABLE_GEMINI_VAD` -- the client picks its
  activity-signal behavior from it (`webFormConnection.ts:864,951` ->
  `onNativeVadMode` at `frontend/src/shared/connection.ts:535`).

### 4. Backend <-> Gemini Live (tools + session config)

Tool names + arg schemas have ONE source of truth:
`Settings.TOOL_DECLARATIONS` (`backend/config.py:588-816`), deep-copied into the
live config by `form_filling_service.py:222-228` (which drops `switch_section`
in continuous mode, and appends `SPELLBACK_TOOL_DECLARATION` under
`SPELLBACK_TOOL_ENABLED` -- default ON since bd polyglot-pdf-apkdl, so a
production session ships 7 declarations; setting the flag false rolls back to 6,
bd polyglot-pdf-22h1f) and declared to
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
| `name_spellback` (no args; `SPELLBACK_TOOL_ENABLED` default ON, declared via `SPELLBACK_TOOL_DECLARATION` -- kept out of `TOOL_DECLARATIONS` so the flag stays a real rollback) | `_handle_name_spellback_tool` | `spellback` round-trip + client HTTP `POST /api/tts/spellback` (bd polyglot-pdf-22h1f) |

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
Consumer: `PDFFillRequest` (`backend/routes/pdf_fill_routes.py`'s `PDFFillRequest`
class).

- **The backend fills from the CLIENT-SUBMITTED `form_schema`**, typed
  `Dict[str, Any]` -- no `FormSchema` validation runs at fill time, the kit
  store is consulted only for the PDF bytes (`fill_pdf`'s `store.load_pdf_bytes`
  call), and the extraction-time
  `acroform.json` ledger is never read on this path -- its readers all live on
  the editor/publish surface (`_load_kit_dump` in
  `backend/routes/editor_kit_routes.py`, with 7 call sites across the
  lint routes; the mark-complete promotion gate's call is inside
  `set_editor_kit_status`, feeding the pure-function
  checks in `backend/services/widget_picker.py`). *Breaks:* a stale or
  mutated client schema fills a wrong/blank field into a PDF that completes
  "successfully" -- the exact reassembles-without-error failure mode.
- Field-id -> `pdf_field_name` mapping with a two-pass `[]`-alias resolution,
  exact id always winning (`pdf_fill_routes.py`'s field-mapping build loop);
  widget dispatch by `field_type` (the `for field_id, value in
  request.field_values.items()` loop's `if field_type == "radio"` /
  `elif field_type in ("checkbox", "checkbox_group")` / `else` branches):
  text via `fill_widget` with cosmetic-only Comb overflow handling
  (`fit_comb_value`), checkboxes via `get_button_on_state` (defaults to
  `"Yes"` when the widget's on-state is unreadable), v2 shared-name radios via
  direct `xref_set_key` writes.
- A skipped field arrives as bare `null` (the `skipped` flag was unwrapped away)
  and is indistinguishable from never-asked -- both are silently omitted
  (the field-fill loop's `if value is None or value == "":` guard).
- `NeedAppearances` is deliberately NOT set (the `need_appearances_skipped` log
  site near the end of `fill_pdf`); appearance regeneration
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
:1000-1009). Event shape (NO PII, no `value` key anywhere), built in
`confirmation_logger.log_field_confirmation`'s `confirmation_event` dict:
`{timestamp, event, form_id, kit_id, edition_date, firm_id, form_session_id,
field_id, field_name, confirmation_method}` (`firm_id` joined under bd
polyglot-pdf-xwlt -- the CUSTOMER FIRM from the verified token claim, never a
client identifier). Sinks: structured log (the `_log.info("field_confirmed",
**log_data)` call in the same function), local
JSONL (`_write_confirmation_to_file`, dies with the instance),
Firestore `confirmation_events` (`_submit_firestore_write` checks the
`CONFIRMATION_FIRESTORE_ENABLED` gate via `_firestore_enabled()` and dispatches
to `_firestore_write`, which does the actual write and sets the optional
`expire_at` TTL). The
identity keys (`kit_id`, `form_number`, `edition_date`) originate in the
handshake -- sent by the JIT builder at `schemaFormState.ts:1075` (form_number),
`:1088` (kit_id), `:1089` (edition_date), read as `kit_id`/`jit_form_number`/
`jit_edition_date` in websocket_routes.py's handshake handling -- see
contract 2. The
`edition_date` COLUMN carries whichever revision marker won
`resolve_edition_marker`'s three-rank precedence: the government
`edition_date`, else the author's `author_version`, else a `sha256:` shape
fingerprint (bd polyglot-pdf-xzw5) -- so the name is narrower than the values
it holds. The SAME sink carries FOUR event kinds. Two SESSION records per voice session
(`form_session_started` / `form_session_ended`, wired from
`_handle_fill_session` under bd polyglot-pdf-xwlt), keyed on the same
`firm_id` + `kit_id` so per-firm usage spans sessions and confirmations in one
equality query; the end record carries a confirmed-field COUNT, never values.
And `disclaimer_accepted` (bd polyglot-pdf-0dsv4) -- the ONLY one written from
an UNAUTHENTICATED route, so its `firm_id` is structurally always `None` and a
per-firm query cannot see it; `firm_of_events()` recovers the firm from the
session's other records. Bounded two ways (bd polyglot-pdf-g3kui, full
rationale in `standards/confirmation-and-audit.md`): a one-record-per-
`form_session_id` dedupe (`confirmation_logger._claim_first_acceptance`,
except PLACEHOLDER ids, which are deliberately exempt and so remain
unbounded), and Pydantic field caps that 422 an oversized body before it
reaches this sink. Every query against this collection that means
"confirmations" must scope on `event == "field_confirmed"`: an unscoped one
already made a kit permanently undeletable once (bd polyglot-pdf-68s2q).
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
  publish and visibility gates (`kit_gates.py`'s `load_live_metadata`; visibility coercion in
  `kit_gates.py`'s `kit_visibility`; the manifest copy is deploy-time stale in GCS) --
  and the store passes normalized `visibility` / `ownerFirmId` through both
  manifest paths (`form_kits.py`'s `normalize_manifest` and `LocalFormKitStore.load_manifest`).
  `owner_firm_id` is bookkeeping for the firm write path (bd z6bk9), NOT the
  read gate.
- **The firm allowlist**: `firms/{firm_id}.allowed_kits` (producer:
  `scripts/bootstrap_firm.py`) -> `firms.py`'s `get_allowed_kits`
  (fail-closed `[]`) -> resolved per request
  off the `firm_id` ID-token claim (`kit_gates.py`'s `firm_allowed_kits`;
  run off the event loop) -> enforced by `kit_gates.py`'s `require_visible` (404 =
  invisibility) on the schema + pdf + fill reads
  (`pdf_fill_routes.py`'s `fill_pdf`) and by the list filter inside
  `list_form_kits` (`form_kit_routes.py`'s `list_form_kits`). The pdf route
  parses its bearer token OPTIONALLY (`form_kit_routes.py`'s
  `get_form_kit_pdf`); an invalid token degrades to anonymous rather
  than 401.
- **The private-path rewrite**: `form_kit_routes.py`'s `list_form_kits`
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
  (`form_kit_routes.py`, the `FormKitInfo` model): under rewritten paths the URL's last segment is
  a literal route word, so the client must STOP deriving filenames by URL
  split. Consumers: `SchemaFormDemo.tsx`'s manifest mapping (the `schemaFile`/`pdfFile` fallback derivation) and
  `fillPDF`'s explicit `pdfFile` param (`pdfFiller.ts:117` -- the fill POST's
  `pdf_filename` feeds `store.load_pdf_bytes`, contract 5). Breaking either
  half strands a private kit's fill/download while every public-kit test
  stays green.

### 8. Firm retire write path (bd polyglot-pdf-z6bk9)

The firm tier's ONLY write contract -- every other firm-facing surface is read
+ telemetry. `POST /api/form-kits/{kit_id}/retire`
(`form_kit_routes.py`, `retire_own_kit`) flips a firm-owned private kit to
`status: "unpublished"` after archiving it. It INVERTS contract 7's
assumptions, which is the trap for anyone changing either one:

- **Visibility is NOT authorization here.** Contract 7's read gate admits any
  kit in the caller's `allowed_kits` -- INCLUDING kits the firm does not own.
  This write path instead requires `owner_firm_id == firm_id` (the key
  contract 7 explicitly calls "bookkeeping for the write path, NOT the read
  gate"). A change that makes the read gate consult `owner_firm_id`, or makes
  this route consult `allowed_kits`, silently lets a firm retire a form it
  merely licenses. Producer of the claims: `scripts/bootstrap_firm.py`
  (`firm_id` + `firm_role` custom claims); consumer: `_require_firm_owns_private_kit`.
- **`firm_role == "manager"` is the only consumer of that claim.** The
  four-level access model (app admin / firm management / employee / firm
  client) exists in the claim, but this is the FIRST route to read it -- an
  employee-level session must not retire forms. Any future firm write path
  must gate on it too; there is no shared helper yet because there is one
  caller.
- **Refusals are 404, never 403** -- same reason as contract 7's read gate: a
  403 confirms existence to a firm that cannot see the kit. Pinned by
  `test_firm_retire.py::test_a_nonexistent_kit_and_another_firms_kit_are_INDISTINGUISHABLE`.
- **Archive-then-retire, shared with staff.** `_archive_published_revision`
  moved OUT of `editor_kit_routes.py` into `backend/services/kit_gates.py`
  so the staff route's three call sites and this one share ONE implementation
  (routes importing routes would be circular -- `editor_kit_routes` already
  imports `_safe_kit_id` from `form_kit_routes`). Its marker-precedence and
  sibling-disambiguation behavior is contract 6's retrieval guarantee; a
  change there breaks BOTH tiers at once.
- **Retirement is not deletion.** `unpublished` is hidden + write-locked, and
  the retired revision's bytes are what its confirmation records were
  confirmed against. Hard delete stays staff-only behind the guard in
  `confirmation_logger.kit_has_confirmation_records` (contract 6).
- **The status write has TWO consumers beyond this route**, and missing either
  is the cross-surface trap (both caught by Opus outer review, bd
  polyglot-pdf-65hgz / polyglot-pdf-d4hi8):
  - **The archive reads must survive it.** `require_archive_readable`
    (`kit_gates.py`) admits `complete` OR `unpublished` for the two archive
    routes, while `require_published` still guards the LIVE schema/pdf reads.
    Gating history on `complete` meant this route archived a revision and made
    it unreachable to the owning firm in the SAME request -- the exact
    guarantee archive-then-retire exists to provide. Staff never saw it
    (`/api/editor/*` is ungated), so only a cross-surface trace finds it.
  - **The editing lock must be released.** Both staff sites writing this same
    `unpublished` transition pop `editing_lock` (`_lock_after_transition`: a
    transition ends the editing turn). A merged-through lock 409s every editor
    action on the kit with no author actually working. Any THIRD site reaching
    `unpublished` must do both.

No UI consumes this route yet -- the button belongs to the firm console (bd
polyglot-pdf-gob8l), per the maintainer's 2026-08-20 decision.

### 9. Client magic links (bd polyglot-pdf-ugm6)

The CLIENT tier's entire contract surface, and the first credential in this
system that is NOT a Firebase account. Five coupled pieces:

- **The link token** (`backend/services/link_tokens.py`): HMAC-SHA256 over a
  canonical JSON payload, `<payload_b64>.<sig>`. Producer: `POST
  /api/links/mint`. Consumers: `POST /api/links/open` AND
  `websocket_routes._verify_ws_credential`. **The ONE-DOT shape is load-
  bearing** -- it is what keeps this credential and a Firebase JWT (two dots)
  from ever being confused, in both directions. Giving the token a third
  segment, or routing on a caller-supplied hint instead of shape, merges two
  credential systems that must stay apart.
- **The no-client-identifier invariant.** The payload's field set is CLOSED
  and pinned by `test_link_tokens.py`. We hold the pseudonym (`jti`), the
  firm holds identity; neither side alone re-identifies. Widening the payload
  is a change to the product's legal posture (see
  `docs/components/auth.md`).
- **`employee_id` from the verified uid.** Producer: the mint route, reading
  `user["uid"]` -- never `body`, which has no such field (also pinned).
  Consumer: the session telemetry (contract 6), which is how a CLIENT session
  satisfies "firm + form + originating employee" with no account involved.
- **The kit_id the link names beats the handshake's.** The WS handshake is
  client-controlled; a link holder editing `kit_id` is REFUSED (1008), not
  silently corrected -- a substitution would produce a confirmation record
  naming a form the client never saw. Any future code path that trusts the
  handshake's `kit_id` for a link session reopens this.
- **One-time use lives in Firestore** (`link_redemptions`), not the token: a
  signed bearer string is replayable by construction. FAILS CLOSED BY
  REFUSING (opposite polarity to the firms allowlist read, which fails closed
  by returning `[]`) -- note the two "fail closed" directions when changing
  either.
- **The doors that REDEEM do it through ONE helper.**
  `link_redemptions.enforce_link_redemption` runs the redemption check AND the
  COMPLETION-window check, neither of which `verify_link_token` can do -- the
  token carries only the OPEN deadline, and one-time use lives in Firestore.

  **WHICH DOORS CALL IT IS THE WHOLE DESIGN, so read this before adding one.**
  The TTL bounds a BACKEND CONNECTION, not the client's access to their own
  document (maintainer, 2026-08-24):
  - **PAID work redeems** -- `/ws/fill` (a Gemini session), `/api/links/open`,
    and both `/api/tts/*` routes via the `require_paid_client_work`
    dependency. A completed link starts no new session and buys no more audio.
  - **RETRIEVAL does NOT** -- `require_auth` (the archived-revision reads and
    `/api/fill-pdf`) and `require_signin` (choosing a form: `GET
    /api/form-kits` and `.../{kit_id}/schema`, moved off `require_auth` by PR
    #643). `/api/fill-pdf` is a pure PyMuPDF render with no model call, so
    redeeming there spends nothing and only takes away the document the
    client just filled. All still need a valid SIGNED link inside its open
    window, scoped to that link's single
    kit.

  A new door that authenticates a client credential must decide which side it
  is on. THREE dependencies exist, not two:
  - it can cause SPEND -> `require_paid_client_work` (redeems)
  - it serves the client their own data, and the caller must be ENROLLED ->
    `require_auth`
  - it only lets someone CHOOSE a form, which must not require enrolment ->
    `require_signin` (bd polyglot-pdf-ugm6 + PR #643)

  Using `require_auth` on a catalogue-shaped route re-imposes the enrolment
  gate #643 deliberately removed. The sets are pinned by
  `test_http_route_auth.py` and `test_client_link_http_auth.py`.

  (History, so the split is not "corrected" back: the socket originally
  redeemed while `require_auth` did not, and a completed link kept serving
  everything until `exp` -- Opus r1. The over-correction then put redemption
  on retrieval too, which made a finished form undownloadable -- Opus r11.)
  `complete_link` fires ONLY on a genuine completion -- an abandoned session
  must not consume the client's one chance.
- **`link_jti` + `employee_id` ride both SESSION records** (contract 6). The
  jti is the firm's join key; a record without it makes the split-key
  arrangement inoperable, and `employee_id` is what carries "originating
  employee" for a session with no account behind it.

The redeemed token lives in `sessionStorage` via
`shared/sessionCredential.ts` -- TAB-SCOPED, so it survives a reload (the
entry gate clears it from the URL, so memory-only stranded a client on any
refresh) and dies with the tab. Never `localStorage`, which would outlive the
browser session. All NINE backend-calling sites resolve through that one
module; a tenth inline `user.getIdToken()` fails CI.

Frontend: `/f` renders `ClientLinkEntry` OUTSIDE `ProtectedRoute`
(`frontend/src/schema-forms/AppRoutes.tsx` -- extracted from `main.tsx` so a
test could import it, which is itself the fix for a defect: while the table
lived beside `createRoot`, wrapping the client route in `ProtectedRoute` or
renaming its path both passed the entire frontend suite). Moving it inside
bounces every client to a sign-in they can never pass. The path is the
exported `CLIENT_LINK_PATH`; `clientRoute.test.tsx` pins it against the same
`/f` literal `link_routes.py` builds links from -- each side independently
pinned, so a unilateral change on either reddens. The gate pins the form id via
`saveOnboardingState` and leaves LANGUAGE unset -- the form is the firm's
choice, the language is the client's.

**Minting is off by default** until the spend ceiling ships (bd
polyglot-pdf-ik7e): a live link is an unauthenticated door to a paid session.

### 10. Intro agree-label mirror (bd polyglot-pdf-s1iex.3)

Producer: `backend/services/intro_agree_labels.json` (18 language ->
agree-label entries). Consumer: `BUTTON_TRANSLATIONS` in
`frontend/src/schema-forms/components/DisclaimerModal.tsx:38`. The backend
label is INTERPOLATED INTO SPOKEN AUDIO -- `intro_tts.build_intro_text`
replaces the `[AGREE LABEL]` placeholder (`intro_tts.py:76`) with the
backend's copy of the label -- so a drift means Sol speaks a button name
that is not the one on screen. Pinned by
`backend/tests/unit/test_intro_route.py::TestIntroTables::test_agree_labels_match_frontend_mirror`.

### 11. `LIVE_VOICE_NAME` two-consumer coupling (bd polyglot-pdf-22h1f/44ywm)

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
