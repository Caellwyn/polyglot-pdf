# Technical guide -- polyglot-pdf

*Last updated: 2026-09-09 (bd polyglot-pdf-x22hm: Epic 2 Track C bead C5 -- new Surface contract 27, link history (`frontend/src/console/LinkHistoryPage.tsx` at `/console/links/history`), the first real caller of contract 23's admin-service wiring alongside C4's `EmployeesPage.tsx`; a known gap in `require_app_admin_or_owning_manager` (contract 22) that refuses an employee-role account before its own scoping logic runs is filed separately as bd polyglot-pdf-scaig, not fixed in this bead.) (bd polyglot-pdf-w828m outer Opus cross-surface review: Surface contract 26's usage-rollup teardown call site now dispatches `firm_kind()` + `record_session_end()` through ONE `asyncio.to_thread` call, matching every sibling Firestore call already on that route -- both were previously called directly on the shared event loop; and the rollup month-document id is now channel-suffixed (`YYYY-MM` for demo, `YYYY-MM_{channel}` for every other channel, mirroring bd polyglot-pdf-3q9qn's collection-suffix convention), since staging and demo share one Firestore project and the prior bare `YYYY-MM` id let a staging test-drive increment the same document the demo's billing view reads.) (bd polyglot-pdf-w828m: Epic 3 bead E3.4 -- new Surface contract 26, session-end usage rollups (`firms/{firm_id}/usage/{YYYY-MM[_channel]}` + `kits/{kit_id}/usage/{YYYY-MM[_channel]}`, new `backend/services/usage_rollups.py`): `record_session_end()` writes ONE BATCHED `db.batch()` set of `firestore.Increment` updates from the SAME websocket teardown block as `log_form_session_end`/`_bank_link_spend`; `record_link_opened`/`record_link_completed` hook `link_redemptions.py`'s open/complete paths for the two counters the teardown call cannot itself produce. HYPHENATED MAP KEYS (`i-90`, `zh-CN`) are handled by building every nested increment as a REAL nested dict via a `FieldPath(*parts).parts` walk, never a dotted string -- `set(merge=True)`, the write API this module uses so a new month document's first write CREATES it, does NOT dot-expand a flat string key the way `update()` does (confirmed against the vendored SDK before writing the module). `firestore.rules` gains deny blocks for both new nested `usage` subcollections.) (bd polyglot-pdf-f0kuu: Epic 2 Track B bead B3 -- kit commercial settings on the admin service, `GET /admin/kits`, GET/PUT `/admin/kits/{kit_id}/commercial`, extending Surface contract 24 with the write side of the mechanism that contract already documents the read side of: `resolve_commercial` reused as-is (no second reader), and a strictly validated PUT -- credit_cost a positive int, burn_cap_usd a positive finite float, bool/NaN/+-inf all refused explicitly -- audited in the same `@firestore.transactional` body as the write.) (bd polyglot-pdf-rd3s8: Epic 3 bead E3.6 -- new Surface contract 25, the BigQuery telemetry sink + cost/income views (`scripts/setup-telemetry.sh`, `sql/telemetry_views.sql`): a sink filter that ORs across three genuinely different `jsonPayload` shapes (contract 20's nested `message.event_type` for usage events, contract 18's flat `event_type` for `ledger_export`, and a THIRD flat-but-differently-keyed `jsonPayload.event` for the two wired session events) rather than the single field name the plan's prose implied; five views whose referenced columns are pinned by a DERIVED set (from `USAGE_CONTEXT_KEYS` and `LEDGER_EXPORT_FIELDS`), not hand-listed; `income_month`'s `firm_kind = 'live'` filter hard-coded in the view; and `admin-backend-sa`'s two BigQuery roles moved out of `DEFERRED_ROLES` into `EXPECTED_ADMIN_SA_ROLES`, granted by the new script rather than `setup-admin-service.sh`.) (bd polyglot-pdf-jecrl: the mint reservation and the open gate -- new Surface contract 24: `POST /api/links/mint` reserves the credit in ONE transaction (balance + `mint_debit` entry + the `links[_<channel>]/{jti}` record) BEFORE signing a token, refusing `403` for a live or kindless firm off the raw-`demo` channel and `402` when `CREDITS_ENFORCED` and the balance falls short; new `backend/services/kit_commercials.py` reads `kits/{kit_id}` fail-soft for the price and the `cap_usd` signed in; and `enforce_link_redemption` refuses a link with no mint record or a revoked/refunded one, for every door that spends. Contract 16's 'not wired to anything yet' and contract 9's gate description are updated with it.) (bd polyglot-pdf-bo95a: Epic 3 bead E3.5 -- new Surface contract 21, telemetry alert docs (`alerts/{id}`, new `backend/services/alerts.py`) with deterministic ids so a repeated trigger dedups onto the same document: `link_exhausted_{jti}` from `link_spend.check_budget()`'s refusal branch (which gains an optional `firm_id` kwarg purely to label the alert) and day-keyed `{firm_id}_credit_low_{day}` / `{firm_id}_credit_exhausted_{day}` from `credit_ledger.append_entry()` after a `mint_debit` commits, gated on the new runtime-config key `CREDIT_LOW_THRESHOLD` (no env fallback, like `CREDITS_ENFORCED`); both hooks best-effort, never raising into the caller; `firestore.rules` gains a deny block for `alerts/{alertId}`.) (bd polyglot-pdf-cjifh: Epic 3 bead E3.2 -- Surface contract 20's live-voice call site now threads REAL firm/employee/link/kit/channel/model context ids end to end (`_handle_fill_session` -> `FormFillingService.start_session` -> `LiveAIGemini.set_session_context`), instead of the six-keyword shape existing with nothing filling it.) (bd polyglot-pdf-wio6m: usage event v2 -- new Surface contract 20, ONE emitter shape (`StructuredLogger._emit_usage` plus three wrappers) for every paid model/TTS call, the closed `usage_kind` set and `USAGE_CONTEXT_KEYS` written unconditionally so a missing key never masquerades as a null at the BigQuery sink, the AST-derived paid-call-site allowlist, and the text + TTS pricing tables that the Live table does NOT transfer to.) (bd polyglot-pdf-dmjl5: staff-account management -- new Surface contract 19 (the firm-manager rule's ONE home, `backend/services/firms.py`'s `manager_firm_id`, and the admin service's claims allowlist), four new Admin service routes (POST + GET /admin/users, PATCH /admin/users/{uid}/disable, PATCH .../role) behind the composite gate `require_app_admin_or_owning_manager`, and contract 8's manager check now consuming the shared rule rather than restating it.) (bd polyglot-pdf-1op3g: Epic 2 Track A bead A5 -- Surface contract 18 gains `credit_ledger.refund_expired_link()` (the transactional expiry refund keyed on `link_redemptions[_<channel>]/{jti}`'s existence, idempotent on `links[_<channel>]/{jti}.status == "minted"`) and `reconcile_expired_for_firm()` (the lazy per-firm catch-up called only by a balance read, never by the mint transaction -- pinned by an exact-read-set test on `append_entry()` plus an AST-walk non-call guard), plus the socket's `LinkBudgetExhausted` teardown writing a telemetry-only `budget_exhausted` status mirror with no ledger entry.) (bd polyglot-pdf-vnxew: the credit ledger -- new Surface contract 18, `backend/services/credit_ledger.py`'s `append_entry()` as the ONE transactional writer of `firms/{firm_id}.balance_credits` and the only producer of `firms/{firm_id}/ledger/{auto}`, the `ledger_export` structured log line Epic 3's BigQuery sink filters on, and the `scripts/grant_credits.py` operator CLI on the same helper.) (bd polyglot-pdf-li9x0: the admin audit log -- new Surface contract 15, three new Admin service routes (GET /admin/audit, GET+PUT /admin/config/{channel}), and firestore.rules deny blocks for admin_audit_log and app_config pinned by ONE set-derived test over every Admin-SDK-only collection.) (bd polyglot-pdf-6p77c: the kit path rewrite is keyed on the STORE being authoritative, not on privacy -- see "The API-path rewrite" below.) (bd polyglot-pdf-7w17m: the admin service's first gated route, GET /admin/whoami, behind require_app_admin -- see the Admin service routes table below.) (bd polyglot-pdf-pnoik: two new surface contracts -- APP_MODULE selects which ASGI app the ONE image serves, and admin_backend/ may import backend.services/config but never backend.routes.) (bd polyglot-pdf-wurj8: the Pause button is replaced by a sticky manual/voice mode toggle -- manual suppresses the model's proactive speech at the ADAPTER while the session stays live and the mic stays usable; a PTT press unmutes at both ends; the mode is client-owned and re-asserted on every reconnect. bd polyglot-pdf-3q9qn: client links are isolated per channel -- each channel keeps its own redemption ledger.) (bd polyglot-pdf-ah5d3: Epic 2 Track A bead A4, closing polyglot-pdf-4tjt7 -- the socket's client-link spend ceiling is now TOKEN `cap_usd` (a signed claim) over the global default, resolved by `link_budget.cost_ceiling_usd_for_claims`; the earlier "socket passes no kit metadata" / "not yet threaded through the handshake" claims are gone.)*

> **Line-number citations in this file are not trustworthy without re-verifying
> against source.** This doc has drifted the same way repeatedly -- bd
> `polyglot-pdf-vdcm4` re-anchored one class of citation, then bd
> `polyglot-pdf-nyc5j`/`qn8wv`/`x6dq1` had to re-anchor contract 2 again. Cite
> a SYMBOL NAME rather than a line number when adding one.

The [Surface contracts](#surface-contracts) section is the code-derived
cross-surface data-contract map for blast-radius review. Continuous-DTI is the
production default (`USE_DTI` / `CONTINUOUS_SESSION` /
`CONTEXT_COMPRESSION_ENABLED` all default true; section-reset is the deprecated
fallback). This guide lists the deploy flow + env vars; per-channel model/auth
config detail lives in [standards/ai-models.md](standards/ai-models.md) and
[components/config-deployment.md](components/config-deployment.md).

**Tracks:** `backend/main.py`, `admin_backend/main.py`, `backend/config.py`, `backend/routes/*.py`, `backend/models/form_models.py`, `backend/services/form_kits.py`, `backend/services/callback_handler.py`, `backend/services/request_coordinator.py`, `backend/adapters/live_ai_gemini.py`, `frontend/src/webFormConnection.ts`, `frontend/src/schema-forms/state/schemaFormState.ts`, `firebase.json`, `deploy-*.sh`

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
**staging** remote (`deploy-staging.sh`) -> **demo** remote (`deploy-demo.sh`).
Deploys are **local/manual** (`deploy-staging.sh` / `deploy-demo.sh` ->
`deploy-all.sh`), NOT branch-triggered/CI, and there is **no prod** --
`deploy-production.sh` targets a dead, unreachable project and refuses to run.
Staging and demo are two channels in the ONE project `polyglot-demo-aa709`, split
by Cloud Run service (`polyglot-backend-staging` / `polyglot-backend`) and Hosting
site; staging is the disposable target for deploy-only bugs, the demo is what
investors and pilot firms see. They SHARE Firestore, the form-kits bucket and the
Auth pool, so staging isolates broken code, not bad data.
The agent may run either deploy under the three-part gate (local-test-first +
per-instance permission + post-deploy test-drive), and a demo deploy expects the
change to have been verified on staging first; see
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
| `FIRMS_FIRESTORE_ENABLED` | `false` (deploys set `true`) | Enables the firms-store READ path (`backend/services/firms.py`, bd lo88): the `firms/{firm_id}` collection holding firm profiles + allowed-kits, consumed by the form-kit routes' firm-scoped visibility filter (bd vccy). Reads FAIL CLOSED to `[]` when off/broken, so an outage hides private kits rather than exposing them. Set in `deploy-all.sh`'s `BACKEND_ENV`; the `deploy-form-kit.sh` drop-list hint enumerates it (pinned by `tests/test_deploy_form_kit_hints.py`). Firm records are created by `scripts/bootstrap_firm.py`; see `components/auth.md` (Firm identity). |

Non-env tunables also in `config.py` (code constants, **not** `getenv` -- change
them in source, not via environment):
`AUDIO_IN_RATE=16000`,
`AUDIO_OUT_RATE=24000`, `WS_CHUNK_MS=20`, `MAX_UPLOAD_MB=5`. (The VAD
sensitivity knobs that used to be env-overridable here are GONE -- Gemini's
automatic activity detection is unconditionally disabled, so nothing reads them;
bd polyglot-pdf-v1m8g.) The list is not
exhaustive -- additional WS tuning constants live in `config.py`. Also there:
`WS_IDLE_TIMEOUT_SEC` (`120`) -- the idle watchdog closes a WebSocket connection
after this many seconds with no received message (audio, ping, or control).

## Routes / endpoints

Routers are registered in `backend/main.py`. REST routers carry a `/api` prefix;
the `websocket_routes` router carries `/ws` and is mounted **twice** -- bare and
again under `/api` -- so both `/ws/fill` and `/api/ws/fill` resolve (see Gotchas).
Routes declared directly on `app` in `main.py` (`/health`, `/version`) are
**not** part of that double-mount and have no `/api` mirror.

This table covers the **public backend** (`backend.main:app`) only. The
privileged admin service runs the SAME image with a different runtime
`APP_MODULE` and has its own table below -- both apps declare `/health` and
`/version`, so one merged table could not say which service a row describes.

Rows are sorted by **path, then method**, and the set is pinned against the
live app by `tests/test_technical_guide_routes_table.py`, keyed on
`(path, method)` **per app**: a shipped route with no row -- including a NEW
METHOD on an already-listed path, which needs its own row -- a row for a route
that no longer ships, and an out-of-order row each fail that test. The sort is
not cosmetic: it gives every row exactly one correct position, so two PRs
adding different routes edit different lines instead of colliding over the same
insertion point.

| Method | Path | Surface doc |
|--------|------|-------------|
| POST | `/api/disclaimer-acceptance` | Record disclaimer acceptance DURABLY (bd polyglot-pdf-0dsv4: the `confirmation_events` Firestore collection + the per-session file, keyed on `form_session_id`, not a log line -- fail-open, so a sink outage cannot block an Agree click). UNAUTHENTICATED by design (Agree fires before any session exists), so `firm_id` is always `None` here and the `form_session_id` is validated as a single safe path segment before it becomes a filename. One acceptance per `form_session_id` -- a duplicate POST is dropped silently, not errored -- except PLACEHOLDER ids (`unknown`/`undefined`/`null`/`none`/empty), which are deliberately NOT deduped (bd polyglot-pdf-g3kui: `confirmation_logger._claim_first_acceptance`); every request field is bounded at the Pydantic model so an oversized body 422s before reaching the sink. Anonymized; client IP deliberately NOT logged, bd z2is. Records `script_version` -- the hash of the exact script the user saw and heard, echoed from the intro route's `X-Intro-Script-Version` so the record names WHICH text was agreed to; `None` on the legacy model-read path -- a known audit gap, since that path still serves deterministic scripted text (bd s1iex.7, bd polyglot-pdf-pyebx). `standards/confirmation-and-audit.md` |
| GET | `/api/editor/kits` | Editor kit list INCLUDING drafts (from the storage listing, not the complete-only manifest). Editor-tier (per-person Firebase claim). |
| POST | `/api/editor/kits` | Author-tier onboarding: multipart PDF upload -> new draft kit in the store. Author-tier (per-person Firebase claim). |
| DELETE | `/api/editor/kits/{kit_id}` | **AUTHOR ONLY** -- permanently remove a kit and everything under it, ARCHIVES INCLUDED (bd polyglot-pdf-6x1j). GRADUATED FRICTION, never a permanent block (bd polyglot-pdf-6zhaf): risk decides how firmly the caller is asked, not whether the door exists. Never live + no records + the check SUCCEEDED -> deleted. Never live but records exist OR the check could not run -> 409 prefixed `DELETE_NEEDS_ACK:`. EVER LIVE (`complete`/`unpublished`, or any `published_at` -- either signal alone is sufficient, since `w7` is complete with no stamp while `unpublished` means RETIRED-formerly-live; a kit with NO metadata.json is never-live, but one whose metadata is PRESENT and unparseable is treated as live) -> 409 prefixed `DELETE_NEEDS_DOUBLE_ACK:`. Each refusal names the acknowledgement that clears it, and the two are DISTINCT values -- `?acknowledged=understood` for the single, `understood-published` for the double. The weaker does NOT satisfy an ever-live delete: one shared boolean would put "double confirmation" in the client's checkbox only, where any direct API call skips it. The editor sends the level the server asked for, and the double additionally requires an explicit tick before it will send. The old design refused outright when the check was positive or unavailable -- and un-attributable legacy records make it permanently unavailable, so EVERY kit became undeletable forever. The check itself is unchanged and its outcome still grades the warning; the record sink is Firestore (`CONFIRMATION_FIRESTORE_ENABLED`, default false, set by `deploy-all.sh`) whose local JSONL fallback dies with the instance, so silence there is still not evidence of absence. NOTE what a delete destroys: only this kit's prefix -- confirmation records live in a separate collection and SURVIVE, so what is lost is the revision those records name, not the agreement itself. Every delete logs actor + acknowledged + ever_live + had_records. Editors are refused server-side, not merely hidden from in the UI. |
| GET | `/api/editor/kits/{kit_id}/archive`, `.../archive/{marker}/schema` | The editor's archive reads (bd qfyxr): superseded revisions newest-first + one revision's schema, READ-ONLY (returning to an old revision goes through draft/publish, never the archive). Editor-tier (per-person Firebase claim). |
| POST | `/api/editor/kits/{kit_id}/derive-divisions` | Regenerate the kit's parts/sections deterministically (bd 6cfu.3) -- re-runs `derive_sections.derive_and_apply` on the STORED schema + PDF (widget-name conventions -> printed headings -> page fallback) and re-files every field's `section_id`. **DESTRUCTIVE to manual division edits by design**; the editor fronts it with a confirm dialog, field content untouched. Author-only; 409 on complete or on a kit with no PDF; a corrupt/0-page PDF is a 422 data defect, not a 500. |
| GET | `/api/editor/kits/{kit_id}/draft-snapshots` | Prior saved states of this kit's draft, newest-first (bd polyglot-pdf-y2l0p). EDITOR-accessible by deliberate maintainer decision (2026-08-18): routing recovery through an author means the person who lost the work cannot get it back themselves. 404 (not an empty list) for a kit that does not exist -- "no earlier versions" and "no such form" are different answers. Editor-tier (per-person Firebase claim). |
| POST | `/api/editor/kits/{kit_id}/draft-snapshots/{snapshot_id}/restore` | Put a snapshot's schema back as the live draft. Snapshots what it REPLACES first, so restoring the wrong version is one more restore away rather than a second loss -- that is what makes it safe without an author. Refused on a write-locked kit (complete/unpublished), same as a save. Non-numeric snapshot ids 400 before reaching the store. Editor-tier (per-person Firebase claim). |
| POST | `/api/editor/kits/{kit_id}/extract` | Author-tier hosted extraction: runs the PDF->schema pipeline server-side (EXTRACTOR_MODEL, minutes-long, serialized per instance). 409 on any write-locked kit -- complete OR unpublished -- with a revert-first message (`force=true` would overwrite the published schema in place, bd polyglot-pdf-w3zw). Author-tier (per-person Firebase claim). `translate_options` form flag (default true) also bakes option label_translations (bd 2h9j). |
| POST | `/api/editor/kits/{kit_id}/hidden` | **AUTHOR ONLY** -- hide a kit from the editor catalogue, or bring it back (bd polyglot-pdf-n5fwd). Body `{hidden: bool}`; a separate `hidden` metadata key, deliberately NOT a fifth lifecycle status: status answers "where is this in its life?" and drags `_WRITE_LOCKED_STATUSES` with it, while hiding answers "do I want to look at this?" and stays orthogonal. So there is NO write-lock gate (matching `/label`) -- a `complete` or `unpublished` kit can be hidden, and the revision a confirmation record names stays published, fillable and in the manifest; only the editor catalogue view changes. FAILS VISIBLE: `_is_hidden` returns True only for a literal `True`, so absent/malformed/hand-edited values mean visible and a parse accident can never make a kit vanish from the only list that shows it. Author-tier despite looking editor-ish by the reversible/no-tokens/creates-nothing line that puts `/label` at editor -- maintainer decision 2026-09-01, because hiding changes what OTHER people see. 409 when a different editor holds the edit lock, same as every sibling metadata write. Rides the existing `GET /kits` wire as `hidden`. NOT the per-kit revision ARCHIVE, which is the frozen audit copy. |
| POST | `/api/editor/kits/{kit_id}/label` | Rename a kit's DISPLAY label (bd polyglot-pdf-15ic), preserving every other metadata key (the read-merge-write shape of the status flip). Pure display -- the catalogue and form picker render it, nothing keys on it; kit identity is the immutable `kit_id`/storage path and is deliberately NOT renameable here. Exists because onboarding derives labels from PDF filenames, so nameless uploads collide into "Form", "Form 2", ... 409 when a different editor holds the kit's edit lock (bd polyglot-pdf-c63tu), naming the holder, same as every sibling metadata write route. Editor-tier (per-person Firebase claim). |
| DELETE | `/api/editor/kits/{kit_id}/lock` | Release a kit. An author may release anyone's lock; an editor may release only a lock THEY hold (bd polyglot-pdf-5tuas) -- they can neither evict an author nor free another editor's kit. Author preemption is the stale-lock escape when someone closes their laptop. Editor-tier (per-person Firebase claim). |
| POST | `/api/editor/kits/{kit_id}/lock` | Take a kit for editing (bd polyglot-pdf-hqztg). An AUTHOR can always take a lock back from an editor; the reverse 409s. That preemption IS the stale-lock release -- there is no timer, because a clock that steals from someone actively working is worse than a human deciding to take it. USER-scoped (bd polyglot-pdf-5tuas): the lock stores the holder's uid, so a second editor is refused 409 and the refusal NAMES the holder. Re-taking your OWN lock is not a steal. A pre-5tuas lock has no uid, so same-role contention falls back to ALLOW for it rather than stranding anyone. `heldBy` stays a ROLE on the wire; `heldByLabel` carries the person. Returns `{ok, kitId, heldBy, preempted}`. Editor-tier (per-person Firebase claim). |
| POST | `/api/editor/kits/{kit_id}/readiness` | Recompute + persist the kit's readiness stamp for the POSTED schema (the local-save stamp refresher, sprint-18 C4b bd na1zy; same `_stamp_readiness` as the hosted save). 409 on write-locked kits (submitted, complete or unpublished) -- a published revision's stamp only changes through the publish flow. ALSO 409 when a different editor holds the kit's edit lock (bd polyglot-pdf-fwzln) -- this route writes metadata like every sibling write path, so it needs the same `_require_edit_lock` guard; the refusal names the holder. Editor-tier (per-person Firebase claim). `backend/routes/editor_readiness_routes.py`. |
| POST | `/api/editor/kits/{kit_id}/regenerate-guidance` | Re-author field guidance from the kit's instruction booklet (bd polyglot-pdf-cpiw) -- the costly half of the staleness gate, opposite "acknowledge". Optional `fieldIds` scopes the rewrite (the natural call from the staleness banner); omitted means every askable field. Guidance a HUMAN edited is never clobbered (per-channel hashes vs. provenance). A successful rewrite re-stamps `identity_sha1`, which is what CLEARS the staleness flag. Author-only (spends model tokens + rewrites the schema); 409 on complete. |
| POST | `/api/editor/kits/{kit_id}/repair` | One-click Repair-all for a stored draft (bd polyglot-pdf-zgln): runs the SAME deterministic `backend/services/schema_repair.repair()` the CLI extraction pass runs, against the schema + its persisted `acroform.json` dump, so the result equals CLI repair on the same input. Reports what changed plus POST-repair lint counts. **Author-only** (it mutates the stored schema). A draft referencing nonexistent PDF widgets is a 422 naming them, not a 500 -- repair cannot invent mappings. 409 on a complete kit. |
| GET | `/api/editor/kits/{kit_id}/retire-candidates` | Live kits that plausibly serve the SAME FORM as this one, so the publish modal can ask which older version to retire (bd polyglot-pdf-bdedm). A SUGGESTION -- it retires nothing; the author ticks one and it rides the publish as `replaces_kit_id`. AUTHOR-ONLY, matching the publish it feeds. Matches on `form_number` first (a declared mismatch DECIDES -- it never falls through to the label, or an identical label would override two different numbers and offer I-130A when publishing I-130), then EXACT normalised label equality. Deliberately conservative: real form families differ by a one-character suffix and several variants are supplements filed ALONGSIDE their base, so a missed suggestion costs one manual retire while a wrong one asks an author to retire a live form. Each candidate carries kit id, label, form number and whichever revision marker it actually has (`edition_date` > `author_version` > `published_at`), plus WHY it matched, so a human can tell two same-numbered kits apart. Reads one schema per live kit -- confined to this route so the cost lands only when an author is publishing, never on a catalogue render. Author-tier (per-person Firebase claim). |
| GET | `/api/editor/kits/{kit_id}/schema`, `.../pdf` | Draft-capable single-kit reads for the hosted editor. Editor-tier (per-person Firebase claim). |
| PUT | `/api/editor/kits/{kit_id}/schema` | Save an edited schema back to the store (lenient draft save). Editor-tier (per-person Firebase claim). |
| POST | `/api/editor/kits/{kit_id}/status` | Set `draft` \| `submitted` \| `complete` \| `unpublished`. **THE ROLE DEPENDS ON THE TRANSITION, not the route** (bd polyglot-pdf-hqztg): an EDITOR may `draft -> submitted` ("I believe this is ready") and reopen their own submission, but publishing (`-> complete`) and reaching back into a LIVE kit (`complete -> draft`) are AUTHOR-ONLY -- editors are subcontractors, so marking a form ready must not release it. `submitted` is write-locked like complete, or an author would review one version and publish another; the editor reopens it deliberately via Revert to draft, which CLEARS any author version (a submitted kit was never live, so no confirmation record names it). Promotion validates against the Pydantic `FormSchema` AND requires zero schema-lint ERRORs (`backend/services/schema_lint.py`; violations 409 naming the findings -- bd h76m.5). `unpublished` retires a superseded revision: hidden like a draft but WRITE-LOCKED like complete, and never revertible to draft (bd polyglot-pdf-6dz0). Optional `replaces_kit_id` retires another live kit for the same form as part of this publish, archiving it first. A kit whose schema has no `form_metadata.edition_date` must supply `author_version` to publish -- the refusal is a 422 prefixed `AUTHOR_VERSION_REQUIRED:`, which the editor keys on to open its version dialog; the value is normalized server-side and IMMUTABLE once published (bd polyglot-pdf-xzw5). Editor-tier (per-person Firebase claim). |
| POST | `/api/editor/kits/{kit_id}/translate-options` | Author-tier standalone option-label translation bake (OPTION_TRANSLATION_MODEL, in-process, idempotent; `?force=true` retranslates after label renames; 409 on any write-locked kit -- complete OR unpublished -- bd 2h9j). Returns the verify/rectify gate's `flags` and persists them at `_bakeoff.authoring.option_translation`, where schema-lint re-emits them as WARNINGs for the editor ValidationPanel (bd 9djc). Author-tier (per-person Firebase claim). |
| GET | `/api/editor/kits/{kit_id}/unclaimed-widgets` | The kit's PDF button widgets that no field/option claims (bd nivy), powering the "Add from PDF widgets" picker when the extractor missed a checkbox/radio. Read from the persisted `acroform.json` dump; a pre-dump kit returns an empty list. Author-only (it feeds an author-only PDF-mapped option edit). |
| POST | `/api/editor/lint`, `/api/editor/kits/{kit_id}/lint` | Lint the POSTED (possibly-unsaved) schema over the single Python ruleset (`backend/services/schema_lint.py`). The kit-scoped form additionally loads the kit's persisted `acroform.json` dump -- the SAME inputs as the `/status` promotion gate -- so the editor strip sees the dump-gated widget-claim rules live (sprint-18 C1, bd o7y9); the dumpless form remains for schemas with no kit identity. Editor-tier (per-person Firebase claim). |
| GET | `/api/editor/session` | Hosted-editor sign-in probe -> `{role}`; the gate calls it once the person signs in, to learn whether they hold editor access at all (bd polyglot-pdf-yswp3). Per-user Firebase identity (bd polyglot-pdf-hn0jq): the ID token rides `Authorization: Bearer` -- ONLY, since bd polyglot-pdf-rhc2v retired the `X-Editor-Token` header along with the shared secrets. 401 for a token that does not verify, 403 for a valid account without the `schema_editor_role` claim -- and that 403 is prefixed `NO_EDITOR_ACCESS:` (`editor_auth.NO_EDITOR_ACCESS_PREFIX`) to distinguish it from the OTHER 403s an editor legitimately meets (`require_author_actor`, and the per-transition publish gates on `/status`). Only the prefixed one means "you hold no editor role at all"; the client evicts to its refused screen on that and shows the rest as ordinary refusals, so an editor pressing an author-only button is not thrown out of the editor (bd polyglot-pdf-yswp3). There is no unconfigured-surface 503 -- there is no shared secret left to omit. Grant access with `scripts/bootstrap_editor_user.py`. `components/pdf-filling.md` |
| POST | `/api/editor/store-handshake` | Confirm the editor and the backend are looking at the SAME local folder: the editor writes a nonce file into the folder the human picked, this reads it from the backend's own root and reports whether it matches. Read-only on the backend side -- it never creates or deletes the marker, so an unwritable store simply reports no match rather than failing. The `reason` values it actually returns are `not-a-local-store` (GCS; hosted mode never calls it), `mismatch` (no marker observed -- the editor, having just attempted the write, picks the user-facing message) and `stale` (a marker from an earlier session in a different folder). Editor-tier (per-person Firebase claim). |
| POST | `/api/fill-pdf` | Render the filled PDF (PyMuPDF). **Auth-gated** (`Authorization: Bearer <idToken>` via `require_auth`; bd z2is) + **firm-scoped** (bd vy6id: the body's caller-supplied `kit_id` runs the same visibility gate as the kit reads -- a private kit 404s for non-members). `components/pdf-filling.md` |
| GET | `/api/form-kits` | Form-kit manifest (metadata only; GCS/deployed manifest is complete-only, local mode lists any kit with a schema). **Auth-gated** (bd z2is) + **firm-scoped** (bd vccy): PRIVATE kits appear only for callers whose `firm_id` claim resolves to an allowlist containing them, with paths rewritten to the authenticated backend routes. `components/pdf-filling.md` |
| GET | `/api/form-kits/{kit_id}/archive` | A kit's superseded revisions, newest-first by the archived snapshot's `published_at`. **Auth-gated + firm-scoped** (bd qfyxr + polyglot-pdf-65hgz: firm-visibility gate identical to the schema read, but the status gate is WIDER -- complete OR unpublished, so a firm keeps its history after retiring the form). |
| GET | `/api/form-kits/{kit_id}/archive/{marker}/schema` | One archived revision's schema, READ-ONLY (no write counterpart exists -- superseded bytes are what the audit trail names). **Auth-gated + firm-scoped** (bd qfyxr); marker validated to `encode_marker`'s contract. |
| GET | `/api/form-kits/{kit_id}/pdf` | A single kit's PDF bytes, streamed from the store. **Public for PUBLIC kits** (their blank-template bytes ship in the static bundle regardless -- bd z2is); a PRIVATE kit needs a bearer token whose firm allowlist contains it, else 404 (bd vccy; invalid token degrades to anonymous -- existence is the secret). |
| POST | `/api/form-kits/{kit_id}/retire` | Retire a form THIS FIRM owns (status -> `unpublished`), archiving the revision first. **Auth-gated + firm-scoped**, and authorization is three further checks (bd `polyglot-pdf-z6bk9`): `firm_role=manager` AND `owner_firm_id` == the caller's firm AND `visibility=private` -- so a firm can never retire a shared/government kit, nor one it merely licenses. EVERY refusal is 404, never 403 (existence is the secret). Not a delete: hard delete stays staff-only and guarded. No UI ships yet -- the button belongs to the firm console (bd `polyglot-pdf-gob8l`). `components/auth.md` |
| GET | `/api/form-kits/{kit_id}/schema` | A single kit's schema JSON, streamed from the store (works local + gcs; `no-store`). **Auth-gated** (bd z2is) + **firm-scoped** (bd vccy: a private kit 404s for non-members). |
| POST | `/api/links/mint` | Mint a ONE-TIME client link for a form the firm may use. **Auth-gated** (per-user Firebase; the employee's `uid` becomes the link's `employee_id`, so every session traces to who sent it) + firm-scoped (the kit must be in the firm's allowlist, else 404). Returns the URL and the `jti` -- the firm's JOIN KEY for matching their client to our pseudonymous record. **404 unless `LINK_MINTING_ENABLED`** (default false; the spend ceiling it waited on, bd `polyglot-pdf-ik7e`, has landed). `LINK_MINTING_ENABLED` is now a RUNTIME setting read from `app_config/{channel}` in Firestore via `backend/services/runtime_config.py` (bd `polyglot-pdf-bg313`), TTL-cached, with the deploy-time `LINK_MINTING_ENABLED` env var still read as the fallback until a channel has a Firestore value -- an operator can override it per channel with `scripts/set_runtime_config.py` (or the admin console once bd `polyglot-pdf-li9x0` ships its route) with no redeploy. Consumed by the staff mint page at `/console/links` (bd `polyglot-pdf-gob8l`). `components/auth.md` |
| POST | `/api/links/open` | Redeem a client link. **UNAUTHENTICATED BY DESIGN** -- a client has no account, so the signed token IS the credential (bd `polyglot-pdf-ugm6`). Enforces one-time use, the open/complete windows, and re-checks firm entitlement at open rather than trusting the mint-time snapshot. EVERY failure returns the same 404 so the response cannot be used as an oracle. `components/auth.md` |
| POST | `/api/resume-form` | Verify a client's SAVED PDF and return the answers inside it (bd `polyglot-pdf-dft1`). **Auth-gated** (`require_auth`) and **firm-scoped** by the same gate chain as `/api/fill-pdf`, so a client link resolves to the one kit it was minted for. The upload is attacker-controlled: it must be STRUCTURALLY identical to that kit's own form.pdf (`services/pdf_structure.py`) before a single value is read out of it. `components/pdf-filling.md` |
| POST | `/api/tts/intro` | Sol's scripted intro+disclaimer clip (sprint 20, bd s1iex.3). KEYED route: `{form_number, language}` resolve against server-side tables only (`intro_tts.KNOWN_FORMS` + `intro_script.json` + `intro_agree_labels.json`) so caller text never enters synthesis; unknown form -> 400, unknown language -> English fallback. In-process cache per `(language, form, script_hash)`; `Cache-Control: private` + ETag with If-None-Match 304, plus `X-Intro-Script-Version` (the script hash the acceptance record echoes, bd s1iex.7 -- both headers need CORS `expose_headers` to be readable cross-origin); 0 dB gain (the spell-back +4 dB clips ~90s clips). **Auth-gated**; 503 unless `INTRO_TTS_ENABLED`. `backend/services/intro_tts.py` |
| POST | `/api/tts/notice` | Speak one of the app's OWN safety notices (bd `polyglot-pdf-dft1`). **Auth-gated** (`require_auth`) and deliberately NOT `require_paid_client_work`: the paid dependency redeems the link, which would answer a budget-exhausted client with silence and burn a live client's link to deliver a warning we chose to give. Caller sends a KEY, never text, so being free does not make it an open text-to-speech service. In-process cache per `(language, notice_key)`; `Cache-Control: private` + ETag with If-None-Match 304 (bd polyglot-pdf-see5j). `backend/services/notice_tts.py` |
| POST | `/api/tts/spellback` | Deterministic spell-back verification clip (Cloud TTS, session language + persona voice; the value is PII -- never logged, lengths only; 60-char input cap). **Auth-gated**; 503 unless `SPELLBACK_TOOL_ENABLED` (default ON since bd polyglot-pdf-apkdl; bd 22h1f/44ywm). `backend/routes/tts_routes.py`, `backend/services/spellback_tts.py` |
| POST | `/dev/console-log` | Dev-only console-log ingest (404 in prod; no `/api` prefix). `frontend/src/shared/devConsoleCapture.ts`, `backend/routes/dev_console_routes.py`. |
| GET | `/health` | Liveness + reports active models, audio rates, limits, key-presence. The ADMIN service serves a different `/health` at its own hostname -- see "Admin service routes" below. |
| GET | `/version` | `{version, git_sha}` (bd `polyglot-pdf-9hzod`) -- `git_sha` reads the `GIT_SHA` runtime env var, `"unknown"` when unset or empty. The admin service serves its own `/version` at its own hostname. |
| WS | `/ws/audio`, `/ws/echo` | Lower-level / debug audio sockets. **Dev-only**: handshake rejected unless the `backend/.env.DEV` marker exists (same gate as `/dev/console-log`; bd polyglot-pdf-puu8). `components/websocket-routing.md` |
| WS | `/ws/fill` (+ `/api/ws/fill`) | The voice form-fill session. Requires `?token=<Firebase idToken>`. `components/websocket-routing.md`, `components/voice-ai.md` |

## Admin service routes

The privileged admin service (`admin_backend.main:app`, Cloud Run service
`polyglot-admin`) is a **separate deployment on its own hostname**, running the
same image with `APP_MODULE=admin_backend.main:app`. Its paths therefore do not
collide with the public backend's despite sharing names -- `/health` on the
admin host is the row below, not the one above.

Same rules as the table above: sorted by **path, then method**, and pinned
against `admin_backend.main:app` by the same
`tests/test_technical_guide_routes_table.py` (the checks are parametrized over
every ASGI app the `Dockerfile` copies, so a third service cannot ship without
its own table).

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/audit` | The admin audit log, newest first (bd `polyglot-pdf-li9x0`). Optional equality filters `action`, `actor_uid`, `channel`, `state`; page size `limit` (default 50, max 200) and an opaque `cursor`. The cursor is the last row's `ts` and document id joined by a pipe -- Firestore's `offset` still reads and bills the skipped documents, so a deep page would get slower and dearer the further back an operator scrolled. Ordered by `ts` then `__name__` DESCENDING: the document-id tiebreaker is what makes a page boundary total, so a walk can neither repeat nor drop a row when two rows share a timestamp. The response is `{rows, next_cursor}`, `next_cursor` null on the last page. Reads are NOT audited; a row per read would bury the mutations. Each filter needs a composite index (`firestore.indexes.json`, deployed by `deploy-demo.sh`) -- see Surface contract 15. `admin_backend/routes/audit_routes.py` |
| GET | `/admin/config/{channel}` | The channel's stored `app_config/{channel}` doc (bd `polyglot-pdf-li9x0`), returned RAW rather than coerced -- a malformed value `runtime_config` would ignore stays visible on the one screen meant to diagnose it, with `unknown_keys` naming entries no backend reads. `channel` must be one of `KNOWN_CHANNELS` (`demo`, `staging`), else 404. `admin_backend/routes/config_routes.py` |
| PUT | `/admin/config/{channel}` | Set ONE runtime-config key for one channel, **audited in the same Firestore transaction as the write** (bd `polyglot-pdf-li9x0`) -- the first consumer of `audit_log.record_in_transaction`. Body `{key, value}`; refuses BEFORE any write on an unknown channel (404), a key outside `runtime_config.RUNTIME_CONFIG_KEYS` (400), or a value `runtime_config.coerce_value` rejects (400 -- storing one would look like success in the console while the backend kept the old value). Writes with `merge=True`, so the channel's other keys survive. See Surface contracts 14 (runtime config) and 15 (the audit log). `admin_backend/routes/config_routes.py` |
| GET | `/admin/firms` | Every firm, with `kind`, `balance_credits` and `status` (bd `polyglot-pdf-zopqq`), unfiltered -- the bead names columns, not filters, so no composite index is owed the way `/admin/audit`'s filters are. A read, so no audit row. `admin_backend/routes/firm_routes.py` |
| POST | `/admin/firms` | Create a firm (bd `polyglot-pdf-zopqq`). Body `{firm_id, name, contact_email, kind, allowed_kits?, status?}` -- `kind` is REQUIRED with NO default (422 if missing or not `mock`/`live`), matching `upsert_firm`'s own required parameter. Writes the SAME field shape as `backend/services/firms.py::upsert_firm` but does NOT call it: this route needs the doc write and the audit row in one `@firestore.transactional` body (contract 15's in-transaction form), and `upsert_firm` does its own non-transactional read+write -- calling it from inside a transaction would add a second, transaction-illegal read. `admin_backend/routes/firm_routes.py` |
| GET | `/admin/firms/{firm_id}` | One firm's profile, balance, and a page of ledger rows (bd `polyglot-pdf-zopqq`). **Runs `credit_ledger.reconcile_expired_for_firm` once per known channel (`demo`, `staging`) BEFORE reading the balance** -- a lazy, best-effort catch-up for expired unopened links the hourly sweep (bd `polyglot-pdf-8vgfh`, below) has not reached, so the balance shown reflects any refund that catch-up applies. A per-channel reconciliation failure is logged and skipped, never 500s the page. `?ledger_limit=` (default 50, max 200) pages the newest-first ledger view. A read, so no audit row. `admin_backend/routes/firm_routes.py` |
| PATCH | `/admin/firms/{firm_id}/allowed_kits` | Replace a firm's private-kit allowlist (bd `polyglot-pdf-zopqq`). Body `{allowed_kits}` (a full replace, matching `upsert_firm`'s no-partial-update contract, though this route re-writes the doc itself in its own transaction rather than calling `upsert_firm` -- see the POST `/admin/firms` row above). Audited in-transaction. `admin_backend/routes/firm_routes.py` |
| POST | `/admin/firms/{firm_id}/credits/adjust` | The operator's signed adjustment (bd `polyglot-pdf-zopqq`). Body `{amount, reason}` -- `amount` may be positive or negative, `reason` is REQUIRED (422 if blank). Calls `backend/services/credit_ledger.py::append_entry` with `entry_type=adjustment`, `actor=` the admin's uid, `channel=None`. Audited via `append_entry`'s `extra_writes` hook, joined to its OWN Firestore transaction (see Surface contract 18) -- a forced audit failure leaves the balance unchanged. `admin_backend/routes/credit_routes.py` |
| POST | `/admin/firms/{firm_id}/credits/grant` | Grant credits (bd `polyglot-pdf-zopqq`). Body `{type, amount, usd_amount?, kit_id?}` -- `type` in `subscription_grant`\|`purchase`\|`promo_grant`; `usd_amount` REQUIRED for the first two and REFUSED otherwise (422), exactly as `append_entry`'s own validation enforces. Grants to `kind=mock` firms are allowed (staging needs credits to test); `firm_kind` is snapshotted onto the entry by `append_entry` itself. Same in-transaction audit form as `adjust`. `admin_backend/routes/credit_routes.py` |
| PATCH | `/admin/firms/{firm_id}/kind` | Reclassify a firm `mock`<->`live` (bd `polyglot-pdf-zopqq`). Body `{kind, reason}` -- `reason` is REQUIRED (422 if blank); the UI's confirm-twice is a console-side control this route cannot see or enforce. Audited in-transaction. `admin_backend/routes/firm_routes.py` |
| GET | `/admin/firms/{firm_id}/links` | The firm's client links (bd `polyglot-pdf-jmiys`, Track B bead B4), joining `links[_<channel>]` mint records (bd A1) with `link_redemptions[_<channel>]` detail (`opened_at`, `completed_at`, bead ik7e's `spend_usd`/`turns`) by `jti`. `?channel=` REQUIRED (422 if missing/unknown -- the admin service has no channel of its own); `?status=`/`?employee_id=` optional equality filters. Gate: `require_app_admin_or_owning_manager` -- a manager reaches only their OWN `firm_id` (404 for any other, the SAME 404 an unknown firm would get -- NOT `resolve_target_firm`'s body-field 403 rule, since `firm_id` here is a URL path segment a manager must name to reach a GET at all; see Surface contract 22); an app admin reaches any. Response rows are an EXPLICIT key allowlist, built by hand rather than `**doc`. A read, so no audit row. `admin_backend/routes/link_routes.py` |
| PATCH | `/admin/firms/{firm_id}/status` | Set a firm `active`\|`suspended` (bd `polyglot-pdf-zopqq`). Body `{status}`. Audited in-transaction. `admin_backend/routes/firm_routes.py` |
| GET | `/admin/kits` | Every kit in the form-kit store (bd `polyglot-pdf-f0kuu`, Track B bead B3), each joined with its resolved commercial doc (or the global defaults) via the SAME reader `GET /admin/kits/{kit_id}/commercial` and the mint transaction use (Surface contract 24) -- so this list can never disagree with what a mint actually charges. `list_kit_ids()` is ASYNC (the store may be GCS-backed), awaited directly rather than run under `asyncio.to_thread`. A read, so no audit row. `admin_backend/routes/kit_routes.py` |
| GET | `/admin/kits/{kit_id}/commercial` | One kit's resolved credit price and USD spend ceiling (bd `polyglot-pdf-f0kuu`, Track B bead B3), via `backend/services/kit_commercials.py::resolve_commercial` -- the SAME reader bead A3's mint transaction calls (Surface contract 24). `source` is `"kit"` when a commercial doc exists, `"default"` when it does not. A read, so no audit row. `admin_backend/routes/kit_routes.py` |
| PUT | `/admin/kits/{kit_id}/commercial` | Set a kit's `credit_cost`, `burn_cap_usd` and `display` (bd `polyglot-pdf-f0kuu`, Track B bead B3). Refuses BEFORE any write on a malformed `credit_cost` (must be a positive int; bool refused), `burn_cap_usd` (must be a positive finite float; bool/NaN/+-inf refused) or `display` (a small string map) -- 422, so a bad edit can never reach the store as a "successful" write the read side's fallback would then paper over. Audited in the SAME `@firestore.transactional` body as the write (mirrors `firm_routes.py`'s `_apply_firm_patch` shape). `admin_backend/routes/kit_routes.py` |
| POST | `/admin/links/sweep-expired` | The hourly expired-link refund sweep (bd `polyglot-pdf-8vgfh`, plan: "Refund on unopened expiry"). Gate: `require_google_oidc(audience, allowed_caller_emails)` -- the FOURTH and last admin-service gate, its first consumer. Cloud Scheduler presents a Google-signed OIDC token; the gate checks the token's `aud` against this route's own URL -- the bare `ADMIN_SERVICE_URL` env var (service root) with the route's own path appended -- AND its `email` claim against the scheduler job's service account (`SWEEP_SCHEDULER_SA_EMAIL` env var); both env vars are set automatically by `deploy-admin.sh` on every run -- on a public (`--allow-unauthenticated`) service, a matching audience alone is forgeable by anyone with a GCP project, so it is not by itself proof of caller identity. Optional `?channel=` sweeps one channel (404 on an unknown value); omitted, sweeps every channel in `KNOWN_CHANNELS`. Per channel, queries `links[_<channel>]` for `status == minted AND open_deadline < now` and calls bead A5's `credit_ledger.refund_expired_link()` once per hit, which itself re-reads `link_redemptions` first and refuses an opened link -- this route adds no refund logic of its own. Each committed refund's audit row is written IN THE SAME Firestore transaction as the refund via `refund_expired_link`'s `extra_writes` parameter (bd `polyglot-pdf-8vgfh`'s extension to that A5 helper) -- the SAME extra_writes-delegated shape of Surface contract 15's `MUTATION_KIND_FIRESTORE` the credit routes above use (see `_EXTRA_WRITES_TRANSACTION_OPENERS`). A per-link failure is logged and skipped rather than aborting the whole pass. Returns `{results: [{channel, refunded, skipped}], total_refunded, total_skipped}` -- counts only; the ledger entry and the audit row are the durable record. `admin_backend/routes/sweep_routes.py`, `admin_backend/services/admin_auth.py`, `backend/services/credit_ledger.py` |
| POST | `/admin/links/{jti}/revoke` | Revoke a minted link (bd `polyglot-pdf-jmiys`, Track B bead B4). `?channel=` REQUIRED. One `@firestore.transactional` body (mirrors `firm_routes.py`'s `_apply_firm_patch` shape -- there is no balance mutation to join via `credit_ledger`'s `extra_writes` hook, since revoke touches only the link's own `status`) sets `status=revoked` with `revoked_by`/`revoked_at`, audited in the SAME transaction. Only a `minted` record may transition (409, naming the current status, otherwise). Gate: `require_app_admin_or_owning_manager` -- a manager may revoke only a jti belonging to their own firm (404 otherwise, same as an unknown jti); an app admin may revoke any. This status flip is what Epic 2 Track A bead A3's open gate (`backend/routes/link_routes.py`) must refuse on once it lands -- see Surface contract 22. `admin_backend/routes/link_routes.py` |
| GET | `/admin/users` | The firm's staff pool (bd `polyglot-pdf-dmjl5`). `?firm_id=` for an app admin; a firm manager sends none and gets their own. `list_users()` plus a CLIENT-SIDE claims filter -- Firebase Auth has no server-side query over custom claims -- which is affordable only because the pool is firm staff, editors and devs: clients never get accounts, so this list does not grow with a firm's caseload and no members mirror is needed. Response is `{firm_id, users, truncated}`; each row is an EXPLICIT key allowlist, so a future internal claim does not reach the console the day it appears. A read, so no audit row. `admin_backend/routes/user_routes.py` |
| POST | `/admin/users` | Create a staff account for a firm and return a password-**reset link** (bd `polyglot-pdf-dmjl5`). Body `{email, firm_role, firm_id?, display_name?}`. Gate: `require_app_admin_or_owning_manager` -- an app admin MUST name a firm (422 otherwise), a firm manager may NOT name one (403, even their own; see Surface contract 19). Creates the Firebase account with an unguessable random password that is never returned or logged, then stamps ONLY `firm_id` + `firm_role` merged over existing claims. NO outbound email in this epic: the console displays the link. 409 on a duplicate address; 422 on a role outside `{manager, employee}` or a firm slug failing `FIRM_ID_RE`. Audited pending-then-committed (contract 15). `admin_backend/routes/user_routes.py`, `admin_backend/services/user_admin.py` |
| PATCH | `/admin/users/{uid}/disable` | Disable or re-enable a staff account (bd `polyglot-pdf-dmjl5`). Body `{disabled, firm_id?}` -- an explicit value, not a toggle, so a retrying console cannot land in whichever state the race decided. Claims are untouched: disabling is not deleting, and a deleted uid would take its audit trail's subject with it. The account must already be in the resolved firm, else the SAME 404 a nonexistent uid gets (a 403 would confirm a guessed uid names a real account). `admin_backend/routes/user_routes.py` |
| PATCH | `/admin/users/{uid}/role` | Move a staff account between `manager` and `employee` (bd `polyglot-pdf-dmjl5`). Body `{firm_role, firm_id?}`. Merges over every other claim, so a promotion cannot strip the account's `vff_dev` or `schema_editor_role`. Same firm-scoping 404 as disable, so this route cannot move an account between firms however the request is shaped. `admin_backend/routes/user_routes.py` |
| GET | `/admin/whoami` | The FIRST gated route (bd `polyglot-pdf-7w17m`): returns `{uid, email}` for the caller, gated by `require_app_admin`. Exists to prove the gate end to end before any business logic lands -- a stamped account passes, a valid unstamped account 403s with the `NO_ADMIN_ACCESS:` prefix, a tokenless caller 401s. `admin_backend/routes/whoami.py`, `admin_backend/services/admin_auth.py` |
| GET | `/health` | Liveness + identity. Deliberately THIN next to the public backend's: this service proxies no model and owns no confirmation sink. Reports `app_module` -- the ASGI target the container actually launched -- because `APP_MODULE` is a runtime env var, so a service pointed at the wrong module would otherwise look healthy while serving the wrong app. **Unauthenticated by design** (the liveness probe; it reports nothing an unauthenticated caller could not infer) and, together with `/version`, the ONLY routes that stay so -- every other route on this service carries one of the four gates named in `admin_backend/tests/unit/test_admin_route_auth.py`. `deploy-all.sh`'s IAM-based reachability check still issues no HTTP request against it, but `deploy-admin.sh`'s tagged flow (bd `polyglot-pdf-3l2vp`) DOES curl this exact route at the tagged candidate revision's stable URL and aborts the traffic shift on anything but a 200 -- so for the admin service, this route is now exercised by a real deploy gate, not just by an operator's manual curl. `admin_backend/main.py` |
| GET | `/version` | `{version, git_sha}` (bd `polyglot-pdf-9hzod`, same GIT_SHA env var and "unknown" fallback as the public backend's `/version`) -- the admin app's own `version`, not the public backend's. `admin_backend/main.py` |

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
- **Turn-taking is push-to-talk, and only push-to-talk.** Gemini's automatic
  activity detection is unconditionally disabled; the frontend brackets every turn
  with explicit `activity_start`/`activity_end`. There is no mode flag -- PTT knows
  when the user is speaking, so a second detector inferring it could only disagree
  (bd polyglot-pdf-v1m8g). (See `standards/voice-and-vad.md`.)
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
  (`save_editor_kit_schema` in `editor_kit_routes.py`) check just that
  `fields` is a list and write the raw dict via the store
  (`FormKitStore.put_schema`, `backend/services/form_kits.py:324` abstract /
  `LocalFormKitStore.put_schema` :605 local / `GCSFormKitStore.put_schema`
  :1172 GCS). The one chokepoint is "mark complete"
  (`set_editor_kit_status` in `editor_kit_routes.py`):
  `FormSchema.model_validate` plus the zero-ERROR schema-lint gate
  (`lint_schema`, `backend/services/schema_lint.py:833`, checked via its own
  `lint_schema` call further down the same function). Every read path
  streams the raw stored dict unvalidated (`get_form_kit_schema`,
  `backend/routes/form_kit_routes.py:233-257`; `get_editor_kit_schema` in
  `editor_kit_routes.py`, which loads and returns the schema with no
  validation at all). *Breaks if bypassed:* a hand-edited or
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
    (`resolve_edition_marker`, defined in `backend/utils/confirmation_logger.py`,
    called from `form_filling_service.py`). The key is
    `form_metadata`, NOT `metadata` -- the wrong name no-ops the whole reference
    block with zero signal (in-source note at `secretary_context.py:227-230`).
  - Legacy `controls_fields`/`conditional_fields`: REMOVED from the model and
    `extra="ignore"`-dropped by Pydantic (`form_models.py:942-957`); only
    schema-lint (`schema_lint.py:891-902`) errors on them. A stale kit that skips
    lint publishes with its trigger-side behavior silently deleted.

### 2. WS handshake: client -> backend (`/ws/fill` first frame)

Producer: `getHandshakePayload` (legacy, `frontend/src/schema-forms/state/schemaFormState.ts`)
/ `getJITHandshakePayload` (DTI, :1015), sent by `frontend/src/webFormConnection.ts`'s
`this.send(handshake)` call.
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
- `full_schema` (sent by `schemaFormState.ts`'s `getHandshakePayload` and
  `getJITHandshakePayload`): type-checked
  `isinstance(dict)` only (the `full_schema` type-check right after handshake
  parsing), cached in
  `form_filling_service.py`'s `self._full_schema = full_schema` assignment
  (preserved across internal restarts), then read
  by `handle_ask_secretary` (`form_filling_service.py`'s
  `self._full_schema or self._schema` read) and rendered into the secretary catalog by
  `render_static_catalog(schema)` in `text_ai_gemini.py:302`, the edition fingerprint
  (`resolve_edition_marker` call in `form_filling_service.py`), the injection
  budget (`guidance_contract.inline_injection_budget_tokens` calls in
  `form_filling_service.py`, two call sites), and runtime translation overrides
  (`_maybe_start_option_translation` call in `form_filling_service.py` ->
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
Server->client: one dispatch switch at `frontend/src/webFormConnection.ts`'s
`switch (message.type)` block.
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
`webFormConnection.ts`'s `sendConfirmFieldResponse` /
`sendSkipFieldResponse` / `sendSwitchFieldResponse` /
`sendSpellbackResponse`.

Known traps (all deliberate, all pinned only by comments):
- The frontend still carries a dead `case "field_update"`
  (`webFormConnection.ts`, expecting an `updates: Record<name, value>`
  shape) with **no live backend producer** -- field updates ride `form_updated`
  (`backend/services/callback_handler.py`'s `send_form_update`) with a different
  `data.form_state`/`data.applied_fields` shape. Never reintroduce a
  `field_update` producer against the old shape.
- `change_spoken_language` is a wire-compat misnomer -- it re-asserts the pinned
  session language, it does not change it (websocket_routes.py's
  `change_spoken_language` arm).
- `validation_result` carries `conflicts` only; the Python-side `result_type`
  label is deliberately never serialized (`_run_validation_and_push` in
  websocket_routes.py, contract pinned in `standards/validation-delegation.md`).
- `voice_mode` is CLIENT-OWNED and must be RE-SENT on every (re)connect
  (bd polyglot-pdf-wurj8). Producer: `webFormConnection.ts`'s `setVoiceMode`,
  called from the manager's `setVoiceMode` and from `reassertVoiceMode` in the
  `onSessionReady` / `onSessionRestarted` callbacks. Consumer: the `voice_mode`
  arm in `websocket_routes.py` -> `FormFillingService.set_voice_muted` ->
  `LiveAIGemini.set_voice_muted`. The backend holds NO per-session mode across a
  reconnect (it is stateless, and each new Gemini session defaults to speaking),
  so a client that sends the mode only once silently drops the user back into a
  talking session on the next GoAway or auto-drop. `vad_activity_start` also
  clears the mute on BOTH ends, so a PTT press never lands in silence -- removing
  either half leaves the other looking correct in isolation.
- The `session_ready` message carries NO VAD-mode flag (bd polyglot-pdf-v1m8g).
  It used to send `native_vad`, which the client destructured to pick its
  activity-signal behavior; both ends are gone, and the client now always sends
  manual activity signals. A re-added flag would be a contract change on both
  sides, not a backend-only toggle.

### 4. Backend <-> Gemini Live (tools + session config)

Tool names + arg schemas have ONE source of truth:
`Settings.TOOL_DECLARATIONS` (the list literal in `backend/config.py`),
deep-copied into the live config by `form_filling_service.py`'s
`_build_tool_declarations` (which drops `switch_section`
in continuous mode, and appends `SPELLBACK_TOOL_DECLARATION` under
`SPELLBACK_TOOL_ENABLED` -- default ON since bd polyglot-pdf-apkdl, so a
production session ships 7 declarations; setting the flag false rolls back to 6,
bd polyglot-pdf-22h1f) and declared to
Gemini in `_build_live_config` (`backend/adapters/live_ai_gemini.py`;
tools assembled into `tools_config` in the same method). Gemini's tool
calls come back through the adapter (`self._on_tool_call(...)` call sites in
`live_ai_gemini.py`, two sites)
into `CallbackHandler.on_tool_call`, which dispatches to the
`form_filling_service` handlers that emit the Leg-A
client messages above. The coupling table (tool -> handler -> client message);
each row's branch is `on_tool_call`'s `if normalized == "<tool>"` (or, for
`get_form_status`, `if normalized in {"get_form_status", "get_form_state"}`):

| Gemini tool (args) | Handler (`callback_handler.py`, dispatch branch) | Client message |
|---|---|---|
| `update_form_fields` (`field_id`, `value`) | `normalized == "update_form_fields"` | `form_updated` |
| `get_form_status` (`field_ids`) | `normalized in {"get_form_status", "get_form_state"}` | `get_form_state` round-trip |
| `confirm_field` (`field_id`, `confirmation_method`) | `normalized == "confirm_field"` | `confirm_field` round-trip |
| `skip_field` (`field_id`) | `normalized == "skip_field"` | `skip_field` round-trip |
| `switch_to_field` (`field`) | `normalized == "switch_to_field"` | `switch_field` round-trip -- **the tool name and the wire type differ on purpose** |
| `ask_secretary` (`query`) | `normalized == "ask_secretary"` | none -- answered server-side from the cached `full_schema` |
| `switch_section` (deprecated; dropped in continuous mode) | `normalized == "switch_section"` | internal session restart + `section_switched` |
| `name_spellback` (no args; `SPELLBACK_TOOL_ENABLED` default ON, declared via `SPELLBACK_TOOL_DECLARATION` -- kept out of `TOOL_DECLARATIONS` so the flag stays a real rollback) | `_handle_name_spellback_tool` | `spellback` round-trip + client HTTP `POST /api/tts/spellback` (bd polyglot-pdf-22h1f) |

Field values never cross to Gemini as structured data -- they are rendered into
guidance prose by `ai_context.render_field_guidance`
(`backend/services/ai_context.py`); the contract there is between the SI
templates and the prose, not key names. System instruction:
`form_filling_service.build_form_context_message`
(`form_filling_service.py`) ->
`ai_context.build_form_context`.

### 5. Fill round-trip: sessionStorage -> `/api/fill-pdf` -> AcroForm

Producer: client state `SchemaFormState.fieldValues`
(`frontend/src/schema-forms/state/schemaFormState.ts`, the `jitModeEnabled`
field on `SchemaFormState`, persisted by `save`).
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
  `set_editor_kit_status`, feeding `lint_schema`'s dump-gated widget-claim
  checks in `backend/services/schema_lint.py` -- a separate `_load_kit_dump`
  call, inside the unclaimed-widgets endpoint, feeds
  `backend/services/widget_picker.py`'s `unclaimed_button_widgets` instead).
  *Breaks:* a stale or
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
(`request_coordinator.py`'s `request_confirm_field`) -> client verifies it
has a usable value and acks (`webFormConnection.ts`'s
`handleConfirmFieldRequest`; reply built by `sendConfirmFieldResponse`
-- `reason` is a fixed category token, never a field value) -> backend
logs ONLY on a positive ack (the "Recorded" guard inside
`callback_handler.py`'s `_handle_confirm_field_tool`, which protects the
`log_field_confirmation` call immediately below it). Event shape (NO PII, no `value` key anywhere), built in
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
handshake -- sent by the JIT builder (`getJITHandshakePayload` in
`schemaFormState.ts`, which sets `form_number`, `kit_id` and `edition_date`),
read as `kit_id`/`jit_form_number`/
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
- **The API-path rewrite**: `form_kit_routes.py`'s `list_form_kits`
  rewrites a kit's `schema_path`/`pdf_path` to the authenticated backend
  routes (`/api/form-kits/<id>/schema|pdf`) whenever the STORE, not the static
  bundle, is the source of truth. That is **any kit in GCS mode**, plus a
  private kit in either mode. The discriminator is presence in the static
  bundle, NOT privacy: the bundle contains only kits that were in the git tree
  at frontend BUILD time, and kits are bucket-canonical (CLAUDE.md scar #10),
  so a `complete`, PUBLIC kit published from the hosted editor is absent from
  it too -- its baked static path then falls through the SPA catch-all and
  returns `index.html` with HTTP 200, which is the `Unexpected token '<'`
  failure of bd `polyglot-pdf-6p77c`. LOCAL mode keeps static paths (there the
  store root IS the git tree). The private half of the rule remains true and
  is why the rewrite existed at all (bd kkos:
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
- **The manager check is no longer written here.** It calls
  `backend/services/firms.py`'s `manager_firm_id(claims)`, the ONE home for
  the rule (bd `polyglot-pdf-dmjl5`, Surface contract 19) -- an
  employee-level session must not retire forms, and the admin service's
  staff-account routes need the identical rule. This route uses the
  PREDICATE rather than the `require_firm_manager` dependency, because the
  dependency raises 403 and every refusal here must stay a 404 (next
  bullet). The rule is shared; the refusal shape is each caller's own.
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
- **One-time use lives in Firestore** (`link_redemptions` on the demo,
  `link_redemptions_<channel>` elsewhere -- see `LINK_CHANNEL`), not the token: a
  signed bearer string is replayable by construction. FAILS CLOSED BY
  REFUSING (opposite polarity to the firms allowlist read, which fails closed
  by returning `[]`) -- note the two "fail closed" directions when changing
  either. `link_redemptions._collection_name(channel)` takes `channel` as an
  EXPLICIT argument (Epic 2 bead A1), not read from the environment: the
  public backend's own callers (`_collection()`, defaulted from `open_link`/
  `complete_link`/`enforce_link_redemption`) pass no argument and so still
  resolve through `link_channel()`, but a caller that DOES name a channel (a
  future admin-service sweep/reconciler) is never silently redirected to
  whichever channel the calling PROCESS happens to be on. See contract 16 for
  the sibling mint-record store that mirrors this exact convention.
- **The doors that REDEEM do it through ONE helper.**
  `link_redemptions.enforce_link_redemption` runs the MINT-RECORD check (bd
  `polyglot-pdf-jecrl`, contract 24 -- first, before anything is written), the
  redemption check, AND the COMPLETION-window check, none of which
  `verify_link_token` can do -- the token carries only the OPEN deadline, and
  both one-time use and the reservation live in Firestore.

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

- **SPEND is bounded per LINK, and metering is NOT a gate** (bd
  polyglot-pdf-ik7e). Two different numbers, doing two different jobs. Both
  numbers are RUNTIME settings now (bd polyglot-pdf-bg313): `link_budget.py`'s
  `firm_link_cap()` and `default_cost_ceiling_usd()` resolve through
  `backend/services/runtime_config.py` (`app_config/{channel}` in Firestore,
  TTL-cached), not `os.getenv` -- an operator retunes either per channel with
  `scripts/set_runtime_config.py` and no redeploy.
  - **Per-link cost ceiling ($10, `LINK_COST_CEILING_USD`) ENFORCES.**
    `link_spend.check_budget` runs at the socket's paid gate -- after the link
    verifies, before any Gemini session exists -- and a link at or over its
    ceiling is closed with **1013 `budget_exhausted`**, deliberately NOT the
    1008 "Authentication failed" the other refusals use: a client who spent
    their allowance has a perfectly good link, and an auth error sends them to
    the firm with the wrong problem. Retrieval never redeems, so their
    download, print and preview keep working.
  - **Per-firm monthly allowance (30, `LINK_FIRM_CAP`) only METERS.** It is a
    subscription tier ($500/mo for 30 links, then $15 each -- provisional
    pending market research), not an abuse limit. A firm minting link 31 has
    PAID for link 31, so `link_metering.record_mint` counts, flags
    `over_allowance` for billing, and **never refuses**. Adding a refusal there
    breaks a paying customer; a test derived from the route source guards it.

  Spend accumulates on the **signed `jti`**, not on `form_session_id`: the
  latter is generated in the browser and lives in sessionStorage, so a ceiling
  keyed on it is defeated by a page refresh.

  **Two cost counters exist on the adapter, and the difference bites.**
  `_session_total_cost` is zeroed on every Gemini session start -- and a
  SECTION SWITCH starts a new Gemini session on the same adapter without
  dropping the WebSocket, so it holds only the CURRENT section. It feeds the
  per-session cost log, which is what it is for. The ceiling reads
  `_connection_total_cost`, which is never reset, via `session_cost_usd()`.
  Banking the wrong one discards 88-96% of a client's spend on the shipped
  kits (8, 13 and 27 sections) while looking enforced -- caught in review, and
  pinned by `test_the_cost_counter_SURVIVES_a_section_switch`.

  The client IS told why voice stopped (bd polyglot-pdf-cke6v, shipped).
  `webFormConnection.handleClose` branches on the close REASON, not the code:
  `budget_exhausted` returns early with a terminal status of the same name --
  no retries -- and both overlays show a modal carrying the translated
  voice-ending copy. `budget_unavailable` is deliberately NOT matched, because
  an unreachable spend store IS transient and must keep the ordinary retry
  path. Same code (1013), opposite handling; the two tokens are matched by
  STRING COMPARE with no shared constant, so renaming either side silently
  restores the old behavior -- each side carries its own pinning test.

  That modal offers NO recovery action (a Reconnect could never work) but IS
  dismissible: it is a full-viewport overlay, and its own copy promises the
  client can still type, download and print -- so blocking the page would
  contradict it. On desktop it yields to the save nudge, which carries the same
  words plus a working Save button.

  Scope today (bd polyglot-pdf-ah5d3 / Epic 2 A4, closing polyglot-pdf-4tjt7):
  the socket's spend ceiling is the TOKEN's own `cap_usd` claim when present,
  else the GLOBAL default -- `link_budget.cost_ceiling_usd_for_claims(claims)`
  resolves it, and the socket passes that resolved number into `check_budget`
  as `{KIT_COST_CEILING_KEY: ceiling_usd}`. No per-connect kit metadata read
  happens here or upstream of it: after the open-requires-a-mint-record
  cutover (Epic 2 bead A3) every token that CAN open already carries `cap_usd`
  for a kit that has one, resolved once at mint from the kit's price
  commercial. Before A3 ships (or for a kit with no resolvable ceiling), the
  claim is simply absent and the socket falls through to the global -- w7 and
  i-90 both declare a per-form ceiling (at $3, bd polyglot-pdf-gob8l), but
  until A3 lands their links carry no `cap_usd` claim and stay bounded by the
  GLOBAL default rather than the declared $3. Fails safe: a higher ceiling,
  never an absent one. And the check is at CONNECT, so a single session that
  blows the ceiling mid-call is caught on the NEXT connect -- overrun is
  bounded by one session.

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
browser session. EVERY backend-calling site resolves through that one
module; an inline `user.getIdToken()` anywhere else fails CI. Deliberately not
a COUNT: the guard asserts the allowlist is empty, not a number, so a count
here goes stale silently every time a site is added (it said NINE until the
mint page at `/console/links` made it ten, bd polyglot-pdf-gob8l).

Frontend: `/f` renders `ClientLinkEntry` OUTSIDE `ProtectedRoute`
(`frontend/src/schema-forms/AppRoutes.tsx` -- extracted from `main.tsx` so a
test could import it, which is itself the fix for a defect: while the table
lived beside `createRoot`, wrapping the client route in `ProtectedRoute` or
renaming its path both passed the entire frontend suite). Moving it inside
bounces every client to a sign-in they can never pass. The path is the
exported `CLIENT_LINK_PATH`; `AppRoutes.test.tsx` (renamed from
`clientRoute.test.tsx` by bd polyglot-pdf-krbol once the file grew to cover
every console route, not just the client one) pins it against the same `/f`
literal `link_routes.py` builds links from -- each side independently
pinned, so a unilateral change on either reddens. The gate pins the form id via
`saveOnboardingState` and leaves LANGUAGE unset -- the form is the firm's
choice, the language is the client's.

**Minting is off by default** -- a live link is an unauthenticated door to a
paid session, so it stays off wherever `LINK_MINTING_ENABLED` resolves false.
The spend ceiling it waited on (bd polyglot-pdf-ik7e) has shipped.
`LINK_MINTING_ENABLED` is a RUNTIME setting now (bd polyglot-pdf-bg313):
`backend/services/runtime_config.py` resolves it from `app_config/{channel}`
in Firestore first, but the `deploy-demo.sh` / `deploy-staging.sh`
`LINK_MINTING_ENABLED=true` env line is still LIVE as the fallback -- when a
channel's Firestore doc has never had a value written (or a read fails with
no last-known-good yet), `runtime_config.py` reads that same env var itself
and parses it the same way the pre-bg313 call site did, before falling back
further to the compiled default (`false`). An operator overrides it per
channel by seeding `app_config/{channel}` with `scripts/set_runtime_config.py`,
or the admin console's own config route once it lands (bd polyglot-pdf-li9x0).
The GLOBAL ceiling is runtime-config-backed (same env-var fallback); the
ceiling actually in force at connect is TOKEN `cap_usd` > that global, via
`link_budget.cost_ceiling_usd_for_claims` (bd polyglot-pdf-ah5d3 / Epic 2 A4,
closing polyglot-pdf-4tjt7) -- carried on the signed link token's claims, not
the handshake. A kit's own `link_cost_ceiling_usd` reaches a token's `cap_usd`
only once Epic 2 bead A3's mint-time resolve lands; until then every link
stays bounded by the global.

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

- `backend/adapters/live_ai_gemini.py`'s `voice_name = (getattr(settings,
  "LIVE_VOICE_NAME", "") or "").strip()` read -- feeds the Gemini Live session's
  `speech_config.voice_config.prebuilt_voice_config.voice_name`. An
  unaccepted name is a hard `1007 Invalid voice name` at connect that
  breaks EVERY session.
- `backend/services/spellback_tts.py`'s
  `resolve_spellback_voice` -- the PERSONA half of the spell-back clip's
  Cloud TTS voice (`{locale}-Chirp3-HD-{persona}`), which in turn selects
  the clip's loudness gain via `spellback_gain_db` /
  `_MEASURED_GAIN_DB` (`spellback_tts.py:91-98`).

Full detail: [`components/voice-ai.md`](components/voice-ai.md), which has
its own "`LIVE_VOICE_NAME` has a SECOND consumer" section.

### 12. `APP_MODULE`: one image, two Cloud Run services (bd polyglot-pdf-pnoik)

The root `Dockerfile` copies BOTH top-level Python packages and chooses which
ASGI app to serve at RUNTIME. There is no build arg -- `deploy-all.sh` builds
with `gcloud builds submit --tag`, which cannot pass one.

- **Producer:** `deploy-all.sh`'s backend stage (bd polyglot-pdf-3l2vp, sprint-
  22 plan bead 1.3) computes `APP_MODULE="${APP_MODULE:-backend.main:app}"`
  and passes it (plus `GIT_SHA=$(git rev-parse HEAD)`) as RUNTIME env in
  `--set-env-vars` on EVERY backend deploy. A caller that sets nothing (every
  existing channel: `deploy-staging.sh`, `deploy-demo.sh`, `backend/deploy-
  new.sh`) still resolves to `backend.main:app`, so this is a config addition
  with no behavior change for the public channels. `deploy-admin.sh` is the
  one caller that overrides it, exporting `APP_MODULE=admin_backend.main:app`
  ahead of the same `deploy-all.sh --backend` invocation.
- **Staging tier (bd polyglot-pdf-3l2vp):** `deploy-admin.sh` also sets
  `BACKEND_NO_TRAFFIC_TAG=candidate`, which makes `deploy-all.sh` deploy
  `--no-traffic --tag candidate`, curl the TAGGED revision's own stable URL's
  `/health` (built by inserting `<tag>---` ahead of the service's base host,
  since `gcloud run services describe` reports no revision-scoped address),
  and only on a 200 run `gcloud run services update-traffic --to-latest`. A
  failing health check aborts the script WITHOUT shifting traffic, leaving the
  previously-live revision serving. There is ONE admin service backing BOTH
  channels' data, so this is that service's own staging tier -- it has no
  second Cloud Run service to rehearse against first.
- **Consumer:** the root `Dockerfile`'s
  `CMD uvicorn ${APP_MODULE:-backend.main:app} --host 0.0.0.0 --port ${PORT}`,
  plus `admin_backend/main.py`'s `DEFAULT_APP_MODULE` constant, which must
  carry the SAME default string so the admin `/health`'s `app_module` field
  does not lie about which app is live.
- *Breaks if disagreed:* a service pointed at the wrong module starts cleanly
  and serves the WRONG app -- the public voice API on the wide admin service
  account, or an admin URL with none of the admin routes -- and every probe
  short of reading `/health`'s `app_module` reports it healthy. An `ENV
  APP_MODULE=` default, or `-` in place of `:-`, additionally hides a deploy
  that passes an empty value, which crash-loops the container instead.
- **Pinned by** `tests/test_dockerfile_app_module.py` (CMD shape, default,
  no `ARG`, no `ENV` default, both `COPY` lines, and the constant/Dockerfile
  agreement), `admin_backend/tests/unit/test_admin_health.py`, and
  `tests/test_deploy_admin_tag_flow.py` (the untagged-vs-tagged `deploy-
  all.sh` invocation: `APP_MODULE`/`GIT_SHA` always set; `--tag`/`--no-
  traffic` only with `BACKEND_NO_TRAFFIC_TAG`; a failing tag-URL `/health`
  aborts before `update-traffic` runs).

### 13. `admin_backend/` -> `backend/` shared-code direction (bd polyglot-pdf-pnoik)

The privileged admin service and the public backend are separate Cloud Run
services with separate service accounts, built from one image. The dependency
between their packages is one-directional and partial.

- **Allowed:** `admin_backend/` imports `backend.services.*` and
  `backend.config` (firms, link tokens, kit gates, the Firestore client,
  `parse_extra_origins`).
- **Forbidden:** `admin_backend/` importing `backend.routes.*`. Importing a
  route module executes the public app's router construction inside the
  PRIVILEGED process, binding handlers written and reviewed against the narrow
  `polyglot-backend-sa` onto the wide `admin-backend-sa`.
- **Forbidden in the other direction too:** `backend/` never imports
  `admin_backend`. This is the direction that DEFEATS the scar-#7 guard, so it
  is pinned rather than assumed: `backend/tests/unit/test_deployed_iam_envelope.py`
  walks `backend/` only (its root is `parents[2]` of that test file), so a
  privileged helper reached from `backend/` via `admin_backend` would sit in a
  file that guard never opens -- and would run under the NARROW
  `polyglot-backend-sa`.
- **Pinned by**, in each direction:
  - `admin_backend/` -/-> `backend.routes`:
    `admin_backend/tests/unit/test_admin_sa_iam_envelope.py`
    (`test_admin_backend_never_imports_backend_routes`).
  - `backend/` -/-> `admin_backend`:
    `backend/tests/unit/test_deployed_iam_envelope.py`
    (`test_the_public_backend_never_imports_the_admin_package`).

  Each has a matching-rule test over synthetic sources (both import shapes,
  plus a same-prefix package that must NOT be flagged) and a vacuity guard
  asserting its source walk actually reaches the app module.

### 14. Runtime config: `app_config/{channel}` (bd polyglot-pdf-bg313)

Five backend settings moved off deploy-time env to a per-channel Firestore
doc, so an operator retunes them with no redeploy.

- **Producers -- TWO, and only one of them audits.** The admin service's
  config route `PUT /admin/config/{channel}`
  (`admin_backend/routes/config_routes.py`, bd polyglot-pdf-li9x0) is the
  operational path: it validates the key against `RUNTIME_CONFIG_KEYS` and
  the value through `runtime_config.coerce_value` BEFORE writing, and writes
  the value and its audit row in ONE Firestore transaction (contract 15).
  The operator CLI `scripts/set_runtime_config.py <channel> set <KEY>
  <value> --project <p>` is the un-audited break-glass path, kept because it
  needs no console and no deployed admin service. Both write
  `app_config/{channel}` with Admin-SDK `set(..., merge=True)`, so a write
  never drops the channel's other keys.
- **Consumer:** `backend/services/runtime_config.py` -- the ONLY reader.
  `RUNTIME_CONFIG_KEYS` = `LINK_MINTING_ENABLED` (bool),
  `LINK_COST_CEILING_USD` (float), `LINK_FIRM_CAP` (int), `CREDITS_ENFORCED`
  (bool -- Epic 2 bead A3 gates a zero-balance mint on it),
  `CREDIT_LOW_THRESHOLD` (int, new -- Epic 3 bead E3.5 gates the low-balance
  alert on it; see contract 21). A key present in the doc but outside this
  set is logged and ignored, never applied. TTL-cached per channel
  (`TTL_SECONDS`, 30-60s) -- explicitly NOT `get_settings()`
  (`backend/config.py`), which is `lru_cached` for the whole
  process lifetime and would never pick up a change.
- **Fallback order** on a Firestore miss (unreachable store, missing doc, or
  a key absent/malformed in it): the LAST-KNOWN-GOOD value from this
  process's previous successful read of that key, then -- only when nothing
  was EVER read successfully -- the env default. For the three legacy keys
  (`LINK_MINTING_ENABLED`, `LINK_COST_CEILING_USD`, `LINK_FIRM_CAP`) that env
  default is a LIVE `os.getenv` read INSIDE `runtime_config.py` itself
  (`_legacy_env_default`), parsed exactly as the pre-bg313 call sites parsed
  it, falling further back to the compiled constant only when the variable is
  unset or unparsable -- this is what keeps `deploy-demo.sh` /
  `deploy-staging.sh`'s `LINK_MINTING_ENABLED=true` a real fallback rather
  than dead text. `CREDITS_ENFORCED` has no env var at all and always falls
  straight to its compiled `false`. Env-first (ahead of last-known-good)
  would be wrong regardless: a console that just LOWERED the ceiling must not
  see a higher value -- from Firestore's old value OR the env var -- reappear
  during a blip; both are pinned by `test_runtime_config.py`.
- **Call sites swapped:** `backend/routes/link_routes.py`'s
  `_minting_enabled()` and `backend/services/link_budget.py`'s
  `firm_link_cap()` / `default_cost_ceiling_usd()` now call into
  `runtime_config` instead of reading `os.getenv` directly. Pinned by a
  grep-derived test (`test_runtime_config.py`) over the shipped sources, so a
  reintroduced `os.getenv("LINK_MINTING_ENABLED", ...)` anywhere outside
  `runtime_config.py` fails CI.
- **NOT MOVED, deliberately:** `LINK_TOKEN_SECRET` (Secret Manager -- a
  secret has no business in a plain Firestore doc), `LINK_BASE_URL`,
  `LINK_CHANNEL` (topology; moving either would reopen the channel-isolation
  bead polyglot-pdf-3q9qn).
- **Deploy-script env lines are the fallback, not dead text.**
  `deploy-demo.sh` and `deploy-staging.sh` still set
  `LINK_MINTING_ENABLED=true` in `BACKEND_EXTRA_ENV` (pre-dates this bead);
  `runtime_config.py` reads that SAME env var as its own fallback (see
  above), so a freshly deployed channel with no `app_config/{channel}` doc
  yet still mints exactly as before this bead. Seeding
  `app_config/{channel}` via `scripts/set_runtime_config.py` or the console
  route lets an operator override the deploy-time value per channel with no
  redeploy; it is not required just to keep the deploy scripts' setting
  working. `CREDITS_ENFORCED` and `CREDIT_LOW_THRESHOLD` are the two keys
  with no env fallback (both are brand new); each stays at its compiled
  default (`false`, `10`) until a channel's doc sets it -- see
  `test_runtime_config.py`'s `_NO_ENV_FALLBACK_KEYS`.
- **`firestore.rules` carries a full client deny for `app_config/{channel}`**
  (bd polyglot-pdf-li9x0), alongside `admin_audit_log` and `firms`. The set
  of Admin-SDK-only collections lives in ONE constant,
  `ADMIN_SDK_ONLY_COLLECTIONS` in
  `backend/tests/unit/test_firestore_rules_text.py`; a later bead extends
  that list rather than adding another copy of the assertion, and the test
  fails in BOTH directions (a listed collection with no block, and a block
  for a collection nobody listed). A client-writable copy of this doc would
  let a browser raise its own per-link USD spend ceiling.

### 15. Admin audit log: `admin_audit_log/{auto}` (bd polyglot-pdf-li9x0)

One row per privileged mutation on the admin service: WHO did it, WHAT they
did, to WHAT, and the before/after metadata. Unlike the confirmation sink
(contract 6), which is deliberately fire-and-forget, this log's job is
preventing a DOUBLE APPLY -- an operator who sees a 500 retries -- so both
write forms BIND the row to the mutation rather than firing it alongside.

- **Producer:** `admin_backend/services/audit_log.py`, the only writer. Two
  forms, and they are NOT interchangeable:
  - **`record_in_transaction(tx, db, ...)`** for FIRESTORE mutations. The row
    is written with `tx.set` inside the CALLER'S transaction, so either both
    commit or neither does; the helper takes the transaction rather than
    opening one, and deliberately has no `try/except` (swallowing an audit
    failure would let the mutation commit unaudited). First consumer:
    `PUT /admin/config/{channel}`.
  - **`MUTATION_KIND_DELEGATED_FIRESTORE`** (bd `polyglot-pdf-8vgfh`): the
    same in-transaction guarantee as `record_in_transaction` above, for a
    route whose Firestore transaction is opened by ANOTHER module's helper
    rather than the route module's own `@firestore.transactional` body.
    `POST /admin/links/sweep-expired` is the first (and so far only)
    example: it joins bead A5's `credit_ledger.refund_expired_link`
    transaction via that function's `extra_writes` parameter (extended by
    this bead to accept one), passing a closure that calls
    `record_in_transaction`. Because the transaction itself lives outside
    `admin_backend/`, the audit-coverage test's usual AST check (does a
    `@firestore.transactional` function IN THIS MODULE contain the call)
    cannot apply; the static proxy is instead "does this module define a
    closure calling `record_in_transaction` AND pass that closure BY NAME
    as `extra_writes=` at some call site in this same module" -- `extra_
    writes` is the one documented seam (`append_entry` and `refund_expired_
    link` both carry it, identical contract) for joining a second write to
    a transaction opened elsewhere. The GENUINE atomicity guarantee is
    proven by a real test exercising the real call path with a forced
    audit-write failure (`admin_backend/tests/unit/test_sweep_routes.py::
    test_a_forced_audit_failure_leaves_the_refund_uncommitted`), mirroring
    `test_config_routes.py`'s own forced-failure pin for the plain
    Firestore form.
  - **`record_pending(db, ...)` then `mark_committed(ref, ...)` /
    `mark_failed(ref, error=...)`** for mutations Firestore cannot wrap
    (`firebase_admin.auth` user create/disable, claim stamps, Cloud Build
    triggers). Its FIRST consumers are the three mutating `/admin/users`
    routes (bd `polyglot-pdf-dmjl5`, contract 19); Epic 4's build triggers
    follow. Note the deliberate ASYMMETRY: `record_pending` RAISES
    (if the intent cannot be recorded, the action must not happen), while
    both closeouts are best-effort (the action already happened; raising
    would surface an error for a success, and a caller that retried on it
    would double-apply). A row stuck at `pending` reads as "this may have
    taken effect", which is true.
- **Row shape** -- built in ONE place (`build_row`) so the two forms cannot
  drift: `actor_uid`, `actor_email`, `action`, `target`, `before`, `after`,
  `channel` (nullable -- the admin service has no channel of its own),
  `request_id`, `state` (`committed` | `pending` | `failed`), `ts` (a plain
  epoch float, NOT `SERVER_TIMESTAMP`: the pending form needs the value to
  exist before the action runs). `ROW_FIELDS` pins the set. The closeouts add
  `committed_ts`, and `mark_failed` adds a truncated `error`.
- **Consumer:** `GET /admin/audit`
  (`admin_backend/routes/audit_routes.py`), newest first, cursor-paginated.
  The admin console's audit-log page (bead 1.7) is its first UI consumer.
- **Composite indexes are a REQUIRED part of this contract, not an
  optimization.** Each of the route's four filters produces an equality
  filter plus an `order_by` on a *different* field (`ts`), which Firestore
  serves ONLY from a composite index; unindexed, the query fails at runtime
  with `FAILED_PRECONDITION`. The unfiltered default view needs no composite
  (single-field auto-index on `ts`), so an operator's FIRST use of a filter
  is where the gap would surface. The four indexes ship in
  `firestore.indexes.json`, wired via `firebase.json` and deployed by
  `deploy-demo.sh` (`firebase deploy --only firestore:indexes`) -- indexes
  are PROJECT-wide exactly like rules, so the demo deploy lands them for
  staging too, and index builds are asynchronous (a freshly added index is
  not READY the moment the command returns).
  `admin_backend/tests/unit/test_firestore_indexes.py` derives the filter
  set from the route's own AST and pins it against the shipped artifact in
  both directions, so a fifth filter added without its index fails CI rather
  than in production. This is CLAUDE.md scar #7 applied to indexes rather
  than IAM: the route's tests substitute an in-memory query that filters and
  sorts in Python, and a fake cannot tell you the real datastore will refuse
  the query.
- **The coverage pin:**
  `admin_backend/tests/unit/test_admin_audit_coverage.py` derives every
  MUTATING route off the live `app.routes` and asserts the form each one's
  mutation REQUIRES -- not merely that some audit call is present, which
  would pass a Firestore mutation auditing outside its transaction. Every
  mutating route must declare its form in `MUTATION_KINDS`; a new one that
  does not fails there, and the declaration is checked in both directions
  against the live route set.
- **What never goes in a row:** field values, PII, or PHI
  (`standards/hipaa-pii-policy.md`). `before`/`after` carry config and
  commercial metadata only. The admin service has no access to field values
  in the first place -- it serves operators, not form sessions.
- **`firestore.rules` denies `admin_audit_log/{rowId}` to all clients.**
  Append-only is a property of the WRITERS (nothing here deletes or rewrites
  a row's identity fields; the one legal transition is `pending` ->
  `committed` | `failed`); the deny block is what stops a client-SDK caller
  regardless. The Admin SDK bypasses rules, so the discipline lives in the
  helper.
- **IAM:** the writes need `roles/datastore.user`, which `admin-backend-sa`
  already holds and which `test_admin_sa_iam_envelope.py` pins by name AND
  justification. This contract added no new permission (CLAUDE.md scar #7).

### 16. Credits data model: firm kind/balance + the mint record (Epic 2 bead A1)

Schema and plumbing only -- no route reads or writes any of this yet
(the mint transaction and the routes that use it are Epic 2 beads A2/A3/A5).
Laid now so those beads compose an already-agreed shape rather than each
inventing its own.

- **`firms/{firm_id}` gains `kind: "mock" | "live"` (required on create) and
  `balance_credits`/`balance_updated_at`.** Producer:
  `backend/services/firms.py:upsert_firm` (0-initializes the balance fields
  on first create ONLY; never touches them on a re-run -- a re-bootstrap of
  an existing firm must not zero a real balance). Consumer, THIS bead:
  `firms.firm_kind(firm_id)`, which is the FAIL-CLOSED-TO-`"live"` reader --
  the opposite polarity from `get_allowed_kits`'s fail-closed-to-`[]`, and
  the two are pinned in the same test file so the contrast stays visible.
  Consumer, LATER bead (A3): the mint route's live-firm-demo-channel-only
  gate reads `firm_kind()` directly. The balance is NOT
  channel-partitioned -- one firm, one `balance_credits`, whichever
  channel's mint debits it -- which is safe only because a `live` firm can
  mint solely on the explicit demo channel (A3) and a `mock` firm carries no
  real money. **`scripts/bootstrap_firm.py` gains a REQUIRED `--kind`** (no
  default, either direction): the CLI's positional call into `upsert_firm`
  shifted (`kind` is now the 5th positional argument, `status` moved to a
  keyword) -- any other future caller of `upsert_firm` must update its call
  site.
- **NEW `links[_<channel>]/{jti}` mint record**
  (`backend/services/links_store.py`), a collection SEPARATE from
  `link_redemptions` on purpose: `link_redemptions` answers "has this link
  been opened/completed" (written on the client's first open);
  `links_store` answers "was this link ever legitimately minted, for how
  much, and is it still good to open" (written at MINT time, by staff,
  before the client ever sees it). Folding the two together would mean a
  doc exists before the client's first open -- exactly the state
  `link_redemptions`'s callers currently treat as proof of a real open.
  - **Doc shape:** `firm_id`, `kit_id`, `employee_id`, `credit_cost` and
    `cap_usd` snapshots (the latter closes bd `polyglot-pdf-4tjt7`),
    `minted_at`, `open_deadline` (mirrors the token's `exp`, stored
    separately so a later sweep can query Firestore without decoding a
    token), `status` (one of `links_store.ALL_STATUSES`: `minted` |
    `opened` | `completed` | `refunded` | `revoked` | `budget_exhausted`),
    `revoked_by`/`revoked_at`, `expire_at` (a TTL field -- see below).
    **`status` is a DERIVED CACHE for listing, never the money decision**:
    any transaction that moves real credits (the mint debit, and A5's
    expiry refund) reads the AUTHORITATIVE record fields directly and never
    trusts `status` alone. The mint route writes the record inside the
    ledger transaction (contract 24); `mark_opened()` is a best-effort
    mirror that never raises and only ever moves `minted` -> `opened`; the
    refund and revoke writers land in A5. `links_store.build_mint_record()`
    is the ONE definition of the doc shape -- both the transactional
    `tx.set()` and the plain `record_mint()` write what it returns, so a
    transactional copy cannot drift from the plain one.
  - **`channel` is an EXPLICIT argument, mirroring `link_redemptions`'s
    convention (contract 9) exactly** -- `links_store._collection_name(channel)`
    and `_collection(channel=None)` (defaulting to `link_channel()`) have
    the identical shape as their `link_redemptions` counterparts, on
    purpose: an operator who understands one collection's channel isolation
    already understands the other's. The demo channel keeps the bare
    `links` name; every other channel gets `links_<channel>`.
  - **TTL:** `links_store.expire_at_for(open_deadline)` returns
    `open_deadline` plus a 30-day retention margin, as a timezone-aware UTC
    datetime. `scripts/setup-firestore-ttl.sh` (NEW, this bead) declares a
    Firestore TTL policy on the `expire_at` field for `links`,
    `links_staging`, and (ahead of Epic 3) `alerts` -- explicitly NOT for
    `admin_audit_log` or `deployments` (retained) or `link_redemptions`/
    `link_redemptions_staging` (a separate, deliberate retention decision
    this bead does not touch). The script is idempotent (re-running it
    against an already-declared policy is a no-op success) and is NOT run
    by any deploy script -- an operator runs it by hand, once per project,
    same as `scripts/setup-gcp-project.sh` and `scripts/setup-admin-service.sh`.
- **`firestore.rules` gains deny blocks for every new collection, plus one
  fold-in.** New: `kits/{kitId}` (kit commercial docs, `credit_cost` /
  `burn_cap_usd` -- READ at mint by `backend/services/kit_commercials.py`
  since bead A3, contract 24; WRITTEN by a Track B admin-service route in a
  later bead), `links/{jti}` + `links_staging/{jti}`, and the nested
  `firms/{firmId}/ledger/{entryId}` (Epic 2 bead A2's per-firm credit
  ledger rows -- a parent's deny does NOT cascade to a subcollection in
  Firestore's rules language, so this needed its own block even though
  `firms/{firmId}` was already denied). Fold-in:
  `link_redemptions/{jti}` + `link_redemptions_staging/{jti}` had NO deny
  block until this bead, despite being Admin-SDK-only by access pattern
  since it shipped (bd polyglot-pdf-ugm6) -- an oversight this bead closes
  opportunistically since the rules-set test was already being extended.
  All six are added to `ADMIN_SDK_ONLY_COLLECTIONS` in
  `backend/tests/unit/test_firestore_rules_text.py` (see contract 15 for
  the set-derived-test shape); the nested ledger entry required widening
  that test's both-directions regex to allow one extra
  `/{wildcard}/segment` hop, since the file-wide scan otherwise only
  recognizes single-level `collection/{wildcard}` blocks.

### 17. Admin console -> admin service: sign-in gate + page reads/writes (bd polyglot-pdf-b6943)

The admin console (`admin-console/`, a separate Vite app, Hosting sites
`polyglot-admin-demo` + `polyglot-admin-candidate`) is the FIRST client of the
admin service's routes (contracts 15 above and `GET /admin/whoami`). It
mirrors `schema-editor/`'s producer/consumer shape closely enough that a
change to one side's contract usually needs a matching change on the other.

- **Producer:** `admin_backend/routes/whoami.py` (`GET /admin/whoami` ->
  `{uid, email}`), `admin_backend/routes/audit_routes.py` (`GET /admin/audit`
  -> `{rows, next_cursor}`), `admin_backend/routes/config_routes.py`
  (`GET /admin/config/{channel}` -> `{channel, values, known_keys,
  unknown_keys}`; `PUT /admin/config/{channel}` body `{key, value}` ->
  `{channel, key, before, after, request_id}`). All four gated by
  `require_app_admin` (`admin_backend/services/admin_auth.py`): 401 on a
  missing/invalid token, 403 with the `NO_ADMIN_ACCESS:` prefix on a valid
  account with no `app_admin` claim.
- **Consumer:** `admin-console/src/utils/adminApi.ts` -- `probeWhoAmI`,
  `listAuditRows`, `getChannelConfig`, `setChannelConfigKey`. Every call
  carries `Authorization: Bearer <Firebase ID token>`, fetched PER REQUEST
  from `admin-console/src/utils/adminAuth.ts`'s `adminIdToken()` (never
  cached client-side -- an ID token expires in about an hour and the SDK
  refreshes it transparently, so caching one here would reintroduce a stale-
  credential 401 mid-session). A 401 raises `AuthError`; a 403 raises
  `ForbiddenError`, classified by the `NO_ADMIN_ACCESS:` prefix into
  `noAdminAccess` -- the SAME wire marker `schema-editor`'s
  `NO_EDITOR_ACCESS_PREFIX` classification uses, kept as a machine-readable
  prefix rather than a client string-match on prose for the same reason (a
  reworded message must not silently stop evicting).
- **`admin-console/src/components/SignInGate.tsx`** mirrors
  `schema-editor/src/components/SignInGate.tsx`'s two-gate shape (Firebase
  authentication, then a server-side authorization probe) almost verbatim,
  duplicated rather than imported for the same maintainer constraint that
  keeps `schema-editor/` from importing `frontend/` (2026-08-20: no new
  cross-surface dependencies to unravel later). `onReady` is called with the
  `WhoAmI` the server returns, not a role string -- `app_admin` is boolean
  (`admin_backend/services/admin_auth.py`'s `AdminActor` has no role field to
  report), unlike the editor's `editor`/`author` `EditorRole`.
- **`VITE_ADMIN_API_BASE_URL`** (`admin-console/src/utils/adminApi.ts`'s
  `apiBaseUrl()`) is the admin service's own Cloud Run URL, resolved at
  DEPLOY time by `deploy-admin-console.sh` the same way `deploy-editor.sh`
  resolves `VITE_API_BASE_URL` for the public backend -- see Surface
  contract-adjacent detail in `docs/components/config-deployment.md`'s
  "Admin console" section. Distinct from `VITE_API_BASE_URL`: the console
  never calls the public backend, so the two base URLs cannot be confused by
  sharing a name.
- **Auth project:** the SAME Firebase project as the voice app and the
  schema editor (`admin-console/.env.hosted`'s `VITE_FIREBASE_*`, identical
  values to `schema-editor/.env.hosted`'s) -- a second project is a
  separation epic's job, not this one's. Access is granted per person with
  `scripts/bootstrap_admin_user.py`, never self-served; the console offers no
  account-creation UI.
- **Build-time git SHA:** `admin-console/vite.config.ts` bakes
  `__ADMIN_CONSOLE_GIT_SHA__` into the bundle via a Vite `define` (`git
  rev-parse HEAD` at build time, `'unknown'` on failure). This is the
  CONSOLE's own build commit, rendered on the "who am I" page --
  intentionally separate from `GET /version`'s `git_sha`, which reports the
  ADMIN SERVICE's commit (a different deploy, reached over HTTP, not the
  build this bundle came from).
- **CORS:** `admin_backend/main.py`'s `CORSMiddleware` allowlist carries both
  console sites' localhost dev ports (3002) plus, at deploy time,
  `deploy-admin.sh`'s `ADMIN_CORS_ORIGINS` (both sites' `.web.app` and
  `.firebaseapp.com` domains, alongside the main app's origins for Epic 2's
  firm-manager pages).

### 18. Credit ledger: the ONE transactional balance writer (Epic 2 bead A2)

`backend/services/credit_ledger.py` is the only code in the repo that writes
`firms/{firm_id}.balance_credits` after the firm is created, and the only
producer of `firms/{firm_id}/ledger/{auto}`. Every credit movement --
subscription grants, prepaid purchases, promotional grants, mint debits,
expiry refunds, operator adjustments -- goes through the single
`append_entry()` transaction, so the invariant `balance_credits ==
sum(amount)` holds by construction rather than by six call sites each
remembering to update the balance. Nothing recomputes the balance from the
ledger on a read, so a second writer breaks the invariant silently.

- **The two deliberate other sites** are `firms.upsert_firm()` (contract 16)
  and `admin_backend/routes/firm_routes.py`'s create route, both of which
  0-initialize `balance_credits`/`balance_updated_at` on FIRST CREATE and
  never touch them again -- a firm with no ledger and a zero balance.
  `test_credit_ledger_is_the_only_module_that_writes_balance_credits` derives
  the allowed set from the source tree, walks both `backend/` and
  `admin_backend/`, and fails on any writer outside that set.
- **`append_entry(db, firm_id, *, entry_type, amount, actor, usd_amount=None,
  channel=None, reason=None, link_jti=None, kit_id=None,
  require_sufficient_balance=False, extra_writes=None, ts=None) -> dict`.**
  Returns the committed entry plus `doc_id`, `firm_id` and
  `balance_credits`. **SYNC on the Admin SDK** -- every async caller (the
  mint route, the socket, the refund sweep) must wrap it in
  `asyncio.to_thread`, as `backend/routes/link_routes.py` already does for
  its Firestore reads.
- **Entry shape** (`credit_ledger.ENTRY_FIELDS`, pinned as a frozenset):
  `type`, signed `amount`, nullable `usd_amount`, `firm_kind` snapshot,
  nullable `channel`, `balance_after`, `actor`, `reason`, `link_jti`,
  `kit_id`, `ts`. Consumers: Epic 3's BigQuery `income_month` view (which
  hard-codes `WHERE firm_kind = 'live'`) and the Track C console ledger
  table; a dropped field becomes a NULL column nobody notices until a
  revenue number is wrong, which is why the set is a test and not prose.
- **The type rules run BOTH ways.** `purchase` and `subscription_grant`
  (`USD_REQUIRED_TYPES`) REQUIRE `usd_amount`; the other four REFUSE it -- a
  dollar figure on a promo grant or a debit would be double-counted as
  income by a view that sums `usd_amount`. `POSITIVE_ONLY_TYPES` (the four
  credit-adding types) refuse a negative amount and `NEGATIVE_ONLY_TYPES`
  (`mint_debit`) refuses a positive one; `adjustment` is the signed escape
  hatch and is the one type that REQUIRES a non-blank `reason`. `actor` is
  required and never blank (a uid, or `system:<origin>`).
- **Reads before writes, and nothing hoisted out of the body.** Firestore
  requires every transactional read to precede every write, and RE-RUNS the
  whole body on contention. The balance, the `firm_kind` snapshot, the
  sufficiency verdict and `balance_after` are therefore all computed INSIDE
  the body from the same snapshot, every run -- a value read before the
  transaction would be stale on the retry, which is exactly the double-mint
  race. `firm_kind` falls back to `"live"` on a missing/malformed key, the
  same fail-closed polarity as `firms.firm_kind()` (contract 16); a
  missing/malformed `balance_credits` reads as 0, which is what lets a grant
  lift a pre-backfill firm (bead A6) out of the window.
- **`require_sufficient_balance` is the enforcement switch, not a default.**
  False (the default) WRITES the debit and lets the balance go negative --
  the metered soft-launch mode. True raises `InsufficientCredits` (a
  `LedgerError` subclass) with NOTHING committed. Consumer: Epic 2 bead A3's
  mint route passes it from the `CREDITS_ENFORCED` runtime-config flag
  (contract 14), and maps the refusal to `402`.
- **`extra_writes(tx, firm_snapshot)` joins a caller's documents to the SAME
  transaction.** Consumer: bead A3 passes the `links[_<channel>]/{jti}` mint
  record (contract 16) so the debit, the ledger entry and the record commit
  together or not at all. It runs inside the body AFTER the reads, must not
  read, must write the same thing from the same inputs on a retry, and its
  exceptions deliberately abort the whole transaction.
- **Every committed write emits ONE `ledger_export` structured log line**
  (`credit_ledger.LEDGER_EXPORT_FIELDS`: `event_type`, `type`, `amount`,
  `usd_amount`, `firm_id`, `firm_kind`, `channel`, `link_jti`). structlog's
  `JSONRenderer` puts each bound key at the top level of the JSON line, so
  Epic 3's Cloud Logging sink filter `jsonPayload.event_type =
  "ledger_export"` matches it directly -- this is the income and spend feed
  BigQuery reads, with no Firestore export extension and no nightly job. It
  is emitted AFTER the commit (a line for an entry that never committed
  would inflate the income view) and carries NO field values, PII or PHI:
  `reason` is operator free text and deliberately stays OUT of the log line
  while being stored on the entry.
- **Readers:** `read_balance(db, firm_id)` returns the materialized field
  (None for a missing firm -- distinct from 0, which a CLI dry run relies
  on) and does NOT sum the ledger; `read_entries(db, firm_id, limit=None)`
  returns entries oldest-first by `ts` (the replay shape, not the console's
  newest-n).
- **Expiry refund (Epic 2 bead A5): `refund_expired_link(db, jti, *, actor,
  channel=None, now=None) -> dict` and `reconcile_expired_for_firm(firm_id,
  channel=None, now=None) -> list[dict]`.** ONE transactional helper, keyed
  on the AUTHORITATIVE `link_redemptions[_<channel>]/{jti}` doc rather than
  the `links` record's best-effort `opened` mirror: `refund_expired_link`
  reads that doc first and refuses (`LinkNotRefundable(reason="redeemed")`)
  on its existence ALONE, then reads `links[_<channel>]/{jti}` and proceeds
  only from `status == "minted"` (`reason="not_minted"`/`"not_pending"`
  otherwise) -- a re-run against an already-refunded jti no-ops, which is
  what lets an hourly sweep (Track B bead B5, not yet built) and
  `reconcile_expired_for_firm`'s lazy per-firm pass race on the same jti and
  serialize on Firestore rather than double-crediting. Reuses the same
  write path `append_entry()` does (extracted into `_apply_entry_writes()`
  so both share one balance/entry-shape implementation) and joins the links
  record's `status=refunded` flip to the SAME transaction via
  `extra_writes`. `reconcile_expired_for_firm` queries `links[_<channel>]`
  for one firm's `status == "minted"` and `open_deadline < now`, calling
  `refund_expired_link` per hit and SKIPPING (never raising) a per-link
  `LinkNotRefundable` so one race lost to the sweep does not fail a whole
  balance read. **Consumer, and the load-bearing exclusion:** called ONLY
  by admin-service/firm-console balance reads, as their OWN transaction
  before the read -- NEVER by the mint transaction (bead A3). `append_entry()`'s
  own transaction reads exactly the firm doc (pinned by a test asserting its
  exact read set, plus an AST-walk guard that neither `append_entry` nor
  `_apply_entry_writes` ever calls `reconcile_expired_for_firm`), so when A3
  composes its own kit read around the same call, the combined mint
  transaction's read set stays `{firm, kit}` with no reconciliation query on
  the hottest transaction in the codebase. Opened-but-abandoned links are
  NOT refunded (maintainer pricing call, per the plan). The socket's
  `LinkBudgetExhausted` teardown (`websocket_routes._mirror_budget_exhausted`)
  writes a TELEMETRY-ONLY `links[_<channel>]/{jti}.status =
  "budget_exhausted"` mirror alongside this -- no ledger entry, pending a
  maintainer call on refund/replacement pricing.
- **`scripts/grant_credits.py`** (NEW) is the operator CLI on the same
  helper, so credits can be granted and rolled back before the console
  exists. Two subcommands: `grant` (positive only; `--type` in
  `promo_grant` | `purchase` | `subscription_grant`, the latter two
  requiring `--usd`, which `promo_grant` refuses) and `adjust` (either sign,
  `--reason` required by argparse). Both take a REQUIRED `--project`, whose
  resolved firebase_admin project is asserted before any write (the trap
  `scripts/bootstrap_firm.py` documents), refuse the dead project
  `polyglot-forms-919f2`, refuse a zero delta, and support `--dry-run`
  (reads the balance, prints the entry, writes nothing). Grants carry
  `channel=None` -- an operator grant is not a channel action. `actor` is
  stamped `system:grant_credits_cli:<operator>`, deliberately
  distinguishable from a console grant's Firebase uid. The CLI keeps its
  type lists as LITERALS (a `backend.*` import at module scope would run
  before `initialize_app`) and pins them against the service's constants by
  test.
- **Rules + IAM:** `firestore.rules`'s `firms/{firmId}/ledger/{entryId}`
  deny block already exists (contract 16) and is pinned by the set-derived
  rules test. The writes need `roles/datastore.user`, which both
  `polyglot-backend-sa` and `admin-backend-sa` already hold; this contract
  adds no new permission (CLAUDE.md scar #7).

### 19. The firm-manager rule + the admin claims allowlist (bd polyglot-pdf-dmjl5)

Two coupled contracts that ship together because the second is why the first
had to move.

**A. `manager_firm_id(claims)` is the ONE home for the manager rule.**
`backend/services/firms.py` decides "is this caller a manager, and of which
firm": the `firm_id` only when `firm_role` is exactly `"manager"` AND
`firm_id` is a non-empty string. It is PURE and side-effect free, over an
ALREADY-VERIFIED claims dict -- it decides authorization, not
authentication, and doing the verification twice in two places is how the
two disagree.

- **Why `firms.py` and not `auth.py`.** Both surfaces need it, and
  `admin_backend/services/admin_auth.py` may NOT import
  `backend/services/auth.py`: that module is deliberately liftable, pinned
  by
  `test_admin_auth.py::test_admin_auth_does_not_import_the_other_two_auth_modules`
  (contract 13's shared-code direction allows `backend.services`, and this
  is the narrowest possible use of it). `firms.py` is neither surface's
  verifier -- it owns what a firm IS. `backend/services/auth.py` re-exports
  the name so the voice app's callers read it from their own auth module.
- **Consumers, and the deliberate difference in refusal shape:**
  `auth.require_firm_manager` (the FastAPI dependency, layered on
  `require_auth`) raises **403**;
  `form_kit_routes._require_firm_owns_private_kit` uses the predicate and
  keeps its **404** (contract 8 -- a 403 would confirm another firm's kit
  exists); `admin_auth.require_app_admin_or_owning_manager` uses the
  predicate and raises 403 with the `NO_ADMIN_ACCESS:` prefix.
- **Pinned as a SET, not an instance** (CLAUDE.md scar #8).
  `backend/tests/unit/test_require_firm_manager.py` walks every non-test
  module under `backend/`, `admin_backend/` and `scripts/` and fails on ANY
  comparison against the literal `"manager"` outside a justified allowlist
  (`firms.py`, the home; `bootstrap_firm.py` and `user_admin.py`, which
  restate it as a wire contract and are pinned against the home). So the
  next route that hand-writes `claims.get("firm_role") == "manager"` fails
  CI instead of drifting for a release. A separate test pins that the retire
  helper CALLS the shared rule, since dropping the check entirely would also
  pass a no-literal scan.

**B. The console writes exactly two claims, and cannot write the others.**
`admin_backend/services/user_admin.py`'s `merge_firm_claims(existing, *,
firm_id, firm_role)` is the ONE place the four user routes assemble a claims
object.

- **`WRITABLE_CLAIMS = {firm_id, firm_role}`; `FORBIDDEN_CLAIMS =
  {app_admin, schema_editor_role, vff_dev}`.** The allowlist is a PROPERTY,
  not a promise: the returned dict is the account's existing claims with
  only the writable keys overlaid, both built from `WRITABLE_CLAIMS`, so
  there is no path by which a request value reaches any other key. A
  compromised console cannot mint its own admins. `app_admin` is still
  stamped only by `scripts/bootstrap_admin_user.py` under an operator's own
  credentials.
- **MERGE, NEVER REPLACE.** `firebase_admin.auth.set_custom_user_claims`
  REPLACES the whole claims object -- the highest-risk line in
  `scripts/bootstrap_firm.py`, and the same trap here. Without the merge, a
  role change would silently strip a firm dev's `vff_dev` claim and lock
  them out of the voice app. Both directions (nothing lost, nothing extra
  written) are pinned per-claim in
  `admin_backend/tests/unit/test_user_routes.py`.
- **The two-actor firm rule is `admin_auth.resolve_target_firm(actor,
  body_firm_id)`,** also one home. An APP ADMIN must name a firm (422
  otherwise -- defaulting to any particular firm would be a guess with a
  write behind it); a FIRM MANAGER may not name one at all, and naming
  their OWN firm is refused too. "The same value" is not the test; "did you
  try to choose" is -- accepting a matching value would make the refusal
  depend on what the caller happened to send, so the next console version
  that sent it on every request would silently stop being refused, and a
  bug that sent the wrong firm would become a cross-firm write. The refusal
  is pinned over all four routes x both named-firm cases.
- **The composite gate checks app_admin FIRST.** An account holding both
  `app_admin` and a manager claim acts as an app admin, the strictly wider
  role; the reverse order would silently downgrade it to its own firm.
  Both branches call the same `fb_auth.verify_id_token`, made by
  `admin_auth.py` itself.
- **A uid is a bearer of nothing.** The two by-uid routes prove the target
  account is in the RESOLVED firm before touching it, else a manager could
  disable any account in the project by pasting its uid. That refusal is a
  404 byte-identical to the one for a nonexistent uid.
- **Audit form: pending-then-committed** (contract 15), and it must be --
  Firebase Auth mutations cannot join a Firestore transaction. The three
  actions are `user.create`, `user.disable`, `user.role`, declared in
  `test_admin_audit_coverage.py`'s `MUTATION_KINDS`, which are the FIRST
  consumers of the external form. Neither the generated password nor the
  reset link ever reaches an audit row, a log line, or the response beyond
  the link itself.
- **IAM:** `create_user`, `set_custom_user_claims`, `update_user`,
  `list_users` and `generate_password_reset_link` all need
  `roles/firebaseauth.admin`, which `admin-backend-sa` already holds and
  `test_admin_sa_iam_envelope.py` pins by name. This contract adds NO new
  permission (CLAUDE.md scar #7). The PUBLIC backend still makes zero
  privileged Auth calls -- these live only under `admin_backend/`.


### 20. Usage event v2: the emitter -> Cloud Logging -> BigQuery shape (Epic 3 bead E3.1)

ONE structured event shape for every paid model or TTS call, so the logging sink
sees one column shape instead of one per call path. This is a WIRE contract in
the same sense as the WS legs: nothing type-checks it end to end, and a producer
that drops a key breaks a consumer query silently.

- **Producer:** `StructuredLogger._emit_usage`
  (`backend/utils/structured_logger.py`), reached only through three wrappers on
  the same class -- `log_gemini_api_response` (`event_type`
  `gemini_api_response`, `usage_kind` `live_voice`), `log_text_ai_usage`
  (`text_ai_usage`), `log_tts_usage` (`tts_usage`). Nothing else may emit a
  usage event; the wrappers exist so the key set has exactly one writer.
- **Consumers:** the Cloud Logging -> BigQuery sink and the cost views built on
  it (Epic 3 bead `polyglot-pdf-rd3s8`), plus the session-end Firestore rollups
  (`polyglot-pdf-*` E3.4) which read the same cost figures.
- **The shape.** `usage_kind` is a closed `Literal` in
  `backend/utils/log_schemas.py`: `live_voice`, `text_secretary`,
  `text_validator`, `text_translation`, `tts_spellback`, `tts_notice`,
  `tts_intro`. The optional context keys are declared ONCE as
  `USAGE_CONTEXT_KEYS` (`firm_id`, `employee_id`, `link_jti`, `kit_id`,
  `channel`, `model`), and `_emit_usage` iterates THAT tuple -- a key added to
  the schema without a matching emitter parameter raises `KeyError` on the first
  emit rather than silently never being written.
- **Every key on every call, `None` included.** *Breaks if drifted:* at the
  BigQuery sink a MISSING key and a NULL are not the same thing. A wrapper that
  omits `firm_id` when it has no value produces rows that vanish from a
  `GROUP BY firm_id`, so a per-firm cost total under-reports with no error
  anywhere -- the invoice and the dashboard just disagree. Pinned per
  `usage_kind` by `backend/tests/test_usage_event_schema.py`.
- **Ordering guarantee:** caller `metadata` is written FIRST and the envelope
  keys on top, so a caller whose metadata happens to contain `model` or
  `usage_kind` cannot mislabel its own row.
- **`log_gemini_api_response` keeps its v1 name and positional signature.** The
  live adapter's existing call site
  (`backend/adapters/live_ai_gemini.py`, in the per-turn `usage_metadata` block)
  compiles unchanged; the six context ids arrive as optional keywords, now
  ACTUALLY POPULATED end to end (bd `polyglot-pdf-cjifh`, E3.2): the WS route's
  decoded token claims (`firm_id`, and `link_jti`/`employee_id` for a client-
  link session, or the staff uid for a staff session) plus `kit_id` and
  `link_tokens.link_channel()` thread through `_handle_fill_session` ->
  `FormFillingService.start_session` -> `LiveAIGemini.set_session_context` ->
  this call, so every live-voice usage event now carries firm/employee/link/
  kit/channel/model instead of six nulls. *Breaks if renamed:* that one call
  site, and any Cloud Logging query or dashboard keyed on the
  `gemini_api_response` event name.
- **Call-site coverage is enumerated, not remembered.**
  `backend/tests/test_usage_event_coverage.py` AST-walks everything under
  `backend/` that Cloud Run executes (exclusion-derived, like
  `backend/tests/unit/test_deployed_iam_envelope.py`) for `generate_content`,
  `aio.live.connect` and `synthesize_speech`, and requires the found set to
  EQUAL a pinned allowlist -- in both directions, so a new paid call fails the
  test and a stale entry does too. `backend/scripts/` is deliberately out of
  scope (operator budget, not product cost). Three sites today: the Live
  adapter, the text adapter, and `spellback_tts._synthesize_sync` -- which
  `intro_tts` and `notice_tts` both call, so all three TTS kinds share ONE call
  site. ALL THREE are `emit_wired: True` now (bd `polyglot-pdf-cjifh` for the
  live site, bd `polyglot-pdf-t86oz` for the other two), so no case in
  `test_paid_site_emits_a_usage_event` is xfail any more. The Live adapter's
  own proof was never xfail (`log_gemini_api_response` was already called
  before this); bd `polyglot-pdf-cjifh` is what makes that call's context ids
  real instead of always-None. Bd `polyglot-pdf-t86oz` did the equivalent for
  the other two: `TextAIGemini._generate` takes an optional `usage_kind` +
  `session_ctx` (threaded through `validate`/`ask`/`translate_labels`/
  `translate_items` -- `TextAIGemini` is a per-process SINGLETON, so these ids
  ride the call rather than living on `self`) reaching `_log_usage` ->
  `log_text_ai_usage`; and `synthesize_spellback`/`synthesize_notice`/
  `synthesize_intro` each call a shared `_log_tts_usage_event` helper
  (`spellback_tts.py`) after an ACTUAL synthesis (never on a cache hit) ->
  `log_tts_usage`. Callers build the `session_ctx` dict from their own state:
  `ValidatorService`/`FormFillingService` (a `_text_ai_session_ctx()` helper)
  for the text side, `backend/routes/tts_routes.py`'s `_usage_session_ctx`
  (built from the auth dependency's claims dict, mirroring the WS route's
  staff-uid-as-employee_id fallback) for TTS. Two callers OUTSIDE this bead's
  surfaces (`option_translation.py`'s authoring-time bake and runtime
  override build) do not pass `session_ctx` yet, so their `text_translation`
  events carry every context key null -- same shape as any other unmigrated
  caller, not a bug.
- **Pricing is a separate table per product** (`backend/config.py`).
  `GEMINI_PRICING_BY_FAMILY` prices the Live endpoint and does NOT transfer:
  `TEXT_GENERATION_PRICING` prices plain `generate_content`, and
  `TTS_PRICING_USD_PER_CHAR` prices Cloud TTS per CHARACTER, not per token.
  `get_text_generation_pricing` matches longest-key-first (so a `-lite` id is
  not billed at flash rates) and returns `None` for an unknown model instead of
  a fallback row -- deliberately unlike the Live lookup's
  `DEFAULT_PRICING_FAMILY`, because a confident wrong number in a cost report is
  worse than a visible gap. The Chirp3-HD rate is an unverified `None` today;
  see `docs/standards/logging-and-cost.md`.
- **PII:** ids, counts, costs and model names only. The envelope has no
  free-text slot, so the shape is HIPAA-safe by construction
  (`docs/standards/hipaa-pii-policy.md`, `backend/tests/test_no_pii_logging.py`).

### 21. Telemetry alert docs: `alerts/{id}` (Epic 3 bead E3.5, bd polyglot-pdf-bo95a)

Two hooks write into ONE collection with DETERMINISTIC ids, so a repeated
trigger dedups by overwriting the same document rather than piling up a row
per occurrence -- the load-bearing property this contract exists to pin.

- **Producer:** `backend/services/alerts.py`, the ONLY writer of the `alerts`
  collection. Two public entry points, both routed through one private
  `_write(doc_id, ...)` so the merge/idempotency/failure-swallowing logic
  lives in exactly one place:
  - **`record_link_exhausted(jti, firm_id, spend_usd, ceiling_usd)`**, called
    from `backend/services/link_spend.py`'s `check_budget()` in its
    `LinkBudgetExhausted` refusal branch, ONCE per raise. Doc id
    `link_exhausted_{jti}` -- a link that keeps attempting paid work after its
    ceiling trips collapses onto the SAME doc rather than paging an operator
    once per attempt. `check_budget` gained an OPTIONAL `firm_id` keyword
    purely to label this doc; it is never consulted by the budget decision
    itself. `firm_id` reaches the one call site
    (`backend/routes/websocket_routes.py`'s `_resolve_ceiling_and_check_
    budget`) from the verified token claims (`claims.get("firm_id")`).
  - **`record_credit_threshold(firm_id, balance, threshold)`**, called from
    `backend/services/credit_ledger.py`'s `append_entry()` AFTER a
    `mint_debit` commits (never for any other entry type -- a grant,
    adjustment or refund that happens to land while a firm is still low fires
    nothing; only a DEBIT pushing the firm there counts). Two DAY-KEYED doc
    ids, `{firm_id}_credit_low_{YYYY-MM-DD}` and
    `{firm_id}_credit_exhausted_{YYYY-MM-DD}` (UTC calendar day) -- a firm
    crossing the same boundary twice in one day still yields exactly one doc
    per kind per day, and a new UTC day resets it. `balance <= 0` writes the
    exhausted doc; `balance <= threshold` writes the low doc; both fire
    together when the balance is exactly zero (zero is also at-or-below any
    positive threshold). `threshold` comes from the new runtime-config key
    `CREDIT_LOW_THRESHOLD` (`runtime_config.credit_low_threshold()`, compiled
    default 10).
- **Idempotent id, not a merge race.** `_write` calls
  `ref.get()` then `ref.set(doc, merge=True)` as TWO separate, non-
  transactional Firestore calls -- deliberately, unlike `credit_ledger.py`'s
  `append_entry`, because this is best-effort telemetry, not money: a rare
  lost update on a repeat trigger the same second degrades to "the doc's
  `ts`/`context` reflect an earlier crossing instead of the latest one",
  never a wrong balance or a missed alert kind. The `ref.get()` read decides
  ONLY whether to seed `acknowledged_by`/`acknowledged_at`/`emailed_at` to
  `None` on first creation; a re-trigger of an already-acknowledged or
  already-emailed doc must not silently revive it, so those three keys are
  simply OMITTED from the payload on every write after the first (an omitted
  key survives a `merge=True` set untouched).
- **Fields (`alerts.ALERT_FIELDS`):** `firm_id`, `kind`
  (`link_exhausted`|`credit_low`|`credit_exhausted`), `level`
  (`warning`|`critical`), `ts`, `context` (metadata only -- `jti`/
  `spend_usd`/`ceiling_usd` for a link alert, `balance`/`threshold` for a
  credit alert; NEVER a field value, per
  `docs/standards/hipaa-pii-policy.md` and
  `docs/standards/stateless-architecture.md`), `acknowledged_by`,
  `acknowledged_at`, `emailed_at` (all three `None` until a later bead --
  the admin console's acknowledge action and Epic 3's dispatcher,
  respectively), `expire_at` (a datetime 90 days past the alert's own `ts`,
  for the TTL policy `scripts/setup-firestore-ttl.sh` already declares on
  this collection).
- **Never raises into the paid path (exit criterion 2).** `_write`'s
  Firestore calls are wrapped in one `try/except Exception`, including the
  `_collection()` call itself -- `get_db()` can RAISE (a broken
  `firebase_admin` app) rather than merely returning `None`, and that
  exception must be swallowed exactly like a write failure; both public
  entry points therefore never raise for any reason, so `check_budget` still
  raises `LinkBudgetExhausted` for the REAL reason even when the alert store
  is unreachable, and a debit already committed in `append_entry` is never
  undone by a telemetry failure downstream of it.
- **`CREDIT_LOW_THRESHOLD`** joins `RUNTIME_CONFIG_KEYS` (contract 14) as a
  SECOND never-had-an-env-var key alongside `CREDITS_ENFORCED` -- no
  `os.getenv` fallback exists or may exist for either; the coercion rejects
  a `bool` (the same int-subclass trap `LINK_FIRM_CAP` guards) and any
  negative value, but ACCEPTS zero (an operator who wants only the
  zero-balance/exhausted alert, no separate low warning -- `alerts.py`'s
  `record_credit_threshold` gates its low-alert write on `threshold > 0` so
  a threshold of exactly zero never emits the separate `credit_low` doc).
- **`firestore.rules` denies `alerts/{alertId}` to all clients**, pinned by
  the same set-derived test as every other Admin-SDK-only collection
  (contract 15's neighbour, `test_firestore_rules_text.py`).
- **Consumer:** none yet in this bead -- the admin console's alerts list
  (acknowledge) and Epic 3's `POST /admin/alerts/dispatch` email sender are
  later beads, both reading/writing the same doc shape this contract fixes.

### 22. Link listing + revoke: admin routes -> the mint record's `status` -> A3's open gate (Epic 2 Track B bead B4, bd polyglot-pdf-jmiys)

**The FIRST bead to actually WRITE `links[_<channel>]/{jti}.status` past
`minted`** (contract 16 laid the schema and left every non-mint transition
"not wired to anything yet"). `POST /admin/links/{jti}/revoke`
(`admin_backend/routes/link_routes.py`) is the producer: a
`@firestore.transactional` read-check-write (mirrors `firm_routes.py`'s
`_apply_firm_patch` shape) that flips `status` from `links_store.
STATUS_MINTED` to `STATUS_REVOKED` and stamps `revoked_by`/`revoked_at`,
with the audit row in the SAME transaction. Only a `STATUS_MINTED` record
may transition (409 naming the current status otherwise) -- an
opened/completed/refunded/already-revoked record's `status` is never
overwritten by this route.

**The consumer this status flip exists FOR is Epic 2 Track A bead A3's
open gate** (Surface contract 24, bd polyglot-pdf-jecrl):
`backend/routes/link_routes.py`'s `open_client_link` reads
`links_store.get_link(jti, channel=...)` and a `STATUS_REVOKED` (or
`STATUS_REFUNDED`, or missing) record makes `POST /api/links/open` return
the SAME uniform 404 every other refusal on that route already returns (bd
polyglot-pdf-ugm6's indistinguishable-refusals invariant). This bead does
not add that consumer itself -- doing so would fork A3's one gate outside
its declared surfaces -- so `backend/tests/integration/
test_revoked_link_open.py` (this bead's own surface) pins the
producer-to-consumer contract end to end over the real open route: a
record revoked through this route cannot open.

**Second consumer: the listing route's join.** `GET /admin/firms/{firm_id}
/links` reads BOTH `links[_<channel>]` (bead A1's mint record: `jti`,
`kit_id`, `employee_id`, `status`, `minted_at`, `open_deadline`, `cap_usd`,
`credit_cost`) and `link_redemptions[_<channel>]` (contract 9's shape, plus
bead ik7e's `spend_usd`/`turns` fields, `backend/services/link_spend.py`)
by `jti`, and assembles the two into ONE explicit key allowlist
(`link_routes._ALLOWLISTED_KEYS`) -- never `**doc`, so a field added to
either stored document later does not silently reach a firm manager's
response. There is no cross-collection query; a firm's link count is
already bounded by bead ik7e's per-firm minting meter, so an N+1 per-jti
redemption read is the same shape `credit_ledger.reconcile_expired_for_
firm` and the sweep route (contract 15's neighbour) already accept.

**The firm-scoping shape is NOT `admin_auth.resolve_target_firm`
(contract 19).** That helper's rule is "a manager may not NAME a firm in
the request body at all" -- correct for `/admin/users`, where a manager
never has a reason to type their own `firm_id`. Both B4 routes take
`firm_id`/the link's owning firm from a URL PATH, which a manager MUST be
able to name (their own firm) to reach a `GET` at all -- so this bead adds
its own small `_require_owning_firm(actor, firm_id)` helper, LOCAL to
`admin_backend/routes/link_routes.py`, which refuses a manager acting on
any OTHER firm with the SAME 404 an unknown firm_id/jti would get (never
403, which would confirm the other firm exists). `resolve_target_firm`
itself is untouched by this bead and stays the one home for the body-field
rule it already owns.

### 23. Main app -> admin service: base URL + channel wiring (Epic 2 Track C bead C0, bd polyglot-pdf-z4ljj)

The main voice app's firm-console pages (`frontend/src/console/*`, alongside
`MintLinkPage.tsx`) call the admin service directly, over plain HTTP -- a
THIRD destination distinct from both the `/api/**` Hosting rewrite (which
proxies only the public backend) and the WebSocket path (contract 9 /
`config.ts`'s `getBackendUrl()`). This contract is the plumbing bead C4
(employees) and C5 (link history) build their actual route calls on; BOTH
now call it -- C4's `EmployeesPage.tsx` (contract 19's four `/admin/users`
routes) and C5's `LinkHistoryPage.tsx` (contract 22's listing + revoke).

- **Producer:** `deploy-all.sh`'s frontend stage. `ADMIN_SERVICE_NAME`
  (`${ADMIN_SERVICE_NAME:-polyglot-admin}`, matching `deploy-admin.sh`'s and
  `deploy-admin-console.sh`'s own default) is resolved to a live Cloud Run URL
  via `gcloud run services describe`, the SAME mechanism `VITE_WS_URL` already
  uses for the public backend -- a second, independent `gcloud` call and a
  second `export VITE_ADMIN_API_BASE_URL=...` in the same stage. Unlike
  `BACKEND_SERVICE_NAME`, `ADMIN_SERVICE_NAME` is never overridden by either
  channel wrapper: there is ONE admin service serving BOTH channels'
  Firestore data (see contract 17 and `docs/doctrine/promotion-tiers.md`), so
  staging and demo both want the same value. Each resolution is followed by
  its own `verify_service_publicly_reachable(..., warn)` call -- warn, not
  fatal, because the admin service is pre-existing from this script's point
  of view (`deploy-admin.sh`'s job, not this one's), the same reasoning
  `deploy-admin-console.sh`'s and `deploy-editor.sh`'s identical warn-mode
  calls already use. An EXPLICITLY-selected channel (`BACKEND_SERVICE_NAME_
  EXPLICIT` -- the SAME capture `VITE_WS_URL`'s abort branch reads; there is
  only one such signal in `deploy-all.sh`) whose admin URL cannot be resolved
  aborts the build (`exit 1`); a bare run warns and falls back to the
  committed `.env.demo` literal, exactly mirroring `VITE_WS_URL`'s two-branch
  shape. Pinned by `tests/test_deploy_admin_url_injection.py` and
  `tests/test_deploy_reachability_gate.py`'s `URL_BAKING_SEVERITY["deploy-
  all.sh"] = (2, 1)` / `GATED_DEPLOY_SEVERITY["deploy-all.sh"] = (2, 1)`.
- **`VITE_APP_CHANNEL`**, the SECOND half of this contract: `deploy-
  staging.sh` exports `VITE_APP_CHANNEL="staging"` and `deploy-demo.sh`
  exports `VITE_APP_CHANNEL="demo"`, each as a `VAR=value` prefix on their own
  `FRONTEND_BUILD_CMD=...` invocation of `deploy-all.sh` -- inherited by
  `deploy-all.sh`'s own `$FRONTEND_BUILD_CMD` child process without
  `deploy-all.sh` needing to `export` it itself (unlike the two
  `gcloud`-resolved URLs, which `deploy-all.sh` computes rather than
  receives). This is deliberately NOT derived from Vite's `MODE`: both
  channel wrappers build with `npm run build:schema:demo` (mode `demo`,
  because staging and demo share one Firebase project and therefore one set
  of client Firebase keys -- see "Frontend" in
  `docs/components/config-deployment.md`), so `import.meta.env.MODE` cannot
  tell the two apart.
- **Consumer:** `frontend/src/shared/config.ts`'s `getAdminApiBaseUrl()`
  (reads `VITE_ADMIN_API_BASE_URL`, empty string when unset -- no
  runtime-detection fallback chain the way `getBackendUrl()` has, since a
  wrong guess here would point firm-console pages at a plausible but wrong
  URL rather than failing visibly) and `getAppChannel()` (reads
  `VITE_APP_CHANNEL`, falling back to `'demo'` on an unset OR unrecognized
  value -- the same "unset means demo" convention `link_channel()` and every
  bucket default in this repo already use, and a defense against a typo
  minting a `channel` value the admin service's own `KNOWN_CHANNELS` check
  would 404 on). `APP_CHANNELS = ['demo', 'staging']` mirrors
  `admin_backend/routes/config_routes.py`'s `KNOWN_CHANNELS` -- there is no
  `prod`.
  `frontend/src/console/adminApi.ts` wraps both into `adminFetch(path, user,
  init, fetchImpl)`: resolves the caller's Bearer token via
  `resolveStaffToken` (never `resolveSessionToken` -- firm-console actions
  are staff-only, and the form-filling resolver's client-link-wins
  precedence would send the wrong credential the moment a staffer has opened
  one of their own links in the same tab, bd `polyglot-pdf-so88g`, the exact
  workaround `MintLinkPage.tsx` already applies), appends `?channel=<this
  build's channel>` via the exported `withChannel()` helper (preserving any
  query params the caller's `path` already carries), and classifies a 401 as
  `AuthError` / a 403 as `ForbiddenError` carrying the server's `detail` --
  mirroring `admin-console/src/utils/adminApi.ts`'s identical shape against
  the SAME admin service, deliberately duplicated rather than imported (no
  new cross-surface dependency between `frontend/` and `admin-console/`, the
  same constraint `admin-console/src/utils/adminAuth.ts` documents).
  Both C4/EmployeesPage.tsx (wired to all four `/admin/users` routes,
  contract 19) and C5/LinkHistoryPage.tsx (wired to contract 22's listing +
  revoke routes) are now real callers of this app's `adminFetch`.
- **`MintLinkPage.tsx`'s A3 responses** (bd `polyglot-pdf-jecrl`, contract 9):
  the mint route's 402 (`credit_ledger.InsufficientCredits` ->
  `MintRefused(402, ...)`) and its SECOND 403 (a live firm on a non-demo
  `LINK_CHANNEL` -> `MintRefused(403, "This deployment cannot mint links for
  a live firm.")`, distinct from the pre-existing "no firm claim" 403) are
  each shown as their own plain-language message. The two 403s are
  distinguished by a substring check on the response `detail` (`"live
  firm"`), since they need opposite remedies -- the original means "ask an
  app admin to attach your account to a firm"; the new one means "this
  firm's deployment choice is wrong" and is not fixable by the signed-in
  staffer at all. The 402 body carries no `balance` field today
  (`link_routes.py`'s `MintRefused` detail is always a plain string); the
  page checks for one defensively (`typeof body.balance === 'number'`) so a
  future response gains the richer message with no frontend change required.

### 24. The mint reservation and the open gate (Epic 2 bead A3, bd polyglot-pdf-jecrl)

**One invariant seen from both ends:** a signed client-link token exists only
because a credit was reserved for it, and only a token with that reservation
on record can open. Break either half and the other becomes decorative --
minting without reserving gives away sessions, and reserving without gating
the open leaves pre-cutover tokens spending for free.

**Producer -- `backend/routes/link_routes.py`'s `mint_link`** now runs
`new_jti()` -> ONE transaction -> sign, in that order. The transaction is
`credit_ledger.append_entry()` (contract 18) with the
`links[_<channel>]/{jti}` record (contract 16) passed as `extra_writes`, so
the balance, the `mint_debit` entry and the mint record commit together or
not at all. Only then is `mint_link_token(..., jti=..., cap_usd=..., now=...)`
called. **A refused mint returns no token, writes no ledger entry and leaves
no record.** Anything that reorders these steps -- or adds a second,
non-transactional write between them -- reopens the hole.

- **`_reserve_mint(jti, firm_id, kit_id, employee_id, credit_cost, cap_usd,
  open_deadline, channel, enforced, now)`** is the sync helper the route
  dispatches through `asyncio.to_thread` (a multi-round-trip transaction on
  the shared Cloud Run loop would stall every concurrent request, in-flight
  audio included). It raises `MintRefused(status_code, detail, reason)` for
  the two caller-visible refusals and lets `LedgerError` through for
  deployment faults.
- **`links_store.mint_record_ref(db, jti, channel)`** exists so the
  transaction can write that document through the SAME client the transaction
  belongs to. `channel` is REQUIRED there, not defaulted: the only caller has
  already decided which channel it is acting on.
- **The refusal codes are staff-facing and deliberately NOT the uniform 404.**
  `403` -- the firm is `live`, or has no `kind` at all, and the process's
  **raw `LINK_CHANNEL` env var** is not exactly `demo`. `402` --
  `CREDITS_ENFORCED` (runtime config, contract 14) is on and the balance will
  not cover `credit_cost`; with it OFF the debit is still written and the
  balance may go negative, the metered soft-launch mode. `503` -- no such
  firm, or an unreachable store. The uniform-refusal rule protects the
  UNAUTHENTICATED `/open` door; this one already knows exactly who is calling.
- **The channel gate reads `os.environ["LINK_CHANNEL"]`, NOT
  `link_tokens.link_channel()`.** `link_channel()` defaults to `demo` (so an
  unconfigured deploy keeps working), which means asking it would let an UNSET
  channel debit a paying firm. Both halves are load-bearing and both are
  pinned: an unset channel still mints `aud=demo` tokens for **mock** firms
  while refusing live ones. A firm with no `kind` counts as live -- the same
  fail-closed polarity as `firms.firm_kind()`. **This is what makes
  staging-vs-demo firm-billing isolation a code property**, replacing the
  operational habit `docs/doctrine/promotion-tiers.md` used to describe.
- **The kit's price: `backend/services/kit_commercials.py` (NEW).**
  `resolve_commercial(kit_id)` reads `kits/{kit_id}` and returns
  `{credit_cost, cap_usd, source}`. FAIL-SOFT IN ONE DIRECTION: a missing
  doc, an unreachable store or a malformed value resolves to the global
  defaults, never to "free" and never to "no ceiling". `burn_cap_usd` funnels
  through `link_budget.cost_ceiling_usd_for_kit()` (contract 12's parsing
  rule, reused rather than re-implemented); `credit_cost` falls back to
  `DEFAULT_CREDIT_COST = 1`, because no global runtime-config key for it
  exists. The read sits OUTSIDE the transaction on purpose -- both numbers
  have safe defaults, and the invariant that must not break is the
  transaction's, not this read's.
- **Both numbers are resolved ONCE and then travel.** `cap_usd` is signed
  into the token (contract 12's precedence then needs no per-connect kit
  read); both are snapshotted onto the record. A later pricing edit cannot
  change what an already-minted link costs or may spend.
- **`open_deadline` MUST equal the token's `exp`.** The route passes one
  `issued` clock to both. A5's expiry sweep queries Firestore on
  `open_deadline`; a drifted value would refund a link that can still open,
  or leave a dead one unrefunded.

**Consumer -- the open gate, inside
`link_redemptions.enforce_link_redemption`** (contract 9's shared helper, so
`/api/links/open`, `/ws/fill` and `require_paid_client_work` all inherit it
from one place rather than three copies). `_require_mint_record(jti)` reads
`links_store.get_link(jti, channel=link_channel())` and raises the new
`LinkNotMinted` when there is no record, or when `status` is in
`links_store.OPEN_BLOCKING_STATUSES` (`revoked`, `refunded`). Every other
status falls through to the redemption gate.

- **It runs FIRST**, before `open_link()` creates the redemption doc.
  Checking after would stamp `opened_at` on a link about to be refused.
- **`LinkNotMinted` subclasses `RedemptionUnavailable`.** The socket gate and
  `require_paid_client_work` catch a tuple that already names the base class,
  so a door added later that catches only that still fails closed. Changing
  the base class silently un-gates every door that does not name
  `LinkNotMinted` explicitly.
- **`OPEN_BLOCKING_STATUSES` is a closed set of TERMINAL MONEY states.**
  `opened` and `completed` are best-effort mirrors -- refusing on them would
  break reopening an unfinished link, which the seven-day completion window
  exists to allow -- and `budget_exhausted` is telemetry only. A new status
  joins the blocking set only if it, too, means the money is gone.
- **An unreachable links store RAISES** (`get_link`'s documented
  None-vs-raise split), so "never minted" and "cannot tell" both refuse but
  stay distinguishable in the log.
- **No new oracle:** every door returns the refusal it already returned (the
  uniform `404`; close code `1008` at the socket).
- **A successful `/open` best-effort mirrors the record to `opened`**
  (`links_store.mark_opened`, which never raises). The console's link table
  reads it; nothing that moves money does.

**CUTOVER (deliberate, maintainer call):** tokens minted before the record
existed cannot open. The maintainer re-mints any outstanding link.

**Test fake:** `backend/tests/unit/_fake_firestore.py` is the shared
buffer-and-retry Firestore fake, used by both `test_credit_ledger.py` and
`test_link_routes.py` now that two callers drive the same transaction. A
second copy would drift, and a drifted copy lets one caller's tests pass
against semantics the other does not have.

**Write side (Epic 2 Track B bead B3, bd polyglot-pdf-f0kuu):**
`admin_backend/routes/kit_routes.py` adds GET `/admin/kits`, GET/PUT
`/admin/kits/{kit_id}/commercial`, all behind `require_app_admin`. GET
calls `kit_commercials.resolve_commercial(kit_id)` -- the SAME reader the
mint transaction above uses, so the console can never show a number the
mint path would not also charge; `GET /admin/kits` lists every kit id the
form-kit store knows (`backend/services/form_kits.py`'s async
`list_kit_ids()`) joined with that same resolved commercial. PUT is
STRICTER than the read-side fallback on purpose: `credit_cost` must be a
positive int, `burn_cap_usd` a positive finite float (bool, NaN and +-inf
all refused explicitly -- bool is an int subclass, so an unguarded check
would price a form at 1 credit on a stray `true`), `display` a small string
map -- a malformed value here must be REFUSED (422) before it ever reaches
the store, never silently written and left for the read side's fallback to
paper over. The write and its audit row share ONE `@firestore.transactional`
body (mirrors `firm_routes.py`'s `_apply_firm_patch` shape), so a forced
audit failure leaves `kits/{kit_id}` unchanged.

### 25. BigQuery telemetry sink + cost/income views (Epic 3 bead E3.6, bd polyglot-pdf-rd3s8)

The consumer half of contract 20's usage-event shape, plus a second, genuinely
DIFFERENT shape (`ledger_export`) that contract 18 already produces. Declarative,
operator-run infrastructure: nothing in this contract executes against GCP from
a deploy script.

- **Producer:** `scripts/setup-telemetry.sh` creates the `polyglot_telemetry`
  BigQuery dataset (`us-central1`) and a Cloud Logging sink over THREE Cloud Run
  services -- the public backend, its staging twin, AND the admin service
  (`polyglot-admin`, since `ledger_export` is emitted only from
  `admin_backend/routes/credit_routes.py` and `sweep_routes.py`, never from the
  public backend) -- then applies `sql/telemetry_views.sql`'s five
  `CREATE OR REPLACE VIEW` statements via `bq query`, substituting `${DATASET}`,
  `${TELEMETRY_TABLE_STDOUT}` and `${TELEMETRY_TABLE_STDERR}` (read back from
  `bq ls` on the dataset, not hardcoded -- the sink writes TWO destination
  tables, not one: usage events print to stdout
  (`structured_logger.py`'s `print(..., file=sys.stdout)`) while
  `ledger_export` and the session events go through plain `structlog` calls
  that reach stdlib logging's default stream, which `backend/utils/logging.py`
  never overrides to stdout, so those land on stderr instead -- the three
  cost views read `${TELEMETRY_TABLE_STDOUT}` and `income_month` reads
  `${TELEMETRY_TABLE_STDERR}`; see bd polyglot-pdf-ih428) and
  `${BILLING_EXPORT_TABLE}` (a required second script argument; the Cloud
  Billing export itself is a separate maintainer console step, Epic 3
  bead 7).
- **Consumers:** the admin console's cost/income dashboards (a later bead) query
  `cost_by_firm_month`, `cost_by_kit_month`, `cost_by_employee_month`,
  `hosting_cost_by_service_month` and `income_month` directly; `admin-backend-sa`
  is the identity that runs those queries (`roles/bigquery.jobUser` +
  dataset-scoped `roles/bigquery.dataViewer`, both granted by this script rather
  than `scripts/setup-admin-service.sh`).
- **The sink filter is three DIFFERENT jsonPayload shapes ORed together, not
  one field name.** *Breaks if collapsed to a single clause:* `jsonPayload.
  event_type IN (...)` alone would match `ledger_export` (contract 18's
  producer passes `event_type=` as an explicit `structlog`-bound kwarg, so
  `JSONRenderer` puts it at the top level) but silently drop every usage event
  (contract 20's producer, `StructuredLogger._emit`, wraps the whole envelope
  in a `message` key, so its event type is at the NESTED
  `jsonPayload.message.event_type`) and every session event
  (`confirmation_logger.py`'s `log_form_session_start`/`log_form_session_end`
  pass NO `event_type` kwarg at all, so `structlog` renders the POSITIONAL
  event name under the plain key `jsonPayload.event`, a third shape again).
  Verified against real emitted JSON, not the plan's prose, which describes
  the filter as if one field covered every case. Error events (Epic 3 bead 8,
  not yet built) are deliberately absent from the filter until
  `StructuredLogger.log_error` has a real call site; when it does, it shares
  contract 20's nested shape, so widening this filter is a one-line addition.
- **Views reference ONLY columns their source event actually emits, checked by
  a DERIVED set, not a hand list.** `backend/tests/unit/test_telemetry_views.py`
  parses `sql/telemetry_views.sql` and asserts every
  `jsonPayload.message.metadata.*` reference in the three cost-by-* views is a
  member of `log_schemas.USAGE_CONTEXT_KEYS` (contract 20) plus the fixed
  cost/count keys `StructuredLogger._emit_usage` always writes, and every flat
  `jsonPayload.*` reference in `income_month` is a member of
  `credit_ledger.LEDGER_EXPORT_FIELDS` (contract 18). *Breaks if a view drifts
  onto an unemitted column:* BigQuery does not error on an unknown JSON path --
  it returns NULL forever, so a dashboard column goes silently and permanently
  empty.
- **`income_month` hard-codes `firm_kind = 'live'` in the view definition, not
  left to a caller's WHERE clause** -- Epic 3's overall exit criterion 5 (the
  income-filter half this bead inherits). Income cannot filter on `channel`:
  the admin service that writes `purchase`/`subscription_grant` ledger entries
  has none, so the firm's `firm_kind`, snapshotted onto each `ledger_export`
  line by `append_entry` (contract 18), is the only test-vs-real signal
  available. `backend/tests/unit/test_telemetry_views.py` and
  `backend/tests/unit/test_credit_ledger.py::
  test_export_line_carries_every_column_income_month_reads` both pin this --
  the latter closes the loop from the OTHER direction, deriving `income_month`'s
  referenced columns from the SQL and asserting a real emitted `ledger_export`
  payload carries every one of them.
- **`hosting_cost_by_service_month` reads the Cloud Billing detailed export
  table, not the telemetry sink** -- the sink carries no cost figures for
  Cloud Run compute or Firebase Hosting bandwidth, only the application's own
  usage/ledger events. Splits by `resource.name` (the Cloud Run service name)
  so `polyglot-backend` and `polyglot-backend-staging` cost never mix; Firebase
  Hosting line items carry no per-channel resource name in the export and
  group under `NULL` rather than being misattributed to one channel. Returns
  zero rows until the maintainer enables the export (Epic 3 bead 7) -- not
  retroactive.
- **The sink step is create-or-update, not create-only (bd polyglot-pdf-f7f0h):**
  `gcloud logging sinks describe` decides whether to `sinks create` (first
  run) or `sinks update` (the sink already exists), so a re-run after
  `SINK_FILTER` changes actually applies the new filter to the LIVE sink --
  a bare `sinks create` fails on an existing sink and cannot do this.
- **IAM, four grants total:** the sink's own writer identity (parsed at
  runtime -- from `gcloud logging sinks create`'s output on first creation, or
  from a `gcloud logging sinks describe --format=value(writerIdentity)` call
  on a re-run, NOT a hardcoded principal) gets `roles/bigquery.dataEditor` on
  the dataset; `admin-backend-sa`
  gets project-level `roles/bigquery.jobUser` and dataset-scoped
  `roles/bigquery.dataViewer`. The latter two were moved OUT of
  `admin_backend/tests/unit/test_admin_sa_iam_envelope.py`'s `DEFERRED_ROLES`
  set (where Epic 1's `setup-admin-service.sh` had deliberately left them
  ungranted) into `EXPECTED_ADMIN_SA_ROLES`, with a new
  `TELEMETRY_GRANTED_ROLES` constant marking that `setup-telemetry.sh`, not
  `setup-admin-service.sh`'s `PROJECT_ROLES` array, is what actually grants
  them -- `test_admin_sa_project_role_pin_matches_the_setup_script` subtracts
  that constant out before comparing against `setup-admin-service.sh` alone.

### 26. Session-end usage rollups: `firms/{firm_id}/usage/{YYYY-MM[_channel]}` + `kits/{kit_id}/usage/{YYYY-MM[_channel]}` (Epic 3 bead E3.4, bd polyglot-pdf-w828m)

**Two entry points, new `backend/services/usage_rollups.py`, write into the
SAME per-month rollup documents from three call sites.**

- **`record_session_end(firm_id, kit_id, employee_id, language, channel,
  kind, completion_status, cost_usd, now=None)`** -- called from the SAME
  teardown block in `backend/routes/websocket_routes.py` that already runs
  `log_form_session_end` and `_bank_link_spend`, on EVERY connection
  teardown (gated on `should_log_session_end`, the same gate the audit row
  uses). Writes ONE BATCHED `db.batch()` set of `firestore.Increment`
  updates -- `firms/{firm_id}/usage/{YYYY-MM[_channel]}` (`connections_ended`,
  `sessions_completed`, `cost_usd_total`, `by_kit.{kit_id}.{sessions,
  cost_usd}`, `by_employee.{uid}.{...}`, `by_language.{code}.{...}`, `kind`,
  `channel`) and `kits/{kit_id}/usage/{YYYY-MM[_channel]}` (`connections_ended`,
  `sessions_completed`, `cost_usd_total`, `by_firm.{firm_id}.{...}`, `kind`,
  `channel`) -- committed TOGETHER so a mid-write failure cannot leave one
  side bumped with no matching entry on the other. A firm-less session
  (`firm_id` falsy) returns `False` and writes NOTHING before ever calling
  `_get_db()` -- both target documents are firm/kit-keyed, so there is no
  unattributed bucket to write into. `connections_ended` is the HONEST name
  (this fires per CONNECTION, same distinction `log_form_session_end`
  already documents); `sessions_completed` increments only when
  `completion_status == "completed"`.
- **`record_link_opened(firm_id)` / `record_link_completed(firm_id)`** --
  single-doc `firms/{firm_id}/usage/{YYYY-MM[_channel]}` increments
  (`links_opened`/`links_completed`), called from
  `backend/services/link_redemptions.py`'s `open_link()` (ONLY on the
  genuine first-open branch -- the idempotent re-open of an already-open
  link inside its completion window must NOT inflate the counter on every
  reconnect) and `complete_link()` (which reads `firm_id` back off the
  just-updated redemption record, since its only caller has no other reason
  to thread it through). `record_session_end` does not produce these two
  counters itself: open/complete are redemption-record events, not
  connection-teardown events, and a link can be opened without a session
  ever completing. Neither takes a `channel` argument -- both callers run
  only on the public backend, which has exactly one channel of its own, so
  the month id resolves through `link_channel()`, same as
  `record_session_end`'s default-resolution sibling.
- **The month DOCUMENT ID is channel-suffixed, not the collection.** Staging
  and demo share one Firestore project (see "Deployment / promotion" in
  CLAUDE.md), and these rollup docs are shared AGGREGATE counters each
  write overwrites in place -- unlike `credit_ledger.py`'s append-only
  entries, where `channel` is honestly just a record of where a debit
  happened. A bare `YYYY-MM` id would let a staging test-drive increment
  the SAME document the demo's billing view reads, with no way to filter
  it back out at read time. `_month_key(stamp, channel)` follows the
  established channel-suffix convention from bd polyglot-pdf-3q9qn
  (`link_redemptions._collection_name` / `links_store._collection_name`,
  which suffix a COLLECTION name): the demo channel keeps the bare
  `YYYY-MM` id (nothing already written is orphaned), every other channel
  gets `YYYY-MM_{channel}`. Pinned by
  `backend/tests/unit/test_usage_rollups.py`'s channel-partitioning cases
  (a staging session's totals do not land on the demo firm/kit docs; the
  demo channel keeps the bare id; the link-opened/completed counters are
  also partitioned).
- **Cost is read from the SAME live adapter `_bank_link_spend` reads,**
  through a new shared helper `websocket_routes._session_cost_usd(service)`
  (`getattr(service, "live_ai", None)` then `.session_cost_usd()`, never
  raising) -- extracted so the two call sites cannot drift on the hasattr
  guard or the None-coalescing. Both MUST run before `service.end_session()`
  finalises the adapter.
- **`by_language` keys on the session's BCP-47 code, with a raw-name
  fallback.** New `websocket_routes._rollup_language_key(service)` calls
  `FormFillingService.spoken_language()` (a new public accessor for the
  otherwise-private `_spoken_language`) through
  `backend.utils.language_codes.bcp47_codes_for_spoken_language`; a spoken
  language not yet in that map (the "17 languages growing to ~90" doctrine
  -- see CLAUDE.md scar tissue) still gets counted, under its plain name,
  rather than silently dropped from `by_language`. (The raw-name fallback
  is an unbounded, client-influenced map key -- tracked separately as bd
  polyglot-pdf-u9gtj, not a gap in this contract's own shape.)
- **`by_employee` keys on `usage_employee_id`** (Epic 3 bead E3.2's existing
  parameter: the link's `employee_id` for a client-link session, the staff
  uid for a staff session) -- NOT `link_employee_id`, which is
  contractually `None` for a staff session (the confirmation-audit "who
  SENT the link" field). `record_session_end` itself is attribution-source
  agnostic; the caller resolves which id applies.
- **`kind` comes from `backend/services/firms.py`'s existing
  `firm_kind(firm_id)`** (fail-closed to `"live"`); `channel` from
  `link_tokens.link_channel()`. Neither is new plumbing.
- **Both `firm_kind()` and `record_session_end()` run OFF the event loop,**
  dispatched through ONE `asyncio.to_thread` call in the teardown block
  (`firm_kind`'s result feeds `record_session_end`'s `kind` argument, so
  both resolve inside the same thread dispatch -- mirrors the
  `_resolve_ceiling_and_check_budget` pattern already on this route).
  `firm_kind` is an uncached sync Admin-SDK `.get()` and
  `record_session_end` does its own db lookup plus a `batch.commit()` --
  both blocking network calls that, called directly on the shared Cloud Run
  loop, would stall every other concurrent connection (in-flight audio
  included) on the highest-frequency teardown path in the app. Pinned by
  `test_TEARDOWN_dispatches_the_usage_rollup_OFF_the_event_loop` in
  `backend/tests/integration/test_websocket_ephemeral.py`, which spies on
  `asyncio.to_thread` directly (a fake Firestore's instant return makes a
  missing wrapper invisible to every other test in this suite).
- **HYPHENATED MAP KEYS BREAK ONE FIRESTORE WRITE API BUT NOT THE OTHER --
  the load-bearing subtlety this bead exists to get right.** A kit id like
  `i-90` or a language code like `zh-CN` cannot be a flat dotted STRING
  key handed to `set(merge=True)` (the write API this module uses, chosen
  over `update()` so the FIRST write of a new month document CREATES it
  rather than raising on `update()`'s default `exists=True` precondition):
  confirmed against the vendored SDK
  (`backend/.venv/Lib/site-packages/google/cloud/firestore_v1/_helpers.py`)
  that `DocumentExtractorForMerge._get_document_iterator` calls
  `extract_fields(..., expand_dots=False)`, so a string key --
  hand-joined OR a properly-escaped `FieldPath(...).to_api_repr()`, the
  string form `update()`'s DIFFERENT extractor needs -- is stored as ONE
  literal top-level field, not the intended nested path. So every nested
  increment is built by `_nest_increment()` as a REAL nested Python dict,
  walking a `FieldPath(*parts).parts` tuple (the raw, unescaped segment
  strings) rather than ever serializing through a dotted string. Pinned by
  `backend/tests/unit/test_usage_rollups.py`'s hyphenated-kit-id and
  hyphenated-language-code cases, which assert on the actual nested-dict
  shape a faithful fake Firestore merge receives.
- **No sharding** -- the documented escape hatch, matching
  `link_spend.py`/`credit_ledger.py`'s own unsharded `Increment` precedent;
  shard the doc id (`YYYY-MM-{n}`) and sum on read if contention becomes
  real.
- **No IAM change.** Writes through the same `get_db()` (`firebase_admin`'s
  Firestore client) every other backend Firestore write in this codebase
  uses -- the public backend's runtime service account already writes
  `firms/{firm_id}` ledger entries, links, link_redemptions and alerts
  through this identical client.
- **Best-effort, never raises**, matching `alerts.py`'s contract exactly
  (including a broken `firebase_admin` app -- `get_db()` RAISING, not just
  returning `None`): this runs inside `websocket_routes.py`'s teardown
  `finally` block, so a Firestore hiccup here must not stop the other
  teardown steps or crash the connection close.
- **`firestore.rules` denies both `firms/{firmId}/usage/{monthId}` and
  `kits/{kitId}/usage/{monthId}` to every client**, pinned by the same
  set-derived test as every other Admin-SDK-only collection (contract 15's
  neighbour, `test_firestore_rules_text.py`) -- TWO entries, since neither
  parent's deny block cascades to a nested subcollection.
- **Consumer:** none yet in this bead -- the admin console's per-firm usage
  view (Epic 1 shell) and the future per-kit view are later beads reading
  this exact document shape.

### 27. Link history: the first real caller of contract 23's admin-service wiring (Epic 2 Track C bead C5, bd polyglot-pdf-x22hm)

`frontend/src/console/LinkHistoryPage.tsx`, mounted at `/console/links/history`
(`frontend/src/schema-forms/AppRoutes.tsx`'s `LINK_HISTORY_PATH`, behind
`ProtectedRoute` -- pinned by `AppRoutes.test.tsx`, extended to cover this
route alongside C4's employees-route coverage rather than a separate file),
is the first page to call a concrete admin-service route through contract
23's `adminFetch` -- contract 23 named this page and C4's `EmployeesPage.tsx`
as "the first real callers" before either existed.

- **Role comes from the verified token's OWN custom claims**, read via
  `user.getIdTokenResult()` -- `claims.firm_id` and `claims.firm_role`, the
  SAME two claims `backend/services/firms.py`'s `manager_firm_id` reads
  server-side. This is a NEW client-side read (no prior page in this repo
  called `getIdTokenResult()`); it decides only which UI controls render
  (the manager's filter row and Revoke column) and is never trusted as a
  security boundary -- the admin service re-verifies the bearer token on
  every request regardless of what this page shows.
- **The fetch path is built from the claimed `firm_id`**:
  `GET /admin/firms/{firm_id}/links`, with `?status=`/`?employee_id=` added
  ONLY for a manager (an employee's request always omits `employee_id`,
  matching the bead's own wording). `POST /admin/links/{jti}/revoke` is
  manager-only, fires once per click (disabled while in flight), and on
  success RE-FETCHES the list rather than patching the clicked row locally
  -- the server, not local state, decides what the table shows after a
  write (a 409 means the write did NOT land).
- **Renders only bead B4's allowlisted columns** (`_public_link_view`'s
  `jti, kit_id, employee_id, status, minted_at, open_deadline, opened_at,
  completed_at, spend_usd, turns, cap_usd, credit_cost`), built by hand from
  named fields -- never `{...row}` -- so a row is never spread onto the DOM.

**A KNOWN GAP, found while building this page, NOT fixed here:**
`require_app_admin_or_owning_manager` (contract 22) has exactly two actor
kinds -- app admin, or firm MANAGER. An EMPLOYEE-role account is refused
with a flat 403 before `GET /admin/firms/{firm_id}/links` ever reaches its
own `employee_id` filtering logic, so an employee cannot see even their own
link history against the real deployed admin service today. The plan named
two tests for this (`test_employee_link_listing_response_is_allowlisted`,
`test_employee_history_scoped_to_token`) that bead B4 (`polyglot-pdf-jmiys`)
never implemented. Filed as `polyglot-pdf-scaig` (admin_backend surfaces,
not this bead's) rather than fixed inline -- this page's own exit criteria
are frontend-only and are pinned against a mocked API regardless, so the
page needs no change once `scaig` closes.
