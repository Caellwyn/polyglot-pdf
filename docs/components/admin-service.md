# Admin service + console

**Tracks:** admin_backend/main.py admin_backend/routes/whoami.py admin_backend/routes/config_routes.py admin_backend/routes/audit_routes.py admin_backend/routes/user_routes.py admin_backend/routes/firm_routes.py admin_backend/routes/credit_routes.py admin_backend/routes/link_routes.py admin_backend/routes/sweep_routes.py admin_backend/routes/kit_routes.py admin_backend/routes/usage_routes.py admin_backend/routes/report_routes.py admin_backend/routes/alert_routes.py admin_backend/routes/ops_routes.py admin_backend/services/admin_auth.py admin_backend/services/audit_log.py admin_backend/services/user_admin.py admin_backend/services/bigquery_reports.py admin_backend/services/error_stats.py scripts/bootstrap_admin_user.py scripts/setup-admin-service.sh deploy-admin.sh deploy-admin-console.sh admin-console/

*Last updated: 2026-09-12 (bd polyglot-pdf-i6dlb, E3.11b -- the five
monitoring CONSOLE PAGES over bd polyglot-pdf-mpebj's read routes above:
`pages/MonitoringPage.tsx` (one card per channel from `GET /admin/health`,
fetched independently so one channel's failure never blanks the other's
card; THREE backend states rendered distinctly -- `configured: false`,
`configured: true, reachable: false`, and `reachable: true` with the
backend's version SHA -- plus a fourth, the console's OWN fetch failing,
shown as that card's own error text, never a blank card), `pages/
UsagePage.tsx` (a firm picker over `GET /admin/firms` + a month/channel
picker over `GET /admin/firms/{firm_id}/usage`; a month with an all-null
`usage` object -- no rollup doc yet -- renders an explicit "no usage
recorded" message rather than a table of zeros; `by_kit`/`by_employee`/
`by_language` render as three separate tables, sorted by key for a stable
render), `pages/CostReportsPage.tsx` (a Cost tab over `GET
/admin/reports/cost` with `group_by`/channel, and an Income tab over `GET
/admin/reports/income` with no channel selector at all -- mirroring that
route's own refusal of one; BOTH tabs refuse a from/to range over 12
months CLIENT-SIDE, before any network call, with the identical message
`report_routes.py`'s own `_validated_range` returns; the `delayed`/`note`
label renders only when the response's own `delayed` flag says so, never
assumed), `pages/AlertsPage.tsx` (kind/firm filters -- the route has no
`level` query param to filter on, so `level` renders only as a display
column, never a filter -- defaulting to
`acknowledged=false`; Acknowledge calls the PATCH exactly once per click
via a per-row `busyId` guard then re-reads the CURRENT filtered list; a
409 from acknowledging an already-acknowledged alert surfaces the route's
own "already acknowledged by X" text next to that row rather than a
generic banner, and does NOT trigger the success re-read -- mirrors
`UsersPage.tsx`'s "a failed mutation must not trigger the success
re-read" rule), and `pages/ErrorsPage.tsx` (channel tabs over `GET
/admin/errors`, one fetch per tab switch; renders ONLY the five
`ErrorGroup` fields adminApi.ts types -- count, first/last seen,
error_type, top_frame -- by name, so a payload carrying any other key
(a stray `message`, say) has no code path that would ever put it in the
DOM, pinned by a test that feeds exactly that shape and asserts the
sentinel value is absent from `document.body.textContent`, not just from
a typed field). `App.tsx` gains five tabs (Monitoring, Usage, Cost &
income, Alerts, Errors) alongside the existing six. `adminApi.ts` gains
the typed calls and wire-contract exports: `getChannelHealth`,
`getChannelErrors`, `getFirmUsage`, `getCostReport`, `getIncomeReport`,
`listAlerts`, `acknowledgeAlert`, plus `MONITORING_CHANNELS`,
`COST_GROUP_BY`, `MAX_REPORT_RANGE_MONTHS`, `ALERT_KINDS`, `ALERT_LEVELS`
and their matching response-shape interfaces. Every new page is a plain
mocked-`adminApi.ts` Vitest file, mutation-verified per assertion (revert
the branch, watch it fail, restore).)*

*Last updated: 2026-09-11 (bd polyglot-pdf-mpebj, E3.11a -- the monitoring
console's READ routes: `GET /admin/firms/{firm_id}/usage` +
`GET /admin/kits/{kit_id}/usage` (`admin_backend/routes/usage_routes.py`),
reading the E3.4 Firestore rollup docs (`firms/{id}/usage/{month}`,
`kits/{id}/usage/{month}`) under an explicit key allowlist -- the firm
route carries `require_app_admin_or_owning_manager` (a manager reads only
their own firm, 404 not 403 for another, mirroring bead B4's rule), the
kit route `require_app_admin` (a kit spans every firm, so there is no
owning manager). `GET /admin/reports/cost` + `GET /admin/reports/income`
(`admin_backend/routes/report_routes.py`, `require_app_admin`) run
PARAMETERISED queries against the E3.6 BigQuery views
(`cost_by_firm_month`/`cost_by_kit_month`/`cost_by_employee_month`/
`income_month`) through a new `admin_backend/services/bigquery_reports.py`
-- every `from`/`to`/`channel` value is bound as a `bigquery.
ScalarQueryParameter`, never interpolated into SQL text, and `group_by`
selects the view via a closed Python dict lookup (never a value reaching
the FROM clause); a range wider than 12 months is a 422, and every
response carries `delayed: true` plus a sink-lag note. `GET /admin/alerts`
+ `PATCH /admin/alerts/{id}/acknowledge` (`admin_backend/routes/
alert_routes.py`, `require_app_admin`) list the E3.5 `alerts/{id}` docs
(newest first, filterable by `acknowledged`/`firm_id`/`kind`, page-capped)
and acknowledge one -- the ONE mutation this bead ships, setting
`acknowledged_by` (the actor's uid) + `acknowledged_at` inside ONE
Firestore transaction with its audit row (mirrors `firm_routes.py`'s
`_apply_firm_patch` shape); acknowledging twice is a 409. `GET
/admin/errors` (`admin_backend/routes/ops_routes.py`, `require_app_admin`)
calls Cloud Error Reporting's `groupStats.list` REST endpoint (a new
`admin_backend/services/error_stats.py`, authenticated with the runtime
SA's ADC token via `google.auth` -- `admin-backend-sa` already holds
`roles/errorreporting.viewer` from bd `polyglot-pdf-e4dt8`'s
`setup-monitoring.sh`, so this bead grants nothing new), filtered to the
channel's Cloud Run service name (`polyglot-backend` / `polyglot-backend-
staging`) and returning count, first/last seen, and the group's
representative TYPE and TOP FRAME ONLY. The Error Reporting API has no
`representative.type` field (the live discovery document's `ErrorEvent`
schema is `context`/`serviceContext`/`message`/`eventTime` only) -- the
type is recovered from `representative.message`'s own terminating line,
which E3.8's write-side PII rule already guarantees is the bare exception
type name and nothing else, so no message text ever reaches the console.
`GET
/admin/health` (`ops_routes.py`, `require_app_admin`) fans out to the
requested channel's PUBLIC backend `/health` + `/version` over a
short-timeout HTTP call, plus this service's own `/version` (an
in-process read, not a second hop); `reachable` is true only when BOTH
calls succeed, and one channel's outage yields a PARTIAL result
(`reachable: false`), never a 500. The per-channel backend base URLs come
from a new admin-service-only env var, `BACKEND_URLS_JSON` -- despite the
name, its WIRE FORMAT is `"channel=url;channel=url"`, not literal JSON:
`deploy-admin.sh` builds it via two `gcloud run services describe` calls
(the same mechanism `deploy-all.sh` uses for `VITE_WS_URL`) and appends it
to `BACKEND_EXTRA_ENV`, which rides inside `deploy-all.sh`'s own
comma-joined `--set-env-vars` block -- a literal JSON object's `,` between
key/value pairs would be silently split apart there, the same reason
`CORS_EXTRA_ORIGINS` is semicolon-separated rather than comma-separated. A
channel with no entry in `BACKEND_URLS_JSON` reads `configured: false`,
distinct from `reachable: false` (configured, but unreachable). See
Surface contract 26's extension below for the usage-rollup read shape and
Surface contract 25 for the BigQuery views this bead reads.)*
*Last updated: 2026-09-09 (bd polyglot-pdf-scaig: an employee-role staff
account could not reach `GET /admin/firms/{firm_id}/links` at all -- the
route's only gate, `require_app_admin_or_owning_manager`, has exactly two
actor kinds (app admin, firm manager), so an employee was refused with a
flat 403 before the route's own `employee_id` filtering ever ran. Fixed
with a FIFTH, route-scoped dependency,
`require_app_admin_or_owning_manager_or_employee`
(`admin_backend/services/admin_auth.py`), wired ONLY onto the listing
route -- `POST /admin/links/{jti}/revoke` deliberately keeps the original,
narrower gate unchanged, since an employee must never revoke a link. The
new gate's employee branch resolves via a new sibling rule,
`backend/services/firms.py::employee_firm_id(claims)` (the same shape as
`manager_firm_id`, one role over), and the route forces `employee_id` to
`actor.employee_id` (the caller's own uid from the verified token)
whenever the actor is an employee, ignoring/overriding any `?employee_id=`
the query names -- the plan's own words, "ids come from the token, not the
query". THIS IS NOT A WIDENING of `require_app_admin_or_owning_manager`
itself: that gate keeps refusing an employee everywhere else (the four
`/admin/users` routes in particular), which is why the fix is a new
function rather than a third branch on the existing one --
`test_composite_gate.py`'s `test_neither_an_admin_nor_a_manager_is_403`
already pinned an employee claims dict as a 403 through that name before
this bead, and still does. The fifth gate is deliberately NOT part of
`test_admin_route_auth.py`'s four-gate vocabulary (the plan's own named
list); it is pinned directly on its one route instead, both there
(`test_only_the_link_listing_route_carries_the_fifth_gate`) and in
`test_admin_link_routes.py`.)*
*Last updated: 2026-09-09 (bd polyglot-pdf-r8z9g: Epic 2 Track C bead C2 --
the console's Firms tab (`admin-console/src/pages/FirmsPage.tsx`,
`FirmDetailPage.tsx`), the SECOND page under `pages/` (after
`UsersPage.tsx`). FirmsPage lists every firm (kind badge, balance, status --
driving `GET /admin/firms`) and creates one; `kind` has NO client-side
default (an explicit "Choose kind..." placeholder option, never
pre-selected mock or live) and the Create button stays disabled until an
operator actively picks one -- the route's own kind-REQUIRED 422 mirrored
client-side, deliberately in the safer direction since a mis-defaulted LIVE
firm can mint for real money (firm_routes.py's own docstring). FirmDetailPage
drives `GET /admin/firms/{firm_id}` (profile, balance, ledger page),
`PATCH .../allowed_kits` (a comma-separated textarea, full replace),
`PATCH .../kind` (CONFIRM-TWICE IN THE CONSOLE, not the route -- opening the
change-kind form is confirmation #1, and a second dialog rendered only
after a reason is typed gates the actual write as confirmation #2; the
route's own `reason` REQUIRED 422 is mirrored client-side ahead of both
confirmations), `POST .../credits/grant` and `.../credits/adjust` (grant
shows `usd_amount` ONLY for `subscription_grant`/`purchase` -- switching to
`promo_grant` clears any typed value so it can never ride along on a type
credit_routes.py would refuse it on; adjust requires a non-blank `reason`,
enforced by both the input's own `required` attribute and a `.trim()`
check, since a whitespace-only value passes the former), and bead B4's
`GET /admin/firms/{firm_id}/links` + `POST /admin/links/{jti}/revoke`
(a channel `<select>` defaulting to `demo` reloads the link list on
change -- `channel` is a REQUIRED query param on both routes, per
link_routes.py's own 422-on-missing rule; revoke is enabled only on a
`minted` link, calls the route once, and re-reads the link list from the
same channel). Every mutation on this page follows the same MUTATE-THEN-
RE-READ round trip `ConfigEditorPage`/`UsersPage` already use. `App.tsx`
gains a fifth tab, Firms, whose detail view is a SUB-STATE of that tab
(`openFirmId`) rather than a sixth tab -- switching tabs away and back to
Firms always returns to the list. `adminApi.ts` gains `listFirms`,
`createFirm`, `getFirm`, `setFirmStatus`, `setFirmAllowedKits`,
`setFirmKind`, `grantCredits`, `adjustCredits`, `listFirmLinks`,
`revokeLink`.)*
*Last updated: 2026-09-09 (bd polyglot-pdf-f0kuu: kit commercial settings,
Track B bead B3 -- `GET /admin/kits` (every kit in the form-kit store,
joined with its resolved commercial or the global defaults),
`GET /admin/kits/{kit_id}/commercial` (calls
`backend/services/kit_commercials.py::resolve_commercial` -- the SAME
reader bead A3's mint transaction uses, so this bead adds NO second
reader), and `PUT /admin/kits/{kit_id}/commercial` (`{credit_cost,
burn_cap_usd, display}`, `credit_cost` a positive int, `burn_cap_usd` a
positive finite float -- bool, NaN and +-inf all refused explicitly, since
bool is an int subclass and an unguarded check would price a form at 1
credit on a stray `true` -- refused with 422 BEFORE any write, deliberately
STRICTER than the read side's defensive fallback: a bad edit must never
reach the store as a "successful" write the fallback then papers over).
All three behind `require_app_admin` -- kit pricing has no firm-manager
counterpart. PUT audits in ONE `@firestore.transactional` body (mirrors
`firm_routes.py`'s `_apply_firm_patch` shape); there is no other writer's
transaction to join via `extra_writes`, since this route is the only
writer of `kits/{kit_id}`.)
(bd polyglot-pdf-mzblw: kit commercials console page, Epic 2 Track C bead
C1 -- `admin-console/src/pages/KitCommercialsPage.tsx`, the first mutating
console page over `kit_routes.py`'s three routes. Lists every kit
(`GET /admin/kits`) with its `credit_cost`, `cap_usd` and `source`; "Edit"
on a row does a FRESH `GET /admin/kits/{kit_id}/commercial` read (never the
list row's already-rendered values, which can be stale if another operator
just saved the same kit) and one Save PUTs the WHOLE commercial body,
mirroring the route's own "a PUT replaces the whole doc" contract -- never a
partial patch. Client-side validation mirrors the route's own rules
(`credit_cost` a positive int, `burn_cap_usd` a positive finite number)
ahead of the network call, but the route's own 422 detail is still what
this page trusts for anything its check does not catch: `fieldFromDetail`
classifies a 422 onto the `credit_cost`/`burn_cap_usd` field it names (an
ALLOWLIST prefix match against `kit_routes.py`'s own detail strings, never
a blacklist) so the console shows a field-level error instead of a generic
banner. A successful save re-reads the kit (GET) and reloads the list,
mirroring `ConfigEditorPage`/`UsersPage`'s round-trip pattern. `adminApi.ts`
gains `listKits` / `getKitCommercial` / `setKitCommercial`; `App.tsx` gains
the "Kit commercials" tab. DOES NOT SHOW `updated_by`: neither GET route's
response carries it (only the raw Firestore doc does) -- a discrepancy from
the bead's own prose, left for a future bead if the console needs it, since
adding it needs a `kit_routes.py` wire change outside this bead's Surfaces.
DISPLAY IS PRESERVED, NOT EDITED (bd polyglot-pdf-zcbm1): the page has no UI
for the console label itself, but the fresh GET on Edit captures the kit's
`display` map (now returned by `resolve_commercial`, see below) into state,
and Save echoes that same map back on the PUT unchanged -- so a price edit
never silently wipes a label `scripts/seed_kit_commercials.py` or a
previous save had set. Before `resolve_commercial` returned `display`, this
page had nothing to read it from and always sent `display: {}`, erasing any
seeded label on every price edit; that reader-side gap is now closed.)
(bd polyglot-pdf-jmiys: link listing and revoke,
Track B bead B4 -- `GET /admin/firms/{firm_id}/links`
(`?channel=` REQUIRED, `?status=`/`?employee_id=` optional filters) joins a
firm's `links[_<channel>]` mint records (bead A1) with their
`link_redemptions[_<channel>]` detail (`opened_at`, `completed_at`, and bead
ik7e's `spend_usd`/`turns`) by hand into an explicit key ALLOWLIST -- never
`**doc`, so a future internal field on either stored document cannot leak.
`POST /admin/links/{jti}/revoke` (`?channel=` REQUIRED) sets
`status=revoked` with `revoked_by`/`revoked_at`, in ONE
`@firestore.transactional` body with an in-transaction audit row (mirrors
`firm_routes.py`'s `_apply_firm_patch` shape -- there is no balance
mutation to join via `credit_ledger`'s `extra_writes` hook, since revoke
touches only the link's own status). Only a `STATUS_MINTED` record may be
revoked; any other status is a 409 naming the current status. Revoke
carries `require_app_admin_or_owning_manager`; unlike the body-field firm
rule `resolve_target_firm` enforces for `/admin/users`, `firm_id` here is a
URL PATH segment a manager must be able to name (their own firm) to reach a
GET at all -- so this bead's own small `_require_owning_firm` helper
refuses a manager acting on ANY OTHER firm's `firm_id` (or a jti belonging
to one) with the SAME 404 an unknown firm_id/jti would get, never 403,
which would confirm the other firm exists. Revoking a link does not itself
change what `POST /api/links/open` does on the PUBLIC backend -- that check
is Epic 2 Track A bead A3's job (`backend/routes/link_routes.py`,
`links_store.get_link`), landing separately. LISTING'S GATE WIDENED LATER
(bd polyglot-pdf-scaig, 2026-09-09) to also accept a firm EMPLOYEE -- see
that note below for the current shape; this note stays as the bead-B4-era
description of revoke, which is unchanged.)
(bd polyglot-pdf-8vgfh: the hourly expired-link
refund sweep, `POST /admin/links/sweep-expired`
(`admin_backend/routes/sweep_routes.py`) -- the fourth and last gate,
`require_google_oidc(audience, allowed_caller_emails)`
(`admin_backend/services/admin_auth.py`), lands with it. Per channel (or
every `KNOWN_CHANNELS` channel when `?channel=` is omitted), queries
`links[_<channel>]` for `status == minted AND open_deadline < now` and
calls bead A5's `credit_ledger.refund_expired_link()` once per hit; each
committed refund's audit row rides the SAME Firestore transaction via that
function's `extra_writes` parameter (this bead's extension to A5's
helper) -- the SAME extra_writes-delegated shape of `MUTATION_KIND_
FIRESTORE` bd polyglot-pdf-zopqq's `credit_routes.py` uses with `append_
entry`, both now recognized by `test_admin_audit_coverage.py`'s
`_EXTRA_WRITES_TRANSACTION_OPENERS`. `scripts/setup-admin-
service.sh` gains the `cloudscheduler.googleapis.com` API enable, a
dedicated `admin-sweep-scheduler-sa` (a caller identity kept separate from
`admin-backend-sa`, the service's own callee identity), and the
hourly-job `gcloud scheduler jobs create http` command as an operator NOTE
to run once after the admin service's first deploy -- the job needs that
deploy's own Cloud Run URL, which this script cannot know ahead of time.)
(bd polyglot-pdf-zopqq: firm CRUD
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
| `/admin/firms/{firm_id}` | GET | `require_app_admin` | One firm's profile, balance, and a page of ledger rows. **Reconciles expired unopened links across BOTH known channels (via `credit_ledger.reconcile_expired_for_firm`) before reading the balance** -- a lazy catch-up for what the hourly sweep (bd polyglot-pdf-8vgfh, below) has not reached. A read, so no audit row. |
| `/admin/firms/{firm_id}/status` | PATCH | `require_app_admin` | Set `active`\|`suspended` (`{status}`). Audited in-transaction. |
| `/admin/firms/{firm_id}/allowed_kits` | PATCH | `require_app_admin` | Replace the private-kit allowlist (`{allowed_kits}`, full replace). Audited in-transaction. |
| `/admin/firms/{firm_id}/kind` | PATCH | `require_app_admin` | Reclassify `mock`<->`live` (`{kind, reason}`) -- `reason` REQUIRED; the confirm-twice UI control is the console's job, not this route's. Audited in-transaction. |
| `/admin/firms/{firm_id}/credits/grant` | POST | `require_app_admin` | Grant credits (`{type, amount, usd_amount?, kit_id?}`; `type` in `subscription_grant`\|`purchase`\|`promo_grant`, `usd_amount` required for the first two and refused otherwise). Calls `backend/services/credit_ledger.py::append_entry` -- the ONE writer of a firm's balance. Grants to `kind=mock` firms are allowed. Audited via `append_entry`'s `extra_writes` hook, joined to its own transaction. |
| `/admin/firms/{firm_id}/credits/adjust` | POST | `require_app_admin` | The operator's signed adjustment (`{amount, reason}`; `reason` REQUIRED, `amount` may be either sign). Same writer and audit form as `grant`. |
| `/admin/firms/{firm_id}/links` | GET | `require_app_admin_or_owning_manager_or_employee` | The firm's links (bd polyglot-pdf-jmiys, Track B bead B4; gate widened to a firm EMPLOYEE by bd polyglot-pdf-scaig), joining `links[_<channel>]` mint records with `link_redemptions[_<channel>]` detail. `?channel=` REQUIRED (422 if missing/unknown); `?status=` an optional equality filter; `?employee_id=` is an optional filter for a manager/app admin but is FORCED to the caller's own uid (from the verified token) for an employee actor, overriding whatever the query names. A manager or employee reaches only their own firm (404 for any other `firm_id`); an app admin reaches any. Response rows are an explicit key allowlist. A read, so no audit row. |
| `/admin/links/{jti}/revoke` | POST | `require_app_admin_or_owning_manager` | Revoke a minted link (bd polyglot-pdf-jmiys). `?channel=` REQUIRED. Sets `status=revoked` with `revoked_by`/`revoked_at` in one transaction with an in-transaction audit row; only a `minted` link may be revoked (409 otherwise, naming the current status). A manager may revoke only a jti belonging to their own firm (404 otherwise, same as an unknown jti). |
| `/admin/links/sweep-expired` | POST | `require_google_oidc` | The hourly expired-link refund sweep (bd polyglot-pdf-8vgfh). Optional `?channel=` sweeps one channel (404 on an unknown value); omitted, sweeps every `KNOWN_CHANNELS` channel. Per channel, queries `links[_<channel>]` for `status == minted AND open_deadline < now` and calls bead A5's `credit_ledger.refund_expired_link()` once per hit -- see Surface contract 18 in [technical_guide.md](../technical_guide.md) for that helper. Returns counts only (`{results, total_refunded, total_skipped}`); the ledger entry and the extra_writes-delegated audit row (joined via the same `_EXTRA_WRITES_TRANSACTION_OPENERS` shape as the credit routes above) are the durable record. |
| `/admin/kits` | GET | `require_app_admin` | Every kit in the form-kit store (bd polyglot-pdf-f0kuu, Track B bead B3), each joined with its resolved commercial doc (or the global defaults) via the same reader the single-kit GET below and the mint transaction use. A read, so no audit row. |
| `/admin/kits/{kit_id}/commercial` | GET | `require_app_admin` | One kit's resolved `credit_cost`/`cap_usd` (bd polyglot-pdf-f0kuu), via `backend/services/kit_commercials.py::resolve_commercial` -- the SAME reader bead A3's mint transaction calls (Surface contract 24 in [technical_guide.md](../technical_guide.md)); this bead adds no second reader. `source` is `"kit"` when a commercial doc exists, `"default"` otherwise. A read, so no audit row. |
| `/admin/kits/{kit_id}/commercial` | PUT | `require_app_admin` | Set a kit's `credit_cost`/`burn_cap_usd`/`display` (bd polyglot-pdf-f0kuu). Refuses BEFORE any write on a malformed `credit_cost` (must be a positive int), `burn_cap_usd` (must be a positive finite float) or `display` (a small string map) -- 422, deliberately stricter than the read side's fallback: a bad edit must never reach the store as a "successful" write. Audited in the same `@firestore.transactional` body as the write. |
| `/admin/firms/{firm_id}/usage` | GET | `require_app_admin_or_owning_manager` | One firm's usage rollup for one month (bd polyglot-pdf-mpebj, E3.11a) -- `firms/{firm_id}/usage/{month}` (bd polyglot-pdf-w828m), an explicit key allowlist. `?month=YYYY-MM` and `?channel=` are both REQUIRED (422 if missing/malformed). A manager reaches only their own firm (404 for any other, same as an unknown firm_id); an app admin reaches any. A missing rollup doc is an empty reading, not a 404 -- only a nonexistent firm_id 404s. A read, so no audit row. |
| `/admin/kits/{kit_id}/usage` | GET | `require_app_admin` | One kit's usage rollup for one month -- `kits/{kit_id}/usage/{month}`, an explicit key allowlist. `?month=`/`?channel=` REQUIRED. `require_app_admin` only (a kit spans every firm, so there is no owning manager). Does NOT 404 on a kit with no separate profile doc. A read, so no audit row. |
| `/admin/reports/cost` | GET | `require_app_admin` | Parameterised BigQuery read over `cost_by_{firm\|kit\|employee}_month` (bd polyglot-pdf-mpebj, via `admin_backend/services/bigquery_reports.py`). `?from=&to=&group_by=` REQUIRED (422 on missing/malformed/a range over 12 months); `?channel=` optional. Every value is bound as a `bigquery.ScalarQueryParameter`, never interpolated SQL text. Carries `delayed: true` plus a sink-lag note. A read, so no audit row. |
| `/admin/reports/income` | GET | `require_app_admin` | Parameterised BigQuery read over `income_month` (real firms only -- the view's own `firm_kind = 'live'` filter, contract 25). `?from=&to=` REQUIRED; `?channel=` optional. Same parameterisation, 12-month ceiling, and `delayed: true` as the cost report. A read, so no audit row. |
| `/admin/alerts` | GET | `require_app_admin` | Lists `alerts/{id}` docs (bd polyglot-pdf-mpebj; docs: bd polyglot-pdf-bo95a), newest first, page-capped, an explicit key allowlist. Optional `?acknowledged=`/`?firm_id=`/`?kind=` filters (422 on an unrecognized `kind`). A read, so no audit row. |
| `/admin/alerts/{alert_id}/acknowledge` | PATCH | `require_app_admin` | Acknowledge one alert -- sets `acknowledged_by` (the ACTOR's uid) + `acknowledged_at` in one Firestore transaction with an in-transaction audit row (mirrors `firm_routes.py`'s `_apply_firm_patch` shape). 404 for an unknown id; 409 for one already acknowledged, naming who acknowledged it first. The ONE mutating route this bead adds. |
| `/admin/errors` | GET | `require_app_admin` | Cloud Error Reporting `groupStats` for one channel's Cloud Run service (bd polyglot-pdf-mpebj, via `admin_backend/services/error_stats.py`), filtered to `polyglot-backend`/`polyglot-backend-staging`. `?channel=` REQUIRED. Returns count, first/last seen, and the group's representative TYPE and top FRAME ONLY -- the API has no `representative.type` field, so the type is parsed from the terminating line of `representative.message`, which E3.8's PII rule already guarantees is the bare type name with no message text; the rest of that message is never returned. A read, so no audit row. |
| `/admin/health` | GET | `require_app_admin` | Fans out to one channel's PUBLIC backend `/health` + `/version` over a short-timeout HTTP call, plus this service's own `/version` (bd polyglot-pdf-mpebj). `?channel=` REQUIRED. `configured: false` when `BACKEND_URLS_JSON` has no entry for this channel; `reachable: false` (never a 500) when the entry exists but the HTTP calls fail -- `reachable` requires BOTH `/health` and `/version` to succeed. A read, so no audit row. |

`channel` is always an explicit path parameter or query parameter
(validated against `("demo", "staging")`), never derived from the
environment -- the admin service has no channel of its own, since it serves
both channels' data from one deployment.

This is the COMPLETE route set as of this doc's stamp, and it is pinned
mechanically: `admin_backend/tests/unit/test_admin_route_auth.py` derives
the live route set off `admin_backend.main.app` and fails if a route is
added without exactly one of the PLAN'S four gate names
(`require_app_admin`; `require_firm_manager`;
`require_app_admin_or_owning_manager`; `require_google_oidc`). ALL FOUR now
exist; `require_google_oidc` shipped with its first consuming route above
(bd polyglot-pdf-8vgfh) -- Epic 4 4.3's Pub/Sub push route will be its
second. A FIFTH dependency, `require_app_admin_or_owning_manager_or_employee`
(bd polyglot-pdf-scaig), exists beside these four for the ONE route that
needs a third actor kind (`GET /admin/firms/{firm_id}/links` -- see that
gate's own subsection below); it is deliberately outside the four-gate
vocabulary the set-pin test enforces and is instead pinned directly on its
one route. Read that test, not this table, for the authoritative set the
day a new route lands.

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

## `require_app_admin_or_owning_manager_or_employee` (bd polyglot-pdf-scaig)

The ONLY gate on `GET /admin/firms/{firm_id}/links`. Same first two
branches as `require_app_admin_or_owning_manager` above (app admin, then
firm manager), PLUS a third: a firm **employee**, resolved via a new sibling
rule beside `manager_firm_id`, `backend/services/firms.py::employee_firm_id
(claims)` -- accepts only `firm_role == "employee"`, the same shape one role
over. An employee actor's `firm_id` is their own firm and `employee_id` is
their own uid, both from the **verified token**; the route forces
`employee_id` to that value whenever the actor is an employee, silently
overriding any `?employee_id=` the query names (unlike the manager firm-body
rule, naming a DIFFERENT value here is not itself refused -- there is
exactly one value an employee's own filter could ever legitimately mean, so
substituting it is applying the only correct answer, not papering over a
disagreement). `_require_owning_firm` (`link_routes.py`) covers the
employee actor with the SAME check it already used for a manager (both
kinds carry `firm_id` on the actor identically), so an employee naming
another firm gets the same 404-not-403 existence-hiding refusal.

**Why a separate dependency, not a third branch on
`require_app_admin_or_owning_manager` itself:** that gate is also the gate
on all four `/admin/users` routes and on `POST /admin/links/{jti}/revoke`,
where an employee has never had access and must continue not to --
`test_composite_gate.py::test_neither_an_admin_nor_a_manager_is_403`
already pinned an employee claims dict as a 403 through that name, and
widening the shared function would have silently widened every one of
those routes too. The two dependencies share their token-verification body
(`_resolve_admin_or_manager_or_employee_actor(token, allow_employee=...)`
in `admin_auth.py`) so the branch order (app admin first) cannot drift
between them; only whether the employee branch is reachable differs.
`POST /admin/links/{jti}/revoke` deliberately keeps the narrower,
unwidened dependency -- an employee must never revoke a link, and the
route's own dependency graph makes that unreachable rather than relying on
an in-route check.

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

## `require_google_oidc` (the machine-caller gate, bd polyglot-pdf-8vgfh)

The fourth and last gate, for Google-managed service callers (Cloud
Scheduler today; Pub/Sub push in Epic 4) rather than a human sign-in. A
**FACTORY**, not a plain dependency: `require_google_oidc(audience,
allowed_caller_emails)` returns the actual FastAPI dependency, because both
arguments vary per route and per deployment -- the route's own URL (unknown
until after its first deploy) and the specific caller identity it should
accept. A route wires it as
`Depends(require_google_oidc(audience=..., allowed_caller_emails=...))`.

**Both arguments accept a zero-arg callable as well as a plain value**,
resolved fresh on every request rather than once at import time. This
matters because the sweep route's real values come from environment
variables (`ADMIN_SERVICE_URL`, `SWEEP_SCHEDULER_SA_EMAIL`) set at DEPLOY
time, and the route module imports at process START -- reading `os.environ`
eagerly would freeze in whatever value (or absence) existed before a real
deployment finished configuring the service.

**Why audience alone does not prove the caller.** On a public
(`--allow-unauthenticated`) Cloud Run service, the audience claim is simply
this route's own URL -- not a secret. Anyone who can read this source file,
or simply guess the URL, can mint a Google-signed token carrying that SAME
audience from their OWN GCP project (`gcloud auth print-identity-token
--audiences=...`). A valid signature and matching audience together prove
only "Google vouches this token was minted for this URL", never "this
specific caller is the job we created". So the gate ALSO pins the token's
`email` claim against `allowed_caller_emails`, and additionally requires
`email_verified is True` -- a Google service account's email is always
verified by construction, so a token claiming otherwise is not one this
gate should ever accept.

**The status-code split:** 401 for a token that fails verification outright
(bad signature, expired, wrong audience -- retrying with a fresh token might
help); 403 for a token that verifies but whose email is not allowlisted (a
real Google-signed token, just the wrong caller -- retrying will never
help); 503 when the verification machinery itself could not run (a broken
`google-auth` install, or the certs endpoint unreachable) OR when the
route's own configuration is incomplete (an empty audience or empty
allowlist must never be read as "nothing to check against, allow it" --
fail CLOSED).

**The factory's returned closure is renamed to `require_google_oidc`
itself.** `admin_backend/tests/unit/test_admin_route_auth.py`'s route/gate
set pin reads a dependency's bare `__name__` to learn which of the four
known gates a route carries; left as Python's default inner-function name
(`_dependency`), a route wired through this factory would look ungated to
that test. `admin_auth.py` sets `_dependency.__name__ = "require_google_
oidc"` before returning it, which is what keeps detection uniform across
all four gates despite this one being the only factory.

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
the public backend never touches it) and, since bd polyglot-pdf-8vgfh,
`cloudscheduler.googleapis.com`.

**The sweep's caller identity, `admin-sweep-scheduler-sa`, is a SEPARATE
service account from `admin-backend-sa`** (bd polyglot-pdf-8vgfh), also
created by this script. `admin-backend-sa` is the admin service's own
CALLEE identity; `require_google_oidc`'s whole point is pinning a DIFFERENT
identity as the CALLER, so reusing `admin-backend-sa` for both directions
would let one compromised credential both act as the admin service and
trigger it. This account gets no IAM role grants of its own beyond what
Cloud Scheduler needs to mint an OIDC token in its name (`--oidc-service-
account-email` at job-creation time; no extra binding required for that).
The script prints, but does not run, the `gcloud scheduler jobs create
http admin-sweep-expired-links` command that wires this account to the
hourly job -- it needs the admin service's own Cloud Run URL, unknown until
after that service's first deploy. See the route table above and
`admin_backend/routes/sweep_routes.py`'s own docstring for the job's shape.

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
| `roles/bigquery.jobUser` | project | Run BigQuery queries against the telemetry views (Epic 3 bead 6; the actual queries are bd `polyglot-pdf-mpebj`'s `admin_backend/services/bigquery_reports.py`). Granted by `scripts/setup-telemetry.sh`, not this script -- see that script's own comment for why the BigQuery grants live there instead of here. |
| `roles/bigquery.dataViewer` | the telemetry dataset ONLY | Read the cost/income views. Dataset-scoped, not project-wide, so a compromised admin-backend-sa credential cannot read an unrelated BigQuery dataset in the same project. Also granted by `scripts/setup-telemetry.sh`. |
| `roles/errorreporting.viewer` | project | Read Cloud Error Reporting's `groupStats` (bd `polyglot-pdf-mpebj`'s `GET /admin/errors`, `admin_backend/services/error_stats.py`). Granted by `scripts/setup-monitoring.sh` (bd `polyglot-pdf-e4dt8`), not this script. |
| `roles/monitoring.viewer` | project | Read Cloud Monitoring data for a future console metrics view. Also granted by `scripts/setup-monitoring.sh`; no route reads it yet. |

Deferred, deliberately absent until the epic that first needs them (an
unused grant is its own risk): `roles/cloudbuild.builds.editor` +
`roles/iam.serviceAccountUser` on the Cloud Build SA, `roles/run.admin` +
`roles/iam.serviceAccountUser` on `polyglot-backend-sa` (resource-scoped),
`roles/firebasehosting.admin` (Epic 4, deploy control plane).

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
  location), Firms (`pages/FirmsPage.tsx` + `pages/FirmDetailPage.tsx`, bd
  polyglot-pdf-r8z9g -- see below), Kit commercials
  (`pages/KitCommercialsPage.tsx`, bd polyglot-pdf-mzblw -- see below), and
  the five monitoring pages (bd polyglot-pdf-i6dlb, E3.11b -- see below):
  Monitoring (`pages/MonitoringPage.tsx`), Usage (`pages/UsagePage.tsx`),
  Cost & income (`pages/CostReportsPage.tsx`), Alerts
  (`pages/AlertsPage.tsx`), and Errors (`pages/ErrorsPage.tsx`).
  A page's API failures route back to `SignInGate`'s refused screen when
  they are a 401/403 (the account's session ended or was revoked
  mid-session), and to a generic in-page error otherwise -- see `App.tsx`'s
  `handleAuthExpired`.
- **Users page** (`pages/UsersPage.tsx`): the firm-ID field is a REQUIRED
  text input, always shown -- there is no firm-picker dropdown (the Firms
  page's own firm picker is a SEPARATE tab, not wired into this one) and
  because the console's sign-in gate calls only `GET /admin/whoami`
  (`require_app_admin`, the STRICT gate), never the composite
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
- **Firms pages** (`pages/FirmsPage.tsx` + `pages/FirmDetailPage.tsx`, bd
  polyglot-pdf-r8z9g, Epic 2 Track C bead C2): the SECOND page pair under
  `pages/`. `FirmsPage` loads `GET /admin/firms` on mount (deliberately
  unfiltered, matching the route's own contract) and lists every firm's
  kind badge, balance, and status; its create form's `kind` <select> has NO
  default -- an explicit "Choose kind..." placeholder that is never a valid
  `FirmKind`, so the Create button stays disabled until an operator makes
  an active choice, the SAFER direction to default given a mis-defaulted
  LIVE firm can mint for real money (`firm_routes.py`'s own docstring).
  Clicking a firm name opens `FirmDetailPage` as a SUB-STATE of the Firms
  tab (`App.tsx`'s `openFirmId`), not a separate tab -- switching tabs away
  and back to Firms always returns to the list.
  `FirmDetailPage` drives `GET /admin/firms/{firm_id}` (profile, balance,
  and a ledger page), `PATCH .../allowed_kits` (a comma-separated textarea
  committed as a full replace, matching the route's own full-replace
  contract), `PATCH .../kind` (CONFIRM-TWICE IN THE CONSOLE, not the route
  -- `firm_routes.py`'s `SetKindRequest` docstring: "a route cannot see how
  many times a human clicked". Opening the change-kind form is confirmation
  #1; a second dialog, rendered only once a non-blank reason is typed,
  gates the actual `setFirmKind` call as confirmation #2. `reason` is
  REQUIRED client-side ahead of both confirmations, mirroring the route's
  own 422), `POST .../credits/grant` and `.../credits/adjust` (grant shows
  `usd_amount` ONLY for `subscription_grant`/`purchase` -- the two income
  types `credit_routes.py` requires it for; switching the type <select> to
  `promo_grant` clears any typed `usd_amount` so a stale value can never
  ride along on a type the route would refuse it on. Adjust requires a
  non-blank `reason`, enforced by BOTH the input's own `required` attribute
  and a `.trim()` check -- the former alone lets a whitespace-only value
  through), and bead B4's `GET /admin/firms/{firm_id}/links` +
  `POST /admin/links/{jti}/revoke` (a channel `<select>`, defaulting to
  `demo`, reloads the link list on change -- `channel` is a REQUIRED query
  param on both routes per `link_routes.py`'s own 422-on-missing rule;
  Revoke is enabled only on a `minted` link, calls the route once, and
  re-reads the SAME channel's link list afterward). Every mutation on this
  page follows the same MUTATE-THEN-RE-READ round trip `ConfigEditorPage`/
  `UsersPage` already use.
- **Kit commercials page** (`pages/KitCommercialsPage.tsx`, bd
  polyglot-pdf-mzblw, Epic 2 Track C bead C1): the FIRST console page over
  `admin_backend/routes/kit_routes.py`'s three routes. Lists every kit
  (`GET /admin/kits`: kit id, `credit_cost`, `cap_usd`, `source` --
  "kit" when a commercial doc exists, "default" when the kit rides the
  global fallback), then edits ONE kit's pricing at a time: clicking Edit
  loads that kit's fresh commercial (`GET /admin/kits/{kit_id}/commercial`,
  never the list row's already-rendered values, since the list can be
  stale if another operator just saved), and Save `PUT`s the WHOLE body
  (`credit_cost`, `burn_cap_usd`, `display: {}`) -- never a partial patch,
  matching the route's own whole-doc-replace contract. Client-side
  validation mirrors the route's own rules (a positive int credit cost, a
  positive finite burn cap) ahead of the network call, but the server's own
  422 still governs anything that check misses, surfaced next to the named
  field (an allowlist match against the route's own `"credit_cost "` /
  `"burn_cap_usd "` detail prefixes) rather than as a generic banner. A
  successful save re-reads the kit's commercial so the editor reflects what
  the server actually stored, then reloads the list, the same
  MUTATE-THEN-RE-READ pattern the other pages use. KNOWN GAP: because
  neither GET route this page reads ever returns a kit's existing
  `display` value, this page always sends `display: {}` on save, wiping any
  `display.label` a kit was seeded with (bd polyglot-pdf-zcbm1;
  currently cosmetic, since nothing in the repo reads `display.label`
  today).
- **Monitoring pages** (bd polyglot-pdf-i6dlb, E3.11b): the FIFTH page
  group under `pages/`, one page per bd polyglot-pdf-mpebj route.
  `MonitoringPage.tsx` fetches `GET /admin/health` for BOTH channels
  independently on mount into two side-by-side cards -- a slow or failing
  channel never blocks or blanks the other's card. Each card renders one
  of three backend states: `configured: false` ("Not configured"),
  `configured: true, reachable: false` ("Unreachable"), or `reachable:
  true` (the backend's version SHA); a card-level fetch failure (the
  `/admin/health` call itself throwing) is a FOURTH state, that card's own
  error text, still never a blank card. `UsagePage.tsx` loads the firm
  list (`GET /admin/firms`) into a picker, then `GET
  /admin/firms/{firm_id}/usage` for the chosen firm/month/channel; an
  all-null `usage` object (no rollup doc for that month) renders an
  explicit "No usage recorded" message rather than a table of zeros, and
  `by_kit`/`by_employee`/`by_language` render as three sorted-by-key
  tables. `CostReportsPage.tsx` has a Cost tab (`GET /admin/reports/cost`,
  group-by firm/kit/employee, optional channel) and an Income tab (`GET
  /admin/reports/income`, no channel selector -- that route refuses one);
  BOTH refuse a from/to range over `MAX_REPORT_RANGE_MONTHS` (12) months
  CLIENT-SIDE with the identical message `report_routes.py`'s own
  `_validated_range` returns, before any network call, and the server's
  own 422 text still governs anything the client check misses; the
  `delayed`/`note` label renders only when the response's own `delayed`
  flag is true. `AlertsPage.tsx` defaults to `acknowledged=false`
  (unacknowledged-only), with kind/firm filters applied only on submit (a
  `Filter` button, not live-as-you-type, so choosing a kind mid-edit does
  not auto-fire a request); Acknowledge calls `PATCH
  /admin/alerts/{id}/acknowledge` exactly once per click (a per-row
  `busyId` disables the button while in flight) and re-reads the list on
  SUCCESS only -- mirrors `UsersPage.tsx`'s "a failed mutation must not
  trigger the success re-read" rule, so a 409 (already acknowledged by
  someone else) shows that route's own message next to the row without a
  spurious extra read. `ErrorsPage.tsx` has channel tabs over `GET
  /admin/errors`, one fetch per tab switch, rendering ONLY the five
  `ErrorGroup` fields `adminApi.ts` types (count, first/last seen,
  error_type, top_frame) BY NAME -- no spread, no key iteration -- so a
  payload carrying an extra key (a stray `message`) has no code path that
  would ever reach the DOM; pinned by a test that feeds exactly that shape
  and asserts a sentinel value is absent from `document.body.textContent`.
- **API client:** `admin-console/src/utils/adminApi.ts` (`probeWhoAmI`,
  `listAuditRows`, `getChannelConfig`, `setChannelConfigKey`, `listUsers`,
  `createUser`, `setUserDisabled`, `setUserRole`, `listKits`,
  `getKitCommercial`, `setKitCommercial`, `listFirms`, `createFirm`,
  `getFirm`, `setFirmStatus`, `setFirmAllowedKits`, `setFirmKind`,
  `grantCredits`, `adjustCredits`, `listFirmLinks`, `revokeLink`,
  `getChannelHealth`, `getChannelErrors`, `getFirmUsage`, `getCostReport`,
  `getIncomeReport`, `listAlerts`, `acknowledgeAlert` -- the last seven
  added by bd polyglot-pdf-i6dlb, E3.11b, alongside the wire-contract
  exports `MONITORING_CHANNELS`, `COST_GROUP_BY`, `MAX_REPORT_RANGE_MONTHS`,
  `ALERT_KINDS`, `ALERT_LEVELS`), each call
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
audit forms and coverage pin, including `MUTATION_KIND_DELEGATED_
FIRESTORE`), `test_config_routes.py` (the config route's validation and
transactional write), `test_firestore_indexes.py` (the audit route's
filter/index pin), `test_google_oidc_gate.py` (`require_google_oidc`'s own
contract: lazy config resolution, the 401/403/503 split, the closure
rename), `test_sweep_routes.py` (the sweep route end to end through a fake
Firestore, including the forced-audit-failure atomicity pin),
`test_admin_link_routes.py` (bd polyglot-pdf-jmiys: link listing's allowlist
and firm-scoping, and revoke's atomicity and 409/404 refusals, over the
same fake-Firestore shape `test_sweep_routes.py` uses; bd polyglot-pdf-scaig
adds the employee actor's own scoping -- token-not-query `employee_id`, one
employee never seeing another's links, the 404-not-403 rule extending to an
employee, and a direct pin that revoke's route wiring still carries only
the narrower gate), `test_composite_gate.py` (bd polyglot-pdf-scaig: the new
`require_app_admin_or_owning_manager_or_employee` gate's own branch
resolution and 401/403 splits, plus a pin that the ORIGINAL
`require_app_admin_or_owning_manager` still 403s an employee claims dict
unchanged), `test_require_firm_manager.py` (bd polyglot-pdf-scaig adds
`employee_firm_id`'s own whole-claim-space enumeration beside
`manager_firm_id`'s, plus a check that the two rules never both accept the
same claims), `test_kit_routes.py`
(bd polyglot-pdf-f0kuu: PUT's in-transaction audit atomicity, the
parametrized 422 refusal over every malformed `credit_cost`/`burn_cap_usd`/
`display` shape -- including bool-as-number and NaN/+-inf sent as raw JSON
body bytes, since httpx's own client-side encoder cannot serialize a
Python `float("nan")` -- GET's shared-reader import pin, and the list
route's join over a faked `FormKitStore`). The PUBLIC backend's
`backend/tests/integration/test_revoked_link_open.py` pins the OTHER half
of B4's exit criterion 3 -- a revoked link's subsequent open is refused with
the uniform 404 -- over the real `POST /api/links/open` route; that
assertion depends on Epic 2 Track A bead A3's open-side gate
(`backend/routes/link_routes.py` reading `links_store.get_link`), landing
separately from this bead. The sibling
root-level `tests/test_setup_admin_service_scheduler.py` pins
`setup-admin-service.sh`'s Cloud Scheduler declaration by its shipped
script TEXT, the same operator-script pattern as
`tests/test_setup_firestore_ttl_script.py`. `admin-console/src/components/
*.test.tsx` and `admin-console/src/pages/*.test.tsx` cover the console
pages (Vitest, same harness as `schema-editor/`).

**bd polyglot-pdf-mpebj (E3.11a) adds:** `test_usage_routes.py` (the
required month/channel validation, the doc-id resolution matching
`usage_rollups.py`'s own demo-bare/other-suffixed convention, the explicit
key allowlist, "a missing rollup doc is an empty reading, not a 404", and
the firm route's manager 404-not-403 scoping); `test_report_routes.py`
(the required from/to/group_by validation, the 12-month range ceiling
pinned in BOTH directions -- exactly 12 months allowed, 13 refused --
every value asserted as a bound `bigquery.ScalarQueryParameter` that never
appears literally in the SQL text, the `delayed: true` + note on every
response, and a `BigQueryUnavailable` -> 503 mapping, all against
`bigquery_reports.py`'s own `_run_query` seam rather than a real BigQuery
client); `test_alert_routes.py` (list filters and ordering, and
acknowledge's atomicity pin over the SAME real-transaction fake Firestore
shape `test_sweep_routes.py`/`test_kit_routes.py` use -- a forced audit
failure leaves `acknowledged_at` unset, and acknowledging twice is a 409
that leaves the first acknowledger's identity and audit-row count
untouched); `test_ops_routes.py` (the required `?channel=` on both routes;
`GET /admin/errors` returns type + top frame only for a mocked
`groupStats` payload carrying a sentinel message, with the sentinel
asserted absent from the raw response TEXT, not just from a typed field;
`GET /admin/health` returns a partial result -- `reachable: false`, never
a 500 -- when the backend is unreachable, requires BOTH `/health` and
`/version` to succeed for `reachable: true`, and parses `BACKEND_URLS_JSON`
's real `"channel=url;channel=url"` wire format, including the
missing-entry-is-`configured: false` and malformed-segment-degrades cases).
`test_admin_route_auth.py` and `test_admin_audit_coverage.py` both grew:
the former with the eight new routes in the registered-set pin plus two
gate-specificity tests (the firm-usage route's composite gate; every other
new route's plain `require_app_admin`), the latter with the one new
mutating route (`PATCH /admin/alerts/{alert_id}/acknowledge`,
`MUTATION_KIND_FIRESTORE`, its own transaction) and its synthetic-check
tie-back.
