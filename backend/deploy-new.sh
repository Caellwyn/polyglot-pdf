#!/bin/bash
# Deploy a NEW backend service to Google Cloud Run
# Usage: ./deploy-new.sh [SERVICE_NAME]

set -e

# Default service name
SERVICE_NAME=${1:-polyglot-backend}
REGION="us-central1"

echo "🚀 Preparing to deploy service: $SERVICE_NAME"

# Check for VOICE_PROJECT_NAME env var
if [ -z "$VOICE_PROJECT_NAME" ]; then
    echo "⚠️  VOICE_PROJECT_NAME not set. Trying to detect from gcloud config..."
    VOICE_PROJECT_NAME=$(gcloud config get-value project)
    if [ -z "$VOICE_PROJECT_NAME" ]; then
        echo "❌ Error: Could not determine project ID. Please set VOICE_PROJECT_NAME or run 'gcloud config set project <PROJECT_ID>'."
        exit 1
    fi
    echo "✅ Using project: $VOICE_PROJECT_NAME"
fi

# Enable necessary APIs (just in case)
echo "🛠️  Ensuring Cloud Run and Build APIs are enabled..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# Build and push container
echo "📦 Building container image..."
IMAGE_URL="gcr.io/$VOICE_PROJECT_NAME/$SERVICE_NAME"
gcloud builds submit --tag $IMAGE_URL .

# Deploy to Cloud Run
echo "🌐 Deploying to Cloud Run service: $SERVICE_NAME..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_URL \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=$VOICE_PROJECT_NAME"

echo "✅ Deployment Complete!"
echo "Service URL: $(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')"
echo "Next Step: Ensure your firebase.json points to serviceId: '$SERVICE_NAME'"
