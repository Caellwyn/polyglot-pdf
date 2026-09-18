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


def test_dataset_name_is_pinned():
    """The dataset name the bead's contract names literally.
    Mutation: change DATASET's value -- red."""
    text = _script_text()
    assert re.search(r'DATASET="polyglot_telemetry"', text), (
        "the dataset must be named polyglot_telemetry")
    # And the dataset-create call actually uses this variable, not a
    # hardcoded literal that could drift from the pinned name above.
    assert re.search(r'--location="\$LOCATION"', text)
    assert re.search(r'"\$DATASET"', text)


def test_location_falls_back_to_us_central1_only_without_billing_table():
    """bd polyglot-pdf-vzvio: LOCATION must no longer be a bare hard-coded
    literal -- it is derived from the billing dataset (via
    telemetry_bq_setup.py resolve-location) whenever BILLING_EXPORT_TABLE
    is given, and only DEFAULTS to us-central1 on the no-argument path.
    Mutation: make LOCATION an unconditional literal again (delete the
    if/else and the resolve-location call) -- red.
    """
    text = _script_text()
    # There must be exactly one top-level LOCATION=... literal assignment
    # (the us-central1 fallback), not the unconditional single assignment
    # the bug report found.
    location_assignments = re.findall(r'^\s*LOCATION="[^"]*"', text, re.MULTILINE)
    assert len(location_assignments) == 1, (
        "expected exactly one top-level LOCATION=... assignment (the "
        "us-central1 fallback in the else branch); got: "
        "{}".format(location_assignments)
    )
    assert location_assignments[0].strip() == 'LOCATION="us-central1"'
    # That assignment must sit in an else branch keyed on
    # BILLING_EXPORT_TABLE, not at top level unconditionally.
    fallback_block = re.search(
        r'if \[ -n "\$BILLING_EXPORT_TABLE" \]; then'
        r'(?:.*?\n){1,20}?else\n\s*LOCATION="us-central1"',
        text, re.DOTALL,
    )
    assert fallback_block, (
        'LOCATION="us-central1" is not inside the else branch of an '
        'if [ -n "$BILLING_EXPORT_TABLE" ] check'
    )


def test_location_is_derived_via_telemetry_bq_setup_resolve_location():
    """The BILLING_EXPORT_TABLE-given branch must call
    telemetry_bq_setup.py resolve-location with the project, the pinned
    DATASET, and the billing table, and must abort the script (exit 1) if
    that call fails -- a location the operator cannot see is silently
    wrong is worse than an aborted run. Mutation: drop the `exit 1` on
    failure, or stop passing --billing-table -- red."""
    text = _script_text()
    assert 'telemetry_bq_setup.py" resolve-location' in text, (
        "setup-telemetry.sh does not call telemetry_bq_setup.py "
        "resolve-location")
    call_block = re.search(
        r'resolve-location \\\n(?:[^\n]*\n){0,4}?[^\n]*--billing-table '
        r'"\$BILLING_EXPORT_TABLE"',
        text,
    )
    assert call_block, (
        "resolve-location is not called with --billing-table "
        '"$BILLING_EXPORT_TABLE"'
    )
    assert re.search(
        r'if ! LOCATION=\$\("\$PYTHON_BIN" "\$SCRIPT_DIR/telemetry_bq_setup\.py" '
        r'resolve-location',
        text,
    ), "LOCATION is not assigned from the resolve-location call's stdout"
    # Failure must abort the script.
    abort_block = re.search(
        r'if ! LOCATION=\$\([^)]*resolve-location.*?\n(?:.*?\n){0,4}?\s*exit 1',
        text, re.DOTALL,
    )
    assert abort_block, (
        "a failed resolve-location call does not `exit 1` -- the script "
        "would continue with an empty/stale LOCATION"
    )


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


def test_writer_identity_is_normalised_to_a_bare_email_before_the_grant():
    """bd polyglot-pdf-k5w16 (the headline bug): the update-branch
    `gcloud logging sinks describe --format=value(writerIdentity)` call
    ALREADY returns the "serviceAccount:service-..." PREFIXED form, while
    the create-branch grep pulls a BARE email out of `sinks create`'s own
    output -- two different shapes landing in the same WRITER_IDENTITY
    variable depending on which branch ran. The grant call below always
    assumed the bare shape (`--member "serviceAccount:$WRITER_IDENTITY"`),
    which doubled the prefix on the update branch and made the deployed
    grant-dataset-role call fail outright (live error: "could not grant
    roles/bigquery.dataEditor ... to
    serviceAccount:serviceAccount:service-..."), aborting the script under
    `set -e` before the view-creation step ever ran. Mutation: delete the
    `WRITER_IDENTITY="${WRITER_IDENTITY#serviceAccount:}"` normalisation
    line -- red (the sink-update-branch bare-prefix-stripped assertion
    below would fail, and a functional run would reproduce the doubled
    member string)."""
    text = _script_text()
    norm_line = re.search(
        r'WRITER_IDENTITY="\$\{WRITER_IDENTITY#serviceAccount:\}"', text)
    assert norm_line, (
        "no WRITER_IDENTITY normalisation line found -- the grant call "
        "below assumes a bare email and will double the prefix whenever "
        "WRITER_IDENTITY already carries one (the update/re-run branch)")
    # The normalisation must run AFTER both branches assign WRITER_IDENTITY
    # (the if/else block) and BEFORE the grant call uses it -- otherwise it
    # only protects one branch.
    if_fi_end = text.index("fi\n", text.index('WRITER_IDENTITY=$(echo "$SINK_CREATE_OUTPUT"'))
    grant_call = text.index('--member "serviceAccount:$WRITER_IDENTITY"')
    assert if_fi_end < norm_line.start() < grant_call, (
        "the normalisation line does not sit between the create/update "
        "branches and the grant call that consumes WRITER_IDENTITY")


def test_writer_identity_normalisation_uses_bash_prefix_strip_not_sed_or_cut():
    """Pin the EXACT mechanism, not just that a normalisation line exists
    (test_writer_identity_is_normalised_to_a_bare_email_before_the_grant
    above already pins presence and position) -- bash's own
    ${VAR#prefix} parameter expansion is a no-op when the prefix is
    absent and strips it exactly once when present, which is exactly the
    two input shapes (bare email from the create branch, prefixed email
    from the update branch) this bead's bug report is about. Mutation:
    change the expansion operator from `#` (strip shortest match from
    the front) to `%` (strip from the back) or `##` (greedy) -- red
    (`%serviceAccount:` would never match anywhere in a
    "serviceAccount:service-..." string since that suffix never
    appears at the END of the value, so the prefix would never be
    stripped at all)."""
    text = _script_text()
    assert re.search(
        r'WRITER_IDENTITY="\$\{WRITER_IDENTITY#serviceAccount:\}"',
        text), (
        "the normalisation does not use bash's ${VAR#prefix} form on "
        "exactly 'serviceAccount:'")


def test_grant_call_consumes_the_normalised_variable():
    """The grant call must read the SAME WRITER_IDENTITY variable the
    normalisation line just reassigned, not a separately-derived or
    stale copy -- otherwise normalising the variable achieves nothing if
    the grant call reads something else. Mutation: introduce a second
    variable (e.g. NORMALISED_WRITER_IDENTITY) for the stripped value and
    leave the grant call reading the original WRITER_IDENTITY -- red
    (grep for a second variable name would need to also update this
    test, but the grant call's own --member argument, pinned below,
    would still show the untouched $WRITER_IDENTITY name either way).
    """
    text = _script_text()
    assert 'serviceAccount:$WRITER_IDENTITY' in text, (
        "the grant call's --member argument does not read "
        "$WRITER_IDENTITY -- normalising a different variable would not "
        "fix the doubled-prefix bug")
def test_sink_uses_partitioned_tables():
    """Mutation: drop --use-partitioned-tables -- red (the views assume
    partition pruning on a month-range filter)."""
    text = _script_text()
    assert "--use-partitioned-tables" in text


def test_writer_identity_gets_dataeditor_on_the_dataset():
    """The sink's own writer identity (printed by `gcloud logging sinks
    create`, parsed at runtime -- not a hardcoded principal) must be granted
    bigquery.dataEditor on the dataset, via scripts/telemetry_bq_setup.py's
    grant-dataset-role subcommand (the BigQuery API's Dataset.access_entries),
    NOT `bq add-iam-policy-binding` (bd polyglot-pdf-vzvio: on at least one
    maintainer machine `bq` itself exits non-zero here) and not `gcloud
    projects add-iam-policy-binding` (project-wide). Mutation: change
    dataEditor to a different role, or move the grant onto `gcloud projects
    add-iam-policy-binding`, or revert to `bq add-iam-policy-binding` -- red.
    """
    text = _script_text()
    assert "roles/bigquery.dataEditor" in text
    # The grant is issued via telemetry_bq_setup.py grant-dataset-role, not
    # `bq add-iam-policy-binding`.
    editor_block_match = re.search(
        r'telemetry_bq_setup\.py" grant-dataset-role \\(?:[^\n]*\n){0,6}?[^\n]*'
        r'--role "roles/bigquery\.dataEditor"',
        text)
    assert editor_block_match, (
        "roles/bigquery.dataEditor is not granted via telemetry_bq_setup.py "
        "grant-dataset-role")
    # `bq add-iam-policy-binding` must not appear anywhere in the script any
    # more -- both dataset-scoped grants moved to the API helper.
    # The old invocation shape (line-start `bq add-iam-policy-binding`, not
    # a backtick-quoted mention inside an explanatory comment) must be gone
    # entirely -- both dataset-scoped grants moved to the API helper.
    invocation_lines = [
        line for line in text.splitlines()
        if line.strip().startswith("bq add-iam-policy-binding")
    ]
    assert not invocation_lines, (
        "scripts/setup-telemetry.sh still INVOKES `bq add-iam-policy-binding` "
        "-- both dataset-scoped BigQuery grants must go through "
        "telemetry_bq_setup.py grant-dataset-role instead (bd "
        "polyglot-pdf-vzvio): {}".format(invocation_lines))
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
    """admin-backend-sa gets roles/bigquery.jobUser (project-level, via
    `gcloud projects add-iam-policy-binding`, unaffected by this bead) and
    roles/bigquery.dataViewer (dataset-scoped, via telemetry_bq_setup.py
    grant-dataset-role, NOT `bq add-iam-policy-binding` -- bd
    polyglot-pdf-vzvio) -- the third and fourth of the bead's four IAM
    grants (writer-identity dataEditor and the two admin-sa roles).
    Mutation: drop either grant, or revert dataViewer to `bq
    add-iam-policy-binding` -- red."""
    text = _script_text()
    assert 'ADMIN_SA_EMAIL="admin-backend-sa@' in text
    assert "roles/bigquery.jobUser" in text
    assert "roles/bigquery.dataViewer" in text
    # jobUser via the project-level command.
    assert re.search(
        r'gcloud projects add-iam-policy-binding "\$PROJECT_ID"[^\n]*\n'
        r'(?:[^\n]*\n){0,4}?\s*--role="roles/bigquery\.jobUser"',
        text), "bigquery.jobUser must be granted project-wide via gcloud projects add-iam-policy-binding"
    # dataViewer via telemetry_bq_setup.py grant-dataset-role, targeting
    # $DATASET.
    dataviewer_block = re.search(
        r'telemetry_bq_setup\.py" grant-dataset-role \\(?:[^\n]*\n){0,6}?[^\n]*'
        r'--role "roles/bigquery\.dataViewer"',
        text)
    assert dataviewer_block, (
        "roles/bigquery.dataViewer must be granted via telemetry_bq_setup.py "
        "grant-dataset-role")
    dataset_arg = re.search(
        r'telemetry_bq_setup\.py" grant-dataset-role \\(?:[^\n]*\n){0,6}?[^\n]*'
        r'--dataset "\$DATASET"(?:[^\n]*\n){0,6}?[^\n]*'
        r'--role "roles/bigquery\.dataViewer"',
        text)
    assert dataset_arg, (
        "the dataViewer grant-dataset-role call does not pass "
        '--dataset "$DATASET" -- it must be scoped to the telemetry '
        "dataset, not the whole project")


def test_all_four_iam_grants_are_present():
    """The bead names exactly four IAM grants in its description: the sink
    writer's dataEditor, and admin-backend-sa's jobUser + dataViewer (three
    role grants across two identities -- the fourth 'grant' in the bead's
    prose count is the sink creation itself, which is not a role binding).
    Enumerated here as a single set-based pin so a future edit that drops
    one is caught by name, not just by the individual tests above drifting
    green for the wrong reason. Roles are granted either via `--role=` on a
    gcloud/bq call or `--role ` on the telemetry_bq_setup.py helper (bd
    polyglot-pdf-vzvio moved the two dataset-scoped grants to the latter)."""
    text = _script_text()
    role_grants = re.findall(r'--role[= ]"(roles/bigquery\.\w+)"', text)
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


def test_script_applies_each_view_independently_of_the_other_table(tmp_path):
    """bd polyglot-pdf-k5w16: the OLD gate skipped EVERY view (all five)
    whenever either sink destination table was missing -- an all-or-nothing
    guard that, per this bead's own live finding, left every cost view
    pending for days after only the stdout table had a row, because the
    stderr table (ledger_export/session events) had not landed one yet.
    The script must instead apply the views that only need
    TELEMETRY_TABLE_STDOUT (cost_by_firm_month, cost_by_kit_month,
    cost_by_employee_month) and the one that only needs
    BILLING_EXPORT_TABLE (hosting_cost_by_service_month) even when
    TELEMETRY_TABLE_STDERR is empty, and vice versa for income_month.
    Mutation: reinstate a single combined `[ -z "$TELEMETRY_TABLE_STDOUT" ]
    || [ -z "$TELEMETRY_TABLE_STDERR" ]` guard that exits before any
    _apply_view call -- red (this test's per-view gating assertions below
    would then find no _apply_view calls reachable when only one table is
    missing)."""
    text = _script_text()
    # No single guard may exit (or skip the whole apply step) on EITHER
    # table alone before per-view gating gets a chance to run -- the only
    # gate this early in the script is the BILLING_EXPORT_TABLE check
    # (unrelated to the two sink tables).
    combined_guard = re.search(
        r'if \[ -z "\$TELEMETRY_TABLE_STDOUT" \] (\|\||&&) '
        r'\[ -z "\$TELEMETRY_TABLE_STDERR" \]', text)
    assert combined_guard is None, (
        "a combined TELEMETRY_TABLE_STDOUT/STDERR guard still exists -- "
        "this bead requires per-view gating instead of an all-or-nothing "
        "exit before any view is applied")
    # Each view name must be routed through _apply_view with the flag for
    # the table it actually depends on (not hard-coded "true"/"false" for
    # the wrong table).
    assert re.search(
        r'_apply_view "cost_by_firm_month"[^\n]*"\$STDOUT_OK"', text)
    assert re.search(
        r'_apply_view "cost_by_kit_month"[^\n]*"\$STDOUT_OK"', text)
    assert re.search(
        r'_apply_view "cost_by_employee_month"[^\n]*"\$STDOUT_OK"', text)
    assert re.search(
        r'_apply_view "income_month"[^\n]*"\$STDERR_OK"', text)
    # hosting_cost_by_service_month depends on BILLING_EXPORT_TABLE only,
    # which is already guaranteed non-empty by the earlier
    # `if [ -z "$BILLING_EXPORT_TABLE" ]; then ... exit 0; fi` gate -- so it
    # must always be attempted (gated "true"), never gated on either sink
    # table's presence.
    assert re.search(
        r'_apply_view "hosting_cost_by_service_month" "[^"]*" "true"', text)
    # STDOUT_OK/STDERR_OK must actually be DERIVED from the discovered
    # table variables, not hard-coded literals.
    assert re.search(
        r'if \[ -n "\$TELEMETRY_TABLE_STDOUT" \]; then\s*\n\s*STDOUT_OK="true"',
        text)
    assert re.search(
        r'if \[ -n "\$TELEMETRY_TABLE_STDERR" \]; then\s*\n\s*STDERR_OK="true"',
        text)


def test_script_exits_0_when_a_view_is_pending_but_reports_it():
    """Exit criterion 2 of bd polyglot-pdf-k5w16: a re-run that creates some
    views and finds others' source table still missing must exit 0 (this is
    a normal, expected state on a fresh project -- not a failure) while
    still telling the operator which views are pending. Mutation: make the
    script `exit 1` whenever PENDING_VIEWS is non-empty -- red (that would
    turn an expected, transient state into a hard failure understood by
    `set -e` callers as broken)."""
    text = _script_text()
    assert "PENDING_VIEWS" in text
    # The PENDING_VIEWS conditional block in the final summary must be
    # EXACTLY an echo -- no exit statement of any kind inside it. Matched
    # precisely (not just "does `exit 0` appear somewhere after this
    # point", which a later, unrelated `exit 0` would satisfy even if this
    # block itself exits early).
    pending_block = re.search(
        r'if \[ -n "\$PENDING_VIEWS" \]; then\n([^\n]*\n)*?fi\n', text)
    assert pending_block, "no 'if [ -n \"$PENDING_VIEWS\" ]; then ... fi' block found"
    assert "exit" not in pending_block.group(0), (
        "the PENDING_VIEWS block contains an exit statement -- a pending "
        "view (missing source table) must not itself trigger any exit; "
        "the block found was: {!r}".format(pending_block.group(0)))
    failed_gate = re.search(
        r'if \[ -n "\$FAILED_VIEWS" \]; then\s*\n[^\n]*\n\s*exit 1', text)
    assert failed_gate, (
        "exit 1 is not gated on FAILED_VIEWS specifically -- a pending "
        "view must not share the same exit path as an actual apply failure"
    )
    assert text.rstrip().endswith("exit 0"), (
        "the script's last statement is not an unconditional `exit 0` -- "
        "a run with only pending (never failed) views must still exit "
        "cleanly")


def test_both_usage_strings_name_the_optional_second_argument():
    """bd polyglot-pdf-un0es: the header comment and the runtime error must
    both tell the operator BILLING_EXPORT_TABLE exists -- an operator who
    only sees `<PROJECT_ID>` has no way to learn the argument that unlocks
    view creation exists at all. Mutation: drop `[BILLING_EXPORT_TABLE]`
    from either string -- red."""
    text = _script_text()
    assert re.search(
        r"# Usage: \./scripts/setup-telemetry\.sh <PROJECT_ID> "
        r"\[BILLING_EXPORT_TABLE\]", text), (
        "the header usage comment does not name the optional second argument")
    assert re.search(
        r'Usage: \$0 <PROJECT_ID> \[BILLING_EXPORT_TABLE\]', text), (
        "the runtime argument-error message does not name the optional "
        "second argument")


def test_billing_export_table_comment_says_optional_not_required():
    """The comment directly above `BILLING_EXPORT_TABLE=$2` must agree with
    the code immediately below it, which skips view creation and exits 0
    when the argument is absent -- that is optional-with-skip, not required.
    Mutation: restore the word 'REQUIRED' -- red."""
    text = _script_text()
    assert "REQUIRED second argument" not in text, (
        "comment still calls BILLING_EXPORT_TABLE a REQUIRED argument, but "
        "the code below treats a missing value as optional (skip + exit 0)")
    assert "OPTIONAL second argument" in text, (
        "comment above BILLING_EXPORT_TABLE=$2 should say OPTIONAL, "
        "matching the skip-on-absence code path"
    )


def test_no_billing_arg_path_does_not_read_as_unqualified_success():
    """When BILLING_EXPORT_TABLE is omitted, the script's LAST printed line
    (before exit 0) must say views were not created -- otherwise an operator
    sees only the final '[INFO] ... setup complete for $PROJECT_ID!' line and
    reasonably concludes the whole script succeeded, missing that zero views
    were ever created. Mutation: revert to the unqualified 'setup complete
    for $PROJECT_ID!' with no views-skipped qualifier -- red."""
    text = _script_text()
    match = re.search(
        r'No BILLING_EXPORT_TABLE argument given -- skipping view creation'
        r'.*?\n(.*?)\n\s*exit 0',
        text, re.DOTALL)
    assert match, "could not locate the no-BILLING_EXPORT_TABLE skip block"
    final_line = match.group(1)
    assert "NO VIEWS CREATED" in final_line or "no views" in final_line.lower(), (
        "the final line printed before exit 0 in the no-billing-arg path "
        "does not say views were NOT created: {!r}".format(final_line)
    )


def test_every_sql_placeholder_has_a_corresponding_sed_substitution():
    """Exit criterion 1: the script substitutes EVERY ${...} placeholder
    sql/telemetry_views.sql actually declares -- enumerated mechanically
    from the SQL file (CLAUDE.md scar #8: enumerate the set, don't hand-list
    it), not a fixed list of the four placeholders known today. A future
    view that introduces a fifth placeholder without a matching sed clause
    would otherwise ship a SQL statement with a literal, unsubstituted
    ${...} string reaching `bq query` -- a guaranteed query failure, but one
    this test catches at review time instead of at the operator's terminal.
    Mutation: remove any one of the sed -e clauses -- red."""
    sql_text = SQL_FILE.read_text(encoding="utf-8")
    declared_placeholders = set(re.findall(r"\$\{[A-Z_]+\}", sql_text))
    assert declared_placeholders, (
        "sql/telemetry_views.sql declares no ${...} placeholders at all -- "
        "this test would pass vacuously; check the SQL file is being read "
        "correctly")

    script_text = _script_text()
    # Every sed clause is `-e "s|\${PLACEHOLDER}|...|g"` -- the script
    # backslash-escapes the leading $ so the shell does not expand it
    # before sed sees it.
    substituted_names = set(
        re.findall(r'-e "s\|\\\$\{([A-Z_]+)\}\|', script_text)
    )
    substituted_placeholders = set(
        "${{{}}}".format(name) for name in substituted_names
    )
    assert substituted_placeholders == declared_placeholders, (
        "the sed pipeline's substituted placeholders {} do not match "
        "sql/telemetry_views.sql's declared placeholders {} -- every "
        "placeholder the SQL file declares must have a matching sed clause, "
        "and the script must not substitute a placeholder the SQL no longer "
        "uses".format(
            sorted(substituted_placeholders), sorted(declared_placeholders)
        )
    )



def test_python_probe_checks_the_real_dependency_not_a_bare_run():
    """bd polyglot-pdf-vzvio cross-surface review round 5: a candidate that
    merely RUNS (`-c pass`) is not enough -- telemetry_bq_setup.py imports
    google-cloud-bigquery, a backend/requirements.txt dependency, not a
    stdlib one. Reproduced directly on the maintainer's machine: `python`
    passes a bare `-c pass` probe but has no google-cloud-bigquery
    installed, so the script aborted with "ModuleNotFoundError: No module
    named 'google'" before the dataset was even created.
    Mutation: revert the probe body back to `-c "pass"` -- red (this test
    fails because the probe would then accept ANY runnable interpreter,
    including one without the library)."""
    text = _script_text()
    assert 'import google.cloud.bigquery' in text, (
        "find_telemetry_python's probe does not check for "
        "google.cloud.bigquery -- a bare `-c pass` accepts any runnable "
        "interpreter, including one missing the dependency the script "
        "actually needs")
    assert '-c "pass"' not in text, (
        "the old bare `-c \"pass\"` probe is still present -- it must be "
        "replaced by the dependency-checking probe, not left alongside it")


def test_python_candidates_try_backend_venv_before_bare_python():
    """bd polyglot-pdf-vzvio cross-surface review round 5: the repo's other
    operator script with a real backend/.venv dependency
    (scripts/audit/infra_posture.sh) puts its venv candidates FIRST, ahead
    of bare python3/python/py, precisely because a bare `python` on the
    operator's PATH commonly lacks the library that lives only in the venv.
    Mutation: reorder the default candidate list so a bare python3/python/py
    comes before the backend/.venv candidates -- red (this regex requires
    the venv candidates to appear first in the default list)."""
    text = _script_text()
    match = re.search(
        r'for cand in \$\{TELEMETRY_PYTHON_CANDIDATES:-(.*?)\}; do',
        text,
    )
    assert match, "find_telemetry_python's default candidate list is missing"
    defaults = match.group(1)
    venv_pos = defaults.find("backend/.venv")
    bare_python_pos = defaults.find("python3 python py")
    assert venv_pos != -1, "no backend/.venv candidate in the default list"
    assert bare_python_pos != -1, (
        "no bare 'python3 python py' fallback tail in the default list")
    assert venv_pos < bare_python_pos, (
        "backend/.venv candidates must come BEFORE the bare python3/python/"
        "py fallbacks in the default candidate list, matching "
        "infra_posture.sh's _python_candidates ordering")


def test_python_candidates_support_an_explicit_override():
    """An operator (or CI) must be able to point at a known-good
    interpreter without editing the script, matching infra_posture.sh's
    INFRA_POSTURE_PYTHON override. Mutation: remove
    TELEMETRY_PYTHON_OVERRIDE from the default-candidate expression -- red."""
    text = _script_text()
    assert "TELEMETRY_PYTHON_OVERRIDE" in text, (
        "no TELEMETRY_PYTHON_OVERRIDE escape hatch for an operator to pin "
        "a known-good interpreter")


def test_repo_root_is_computed_before_the_python_probe_runs():
    """REPO_ROOT (used to build the backend/.venv candidate paths) must be
    computed BEFORE find_telemetry_python is invoked, not after -- an
    empty/undefined REPO_ROOT at call time would silently produce a bare
    "backend/.venv/..." candidate relative to the shell's cwd instead of the
    repo root. Mutation: move the REPO_ROOT assignment to after the
    `if ! PYTHON_BIN=$(find_telemetry_python)` call -- red."""
    text = _script_text()
    repo_root_pos = text.find('REPO_ROOT="$(cd "$SCRIPT_DIR/.."')
    probe_call_pos = text.find("if ! PYTHON_BIN=$(find_telemetry_python)")
    assert repo_root_pos != -1, "REPO_ROOT is not computed in the script"
    assert probe_call_pos != -1, "find_telemetry_python is never invoked"
    assert repo_root_pos < probe_call_pos, (
        "REPO_ROOT must be assigned before find_telemetry_python is called")
