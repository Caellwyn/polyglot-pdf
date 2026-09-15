"""FastAPI app for the privileged admin service (Cloud Run: polyglot-admin).

The app, CORS, /health and /version were the skeleton stage (bd
polyglot-pdf-pnoik). bd polyglot-pdf-7w17m adds the first gate
(require_app_admin, admin_backend/services/admin_auth.py) and the first
route (GET /admin/whoami); bd polyglot-pdf-li9x0 adds the audit log and its
first consumers (GET/PUT /admin/config/{channel}, GET /admin/audit); bd
polyglot-pdf-dmjl5 adds the four staff-account routes (POST + GET
/admin/users, PATCH /admin/users/{uid}/disable, PATCH .../role) behind the
composite gate require_app_admin_or_owning_manager, and with them the first
consumers of the audit log's pending-then-committed form; bd polyglot-pdf-
zopqq adds firm CRUD (admin_backend/routes/firm_routes.py) and credit
grant/adjust (admin_backend/routes/credit_routes.py), both behind
require_app_admin and both auditing in-transaction, reusing
backend/services/firms.py::upsert_firm and
backend/services/credit_ledger.py::append_entry rather than adding a second
writer of either. bd polyglot-pdf-8vgfh adds the fourth and last gate,
require_google_oidc, with its first consuming route (POST
/admin/links/sweep-expired, the hourly Cloud Scheduler expired-link
refund sweep). bd polyglot-pdf-jmiys adds link listing (GET
/admin/firms/{firm_id}/links) and revoke (POST /admin/links/{jti}/revoke),
both behind require_app_admin_or_owning_manager -- a manager sees and
revokes only their own firm's links (admin_backend/routes/link_routes.py).
Every route added to this service from
here on must carry one of the four gates named in the plan
(require_app_admin; require_firm_manager; require_app_admin_or_owning_
manager; require_google_oidc), which admin_backend/tests/unit/
test_admin_route_auth.py enforces by deriving the registered route set.
bd polyglot-pdf-f0kuu adds kit commercial settings (GET /admin/kits, GET/PUT
/admin/kits/{kit_id}/commercial), behind require_app_admin, reusing bead
A3's backend/services/kit_commercials.py reader rather than adding a second
one (admin_backend/routes/kit_routes.py). bd polyglot-pdf-mpebj (E3.11a)
adds the monitoring console's READ routes: GET /admin/firms/{firm_id}/usage
+ GET /admin/kits/{kit_id}/usage (admin_backend/routes/usage_routes.py, the
E3.4 rollup docs), GET /admin/reports/cost + GET /admin/reports/income
(admin_backend/routes/report_routes.py, parameterised BigQuery reads over
the E3.6 views via admin_backend/services/bigquery_reports.py), GET
/admin/alerts + PATCH /admin/alerts/{id}/acknowledge (admin_backend/routes/
alert_routes.py, the E3.5 alert docs -- the one mutation here, audited
in-transaction), and GET /admin/errors + GET /admin/health
(admin_backend/routes/ops_routes.py: Error Reporting groupStats via
admin_backend/services/error_stats.py, and a per-channel public-backend
health/version fan-out over the new BACKEND_URLS_JSON env var). All behind
require_app_admin except the firm usage route, which reuses
require_app_admin_or_owning_manager (a manager reads only their own firm's
usage, 404 not 403 for another firm -- mirroring bead B4's rule). bd
polyglot-pdf-tb3kp (E4.3) adds POST/GET /admin/deploys + GET
/admin/deploys/{id} (admin_backend/routes/deploy_routes.py, behind
require_app_admin -- triggers a Cloud Build via
admin_backend/services/cloud_build.py and reads back the deployments/{id}
rows it writes) and POST /api/deploys/webhook (admin_backend/routes/
deploy_webhook.py, the Pub/Sub push endpoint for Cloud Build's build-status
notifications, behind require_google_oidc -- this gate's SECOND consuming
route after bead 8vgfh's sweep route).

THE ADMIN SERVICE HAS NO CHANNEL. It serves BOTH staging's and the demo's
data, so nothing here may derive a Firestore collection name from
LINK_CHANNEL -- the channel is an explicit argument on every shared helper
that needs one (see the plan's "Architecture" section). What separates test
money from real money is the FIRM's kind, never the channel.

Cloud Run runs this service with --allow-unauthenticated plus an app-level
gate on EVERY route, so nothing is reachable without an app_admin claim once
the routers land. /health is deliberately the exception: it is the
unauthenticated liveness probe, and it reports no data an unauthenticated
caller could not already infer.

NOTE on the deploy gate: deploy-all.sh's post-deploy
verify_service_publicly_reachable() does NOT call this route -- it reads the
Cloud Run IAM policy for an allUsers roles/run.invoker binding and issues no
HTTP request. But this service's own deploy bridge, deploy-admin.sh (bd
polyglot-pdf-3l2vp), sets BACKEND_NO_TRAFFIC_TAG, which makes deploy-all.sh
additionally curl THIS route at the tagged candidate revision's own stable
URL and gate `update-traffic --to-latest` on a 200 -- so for the admin
service specifically, a broken /health on a new revision now DOES abort the
deploy before that revision ever receives traffic. (A public-backend deploy
that sets no tag still gets none of this -- the IAM check is the only gate
there.)
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

load_dotenv()

from backend.config import get_settings, parse_extra_origins
from backend.utils.logging import configure_logging

from admin_backend.routes import (
    alert_routes, audit_routes, config_routes, credit_routes, deploy_routes,
    deploy_webhook, firm_routes, kit_routes, link_routes, ops_routes,
    report_routes, sweep_routes, usage_routes, user_routes,
)
from admin_backend.routes import whoami as whoami_routes

# The ASGI target the container actually launched, and the default the
# Dockerfile falls back to when APP_MODULE is unset. Kept as a module constant
# rather than a backend.config.Settings field because APP_MODULE selects WHICH
# app runs -- it is read before either app's settings exist, and the public
# backend never consults it. The Dockerfile CMD and this default are pinned
# together by tests/test_dockerfile_app_module.py, so they cannot drift.
DEFAULT_APP_MODULE = "backend.main:app"


def _active_app_module() -> str:
    """The ASGI target, resolved the way the CONTAINER resolves it.

    Mirrors the Dockerfile's `${APP_MODULE:-backend.main:app}`, which is the
    `:-` form: it falls back when the variable is UNSET **or EMPTY**. A plain
    os.getenv("APP_MODULE", DEFAULT_APP_MODULE) agrees only on unset -- it
    returns '' for an empty value -- so /health would report an empty
    app_module while answering the one question the field exists to answer.
    Reading it through one helper keeps the two readers in agreement on both
    states rather than only on the default string.
    """
    return os.getenv("APP_MODULE") or DEFAULT_APP_MODULE


configure_logging()

_log = structlog.get_logger().bind(module="admin_main")

app = FastAPI(title="Polyglot Admin API", version="0.1.0")

# The admin CONSOLE is a separate Vite app on its own Hosting site, so it is
# always a cross-origin caller -- there is no same-origin Hosting rewrite in
# front of this service. Its hosted origin(s) arrive through
# CORS_EXTRA_ORIGINS at deploy time (semicolon-separated: the value rides
# inside gcloud's comma-separated --set-env-vars block, see
# parse_extra_origins), so a new console origin never needs a code change.
# The localhost entries are the console's and the main app's dev servers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3001",  # schema-editor dev server
        "http://127.0.0.1:3001",
        "http://localhost:3002",  # admin-console dev server
        "http://127.0.0.1:3002",
    ] + parse_extra_origins(get_settings().CORS_EXTRA_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Liveness + identity probe.

    Deliberately THIN compared with the public backend's /health: this service
    proxies no model and owns no confirmation sink, so there is nothing to
    probe but the process itself. It reports which ASGI module is live, which
    is the one fact a deploy of the shared image most needs to confirm --
    APP_MODULE is a runtime env var, so a service pointed at the wrong module
    would otherwise look healthy while serving the wrong app.
    """
    return {
        "status": "ok",
        "service": "polyglot-admin",
        "app_module": _active_app_module(),
    }


@app.get("/version")
async def version():
    """App version plus the deployed commit SHA.

    Same GIT_SHA runtime env var and "unknown" fallback (including the
    empty-string case; see backend/main.py's version route) as the public
    backend's /version (bd polyglot-pdf-9hzod) -- the admin console's "what
    is live per channel" view (bead 1.7) reads this route on both services.
    Set by the deploy bridge (bead 1.3) via `--set-env-vars
    GIT_SHA=$(git rev-parse HEAD)` until Cloud Build's $COMMIT_SHA takes
    over (Epic 4).
    """
    return {"version": app.version, "git_sha": os.getenv("GIT_SHA") or "unknown"}


app.include_router(whoami_routes.router)
app.include_router(config_routes.router)
app.include_router(audit_routes.router)
app.include_router(user_routes.router)
app.include_router(firm_routes.router)
app.include_router(credit_routes.router)
app.include_router(link_routes.router)
app.include_router(sweep_routes.router)
app.include_router(kit_routes.router)
app.include_router(usage_routes.router)
app.include_router(report_routes.router)
app.include_router(alert_routes.router)
app.include_router(ops_routes.router)
app.include_router(deploy_routes.router)
app.include_router(deploy_webhook.router)
