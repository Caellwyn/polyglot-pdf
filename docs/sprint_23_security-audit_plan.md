# Sprint 23 -- Security + data-leak audit

**Epic:** `polyglot-pdf-uijam`
**Approved:** 2026-09-09 (plan-mode review; one maintainer review round folded in the same day)
**Beads filed:** 2026-09-11 -- B0 `6rj0j`, A `uaxt5`, B1a `wfgjz`, B1b `2kbo0`, B2 `v8l6m`, C1 `fr20a`, C2 `bwevj`, C3 `vcjgs`, C4 `6088m`, D `m1dlv`, E1 `8v8i7`, E2 `j29z1`, F1 `ikdnd`, F2 `cwiip`, G `vzrbc` (all `polyglot-pdf-` prefixed; label `security-audit`)

---

*Planning session 2026-09-09, branch `claude/security-audit-plan-93d1d3`.
Three read-only exploration passes (backend sinks, auth/deploy config,
browser apps) plus one adversarial critique of the draft plan produced the
pre-findings below; the maintainer then verified every pre-finding against
the tree and corrected the sequencing (the P0 now has a wave-0 bead), the
bead split, and several stale references. Between approval and filing,
`polyglot-pdf-e4dt8` (the PII-safe exception shape, close-code counters and
monitoring setup) merged as PR #774, so the log-sink beads no longer wait on
it -- noted where it matters.*

## Context

polyglot-pdf handles immigration-intake PII/PHI (names, A-numbers, DOBs,
addresses, and the user's spoken audio) for pilot law firms. The architecture
is deliberately minimal on data-at-rest (client-owns-state, stateless
backend, metadata-only audit trail), but the surface has grown fast in the
last month: a second privileged Cloud Run service (`admin_backend/`), four
credential systems, client magic links, a credit ledger, a BigQuery telemetry
sink, and three browser apps. Past incidents show the policy and the code
drift apart between audits (bd hjo: 13 live PII log sites; bd z2is: an
unauthenticated fill-pdf route + a logged client IP; bd knmp: an auth bypass
a stray env var could enable in prod).

The maintainer wants the codebase AND the deployed environments audited for
(1) PII being recorded anywhere on the deployed app and (2) paths by which an
unauthorized party could extract data. The outcome is a findings report,
mechanical guards that keep each finding fixed, and beads for remediation --
not a one-off checklist.

**Shape of the deliverable:** one epic with MECE child beads, per
`docs/doctrine/planning.md`. Each investigation bead leaves behind a
re-runnable script or a set-derived test, so the audit repeats for free. A
new tier-2 doc, `docs/standards/security-posture.md`, becomes the current-
state home for the threat model, data inventory, route/gate matrix, the
third-party processor table and the live-check runbook; dated findings go to
the journal.

## Decisions (maintainer, 2026-09-09 -- do not relitigate)

1. **Live environment IS in scope.** Read-only gcloud/bq/Firestore/Logging
   queries against `polyglot-demo-aa709` under the operator's ADC, with
   redacted output (counts, keys, types, ids -- never a value). Any live
   CHANGE (the interim log exclusion, a secret rotation, a log deletion)
   remains a separate per-instance ask.
2. **P0/P1 are fixed in-epic; P2/P3 are filed as beads.**
3. **C2 (move the WS credential out of the URL) is APPROVED** as part of
   this epic, with a one-deploy compatibility window for `?token=`.

## Threat model (who is "unauthorized")

| # | Actor | Reaches | Question the audit answers |
|---|-------|---------|----------------------------|
| T1 | Anonymous internet caller | Both Cloud Run services (`--allow-unauthenticated`), 5 Hosting sites, Firestore via the public web config, the GCS bucket, `/api/links/open`, `/api/disclaimer-acceptance` | Which routes/collections/objects answer without a credential, and what do they reveal (data, existence oracles, cost)? |
| T2 | Authenticated wrong-tier user | firm A staff vs firm B data; employee vs manager; client-link holder vs staff routes; editor vs author; app admin scope | Is every tenant boundary enforced server-side from the VERIFIED token, never from a body/handshake field? |
| T3 | Operator / insider with GCP console or log access | Cloud Logging (incl. Cloud Run request logs), Firestore, BigQuery, GCS, Cloud Run revision env, Cloud Build | What PII or live credentials are at rest in each store, for how long, and who holds viewer roles? |
| T4 | Third-party processors | Gemini (Vertex vs AI Studio), Cloud TTS, Firebase Auth, any analytics/error SDK | What user data leaves the project boundary, under which terms and retention, and is the Vertex-only guard airtight? Owned by G (the processor table) + D (the live settings). |
| T5 | Supply chain | pip/npm deps, base image, CDN scripts in bundles | Known-vulnerable or unpinned components? |
| T6 | The browser / a shared device | sessionStorage, magic-link URL in email/SMS/history, console, print flows | Does a client's data outlive their session on a shared law-office tablet? |

## What planning already established (so execution does not redo it)

### Controls that exist and should be reused, not rebuilt

- PII logging guard: `backend/tests/test_no_pii_logging.py` (6 guarded files +
  an anywhere-sweep; detects `_log.*` sensitive kwargs, `print()` f-strings,
  and -- since e4dt8 -- an exception-message sentinel through the production
  processor).
- Exception shape: `backend/utils/logging.py`'s PII-safe processor (type +
  frames, never the message), `backend/tests/unit/test_error_shape.py` (incl.
  the AST enumeration of every `_log.exception` / `exc_info` site), and the
  WS close-code events `backend/tests/unit/test_ws_close_events.py` (all
  e4dt8, PR #774).
- Store-shape allowlists: `backend/tests/unit/test_confirmation_firestore_sink.py`
  (exact `confirmation_events` keys), `backend/tests/unit/test_disclaimer_acceptance_route.py`
  (log kwargs), `backend/tests/test_usage_event_schema.py` (no free-text slot).
- Auth/route set pins: `backend/tests/unit/test_http_route_auth.py`,
  `test_client_link_http_auth.py`, `admin_backend/tests/unit/test_admin_route_auth.py`,
  `test_require_firm_manager.py`, `test_link_tokens.py`, `test_link_redemptions.py`,
  `test_auth_bypass_guard.py`.
- Infra pins: `backend/tests/unit/test_deployed_iam_envelope.py`,
  `admin_backend/tests/unit/test_admin_sa_iam_envelope.py`,
  `backend/tests/unit/test_firestore_rules_text.py` (`ADMIN_SDK_ONLY_COLLECTIONS`),
  `tests/test_deploy_reachability_gate.py`, `backend/tests/unit/test_deploy_channel_isolation.py`,
  `tests/test_deploy_channel_parity.py`, `tests/test_dockerfile_app_module.py`,
  `tests/test_setup_monitoring_script.py`.
- Browser: `isLocalhostOrigin()` hard-gates every `__VFF_*` security flag;
  `devConsoleCapture` only posts to a localhost backend; `sessionCredential.ts`
  never caches a Firebase token itself; `ClientLinkEntry.tsx:129` strips the
  fragment after redemption; the three manual Clear-form buttons already
  call `SchemaFormStateManager.clear()` + `clearOnboardingState()` -- E1
  reuses that path.
- Design properties confirmed clean: no filled or uploaded PDF ever reaches GCS
  (fill-pdf is temp-and-delete, resume-form is in-memory); spellback TTS has no
  cache; Vertex-only is enforced at startup on `K_SERVICE`; all four dev-bypass
  sites fail closed on `K_SERVICE`; every `kit_id`/filename/marker is
  sanitized before a path join; subprocess extraction uses an argv list; no
  Stripe/Sentry/email/analytics egress exists in the backend; secrets ride
  `--set-secrets`, never `--set-env-vars`; the only tracked "key" is the
  public Firebase web API key; no XSS sink in any of the three apps; pdf.js
  worker bundled locally; blob URLs revoked; only public `VITE_*` values
  reach a bundle.

### Pre-findings (verified against the tree by the maintainer 2026-09-09; dispositioned by the beads)

| ID | Sev | Finding | Where |
|----|-----|---------|-------|
| PF-1 | **P0** | The WS credential (Firebase ID token or magic-link token) rides `?token=` on `/ws/fill`. uvicorn access logging is deliberately kept at INFO (`backend/utils/logging.py`, `uvicorn.access` set to INFO; no `--no-access-log` on the `Dockerfile` CMD), AND Cloud Run's own request log records `httpRequest.requestUrl` regardless of uvicorn. A live, replayable credential lands in Cloud Logging for every voice session, readable by anyone with log-viewer access, for the retention period. **Link tokens minted inside the retention window are in the request log NOW** (48 h default open window, up to 14 days, plus the completion window), so stopping the write is not enough -- they must be invalidated or the log deleted. No existing guard sees this sink. | `backend/routes/websocket_routes.py` (`token: str = Query(...)`), `backend/utils/logging.py`, `Dockerfile` |
| PF-2 | P1 | `error=str(exc)`-shaped kwargs appear on ~185 lines across both backends and `error` is not a guarded kwarg; a plain `_log.warning(..., error=str(exc))` carries the message past e4dt8's exception processor. Clearest instance: `validation_handler.py:138-142`, the handler that validates user-spoken field updates. (The three ungated `_log.exception` sites in `live_ai_gemini.py` and the sentinel test are CLOSED by e4dt8.) | `backend/services/validation_handler.py:138` + the enumerated set |
| PF-3 | P1 | No custom `RequestValidationError` handler on either FastAPI app: a 422 echoes the offending request-body values back to the caller (e.g. an over-long field value on `/api/fill-pdf`). Response-side, not a log leak, but outside the policy's scope today. `debug=` is unset (default False) on both apps -- pin it. | `backend/main.py`, `admin_backend/main.py` |
| PF-4 | P1 | `firebase.json` sets NO response headers on any of the 5 Hosting sites: no CSP, HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy. | `firebase.json` |
| PF-5 | P1 | No rate limiting anywhere. `POST /api/links/open` (unauthenticated) and `POST /api/disclaimer-acceptance` (unauthenticated durable write) are bounded only by token entropy / field caps; `/health` and `/version` are free fingerprinting targets. Any real limiter is new infrastructure or a cost decision (maintainer). | `backend/routes/link_routes.py`, `disclaimer_routes.py` |
| PF-6 | P1 | `authorized_emails` allows an unauthenticated **list** (`allow read: if true`), so anyone with the public web config can enumerate every allowlisted staff email. A client-side `get` by doc id still leaves a per-email oracle; a server-side check behind the uniform 404 is cleaner. The separate registered-user oracle in Firebase sign-up itself is D's email-enumeration-protection check. | `firestore.rules:16-19`, `frontend/src/contexts/AuthContext.tsx:119` |
| PF-7 | P2 | No dependency, secret, or SAST scanning in CI; `.github/` has one informational test workflow. `backend/requirements.txt` ships test tooling into the production image and pins `uvicorn==0.24.0` (2023), `python-multipart==0.0.9` (check CVE-2024-53981, fixed in 0.0.18), `PyMuPDF==1.24.14`. | `.github/workflows/ci.yml`, `backend/requirements.txt`, `Dockerfile` |
| PF-8 | P2 | `confirmation_events` (the legal evidence trail) has no explicit deny block in `firestore.rules` and is absent from `ADMIN_SDK_ONLY_COLLECTIONS`; it is safe only by the implicit default deny. It also has no TTL and no documented retention decision -- and no retention bead exists yet (bd `pol2` is the attorney-contract bead; it only NOTES the "what must we retain" question). | `firestore.rules`, `test_firestore_rules_text.py`, `scripts/setup-firestore-ttl.sh` |
| PF-9 | P1 | Operator free text: credit-adjust `reason` is unbounded, stored verbatim in `firms/*/ledger` AND `admin_audit_log.after` (an evidence-adjacent store), AND logged to Cloud Logging -- an operator pasting a client's intake notes into it lands them in three stores with no control. `admin_audit_log.before/after` are arbitrary dicts with no content allowlist test. Same "unbounded string reaches Cloud Logging" class as PF-2. | `admin_backend/routes/credit_routes.py`, `admin_backend/services/audit_log.py` |
| PF-10 | P2 | Unauthenticated-surface hardening gaps: `/health` discloses model names, flags, rates; the dev-only routes (`/ws/echo`, `/ws/audio`, `/dev/console-log`) gate on the `backend/.env.DEV` MARKER FILE (not an env var) whose real production control is `.dockerignore` excluding `backend/.env.*` -- add `K_SERVICE` fail-closed AND pin the dockerignore line; `MAX_UPLOAD_MB` is declared and reported but enforced nowhere; `/api/resume-form` base64-decodes the whole body before its 25 MB check and runs `fitz.open` on attacker-controlled bytes with no timeout/isolation; `/ws/fill` has no app-level frame-size cap; no WS Origin check. | `backend/main.py`, `dev_console_routes.py`, `backend/utils/dev_file_logger.py`, `.dockerignore`, `pdf_fill_routes.py`, `websocket_routes.py` |
| PF-11 | P3 | `token_file_logger` writes `backend/logs/token_usage.jsonl` on the production container every turn; the call-site comment claims "local dev only" but the gate is session-context presence, not `DEV_LOGGING_ENABLED`. Metadata only. A bare `print()` usage banner bypasses structlog. | `backend/adapters/live_ai_gemini.py` (token-usage block) |
| PF-12 | P3 | `.gitignore` has no `*.pem` / `*service-account*.json` / `*credentials*.json` pattern; `polyglot-backend-sa` holds `roles/storage.objectViewer` project-wide rather than bucket-scoped; no script sets bucket public-access-prevention / uniform access (must be verified live). | `.gitignore`, `scripts/setup-gcp-project.sh` |
| PF-13 | P2 | Raw field values (names, DOBs, A-numbers, addresses) are `console.log`ged in the PRODUCTION bundle at 10+ sites, and no vite config strips console calls. A demo-era submit handler dumps the whole `fieldValues` map and `alert()`s "Check console for field values" on the screen magic-link clients use. `send()`'s not-OPEN/"suspicious" branches dump whole outbound messages, including a handshake's `current_values`. P2 by the harm scale (the reader already has the screen); the shared-device harm is PF-14's. | `frontend/src/schema-forms/state/schemaFormState.ts`, `shared/connection.ts`, `utils/pdfFiller.ts`, `components/SchemaForm.tsx`, `SchemaFormDemo.tsx`, `fields/CheckboxField.tsx`, `webFormConnection.ts`; `frontend/vite.config.schema.ts` |
| PF-14 | P1 | Nothing AUTOMATICALLY clears a client's form PII (`schema_form_state`) or their magic-link token (`vff_client_link_token`): `clear()` is reached only from the three manual Clear-form buttons, `clearClientLinkToken()` has no production caller, `WebFormConnection.reset()` is dead code, the `idle_timeout` handler only closes the socket, and the voice app has NO logout UI while all three apps use `browserLocalPersistence` (survives browser restart). On a shared law-office tablet the previous client's answers and a live credential sit in the tab. | `frontend/src/schema-forms/state/schemaFormState.ts`, `shared/sessionCredential.ts`, `webFormConnection.ts`, `contexts/AuthContext.tsx` |
| PF-15 | P3 | `frontend/index.html` loads Google Fonts from `fonts.googleapis.com`/`gstatic` -- third-party egress (no PII; a data-minimization note only). | `frontend/index.html` |
| PF-16 | P2 | No document states what each third-party processor receives: Vertex retains prompts for abuse monitoring unless the project opts out; spellback sends the user's field value to Cloud TTS; Firebase Auth holds staff emails. Terms, retention and opt-out status are unrecorded. | `backend/adapters/live_ai_gemini.py`, `spellback_tts.py`, `text_ai_gemini.py` |

Related beads to link rather than duplicate: `polyglot-pdf-e4dt8` (CLOSED,
PR #774: the exception processor, the site-enumeration test, the sentinel
case in the PII guard, WS close-code events, `/health` firms probe -- B1a/B1b
build on it), `polyglot-pdf-yqg` (Logging Phase 6: the "BigQuery field-value
scan returns zero" criterion is satisfied by B2), `polyglot-pdf-q34sy`
(disclaimer timestamp bounds -> C4), `polyglot-pdf-u9gtj` (client-controlled
`spoken_language` becomes an unbounded Firestore map key -- the same "client
value reaches a store" class A's allowlists pin; link, do not duplicate). A
files a NEW retention-policy bead (none exists); `pol2` is cited only as the
source of the legal question.

## Workstreams (one child bead each; surfaces disjoint WITHIN a wave -- shared-file pairs carry a `blocks` edge in bead metadata so the collision guard sees the sequencing)

### B0. P0 stop-the-bleed, WAVE 0 (T3) -- PF-1, log half + invalidation
Runs before anything else; nothing depends on it and it depends on nothing.
- `--no-access-log` on the `Dockerfile` CMD (uvicorn 0.24 supports it; no
  upgrade needed) and drop the `uvicorn.access` INFO line in
  `backend/utils/logging.py`; pin both (extend `tests/test_dockerfile_app_module.py`
  with the flag, and a logging-config test). This removes the app-stream
  copy of the URL. Note the diagnostic cost: the per-connection access line
  is gone; the Cloud Run request log still carries status/duration until
  the exclusion below lands.
- ASK 1 (live change): a Cloud Logging exclusion on the `_Default` bucket
  scoped to `logName=~"requests" AND httpRequest.requestUrl=~"[?&]token="`.
  Narrow on purpose -- it drops only WS-connect rows (which all carry the
  token today), and C2 is what restores those rows by taking the token out
  of the URL. Land the flag FIRST so the filter never has to match the app
  stream.
- ASK 2 (firm-facing decision, escalate with the options memo): every link
  token minted inside the log retention window is in the request log now.
  Either rotate `LINK_TOKEN_SECRET` (invalidates every outstanding link; the
  firm re-mints; a deploy) or delete the request-log entries for the window
  (destructive). Firebase ID tokens expire within an hour and need no
  action. The maintainer picks; B0 records the choice and the timestamp,
  which becomes criterion 2's "fix timestamp".
- Surfaces: `Dockerfile`, `backend/utils/logging.py`,
  `tests/test_dockerfile_app_module.py`, a new logging-config test,
  `docs/components/config-deployment.md`.

### A. Data-at-rest inventory + store allowlists (T3) -- PF-8 (retention half), PF-9
- **Static:** list every persistent store the deployed system writes:
  Firestore (`confirmation_events`, `users`, `authorized_emails`, `firms`,
  `firms/*/ledger`, `links[_staging]`, `link_redemptions[_staging]`,
  `admin_audit_log`, `app_config`, `kits`, `alerts`), Firebase Auth user
  records, the GCS kit bucket (`<kit>/`, `_archive/`, `_drafts/`,
  `acroform.json`), BigQuery `polyglot_telemetry` (two tables), Cloud
  Logging streams (app stdout/stderr + `run.googleapis.com/requests`),
  container disk (`backend/logs/`, `logs/confirmations/`, the fill-pdf
  `NamedTemporaryFile`, and the editor extraction
  `tempfile.mkdtemp(prefix="extract_<kit>")` in `editor_kit_routes.py`
  -- cleaned in `finally`, but an OOM-killed subprocess leaves uploaded PDF
  bytes on a warm instance's disk), plus any SECOND COPY of a store:
  Firestore PITR / scheduled exports, Firebase Auth bulk export, Cloud
  Build logs (content, not just ACL).
- **Repo-as-a-store:** `scripts/pull-form-kits.sh` rsyncs the whole bucket
  (incl. `_drafts/` + `_archive/`) into the tracked tree; `scripts/spikes/*`
  holds tracked probe-run artifacts from live Gemini sessions;
  `.beads/*.jsonl` is a 800 KB text mirror of the tracker. Each gets the
  same redacted regex sweep (F1 runs it as part of the secret scan; A reads
  the result). The draft/archive schema check is a PROPERTY over kits
  discovered from `git ls-files form-kits/` + the bucket listing ("no schema
  anywhere carries a non-empty sample/example value"), never a named kit
  (scar #10).
- **Live (read-only, redacted):** new `scripts/audit/inventory_stores.py`
  (operator ADC, `--project` required + dead-project refusal, same shape as
  `scripts/read_confirmations.py`): for each Firestore collection sample N
  docs and print KEY NAMES, value TYPES and max string length per key --
  never a value -- and flag any key outside the collection's pinned
  allowlist; `gcloud storage ls -r` the bucket for unexpected objects; `bq
  show` both telemetry tables' schemas.
- **Guards to add:** bound `reason` (max length) at the Pydantic model, drop
  it from the `admin_credits_adjusted` log line (ids only), and pin the
  ledger entry key set; allowlist test for `admin_audit_log.before/after`
  key shapes per route (no client-data keys); pin `firms` doc keys. A owns
  all of PF-9. (Rules-file changes belong to C3.)
- **Deliverable:** the data-inventory table (store, key set, PII class,
  retention, reader roles, guard test) for the posture doc; a NEW
  retention-policy bead capturing the open decisions (confirmation_events
  and link_redemptions TTL, Cloud Logging bucket retention, BigQuery
  expiration, Firebase Auth deleted users) with `pol2`'s "what must we
  retain by law" note as its legal input -- filed, not decided.
- Surfaces: `scripts/audit/inventory_stores.py`, `backend/services/credit_ledger.py`,
  `admin_backend/routes/credit_routes.py`, `admin_backend/services/audit_log.py`,
  new tests under `backend/tests/unit/` + `admin_backend/tests/unit/`.

### B1a. Log-sink hardening, independent half (T3) -- PF-3, PF-11, close reasons, verbosity knobs
- Register a `RequestValidationError` handler on BOTH apps that returns
  `loc` + `type` + `msg` and never `input`; pin with a test that posts a
  sentinel value and asserts it is absent from the 422 body; assert
  `debug` is False on both apps.
- Gate `token_file_logger` on `DEV_LOGGING_ENABLED` (or delete the prod
  write) and route the usage `print()` through structlog; fix the comment.
- Enumerate and pin: WS close `reason=` strings (they go over the wire AND
  into Cloud Run's WS logging; assert the set is static literals -- e4dt8
  counts the CODES, this pins the TEXT); the secretary/validator/translation
  text-model call sites (`text_ai_gemini.py`, `secretary_context.py`) --
  confirm no INFO-level request/response logging of prompt or completion
  text; library verbosity knobs -- assert no `HTTPX_LOG_LEVEL` /
  `GOOGLE_GENAI_*` / `SEND_TRANSCRIPT` debug env is honoured on a deployed
  instance (D checks the live env for the same names).
- Sentinel cases in `test_no_pii_logging.py` for the 422 echo and the close
  reason; each proven red by reverting its fix (scar #9). The exception-
  message sentinel already exists (e4dt8).
- Surfaces: `backend/main.py` (the handler registration only),
  `admin_backend/main.py`, `backend/utils/token_file_logger.py`,
  `backend/adapters/live_ai_gemini.py` (print + token-logger lines only),
  `backend/tests/test_no_pii_logging.py`, new tests.

### B1b. Log-sink hardening, `error=` class + `/health` trim (T3) -- PF-2, PF-10 (`/health`)
- Sequenced after B1a (same guard file). Add `error`, `err`, `exc`,
  `message`, `detail` to `_SENSITIVE_KWARGS` with an explicit per-site
  allowlist for type-only values, so the ~185-line `error=str(` pattern is
  enumerated once (scar #8) and pinned; a plain `_log.warning` carrying
  `str(exc)` is the case the exception processor cannot catch.
  `validation_handler.py:138` is fixed here.
- `/health` on both apps returns booleans/status only (no model ids,
  rates, flags); keep both probes e4dt8 wired.
- Surfaces: `backend/tests/test_no_pii_logging.py`, `backend/main.py`
  (`/health`), `admin_backend/main.py` (`/health`),
  `backend/services/validation_handler.py`, the allowlisted call sites,
  `backend/tests/unit/test_health.py`.

### B2. Live log sweep (T3) -- verifies PF-1/PF-2 in production, closes yqg's zero-PII criterion
- New `scripts/audit/log_pii_sweep.py`: queries Cloud Logging for
  `polyglot-backend`, `polyglot-backend-staging`, `polyglot-admin` over the
  retention window, across BOTH the application streams and
  `run.googleapis.com/requests`, applying TIGHT detectors (a loose
  `A\d{8,9}` matched 227 bead ids in the tracker mirror alone): `[?&]token=`
  inside `httpRequest.requestUrl`; a two-segment JWT `\beyJ[\w-]{20,}\.eyJ`;
  the one-dot link-token shape only inside a URL; `(?<![\w])A[0-9]{8,9}(?![\w])`
  (explicit lookarounds -- `\b` fails after an underscore); SSN with
  boundaries; email; phone; DOB-shaped dates only inside `jsonPayload`
  string fields (never `insertId`/labels). Output is COUNTS per (service,
  logName, detector, jsonPayload key) plus `insertId`s and timestamps --
  **never the matched text** -- and the script refuses to run under
  `--log-http` or a debug verbosity. Same query shape against the BigQuery
  telemetry tables.
- Deliverable: a dated results snapshot in the journal entry with EVERY hit
  dispositioned: hits AFTER B0's fix timestamp are true positives to fix
  and re-sweep to zero, or false positives with the detector tightened;
  hits BEFORE it are residue, listed with their count and the invalidation
  or deletion B0 chose. The script stays as the recurring check.
- Surfaces: `scripts/audit/log_pii_sweep.py`, journal.

### C1. Route/gate matrix + cross-tenant tests, HTTP and WS (T1, T2)
- Generate the (method, path, gate) table for both apps from the live route
  tables (extend the existing set pins rather than hand-listing) and publish
  it into the posture doc.
- New integration matrix test over real HTTP AND the WebSocket (TestClient
  + `websocket_connect`, patched verifiers): actors = anonymous, firm-A
  employee, firm-A manager, firm-B manager, client link for firm A, client
  link for firm B, editor, author, app admin; for every route assert the
  expected status. Must prove: A cannot read B's private kits/archive/
  links/users/ledger; a client link reaches only its own kit + the paid/
  browse doors; editor cannot reach admin; a Firebase token with no claims
  gets only the browse set; every refusal on the oracle-sensitive doors is
  the uniform 404. WS cases: anonymous is refused BEFORE accept; a firm-B
  link naming a firm-A kit hits the mismatch branch in
  `websocket_routes.py` and closes 1008; a staff token naming a kit outside
  its firm is refused. Derived from the route table, so a new route without
  a classification fails CI.
- Review `link_tokens.py` (`iat` unchecked, secret rotation runbook, jti
  entropy) and `link_redemptions.py` reopen semantics; record verdicts.
- Surfaces: `backend/tests/integration/test_access_matrix.py`,
  `admin_backend/tests/unit/test_access_matrix.py`, posture doc routes
  section (handed to G).

### C2. Move the WS credential off the URL + WS hardening (T3, T1) -- PF-1 root cause; APPROVED
- Carry the credential in the first WS frame (the handshake is already the
  first frame; verify BEFORE any Gemini session starts and close 1008 on
  failure). Keep `?token=` accepted for ONE deploy cycle behind a
  deprecation log line, then remove. Update `docs/standards/ws-protocol.md`,
  `docs/components/websocket-routing.md`, `docs/components/auth.md`.
- Same bead (same file): an Origin allowlist check on `/ws/fill` reusing
  the CORS origin list; a max frame size on `/ws/fill`; `/ws/echo` +
  `/ws/audio` fail closed on `K_SERVICE`.
- Once deployed, B0's exclusion filter matches nothing and the WS-connect
  rows return to the request log with status and duration.
- Surfaces: `backend/routes/websocket_routes.py`, `frontend/src/webFormConnection.ts`,
  `frontend/src/shared/connection.ts`, `frontend/src/shared/config.ts`, the
  voice-harness client under `tests/e2e/voice-harness/`, the three WS docs.
  Sequenced AFTER E1 (shares `webFormConnection.ts`/`connection.ts`). Tier
  `opus`, `cross-surface`; consequence-bearing (maintainer merge).

### C3. Firestore rules hardening + rules tests (T1) -- PF-6, PF-8 (rules half)
- `authorized_emails`: close the public read entirely
  (`allow read, write: if false`) and move the signup allowlist check
  server-side -- a backend route that answers the uniform 404 for a
  non-allowlisted address (same posture as `/api/links/open`), rate-
  limitable later with the rest. The client calls it before
  `createUserWithEmailAndPassword`. Verify how entries are keyed today.
- Add an explicit deny block for `confirmation_events` and add it to
  `ADMIN_SDK_ONLY_COLLECTIONS`; confirm `users/{uid}` cannot be listed.
- Run the `firebase:firebase-security-rules-auditor` skill on the final
  file; add emulator-backed rules tests (`@firebase/rules-unit-testing`)
  proving the enumeration is closed and the profile isolation holds.
- Surfaces: `firestore.rules`, `backend/tests/unit/test_firestore_rules_text.py`,
  a new `backend/routes/signup_routes.py` (+ its `test_http_route_auth.py`
  classification), `frontend/src/contexts/AuthContext.tsx` (+ its test),
  new rules test dir.

### C4. Unauthenticated-surface hardening, WAVE 1 (T1) -- PF-5 (decision), PF-10 (non-WS half), q34sy
- `/dev/console-log`: fail closed on `K_SERVICE`, AND pin the
  `.dockerignore` `backend/.env.*` line (the real production control for
  the `.env.DEV` marker) with a test. `MAX_UPLOAD_MB`: enforce it as a body
  cap on every upload route or delete it (a knob nothing enforces is a trap
  -- scar #7). Resume form: check the base64 length BEFORE decoding; run
  `fitz.open` + the structural check under a wall-clock timeout (thread +
  timeout, or the same subprocess isolation the extractor uses). Bound the
  disclaimer timestamp (q34sy).
- Rate limiting: write the options memo (Cloud Armor + LB = new infra +
  cost; app-level per-instance token bucket = cheap, weak; Cloud Run
  max-instances/concurrency = cost bound only) and ESCALATE the choice; do
  not pick. Implement whatever the maintainer chooses in a follow-up bead.
- Surfaces: `backend/routes/dev_console_routes.py`,
  `backend/routes/pdf_fill_routes.py`, `backend/routes/disclaimer_routes.py`,
  `backend/config.py`, `.dockerignore` pin test under `tests/`. No
  `main.py` edit (the `/health` trim lives in B1b), so no dependency.

### D. Live infrastructure posture, read-only (T1, T3, T4) -- verifies PF-12 and the deployed side of everything above
- New `scripts/audit/infra_posture.sh` (read-only `gcloud`/`bq`/`firebase`
  commands, operator ADC, `--project` required, prints PASS/FAIL/N-A per
  check): project IAM policy (every principal; flag human Owner/Editor, log
  viewers, datastore viewers); both SAs' roles equal the pinned lists;
  every Cloud Run service + latest revisions: env vars contain no
  secret-shaped value, none of `VFF_DISABLE_AUTH`/`VERTEXAI=false`, and no
  verbosity knob (`HTTPX_LOG_LEVEL`, `GOOGLE_GENAI_*`, `SEND_TRANSCRIPT`,
  `DEV_LOGGING_ENABLED`), secret bindings present, ingress, min/max
  instances, runtime SA; Secret Manager secrets + IAM; bucket IAM (no
  `allUsers`), public-access-prevention enforced, uniform bucket-level
  access, object listing anomalies; deployed Firestore rules byte-equal to
  the repo file; Firestore TTL policies, PITR/backup schedules and export
  buckets; Cloud Logging bucket retention, sinks (filter == repo),
  exclusion filters (B0's present), data-access audit-log config; BigQuery
  dataset ACL + table expiration; Firebase Auth: authorized domains,
  email-enumeration protection, providers, MFA status of admin/editor
  accounts, password policy, export settings; Hosting response headers
  (curl each site); container image vulnerability scan results (if
  Artifact Registry scanning is OFF, enabling it is a live change -> an
  ASK, and the check reports `N/A: scanning disabled`) and base-image age;
  Cloud Build log CONTENT for echoed env/secret values, plus the logs
  bucket ACL; **T4 live settings**: the Vertex AI abuse-monitoring /
  data-caching opt-out state for the project, and the Cloud TTS data-use
  setting, for G's processor table.
- Every check ends PASS, FAIL, or `N/A: <reason>` (e.g. the operator's
  identity lacks a viewer role) -- never a silent skip; the script keeps
  going past a permission error.
- IAM findings are corroborated against the existing pins
  (`test_deployed_iam_envelope.py`, `test_admin_sa_iam_envelope.py`) and any
  TIGHTENING the audit proposes (e.g. bucket-scoping `storage.objectViewer`)
  goes through scar #7's ritual in BOTH directions -- name the call, name
  the permission, check the live policy -- because a mock cannot tell you a
  removed role was load-bearing.
- The `experimentation` skill's cost gate does not apply to these scripts:
  none of them calls a Gemini model; they read infrastructure only.
- Deliverable: the runbook (recurring), a dated snapshot in the journal, the
  posture doc "live checks" section.
- Surfaces: `scripts/audit/infra_posture.sh`, journal, `docs/components/config-deployment.md`.

### E1. Browser PII hygiene, WAVE 1 (T6) -- PF-13, PF-14
The harm is to the NEXT person who touches a shared law-office tablet, not a
hypothetical attacker, and the fix is small -- so it ships first.
- **Console PII**: delete the value-logging sites (the sites are the bug)
  including the `alert("Check console...")` submit handler; redact `send()`'s
  error branches to `{type, size}`. Then the build-time backstop, three
  lines per config: `esbuild: { pure: ['console.log', 'console.debug'] }`
  in `frontend/vite.config.schema.ts` (the config `build:schema` actually
  ships; `frontend/vite.config.ts` does not), `schema-editor/vite.config.ts`,
  `admin-console/vite.config.ts` -- NOT `drop: ['console']`, which would
  also remove `warn`/`error`. Triage first: the app has ~375 `console.log`
  calls and staff read some on staging (the WS close diagnostic in
  `webFormConnection.ts`); promote the diagnostics to `console.info`/`warn`
  before the drop so they survive it. Guards: a bundle test asserting the
  production build contains no `console.log(` (the property), and a narrow
  vitest source-scan over `frontend/src` that fails on a `console.*` call
  whose arguments name `fieldValues`, `current_values`, or a token
  identifier -- deliberately NOT `value`/`message`/`state`, which are
  everywhere and would need an ever-growing allowlist. Proven red first
  against the current tree.
- **Storage lifecycle**: reuse the existing Clear-form path
  (`SchemaFormStateManager.clear()` + `clearOnboardingState()`, plus
  `clearClientLinkToken()`) and call it automatically (a) when the client
  marks the form complete (after the download/print action, on
  `complete_link` success), (b) on idle timeout after an on-screen warning,
  and (c) on logout; delete the dead `WebFormConnection.reset()`; add a
  visible logout control to the voice app's staff header that calls the
  existing `logout()` and clears storage. Persistence mode (local vs
  session) for the voice app is a UX call -- recommend
  `browserSessionPersistence` for the voice app only, keep local for
  editor/admin, recorded as a decision for the maintainer in G.
- Surfaces: `frontend/vite.config.schema.ts`, `schema-editor/vite.config.ts`,
  `admin-console/vite.config.ts`,
  `frontend/src/schema-forms/state/schemaFormState.ts`,
  `frontend/src/shared/connection.ts`, `frontend/src/shared/sessionCredential.ts`,
  `frontend/src/schema-forms/utils/pdfFiller.ts`,
  `frontend/src/schema-forms/components/SchemaForm.tsx`,
  `frontend/src/schema-forms/SchemaFormDemo.tsx`,
  `frontend/src/schema-forms/components/fields/CheckboxField.tsx`,
  `frontend/src/webFormConnection.ts` (console + clearing lines), a new
  `frontend/src/**/consoleGuard.test.ts` + bundle test. (`AuthContext.tsx`
  belongs to C3; E1 adds the logout button in a UI component and calls the
  existing `logout()`.) C2 is sequenced AFTER E1.

### E2. Hosting headers + fonts, second wave (T1, T4) -- PF-4, PF-15
- **Hosting headers** (`firebase.json`, all 5 sites): CSP built from the real
  connect-src inventory (own origin, the two Cloud Run URLs, Firebase
  Auth/Firestore endpoints, self-hosted fonts), `frame-ancestors 'none'`,
  HSTS with preload, `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  no-referrer`, `Permissions-Policy` that allows `microphone=(self)` and
  denies the rest. Ship as `Content-Security-Policy-Report-Only` on staging
  first, read the violation reports, then enforce. Pin with a test that
  parses `firebase.json` and asserts every target has the header set.
- Fonts: self-host the two Google Fonts (removes the last third-party egress
  and simplifies the CSP).
- Surfaces: `firebase.json`, `frontend/index.html`, `frontend/public/fonts/`,
  `tests/test_hosting_headers.py`. Depends on E1 (the CSP inventory reads
  E1's final connect-src set). Verifying the headers on a live site needs a
  staging deploy (gated ask).

### F1. Secrets + supply chain + CI scanning (T5) -- PF-7 (all but uvicorn), PF-12 (gitignore)
- Secret scan: `detect-secrets` (pip) over the tree with a baseline that
  allowlists the public Firebase key, plus a history sweep over every blob
  reachable from `git rev-list --all` (a small Python regex sweep; no Go
  binary needed) -- the same sweep covers `scripts/spikes/*` and
  `.beads/*.jsonl` for A. Record the result; if history is clean, add the
  diff scan to CI.
- `pip-audit -r backend/requirements.txt`; `npm audit --omit=dev` in
  `frontend/`, `schema-editor/`, `admin-console/`; `bandit -r backend
  admin_backend -ll`; `semgrep --config p/python --config p/typescript`
  (pip-installable). Upgrade what the audits flag EXCEPT `uvicorn`/
  `websockets` (F2) -- `python-multipart` and `PyMuPDF` are the expected
  hits; each upgrade runs the full suite.
- Split runtime deps from test deps so the image ships no pytest; run the
  container as non-root; pin the base image by digest.
- CI: add a `security` job to `ci.yml` (pip-audit, npm audit x3, detect-
  secrets diff, bandit) -- **informational, matching ci.yml's non-blocking
  doctrine** (making it required is a maintainer call, flagged in G); add
  `.github/dependabot.yml` (pip, npm x3, actions; weekly, grouped).
- `.gitignore`: `*.pem`, `*service-account*.json`, `*credentials*.json`,
  `*.key`.
- Surfaces: `.github/workflows/ci.yml`, `.github/dependabot.yml`, `.gitignore`,
  `backend/requirements.txt` (+ a `requirements-dev.txt`), `Dockerfile`
  (user + digest lines; B0 owns the CMD line -- B0 lands first),
  `.secrets.baseline`, the three `package-lock.json` files as audits require.

### F2. uvicorn / websockets bump, harness-gated (T5) -- PF-7 (uvicorn)
- Its own bead because the `/ws/fill` handshake has broken on exactly this
  bump before (uvicorn + websockets 14: sync Vertex `Depends` blocked the
  loop before `accept()`). Tier `sonnet` / `local-bug`, NOT mechanical.
  Exit criterion: the full backend suite green AND the voice harness
  (`/voice-harness`) passes end to end against the local stack on the new
  pins, before the PR opens.
- Surfaces: `backend/requirements.txt` (the two pins -- after F1's split
  lands), the harness runbook note.

### G. Triage, remediation tracking, processor table, report + posture doc (all; T4 owner)
- Severity scale: **P0** a live credential or CLIENT PII exposed, or
  unauthenticated access to client data (fix before anything else in the
  epic); **P1** client data or staff identity exposed to a wrong-tier user,
  to an insider with ordinary log/console access, or to the next user of a
  shared device (staff-email enumeration, PF-6, sits here by harm even
  though it is unauthenticated); **P2** defense-in-depth; **P3** hygiene.
  The scale is by HARM, not by who can reach the door.
- Every finding from the beads above gets a disposition: fixed in-epic
  (P0/P1 -- a bead of its own if not already one of the beads above), filed
  as a bead with tier/work_class (P2/P3), or accepted by the maintainer in a
  written note captured on the bead or in the journal entry.
- **Third-party processor table (T4, PF-16):** for Vertex AI (Gemini Live +
  generate_content), Cloud Text-to-Speech, Firebase Auth, and Firestore/
  GCS/BigQuery as Google-hosted stores: what data is sent (audio, SI with
  `current_values`, tool args; the spellback field value; staff emails),
  the governing terms (Vertex's enterprise DPA vs AI Studio's consumer
  terms), retention (Vertex abuse-monitoring prompt retention unless opted
  out; TTS request data use), and the project's opt-out status as read by
  D. Lives in the posture doc.
- Write `docs/standards/security-posture.md` (tier 2, current-state only,
  with a `**Tracks:**` line): threat model, data inventory (from A), route/
  gate matrix (from C1), credential systems summary, the processor table,
  live-check runbook pointers (D, B2), the "known accepted risks" list, and
  the decisions handed to the maintainer (rate limiting, retention bead,
  CI job blocking, voice-app persistence mode). Add the INDEX row; add
  per-surface rows to `hipaa-pii-policy.md` for the newly-covered sinks
  (access log, 422 echo, ledger `reason`, audit-log `before/after`, close
  reasons); journal entry with the dated findings + live snapshots.
- Surfaces: `docs/standards/security-posture.md`, `docs/INDEX.md`,
  `docs/standards/hipaa-pii-policy.md`, journal.

## Exit rubric (epic)

| # | Criterion (binary) | Verify |
|---|--------------------|--------|
| 1 | **Inventory complete + live-verified.** The set of stores in `security-posture.md`'s inventory table is IDENTICAL to the set `scripts/audit/inventory_stores.py` iterates -- diffed mechanically by a test that parses the table's STORE-NAME cell only (never the prose columns; the `abn4o` lesson) against the script's store list; every row carries key set, PII class, retention and reader roles; and the script run against the demo project reports zero keys outside each store's pinned allowlist. | Run the doc-vs-script test; run the script with `--project polyglot-demo-aa709`. |
| 2 | **No credential or field value in Cloud Logging or BigQuery after the fix.** `scripts/audit/log_pii_sweep.py` over all three services (application + request logs) and both telemetry tables reports ZERO hits on every detector for entries timestamped after B0's fix timestamp; every older hit is listed as residue with its count and the invalidation or deletion B0 chose; and the static guard has a red-then-green sentinel test for each sink shape this epic adds (`error=` kwarg, `print`, access log, 422 echo, close reason -- the exception-message sentinel is e4dt8's). | Run the sweep and read the post-fix and residue columns; run `test_no_pii_logging.py`; revert one fix per shape and watch its sentinel fail. |
| 3 | **Every route on both services, HTTP and WS, is classified and cross-tenant-tested.** A set-derived matrix test asserts the expected status for every (actor x route) pair per the route/gate matrix C1 produces, including the three WS cases, and adding a route without a classification fails CI; the firm-A-vs-B, client-link-vs-staff, editor-vs-admin and anonymous cases all refuse per that matrix. | Run the matrix tests; remove one `Depends(...)` gate and watch the matrix go red. |
| 4 | **Live posture equals the repo.** `scripts/audit/infra_posture.sh --project polyglot-demo-aa709` ends with every check PASS or `N/A: <documented reason>` (never FAIL, never silently skipped): SA roles equal the pinned lists; no plaintext secret, dev/bypass flag or verbosity knob on any live Cloud Run revision; bucket has public-access-prevention enforced and no `allUsers` binding; deployed Firestore rules byte-equal the repo; every Hosting site serves CSP/HSTS/XFO/Referrer-Policy; `authorized_emails` cannot be read by the public web config; the Vertex opt-out state is recorded. **Passing the headers and rules checks requires a DEMO deploy of E2 and C3 (gated ask), so the epic's close is visibly gated on that deploy.** | Run the script after the demo deploy; read its PASS/FAIL/N-A table. |
| 5 | **Every finding is dispositioned and scanning recurs.** The journal entry lists each finding with severity; every P0/P1 is merged, or accepted by the maintainer in a written note captured in the journal entry or on the bead; every P2/P3 has a bead (incl. the new retention-policy bead); a PR opened after the epic shows the CI security job (dependency + secret scan) ran. | Read the entry; `bd list` the epic's children; open any PR and see the job. |

Criteria -> children: 1 <- A, G; 2 <- B0, B1a, B1b, B2, C2; 3 <- C1 (+ C2,
C3, C4 as the fixes it exercises); 4 <- D, C3, E2, G (processor table);
5 <- F1, F2, G. E1's guards are in-repo tests verified under criterion 3's
mutation rule; its shared-device outcome is what criterion 5's P1
disposition of PF-14 records.

## Bead tree, tiers, order

| Bead | Tier / class | Depends on | Parallel with |
|------|-------------|------------|---------------|
| B0 P0 stop-the-bleed | sonnet / local-bug | -- (wave 0, first) | -- |
| A inventory + allowlists | sonnet / local-bug | B0 (order only) | B1a, B2, C1, C4, D, E1, F1 |
| B1a log-sink, independent half | sonnet / local-bug | B0 | A, B2, C1, C4, D, E1, F1 |
| B1b log-sink, `error=` class + `/health` | opus / cross-surface | B1a (shared guard file) | C3, E2, F2 |
| B2 live log sweep | sonnet / mechanical | B0 (needs the fix timestamp) | everything |
| C1 route matrix, HTTP + WS | sonnet / local-bug (opus if it reveals a gate bug) | -- | A, B1a, B2, C4, D, E1, F1 |
| C2 WS credential off URL | opus / cross-surface | E1 (shared files); approved | B1b, C3, E2, F2 |
| C3 rules hardening + server-side signup check | sonnet / local-bug | -- (wave 2 only for load-balancing; needs a rules deploy ask at the end) | B1b, C2, E2, F2 |
| C4 unauth-surface hardening | sonnet / local-bug | -- | A, B1a, B2, C1, D, E1, F1 |
| D infra posture runbook | sonnet / mechanical | B0 (reads its exclusion) | everything |
| E1 browser PII hygiene | sonnet / local-bug | -- | everything in wave 1 |
| E2 hosting headers + fonts | opus / cross-surface (CSP vs 3 apps + 2 backends) | E1 | B1b, C2, C3, F2 |
| F1 secrets + supply chain + CI | sonnet / mechanical | B0 (Dockerfile CMD line lands first) | everything in wave 1 |
| F2 uvicorn/websockets bump | sonnet / local-bug | F1 (requirements split); voice harness available | B1b, C2, C3, E2 |
| G triage + processor table + report + posture doc | opus / needs-plan -> writes docs | all of the above | -- |

Wave 0: B0 alone, first. Wave 1 (concurrent): A, B1a, B2, C1, C4, D, E1,
F1. Wave 2: B1b, C3, E2, F2. Wave 3: C2. Last: G.

`blocks` edges: A/B1a/B2/D/F1 <- B0; B1b <- B1a; C2 <- E1; E2 <- E1;
F2 <- F1; G <- every child.

## Decisions made in planning (defended)

- **Epic + beads, not a one-session audit.** Remediation spans many PRs and
  surfaces; the repo's own doctrine makes the sprint plan the scope of record.
- **A new tier-2 `security-posture.md` rather than growing `hipaa-pii-policy.md`.**
  That doc is scoped to logging; the threat model, route matrix, processor
  table and live runbook need a current-state home of their own.
- **Every live check prints counts, keys, types and ids -- never a value.**
  Running the sweeps must not itself move client PII into an agent
  transcript.
- **B0 lands the access-log flag before the exclusion filter, and the
  filter stays narrow.** A URL-wide exclusion would also drop the WS-connect
  rows staff read when diagnosing 1011s; the flag removes the app-stream
  copy, the narrow filter covers the request log, and C2 restores the rows.
- **CI security job is informational**, matching the existing workflow's
  non-blocking doctrine; promoting it to required is flagged for the
  maintainer in G, not done unilaterally.
- **Rate limiting, the credential-invalidation choice, log retention/TTL
  and the voice-app persistence mode are ESCALATED, not chosen.** Cost,
  firm-facing, legal, and UX decisions respectively.
- **B1 stays split even though e4dt8 closed.** Two smaller PRs on the same
  guard file are cheaper to review than one, and B1a needs nothing.

## Verification (end-to-end)

1. `pytest -q -m "not external"` from the worktree (full suite, both roots)
   plus the three vitest suites -- every new guard/matrix test green, and
   each proven red by mutation before merge (scar #9).
2. Run the three audit scripts against the demo project and attach their
   PASS/FAIL + count tables to the journal entry.
3. Local stack (`/run-local`): a voice session still connects after B0/F2/C2
   (credential path); a 422 on `/api/fill-pdf` no longer echoes input;
   `/health` is trimmed; the dev routes 404 with `K_SERVICE` set; the
   client's storage is empty after completion and after an idle timeout.
4. Staging deploy (gated ask) before demo: re-run `infra_posture.sh` and
   `log_pii_sweep.py` against staging (headers, rules, no `token=` rows
   after C2), then the demo deploy (gated ask; also ships the rules) and a
   final sweep. Criterion 4 cannot pass before that demo deploy.
5. Each bead ships through `/closeout`; C2, C3 (rules), B0's live asks and
   anything touching a deploy script are consequence-bearing (maintainer
   merge).

## Out of scope

- Magic-link DELIVERY (email/SMS): by design there is no client identifier
  anywhere in the mint request (`link_routes.py`, `MintLinkRequest`); the
  firm copies the URL into its own channel. Whether the firm's mail system
  logs that URL is the firm's surface, not this codebase's -- the posture
  doc states this so nobody chases it.
- The legal retention answer and the counsel review (bd `pol2`): A files
  the retention-policy bead; the audit surfaces the decision, it does not
  make it.
- Implementing rate limiting infrastructure (Cloud Armor/LB) -- decided
  after C4's memo.
- A separate admin-only Firebase project, MFA rollout mechanics, and SOC2-
  style evidence packaging -- follow-on epics if the maintainer wants them.
- Penetration testing by a third party.
