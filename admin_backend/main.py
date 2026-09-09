"""FastAPI app for the privileged admin service (Cloud Run: polyglot-admin).

The app, CORS, /health and /version were the skeleton stage (bd
polyglot-pdf-pnoik). bd polyglot-pdf-7w17m adds the first gate
(require_app_admin, admin_backend/services/admin_auth.py) and the first
route (GET /admin/whoami); bd polyglot-pdf-li9x0 adds the audit log and its
first consumers (GET/PUT /admin/config/{channel}, GET /admin/audit) -- every
OTHER route added to this service from
here on must carry one of the four gates named in the plan
(require_app_admin; require_firm_manager; require_app_admin_or_owning_
manager; require_google_oidc), which admin_backend/tests/unit/
test_admin_route_auth.py enforces by deriving the registered route set.

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

from admin_backend.routes import audit_routes, config_routes, user_routes
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
