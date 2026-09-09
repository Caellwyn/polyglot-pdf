"""scripts/setup-telemetry.sh's declared dataset, sink filter, and IAM grants
(Epic 3 bead 6, E3.6).

This is an OPERATOR script -- no deploy pipeline runs it, and no CI step
executes gcloud/bq -- so the only mechanical guard available is pinning the
SHIPPED SCRIPT TEXT, matching the sibling tests/test_setup_firestore_ttl_
script.py and tests/test_setup_admin_service_scheduler.py pattern.

WHY THE SINK FILTER GETS ITS OWN CAREFUL TEST. The bead's own description
and docs/sprint_22_admin-console_plan.md both say the sink filters on
"jsonPayload.event_type in the usage / session / ledger_export / error set"
as if one field name covers every emitter. It does not: usage events
(gemini_api_response, text_ai_usage, tts_usage) are emitted by
StructuredLogger._emit, which nests the whole envelope under a `message`
key, so their event type is at jsonPayload.message.event_type; ledger_export
is emitted by credit_ledger.py's plain structlog call WITH an explicit
event_type kwarg, so it lands flat at jsonPayload.event_type; and the two
wired session events (form_session_started / form_session_ended) are
emitted by confirmation_logger.py's plain structlog calls WITHOUT an
event_type kwarg, so they land under the POSITIONAL event name key
jsonPayload.event, not jsonPayload.event_type at all. Verified against real
emitted JSON (see scripts/setup-telemetry.sh's own module docstring for the
three captured shapes), not reconstructed from the plan prose. A filter that
only checked jsonPayload.event_type would silently drop the session rows
entirely and the usage rows too (wrong nesting depth) -- exactly the kind of
gap where BigQuery returns zero rows with no error and the plan's own text
would have you believe that was the whole filter.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup-telemetry.sh"
SQL_FILE = REPO_ROOT / "sql" / "telemetry_views.sql"


def _script_text() -> str:
    assert SCRIPT.is_file(), (
        "scripts/setup-telemetry.sh is missing. It is the script this "
        "whole file asserts against.")
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists_and_starts_with_a_shebang():
    """Mirrors test_setup_firestore_ttl_script.py's rationale: git tracks
    these sibling scripts as mode 100644 on this repo, and Windows stat()
    never reports S_IXUSR, so the shebang -- not the executable bit -- is
    what actually governs `bash scripts/foo.sh` / `./scripts/foo.sh`."""
    text = _script_text()
    assert text.startswith("#!/bin/bash"), (
        "scripts/setup-telemetry.sh must start with a #!/bin/bash shebang")


def test_script_requires_a_project_id_argument():
    """Mutation: drop the PROJECT_ID empty-check / exit 1 -- red."""
    text = _script_text()
    assert re.search(r'if\s*\[\s*-z\s*"\$PROJECT_ID"\s*\]', text)
    assert "exit 1" in text


def test_script_is_idempotent_by_construction():
    """set -e must be declared so a genuine gcloud/bq failure stops the
    script rather than silently continuing to the next step. Mutation:
    remove 'set -e' -- red."""
    text = _script_text()
    assert re.search(r"^set -e\s*$", text, re.MULTILINE), (
        "scripts/setup-telemetry.sh must declare 'set -e'")


def test_dataset_name_and_location_are_pinned():
    """The dataset name and location the bead's contract names literally.
    Mutation: change DATASET or LOCATION's value -- red."""
    text = _script_text()
    assert re.search(r'DATASET="polyglot_telemetry"', text), (
        "the dataset must be named polyglot_telemetry")
    assert re.search(r'LOCATION="us-central1"', text), (
        "the dataset location must be us-central1")
    # And the dataset-create call actually uses these variables, not a
    # hardcoded literal that could drift from the pinned name above.
    assert re.search(r'--location="\$LOCATION"', text)
    assert re.search(r'"\$DATASET"', text)


def test_bigquery_api_is_enabled():
    """Mutation: remove the bigquery.googleapis.com enable line -- red."""
    text = _script_text()
    assert re.search(r"gcloud services enable[^\n]*\n[^\n]*bigquery\.googleapis\.com", text), (
        "scripts/setup-telemetry.sh does not enable bigquery.googleapis.com")


def test_sink_covers_both_cloud_run_services():
    """The sink's resource filter names BOTH backend services by name, per
    the bead's own description. Mutation: drop
    "polyglot-backend-staging" from the filter -- red."""
    text = _script_text()
    filter_match = re.search(r"SINK_FILTER='([^']*)'", text)
    assert filter_match, "SINK_FILTER is not defined as a single-quoted string"
    sink_filter = filter_match.group(1)
    assert '"polyglot-backend"' in sink_filter
    assert '"polyglot-backend-staging"' in sink_filter


def test_sink_filter_covers_all_three_actual_event_shapes():
    """THE core pin: the sink filter must actually match what each emitter
    produces, not the single-shape story the plan's prose tells.

    Mutation: change any ONE of the three OR clauses below (e.g. drop the
    jsonPayload.event clause entirely, or point jsonPayload.message.event_type
    at jsonPayload.event_type) -- red.
    """
    text = _script_text()
    filter_match = re.search(r"SINK_FILTER='([^']*)'", text)
    assert filter_match, "SINK_FILTER is not defined as a single-quoted string"
    sink_filter = filter_match.group(1)

    # Shape 1: ledger_export -- flat jsonPayload.event_type (credit_ledger.py
    # passes event_type as an explicit structlog-bound kwarg).
    assert 'jsonPayload.event_type="ledger_export"' in sink_filter, (
        "the filter is missing the flat jsonPayload.event_type clause for "
        "ledger_export")

    # Shape 2: usage events -- NESTED jsonPayload.message.event_type
    # (StructuredLogger._emit wraps the envelope in a `message` key).
    assert "jsonPayload.message.event_type=" in sink_filter, (
        "the filter is missing the nested jsonPayload.message.event_type "
        "clause for the usage events")
    for usage_event in ("gemini_api_response", "text_ai_usage", "tts_usage"):
        assert '"{}"'.format(usage_event) in sink_filter, (
            "the filter's usage clause is missing {!r}".format(usage_event))

    # Shape 3: session events -- flat jsonPayload.event (confirmation_
    # logger.py's structlog calls pass NO event_type kwarg, so the
    # POSITIONAL event name renders under the plain "event" key).
    assert "jsonPayload.event=" in sink_filter, (
        "the filter is missing the jsonPayload.event clause for the "
        "session events (form_session_started/form_session_ended land "
        "under the bare 'event' key, not 'event_type', because "
        "confirmation_logger.py never passes an event_type kwarg)")
    for session_event in ("form_session_started", "form_session_ended"):
        assert '"{}"'.format(session_event) in sink_filter, (
            "the filter's session clause is missing {!r}".format(session_event))

    # The three shapes must be OR'd together, not AND'd -- a row satisfying
    # any ONE of them should be captured.
    assert " OR " in sink_filter


def test_sink_filter_does_not_claim_a_single_flat_event_type_clause():
    """The negative half of the shape test above: the filter must not be
    written as if jsonPayload.event_type alone covered every case (the bug
    this bead's investigation found in the plan's own prose). Mutation:
    collapse the filter to one bare `jsonPayload.event_type IN (...)`
    clause -- red."""
    text = _script_text()
    filter_match = re.search(r"SINK_FILTER='([^']*)'", text)
    assert filter_match
    sink_filter = filter_match.group(1)
    # A single "IN (" list covering all four names is the exact
    # single-shape shortcut this test forbids.
    assert " IN (" not in sink_filter, (
        "the sink filter uses a single 'IN (...)' clause, which cannot "
        "express the three genuinely different jsonPayload shapes "
        "(flat event_type, nested message.event_type, flat event)")


def test_sink_uses_partitioned_tables():
    """Mutation: drop --use-partitioned-tables -- red (the views assume
    partition pruning on a month-range filter)."""
    text = _script_text()
    assert "--use-partitioned-tables" in text


def test_writer_identity_gets_dataeditor_on_the_dataset():
    """The sink's own writer identity (printed by `gcloud logging sinks
    create`, parsed at runtime -- not a hardcoded principal) must be granted
    bigquery.dataEditor on the dataset, via `bq add-iam-policy-binding`
    (dataset-scoped), not `gcloud projects add-iam-policy-binding`
    (project-wide). Mutation: change dataEditor to a different role, or move
    the grant onto `gcloud projects add-iam-policy-binding` -- red."""
    text = _script_text()
    assert "roles/bigquery.dataEditor" in text
    # The grant is issued via `bq add-iam-policy-binding`, not the
    # project-level gcloud command.
    editor_block_match = re.search(
        r'bq add-iam-policy-binding \\(?:[^\n]*\n){0,6}?[^\n]*'
        r'--role="roles/bigquery\.dataEditor"',
        text)
    assert editor_block_match, (
        "roles/bigquery.dataEditor is not granted via `bq "
        "add-iam-policy-binding`")
    # And the negative half: dataEditor must never appear on a
    # project-level gcloud add-iam-policy-binding invocation.
    project_binding_blocks = re.findall(
        r'gcloud projects add-iam-policy-binding.*?(?=\n\n|\Z)', text,
        re.DOTALL)
    for block in project_binding_blocks:
        assert "bigquery.dataEditor" not in block, (
            "roles/bigquery.dataEditor appears in a project-level "
            "add-iam-policy-binding call -- it must be dataset-scoped.")


def test_admin_sa_gets_jobuser_and_dataviewer():
    """admin-backend-sa gets roles/bigquery.jobUser (project-level) and
    roles/bigquery.dataViewer (dataset-scoped) -- the third and fourth of
    the bead's four IAM grants (writer-identity dataEditor and the two
    admin-sa roles). Mutation: drop either grant -- red."""
    text = _script_text()
    assert 'ADMIN_SA_EMAIL="admin-backend-sa@' in text
    assert "roles/bigquery.jobUser" in text
    assert "roles/bigquery.dataViewer" in text
    # jobUser via the project-level command.
    assert re.search(
        r'gcloud projects add-iam-policy-binding "\$PROJECT_ID"[^\n]*\n'
        r'(?:[^\n]*\n){0,4}?\s*--role="roles/bigquery\.jobUser"',
        text), "bigquery.jobUser must be granted project-wide via gcloud projects add-iam-policy-binding"
    # dataViewer via the dataset-scoped bq command, targeting $DATASET.
    dataviewer_block = re.search(
        r'bq add-iam-policy-binding \\(?:[^\n]*\n){0,6}?[^\n]*'
        r'--role="roles/bigquery\.dataViewer"(?:[^\n]*\n){0,3}?[^\n]*"\$DATASET"',
        text)
    assert dataviewer_block, (
        "roles/bigquery.dataViewer must be granted via `bq "
        "add-iam-policy-binding ... \"$DATASET\"` (dataset-scoped)")


def test_all_four_iam_grants_are_present():
    """The bead names exactly four IAM grants in its description: the sink
    writer's dataEditor, and admin-backend-sa's jobUser + dataViewer (three
    role grants across two identities -- the fourth 'grant' in the bead's
    prose count is the sink creation itself, which is not a role binding).
    Enumerated here as a single set-based pin so a future edit that drops
    one is caught by name, not just by the individual tests above drifting
    green for the wrong reason."""
    text = _script_text()
    role_grants = re.findall(r'--role="(roles/bigquery\.\w+)"', text)
    assert set(role_grants) == {
        "roles/bigquery.dataEditor",
        "roles/bigquery.jobUser",
        "roles/bigquery.dataViewer",
    }, (
        "expected exactly the sink-writer dataEditor grant plus "
        "admin-backend-sa's jobUser + dataViewer grants; got: "
        "{}".format(sorted(set(role_grants)))
    )


def test_sql_file_exists_and_is_applied_by_the_script():
    """sql/telemetry_views.sql must exist and the script must actually
    apply it (via bq query), not just reference it in a comment. Mutation:
    remove the `bq query` invocation -- red."""
    assert SQL_FILE.is_file(), "sql/telemetry_views.sql is missing"
    text = _script_text()
    assert re.search(r"bq query[^\n]*--use_legacy_sql=false", text), (
        "scripts/setup-telemetry.sh never runs `bq query ... "
        "--use_legacy_sql=false` against sql/telemetry_views.sql")
    assert "telemetry_views.sql" in text
