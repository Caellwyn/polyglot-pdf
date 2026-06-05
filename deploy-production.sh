#!/bin/bash
# deploy-production.sh - Deploy to Business channel
#
# Usage: ./deploy-production.sh [options]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Verify account
echo -e "${GREEN}[INFO]${NC} 👀 Checking gcloud account..."
CURRENT_ACCOUNT=$(gcloud config get-value account)
if [[ "$CURRENT_ACCOUNT" != *"caellwynai.com"* ]]; then
  echo -e "${YELLOW}[WARN]${NC} Current account is $CURRENT_ACCOUNT. Need josh@caellwynai.com."
  gcloud auth login --update-adc
fi

# Configuration
export POLYGLOT_PROJECT_NAME="polyglot-forms-919f2"
export FORM_KITS_BUCKET="polyglot-pdf-form-kits"
export BACKEND_SERVICE_NAME="polyglot-backend"

echo -e "${GREEN}[INFO]${NC} 🚀 Deploying to Production (Business) Channel..."
echo -e "${GREEN}[INFO]${NC} Project: $POLYGLOT_PROJECT_NAME"

# Decide whether to deploy Firestore rules: only when the frontend is in scope
# (deploy-all.sh ships hosting only, and a project left on default-deny breaks
# email signup -- the unauth authorized_emails read -- and the users/{uid}
# profile sync on login). Skip on backend/form-kits-only runs, which do not touch
# the frontend.
DEPLOY_RULES=false
if [ $# -eq 0 ] || [ "$1" = "--all" ]; then
    DEPLOY_RULES=true
else
    for arg in "$@"; do
        [ "$arg" = "--frontend" ] && DEPLOY_RULES=true
    done
fi

# Deploy rules BEFORE deploy-all.sh so the new frontend never goes live against
# stale rules (firestore.rules, wired via firebase.json). The rules deploy is
# independent of the backend/form-kits stages deploy-all.sh also runs.
if [ "$DEPLOY_RULES" = true ]; then
    echo -e "${GREEN}[INFO]${NC} 🔒 Deploying Firestore rules to Firebase ($POLYGLOT_PROJECT_NAME)..."
    firebase deploy --only firestore:rules --project "$POLYGLOT_PROJECT_NAME"
fi

./deploy-all.sh "$@"
