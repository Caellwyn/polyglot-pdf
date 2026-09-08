#!/bin/bash
# setup-firestore-ttl.sh - Declare Firestore TTL policies on expire_at.
#
# Epic 2 bead A1, plan docs/sprint_22_admin-console_plan.md ("Data model").
# A TTL policy tells Firestore to auto-delete a document once its `expire_at`
# field's timestamp is in the past -- Firestore does the deletion itself, on
# its own schedule (documented as "usually within 24 hours"), so nothing in
# this repo runs a sweep or a cron job to reap these collections.
#
# WHICH COLLECTIONS GET A POLICY, AND WHICH DELIBERATELY DO NOT (plan, "Data
# model" section):
#
#   links, links_staging            -- the client-link mint record
#                                       (backend/services/links_store.py).
#                                       expire_at is open_deadline plus a
#                                       retention margin
#                                       (links_store.expire_at_for()), so a
#                                       link's bookkeeping row survives well
#                                       past its own open/completion window
#                                       before Firestore reaps it.
#   alerts                          -- Epic 3's telemetry alerts collection.
#                                       Declared here NOW, ahead of that
#                                       epic, because a TTL policy on a
#                                       not-yet-existing collection is valid
#                                       (Firestore applies it the moment a
#                                       matching document appears) and this
#                                       is the one script that owns TTL
#                                       policy declarations -- Epic 3 should
#                                       not need to reinvent this file.
#
#   admin_audit_log, deployments    -- KEPT, no TTL, deliberately NOT listed
#                                       below. The audit log is the
#                                       "who did what, when" record and must
#                                       outlive any individual link or alert;
#                                       `deployments` (Epic 4) is a small,
#                                       low-volume history collection with no
#                                       storage-cost pressure to reap it.
#
# link_redemptions / link_redemptions_staging are NOT listed either: that
# collection is the load-bearing one-time-use record (bd polyglot-pdf-ugm6)
# and this bead does not touch its retention policy -- changing it is a
# separate, deliberate decision, not a side effect of adding TTL to a
# DIFFERENT collection that happens to sit next to it.
#
# WHY expire_at ON EVERY LISTED COLLECTION, NOT A DIFFERENT FIELD PER
# COLLECTION: one field name means one gcloud invocation shape below, and
# means a human auditing "which collections can silently disappear" greps
# for one name across firestore.rules and the service modules.
#
# Idempotent: `gcloud firestore fields ttls update` on a field that already
# carries the policy is a no-op success, so re-running this script is safe.
# NOT run by any deploy script -- an operator runs it by hand, once per
# project (staging and demo SHARE one Firestore project, so this needs
# exactly one run for both channels, same as scripts/setup-gcp-project.sh
# and scripts/setup-admin-service.sh).
#
# Usage: ./scripts/setup-firestore-ttl.sh <PROJECT_ID>

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ID=$1
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}[ERROR]${NC} Usage: $0 <PROJECT_ID>"
    exit 1
fi

# THE SET. Extend this list, not a one-off gcloud call elsewhere, when a
# later bead adds another expire_at-bearing collection -- this script is the
# one place TTL policies are declared (CLAUDE.md scar #8: enumerate the set).
TTL_COLLECTIONS=(
    "links"
    "links_staging"
    "alerts"
)

echo -e "${GREEN}[INFO]${NC} Declaring Firestore TTL policies on 'expire_at' for project: $PROJECT_ID"

for collection in "${TTL_COLLECTIONS[@]}"; do
    echo -e "${GREEN}[INFO]${NC}    $collection.expire_at ..."
    gcloud firestore fields ttls update expire_at \
        --collection-group="$collection" \
        --enable-ttl \
        --project="$PROJECT_ID"
done

echo -e "${GREEN}[INFO]${NC} Done. A TTL policy can take a short time to become ACTIVE; check with:"
echo -e "${YELLOW}[NOTE]${NC}    gcloud firestore fields describe expire_at --collection-group=links --project=$PROJECT_ID"
