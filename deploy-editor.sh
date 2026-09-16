#!/bin/bash
# deploy-editor.sh - Deploy the HOSTED schema editor to its own Firebase
# Hosting site (bd polyglot-pdf-92qe.4).
#
# A THIN WRAPPER OVER CLOUD BUILD (bd polyglot-pdf-oqtm7, Epic 4 bead 4.6).
# The build/deploy itself is cloudbuild.yaml's `editor` target: it resolves
# the live backend URL, builds schema-editor in hosted mode, and deploys the
# `editor` Hosting target. This script refuses a dirty or unpushed tree, then
# runs that target's trigger at the current commit and streams its log.
#
# The voice app and the editor are separate Hosting SITES in the same Firebase
# project: the voice app keeps its /api rewrite; the editor has NO rewrite (it
# calls Cloud Run directly via VITE_API_BASE_URL -- the Hosting rewrite's 60s
# cap would kill minutes-long extraction requests, so CORS_EXTRA_ORIGINS on the
# backend allows the editor origin instead).
#
# ONE-TIME setup (per project, before the first editor deploy):
#   1. Create the site (name is globally unique across Firebase):
#        firebase hosting:sites:create polyglot-editor-demo --project polyglot-demo-aa709
#   2. Map BOTH deploy targets (the voice app keeps the default site):
#        firebase target:apply hosting app polyglot-demo-aa709 --project polyglot-demo-aa709
#        firebase target:apply hosting editor polyglot-editor-demo --project polyglot-demo-aa709
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
#      Confirm polyglot-editor-demo.web.app is listed (and any custom domain).
#      The sign-in screen names this case explicitly if it fires.
#      CORS_EXTRA_ORIGINS + EXTRACTOR_MODEL ride the normal backend deploy
#      config (deploy/channels/<channel>.env).
#   4. Bucket WRITE access for the editor surface (reads work today; saves 403
#      until granted). Resolve the service's RUNTIME identity first (on the
#      demo it is polyglot-backend-sa@...; a project that never set
#      SERVICE_ACCOUNT in its channel file runs on the default compute SA,
#      <PROJECT_NUMBER>-compute@developer.gserviceaccount.com):
#        SA=$(gcloud run services describe polyglot-backend --region us-central1 \
#          --project polyglot-demo-aa709 --format='value(spec.template.spec.serviceAccountName)')
#        gcloud storage buckets add-iam-policy-binding "gs://polyglot-demo-aa709-form-kits" \
#          --member="serviceAccount:$SA" \
#          --role=roles/storage.objectAdmin --project polyglot-demo-aa709
#
# Usage:
#   ./deploy-editor.sh
#   EDITOR_SITE=polyglot-editor-demo ./deploy-editor.sh   # banner URL only

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDITOR_SITE="${EDITOR_SITE:-polyglot-editor-demo}"

# DEPLOY PREFLIGHT (bd polyglot-pdf-1s3ko): a build runs from a COMMIT and
# build_checks/{sha} vouches for that commit's test run, so a dirty or
# unpushed tree makes both claims false.
source "$SCRIPT_DIR/scripts/deploy_preflight.sh"
deploy_preflight "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/deploy_build_targets.sh"

SHA=$(deploy_build_sha "$SCRIPT_DIR")

echo "Deploying the hosted schema editor at $SHA..."
run_build_targets "$SHA" editor

echo ""
echo "Hosted editor deployed: https://$EDITOR_SITE.web.app"
echo "Share that URL with a contractor whose account carries an editor or"
echo "author role (scripts/bootstrap_editor_user.py):"
echo "  - editor role  -> polish the provided forms"
echo "  - author role  -> also upload PDFs + run extraction"
