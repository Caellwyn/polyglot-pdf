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
# Usage:
#   CLOUD_BUILD_CONNECTION=... CLOUD_BUILD_REPOSITORY=... \
#     bash scripts/setup-cloud-build.sh [--dry-run]

set -euo pipefail

PROJECT="${POLYGLOT_PROJECT_NAME:-polyglot-demo-aa709}"
CLOUD_BUILD_REGION="${CLOUD_BUILD_REGION:-us-central1}"
BUILD_SA="${CLOUD_BUILD_SA:-polyglot-cloudbuild-sa@$PROJECT.iam.gserviceaccount.com}"
CONFIG_PATH="cloudbuild.yaml"

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

echo "[INFO] Enabling the Cloud Build API (idempotent)..."
if [ "$DRY_RUN" = false ]; then
    gcloud services enable cloudbuild.googleapis.com --project "$PROJECT"
else
    echo "[DRY-RUN] gcloud services enable cloudbuild.googleapis.com --project $PROJECT"
fi

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
