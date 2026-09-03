"""FastAPI app for the privileged admin service (Cloud Run: polyglot-admin).

Skeleton stage (bd polyglot-pdf-pnoik): the app, CORS, /health and /version
only. Routers and the require_app_admin gate land in bd polyglot-pdf-7w17m.

THE ADMIN SERVICE HAS NO CHANNEL. It serves BOTH staging's and the demo's
data, so nothing here may derive a Firestore collection name from
LINK_CHANNEL -- the channel is an explicit argument on every shared helper
that needs one (see the plan's "Architecture" section). What separates test
money from real money is the FIRM's kind, never the channel.

Cloud Run runs this service with --allow-unauthenticated plus an app-level
gate on EVERY route, so nothing is reachable without an app_admin claim once
the routers land. /health is deliberately the exception: Cloud Run's own
reachability probe and deploy-all.sh's post-deploy gate call it unauthenticated,
and it reports no data an unauthenticated caller could not already infer.
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

load_dotenv()

from backend.config import get_settings, parse_extra_origins
from backend.utils.logging import configure_logging

# The ASGI target the container actually launched, and the default the
# Dockerfile falls back to when APP_MODULE is unset. Kept as a module constant
# rather than a backend.config.Settings field because APP_MODULE selects WHICH
# app runs -- it is read before either app's settings exist, and the public
# backend never consults it. The Dockerfile CMD and this default are pinned
# together by tests/test_dockerfile_app_module.py, so they cannot drift.
DEFAULT_APP_MODULE = "backend.main:app"


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
        "app_module": os.getenv("APP_MODULE", DEFAULT_APP_MODULE),
    }


@app.get("/version")
async def version():
    return {"version": app.version}
