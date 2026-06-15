#!/bin/bash
# deploy-all.sh - Unified deployment script for Polyglot PDF Form Filler
#
# Usage:
#   ./deploy-all.sh              # Deploy everything (backend, frontend, form-kits)
#   ./deploy-all.sh --backend    # Deploy backend only
#   ./deploy-all.sh --frontend   # Deploy frontend only
#   ./deploy-all.sh --form-kits  # Deploy form-kits only
#   ./deploy-all.sh --all        # Deploy everything (explicit)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Complete-gate (bd polyglot-pdf-b0pe): only kits explicitly marked
# status:complete in metadata.json may reach GCS / the voice app. In-progress
# (draft) and unmarked kits stay LOCAL + git-backed but are never deployed, so a
# deploy run after a new form is onboarded cannot leak a draft to production.
# Returns 0 (complete) only when metadata.json exists AND its status is exactly
# "complete"; absent metadata.json or any other/absent status -> 1 (skip).
kit_is_complete() {
    local kit_dir="$1"
    local meta="$kit_dir/metadata.json"
    [ -f "$meta" ] || return 1
    # Match "status": "complete" tolerant of whitespace; no jq dependency.
    grep -Eq '"status"[[:space:]]*:[[:space:]]*"complete"' "$meta"
}

# Resolve a kit's schema filename (bd polyglot-pdf-snpi). metadata.json may carry
# a custom "schema" field (KitMetadata.schema in formKitDirectory.ts); when present
# the kit's schema lives in that file, NOT the hardcoded schema.json. Echoes the
# resolved filename; defaults to schema.json when metadata.json is absent or has no
# "schema" string -- mirroring the editor's `meta?.schema || 'schema.json'`.
#
# We FLATTEN newlines (tr -d) BEFORE the grep so a metadata.json with the "schema"
# key/value split across lines still matches -- a plain line-oriented grep would
# miss that form and silently fall back to schema.json, leaving the custom-schema
# kit skipped even though the editor's JSON.parse accepts it (Codex review, bd
# snpi). Pure POSIX text tools (tr/grep/sed), no jq or python dependency: python3
# is NOT reliably present (on Windows it can be the no-op Store shim), so the
# script must not lean on it. The sed also trims whitespace that sat inside the
# quotes ("schema": " custom.json ").
kit_schema_file() {
    local kit_dir="$1"
    local meta="$kit_dir/metadata.json"
    local name=""
    if [ -f "$meta" ]; then
        name=$(tr -d '\n' < "$meta" \
            | grep -Eo '"schema"[[:space:]]*:[[:space:]]*"[^"]+"' \
            | head -1 \
            | sed -E 's/.*:[[:space:]]*"[[:space:]]*([^"]*[^"[:space:]])[[:space:]]*".*/\1/')
    fi
    echo "${name:-schema.json}"
}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
FORM_KITS_DIR="$SCRIPT_DIR/form-kits"

BACKEND_SERVICE_NAME="polyglot-backend"
REGION="us-central1"
FORM_KITS_BUCKET="${FORM_KITS_BUCKET:-polyglot-pdf-form-kits}"
FORM_KITS_PREFIX="${FORM_KITS_PREFIX:-form-kits}"

# Frontend build command, overridable by the channel deploy scripts. The deployed
# app is the schema-forms app (index.html -> src/schema-forms/main.tsx), so the
# build MUST run the schema config so Vite loads the right .env per channel and
# bakes in the Firebase config:
#   demo -> build:schema:demo (--mode demo -> .env.demo, demo Firebase keys)
#   prod -> build:schema      (.env.production, prod Firebase keys)
# A bare "vite build" (npm run build) loads .env.production under the default
# config, which has no VITE_FIREBASE_* keys -- the app then dies at launch with
# Firebase "auth/invalid-api-key". Default to the prod schema build so a direct
# deploy-all.sh --frontend is safe.
FRONTEND_BUILD_CMD="${FRONTEND_BUILD_CMD:-npm run build:schema}"

# Print header
echo ""
log_info "═══════════════════════════════════════════════════════════"
log_info "  Polyglot PDF Form Filler - Unified Deployment Script   "
log_info "═══════════════════════════════════════════════════════════"
echo ""

# Parse arguments
DEPLOY_BACKEND=false
DEPLOY_FRONTEND=false
DEPLOY_FORM_KITS=false

if [ $# -eq 0 ] || [ "$1" = "--all" ]; then
    # No args or --all: deploy everything
    DEPLOY_BACKEND=true
    DEPLOY_FRONTEND=true
    DEPLOY_FORM_KITS=true
else
    for arg in "$@"; do
        case "$arg" in
            --backend)
                DEPLOY_BACKEND=true
                ;;
            --frontend)
                DEPLOY_FRONTEND=true
                ;;
            --form-kits)
                DEPLOY_FORM_KITS=true
                ;;
            *)
                log_error "Unknown argument: $arg"
                echo "Usage: $0 [--backend] [--frontend] [--form-kits] [--all]"
                exit 1
                ;;
        esac
    done
fi

# Check prerequisites
check_project() {
    if [ -z "$POLYGLOT_PROJECT_NAME" ]; then
        log_warn "POLYGLOT_PROJECT_NAME not set, trying to detect from gcloud..."
        POLYGLOT_PROJECT_NAME=$(gcloud config get-value project 2>/dev/null)
        if [ -z "$POLYGLOT_PROJECT_NAME" ] || [ "$POLYGLOT_PROJECT_NAME" = "(unset)" ]; then
            log_error "Could not determine project ID. Please set POLYGLOT_PROJECT_NAME or run: gcloud config set project <project-id>"
            exit 1
        fi
        log_info "Using detected project: $POLYGLOT_PROJECT_NAME"
    else
        log_info "Using project: $POLYGLOT_PROJECT_NAME"
    fi
}

# Display deployment plan
echo ""
log_info "Deployment Plan:"
log_info "  Backend:   $DEPLOY_BACKEND"
log_info "  Frontend:  $DEPLOY_FRONTEND"
log_info "  Form Kits: $DEPLOY_FORM_KITS"
echo ""

check_project

# ============================================================================
# BACKEND DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_BACKEND" = true ]; then
    log_info "═══════════════════════════════════════════════════════════"
    log_info "  DEPLOYING BACKEND TO CLOUD RUN"
    log_info "═══════════════════════════════════════════════════════════"
    echo ""
    
    cd "$BACKEND_DIR"

    # No local-dependency self-heal here (unlike the frontend): the backend image
    # is built fresh by Cloud Build on every deploy, and the Dockerfile runs
    # "pip install -r requirements.txt" inside it. There is no local .venv in the
    # deploy path, so nothing local can go stale.

    # Enable necessary APIs
    log_info "Ensuring necessary Google Cloud APIs are enabled..."
    gcloud services enable run.googleapis.com \
        cloudbuild.googleapis.com \
        artifactregistry.googleapis.com \
        aiplatform.googleapis.com \
        storage.googleapis.com \
        --project "$POLYGLOT_PROJECT_NAME"
    
    # Build the image using Cloud Build
    IMAGE_URL="gcr.io/$POLYGLOT_PROJECT_NAME/$BACKEND_SERVICE_NAME"
    log_info "Building container image: $IMAGE_URL..."
    gcloud builds submit --tag "$IMAGE_URL" --project "$POLYGLOT_PROJECT_NAME"
    
    # Deploy to Cloud Run
    log_info "🌐 Deploying to Cloud Run service: $BACKEND_SERVICE_NAME..."
    # BACKEND_EXTRA_ENV: channel deploy scripts append channel-specific env vars
    # here (e.g. the demo runs on AI Studio: VERTEXAI=false,USE_PREMIUM_MODEL=false).
    # Default empty -> prod keeps the Vertex defaults baked into config.py.
    # GEMINI_API_KEY is injected separately via Secret Manager (--set-secrets),
    # NOT here -- never put the key in plaintext env vars.
    BACKEND_ENV="GOOGLE_CLOUD_PROJECT=$POLYGLOT_PROJECT_NAME,FORM_KITS_MODE=gcs,FORM_KITS_GCS_BUCKET=$FORM_KITS_BUCKET,FORM_KITS_REMOTE_PREFIX=$FORM_KITS_PREFIX"
    [ -n "$BACKEND_EXTRA_ENV" ] && BACKEND_ENV="$BACKEND_ENV,$BACKEND_EXTRA_ENV"

    # --timeout: Cloud Run kills any request at this limit, including live
    # WebSockets. The 300s default terminated every /ws/fill session at exactly
    # 5 minutes (bd polyglot-pdf-9w5k); 3600s is the Cloud Run maximum, so WS
    # lifetime is bounded by Gemini Live session limits (GoAway handling)
    # instead of the HTTP layer.
    gcloud run deploy "$BACKEND_SERVICE_NAME" \
        --image "$IMAGE_URL" \
        --region "$REGION" \
        --platform managed \
        --allow-unauthenticated \
        --timeout=3600 \
        --project "$POLYGLOT_PROJECT_NAME" \
        --set-env-vars="$BACKEND_ENV"
    
    BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE_NAME" --platform managed --region "$REGION" --project "$POLYGLOT_PROJECT_NAME" --format 'value(status.url)')
    log_success "✅ Backend deployed successfully!"
    echo "   URL: $BACKEND_URL"
    echo ""
    
    cd "$SCRIPT_DIR"
fi

# ============================================================================
# FORM KITS DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_FORM_KITS" = true ]; then
    log_info "═══════════════════════════════════════════════════════════"
    log_info "  DEPLOYING FORM KITS TO GCS"
    log_info "═══════════════════════════════════════════════════════════"
    echo ""
    
    # Create bucket if it doesn't exist
    if ! gcloud storage buckets describe "gs://$FORM_KITS_BUCKET" &>/dev/null; then
        log_info "Creating bucket gs://$FORM_KITS_BUCKET..."
        gcloud storage buckets create "gs://$FORM_KITS_BUCKET" \
            --location=us-central1 \
            --uniform-bucket-level-access \
            --project "$POLYGLOT_PROJECT_NAME"
        log_success "Bucket created successfully"
    fi
    
    # Upload all form kits
    log_info "📦 Uploading form kits..."
    for kit_dir in "$FORM_KITS_DIR"/*/; do
        [ -d "$kit_dir" ] || continue
        kit_id=$(basename "$kit_dir")

        schema_file=$(kit_schema_file "$kit_dir")
        if [ ! -f "$kit_dir/$schema_file" ]; then
            log_warn "Skipping $kit_id - no $schema_file found"
            continue
        fi

        if ! kit_is_complete "$kit_dir"; then
            log_warn "Skipping $kit_id - not status:complete (draft kept local; bd b0pe gate)"
            continue
        fi

        log_info "  Uploading $kit_id..."
        gcloud storage cp -r "$kit_dir"/* "gs://$FORM_KITS_BUCKET/$FORM_KITS_PREFIX/$kit_id/" --project "$POLYGLOT_PROJECT_NAME"
    done
    
    # Generate and upload manifest
    log_info "📝 Generating manifest..."
    
    manifest_content='{"generatedAt":"'$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")'","forms":['
    first=true
    
    for kit_dir in "$FORM_KITS_DIR"/*/; do
        [ -d "$kit_dir" ] || continue
        kit_id=$(basename "$kit_dir")

        schema_file=$(kit_schema_file "$kit_dir")
        if [ ! -f "$kit_dir/$schema_file" ]; then
            continue
        fi

        # Complete-gate: a draft/unmarked kit is uploaded by neither loop, so it
        # is also absent from the manifest the voice app reads (bd b0pe).
        if ! kit_is_complete "$kit_dir"; then
            continue
        fi

        # Extract title from the resolved schema file (custom filename per bd snpi)
        label=$(grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' "$kit_dir/$schema_file" | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/' || echo "$kit_id")
        [ -z "$label" ] && label="$kit_id"
        
        # Find PDF file
        pdf_file="form.pdf"
        if [ ! -f "$kit_dir/form.pdf" ]; then
            pdf_file=$(ls "$kit_dir"/*.pdf 2>/dev/null | head -1 | xargs basename 2>/dev/null || echo "form.pdf")
        fi
        
        if [ "$first" = true ]; then
            first=false
        else
            manifest_content+=','
        fi
        
        manifest_content+='{"id":"'$kit_id'","label":"'$label'","schemaFile":"'$schema_file'","schemaPath":"/'$FORM_KITS_PREFIX'/'$kit_id'/'$schema_file'","pdfFile":"'$pdf_file'","pdfPath":"/'$FORM_KITS_PREFIX'/'$kit_id'/'$pdf_file'"}'
    done
    
    manifest_content+=']}'
    
    # Upload manifest
    temp_manifest=$(mktemp)
    echo "$manifest_content" | python3 -m json.tool > "$temp_manifest" 2>/dev/null || echo "$manifest_content" > "$temp_manifest"
    gcloud storage cp "$temp_manifest" "gs://$FORM_KITS_BUCKET/$FORM_KITS_PREFIX/index.json" --project "$POLYGLOT_PROJECT_NAME"
    rm "$temp_manifest"
    
    log_success "✅ Form kits deployed successfully!"
    echo "   Bucket: gs://$FORM_KITS_BUCKET"
    echo "   Manifest: gs://$FORM_KITS_BUCKET/$FORM_KITS_PREFIX/index.json"
    echo ""
fi

# ============================================================================
# FRONTEND DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_FRONTEND" = true ]; then
    log_info "═══════════════════════════════════════════════════════════"
    log_info "  DEPLOYING FRONTEND TO FIREBASE HOSTING"
    log_info "═══════════════════════════════════════════════════════════"
    echo ""
    
    cd "$FRONTEND_DIR"
    
    # Check if Firebase CLI is installed
    if ! command -v firebase &> /dev/null; then
        log_error "Firebase CLI not found. Install with: npm install -g firebase-tools"
        exit 1
    fi
    
    # Self-heal dependencies. node_modules is git-ignored, so a fresh checkout
    # (or an "npm install" accidentally run from the repo root instead of here)
    # leaves frontend/node_modules empty. The build's prebuild hook then calls
    # tsx, which is not on disk, and fails with "tsx is not recognized". We are
    # already in $FRONTEND_DIR (cd above), so this installs into the right tree
    # no matter where the deploy was launched from. Test the actual binary the
    # build needs -- catches both the empty and the partial-install cases.
    if [ ! -x node_modules/.bin/tsx ]; then
        log_info "Frontend dependencies missing -- installing..."
        if [ -f package-lock.json ]; then
            npm ci
        else
            npm install
        fi
    fi

    # Build frontend (channel-aware; see FRONTEND_BUILD_CMD above)
    log_info "📦 Building frontend ($FRONTEND_BUILD_CMD)..."
    $FRONTEND_BUILD_CMD
    
    # Deploy to Firebase Hosting
    log_info "🌐 Deploying to Firebase Hosting..."
    firebase deploy --only hosting --project "$POLYGLOT_PROJECT_NAME"
    
    log_success "✅ Frontend deployed successfully!"
    echo "   URL: https://$POLYGLOT_PROJECT_NAME.web.app"
    echo ""
    
    cd "$SCRIPT_DIR"
fi

# ============================================================================
# DEPLOYMENT SUMMARY
# ============================================================================
echo ""
log_success "╔═══════════════════════════════════════════════════════════╗"
log_success "║         DEPLOYMENT COMPLETED SUCCESSFULLY                 ║"
log_success "╚═══════════════════════════════════════════════════════════╝"
echo ""

if [ "$DEPLOY_BACKEND" = true ]; then
    log_info "🔧 Backend API:"
    echo "   $BACKEND_URL"
    echo ""
fi

if [ "$DEPLOY_FRONTEND" = true ]; then
    log_info "🌐 Frontend URL:"
    echo "   https://$POLYGLOT_PROJECT_NAME.web.app"
    echo ""
fi

if [ "$DEPLOY_FORM_KITS" = true ]; then
    log_info "📦 Form Kits Bucket:"
    echo "   gs://$FORM_KITS_BUCKET/$FORM_KITS_PREFIX"
    echo ""
fi

log_info "💡 Next steps:"
echo "   1. Test the application at the frontend URL"
echo "   2. Verify API routes work through Firebase hosting"
echo "   3. Check form-kits load via /api/form-kits endpoint"
echo ""
