#!/bin/bash
# setup-gcp-project.sh - Configure APIs and IAM for a new project
#
# Usage: ./scripts/setup-gcp-project.sh <PROJECT_ID>

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ID=$1
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}[ERROR]${NC} Usage: $0 <PROJECT_ID>"
    exit 1
fi

echo -e "${GREEN}[INFO]${NC} 🛠️  Setting up infrastructure for project: $PROJECT_ID"

# 1. Enable APIs
echo -e "${GREEN}[INFO]${NC} 📡 Enabling necessary APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    storage.googleapis.com \
    --project "$PROJECT_ID"

# 2. Create Service Account for Cloud Run
SA_NAME="polyglot-backend-sa"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" &>/dev/null; then
    echo -e "${GREEN}[INFO]${NC} 👤 Creating service account: $SA_NAME..."
    gcloud iam service-accounts create "$SA_NAME" \
        --display-name="Polyglot Backend Service Account" \
        --project "$PROJECT_ID"
else
    echo -e "${GREEN}[INFO]${NC} ✅ Service account $SA_NAME already exists"
fi

# 3. Assign IAM Roles
echo -e "${GREEN}[INFO]${NC} 🔑 Assigning IAM roles to service account..."
ROLES=(
    "roles/aiplatform.user"
    "roles/storage.objectViewer"
    "roles/logging.logWriter"
    # Firestore writer for the durable confirmation audit sink (bd
    # polyglot-pdf-z2is): CONFIRMATION_FIRESTORE_ENABLED=true makes the
    # backend mirror confirmation metadata to the confirmation_events
    # collection. Without this role every sink write 403s SILENTLY (the
    # writer logs-and-continues by design), so the liability trail stays
    # empty while the app looks healthy. Re-run this script against an
    # existing project to add the binding.
    "roles/datastore.user"
)

for role in "${ROLES[@]}"; do
    echo -e "${GREEN}[INFO]${NC}    Adding $role..."
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$role" \
        --condition=None > /dev/null
done

echo -e "${GREEN}[INFO]${NC} ✅ Infrastructure setup complete for $PROJECT_ID!"
echo -e "${GREEN}[INFO]${NC} Next step: Run ./deploy-demo.sh"
