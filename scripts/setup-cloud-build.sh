#!/bin/bash
# setup-cloud-build.sh -- create ONE manual Cloud Build trigger per target.
#
# OPERATOR-RUN, ONCE. Nothing in the normal deploy path calls this; it is the
# provisioning step that makes `gcloud builds triggers run polyglot-<target>
# --sha=<sha>` work (bead polyglot-pdf-1s3ko, wrappers in bead 4.6).
#
# ============================================================================
# PREREQUISITE THE MAINTAINER MUST DO FIRST (one-time OAuth)
# ============================================================================
# This repo is PRIVATE, so Cloud Build can only fetch an arbitrary commit
# through a 2nd-generation GitHub connection. Creating one requires an
# interactive OAuth authorization in the Cloud Build console -- it cannot be
# scripted, and nothing below works without it:
#
#   Cloud Build > Repositories > 2nd gen > Create host connection
#     region: us-central1     (MUST match CLOUD_BUILD_REGION below)
#   then: Link repository -> Caellwyn/polyglot-pdf
#
# That produces two resource names, which this script takes as env vars:
#
#   CLOUD_BUILD_CONNECTION=projects/<project>/locations/us-central1/connections/<name>
#   CLOUD_BUILD_REPOSITORY=projects/<project>/locations/us-central1/connections/<name>/repositories/<name>
#
# Read them back at any time with:
#   gcloud builds connections list --region=us-central1
#   gcloud builds repositories list --connection=<name> --region=us-central1
#
# ============================================================================
# WHY MANUAL TRIGGERS, AND WHY --sha WORKS
# ============================================================================
# `gcloud builds triggers run <trigger> --sha=<sha>` is supported and takes at
# most one of --branch / --sha / --tag (verified against the current gcloud
# reference, 2026-09-11). So a manual trigger per target, each pinning its own
# _TARGET/_CHANNEL substitutions, gives the wrappers and the admin service one
# stable command shape: name the trigger, name the commit.
#
# --repository (the 2nd-gen resource) and --repo/--repo-type (the 1st-gen
# pair) are MUTUALLY EXCLUSIVE, so this script passes only --repository.
# Adding --repo-type=GITHUB alongside it is rejected by the CLI, not ignored.
#
# REGION IS NOT OPTIONAL for a 2nd-gen repository -- `global` is unsupported.
# Every trigger here is created in, and must be run with, CLOUD_BUILD_REGION.
# Omitting --region on `triggers run` resolves to the builds/region property
# or global, and the trigger is simply not found.
#
# The alternative shape, `gcloud builds submit`, is deliberately NOT used:
# it uploads the LOCAL tree as a tarball, which .gcloudignore has stripped of
# frontend/, tests/ and docs/, so the verify and site targets cannot run at
# all -- and COMMIT_SHA would be empty while uncommitted code shipped under a
# SHA the verify gate vouches for. cloudbuild.yaml's header states the same.
#
# ============================================================================
# THE BUILD IDENTITY: polyglot-cloudbuild-sa (bead polyglot-pdf-p4ale, E4.5)
# ============================================================================
# Every trigger above runs AS a dedicated service account, never the legacy
# default Cloud Build SA (which historically holds project Editor -- far
# wider than anything a deploy build needs). Sibling of
# scripts/setup-admin-service.sh's admin-backend-sa: one justified role per
# line, pinned by admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py
# (which parses THIS file's role arrays -- a role added here without adding
# it to that test's constant fails CI, same collusion-proof pattern as the
# admin SA pin).
#
# WHY actAs, NOT JUST run.admin. `gcloud run deploy --service-account
# $RUNTIME_SA` fails unless the CALLER (this build's identity) holds
# `roles/iam.serviceAccountUser` ON that runtime SA specifically --
# "deploy a revision that runs as X" is itself a privileged act on X, not
# just on the Cloud Run service. The build deploys revisions running as BOTH
# polyglot-backend-sa (public backend targets) and admin-backend-sa (the
# admin-service target), so it needs actAs on both -- resource-scoped to
# each SA individually, never project-wide serviceAccountUser, which would
# let this identity impersonate every service account in the project.
#
# Usage:
#   CLOUD_BUILD_CONNECTION=... CLOUD_BUILD_REPOSITORY=... \
#     bash scripts/setup-cloud-build.sh [--dry-run]

set -euo pipefail

PROJECT="${POLYGLOT_PROJECT_NAME:-polyglot-demo-aa709}"
CLOUD_BUILD_REGION="${CLOUD_BUILD_REGION:-us-central1}"
BUILD_SA_NAME="polyglot-cloudbuild-sa"
BUILD_SA="${CLOUD_BUILD_SA:-$BUILD_SA_NAME@$PROJECT.iam.gserviceaccount.com}"
CONFIG_PATH="cloudbuild.yaml"

# The two RUNTIME identities the build must be able to deploy revisions as.
# Resource-scoped actAs bindings below name these explicitly rather than
# reaching for a project-wide grant.
PUBLIC_BACKEND_SA="polyglot-backend-sa@$PROJECT.iam.gserviceaccount.com"
ADMIN_BACKEND_SA="admin-backend-sa@$PROJECT.iam.gserviceaccount.com"

# The shared form-kit store -- same bucket setup-admin-service.sh scopes
# storage.objectAdmin to. storage.objectAdmin is granted here on THIS BUCKET
# ONLY, never project-wide -- see BUCKET_ROLES below.
FORM_KITS_BUCKET="${FORM_KITS_BUCKET:-$PROJECT-form-kits}"

DRY_RUN=false
[ "${1:-}" = "--dry-run" ] && DRY_RUN=true

if [ "$DRY_RUN" = false ]; then
    if [ -z "${CLOUD_BUILD_REPOSITORY:-}" ]; then
        echo "[ERROR] CLOUD_BUILD_REPOSITORY is not set." >&2
        echo "[ERROR] It is the output of the maintainer's one-time OAuth step --" >&2
        echo "[ERROR] see this script's header. Find it with:" >&2
        echo "[ERROR]   gcloud builds repositories list --connection=<name> \\" >&2
        echo "[ERROR]     --region=$CLOUD_BUILD_REGION" >&2
        exit 1
    fi
fi

echo "[INFO] Enabling the Cloud Build API (idempotent)..."
if [ "$DRY_RUN" = false ]; then
    gcloud services enable cloudbuild.googleapis.com --project "$PROJECT"
else
    echo "[DRY-RUN] gcloud services enable cloudbuild.googleapis.com --project $PROJECT"
fi

# ----------------------------------------------------------------------------
# 1. The build service account itself.
# ----------------------------------------------------------------------------
echo "[INFO] Provisioning build service account: $BUILD_SA_NAME..."
if [ "$DRY_RUN" = false ]; then
    if ! gcloud iam service-accounts describe "$BUILD_SA" --project "$PROJECT" &>/dev/null; then
        gcloud iam service-accounts create "$BUILD_SA_NAME" \
            --display-name="Polyglot Cloud Build Service Account" \
            --project "$PROJECT"
    else
        echo "[INFO] Service account $BUILD_SA_NAME already exists"
    fi
else
    echo "[DRY-RUN] gcloud iam service-accounts create $BUILD_SA_NAME --project $PROJECT"
fi

# 2. PROJECT-level roles. Each carries the one class of build step that
# needs it -- see the per-target step list in cloudbuild.yaml.
PROJECT_ROLES=(
    # Deploy Cloud Run revisions (backend-staging, backend-demo,
    # admin-service targets) and shift traffic on the admin tagged-revision
    # gate.
    "roles/run.admin"
    # Publish the Hosting site targets (frontend-*, admin-console,
    # admin-console-candidate, editor).
    "roles/firebasehosting.admin"
    # Deploy the firestore-rules target (`firebase deploy --only
    # firestore:rules`).
    "roles/firebaserules.admin"
    # Push the built backend image. NOTE: images live on gcr.io today, not
    # Artifact Registry -- this role still applies because gcr.io pushes are
    # served through the Artifact Registry API on projects created after its
    # GA. Moving the images themselves to an Artifact Registry repository is
    # a separable follow-up (bead 4.5 description), not required for this
    # role to work.
    "roles/artifactregistry.writer"
    # Structured build-step logs to Cloud Logging, same as both runtime SAs.
    "roles/logging.logWriter"
    # Write build_checks/{sha} (the verify gate's record) and deployments/{id}
    # success rows (the staging-before-demo gate's evidence), and read
    # deployments/{id} to evaluate that gate for a demo build.
    "roles/datastore.user"
    # Deploy the COMPOSITE INDEXES half of the firestore-rules target
    # (`firebase deploy --only firestore:indexes`). NOT covered by either
    # role above: roles/firebaserules.admin is rules-only, and
    # roles/datastore.user carries datastore.schemas.list (read) but none of
    # datastore.schemas.create/update/delete, which is what writing an index
    # definition needs. Until this bead the index deploy ran on an
    # OPERATOR's own owner-level account inside deploy-demo.sh; moving it
    # into the build (bd polyglot-pdf-oqtm7) moved it onto this identity, so
    # the permission question is new. Without the role the target is a no-op
    # list that passes by luck while firestore.indexes.json is unchanged,
    # then dies with PERMISSION_DENIED on the first added or edited index --
    # and takes the whole demo deploy down with it, because firestore-rules
    # runs BEFORE frontend-demo and the runner stops at the first failure
    # (CLAUDE.md scar #7).
    "roles/datastore.indexAdmin"
)

echo "[INFO] Assigning project-level IAM roles to $BUILD_SA_NAME..."
for role in "${PROJECT_ROLES[@]}"; do
    echo "[INFO]    Adding $role..."
    if [ "$DRY_RUN" = false ]; then
        gcloud projects add-iam-policy-binding "$PROJECT" \
            --member="serviceAccount:$BUILD_SA" \
            --role="$role" \
            --condition=None > /dev/null
    else
        echo "[DRY-RUN] gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$BUILD_SA --role=$role"
    fi
done

# 3. RESOURCE-scoped roles. Granted on one bucket, never project-wide -- see
# the FORM_KITS_BUCKET comment above for why the scope matters.
BUCKET_ROLES=(
    # Publish and retire form kits in the shared bucket (the form-kits
    # target). Same role, same bucket, same scoping shape as
    # setup-admin-service.sh's grant to admin-backend-sa.
    "roles/storage.objectAdmin"
)

echo "[INFO] Assigning bucket-scoped IAM roles on gs://$FORM_KITS_BUCKET..."
for role in "${BUCKET_ROLES[@]}"; do
    echo "[INFO]    Adding $role on gs://$FORM_KITS_BUCKET..."
    if [ "$DRY_RUN" = false ]; then
        gcloud storage buckets add-iam-policy-binding "gs://$FORM_KITS_BUCKET" \
            --member="serviceAccount:$BUILD_SA" \
            --role="$role" \
            --project "$PROJECT" > /dev/null
    else
        echo "[DRY-RUN] gcloud storage buckets add-iam-policy-binding gs://$FORM_KITS_BUCKET --member=serviceAccount:$BUILD_SA --role=$role"
    fi
done

# 4. actAs bindings: iam.serviceAccountUser, resource-scoped to EACH runtime
# SA the build deploys revisions as. Granted with
# `gcloud iam service-accounts add-iam-policy-binding` on the TARGET SA
# (the resource), not `gcloud projects add-iam-policy-binding` -- a
# project-level grant of this role would let the build identity impersonate
# every service account in the project, not just the two it deploys as.
ACTAS_TARGETS=(
    "$PUBLIC_BACKEND_SA"
    "$ADMIN_BACKEND_SA"
)

echo "[INFO] Granting $BUILD_SA_NAME actAs (roles/iam.serviceAccountUser) on the runtime SAs..."
for target_sa in "${ACTAS_TARGETS[@]}"; do
    echo "[INFO]    Adding roles/iam.serviceAccountUser on $target_sa..."
    if [ "$DRY_RUN" = false ]; then
        gcloud iam service-accounts add-iam-policy-binding "$target_sa" \
            --member="serviceAccount:$BUILD_SA" \
            --role="roles/iam.serviceAccountUser" \
            --project "$PROJECT" > /dev/null
    else
        echo "[DRY-RUN] gcloud iam service-accounts add-iam-policy-binding $target_sa --member=serviceAccount:$BUILD_SA --role=roles/iam.serviceAccountUser"
    fi
done

# 5. The Pub/Sub service agent needs iam.serviceAccountTokenCreator to mint
# the OIDC token it pushes to the admin service's build-status webhook (bead
# 4.3, POST /api/deploys/webhook, gated by require_google_oidc). Pinned here
# too so the whole deploy-plane IAM -- the build SA above AND this one
# Google-managed agent -- is asserted from one script and one test, per the
# bead's own framing ("the whole deploy-plane IAM is in one pin"). This is
# NOT a role on BUILD_SA: the Pub/Sub service agent is a separate,
# Google-managed identity (service-<PROJECT_NUMBER>@gcp-sa-pubsub.iam.
# gserviceaccount.com), and the role is granted on itself so it may mint a
# token asserting its own identity to a push subscription -- the standard
# shape for an OIDC-authenticated Pub/Sub push endpoint.
echo "[INFO] Granting the Pub/Sub service agent roles/iam.serviceAccountTokenCreator..."
if [ "$DRY_RUN" = false ]; then
    PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
    PUBSUB_SERVICE_AGENT="service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com"
    gcloud projects add-iam-policy-binding "$PROJECT" \
        --member="serviceAccount:$PUBSUB_SERVICE_AGENT" \
        --role="roles/iam.serviceAccountTokenCreator" \
        --condition=None > /dev/null
else
    echo "[DRY-RUN] PROJECT_NUMBER=\$(gcloud projects describe $PROJECT --format='value(projectNumber)')"
    echo "[DRY-RUN] gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:service-\$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com --role=roles/iam.serviceAccountTokenCreator"
fi

# EVERY target in cloudbuild.yaml gets a trigger, including the ones bead
# polyglot-pdf-ywxoh (4.2) has not implemented yet: their build fails loudly
# with "target not implemented" rather than the trigger being missing, so the
# console's target list and this script's list cannot silently disagree.
#
# "<target>:<channel>" -- the channel selects deploy/channels/<channel>.env.
# A target with no channel of its own carries the one its file is named for.
TARGETS=(
    "verify:staging"
    "backend-staging:staging"
    "backend-demo:demo"
    "frontend-staging:staging"
    "frontend-demo:demo"
    "editor:demo"
    "form-kits:demo"
    "firestore-rules:demo"
    "admin-service:admin"
    "admin-console-candidate:admin"
    "admin-console:admin"
    "landing:demo"
)

for entry in "${TARGETS[@]}"; do
    target="${entry%%:*}"
    channel="${entry##*:}"
    name="polyglot-$target"

    echo "[INFO] Trigger $name  (_TARGET=$target _CHANNEL=$channel)"

    # `triggers create manual` has no --update, so a re-run of this script
    # would fail on an existing trigger. Delete-then-create keeps it
    # idempotent, and a manual trigger holds no state worth preserving.
    if [ "$DRY_RUN" = false ]; then
        gcloud builds triggers delete "$name" \
            --region="$CLOUD_BUILD_REGION" --project="$PROJECT" --quiet \
            >/dev/null 2>&1 || true
    fi

    cmd=(gcloud builds triggers create manual
        --name="$name"
        --region="$CLOUD_BUILD_REGION"
        --project="$PROJECT"
        --repository="${CLOUD_BUILD_REPOSITORY:-<CLOUD_BUILD_REPOSITORY>}"
        --branch=dev
        --build-config="$CONFIG_PATH"
        --substitutions="_TARGET=$target,_CHANNEL=$channel"
        --service-account="projects/$PROJECT/serviceAccounts/$BUILD_SA")

    if [ "$DRY_RUN" = true ]; then
        printf '[DRY-RUN] %s\n' "${cmd[*]}"
    else
        "${cmd[@]}"
    fi
done

echo ""
echo "[INFO] Done. Run a build for a specific commit with:"
echo "[INFO]   gcloud builds triggers run polyglot-verify \\"
echo "[INFO]     --sha=<sha> --region=$CLOUD_BUILD_REGION --project=$PROJECT \\"
echo "[INFO]     --substitutions=_SHA=<sha>"
echo "[INFO]"
echo "[INFO] --region is REQUIRED: a 2nd-gen repository cannot live in global,"
echo "[INFO] so a run without it looks like a missing trigger."
