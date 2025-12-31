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

./deploy-all.sh "$@"
