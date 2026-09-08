# Admin service + console

**Tracks:** admin_backend/main.py admin_backend/routes/whoami.py admin_backend/routes/config_routes.py admin_backend/routes/audit_routes.py admin_backend/services/admin_auth.py admin_backend/services/audit_log.py scripts/bootstrap_admin_user.py scripts/setup-admin-service.sh deploy-admin.sh deploy-admin-console.sh admin-console/

*Last updated: 2026-09-08 (bd polyglot-pdf-2cwja: doc created -- the admin
tier as current state, covering `admin_backend/` (bd polyglot-pdf-pnoik,
polyglot-pdf-7w17m, polyglot-pdf-li9x0) and `admin-console/` (bd
polyglot-pdf-b6943). No code changed in this bead.)*

The privileged control plane: a second FastAPI service (`admin_backend/`,
Cloud Run `polyglot-admin`) and a second Vite app (`admin-console/`,
Hosting) that exist so operators can run/monitor the app without shell access
to `deploy-*.sh` or the GCP console. This doc covers the service and console
themselves; the runtime-config mechanism they read/write is in
[config-deployment.md](config-deployment.md), the `app_admin` credential is
the fourth system in [auth.md](auth.md), and the staging tier for THIS
service (tagged-revision + candidate-site, distinct from the public
backend's staging/demo split) is in
[../doctrine/promotion-tiers.md](../doctrine/promotion-tiers.md).

## Why a second service, not a route on the public backend

CLAUDE.md scar #7: a mock cannot tell you the real dependency is forbidden.
`polyglot-backend-sa` (the public backend's identity) deliberately lacks
Firebase Auth admin permissions, Cloud Build, and BigQuery access, so a
privileged call added to `backend/` fails LOUDLY on its first deployed
request rather than silently working under too-wide a grant. Splitting the
privileged surface into its own package, service, and service account keeps
that property intact: `admin_backend/` is where privileged code (user/claim
management today; Cloud Build and BigQuery in later epics) is allowed to
live, and nothing in `backend/` may reach it.

## The shared image, split by a runtime env var

One root `Dockerfile` builds both packages; which ASGI app a container
actually serves is a RUNTIME choice, not a build-time one --
`deploy-all.sh` builds with `gcloud builds submit --tag`, which cannot pass
a build arg.

- `Dockerfile`'s `CMD` is `uvicorn ${APP_MODULE:-backend.main:app} --host
  0.0.0.0 --port ${PORT}`. Unset or empty resolves to the public backend
  (the `:-` form covers both cases).
- `admin_backend/main.py`'s `DEFAULT_APP_MODULE = "backend.main:app"` is the
  SAME string, read by `_active_app_module()` the same way the container
  resolves it (`os.getenv("APP_MODULE") or DEFAULT_APP_MODULE"`), so the
  admin service's own `/health` reports the true running module even when
  `APP_MODULE` is set but empty.
- `deploy-admin.sh` sets `APP_MODULE=admin_backend.main:app` (plus
  `BACKEND_SERVICE_NAME=polyglot-admin`, `BACKEND_SERVICE_ACCOUNT=admin-
  backend-sa@...`) ahead of the SAME `deploy-all.sh --backend` the public
  channels use. No other caller sets `APP_MODULE`, so `deploy-staging.sh` /
  `deploy-demo.sh` / `backend/deploy-new.sh` are unaffected.
- Full contract, including the pin tests, is Surface contract 12 in
  [technical_guide.md](../technical_guide.md).

## Routes

Cloud Run runs `polyglot-admin` with `--allow-unauthenticated`, so the
app-level gate on EVERY route is the entire access control -- there is no
network-layer fallback. `/health` and `/version` are the deliberate
exception (unauthenticated liveness/identity, matching the public backend's
`/health`).

| Route | Method | Gate | Purpose |
|-------|--------|------|---------|
| `/health` | GET | none | Liveness + which `APP_MODULE` is actually running. |
| `/version` | GET | none | `{"version", "git_sha"}` -- same shape as the public backend's `/version`, `GIT_SHA` from the runtime env var set at deploy time. |
| `/admin/whoami` | GET | `require_app_admin` | `{uid, email}` for the calling account. The FIRST business route (bd polyglot-pdf-7w17m); the console's sign-in gate calls it to confirm a signed-in Firebase account actually holds admin access. |
| `/admin/config/{channel}` | GET | `require_app_admin` | The channel's stored `app_config/{channel}` doc, raw (uncoerced), plus `known_keys`/`unknown_keys`. A read; writes no audit row. |
| `/admin/config/{channel}` | PUT | `require_app_admin` | Set ONE runtime-config key for one channel (`{key, value}` body), validated against `runtime_config.RUNTIME_CONFIG_KEYS` and `coerce_value` before any write, then written and audited in ONE Firestore transaction. See [config-deployment.md](config-deployment.md). |
| `/admin/audit` | GET | `require_app_admin` | One page of `admin_audit_log` rows, newest first, cursor-paginated (`{rows, next_cursor}`); filterable by `action`/`actor_uid`/`channel`/`state`. |

`channel` is always an explicit path parameter (validated against
`("demo", "staging")`), never derived from the environment -- the admin
service has no channel of its own, since it serves both channels' data from
one deployment.

This is the COMPLETE route set as of this doc's stamp, and it is pinned
mechanically: `admin_backend/tests/unit/test_admin_route_auth.py` derives
the live route set off `admin_backend.main.app` and fails if a route is
added without exactly one of four gate names
(`require_app_admin`; `require_firm_manager`,
`require_app_admin_or_owning_manager`, `require_google_oidc` -- the latter
three do not exist yet and ship with their first consuming route in Epic 2 /
Epic 4). Read that test, not this table, for the authoritative set the day
a new route lands.

## `require_app_admin` (`admin_backend/services/admin_auth.py`)

Mirrors `backend/services/editor_auth.py`'s shape: a boolean custom claim
(`APP_ADMIN_CLAIM = "app_admin"`), `verify_id_token` with **no**
`check_revoked` (same CLAUDE.md scar #7 reasoning as the other two
verifiers -- see the module docstring for why this service, which DOES hold
`roles/firebaseauth.admin` and so could afford the extra lookup, still
leaves it off for now), and a 401/403 split: 401 for a token that fails to
verify, 403 with the machine-readable `NO_ADMIN_ACCESS:` prefix
(`NO_ADMIN_ACCESS_PREFIX`) for a valid account with no `app_admin` claim.
The dev bypass (`VFF_DISABLE_AUTH=true`) is refused outright when `K_SERVICE`
is set (a deployed instance), matching the public backend's and editor's own
bypass guards.

This is the fourth credential system in this repo -- see
[auth.md](auth.md)'s credential table, which this bead extends from three
rows to four.

## Granting access: `scripts/bootstrap_admin_user.py`

The ONLY way to grant (or revoke) `app_admin` -- there is no self-serve
signup and no in-console user management yet. Mirrors
`scripts/bootstrap_editor_user.py`'s shape (`--email`, `--revoke`, `--list`,
merges claims rather than replacing them) plus `scripts/bootstrap_firm.py`'s
`--project` machinery (a REQUIRED flag; the script asserts the resolved
Firebase project matches it and aborts otherwise, rather than trusting
whatever project the operator's gcloud ADC happens to resolve to). Runs
under the OPERATOR's own gcloud ADC, not the deployed `admin-backend-sa` --
the operator's principal needs Firebase Auth admin on the target project. A
stamped claim appears in the account's ID token only on its next refresh (up
to about an hour), or immediately after a sign-out/sign-in.

```bash
python scripts/bootstrap_admin_user.py --email you@example.com --project polyglot-demo-aa709
python scripts/bootstrap_admin_user.py --email you@example.com --revoke --project polyglot-demo-aa709
python scripts/bootstrap_admin_user.py --list --project polyglot-demo-aa709
```

## The audit log (`admin_backend/services/audit_log.py`)

Every mutating admin route writes exactly one row to `admin_audit_log/{auto}`
-- see Surface contract 15 in [technical_guide.md](../technical_guide.md)
for the full shape, the two write forms (in-transaction for Firestore
mutations, pending-then-committed for everything else), and the coverage
test that derives the mutating route set and asserts each declares which
form it uses. `GET /admin/audit` above is the read side.

## Service account: `admin-backend-sa`

Provisioned by `scripts/setup-admin-service.sh <PROJECT_ID> [FORM_KITS_BUCKET]`
(idempotent; sibling of `scripts/setup-gcp-project.sh`, which provisions the
public backend's narrow SA). NOT run by any deploy script -- an operator runs
it by hand, once per project or whenever the role set changes. It also
enables the `identitytoolkit` API (every Firebase Auth admin call needs it;
the public backend never touches it).

Roles, each justified inline in the script and pinned by
`admin_backend/tests/unit/test_admin_sa_iam_envelope.py` (which parses the
script's own role arrays, so a role added there without updating the test's
constant fails CI):

| Role | Scope | Why |
|------|-------|-----|
| `roles/firebaseauth.admin` | project | Create/disable Auth users, stamp `app_admin` and `firm_role` custom claims -- the one permission `polyglot-backend-sa` deliberately lacks. |
| `roles/datastore.user` | project | Firestore reads/writes: firms, the credit ledger, kits, links, `admin_audit_log`, deployments, `app_config`. |
| `roles/logging.logWriter` | project | Structured logs to Cloud Logging, same as the public backend. |
| `roles/secretmanager.secretAccessor` | project | Read Secret-Manager-backed values (the link-signing secret, an email-provider key) -- a missing binding here fails LOUDLY at Cloud Run deploy time, not silently. |
| `roles/storage.objectAdmin` | the form-kits bucket ONLY | Publish/retire form kits. The public backend holds only `roles/storage.objectViewer` on the same bucket. |

Deferred, deliberately absent until the epic that first needs them (an
unused grant is its own risk): `roles/cloudbuild.builds.editor` +
`roles/iam.serviceAccountUser` on the Cloud Build SA, `roles/run.admin` +
`roles/iam.serviceAccountUser` on `polyglot-backend-sa` (resource-scoped),
`roles/firebasehosting.admin` (Epic 4, deploy control plane);
`roles/bigquery.jobUser` + dataset-scoped `roles/bigquery.dataViewer`,
`roles/errorreporting.viewer`, `roles/monitoring.viewer` (Epic 3,
telemetry).

## CORS

The admin console is ALWAYS a cross-origin caller of the admin service --
there is no same-origin Hosting rewrite in front of it (unlike the main
app's `/api/**` rewrite). `admin_backend/main.py`'s `CORSMiddleware`
allowlist carries the console's and the main app's dev-server localhost
ports (3002 for the console, mirroring the editor's 3001) plus, at deploy
time, `deploy-admin.sh`'s `ADMIN_CORS_ORIGINS` -- both admin Hosting sites'
`.web.app` and `.firebaseapp.com` domains, and both channels' app origins
(the main app's future firm-manager pages call this service too), via
`parse_extra_origins` (`backend/config.py`).

## Deploying the service: `deploy-admin.sh`

Builds on `deploy-all.sh`'s backend stage with
`BACKEND_SERVICE_NAME=polyglot-admin`,
`BACKEND_SERVICE_ACCOUNT=admin-backend-sa@...`,
`APP_MODULE=admin_backend.main:app`, and `BACKEND_NO_TRAFFIC_TAG=candidate`.

**Why tagged-no-traffic, unlike `deploy-staging.sh`/`deploy-demo.sh`.**
There is ONE admin service backing BOTH channels' data -- a bad deploy would
take the control plane down for staging and the demo at once, and there is
no cheap staging Cloud Run service to rehearse against first the way the
public backend has. So every admin deploy lands as a Cloud Run revision with
`--no-traffic --tag candidate`, gets curled at ITS OWN stable tagged URL's
`/health`, and only on a 200 receives traffic via
`gcloud run services update-traffic --to-latest`. A failing health check
aborts before any traffic shifts; the previously-live revision keeps
serving throughout. Full mechanism (URL construction, the aborting
condition) is Surface contract 12 in
[technical_guide.md](../technical_guide.md); the doctrine framing (why this
counts as this service's OWN staging tier) is in
[../doctrine/promotion-tiers.md](../doctrine/promotion-tiers.md).

One-time setup before the first deploy: run `setup-admin-service.sh` once,
then stamp the first admin account with `bootstrap_admin_user.py`. The
domain-restricted-sharing org policy can refuse the `--allow-unauthenticated`
binding on this BRAND NEW service exactly as it can on any new Cloud Run
service -- see the reachability gate in
[../doctrine/promotion-tiers.md](../doctrine/promotion-tiers.md).

This script deploys the BACKEND only; it prints no console URL and stands
the API up with no UI in front of it, which is a legitimate intermediate
state (the routes are reachable by curl with a bearer token from
`bootstrap_admin_user.py`).

## The console (`admin-console/`)

A separate Vite + React app, mirroring `schema-editor/`'s shape: Firebase
sign-in (`admin-console/src/components/SignInGate.tsx`) followed by a
server-side authorization probe (`GET /admin/whoami`) -- an authenticated
but non-admin account sees an explicit not-authorized screen, not a blank
or broken page. No router: three tabs (`admin-console/src/App.tsx`) behind
a boolean signed-in state, since the page count does not yet justify one.

- **Pages:** Who-am-I (`WhoAmIPage.tsx` -- identity plus the console's own
  build SHA), Audit log (`AuditLogPage.tsx` -- lists/filters `GET
  /admin/audit`), Runtime config (`ConfigEditorPage.tsx` -- reads/writes
  `GET`/`PUT /admin/config/{channel}`).
  A page's API failures route back to `SignInGate`'s refused screen when
  they are a 401/403 (the account's session ended or was revoked
  mid-session), and to a generic in-page error otherwise -- see `App.tsx`'s
  `handleAuthExpired`.
- **API client:** `admin-console/src/utils/adminApi.ts` (`probeWhoAmI`,
  `listAuditRows`, `getChannelConfig`, `setChannelConfigKey`), each call
  carrying `Authorization: Bearer <Firebase ID token>` fetched PER REQUEST
  from `admin-console/src/utils/adminAuth.ts` (never cached client-side, so
  a mid-session token refresh cannot leave a stale credential in memory). A
  403 is classified into `ForbiddenError.noAdminAccess` by the
  `NO_ADMIN_ACCESS:` wire prefix, the same idiom the schema editor's
  `NO_EDITOR_ACCESS_PREFIX` uses.
- **`VITE_ADMIN_API_BASE_URL`:** the admin service's own Cloud Run URL,
  resolved at DEPLOY time by `deploy-admin-console.sh`, the same way
  `deploy-editor.sh` resolves the public backend's URL for the schema
  editor. Distinct from `VITE_API_BASE_URL` -- the console never calls the
  public backend.
- **Auth project:** the SAME Firebase project as the voice app and the
  schema editor (`admin-console/.env.hosted`'s `VITE_FIREBASE_*` match
  `schema-editor/.env.hosted`'s) -- a separate admin-only Firebase project
  is a future separation epic's call, not this one's.
- **Build-time git SHA:** `admin-console/vite.config.ts` bakes
  `__ADMIN_CONSOLE_GIT_SHA__` in via a Vite `define` (`git rev-parse HEAD`
  at build time, `'unknown'` on failure). This is the CONSOLE bundle's own
  commit, deliberately separate from `GET /version`'s `git_sha` (the ADMIN
  SERVICE's commit, a different deploy reached over HTTP).

## Deploying the console: candidate site, then live

`deploy-admin-console.sh` (no flag) builds and deploys to
`polyglot-admin-candidate`; `deploy-admin-console.sh --live` deploys the
SAME build to `polyglot-admin-demo`, the site every admin actually uses. An
unrecognized argument is fatal (never silently falls through to the
candidate deploy while printing a success banner).

**Why a second permanent site, not a Hosting preview channel.** A preview
channel (`firebase hosting:channel:deploy`) mints a random-hash URL per
deploy, which would have to be re-added to Firebase Auth's authorized-domain
list and to the admin service's CORS allowlist on every single deploy. A
fixed candidate site's domain is authorized ONCE, exactly like the live
site's.

One-time setup (per project): create both Hosting sites
(`polyglot-admin-demo`, `polyglot-admin-candidate` -- names are globally
unique across all of Firebase) and map both deploy targets
(`admin` -> the live site, `admin-candidate` -> the candidate site) via
`firebase target:apply`; verify BOTH sites' domains are on Firebase Auth's
authorized-domains list (Firebase does not always auto-authorize a second
site under the same project, and no build check can catch a missing one --
the console's sign-in screen names this failure explicitly if it fires);
grant each operator access with `bootstrap_admin_user.py` above.

## Testing

`admin_backend/tests/unit/` mirrors the public backend's test layout:
`test_admin_auth.py` (the gate itself), `test_admin_route_auth.py` (the
route/gate set pin above), `test_admin_health.py` (`/health`/`/version`),
`test_admin_sa_iam_envelope.py` (the role-list pin, and the
`admin_backend` -/-> `backend.routes` import-direction guard -- Surface
contract 13), `test_audit_log.py` + `test_admin_audit_coverage.py` (the
audit forms and coverage pin), `test_config_routes.py` (the config route's
validation and transactional write), `test_firestore_indexes.py` (the audit
route's filter/index pin). `admin-console/src/components/*.test.tsx` covers
the console pages (Vitest, same harness as `schema-editor/`).
