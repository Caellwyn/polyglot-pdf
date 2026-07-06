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
    # the reason for moving off AI Studio.
    #
    # We do NOT pin MODEL_NATIVE: config.py _resolve_model is backend-aware and,
    # with VERTEXAI=true and the standard tier, resolves to the Vertex native-audio
    # id (gemini-live-2.5-flash-native-audio) on its own. The model strings differ
    # by backend -- the AI Studio native-audio id 1008s on Vertex and vice versa --
    # so letting the resolver pick keeps demo and a bare deploy-all.sh Vertex run
    # consistent, and means flipping BACK to AI Studio (VERTEXAI=false) for 3.1
    # needs no stale pin cleared. Both ids are 2.5-family, so model_family() bills
    # them identically and the audio/VAD tuning carries over (bd polyglot-pdf-a079).
    #
    # 3.1 is not available on Vertex as of 2026-06; running it still requires the
    # AI Studio path (VERTEXAI=false, USE_PREMIUM_MODEL=true). GEMINI_API_KEY
    # (still injected via Secret Manager) is unused on this Vertex path. See
    # docs/standards/ai-models.md.
    # BACKEND_SERVICE_ACCOUNT pins the Cloud Run runtime identity (the custom SA
    # that holds roles/aiplatform.user for the Vertex path) IN the deploy itself,
    # so the new revision is created+routed under the right SA from the start --
    # no separate post-deploy `gcloud run services update`, which could briefly
    # serve a Vertex revision under the wrong identity or strand the demo if it
    # failed (bd polyglot-pdf-ignt). deploy-all.sh adds --service-account only when
    # this is non-empty, so other channels/bare runs are unchanged.
    # Continuous DTI + compression cutover (bd polyglot-pdf-x8rt / ctu8): run the
    # whole form as ONE session bounded by the compression window instead of
    # per-section resets. USE_DTI + CONTINUOUS_SESSION + CONTEXT_COMPRESSION_ENABLED
    # turn it on; TRIGGER_MARGIN_TOKENS=1500 lands the window at the ctu8-VALIDATED
    # 3500 tokens (5000 Vertex-clamped trigger - 1500 margin). The default margin
    # (600) would derive an UNTESTED 4400 window, so this override is load-bearing.
    # Reversible: drop these 4 vars to fall back to the section-reset flow.
    BACKEND_EXTRA_ENV="VERTEXAI=true,USE_PREMIUM_MODEL=false,EXTRACTOR_MODEL=gemini-2.5-pro,USE_DTI=true,CONTINUOUS_SESSION=true,CONTEXT_COMPRESSION_ENABLED=true,CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS=1500,CORS_EXTRA_ORIGINS=https://polyglot-editor-demo.web.app;https://polyglot-editor-demo.firebaseapp.com" \
        BACKEND_SERVICE_ACCOUNT="$SA_EMAIL" \
        ./deploy-all.sh "${GCP_ARGS[@]}"
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
