#!/bin/bash
# Deploy a NEW backend service to Google Cloud Run
# Usage: ./deploy-new.sh [SERVICE_NAME] [PROJECT_ID]
#   SERVICE_NAME defaults to polyglot-backend.
#   PROJECT_ID   pins the project; without it POLYGLOT_PROJECT_NAME is used,
#                then the active gcloud config.

set -e

# Verify a just-deployed Cloud Run service is PUBLICLY REACHABLE, and abort if
# it is not (bd polyglot-pdf-pidtg, extended to this script by bd
# polyglot-pdf-6oi9s).
#
# THE GATE ITSELF LIVES IN scripts/verify_service_reachable.py NOW (bd
# polyglot-pdf-ywxoh, 4.2). Four bash scripts used to each carry a
# byte-identical copy of this function's BODY (deploy-all.sh, backend/deploy-
# new.sh, deploy-editor.sh, deploy-admin-console.sh) -- pinned equal by
# tests/test_deploy_reachability_gate.py. cloudbuild.yaml's build steps need
# the SAME check and cannot source a bash function, so rather than add a
# FIFTH hand copy for the build, the check itself moved to one python module
# that both the build and every bash wrapper call. This function is now a
# THIN SHELL WRAPPER around that module -- kept so every call site below
# reads exactly as it always has (`verify_service_publicly_reachable "$SVC"
# "$REGION" "$PROJECT" [warn]`), with its bare-command shape (no pipe, no
# subshell, no `if`) still load-bearing: `exit 1` inside this function must
# still terminate the CALLING script, which a subshell would swallow.
#
# ${BASH_SOURCE[0]} here is THIS FILE (the function is defined inline, not
# sourced from elsewhere), so the module path resolves correctly regardless
# of the caller's own cwd or SCRIPT_DIR/REPO_ROOT naming.
#
# find_manifest_python-STYLE interpreter resolution, inlined rather than
# shared: python3 is not guaranteed on Windows Git Bash, and a python3
# App-Execution-Alias stub can exist on PATH without being able to run.
#
# Args: $1 service name, $2 region, $3 project id, $4 severity ("fatal"
# default, or "warn").
verify_service_publicly_reachable() {
    local svc="$1" region="$2" project="$3" severity="${4:-fatal}"
    local self_dir module py cand rc
    self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # This function is defined inline in FOUR files at two different repo
    # depths (the three root-level wrappers, and backend/deploy-new.sh one
    # directory down), so the module is looked up at both candidate paths
    # relative to THIS file rather than assuming the repo root.
    if [ -f "$self_dir/scripts/verify_service_reachable.py" ]; then
        module="$self_dir/scripts/verify_service_reachable.py"
    else
        module="$self_dir/../scripts/verify_service_reachable.py"
    fi
    for cand in ${MANIFEST_PYTHON_CANDIDATES:-python3 python py}; do
        if "$cand" -c "pass" >/dev/null 2>&1; then py="$cand"; break; fi
    done
    if [ -z "$py" ]; then
        echo "[ERROR] No python interpreter found -- cannot run the reachability gate; aborting deploy." >&2
        exit 1
    fi
    "$py" "$module" "$svc" "$region" "$project" --severity "$severity"
    rc=$?
    if [ "$rc" -ne 0 ]; then
        exit 1
    fi
    return 0
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
