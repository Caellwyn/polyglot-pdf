"""Parameterised BigQuery reads over the E3.6 telemetry views (bd
polyglot-pdf-mpebj, E3.11a): cost_by_firm_month, cost_by_kit_month,
cost_by_employee_month, and income_month (sql/telemetry_views.sql, bd
polyglot-pdf-rd3s8).

WHY A SEPARATE SERVICE MODULE, NOT INLINE IN report_routes.py. The
google-cloud-bigquery client and its query-parameter API are a genuinely
different SDK surface from every other admin-service dependency (Firestore,
firebase_admin.auth, google.auth's OIDC verifier) -- isolating the client
construction and query execution here means report_routes.py's own tests
can monkeypatch ONE seam (this module's `run_query`) rather than reaching
into the BigQuery client library, mirroring admin_auth.py's own
_verify_google_id_token isolation for the same reason.

EVERY QUERY IS PARAMETERISED (exit criterion 2). No caller-supplied string
(`from`, `to`, `group_by`, `channel`) is ever interpolated into SQL text --
each becomes a `bigquery.ScalarQueryParameter` bound by `@name` placeholder,
which is what makes a malicious or malformed month string inert rather than
a SQL-injection vector. `group_by` selects WHICH VIEW to query (a Python
dict lookup against a closed allowlist, never a value substituted into the
FROM clause), so there is no string-formatting path from `group_by` to SQL
at all -- the strongest form of this guarantee, since a parameterised
IDENTIFIER is not something BigQuery's client API supports in the first
place (query parameters bind VALUES, not table/view names).

RANGE INTEGRITY (a from/to relationship, not a place-into-a-`?`
substitution) IS APPLIED BEFORE THIS MODULE IS EVEN CALLED --
report_routes.py's own _validated_range refuses `to < from` or a span past
12 months with a 422, so this module can assume a sane, already-ordered
range and never needs to defend against one itself.

DISPATCHED WITH asyncio.to_thread, matching every other admin-service call
into a synchronous SDK (google-cloud-bigquery's Client.query().result() is
synchronous, blocking on the query job).

THE CLIENT IS BUILT LAZILY, PER CALL, not once at import time -- consistent
with every other Firestore/Auth client in this package (module import must
not require credentials to be resolvable), and cheap: google-cloud-bigquery
's Client() constructor does not itself make a network call.

`DATASET` names the SAME dataset scripts/setup-telemetry.sh provisions
(polyglot_telemetry, us-central1) -- restated here as a literal for the
same reason every other admin route module restates its own small
constants rather than importing a script's shell variable.

ASCII only.
"""
from __future__ import annotations

from typing import Any, Optional

import structlog

_log = structlog.get_logger(module="bigquery_reports")

# The dataset scripts/setup-telemetry.sh creates (bd polyglot-pdf-rd3s8).
# us-central1, per that script and this bead's own "no new grant" note --
# admin-backend-sa already holds bigquery.jobUser (project) and
# bigquery.dataViewer (this dataset only).
DATASET = "polyglot_telemetry"

# The three cost views, keyed by the bead's own `group_by` vocabulary
# (firm|kit|employee) -- a closed dict lookup, never a value that reaches
# SQL text (see module docstring). Each view's own grouping column name is
# recorded alongside it so the caller can select it without a second
# per-view branch.
COST_VIEWS = {
    "firm": ("cost_by_firm_month", "firm_id"),
    "kit": ("cost_by_kit_month", "kit_id"),
    "employee": ("cost_by_employee_month", "employee_id"),
}

INCOME_VIEW = "income_month"


class BigQueryUnavailable(Exception):
    """The BigQuery client could not be constructed, or the query itself
    failed (a network error, a missing dataset/view, an auth failure).

    Raised rather than left to propagate the SDK's own exception types
    directly: report_routes.py maps this to one 503, keeping the SDK's
    exception hierarchy out of the route layer the same way admin_auth.py's
    OidcVerificationUnavailable keeps google.auth's hierarchy out of that
    gate.
    """


def _client():
    """A google.cloud.bigquery.Client, or raise BigQueryUnavailable.

    Lazy-imported, matching every other admin-service SDK client in this
    package (module import must not require the library or ambient
    credentials to be resolvable) -- and the ONE seam a test replaces
    (monkeypatching this module's `_client` function) so report_routes.py's
    tests never need a real BigQuery project.
    """
    try:
        from google.cloud import bigquery
    except ImportError as exc:  # pragma: no cover -- pinned dependency
        raise BigQueryUnavailable(
            "google-cloud-bigquery is not importable: {}".format(exc)
        ) from exc
    try:
        return bigquery.Client()
    except Exception as exc:  # noqa: BLE001
        raise BigQueryUnavailable(
            "could not construct a BigQuery client: {}".format(exc)
        ) from exc


def _run_query(sql: str, parameters: list) -> list[dict[str, Any]]:
    """Execute one parameterised query and return its rows as plain dicts.

    THE ONE SEAM a test monkeypatches (report_routes.py's tests patch
    `bigquery_reports._run_query` directly, never the SDK client) -- kept
    separate from `_client()` so a test can also exercise "the client
    itself could not be built" (BigQueryUnavailable from _client) apart
    from "the client built fine but the query failed" (BigQueryUnavailable
    from here), matching admin_auth.py's own two-seam split for OIDC
    verification.
    """
    from google.cloud import bigquery

    client = _client()
    job_config = bigquery.QueryJobConfig(query_parameters=parameters)
    try:
        result = client.query(sql, job_config=job_config).result()
    except Exception as exc:  # noqa: BLE001
        raise BigQueryUnavailable(
            "BigQuery query failed: {}".format(exc)) from exc
    return [dict(row.items()) for row in result]


def _str_param(name: str, value: str):
    from google.cloud import bigquery

    return bigquery.ScalarQueryParameter(name, "STRING", value)


def query_cost_report(
    *, group_by: str, from_month: str, to_month: str,
    channel: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Rows from cost_by_{group_by}_month, filtered to [from_month, to_month]
    inclusive (both are "YYYY-MM" strings, matching the view's own `month`
    column shape) and, optionally, one channel.

    `group_by` MUST already be a key of COST_VIEWS -- report_routes.py's own
    422 for an unrecognized value runs before this is ever called; this
    function KeyErrors on anything else rather than silently defaulting,
    since a silent default here would query the wrong view for a caller who
    made a typo report_routes.py's own check should have caught.
    """
    view, group_col = COST_VIEWS[group_by]
    where = ["month >= @from_month", "month <= @to_month"]
    parameters = [
        _str_param("from_month", from_month),
        _str_param("to_month", to_month),
    ]
    if channel is not None:
        where.append("channel = @channel")
        parameters.append(_str_param("channel", channel))

    sql = (
        "SELECT month, {group_col}, channel, usage_kind, call_count, "
        "cost_usd FROM `{dataset}.{view}` WHERE {where} "
        "ORDER BY month, {group_col}".format(
            group_col=group_col, dataset=DATASET, view=view,
            where=" AND ".join(where),
        )
    )
    return _run_query(sql, parameters)


def query_income_report(
    *, from_month: str, to_month: str,
) -> list[dict[str, Any]]:
    """Rows from income_month, filtered to [from_month, to_month] inclusive.
    income_month's own view definition already hard-codes firm_kind = 'live'
    (contract 25) -- this function adds no second filter for that; a caller
    cannot widen it back to mock firms by any parameter this function
    accepts.

    NO channel PARAMETER, ON PURPOSE (bd polyglot-pdf-mpebj cross-surface
    review). income_month rows carry a `channel` column, but every value in
    it is NULL: sql/telemetry_views.sql documents that the admin service
    writing purchase/subscription_grant ledger entries has no channel of
    its own. A `channel = @channel` filter can therefore never match a
    single row -- report_routes.py's income route refuses `?channel=`
    outright (422) rather than accept a parameter that can only ever
    silently return zero rows, so this function never receives one. A
    parameter nothing can safely turn on is a trap for the next caller;
    removed rather than defaulted off (CLAUDE.md scar #7).
    """
    where = ["month >= @from_month", "month <= @to_month"]
    parameters = [
        _str_param("from_month", from_month),
        _str_param("to_month", to_month),
    ]

    sql = (
        "SELECT month, entry_type, channel, entry_count, usd_amount "
        "FROM `{dataset}.{view}` WHERE {where} "
        "ORDER BY month, entry_type".format(
            dataset=DATASET, view=INCOME_VIEW, where=" AND ".join(where),
        )
    )
    return _run_query(sql, parameters)
