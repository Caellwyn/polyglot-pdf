"""GET /admin/reports/cost, GET /admin/reports/income (bd polyglot-pdf-mpebj,
E3.11a).

Pins: the required from/to/group_by validation, the 12-month range ceiling
(exit criterion 2), that every value reaches bigquery_reports.py as a
QUERY PARAMETER rather than interpolated SQL text (asserted by inspecting
the parameters bigquery_reports._run_query actually receives, mirroring the
bead's own "the test asserts query parameters are used" wording), the
`delayed: true` + note on every response, and a BigQueryUnavailable ->
503 mapping.

bigquery_reports.py's own `_run_query` is the ONE seam this file
monkeypatches -- no real BigQuery client or credentials are ever touched.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import report_routes
from admin_backend.services import bigquery_reports
from admin_backend.services.admin_auth import AdminActor, require_app_admin


@pytest.fixture
def client():
    actor = AdminActor(uid="admin-1", email="ops@example.com")
    app.dependency_overrides[require_app_admin] = lambda: actor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def captured_queries(monkeypatch):
    """Replaces bigquery_reports._run_query with a recorder that returns a
    canned row set and captures (sql, parameters) for every call -- so a
    test can assert what actually reached the "BigQuery boundary" without a
    real client."""
    calls = []

    def _fake_run_query(sql, parameters):
        calls.append({"sql": sql, "parameters": list(parameters)})
        return [{"month": "2026-09", "cost_usd": 1.5}]

    monkeypatch.setattr(bigquery_reports, "_run_query", _fake_run_query)
    return calls


# --------------------------------------------------------------------------
# Range validation (exit criterion 2, part 1).
# --------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "to=2026-09&group_by=firm",  # missing from
    "from=2026-01&group_by=firm",  # missing to
    "from=2026-01&to=2026-9&group_by=firm",  # unpadded to
    "from=2026-05&to=2026-01&group_by=firm",  # to before from
    "from=2026-01&to=2026-09&group_by=nonsense",  # bad group_by
], ids=["no-from", "no-to", "unpadded-to", "to-before-from",
        "bad-group-by"])
def test_cost_report_refuses_missing_or_malformed_params(
        client, captured_queries, query):
    resp = client.get("/admin/reports/cost?{}".format(query))
    assert resp.status_code == 422, resp.text
    assert captured_queries == [], (
        "a refused request must never reach BigQuery at all")


def test_cost_report_refuses_a_range_wider_than_12_months(
        client, captured_queries):
    """Mutation: loosen _MAX_RANGE_MONTHS's comparison from `> 11` to
    `> 12` -- a 13-calendar-month span would then be silently accepted --
    red. Verified both directions: exactly 12 months is allowed, 13 is not."""
    # 2026-01 .. 2026-12 is 12 calendar months inclusive -- allowed.
    resp_ok = client.get(
        "/admin/reports/cost?from=2026-01&to=2026-12&group_by=firm")
    assert resp_ok.status_code == 200, resp_ok.text

    # 2026-01 .. 2027-01 is 13 calendar months inclusive -- refused.
    resp_too_wide = client.get(
        "/admin/reports/cost?from=2026-01&to=2027-01&group_by=firm")
    assert resp_too_wide.status_code == 422, resp_too_wide.text


# --------------------------------------------------------------------------
# Parameterisation (exit criterion 2, part 2): the mutation this test must
# catch is a route that string-formats from/to/channel into the SQL text
# instead of binding them as query parameters.
# --------------------------------------------------------------------------

def test_cost_report_sends_the_range_as_bound_query_parameters(
        client, captured_queries):
    resp = client.get(
        "/admin/reports/cost?from=2026-01&to=2026-03&group_by=kit"
        "&channel=demo")
    assert resp.status_code == 200, resp.text
    assert len(captured_queries) == 1
    call = captured_queries[0]
    param_names = {p.name for p in call["parameters"]}
    param_values = {p.name: p.value for p in call["parameters"]}
    assert {"from_month", "to_month", "channel"} <= param_names
    assert param_values["from_month"] == "2026-01"
    assert param_values["to_month"] == "2026-03"
    assert param_values["channel"] == "demo"
    # The values themselves must NEVER appear literally inside the SQL text
    # -- a route that reverted to f-string interpolation would still pass
    # the parameter-presence check above (nothing stops a caller from ALSO
    # formatting the value into the string) unless this is checked too.
    assert "2026-01" not in call["sql"]
    assert "2026-03" not in call["sql"]
    assert "'demo'" not in call["sql"]
    assert "@from_month" in call["sql"]
    assert "@to_month" in call["sql"]
    assert "@channel" in call["sql"]


def test_cost_report_selects_the_right_view_per_group_by(
        client, captured_queries):
    """Mutation: hard-code cost_by_firm_month regardless of group_by --
    red."""
    for group_by, view in (
        ("firm", "cost_by_firm_month"),
        ("kit", "cost_by_kit_month"),
        ("employee", "cost_by_employee_month"),
    ):
        captured_queries.clear()
        resp = client.get(
            "/admin/reports/cost?from=2026-01&to=2026-01&group_by={}"
            .format(group_by))
        assert resp.status_code == 200, resp.text
        assert view in captured_queries[0]["sql"], (
            group_by, captured_queries[0]["sql"])


def test_cost_report_carries_delayed_true_and_a_note(
        client, captured_queries):
    resp = client.get(
        "/admin/reports/cost?from=2026-01&to=2026-01&group_by=firm")
    body = resp.json()
    assert body["delayed"] is True
    assert body["note"] == report_routes.DELAYED_NOTE


def test_cost_report_maps_bigquery_unavailable_to_503(
        client, monkeypatch):
    def _boom(sql, parameters):
        raise bigquery_reports.BigQueryUnavailable("boom")

    monkeypatch.setattr(bigquery_reports, "_run_query", _boom)
    resp = client.get(
        "/admin/reports/cost?from=2026-01&to=2026-01&group_by=firm")
    assert resp.status_code == 503, resp.text


# --------------------------------------------------------------------------
# Income report.
# --------------------------------------------------------------------------

def test_income_report_requires_from_and_to(client, captured_queries):
    resp = client.get("/admin/reports/income?to=2026-09")
    assert resp.status_code == 422
    resp = client.get("/admin/reports/income?from=2026-01")
    assert resp.status_code == 422


def test_income_report_uses_income_month_view_and_bound_parameters(
        client, captured_queries):
    resp = client.get(
        "/admin/reports/income?from=2026-01&to=2026-03")
    assert resp.status_code == 200, resp.text
    call = captured_queries[0]
    assert "income_month" in call["sql"]
    param_values = {p.name: p.value for p in call["parameters"]}
    assert param_values["from_month"] == "2026-01"
    assert param_values["to_month"] == "2026-03"
    assert "2026-01" not in call["sql"]


def test_income_report_refuses_a_range_wider_than_12_months(
        client, captured_queries):
    resp = client.get(
        "/admin/reports/income?from=2026-01&to=2027-01")
    assert resp.status_code == 422, resp.text


def test_income_report_carries_delayed_true_and_a_note(
        client, captured_queries):
    resp = client.get("/admin/reports/income?from=2026-01&to=2026-01")
    body = resp.json()
    assert body["delayed"] is True
    assert body["note"] == report_routes.DELAYED_NOTE


def test_income_report_maps_bigquery_unavailable_to_503(client, monkeypatch):
    def _boom(sql, parameters):
        raise bigquery_reports.BigQueryUnavailable("boom")

    monkeypatch.setattr(bigquery_reports, "_run_query", _boom)
    resp = client.get("/admin/reports/income?from=2026-01&to=2026-01")
    assert resp.status_code == 503, resp.text


def test_income_report_has_no_channel_parameter(client, captured_queries):
    """Unlike the cost report, income has NO channel filter at all -- a
    request with no ?channel= must succeed and never bind a `channel`
    query parameter (income_month rows carry no channel to filter on; see
    bigquery_reports.query_income_report's docstring)."""
    resp = client.get("/admin/reports/income?from=2026-01&to=2026-01")
    assert resp.status_code == 200, resp.text
    param_names = {p.name for p in captured_queries[0]["parameters"]}
    assert "channel" not in param_names


@pytest.mark.parametrize("channel", ["demo", "staging", "prod"])
def test_income_report_refuses_any_channel_value(
        client, captured_queries, channel):
    """income_month rows are always channel=NULL (sql/telemetry_views.sql):
    a `channel = @channel` filter can never match a row, so the route
    refuses ANY channel value -- including a KNOWN one -- rather than
    silently returning zero rows for a filter that can never work. This is
    the mpebj cross-surface review finding: the route must not accept a
    parameter it can only ever answer wrong."""
    resp = client.get(
        "/admin/reports/income?from=2026-01&to=2026-01&channel={}".format(
            channel))
    assert resp.status_code == 422, resp.text
    assert captured_queries == []
