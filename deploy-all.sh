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

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
FORM_KITS_DIR="$SCRIPT_DIR/form-kits"

BACKEND_SERVICE_NAME="polyglot-backend"
REGION="us-central1"
FORM_KITS_BUCKET="${FORM_KITS_BUCKET:-polyglot-pdf-form-kits}"
FORM_KITS_PREFIX="${FORM_KITS_PREFIX:-form-kits}"

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
log_info "📋 Deployment Plan:"
[ "$DEPLOY_BACKEND" = true ] && echo "   ✓ Backend (Cloud Run)"
[ "$DEPLOY_FRONTEND" = true ] && echo "   ✓ Frontend (Firebase Hosting)"
[ "$DEPLOY_FORM_KITS" = true ] && echo "   ✓ Form Kits (GCS)"
log_info "📋 Deployment Plan:"
[ "$DEPLOY_BACKEND" = true ] && echo "   ✓ Backend (Cloud Run)"
[ "$DEPLOY_FRONTEND" = true ] && echo "   ✓ Frontend (Firebase Hosting)"
[ "$DEPLOY_FORM_KITS" = true ] && echo "   ✓ Form Kits (GCS)"
echo ""

check_project

check_project

# Confirmation prompt
read -p "Continue with deployment? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_warn "Deployment cancelled."
    log_warn "Deployment cancelled."
    exit 0
fi

echo ""

# ============================================================================
# BACKEND DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_BACKEND" = true ]; then
    log_info "═══════════════════════════════════════════════════════════"
    log_info "  DEPLOYING BACKEND TO CLOUD RUN"
    log_info "═══════════════════════════════════════════════════════════"
    log_info "═══════════════════════════════════════════════════════════"
    log_info "  DEPLOYING BACKEND TO CLOUD RUN"
    log_info "═══════════════════════════════════════════════════════════"
    echo ""
    
    cd "$BACKEND_DIR"
    
    # Enable necessary APIs
    log_info "🛠️  Ensuring Cloud Run and Build APIs are enabled..."
    gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project "$POLYGLOT_PROJECT_NAME"
    cd "$BACKEND_DIR"
    
    # Enable necessary APIs
    log_info "🛠️  Ensuring Cloud Run and Build APIs are enabled..."
    gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project "$POLYGLOT_PROJECT_NAME"
    
    # Build and push container
    log_info "📦 Building container image..."
    IMAGE_URL="gcr.io/$POLYGLOT_PROJECT_NAME/$BACKEND_SERVICE_NAME"
    gcloud builds submit --tag "$IMAGE_URL" --project "$POLYGLOT_PROJECT_NAME" .
    log_info "📦 Building container image..."
    IMAGE_URL="gcr.io/$POLYGLOT_PROJECT_NAME/$BACKEND_SERVICE_NAME"
    gcloud builds submit --tag "$IMAGE_URL" --project "$POLYGLOT_PROJECT_NAME" .
    
    # Deploy to Cloud Run
    log_info "🌐 Deploying to Cloud Run service: $BACKEND_SERVICE_NAME..."
    gcloud run deploy "$BACKEND_SERVICE_NAME" \
        --image "$IMAGE_URL" \
        --region "$REGION" \
    log_info "🌐 Deploying to Cloud Run service: $BACKEND_SERVICE_NAME..."
    gcloud run deploy "$BACKEND_SERVICE_NAME" \
        --image "$IMAGE_URL" \
        --region "$REGION" \
        --platform managed \
        --allow-unauthenticated \
        --project "$POLYGLOT_PROJECT_NAME" \
        --set-env-vars="GOOGLE_CLOUD_PROJECT=$POLYGLOT_PROJECT_NAME,FORM_KITS_MODE=gcs,FORM_KITS_GCS_BUCKET=$FORM_KITS_BUCKET,FORM_KITS_REMOTE_PREFIX=$FORM_KITS_PREFIX"
        --project "$POLYGLOT_PROJECT_NAME" \
        --set-env-vars="GOOGLE_CLOUD_PROJECT=$POLYGLOT_PROJECT_NAME,FORM_KITS_MODE=gcs,FORM_KITS_GCS_BUCKET=$FORM_KITS_BUCKET,FORM_KITS_REMOTE_PREFIX=$FORM_KITS_PREFIX"
    
    BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE_NAME" --platform managed --region "$REGION" --project "$POLYGLOT_PROJECT_NAME" --format 'value(status.url)')
    log_success "✅ Backend deployed successfully!"
    BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE_NAME" --platform managed --region "$REGION" --project "$POLYGLOT_PROJECT_NAME" --format 'value(status.url)')
    log_success "✅ Backend deployed successfully!"
    echo "   URL: $BACKEND_URL"
    echo ""
    
    cd "$SCRIPT_DIR"
    cd "$SCRIPT_DIR"
fi

# ============================================================================
# FORM KITS DEPLOYMENT
# FORM KITS DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_FORM_KITS" = true ]; then
    log_info "═══════════════════════════════════════════════════════════"
    log_info "  DEPLOYING FORM KITS TO GCS"
    log_info "═══════════════════════════════════════════════════════════"
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
        
        if [ ! -f "$kit_dir/schema.json" ]; then
            log_warn "Skipping $kit_id - no schema.json found"
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
        
        if [ ! -f "$kit_dir/schema.json" ]; then
            continue
        fi
        
        # Extract title from schema.json
        label=$(grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' "$kit_dir/schema.json" | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/' || echo "$kit_id")
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
        
        manifest_content+='{"id":"'$kit_id'","label":"'$label'","schemaFile":"schema.json","schemaPath":"/'$FORM_KITS_PREFIX'/'$kit_id'/schema.json","pdfFile":"'$pdf_file'","pdfPath":"/'$FORM_KITS_PREFIX'/'$kit_id'/'$pdf_file'"}'
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
    # Upload all form kits
    log_info "📦 Uploading form kits..."
    for kit_dir in "$FORM_KITS_DIR"/*/; do
        [ -d "$kit_dir" ] || continue
        kit_id=$(basename "$kit_dir")
        
        if [ ! -f "$kit_dir/schema.json" ]; then
            log_warn "Skipping $kit_id - no schema.json found"
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
        
        if [ ! -f "$kit_dir/schema.json" ]; then
            continue
        fi
        
        # Extract title from schema.json
        label=$(grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' "$kit_dir/schema.json" | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/' || echo "$kit_id")
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
        
        manifest_content+='{"id":"'$kit_id'","label":"'$label'","schemaFile":"schema.json","schemaPath":"/'$FORM_KITS_PREFIX'/'$kit_id'/schema.json","pdfFile":"'$pdf_file'","pdfPath":"/'$FORM_KITS_PREFIX'/'$kit_id'/'$pdf_file'"}'
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
    
    # Build frontend
    log_info "📦 Building frontend..."
    npm run build
    
    # Deploy to Firebase Hosting
    log_info "🌐 Deploying to Firebase Hosting..."
    firebase deploy --only hosting --project "$POLYGLOT_PROJECT_NAME"
    
    log_success "✅ Frontend deployed successfully!"
    echo "   URL: https://$POLYGLOT_PROJECT_NAME.web.app"
    echo ""
    
    cd "$SCRIPT_DIR"
    cd "$SCRIPT_DIR"
fi

# ============================================================================
# DEPLOYMENT SUMMARY
# ============================================================================
echo ""
log_success "╔═══════════════════════════════════════════════════════════╗"
log_success "║         DEPLOYMENT COMPLETED SUCCESSFULLY                 ║"
log_success "╚═══════════════════════════════════════════════════════════╝"
log_success "╔═══════════════════════════════════════════════════════════╗"
log_success "║         DEPLOYMENT COMPLETED SUCCESSFULLY                 ║"
log_success "╚═══════════════════════════════════════════════════════════╝"
echo ""

if [ "$DEPLOY_BACKEND" = true ]; then
    log_info "🔧 Backend API:"
    echo "   $BACKEND_URL"
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
