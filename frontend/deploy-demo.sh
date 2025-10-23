#!/bin/bash
# Deploy demo to Google Cloud Storage
# Requirements: gcloud CLI configured, VOICE_PROJECT_NAME and VOICE_GCS_BUCKET set

set -e

echo "🚀 Deploying Voice Form Filler Demo to GCS..."

# Verify environment
if [ -z "$VOICE_PROJECT_NAME" ]; then
    echo "❌ Error: VOICE_PROJECT_NAME not set"
    echo "   export VOICE_PROJECT_NAME=your-project-id"
    exit 1
fi

if [ -z "$VOICE_GCS_BUCKET" ]; then
    echo "❌ Error: VOICE_GCS_BUCKET not set"
    echo "   export VOICE_GCS_BUCKET=your-bucket-name"
    exit 1
fi

# Set production WebSocket URL
PROD_WS_URL="wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill"
echo "🔧 Building with WebSocket URL: $PROD_WS_URL"

# Check if VAD assets exist, download if not
if [ ! -d "public/vad-assets" ]; then
    echo "📦 VAD assets not found, downloading..."
    ./download-vad-assets.sh
else
    echo "✓ VAD assets found"
fi

# Build production demo with environment variables
echo "📦 Building production demo..."
# Note: Vite automatically uses .env.production in build mode
# We still pass VITE_WS_URL to override if needed
VITE_WS_URL="$PROD_WS_URL" VITE_GCS_BUCKET="$VOICE_GCS_BUCKET" npm run build:demo

# Verify build output exists
if [ ! -f "dist/demo/demo.html" ]; then
    echo "❌ Error: Build output not found"
    exit 1
fi

# Get bundle sizes
echo "📊 Bundle sizes:"
du -h dist/demo/demo.html | awk '{print "   demo.html: " $1}'
du -h dist/demo/assets/*.js | awk '{print "   " $2 ": " $1}'

# Upload to GCS (demo/ subfolder, won't touch bookmarklet/)
echo "☁️  Uploading to gs://$VOICE_GCS_BUCKET/demo/..."

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
# Note: Demo has its own copy of bookmarklet files (bundle + worklet)
# This keeps demo and bookmarklet distributions completely independent
gcloud storage cp -r dist/demo/bookmarklet \
    gs://$VOICE_GCS_BUCKET/demo/ \
    --cache-control="public, max-age=31536000"

# Upload VAD assets (ONNX models + WASM runtime) - self-hosted for reliability
# These were previously loaded from CDN, causing slow initialization on cloud
echo "📦 Uploading VAD assets (~12 MB)..."
if [ -d "dist/demo/vad-assets" ]; then
    gcloud storage cp -r dist/demo/vad-assets \
        gs://$VOICE_GCS_BUCKET/ \
        --cache-control="public, max-age=31536000"
    echo "✓ VAD assets uploaded (self-hosted, no CDN dependency)"
else
    echo "⚠️  Warning: VAD assets not found at dist/demo/vad-assets/"
    echo "   Run ./download-vad-assets.sh to download them first"
    echo "   They should be copied to dist/ during the build process"
fi

# Make bucket contents publicly readable (if not already set)
echo "🌐 Setting public access on bucket..."
gcloud storage buckets add-iam-policy-binding gs://$VOICE_GCS_BUCKET \
    --member=allUsers \
    --role=roles/storage.objectViewer \
    2>/dev/null || echo "✓ Public access already configured"

# Display URLs
echo ""
echo "✅ Demo deployed successfully!"
echo ""
echo "📍 Demo URL:"
echo "   https://storage.googleapis.com/$VOICE_GCS_BUCKET/demo/demo.html"
echo ""
echo "🔗 Share this URL to demo on mobile devices!"
echo ""
echo "⚙️  Backend: $PROD_WS_URL"
echo ""
echo "💡 Next steps:"
echo "   1. Open the URL on your mobile device"
echo "   2. Test form loading and overlay appearance"
echo "   3. Click 'Connect to Voice' and test voice input"
echo "   4. Verify all 174 fields are detected"
echo ""
echo "📝 Note: Bookmarklet remains untouched at gs://$VOICE_GCS_BUCKET/bookmarklet/"
