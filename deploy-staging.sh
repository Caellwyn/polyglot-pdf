#!/bin/bash
# deploy-staging.sh - Deploy to the STAGING channel (the test deploy)
#
# Usage: ./deploy-staging.sh [--backend] [--frontend] [--form-kits] [--all]
#
# WHY THIS EXISTS (bd polyglot-pdf-9qn64). Some bugs only appear once deployed
# -- the Cloud Run WebSocket timeout, the Vertex model-id resolution, the IAM
# envelope, the Hosting rewrite, the per-mode Vite build. Before this channel
# existed, the ONLY way to find them was to deploy to the demo, which is the
# same URL shown to investors and pilot firms. Staging is a second, disposable
# copy of the deployed surface so a broken deploy can no longer take the demo
# down.
#
# WHAT IS SEPARATE, AND WHAT IS NOT. Staging and demo live in the SAME GCP /
# Firebase project (polyglot-demo-aa709), deliberately -- a whole second project
# would need its own IAM bootstrap, its own Firebase Auth user set, and its own
# enrolment run. What that buys, and what it does NOT:
#
#   SEPARATE (a staging deploy cannot touch these):
#     - Cloud Run service   polyglot-backend-staging   vs  polyglot-backend
#     - Hosting site        polyglot-app-staging       vs  polyglot-demo-aa709
#     - the /api/** rewrite: each Hosting site routes to its OWN service
#       (firebase.json), so the staging app talks only to the staging backend.
#
#   SHARED (a mistake here DOES reach the demo):
#     - the form-kits GCS bucket. A kit marked status:complete deploys to the one
#       bucket and appears in the DEMO's form list too. This script therefore
#       does NOT deploy form kits by default -- see the --form-kits note below.
#     - Firestore (confirmation_events, users/{uid}, firms, authorized_emails).
#     - Firebase Auth: one user pool, so a staging tester can sign into the demo.
#
#   So this channel protects against BROKEN CODE reaching the demo. It does not
#   protect against bad DATA. Treat kit publishing and Firestore writes as
#   production actions no matter which channel you ran them from.
#
# ONE-TIME setup, before the first staging deploy -- see docs/doctrine/
# promotion-tiers.md for the full walkthrough:
#     firebase hosting:sites:create polyglot-app-staging --project polyglot-demo-aa709
#     firebase target:apply hosting app-staging polyglot-app-staging --project polyglot-demo-aa709
#   (The target mapping ships in .firebaserc already; re-run target:apply only
#   for a NEW site.) Then add the staging site to Firebase Auth's authorized
#   domains -- Authentication > Settings > Authorized domains -- or sign-in
#   fails at a human's first attempt with the whole config present and valid.

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ENROLMENT CHECK (bd polyglot-pdf-hn0jq). Same as the demo: the voice app
# refuses any account carrying neither firm_id nor the vff_dev claim, and custom
# claims only reach a NEWLY MINTED token. Auth is SHARED with the demo, so an
# account already enrolled there needs nothing further here.
echo -e "${GREEN}[INFO]${NC} Reminder: voice accounts need firm_id or a dev claim."
echo -e "${GREEN}[INFO]${NC}   check with: python scripts/bootstrap_voice_dev.py --list"

# Verify account (same identity as the demo -- one project)
echo -e "${GREEN}[INFO]${NC} 👀 Checking gcloud account..."
CURRENT_ACCOUNT=$(gcloud config get-value account)
if [[ "$CURRENT_ACCOUNT" != *"gmail.com"* ]]; then
  echo -e "${YELLOW}[WARN]${NC} Current account is $CURRENT_ACCOUNT. Need caellwyn@gmail.com."
  gcloud auth login --update-adc
fi

# Configuration. Same project as the demo; the SERVICE and SITE are what differ.
CONSOLIDATED_PROJECT="polyglot-demo-aa709"
GCP_PROJECT="$CONSOLIDATED_PROJECT"
FIREBASE_PROJECT="$CONSOLIDATED_PROJECT"
BUCKET_NAME="$CONSOLIDATED_PROJECT-form-kits"
SA_NAME="polyglot-backend-sa"
SA_EMAIL="$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com"

STAGING_SERVICE_NAME="polyglot-backend-staging"
STAGING_SITE="polyglot-app-staging"
STAGING_HOSTING_TARGET="app-staging"

# Determine which components to deploy.
#
# NOTE the deliberate asymmetry with deploy-demo.sh: a bare run here deploys
# backend + frontend but NOT form kits. The bucket is shared with the demo, so a
# staging form-kits deploy would publish kits to the demo's form list -- exactly
# the cross-channel leak this environment exists to prevent. Pass --form-kits
# explicitly if you really mean to publish kits (it is the same act as running
# deploy-demo.sh --form-kits).
DEPLOY_GCP=true
DEPLOY_FIREBASE=true
DEPLOY_FORM_KITS=false

if [ $# -gt 0 ] && [ "$1" != "--all" ]; then
    DEPLOY_GCP=false
    DEPLOY_FIREBASE=false
    for arg in "$@"; do
        case "$arg" in
            --backend)
                DEPLOY_GCP=true
                ;;
            --form-kits)
                DEPLOY_FORM_KITS=true
                ;;
            --frontend)
                DEPLOY_FIREBASE=true
                ;;
        esac
    done
elif [ "$1" = "--all" ]; then
    DEPLOY_FORM_KITS=true
fi

echo -e "${GREEN}[INFO]${NC} 🚧 Deploying to STAGING Channel (test deploy)..."
echo -e "${GREEN}[INFO]${NC}    service: $STAGING_SERVICE_NAME   site: $STAGING_SITE"
if [ "$DEPLOY_FORM_KITS" = true ]; then
    echo -e "${YELLOW}[WARN]${NC} Form kits are SHARED with the demo -- publishing here"
    echo -e "${YELLOW}[WARN]${NC} also changes the demo's form list."
fi

# 1. Deploy Backend (+ optionally form kits) to the staging Cloud Run service
if [ "$DEPLOY_GCP" = true ] || [ "$DEPLOY_FORM_KITS" = true ]; then
    echo -e "${GREEN}[INFO]${NC} 🛠️  Stage 1: Deploying to GCP ($GCP_PROJECT / $STAGING_SERVICE_NAME)..."
    export POLYGLOT_PROJECT_NAME="$GCP_PROJECT"
    export FORM_KITS_BUCKET="$BUCKET_NAME"

    GCP_ARGS=()
    [ "$DEPLOY_GCP" = true ] && GCP_ARGS+=("--backend")
    [ "$DEPLOY_FORM_KITS" = true ] && GCP_ARGS+=("--form-kits")

    # Backend env MIRRORS deploy-demo.sh exactly. That is the whole point of a
    # staging channel: a config difference between the two would mean staging
    # stops predicting demo behavior, and the deploy-only bugs this environment
    # exists to catch are precisely the config-shaped ones. When you change a
    # setting in deploy-demo.sh's BACKEND_EXTRA_ENV, change it HERE FIRST, verify
    # on staging, and only then promote it to the demo.
    #
    # The one deliberate difference is CORS_EXTRA_ORIGINS, which names the
    # editor origins. The voice app reaches the backend same-origin through the
    # Hosting /api/** rewrite, so the staging SITE needs no CORS entry of its
    # own; the editor origins stay listed because the hosted editor calls Cloud
    # Run directly and may be pointed at this service for testing.
    BACKEND_EXTRA_ENV="VERTEXAI=true,USE_PREMIUM_MODEL=false,SPELLBACK_TOOL_ENABLED=true,LIVE_TEMPERATURE=0.4,EXTRACTOR_MODEL=gemini-2.5-pro,CORS_EXTRA_ORIGINS=https://polyglot-editor-demo.web.app;https://polyglot-editor-demo.firebaseapp.com" \
        BACKEND_SERVICE_ACCOUNT="$SA_EMAIL" \
        BACKEND_SERVICE_NAME="$STAGING_SERVICE_NAME" \
        ./deploy-all.sh "${GCP_ARGS[@]}"
fi

# 2. Deploy Frontend to the staging Hosting site
if [ "$DEPLOY_FIREBASE" = true ]; then
    export POLYGLOT_PROJECT_NAME="$FIREBASE_PROJECT"

    # Firestore rules are deliberately NOT deployed here. They are PROJECT-wide,
    # not per-site: deploying them from staging would apply the staging branch's
    # rules to the live demo, which is exactly the blast radius this channel is
    # meant to remove. Rules ship with the demo deploy (deploy-demo.sh), after
    # the change has been reviewed. If a staging test genuinely needs new rules,
    # that is a rules change to land on the demo deliberately -- not a side
    # effect of a test deploy.
    echo -e "${GREEN}[INFO]${NC} 🌐 Stage 2: Deploying Frontend to $STAGING_SITE..."

    # Build in demo mode: .env.demo carries the Firebase config for
    # polyglot-demo-aa709, which is the SAME project staging lives in, so the
    # client-side Firebase keys are correct for both channels. The backend URL
    # baked into the build does NOT come from that file -- deploy-all.sh
    # resolves the LIVE Cloud Run URL for BACKEND_SERVICE_NAME at deploy time
    # and passes it as VITE_WS_URL, so exporting the staging service name here
    # is what points the staging build at the staging backend.
    FRONTEND_BUILD_CMD="npm run build:schema:demo" \
        BACKEND_SERVICE_NAME="$STAGING_SERVICE_NAME" \
        FRONTEND_HOSTING_TARGET="$STAGING_HOSTING_TARGET" \
        FRONTEND_SITE_NAME="$STAGING_SITE" \
        ./deploy-all.sh --frontend
fi

echo -e "${GREEN}[INFO]${NC} ✅ Staging Deployment Complete!"
echo -e "${GREEN}[INFO]${NC} Staging URL: https://$STAGING_SITE.web.app"
echo -e "${GREEN}[INFO]${NC} Demo (untouched): https://$FIREBASE_PROJECT.web.app"
