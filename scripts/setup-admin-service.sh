#!/bin/bash
# setup-admin-service.sh - Provision the PRIVILEGED admin service account.
#
# Sibling of scripts/setup-gcp-project.sh, which provisions the PUBLIC
# backend's narrow polyglot-backend-sa. This one provisions admin-backend-sa,
# the identity behind the Cloud Run service polyglot-admin (package
# admin_backend/). Sprint 22 Epic 1, plan
# docs/sprint_22_admin-console_plan.md ("Admin service").
#
# WHY TWO SERVICE ACCOUNTS. CLAUDE.md scar #7: a mock cannot tell you the real
# dependency is forbidden. The public backend deliberately CANNOT call
# Firebase Auth beyond verifying a token signature, so a privileged call added
# there fails on the first request in production. Keeping every privileged
# call in a separate package behind a separate identity is what preserves that
# property while still letting the admin console do admin things.
#
# ROLE CHANGES ARE A DELIBERATE ACT. The two arrays below are pinned by
# admin_backend/tests/unit/test_admin_sa_iam_envelope.py, which parses THIS
# file. Adding a role here without adding it to that test's constant fails
# CI -- on purpose, so a widening is reviewed rather than noticed later.
#
# Usage: ./scripts/setup-admin-service.sh <PROJECT_ID> [FORM_KITS_BUCKET]
#
# Idempotent: re-run it against an existing project to add a new binding.
# NOT run by any deploy script -- an operator runs it by hand, under their own
# gcloud credentials, when the project or the role set changes.

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ID=$1
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}[ERROR]${NC} Usage: $0 <PROJECT_ID> [FORM_KITS_BUCKET]"
    exit 1
fi

# The shared form-kit store. storage.objectAdmin is granted on THIS BUCKET
# ONLY, never project-wide -- see BUCKET_ROLES below.
FORM_KITS_BUCKET="${2:-${PROJECT_ID}-form-kits}"

echo -e "${GREEN}[INFO]${NC} Setting up the admin service for project: $PROJECT_ID"

# 1. APIs the admin service needs beyond what setup-gcp-project.sh enables.
#
# identitytoolkit: every Firebase Auth ADMIN call (create/disable a user, set
# a custom claim) goes through it. The public backend never touches it -- that
# is the whole point of the split.
#
# Cloud Scheduler and Pub/Sub are NOT enabled here yet. They arrive with their
# first consumers (Epic 2 B5, Epic 4 4.3); an API enabled ahead of its caller
# is the same unused-surface risk as an unused IAM grant.
echo -e "${GREEN}[INFO]${NC} Enabling APIs..."
gcloud services enable \
    run.googleapis.com \
    identitytoolkit.googleapis.com \
    firestore.googleapis.com \
    secretmanager.googleapis.com \
    --project "$PROJECT_ID"

# 2. The service account.
SA_NAME="admin-backend-sa"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" &>/dev/null; then
    echo -e "${GREEN}[INFO]${NC} Creating service account: $SA_NAME..."
    gcloud iam service-accounts create "$SA_NAME" \
        --display-name="Polyglot Admin Service Account" \
        --project "$PROJECT_ID"
else
    echo -e "${GREEN}[INFO]${NC} Service account $SA_NAME already exists"
fi

# 3. PROJECT-level roles. Each carries the one call that needs it.
#
# DEFERRED, deliberately absent until the epic that first calls them:
#   Epic 4 (deploy control plane): roles/cloudbuild.builds.editor +
#     roles/iam.serviceAccountUser on the Cloud Build SA, roles/run.admin +
#     roles/iam.serviceAccountUser on polyglot-backend-sa (resource-scoped),
#     roles/firebasehosting.admin.
#   Epic 3 (telemetry): roles/bigquery.jobUser + dataset-scoped
#     roles/bigquery.dataViewer, roles/errorreporting.viewer,
#     roles/monitoring.viewer.
# An unused grant is its own risk; the pin test fails if one appears early.
PROJECT_ROLES=(
    # Firebase Auth admin: create and disable users, and stamp the app_admin
    # and firm_role custom claims. THIS is the permission polyglot-backend-sa
    # deliberately lacks (scar #7) and the reason this identity exists.
    "roles/firebaseauth.admin"
    # Firestore reads and writes: firms, the credit ledger, kits, links,
    # admin_audit_log, deployments, app_config.
    "roles/datastore.user"
    # Structured logs to Cloud Logging, same as the public backend.
    "roles/logging.logWriter"
    # Read the email-provider API key (and the link-signing secret) out of
    # Secret Manager. Cloud Run refuses a revision whose runtime SA cannot
    # read a bound secret, so this fails LOUDLY at deploy time, not silently.
    "roles/secretmanager.secretAccessor"
)

echo -e "${GREEN}[INFO]${NC} Assigning project-level IAM roles..."
for role in "${PROJECT_ROLES[@]}"; do
    echo -e "${GREEN}[INFO]${NC}    Adding $role..."
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$role" \
        --condition=None > /dev/null
done

# 4. RESOURCE-scoped roles. Granted on one bucket, never project-wide.
#
# The scope is the security-relevant half: objectAdmin at the project level
# would hand the admin service write access to every bucket in the project,
# and no test keyed on the role NAME alone would notice. The pin test asserts
# both that these appear here and that they do NOT appear in PROJECT_ROLES.
BUCKET_ROLES=(
    # Publish and retire form kits in the shared form-kits bucket. The public
    # backend holds only roles/storage.objectViewer on the same bucket.
    "roles/storage.objectAdmin"
)

echo -e "${GREEN}[INFO]${NC} Assigning bucket-scoped IAM roles on gs://$FORM_KITS_BUCKET..."
for role in "${BUCKET_ROLES[@]}"; do
    echo -e "${GREEN}[INFO]${NC}    Adding $role on gs://$FORM_KITS_BUCKET..."
    gcloud storage buckets add-iam-policy-binding "gs://$FORM_KITS_BUCKET" \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$role" \
        --project "$PROJECT_ID" > /dev/null
done

echo -e "${GREEN}[INFO]${NC} Admin service account ready: $SA_EMAIL"
echo -e "${YELLOW}[NOTE]${NC} Deploy the admin service with the SHARED image and"
echo -e "${YELLOW}[NOTE]${NC} APP_MODULE=admin_backend.main:app plus --service-account $SA_EMAIL."
