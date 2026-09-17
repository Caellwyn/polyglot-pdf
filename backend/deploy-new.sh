#!/bin/bash
# deploy-new.sh - Deploy one backend Cloud Run service by name.
#
# Usage: ./deploy-new.sh [SERVICE_NAME]
#   SERVICE_NAME defaults to polyglot-backend.
#
# A THIN WRAPPER OVER CLOUD BUILD (bd polyglot-pdf-oqtm7, Epic 4 bead 4.6).
# This script used to be the "stand up a brand new service" path: it uploaded
# the local tree with `gcloud builds submit --tag`, ran `gcloud run deploy`
# itself, and checked the new service's reachability. All three now live in
# cloudbuild.yaml, whose backend and admin-service targets create the service
# if it does not exist -- and only the build can satisfy the per-SHA verify
# gate, so a deploy that went around it would fail anyway. The script survives
# as the by-service-name entry point, mapping a service to its target.
#
# THERE IS NO GENERIC TARGET. Each service's env, secrets and runtime identity
# come from deploy/channels/<channel>.env, so a service name with no channel
# file has no configuration to deploy -- which is why an unrecognised name is
# refused here rather than guessed at. Adding a service means adding its
# channel file and its cloudbuild.yaml target (and a trigger, via
# scripts/setup-cloud-build.sh), not calling this script with a new name.

set -e

REPO_ROOT="$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")"

SERVICE_NAME="${1:-polyglot-backend}"

case "$SERVICE_NAME" in
    polyglot-backend)          TARGET="backend-demo" ;;
    polyglot-backend-staging)  TARGET="backend-staging" ;;
    polyglot-admin)            TARGET="admin-service" ;;
    *)
        echo "[ERROR] No Cloud Build target deploys a service named '$SERVICE_NAME'." >&2
        echo "[ERROR] Known services and their targets:" >&2
        echo "[ERROR]   polyglot-backend          -> backend-demo    (./deploy-demo.sh)" >&2
        echo "[ERROR]   polyglot-backend-staging  -> backend-staging (./deploy-staging.sh)" >&2
        echo "[ERROR]   polyglot-admin            -> admin-service   (./deploy-admin.sh)" >&2
        echo "[ERROR] A new service needs its own deploy/channels/<channel>.env and" >&2
        echo "[ERROR] its own cloudbuild.yaml target first." >&2
        exit 1
        ;;
esac

# DEPLOY PREFLIGHT (bd polyglot-pdf-1s3ko): a build runs from a COMMIT and
# build_checks/{sha} vouches for that commit's test run, so a dirty or
# unpushed tree makes both claims false.
source "$REPO_ROOT/scripts/deploy_preflight.sh"
deploy_preflight "$REPO_ROOT"

source "$REPO_ROOT/scripts/deploy_build_targets.sh"

SHA=$(deploy_build_sha "$REPO_ROOT")

echo "Deploying $SERVICE_NAME via Cloud Build target $TARGET at $SHA..."
run_build_targets "$SHA" "$TARGET"

echo "Deployment complete."
echo "Next Step: ensure firebase.json points to serviceId: '$SERVICE_NAME'"
