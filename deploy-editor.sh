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
