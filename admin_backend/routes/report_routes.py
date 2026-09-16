"""GET /admin/reports/cost and GET /admin/reports/income -- parameterised
BigQuery reads over the E3.6 telemetry views (bd polyglot-pdf-mpebj,
E3.11a; views: bd polyglot-pdf-rd3s8, sql/telemetry_views.sql).

BOTH ROUTES BEHIND require_app_admin ONLY -- cost/income reporting spans
every firm at once (that is the whole point of a BigQuery rollup), so there
is no firm-manager-scoped reading of it the way usage_routes.py's firm
route has one.

`?from=YYYY-MM&to=YYYY-MM` ARE BOTH REQUIRED ON BOTH ROUTES, validated
against the same strict month shape usage_routes.py uses, with `to` REFUSED
(422) when it precedes `from` OR when the inclusive span exceeds 12 MONTHS
(exit criterion 2: "refuse a range wider than 12 months") -- an unbounded
range would let one console click submit a query BigQuery might legitimately
take a long time (and real dollars) to run, over a dataset this bead adds no
caching in front of. The 12-month ceiling is INCLUSIVE of both endpoints
(from=2026-01, to=2026-12 is exactly 12 months and is allowed; to=2027-01
is 13 and is refused).

`group_by=firm|kit|employee` ON THE COST ROUTE selects which of the three
E3.6 cost views to query -- validated against
bigquery_reports.COST_VIEWS's own key set (422 on anything else) BEFORE
bigquery_reports.query_cost_report is ever called, so an unrecognized value
never reaches that function's own KeyError.

EVERY QUERY IS PARAMETERISED (exit criterion 2's other half): this route
passes `from`/`to`/`channel` to bigquery_reports.py as plain Python values,
which THAT module turns into `bigquery.ScalarQueryParameter` bindings --
this route module itself builds no SQL string at all. See
bigquery_reports.py's own module docstring for the full argument.

`delayed: true` PLUS A NOTE ON EVERY RESPONSE (bead requirement): the
Cloud Logging -> BigQuery sink this data comes through lags live traffic
by seconds to minutes (contract 25's own wording), so a console screen
showing "today" numbers from this route must visibly say the data is not
real-time -- silently presenting a delayed read as live would let an
operator draw a wrong conclusion from a gap that is not a bug.

DISPATCHED WITH asyncio.to_thread (bigquery_reports.py's own query
execution is synchronous, matching the SDK).

BigQueryUnavailable (bigquery_reports.py: the client could not be built, or
the query itself failed) maps to a 503 here -- the same "could not verify"
polarity admin_auth.py's OidcVerificationUnavailable uses, since a BigQuery
outage or a misconfigured dataset is a retryable operational condition, not
the caller's fault.

A READ, SO NEITHER ROUTE AUDITS -- matching every other read route in this
service.

ASCII only.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from admin_backend.services import bigquery_reports
from admin_backend.services.admin_auth import AdminActor, require_app_admin

_log = structlog.get_logger().bind(module="admin_report_routes")

router = APIRouter()

# The two channels that actually exist -- restated here rather than
# imported, matching every other admin route module's own copy.
KNOWN_CHANNELS = ("demo", "staging")

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# The sink-lag note every response carries alongside `delayed: true` (bead
# requirement) -- a constant string so the console and any future route
# reading this note agree on wording rather than each writing their own.
DELAYED_NOTE = (
    "Cost and income figures come from a Cloud Logging -> BigQuery sink "
    "that lags live traffic by seconds to minutes; this is not a real-time "
    "view."
)

# Inclusive month-span ceiling (exit criterion 2).
_MAX_RANGE_MONTHS = 12


def _parse_month(value: str) -> date:
    """The first day of the month, for range-length arithmetic -- never
    exposed in a response, only used to compute a month DELTA below."""
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def _month_delta(from_month: str, to_month: str) -> int:
    """The inclusive span in months between two "YYYY-MM" strings (0 when
    equal, e.g. 2026-01 -> 2026-01)."""
    a = _parse_month(from_month)
    b = _parse_month(to_month)
    return (b.year - a.year) * 12 + (b.month - a.month)


def _validated_range(from_month: Optional[str],
                      to_month: Optional[str]) -> tuple[str, str]:
    """A validated (from, to) pair, or the 422 the bead requires.

    Checks, in order: both present and each individually a strict YYYY-MM
    (never coerced); `to` not before `from`; the inclusive span at most
    _MAX_RANGE_MONTHS (12) -- from=2026-01/to=2026-12 is a 11-month DELTA,
    i.e. 12 calendar months inclusive, and is allowed; from=2026-01/
    to=2027-01 is a 12-month delta (13 calendar months) and is refused.
    """
    for label, value in (("from", from_month), ("to", to_month)):
        if not value or not _MONTH_RE.fullmatch(value):
            raise HTTPException(
                status_code=422,
                detail="{} is required and must be YYYY-MM, got {!r}".format(
                    label, value),
            )
    delta = _month_delta(from_month, to_month)
    if delta < 0:
        raise HTTPException(
            status_code=422,
            detail="to ({}) must not be before from ({})".format(
                to_month, from_month),
        )
    if delta > _MAX_RANGE_MONTHS - 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "the range from {} to {} spans more than {} months; "
                "narrow it and query again".format(
                    from_month, to_month, _MAX_RANGE_MONTHS)),
        )
    return from_month, to_month


def _validated_channel(channel: Optional[str]) -> Optional[str]:
    """An OPTIONAL channel filter -- unlike usage_routes.py's REQUIRED
    channel, a report route with no ?channel= legitimately means "both
    channels combined" (the views themselves carry a `channel` column per
    row, so an unfiltered query still tells the two apart in the response
    rows -- there is no cross-channel MERGING that would hide one).

    THIS REASONING HOLDS ONLY FOR THE COST VIEWS. income_month's `channel`
    column is different in kind, not just in value: sql/telemetry_views.sql
    documents that the admin service writing purchase/subscription_grant
    ledger entries has no channel of its own, so every row income_month can
    ever produce carries `channel IS NULL`. A `channel = @channel` filter
    against a non-null value can therefore never match a single row --
    silently returning "0 income" for the one route whose job is reporting
    real money, rather than an error explaining why. See
    _validated_income_channel below, which the income route uses instead."""
    if channel is None:
        return None
    if channel not in KNOWN_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail="channel must be one of {}".format(
                ", ".join(KNOWN_CHANNELS)),
        )
    return channel


def _validated_income_channel(channel: Optional[str]) -> None:
    """income_month rows never carry a non-null `channel` (see
    _validated_channel's docstring and sql/telemetry_views.sql) -- so
    `?channel=` on the income route can only ever produce a confidently
    empty result set, never a real answer. Refuse it outright (422) rather
    than silently returning zero rows for a filter that can never match.
    """
    if channel is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "channel is not supported on the income report: income "
                "ledger entries carry no channel (the admin service that "
                "writes them has none), so a channel filter would always "
                "return zero rows"
            ),
        )
    return None


def _validated_group_by(group_by: Optional[str]) -> str:
    if not group_by or group_by not in bigquery_reports.COST_VIEWS:
        raise HTTPException(
            status_code=422,
            detail="group_by is required and must be one of {}".format(
                ", ".join(sorted(bigquery_reports.COST_VIEWS))),
        )
    return group_by


@router.get("/admin/reports/cost")
async def get_cost_report(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    from_: Annotated[Optional[str], Query(alias="from")] = None,
    to: Annotated[Optional[str], Query()] = None,
    group_by: Annotated[Optional[str], Query()] = None,
    channel: Annotated[Optional[str], Query()] = None,
) -> dict:
    """Cost rows from cost_by_{group_by}_month, filtered to [from, to] and
    an optional channel. `from`/`to`/`group_by` are all REQUIRED (422 if
    missing, malformed, or the range exceeds 12 months). Every value reaches
    BigQuery as a bound query parameter, never interpolated SQL text (see
    bigquery_reports.py). Carries `delayed: true` and DELAYED_NOTE (bead
    requirement -- the sink lags live traffic).
    """
    from_month, to_month = _validated_range(from_, to)
    group_by = _validated_group_by(group_by)
    channel = _validated_channel(channel)

    try:
        rows = await asyncio.to_thread(
            bigquery_reports.query_cost_report,
            group_by=group_by, from_month=from_month, to_month=to_month,
            channel=channel,
        )
    except bigquery_reports.BigQueryUnavailable as exc:
        _log.error("admin_cost_report_failed", group_by=group_by,
                   from_month=from_month, to_month=to_month, error_type=type(exc).__name__)
        raise HTTPException(status_code=503,
                            detail="cost report unavailable") from exc

    return {
        "group_by": group_by, "from": from_month, "to": to_month,
        "channel": channel, "rows": rows,
        "delayed": True, "note": DELAYED_NOTE,
    }


@router.get("/admin/reports/income")
async def get_income_report(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    from_: Annotated[Optional[str], Query(alias="from")] = None,
    to: Annotated[Optional[str], Query()] = None,
    channel: Annotated[Optional[str], Query()] = None,
) -> dict:
    """Income rows from income_month (real firms only -- the view's own
    firm_kind = 'live' filter, contract 25), filtered to [from, to].
    `from`/`to` are both REQUIRED. `?channel=` is REFUSED (422) rather than
    silently accepted: income_month rows carry no channel (see
    _validated_income_channel), so filtering on one can only ever return
    zero rows. Carries `delayed: true` and DELAYED_NOTE, same as the cost
    report.
    """
    from_month, to_month = _validated_range(from_, to)
    _validated_income_channel(channel)

    try:
        rows = await asyncio.to_thread(
            bigquery_reports.query_income_report,
            from_month=from_month, to_month=to_month,
        )
    except bigquery_reports.BigQueryUnavailable as exc:
        _log.error("admin_income_report_failed", from_month=from_month,
                   to_month=to_month, error_type=type(exc).__name__)
        raise HTTPException(status_code=503,
                            detail="income report unavailable") from exc

    return {
        "from": from_month, "to": to_month,
        "rows": rows, "delayed": True, "note": DELAYED_NOTE,
    }
