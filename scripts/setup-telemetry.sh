#!/bin/bash
# setup-telemetry.sh - Provision the BigQuery telemetry sink + cost/income views.
#
# Sibling of scripts/setup-gcp-project.sh (public backend SA) and
# scripts/setup-admin-service.sh (admin SA). Epic 3 bead 6 (E3.6), plan:
# docs/sprint_22_admin-console_plan.md "BigQuery". DECLARATIVE and
# OPERATOR-RUN: nothing here runs from a deploy script, and this bead does
# NOT execute anything against GCP itself -- an operator runs this by hand,
# under their own gcloud credentials, when the project is first provisioned
# or the telemetry surface changes.
#
# WHY A SEPARATE SCRIPT FROM setup-admin-service.sh. The BigQuery grants on
# admin-backend-sa (below) are the SAME identity that script provisions, but
# this script also creates the dataset, the Cloud Logging sink (a
# project-wide resource that is NOT scoped to any one service account), and
# the sink's OWN writer identity's grant -- none of which belongs on the SA
# provisioning script. Keeping telemetry infra in its own script also means
# an operator can re-run it alone when only the sink filter or a view
# definition changes, without touching IAM for the admin service itself.
#
# THE SINK FILTER MATCHES THREE DIFFERENT LOG SHAPES, NOT ONE. The plan and
# this bead's own description say "filtered to jsonPayload.event_type in the
# usage / session / ledger_export / error set" as if one field name covers
# every emitter. It does not, and the filter below is written against what
# each emitter ACTUALLY produces (verified against real emitted JSON, not
# reconstructed from memory):
#
#   1. USAGE events (gemini_api_response, text_ai_usage, tts_usage) go
#      through backend/utils/structured_logger.py's StructuredLogger._emit,
#      which wraps the whole envelope in a `message` key before printing
#      (see that module's own docstring: "message": { "event_type": ...
#      }). So a usage row's event type is at
#      jsonPayload.message.event_type, one level down from the top.
#   2. LEDGER_EXPORT lines go through backend/services/credit_ledger.py's
#      plain structlog call, which passes event_type as an explicit bound
#      key: `_log.info(LEDGER_EXPORT_EVENT, event_type=LEDGER_EXPORT_EVENT,
#      ...)`. structlog's JSONRenderer (backend/utils/logging.py) places
#      every bound key at the TOP level of the line with no wrapper, so this
#      one really is jsonPayload.event_type.
#   3. SESSION events (form_session_started / form_session_ended) go through
#      backend/utils/confirmation_logger.py's plain structlog calls, e.g.
#      `_log.info("form_session_started", **fields)` -- note NO event_type
#      kwarg is passed. structlog's JSONRenderer renders the POSITIONAL
#      event name under the key "event" (not "event_type") when no
#      explicit event_type is bound. So these land at jsonPayload.event,
#      not jsonPayload.event_type at all today.
#
# A filter written as a single `jsonPayload.event_type IN (...)` clause
# would therefore silently DROP every session row (wrong key entirely) and
# every usage row (wrong nesting depth) while only matching ledger_export --
# exactly the kind of gap that looks fine until someone tries to query a
# session count from BigQuery and gets zero rows with no error. The filter
# below is an OR across the three actual shapes instead. ERROR events (the
# fourth member of the plan's set) are deliberately NOT filtered on below:
# Epic 3 bead 8 (setup-monitoring.sh, a separate bead) is what first WIRES
# StructuredLogger.log_error to a real call site; until it does, no error
# event_type value was ever emitted. That bead has now LANDED, and the
# prediction held: StructuredLogger.log_ws_close routes through the SAME
# StructuredLogger._emit as the usage events, so its ws_error rows carry the
# same nested jsonPayload.message.event_type shape and widening this filter
# was the predicted one-word addition to the existing message.event_type
# clause rather than a fourth shape to reason about.
#
# ONLY ws_error is added, not every error_* EventType. The other five
# (error_validation, error_network, error_ai, error_tool, error_timeout) are
# still declared-but-unemitted in backend/utils/log_schemas.py; naming them
# here would be guessing at rows nothing writes, and the clause can be
# widened by one word each when they acquire a real call site.
#
# Pinned by tests/test_setup_telemetry_script.py, which reads this script's
# actual shipped text (gcloud is never invoked in CI).
#
# Usage: ./scripts/setup-telemetry.sh <PROJECT_ID> [BILLING_EXPORT_TABLE]
#   BILLING_EXPORT_TABLE is optional but not cosmetic: omitting it skips
#   creating every one of the script's cost-reporting views (see the
#   BILLING_EXPORT_TABLE block below), so most of what this script exists to
#   set up silently does not happen without it.
#
# Idempotent throughout, including the sink step (bd polyglot-pdf-f7f0h):
# `gcloud logging sinks describe` decides whether to `sinks create` (sink
# does not exist yet) or `sinks update` (it does), so a re-run after
# SINK_FILTER changes -- e.g. Epic 3 bead 8 adding the error-event clause --
# actually applies the new filter to the live sink, rather than failing
# silently on a create-only call that leaves the deployed filter stale.

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ID=$1
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}[ERROR]${NC} Usage: $0 <PROJECT_ID> [BILLING_EXPORT_TABLE]"
    exit 1
fi

# BILLING_EXPORT_TABLE is read HERE, before the dataset is created, not down
# at the view-application step -- LOCATION derivation (below) needs it, and a
# BigQuery dataset's location is fixed at creation time, so this cannot be
# deferred to where the script used to first look at this argument.
BILLING_EXPORT_TABLE=$2

DATASET="polyglot_telemetry"
SINK_NAME="polyglot-telemetry-sink"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Resolve a python interpreter for scripts/telemetry_bq_setup.py (location
# derivation + the dataset-scoped IAM grants below). That script imports
# google-cloud-bigquery, a backend/requirements.txt dependency, NOT a
# stdlib one -- a candidate that merely RUNS (-c pass) is not enough, since
# the library is installed only inside backend/.venv on a normal checkout.
# Reproduced directly on the maintainer's machine (bd polyglot-pdf-vzvio,
# cross-surface review round 5): `python` passes a bare `-c pass` probe but
# has no google-cloud-bigquery installed, so telemetry_bq_setup.py aborted
# with "ModuleNotFoundError: No module named 'google'" -- BEFORE the
# dataset, sink, or grants were even created, i.e. strictly earlier and
# broader than the bug this bead was filed to fix.
#
# Mirrors scripts/audit/infra_posture.sh's _python_candidates -- the
# repo's other operator script with a real dependency on backend/.venv --
# which puts an explicit override and the venv candidates FIRST, ahead of
# bare python3/python/py: an operator running this from a plain shell,
# without having activated the venv, still gets a working interpreter. A
# worktree (which has no backend/.venv of its own -- CLAUDE.md scar #3)
# just falls through those candidates to the bare ones, same as
# infra_posture.sh.
#
# The probe checks `import google.cloud.bigquery`, not just `-c pass`, so
# a python that merely runs but lacks the dependency is correctly skipped
# instead of being selected and failing deeper into the script.
find_telemetry_python() {
    local cand
    for cand in ${TELEMETRY_PYTHON_CANDIDATES:-${TELEMETRY_PYTHON_OVERRIDE:-} "$REPO_ROOT/backend/.venv/Scripts/python.exe" "$REPO_ROOT/backend/.venv/bin/python" backend/.venv/Scripts/python.exe backend/.venv/bin/python python3 python py}; do
        [ -z "$cand" ] && continue
        if "$cand" -c "import google.cloud.bigquery" >/dev/null 2>&1; then
            echo "$cand"
            return 0
        fi
    done
    return 1
}

if ! PYTHON_BIN=$(find_telemetry_python); then
    echo -e "${RED}[ERROR]${NC} No python interpreter with google-cloud-bigquery installed found (tried: TELEMETRY_PYTHON_OVERRIDE, ${REPO_ROOT}/backend/.venv/{Scripts,bin}/python{.exe,}, backend/.venv/{Scripts,bin}/python{.exe,}, python3, python, py) -- cannot run scripts/telemetry_bq_setup.py; aborting. Activate backend/.venv first, or set TELEMETRY_PYTHON_OVERRIDE=<path> to an interpreter with google-cloud-bigquery installed."
    exit 1
fi

# LOCATION: derived from the billing dataset when BILLING_EXPORT_TABLE is
# given (bd polyglot-pdf-vzvio) -- BigQuery refuses to create a view
# (hosting_cost_by_service_month) that reads a table in a DIFFERENT location
# than its own dataset, so hard-coding us-central1 here silently breaks that
# view the moment the maintainer's Cloud Billing export dataset happens to
# live in the US multi-region (or any other location) instead. Falls back to
# us-central1 only when no BILLING_EXPORT_TABLE is given at all -- there is
# nothing to match locations against yet, and the dataset/sink/IAM setup
# below still needs SOME location to create the dataset in on a first run.
# scripts/telemetry_bq_setup.py resolve-location refuses (non-zero, message
# on stderr, caught by `set -e`) if the telemetry dataset already exists,
# already holds tables, AND its location differs from the billing dataset's
# -- BigQuery cannot move a populated dataset between locations, so this
# script must not paper over that with a location it cannot actually apply.
if [ -n "$BILLING_EXPORT_TABLE" ]; then
    echo -e "${GREEN}[INFO]${NC} Deriving telemetry dataset location from billing table $BILLING_EXPORT_TABLE..."
    if ! LOCATION=$("$PYTHON_BIN" "$SCRIPT_DIR/telemetry_bq_setup.py" resolve-location \
        --project "$PROJECT_ID" --dataset "$DATASET" \
        --billing-table "$BILLING_EXPORT_TABLE"); then
        exit 1
    fi
    echo -e "${GREEN}[INFO]${NC} Using location $LOCATION (from the billing dataset)."
else
    LOCATION="us-central1"
    echo -e "${YELLOW}[NOTE]${NC} No BILLING_EXPORT_TABLE given -- defaulting the telemetry dataset location to $LOCATION. Pass BILLING_EXPORT_TABLE to derive the location from the billing dataset instead."
fi

echo -e "${GREEN}[INFO]${NC} Setting up telemetry (BigQuery) for project: $PROJECT_ID"

# 1. Enable the BigQuery API.
echo -e "${GREEN}[INFO]${NC} Enabling bigquery.googleapis.com..."
gcloud services enable \
    bigquery.googleapis.com \
    --project "$PROJECT_ID"

# 2. Create the dataset, if it does not already exist.
if bq show --project_id="$PROJECT_ID" "$DATASET" &>/dev/null; then
    echo -e "${GREEN}[INFO]${NC} Dataset $DATASET already exists"
else
    echo -e "${GREEN}[INFO]${NC} Creating dataset $DATASET in $LOCATION..."
    bq mk \
        --project_id="$PROJECT_ID" \
        --location="$LOCATION" \
        --dataset \
        "$DATASET"
fi

# 3. Create the Cloud Logging -> BigQuery sink, over THREE Cloud Run
#    services (the public backend's demo/production service, its staging
#    twin, AND the admin service), with partitioned destination tables. See
#    the module docstring above for why the filter ORs across three
#    different jsonPayload shapes instead of checking one field.
#
# resource.type="cloud_run_revision" scopes the sink to Cloud Run logs only
# (excluding, e.g., Cloud Build or Cloud Scheduler noise landing in the same
# project). resource.labels.service_name narrows to the three services that
# actually emit a filtered event_type today -- "polyglot-backend" and
# "polyglot-backend-staging" (usage + session events) AND "polyglot-admin"
# (ledger_export). ledger_export is NOT emitted by the public backend: its
# only non-test callers, credit_ledger.append_entry() and
# refund_expired_link(), are called exclusively from
# admin_backend/routes/credit_routes.py and admin_backend/routes/
# sweep_routes.py, both of which run on the admin service
# (deploy-admin.sh's ADMIN_SERVICE_NAME, "polyglot-admin"; the public
# backend's websocket_routes.py explicitly never calls
# refund_expired_link()). Omitting "polyglot-admin" here would make
# income_month return zero rows forever with no error -- the sink would
# simply never see a ledger_export line to match. Any future service beyond
# these three is deliberately excluded until it needs telemetry of its own.
#
# --use-partitioned-tables: partitioned by the LogEntry's own timestamp, so
# a month-range query in the views above prunes partitions instead of
# scanning the whole sink history.
#
# CREATE-OR-UPDATE, NOT CREATE-ONLY (bd polyglot-pdf-f7f0h). `gcloud logging
# sinks create` fails on a sink that already exists, so a bare create-only
# call cannot be how a re-run applies a changed SINK_FILTER (e.g. Epic 3
# bead 8 adding the error-event clause to the OR above, per this script's
# own module docstring) -- create-only would leave the LIVE sink on its
# original filter forever while gcloud printed a swallowed error and the
# script exited 0. `gcloud logging sinks describe` decides which of
# `sinks create` / `sinks update` to run: describe (unlike create) is safe
# to call on a sink that does not exist yet (it just fails, which is
# exactly the signal needed), and on a sink that DOES exist its output
# carries writerIdentity -- the same field `sinks create` prints on first
# creation -- so step 4 below can grant the writer identity
# bigquery.dataEditor on either path, not just the create one.
echo -e "${GREEN}[INFO]${NC} Checking whether Cloud Logging sink $SINK_NAME already exists..."
SINK_FILTER='resource.type="cloud_run_revision" AND resource.labels.service_name=("polyglot-backend" OR "polyglot-backend-staging" OR "polyglot-admin") AND (jsonPayload.event_type="ledger_export" OR jsonPayload.message.event_type=("gemini_api_response" OR "text_ai_usage" OR "tts_usage" OR "ws_error") OR jsonPayload.event=("form_session_started" OR "form_session_ended"))'

if gcloud logging sinks describe "$SINK_NAME" --project="$PROJECT_ID" &>/dev/null; then
    echo -e "${GREEN}[INFO]${NC} Sink $SINK_NAME already exists -- updating its filter..."
    SINK_CREATE_OUTPUT=$(gcloud logging sinks update "$SINK_NAME" \
        --project="$PROJECT_ID" \
        --log-filter="$SINK_FILTER" \
        2>&1) || {
        echo -e "${RED}[ERROR]${NC} sink update failed -- see output below."
        echo "$SINK_CREATE_OUTPUT"
        exit 1
    }
    echo "$SINK_CREATE_OUTPUT"
    WRITER_IDENTITY=$(gcloud logging sinks describe "$SINK_NAME" \
        --project="$PROJECT_ID" --format="value(writerIdentity)" 2>/dev/null)
else
    echo -e "${GREEN}[INFO]${NC} Creating Cloud Logging sink $SINK_NAME..."
    SINK_CREATE_OUTPUT=$(gcloud logging sinks create "$SINK_NAME" \
        "bigquery.googleapis.com/projects/$PROJECT_ID/datasets/$DATASET" \
        --project="$PROJECT_ID" \
        --log-filter="$SINK_FILTER" \
        --use-partitioned-tables \
        2>&1) || {
        echo -e "${RED}[ERROR]${NC} sink create failed -- see output below."
        echo "$SINK_CREATE_OUTPUT"
        exit 1
    }
    echo "$SINK_CREATE_OUTPUT"
    WRITER_IDENTITY=$(echo "$SINK_CREATE_OUTPUT" | grep -oE '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.iam\.gserviceaccount\.com' | head -1)
fi

# NORMALISE WRITER_IDENTITY TO A BARE EMAIL (bd polyglot-pdf-k5w16). The two
# branches above hand back DIFFERENT shapes for the same variable: the
# re-run (update) branch reads `gcloud logging sinks describe
# --format=value(writerIdentity)`, which already returns the
# "serviceAccount:service-..." PREFIXED form, while the first-run (create)
# branch greps the bare email straight out of `gcloud logging sinks
# create`'s own output, with no prefix at all. The grant call below has
# always assumed the bare-email shape (it does `serviceAccount:$WRITER_IDENTITY`
# itself), which is correct for the create branch but DOUBLES the prefix on
# the update/re-run branch -- exactly the failure this bead was filed for
# (observed live on the first setup-telemetry.sh run after the sink already
# existed: "could not grant roles/bigquery.dataEditor ... to
# serviceAccount:serviceAccount:service-...", and the view-creation steps
# after it never ran because of `set -e`). Strip a leading `serviceAccount:`
# here, once, so every consumer below sees the same bare-email shape
# regardless of which branch set it.
WRITER_IDENTITY="${WRITER_IDENTITY#serviceAccount:}"

# 4. Grant the sink's own writer identity roles/bigquery.dataEditor on the
#    dataset. The block above resolves this identity on BOTH the create and
#    the update path (a project-scoped service agent the sink itself
#    provisions, NOT admin-backend-sa or polyglot-backend-sa) -- without
#    this grant every row the sink tries to write 403s silently and the
#    dataset stays empty while the sink itself reports healthy (the same
#    "mock cannot tell you the real dependency is forbidden" trap as
#    CLAUDE.md scar #7, just on the WRITE side instead of a read).
#
# Granted via scripts/telemetry_bq_setup.py (the BigQuery API's
# Dataset.access_entries), NOT `bq add-iam-policy-binding` (bd
# polyglot-pdf-vzvio) -- on at least one maintainer machine `bq` itself
# exits non-zero here because its shim needs CLOUDSDK_PYTHON pointed at an
# installed Python, which aborted this script (via `set -e`) before the
# views below were ever applied. See that script's own module docstring for
# why the API path is equivalent, not merely a workaround.
if [ -n "$WRITER_IDENTITY" ]; then
    echo -e "${GREEN}[INFO]${NC} Granting bigquery.dataEditor on $DATASET to sink writer $WRITER_IDENTITY..."
    "$PYTHON_BIN" "$SCRIPT_DIR/telemetry_bq_setup.py" grant-dataset-role \
        --project "$PROJECT_ID" \
        --dataset "$DATASET" \
        --member "serviceAccount:$WRITER_IDENTITY" \
        --role "roles/bigquery.dataEditor"
else
    echo -e "${YELLOW}[NOTE]${NC} Could not resolve the sink's writer identity."
    echo -e "${YELLOW}[NOTE]${NC} Run 'gcloud logging sinks describe $SINK_NAME --project=$PROJECT_ID'"
    echo -e "${YELLOW}[NOTE]${NC} and grant roles/bigquery.dataEditor on $DATASET to its writerIdentity by hand:"
    echo -e "${YELLOW}[NOTE]${NC}   python scripts/telemetry_bq_setup.py grant-dataset-role --project $PROJECT_ID \\"
    echo -e "${YELLOW}[NOTE]${NC}     --dataset $DATASET --member serviceAccount:<writerIdentity> --role roles/bigquery.dataEditor"
fi

# 5. Grant admin-backend-sa the two BigQuery roles Epic 1's
#    setup-admin-service.sh deliberately DEFERRED to this bead
#    (admin_backend/tests/unit/test_admin_sa_iam_envelope.py's
#    DEFERRED_ROLES set -- update alongside this script, same commit).
#    jobUser lets the admin console RUN queries against the views above;
#    dataViewer is scoped to the dataset only, not project-wide, so a
#    compromised admin-backend-sa credential cannot read an unrelated
#    dataset in the same project.
ADMIN_SA_EMAIL="admin-backend-sa@$PROJECT_ID.iam.gserviceaccount.com"

echo -e "${GREEN}[INFO]${NC} Granting roles/bigquery.jobUser (project-level) to $ADMIN_SA_EMAIL..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$ADMIN_SA_EMAIL" \
    --role="roles/bigquery.jobUser" \
    --condition=None > /dev/null

echo -e "${GREEN}[INFO]${NC} Granting roles/bigquery.dataViewer (dataset-scoped) to $ADMIN_SA_EMAIL on $DATASET..."
# Via scripts/telemetry_bq_setup.py, not `bq add-iam-policy-binding` --
# same reason as the sink-writer dataEditor grant above (bd polyglot-pdf-vzvio).
"$PYTHON_BIN" "$SCRIPT_DIR/telemetry_bq_setup.py" grant-dataset-role \
    --project "$PROJECT_ID" \
    --dataset "$DATASET" \
    --member "serviceAccount:$ADMIN_SA_EMAIL" \
    --role "roles/bigquery.dataViewer"

# 6. Apply the view definitions (sql/telemetry_views.sql), substituting the
#    dataset, the sink's TWO destination tables, and the Cloud Billing
#    export table into the SQL's ${...} placeholders.
#
# TELEMETRY_TABLE_STDOUT / TELEMETRY_TABLE_STDERR: the sink writes to TWO
# destination tables, not one (bd polyglot-pdf-ih428) -- a Cloud Logging ->
# BigQuery sink names its destination table per LOG ID, and this sink's
# filter matches both the `run.googleapis.com/stdout` stream (usage events,
# printed directly by backend/utils/structured_logger.py) and the
# `run.googleapis.com/stderr` stream (ledger_export and the session events,
# which reach stdlib logging's default stream via
# backend/utils/logging.py's configure_logging() -- see that function and
# sql/telemetry_views.sql's header for the full split). Neither name is
# hand-picked here: both are read back from the dataset via
# telemetry_bq_setup.py list-tables (bd polyglot-pdf-vm2fu), NOT `bq ls`
# (NOT `gcloud logging sinks describe` either, which reports the sink's own
# config, not its destination tables). `bq ls ... 2>/dev/null | tail -n +2`
# was the ORIGINAL mechanism here, and it has a real bug: it swallows stderr
# and treats an EMPTY listing as "no tables yet", so a `bq` CLI that fails
# to list at all (a broken shim needing CLOUDSDK_PYTHON, a transient DNS
# blip) reads back identically to a genuinely empty, not-yet-written
# dataset -- live-observed reporting every cost view PENDING while the
# stdout table was confirmed present via the SAME google-cloud-bigquery
# client this script already requires for LOCATION derivation and the IAM
# grants above. `telemetry_bq_setup.py list-tables` exits non-zero with a
# message on any real API error instead, which `set -e` below turns into an
# immediate abort -- an operator seeing a clear ERROR, not a script that
# quietly proceeds believing the dataset is empty. Either or both tables may
# genuinely not exist yet on a freshly created sink (a real empty dataset,
# confirmed by a SUCCESSFUL list-tables call) -- if EITHER is missing, the
# operator is told to re-run this step once the sink has produced a row of
# the corresponding kind, since running with only one of the two present
# would leave the other stream's views permanently empty and silently so.
#
# BILLING_EXPORT_TABLE: the detailed Cloud Billing export table. Enabling
# that export is a MAINTAINER console step (plan: Epic 3 bead 7, NOT this
# bead) and requires knowing the destination project/dataset chosen there,
# so it is an OPTIONAL second argument rather than guessed -- omitting it
# skips view creation below (this script's sink/dataset/IAM setup still runs
# either way). Already read into $BILLING_EXPORT_TABLE near the top of this
# script (LOCATION derivation needs it before the dataset is even created).
if [ -z "$BILLING_EXPORT_TABLE" ]; then
    echo -e "${YELLOW}[NOTE]${NC} No BILLING_EXPORT_TABLE argument given -- skipping view creation."
    echo -e "${YELLOW}[NOTE]${NC} Re-run once the Cloud Billing export is enabled (Epic 3 bead 7):"
    echo -e "${YELLOW}[NOTE]${NC}   ./scripts/setup-telemetry.sh $PROJECT_ID <BILLING_PROJECT.BILLING_DATASET.gcp_billing_export_resource_v1_XXXXXX>"
    echo -e "${GREEN}[INFO]${NC} Telemetry sink + dataset + IAM setup complete for $PROJECT_ID -- NO VIEWS CREATED (no BILLING_EXPORT_TABLE given)."
    exit 0
fi

# list-tables aborts (exit 1, message on stderr) on a real API error --
# `set -e` turns that straight into a script abort here, rather than the
# old `bq ls ... 2>/dev/null` pipeline's silent "empty listing" ambiguity
# between "no tables yet" and "bq itself could not list".
if ! TELEMETRY_TABLES=$("$PYTHON_BIN" "$SCRIPT_DIR/telemetry_bq_setup.py" list-tables \
    --project "$PROJECT_ID" --dataset "$DATASET"); then
    echo -e "${RED}[ERROR]${NC} could not list tables in $DATASET -- see message above. Aborting rather than reporting every view PENDING against an unknown table state."
    exit 1
fi

TELEMETRY_TABLE_STDOUT=$(echo "$TELEMETRY_TABLES" | grep -i "stdout" | head -1)
TELEMETRY_TABLE_STDERR=$(echo "$TELEMETRY_TABLES" | grep -i "stderr" | head -1)

if [ -z "$TELEMETRY_TABLE_STDOUT" ]; then
    echo -e "${YELLOW}[NOTE]${NC} stdout table (usage events) does not exist yet under $DATASET -- the"
    echo -e "${YELLOW}[NOTE]${NC} sink has not written a first usage row. cost_by_firm_month,"
    echo -e "${YELLOW}[NOTE]${NC} cost_by_kit_month, and cost_by_employee_month are PENDING; re-run this"
    echo -e "${YELLOW}[NOTE]${NC} script after the next deploy generates at least one usage event."
fi
if [ -z "$TELEMETRY_TABLE_STDERR" ]; then
    echo -e "${YELLOW}[NOTE]${NC} stderr table (ledger_export/session events) does not exist yet under"
    echo -e "${YELLOW}[NOTE]${NC} $DATASET -- the sink has not written a first row of that kind."
    echo -e "${YELLOW}[NOTE]${NC} income_month is PENDING; re-run this script after the next mint or"
    echo -e "${YELLOW}[NOTE]${NC} session-end event."
fi

# APPLY EACH VIEW WHOSE SOURCE TABLE ALREADY EXISTS, REPORT THE REST AS
# PENDING, EXIT 0 (bd polyglot-pdf-k5w16). CREATE VIEW requires its
# referenced table to exist (see sql/telemetry_views.sql's own corrected
# header comment -- an earlier version of this script and that file both
# claimed BigQuery views are late-bound at CREATE time, which is false and
# was observed live: applying income_month before the stderr table existed
# failed with "404 Not found: Table ...run_googleapis_com_stderr"). The
# five views split into three source-table groups -- cost_by_firm_month,
# cost_by_kit_month, and cost_by_employee_month need TELEMETRY_TABLE_STDOUT;
# income_month needs TELEMETRY_TABLE_STDERR; hosting_cost_by_service_month
# needs only BILLING_EXPORT_TABLE (already guaranteed non-empty by the
# check above this block) -- so applying them ONE AT A TIME, gated on the
# table each one actually reads, lets a project with only one sink stream
# populated still get every view that stream can support, instead of the
# previous all-or-nothing gate leaving every view pending until BOTH
# streams existed.
#
# Each view's SQL is extracted from sql/telemetry_views.sql by slicing from
# its own `CREATE OR REPLACE VIEW` line up to the next one (or end of file)
# -- the same shape backend/tests/unit/test_telemetry_views.py's own
# `_view_body` helper matches views by, so a view renamed or reordered
# there is still found here without this script needing its own hand-kept
# list of line ranges.
_extract_view() {
    # $1 = view name (e.g. cost_by_firm_month). Matches the literal
    # `${DATASET}.<view_name>` marker text (via awk's index(), not a
    # constructed regex -- a dynamic regex built from a shell variable that
    # itself contains awk metacharacters like `$` is exactly the kind of
    # thing that silently fails to match instead of erroring, which a
    # literal substring search avoids).
    local marker="\`\${DATASET}.$1\`"
    awk -v marker="$marker" '
        BEGIN { capture = 0 }
        /^CREATE OR REPLACE VIEW/ {
            if (capture) exit
            if (index($0, marker) > 0) capture = 1
        }
        capture { print }
    ' "$SCRIPT_DIR/../sql/telemetry_views.sql"
}

CREATED_VIEWS=""
PENDING_VIEWS=""
FAILED_VIEWS=""

_apply_view() {
    # $1 = view name, $2 = human-readable reason to skip if table_ok=false,
    # $3 = "true"/"false" whether this view's source table exists.
    local view_name="$1"
    local skip_reason="$2"
    local table_ok="$3"
    if [ "$table_ok" != "true" ]; then
        echo -e "${YELLOW}[NOTE]${NC} Skipping $view_name -- $skip_reason"
        PENDING_VIEWS="$PENDING_VIEWS $view_name"
        return 0
    fi
    echo -e "${GREEN}[INFO]${NC} Applying $view_name..."
    if _extract_view "$view_name" \
        | sed \
            -e "s|\${DATASET}|$PROJECT_ID.$DATASET|g" \
            -e "s|\${TELEMETRY_TABLE_STDOUT}|$PROJECT_ID.$DATASET.$TELEMETRY_TABLE_STDOUT|g" \
            -e "s|\${TELEMETRY_TABLE_STDERR}|$PROJECT_ID.$DATASET.$TELEMETRY_TABLE_STDERR|g" \
            -e "s|\${BILLING_EXPORT_TABLE}|$BILLING_EXPORT_TABLE|g" \
        | bq query --project_id="$PROJECT_ID" --use_legacy_sql=false; then
        CREATED_VIEWS="$CREATED_VIEWS $view_name"
    else
        echo -e "${RED}[ERROR]${NC} $view_name failed to apply -- see bq output above."
        FAILED_VIEWS="$FAILED_VIEWS $view_name"
    fi
}

if [ -n "$TELEMETRY_TABLE_STDOUT" ]; then
    STDOUT_OK="true"
else
    STDOUT_OK="false"
fi
if [ -n "$TELEMETRY_TABLE_STDERR" ]; then
    STDERR_OK="true"
else
    STDERR_OK="false"
fi

_apply_view "cost_by_firm_month" "stdout table not found yet" "$STDOUT_OK"
_apply_view "cost_by_kit_month" "stdout table not found yet" "$STDOUT_OK"
_apply_view "cost_by_employee_month" "stdout table not found yet" "$STDOUT_OK"
_apply_view "hosting_cost_by_service_month" "BILLING_EXPORT_TABLE not given" "true"
_apply_view "income_month" "stderr table not found yet" "$STDERR_OK"

echo -e "${GREEN}[INFO]${NC} Telemetry setup complete for $PROJECT_ID."
if [ -n "$CREATED_VIEWS" ]; then
    echo -e "${GREEN}[INFO]${NC} Views created/updated:$CREATED_VIEWS"
fi
if [ -n "$PENDING_VIEWS" ]; then
    echo -e "${YELLOW}[NOTE]${NC} Views pending (source table not ready yet):$PENDING_VIEWS"
fi
if [ -n "$FAILED_VIEWS" ]; then
    echo -e "${RED}[ERROR]${NC} Views that failed to apply:$FAILED_VIEWS"
    exit 1
fi
exit 0
