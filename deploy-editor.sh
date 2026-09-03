#!/bin/bash
# deploy-editor.sh - Build + deploy the HOSTED schema editor to its own
# Firebase Hosting site (bd polyglot-pdf-92qe.4).
#
# The voice app and the editor are separate Hosting SITES in the same Firebase
# project: the voice app keeps its /api rewrite; the editor has NO rewrite (it
# calls Cloud Run directly via VITE_API_BASE_URL -- the Hosting rewrite's 60s
# cap would kill minutes-long extraction requests, so CORS_EXTRA_ORIGINS on the
# backend allows the editor origin instead).
#
# ONE-TIME setup (per project, before the first editor deploy):
#   1. Create the site (name is globally unique across Firebase):
#        firebase hosting:sites:create "$EDITOR_SITE" --project "$PROJECT"
#   2. Map BOTH deploy targets (the voice app keeps the default site):
#        firebase target:apply hosting app "$PROJECT" --project "$PROJECT"
#        firebase target:apply hosting editor "$EDITOR_SITE" --project "$PROJECT"
#      (Mappings persist in .firebaserc "targets"; this repo ships the demo
#      mapping already -- re-run target:apply only for a NEW project/site.)
#   3. Grant each person editor access (bd polyglot-pdf-hn0jq): there is no
#      shared secret any more -- per-person Firebase custom claims are the
#      only gate, and the old SCHEMA_EDITOR_TOKEN / SCHEMA_AUTHOR_TOKEN env
#      vars were deleted outright in bd polyglot-pdf-rhc2v (inert if still
#      attached to a deployed service; drop them at the next deploy). REQUIRED
#      before anyone's first sign-in: the editor signs them in with Firebase
#      (bd polyglot-pdf-yswp3), and a valid account with no role claim is then
#      refused with 403 ("This account does not have schema editor access"):
#        python scripts/bootstrap_editor_user.py --email you@example.com --role editor
#      This STAMPS a role on an EXISTING Firebase Auth account -- it does not
#      create one, and fails with "No Firebase account for ..." if the person
#      has never had one. The sign-in screen deliberately offers no account
#      creation (editor access is granted, never self-served), so the operator
#      creates the person's Firebase Auth account first (Firebase console, or
#      Admin SDK/gcloud) and then runs the command above. A person who forgot
#      their password can self-serve a reset from the sign-in screen.
#      See scripts/README.md / the script's own docstring for --revoke, --list,
#      and the author role.
#      The BUILD also needs the VITE_FIREBASE_* values (committed in
#      schema-editor/.env.hosted -- public client ids, not secrets); a build
#      without them renders an explicit "no Firebase configuration" screen.
#   3b. AUTHORIZED DOMAIN for the editor site. The editor is a SEPARATE
#      Hosting site from the voice app, and Firebase Auth refuses sign-in
#      from any domain not on the project's list -- with the whole config
#      present and valid, so no build check can catch it. Firebase usually
#      auto-authorizes sites created under the same project; VERIFY rather
#      than assume, because the failure only appears at a human's first
#      sign-in attempt:
#        Firebase console -> Authentication -> Settings -> Authorized domains
#      Confirm "$EDITOR_SITE.web.app" is listed (and any custom domain).
#      The sign-in screen names this case explicitly if it fires.
#      CORS_EXTRA_ORIGINS + EXTRACTOR_MODEL ride the normal backend deploy env
#      (deploy-demo.sh exports them via BACKEND_EXTRA_ENV).
#   4. Bucket WRITE access for the editor surface (reads work today; saves 403
#      until granted). Resolve the service's RUNTIME identity first (on the
#      demo it is polyglot-backend-sa@...; a project that never set
#      BACKEND_SERVICE_ACCOUNT runs on the default compute SA,
#      <PROJECT_NUMBER>-compute@developer.gserviceaccount.com):
#        SA=$(gcloud run services describe polyglot-backend --region us-central1 \
#          --project "$PROJECT" --format='value(spec.template.spec.serviceAccountName)')
#        gcloud storage buckets add-iam-policy-binding "gs://$FORM_KITS_BUCKET" \
#          --member="serviceAccount:$SA" \
#          --role=roles/storage.objectAdmin --project "$PROJECT"
#
# Usage:
#   PROJECT=polyglot-demo-aa709 EDITOR_SITE=polyglot-editor-demo ./deploy-editor.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${PROJECT:-polyglot-demo-aa709}"
EDITOR_SITE="${EDITOR_SITE:-polyglot-editor-demo}"
BACKEND_SERVICE_NAME="${BACKEND_SERVICE_NAME:-polyglot-backend}"
REGION="${REGION:-us-central1}"

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
# MUST match the sibling copy in the other deploy script EXACTLY -- this
# block is duplicated in deploy-all.sh and backend/deploy-new.sh, and
# tests/test_deploy_reachability_gate.py pins the two byte-identical.
# Any edit here must be made in both.
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

# Resolve the LIVE backend URL at deploy time and inject it, instead of trusting
# the committed VITE_API_BASE_URL literal in .env.hosted (bd polyglot-pdf-emm7).
# The Cloud Run auto-URL hash is NOT stable -- it changed (d3mhrrkwfq ->
# won24rgefq) on a service recreate and every editor access-code entry then hit a
# 404'd backend, looking like a wrong password. A shell VITE_* overrides the
# .env.hosted value (standard Vite precedence), so the committed literal becomes a
# documented fallback, not a landmine. Let a caller-provided VITE_API_BASE_URL win
# (e.g. a local full-stack test pointing at http://localhost:8000).
if [ -z "$VITE_API_BASE_URL" ]; then
    RESOLVED_BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE_NAME" --platform managed --region "$REGION" --project "$PROJECT" --format 'value(status.url)' 2>/dev/null || true)
    if [ -n "$RESOLVED_BACKEND_URL" ]; then
        export VITE_API_BASE_URL="$RESOLVED_BACKEND_URL"
        echo "Injecting live backend URL into build: VITE_API_BASE_URL=$VITE_API_BASE_URL"

        # REACHABILITY WARNING (bd polyglot-pdf-dldwb). Resolving a URL
        # proves the service EXISTS, not that anyone may call it --
        # `describe` answers whether or not an allUsers invoker binding was
        # ever granted. Without this the editor could ship pinned to a
        # backend that 403s every request while the deploy reports success,
        # and because schema-editor/src/utils/remoteKitStore.ts routes EVERY
        # editor call through VITE_API_BASE_URL (kit list, draft save,
        # publish, the editing lock), a contractor would see what looks like
        # an access-code failure and report an auth problem.
        #
        # WARN, not abort -- same reasoning as deploy-all.sh's frontend
        # stage: this backend is PRE-EXISTING and possibly mid-fix by
        # someone else, so refusing to ship the editor over its IAM state
        # would be the gate crying wolf. The backend stage aborts because
        # there the deploy had just created the service itself.
        verify_service_publicly_reachable \
            "$BACKEND_SERVICE_NAME" "$REGION" "$PROJECT" warn
    else
        echo "WARN: could not resolve live backend URL; build falls back to VITE_API_BASE_URL in .env.hosted (may be stale -- bd polyglot-pdf-emm7)" >&2
    fi
fi

echo "Building the hosted editor (mode hosted -> .env.hosted)..."
cd "$SCRIPT_DIR/schema-editor"
if [ ! -d node_modules ]; then npm install; fi
npm run build:hosted

echo "Deploying ONLY the editor hosting target to $PROJECT..."
cd "$SCRIPT_DIR"
firebase deploy --only "hosting:editor" --project "$PROJECT"

echo ""
echo "Hosted editor deployed: https://$EDITOR_SITE.web.app"
echo "Share that URL plus an access code with a contractor:"
echo "  - editor code  -> polish the provided forms"
echo "  - author code  -> also upload PDFs + run extraction"
