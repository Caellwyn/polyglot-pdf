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
# event_type value is ever emitted, and pre-filtering for one now would be
# guessing at a shape that bead has not built yet. When it lands, log_error
# routes through the SAME StructuredLogger._emit as the usage events (same
# nested jsonPayload.message.event_type shape), so widening this filter at
# that point is a one-line addition to the existing message.event_type
# clause, not a new shape to reason about.
#
# Pinned by tests/test_setup_telemetry_script.py, which reads this script's
# actual shipped text (gcloud is never invoked in CI).
#
# Usage: ./scripts/setup-telemetry.sh <PROJECT_ID>
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
    echo -e "${RED}[ERROR]${NC} Usage: $0 <PROJECT_ID>"
    exit 1
fi

DATASET="polyglot_telemetry"
LOCATION="us-central1"
SINK_NAME="polyglot-telemetry-sink"

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
SINK_FILTER='resource.type="cloud_run_revision" AND resource.labels.service_name=("polyglot-backend" OR "polyglot-backend-staging" OR "polyglot-admin") AND (jsonPayload.event_type="ledger_export" OR jsonPayload.message.event_type=("gemini_api_response" OR "text_ai_usage" OR "tts_usage") OR jsonPayload.event=("form_session_started" OR "form_session_ended"))'

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

# 4. Grant the sink's own writer identity roles/bigquery.dataEditor on the
#    dataset. The block above resolves this identity on BOTH the create and
#    the update path (a project-scoped service agent the sink itself
#    provisions, NOT admin-backend-sa or polyglot-backend-sa) -- without
#    this grant every row the sink tries to write 403s silently and the
#    dataset stays empty while the sink itself reports healthy (the same
#    "mock cannot tell you the real dependency is forbidden" trap as
#    CLAUDE.md scar #7, just on the WRITE side instead of a read).
if [ -n "$WRITER_IDENTITY" ]; then
    echo -e "${GREEN}[INFO]${NC} Granting bigquery.dataEditor on $DATASET to sink writer $WRITER_IDENTITY..."
    bq add-iam-policy-binding \
        --project_id="$PROJECT_ID" \
        --member="serviceAccount:$WRITER_IDENTITY" \
        --role="roles/bigquery.dataEditor" \
        "$DATASET" > /dev/null
else
    echo -e "${YELLOW}[NOTE]${NC} Could not resolve the sink's writer identity."
    echo -e "${YELLOW}[NOTE]${NC} Run 'gcloud logging sinks describe $SINK_NAME --project=$PROJECT_ID'"
    echo -e "${YELLOW}[NOTE]${NC} and grant roles/bigquery.dataEditor on $DATASET to its writerIdentity by hand:"
    echo -e "${YELLOW}[NOTE]${NC}   bq add-iam-policy-binding --project_id=$PROJECT_ID \\"
    echo -e "${YELLOW}[NOTE]${NC}     --member=serviceAccount:<writerIdentity> --role=roles/bigquery.dataEditor $DATASET"
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
bq add-iam-policy-binding \
    --project_id="$PROJECT_ID" \
    --member="serviceAccount:$ADMIN_SA_EMAIL" \
    --role="roles/bigquery.dataViewer" \
    "$DATASET" > /dev/null

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
# hand-picked here: both are read back from the dataset with `bq ls`
# (NOT `gcloud logging sinks describe`, which reports the sink's own config,
# not its destination tables). Either or both may not exist yet on a
# freshly created sink (BigQuery views are late-bound, so applying a view
# against a not-yet-existent table is fine) -- if EITHER is missing, the
# operator is told to re-run this step once the sink has produced a row of
# the corresponding kind, since running with only one of the two present
# would leave the other stream's views permanently empty and silently so.
#
# BILLING_EXPORT_TABLE: the detailed Cloud Billing export table. Enabling
# that export is a MAINTAINER console step (plan: Epic 3 bead 7, NOT this
# bead) and requires knowing the destination project/dataset chosen there,
# so it is a REQUIRED second argument rather than guessed.
BILLING_EXPORT_TABLE=$2
if [ -z "$BILLING_EXPORT_TABLE" ]; then
    echo -e "${YELLOW}[NOTE]${NC} No BILLING_EXPORT_TABLE argument given -- skipping view creation."
    echo -e "${YELLOW}[NOTE]${NC} Re-run once the Cloud Billing export is enabled (Epic 3 bead 7):"
    echo -e "${YELLOW}[NOTE]${NC}   ./scripts/setup-telemetry.sh $PROJECT_ID <BILLING_PROJECT.BILLING_DATASET.gcp_billing_export_resource_v1_XXXXXX>"
    echo -e "${GREEN}[INFO]${NC} Telemetry sink + dataset + IAM setup complete for $PROJECT_ID!"
    exit 0
fi

TELEMETRY_TABLES_CSV=$(bq ls --project_id="$PROJECT_ID" --format=csv "$DATASET" 2>/dev/null | tail -n +2)

TELEMETRY_TABLE_STDOUT=$(echo "$TELEMETRY_TABLES_CSV" | grep -i "stdout" | head -1 | cut -d',' -f1)
TELEMETRY_TABLE_STDERR=$(echo "$TELEMETRY_TABLES_CSV" | grep -i "stderr" | head -1 | cut -d',' -f1)

if [ -z "$TELEMETRY_TABLE_STDOUT" ] || [ -z "$TELEMETRY_TABLE_STDERR" ]; then
    echo -e "${YELLOW}[NOTE]${NC} Not both sink destination tables exist yet under $DATASET."
    echo -e "${YELLOW}[NOTE]${NC}   stdout table (usage events): ${TELEMETRY_TABLE_STDOUT:-not found}"
    echo -e "${YELLOW}[NOTE]${NC}   stderr table (ledger_export/session events): ${TELEMETRY_TABLE_STDERR:-not found}"
    echo -e "${YELLOW}[NOTE]${NC} The sink has not written a first row of one or both kinds -- re-run this"
    echo -e "${YELLOW}[NOTE]${NC} script after the next deploy generates at least one usage AND one"
    echo -e "${YELLOW}[NOTE]${NC} ledger_export/session event."
    echo -e "${GREEN}[INFO]${NC} Telemetry sink + dataset + IAM setup complete for $PROJECT_ID (views pending)!"
    exit 0
fi

echo -e "${GREEN}[INFO]${NC} Applying sql/telemetry_views.sql (stdout table: $DATASET.$TELEMETRY_TABLE_STDOUT, stderr table: $DATASET.$TELEMETRY_TABLE_STDERR)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sed \
    -e "s|\${DATASET}|$PROJECT_ID.$DATASET|g" \
    -e "s|\${TELEMETRY_TABLE_STDOUT}|$PROJECT_ID.$DATASET.$TELEMETRY_TABLE_STDOUT|g" \
    -e "s|\${TELEMETRY_TABLE_STDERR}|$PROJECT_ID.$DATASET.$TELEMETRY_TABLE_STDERR|g" \
    -e "s|\${BILLING_EXPORT_TABLE}|$BILLING_EXPORT_TABLE|g" \
    "$SCRIPT_DIR/../sql/telemetry_views.sql" \
    | bq query --project_id="$PROJECT_ID" --use_legacy_sql=false

echo -e "${GREEN}[INFO]${NC} Telemetry setup complete for $PROJECT_ID!"
