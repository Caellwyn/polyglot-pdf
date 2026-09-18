#!/bin/bash
# deploy-admin.sh - Deploy the privileged admin backend (Cloud Run:
# polyglot-admin) as a NO-TRAFFIC TAGGED REVISION, verified, then shifted.
#
# A THIN WRAPPER OVER CLOUD BUILD (bd polyglot-pdf-oqtm7, Epic 4 bead 4.6).
# The whole sequence is cloudbuild.yaml's `admin-service` target: build the
# shared image, deploy it as a tagged no-traffic revision, health-check that
# revision at its own tag URL, and only then shift 100% of traffic. This
# script refuses a dirty or unpushed tree, then runs that target's trigger at
# the current commit and streams its log.
#
# WHY A TAGGED NO-TRAFFIC DEPLOY, UNLIKE deploy-staging.sh / deploy-demo.sh.
# There is ONE admin service and ONE console site backing BOTH channels' data
# (the admin service has no channel of its own -- see the plan's
# "Architecture" section), so a bad admin deploy takes the control plane down
# for staging AND the demo at once. A revision that fails its health check
# never serves a single request; the previous good revision keeps serving
# throughout. That is this service's staging tier.
#
# THE FIRST DEPLOY IS A DIFFERENT BRANCH (bd polyglot-pdf-h1nvd). Cloud Run
# refuses --no-traffic on a service that does not exist yet, so
# admin-service-deploy-tagged (cloudbuild.yaml) checks whether polyglot-admin
# already resolves a URL before it deploys: if not, it creates the service
# WITHOUT --no-traffic/--tag, which lands 100% of traffic on that first
# revision immediately (there is no previous revision to protect traffic
# from). admin-service-verify-tagged mirrors the branch -- it health-checks
# the base URL directly when no "candidate" tag exists rather than probing a
# tag that was never created. Every later run finds the service already
# exists and keeps the tagged no-traffic-then-shift flow described above
# unchanged.
#
# WHERE ITS CONFIG LIVES NOW. Everything this script used to assemble inline
# and pass as BACKEND_EXTRA_ENV is in deploy/channels/admin.env
# (APP_MODULE, CORS_EXTRA_ORIGINS, and the three Scheduler/Pub-Sub caller
# identities the OIDC gates allowlist) plus the build's own lookups for the
# two values Google only assigns at deploy time (ADMIN_SERVICE_URL and each
# public backend's URL for GET /admin/health's fan-out). ONE source, read by
# the build -- not two live copies in two languages.
#
# WHAT THIS SCRIPT DOES NOT DO. It deploys the BACKEND only -- the
# admin-console Vite app (its own candidate + live Hosting sites) has its own
# wrapper, deploy-admin-console.sh. Running this script alone stands the API
# up with no UI in front of it; that is a legitimate intermediate state.
#
# ONE-TIME setup, before the first admin deploy:
#   1. Run scripts/setup-admin-service.sh <PROJECT_ID> once to create
#      admin-backend-sa and grant its roles (idempotent; safe to re-run).
#   2. Stamp the FIRST app_admin account:
#        python scripts/bootstrap_admin_user.py --email you@example.com
#   3. The org's domain-restricted-sharing policy may REFUSE the allUsers
#      invoker binding the deploy requests -- exactly the failure mode the
#      build's reachability gate (scripts/verify_service_reachable.py) exists
#      to catch, and it bites hardest on a BRAND NEW service. If it fires,
#      either grant the binding by hand (the gate's own error message names
#      the exact command) or relax the org policy for this project -- both
#      maintainer actions. See docs/doctrine/promotion-tiers.md.
#
# Usage:
#   ./deploy-admin.sh
#
# Every run deploys the admin backend only; there is no --frontend/--form-kits
# split here because this service has neither. Re-run it any time the
# admin_backend/ package changes.

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${POLYGLOT_PROJECT_NAME:-polyglot-demo-aa709}"
ADMIN_SERVICE_NAME="${ADMIN_SERVICE_NAME:-polyglot-admin}"

source "$SCRIPT_DIR/scripts/deploy_preflight.sh"
deploy_preflight "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/deploy_build_targets.sh"

SHA=$(deploy_build_sha "$SCRIPT_DIR")

echo -e "${GREEN}[INFO]${NC} Deploying the ADMIN backend (tagged, no-traffic-first) at $SHA..."
echo -e "${GREEN}[INFO]${NC}    project: $PROJECT   service: $ADMIN_SERVICE_NAME"

run_build_targets "$SHA" admin-service

echo -e "${GREEN}[INFO]${NC} Admin backend deployed and traffic shifted."
echo -e "${YELLOW}[NOTE]${NC} No console UI is deployed by this script."
echo -e "${YELLOW}[NOTE]${NC}   ./deploy-admin-console.sh  deploys the console."
