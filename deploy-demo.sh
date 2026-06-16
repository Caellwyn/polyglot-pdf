#!/bin/bash
# deploy-demo.sh - Deploy to Personal (Portfolio) channel
#
# Usage: ./deploy-demo.sh [options]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

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
SA_NAME="polyglot-backend-sa"
SA_EMAIL="$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com"
REGION="us-central1"

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

    # Demo runs on Vertex AI: VERTEXAI=true selects the service-account ADC path
    # (authenticates via GOOGLE_CLOUD_PROJECT + the Cloud Run SA's
    # roles/aiplatform.user; no API key), which keeps request data private --
    # the reason for moving off AI Studio. USE_PREMIUM_MODEL=false selects 2.5
    # (gemini-2.5-flash-native-audio-preview), which runs on Vertex. We are NOT
    # using 3.1, so the AI Studio path (the only one with 3.1 as of 2026-06) is
    # no longer needed. To run 3.1 you would need both USE_PREMIUM_MODEL=true AND
    # VERTEXAI=false until Vertex ships 3.1. GEMINI_API_KEY (still injected via
    # Secret Manager) is unused on this path. See docs/standards/ai-models.md.
    BACKEND_EXTRA_ENV="VERTEXAI=true,USE_PREMIUM_MODEL=false" ./deploy-all.sh "${GCP_ARGS[@]}"

    # Update Cloud Run to use the custom Service Account
    echo -e "${GREEN}[INFO]${NC} 🔑 Ensuring Cloud Run uses service account $SA_NAME..."
    gcloud run services update polyglot-backend \
        --service-account="$SA_EMAIL" \
        --region="$REGION" \
        --project="$GCP_PROJECT"
fi

# 2. Deploy Firestore rules + Frontend to Firebase project
if [ "$DEPLOY_FIREBASE" = true ]; then
    export POLYGLOT_PROJECT_NAME="$FIREBASE_PROJECT"

    # Deploy Firestore security rules (firestore.rules, wired via firebase.json)
    # BEFORE the frontend: deploy-all.sh ships hosting only, and the demo project
    # otherwise stays on default-deny -- which breaks email signup (the unauth
    # authorized_emails read) and the users/{uid} profile sync on login. Rules
    # first so the new frontend never goes live against stale rules.
    echo -e "${GREEN}[INFO]${NC} 🔒 Stage 2a: Deploying Firestore rules to Firebase ($FIREBASE_PROJECT)..."
    firebase deploy --only firestore:rules --project "$FIREBASE_PROJECT"

    # Build in demo mode so Vite loads .env.demo (the demo Firebase keys).
    # A bare "npm run build" loads .env.production, which has no Firebase config
    # for this project -- the app then dies with "auth/invalid-api-key".
    echo -e "${GREEN}[INFO]${NC} 🌐 Stage 2b: Deploying Frontend to Firebase ($FIREBASE_PROJECT)..."
    FRONTEND_BUILD_CMD="npm run build:schema:demo" ./deploy-all.sh --frontend
fi

echo -e "${GREEN}[INFO]${NC} ✅ Demo Deployment Complete!"
echo -e "${GREEN}[INFO]${NC} Frontend URL: https://$FIREBASE_PROJECT.web.app"
