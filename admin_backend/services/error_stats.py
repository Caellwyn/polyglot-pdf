"""Cloud Error Reporting groupStats REST reader (bd polyglot-pdf-mpebj,
E3.11a) -- the console's error-rate view for one channel.

WHAT THIS CALLS. `projects.groupStats.list` (Error Reporting API v1beta1),
`GET https://clouderrorreporting.googleapis.com/v1beta1/projects/{project}
/groupStats`, filtered to the channel's own Cloud Run SERVICE NAME
(`polyglot-backend` for demo, `polyglot-backend-staging` for staging --
resolved by report_error_routes.py's caller, never derived here) via the
`serviceFilter.service` query parameter. Error Reporting GROUPS entries by
their exception frames (Surface contract 28a: "GROUPS on the frames"); this
route reads the resulting per-group STATS, not individual log entries.

AUTHENTICATED WITH THE RUNTIME SERVICE ACCOUNT'S ADC TOKEN (google.auth,
same library admin_auth.py already uses for OIDC verification), never a
hand-managed API key -- admin-backend-sa already holds
`roles/errorreporting.viewer` (Surface contract 28a's own note; granted by
`scripts/setup-monitoring.sh`, bd polyglot-pdf-e4dt8), so this bead needs no
new IAM grant.

NEVER RETURNS A MESSAGE BODY -- ONLY TYPE + TOP FRAME (exit criterion 3;
E3.8's PII rule, docs/standards/hipaa-pii-policy.md, reaching the console
too).

`representative.type` DOES NOT EXIST ON THE REAL API. `ErrorEvent` (the
schema of `groupStats.representative`) has exactly four properties --
`context`, `serviceContext`, `message`, `eventTime` -- per the live
v1beta1 discovery document (fetch it yourself: `curl -s
"https://clouderrorreporting.googleapis.com/$discovery/rest?version=v1beta1"
| python -c "import json,sys; print(list(json.load(sys.stdin)['schemas']
['ErrorEvent']['properties']))"` prints exactly those four names). No
schema in that API defines `type`, `errorType`, or `exceptionType` on a
representative sample, so `representative.get("type")` always returns
None; the field the API actually exposes is `representative.message`.

`representative.message` IS SAFE TO READ HERE, because of what Surface
contract 28a's WRITE side (backend/utils/logging.py's
`pii_safe_exception_processor` / `pii_safe_exception_info`) already
guarantees about it before it ever reaches Error Reporting: the
`stack_trace` field that processor emits -- which Error Reporting ingests
as a qualifying log entry's display message, becoming this group's
`representative.message` -- carries ONLY frames (`file`, `line`,
`function`) and, on the terminating line of each chained block, the bare
exception TYPE NAME with nothing appended (`pii_safe_exception_info`'s own
comment: "TYPE ONLY on the terminating line ... we print \"ValueError\"
and stop"). So in THIS repo's own error paths, `representative.message`
can never carry a field value -- the write side already closed that door.

`_error_type_from_message` below reads the type back out WITHOUT
reopening a way for some OTHER shape of message (a differently-rendered
log entry, a future change to the processor) to leak a real message
through by accident: it takes ONLY the LAST non-blank line, and returns it
ONLY if that line is a single bare token (no whitespace, no ":") --
exactly the shape `pii_safe_exception_info` guarantees and nothing an
ordinary "ValueError: <message>" rendering would ever produce. Any other
shape -- multiple words, a colon, an empty message -- yields `None`
rather than a guess, so a message this module does not recognize as
type-only degrades to "unknown" instead of leaking. The REST of the
message (every frame line) is discarded outright: it is parsed only to
find the last line, never stored, returned, or logged by this module. The
FIRST frame's `filePath`/`lineNumber`/`functionName` still comes from
`representative.context.reportLocation` -- the one location field Error
Reporting's schema exposes on a group's representative sample, itself
already frame-shaped (file/line/function, no source text).

THE HTTP CALL IS THE ONE SEAM A TEST MONKEYPATCHES (this module's
`_fetch_group_stats`), mirroring bigquery_reports.py's `_run_query` and
admin_auth.py's `_verify_google_id_token` -- the SDK/transport boundary is
isolated so route-level tests never need real GCP credentials or network
access.

DISPATCHED WITH asyncio.to_thread by the calling route (this module's own
functions are synchronous, matching google.auth's transport).

ASCII only.
"""
from __future__ import annotations

from typing import Any, Optional

import structlog

_log = structlog.get_logger().bind(module="error_stats")

_ERROR_REPORTING_BASE = "https://clouderrorreporting.googleapis.com/v1beta1"

# Cloud Run service names per channel -- the SAME two names deploy-admin.sh
# and every other admin-service module that fans out by channel already
# uses (deploy-all.sh's own BACKEND_SERVICE_NAME defaults: "polyglot-backend"
# for demo, "polyglot-backend-staging" for staging). Restated here as this
# module's own literal for the same reason every other admin route module
# keeps its own small channel constants rather than importing a deploy
# script's shell variable.
SERVICE_NAME_BY_CHANNEL = {
    "demo": "polyglot-backend",
    "staging": "polyglot-backend-staging",
}


class ErrorReportingUnavailable(Exception):
    """The ADC token could not be minted, or the groupStats call itself
    failed (network, auth, a non-2xx response). Mapped to a 503 by the
    calling route, mirroring bigquery_reports.BigQueryUnavailable and
    admin_auth.OidcVerificationUnavailable's identical polarity."""


def _project_id() -> str:
    """The GCP project id this service runs in, from google.auth's own ADC
    resolution -- never hard-coded, so this module works identically in
    whatever project a deploy actually lands in.
    """
    import google.auth

    try:
        _, project = google.auth.default()
    except Exception as exc:  # noqa: BLE001
        raise ErrorReportingUnavailable(
            "could not resolve ADC project: {}".format(exc)) from exc
    if not project:
        raise ErrorReportingUnavailable(
            "ADC resolved no project id")
    return project


def _access_token() -> str:
    """A bearer access token for the runtime service account's ADC
    credentials, refreshed if necessary -- the same google.auth machinery
    admin_auth.py's _verify_google_id_token already depends on."""
    import google.auth
    import google.auth.transport.requests

    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())
    except Exception as exc:  # noqa: BLE001
        raise ErrorReportingUnavailable(
            "could not mint an ADC access token: {}".format(exc)) from exc
    return credentials.token


def _fetch_group_stats(project: str, token: str, service: str) -> dict:
    """The raw groupStats.list JSON response for one Cloud Run service. THE
    ONE SEAM a test monkeypatches -- see module docstring."""
    import requests

    url = "{}/projects/{}/groupStats".format(_ERROR_REPORTING_BASE, project)
    params = {
        "serviceFilter.service": service,
        # A generous but bounded time window -- groupStats defaults to a
        # short recent window server-side if omitted; naming it explicitly
        # keeps this module's behavior independent of that default ever
        # changing. PERIOD_1_HOUR/PERIOD_1_DAY/PERIOD_1_WEEK/PERIOD_1_MONTH
        # are the enum's own values; 1 week is a reasonable "what should an
        # operator worry about" default for a console glance.
        "timeRange.period": "PERIOD_1_WEEK",
        "pageSize": 100,
    }
    try:
        resp = requests.get(
            url, params=params,
            headers={"Authorization": "Bearer {}".format(token)},
            timeout=10.0,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise ErrorReportingUnavailable(
            "groupStats.list failed: {}".format(exc)) from exc
    return resp.json()


def _error_type_from_message(message: Optional[str]) -> Optional[str]:
    """The bare exception type name from a `representative.message` string
    this repo's own write side produced -- see module docstring for the
    exact guarantee this leans on and why reading `representative.message`
    is safe here.

    Returns the LAST non-blank line ONLY IF that line is a single bare
    token (no whitespace, no ":"). `pii_safe_exception_info` always ends
    each rendered block with exactly that shape -- the exception class
    name alone, e.g. "ValueError" -- and never appends a colon or a
    message. Anything else (multiple words, a colon, an empty message)
    returns None rather than guess: this function is deliberately narrow
    so a message this module does not recognize as type-only degrades to
    "unknown" instead of parsing further into it.
    """
    if not message:
        return None
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return None
    candidate = lines[-1]
    if " " in candidate or ":" in candidate:
        return None
    return candidate


def _public_group_view(group: dict) -> dict:
    """Count, first/last seen, and the group's representative TYPE and top
    frame ONLY -- see module docstring for why reading
    `representative.message` (to recover the type token) is safe here, and
    why the rest of that message is never returned.
    """
    representative = group.get("representative") or {}
    report_location = (
        (representative.get("context") or {}).get("reportLocation") or {}
    )
    return {
        "group_id": group.get("group", {}).get("groupId"),
        "count": int(group.get("count") or 0),
        "first_seen_time": group.get("firstSeenTime"),
        "last_seen_time": group.get("lastSeenTime"),
        "error_type": _error_type_from_message(representative.get("message")),
        "top_frame": {
            "file_path": report_location.get("filePath"),
            "line_number": report_location.get("lineNumber"),
            "function_name": report_location.get("functionName"),
        },
    }


def channel_error_stats(channel: str) -> list[dict[str, Any]]:
    """Every error group for one channel's Cloud Run service, allowlisted
    to count/first-seen/last-seen/type/top-frame (exit criterion 3).

    `channel` must already be a key of SERVICE_NAME_BY_CHANNEL -- the
    calling route's own 422 for an unrecognized channel runs before this is
    ever called; this function KeyErrors on anything else rather than
    silently defaulting.
    """
    service = SERVICE_NAME_BY_CHANNEL[channel]
    project = _project_id()
    token = _access_token()
    raw = _fetch_group_stats(project, token, service)
    groups = raw.get("errorGroupStats") or []
    return [_public_group_view(g) for g in groups]
