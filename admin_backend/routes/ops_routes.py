"""GET /admin/errors and GET /admin/health -- the console's per-channel
operational views (bd polyglot-pdf-mpebj, E3.11a).

BOTH BEHIND require_app_admin -- these are operator-only concerns (matching
kit_routes.py's / report_routes.py's own "no firm-manager counterpart"
reasoning).

GET /admin/errors CALLS error_stats.channel_error_stats(channel) (Cloud
Error Reporting's groupStats REST endpoint, admin_backend/services/
error_stats.py) -- see that module's own docstring for the type-and-top-
frame-only shape (exit criterion 3) and why the message body is never
read. `?channel=demo|staging` is REQUIRED (422 on anything else), matching
every other admin route's required-channel rule.

GET /admin/health FANS OUT to the requested channel's PUBLIC backend
/health and /version over plain HTTP with a SHORT timeout, plus this
service's OWN /version (never a second HTTP call for that -- this route
runs IN the admin service, so its own version is a plain in-process read,
not a network hop). ONE CHANNEL BEING UNREACHABLE YIELDS A PARTIAL RESULT
(exit criterion 3's other half: `reachable: false`, never a 500) -- an
operator checking on the demo must still see the admin service's own
health even when staging's backend happens to be down, and vice versa.

THE PER-CHANNEL BACKEND BASE URLS COME FROM BACKEND_URLS_JSON (bead
requirement), a NEW admin-service-only env var, because the admin service
has no channel of its own (admin_backend/main.py's own docstring) and
therefore cannot derive either public backend's URL the way each public
backend's own deploy resolves its sibling. deploy-admin.sh resolves it with
`gcloud run services describe` the same way deploy-all.sh resolves
VITE_WS_URL (see that script's own comment on this route's env var).

WIRE FORMAT IS "channel=url;channel=url", NOT LITERAL JSON, even though the
env var keeps the plan's own name (BACKEND_URLS_JSON) -- see
deploy-admin.sh's own comment on this same variable for why: it rides
inside a comma-joined --set-env-vars block (deploy-all.sh's BACKEND_ENV
assembly), and a literal JSON object's "," between key/value pairs would be
silently split apart as a malformed second env-var entry the moment it is
appended there, the exact reason CORS_EXTRA_ORIGINS is semicolon-separated
rather than comma-separated. _backend_urls() below is the ONE parser for
this shape; a channel name outside KNOWN_CHANNELS or a malformed segment
(no "=", or an empty url) is skipped rather than raising, matching the
overall "malformed input degrades to nothing configured" polarity.

A MISSING ENTRY FOR A REQUESTED CHANNEL MAKES THAT CHANNEL
`configured: false` (bead requirement) -- distinctly from `reachable: false`
(configured, but the HTTP call itself failed): an operator debugging a
blank health page needs to know whether nobody has wired the URL yet, or
whether it IS wired and the backend is actually down.

BACKEND_URLS_JSON IS READ AT REQUEST TIME, NOT IMPORT TIME (mirrors
sweep_routes.py's own ADMIN_SERVICE_URL / SWEEP_SCHEDULER_SA_EMAIL
resolution and require_google_oidc's own callable-value contract) -- an
env var set at deploy time must not freeze into whatever value existed
when this module was first imported, and a test must be able to exercise
both the configured and unconfigured cases without reloading the module.

A READ, SO NEITHER ROUTE AUDITS.

ASCII only.
"""
from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from admin_backend.services import error_stats
from admin_backend.services.admin_auth import AdminActor, require_app_admin

_log = structlog.get_logger().bind(module="admin_ops_routes")

router = APIRouter()

# The two channels that actually exist -- restated here rather than
# imported, matching every other admin route module's own copy.
KNOWN_CHANNELS = ("demo", "staging")

# The short per-call timeout for the health/version fan-out (module
# docstring: one unreachable channel must not hang the whole request).
_HEALTH_FETCH_TIMEOUT_S = 5.0


def _validated_channel(channel: Optional[str]) -> str:
    if not channel or channel not in KNOWN_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail="channel is required and must be one of {}".format(
                ", ".join(KNOWN_CHANNELS)),
        )
    return channel


@router.get("/admin/errors")
async def get_channel_errors(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    channel: Annotated[Optional[str], Query()] = None,
) -> dict:
    """Error Reporting group stats for one channel's Cloud Run service
    (exit criterion 3): count, first/last seen, and the group's TYPE and
    top FRAME only -- never a message body. `?channel=` is REQUIRED.
    """
    channel = _validated_channel(channel)
    try:
        groups = await asyncio.to_thread(
            error_stats.channel_error_stats, channel)
    except error_stats.ErrorReportingUnavailable as exc:
        _log.error("admin_errors_read_failed", channel=channel,
                   error_type=type(exc).__name__)
        raise HTTPException(status_code=503,
                            detail="error reporting unavailable") from exc

    return {"channel": channel,
            "service": error_stats.SERVICE_NAME_BY_CHANNEL[channel],
            "groups": groups}


def _backend_urls() -> dict[str, str]:
    """The per-channel public backend base URLs from BACKEND_URLS_JSON, or
    {} if unset/malformed -- read fresh on every call (see module
    docstring).

    PARSES "channel=url;channel=url", NOT json.loads -- see module
    docstring for why the wire format differs from the env var's name. Any
    malformed segment (no "=", an empty url, or a channel outside
    KNOWN_CHANNELS) is SKIPPED rather than raising, matching
    runtime_config.py's own defensive-read polarity for a hand-edited env
    var: an operator's typo in a `--set-env-vars` block must degrade that
    ONE channel to `configured: false`, never crash this route or silently
    poison the other channel's entry.
    """
    raw = os.getenv("BACKEND_URLS_JSON", "")
    if not raw:
        return {}
    urls: dict[str, str] = {}
    for segment in raw.split(";"):
        segment = segment.strip()
        if not segment or "=" not in segment:
            continue
        channel, _, url = segment.partition("=")
        channel = channel.strip()
        url = url.strip()
        if channel in KNOWN_CHANNELS and url:
            urls[channel] = url
        else:
            _log.error("backend_urls_json_segment_malformed",
                       segment=segment)
    return urls


def _fetch_backend_probe(base_url: str) -> dict[str, Any]:
    """{"health": {...} or None, "version": {...} or None, "reachable":
    bool} for one backend base URL -- a SYNCHRONOUS helper (run under
    asyncio.to_thread by the caller), matching every other admin-service
    call into a blocking client (bigquery_reports.py, error_stats.py) for
    the same "no second async HTTP stack" reason.

    reachable is True only when BOTH calls succeed -- a backend that
    answers /health but not /version (or the reverse) is not fully healthy
    from an operator's point of view, and reporting reachable=True on a
    half-answer would hide the very degradation this route exists to
    surface. Each call is independently try/excepted so a slow or broken
    /version does not prevent /health's body from being shown at all.
    """
    try:
        import requests
    except ImportError as exc:  # pragma: no cover -- pinned dependency
        _log.warning("admin_health_fetch_failed", base_url=base_url,
                     probe="import", error_type=type(exc).__name__)
        return {"health": None, "version": None, "reachable": False}

    health_body = None
    version_body = None
    try:
        resp = requests.get(
            "{}/health".format(base_url), timeout=_HEALTH_FETCH_TIMEOUT_S)
        resp.raise_for_status()
        health_body = resp.json()
    except Exception as exc:  # noqa: BLE001 -- one channel's outage must
        # not fail the whole /admin/health response (module docstring).
        _log.warning("admin_health_fetch_failed", base_url=base_url,
                     probe="health", error_type=type(exc).__name__)
    try:
        resp = requests.get(
            "{}/version".format(base_url), timeout=_HEALTH_FETCH_TIMEOUT_S)
        resp.raise_for_status()
        version_body = resp.json()
    except Exception as exc:  # noqa: BLE001
        _log.warning("admin_health_fetch_failed", base_url=base_url,
                     probe="version", error_type=type(exc).__name__)

    return {
        "health": health_body,
        "version": version_body,
        "reachable": health_body is not None and version_body is not None,
    }


@router.get("/admin/health")
async def get_channel_health(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    channel: Annotated[Optional[str], Query()] = None,
) -> dict:
    """This channel's public backend /health + /version, plus the admin
    service's own /version. `?channel=` is REQUIRED. `configured: false`
    when BACKEND_URLS_JSON carries no entry for this channel (never a 500);
    `reachable: false` when the entry exists but the HTTP calls themselves
    fail (exit criterion 3).
    """
    from admin_backend.main import _active_app_module, app as admin_app

    channel = _validated_channel(channel)
    urls = _backend_urls()
    base_url = urls.get(channel)

    if not base_url:
        backend_probe = {
            "configured": False, "reachable": False,
            "health": None, "version": None,
        }
    else:
        probe = await asyncio.to_thread(_fetch_backend_probe, base_url)
        backend_probe = {"configured": True, **probe}

    return {
        "channel": channel,
        "backend": backend_probe,
        "admin_service": {
            "version": admin_app.version,
            "git_sha": os.getenv("GIT_SHA") or "unknown",
            "app_module": _active_app_module(),
        },
    }
