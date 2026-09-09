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
# Epic 2 bead B5 (plan: "Refund on unopened expiry") adds the hourly
# expired-link sweep's Cloud Scheduler job declaration at the bottom of this
# script -- see that section for why it is DECLARED here but not RUN by
# this script (or any deploy script): creating the job needs the admin
# service's OWN Cloud Run URL, which does not exist until after that
# service's first deploy. Pinned by tests/test_setup_admin_service_
# scheduler.py, the sibling of tests/test_setup_firestore_ttl_script.py --
# an OPERATOR script, so the only mechanical guard is the shipped script
# TEXT.
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
# cloudscheduler: enabled HERE, with its first consumer (Epic 2 bead B5's
# hourly expired-link sweep job, declared at the bottom of this script) --
# an API enabled ahead of its caller is the same unused-surface risk as an
# unused IAM grant. Pub/Sub is NOT enabled here yet; it arrives with ITS
# first consumer (Epic 4 4.3).
echo -e "${GREEN}[INFO]${NC} Enabling APIs..."
gcloud services enable \
    run.googleapis.com \
    identitytoolkit.googleapis.com \
    firestore.googleapis.com \
    secretmanager.googleapis.com \
    cloudscheduler.googleapis.com \
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

# 5. Cloud Scheduler: the hourly expired-link refund sweep (Epic 2 bead B5,
# plan: "Refund on unopened expiry").
#
# A SEPARATE service account from admin-backend-sa, on purpose. admin-
# backend-sa is the CALLEE identity (what the admin service RUNS as);
# require_google_oidc's whole point is pinning a DIFFERENT identity as the
# CALLER (admin_backend/services/admin_auth.py's "WHY AUDIENCE ALONE DOES
# NOT PROVE THE CALLER" -- audience alone is forgeable by anyone with a GCP
# project, so the token's own `email` claim must name a caller this route
# actually expects). Reusing admin-backend-sa as the caller too would still
# work mechanically, but would mean a single compromised credential is both
# "can act as the admin service" and "can trigger the admin service" --
# two capabilities this split keeps apart everywhere else in this file.
SCHEDULER_SA_NAME="admin-sweep-scheduler-sa"
SCHEDULER_SA_EMAIL="$SCHEDULER_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$SCHEDULER_SA_EMAIL" --project "$PROJECT_ID" &>/dev/null; then
    echo -e "${GREEN}[INFO]${NC} Creating service account: $SCHEDULER_SA_NAME..."
    gcloud iam service-accounts create "$SCHEDULER_SA_NAME" \
        --display-name="Admin Sweep Cloud Scheduler Caller" \
        --project "$PROJECT_ID"
else
    echo -e "${GREEN}[INFO]${NC} Service account $SCHEDULER_SA_NAME already exists"
fi

# NOT run here: creating the job needs the admin service's OWN Cloud Run
# URL, which is assigned by Google at first deploy and is therefore not
# knowable until AFTER deploy-admin.sh has run at least once. This is
# DECLARATION, not execution -- an operator runs the command below by hand,
# once, after the first successful admin-service deploy, substituting the
# real URL for $ADMIN_SERVICE_URL. tests/test_setup_admin_service_
# scheduler.py pins this exact command's shape (job name, schedule, method,
# and the two --oidc-* flags), not that it ever ran.
#
# --oidc-service-account-email: the caller identity above -- Cloud
# Scheduler mints a Google-signed OIDC token with THIS account's email as
# the token's `email` claim, which is exactly what SWEEP_SCHEDULER_SA_EMAIL
# (the admin service's own env var, read by admin_backend/routes/
# sweep_routes.py) must be set to for the route to accept it.
# --oidc-token-audience: the route's own URL -- what ADMIN_SERVICE_URL on
# the admin service must be set to, and what require_google_oidc checks the
# token's `aud` claim against.
# --uri: the FULL sweep route path, not just the service root -- Cloud Run
# accepts the OIDC token for the whole service, but the route itself only
# ever gets called at this one path.
# --http-method POST: matches the route's own @router.post decorator.
# --schedule "0 * * * *": hourly, on the hour, matching the plan ("Refund
# on unopened expiry": "an hourly sweep").
echo -e "${YELLOW}[NOTE]${NC} After the admin service's FIRST deploy, create the hourly sweep job:"
echo -e "${YELLOW}[NOTE]${NC}"
echo -e "${YELLOW}[NOTE]${NC}   gcloud scheduler jobs create http admin-sweep-expired-links \\"
echo -e "${YELLOW}[NOTE]${NC}     --project=\"$PROJECT_ID\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --location=us-central1 \\"
echo -e "${YELLOW}[NOTE]${NC}     --schedule=\"0 * * * *\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --uri=\"\$ADMIN_SERVICE_URL/admin/links/sweep-expired\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --http-method=POST \\"
echo -e "${YELLOW}[NOTE]${NC}     --oidc-service-account-email=\"$SCHEDULER_SA_EMAIL\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --oidc-token-audience=\"\$ADMIN_SERVICE_URL/admin/links/sweep-expired\""
echo -e "${YELLOW}[NOTE]${NC}"
echo -e "${YELLOW}[NOTE]${NC} Then set on the admin service (redeploy or update-env-vars):"
echo -e "${YELLOW}[NOTE]${NC}   ADMIN_SERVICE_URL=\$ADMIN_SERVICE_URL"
echo -e "${YELLOW}[NOTE]${NC}   SWEEP_SCHEDULER_SA_EMAIL=$SCHEDULER_SA_EMAIL"
