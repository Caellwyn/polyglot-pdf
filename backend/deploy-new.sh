#!/bin/bash
# Deploy a NEW backend service to Google Cloud Run
# Usage: ./deploy-new.sh [SERVICE_NAME]

set -e

# Default service name
SERVICE_NAME=${1:-polyglot-backend}
PROJECT_ID_ARG=$2
REGION="us-central1"

echo "🚀 Preparing to deploy service: $SERVICE_NAME"

# Determine Project ID
if [ -n "$PROJECT_ID_ARG" ]; then
    POLYGLOT_PROJECT_NAME=$PROJECT_ID_ARG
    echo "✅ Using provided project ID: $POLYGLOT_PROJECT_NAME"
elif [ -z "$POLYGLOT_PROJECT_NAME" ]; then
    echo "⚠️  POLYGLOT_PROJECT_NAME not set. Trying to detect from gcloud config..."
    POLYGLOT_PROJECT_NAME=$(gcloud config get-value project)
    if [ -z "$POLYGLOT_PROJECT_NAME" ]; then
        echo "❌ Error: Could not determine project ID. Please set POLYGLOT_PROJECT_NAME or provide it as the second argument."
        exit 1
    fi
    echo "✅ Using detected project: $POLYGLOT_PROJECT_NAME"
else
    echo "✅ Using env var project: $POLYGLOT_PROJECT_NAME"
fi

# Enable necessary APIs (just in case)
echo "🛠️  Ensuring Cloud Run and Build APIs are enabled..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project $POLYGLOT_PROJECT_NAME

# Build and push container -- from the REPO ROOT (bd 92qe.3): the Dockerfile
# lives at the root so the image includes scripts/authoring + scripts/bakeoff
# (the hosted extraction pipeline). .gcloudignore keeps the upload lean.
echo "📦 Building container image (repo-root context)..."
IMAGE_URL="gcr.io/$POLYGLOT_PROJECT_NAME/$SERVICE_NAME"
REPO_ROOT="$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")"
gcloud builds submit --tag $IMAGE_URL --project $POLYGLOT_PROJECT_NAME "$REPO_ROOT"

# Deploy to Cloud Run
echo "🌐 Deploying to Cloud Run service: $SERVICE_NAME..."
# --timeout: Cloud Run kills any request at this limit, including live
# WebSockets; the 300s default terminated every /ws/fill session at exactly
# 5 minutes (bd polyglot-pdf-9w5k). 3600s is the Cloud Run maximum.
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_URL \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --timeout=3600 \
    --project $POLYGLOT_PROJECT_NAME \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=$POLYGLOT_PROJECT_NAME"

echo "✅ Deployment Complete!"
echo "Service URL: $(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --project $POLYGLOT_PROJECT_NAME --format 'value(status.url)')"
echo "Next Step: Ensure your firebase.json points to serviceId: '$SERVICE_NAME'"
