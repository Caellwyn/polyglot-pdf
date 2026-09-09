"""sql/telemetry_views.sql -- the income filter + column provenance
(Epic 3 bead 6, E3.6, exit criterion 1).

WHY THIS FILE PARSES THE SQL TEXT DIRECTLY. No CI step runs `bq query`
(there is no live BigQuery project to run it against in a test), so a
regex/substring read of the shipped SQL is the only mechanical guard
available -- the same shape as tests/test_setup_telemetry_script.py reading
scripts/setup-telemetry.sh's text.

THE INCOME FILTER IS THE HEADLINE ASSERTION. income_month must carry
`firm_kind = 'live'` IN THE VIEW ITSELF, not left to a caller's WHERE
clause -- Epic 3's overall exit criterion 5 ("the income view cannot return
mock-firm entries") depends on this, and this bead inherits that half of it
explicitly (bd body: "Inherits Epic 3 criterion 5 (income filter half)").

THE COLUMN-PROVENANCE CHECK IS DERIVED, NOT HAND-LISTED (CLAUDE.md scar #8:
enumerate the set mechanically). Every column each view references under
jsonPayload.message.metadata.* must be a member of
log_schemas.USAGE_CONTEXT_KEYS (plus the fixed cost/count/usage_kind keys
StructuredLogger._emit always writes), and every column referenced under
flat jsonPayload.* (the ledger_export shape) must be a member of
credit_ledger.LEDGER_EXPORT_FIELDS. A view that references a column neither
event actually emits would silently return NULL for that column forever
(BigQuery does not error on referencing a JSON path that never appears) --
exactly the kind of gap this test exists to catch before it reaches a
dashboard as a quietly-empty column.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.services.credit_ledger import LEDGER_EXPORT_FIELDS
from backend.utils.log_schemas import USAGE_CONTEXT_KEYS

REPO_ROOT = Path(__file__).resolve().parents[3]
SQL_FILE = REPO_ROOT / "sql" / "telemetry_views.sql"

# The fixed keys StructuredLogger._emit_usage always writes into `metadata`
# ALONGSIDE the USAGE_CONTEXT_KEYS identity/context keys (see
# backend/utils/structured_logger.py._emit_usage: usage_metadata["usage_kind"]
# = usage_kind, plus whatever count/cost keys the caller's metadata dict
# supplies). usage_kind is structural (always present); the count/cost keys
# below are the ones log_schemas.UsageEventMetadata actually declares, so a
# view referencing one is referencing a real column, not a fabricated one.
USAGE_FIXED_KEYS = {
    "usage_kind",
    "prompt_token_count",
    "candidates_token_count",
    "total_token_count",
    "cached_content_token_count",
    "character_count",
    "cost_estimate_usd",
}

# The complete set of columns a usage-event view is allowed to reference
# under jsonPayload.message.metadata.*
ALLOWED_USAGE_METADATA_COLUMNS = frozenset(USAGE_CONTEXT_KEYS) | USAGE_FIXED_KEYS

# The complete set of columns a ledger_export-event view is allowed to
# reference under flat jsonPayload.*
ALLOWED_LEDGER_COLUMNS = frozenset(LEDGER_EXPORT_FIELDS)

# event_type is a structural key on both shapes (used to select the rows
# in the first place, not as a GROUP BY / SUM target), so it is permitted
# wherever it appears without needing a schema entry of its own.
STRUCTURAL_KEYS = {"event_type", "timestamp"}


def _sql_text() -> str:
    assert SQL_FILE.is_file(), (
        "sql/telemetry_views.sql is missing. It is the file this whole "
        "test module asserts against.")
    return SQL_FILE.read_text(encoding="utf-8")


def _view_body(text: str, view_name: str) -> str:
    """The CREATE OR REPLACE VIEW body for one view, up to the next such
    statement or end of file."""
    pattern = re.compile(
        r"CREATE OR REPLACE VIEW `\$\{DATASET\}\." + re.escape(view_name)
        + r"` AS(.*?)(?=CREATE OR REPLACE VIEW|\Z)",
        re.DOTALL,
    )
    match = pattern.search(text)
    assert match, "no CREATE OR REPLACE VIEW found for {}".format(view_name)
    return match.group(1)


ALL_VIEW_NAMES = (
    "cost_by_firm_month",
    "cost_by_kit_month",
    "cost_by_employee_month",
    "hosting_cost_by_service_month",
    "income_month",
)


def test_every_named_view_exists_in_the_sql_file():
    """The five views the bead's description names, all present. Mutation:
    delete one CREATE OR REPLACE VIEW statement -- red."""
    text = _sql_text()
    for name in ALL_VIEW_NAMES:
        _view_body(text, name)  # raises (via assert) if missing


def test_income_month_hardcodes_the_live_firm_kind_filter():
    """THE headline assertion. Mutation: delete the firm_kind = 'live'
    predicate, or move it into a comment -- red."""
    text = _sql_text()
    body = _view_body(text, "income_month")
    assert re.search(
        r"JSON_VALUE\(jsonPayload\.firm_kind\)\s*=\s*'live'", body), (
        "income_month's WHERE clause does not hard-code firm_kind = 'live'. "
        "This is Epic 3's exit criterion 5 (income filter half) and must "
        "live in the VIEW DEFINITION, not a caller's query.")


def test_income_month_filters_to_purchase_and_subscription_grant_only():
    """The plan's income definition: purchase | subscription_grant entries
    only, never mint_debit/expiry_refund/adjustment/promo_grant (those would
    inflate or corrupt an income total). Mutation: widen the IN list, or
    drop the type filter entirely -- red."""
    text = _sql_text()
    body = _view_body(text, "income_month")
    type_filter = re.search(
        r"JSON_VALUE\(jsonPayload\.type\)\s+IN\s+\(([^)]*)\)", body)
    assert type_filter, "income_month has no jsonPayload.type IN (...) filter"
    types = {t.strip().strip("'") for t in type_filter.group(1).split(",")}
    assert types == {"purchase", "subscription_grant"}, (
        "income_month's type filter is {}, expected exactly "
        "{{'purchase', 'subscription_grant'}}".format(sorted(types)))


def test_income_month_filters_to_the_ledger_export_event_type():
    """income_month must scope to ledger_export rows specifically (the
    shared sink table also carries usage rows) -- flat jsonPayload.event_type,
    matching how credit_ledger.py actually emits it. Mutation: drop this
    filter, or point it at jsonPayload.message.event_type (the WRONG shape
    for this event) -- red."""
    text = _sql_text()
    body = _view_body(text, "income_month")
    assert re.search(
        r"JSON_VALUE\(jsonPayload\.event_type\)\s*=\s*'ledger_export'",
        body), (
        "income_month does not filter on the flat jsonPayload.event_type = "
        "'ledger_export' -- without it the view would aggregate usage rows "
        "too, which have no jsonPayload.type/usd_amount at all")


def _usage_metadata_columns_referenced(body: str) -> set:
    return set(re.findall(
        r"jsonPayload\.message\.metadata\.(\w+)", body))


def _ledger_columns_referenced(body: str) -> set:
    """Flat jsonPayload.<col> references, excluding the nested
    message.metadata.* accessor (which the regex below would otherwise
    also match as jsonPayload.message)."""
    all_refs = set(re.findall(r"jsonPayload\.(\w+)", body))
    return all_refs - {"message"}


def test_usage_views_reference_only_columns_the_usage_events_emit():
    """cost_by_firm_month / cost_by_kit_month / cost_by_employee_month may
    reference ONLY columns StructuredLogger._emit_usage actually writes into
    jsonPayload.message.metadata -- derived from log_schemas.
    USAGE_CONTEXT_KEYS plus the fixed count/cost keys, never hand-listed
    here. Mutation: add a reference to a column the usage envelope does not
    have (e.g. jsonPayload.message.metadata.session_id) to any of the three
    views -- red."""
    text = _sql_text()
    for name in ("cost_by_firm_month", "cost_by_kit_month", "cost_by_employee_month"):
        body = _view_body(text, name)
        referenced = _usage_metadata_columns_referenced(body)
        assert referenced, "{} references no metadata columns at all".format(name)
        unknown = referenced - ALLOWED_USAGE_METADATA_COLUMNS
        assert not unknown, (
            "{} references column(s) the usage event envelope does not "
            "emit: {}. Allowed columns are derived from "
            "log_schemas.USAGE_CONTEXT_KEYS + the fixed cost/count keys: "
            "{}".format(name, sorted(unknown), sorted(ALLOWED_USAGE_METADATA_COLUMNS))
        )


def test_usage_views_filter_on_the_nested_usage_event_types():
    """Each cost-by-* view must scope to the three usage event_types via the
    NESTED jsonPayload.message.event_type accessor (StructuredLogger._emit's
    shape), not the flat one (which is ledger_export's shape and would
    silently match zero usage rows). Mutation: change
    jsonPayload.message.event_type to jsonPayload.event_type in any of the
    three views -- red."""
    text = _sql_text()
    for name in ("cost_by_firm_month", "cost_by_kit_month", "cost_by_employee_month"):
        body = _view_body(text, name)
        assert "jsonPayload.message.event_type" in body, (
            "{} does not filter on jsonPayload.message.event_type".format(name)
        )
        for usage_event in ("gemini_api_response", "text_ai_usage", "tts_usage"):
            assert "'{}'".format(usage_event) in body, (
                "{} is missing usage_kind {!r} from its event_type "
                "filter".format(name, usage_event)
            )


def test_income_view_references_only_columns_ledger_export_emits():
    """income_month may reference ONLY columns credit_ledger.py's
    LEDGER_EXPORT_FIELDS actually puts on the ledger_export log line.
    Mutation: reference jsonPayload.employee_id (a real usage-event column,
    but NOT one ledger_export emits) in income_month -- red."""
    text = _sql_text()
    body = _view_body(text, "income_month")
    referenced = _ledger_columns_referenced(body) - STRUCTURAL_KEYS
    assert referenced, "income_month references no jsonPayload columns at all"
    unknown = referenced - ALLOWED_LEDGER_COLUMNS
    assert not unknown, (
        "income_month references column(s) the ledger_export event does "
        "not emit: {}. Allowed columns are credit_ledger."
        "LEDGER_EXPORT_FIELDS: {}".format(
            sorted(unknown), sorted(ALLOWED_LEDGER_COLUMNS))
    )


def test_cost_views_group_by_month_and_do_not_double_count_usage_kinds():
    """Each cost-by-* view GROUPs BY usage_kind (not just firm/kit/employee)
    so a live_voice row and a text_secretary row for the same firm/month
    stay distinguishable rather than being summed into one opaque total.
    Mutation: drop usage_kind from a GROUP BY clause -- red."""
    text = _sql_text()
    for name in ("cost_by_firm_month", "cost_by_kit_month", "cost_by_employee_month"):
        body = _view_body(text, name)
        group_by = re.search(r"GROUP BY([^;]*);", body)
        assert group_by, "{} has no GROUP BY clause".format(name)
        assert "usage_kind" in group_by.group(1), (
            "{}'s GROUP BY does not include usage_kind".format(name)
        )
        assert "month" in group_by.group(1), (
            "{}'s GROUP BY does not include month".format(name)
        )


def test_hosting_cost_view_reads_the_billing_export_table_not_the_sink():
    """hosting_cost_by_service_month is the one view that does NOT read the
    telemetry sink table -- it reads the Cloud Billing export instead.
    Mutation: point it at ${TELEMETRY_TABLE} -- red (there is no cost data
    in the logging sink; Cloud Run/Hosting cost only exists in the billing
    export)."""
    text = _sql_text()
    body = _view_body(text, "hosting_cost_by_service_month")
    assert "${BILLING_EXPORT_TABLE}" in body
    assert "${TELEMETRY_TABLE}" not in body
    assert "Cloud Run" in body and "Firebase Hosting" in body


def test_views_that_read_the_sink_use_the_telemetry_table_placeholder():
    """The four sink-backed views reference ${TELEMETRY_TABLE}, and none of
    them accidentally reads the billing export table. Mutation: change one
    view's FROM clause to ${BILLING_EXPORT_TABLE} -- red."""
    text = _sql_text()
    for name in ("cost_by_firm_month", "cost_by_kit_month",
                 "cost_by_employee_month", "income_month"):
        body = _view_body(text, name)
        assert "${TELEMETRY_TABLE}" in body, (
            "{} does not read FROM ${{TELEMETRY_TABLE}}".format(name)
        )
        assert "${BILLING_EXPORT_TABLE}" not in body, (
            "{} incorrectly references the billing export table".format(name)
        )
