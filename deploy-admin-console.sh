#!/bin/bash
# deploy-admin-console.sh - Deploy the admin console to its CANDIDATE Hosting
# site first, then (after a manual sanity check) its LIVE site
# (bd polyglot-pdf-b6943).
#
# A THIN WRAPPER OVER CLOUD BUILD (bd polyglot-pdf-oqtm7, Epic 4 bead 4.6).
# The build/deploy is cloudbuild.yaml's `admin-console-candidate` and
# `admin-console` targets: each resolves the live admin service URL, builds
# admin-console in hosted mode, and deploys its own Hosting target. This
# script refuses a dirty or unpushed tree, then runs the right target's
# trigger at the current commit and streams its log.
#
# WHY CANDIDATE-THEN-LIVE, UNLIKE deploy-editor.sh (which has one site). The
# admin console is the front end for the ONE admin service that backs BOTH
# staging's and the demo's data (admin_backend/main.py -- "THE ADMIN SERVICE
# HAS NO CHANNEL"), so there is no cheap staging channel to catch a bad
# console build the way deploy-staging.sh protects the demo app. Mirroring the
# admin service's own tagged-no-traffic-then-shift pattern, the console gets a
# two-site equivalent: a deploy lands on polyglot-admin-candidate, an operator
# eyeballs it, and ONLY a second explicit run of this script (with --live)
# deploys the same commit to polyglot-admin-demo, the site every admin
# actually uses day to day.
#
# A PREVIEW CHANNEL (`firebase hosting:channel:deploy`) is DELIBERATELY NOT
# used instead of a second named site -- see the plan's "Console app"
# section: preview channels mint a random-hash URL per deploy, which would
# have to be re-added to Firebase Auth's authorized-domains list and to the
# admin service's CORS_EXTRA_ORIGINS on every single deploy. A fixed
# candidate site's domain is authorized ONCE, like polyglot-admin-demo's.
#
# ONE-TIME setup (per project, before the first console deploy):
#   1. Create BOTH sites (names are globally unique across Firebase):
#        firebase hosting:sites:create polyglot-admin-demo --project polyglot-demo-aa709
#        firebase hosting:sites:create polyglot-admin-candidate --project polyglot-demo-aa709
#   2. Map both deploy targets (mappings persist in .firebaserc "targets";
#      this repo ships the demo project's mapping already -- re-run
#      target:apply only for a NEW project):
#        firebase target:apply hosting admin polyglot-demo-aa709 --project polyglot-demo-aa709
#        firebase target:apply hosting admin-candidate polyglot-admin-candidate --project polyglot-demo-aa709
#   3. AUTHORIZED DOMAINS for BOTH sites. Each is a SEPARATE Hosting site, and
#      Firebase Auth refuses sign-in from any domain not on the project's
#      list -- with the whole config present and valid, so no build check
#      can catch it (same trap as the schema editor's deploy-editor.sh).
#      Firebase usually auto-authorizes sites created under the same
#      project; VERIFY rather than assume:
#        Firebase console -> Authentication -> Settings -> Authorized domains
#      Confirm BOTH "polyglot-admin-demo.web.app" and
#      "polyglot-admin-candidate.web.app" are listed (and any custom
#      domains). The console's sign-in screen names this case explicitly if
#      it fires.
#   4. Grant each operator admin-console access (bd polyglot-pdf-7w17m) --
#      there is no shared secret; per-person Firebase custom claims are the
#      only gate:
#        python scripts/bootstrap_admin_user.py --email you@example.com --project polyglot-demo-aa709
#      This STAMPS the app_admin claim on an EXISTING Firebase Auth account
#      -- it does not create one, and the console offers no self-serve
#      signup. See the script's own docstring for --revoke and --list.
#   5. The ADMIN SERVICE's own CORS allowlist (admin_backend/main.py, set from
#      deploy/channels/admin.env's CORS_EXTRA_ORIGINS) already lists both
#      admin sites' .web.app and .firebaseapp.com domains -- nothing to do
#      here unless a custom domain is added later, in which case that file
#      needs it too.
#
# Usage:
#   ./deploy-admin-console.sh              # deploys the CANDIDATE site only
#   ./deploy-admin-console.sh --live       # deploys the LIVE site only (run
#                                          # this SECOND, after checking candidate)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADMIN_SITE="${ADMIN_SITE:-polyglot-admin-demo}"
ADMIN_CANDIDATE_SITE="${ADMIN_CANDIDATE_SITE:-polyglot-admin-candidate}"

DEPLOY_LIVE=false
for arg in "$@"; do
    case "$arg" in
        --live)
            DEPLOY_LIVE=true
            ;;
        *)
            # UNKNOWN ARG IS FATAL (mirrors deploy-staging.sh/deploy-demo.sh,
            # bd polyglot-pdf-7aez9). Without a catch-all arm a typo like
            # --Live or -live matches nothing, DEPLOY_LIVE stays false, and
            # the script silently falls through to the CANDIDATE deploy while
            # printing a normal success banner. The operator then believes
            # they promoted the live site when they only redeployed the
            # candidate.
            echo "[ERROR] Unknown argument: $arg" >&2
            echo "Usage: $0 [--live]" >&2
            exit 1
            ;;
    esac
done

source "$SCRIPT_DIR/scripts/deploy_preflight.sh"
deploy_preflight "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/deploy_build_targets.sh"

if [ "$DEPLOY_LIVE" = true ]; then
    TARGET="admin-console"
    SITE_NAME="$ADMIN_SITE"
else
    TARGET="admin-console-candidate"
    SITE_NAME="$ADMIN_CANDIDATE_SITE"
fi

SHA=$(deploy_build_sha "$SCRIPT_DIR")

echo "Deploying the admin console ($TARGET) at $SHA..."
run_build_targets "$SHA" "$TARGET"

echo ""
if [ "$DEPLOY_LIVE" = true ]; then
    echo "Admin console (LIVE) deployed: https://$SITE_NAME.web.app"
else
    echo "Admin console (CANDIDATE) deployed: https://$SITE_NAME.web.app"
    echo "Sign in there and confirm GET /admin/whoami works end to end, then"
    echo "deploy the SAME commit to the live site with:"
    echo "  ./deploy-admin-console.sh --live"
fi
