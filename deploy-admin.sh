#!/bin/bash
# deploy-admin.sh - Deploy the privileged admin backend (Cloud Run:
# polyglot-admin) as a NO-TRAFFIC TAGGED REVISION, verified, then shifted.
#
# Sprint 22 Epic 1, plan docs/sprint_22_admin-console_plan.md, bead 1.3
# ("Admin service" SA + staging tier + first deploy). Bead 1.1 (PR #732)
# shipped the admin_backend/ package, the shared image's runtime APP_MODULE
# selector, and scripts/setup-admin-service.sh (the admin-backend-sa
# provisioning script -- run THAT first, once per project, before this
# script's first run). Bead 1.2 (PR #733) shipped require_app_admin and
# GET /admin/whoami, the service's first real route.
#
# WHY A TAGGED NO-TRAFFIC DEPLOY, UNLIKE deploy-staging.sh / deploy-demo.sh.
# There is ONE admin service and ONE console site backing BOTH channels'
# data (the admin service has no channel of its own -- see the plan's
# "Architecture" section) -- so a bad admin deploy takes the control plane
# down for staging AND the demo at once. Every deploy here therefore lands as
# a Cloud Run revision that receives ZERO traffic
# (`gcloud run deploy --no-traffic --tag candidate`), gets its OWN stable
# health-checked at its own tag URL, and ONLY THEN receives 100% of traffic
# (`gcloud run services update-traffic --to-latest`) -- deploy-all.sh's
# BACKEND_NO_TRAFFIC_TAG mechanism, set below. A revision that fails its
# health check never serves a single request; the previous good revision
# keeps serving throughout.
#
# WHAT THIS SCRIPT DOES NOT DO. It deploys the BACKEND only -- the
# admin-console Vite app (its own candidate + live Hosting sites) is bead
# 1.7's scope, landing in its own deploy-admin-console.sh. Running this script
# alone stands the API up with no UI in front of it yet; that is a legitimate
# intermediate state (bead 1.2's routes are already reachable by curl + a
# bearer token from bootstrap_admin_user.py).
#
# ONE-TIME setup, before the first admin deploy:
#   1. Run scripts/setup-admin-service.sh <PROJECT_ID> once to create
#      admin-backend-sa and grant its roles (idempotent; safe to re-run).
#   2. Stamp the FIRST app_admin account:
#        python scripts/bootstrap_admin_user.py --email you@example.com
#   3. The org's domain-restricted-sharing policy may REFUSE the allUsers
#      invoker binding this script's --allow-unauthenticated requests --
#      exactly the failure mode verify_service_publicly_reachable() (deploy-
#      all.sh) exists to catch, and it bites hardest on a BRAND NEW service
#      like this one. If it fires, either grant the binding by hand
#      (the gate's own error message names the exact command) or relax the
#      org policy for this project -- both maintainer actions. See
#      docs/doctrine/promotion-tiers.md.
#
# Usage:
#   ./deploy-admin.sh
#
# Every run deploys the admin backend only; there is no --frontend/--form-
# kits split here because this script has neither. Re-run it any time the
# admin_backend/ package changes.

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT="${PROJECT:-polyglot-demo-aa709}"
ADMIN_SERVICE_NAME="${ADMIN_SERVICE_NAME:-polyglot-admin}"
SA_EMAIL="admin-backend-sa@$PROJECT.iam.gserviceaccount.com"

echo -e "${GREEN}[INFO]${NC} 🔐 Deploying the ADMIN backend (tagged, no-traffic-first)..."
echo -e "${GREEN}[INFO]${NC}    project: $PROJECT   service: $ADMIN_SERVICE_NAME"

export POLYGLOT_PROJECT_NAME="$PROJECT"

# ADMIN_SERVICE_URL / SWEEP_SCHEDULER_SA_EMAIL (bd polyglot-pdf-8vgfh cross-
# surface review finding 3, Epic 2 bead B5's sweep-route OIDC gate). These
# used to be set ONLY by an operator's one-time, hand-run `gcloud run
# services update ... --update-env-vars` (scripts/setup-admin-service.sh's
# own printed NOTE) -- but --set-env-vars below REPLACES the service's
# ENTIRE env block (this script's own comment on --set-secrets makes
# exactly this point about that flag; --set-env-vars behaves the same way),
# so the very next run of THIS script silently wiped that hand-set
# binding, fail-closing the sweep route (503) with no test or alert able to
# notice. Both values are now folded into BACKEND_EXTRA_ENV below so every
# deploy re-asserts them instead of erasing them.
#
# SWEEP_SCHEDULER_SA_EMAIL is fully knowable ahead of time: scripts/setup-
# admin-service.sh's SCHEDULER_SA_NAME is a fixed literal
# ("admin-sweep-scheduler-sa"), so its email is constructible with no
# gcloud lookup, mirroring SA_EMAIL immediately above.
SWEEP_SCHEDULER_SA_EMAIL="admin-sweep-scheduler-sa@$PROJECT.iam.gserviceaccount.com"

# ADMIN_SERVICE_URL is NOT knowable before the service's FIRST deploy (it is
# assigned by Google at deploy time -- the same reason ADMIN_URL below is
# read only AFTER deploy-all.sh runs). On every deploy AFTER the first,
# though, the URL is already stable, so this lookup succeeds if run BEFORE
# deploying (unlike ADMIN_URL below, which must be read after) and can be
# folded into THIS SAME deploy's env vars -- durable across every later
# deploy, instead of a separate hand-run step this script keeps erasing.
# `2>/dev/null || true` makes a not-yet-existing service (the true first
# deploy) resolve to an empty string rather than aborting the script
# (`set -e`) -- on that one run ADMIN_SERVICE_URL stays unset exactly as it
# does today, and the sweep route correctly stays fail-closed (503) until an
# operator re-runs this script once more after the service exists.
ADMIN_SERVICE_URL=$(gcloud run services describe "$ADMIN_SERVICE_NAME" \
    --platform managed --region us-central1 --project "$PROJECT" \
    --format 'value(status.url)' 2>/dev/null || true)
SWEEP_ENV="SWEEP_SCHEDULER_SA_EMAIL=$SWEEP_SCHEDULER_SA_EMAIL"
[ -n "$ADMIN_SERVICE_URL" ] && SWEEP_ENV="$SWEEP_ENV,ADMIN_SERVICE_URL=$ADMIN_SERVICE_URL"

# CORS_EXTRA_ORIGINS (admin_backend/main.py): the admin CONSOLE is a separate
# Vite app on its own Hosting site(s) (bead 1.7 -- polyglot-admin-demo and the
# polyglot-admin-candidate staging site), always cross-origin from this
# service's point of view. The main app's firm-manager /console/* pages also
# call this service directly (Epic 2), from BOTH channels' app origins. List
# every known caller explicitly here -- semicolon-separated, matching
# parse_extra_origins -- rather than relying on the admin sites existing yet:
# an operator can run this script before bead 1.7 lands, and a 403-by-CORS on
# a route that otherwise works is a confusing failure to debug blind. EVERY
# origin below is listed on BOTH its .web.app and .firebaseapp.com domains --
# every Firebase Hosting site is reachable at both simultaneously by default
# (platform behavior, matching deploy-demo.sh's / deploy-staging.sh's own
# CORS_EXTRA_ORIGINS convention for the schema-editor sites) -- missing either
# alias here means a page served from that domain gets CORS-rejected.
ADMIN_CORS_ORIGINS="https://polyglot-admin-demo.web.app;https://polyglot-admin-demo.firebaseapp.com;https://polyglot-admin-candidate.web.app;https://polyglot-admin-candidate.firebaseapp.com;https://polyglot-app-staging.web.app;https://polyglot-app-staging.firebaseapp.com;https://$PROJECT.web.app;https://$PROJECT.firebaseapp.com"

BACKEND_NO_TRAFFIC_TAG="candidate" \
    BACKEND_EXTRA_ENV="CORS_EXTRA_ORIGINS=$ADMIN_CORS_ORIGINS,$SWEEP_ENV" \
    BACKEND_SERVICE_ACCOUNT="$SA_EMAIL" \
    BACKEND_SERVICE_NAME="$ADMIN_SERVICE_NAME" \
    APP_MODULE="admin_backend.main:app" \
    ./deploy-all.sh --backend

ADMIN_URL=$(gcloud run services describe "$ADMIN_SERVICE_NAME" \
    --platform managed --region us-central1 --project "$PROJECT" \
    --format 'value(status.url)')

echo -e "${GREEN}[INFO]${NC} ✅ Admin backend deployed and traffic shifted."
echo -e "${GREEN}[INFO]${NC} URL: $ADMIN_URL"
echo -e "${YELLOW}[NOTE]${NC} No console UI is deployed by this script (bead 1.7)."
echo -e "${YELLOW}[NOTE]${NC} Verify by hand: curl $ADMIN_URL/health"
