#!/bin/bash
# setup-monitoring.sh - Provision log-based metrics, alert policies, uptime
# checks, and the admin SA's Error Reporting / Monitoring roles.
#
# Sibling of scripts/setup-gcp-project.sh (public backend SA),
# scripts/setup-admin-service.sh (admin SA) and scripts/setup-telemetry.sh
# (BigQuery sink + views). Epic 3 bead 8 (E3.8), plan:
# docs/sprint_22_admin-console_plan.md "Errors".
#
# DECLARATIVE and OPERATOR-RUN. Nothing here runs from a deploy script, and
# this bead does NOT execute anything against GCP itself -- an operator runs
# this by hand, under their own gcloud credentials, when the project is first
# provisioned or the monitoring surface changes. Its shipped TEXT is what
# tests/test_setup_monitoring_script.py pins; gcloud is never invoked in CI.
#
# WHY LOG-BASED METRICS RATHER THAN AN IN-APP COUNTER. The app is stateless by
# design (CLAUDE.md scar #4) and runs on Cloud Run, so there is nowhere for a
# process-local counter to live across the instance churn -- and adding a
# counter store would be exactly the server-side session state that invariant
# forbids. Cloud Logging already receives every event; counting the entries it
# already has costs nothing and survives every restart.
#
# WHAT THE APP HAD TO SHIP FOR THESE FILTERS TO MATCH ANYTHING. Before this
# bead the /fill route closed eight different ways, with the close code
# sometimes in the log line and sometimes only in a prose reason, so no filter
# could count "the 1013s". backend/utils/structured_logger.py's log_ws_close
# now gives every close ONE shape -- event_type "ws_error" with the code at
# metadata.close_code -- and websocket_routes._close_ws routes every close on
# /fill through it (the 1011/1006 family is emitted from
# backend/adapters/live_ai_gemini.py instead, because that is a GEMINI-side
# close the route only learns about second hand). The filters below name that
# shape; backend/tests/unit/test_ws_close_events.py is what stops the shape
# from drifting out from under them.
#
# THE TWO LOG SHAPES, AGAIN. As setup-telemetry.sh's header explains at
# length, this project emits through TWO different renderers:
#   * StructuredLogger._emit wraps its envelope in a `message` key before
#     printing, so its event type is at jsonPayload.message.event_type. The
#     ws_error events below are this shape.
#   * A plain structlog call renders the positional event name at
#     jsonPayload.event with no wrapper. link_mint_refused is this shape.
# Writing every filter as jsonPayload.event_type would silently match NOTHING
# for both -- the failure mode being an alert that never fires, which nothing
# else in the system would notice. Each filter below is written against the
# shape its emitter actually produces.
#
# Usage: ./scripts/setup-monitoring.sh <PROJECT_ID> [NOTIFICATION_CHANNEL_ID]
#
# NOTIFICATION_CHANNEL_ID is optional. Without it the alert policies are
# created with no notification channel: they still evaluate and still show as
# firing in the console, they just do not email anyone. That is a deliberate
# default rather than a hard requirement, because creating a notification
# channel needs a verified destination address and this script must stay
# runnable on a fresh project. Re-run with the channel id once one exists:
#   gcloud alpha monitoring channels list --project=<PROJECT_ID>
#
# Idempotent throughout: every step describes-then-creates-or-updates, so a
# re-run after a filter or threshold changes actually APPLIES the change
# rather than failing on a create-only call and leaving the live resource
# stale (the trap bd polyglot-pdf-f7f0h caught in setup-telemetry.sh).

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ID=$1
NOTIFICATION_CHANNEL_ID=$2
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}[ERROR]${NC} Usage: $0 <PROJECT_ID> [NOTIFICATION_CHANNEL_ID]"
    exit 1
fi

REGION="us-central1"
# The three Cloud Run services this project runs. Names match deploy-all.sh's
# BACKEND_SERVICE_NAME / ADMIN_SERVICE_NAME defaults and deploy-staging.sh's
# STAGING_SERVICE_NAME -- pinned by tests/test_setup_monitoring_script.py so a
# rename on either side fails rather than silently monitoring nothing.
BACKEND_SERVICE="polyglot-backend"
STAGING_SERVICE="polyglot-backend-staging"
ADMIN_SERVICE="polyglot-admin"

echo -e "${GREEN}[INFO]${NC} Setting up monitoring for project: $PROJECT_ID"

# 1. Enable the APIs. monitoring covers metrics, alert policies and uptime
#    checks; clouderrorreporting is what the admin console's error view reads.
echo -e "${GREEN}[INFO]${NC} Enabling monitoring + error reporting APIs..."
gcloud services enable \
    monitoring.googleapis.com \
    clouderrorreporting.googleapis.com \
    --project "$PROJECT_ID"

# ---------------------------------------------------------------------------
# 2. Log-based metrics
# ---------------------------------------------------------------------------
#
# create_or_update_metric <name> <description> <filter>
#
# `gcloud logging metrics create` FAILS on a metric that already exists, so a
# create-only call cannot be how a re-run applies a changed filter -- it would
# leave the live metric counting the OLD filter forever while the script
# exited 0. describe decides which of create/update to run.
create_or_update_metric() {
    local name=$1
    local description=$2
    local filter=$3

    if gcloud logging metrics describe "$name" --project="$PROJECT_ID" &>/dev/null; then
        echo -e "${GREEN}[INFO]${NC} Updating log-based metric $name..."
        gcloud logging metrics update "$name" \
            --project="$PROJECT_ID" \
            --description="$description" \
            --log-filter="$filter"
    else
        echo -e "${GREEN}[INFO]${NC} Creating log-based metric $name..."
        gcloud logging metrics create "$name" \
            --project="$PROJECT_ID" \
            --description="$description" \
            --log-filter="$filter"
    fi
}

# ws_close_1011_count -- the Gemini-side drop. 1011 is the intermittent
# native-audio "Input data processing failed" the audio pacing work
# (bd polyglot-pdf-daa / -h04c) exists to suppress, and a RISING rate is the
# early warning that a model or config change has re-opened it. Emitted from
# backend/adapters/live_ai_gemini.py's connection-closed except block, which
# is the single place the close code is read off the wire.
#
# 1006 is deliberately NOT in this filter even though it shares the
# spontaneous-drop family: 1006 is what a peer records when the connection
# died with no close frame at all, so it also fires on ordinary network churn
# (a client closing a laptop lid). Mixing it in would raise the floor of this
# metric to a level the alert threshold below could not sit above.
create_or_update_metric \
    "ws_close_1011_count" \
    "WebSocket 1011 closes (Gemini-side session drop)" \
    'resource.type="cloud_run_revision" AND jsonPayload.message.event_type="ws_error" AND jsonPayload.message.metadata.close_code=1011'

# ws_close_1013_count -- the budget refusal. 1013 ("try again later") is
# emitted by websocket_routes._close_ws for budget_exhausted and
# budget_unavailable. This is NOT an error metric: a client using their
# allowance is the system working. It is a BUSINESS signal -- a rising 1013
# rate means link ceilings are set too low for real usage, or one firm is
# burning through links faster than expected -- and it is the input to the
# console's credit views.
create_or_update_metric \
    "ws_close_1013_count" \
    "WebSocket 1013 closes (link budget exhausted or unavailable)" \
    'resource.type="cloud_run_revision" AND jsonPayload.message.event_type="ws_error" AND jsonPayload.message.metadata.close_code=1013'

# mint_refused_count -- a staff mint request that was turned down.
# backend/routes/link_routes.py logs this through a PLAIN structlog call
# (`_log.info("link_mint_refused", ...)`), so the event name renders at
# jsonPayload.event, NOT jsonPayload.message.event_type -- a different shape
# from the two ws_error metrics above, for the reason the header explains.
# Copying their filter form here would produce a metric that counted zero
# forever.
create_or_update_metric \
    "mint_refused_count" \
    "Client magic-link mint requests refused (quota, credits, or gate)" \
    'resource.type="cloud_run_revision" AND jsonPayload.event="link_mint_refused"'

# ---------------------------------------------------------------------------
# 3. Alert policies
# ---------------------------------------------------------------------------
#
# Policies are declared as JSON and applied through
# `gcloud alpha monitoring policies create/update`, because the flag-based
# `gcloud alpha monitoring policies create --condition-filter` form cannot
# express a rate-aligned condition with a per-series aggregation.
#
# apply_policy <display-name> <json-file>
apply_policy() {
    local display_name=$1
    local json_file=$2

    # Policies have no user-chosen id: they are addressed by a generated name
    # and only the displayName is stable, so the existing one is found by
    # filtering on that. An empty result means "create".
    local existing
    existing=$(gcloud alpha monitoring policies list \
        --project="$PROJECT_ID" \
        --filter="displayName=\"$display_name\"" \
        --format="value(name)" 2>/dev/null | head -1)

    if [ -n "$existing" ]; then
        echo -e "${GREEN}[INFO]${NC} Updating alert policy: $display_name"
        gcloud alpha monitoring policies update "$existing" \
            --project="$PROJECT_ID" \
            --policy-from-file="$json_file"
    else
        echo -e "${GREEN}[INFO]${NC} Creating alert policy: $display_name"
        gcloud alpha monitoring policies create \
            --project="$PROJECT_ID" \
            --policy-from-file="$json_file"
    fi
}

POLICY_DIR=$(mktemp -d)
trap 'rm -rf "$POLICY_DIR"' EXIT

# NOTIFICATION_CHANNELS_JSON is the JSON array fragment spliced into each
# policy. Empty array when no channel was given -- see the usage note above.
if [ -n "$NOTIFICATION_CHANNEL_ID" ]; then
    NOTIFICATION_CHANNELS_JSON="[\"projects/$PROJECT_ID/notificationChannels/$NOTIFICATION_CHANNEL_ID\"]"
else
    echo -e "${YELLOW}[NOTE]${NC} No NOTIFICATION_CHANNEL_ID given -- policies will"
    echo -e "${YELLOW}[NOTE]${NC} evaluate and show as firing in the console, but email nobody."
    echo -e "${YELLOW}[NOTE]${NC} Re-run with a channel id from:"
    echo -e "${YELLOW}[NOTE]${NC}   gcloud alpha monitoring channels list --project=$PROJECT_ID"
    NOTIFICATION_CHANNELS_JSON="[]"
fi

# POLICY A -- the 5xx rate across the Cloud Run services.
#
# WHY A RATE AND NOT A COUNT. An absolute count fires on a traffic spike that
# is proportionally healthy, and stays silent on a low-traffic outage where
# every request fails. The condition below aligns to a per-second rate over a
# 5-minute window, so it means the same thing at any volume.
#
# The 300s duration is what keeps a single bad deploy revision's first few
# seconds from paging: a 5xx burst that resolves inside five minutes (a cold
# start, a rolled-back revision) never crosses.
cat > "$POLICY_DIR/policy_5xx.json" <<POLICY_5XX_EOF
{
  "displayName": "polyglot 5xx rate",
  "documentation": {
    "content": "Cloud Run 5xx responses are elevated across the polyglot services. Check the failing service's logs and the most recent revision. Runbook: docs/standards/logging-and-cost.md.",
    "mimeType": "text/markdown"
  },
  "conditions": [
    {
      "displayName": "5xx responses > 0.1/s over 5m",
      "conditionThreshold": {
        "filter": "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\"",
        "aggregations": [
          {
            "alignmentPeriod": "300s",
            "perSeriesAligner": "ALIGN_RATE",
            "crossSeriesReducer": "REDUCE_SUM",
            "groupByFields": ["resource.labels.service_name"]
          }
        ],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0.1,
        "duration": "300s",
        "trigger": {"count": 1}
      }
    }
  ],
  "combiner": "OR",
  "enabled": true,
  "notificationChannels": $NOTIFICATION_CHANNELS_JSON
}
POLICY_5XX_EOF

apply_policy "polyglot 5xx rate" "$POLICY_DIR/policy_5xx.json"

# POLICY B -- the 1011 rate.
#
# Separate from the 5xx policy on purpose: a Gemini-side session drop is NOT a
# 5xx. The WebSocket upgrade already succeeded, so Cloud Run records a
# perfectly healthy request while every user's session dies mid-sentence. The
# 5xx policy above cannot see this failure at all, which is precisely why the
# ws_close_1011_count metric exists.
#
# The threshold is deliberately looser in TIME (900s) than the 5xx policy: an
# occasional 1011 is a known, tolerated fact of the native-audio models
# (bd polyglot-pdf-daa), so what matters is a sustained elevation rather than
# a spike. Fifteen minutes above the line is a real regression; three drops in
# a minute is Tuesday.
cat > "$POLICY_DIR/policy_1011.json" <<POLICY_1011_EOF
{
  "displayName": "polyglot ws 1011 rate",
  "documentation": {
    "content": "Gemini-side WebSocket 1011 drops are sustained above baseline. A live-model or audio-pacing regression is the usual cause (bd polyglot-pdf-daa). Check AUDIO_PACING_ENABLED and any recent model-id change.",
    "mimeType": "text/markdown"
  },
  "conditions": [
    {
      "displayName": "ws 1011 closes > 0.05/s over 15m",
      "conditionThreshold": {
        "filter": "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/ws_close_1011_count\"",
        "aggregations": [
          {
            "alignmentPeriod": "300s",
            "perSeriesAligner": "ALIGN_RATE",
            "crossSeriesReducer": "REDUCE_SUM",
            "groupByFields": ["resource.labels.service_name"]
          }
        ],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0.05,
        "duration": "900s",
        "trigger": {"count": 1}
      }
    }
  ],
  "combiner": "OR",
  "enabled": true,
  "notificationChannels": $NOTIFICATION_CHANNELS_JSON
}
POLICY_1011_EOF

apply_policy "polyglot ws 1011 rate" "$POLICY_DIR/policy_1011.json"

# ---------------------------------------------------------------------------
# 4. Uptime checks -- ONE PER CHANNEL, on /health
# ---------------------------------------------------------------------------
#
# PER CHANNEL, not one shared check. Staging and demo run DIFFERENT CODE on the
# same project (docs/doctrine/promotion-tiers.md): staging is where a
# deploy-only bug is supposed to be found. A single check against one of them
# would either miss a broken demo or page on a staging channel that is
# EXPECTED to be broken. The admin service gets its own for the same reason --
# it is a separate Cloud Run service with its own IAM and its own failure
# modes.
#
# /health, not /. It is unauthenticated (so the checker needs no credential)
# and it now reports the two Firestore probes -- the confirmation sink's WRITE
# probe and the firms store's READ probe (bd polyglot-pdf-vq5wd, wired in this
# same bead). A 200 from it therefore means rather more than "the process is
# up": it means the audit trail can be written and firm data can be read.
#
# The check asserts only the 200, NOT the probe strings inside the body. A
# degraded probe deliberately still answers 200 (see backend/main.py) so that
# the ALERT policies page on it, rather than an uptime check flapping and
# taking the whole channel's availability history with it.
#
# create_or_update_uptime_check <display-name> <cloud-run-service>
create_or_update_uptime_check() {
    local display_name=$1
    local service=$2

    local host
    host=$(gcloud run services describe "$service" \
        --platform=managed --region="$REGION" --project="$PROJECT_ID" \
        --format='value(status.url)' 2>/dev/null | sed -e 's|^https://||')

    if [ -z "$host" ]; then
        echo -e "${YELLOW}[NOTE]${NC} Cloud Run service $service is not deployed yet --"
        echo -e "${YELLOW}[NOTE]${NC} skipping its uptime check. Re-run this script after"
        echo -e "${YELLOW}[NOTE]${NC} deploying it."
        return 0
    fi

    local existing
    existing=$(gcloud monitoring uptime list-configs \
        --project="$PROJECT_ID" \
        --filter="displayName=\"$display_name\"" \
        --format="value(name)" 2>/dev/null | head -1)

    if [ -n "$existing" ]; then
        echo -e "${GREEN}[INFO]${NC} Updating uptime check: $display_name ($host)"
        gcloud monitoring uptime update "$existing" \
            --project="$PROJECT_ID" \
            --period=5 \
            --timeout=10
    else
        echo -e "${GREEN}[INFO]${NC} Creating uptime check: $display_name ($host)"
        gcloud monitoring uptime create "$display_name" \
            --project="$PROJECT_ID" \
            --resource-type=uptime-url \
            --resource-labels="host=$host,project_id=$PROJECT_ID" \
            --path="/health" \
            --port=443 \
            --protocol=https \
            --period=5 \
            --timeout=10
    fi
}

create_or_update_uptime_check "polyglot demo health" "$BACKEND_SERVICE"
create_or_update_uptime_check "polyglot staging health" "$STAGING_SERVICE"
create_or_update_uptime_check "polyglot admin health" "$ADMIN_SERVICE"

# ---------------------------------------------------------------------------
# 5. Admin SA roles deferred to this bead
# ---------------------------------------------------------------------------
#
# Epic 1's setup-admin-service.sh deliberately did NOT grant these: they are in
# admin_backend/tests/unit/test_admin_sa_iam_envelope.py's DEFERRED_ROLES set,
# and that test FAILS if either is granted before the capability exists (an
# unused grant is its own risk -- an idle credential with a permission nothing
# calls). This bead is what makes them live, so this is where they are granted
# and where they move out of DEFERRED_ROLES, in the same commit.
#
# errorreporting.viewer -- the admin console's "errors per channel" view reads
# Error Reporting's groupStats API. VIEWER, not the writer or admin role: the
# console reads groups, it never resolves or deletes them, and the SERVICES
# report errors by writing logs (which needs only the logging.logWriter they
# already hold), not by calling the Error Reporting API.
#
# monitoring.viewer -- the console's health and alert views read the
# log-based metrics, the policies' firing state and the uptime results created
# above. Read-only for the same reason: an operator changes a threshold by
# re-running THIS script under their own credentials, not through the console
# with the service's identity.
#
# The public backend's polyglot-backend-sa gets NEITHER. It writes logs; it
# never reads a metric back (CLAUDE.md scar #7 -- keep the deployed identity's
# envelope as narrow as the code actually needs).
ADMIN_SA_EMAIL="admin-backend-sa@$PROJECT_ID.iam.gserviceaccount.com"

echo -e "${GREEN}[INFO]${NC} Granting roles/errorreporting.viewer to $ADMIN_SA_EMAIL..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$ADMIN_SA_EMAIL" \
    --role="roles/errorreporting.viewer" \
    --condition=None > /dev/null

echo -e "${GREEN}[INFO]${NC} Granting roles/monitoring.viewer to $ADMIN_SA_EMAIL..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$ADMIN_SA_EMAIL" \
    --role="roles/monitoring.viewer" \
    --condition=None > /dev/null

echo -e "${GREEN}[INFO]${NC} Monitoring setup complete for $PROJECT_ID!"
echo -e "${GREEN}[INFO]${NC} Metrics:  ws_close_1011_count, ws_close_1013_count, mint_refused_count"
echo -e "${GREEN}[INFO]${NC} Policies: polyglot 5xx rate, polyglot ws 1011 rate"
echo -e "${GREEN}[INFO]${NC} Uptime:   demo, staging, admin (each on /health)"
