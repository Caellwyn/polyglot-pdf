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
# ACCESS -- WHY THE STORE GETS ITS OWN PROJECT. This script grants no one
# anything, but a bucket also inherits every PROJECT-level storage role, and
# public access prevention does not stop those. The app project
# polyglot-demo-aa709 is the wrong home: its public backend SA holds
# roles/storage.objectViewer project-wide, and its default compute and legacy
# Cloud Build accounts hold broader project roles, so all of them would reach
# every bead body (bd polyglot-pdf-fuao2). The store therefore lives in a
# DEDICATED project, polyglot-beads, where no deployed identity holds any
# role. Keep it that way: grant roles there only to human users -- never to a
# service account, group, or other non-human principal, whatever the role. The operator reaches the store with their own
# credentials (Dolt reads Application Default Credentials -- a new machine
# needs `gcloud auth application-default login` once). Cloud-session access is
# decided separately (bd polyglot-pdf-91a72).
#
# Usage: scripts/setup-beads-remote.sh polyglot-beads
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

# --- 0. Refuse unless only humans and Google's own agents hold roles -------
# The property this store depends on (see ACCESS above), checked live rather
# than by project name. It is an ALLOWLIST of who may hold roles, not a list
# of risky roles: dozens of predefined roles reach object data (firebase.*,
# run.builder, dataflow.worker, roles/viewer via the bucket's default
# projectViewer binding, custom roles, roles that can grant themselves more),
# and a role list is always one entry short. So ANY role held by any other
# principal -- a deployed service account, a group (groups can contain service
# accounts), a workload-identity principal, a deleted principal, allUsers --
# refuses.
#
# It reads the ANCESTORS policy (project + folders + organization), because a
# bucket inherits org- and folder-level grants too. That read needs
# organization-level IAM read access; without it the command fails and the
# script stops (set -e + pipefail): fail closed. Run it as an org admin.
#
# Google service agents are allowed only when they belong to THIS project (by
# project number) or to the very folder/org row they appear on. An agent of
# ANOTHER project acts for that project: the app project's Vertex AI agent,
# for one, can be driven by the public backend SA (roles/aiplatform.user), so
# allowing agents by shape alone would readmit the identity this store moved
# away from.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' | tr -d '\r')
if ! [[ "$PROJECT_NUMBER" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}[ERROR]${NC} Could not read the project number of $PROJECT_ID."
    exit 1
fi
# Args: member, level (project|folder|organization), id of that level's row.
is_allowed_member() {
    local member="$1" level="$2" id="$3"
    case "$member" in
        user:*|domain:*) return 0 ;;   # human accounts / a Workspace domain's humans
        "serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-"*".iam.gserviceaccount.com") return 0 ;;
        "serviceAccount:${PROJECT_NUMBER}@cloudservices.gserviceaccount.com") return 0 ;;
        "serviceAccount:service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com") return 0 ;;
    esac
    case "$level:$member" in
        "organization:serviceAccount:service-org-${id}@gcp-sa-"*".iam.gserviceaccount.com") return 0 ;;
        "folder:serviceAccount:service-folder-${id}@gcp-sa-"*".iam.gserviceaccount.com") return 0 ;;
    esac
    return 1                           # anything else holding any role refuses
}
DISALLOWED=$(gcloud projects get-ancestors-iam-policy "$PROJECT_ID" \
    --flatten='policy.bindings[].members' \
    --format='value(type,id,policy.bindings.role,policy.bindings.members)' \
    | tr -d '\r' \
    | while IFS=$'\t' read -r level id role member; do
        [ -z "$level$role$member" ] && continue   # blank output line
        if ! is_allowed_member "$member" "$level" "$id"; then
            echo "  [$level $id]  $role  $member"
        fi
    done)
if [ -n "$DISALLOWED" ]; then
    echo -e "${RED}[ERROR]${NC} Principals other than humans and Google service agents hold"
    echo "        roles that $BUCKET would inherit:"
    echo "$DISALLOWED"
    echo "        Use a dedicated project where none do (polyglot-beads)."
    exit 4
fi

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
