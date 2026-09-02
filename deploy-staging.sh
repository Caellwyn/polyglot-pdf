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

# Secret Manager bindings, passed to gcloud as --set-secrets (bd
# polyglot-pdf-hvui4). MUST stay identical to deploy-demo.sh's copy -- pinned by
# tests/test_deploy_channel_parity.py, which derives both lists from the two
# scripts rather than restating them.
#
# --set-secrets REPLACES the whole secret block, so this must name EVERY
# binding the service should keep, not just the one being added. Today that is
# the link signing key alone: the two SCHEMA_*_TOKEN bindings live on the demo
# service are hand-applied drift for a gate that is RETIRED (deploy-editor.sh,
# bd rhc2v), so they are deliberately NOT carried forward here.
#
# LINK_TOKEN_SECRET gates client-link minting: without it the mint route 503s.
# The secret itself is provisioned out of band (maintainer, 2026-09-01); this
# only binds the existing secret's latest version to the env var.
BACKEND_SECRETS_COMMON="LINK_TOKEN_SECRET=LINK_TOKEN_SECRET:latest"

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
    # editor origins. The staging SITE needs no CORS entry of its own, but NOT
    # for the reason you might assume: the voice path is a WEBSOCKET, and
    # Firebase Hosting does not proxy WS upgrades, so the client connects to
    # Cloud Run DIRECTLY, cross-origin (docs/technical_guide.md "Gotchas").
    # It works because a WS upgrade is not CORS-preflighted -- not because it is
    # same-origin. Only the app's plain HTTP calls use the Hosting /api/**
    # rewrite and are genuinely same-origin.
    #
    # So: if anyone later adds a cross-origin fetch/XHR from the staging site
    # straight to Cloud Run (bypassing the rewrite), it WILL need an entry here.
    # The editor origins are listed precisely because the hosted editor does
    # exactly that -- it calls Cloud Run directly to dodge the rewrite's 60s cap.
    #
    # CLIENT LINKS mirror the demo (bd polyglot-pdf-hvui4). They were missing
    # here: this script was written from a pre-#693 copy of the demo config, so
    # staging could not mint or open a client link at all -- and a channel that
    # cannot exercise the pilot's core feature does not predict demo behavior,
    # which is the one job stated at the top of this block.
    #
    # LINK_BASE_URL is the STAGING frontend, and that is the ONE link value that
    # must NOT match the demo. A minted link is `<base>/f#t=<token>` and /f is a
    # client-app route (AppRoutes.tsx CLIENT_LINK_PATH), so pointing staging at
    # the demo origin would mint links that open the DEMO -- silently testing
    # the wrong deployment, which is worse than not minting at all.
    BACKEND_EXTRA_ENV="VERTEXAI=true,USE_PREMIUM_MODEL=false,SPELLBACK_TOOL_ENABLED=true,LIVE_TEMPERATURE=0.4,EXTRACTOR_MODEL=gemini-2.5-pro,LINK_MINTING_ENABLED=true,LINK_REDEMPTIONS_FIRESTORE_ENABLED=true,LINK_BASE_URL=https://$STAGING_SITE.web.app,CORS_EXTRA_ORIGINS=https://polyglot-editor-demo.web.app;https://polyglot-editor-demo.firebaseapp.com" \
        BACKEND_SECRETS="$BACKEND_SECRETS_COMMON" \
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
