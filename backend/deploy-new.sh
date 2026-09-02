#!/bin/bash
# Deploy a NEW backend service to Google Cloud Run
# Usage: ./deploy-new.sh [SERVICE_NAME]

set -e

# Verify a just-deployed Cloud Run service is PUBLICLY REACHABLE, and abort if
# it is not (bd polyglot-pdf-pidtg, extended to this script by bd
# polyglot-pdf-6oi9s).
#
# WHY THIS EXISTS. A `gcloud run` deployment with --allow-unauthenticated only
# REQUESTS an
# allUsers -> roles/run.invoker binding, but that request can be REFUSED while
# the deploy still succeeds and exits 0. The domain-restricted-sharing org
# policy (constraints/iam.allowedPolicyMemberDomains) rejects allUsers; gcloud
# creates the service, prints a NON-FATAL warning, and exits 0 -- leaving a
# service that 403s every request at Cloud Run's own gate, BEFORE any
# application code runs. The app then shows an auth error that has nothing to do
# with app auth, sending the operator to debug the wrong layer entirely.
#
# It bites only a NEW service: an existing one's binding predates the policy and
# is not retroactively stripped. So the scripts that create services are exactly
# where this must be checked.
#
# --flatten='bindings[].members' is LOAD-BEARING, and both halves of the query
# were got wrong once each before this was right:
#   1. Grepping the raw policy text for "allUsers" FALSE-PASSED: a
#      `roles/run.viewer -> allUsers` binding satisfied it while the INVOKER
#      binding was missing and the service still 403'd everything.
#   2. Adding --filter WITHOUT --flatten then FALSE-FAILED: --filter is
#      evaluated against the WHOLE policy resource, not per binding, and
#      `value(bindings.role)` emits every role ';'-joined on ONE line, so
#      `grep -qx` stopped matching as soon as a service had a SECOND binding.
# --flatten makes each member/role pair its own record, so the filter is
# genuinely per-binding and each surviving role prints on its own line.
#
# BOTH failure directions matter. Failing OPEN hides the bug behind a green
# check; failing CLOSED blocks a good deploy, and a gate that cries wolf gets
# deleted -- taking the real check with it. An inconclusive IAM READ therefore
# WARNS rather than aborting: being unable to check is not proof of breakage.
#
# stderr is NOT merged into the value (no 2>&1): a gcloud component-update nag
# landing in the variable could otherwise satisfy a text match on its own.
#
# Args: $1 service name, $2 region, $3 project id.
# Exits 1 when the service is definitively unreachable. MUST match
# backend/deploy-new.sh's copy exactly (pinned by
# tests/test_deploy_reachability_gate.py).
verify_service_publicly_reachable() {
    local svc="$1" region="$2" project="$3" invoker_roles
    # Reuse the caller's log helpers WHEN THEY EXIST, so deploy-all.sh keeps its
    # coloured [WARN]/[ERROR] on stdout exactly as before this was extracted
    # (a pre-PR review caught the extraction silently moving them to stderr and
    # dropping the colour). backend/deploy-new.sh defines no such helpers, so it
    # falls back to plain stderr -- which is why the function must not simply
    # call log_warn/log_error unconditionally.
    _gate_warn()  { if declare -f log_warn  >/dev/null 2>&1; then log_warn  "$1"; else echo "[WARN] $1"  >&2; fi; }
    _gate_error() { if declare -f log_error >/dev/null 2>&1; then log_error "$1"; else echo "[ERROR] $1" >&2; fi; }
    invoker_roles=$(gcloud run services get-iam-policy "$svc" \
        --region "$region" --project "$project" \
        --flatten='bindings[].members' \
        --filter='bindings.members:allUsers' \
        --format='value(bindings.role)') || invoker_roles="__QUERY_FAILED__"

    if [ "$invoker_roles" = "__QUERY_FAILED__" ]; then
    _gate_warn "Could not read the IAM policy for $svc -- skipping the"
    _gate_warn "reachability check. If the app cannot reach the backend, verify manually:"
    _gate_warn "  gcloud run services get-iam-policy $svc --region $region --project $project"
        return 0
    fi
    if echo "$invoker_roles" | grep -qx "roles/run.invoker"; then
        return 0
    fi
    _gate_error "==========================================================="
    _gate_error "  DEPLOY FAILED: the service is NOT publicly reachable"
    _gate_error "==========================================================="
    _gate_error "Service '$svc' has no allUsers invoker binding, so"
    _gate_error "Cloud Run will 403 EVERY request before your app ever sees it."
    _gate_error ""
    _gate_error "--allow-unauthenticated was passed, but the binding was refused --"
    _gate_error "almost always the domain-restricted-sharing org policy."
    _gate_error ""
    _gate_error "Fix it with:"
    _gate_error "  gcloud run services add-iam-policy-binding $svc \\"
    _gate_error "    --region $region --project $project \\"
    _gate_error "    --member=allUsers --role=roles/run.invoker"
    _gate_error ""
    _gate_error "If that is itself refused, the org policy must be relaxed for this"
    _gate_error "project first (constraints/iam.allowedPolicyMemberDomains)."
    _gate_error "See bd polyglot-pdf-pidtg."
    exit 1
}

# Default service name
SERVICE_NAME=${1:-polyglot-backend}
PROJECT_ID_ARG=$2
REGION="us-central1"

echo "🚀 Preparing to deploy service: $SERVICE_NAME"

# Determine Project ID
if [ -n "$PROJECT_ID_ARG" ]; then
    POLYGLOT_PROJECT_NAME=$PROJECT_ID_ARG
    echo "✅ Using provided project ID: $POLYGLOT_PROJECT_NAME"
elif [ -z "$POLYGLOT_PROJECT_NAME" ]; then
    echo "⚠️  POLYGLOT_PROJECT_NAME not set. Trying to detect from gcloud config..."
    POLYGLOT_PROJECT_NAME=$(gcloud config get-value project)
    if [ -z "$POLYGLOT_PROJECT_NAME" ]; then
        echo "❌ Error: Could not determine project ID. Please set POLYGLOT_PROJECT_NAME or provide it as the second argument."
        exit 1
    fi
    echo "✅ Using detected project: $POLYGLOT_PROJECT_NAME"
else
    echo "✅ Using env var project: $POLYGLOT_PROJECT_NAME"
fi

# Enable necessary APIs (just in case)
echo "🛠️  Ensuring Cloud Run and Build APIs are enabled..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project $POLYGLOT_PROJECT_NAME

# Build and push container -- from the REPO ROOT (bd 92qe.3): the Dockerfile
# lives at the root so the image includes scripts/authoring + scripts/bakeoff
# (the hosted extraction pipeline). .gcloudignore keeps the upload lean.
echo "📦 Building container image (repo-root context)..."
IMAGE_URL="gcr.io/$POLYGLOT_PROJECT_NAME/$SERVICE_NAME"
REPO_ROOT="$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")"
gcloud builds submit --tag $IMAGE_URL --project $POLYGLOT_PROJECT_NAME "$REPO_ROOT"

# Deploy to Cloud Run
echo "🌐 Deploying to Cloud Run service: $SERVICE_NAME..."
# --timeout: Cloud Run kills any request at this limit, including live
# WebSockets; the 300s default terminated every /ws/fill session at exactly
# 5 minutes (bd polyglot-pdf-9w5k). 3600s is the Cloud Run maximum.
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_URL \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --timeout=3600 \
    --project $POLYGLOT_PROJECT_NAME \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=$POLYGLOT_PROJECT_NAME"

# REACHABILITY GATE (bd polyglot-pdf-6oi9s). This script's whole job is standing
# up a NEW service, which is the ONLY case where the refused-invoker-binding bug
# fires -- so it needs the gate at least as much as deploy-all.sh does. Runs
# BEFORE the success banner: a service that 403s everything must never be
# reported as "Deployment Complete".
echo "🔎 Verifying the service is publicly reachable..."
verify_service_publicly_reachable "$SERVICE_NAME" "$REGION" "$POLYGLOT_PROJECT_NAME"

echo "✅ Deployment Complete!"
echo "Service URL: $(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --project $POLYGLOT_PROJECT_NAME --format 'value(status.url)')"
echo "Next Step: Ensure your firebase.json points to serviceId: '$SERVICE_NAME'"
