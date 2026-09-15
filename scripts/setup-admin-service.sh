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
# roles/iam.serviceAccountUser on polyglot-cloudbuild-sa (bead
# polyglot-pdf-p4ale, E4.5) moved OUT of the deferred set below and into a
# resource-scoped grant of its own (step 3b) -- it is the actAs binding the
# admin service's trigger route needs to submit a build that runs AS the
# Cloud Build SA (`builds.create`, admin_backend/services/cloud_build.py,
# bead 4.3). roles/cloudbuild.builds.editor for that same route is still
# DEFERRED: it lands with bead 4.3 itself, the first (and only) caller.
#
# run.admin and firebasehosting.admin are DELETED from the deferred list
# entirely, not merely left deferred: the admin service never deploys
# anything directly -- Cloud Build does the deploying (polyglot-cloudbuild-sa
# holds both roles, see scripts/setup-cloud-build.sh) -- so there is no
# future epic that grants either to admin-backend-sa. A role with no future
# consumer is a dead expectation, and the pin test below only checks for
# roles the plan still intends to grant.
#
# STILL DEFERRED, absent until the epic that first calls them:
#   Bead 4.3 (admin_backend/services/cloud_build.py, not yet built):
#     roles/cloudbuild.builds.editor (triggers/submits the build itself).
# An unused grant is its own risk; the pin test fails if one appears early.
#
# roles/bigquery.jobUser + dataset-scoped roles/bigquery.dataViewer are NOT
# deferred and NOT granted here -- Epic 3 bead 6 (E3.6) grants them from
# scripts/setup-telemetry.sh instead, alongside the polyglot_telemetry
# dataset that roles/bigquery.dataViewer is scoped to. admin_backend/tests/
# unit/test_admin_sa_iam_envelope.py's EXPECTED_ADMIN_SA_ROLES pin includes
# both roles for the full envelope, but subtracts them back out
# (TELEMETRY_GRANTED_ROLES) before comparing against THIS script's
# PROJECT_ROLES array, and a separate pair of tests reads
# setup-telemetry.sh directly for the grants themselves.
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
    # Submit/trigger a Cloud Build (bd polyglot-pdf-tb3kp, E4.3 --
    # admin_backend/services/cloud_build.py's run_target(), calling
    # CloudBuildClient.run_build_trigger). This is the role's FIRST real
    # consumer, moved here (not left deferred) in the same commit that adds
    # the route that calls it -- admin_backend/tests/unit/
    # test_admin_sa_iam_envelope.py's EXPECTED_ADMIN_SA_ROLES pin includes it.
    "roles/cloudbuild.builds.editor"
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

# 5. actAs on polyglot-cloudbuild-sa: admin-backend-sa may submit a build
# that RUNS AS the Cloud Build SA (bead 4.3's `builds.create` trigger route,
# admin_backend/services/cloud_build.py). Granted with `gcloud iam
# service-accounts add-iam-policy-binding` on the TARGET SA (the resource),
# never `gcloud projects add-iam-policy-binding` -- a project-level grant of
# this role would let admin-backend-sa impersonate every service account in
# the project, not just the one build identity it is allowed to submit
# builds as. Kept in its own array (not folded into PROJECT_ROLES) for the
# same reason BUCKET_ROLES is separate: the SCOPE, not just the role name,
# is what the pin test asserts.
CLOUD_BUILD_SA="polyglot-cloudbuild-sa@$PROJECT_ID.iam.gserviceaccount.com"
CLOUD_BUILD_SA_ROLES=(
    "roles/iam.serviceAccountUser"
)

echo -e "${GREEN}[INFO]${NC} Assigning actAs on $CLOUD_BUILD_SA..."
for role in "${CLOUD_BUILD_SA_ROLES[@]}"; do
    echo -e "${GREEN}[INFO]${NC}    Adding $role on $CLOUD_BUILD_SA..."
    gcloud iam service-accounts add-iam-policy-binding "$CLOUD_BUILD_SA" \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$role" \
        --project "$PROJECT_ID" > /dev/null
done

# 6. Pub/Sub: Cloud Build's build-status notifications (bd polyglot-pdf-tb3kp,
# E4.3). Cloud Build publishes to the "cloud-builds" topic AUTOMATICALLY on
# every build state change once the topic exists and pubsub.googleapis.com
# is enabled -- this script only needs to create the topic (idempotent) and
# wire ONE push subscription from it to the admin service's webhook route
# (POST /api/deploys/webhook, admin_backend/routes/deploy_webhook.py).
#
# roles/iam.serviceAccountTokenCreator for the Pub/Sub service agent (so it
# can MINT the OIDC token the push subscription presents) is granted by
# scripts/setup-cloud-build.sh, NOT here (bead polyglot-pdf-p4ale, E4.5 --
# see that script's own "5. The Pub/Sub service agent" section and
# admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py's
# test_pubsub_service_agent_gets_token_creator_for_the_build_webhook,
# which already pins it there). Granting it a SECOND time here would not be
# wrong, but it would duplicate a grant this repo's own test suite already
# treats as owned by the other script -- one home per grant (CLAUDE.md
# scar #8).
echo -e "${GREEN}[INFO]${NC} Enabling Pub/Sub API..."
gcloud services enable pubsub.googleapis.com --project "$PROJECT_ID"

CLOUD_BUILDS_TOPIC="cloud-builds"
if ! gcloud pubsub topics describe "$CLOUD_BUILDS_TOPIC" --project "$PROJECT_ID" &>/dev/null; then
    echo -e "${GREEN}[INFO]${NC} Creating Pub/Sub topic: $CLOUD_BUILDS_TOPIC..."
    gcloud pubsub topics create "$CLOUD_BUILDS_TOPIC" --project "$PROJECT_ID"
else
    echo -e "${GREEN}[INFO]${NC} Pub/Sub topic $CLOUD_BUILDS_TOPIC already exists"
fi

# The push subscription's OWN caller identity -- a THIRD service account,
# separate from both admin-backend-sa (this script's own SA, the WEBHOOK'S
# callee identity) and polyglot-cloudbuild-sa (the BUILD identity,
# scripts/setup-cloud-build.sh). require_google_oidc's whole point is
# pinning a caller identity DIFFERENT from the service it calls -- reusing
# admin-backend-sa here would mean the service could mint tokens accepted
# by its OWN gate, collapsing the two-factor check to "does the request
# carry any Google-signed token at all". Same reasoning as
# admin-sweep-scheduler-sa above, one section up.
PUBSUB_PUSH_SA_NAME="admin-pubsub-push-sa"
PUBSUB_PUSH_SA_EMAIL="$PUBSUB_PUSH_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$PUBSUB_PUSH_SA_EMAIL" --project "$PROJECT_ID" &>/dev/null; then
    echo -e "${GREEN}[INFO]${NC} Creating service account: $PUBSUB_PUSH_SA_NAME..."
    gcloud iam service-accounts create "$PUBSUB_PUSH_SA_NAME" \
        --display-name="Admin Pub/Sub Push Caller (Cloud Build webhook)" \
        --project "$PROJECT_ID"
else
    echo -e "${GREEN}[INFO]${NC} Service account $PUBSUB_PUSH_SA_NAME already exists"
fi

# NOT run here: creating the push subscription needs the admin service's
# OWN Cloud Run URL, unknown until after its FIRST deploy -- same reason
# the sweep job's gcloud scheduler command above is a printed NOTE, not an
# executed one. --push-auth-service-account is what makes Pub/Sub mint an
# OIDC token as PUBSUB_PUSH_SA_EMAIL on every push (the identity
# PUBSUB_PUSH_SA_EMAIL, the admin service's own env var, must be set to);
# --push-auth-token-audience is the route's own URL (service root + path),
# matching require_google_oidc's audience check
# (admin_backend/routes/deploy_webhook.py's own _audience()).
echo -e "${YELLOW}[NOTE]${NC} After the admin service's FIRST deploy, create the build-status push subscription:"
echo -e "${YELLOW}[NOTE]${NC}"
echo -e "${YELLOW}[NOTE]${NC}   gcloud pubsub subscriptions create cloud-builds-webhook \\"
echo -e "${YELLOW}[NOTE]${NC}     --project=\"$PROJECT_ID\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --topic=\"$CLOUD_BUILDS_TOPIC\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --push-endpoint=\"\$ADMIN_SERVICE_URL/api/deploys/webhook\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --push-auth-service-account=\"$PUBSUB_PUSH_SA_EMAIL\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --push-auth-token-audience=\"\$ADMIN_SERVICE_URL/api/deploys/webhook\""
echo -e "${YELLOW}[NOTE]${NC}"
echo -e "${YELLOW}[NOTE]${NC} Then set PUBSUB_PUSH_SA_EMAIL=$PUBSUB_PUSH_SA_EMAIL on the admin"
echo -e "${YELLOW}[NOTE]${NC} service (alongside the existing ADMIN_SERVICE_URL) so"
echo -e "${YELLOW}[NOTE]${NC} require_google_oidc accepts this subscription's own pushes."

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
# --oidc-token-audience: the route's own URL (service root + path), i.e.
# "$ADMIN_SERVICE_URL/admin/links/sweep-expired" -- NOT the same string as
# the ADMIN_SERVICE_URL env var set on the admin service below (that one is
# the BARE service root; sweep_routes.py's _audience() appends this
# route's own path to it before comparing against the token's `aud` claim,
# so root+path together are what require_google_oidc actually checks).
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
echo -e "${YELLOW}[NOTE]${NC} ADMIN_SERVICE_URL and SWEEP_SCHEDULER_SA_EMAIL are now set AUTOMATICALLY"
echo -e "${YELLOW}[NOTE]${NC} by deploy-admin.sh itself on every run (bd polyglot-pdf-8vgfh finding 3) --"
echo -e "${YELLOW}[NOTE]${NC} no separate update-env-vars step, and no risk of a later deploy wiping"
echo -e "${YELLOW}[NOTE]${NC} a hand-set value. Just re-run ./deploy-admin.sh once after creating the"
echo -e "${YELLOW}[NOTE]${NC} scheduler job above, so this deploy's env vars include ADMIN_SERVICE_URL"
echo -e "${YELLOW}[NOTE]${NC} (unset on the very first deploy, before the service has a URL at all)."


# 6. Cloud Scheduler: the monthly firm-plan credit top-up (bd
# polyglot-pdf-0euzk, plan: "maintainer's pricing decision -- 35
# credits/month cap as a starting place").
#
# A SEPARATE service account from BOTH admin-backend-sa (the callee) and
# admin-sweep-scheduler-sa (the OTHER Scheduler job's caller identity,
# section 5 above) -- see that section's own comment for why a Scheduler
# caller identity is never reused across jobs: rotating one job's
# credential must never silently change what a DIFFERENT job accepts.
MONTHLY_TOPUP_SCHEDULER_SA_NAME="admin-monthly-topup-scheduler-sa"
MONTHLY_TOPUP_SCHEDULER_SA_EMAIL="$MONTHLY_TOPUP_SCHEDULER_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$MONTHLY_TOPUP_SCHEDULER_SA_EMAIL" --project "$PROJECT_ID" &>/dev/null; then
    echo -e "${GREEN}[INFO]${NC} Creating service account: $MONTHLY_TOPUP_SCHEDULER_SA_NAME..."
    gcloud iam service-accounts create "$MONTHLY_TOPUP_SCHEDULER_SA_NAME" \
        --display-name="Admin Monthly Top-Up Cloud Scheduler Caller" \
        --project "$PROJECT_ID"
else
    echo -e "${GREEN}[INFO]${NC} Service account $MONTHLY_TOPUP_SCHEDULER_SA_NAME already exists"
fi

# NOT run here, for the identical reason section 5's sweep job is not: the
# job needs the admin service's OWN Cloud Run URL, unknown until AFTER the
# first successful admin-service deploy. tests/test_setup_admin_service_
# monthly_topup_scheduler.py pins this exact command's shape.
#
# --schedule "5 0 1 * *": the 1st of the month, 5 minutes past midnight UTC
# (matching the plan's own cron string) -- offset from midnight-on-the-hour
# so this job never races the hourly sweep's own "0 * * * *" trigger at the
# month boundary.
# --uri / --oidc-token-audience: the monthly top-up route's own full path,
# admin_backend/routes/credit_routes.py's run_monthly_topup -- root+path,
# mirroring section 5's sweep job exactly (that route's _audience() appends
# its own path to the bare ADMIN_SERVICE_URL the SAME way this route's
# _topup_audience() does).
echo -e "${YELLOW}[NOTE]${NC} After the admin service's FIRST deploy, create the monthly top-up job:"
echo -e "${YELLOW}[NOTE]${NC}"
echo -e "${YELLOW}[NOTE]${NC}   gcloud scheduler jobs create http admin-monthly-credit-topup \\"
echo -e "${YELLOW}[NOTE]${NC}     --project=\"$PROJECT_ID\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --location=us-central1 \\"
echo -e "${YELLOW}[NOTE]${NC}     --schedule=\"5 0 1 * *\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --uri=\"\$ADMIN_SERVICE_URL/admin/credits/monthly-topup\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --http-method=POST \\"
echo -e "${YELLOW}[NOTE]${NC}     --oidc-service-account-email=\"$MONTHLY_TOPUP_SCHEDULER_SA_EMAIL\" \\"
echo -e "${YELLOW}[NOTE]${NC}     --oidc-token-audience=\"\$ADMIN_SERVICE_URL/admin/credits/monthly-topup\""
echo -e "${YELLOW}[NOTE]${NC}"
echo -e "${YELLOW}[NOTE]${NC} ADMIN_SERVICE_URL and MONTHLY_TOPUP_SCHEDULER_SA_EMAIL are now set"
echo -e "${YELLOW}[NOTE]${NC} AUTOMATICALLY by deploy-admin.sh itself on every run -- the identical"
echo -e "${YELLOW}[NOTE]${NC} mechanism section 5's SWEEP_SCHEDULER_SA_EMAIL already uses. Just re-run"
echo -e "${YELLOW}[NOTE]${NC} ./deploy-admin.sh once after creating the scheduler job above, so this"
echo -e "${YELLOW}[NOTE]${NC} deploy's env vars include ADMIN_SERVICE_URL (unset on the very first"
echo -e "${YELLOW}[NOTE]${NC} deploy, before the service has a URL at all)."
