#!/bin/bash
# pull-form-kits.sh - Sync form kits DOWN from the shared GCS bucket into the
# local form-kits/ tree (bd polyglot-pdf-92qe.4).
#
# WHY THIS EXISTS (the round-trip gap): contractors author and polish kits in
# the BUCKET (via the hosted editor), but the deploy regenerates index.json
# from the LOCAL form-kits/ tree -- a kit that exists only in the bucket would
# silently DROP from the served manifest on the next deploy. This script closes
# the loop: pull the bucket state down, review the diff in git (contractor work
# becomes reviewable, versioned history), then run the normal deploy.
#
#   ./scripts/pull-form-kits.sh          # pull all kits (never deletes local)
#   git diff --stat form-kits/           # review the contractor's work
#   ./deploy-demo.sh                     # republish (complete kits only)
#
# Env: FORM_KITS_BUCKET (default: the demo bucket), FORM_KITS_PREFIX.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BUCKET="${FORM_KITS_BUCKET:-polyglot-demo-aa709-form-kits}"
PREFIX="${FORM_KITS_PREFIX:-form-kits}"
DEST="$REPO_ROOT/form-kits"

if ! gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
    echo "ERROR: bucket gs://$BUCKET not found (or no gcloud access)." >&2
    echo "Set FORM_KITS_BUCKET to the right bucket, or run 'gcloud auth login'." >&2
    exit 1
fi

mkdir -p "$DEST"
echo "Pulling gs://$BUCKET/$PREFIX -> $DEST"
# rsync mirrors kit files INTO the local tree. Deliberately NO
# --delete-unmatched-destination-objects: a local-only kit (not yet pushed to
# the bucket) must survive a pull. index.json is EXCLUDED -- it is
# deploy-GENERATED output, never a source file (pulling it would make the
# tracked tree carry a derived artifact that the next deploy overwrites).
gcloud storage rsync --recursive --exclude="^index\.json$" \
    "gs://$BUCKET/$PREFIX" "$DEST"

echo ""
echo "Done. Review with:  git diff --stat form-kits/"
echo "Publish with the normal deploy (only status:complete kits ship)."
