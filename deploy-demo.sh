#!/bin/bash
# deploy-demo.sh - Deploy to the DEMO channel (the protected target)
#
# Usage: ./deploy-demo.sh [--backend] [--frontend] [--form-kits] [--all]
#
# A THIN WRAPPER OVER CLOUD BUILD (bd polyglot-pdf-oqtm7, Epic 4 bead 4.6).
# This script no longer builds or deploys anything itself: it refuses a dirty
# or unpushed tree, then runs the Cloud Build triggers for the demo targets at
# the current commit and streams their logs. The build is the engine, for the
# human path and the admin console alike. See docs/doctrine/promotion-tiers.md.
#
# THE STAGING-BEFORE-DEMO GATE LIVES IN THE BUILD, NOT HERE (bead 4.4). Each
# demo target's first steps refuse unless the SAME commit already has a
# successful staging deploy of the same family recorded in `deployments`, so
# running this script instead of the admin console cannot bypass the gate.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# DEPLOY PREFLIGHT (bd polyglot-pdf-1s3ko). Runs BEFORE anything else: a build
# runs from a COMMIT and build_checks/{sha} vouches for that commit's test run,
# so a dirty or unpushed tree makes both claims false. Refuses with the reason
# and the remedy; see scripts/deploy_preflight.sh for the full rationale.
source "$SCRIPT_DIR/scripts/deploy_preflight.sh"
deploy_preflight "$SCRIPT_DIR"

# The trigger runner: one function per target, log streamed, non-zero on a
# failed build. See scripts/deploy_build_targets.sh.
source "$SCRIPT_DIR/scripts/deploy_build_targets.sh"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ENROLMENT CHECK (bd polyglot-pdf-hn0jq). The voice app refuses any account
# carrying neither firm_id nor the vff_dev claim, so a signed-in user who was
# never enrolled gets a 1008 close the UI shows as a failed connection. Custom
# claims only reach a NEWLY MINTED token, so enrol BEFORE deploying, not after:
#     python scripts/bootstrap_voice_dev.py --list
#     python scripts/bootstrap_voice_dev.py --email you@example.com
echo -e "${GREEN}[INFO]${NC} Reminder: voice accounts need firm_id or a dev claim."
echo -e "${GREEN}[INFO]${NC}   check with: python scripts/bootstrap_voice_dev.py --list"

# Verify account. Still needed with the build as the engine: `gcloud builds
# triggers run` is authenticated as whoever this shell is logged in as.
echo -e "${GREEN}[INFO]${NC} Checking gcloud account..."
CURRENT_ACCOUNT=$(gcloud config get-value account)
if [[ "$CURRENT_ACCOUNT" != *"gmail.com"* ]]; then
  echo -e "${YELLOW}[WARN]${NC} Current account is $CURRENT_ACCOUNT. Need caellwyn@gmail.com."
  gcloud auth login --update-adc
fi

DEMO_SITE="polyglot-demo-aa709"

# Determine which components to deploy. The flags are unchanged; only the
# engine behind them is.
DEPLOY_BACKEND=true
DEPLOY_FORM_KITS=true
DEPLOY_FIREBASE=true

if [ $# -gt 0 ] && [ "$1" != "--all" ]; then
    DEPLOY_BACKEND=false
    DEPLOY_FORM_KITS=false
    DEPLOY_FIREBASE=false
    for arg in "$@"; do
        case "$arg" in
            --backend)
                DEPLOY_BACKEND=true
                ;;
            --form-kits)
                DEPLOY_FORM_KITS=true
                ;;
            --frontend)
                DEPLOY_FIREBASE=true
                ;;
            *)
                # UNKNOWN ARG IS FATAL (bd polyglot-pdf-7aez9). Without this
                # arm a typo like --front-end silently matched nothing, every
                # DEPLOY_* stayed false, the script deployed NOTHING, and
                # still printed its success banner and exited 0.
                echo -e "${RED}[ERROR]${NC} Unknown argument: $arg" >&2
                echo "Usage: $0 [--backend] [--frontend] [--form-kits] [--all]" >&2
                exit 1
                ;;
        esac
    done
fi

SHA=$(deploy_build_sha "$SCRIPT_DIR")

echo -e "${GREEN}[INFO]${NC} Deploying to the DEMO channel at $SHA..."

# THE TARGET ORDER IS THE OLD STAGE ORDER.
#
# Firestore rules ship with the FRONTEND, and BEFORE it: the demo project
# otherwise stays on default-deny, which breaks the users/{uid} profile
# sync on login (email signup's allowlist check is server-side since sprint
# 23 C3 and needs no client-readable rule). Rules first so a new frontend
# never goes live against stale rules. The firestore-rules target deploys
# the composite INDEXES alongside the rules -- both are project-wide, and a
# query combining an equality filter with an order_by on a different field
# is served only from a composite index (index builds are asynchronous, so
# a freshly added filter can still fail for a few minutes after the build
# reports success).
TARGETS=()
[ "$DEPLOY_BACKEND" = true ] && TARGETS+=("backend-demo")
[ "$DEPLOY_FORM_KITS" = true ] && TARGETS+=("form-kits")
[ "$DEPLOY_FIREBASE" = true ] && TARGETS+=("firestore-rules" "frontend-demo")

# A run that would deploy NOTHING must say so rather than print a success
# banner -- the same false-confidence failure the unknown-argument arm above
# exists to stop, reached by a flag combination rather than a typo.
if [ ${#TARGETS[@]} -eq 0 ]; then
    echo -e "${RED}[ERROR]${NC} Nothing selected to deploy." >&2
    echo "Usage: $0 [--backend] [--frontend] [--form-kits] [--all]" >&2
    exit 1
fi

run_build_targets "$SHA" "${TARGETS[@]}"

echo -e "${GREEN}[INFO]${NC} Demo deployment complete."
echo -e "${GREEN}[INFO]${NC} Frontend URL: https://$DEMO_SITE.web.app"
