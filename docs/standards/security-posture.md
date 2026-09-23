# Security posture

**Tracks:** scripts/audit/inventory_stores.py scripts/audit/log_pii_sweep.py scripts/audit/infra_posture.sh backend/tests/integration/test_access_matrix.py admin_backend/tests/unit/test_access_matrix.py firestore.rules firebase.json backend/routes/websocket_routes.py backend/services/link_tokens.py

*Last updated: 2026-09-23 (sprint 23 closing snapshot: the demo deploy, the posture run and the log sweep recorded).*

The current-state home for how this app keeps client data in and
unauthorised parties out: the threat model, every persistent store, every
route and its gate, the credential systems, what leaves the project boundary
to a third-party processor, the read-only live checks that re-verify all of
it, and the risks the maintainer has accepted or still has to decide. Dated
findings, run snapshots and the history of how each control landed live in
the journal (sprint 23, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`); this doc states what is true now.

The logging rule itself (what may and may not be written to a log line)
lives in [hipaa-pii-policy.md](hipaa-pii-policy.md); the audit-trail
invariant in [confirmation-and-audit.md](confirmation-and-audit.md); the
client-owns-state invariant in
[stateless-architecture.md](stateless-architecture.md). This doc points at
them rather than restating them.

## Threat model

Who "unauthorised" means, and the question each actor puts to the design.

| # | Actor | Reaches | The control that answers |
|---|-------|---------|--------------------------|
| T1 | Anonymous internet caller | Both Cloud Run services (`--allow-unauthenticated`), the five Hosting sites, Firestore through the public web config, the kit bucket, the unauthenticated doors (`POST /api/links/open`, `POST /api/disclaimer-acceptance`, `POST /api/signup/check`, `/health`, `/version`) | The route/gate matrix below; the uniform `404 {"detail":"Not found"}` on every oracle-sensitive door; Firestore rules that deny every client read except a user's own profile; the WebSocket's pre-accept Origin check and first-frame credential (C2, PR #834 -- in PR; until it merges the socket takes `?token=` on the URL and checks no Origin) |
| T2 | Authenticated wrong-tier user | Firm A staff vs firm B data; employee vs manager; a client-link holder vs staff routes; editor vs admin; a claimless Firebase token | Every tenant boundary is decided from the VERIFIED token's claims (`firm_id`, `firm_role`, `app_admin`, the link's `firm_id`/`kit_id`), never from a body or handshake field; pinned per (actor x route) by the two access-matrix tests |
| T3 | Operator or insider with GCP console or log access | Cloud Logging (app streams and Cloud Run's request log), Firestore, BigQuery, GCS, Cloud Run revision env, Cloud Build logs | No credential or field value reaches any log sink (the static guards in hipaa-pii-policy.md; the live sweep below); every store's key set is pinned and inventoried; secrets ride Secret Manager bindings, never env values |
| T4 | Third-party processors | Vertex AI (Gemini Live and text models), Cloud Text-to-Speech, Firebase Auth, the Google-hosted stores | The processor table below; Vertex-only enforced at startup on `K_SERVICE`; no analytics, error-reporting, email or payment SDK exists in either backend |
| T5 | Supply chain | pip and npm dependencies, the base image, CDN scripts | Digest-pinned base image, non-root container, runtime-only requirements, the informational CI security job (pip-audit, npm audit x3, detect-secrets, bandit, semgrep), Dependabot; the one remaining third-party executable load (the VAD model and ONNX runtime from jsdelivr) is tracked as `polyglot-pdf-18o7c` |
| T6 | The browser on a shared device | `sessionStorage`, the magic-link URL, the console, print flows | Field values never reach the console (source guard + production strip); the client's answers and link credential are wiped automatically on completion, after an idle grace, and on logout; the link fragment is stripped after redemption |

Out of scope by design, so nobody chases it: magic-link DELIVERY (the firm
copies the URL into its own channel; no client identifier exists in the
mint request); the legal retention answer (bd `pol2` and
`polyglot-pdf-t5v83` hold the question); rate-limiting infrastructure (a
cost decision, see "Decisions handed to the maintainer"); a third-party
penetration test.

## Data inventory

Every persistent store the deployed system writes. A store named in
backticks is one `scripts/audit/inventory_stores.py` iterates (sampled
keys and types, never a value); `tests/test_security_posture_doc.py` diffs
that set against the script mechanically, in both directions. The rows
without backticks are stores the script cannot read; each names the check
that covers it instead.

| Store | Key set | PII class | Retention | Readers | Guard |
|-------|---------|-----------|-----------|---------|-------|
| `confirmation_events` (Firestore) | timestamp, event, form_id, kit_id, edition_date, firm_id, form_session_id, field_id, field_name, confirmation_method, language, timestamp_unix_ms, script_version, user_agent, total_fields_confirmed, completion_status, expire_at, section_id, link_jti, employee_id | metadata only, never a value (the legal evidence trail) | no TTL; decision filed (`t5v83`) | Admin SDK only; explicit client deny in `firestore.rules` | `test_confirmation_firestore_sink.py`, `test_firestore_rules_text.py` |
| `authorized_emails` (Firestore) | email (unmanaged; no code writer in the repo) | staff emails | unmanaged | Admin SDK only (full client deny; the sign-up check is `POST /api/signup/check`) | `test_firestore_rules_text.py`, `test_signup_check_route.py` |
| `firms` (Firestore) | name, contact_email, allowed_kits, status, kind, plan, balance_credits, balance_updated_at, created_at, updated_at | firm profile, no client PII | indefinite | Admin SDK only | `test_audit_log_shapes.py::FIRM_DOC_ALLOWED_KEYS` |
| `firms/*/ledger` (Firestore) | actor, actor_email, amount, balance_after, channel, firm_kind, kit_id, link_jti, period, reason (bounded, 500 chars), ts, type, usd_amount | operator identity (staff email) + bounded free text; no client PII | indefinite (financial record) | Admin SDK only | `test_credit_ledger.py::ENTRY_FIELDS`; `REASON_MAX_LENGTH` at every writer |
| `firms/*/usage` (Firestore) | by_employee, by_kit, by_language, channel, connections_ended, cost_usd_total, kind, links_completed, links_opened, sessions_completed (a monthly rollup; the maps are keyed by id/kit/language) | none | indefinite | Admin SDK only | the script's allowlist; reader allowlist in `usage_routes.py` |
| `kits/*/usage` (Firestore) | by_firm, channel, connections_ended, cost_usd_total, kind, sessions_completed (a monthly rollup per kit) | none | indefinite | Admin SDK only | the script's allowlist |
| `firms/*/link_usage` (Firestore) | minted, updated_at (a monthly counter) | none | indefinite | Admin SDK only | the script's allowlist |
| `links` (Firestore) | cap_usd, credit_cost, employee_email, employee_id, expire_at, firm_id, jti, kit_id, minted_at, open_deadline, opened_at, revoked_at, revoked_by, status | the minting employee's staff email; no client PII (a link never names its client) | TTL via `expire_at` | Admin SDK only | `test_store_shapes.py` |
| `links_staging` (Firestore) | as `links` | as `links` | as `links` | Admin SDK only | `test_store_shapes.py` |
| `link_redemptions` (Firestore) | completed_at, firm_id, jti, kit_id, opened_at, spend_updated_at, spend_usd, turns | pseudonymous join key | no TTL; decision filed (`t5v83`) | Admin SDK only | `test_store_shapes.py` |
| `link_redemptions_staging` (Firestore) | as `link_redemptions` | as `link_redemptions` | as `link_redemptions` | Admin SDK only | `test_store_shapes.py` |
| `admin_audit_log` (Firestore) | actor_uid, actor_email, action, target, before, after, channel, request_id, state, ts, committed_ts, error | operator identity + config/commercial metadata; `target` may carry a staff email | indefinite (audit trail) | Admin SDK only | `test_audit_log.py::ROW_FIELDS`, `test_audit_log_shapes.py` (per-route `before`/`after`, self-enumerating) |
| `app_config` (Firestore) | keys validated against `RUNTIME_CONFIG_KEYS` | operational flags | indefinite | Admin SDK only | `runtime_config.py` known/unknown split |
| `alerts` (Firestore) | firm_id, kind, level, ts, context, expire_at, acknowledged_by, acknowledged_at, emailed_at | operational | TTL via `expire_at` | Admin SDK only | reported live by the script |
| `kits` (Firestore) | commercial/display metadata, no closed schema | none | indefinite | Admin SDK only | report-only in the script |
| `bucket` (GCS form-kits bucket) | `<kit>/`, `_archive/`, `_drafts/`, `acroform.json` | no client PII (schemas and their samples) | indefinite | bucket IAM; the backend SA reads it (project-wide `storage.objectViewer`, see accepted risks) | live listing for unexpected objects |
| `bigquery:cost_by_firm_month` (view) | counts and costs per firm and month | none by shape | no expiration; decision filed (`t5v83`) | dataset ACL (the admin SA is a dataset-scoped reader) | `test_usage_event_schema.py` (no free-text slot in the envelope); live schema read -- the view is not yet deployed on the project (ABSENT in the 2026-09-15 run; only `hosting_cost_by_service_month` exists) |
| `bigquery:cost_by_kit_month` (view) | as above per kit | none by shape | as above | as above | as above; not yet deployed |
| `bigquery:cost_by_employee_month` (view) | as above per employee id | none by shape | as above | as above | as above; not yet deployed |
| `bigquery:income_month` (view) | credit income per month | none by shape | as above | as above | as above; not yet deployed |
| `bigquery:hosting_cost_by_service_month` (view) | month, gcp_service, resource_name | none | as above | as above | swept by `log_pii_sweep.py` (three string columns) |
| Firebase Auth (staff accounts) | uid, email, display name, photo URL, custom claims (`firm_id`, `firm_role`, `app_admin`, editor role) | staff identity | deleted-user handling undocumented (`t5v83`) | Firebase Auth Admin SDK; the operator identity currently lacks Identity Toolkit read, so `infra_posture.sh` reports its settings N/A | `user_admin.py` claims allowlist; checked by `infra_posture.sh` |
| Cloud Logging (app stdout/stderr + `run.googleapis.com/requests`, three services) | log lines | governed by hipaa-pii-policy.md; must carry no credential or field value | 30-day bucket retention (measured); a decision on the number is filed (`t5v83`) | log-viewer IAM | static: `test_no_pii_logging.py` and the sink pins listed in hipaa-pii-policy.md; live: `log_pii_sweep.py` |
| Container disk (`backend/logs/`, `logs/confirmations/`, the fill-pdf temp file, the editor's `extract_<kit>` temp dir) | transient | uploaded PDF bytes in the temp files | ephemeral, cleaned in `finally`; an OOM-killed subprocess can leave residue on a warm instance | container filesystem | design note; the two loggers are no-ops with `K_SERVICE` set |
| Second copies (Firestore PITR/exports, Firebase Auth bulk export, Cloud Build log content) | same class as the source | same | undocumented | project IAM | `infra_posture.sh` (PITR/backup schedules, export buckets, Cloud Build log content as counts) |
| Repo as a store (`scripts/pull-form-kits.sh` output, `scripts/spikes/*`, `.beads/*.jsonl`) | tracked files and their history | possibly schema or sample data, never client PII | git history (indefinite) | repo access | the detect-secrets baseline and the history sweep (F1): no live secret or private key in any reachable blob |

## Route and gate matrix

Derived from the live route tables by
`backend/tests/integration/test_access_matrix.py` (29 tests, HTTP and
WebSocket) and `admin_backend/tests/unit/test_access_matrix.py` (15
tests): every registered route must be gated by a recognised dependency,
listed as deliberately ungated, or belong to the editor surface, or the
suite fails; nine actors (anonymous, firm-A employee, firm-A manager,
firm-B manager, client link for firm A, client link for firm B, editor,
claimless Firebase token, app admin) are asserted per route.

**Public backend** (`backend/main.py`):

| Route | Gate | What a wrong caller gets |
|-------|------|--------------------------|
| `GET /api/form-kits` | `require_signin` | private kits filtered per firm; claimless, editor and client-link callers see the public set |
| `GET /api/form-kits/{kit_id}/schema` | `require_signin` + publish + visibility gates | 404 for a private kit outside the caller's firm |
| `GET /api/form-kits/{kit_id}/pdf` | none for PUBLIC kits (deliberate); inline optional-token check for private kits | 404 unless the owning firm or its client link |
| `GET /api/form-kits/{kit_id}/archive[/{marker}/schema]` | `require_auth` | 403 claimless/editor; 404 other firm |
| `POST /api/form-kits/{kit_id}/retire` | `require_auth` + manager + owner + private | 404 employee / other firm / claimless |
| `POST /api/links/mint` | `require_auth` | 403 client link (no uid), claimless, editor |
| `POST /api/links/open` | none; the token IS the credential; per-address rate limit (`o2fub`) | uniform 404 on any refusal, including over budget |
| `POST /api/signup/check` | none; answers 204 or the uniform 404; per-address rate limit | never lists; over budget is the same 404; the handler logs the address length only and the limiter's refusal line logs door, bucket, budget and hop count only |
| `POST /api/fill-pdf`, `POST /api/resume-form` | `require_auth`; byte-accurate body caps; parse timeout | 403 claimless/editor; 413 over cap; 408 on a hung parse |
| `POST /api/tts/notice` | `require_auth` (free door, no redemption) | 403 |
| `POST /api/tts/spellback`, `POST /api/tts/intro` | `require_paid_client_work` (redeems the client link) | 403 / 404 |
| `POST /api/disclaimer-acceptance` | none (durable metadata write; bounded timestamp; value-free 422); per-address rate limit | 422 out of bounds; 429 over budget |
| `POST /dev/console-log` | `backend/.env.DEV` marker AND not `K_SERVICE` | 404 on Cloud Run |
| `WS /ws/fill` | credential verified before any Gemini session; link: kit match. **With C2 (PR #834, in PR):** browser Origin allowlist before accept, the credential in the first frame (`token`), staff: publish + visibility gates. Until it merges the credential is the `?token=` query parameter and a staff token's `kit_id` is not scoped to its firm (the C1 finding) | 1008 before any session; after C2, `?token=` is honoured one more deploy with a warning (`0j8e5`) |
| `WS /ws/echo`, `WS /ws/audio` | `backend/.env.DEV` marker (the image never carries it); with C2 (in PR) also not `K_SERVICE` | 1008 |
| `/api/editor/*` | `require_editor_actor` (the schema editor's own credential system) | 401/403 |
| `GET /health`, `GET /version` | none | status and the two Firestore probes only; no model id, rate, limit or flag |

**Admin service** (`admin_backend/main.py`):

| Gate | Routes |
|------|--------|
| `require_app_admin` | `GET /admin/whoami`; `GET`+`PUT /admin/config/{channel}`; `GET /admin/audit`; `GET`+`POST /admin/firms`; `GET /admin/firms/{firm_id}` + `PATCH` status / allowed_kits / kind; `POST .../credits/grant`, `.../credits/adjust` (reason bounded at 500 chars); `/admin/kits*`; `GET /admin/kits/{kit_id}/usage`; `GET /admin/reports/*`; `/admin/alerts*` |
| `require_app_admin_or_owning_manager` | `/admin/users*` (`POST`, `GET`, `PATCH` x2); `POST /admin/links/{jti}/revoke`; `GET /admin/firms/{firm_id}/usage` |
| `require_app_admin_or_owning_manager_or_employee` | `GET /admin/firms/{firm_id}/links` |
| `require_google_oidc` | `POST /admin/links/sweep-expired` (Cloud Scheduler) |
| none | `GET /health` (status, service, app_module), `GET /version` |

Firestore from the browser: every collection is a full client deny except
`users/{uid}`, which its owner may read and write (shape validation of that
write is `polyglot-pdf-wnkky`); `test_firestore_rules_text.py` pins the deny
list against the rules file in both directions, and `infra_posture.sh`
confirms the ACTIVE ruleset equals the repo file by hash.

## Credential systems

| Credential | Who | Issued by | Verified where | Notes |
|------------|-----|-----------|----------------|-------|
| Firebase ID token with custom claims (`firm_id`, `firm_role`, `app_admin`) | staff, firm managers, app admins | Firebase Auth (Google sign-in or email/password behind the server-side allowlist check) | `backend/services/auth.py::verify_token` (signature and expiry; NOT `check_revoked`, which the runtime identity is deliberately not permitted to call) and the admin service's gates | Expires within an hour; carried in the `Authorization` header over HTTP and, with C2 (PR #834, in PR), in the first WebSocket frame (today: the `?token=` query parameter) |
| Client magic-link token | a firm's client | `backend/services/link_tokens.py` (HMAC-signed; 128-bit CSPRNG `jti`; `exp` is the only time check) with `LINK_TOKEN_SECRET` from Secret Manager | `POST /api/links/open` (uniform 404), the paid-work gate, the WebSocket (first frame with C2, in PR; `?token=` today) | No key-version claim, so rotation is an all-at-once cutover (`polyglot-pdf-jx5u9`); the reopen check is not transactional (`mzhrp`, P3) |
| Editor actor credential | schema-editor users | the editor's own auth (see `docs/components/auth.md`) | `require_editor_actor` on `/api/editor/*` | Separate system; never grants a voice-app or admin route |
| Google OIDC token | Cloud Scheduler | Google | `require_google_oidc` on the expiry sweep | Audience-checked |
| Runtime service identities | `polyglot-backend-sa`, the admin SA, `polyglot-cloudbuild-sa` | IAM | pinned lists in `test_deployed_iam_envelope.py`, `test_admin_sa_iam_envelope.py`, `setup-cloud-build.sh`; live-compared by `infra_posture.sh` | The Cloud Build identity is not yet provisioned on the project (see decisions) |

No password, API key or token is handled in plain text by the code: the
public Firebase web API key is the one tracked "key" (public by design), and
secrets reach Cloud Run only as Secret Manager bindings (`infra_posture.sh`
reports any secret-shaped env value by NAME).

## Third-party processors

What leaves the project boundary, to whom, and under what terms. The
"live setting" column is what `infra_posture.sh` could read on
2026-09-23 (sprint 23's closing run, after the demo deploy); where it says
console-only, the maintainer reads it in the Cloud Console and the answer
is recorded in the journal.

| Processor | Data sent | Governing terms | Retention / use | Live setting |
|-----------|-----------|-----------------|-----------------|--------------|
| Vertex AI, Gemini Live (`gemini-live-2.5-flash-native-audio`; premium tier per `ai-models.md`) | the client's spoken audio; the system instruction including the current field values (`current_values`) and the form schema text with translations; tool calls and results (field ids and values); the model's audio back | Google Cloud Platform terms with the Cloud Data Processing Addendum (enterprise; customer data is not used to train models) -- NOT AI Studio's consumer terms: `VERTEXAI=true` is enforced at startup on `K_SERVICE` | a Live session holds context for the session only; Vertex may log prompts and responses for abuse monitoring for a limited period unless the project's opt-out is granted | NOT opted out: no toggle is exposed for this project, and Google REFUSED the abuse-monitoring exemption request on 2026-09-23 (most likely because the company has no public website yet). Until a re-application succeeds, Vertex may retain prompts and responses for abuse monitoring for its stated period -- client audio and field values included |
| Vertex AI, text models (`generate_content`: the secretary, validator and option translation) | schema text and field values in the prompt; the secretary's catalog | as above | as above | as above |
| Cloud Text-to-Speech | the spellback field VALUE as text (`spellback_tts.py`), the intro and notice phrases | GCP terms + the Cloud Data Processing Addendum | Google documents TTS request data as not retained beyond serving and not used for improvement; no per-project data-use setting exists to verify (`infra_posture.sh` N/A by design) -- confirm in the contract review | none exists |
| Firebase Auth | staff email, display name, Google profile photo URL (stored, never shown), custom claims | Firebase terms (the project's Firebase services sit under the same Google Cloud account) | until the account is deleted; deleted-user handling undocumented (`t5v83`) | authorized domains, email-enumeration protection, providers and password policy: the script reports N/A because its request carries no quota-project header (`polyglot-pdf-kz7rv`); the same read done in-process on 2026-09-23 succeeded (11 authorized domains), so the settings are readable and the script is what needs fixing |
| Firestore, GCS, BigQuery, Cloud Logging (Google-hosted stores) | the inventory above | GCP terms + the Cloud Data Processing Addendum | per the inventory's retention column; decisions filed (`t5v83`) | Firestore rules byte-equal the repo; bucket has no `allUsers` binding; BigQuery dataset ACL read; Logging retention 30 days |
| jsdelivr CDN (browser) | nothing but the request itself: the voice overlay loads the VAD model, its audio worklet and the ONNX runtime from there | CDN terms | not applicable | the one third-party executable load left in the browser; self-hosting is `polyglot-pdf-18o7c` and the CSP enforcement prerequisite |

Not present, verified by reading both backends and all three bundles:
Google Fonts (self-hosted since E2), analytics, error reporting, email,
payment SDKs, or any other egress.

## Live checks (read-only, redacted)

Three scripts re-verify the deployed project under the operator's own
application-default credentials, `--project` required, refusing the dead
project, printing counts, key names, types and ids and never a value:

| Script | What it proves | Last clean run |
|--------|----------------|----------------|
| `scripts/audit/inventory_stores.py --project <id>` | every sampled document in every store sits inside its pinned key allowlist; the bucket holds only kit objects; the telemetry views' schemas | 2026-09-15 (journal: `2026-09-15-bd-uaxt5-data-at-rest-inventory.md`) |
| `scripts/audit/log_pii_sweep.py --project <id> --retention-days 30` | zero credential, JWT, A-number, SSN, email, phone or DOB hits across the three services' app streams and request logs and the BigQuery views, in-process (spawns nothing) | 2026-09-23 (closing run): the BigQuery views and both backends' app streams clean of client data; the pre-fix request-log residue unchanged (newest 2026-09-14T19:29Z), aging out by 2026-10-14; 46 admin-service lines carry the OIDC caller's email (`actor_email`/`caller_email` on three log calls; service-account or staff addresses, not client data) -- `polyglot-pdf-4ffib` (journal: `2026-09-23-bd-uijam-sprint-23-close.md`) |
| `scripts/audit/infra_posture.sh --project <id>` | 79 checks: IAM, service-account envelopes, Cloud Run env and flags, secrets, bucket, active Firestore rules vs repo, TTL/PITR, Logging retention and exclusions, BigQuery ACL, Firebase Auth, Hosting headers, container scanning, Cloud Build log content, the T4 settings -- each PASS, FAIL or `N/A: <reason>` | 2026-09-23, the closing run after the demo deploy of dev `b91fad5bb`: 66 PASS, 2 FAIL, 11 N/A (journal: `2026-09-23-bd-uijam-sprint-23-close.md`). The FAILs: the two human Owners (accepted, below) and the editor Hosting site's CSP and Referrer-Policy headers, which land on its next `deploy-editor.sh` run (the editor site deploys separately from the demo channel). The N/A: seven are the script's own Firebase Auth and BigQuery command paths (`polyglot-pdf-kz7rv`); four are settings with no readable form (per-user MFA, Auth export, the Vertex org policy, TTS data use) |

Static guards that run in CI on every PR: `test_no_pii_logging.py` (the
sink shapes listed in hipaa-pii-policy.md), the two access matrices, the
rules-text pin, `test_hosting_headers.py`, `test_deploy_channel_parity.py`,
the IAM envelope tests, `test_dockerfile_app_module.py`, the store-shape
pins, and the informational `security` job (pip-audit, npm audit x3,
detect-secrets, bandit, semgrep).

## Known accepted risks

Recorded here so they are not rediscovered as findings.

- **88 to 89 request-log rows carrying a `?token=` credential from before the
  fix** (13 staging; 75 or 76 demo -- the B2 entry's summary and its itemised
  post-fix list disagree by one; 2026-08-17 to 2026-09-14). Accepted by the
  maintainer on 2026-09-14 (option C): every link record in the window was a
  budget-exhausted stub with no minted link, Firebase ID tokens expire
  within an hour, and the rows age out with the 30-day bucket retention (the
  last on 2026-10-14).
- **`?token=` on the WebSocket URL** is the live credential transport until
  C2 (PR #834) ships, then honoured for one more deploy with a deprecation
  warning per use; the request-log exclusion
  filter `ws-token-in-url` covers those rows meanwhile. Removal is
  `polyglot-pdf-0j8e5`.
- **The CSP ships report-only** on all five sites until the staging soak
  shows no violation from the app's own traffic, and enforcement waits on
  self-hosting the VAD assets (`18o7c`), because the ONNX runtime's glue
  needs `'unsafe-eval'` that the policy does not grant.
- **The backend SA holds `storage.objectViewer` project-wide** rather than
  bucket-scoped (PF-12). No other bucket exists on the project; tightening
  it is a scar-7 ritual (name the call, name the permission, check the live
  policy) and is not scheduled.
- **The local kit store is ungated by design** (`enforce_complete_on_public_reads`
  is false locally, true on GCS), so local-harness proofs never exercise the
  publish gate.
- **A hung or OOM-killed extraction subprocess can leave uploaded PDF bytes
  on a warm instance's disk** until the instance is recycled; the parse
  itself is timed out and the temp files are cleaned in `finally`.
- **Rate limiting is a per-instance limiter plus an instance ceiling**, not a
  network-edge control: the buckets reset on autoscale and a distributed
  caller spreads around them. The keys are the tail of the forwarded chain
  (the browser hop Hosting appends -- verified on staging 2026-09-23 by a
  hosted burst refused from the 31st call with a two-hop chain on every
  refusal; the connecting address as the backstop),
  so a forged `X-Forwarded-For` prefix buys nothing; Hosting's egress address
  changes per request, so the connection bucket only ever bites a direct
  caller. Cloud Armor is deferred
  until abuse is observed (`config-deployment.md`, "Rate limiting on the
  unauthenticated doors").
- **Two project Owners are the same person's two accounts** (a sole
  operator, 2026-09-17). The posture check keeps reporting it so a third
  Owner is noticed.
- **Vertex AI may retain prompts and responses for abuse monitoring** (client
  audio and field values included) because the exemption request was refused
  on 2026-09-23; accepted until a re-application after the website launches.
- **The user's own profile write (`users/{uid}`) has no shape validation**
  (`wnkky`, P3): self-corruption only.

## Decisions handed to the maintainer

Each is a product, cost or legal call, not an engineering one. A row marked
DECIDED, DONE, DEFERRED, ACCEPTED or FIXED is closed (the maintainer's
2026-09-17 answers); the others are open. The answer is recorded on the
named bead or in the journal.

| Decision | Options | Where |
|----------|---------|-------|
| Rate limiting on the unauthenticated doors (PF-5, P1) | DECIDED 2026-09-17 and SHIPPED: the per-instance limiter on the three write doors plus `--max-instances` on both services; Cloud Armor + load balancer deferred until abuse is observed | `polyglot-pdf-o2fub` |
| Data retention (`confirmation_events` and `link_redemptions` TTL, Logging bucket retention, BigQuery expiration, deleted Firebase users) | per store | `polyglot-pdf-t5v83`, with `pol2`'s legal input |
| The CI `security` job: informational or required | keep non-blocking (the workflow's doctrine) or make it a required check | `polyglot-pdf-ikdnd` notes |
| The voice app's Firebase persistence mode | `browserSessionPersistence` for the voice app only (recommended), local for editor/admin | `polyglot-pdf-8v8i7` notes |
| Bucket public-access prevention | DONE 2026-09-17: `enforced` on `gs://polyglot-demo-aa709-form-kits` | `polyglot-pdf-m1dlv` |
| Artifact Registry container scanning | DONE 2026-09-17: `containerscanning.googleapis.com` enabled; `infra_posture.sh` reads the findings from the next pushed image on | `polyglot-pdf-m1dlv` |
| Provision `polyglot-cloudbuild-sa` | DEFERRED 2026-09-17: the identity only matters once deploys move to Cloud Build; run `setup-cloud-build.sh` then | `polyglot-pdf-m1dlv` |
| Two human accounts hold project Owner | ACCEPTED 2026-09-17: both are the sole operator's own accounts (see accepted risks) | `polyglot-pdf-m1dlv` |
| Vertex AI abuse-monitoring opt-out | REFUSED by Google 2026-09-23 (requested 2026-09-17; the likely cause is the missing company website, which is now a prerequisite on the maintainer's list); RE-APPLY once the website is live -- until then the retention in the processor table stands as an accepted, dated risk | the processor table above |
| Grant the operator identity Identity Toolkit read (or read the Firebase Auth settings in the console): authorized domains, email-enumeration protection, providers, password policy | a live IAM change | `polyglot-pdf-m1dlv` |
| Flip the CSP from report-only to enforcing after the staging soak and `18o7c` | a `firebase.json` change through review | `polyglot-pdf-j29z1` notes |
| The operator free-text `reason` on `set_firm_kind` reached the logs (`e8wzz`, the PF-9 class) | FIXED 2026-09-17: bounded at the model, dropped from the log line; the whole set (both backends' routes) pinned at zero | `polyglot-pdf-e8wzz` |
