#!/bin/bash
# setup-beads-remote.sh - Provision the GCS bucket that holds the live beads
# (Dolt) remote.
#
# Sibling of scripts/setup-telemetry.sh / setup-admin-service.sh: DECLARATIVE
# and OPERATOR-RUN. Nothing runs this from a deploy script; an operator runs it
# by hand, under their own gcloud credentials, when the bucket is first
# provisioned or its settings change. Idempotent: it creates the bucket only if
# absent, then ALWAYS converges the settings below, so a re-run against an
# already-correct bucket changes nothing.
#
# WHY A GCS BUCKET (epic bd polyglot-pdf-mlcgn). The beads store used to sync
# through a git-backed Dolt remote (git+https://github.com/..., ref
# refs/dolt/data). Dolt reads a git-backed remote one `git cat-file` PROCESS
# per chunk, and on Windows each of those is a console window: three
# concurrent bead-write cycles measured 1651-2207 git.exe with a peak of up to
# 214 windows. The same three cycles against a gs:// remote peaked at 4, and
# those 4 were other sessions' github.com traffic -- a gs:// pull spawns no git
# processes at all, because Dolt talks to GCS in-process over the object API.
#
# This script only provisions storage. It does NOT point the beads store at
# the bucket -- that cutover is bd polyglot-pdf-h06sv and needs a quiet window
# with no bead writes in flight.
#
# SETTINGS, each for a reason:
#   - public access prevention ENFORCED: the store holds every bead body.
#   - uniform bucket-level access: IAM only, no per-object ACLs to drift.
#   - object versioning ON: Dolt rewrites a small manifest object on every
#     push; versioning makes a bad push recoverable.
#   - lifecycle: delete NONCURRENT versions 30 days after they stop being
#     current. Bounds the cost of versioning; live objects are never touched.
#
# ACCESS: the operator reaches the store with their own credentials (Dolt reads
# Application Default Credentials -- a new machine needs
# `gcloud auth application-default login` once). This script grants no one
# anything, BUT a bucket also inherits every PROJECT-level storage role, and
# public access prevention does not stop those. Before the store holds data,
# confirm no deployed identity holds a project-wide storage role on the target
# project -- on polyglot-demo-aa709 the public backend SA holds
# roles/storage.objectViewer project-wide and so can read this bucket
# (bd polyglot-pdf-fuao2, which gates the cutover). Cloud-session access to the
# store is decided separately (bd polyglot-pdf-91a72).
#
# Usage: scripts/setup-beads-remote.sh <PROJECT_ID>
#
# ASCII only.

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ID="${1:-}"
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}[ERROR]${NC} Usage: $0 <PROJECT_ID>"
    exit 1
fi

# The former prod project is dead and unreachable (maintainer, 2026-08-14);
# refuse it rather than hang or half-provision -- the same refusal
# scripts/grant_credits.py and scripts/bootstrap_firm.py carry.
if [ "$PROJECT_ID" = "polyglot-forms-919f2" ]; then
    echo -e "${RED}[ERROR]${NC} $PROJECT_ID is the retired project; refusing."
    exit 2
fi

BUCKET="gs://${PROJECT_ID}-beads"
LOCATION="us-central1"
NONCURRENT_DAYS=30

echo -e "${GREEN}[INFO]${NC} Project:  $PROJECT_ID"
echo -e "${GREEN}[INFO]${NC} Bucket:   $BUCKET ($LOCATION)"

# --- 1. Create only if absent ---------------------------------------------
if gcloud storage buckets describe "$BUCKET" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo -e "${GREEN}[INFO]${NC} Bucket exists; converging settings only."
    # A bucket's location is fixed at creation. If it was ever created
    # somewhere else, updating settings would silently leave it there.
    ACTUAL_LOCATION=$(gcloud storage buckets describe "$BUCKET" \
        --project="$PROJECT_ID" --format="value(location)" | tr '[:upper:]' '[:lower:]')
    if [ "$ACTUAL_LOCATION" != "$LOCATION" ]; then
        echo -e "${RED}[ERROR]${NC} $BUCKET is in '$ACTUAL_LOCATION', expected '$LOCATION'."
        echo "        A bucket's location cannot be changed; resolve this by hand."
        exit 3
    fi
else
    echo -e "${GREEN}[INFO]${NC} Creating $BUCKET ..."
    gcloud storage buckets create "$BUCKET" \
        --project="$PROJECT_ID" \
        --location="$LOCATION" \
        --uniform-bucket-level-access \
        --public-access-prevention
fi

# --- 2. Always converge the settings (idempotent) -------------------------
LIFECYCLE_FILE="$(mktemp)"
trap 'rm -f "$LIFECYCLE_FILE"' EXIT
cat > "$LIFECYCLE_FILE" <<EOF
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"isLive": false, "daysSinceNoncurrentTime": ${NONCURRENT_DAYS}}
    }
  ]
}
EOF

gcloud storage buckets update "$BUCKET" \
    --project="$PROJECT_ID" \
    --uniform-bucket-level-access \
    --public-access-prevention \
    --versioning \
    --lifecycle-file="$LIFECYCLE_FILE"

# --- 3. Read the settings back --------------------------------------------
echo -e "${GREEN}[INFO]${NC} Effective settings:"
gcloud storage buckets describe "$BUCKET" --project="$PROJECT_ID" \
    --format="yaml(name,location,public_access_prevention,uniform_bucket_level_access,versioning_enabled,lifecycle_config)"

echo
echo -e "${GREEN}[DONE]${NC} $BUCKET is provisioned."
echo -e "${YELLOW}[NEXT]${NC} Pointing the beads store at it is a separate, quiet-window step"
echo "       (bd polyglot-pdf-h06sv) -- this script does not touch the store."
