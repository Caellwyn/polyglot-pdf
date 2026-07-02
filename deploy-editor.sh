#!/bin/bash
# deploy-editor.sh - Build + deploy the HOSTED schema editor to its own
# Firebase Hosting site (bd polyglot-pdf-92qe.4).
#
# The voice app and the editor are separate Hosting SITES in the same Firebase
# project: the voice app keeps its /api rewrite; the editor has NO rewrite (it
# calls Cloud Run directly via VITE_API_BASE_URL -- the Hosting rewrite's 60s
# cap would kill minutes-long extraction requests, so CORS_EXTRA_ORIGINS on the
# backend allows the editor origin instead).
#
# ONE-TIME setup (per project, before the first editor deploy):
#   1. Create the site (name is globally unique across Firebase):
#        firebase hosting:sites:create "$EDITOR_SITE" --project "$PROJECT"
#   2. Map BOTH deploy targets (the voice app keeps the default site):
#        firebase target:apply hosting app "$PROJECT" --project "$PROJECT"
#        firebase target:apply hosting editor "$EDITOR_SITE" --project "$PROJECT"
#      (Mappings persist in .firebaserc "targets"; this repo ships the demo
#      mapping already -- re-run target:apply only for a NEW project/site.)
#   3. Backend secrets + env (attach ONCE to the Cloud Run service; later
#      deploys preserve them, matching how GEMINI_API_KEY is wired):
#        printf '%s' '<editor code>' | gcloud secrets create schema-editor-token --data-file=- --project "$PROJECT"
#        printf '%s' '<author code>' | gcloud secrets create schema-author-token --data-file=- --project "$PROJECT"
#        gcloud run services update polyglot-backend --region us-central1 --project "$PROJECT" \
#          --set-secrets=SCHEMA_EDITOR_TOKEN=schema-editor-token:latest,SCHEMA_AUTHOR_TOKEN=schema-author-token:latest
#      CORS_EXTRA_ORIGINS + EXTRACTOR_MODEL ride the normal backend deploy env
#      (deploy-demo.sh exports them via BACKEND_EXTRA_ENV).
#   4. Bucket WRITE access for the editor surface (reads work today; saves 403
#      until granted). Resolve the service's RUNTIME identity first (on the
#      demo it is polyglot-backend-sa@...; a project that never set
#      BACKEND_SERVICE_ACCOUNT runs on the default compute SA,
#      <PROJECT_NUMBER>-compute@developer.gserviceaccount.com):
#        SA=$(gcloud run services describe polyglot-backend --region us-central1 \
#          --project "$PROJECT" --format='value(spec.template.spec.serviceAccountName)')
#        gcloud storage buckets add-iam-policy-binding "gs://$FORM_KITS_BUCKET" \
#          --member="serviceAccount:$SA" \
#          --role=roles/storage.objectAdmin --project "$PROJECT"
#
# Usage:
#   PROJECT=polyglot-demo-aa709 EDITOR_SITE=polyglot-editor-demo ./deploy-editor.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${PROJECT:-polyglot-demo-aa709}"
EDITOR_SITE="${EDITOR_SITE:-polyglot-editor-demo}"

echo "Building the hosted editor (mode hosted -> .env.hosted)..."
cd "$SCRIPT_DIR/schema-editor"
if [ ! -d node_modules ]; then npm install; fi
npm run build:hosted

echo "Deploying ONLY the editor hosting target to $PROJECT..."
cd "$SCRIPT_DIR"
firebase deploy --only "hosting:editor" --project "$PROJECT"

echo ""
echo "Hosted editor deployed: https://$EDITOR_SITE.web.app"
echo "Share that URL plus an access code with a contractor:"
echo "  - editor code  -> polish the provided forms"
echo "  - author code  -> also upload PDFs + run extraction"
