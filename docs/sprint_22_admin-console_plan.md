# Sprint 22 -- Admin console program

**Program epic:** `polyglot-pdf-4uvh2`
**Epics:** E1 foundations `polyglot-pdf-b66pb` . E2 firms + credits `polyglot-pdf-e374w` . E3 telemetry `polyglot-pdf-43c99` . E4 deploy plane `polyglot-pdf-nacfo` . E5 Stripe + reports `polyglot-pdf-m5exr`
**Approved:** 2026-09-03 (two maintainer review rounds folded in the same day)
**Beads filed 2026-09-03:** Epic 1 children 1.1-1.8 (`pnoik`, `7w17m`, `3l2vp`, `li9x0`, `bg313`, `9hzod`, `b6943`, `2cwja`); Epic 2 Track A A1-A6 (`4rkrx`, `vnxew`, `jecrl`, `ah5d3`, `1op3g`, `d4wdi`); this doc's own bead `ybwjw`. Epics 2 (Tracks B/C), 3, 4, 5 get their own `/plan-epic` pass before their remaining beads are filed.

---

*Planning session 2026-09-03. Branch `claude/admin-console-planning-dfe9bf`.
This is a PROGRAM plan (six epics). Each epic still gets its own `/plan-epic`
pass with maintainer approval before beads are filed; this document fixes the
architecture, the cross-epic contracts, the order, and the exit rubric of each
epic so those passes start from a settled shape. Revised the same day after
the maintainer's review: credit reserved before signing and a mint record
required at open (which adds revocation), audit rows inside the mutation's
transaction, refunds keyed on the authoritative redemption doc, a staging
tier for the admin service, enforcement behind a runtime flag with an
operator CLI, the promotion gate inside the build, explicit channel
arguments on the shared link helpers, USD and firm-kind snapshots on ledger
entries, and no Docker build args.*

## Context

Operating the app today means running a growing set of bash scripts by hand
(`deploy-staging.sh`, `deploy-demo.sh`, `deploy-editor.sh`,
`scripts/deploy-form-kit.sh`, `scripts/bootstrap_firm.py`,
`scripts/bootstrap_editor_user.py`, `scripts/bootstrap_voice_dev.py`,
`scripts/read_confirmations.py`) plus the GCP and Firebase consoles. The
maintainer wants ONE admin console covering: code deploys to every target;
form-kit commercial management (publish state, firm access, credit price,
per-link burn cap); firm and user management with credits, promotional
grants, and eventually Stripe; and monitoring (usage and cost by firm, form,
and employee; errors; credit-exhaustion alerts; cost versus income including
Cloud Run hosting).

What already exists and is built on, not replaced (inventory verified
2026-09-03):

- Firms (`firms/{firm_id}`: name, contact_email, allowed_kits, status), staff
  claims `firm_id` + `firm_role`, the bootstrap script, fail-closed reads in
  `backend/services/firms.py`.
- Client magic links: stateless HMAC tokens (`backend/services/link_tokens.py`,
  payload pinned by test), `POST /api/links/mint` + `/open`
  (`backend/routes/link_routes.py`), one-time redemption ledger
  `link_redemptions[_<channel>]/{jti}` created at FIRST OPEN, per-link USD
  spend ceiling enforced at the socket (`link_spend.py`, `link_budget.py`),
  per-firm monthly mint counter (`link_metering.py`, metered never refused),
  channel isolation via the `aud` claim. The staff mint page
  `frontend/src/console/MintLinkPage.tsx` at `/console/links` is the first
  console slice already shipped.
- Kit lifecycle owned by the schema editor (`backend/routes/editor_kit_routes.py`:
  draft/submitted/complete/unpublished, archive, guarded delete, lock) and the
  firm retire route; firm-scoped visibility in `backend/services/kit_gates.py`.
- Per-turn Gemini Live cost events to Cloud Logging (`structured_logger.py`
  `gemini_api_response`) carrying form + session ids only; session start/end
  + confirmations to Firestore `confirmation_events` carrying firm_id,
  kit_id, employee_id, link_jti.
- Deploy engine `deploy-all.sh` (Cloud Build image + `gcloud run deploy` with a
  whole `--set-env-vars` block + reachability gate; kits to the shared bucket;
  Vite build + `firebase deploy --only hosting:<target>`), wrappers per
  channel, `tests/test_deploy_channel_parity.py` pinning staging env == demo
  env except three keys. CI is informational and deploys nothing.

What does NOT exist: any app-admin role; a credit ledger; Stripe; BigQuery or
any log sink; Cloud Run cost data; alerts; cost events tagged with firm or
employee; dollar figures for the secretary, validator, translation, or TTS
calls; a git SHA on `/version`.

## Decisions (maintainer, 2026-09-03 -- do not relitigate)

1. **Topology.** The admin API is a SEPARATE Cloud Run service with its own
   service account holding the wider IAM, gated by a new `app_admin` custom
   claim. The public backend's service account stays narrow (CLAUDE.md scar
   #7; `backend/tests/unit/test_deployed_iam_envelope.py`). The admin console
   is a SEPARATE Vite app on its own Hosting site (precedent: `schema-editor/`).
   Firm-manager and employee pages stay in the MAIN app under `/console/*`
   and call the admin service for privileged operations.
2. **Deploys** move to Cloud Build from a named git ref. The console triggers
   builds, records them, shows what SHA is live per channel, and mechanically
   enforces staging-before-demo. Bash scripts stay until the console path is
   proven on staging and demo, then become thin wrappers or are retired.
3. **Credits.** A firm holds a credit balance. Minting a link for form F
   debits `credit_cost(F)` at mint. A firm at zero is REFUSED. A link that
   expires unopened is REFUNDED automatically. The ledger has typed entries so
   subscription grants, prepaid purchases, promotional grants, and manual
   adjustments all work from day one; Stripe is a later entry source.
4. **Order.** Foundations -> Firms + credits + forms -> Telemetry + monitoring
   -> Deploy control plane -> Stripe + cost-vs-income reports.

Assumptions taken by the planner (reversible, noted for the maintainer):

- The ledger supports BOTH monthly subscription grants and prepaid packs;
  which one a given firm is on is a per-firm setting, not a product-wide
  choice.
- The `landing/` site is an OPTIONAL extra deploy target in the deploy epic,
  not a blocker for anything.
- Email provider for alerts and (later) link delivery: Postmark, key in
  Secret Manager. Provider choice is flagged as a maintainer decision when
  the alerts bead is planned.
- Per-form commercial settings live in Firestore `kits/{kit_id}`, not in the
  kit's `metadata.json`, so a price change never needs an editor publish. The
  existing `link_cost_ceiling_usd` metadata key migrates there.
- Runtime settings that must change without a redeploy (minting on/off,
  global ceiling, alert thresholds) move to one Firestore config document
  read by the public backend with a short TTL cache.

## Architecture (cross-epic contracts)

```
admin-console/ (Vite; Hosting site polyglot-admin-demo)  --Bearer id-token-->  polyglot-admin (Cloud Run; SA admin-backend-sa; package admin_backend/)
frontend /console/* (firm manager + employee pages)       --Bearer id-token-->  polyglot-admin (firm-scoped routes)
frontend /f, /console/links, form filler                  --Bearer/link token->  polyglot-backend[-staging] (SA polyglot-backend-sa, narrow)
Cloud Scheduler / Pub/Sub (machine callers)               --Google OIDC + pinned caller email-->  polyglot-admin (sweep, alert dispatch, build webhook)

polyglot-admin reads/writes: Firestore (firms, ledger, kits, links, alerts, admin_audit_log, deployments, app_config),
                             Firebase Auth (create/disable users, set claims), Cloud Build (trigger + status),
                             BigQuery (cost views), Error Reporting + Monitoring (read), Secret Manager (email key)
polyglot-backend writes:     ledger debit in the mint transaction; usage rollups at session end; alert docs;
                             structured usage events to Cloud Logging. Reads app_config/{channel} with a TTL cache.
```

Two config mechanisms, deliberately distinct: `app_config/{channel}` (Epic 1)
holds POLICY that changes without a deploy; `deploy/channels/<channel>.env`
(Epic 4) holds TOPOLOGY that is part of a deploy (service identity, secrets
bindings, base URLs, channel). Never merge them.

The admin service has NO channel: it serves both channels' data. Every
shared helper that today derives a collection name from `LINK_CHANNEL`
(`link_redemptions`, and the new `links` record) takes `channel` as an
explicit argument; the public backend fills it from its env, the admin
service passes the channel it is acting on. What separates test money from
real money is the FIRM's `kind`, snapshotted onto every ledger entry, never
the channel.

## Epic 1 -- Foundations

### Admin service (`admin_backend/`, Cloud Run service `polyglot-admin`)

- A sibling top-level package with its own `admin_backend/main.py` (FastAPI),
  `routes/`, `services/`, `tests/`. It imports `backend.services.*` for shared
  logic (firms, link_tokens, kit_gates, firestore client); its privileged
  code (Firebase Auth admin calls, Cloud Build, BigQuery) lives ONLY under
  `admin_backend/`. The IAM guard
  `backend/tests/unit/test_deployed_iam_envelope.py` walks `backend/` only
  (its `root` is `parents[2]` of the test file), so the public backend stays
  pinned at zero privileged calls with NO change to that test. Add a sibling
  `admin_backend/tests/unit/test_admin_sa_iam_envelope.py` pinning
  `admin-backend-sa`'s role list (fixture constant, refreshed by hand, offline)
  and asserting `admin_backend/` never imports `backend.routes` (it shares
  services, not routes).
- One root `Dockerfile` (already built from the repo root, already copies
  `backend/` + `scripts/authoring` + `scripts/bakeoff`) gains
  `COPY admin_backend /app/admin_backend` and a CMD that reads the app module
  from a RUNTIME env var with the current default:
  `uvicorn ${APP_MODULE:-backend.main:app} ...`. NO build args:
  `deploy-all.sh` builds with `gcloud builds submit --tag`, which cannot pass
  `--build-arg`. `APP_MODULE` and `GIT_SHA` are set per service at deploy
  time through `--set-env-vars` (the bash bridge computes
  `GIT_SHA=$(git rev-parse HEAD)`; Cloud Build later sets `$COMMIT_SHA`).
  `tests/test_deploy_channel_parity.py`'s channel-specific allowlist gains
  `GIT_SHA`. One image, two services, one requirements file.
- Service account `admin-backend-sa@polyglot-demo-aa709.iam.gserviceaccount.com`,
  created by a new `scripts/setup-admin-service.sh` (sibling of
  `scripts/setup-gcp-project.sh`; it is also where the Cloud Scheduler and
  Pub/Sub APIs get enabled when their first consumers land in Epic 2 B5 and
  Epic 4 4.3). Roles, each justified in the script:
  `roles/firebaseauth.admin` (users + claims), `roles/datastore.user`,
  `roles/logging.logWriter`, `roles/secretmanager.secretAccessor`,
  `roles/storage.objectAdmin` on the form-kits bucket only. Deferred to the
  epic that first needs them: `cloudbuild.builds.editor` plus
  `iam.serviceAccountUser` on the Cloud Build SA (to submit builds that run
  AS it), `run.admin` + `iam.serviceAccountUser` on `polyglot-backend-sa`
  (resource-scoped), `firebasehosting.admin` (Epic 4); `bigquery.jobUser` +
  dataset `bigquery.dataViewer`, `errorreporting.viewer`,
  `monitoring.viewer` (Epic 3). An unused grant is its own risk. Every grant
  lands in the setup script with a one-line justification AND in the role
  pin test, in the shape scar #7 demands.
- Gating: Cloud Run `--allow-unauthenticated` plus app-level checks on EVERY
  route. `admin_backend/services/admin_auth.py` mirrors
  `backend/services/editor_auth.py`: `APP_ADMIN_CLAIM = "app_admin"`
  (boolean), `require_app_admin` (dev bypass refused on `K_SERVICE`, then
  `verify_id_token`, 401 vs 403 split with a machine-readable
  `NO_ADMIN_ACCESS:` prefix). FOUR gates, and the set test enumerates four:
  `require_app_admin`; `require_firm_manager` (firm_role == manager,
  firm_id from the verified token only), which lives in
  `backend/services/auth.py` and REPLACES the inline manager check in the
  retire route (`backend/routes/form_kit_routes.py:490`) so the rule has one
  home (scar #8); `require_app_admin_or_owning_manager` (the composite for
  revoke and link listing: an app admin names the firm, a manager's firm
  comes from the token); and `require_google_oidc(audience,
  allowed_caller_emails)` for Cloud Scheduler / Pub/Sub push callers. Each
  ships with its FIRST consuming route (Epic 2 B-track, Epic 2 B5 / Epic 4
  4.3) so each is proven against a real route, never shipped untested. The
  OIDC gate checks the audience AND the token's `email` against the expected
  scheduler and push service-account identities: on a public service,
  audience alone is forgeable by anyone with a GCP project.
  `admin_backend/tests/unit/test_admin_route_auth.py` derives every
  registered route and asserts each carries exactly one of the four
  dependencies (set-derived like `backend/tests/unit/test_http_route_auth.py`).
  Firm-scoped routes take an explicit `channel` query param validated
  against the two channel names, because the admin service has no channel
  of its own.
- Staging tier for the admin service, decided here because the bash bridge
  and the Epic 4 target list depend on it: there is ONE admin service and
  ONE console site, so a bad admin deploy would take the control plane for
  both channels down. Every admin-service deploy lands as a Cloud Run
  revision with a tag and NO traffic (`--no-traffic --tag candidate`), is
  verified at the tagged URL (stable), then gets traffic shifted
  (`gcloud run services update-traffic --to-latest`). The console deploys
  to a SECOND PERMANENT Hosting site `polyglot-admin-candidate` first, then
  to the live site; a Hosting preview channel would not do (random-hash
  URLs that expire and change on recreation would churn Firebase Auth's
  authorized domains and the CORS allowlist on every candidate). Both
  steps are in the bash bridge now and become Epic 4 targets later.
- First deploy is a bash bridge `deploy-admin.sh` built on `deploy-all.sh`'s
  backend stage (`BACKEND_SERVICE_NAME=polyglot-admin`,
  `BACKEND_SERVICE_ACCOUNT=admin-backend-sa`, env `APP_MODULE`, the
  no-traffic tag + verify + shift sequence above), which keeps the
  reachability gate: the domain-restricted-sharing refusal documented in
  `docs/doctrine/promotion-tiers.md` bites a NEW service, and this is one.
  CORS via `parse_extra_origins` from `backend/config.py`.

### `app_admin` claim bootstrap

`scripts/bootstrap_admin_user.py` mirrors `scripts/bootstrap_editor_user.py`
(`--email`, `--revoke`, `--list`, `--project`, stamps an existing account,
merges claims rather than replacing them, refuses the dead project). It is
the only way to create the FIRST admin and stays the documented
operator-credential path; it is not a hole to close later.

### Append-only audit log

`admin_audit_log/{auto}`: `actor_uid`, `actor_email`, `action`, `target`,
`before`, `after` (metadata only), `channel` (nullable), `request_id`,
`state` (committed | pending | failed), `ts`. ONE helper
`admin_backend/services/audit_log.py`, unlike the fire-and-forget
confirmation sink. Ordering is what prevents a double grant (an operator who
sees a 500 retries):
- Firestore mutations (grants, adjustments, kit commercials, firm edits,
  revocations) write the audit row INSIDE the same transaction as the
  mutation, via `audit_log.record_in_transaction(tx, ...)`. Either both
  commit or neither does.
- Non-Firestore mutations (Auth user create/disable, claims, build
  triggers) write a `pending` row first, perform the action, then mark it
  `committed` (or `failed` with the error); a retry of a `pending` action
  is visible as such.
`test_admin_audit_coverage.py` walks every mutating route on the admin app
and asserts the Firestore routes call the in-transaction form and the
others follow the pending-then-committed form, not merely that some audit
call is present. Deny block in `firestore.rules`, pinned by extending
`test_firestore_rules_text.py` into ONE set-derived test over every
Admin-SDK-only collection.

### Runtime config (`app_config/{channel}`)

- Moves from deploy-time env to Firestore: `LINK_MINTING_ENABLED`
  (`backend/routes/link_routes.py`), `LINK_COST_CEILING_USD` and
  `LINK_FIRM_CAP` (`backend/services/link_budget.py`, whose docstring already
  names the console as the planned home), plus a NEW `CREDITS_ENFORCED`
  (default false) that Epic 2 reads to decide whether a zero balance refuses
  a mint. Later epics add alert thresholds.
  NOT moved: `LINK_TOKEN_SECRET` (Secret Manager), `LINK_BASE_URL`,
  `LINK_CHANNEL` (topology; moving them would reopen the isolation bd
  `polyglot-pdf-3q9qn` closed).
- One doc per channel so a new test can diff `app_config/staging` against
  `app_config/demo` with an explicit allowlist, mirroring
  `tests/test_deploy_channel_parity.py`.
- `backend/services/runtime_config.py`: `RUNTIME_CONFIG_KEYS` frozenset;
  unknown key ignored and logged. Fallback order when Firestore is
  unreachable or the key is absent: LAST-KNOWN-GOOD value from the previous
  successful read, then the env default only when nothing was ever read.
  Env-first would be wrong for the ceiling: a console that LOWERED
  `LINK_COST_CEILING_USD` must not see the higher env value come back
  during a Firestore blip. Minting's default is off either way. Module-level
  TTL cache (30 to 60 s) keyed by channel, explicitly NOT `get_settings()`
  (lru_cached for the process lifetime). Call-site swap at the four
  `os.getenv` reads; the public backend reads Firestore directly, no HTTP to
  the admin service. Pinned by a test that lowers the ceiling, breaks the
  read, and asserts the lowered value survives.

### `/version` with the git SHA

The EXISTING `GET /version` (`backend/main.py:141`, returns only
`app.version` today) is extended to `{"version", "git_sha"}` read from the
`GIT_SHA` runtime env var; the admin service gets the same route. The bash
bridge sets `GIT_SHA=$(git rev-parse HEAD)` at deploy time until Cloud
Build's `$COMMIT_SHA` takes over in Epic 4. The admin console gets the same
value via a Vite define. Ships here because every later "what is live" view
depends on it.

### Console app (`admin-console/`, Hosting site `polyglot-admin-demo`)

Mirror `schema-editor/`: `vite.config.ts` (including the worktree
`fsAllowList` fix and the `.claude/worktrees` watch exclusion, which are
facts of this repo), `schema-editor/src/components/SignInGate.tsx` (Firebase
sign-in, then a server-side role probe, explicit not-authorized screen, no
self-serve signup), `VITE_ADMIN_API_BASE_URL` resolved at deploy time from
the live Cloud Run URL like `deploy-editor.sh` does,
`deploy-admin-console.sh` labelled as a bash bridge Epic 4 supersedes. Two
`firebase.json` hosting entries (`admin` -> `polyglot-admin-demo`,
`admin-candidate` -> `polyglot-admin-candidate`) with NO `/api` rewrite (the
Hosting rewrite has a 60 s cap; deploy triggers are long requests) and the
matching `.firebaserc` targets, with the one-time
`firebase hosting:sites:create` + `target:apply` + Auth authorized-domain
steps in the script header. The admin service's CORS allowlist carries both
admin sites AND both channels' app origins (the main app's firm-manager
pages call it too). Skeleton pages: sign-in, "who am I", audit log list,
app_config editor per channel.

### Exit criteria

1. An account stamped by `bootstrap_admin_user.py` signs into the console
   and calls one real admin route end to end; an unstamped account sees an
   explicit not-authorized screen.
2. `test_deployed_iam_envelope.py` passes UNCHANGED and the admin SA role
   pin test exists and passes.
3. Every mutating admin route writes exactly one audit row, pinned by the
   coverage test, and a real mutation shows a readable row.
4. Flipping `LINK_MINTING_ENABLED` in `app_config/staging` changes
   `/api/links/mint` on staging within the TTL with no redeploy.
5. `GET /version` on both deployed services returns a real SHA.
6. An admin-service deploy lands as a no-traffic tagged revision, is
   verified at the tag URL, and only then receives traffic; the console
   deploys to the candidate site before the live site.

### Beads and order

1.1 admin package skeleton + Dockerfile `APP_MODULE` env + admin SA pin test
-> 1.2 `app_admin` claim + bootstrap script + route-auth set test -> {1.3 SA
+ setup script + first deploy as a tagged no-traffic revision with the
reachability gate, 1.4 audit log (in-transaction + pending forms) +
coverage test + rules block, 1.5 runtime config (incl. `CREDITS_ENFORCED`) +
call-site swap + parity test, 1.6 `/version` SHA on both services} in
parallel -> 1.7 console skeleton + sign-in gate + live and candidate
Hosting sites + bash bridge. Docs: add the two new contracts (app_config
producer/consumer; audit log) to `docs/technical_guide.md`'s Surface
contracts map in the bead that lands each.

### Planner decisions (reversible)

One Dockerfile with a runtime `APP_MODULE`; boolean `app_admin` claim;
`admin_backend` and `admin-console` names; site `polyglot-admin-demo`;
tagged-revision + preview-channel staging for the admin tier;
`check_revoked` stays off on the admin verifier until someone measures the
latency cost of turning it on.

## Epic 2 -- Firms, users, credits, form commercials, link tracking

Depends on Epic 1 for `require_app_admin`, `require_firm_manager(firm_id)`,
and the audit helper (Track B below); Track A runs in the PUBLIC backend and
needs none of them, so it starts immediately. The one Track A dependency on
Epic 1 is bead 1.5 (runtime config, public-backend only), which A3 reads for
the `CREDITS_ENFORCED` gate.

### Data model (all Admin-SDK-only; every new collection gets a client deny
block in `firestore.rules`, pinned by extending
`backend/tests/unit/test_firestore_rules_text.py`)

- `firms/{firm_id}` gains `kind: "mock"|"live"` (required on create;
  migration default `live` because a mis-defaulted mock firm merely blocks
  staging while a mis-defaulted live firm mints for free; a doc with NO
  `kind`, in the window between the code deploy and the backfill, is
  treated as `live` by the gate for the same reason;
  `scripts/bootstrap_firm.py` gains a required `--kind`, and local minting
  needs the dev account's firm created with `--kind mock`),
  `balance_credits: int` (materialized; written ONLY by the one
  transactional ledger helper), `balance_updated_at`. The balance is NOT
  channel-partitioned: one firm, one balance, whichever channel debits it.
  That is safe only because live firms cannot mint outside the demo channel
  and mock firms carry no real money.
- `firms/{firm_id}/ledger/{auto}`: `type` in subscription_grant | purchase |
  promo_grant | mint_debit | expiry_refund | adjustment; signed `amount`
  (credits); `usd_amount` (nullable: the price paid, set on purchase and
  subscription_grant, null on promo, debit, refund, adjustment, so income is
  recorded from day one and Epic 5 needs no migration); `firm_kind`
  (snapshot of the firm's `kind` at write time: the income view filters on
  it, because the admin service that writes grants has no channel);
  `channel` (nullable: filled by the public backend's debits, null for
  admin-service writes); `balance_after`; `actor` (uid or
  `system:<origin>`, never blank); `reason` (required for adjustment);
  `link_jti`, `kit_id` where relevant; `ts`. Invariant:
  `balance_credits == sum(amount)`, enforced by construction and pinned by a
  replay test.
- `kits/{kit_id}` commercial doc: `credit_cost: int`, `burn_cap_usd: float`,
  `display: {label,...}`, `updated_by`, `updated_at`. Missing doc or
  malformed value resolves to the global defaults with the same defensive
  parsing `backend/services/link_budget.py` already uses (a bad edit must
  never remove a form's ceiling).
- NEW `links[_<channel>]/{jti}` mint record (channel-suffixed exactly like
  `link_redemptions`): firm_id, kit_id, employee_id, `credit_cost` and
  `cap_usd` snapshots, `minted_at`, `open_deadline` (== token exp, stored so
  the sweep can query it), `status` in minted | opened | completed |
  refunded | revoked | budget_exhausted, `revoked_by`/`revoked_at`, and an
  `expire_at` timestamp for a Firestore TTL policy (set to open deadline
  plus the completion window plus a retention margin; the admin console
  reads history from BigQuery beyond that). `alerts` gets the same TTL
  field; `admin_audit_log` and `deployments` are kept. The TTL policies are
  created in the setup script (`gcloud firestore fields ttls update`). Kept
  SEPARATE from `link_redemptions` so the load-bearing "no redemption doc
  until first open" invariant is untouched. `status` is a DERIVED CACHE for
  listing and never decides money: the refund transaction reads the
  redemption doc (below), and `opened`/`completed` are best-effort mirrors
  written from the open route and `complete_link`'s caller. The sweep
  writes `refunded`; an admin or firm-manager revoke route writes
  `revoked`; socket teardown on `LinkBudgetExhausted` writes
  `budget_exhausted` (telemetry only, no ledger entry, pending the
  maintainer call below).
- Channel becomes an explicit argument (A1): `link_redemptions.py`'s
  `_collection_name()` and the new `links` helpers take `channel`; the
  public backend passes `link_channel()`, the admin service passes the
  channel it is acting on. The admin service sets no `LINK_CHANNEL`.
- Fold-in: `link_redemptions[_<channel>]` has NO rules block today. Add it
  while the rules test is being extended.

### Mint transaction (public backend, new `backend/services/credit_ledger.py`)

One shared `@firestore.transactional` helper "append ledger entry + update
balance" used by mint_debit, expiry_refund, and every admin grant/adjustment
(one implementation of the invariant, not several). It is SYNC on the Admin
SDK client, so every caller on an async path runs it under
`asyncio.to_thread`, as the mint route already does for its Firestore reads.

Order in `mint_link` (`backend/routes/link_routes.py`): reserve BEFORE
signing, so a refused mint never leaves a signed token that would open.
1. Generate the jti (`link_tokens` gains a `new_jti()` and
   `mint_link_token(..., jti=...)` accepting a caller-supplied id).
2. Transaction: read firm + kit docs -> refuse `403` when the firm is `live`
   (or has no `kind`) and the RAW `LINK_CHANNEL` env var is not exactly
   `demo`. This gate deliberately does NOT call `link_channel()`, whose
   default is `demo`: an unset channel keeps minting tokens with
   `aud=demo` (today's behaviour, on purpose) while refusing live firms,
   and a test pins both halves of that. -> if
   `CREDITS_ENFORCED` (app_config, default false) refuse `402 Payment
   Required` when `balance < credit_cost` (staff-facing, so a clear status,
   unlike the client-facing uniform 404); when enforcement is off the debit
   is still written and the balance may go negative, which is the metered
   soft-launch mode until seeds are granted -> write balance, ledger
   `mint_debit`, and the `links/{jti}` record atomically.
3. Sign the token with `cap_usd` and return.
Firestore optimistic concurrency serializes a double-mint race; the loser
re-reads and refuses. `record_mint` (monthly count) keeps running unchanged
after commit; it answers a different question (count per month for the
allowance signal) and is not deleted in this epic. No Firestore transaction
exists anywhere in the codebase today; this is the first, so the helper
carries the reads-before-writes rule in its docstring.

### Open requires a mint record (adds revocation)

`POST /api/links/open` (and the socket's paid gate, through the shared
`enforce_link_redemption` path) reads `links[_<channel>]/{jti}` and refuses
with the uniform 404 when the record is missing or its status is `revoked`
or `refunded`; every other status falls through to the existing redemption
gate (reopen of an unfinished link stays allowed). One read on a path that
already writes, and it buys `POST /admin/links/{jti}/revoke` (app admin, or
the owning firm's manager; audited in-transaction) which a firm manager
will ask for. Consequence: tokens minted BEFORE the record existed cannot
open. That is a deliberate one-time cutover (there are few or no live
client links today, the same reasoning the `aud` claim cutover used) and
the maintainer re-mints any outstanding link; it is listed in the
maintainer calls.

### Per-link cap in the token (closes bead polyglot-pdf-4tjt7)

Payload gains `cap_usd`; `backend/tests/unit/test_link_tokens.py`'s exact-set
tripwire is widened deliberately with a docstring note. The kit's
`burn_cap_usd` is resolved ONCE, at mint, and signed in. New
`link_budget.cost_ceiling_usd_for_claims(claims)`; precedence at the socket
is token `cap_usd` > `LINK_COST_CEILING_USD` and nothing else: because open
now requires a mint record, every token that can open carries `cap_usd`, so
a per-connect kit read would be a Firestore read for a case that cannot
occur. The global is a defensive default (a ceiling, never none), not a
compatibility path. `websocket_routes.check_budget` is called with the
resolved ceiling (today it passes nothing, so the global applies
everywhere). `metadata.json`'s `link_cost_ceiling_usd` becomes vestigial:
stop reading it, do not delete it from published kits in this epic.

### Refund on unopened expiry

Both mechanisms share one transactional refund helper. Inside the
transaction it reads the AUTHORITATIVE first-open record
`link_redemptions[_<channel>]/{jti}` and refuses to refund when it exists
(the client opened the link; a failed best-effort `opened` mirror must never
cause a refund of a link someone is filling), then reads `links/{jti}` and
proceeds only from `minted`; a re-run sees `refunded` and no-ops, and a
concurrent sweep-vs-lazy race serializes on the same docs. (i) Cloud
Scheduler -> admin-service `POST /admin/links/sweep-expired` (hourly; runs
per channel with the channel passed explicitly, queries
`status == minted AND open_deadline < now`); (ii) lazy, best-effort,
firm-scoped reconciliation ONLY on admin-service and firm-console balance
reads, run as its own transaction before the read, so a dead scheduler
cannot leave a balance visibly wrong. It is never part of the mint
transaction: that is the hottest transaction and already reads the firm
doc; adding a query to it buys contention for nothing. Cloud Scheduler is a
new small dependency (enabled in Epic 1's setup script when B5 lands).

### Admin-service routes (Epic 1 gates; every mutation audited)

- Firms: `POST /admin/firms` (kind required), `PATCH .../status`,
  `PATCH .../allowed_kits`, `PATCH .../kind` (reason required).
- Users: `POST /admin/users` (create by email + firm + role via
  `firebase_admin.auth.create_user` + claims merge, reusing
  `scripts/bootstrap_firm.py`'s merge-not-replace logic; returns a password
  reset link for the console to display, no outbound email in this epic),
  `PATCH /admin/users/{uid}/disable`, `PATCH .../role`,
  `GET /admin/users?firm_id=` (list_users + client-side claims filter; the
  pool is staff, editors, and devs only, since clients never get accounts,
  so no members mirror is needed). These routes accept BOTH actors under
  the composite gate, as bd `polyglot-pdf-gob8l` shipped firm-admin
  employee management: for a manager the firm_id comes from the token and
  the body may not name one; for an app admin it comes from the body.
  CLAIMS ALLOWLIST: these routes write only `firm_id` and `firm_role`, never
  `app_admin`, `schema_editor_role`, or `vff_dev`; `app_admin` is set only
  by the bootstrap script. Pinned by a test that covers both actors.
- Credits: `POST /admin/firms/{id}/credits/grant` (type in
  subscription_grant | purchase | promo_grant; `usd_amount` required for the
  first two), `POST .../credits/adjust` (reason required).
- Kits: `GET`/`PUT /admin/kits/{kit_id}/commercial`.
- Links: `GET /admin/firms/{id}/links?status=&employee_id=` joining
  `links` with `link_redemptions` for spend/opened/completed; the same route
  serves firm managers under `require_firm_manager` with firm_id from the
  token. `POST /admin/links/{jti}/revoke` (app admin, or the owning firm's
  manager).
- Mock/live: grants to mock firms allowed (staging needs credits to test)
  but visually flagged; `kind` changes are confirm-twice in the UI.

### Frontend

- Admin console (Epic 1 shell): kit commercials page first (smallest), then
  firms list/detail with ledger + links, then users.
- Main app `/console/*` beside `MintLinkPage.tsx`: `/console/employees`
  (manager-only; firm_id from the verified token, never the request) and
  `/console/links/history` (manager sees the firm's links; an employee sees
  ONLY links whose `employee_id` equals their own uid, with both firm and
  employee taken from the verified token; the response is an explicit key
  allowlist so future internal fields on the link record never leak to the
  employee role).

### Migration (`scripts/backfill_firm_kind.py`, `scripts/seed_kit_commercials.py`)

Firms: `kind=live` unless named in an explicit `--mock` allowlist;
`balance_credits=0` plus an optional `--seed-credits N` grant entry. Kits:
`burn_cap_usd` from the metadata key where present (w7 and i-90 carry $3),
else the global default; `credit_cost` from a REQUIRED
`--default-credit-cost N` (no pricing signal exists to derive one).

### Tests to pin

1. `test_ledger_balance_invariant_holds_after_replay` (balance and each
   `balance_after` match the running sum).
2. `test_mint_refuses_at_zero_balance` (no ledger entry, no link record).
3. `test_mint_transaction_double_mint_race_is_safe` (exactly one succeeds,
   final balance exactly 0).
4. `test_expiry_refund_is_idempotent`.
5. `test_cap_usd_precedence_at_socket_connect` (the bead-4tjt7 closer).
6. `test_live_firm_mints_only_on_explicit_demo_channel` over all eight
   cases: channel in {demo, staging, unset} x kind in {mock, live}, plus
   {demo, unset} x missing-kind; and
   `test_unset_channel_still_mints_demo_audience` (the gate and
   `link_channel()` disagree about "unset" on purpose).
7. rules deny blocks for every new collection + the missing
   `link_redemptions` ones.
8. `test_every_mutating_admin_route_calls_audit_log` (set-derived from the
   admin router; Firestore routes must use the in-transaction form).
9. `test_employee_link_listing_response_is_allowlisted` and
   `test_employee_history_scoped_to_token` (an employee never sees another
   employee's links; ids come from the token, not the query).
10. `test_refused_mint_leaves_no_openable_token` (402 path: no signed
    token is returned and no record exists).
11. `test_open_refuses_without_mint_record` and
    `test_revoked_link_cannot_open` (uniform 404).
12. `test_refund_refuses_when_redemption_exists` (an opened link is never
    refunded, even with the `opened` mirror missing).
13. `test_user_routes_write_only_firm_claims`.
14. `test_credits_enforced_flag_gates_refusal` (off: debit written, balance
    may go negative; on: 402).

### Exit criteria

1. With enforcement on, a zero-balance firm cannot mint and no token is
   signed; a funded firm's mint debits exactly `credit_cost` with the ledger
   entry and link record written atomically before signing.
2. An unopened link past its open deadline is refunded exactly once, via
   sweep, lazy path, or both racing; an opened link is never refunded.
3. A client socket's spend ceiling is the value signed into its own token,
   shown live for a kit whose `burn_cap_usd` differs from the global.
4. A live firm mints only on the explicit demo channel (all six cases); a
   revoked link cannot open.
5. Every new collection has a deny block; every mutating admin route audits
   in the required form.

### Beads and order

- P0 (independent, anytime): bd `polyglot-pdf-6p77c`, one runtime catalogue
  source (`/api/form-kits`), so a priced kit is the kit the app serves.
- Track A (public backend, starts now): A1 schema + rules + explicit
  `channel` argument on the redemption and links helpers -> {A2 ledger
  service + transactional helper + `scripts/grant_credits.py` (operator CLI
  on the same helper, so credits can be granted and rolled back before the
  console exists), A4 cap_usd + precedence} in parallel -> A3 wire mint
  route (reserve-then-sign, `CREDITS_ENFORCED` gate, live-only-on-demo) +
  open-requires-record -> A5 refund helper + lazy path -> A6 migration
  scripts. Enforcement is switched on per channel through `app_config` only
  after A6 has seeded balances.
- Track B (admin service, after Epic 1): B1 firm CRUD + grants, B2 users, B3
  kit commercials (parallel) -> B4 link listing -> B5 sweep endpoint +
  Cloud Scheduler; audit wiring lands with each route via a shared
  dependency, not at the end.
- Track C (UI, each behind its route): C0 main-app wiring (`deploy-all.sh`
  resolves `VITE_ADMIN_API_BASE_URL` the way it resolves `VITE_WS_URL`; the
  firm-console pages send the app's own channel as the `channel` query
  param; `MintLinkPage.tsx` learns the new 402 and 403 responses), C1 kit
  commercials, C2 firms + ledger, C3 users, C4 firm-console employees, C5
  link history.

### Decisions taken by the planner (reversible, listed for the merge report)

402 for insufficient balance; collapse `expired_unopened` into `refunded`;
existing firms default `kind=live`; keep `record_mint` alongside the ledger;
no outbound email in this epic (invite links are shown in the console); a
live firm mints only when `LINK_CHANNEL` is explicitly `demo` (an unset
local channel refuses live firms).

### Maintainer calls needed before the marked beads ship

- A5: does a budget-exhausted link refund, and does a replacement link
  (bd `polyglot-pdf-1uyof`) cost a fresh credit? Recommendation: no refund,
  replacement costs a credit (the ceiling protects margin; a free
  replacement loop bypasses it). Until decided, `budget_exhausted` is
  telemetry only.
- A5: an OPENED but abandoned link is not refunded (the client used the
  paid session). That is a pricing choice and sits here beside the previous
  one; the plan assumes no refund.
- A3: the open-requires-record cutover refuses tokens minted before the
  record existed; the maintainer re-mints any outstanding link at cutover.
- A6: the seed-credit grant for existing firms and the default credit cost
  per kit. Both are pure pricing.
- Doc change: `docs/doctrine/promotion-tiers.md` says firm-billing isolation
  "rests on staging using its own mock firm, not on code"; A3 makes that
  false and the prose changes with it.

## Epic 3 -- Telemetry, monitoring, alerts

Two layers: Firestore rollups at session end for live views and alerts;
Cloud Logging -> BigQuery sink plus the Cloud Billing export for historical
cost and cost-vs-income. Errors go through Cloud Error Reporting and
Monitoring, not a hand-built tracker.

### Usage event v2 (one shape for every paid call)

- `backend/utils/structured_logger.py` gains a private `_emit_usage(...)`
  with three thin wrappers: `log_gemini_api_response` (existing name kept),
  `log_text_ai_usage`, `log_tts_usage`. Envelope gains optional `firm_id`,
  `employee_id`, `link_jti`, `kit_id`, `channel`, `model`, and a closed
  `usage_kind` literal in `backend/utils/log_schemas.py`: live_voice |
  text_secretary | text_validator | text_translation | tts_spellback |
  tts_notice | tts_intro. Every wrapper emits the full key set (values may
  be None) so BigQuery sees one column shape.
- Live path plumbing: `websocket_routes.py` already holds `kit_id`,
  `firm_id`, `link_jti`, `link_employee_id` as locals in
  `fill_form_from_schema` but passes only kit_id + firm_id into
  `FormFillingService.start_session`; widen that call and
  `LiveAIGemini.set_session_context(...)` (~line 778) with the five ids,
  channel from `link_tokens.link_channel()`. No contextvar: one adapter per
  socket already IS the session.
- Text path: `TextAIGemini` is a per-process singleton
  (`backend/dependencies.py`), so session ids must NOT live on `self` (they
  would leak across concurrent sessions). Add an optional `session_ctx`
  kwarg to `validate/ask/translate_*` -> `_generate` -> `_log_usage`;
  callers in `form_filling_service.py` and `validator_service.py` pass it.
  Translation bake at authoring time legitimately has kit_id only.
- TTS path: `backend/routes/tts_routes.py` has the claims dict from its
  auth dependency; the three synthesize services emit `tts_usage` with
  character counts and claims ids. No `form_session_id` exists on an HTTP
  route; say so in the schema rather than fake one.
- Pricing: new `TEXT_GENERATION_PRICING` (2.5-flash, 2.5-flash-lite:
  input / cached / output per 1M) and `TTS_PRICING_USD_PER_CHAR` (by tier;
  Chirp3-HD today) in `backend/config.py`. The Live table does NOT transfer
  to the plain generate_content endpoint. Numbers are verified against the
  live pricing pages at write time and dated, like the existing rows.
- Test: `backend/tests/test_usage_event_coverage.py` AST-enumerates every
  `generate_content` / `aio.live.connect` / `synthesize_speech` call site
  under `backend/` (exclusion-derived like the IAM test), pins the allowlist,
  and proves each site reaches `_emit_usage` with a valid `usage_kind`.

### Session-end Firestore rollups (`backend/services/usage_rollups.py`)

Written from the same teardown block in `websocket_routes.py` that runs
`log_form_session_end` and `_bank_link_spend`, best-effort, never raises.
`firms/{firm_id}/usage/{YYYY-MM}` and `kits/{kit_id}/usage/{YYYY-MM}` with
`firestore.Increment` on dotted paths: `connections_ended` (honest name: the
session-end event fires per CONNECTION), `sessions_completed`,
`links_opened` (from the open path), `links_completed`, `cost_usd_total`,
`by_kit.{kit_id}.{sessions,cost_usd}`, `by_employee.{uid}.{...}`,
`by_language.{code}.{...}`, `by_firm` on the kit doc, plus `kind` copied
from the firm (mock|live, the Epic 2 field) and `channel`. Map keys such as
`i-90` and `zh-CN` contain hyphens, which break dotted string field paths:
build every nested increment with `firestore.FieldPath(...)` objects (or
sanitize keys through one shared function), pinned by a test that
increments a hyphenated key. by_employee keys on the link's employee_id or
the staff uid, whichever exists. No sharding now: 1 write/s/doc is only hit
by many sessions ending in one second, and the existing counters use the
same pattern; sharding is the documented escape hatch. The per-turn event
stays as the fine-grained source.

### Alerts

- `alerts/{id}` with deterministic ids for dedup:
  `link_exhausted_{jti}` written from `link_spend.check_budget`'s refusal
  branch; `{firm_id}_credit_low_{day}` and `{firm_id}_credit_exhausted_{day}`
  written by the Epic 2 ledger debit helper after the balance changes.
  Fields: firm_id, kind, level, ts, context (metadata only), acknowledged_by,
  acknowledged_at, emailed_at.
- Email is SENT by the admin service on a schedule (Cloud Scheduler ->
  `POST /admin/alerts/dispatch`, gated by `require_google_oidc` with the
  scheduler SA's email pinned), never by the public backend: the outbound
  provider call must not sit on the socket connect path, and the admin
  service already holds the wider secrets. Provider assumed Postmark; the
  choice is a maintainer call recorded below.

### BigQuery

- Dataset `polyglot_telemetry` in us-central1. Logging sink over both Cloud
  Run services filtered to `jsonPayload.event_type` in the usage, session,
  ledger_export, and error set; tables partitioned by timestamp.
- Views: `cost_by_firm_month`, `cost_by_kit_month`,
  `cost_by_employee_month`, `hosting_cost_by_service_month` (billing export
  filtered to Cloud Run + Hosting SKUs, split by service name so staging
  hosting never mixes with demo), and `income_month` (ledger entries of kind
  purchase | subscription_grant summing `usd_amount`, with
  `WHERE firm_kind = 'live'` hard-coded in the view, not left to callers).
  Income cannot filter on channel: the admin service that writes grants has
  none; the firm's kind, snapshotted on the entry, is the test-vs-real line.
  Cost views keep `channel` and `kind` both available.
- Income reaches BigQuery by a `ledger_export` structured log line emitted at
  ledger write time through the same sink, carrying `type`, `amount`,
  `usd_amount`, `firm_id`, `firm_kind`, `channel`, `link_jti`. No Firestore
  export extension, no nightly job. This is a one-line ask on Epic 2's
  ledger helper.
- The Cloud Billing export must be enabled by the maintainer in the Billing
  console (billing-account permission; not automatable here) and is NOT
  retroactive: hosting cost history starts the day it is switched on.
- IAM: admin SA gains `bigquery.jobUser`, `bigquery.dataViewer` on the
  dataset only, `errorreporting.viewer`, `monitoring.viewer`; the logging
  sink's writer identity (returned by `gcloud logging sinks create`) gets
  `bigquery.dataEditor` on the dataset or nothing lands. All in
  `scripts/setup-monitoring.sh` with justifications and in the role pin
  tests.

### Errors

- A P0 PII decision constrains this: production paths in
  `backend/adapters/live_ai_gemini.py` deliberately avoid `_log.exception`
  because `format_exc_info` renders the exception MESSAGE, which can embed a
  field value (line ~3012, bd `polyglot-pdf-p84m`); other sites in the same
  file still call it. So: enumerate every `_log.exception` and
  `exc_info=True` site under `backend/` (set-derived test), and route all of
  them through ONE processor that emits the exception TYPE and the FRAMES
  (file, line, function; no locals, no message) in the Cloud Logging shape
  Error Reporting groups on, with uppercase `severity`. The red test asserts
  BOTH "frames present" and "message absent" for an exception whose message
  contains a sentinel. `test_no_pii_logging.py` gains the sentinel case.
- Wire the unwired `StructuredLogger.log_error` for the WS close-code family
  (1011/1006, 1007, 1013, 1008) as structured non-exception events.
- `scripts/setup-monitoring.sh` (new sibling of `setup-gcp-project.sh`):
  log-based metrics `ws_close_1011_count`, `ws_close_1013_count`,
  `mint_refused_count`; alert policies on 5xx rate and 1011 rate; an uptime
  check per channel on `/health`. Operator-run, declared for repeatability.
- Wire `firms_store_status()` into `/health` (closes bd `polyglot-pdf-vq5wd`).

### Console views (Epic 1 shell)

Per-firm usage this month (Firestore rollups); cost by firm / form /
employee over a month range (BigQuery); alerts list with acknowledge
(Firestore); errors per channel (Error Reporting `groupStats`); health per
channel (`/health` + `/version` on each service). Sink lag is seconds to
minutes, so the BigQuery views are labelled as delayed in the UI.

### Tests to pin

1. `test_usage_event_coverage.py` (every paid call site emits).
2. `test_usage_event_schema.py` (every usage_kind carries the full key set).
3. `test_usage_rollups.py` (staff vs link attribution, completed vs
   abandoned, kind propagation).
4. `test_alerts_dedup.py` (second refusal on the same jti writes nothing).
5. `test_channel_on_every_event.py` (every emitter added here carries
   channel).
6. structlog exception-shape test (red before the fix, green after).
7. `test_admin_sa_iam_envelope.py` (owned by Epic 1; extended here with the
   BigQuery / Error Reporting / Monitoring roles).

### Exit criteria

1. Every enumerated paid call site emits a `usage_kind`-tagged event with
   firm, employee, link, kit, channel, and model ids.
2. A finished voice session writes one batched increment to the firm and
   kit month rollups with correct staff-vs-link attribution.
3. A link hitting its ceiling produces exactly one alert doc, and a firm
   crossing a credit threshold produces at most one per kind per day.
4. An unhandled adapter exception appears in Error Reporting as a grouped
   error carrying type and frames, and its message text appears nowhere in
   Cloud Logging.
5. The income view cannot return mock-firm entries: the `firm_kind = 'live'`
   filter is in the view definition and pinned by test, and a hyphenated
   kit or language key increments correctly in the rollups.

### Beads and order

1 usage-event-v2 schema + pricing + coverage test -> {2 live plumbing, 3
text/TTS plumbing, 5 link-budget alert, 6 BigQuery sink + views, 8 error
reporting + monitoring script} in parallel -> 4 rollups (after 2) -> 7
billing-export setup (maintainer console step, after 6) -> 9 credit alert
hook + 10 ledger_export line (after Epic 2's ledger helper) -> 11 console
views (after Epic 1 shell).

Roadmap beads: 0bs (BigQuery) and nt0 (dashboard) are implemented here and
close with it; g0e is superseded (close with a pointer, after checking its
frontend half); ytf's error half lands here, its field half stays blocked on
3ae; 3ae and yqg stay open, with yqg re-pointed at this sink.

### Maintainer calls

- Email provider (Postmark assumed).
- Enable the Cloud Billing export in the Billing console.
- The two pricing tables' numbers are verified, not typed from memory.

## Epic 4 -- Deploy control plane

### Cloud Build layout

- Every build runs FROM GIT, never from a tarball. `gcloud builds submit`
  uploads the local tree, and `.gcloudignore` excludes `frontend/`,
  `schema-editor/`, and `landing/`, so a tarball build cannot build the
  site targets at all, `$COMMIT_SHA` is empty, and a dirty tree would
  deploy uncommitted code under a clean SHA that `build_checks/{sha}` then
  vouches for. Both the wrappers and the admin service trigger the build
  through the 2nd-generation Cloud Build GitHub connection at an explicit
  commit; the wrappers use `git rev-parse HEAD` and REFUSE a dirty or
  unpushed tree. The GitHub connection is therefore a prerequisite of 4.1,
  not 4.3.
- One root `cloudbuild.yaml`, substitutions `_TARGET`, `_CHANNEL`, `_SHA`.
  Targets: `backend-staging`, `backend-demo`, `frontend-staging`,
  `frontend-demo`, `editor`, `form-kits`, `firestore-rules`,
  `admin-service`, `admin-console`, optional `landing`. Each target's steps
  do what the matching `deploy-all.sh` stage does today: docker build + push
  (the build IS the Cloud Build step now), `gcloud run deploy` for backend
  targets, `npm ci && npm run build:<mode>` then
  `npx firebase-tools deploy --only hosting:<target>` for site targets,
  `firebase deploy --only firestore:rules`, and the status-complete kit upload
  + validated `index.json` for `form-kits`.
- The frontend build resolves the live backend URL in an earlier step of the
  same build and hands it forward through the shared workspace (substitutions
  are fixed at trigger time). Node 22 matches CI. `firebase-tools`
  authenticates through the build SA's ADC.
- Per-channel config leaves bash: `deploy/channels/staging.env` and
  `deploy/channels/demo.env`, plain `KEY=value` data with three sections
  (`SET_ENV_VARS`, `SET_SECRETS`, `SERVICE_ACCOUNT`), each mapped to its own
  `gcloud run deploy` flag. `SERVICE_ACCOUNT` becomes explicit and versioned
  for the first time. `tests/test_deploy_channel_parity.py` is rewritten as a
  line diff of the two files with the existing `CHANNEL_SPECIFIC` allowlist,
  retiring its bash-regex parsing.
- Gates that move INTO the build: a `verify` target runs the backend +
  frontend + admin suites ONCE per SHA and records `build_checks/{sha}` in
  Firestore (status, timestamp, build id); every deploy target's first step
  requires that record for its SHA and fails without it, so five targets per
  SHA pay one test run, not five. The reachability gate is ported once to
  `scripts/verify_service_reachable.py` and called from both the build and
  the remaining bash (no third hand copy;
  `tests/test_deploy_reachability_gate.py` exists because of the second).
  The kits `index.json` validation runs in the `form-kits` target. NOT in
  the build: the voice harness (real Gemini, real audio); it stays a
  pre-promotion human/agent step.
- The staging-before-demo gate lives IN THE BUILD, not only on the admin
  route: the demo targets' first step queries `deployments` for a successful
  staging record of the same family and SHA and fails the build without one.
  A bash-triggered build therefore cannot bypass it. To avoid racing the
  webhook, each staging target's LAST step writes its own success row to
  `deployments` (the build SA has `datastore.user`); the webhook still
  records every build, including bash-triggered ones, and reconciles by
  build id. The admin-route check stays as the early, friendly refusal.
- Admin-tier targets: `admin-service` deploys a tagged no-traffic revision,
  verifies it, then shifts traffic; `admin-console-candidate` deploys the
  candidate site and `admin-console` the live site (the Epic 1 bash-bridge
  sequence, moved into the build).
- Cloud Build SA `polyglot-cloudbuild-sa` (dedicated, not the legacy
  default): `run.admin`, `iam.serviceAccountUser` on the two runtime SAs
  (resource-scoped), `firebasehosting.admin`, `firebaserules.admin` (the
  `firestore-rules` target), `storage.objectAdmin` on the kits bucket,
  `artifactregistry.writer`, `logging.logWriter`, `datastore.user` (writes
  `build_checks`, reads `deployments` for the gate); pinned by a role test
  like the others. Moving images from `gcr.io` to Artifact Registry is a
  separable note.

### Triggering and status from the admin service

- The repo is PRIVATE, so building an arbitrary SHA from the API needs the
  2nd-generation Cloud Build GitHub connection already required by 4.1 (a
  one-time OAuth step only the maintainer can do; listed below) or git
  credentials for a plain source. Once the connection exists either
  mechanism works:
  `triggers.run` with a `RepoSource` carrying the SHA (the CLI's `--sha`),
  or `builds.create` with the connected repo at that revision.
  `admin_backend/services/cloud_build.py` uses `builds.create` for the
  simpler request shape; that is a preference, not a constraint. The admin
  SA gains `cloudbuild.builds.editor` and `iam.serviceAccountUser` on the
  Cloud Build SA here (a build submitted to run AS that SA needs actAs).
- Status arrives by Pub/Sub: the `cloud-builds` topic pushes to
  `POST /api/deploys/webhook` on the admin service, gated by
  `require_google_oidc` with the push subscription's SA email pinned (Epic 1
  auth module; this may be its first consumer or Epic 2's sweep is). The
  Pub/Sub service agent needs `iam.serviceAccountTokenCreator` to mint that
  OIDC token. No polling.
- `deployments/{id}`: `target`, `target_family`, `channel`, `sha`, `ref`,
  `triggered_by`, `build_id`, `status` (queued | working | success | failure
  | cancelled), `log_url`, timestamps. Deny block + rules test.
- Staging-before-demo predicate, extracted as a pure function
  `admin_backend/services/promotion_gate.py::staging_verified(target_family,
  sha, deployments)`: a demo build for `(family, sha)` is allowed only if a
  `deployments` record exists with channel staging, same family, same sha,
  status success. No recency rule: a newer staging deploy does not
  invalidate an older verified SHA, because that is the rollback case.
  `test_demo_promotion_gate.py` proves both directions through the real
  route for at least one case.
- Bash retirement: `deploy-all.sh`, `deploy-staging.sh`, `deploy-demo.sh`,
  `deploy-editor.sh`, `deploy-admin.sh`, `deploy-admin-console.sh` become
  thin wrappers around `gcloud builds submit --config=cloudbuild.yaml
  --substitutions=...`, so the human path and the console path are one
  engine. Deletion is a later call.
- `docs/doctrine/promotion-tiers.md` and
  `docs/components/config-deployment.md` are rewritten in the bead that
  lands the wrappers: deploy is no longer local and manual.

### Exit criteria

1. A human-run `verify` then `backend-staging` build for one SHA runs the
   suites once, builds, deploys, and passes the reachability gate end to
   end; a second target for the same SHA does not re-run the suites.
2. The admin service triggers the same build by SHA, receives the Pub/Sub
   status, and the `deployments` record shows success with the real
   build id; a bash-submitted build for another SHA also appears there.
3. A demo build for a SHA with no staging success FAILS IN THE BUILD (log
   shows the gate step), whether submitted from the admin route or from
   bash; `test_demo_promotion_gate.py` proves the predicate both ways and
   the route refuses early.
4. A deliberately broken test fails the `verify` build, and every deploy
   target for that SHA refuses to run.
5. `deploy-staging.sh` still works as a thin wrapper over the same
   pipeline.

### Beads and order

4.1 GitHub connection (maintainer) + `cloudbuild.yaml` + `verify` +
`backend-staging` targets built from git + `deploy/channels/*.env` +
rewritten parity test + wrapper dirty/unpushed refusal -> 4.2 remaining
targets (incl. the admin tagged-revision and candidate-site targets) +
in-build gates + staging success row + `verify_service_reachable.py` ->
{4.3 trigger + webhook + `deployments`, 4.5 Cloud Build SA + role pin +
Pub/Sub token creator} -> 4.4 promotion gate (build step + route + pure
predicate) -> 4.6 thin wrappers + doctrine rewrite -> 4.7 console deploy
page (trigger, status, `/version` per channel). 4.6 can run alongside
4.3/4.4 once 4.2 lands.

### Maintainer calls

- Create the 2nd-generation Cloud Build GitHub connection for the private
  repo (one-time OAuth; nothing in 4.1 works without it).
- How much testing gates an automatic build (recommendation: unit +
  integration suites; voice harness stays outside).
- Whether `landing/` becomes a target.
- Whether a recency rule is wanted on promotion (recommendation: none).

## Epic 5 -- Stripe + cost-vs-income reports (outline; planned after Epic 3 data exists)

- Stripe as one more ledger entry source: Checkout Sessions for prepaid
  packs and Billing subscriptions for monthly grants, both landing as
  `purchase` / `subscription_grant` entries through the SAME transactional
  helper via a webhook route on the admin service (`require_stripe_signature`
  gate, idempotent on the Stripe event id). Keys in Secret Manager. Load the
  `stripe-best-practices` skill before designing the webhook.
- Reports: BigQuery `income_month` joined with `cost_by_firm_month` and
  `hosting_cost_by_service_month`; per-firm and per-form margin; per-employee
  cost. Console pages read the views; a monthly CSV export.
- Per-firm plan setting (subscription vs prepaid) lives on `firms/{id}`.
- Exit criteria and beads are written by that epic's own `/plan-epic` pass.

## Verification (program level)

Each epic's exit criteria above are the gates; the program-level checks are:

- Local: `scripts/dev-local.ps1` plus a local `uvicorn admin_backend.main:app`
  and `admin-console` dev server; `VFF_DISABLE_AUTH` stays local-only on
  both services (refused on `K_SERVICE`).
- Suites: full backend suite from the worktree (`-m "not external"`),
  `admin_backend/tests`, frontend and `admin-console` vitest in the
  foreground, every new test mutation-verified per parametrization.
- Staging first, always: the runtime config flip, mint debit, refund sweep,
  rollups, alerts, and the Cloud Build pipeline are each proven on staging
  against a `kind: mock` firm before any demo deploy; the admin service and
  console, which have no channel, are proven on a tagged no-traffic revision
  and a Hosting preview channel before traffic shifts. Each deploy is its
  own per-instance ask under the existing gates until Epic 4 changes the
  doctrine.
- Live checks: `/version` on every channel, `/health` with the firms-store
  probe, one end-to-end minted link on staging opened in incognito, a BigQuery
  query returning a row for that session, an alert doc for a forced budget
  exhaustion.

## Open maintainer decisions carried forward

Collected from the epics; none blocks starting Epic 1.

1. Email provider for alerts and later link delivery (Postmark assumed).
2. Budget-exhausted links: no refund, and a replacement link costs a fresh
   credit (recommended; Epic 2 A5 ships `budget_exhausted` as telemetry only
   until decided). Opened-but-abandoned links: no refund (assumed).
3. Seed credits for existing firms and the default credit cost per kit
   (Epic 2 A6 migration flags), and when to flip `CREDITS_ENFORCED` on per
   channel.
4. The open-requires-record cutover: outstanding links minted before the
   record existed must be re-minted (Epic 2 A3).
5. Enable the Cloud Billing BigQuery export in the Billing console (Epic 3;
   not retroactive).
6. Create the 2nd-generation Cloud Build GitHub connection before Epic 4.1
   (the repo is private; every build runs from git).
7. The first admin-service deploy (bead 1.3) will likely hit the org
   policy that refuses the `allUsers` invoker binding
   (`docs/doctrine/promotion-tiers.md:105`): the remedy is a manual binding
   or a policy relaxation, both maintainer actions, so schedule it with the
   deploy rather than discovering it then.
8. What gates an automatic build, and whether `landing/` is a target
   (Epic 4).
9. Sequencing confirmed 2026-09-03: Foundations -> Firms + credits ->
   Telemetry -> Deploy -> Stripe. Epic 2's Track A (public-backend ledger
   and mint transaction) and Epic 3's usage-event schema can start before
   Epic 1 finishes, except that A3's `CREDITS_ENFORCED` gate reads Epic 1's
   runtime config (bead 1.5, public-backend only); everything on the admin
   service waits for Epic 1.2.

## First concrete steps on approval

1. Commit this document as the sprint plan
   (`docs/sprint_22_admin-console_plan.md`, next number per `docs/INDEX.md`,
   with an INDEX row), through `/closeout` as a docs-only PR.
2. Create the program epic and the five epic beads with `plan:` pointers at
   that doc; file Epic 1 children 1.1 to 1.7 and Epic 2 Track A beads A1 to
   A6 (which can start now) and P0 (bd `polyglot-pdf-6p77c` already exists),
   each with `## Exit criteria`, wiring dependencies with `bd dep add` and
   verifying with `bd ready` / `bd blocked`.
3. Claim 1.1 in a fresh worktree off `dev` via `/next-bead`.
4. Epics 2 (Track B/C), 3, 4, and 5 each get their own `/plan-epic` pass
   against the corresponding section here before their beads are filed.
