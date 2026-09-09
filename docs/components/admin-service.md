# Admin service + console

**Tracks:** admin_backend/main.py admin_backend/routes/whoami.py admin_backend/routes/config_routes.py admin_backend/routes/audit_routes.py admin_backend/routes/user_routes.py admin_backend/routes/firm_routes.py admin_backend/routes/credit_routes.py admin_backend/services/admin_auth.py admin_backend/services/audit_log.py admin_backend/services/user_admin.py scripts/bootstrap_admin_user.py scripts/setup-admin-service.sh deploy-admin.sh deploy-admin-console.sh admin-console/

*Last updated: 2026-09-09 (bd polyglot-pdf-zopqq: firm CRUD
(`admin_backend/routes/firm_routes.py`: `POST`/`GET /admin/firms`,
`GET /admin/firms/{firm_id}`, `PATCH .../status`, `PATCH .../allowed_kits`,
`PATCH .../kind`) and credit grant/adjust
(`admin_backend/routes/credit_routes.py`: `POST .../credits/grant`,
`POST .../credits/adjust`), all behind `require_app_admin` and all audited
in-transaction -- firm writes open their OWN transaction (mirrors
`config_routes.py`'s shape); credit writes join
`credit_ledger.append_entry`'s transaction via its `extra_writes` hook
instead of opening a second one, which is now a documented, mechanically-
checked shape in `test_admin_audit_coverage.py`
(`_EXTRA_WRITES_TRANSACTION_OPENERS`). `GET /admin/firms/{firm_id}` runs
`credit_ledger.reconcile_expired_for_firm` once per known channel before
reading the balance, so a dead sweep cannot leave the console's balance
view stale. Neither surface checks `firm.kind` -- grants to mock firms are
allowed by design.) (bd polyglot-pdf-z4y91: the console's Users tab
(`admin-console/src/pages/UsersPage.tsx`) -- the first console page under a
`pages/` directory rather than `components/`, since it is the console's
first CRUD page rather than a read-mostly or single-write one; list a
firm's staff, create one with the reset link shown exactly once, disable/
re-enable, change role. `adminApi.ts` gains `listUsers`, `createUser`,
`setUserDisabled`, `setUserRole`. The firm-ID field is REQUIRED and always
shown -- the console's sign-in gate only supports the strict app-admin path
today, so every caller of this page is an app admin who must name a firm.)
(bd polyglot-pdf-dmjl5: the four staff-account routes (`POST /admin/users`,
`PATCH /admin/users/{uid}/disable`, `PATCH .../role`, `GET /admin/users`)
behind the new composite gate `require_app_admin_or_owning_manager`; the
claims allowlist in `admin_backend/services/user_admin.py`; and
`require_firm_manager` in `backend/services/auth.py`, whose rule the retire
route now consumes -- so three of the four gates now exist.) (bd
polyglot-pdf-2cwja: doc created -- the admin tier as current state, covering
`admin_backend/` (bd polyglot-pdf-pnoik, polyglot-pdf-7w17m,
polyglot-pdf-li9x0) and `admin-console/` (bd polyglot-pdf-b6943).)*

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
| `/admin/users` | POST | `require_app_admin_or_owning_manager` | Create a staff account (bd polyglot-pdf-dmjl5). Body `{email, firm_role, firm_id?, display_name?}`. Creates the Firebase account with an unguessable random password nobody sees, stamps ONLY `firm_id` + `firm_role` (merged over existing claims), and returns a password-**reset link** for the console to display -- no outbound email in this epic. 409 on a duplicate address, 422 on a bad role or firm slug. Audited pending-then-committed. |
| `/admin/users/{uid}/disable` | PATCH | `require_app_admin_or_owning_manager` | Disable or re-enable a staff account (`{disabled, firm_id?}`). An explicit value, not a toggle, so a retry is idempotent. Claims are untouched -- disabling is not deleting, and the account keeps its audit history. 404 for a uid outside the resolved firm, the SAME 404 as a uid that does not exist. |
| `/admin/users/{uid}/role` | PATCH | `require_app_admin_or_owning_manager` | Move an account between `manager` and `employee` (`{firm_role, firm_id?}`), merging over every other claim. Same 404 scoping rule as disable. |
| `/admin/users` | GET | `require_app_admin_or_owning_manager` | The firm's staff pool (`?firm_id=` for an app admin; a manager sends none). `list_users()` plus a CLIENT-SIDE claims filter -- Firebase Auth cannot query custom claims, which is affordable only because the pool is staff, editors and devs and clients never get accounts. Response rows are an explicit key allowlist. A read, so no audit row. |
| `/admin/firms` | POST | `require_app_admin` | Create a firm (bd polyglot-pdf-zopqq). Body `{firm_id, name, contact_email, kind, allowed_kits?, status?}` -- `kind` is REQUIRED with no default (422 if missing or invalid). Writes the same field shape as `backend/services/firms.py::upsert_firm` but does not call it (that helper's read+write is not transactional, so this route's transactional create/audit body writes the doc itself). Audited in its own Firestore transaction. |
| `/admin/firms` | GET | `require_app_admin` | Every firm, with `kind`/`balance_credits`/`status`, unfiltered. A read, so no audit row. |
| `/admin/firms/{firm_id}` | GET | `require_app_admin` | One firm's profile, balance, and a page of ledger rows. **Reconciles expired unopened links across BOTH known channels (via `credit_ledger.reconcile_expired_for_firm`) before reading the balance** -- a lazy catch-up for what the hourly sweep (Track B bead B5, not yet built) has not reached. A read, so no audit row. |
| `/admin/firms/{firm_id}/status` | PATCH | `require_app_admin` | Set `active`\|`suspended` (`{status}`). Audited in-transaction. |
| `/admin/firms/{firm_id}/allowed_kits` | PATCH | `require_app_admin` | Replace the private-kit allowlist (`{allowed_kits}`, full replace). Audited in-transaction. |
| `/admin/firms/{firm_id}/kind` | PATCH | `require_app_admin` | Reclassify `mock`<->`live` (`{kind, reason}`) -- `reason` REQUIRED; the confirm-twice UI control is the console's job, not this route's. Audited in-transaction. |
| `/admin/firms/{firm_id}/credits/grant` | POST | `require_app_admin` | Grant credits (`{type, amount, usd_amount?, kit_id?}`; `type` in `subscription_grant`\|`purchase`\|`promo_grant`, `usd_amount` required for the first two and refused otherwise). Calls `backend/services/credit_ledger.py::append_entry` -- the ONE writer of a firm's balance. Grants to `kind=mock` firms are allowed. Audited via `append_entry`'s `extra_writes` hook, joined to its own transaction. |
| `/admin/firms/{firm_id}/credits/adjust` | POST | `require_app_admin` | The operator's signed adjustment (`{amount, reason}`; `reason` REQUIRED, `amount` may be either sign). Same writer and audit form as `grant`. |

`channel` is always an explicit path parameter (validated against
`("demo", "staging")`), never derived from the environment -- the admin
service has no channel of its own, since it serves both channels' data from
one deployment.

This is the COMPLETE route set as of this doc's stamp, and it is pinned
mechanically: `admin_backend/tests/unit/test_admin_route_auth.py` derives
the live route set off `admin_backend.main.app` and fails if a route is
added without exactly one of four gate names
(`require_app_admin`; `require_firm_manager`;
`require_app_admin_or_owning_manager`; `require_google_oidc` -- only the
last does not exist yet, and it ships with its first consuming route in
Epic 2 B5 / Epic 4 4.3). Read that test, not this table, for the
authoritative set the day a new route lands.

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

## `require_app_admin_or_owning_manager` (the composite gate)

The gate on all four user routes. **Two very different people reach them**,
and the difference is where the firm comes from:

- an **app admin** serves every firm, so they must **name** the firm they
  are acting on -- there is no other way to know which one, and omitting it
  is a 422 rather than a guess with a write behind it;
- a **firm manager**'s firm comes from their **verified token**, and a
  request that names a firm at all is refused **403** -- including one that
  names their own firm. "The same value" is not the test; "did you try to
  choose" is. Accepting a matching value would make the refusal depend on
  what the caller happened to send, so the next console version that sent it
  on every request would silently stop being refused.

The app-admin branch is checked **first**, deliberately: an account holding
both `app_admin` and a firm manager claim acts as an app admin, the strictly
wider role. Both branches verify the same token with the same
`verify_id_token` call, made by `admin_auth.py` itself -- the admin service
never reaches into the voice app's verifier, which is what keeps that module
liftable (pinned by
`test_admin_auth.py::test_admin_auth_does_not_import_the_other_two_auth_modules`).
`resolve_target_firm(actor, body_firm_id)` is the ONE home for the two-actor
rule; every route calls it rather than restating it.

The two by-uid routes additionally prove the target account is **in the
resolved firm** before touching it -- a uid is a bearer of nothing, so
without that check a manager could disable any account in the project by
pasting its uid. That refusal is a 404 identical to the one for a uid that
does not exist, so the status code is not an existence oracle.

The **claims allowlist** is `admin_backend/services/user_admin.py`: these
routes write **only** `firm_id` and `firm_role`, never `app_admin`,
`schema_editor_role` or `vff_dev`. That is a property, not a promise --
`merge_firm_claims()` builds its output from `WRITABLE_CLAIMS` plus the
account's existing claims, so no request value can reach any other key, and
every pre-existing claim survives (`set_custom_user_claims` **replaces** the
whole claims object, the same trap `scripts/bootstrap_firm.py` documents).
`app_admin` is still granted only by `scripts/bootstrap_admin_user.py`.

## `require_firm_manager` (`backend/services/auth.py`)

Lives on the **public** backend, not here: its first consumer is the firm
retire route. The rule itself -- which firm does this caller manage -- is
`backend/services/firms.py`'s `manager_firm_id(claims)`, a pure predicate
over an already-verified claims dict, so **both** surfaces share one home
(CLAUDE.md scar #8) without the admin service depending on the voice app's
verifier. `backend/services/auth.py` re-exports the name for its own
callers.

`require_firm_manager` is the FastAPI form and raises **403**.
`form_kit_routes._require_firm_owns_private_kit` uses the **predicate**
instead, because every refusal there must stay a **404** -- a 403 would
confirm to a firm that another firm's kit exists. The rule is shared; the
refusal shape is each caller's own.
`backend/tests/unit/test_require_firm_manager.py` enumerates every non-test
module under `backend/`, `admin_backend/` and `scripts/` and fails on any
site that compares against the literal `"manager"` outside a short
allowlist, so the next hand-written copy fails CI rather than drifting.

**No route declares `require_firm_manager` yet, deliberately.** The plan
named the retire route as its first consumer, but that route cannot use it:
its refusals must be 404s, so it takes the rule and raises its own error
instead. The admin service's user routes need "app admin OR manager", a
different gate. What ships proven is therefore the RULE -- exercised by
both real callers -- with this dependency as the 403-shaped wrapper waiting
for the first public-backend route that wants manager-only access with no
existence to protect. It is unit-tested directly rather than left untested,
and the route-auth set test keeps the name in its vocabulary of legal
gates.

## Granting access: `scripts/bootstrap_admin_user.py`

The ONLY way to grant (or revoke) `app_admin` -- there is no self-serve
signup, and the console's own `/admin/users` routes (bd
`polyglot-pdf-dmjl5`) deliberately CANNOT write this claim: they are
allowlisted to `firm_id` and `firm_role`, so a compromised console could not
mint its own admins. Mirrors
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
or broken page. No router: a handful of tabs (`admin-console/src/App.tsx`)
behind a boolean signed-in state, since the page count does not yet justify
one.

- **Pages:** Who-am-I (`components/WhoAmIPage.tsx` -- identity plus the
  console's own build SHA), Audit log (`components/AuditLogPage.tsx` --
  lists/filters `GET /admin/audit`), Runtime config
  (`components/ConfigEditorPage.tsx` -- reads/writes `GET`/`PUT
  /admin/config/{channel}`), Users (`pages/UsersPage.tsx`, bd
  polyglot-pdf-z4y91 -- the FIRST page under `pages/` rather than
  `components/`: it drives four routes and two mutations with a re-read
  each, past the point a single-file "page" component was the more natural
  location).
  A page's API failures route back to `SignInGate`'s refused screen when
  they are a 401/403 (the account's session ended or was revoked
  mid-session), and to a generic in-page error otherwise -- see `App.tsx`'s
  `handleAuthExpired`.
- **Users page** (`pages/UsersPage.tsx`): the firm-ID field is a REQUIRED
  text input, always shown -- there is no firm-picker dropdown, because no
  `GET /admin/firms` list route exists yet (Epic 2 Track C's firms page, C2,
  has not shipped) and because the console's sign-in gate calls only `GET
  /admin/whoami` (`require_app_admin`, the STRICT gate), never the composite
  `require_app_admin_or_owning_manager` the user routes accept -- so every
  signed-in caller of this page is necessarily an app admin, who must name a
  firm (`admin_auth.resolve_target_firm` 422s an app admin who omits one). A
  firm-manager sign-in mode with the selector hidden is a later bead's
  concern, once the console itself supports signing in as one. Create shows
  the returned password-RESET LINK exactly once, with a copy button, and
  clears it on the next create or firm switch; NO password ever reaches this
  page (`create_staff_user` never returns one). Disable and role-change each
  call their route once and then RE-READ the firm's list, the same
  round-trip pattern `ConfigEditorPage` uses, so the screen always reflects
  what the server actually stored.
- **API client:** `admin-console/src/utils/adminApi.ts` (`probeWhoAmI`,
  `listAuditRows`, `getChannelConfig`, `setChannelConfigKey`, `listUsers`,
  `createUser`, `setUserDisabled`, `setUserRole`), each call carrying
  `Authorization: Bearer <Firebase ID token>` fetched PER REQUEST from
  `admin-console/src/utils/adminAuth.ts` (never cached client-side, so a
  mid-session token refresh cannot leave a stale credential in memory). A
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
route's filter/index pin). `admin-console/src/components/*.test.tsx` and
`admin-console/src/pages/*.test.tsx` cover the console pages (Vitest, same
harness as `schema-editor/`).
