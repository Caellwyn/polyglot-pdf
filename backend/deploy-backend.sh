#!/bin/bash
# Deploy backend to Google Cloud Run
# Requirements: gcloud CLI configured, VOICE_PROJECT_NAME set

set -e

echo "🚀 Deploying Voice Form Filler Backend to Cloud Run..."

# Verify environment
if [ -z "$VOICE_PROJECT_NAME" ]; then
    echo "❌ Error: VOICE_PROJECT_NAME not set"
    exit 1
fi

# Build and push container
echo "📦 Building container image..."
gcloud builds submit --tag gcr.io/$VOICE_PROJECT_NAME/voice-form-filler .

# Deploy to Cloud Run
echo "🌐 Deploying to Cloud Run..."
gcloud run deploy voice-form-filler \
    --image gcr.io/$VOICE_PROJECT_NAME/voice-form-filler \
    --region us-central1 \
    --platform managed \
    --allow-unauthenticated

echo "✅ Backend deployed successfully!  url: https://voice-form-filler-773443099751.us-central1.run.app"
