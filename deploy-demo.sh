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
SA_NAME="polyglot-backend-sa"
SA_EMAIL="$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com"

# Secret Manager bindings, passed to gcloud as --set-secrets (bd
# polyglot-pdf-hvui4). MUST stay identical to deploy-staging.sh's copy -- pinned
# by tests/test_deploy_channel_parity.py, which derives both lists from the two
# scripts rather than restating them.
#
# --set-secrets REPLACES the whole secret block, so this must name EVERY
# binding the service should keep, not just the one being added. Today that is
# the link signing key alone: the two SCHEMA_*_TOKEN bindings currently live on
# this service are hand-applied drift for a gate that is RETIRED
# (deploy-editor.sh, bd rhc2v), so the next deploy deliberately drops them.
#
# LINK_TOKEN_SECRET gates client-link minting: without it the mint route 503s.
# The secret itself is provisioned out of band (maintainer, 2026-09-01); this
# only binds the existing secret's latest version to the env var.
BACKEND_SECRETS_COMMON="LINK_TOKEN_SECRET=LINK_TOKEN_SECRET:latest"

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
    # consistent, and means a LOCAL AI Studio run (VERTEXAI=false, the only place
    # that path is allowed -- see below) needs no stale pin cleared. Both ids are
    # 2.5-family, so model_family() bills them identically and the audio/VAD
    # tuning carries over (bd polyglot-pdf-a079).
    #
    # 3.1 is not available on Vertex as of 2026-06, and it therefore CANNOT be
    # deployed: AI Studio is never a production path (maintainer directive
    # 2026-08-04, bd polyglot-pdf-5e6a) because only Vertex's privacy agreement
    # keeps client data out of Google's model training. config.py REFUSES to
    # start with VERTEXAI=false whenever K_SERVICE is set, and there is no
    # override flag. Test 3.1 LOCALLY (no K_SERVICE) and deploy it only once it
    # is GA for Vertex customers. GEMINI_API_KEY is unused on this Vertex path
    # -- and is NOT bound by any deploy script: --set-secrets carries
    # LINK_TOKEN_SECRET alone (see BACKEND_SECRETS_COMMON above). Add it there
    # if a channel ever needs the AI Studio path. See
    # docs/standards/ai-models.md.
    # BACKEND_SERVICE_ACCOUNT pins the Cloud Run runtime identity (the custom SA
    # that holds roles/aiplatform.user for the Vertex path) IN the deploy itself,
    # so the new revision is created+routed under the right SA from the start --
    # no separate post-deploy `gcloud run services update`, which could briefly
    # serve a Vertex revision under the wrong identity or strand the demo if it
    # failed (bd polyglot-pdf-ignt). deploy-all.sh adds --service-account only when
    # this is non-empty, so other channels/bare runs are unchanged.
    # Continuous DTI + compression is the CODE DEFAULT (bd polyglot-pdf-7872):
    # USE_DTI, CONTINUOUS_SESSION, CONTEXT_COMPRESSION_ENABLED and the
    # ctu8-validated CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS=1500 all default
    # on/1500 in backend/config.py now, so this deploy no longer sets them.
    # Emergency fallback to the legacy section-reset flow: add USE_DTI=false,
    # CONTINUOUS_SESSION=false,CONTEXT_COMPRESSION_ENABLED=false here.
    # SPELL-BACK (bd polyglot-pdf-22h1f + 44ywm; maintainer go-ahead
    # 2026-08-10). The deterministic name_spellback tool: the model stops
    # speaking spellings and the client plays a Cloud TTS clip built from the
    # STORED value instead -- the fix for the bd 0rpu sticky-first-spelling
    # defect, where the model's speech read back a WRONG name.
    #
    # SPELLBACK_TOOL_ENABLED=true is now REDUNDANT: the default flipped ON at
    # the cutover (bd polyglot-pdf-apkdl), after this deploy baked it from
    # 2026-08-10. It stays explicit ON PURPOSE -- this script should state the
    # configuration it deploys rather than inherit it silently, so a later
    # default change cannot alter the demo without touching this file.
    # To roll back, set it to false HERE and redeploy: the declaration, the SI
    # addendum, the dispatch guard and the /api/tts/spellback route all follow
    # that one flag.
    #
    # LIVE_TEMPERATURE=0.4 is the maintainer's by-ear clarity setting, and the
    # temperature EVERY spell-back validation run used -- deploying at Google's
    # default 1.0 would ship a configuration we never tested. This var only
    # became deployable in this same change (it was dev-marker-gated before).
    #
    # LINK_MINTING_ENABLED=true turns the CLIENT LINK tier on for the demo
    # (maintainer, 2026-08-28, so testers can try the deployed app). It is
    # false by default on purpose -- the bd polyglot-pdf-ik7e interlock: a live
    # link is an unauthenticated entry point to a paid Gemini session, so it
    # must not exist without a spend ceiling behind it. A ceiling IS enforced
    # per link across reconnects (services/link_spend.check_budget), which
    # satisfies the interlock.
    #
    # But it is the GLOBAL $10 default, NOT the $3 the two kits declare. The
    # kits carry link_cost_ceiling_usd=3 and cost_ceiling_usd_for_kit reads it
    # correctly; the WS handshake simply never passes kit metadata to
    # check_budget (websocket_routes.py), so the per-form value is inert. Real
    # per-link exposure on this demo is therefore $10, not $3. Threading the
    # metadata through the handshake is bd polyglot-pdf-4tjt7 -- it needs a kit
    # load on the hottest path, which is why it is its own bead. Fails SAFE (a
    # higher ceiling, never an absent one), so this is a cost note, not a hole.
    #
    # LINK_REDEMPTIONS_FIRESTORE_ENABLED=true is REQUIRED alongside minting,
    # not optional: open_link raises RedemptionUnavailable when the store is
    # off, and the redemption gate fails CLOSED, so every minted link would
    # 404 at /api/links/open. Cloud Run's disk is ephemeral tmpfs, so
    # Firestore is the only durable one-time-use record -- same reason
    # CONFIRMATION_FIRESTORE_ENABLED is set in deploy-all.sh.
    #
    # LINK_TOKEN_SECRET (>=32 chars) is the HMAC SIGNING KEY for every link
    # token, so it is injected via Secret Manager, NEVER as a plaintext env
    # var. It IS wired now -- see BACKEND_SECRETS_COMMON near the top of this
    # file, passed as --set-secrets (bd polyglot-pdf-hvui4); this block used to
    # say it was still unset, which my own change falsified. Without the
    # binding, minting 503s and the mint page names BOTH this and LINK_BASE_URL,
    # because the route cannot distinguish them. Provisioning the secret itself
    # remains a maintainer step; this only binds an existing one.
    #
    # NOTE --set-env-vars REPLACES the whole env block, so a LINK_* var set by
    # hand on the service does NOT survive the next deploy. That is why these
    # are declared here rather than clicked in.
    #
    # LINK_BASE_URL is the FRONTEND origin, not this backend. A minted link is
    # `<base>/f#t=<token>` and /f is a client-app route (AppRoutes.tsx
    # CLIENT_LINK_PATH); pointing it at Cloud Run would 404 every tester. The
    # token rides in the URL FRAGMENT, which browsers never send to a server,
    # so it stays out of access logs and referrers.
    BACKEND_EXTRA_ENV="VERTEXAI=true,USE_PREMIUM_MODEL=false,SPELLBACK_TOOL_ENABLED=true,LIVE_TEMPERATURE=0.4,EXTRACTOR_MODEL=gemini-2.5-pro,LINK_MINTING_ENABLED=true,LINK_CHANNEL=demo,LINK_REDEMPTIONS_FIRESTORE_ENABLED=true,LINK_BASE_URL=https://polyglot-demo-aa709.web.app,CORS_EXTRA_ORIGINS=https://polyglot-editor-demo.web.app;https://polyglot-editor-demo.firebaseapp.com" \
        BACKEND_SECRETS="$BACKEND_SECRETS_COMMON" \
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
