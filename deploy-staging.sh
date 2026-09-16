#!/bin/bash
# deploy-staging.sh - Deploy to the STAGING channel (the test deploy)
#
# Usage: ./deploy-staging.sh [--backend] [--frontend] [--form-kits] [--all]
#
# A THIN WRAPPER OVER CLOUD BUILD (bd polyglot-pdf-oqtm7, Epic 4 bead 4.6).
# This script no longer builds or deploys anything itself: it refuses a dirty
# or unpushed tree, then runs the Cloud Build triggers for the staging
# targets at the current commit and streams their logs. The build is the
# engine -- for the human path and for the admin console alike -- so the
# per-SHA verify record, the reachability gate and the manifest validation
# cannot be skipped by running this script instead of that one. See
# docs/doctrine/promotion-tiers.md.
#
# WHY THIS CHANNEL EXISTS (bd polyglot-pdf-9qn64). Some bugs only appear once
# deployed -- the Cloud Run WebSocket timeout, the Vertex model-id
# resolution, the IAM envelope, the Hosting rewrite, the per-mode Vite build.
# Before this channel existed, the ONLY way to find them was to deploy to the
# demo, which is the same URL shown to investors and pilot firms. Staging is a
# second, disposable copy of the deployed surface so a broken deploy can no
# longer take the demo down.
#
# WHAT IS SEPARATE, AND WHAT IS NOT. Staging and demo live in the SAME GCP /
# Firebase project (polyglot-demo-aa709), deliberately -- a whole second project
# would need its own IAM bootstrap, its own Firebase Auth user set, and its own
# enrolment run. What that buys, and what it does NOT:
#
#   SEPARATE (a staging deploy cannot touch these):
#     - Cloud Run service   polyglot-backend-staging   vs  polyglot-backend
#     - Hosting site        polyglot-app-staging       vs  polyglot-demo-aa709
#     - the /api/** rewrite: each Hosting site routes to its OWN service
#       (firebase.json), so the staging app talks only to the staging backend.
#
#   SHARED (a mistake here DOES reach the demo):
#     - the form-kits GCS bucket. A kit marked status:complete deploys to the one
#       bucket and appears in the DEMO's form list too. This script therefore
#       does NOT deploy form kits by default -- see the --form-kits note below.
#     - Firestore (confirmation_events, users/{uid}, firms, authorized_emails).
#     - Firebase Auth: one user pool, so a staging tester can sign into the demo.
#
#   So this channel protects against BROKEN CODE reaching the demo. It does not
#   protect against bad DATA. Treat kit publishing and Firestore writes as
#   production actions no matter which channel you ran them from.
#
# ONE-TIME setup, before the first staging deploy -- see docs/doctrine/
# promotion-tiers.md for the full walkthrough:
#     firebase hosting:sites:create polyglot-app-staging --project polyglot-demo-aa709
#     firebase target:apply hosting app-staging polyglot-app-staging --project polyglot-demo-aa709
#   (The target mapping ships in .firebaserc already; re-run target:apply only
#   for a NEW site.) Then add the staging site to Firebase Auth's authorized
#   domains -- Authentication > Settings > Authorized domains -- or sign-in
#   fails at a human's first attempt with the whole config present and valid.
#   Cloud Build's own one-time setup (the GitHub connection and one manual
#   trigger per target) lives in scripts/setup-cloud-build.sh.

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

# ENROLMENT CHECK (bd polyglot-pdf-hn0jq). Same as the demo: the voice app
# refuses any account carrying neither firm_id nor the vff_dev claim, and custom
# claims only reach a NEWLY MINTED token. Auth is SHARED with the demo, so an
# account already enrolled there needs nothing further here.
echo -e "${GREEN}[INFO]${NC} Reminder: voice accounts need firm_id or a dev claim."
echo -e "${GREEN}[INFO]${NC}   check with: python scripts/bootstrap_voice_dev.py --list"

# Verify account (same identity as the demo -- one project). Still needed with
# the build as the engine: `gcloud builds triggers run` is authenticated as
# whoever this shell is logged in as.
echo -e "${GREEN}[INFO]${NC} Checking gcloud account..."
CURRENT_ACCOUNT=$(gcloud config get-value account)
if [[ "$CURRENT_ACCOUNT" != *"gmail.com"* ]]; then
  echo -e "${YELLOW}[WARN]${NC} Current account is $CURRENT_ACCOUNT. Need caellwyn@gmail.com."
  gcloud auth login --update-adc
fi

STAGING_SITE="polyglot-app-staging"
DEMO_SITE="polyglot-demo-aa709"

# Determine which components to deploy.
#
# NOTE the deliberate asymmetry with deploy-demo.sh: a bare run here deploys
# backend + frontend but NOT form kits. The bucket is shared with the demo, so a
# staging form-kits deploy would publish kits to the demo's form list -- exactly
# the cross-channel leak this environment exists to prevent. Pass --form-kits
# explicitly if you really mean to publish kits (it is the same act as running
# deploy-demo.sh --form-kits).
DEPLOY_GCP=true
DEPLOY_FIREBASE=true
DEPLOY_FORM_KITS=false

if [ $# -gt 0 ] && [ "$1" != "--all" ]; then
    DEPLOY_GCP=false
    DEPLOY_FIREBASE=false
    for arg in "$@"; do
        case "$arg" in
            --backend)
                DEPLOY_GCP=true
                ;;
            --form-kits)
                DEPLOY_FORM_KITS=true
                ;;
            --frontend)
                DEPLOY_FIREBASE=true
                ;;
            *)
                # UNKNOWN ARG IS FATAL (bd polyglot-pdf-7aez9). Without this arm
                # a typo like --front-end silently matched nothing, every
                # DEPLOY_* stayed false, the script deployed NOTHING, and still
                # printed its success banner and exited 0. The operator then
                # believes they verified a change they never deployed -- and on
                # the staging channel that is exactly the false confidence the
                # tier exists to remove.
                echo -e "${RED}[ERROR]${NC} Unknown argument: $arg" >&2
                echo "Usage: $0 [--backend] [--frontend] [--form-kits] [--all]" >&2
                exit 1
                ;;
        esac
    done
elif [ "$1" = "--all" ]; then
    DEPLOY_FORM_KITS=true
fi

SHA=$(deploy_build_sha "$SCRIPT_DIR")

echo -e "${GREEN}[INFO]${NC} Deploying to the STAGING channel (test deploy) at $SHA..."
if [ "$DEPLOY_FORM_KITS" = true ]; then
    echo -e "${YELLOW}[WARN]${NC} Form kits are SHARED with the demo -- publishing here"
    echo -e "${YELLOW}[WARN]${NC} also changes the demo's form list."
fi

# THE TARGET ORDER IS THE OLD STAGE ORDER. Backend first, so the frontend
# build resolves a Cloud Run URL that already serves this commit; form kits
# before the frontend for the same reason the old script uploaded them in
# stage 1.
#
# Firestore rules are deliberately NOT in this list. They are PROJECT-wide,
# not per-site: deploying them from staging would apply the staging branch's
# rules to the live demo, which is exactly the blast radius this channel is
# meant to remove. Rules ship with the demo deploy (deploy-demo.sh), after the
# change has been reviewed.
TARGETS=()

# VERIFY FIRST, ONCE PER COMMIT. Every deploy target's first build step
# REFUSES without a build_checks/{sha} success record, so a commit that has
# never been verified cannot deploy by any route. Running verify here when the
# record is missing is what makes a first staging deploy of a new commit a
# single command instead of two; when the record already exists (a second
# target for the same SHA, or a verify run from the console) it is skipped, so
# five targets for one commit still pay for one test run.
if build_check_recorded "$SCRIPT_DIR" "$SHA"; then
    echo -e "${GREEN}[INFO]${NC} build_checks record found for $SHA -- skipping verify."
else
    echo -e "${GREEN}[INFO]${NC} No build_checks record for $SHA -- running verify first."
    TARGETS+=("verify")
fi

[ "$DEPLOY_GCP" = true ] && TARGETS+=("backend-staging")
[ "$DEPLOY_FORM_KITS" = true ] && TARGETS+=("form-kits")
[ "$DEPLOY_FIREBASE" = true ] && TARGETS+=("frontend-staging")

# A run that would deploy NOTHING must say so rather than print a success
# banner -- the same false-confidence failure the unknown-argument arm above
# exists to stop (bd polyglot-pdf-7aez9), reached here by a flag combination
# rather than a typo.
if [ ${#TARGETS[@]} -eq 0 ]; then
    echo -e "${RED}[ERROR]${NC} Nothing selected to deploy." >&2
    echo "Usage: $0 [--backend] [--frontend] [--form-kits] [--all]" >&2
    exit 1
fi

run_build_targets "$SHA" "${TARGETS[@]}"

echo -e "${GREEN}[INFO]${NC} Staging deployment complete."
echo -e "${GREEN}[INFO]${NC} Staging URL: https://$STAGING_SITE.web.app"
echo -e "${GREEN}[INFO]${NC} Demo (untouched): https://$DEMO_SITE.web.app"
