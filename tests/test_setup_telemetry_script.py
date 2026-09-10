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


def test_sink_covers_all_three_emitting_cloud_run_services():
    """The sink's resource filter must name all THREE services that
    actually emit a filtered event_type: the public backend, its staging
    twin, AND the admin service. ledger_export (the event income_month
    reads) is emitted ONLY by admin_backend/routes/credit_routes.py and
    admin_backend/routes/sweep_routes.py -- both of which run on the admin
    service (deploy-admin.sh's ADMIN_SERVICE_NAME, "polyglot-admin"), never
    on the public backend. Omitting "polyglot-admin" here makes
    income_month return zero rows forever with no error (bd
    polyglot-pdf-rd3s8 review finding 1).

    Mutation: drop "polyglot-backend-staging" OR "polyglot-admin" from the
    filter -- red."""
    text = _script_text()
    filter_match = re.search(r"SINK_FILTER='([^']*)'", text)
    assert filter_match, "SINK_FILTER is not defined as a single-quoted string"
    sink_filter = filter_match.group(1)
    assert '"polyglot-backend"' in sink_filter
    assert '"polyglot-backend-staging"' in sink_filter
    assert '"polyglot-admin"' in sink_filter, (
        "the sink filter must include \"polyglot-admin\" -- ledger_export "
        "(which income_month reads) is emitted only by the admin service's "
        "credit_routes.py and sweep_routes.py, never by the public backend")


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


def test_sink_filter_captures_the_ws_error_rows():
    """The error clause Epic 3 bead 8 (E3.8) added.

    This script's own header PREDICTED this widening: log_error routes
    through the same StructuredLogger._emit as the usage events, so ws_error
    shares their nested jsonPayload.message.event_type shape and joining the
    existing clause was a one-word change. Pinning it stops a later edit from
    silently dropping it back out -- which would leave BigQuery with no error
    rows at all while the sink still reported healthy.

    Mutation: remove "ws_error" from the usage clause -- red.
    """
    text = _script_text()
    filter_match = re.search(r"SINK_FILTER='([^']*)'", text)
    assert filter_match
    sink_filter = filter_match.group(1)

    assert '"ws_error"' in sink_filter, (
        "the sink filter does not capture ws_error rows, so the WebSocket "
        "close events wired by bd polyglot-pdf-e4dt8 never reach BigQuery")
    # And it must sit in the NESTED clause, with the usage events -- ws_error
    # is a StructuredLogger._emit row, so a flat jsonPayload.event_type or
    # jsonPayload.event clause for it would match nothing.
    nested_clause = re.search(
        r"jsonPayload\.message\.event_type=\(([^)]*)\)", sink_filter)
    assert nested_clause, "no nested message.event_type clause at all"
    assert '"ws_error"' in nested_clause.group(1), (
        "ws_error is in the filter but NOT in the nested "
        "jsonPayload.message.event_type clause -- StructuredLogger nests its "
        "envelope, so any flatter placement matches zero rows")


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


def test_sink_step_is_create_or_update_not_create_only():
    """bd polyglot-pdf-f7f0h: a re-run must actually APPLY a changed
    SINK_FILTER to the live sink, not just to the file. `gcloud logging
    sinks create` fails on a sink that already exists, so a create-only
    call cannot do this -- the script must branch on `gcloud logging sinks
    describe` and call `gcloud logging sinks update` on the branch where
    the sink already exists. Mutation: remove the `sinks update` call, or
    remove the `sinks describe` branch so the script falls back to
    create-only again -- red."""
    text = _script_text()
    assert "gcloud logging sinks describe" in text, (
        "the script never calls `gcloud logging sinks describe` to decide "
        "whether the sink already exists")
    assert re.search(r"gcloud logging sinks update \"\$SINK_NAME\"", text), (
        "the script never calls `gcloud logging sinks update` -- a re-run "
        "against a project that already has the sink cannot apply a "
        "changed SINK_FILTER without this call")
    assert re.search(r"gcloud logging sinks create \"\$SINK_NAME\"", text), (
        "the script must still call `gcloud logging sinks create` on the "
        "branch where the sink does not exist yet")
    # The update call must actually pass the (possibly changed) filter, not
    # just re-touch the sink.
    update_block = re.search(
        r"gcloud logging sinks update \"\$SINK_NAME\"(?:[^\n]*\n){0,4}?"
        r"[^\n]*--log-filter=\"\$SINK_FILTER\"",
        text)
    assert update_block, (
        "the `sinks update` call does not pass --log-filter=\"$SINK_FILTER\" "
        "-- a re-run would touch the sink without actually applying the "
        "new filter")


def test_sink_step_resolves_writer_identity_on_both_branches():
    """The writer-identity grant (step 4) must not silently go missing on
    a re-run: `gcloud logging sinks create` prints writerIdentity in its
    output, but `gcloud logging sinks update` does not -- so the update
    branch must fetch it via a separate `sinks describe --format=` call.
    Mutation: drop the describe-for-writerIdentity call on the update
    branch, leaving WRITER_IDENTITY empty on every re-run -- red."""
    text = _script_text()
    assert re.search(
        r'WRITER_IDENTITY=\$\(gcloud logging sinks describe "\$SINK_NAME"'
        r'(?:[^\n]*\n){0,3}?[^\n]*--format="value\(writerIdentity\)"',
        text), (
        "the update branch does not resolve WRITER_IDENTITY via "
        "`gcloud logging sinks describe ... --format=value(writerIdentity)`")


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


def test_script_discovers_both_stdout_and_stderr_tables_separately():
    """bd polyglot-pdf-ih428: the sink writes usage events to a
    run_googleapis_com_stdout table and ledger_export/session events to a
    SEPARATE run_googleapis_com_stderr table (see the script's own section-6
    comment for why). The script must discover BOTH table names from `bq
    ls`, not `head -1` a single one and reuse it for every view. Mutation:
    collapse TELEMETRY_TABLE_STDOUT/TELEMETRY_TABLE_STDERR back into one
    TELEMETRY_TABLE variable fed by a single `bq ls | ... | head -1` -- red.
    """
    text = _script_text()
    # A single `bq ls` call populates a shared CSV variable that both
    # TELEMETRY_TABLE_STDOUT and TELEMETRY_TABLE_STDERR are then filtered
    # from -- so the traceable requirement is that `bq ls` feeds a variable
    # that BOTH assignments read from, and each assignment greps for its
    # own distinct stream name.
    csv_source = re.search(r'(\w+)=\$\(bq ls[^\n]*\)', text)
    assert csv_source, "no variable is populated directly from `bq ls`"
    csv_var = csv_source.group(1)
    stdout_line = re.search(
        r'TELEMETRY_TABLE_STDOUT=\$\([^\n]*\$' + re.escape(csv_var) + r'[^\n]*\)', text)
    stderr_line = re.search(
        r'TELEMETRY_TABLE_STDERR=\$\([^\n]*\$' + re.escape(csv_var) + r'[^\n]*\)', text)
    assert stdout_line, (
        "TELEMETRY_TABLE_STDOUT is not populated from the `bq ls` output "
        "variable ({!r})".format(csv_var))
    assert stderr_line, (
        "TELEMETRY_TABLE_STDERR is not populated from the `bq ls` output "
        "variable ({!r})".format(csv_var))
    # The two discovery pipelines must filter on DIFFERENT stream names, not
    # the same "stdout" grep reused twice.
    stdout_grep = re.search(r'grep -i "([^"]*)"', stdout_line.group(0))
    stderr_grep = re.search(r'grep -i "([^"]*)"', stderr_line.group(0))
    assert stdout_grep and stderr_grep, (
        "could not find the grep filters for the two table-discovery lines")
    assert "stdout" in stdout_grep.group(1).lower()
    assert "stderr" in stderr_grep.group(1).lower()
    assert stdout_grep.group(1) != stderr_grep.group(1), (
        "the stdout and stderr table-discovery greps use the same filter -- "
        "they must select different rows from `bq ls`")


def test_script_substitutes_both_telemetry_table_placeholders_independently():
    """The sed pipeline applying sql/telemetry_views.sql must substitute
    ${TELEMETRY_TABLE_STDOUT} and ${TELEMETRY_TABLE_STDERR} with their own
    discovered table names, not the same single ${TELEMETRY_TABLE}
    placeholder for both (the exact bug bd polyglot-pdf-ih428 pins: a
    single substituted table left either the three cost views or
    income_month permanently and silently empty). Mutation: change the
    TELEMETRY_TABLE_STDERR sed clause to substitute
    $TELEMETRY_TABLE_STDOUT instead of $TELEMETRY_TABLE_STDERR -- red."""
    text = _script_text()
    assert re.search(
        r'-e "s\|\\\$\{TELEMETRY_TABLE_STDOUT\}\|\$PROJECT_ID\.\$DATASET\.\$TELEMETRY_TABLE_STDOUT\|g"',
        text), (
        "the sed pipeline does not substitute ${TELEMETRY_TABLE_STDOUT} "
        "with $TELEMETRY_TABLE_STDOUT")
    assert re.search(
        r'-e "s\|\\\$\{TELEMETRY_TABLE_STDERR\}\|\$PROJECT_ID\.\$DATASET\.\$TELEMETRY_TABLE_STDERR\|g"',
        text), (
        "the sed pipeline does not substitute ${TELEMETRY_TABLE_STDERR} "
        "with $TELEMETRY_TABLE_STDERR")
    # And the negative half: the old single-table placeholder must be gone
    # entirely, not left behind as a third, unused substitution.
    assert "${TELEMETRY_TABLE}" not in text.replace(
        "${TELEMETRY_TABLE_STDOUT}", "").replace("${TELEMETRY_TABLE_STDERR}", ""), (
        "a bare ${TELEMETRY_TABLE} placeholder (the pre-fix single-table "
        "name) is still referenced somewhere in the script")


def test_script_requires_both_tables_before_applying_views():
    """If either the stdout or the stderr table is missing (sink has not
    yet produced a row of that kind), the script must skip view creation
    for BOTH rather than applying with one placeholder left as a literal
    empty string. Mutation: change the guard from `||` to `&&` (only skip
    when BOTH are missing) -- red."""
    text = _script_text()
    guard = re.search(
        r'if \[ -z "\$TELEMETRY_TABLE_STDOUT" \] (\|\||&&) '
        r'\[ -z "\$TELEMETRY_TABLE_STDERR" \]', text)
    assert guard, "no guard found checking both TELEMETRY_TABLE_STDOUT/STDERR"
    assert guard.group(1) == "||", (
        "the both-tables guard uses {!r}, expected '||' -- with '&&' the "
        "script would proceed to substitute an EMPTY table name into the "
        "SQL when only one of the two tables exists yet".format(guard.group(1))
    )
