#!/bin/bash
# deploy-admin-console.sh - Build + deploy the admin console to its
# CANDIDATE Hosting site first, then (after a manual sanity check) its LIVE
# site (bd polyglot-pdf-b6943).
#
# WHY CANDIDATE-THEN-LIVE, UNLIKE deploy-editor.sh (which has one site). The
# admin console is the front end for the ONE admin service that backs BOTH
# staging's and the demo's data (admin_backend/main.py -- "THE ADMIN SERVICE
# HAS NO CHANNEL"), so there is no cheap staging channel to catch a bad
# console build the way deploy-staging.sh protects the demo app. Mirroring
# deploy-admin.sh's tagged-no-traffic-then-shift pattern for the BACKEND,
# this script gives the CONSOLE its own two-site equivalent: every deploy
# lands on polyglot-admin-candidate first, an operator eyeballs it, and ONLY
# a second explicit run of this script (with --live) promotes the SAME build
# to polyglot-admin-demo, the site every admin actually uses day to day.
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
#        firebase hosting:sites:create polyglot-admin-demo --project "$PROJECT"
#        firebase hosting:sites:create polyglot-admin-candidate --project "$PROJECT"
#   2. Map both deploy targets (mappings persist in .firebaserc "targets";
#      this repo ships the demo project's mapping already -- re-run
#      target:apply only for a NEW project):
#        firebase target:apply hosting admin "$PROJECT" --project "$PROJECT"
#        firebase target:apply hosting admin-candidate polyglot-admin-candidate --project "$PROJECT"
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
#        python scripts/bootstrap_admin_user.py --email you@example.com --project "$PROJECT"
#      This STAMPS the app_admin claim on an EXISTING Firebase Auth account
#      -- it does not create one, and the console offers no self-serve
#      signup. See the script's own docstring for --revoke and --list.
#   5. The ADMIN SERVICE's own CORS allowlist (admin_backend/main.py, set by
#      deploy-admin.sh's ADMIN_CORS_ORIGINS) already lists both admin sites'
#      .web.app and .firebaseapp.com domains -- nothing to do here unless a
#      custom domain is added later, in which case deploy-admin.sh needs it
#      too.
#
# Usage:
#   ./deploy-admin-console.sh              # deploys the CANDIDATE site only
#   ./deploy-admin-console.sh --live       # deploys the LIVE site only (run
#                                           # this SECOND, after checking candidate)
#   PROJECT=polyglot-demo-aa709 ./deploy-admin-console.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${PROJECT:-polyglot-demo-aa709}"
ADMIN_SITE="${ADMIN_SITE:-polyglot-admin-demo}"
ADMIN_CANDIDATE_SITE="${ADMIN_CANDIDATE_SITE:-polyglot-admin-candidate}"
ADMIN_SERVICE_NAME="${ADMIN_SERVICE_NAME:-polyglot-admin}"
REGION="${REGION:-us-central1}"

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
            # candidate -- the exact false-confidence bug 7aez9 exists to
            # stop, just with a milder consequence here (candidate, not
            # nothing).
            echo "[ERROR] Unknown argument: $arg" >&2
            echo "Usage: $0 [--live]" >&2
            exit 1
            ;;
    esac
done

if [ "$DEPLOY_LIVE" = true ]; then
    HOSTING_TARGET="admin"
    SITE_NAME="$ADMIN_SITE"
else
    HOSTING_TARGET="admin-candidate"
    SITE_NAME="$ADMIN_CANDIDATE_SITE"
fi

# Verify a just-deployed Cloud Run service is PUBLICLY REACHABLE, and abort if
# it is not (bd polyglot-pdf-pidtg, extended to this script by bd
# polyglot-pdf-6oi9s).
#
# THE GATE ITSELF LIVES IN scripts/verify_service_reachable.py NOW (bd
# polyglot-pdf-ywxoh, 4.2). Four bash scripts used to each carry a
# byte-identical copy of this function's BODY (deploy-all.sh, backend/deploy-
# new.sh, deploy-editor.sh, deploy-admin-console.sh) -- pinned equal by
# tests/test_deploy_reachability_gate.py. cloudbuild.yaml's build steps need
# the SAME check and cannot source a bash function, so rather than add a
# FIFTH hand copy for the build, the check itself moved to one python module
# that both the build and every bash wrapper call. This function is now a
# THIN SHELL WRAPPER around that module -- kept so every call site below
# reads exactly as it always has (`verify_service_publicly_reachable "$SVC"
# "$REGION" "$PROJECT" [warn]`), with its bare-command shape (no pipe, no
# subshell, no `if`) still load-bearing: `exit 1` inside this function must
# still terminate the CALLING script, which a subshell would swallow.
#
# ${BASH_SOURCE[0]} here is THIS FILE (the function is defined inline, not
# sourced from elsewhere), so the module path resolves correctly regardless
# of the caller's own cwd or SCRIPT_DIR/REPO_ROOT naming.
#
# find_manifest_python-STYLE interpreter resolution, inlined rather than
# shared: python3 is not guaranteed on Windows Git Bash, and a python3
# App-Execution-Alias stub can exist on PATH without being able to run.
#
# Args: $1 service name, $2 region, $3 project id, $4 severity ("fatal"
# default, or "warn").
verify_service_publicly_reachable() {
    local svc="$1" region="$2" project="$3" severity="${4:-fatal}"
    local self_dir module py cand rc
    self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # This function is defined inline in FOUR files at two different repo
    # depths (the three root-level wrappers, and backend/deploy-new.sh one
    # directory down), so the module is looked up at both candidate paths
    # relative to THIS file rather than assuming the repo root.
    if [ -f "$self_dir/scripts/verify_service_reachable.py" ]; then
        module="$self_dir/scripts/verify_service_reachable.py"
    else
        module="$self_dir/../scripts/verify_service_reachable.py"
    fi
    for cand in ${MANIFEST_PYTHON_CANDIDATES:-python3 python py}; do
        if "$cand" -c "pass" >/dev/null 2>&1; then py="$cand"; break; fi
    done
    if [ -z "$py" ]; then
        echo "[ERROR] No python interpreter found -- cannot run the reachability gate; aborting deploy." >&2
        exit 1
    fi
    "$py" "$module" "$svc" "$region" "$project" --severity "$severity"
    rc=$?
    if [ "$rc" -ne 0 ]; then
        exit 1
    fi
    return 0
}

# Resolve the LIVE admin service URL at deploy time and inject it, instead of
# trusting the committed VITE_ADMIN_API_BASE_URL literal in
# admin-console/.env.hosted -- mirrors deploy-editor.sh's VITE_API_BASE_URL
# resolution and the same auto-URL-hash-instability reasoning
# (bd polyglot-pdf-emm7). A caller-provided VITE_ADMIN_API_BASE_URL wins
# (e.g. a local full-stack test pointing at http://localhost:8001, the admin
# backend's local dev port).
if [ -z "$VITE_ADMIN_API_BASE_URL" ]; then
    RESOLVED_ADMIN_URL=$(gcloud run services describe "$ADMIN_SERVICE_NAME" --platform managed --region "$REGION" --project "$PROJECT" --format 'value(status.url)' 2>/dev/null || true)
    if [ -n "$RESOLVED_ADMIN_URL" ]; then
        export VITE_ADMIN_API_BASE_URL="$RESOLVED_ADMIN_URL"
        echo "Injecting live admin service URL into build: VITE_ADMIN_API_BASE_URL=$VITE_ADMIN_API_BASE_URL"

        # REACHABILITY WARNING -- same reasoning as deploy-editor.sh's: this
        # admin service is PRE-EXISTING (deploy-admin.sh's job, not this
        # script's) and possibly mid-fix by someone else, so refusing to
        # ship the console over its IAM state would be the gate crying wolf.
        verify_service_publicly_reachable \
            "$ADMIN_SERVICE_NAME" "$REGION" "$PROJECT" warn
    else
        echo "WARN: could not resolve live admin service URL; build falls back to VITE_ADMIN_API_BASE_URL in admin-console/.env.hosted (may be stale)" >&2
    fi
fi

echo "Building the hosted admin console (mode hosted -> .env.hosted)..."
cd "$SCRIPT_DIR/admin-console"
if [ ! -d node_modules ]; then npm install; fi
npm run build:hosted

echo "Deploying ONLY the $HOSTING_TARGET hosting target to $PROJECT..."
cd "$SCRIPT_DIR"
firebase deploy --only "hosting:$HOSTING_TARGET" --project "$PROJECT"

echo ""
if [ "$DEPLOY_LIVE" = true ]; then
    echo "Admin console (LIVE) deployed: https://$SITE_NAME.web.app"
else
    echo "Admin console (CANDIDATE) deployed: https://$SITE_NAME.web.app"
    echo "Sign in there and confirm GET /admin/whoami works end to end, then"
    echo "promote the SAME build to the live site with:"
    echo "  ./deploy-admin-console.sh --live"
fi
