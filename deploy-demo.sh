#!/bin/bash
# deploy-demo.sh - Deploy to Personal (Portfolio) channel
#
# Usage: ./deploy-demo.sh [options]

set -e

# DEPLOY PREFLIGHT (bd polyglot-pdf-1s3ko). Runs BEFORE anything else: a build
# runs from a COMMIT and build_checks/{sha} vouches for that commit's test run,
# so a dirty or unpushed tree makes both claims false. Refuses with the reason
# and the remedy; see scripts/deploy_preflight.sh for the full rationale.
PREFLIGHT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PREFLIGHT_DIR/scripts/deploy_preflight.sh"
deploy_preflight "$PREFLIGHT_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ENROLMENT CHECK (bd polyglot-pdf-hn0jq). The voice app now refuses any
# account carrying neither firm_id nor the vff_dev claim, so a signed-in user
# who was never enrolled gets a 1008 close the UI shows as a failed
# connection. Custom claims only reach a NEWLY MINTED token, so enrol BEFORE
# deploying, not after:
#     python scripts/bootstrap_voice_dev.py --list
#     python scripts/bootstrap_voice_dev.py --email you@example.com
echo -e "${GREEN}[INFO]${NC} Reminder: voice accounts need firm_id or a dev claim."
echo -e "${GREEN}[INFO]${NC}   check with: python scripts/bootstrap_voice_dev.py --list"

# Verify account
echo -e "${GREEN}[INFO]${NC} 👀 Checking gcloud account..."
CURRENT_ACCOUNT=$(gcloud config get-value account)
if [[ "$CURRENT_ACCOUNT" != *"gmail.com"* ]]; then
  echo -e "${YELLOW}[WARN]${NC} Current account is $CURRENT_ACCOUNT. Need caellwyn@gmail.com."
  gcloud auth login --update-adc
fi

# Configuration
CONSOLIDATED_PROJECT="polyglot-demo-aa709"
GCP_PROJECT="$CONSOLIDATED_PROJECT"
FIREBASE_PROJECT="$CONSOLIDATED_PROJECT"
BUCKET_NAME="$CONSOLIDATED_PROJECT-form-kits"
# The runtime service account and the Secret Manager bindings moved to
# deploy/channels/<channel>.env (bd polyglot-pdf-1s3ko) -- they were
# constants here, and a constant that two files must keep in step is the
# drift the channel files exist to end. deploy-all.sh reads them from the
# file; so does cloudbuild.yaml's backend target.

# Determine which components to deploy
DEPLOY_GCP=true
DEPLOY_FIREBASE=true

if [ $# -gt 0 ] && [ "$1" != "--all" ]; then
    DEPLOY_GCP=false
    DEPLOY_FIREBASE=false
    for arg in "$@"; do
        case "$arg" in
            --backend|--form-kits)
                DEPLOY_GCP=true
                ;;
            --frontend)
                DEPLOY_FIREBASE=true
                ;;
            *)
                # UNKNOWN ARG IS FATAL (bd polyglot-pdf-7aez9). Without this arm
                # a typo like --front-end silently matched nothing, every
                # DEPLOY_* stayed false, the script deployed NOTHING, and still
                # printed its success banner and exited 0. The operator then
                # believes they verified a change they never deployed -- and on
                # the staging channel that is exactly the false confidence the
                # tier exists to remove. Mirrors deploy-all.sh, which has always
                # errored on an unknown argument.
                echo -e "${RED}[ERROR]${NC} Unknown argument: $arg" >&2
                echo "Usage: $0 [--backend] [--frontend] [--form-kits] [--all]" >&2
                exit 1
                ;;
        esac
    done
fi

echo -e "${GREEN}[INFO]${NC} 🚀 Deploying to Demo (Portfolio) Channel..."

# 1. Deploy Backend and Form Kits to GCP project
if [ "$DEPLOY_GCP" = true ]; then
    echo -e "${GREEN}[INFO]${NC} 🛠️  Stage 1: Deploying Backend and Form Kits to GCP ($GCP_PROJECT)..."
    export POLYGLOT_PROJECT_NAME="$GCP_PROJECT"
    export FORM_KITS_BUCKET="$BUCKET_NAME"

    # Filter arguments for Stage 1: only pass --backend, --form-kits, or nothing/all
    GCP_ARGS=()
    for arg in "$@"; do
        [[ "$arg" == "--backend" || "$arg" == "--form-kits" ]] && GCP_ARGS+=("$arg")
    done
    [ ${#GCP_ARGS[@]} -eq 0 ] && GCP_ARGS=("--backend" "--form-kits")
    # CHANNEL CONFIG LIVES IN A FILE NOW (bd polyglot-pdf-1s3ko).
    #
    # Everything this block used to spell out inline -- VERTEXAI, the LINK_*
    # set, CORS_EXTRA_ORIGINS, the secret binding, the runtime SA -- is in
    # deploy/channels/demo.env, which deploy-all.sh reads and cloudbuild.yaml's
    # backend-demo target reads too. ONE source, two consumers: a Cloud Build
    # step cannot read a bash string, and a restated config is exactly the drift
    # tests/test_deploy_channel_parity.py exists to catch.
    #
    # PROMOTE, do not edit here: change deploy/channels/staging.env FIRST,
    # verify on the staging channel, then copy the line into demo.env. The
    # parity test fails on any difference outside the CHANNEL_SPECIFIC keys.
    DEPLOY_CHANNEL="demo" \
        ./deploy-all.sh "${GCP_ARGS[@]}"
fi

# 2. Deploy Firestore rules + Frontend to Firebase project
if [ "$DEPLOY_FIREBASE" = true ]; then
    export POLYGLOT_PROJECT_NAME="$FIREBASE_PROJECT"

    # Deploy Firestore security rules (firestore.rules, wired via firebase.json)
    # BEFORE the frontend: deploy-all.sh ships hosting only, and the demo project
    # otherwise stays on default-deny -- which breaks the users/{uid} profile
    # sync on login (email signup's allowlist check is server-side since sprint
    # 23 C3 and needs no client-readable rule). Rules first so the new frontend
    # never goes live against stale rules.
    echo -e "${GREEN}[INFO]${NC} 🔒 Stage 2a: Deploying Firestore rules to Firebase ($FIREBASE_PROJECT)..."
    firebase deploy --only firestore:rules --project "$FIREBASE_PROJECT"

    # Composite indexes (firestore.indexes.json, wired via firebase.json).
    # A Firestore query combining an equality filter with an order_by on a
    # DIFFERENT field is served ONLY from a composite index -- without one it
    # fails at runtime with FAILED_PRECONDITION, and no local test catches it
    # because a fake query object filters and sorts in Python (CLAUDE.md scar
    # #7, applied to indexes rather than IAM). GET /admin/audit emits exactly
    # that shape for each of its four filters, so the index set ships with the
    # rules. Indexes are PROJECT-wide, like rules: deploying them here lands
    # them for the staging channel too. Index builds are ASYNCHRONOUS -- the
    # command returns before a new index is READY, so a freshly added filter
    # can still fail for a few minutes after this deploy completes.
    echo -e "${GREEN}[INFO]${NC} Stage 2a2: Deploying Firestore indexes to Firebase ($FIREBASE_PROJECT)..."
    firebase deploy --only firestore:indexes --project "$FIREBASE_PROJECT"

    # Build in demo mode so Vite loads .env.demo (the demo Firebase keys).
    # A bare "npm run build" loads .env.production, which has no Firebase config
    # for this project -- the app then dies with "auth/invalid-api-key".
    #
    # VITE_APP_CHANNEL=demo (bd polyglot-pdf-z4ljj, C0): explicit rather than
    # relying on config.ts's getAppChannel() default, for the same reason
    # deploy-staging.sh sets it explicitly to "staging" -- a future default
    # change must not silently flip which channel the demo's firm-console
    # pages claim to be on the admin service's required `?channel=` param.
    echo -e "${GREEN}[INFO]${NC} 🌐 Stage 2b: Deploying Frontend to Firebase ($FIREBASE_PROJECT)..."
    FRONTEND_BUILD_CMD="npm run build:schema:demo" VITE_APP_CHANNEL="demo" ./deploy-all.sh --frontend
fi

echo -e "${GREEN}[INFO]${NC} ✅ Demo Deployment Complete!"
echo -e "${GREEN}[INFO]${NC} Frontend URL: https://$FIREBASE_PROJECT.web.app"
