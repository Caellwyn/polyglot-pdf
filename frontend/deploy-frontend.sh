#!/bin/bash
# Deploy frontend bookmarklet to Google Cloud Storage CDN
# Requirements: gcloud CLI configured, VOICE_PROJECT_NAME and VOICE_GCS_BUCKET set

set -e

echo "🚀 Deploying Voice Form Filler Bookmarklet to CDN..."

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

# Build production bookmarklet
echo "📦 Building production bookmarklet..."
npm run build:bookmarklet

# Verify build output exists
if [ ! -f "dist/bookmarklet/bookmarklet.bundle.js" ]; then
    echo "❌ Error: Build output not found"
    exit 1
fi

# Get bundle size
BUNDLE_SIZE=$(du -h dist/bookmarklet/bookmarklet.bundle.js | cut -f1)
echo "📊 Bundle size: $BUNDLE_SIZE"

# Generate bookmarklet with updated SRI hash
echo "🔐 Generating bookmarklet with SRI hash..."
CDN_URL="https://storage.googleapis.com/$VOICE_GCS_BUCKET/bookmarklet/bookmarklet.bundle.js"
node scripts/generate-bookmarklet.js "dist/bookmarklet/bookmarklet.bundle.js" "$CDN_URL"

if [ ! -f "bookmarklet-output.json" ]; then
    echo "❌ Error: Bookmarklet generation failed"
    exit 1
fi

echo "✅ Bookmarklet generated with updated SRI hash"

# Upload to GCS with public read access using gcloud storage (newer tool)
echo "☁️  Uploading to gs://$VOICE_GCS_BUCKET/bookmarklet/..."
gcloud storage cp dist/bookmarklet/bookmarklet.bundle.js \
    gs://$VOICE_GCS_BUCKET/bookmarklet/bookmarklet.bundle.js \
    --cache-control="public, max-age=300"

# Make bucket contents publicly readable (uniform bucket-level access)
echo "🌐 Setting public access on bucket..."
gcloud storage buckets add-iam-policy-binding gs://$VOICE_GCS_BUCKET \
    --member=allUsers \
    --role=roles/storage.objectViewer \
    2>/dev/null || echo "⚠️  Public access already set or requires manual configuration"

# Upload install page if it exists
if [ -f "install-bookmarklet-production.html" ]; then
    echo "📄 Uploading install page..."
    gcloud storage cp install-bookmarklet-production.html \
        gs://$VOICE_GCS_BUCKET/bookmarklet/install.html \
        --cache-control="public, max-age=60"
fi

# Display CDN URLs
echo ""
echo "✅ Bookmarklet deployed successfully!"
echo ""
echo "📍 CDN URLs:"
echo "   Bookmarklet: https://storage.googleapis.com/$VOICE_GCS_BUCKET/bookmarklet/bookmarklet.bundle.js"
if [ -f "install-bookmarklet-production.html" ]; then
    echo "   Install Page: https://storage.googleapis.com/$VOICE_GCS_BUCKET/bookmarklet/install.html"
fi
echo ""
echo "⚠️  IMPORTANT: The install page needs manual update!"
echo ""
echo "📋 Copy the new bookmarklet from: bookmarklet-output.json"
echo "   Update the href= attribute in: install-bookmarklet-production.html"
echo ""
echo "💡 Next steps:"
echo "   1. Update install-bookmarklet-production.html with new bookmarklet code"
echo "   2. Re-run this script to deploy the updated install page"
echo "   3. Test installation on a sample web form"
echo "   4. Clear browser cache if reloading existing bookmarklet"
