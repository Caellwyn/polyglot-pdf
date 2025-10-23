#!/bin/bash
# Deploy both backend and frontend (demo) to Google Cloud
# Requirements: gcloud CLI configured, VOICE_PROJECT_NAME and VOICE_GCS_BUCKET set
#
# Usage:
#   ./deploy-all.sh             # Deploy both backend and frontend
#   ./deploy-all.sh backend     # Deploy backend only
#   ./deploy-all.sh frontend    # Deploy frontend only
#   ./deploy-all.sh demo        # Deploy frontend only (alias)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored message
print_info() { echo -e "${BLUE}$1${NC}"; }
print_success() { echo -e "${GREEN}$1${NC}"; }
print_warning() { echo -e "${YELLOW}$1${NC}"; }
print_error() { echo -e "${RED}$1${NC}"; }

# Print header
echo ""
print_info "╔════════════════════════════════════════════════════════════╗"
print_info "║     Voice Form Filler - Combined Deployment Script        ║"
print_info "╚════════════════════════════════════════════════════════════╝"
echo ""

# Parse arguments
DEPLOY_BACKEND=true
DEPLOY_FRONTEND=true

if [ "$1" = "backend" ]; then
    DEPLOY_FRONTEND=false
elif [ "$1" = "frontend" ] || [ "$1" = "demo" ]; then
    DEPLOY_BACKEND=false
fi

# Verify environment variables
ENV_ERROR=false

if [ -z "$VOICE_PROJECT_NAME" ]; then
    print_error "❌ Error: VOICE_PROJECT_NAME not set"
    echo "   export VOICE_PROJECT_NAME=your-project-id"
    ENV_ERROR=true
fi

if [ "$DEPLOY_FRONTEND" = true ] && [ -z "$VOICE_GCS_BUCKET" ]; then
    print_error "❌ Error: VOICE_GCS_BUCKET not set (required for frontend deployment)"
    echo "   export VOICE_GCS_BUCKET=your-bucket-name"
    ENV_ERROR=true
fi

if [ "$ENV_ERROR" = true ]; then
    exit 1
fi

# Display deployment plan
echo ""
print_info "📋 Deployment Plan:"
if [ "$DEPLOY_BACKEND" = true ]; then
    echo "   ✓ Backend (Cloud Run)"
fi
if [ "$DEPLOY_FRONTEND" = true ]; then
    echo "   ✓ Frontend Demo (GCS)"
fi
echo ""
echo "   Project: $VOICE_PROJECT_NAME"
if [ "$DEPLOY_FRONTEND" = true ]; then
    echo "   Bucket: $VOICE_GCS_BUCKET"
fi
echo ""

# Confirmation prompt
read -p "Continue with deployment? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Deployment cancelled."
    exit 0
fi

echo ""

# ============================================================================
# BACKEND DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_BACKEND" = true ]; then
    print_info "════════════════════════════════════════════════════════════"
    print_info "  DEPLOYING BACKEND TO CLOUD RUN"
    print_info "════════════════════════════════════════════════════════════"
    echo ""
    
    cd backend
    
    # Build and push container
    print_info "📦 Building container image..."
    gcloud builds submit --tag gcr.io/$VOICE_PROJECT_NAME/voice-form-filler .
    
    # Deploy to Cloud Run
    print_info "🌐 Deploying to Cloud Run..."
    gcloud run deploy voice-form-filler \
        --image gcr.io/$VOICE_PROJECT_NAME/voice-form-filler \
        --region us-central1 \
        --platform managed \
        --allow-unauthenticated
    
    BACKEND_URL="https://voice-form-filler-773443099751.us-central1.run.app"
    print_success "✅ Backend deployed successfully!"
    echo "   URL: $BACKEND_URL"
    echo ""
    
    cd ..
fi

# ============================================================================
# FRONTEND DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_FRONTEND" = true ]; then
    print_info "════════════════════════════════════════════════════════════"
    print_info "  DEPLOYING FRONTEND DEMO TO GOOGLE CLOUD STORAGE"
    print_info "════════════════════════════════════════════════════════════"
    echo ""
    
    cd frontend
    
    # Set production WebSocket URL
    PROD_WS_URL="wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill"
    print_info "🔧 Building with WebSocket URL: $PROD_WS_URL"
    echo ""
    
    # Check if VAD assets exist, download if not
    if [ ! -d "public/vad-assets" ]; then
        print_warning "📦 VAD assets not found, downloading..."
        if [ -f "./download-vad-assets.sh" ]; then
            ./download-vad-assets.sh
        else
            print_warning "⚠️  download-vad-assets.sh not found - skipping VAD assets"
        fi
    else
        print_success "✓ VAD assets found"
    fi
    
    # Build production demo with environment variables
    print_info "📦 Building production demo..."
    # Note: Vite automatically uses .env.production in build mode
    # We still pass VITE_WS_URL to override if needed
    VITE_WS_URL="$PROD_WS_URL" VITE_GCS_BUCKET="$VOICE_GCS_BUCKET" npm run build:demo
    
    # Verify build output exists
    if [ ! -f "dist/demo/demo.html" ]; then
        print_error "❌ Error: Build output not found"
        exit 1
    fi
    
    # Get bundle sizes
    print_info "📊 Bundle sizes:"
    du -h dist/demo/demo.html | awk '{print "   demo.html: " $1}'
    du -h dist/demo/assets/*.js 2>/dev/null | awk '{print "   " $2 ": " $1}' || true
    echo ""
    
    # Upload to GCS (demo/ subfolder, won't touch bookmarklet/)
    print_info "☁️  Uploading to gs://$VOICE_GCS_BUCKET/demo/..."
    
    # Upload HTML files with short cache (content changes)
    gcloud storage cp dist/demo/demo.html \
        gs://$VOICE_GCS_BUCKET/demo/demo.html \
        --cache-control="public, max-age=300"
    
    gcloud storage cp dist/demo/adult_intake_demo.html \
        gs://$VOICE_GCS_BUCKET/demo/adult_intake_demo.html \
        --cache-control="public, max-age=300"
    
    gcloud storage cp dist/demo/adult_intake_demo_schema.json \
        gs://$VOICE_GCS_BUCKET/demo/adult_intake_demo_schema.json \
        --cache-control="public, max-age=300"
    
    gcloud storage cp dist/demo/adult_intake_sections_index.json \
        gs://$VOICE_GCS_BUCKET/demo/adult_intake_sections_index.json \
        --cache-control="public, max-age=300"
    
    # Upload thank-you page and logo
    gcloud storage cp dist/demo/thank-you.html \
        gs://$VOICE_GCS_BUCKET/demo/thank-you.html \
        --cache-control="public, max-age=300"
    
    gcloud storage cp dist/demo/logo_with_text.png \
        gs://$VOICE_GCS_BUCKET/demo/logo_with_text.png \
        --cache-control="public, max-age=31536000"
    
    # Upload JS assets with long cache (content-hashed filenames)
    gcloud storage cp -r dist/demo/assets \
        gs://$VOICE_GCS_BUCKET/demo/ \
        --cache-control="public, max-age=31536000"
    
    # Upload shared audio worklet (needed for microphone recording)
    gcloud storage cp -r dist/shared \
        gs://$VOICE_GCS_BUCKET/ \
        --cache-control="public, max-age=31536000"
    
    # Upload bookmarklet bundle (needed by demo)
    gcloud storage cp -r dist/demo/bookmarklet \
        gs://$VOICE_GCS_BUCKET/demo/ \
        --cache-control="public, max-age=31536000"
    
    # Upload VAD assets (ONNX models + WASM runtime) - self-hosted for reliability
    print_info "📦 Uploading VAD assets (~5 MB)..."
    if [ -d "public/vad-assets" ]; then
        gcloud storage cp -r public/vad-assets \
            gs://$VOICE_GCS_BUCKET/ \
            --cache-control="public, max-age=31536000"
        print_success "✓ VAD assets uploaded (self-hosted, no CDN dependency)"
    else
        print_warning "⚠️  Warning: VAD assets not found at public/vad-assets/"
        echo "   Run ./download-vad-assets.sh to download them"
    fi
    
    # Make bucket contents publicly readable (if not already set)
    print_info "🌐 Setting public access on bucket..."
    gcloud storage buckets add-iam-policy-binding gs://$VOICE_GCS_BUCKET \
        --member=allUsers \
        --role=roles/storage.objectViewer \
        2>/dev/null || print_success "✓ Public access already configured"
    
    DEMO_URL="https://storage.googleapis.com/$VOICE_GCS_BUCKET/demo/demo.html"
    print_success "✅ Demo deployed successfully!"
    echo "   URL: $DEMO_URL"
    echo ""
    
    cd ..
fi

# ============================================================================
# DEPLOYMENT SUMMARY
# ============================================================================
echo ""
print_success "╔════════════════════════════════════════════════════════════╗"
print_success "║              DEPLOYMENT COMPLETED SUCCESSFULLY             ║"
print_success "╚════════════════════════════════════════════════════════════╝"
echo ""

if [ "$DEPLOY_BACKEND" = true ]; then
    print_info "🔧 Backend API:"
    echo "   https://voice-form-filler-773443099751.us-central1.run.app"
    echo ""
fi

if [ "$DEPLOY_FRONTEND" = true ]; then
    print_info "🌐 Demo URL:"
    echo "   https://storage.googleapis.com/$VOICE_GCS_BUCKET/demo/demo.html"
    echo ""
    print_info "🔗 Share this URL to demo on mobile devices!"
    echo ""
fi

print_info "💡 Next steps:"
if [ "$DEPLOY_FRONTEND" = true ]; then
    echo "   1. Open the demo URL on your mobile device"
    echo "   2. Test form loading and overlay appearance"
    echo "   3. Click 'Connect to Voice' and test voice input"
    echo "   4. Verify all 174 fields are detected"
fi
if [ "$DEPLOY_BACKEND" = true ] && [ "$DEPLOY_FRONTEND" = false ]; then
    echo "   1. Test backend health: curl https://voice-form-filler-773443099751.us-central1.run.app/health"
    echo "   2. Check WebSocket endpoint is available"
    echo "   3. Deploy frontend to complete the update"
fi
echo ""

if [ "$DEPLOY_FRONTEND" = true ]; then
    print_info "📝 Note: Bookmarklet remains untouched at gs://$VOICE_GCS_BUCKET/bookmarklet/"
fi

echo ""
