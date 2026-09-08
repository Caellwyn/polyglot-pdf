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

# NOTE: the block below is byte-identical to the copies in deploy-all.sh,
# backend/deploy-new.sh and deploy-editor.sh -- tests/test_deploy_reachability_gate.py
# pins all four copies equal. Any edit to the gate must be made in all four.
#
# Verify a just-deployed Cloud Run service is PUBLICLY REACHABLE, and abort if
# it is not (bd polyglot-pdf-pidtg, extended to this script by bd
# polyglot-pdf-6oi9s).
#
# WHY THIS EXISTS. A `gcloud run` deployment with --allow-unauthenticated only
# REQUESTS an
# allUsers -> roles/run.invoker binding, but that request can be REFUSED while
# the deploy still succeeds and exits 0. The domain-restricted-sharing org
# policy (constraints/iam.allowedPolicyMemberDomains) rejects allUsers; gcloud
# creates the service, prints a NON-FATAL warning, and exits 0 -- leaving a
# service that 403s every request at Cloud Run's own gate, BEFORE any
# application code runs. The app then shows an auth error that has nothing to do
# with app auth, sending the operator to debug the wrong layer entirely.
#
# It bites only a NEW service: an existing one's binding predates the policy and
# is not retroactively stripped. So the scripts that create services are exactly
# where this must be checked.
#
# --flatten='bindings[].members' is LOAD-BEARING, and both halves of the query
# were got wrong once each before this was right:
#   1. Grepping the raw policy text for "allUsers" FALSE-PASSED: a
#      `roles/run.viewer -> allUsers` binding satisfied it while the INVOKER
#      binding was missing and the service still 403'd everything.
#   2. Adding --filter WITHOUT --flatten then FALSE-FAILED: --filter is
#      evaluated against the WHOLE policy resource, not per binding, and
#      `value(bindings.role)` emits every role ';'-joined on ONE line, so
#      `grep -qx` stopped matching as soon as a service had a SECOND binding.
# --flatten makes each member/role pair its own record, so the filter is
# genuinely per-binding and each surviving role prints on its own line.
#
# BOTH failure directions matter. Failing OPEN hides the bug behind a green
# check; failing CLOSED blocks a good deploy, and a gate that cries wolf gets
# deleted -- taking the real check with it. An inconclusive IAM READ therefore
# WARNS rather than aborting: being unable to check is not proof of breakage.
#
# stderr is NOT merged into the value (no 2>&1): a gcloud component-update nag
# landing in the variable could otherwise satisfy a text match on its own.
#
# Args: $1 service name, $2 region, $3 project id, $4 severity ("fatal"
# default, or "warn").
#
# SEVERITY. Exits 1 when the service is definitively unreachable; pass "warn" to
# downgrade that to a warning and return 0. The frontend stage passes "warn"
# because there the backend is pre-existing and possibly someone else's to fix
# (bd polyglot-pdf-816te); the backend stage takes the default, because a deploy
# that just CREATED an unreachable service must never exit 0
# (bd polyglot-pdf-pidtg).
#
# AN ARGUMENT, NOT AN ENV VAR, and that distinction is the point. The first cut
# read VERIFY_FAIL_IS_FATAL from the environment, which cannot tell "the frontend
# stage set this for one call" from "it was ambient in the operator's shell" --
# so an exported VERIFY_FAIL_IS_FATAL=false silently disarmed the BACKEND abort,
# reproducing the exact bug this gate exists to stop (caught by the pre-PR
# cross-surface review). A positional argument can only come from a real call
# site.
#
# MUST match the sibling copies EXACTLY. This block is duplicated in THREE
# scripts -- deploy-all.sh, backend/deploy-new.sh and deploy-editor.sh -- and
# tests/test_deploy_reachability_gate.py pins all three byte-identical.
# Any edit here must be made in all three.
verify_service_publicly_reachable() {
    local svc="$1" region="$2" project="$3" severity="${4:-fatal}" invoker_roles
    # Reuse the caller's log helpers WHEN THEY EXIST, so deploy-all.sh keeps its
    # coloured [WARN]/[ERROR] on stdout exactly as before this was extracted
    # (a pre-PR review caught the extraction silently moving them to stderr and
    # dropping the colour). The bootstrap script defines no such helpers, so it
    # falls back to plain stderr -- which is why the function must not simply
    # call log_warn/log_error unconditionally.
    _gate_warn()  { if declare -f log_warn  >/dev/null 2>&1; then log_warn  "$1"; else echo "[WARN] $1"  >&2; fi; }
    _gate_error() { if declare -f log_error >/dev/null 2>&1; then log_error "$1"; else echo "[ERROR] $1" >&2; fi; }
    invoker_roles=$(gcloud run services get-iam-policy "$svc" \
        --region "$region" --project "$project" \
        --flatten='bindings[].members' \
        --filter='bindings.members:allUsers' \
        --format='value(bindings.role)') || invoker_roles="__QUERY_FAILED__"

    if [ "$invoker_roles" = "__QUERY_FAILED__" ]; then
    _gate_warn "Could not read the IAM policy for $svc -- skipping the"
    _gate_warn "reachability check. If the app cannot reach the backend, verify manually:"
    _gate_warn "  gcloud run services get-iam-policy $svc --region $region --project $project"
        return 0
    fi
    if echo "$invoker_roles" | grep -qx "roles/run.invoker"; then
        return 0
    fi
    # Plain ASCII '=' -- a free choice, not a constraint. An earlier comment here
    # claimed the shell could not carry a box-drawing glyph because the tests
    # decode it as cp1252 on Windows; that was the TEST's defect (a
    # subprocess.run without encoding=), since fixed, and this function is
    # byte-identical in the sibling copy, which has no box-drawing at all.
    # ASCII simply travels everywhere without depending on the reader's codec.
    _gate_error "==========================================================="
    if [ "$severity" = "warn" ]; then
        _gate_error "  WARNING: the service is NOT publicly reachable"
    else
        _gate_error "  DEPLOY FAILED: the service is NOT publicly reachable"
    fi
    _gate_error "==========================================================="
    _gate_error "Service '$svc' has no allUsers invoker binding, so"
    _gate_error "Cloud Run will 403 EVERY request before your app ever sees it."
    _gate_error ""
    _gate_error "--allow-unauthenticated was passed, but the binding was refused --"
    _gate_error "almost always the domain-restricted-sharing org policy."
    _gate_error ""
    _gate_error "Fix it with:"
    _gate_error "  gcloud run services add-iam-policy-binding $svc \\"
    _gate_error "    --region $region --project $project \\"
    _gate_error "    --member=allUsers --role=roles/run.invoker"
    _gate_error ""
    _gate_error "If that is itself refused, the org policy must be relaxed for this"
    _gate_error "project first (constraints/iam.allowedPolicyMemberDomains)."
    _gate_error "See bd polyglot-pdf-pidtg."
    if [ "$severity" = "warn" ]; then
        _gate_warn "Continuing anyway (this stage treats an unreachable backend as a warning)."
        return 0
    fi
    exit 1
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
