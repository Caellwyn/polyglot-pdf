"""Read-only, redacted live PII sweep of Cloud Logging + BigQuery (bd
polyglot-pdf-v8l6m, sprint 23 workstream B2: verifies PF-1/PF-2 in production
and closes bd polyglot-pdf-yqg's "BigQuery field-value scan returns zero"
criterion).

WHAT THIS IS. B0 (bd polyglot-pdf-6rj0j) turned off the uvicorn access log
and (once the maintainer's live exclusion landed) narrowed the Cloud Run
request log's exposure of the WS `?token=` credential. This script is the
LIVE VERIFICATION that those fixes actually stopped new hits, applied over
Cloud Logging for `polyglot-backend`, `polyglot-backend-staging` and
`polyglot-admin` (both the application streams -- stdout/stderr -- and
`run.googleapis.com/requests`), and over the BigQuery telemetry tables that
exist. It never prints a match -- only COUNTS per (service, logName,
detector, jsonPayload key) plus insertId/timestamp lists for hits.

DETECTORS (deliberately TIGHT -- a loose `A\\d{8,9}` matched 227 bead ids in
the tracker mirror alone, per this bead's own report):
  - ws_token_in_url: `[?&]token=` inside `httpRequest.requestUrl` only.
  - jwt: a two-segment JWT shape, `\\beyJ[\\w-]{20,}\\.eyJ` (Firebase ID
    tokens are JWTs; anywhere in the payload).
  - link_token_in_url: this app's own one-dot signed link-token shape
    (base64url payload + "." + base64url HMAC, see
    backend/services/link_tokens.py::mint_link_token), matched ONLY inside
    a URL-shaped string (a query value or a request URL) -- unscoped, a
    base64-ish string with an incidental dot anywhere in a log line would
    false-positive constantly.
  - a_number: `(?<![\\w])A[0-9]{8,9}(?![\\w])` -- written with explicit
    lookarounds against the `\\w` class (equivalent to `\\bA[0-9]{8,9}\\b`
    for this class; both correctly refuse to flag an id embedded in a
    longer underscore-joined identifier, e.g.
    `tracker_id_A123456789_suffix` -- the literal case behind this repo's
    own scar, "`\\bptin` never matches `agent_ptin`"). Written this way,
    rather than `\\b`, to make the boundary class explicit at the call
    site: a future edit that narrows it away from `\\w` (e.g. to
    whitespace/punctuation only, a mistaken "fix" for that same scar) is a
    visible diff on this line, and is pinned red by
    tests/test_log_pii_sweep_detectors.py::test_a_number_mutation_to_whitespace_only_boundary_goes_red.
  - ssn: `(?<!\\d)\\d{3}-\\d{2}-\\d{4}(?!\\d)`.
  - email: a conventional user@host.tld shape.
  - phone: a US-shaped `(?<!\\d)\\d{3}[-. ]?\\d{3}[-. ]?\\d{4}(?!\\d)` --
    intentionally narrow (10 digits, optional separators) rather than a
    generic international phone grammar, to keep the false-positive rate on
    order/request ids low.
  - dob_date: a DOB-shaped date (`YYYY-MM-DD`, `MM/DD/YYYY`, or
    `Month D, YYYY`) matched ONLY inside a `jsonPayload` STRING field value
    -- never `insertId`, `labels`, `timestamp` or `receiveTimestamp`, which
    are legitimately date-shaped and would drown every real hit.

NEVER PRINTS A MATCH. Every detector returns spans (start/end offsets into
the string it matched against), never the matched substring itself; the
formatter (`format_report`) is the ONE place a hit's location info is
rendered, and it renders only service/logName/detector/key/count plus
insertId + timestamp lists. `tests/test_log_pii_sweep_detectors.py` proves
this by feeding a sentinel-valued log entry through the whole pipeline and
asserting the sentinel is absent from every formatted line.

REFUSES to run under `--log-http` or a debug verbosity, or when
`CLOUDSDK_CORE_LOG_HTTP` is truthy -- any of these would have gcloud itself
echo the payloads this script exists to keep out of the transcript.

WINDOW: the Cloud Logging bucket retention is 30 days (measured, bd
polyglot-pdf-6rj0j / B0). Swept in DAILY windows, each walked to the end
with the API's own page tokens, so a busy day is never truncated and no
single request asks for a month of traffic at once.

SHAPE: operator ADC, `--project` REQUIRED (pins the query deterministically
and must match the ADC's own project), the same DEAD_PROJECTS refusal as
scripts/grant_credits.py. TRANSPORT IS IN-PROCESS ONLY: the Cloud Logging
entries.list REST endpoint via google-auth + requests, and the bigquery
client library -- this script never spawns gcloud, bq or any subprocess
(on Windows every gcloud.cmd child opens its own console window, and a
30-day sweep is ~180 of them).

EXIT CODES: 0 = ran to completion (a report can still be non-empty; read the
SUMMARY line, do not rely on exit 0 meaning "clean"); 2 = refused (missing
--project, dead project, project mismatch, --log-http/debug-verbosity
guard); 3 = a query could not complete at all (partial report; "incomplete",
not "clean").

ASCII only.
"""
from __future__ import annotations

import argparse
import configparser
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Same former-prod project this app's other operator scripts refuse (bd
# polyglot-pdf-uaxt5's inventory_stores.py; scripts/grant_credits.py;
# scripts/bootstrap_firm.py) -- restated here for the same reason: a stale
# muscle-memory invocation must not hang or half-read against a dead
# project, even though this script never writes anything.
DEAD_PROJECTS = {"polyglot-forms-919f2"}

SERVICES = ("polyglot-backend", "polyglot-backend-staging", "polyglot-admin")

# The two Cloud Run log streams this sweep covers -- the application streams
# (stdout/stderr, where structlog / print() land) AND the Cloud Run request
# log (which independently records httpRequest.requestUrl regardless of
# uvicorn's own access-log setting -- the reason PF-1 needed a live sink
# exclusion, not just the app-side --no-access-log flag).
LOG_STREAMS = (
    "run.googleapis.com/stdout",
    "run.googleapis.com/stderr",
    "run.googleapis.com/requests",
)

RETENTION_DAYS = 30

# BigQuery telemetry tables/views this project has attempted to deploy
# (sql/telemetry_views.sql) -- copied from inventory_stores.py's own
# --bq-tables default so both audit scripts agree on the set. Per bd
# polyglot-pdf-uaxt5's live run against polyglot-demo-aa709, only
# hosting_cost_by_service_month exists there today; the rest are reported
# ABSENT, not FAILED (a bq "not found" is the honest, expected answer, not a
# sweep defect).
DEFAULT_BQ_DATASET = "polyglot_telemetry"
DEFAULT_BQ_TABLES = (
    "cost_by_firm_month",
    "cost_by_kit_month",
    "cost_by_employee_month",
    "income_month",
    "hosting_cost_by_service_month",
)

# BigQuery columns are NOT allowlisted by name: the sweep reads each
# table/view's live schema and selects every STRING column it finds, named
# explicitly (never SELECT *). A name-based allowlist drifted from
# sql/telemetry_views.sql's output aliases on its first live run and scanned
# zero cells while reporting "no detector hit".
_BQ_MAX_ROWS = 100000  # rows read per table before the sweep reports TRUNCATED


class RefusedError(Exception):
    """A live-run precondition failed; the sweep must not proceed."""


# ---------------------------------------------------------------------------
# Detectors -- each returns a list of (start, end) SPANS into the searched
# string, never the matched text itself. A caller that wants the matched
# substring for its own logic (there is exactly one: link_token_in_url and
# jwt need to confirm they are inside a URL-shaped context) does that
# scoping BEFORE calling the detector, on the outer context string, not by
# reading the detector's own return value.
# ---------------------------------------------------------------------------

_WS_TOKEN_IN_URL_RE = re.compile(r"[?&]token=")
_JWT_RE = re.compile(r"\beyJ[\w-]{20,}\.eyJ")
# base64url payload (no padding, this app's own _b64u strips it) + "." +
# base64url HMAC-SHA256 (32 bytes -> 43 base64url chars, no padding). The
# EXACT 43-char final segment is what keeps this from colliding with a real
# Firebase ID token: Firebase signs RS256 (RSA-2048), a 342-char base64url
# signature, far longer than 43 -- so a genuine Firebase JWT never also
# matches this pattern. (An HS256 JWT's 32-byte HMAC signature would ALSO be
# 43 chars and WOULD collide with this pattern; this app never issues or
# verifies HS256 tokens, only Firebase's own RS256 ones, so that collision
# is not reachable here -- flagged for whoever next touches this if that
# assumption ever changes.)
_LINK_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{43}\b")
_A_NUMBER_RE = re.compile(r"(?<![\w])A[0-9]{8,9}(?![\w])")
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# NANP shape (optionally +1 / 1 and a parenthesised area code): area code and
# exchange both start with [2-9] (this is what
# keeps a bare 10-digit epoch-seconds timestamp, "17xxxxxxxx", out), the
# separators are all-or-none and identical (a UUID fragment "123456-7890"
# is not a phone), and the neighbours may be neither word chars nor "-"
# (a hex id continuing on either side is not a phone). First live sweep:
# both phone hits were exactly those two shapes.
_PHONE_RE = re.compile(
    r"(?<![\w-])(?:\+?1[-. ])?"
    r"(?:\([2-9]\d{2}\) ?[2-9]\d{2}[-. ]\d{4}"      # (555) 234-5678
    r"|[2-9]\d{2}([-. ])[2-9]\d{2}\1\d{4}"            # 555-234-5678, 555.234.5678, 555 234 5678
    r"|[2-9]\d{2}[2-9]\d{6})"                            # 5552345678
    r"(?![\w-])"
)
_DOB_DATE_RE = re.compile(
    r"\b(?:"
    r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"  # YYYY-MM-DD
    r"|(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/(?:19|20)\d{2}"  # MM/DD/YYYY
    r"|(?:January|February|March|April|May|June|July|August|September"
    r"|October|November|December)\s+\d{1,2},\s*(?:19|20)\d{2}"  # Month D, YYYY
    r")\b"
)

# URL-shaped substrings the JWT and link-token detectors are scoped to when
# the bead calls for "only inside a URL": anything that looks like it starts
# a query string or a full URL. This is intentionally permissive (it just
# needs to find candidate URL windows to re-search within, not validate a
# URL), since a false-negative here (missing a URL-scoped hit) is worse than
# a false-positive scope (re-searching a non-URL span costs nothing -- the
# detector regex itself is still the thing that must match).
_URL_SPAN_RE = re.compile(
    r"https?://\S+|[/?&][\w.-]*[?&][\w=&%.\-]+|\b[A-Za-z_]+=[\w.%-]{20,}"
)


def _spans(pattern: "re.Pattern", text: str) -> "list[tuple[int, int]]":
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


def _url_scoped_spans(pattern: "re.Pattern", text: str) -> "list[tuple[int, int]]":
    """Only spans of `pattern` that fall inside a URL-shaped window of
    `text`. Used for link_token_in_url (per the bead: "the one-dot
    link-token shape only inside a URL") -- searching the whole text
    unscoped would false-positive on any base64-ish string with an
    incidental single dot.
    """
    url_spans = [(m.start(), m.end()) for m in _URL_SPAN_RE.finditer(text)]
    if not url_spans:
        return []
    hits = []
    for m in pattern.finditer(text):
        start, end = m.start(), m.end()
        if any(start >= u0 and end <= u1 for u0, u1 in url_spans):
            hits.append((start, end))
    return hits


DETECTORS = {
    # httpRequest.requestUrl-scoped: the caller passes ONLY that field's
    # value as `text`, never the whole entry, so no extra scoping needed
    # here.
    "ws_token_in_url": lambda text: _spans(_WS_TOKEN_IN_URL_RE, text),
    "jwt": lambda text: _spans(_JWT_RE, text),
    "link_token_in_url": lambda text: _url_scoped_spans(_LINK_TOKEN_RE, text),
    "a_number": lambda text: _spans(_A_NUMBER_RE, text),
    "ssn": lambda text: _spans(_SSN_RE, text),
    "email": lambda text: _spans(_EMAIL_RE, text),
    "phone": lambda text: _spans(_PHONE_RE, text),
    "dob_date": lambda text: _spans(_DOB_DATE_RE, text),
}

# Detectors that only ever look at httpRequest.requestUrl (never jsonPayload
# string fields) -- the request-log-only detectors.
_URL_ONLY_DETECTORS = frozenset({"ws_token_in_url"})
# Detectors that run over jsonPayload string values (the application-stream
# detectors) as well as anywhere else text is searched.
_JSONPAYLOAD_DETECTORS = frozenset({
    "jwt", "link_token_in_url", "a_number", "ssn", "email", "phone", "dob_date",
})


# ---------------------------------------------------------------------------
# Refusal gates -- must fire BEFORE any gcloud/bq call.
# ---------------------------------------------------------------------------

def check_no_debug_leakage(argv: "list[str]", environ: "dict[str, str]") -> None:
    """Refuse if this invocation carries the flags or env that make Google
    tooling echo request/response payloads to a transcript -- the exact
    leak class this script exists to sweep FOR, not cause. The script
    itself never spawns gcloud, so this is defence in depth against the
    habit; case-insensitive. Raises RefusedError; callers exit 2.
    """
    if "--log-http" in argv:
        raise RefusedError(
            "refusing to run: --log-http was passed, which makes gcloud "
            "echo full request/response bodies (potentially including log "
            "payloads) to this transcript."
        )
    for i, arg in enumerate(argv):
        if arg.lower() == "--verbosity=debug":
            raise RefusedError(
                "refusing to run: --verbosity=debug was passed, which "
                "raises gcloud's own logging to a level that can echo "
                "response payloads."
            )
        if arg == "--verbosity" and i + 1 < len(argv) and argv[i + 1].lower() == "debug":
            raise RefusedError(
                "refusing to run: --verbosity debug was passed, which "
                "raises gcloud's own logging to a level that can echo "
                "response payloads."
            )
    if environ.get("CLOUDSDK_CORE_LOG_HTTP", "").strip().lower() in (
        "1", "true", "yes",
    ):
        raise RefusedError(
            "refusing to run: CLOUDSDK_CORE_LOG_HTTP is set, which makes "
            "gcloud echo full request/response bodies to this transcript."
        )


def check_not_dead_project(project: str) -> None:
    if project in DEAD_PROJECTS:
        raise RefusedError(
            "project {!r} is DEAD and unreachable (maintainer 2026-08-14); "
            "refusing.".format(project)
        )


# ---------------------------------------------------------------------------
# Transport -- IN-PROCESS only. No gcloud, no bq, no subprocess: every call
# is an HTTPS request from this interpreter under the operator's ADC. Pages
# are walked with the API's own tokens, so nothing is silently truncated.
# The google libraries are imported lazily inside these helpers so importing
# this module (the unit tests) never touches ADC.
# ---------------------------------------------------------------------------

class TransportError(Exception):
    """A query could not complete. The message is already scrubbed."""


_MAX_PAGES_PER_WINDOW = 50  # x 1000 entries per daily window per stream
_LOGGING_ENDPOINT = "https://logging.googleapis.com/v2/entries:list"
_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)
_ERROR_TEXT_LIMIT = 300
_RETRY_STATUSES = (429, 500, 502, 503, 504)
_RETRY_BACKOFF_S = (5, 15, 45)  # 3 retries; a 429 is the per-minute read quota

_session = None
_credentials = None
_bq = None


def scrub(text: "Any", limit: int = _ERROR_TEXT_LIMIT) -> str:
    """Redact every detector match inside free text and cap its length.
    Transport error messages are the ONE place raw remote text can reach
    the report (an API error can echo a filter or a row); they pass through
    here first, so even that channel cannot carry a credential, an email, an
    A-number or a date."""
    out = str(text)
    spans: "list[tuple[int, int, str]]" = []
    for name, detect in DETECTORS.items():
        for a, b in detect(out):
            spans.append((a, b, name))
    # Overlapping spans (a JWT is also the head of a link-token shape; an
    # SSN can sit inside a longer digit run) are merged into one region
    # BEFORE splicing: splicing them one by one against a string whose
    # length has already changed would leave raw characters behind.
    merged: "list[list]" = []
    for a, b, name in sorted(spans, key=lambda t: (t[0], t[1])):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2].add(name)
        else:
            merged.append([a, b, {name}])
    for a, b, names in reversed(merged):
        out = out[:a] + "<redacted:" + "+".join(sorted(names)) + ">" + out[b:]
    return out[:limit]


def _gcloud_config_dir() -> str:
    override = os.environ.get("CLOUDSDK_CONFIG")
    if override:
        return override
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA", ""), "gcloud")
    return os.path.join(os.path.expanduser("~"), ".config", "gcloud")


def _adc_file() -> str:
    explicit = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if explicit:
        return explicit
    return os.path.join(_gcloud_config_dir(), "application_default_credentials.json")


def ensure_credentials():
    """Load the operator's application-default credentials FROM THE FILE,
    through the typed constructor for the file's own kind. Never the
    google.auth default() lookup: on a machine whose ADC file carries no
    project id, that helper shells out to `gcloud config get project`
    (a console window on Windows) -- the exact thing this transport exists
    to avoid. Raises RefusedError when no ADC file exists or its kind is
    not one this script knows how to load."""
    global _credentials
    if _credentials is None:
        path = _adc_file()
        if not os.path.exists(path):
            raise RefusedError(
                "no application-default credentials at {}; run "
                "`gcloud auth application-default login` first.".format(path)
            )
        with open(path, encoding="utf-8") as f:
            info = json.load(f)
        kind = info.get("type")
        if kind == "authorized_user":
            from google.oauth2.credentials import Credentials
            _credentials = Credentials.from_authorized_user_info(info, scopes=list(_SCOPES))
        elif kind == "service_account":
            from google.oauth2 import service_account
            _credentials = service_account.Credentials.from_service_account_info(
                info, scopes=list(_SCOPES))
        else:
            raise RefusedError(
                "the credentials file at {} is of kind {!r}; only authorized_user "
                "(gcloud auth application-default login) and service_account "
                "files are loaded.".format(path, kind)
            )
    return _credentials


def _authorized_session():
    global _session
    if _session is None:
        from google.auth.transport.requests import AuthorizedSession
        _session = AuthorizedSession(ensure_credentials())
    return _session


def adc_project() -> "Optional[str]":
    """core/project of the operator's ACTIVE gcloud configuration, read
    from the config files on disk (never `gcloud config get`, which is a
    subprocess). None when no configuration names one."""
    cfg_dir = _gcloud_config_dir()
    name = "default"
    try:
        with open(os.path.join(cfg_dir, "active_config"), encoding="utf-8") as f:
            name = f.read().strip() or "default"
    except OSError:
        pass
    parser = configparser.ConfigParser()
    parser.read(os.path.join(cfg_dir, "configurations", "config_" + name), encoding="utf-8")
    return parser.get("core", "project", fallback=None) or None


def check_project_matches_adc(project: str) -> None:
    resolved = adc_project()
    if resolved and resolved != project:
        raise RefusedError(
            "--project {!r} does not match the active gcloud configuration's project "
            "({!r}); refusing rather than read a different project's logs "
            "under the wrong identity.".format(project, resolved)
        )


def _error_message(resp: "Any") -> str:
    try:
        return str((resp.json().get("error") or {}).get("message", ""))
    except Exception:  # noqa: BLE001 -- any parse failure -> no message
        return "(no error message)"


def _post_with_retry(session, body: "dict[str, Any]"):
    """One entries.list POST, retried on the retryable statuses (the
    per-minute read quota answers 429 partway through a 30-day sweep) and
    on a connection-level failure; after the retry budget either becomes a
    TransportError (scrubbed), so a window is reported INCOMPLETE rather
    than the sweep dying with a raw traceback."""
    import requests
    from google.auth import exceptions as gauth_exc

    def _post():
        try:
            return session.post(_LOGGING_ENDPOINT, json=body, timeout=120)
        except gauth_exc.GoogleAuthError as exc:
            # A token refresh failure (revoked / expired ADC) is not transient:
            # no retry, and the token endpoint's text is scrubbed like any other.
            raise TransportError(scrub("{}: {}".format(type(exc).__name__, exc)))
        except requests.RequestException as exc:
            # A connection reset / timeout carries the URL (and could carry
            # a filter) in its text: scrubbed, and never a bare traceback.
            return TransportError(scrub("{}: {}".format(type(exc).__name__, exc)))

    resp = _post()
    for delay in _RETRY_BACKOFF_S:
        if not isinstance(resp, TransportError) and resp.status_code not in _RETRY_STATUSES:
            break
        time.sleep(delay)
        resp = _post()
    if isinstance(resp, TransportError):
        raise resp
    return resp


def _fetch_entries(project: str, log_filter: str, *, page_size: int = 1000) -> "list[dict]":
    """Every entry matching the filter, walking nextPageToken to the end.
    Raises TransportError (already scrubbed) on an HTTP error or when a
    single window exceeds _MAX_PAGES_PER_WINDOW pages."""
    session = _authorized_session()
    entries: "list[dict]" = []
    token: "Optional[str]" = None
    for _ in range(_MAX_PAGES_PER_WINDOW):
        body: "dict[str, Any]" = {
            "resourceNames": ["projects/" + project],
            "filter": log_filter,
            "pageSize": page_size,
            "orderBy": "timestamp desc",
        }
        if token:
            body["pageToken"] = token
        resp = _post_with_retry(session, body)
        if resp.status_code != 200:
            raise TransportError(
                "entries.list HTTP {}: {}".format(resp.status_code, scrub(_error_message(resp)))
            )
        payload = resp.json()
        entries.extend(payload.get("entries", []))
        token = payload.get("nextPageToken")
        if not token:
            return entries
    raise TransportError(
        "entries.list exceeded {} pages for one daily window; narrow the window".format(
            _MAX_PAGES_PER_WINDOW)
    )


def _bq_client(project: str):
    global _bq
    if _bq is None:
        from google.cloud import bigquery
        _bq = bigquery.Client(project=project, credentials=ensure_credentials())
    return _bq


def _bq_table_schema(project: str, dataset: str, table: str) -> "Optional[list[tuple[str, str]]]":
    """[(column, type)] for a table/view, None when it does not exist;
    TransportError (scrubbed) for anything else."""
    from google.api_core import exceptions as gexc
    try:
        t = _bq_client(project).get_table("{}.{}.{}".format(project, dataset, table))
    except gexc.NotFound:
        return None
    except Exception as exc:  # noqa: BLE001 -- surfaced as UNREACHABLE, scrubbed
        raise TransportError(scrub("{}: {}".format(type(exc).__name__, exc)))
    return [(f.name, f.field_type) for f in t.schema]


def _bq_query_rows(project: str, sql: str) -> "list[dict]":
    """Every row of the query (the client pages transparently), up to
    _BQ_MAX_ROWS + 1 so the caller can tell a full read from a truncated one."""
    rows: "list[dict]" = []
    try:
        for r in _bq_client(project).query(sql).result():
            rows.append(dict(r))
            if len(rows) > _BQ_MAX_ROWS:
                break
    except Exception as exc:  # noqa: BLE001 -- surfaced as UNREACHABLE, scrubbed
        raise TransportError(scrub("{}: {}".format(type(exc).__name__, exc)))
    return rows


# ---------------------------------------------------------------------------
# Cloud Logging read, paged by day to stay under quota over a 30-day window.
# ---------------------------------------------------------------------------

@dataclass
class Hit:
    service: str
    log_name: str
    detector: str
    json_key: "Optional[str]"  # None for httpRequest-scoped detectors
    insert_id: str
    timestamp: str


@dataclass
class SweepResult:
    hits: "list[Hit]" = field(default_factory=list)
    counts: "dict[tuple, int]" = field(default_factory=dict)  # keyed (service, log_name, detector, json_key)
    incomplete: bool = False
    errors: "list[str]" = field(default_factory=list)


def _short_log_name(log_name: str) -> str:
    """projects/<p>/logs/run.googleapis.com%2Fstdout -> run.googleapis.com/stdout."""
    tail = log_name.rsplit("/logs/", 1)[-1]
    return tail.replace("%2F", "/").replace("%2f", "/")


def _day_windows(start: datetime, end: datetime) -> "Iterable[tuple[datetime, datetime]]":
    """Yield [day_start, day_end) pairs covering [start, end), so a 30-day
    sweep issues ~30 bounded entries.list queries (each walked to its end
    with page tokens) instead of one unbounded one."""
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=1), end)
        yield cur, nxt
        cur = nxt


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _entry_json_string_fields(entry: dict) -> "dict[str, str]":
    """Flatten jsonPayload's STRING leaves into {dotted.key: value}. The
    entry's own insertId/labels/timestamp/receiveTimestamp live at the top
    level and are never walked; the app's structured logger DOES put ISO
    timestamps inside jsonPayload (`timestamp`, `message.timestamp`), and
    those are walked -- dob_date stays quiet on them only because its
    trailing boundary fails between the day and the `T` of an ISO
    timestamp, which the detector tests pin."""
    out: "dict[str, str]" = {}

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk("{}.{}".format(prefix, k) if prefix else k, v)
        elif isinstance(node, (list, tuple)):
            # A list of strings is a real leak shape (a `fields=list(...)`
            # kwarg carrying the client's answers instead of its keys), so
            # every element is a leaf too, keyed as parent[i].
            for i, v in enumerate(node):
                walk("{}[{}]".format(prefix, i), v)
        elif isinstance(node, str):
            out[prefix] = node
        # numbers/bools/None: not string leaves, skip.

    walk("", entry.get("jsonPayload") or {})
    return out


def sweep_service_stream(
    project: str, service: str, log_stream: str,
    window_start: datetime, window_end: datetime,
) -> "tuple[list[Hit], bool, Optional[str]]":
    """Read one (service, log_stream) pair over [window_start, window_end),
    paged by day, and return (hits, incomplete, error).

    Returns hits with NO matched text anywhere on them -- only
    service/log_name/detector/key/insertId/timestamp, per Hit's own fields.
    """
    hits: "list[Hit]" = []
    incomplete = False
    last_error: "Optional[str]" = None

    for day_start, day_end in _day_windows(window_start, window_end):
        log_filter = (
            'resource.type="cloud_run_revision" '
            'AND resource.labels.service_name="{service}" '
            'AND logName="projects/{project}/logs/{stream}" '
            'AND timestamp>="{start}" AND timestamp<"{end}"'
        ).format(
            service=service, project=project,
            stream=log_stream.replace("/", "%2F"),
            start=_iso(day_start), end=_iso(day_end),
        )
        try:
            entries = _fetch_entries(project, log_filter)
        except TransportError as exc:
            incomplete = True
            last_error = str(exc)
            continue

        is_requests = log_stream.endswith("/requests")
        for entry in entries:
            insert_id = str(entry.get("insertId", ""))
            timestamp = str(entry.get("timestamp", ""))
            log_name = _short_log_name(str(entry.get("logName", log_stream)))

            if is_requests:
                request_url = str(
                    (entry.get("httpRequest") or {}).get("requestUrl", "")
                )
                for name in _URL_ONLY_DETECTORS:
                    for _ in DETECTORS[name](request_url):
                        hits.append(Hit(service, log_name, name, None,
                                         insert_id, timestamp))
                # The request log's URL is also worth the general text
                # detectors (a JWT or link token can ride the URL too, and
                # PF-1's whole premise is that a credential rides this
                # field) -- scoped detectors search it directly since the
                # whole string already IS a URL.
                for name in ("jwt",):
                    for _ in DETECTORS[name](request_url):
                        hits.append(Hit(service, log_name, name, None,
                                         insert_id, timestamp))
                for _ in _url_scoped_spans(_LINK_TOKEN_RE, request_url):
                    hits.append(Hit(service, log_name, "link_token_in_url",
                                     None, insert_id, timestamp))
                # The identity detectors also run over the URL (a query
                # string can carry an A-number or an email). dob_date is the
                # one jsonPayload-class detector deliberately NOT run here:
                # a date-shaped path segment is routine and not a leak.
                for name in ("a_number", "ssn", "email", "phone"):
                    for _ in DETECTORS[name](request_url):
                        hits.append(Hit(service, log_name, name, None,
                                         insert_id, timestamp))
            else:
                fields = _entry_json_string_fields(entry)
                for key, text in fields.items():
                    for name in _JSONPAYLOAD_DETECTORS:
                        for _ in DETECTORS[name](text):
                            hits.append(Hit(service, log_name, name, key,
                                             insert_id, timestamp))

    return hits, incomplete, last_error


def run_cloud_logging_sweep(
    project: str, *, retention_days: int = RETENTION_DAYS,
    now: "Optional[datetime]" = None,
) -> SweepResult:
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(days=retention_days)
    result = SweepResult()

    for service in SERVICES:
        for log_stream in LOG_STREAMS:
            hits, incomplete, error = sweep_service_stream(
                project, service, log_stream, window_start, now)
            result.hits.extend(hits)
            if incomplete:
                result.incomplete = True
                result.errors.append(
                    "{}/{}: {}".format(service, log_stream, error))

    for hit in result.hits:
        key = (hit.service, hit.log_name, hit.detector, hit.json_key)
        result.counts[key] = result.counts.get(key, 0) + 1

    return result


# ---------------------------------------------------------------------------
# BigQuery telemetry sweep -- same detectors, over STRING columns only.
# ---------------------------------------------------------------------------

@dataclass
class BQTableResult:
    reachable: bool
    absent: bool = False
    error: "Optional[str]" = None
    row_hits: "dict[tuple, int]" = field(default_factory=dict)  # (column, detector) -> count
    string_cols: "list[str]" = field(default_factory=list)  # what was actually swept
    rows_seen: int = 0
    truncated: bool = False  # more than _BQ_MAX_ROWS rows: NOT a complete read


def sweep_bigquery_table(project: str, dataset: str, table: str) -> BQTableResult:
    """SELECT every STRING column the live schema reports, named explicitly
    (never `SELECT *`, so a numeric/cost column can never reach a text
    detector), from one telemetry table/view and run every jsonPayload-class
    detector over each string cell. A table/view that does not exist in this
    project is ABSENT (a clean result), not UNREACHABLE: per bd
    polyglot-pdf-uaxt5's live finding only hosting_cost_by_service_month
    exists on polyglot-demo-aa709 today. The result records which columns
    were swept and how many rows, so "no detector hit" can never be confused
    with "nothing was read".
    """
    try:
        schema = _bq_table_schema(project, dataset, table)
    except TransportError as exc:
        return BQTableResult(reachable=False, error=str(exc))
    if schema is None:
        return BQTableResult(reachable=False, absent=True, error="not found")

    string_cols = [name for name, ftype in schema if ftype == "STRING"]
    if not string_cols:
        # A real, reachable table/view with nothing string-shaped to sweep
        # (all-numeric): reachable, nothing read -- reported as such, not as
        # a clean scan.
        return BQTableResult(reachable=True)

    select_list = ", ".join("`{}`".format(c) for c in string_cols)
    query = "SELECT {} FROM `{}.{}.{}`".format(select_list, project, dataset, table)
    try:
        rows = _bq_query_rows(project, query)
    except TransportError as exc:
        return BQTableResult(reachable=False, error=str(exc), string_cols=string_cols)
    truncated = len(rows) > _BQ_MAX_ROWS
    rows = rows[:_BQ_MAX_ROWS]

    row_hits: "dict[tuple, int]" = {}
    for row in rows:
        for col in string_cols:
            value = row.get(col)
            if not isinstance(value, str) or not value:
                continue
            for name in _JSONPAYLOAD_DETECTORS:
                n = len(DETECTORS[name](value))
                if n:
                    key = (col, name)
                    row_hits[key] = row_hits.get(key, 0) + n

    return BQTableResult(reachable=True, row_hits=row_hits, string_cols=string_cols,
                         rows_seen=len(rows), truncated=truncated)


def run_bigquery_sweep(
    project: str, dataset: str, tables: "Iterable[str]",
) -> "dict[str, BQTableResult]":
    return {table: sweep_bigquery_table(project, dataset, table) for table in tables}


# ---------------------------------------------------------------------------
# Formatting -- the ONE choke point that renders a Hit. Never given the
# matched substring (Hit/BQTableResult never carry one), and every free-text
# error string passes through scrub() -- the properties the unit tests pin.
# ---------------------------------------------------------------------------

def format_report(
    project: str,
    log_result: SweepResult,
    bq_results: "dict[str, BQTableResult]",
) -> str:
    lines = ["=== log PII sweep: project {} ===".format(project)]

    if not log_result.counts:
        lines.append("  Cloud Logging: no detector hit in the swept window.")
    else:
        for (service, log_name, detector, json_key), count in sorted(
            log_result.counts.items(), key=lambda kv: kv[0]
        ):
            key_label = json_key if json_key is not None else "(httpRequest.requestUrl)"
            lines.append(
                "  [{}] {} detector={} key={} count={}".format(
                    service, log_name, detector, key_label, count)
            )
            matching = [
                h for h in log_result.hits
                if (h.service, h.log_name, h.detector, h.json_key)
                == (service, log_name, detector, json_key)
            ]
            insert_ids = [h.insert_id for h in matching]
            timestamps = [h.timestamp for h in matching]
            lines.append("      insertIds: {}".format(insert_ids))
            lines.append("      timestamps: {}".format(timestamps))

    if log_result.incomplete:
        lines.append("  INCOMPLETE (some queries failed): {}".format(
            [scrub(e) for e in log_result.errors]))

    lines.append("--- BigQuery ---")
    for table, res in bq_results.items():
        if res.absent:
            lines.append("  [{}] ABSENT (not deployed to this project)".format(table))
        elif not res.reachable:
            lines.append("  [{}] UNREACHABLE: {}".format(table, scrub(res.error)))
        elif res.row_hits:
            for (col, detector), count in sorted(res.row_hits.items()):
                lines.append(
                    "  [{}] column={} detector={} count={}".format(
                        table, col, detector, count)
                )
        elif not res.string_cols:
            lines.append("  [{}] NO SWEEPABLE STRING COLUMNS (nothing read)".format(table))
        else:
            lines.append("  [{}] no detector hit (rows={} columns={})".format(
                table, res.rows_seen, ",".join(res.string_cols)))
        if res.truncated:
            lines.append("  [{}] TRUNCATED after {} rows -- NOT a complete read".format(
                table, res.rows_seen))

    any_hits = bool(log_result.counts) or any(
        r.row_hits for r in bq_results.values()
    )
    lines.append(
        "=== SUMMARY: {} ===".format(
            "HITS FOUND -- see counts above, disposition each against the "
            "service's fix timestamp" if any_hits
            else "zero hits across all services/streams/tables"
        )
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only, redacted live PII sweep of Cloud Logging "
        "(polyglot-backend, polyglot-backend-staging, polyglot-admin -- "
        "application streams + the Cloud Run request log) and the "
        "BigQuery telemetry tables. Never prints a matched value."
    )
    parser.add_argument(
        "--project", required=True,
        help="target GCP/Firebase project (e.g. polyglot-demo-aa709)",
    )
    parser.add_argument(
        "--retention-days", type=int, default=RETENTION_DAYS,
        help="sweep window in days back from now (default {}, the measured "
        "Cloud Logging bucket retention)".format(RETENTION_DAYS),
    )
    parser.add_argument(
        "--bq-dataset", default=DEFAULT_BQ_DATASET,
        help="BigQuery dataset holding the telemetry tables",
    )
    parser.add_argument(
        "--bq-tables", nargs="+", default=list(DEFAULT_BQ_TABLES),
        help="BigQuery telemetry table/view names to sweep",
    )
    parser.add_argument(
        "--skip-bigquery", action="store_true",
        help="skip the BigQuery sweep (Cloud Logging only)",
    )
    return parser


def main(argv: "Optional[list]" = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    try:
        check_no_debug_leakage(argv, os.environ)
    except RefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    args = _build_parser().parse_args(argv)

    try:
        check_not_dead_project(args.project)
    except RefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.retention_days < 1:
        print("--retention-days must be at least 1 (an empty window would"
              " report a false 'zero hits')", file=sys.stderr)
        return 2

    try:
        check_project_matches_adc(args.project)
        ensure_credentials()
    except RefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    log_result = run_cloud_logging_sweep(args.project, retention_days=args.retention_days)

    bq_results: "dict[str, BQTableResult]" = {}
    if not args.skip_bigquery:
        bq_results = run_bigquery_sweep(args.project, args.bq_dataset, args.bq_tables)

    print(format_report(args.project, log_result, bq_results))

    incomplete = log_result.incomplete or any(
        ((not r.reachable) and (not r.absent)) or r.truncated for r in bq_results.values()
    )
    if incomplete:
        print(
            "=== INCOMPLETE: at least one query could not complete -- this "
            "is NOT a clean report ===", file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
