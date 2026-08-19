#!/bin/bash
# deploy-all.sh - Unified deployment script for Polyglot PDF Form Filler
#
# Usage:
#   ./deploy-all.sh              # Deploy everything (backend, frontend, form-kits)
#   ./deploy-all.sh --backend    # Deploy backend only
#   ./deploy-all.sh --frontend   # Deploy frontend only
#   ./deploy-all.sh --form-kits  # Deploy form-kits only
#   ./deploy-all.sh --all        # Deploy everything (explicit)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Resolve a python interpreter for manifest validation. python3 is not
# guaranteed on Windows Git Bash, so fall back to python, then the py
# launcher. Each candidate must actually RUN (-c pass), not merely exist:
# Windows ships a python3 App-Execution-Alias stub that command -v finds but
# that cannot execute, which would misreport every manifest as invalid.
# Candidates are env-overridable for tests. MUST match
# scripts/deploy-form-kit.sh's copy exactly.
find_manifest_python() {
    local cand
    for cand in ${MANIFEST_PYTHON_CANDIDATES:-python3 python py}; do
        if "$cand" -c "pass" >/dev/null 2>&1; then
            echo "$cand"
            return 0
        fi
    done
    return 1
}

# Validate the string-concatenated manifest JSON and pretty-print it into the
# output file. A validation FAILURE aborts the deploy: shipping invalid JSON
# silently breaks the voice app's form list with zero deploy-time signal
# (bd polyglot-pdf-4w0l). No python interpreter at all is also fatal -- with
# no validator we cannot know the manifest is safe to ship (gcloud itself
# requires Python, so a working deploy machine always has one). MUST match
# scripts/deploy-form-kit.sh's copy exactly.
write_validated_manifest() {
    local content="$1" out="$2" py
    if ! py=$(find_manifest_python); then
        log_error "No python interpreter found (tried: ${MANIFEST_PYTHON_CANDIDATES:-python3 python py}) -- cannot validate the manifest; aborting deploy."
        return 1
    fi
    if ! echo "$content" | "$py" -m json.tool > "$out" 2>/dev/null; then
        log_error "Generated manifest is INVALID JSON -- aborting deploy (nothing uploaded)."
        log_error "Offending manifest content: $content"
        return 1
    fi
}

# Complete-gate (bd polyglot-pdf-b0pe): only kits explicitly marked
# status:complete in metadata.json may reach GCS / the voice app. In-progress
# (draft) and unmarked kits stay LOCAL + git-backed but are never deployed, so a
# deploy run after a new form is onboarded cannot leak a draft to production.
# Returns 0 (complete) only when metadata.json exists AND its status is exactly
# "complete"; absent metadata.json or any other/absent status -> 1 (skip).
kit_is_complete() {
    local kit_dir="$1"
    local meta="$kit_dir/metadata.json"
    [ -f "$meta" ] || return 1
    # Match "status": "complete" tolerant of whitespace; no jq dependency.
    grep -Eq '"status"[[:space:]]*:[[:space:]]*"complete"' "$meta"
}

# Resolve a kit's schema filename (bd polyglot-pdf-snpi). metadata.json may carry
# a custom "schema" field (KitMetadata.schema in formKitDirectory.ts); when present
# the kit's schema lives in that file, NOT the hardcoded schema.json. Echoes the
# resolved filename; defaults to schema.json when metadata.json is absent or has no
# "schema" string -- mirroring the editor's `meta?.schema || 'schema.json'`.
#
# We FLATTEN newlines (tr -d) BEFORE the grep so a metadata.json with the "schema"
# key/value split across lines still matches -- a plain line-oriented grep would
# miss that form and silently fall back to schema.json, leaving the custom-schema
# kit skipped even though the editor's JSON.parse accepts it (Codex review, bd
# snpi). Pure POSIX text tools (tr/grep/sed), no jq or python dependency: python3
# is NOT reliably present (on Windows it can be the no-op Store shim), so the
# script must not lean on it. The sed also trims whitespace that sat inside the
# quotes ("schema": " custom.json ").
kit_schema_file() {
    local kit_dir="$1"
    local meta="$kit_dir/metadata.json"
    local name=""
    if [ -f "$meta" ]; then
        name=$(tr -d '\n' < "$meta" \
            | grep -Eo '"schema"[[:space:]]*:[[:space:]]*"[^"]+"' \
            | head -1 \
            | sed -E 's/.*:[[:space:]]*"[[:space:]]*([^"]*[^"[:space:]])[[:space:]]*".*/\1/')
    fi
    echo "${name:-schema.json}"
}

# Collect a kit's PUBLISHABLE children into the array named by $1, skipping any
# _-prefixed directory (bd polyglot-pdf-06u5o).
#
# "$kit_dir"/* used to be passed straight to the upload, and the `case $kit_id in
# _*)` guard above it filters only the TOP-LEVEL kit id -- not children inside a
# kit. So _archive/ (superseded revisions, bd w3zw) and _drafts/ (up to 10 draft
# snapshots per kit, bd y2l0p) both rode every deploy into the bucket. Nothing
# clears either ring on the status transition, so a kit carried them through
# promotion.
#
# NOT an --exclude flag: `gcloud storage cp` has no such flag (only `rsync`
# does), so that spelling would fail at deploy time. cp takes [SOURCE ...], so
# enumerating is the supported shape.
collect_publishable_kit_files() {
    local -n _out=$1
    local dir=$2
    local entry base
    _out=()
    for entry in "$dir"/*; do
        [ -e "$entry" ] || continue
        base=$(basename "$entry")
        case "$base" in _*) continue ;; esac
        _out+=("$entry")
    done
}

# When this file is SOURCED (not executed directly), stop here -- expose only the
# helper functions above and run none of the deploy flow below. This lets a test
# harness source the script to exercise kit_is_complete / kit_schema_file in
# isolation (bd polyglot-pdf-45x5) without triggering a real deploy. Direct
# execution (`./deploy-all.sh ...`) has BASH_SOURCE[0] == $0 and falls through.
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    return 0
fi

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
FORM_KITS_DIR="$SCRIPT_DIR/form-kits"

BACKEND_SERVICE_NAME="polyglot-backend"
REGION="us-central1"
# Demo bucket by default (bd polyglot-pdf-d7hy, enumerated the set after the
# outer cross-surface review caught this 4th caller), matching every other
# bucket-default in the repo (scripts/deploy-form-kit.sh, scripts/pull-form-
# kits.sh, schema-editor/vite-plugins/deployKitEndpoint.ts's DEFAULT_BUCKET)
# -- "unset" means demo everywhere, never a silent prod upload. Both
# deploy-demo.sh and deploy-production.sh export FORM_KITS_BUCKET explicitly
# before calling this script, so this default only matters for a bare
# `./deploy-all.sh --form-kits` invocation (DEPLOYMENT.md's documented usage);
# explicitly set FORM_KITS_BUCKET for a real prod deploy run this way.
FORM_KITS_BUCKET="${FORM_KITS_BUCKET:-polyglot-demo-aa709-form-kits}"
FORM_KITS_PREFIX="${FORM_KITS_PREFIX:-form-kits}"

# Frontend build command, overridable by the channel deploy scripts. The deployed
# app is the schema-forms app (index.html -> src/schema-forms/main.tsx), so the
# build MUST run the schema config so Vite loads the right .env per channel and
# bakes in the Firebase config:
#   demo -> build:schema:demo (--mode demo -> .env.demo, demo Firebase keys)
#   prod -> build:schema      (.env.production, prod Firebase keys)
# A bare "vite build" (npm run build) loads .env.production under the default
# config, which has no VITE_FIREBASE_* keys -- the app then dies at launch with
# Firebase "auth/invalid-api-key". Default to the prod schema build so a direct
# deploy-all.sh --frontend is safe.
FRONTEND_BUILD_CMD="${FRONTEND_BUILD_CMD:-npm run build:schema}"

# Print header
echo ""
log_info "═══════════════════════════════════════════════════════════"
log_info "  Polyglot PDF Form Filler - Unified Deployment Script   "
log_info "═══════════════════════════════════════════════════════════"
echo ""

# Parse arguments
DEPLOY_BACKEND=false
DEPLOY_FRONTEND=false
DEPLOY_FORM_KITS=false

if [ $# -eq 0 ] || [ "$1" = "--all" ]; then
    # No args or --all: deploy everything
    DEPLOY_BACKEND=true
    DEPLOY_FRONTEND=true
    DEPLOY_FORM_KITS=true
else
    for arg in "$@"; do
        case "$arg" in
            --backend)
                DEPLOY_BACKEND=true
                ;;
            --frontend)
                DEPLOY_FRONTEND=true
                ;;
            --form-kits)
                DEPLOY_FORM_KITS=true
                ;;
            *)
                log_error "Unknown argument: $arg"
                echo "Usage: $0 [--backend] [--frontend] [--form-kits] [--all]"
                exit 1
                ;;
        esac
    done
fi

# Check prerequisites
check_project() {
    if [ -z "$POLYGLOT_PROJECT_NAME" ]; then
        log_warn "POLYGLOT_PROJECT_NAME not set, trying to detect from gcloud..."
        POLYGLOT_PROJECT_NAME=$(gcloud config get-value project 2>/dev/null)
        if [ -z "$POLYGLOT_PROJECT_NAME" ] || [ "$POLYGLOT_PROJECT_NAME" = "(unset)" ]; then
            log_error "Could not determine project ID. Please set POLYGLOT_PROJECT_NAME or run: gcloud config set project <project-id>"
            exit 1
        fi
        log_info "Using detected project: $POLYGLOT_PROJECT_NAME"
    else
        log_info "Using project: $POLYGLOT_PROJECT_NAME"
    fi
}

# Display deployment plan
echo ""
log_info "Deployment Plan:"
log_info "  Backend:   $DEPLOY_BACKEND"
log_info "  Frontend:  $DEPLOY_FRONTEND"
log_info "  Form Kits: $DEPLOY_FORM_KITS"
echo ""

check_project

# ============================================================================
# BACKEND DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_BACKEND" = true ]; then
    log_info "═══════════════════════════════════════════════════════════"
    log_info "  DEPLOYING BACKEND TO CLOUD RUN"
    log_info "═══════════════════════════════════════════════════════════"
    echo ""
    
    # Build from the REPO ROOT (bd 92qe.3): the Dockerfile moved from backend/
    # to the root so the image can copy scripts/authoring + scripts/bakeoff --
    # the PDF->schema pipeline the hosted extraction route spawns. .gcloudignore
    # keeps the Cloud Build upload lean (no PDFs/node_modules/docs).
    cd "$SCRIPT_DIR"

    # No local-dependency self-heal here (unlike the frontend): the backend image
    # is built fresh by Cloud Build on every deploy, and the Dockerfile runs
    # "pip install -r requirements.txt" inside it. There is no local .venv in the
    # deploy path, so nothing local can go stale.

    # Enable necessary APIs
    log_info "Ensuring necessary Google Cloud APIs are enabled..."
    gcloud services enable run.googleapis.com \
        cloudbuild.googleapis.com \
        artifactregistry.googleapis.com \
        aiplatform.googleapis.com \
        storage.googleapis.com \
        texttospeech.googleapis.com \
        --project "$POLYGLOT_PROJECT_NAME"

    # Build the image using Cloud Build
    IMAGE_URL="gcr.io/$POLYGLOT_PROJECT_NAME/$BACKEND_SERVICE_NAME"
    log_info "Building container image: $IMAGE_URL (repo-root context)..."
    gcloud builds submit --tag "$IMAGE_URL" --project "$POLYGLOT_PROJECT_NAME" "$SCRIPT_DIR"
    
    # Deploy to Cloud Run
    log_info "🌐 Deploying to Cloud Run service: $BACKEND_SERVICE_NAME..."
    # BACKEND_EXTRA_ENV: channel deploy scripts append channel-specific env vars
    # here (e.g. the demo sets VERTEXAI=true,USE_PREMIUM_MODEL=false -- the demo
    # runs on Vertex ADC, see deploy-demo.sh).
    # Default empty -> prod keeps the Vertex defaults baked into config.py.
    # GEMINI_API_KEY is injected separately via Secret Manager (--set-secrets),
    # NOT here -- never put the key in plaintext env vars.
    # CONFIRMATION_FIRESTORE_ENABLED (bd polyglot-pdf-z2is): mirror the
    # liability confirmation trail to Firestore. Cloud Run's filesystem is
    # ephemeral tmpfs, so the file-only trail did NOT survive deployment --
    # every deployed env needs the durable sink. Metadata only, never values.
    # FIRMS_FIRESTORE_ENABLED (bd polyglot-pdf-vccy): enable the firms-store
    # READ path so firm staff see their firm's PRIVATE kits. Reads fail
    # CLOSED ([]), so the flag can only ever narrow what an outage shows.
    # (deploy-production.sh also sources this block, but that channel is dead
    # -- the former prod project is unreachable, purge bd polyglot-pdf-je6iy.)
    BACKEND_ENV="GOOGLE_CLOUD_PROJECT=$POLYGLOT_PROJECT_NAME,FORM_KITS_MODE=gcs,FORM_KITS_GCS_BUCKET=$FORM_KITS_BUCKET,FORM_KITS_REMOTE_PREFIX=$FORM_KITS_PREFIX,CONFIRMATION_FIRESTORE_ENABLED=true,FIRMS_FIRESTORE_ENABLED=true"
    [ -n "$BACKEND_EXTRA_ENV" ] && BACKEND_ENV="$BACKEND_ENV,$BACKEND_EXTRA_ENV"

    # BACKEND_SERVICE_ACCOUNT: when a channel deploy script exports it, set the
    # Cloud Run runtime identity IN THIS SAME deploy, so the new revision is
    # created+routed under the correct SA from the start. The demo needs a custom
    # SA (polyglot-backend-sa, holds roles/aiplatform.user for the Vertex path);
    # applying it here -- rather than in a SEPARATE post-deploy
    # `gcloud run services update` -- means a fresh service (or one whose identity
    # drifted) never briefly serves a Vertex revision under the wrong/default
    # identity, and a failed follow-up update can't strand the demo on a revision
    # that can't call Vertex (bd polyglot-pdf-ignt). Empty (the default, e.g. a
    # bare deploy-all.sh run) -> no --service-account, behavior unchanged.
    SA_FLAG=()
    [ -n "$BACKEND_SERVICE_ACCOUNT" ] && SA_FLAG=(--service-account "$BACKEND_SERVICE_ACCOUNT")

    # --timeout: Cloud Run kills any request at this limit, including live
    # WebSockets. The 300s default terminated every /ws/fill session at exactly
    # 5 minutes (bd polyglot-pdf-9w5k); 3600s is the Cloud Run maximum, so WS
    # lifetime is bounded by Gemini Live session limits (GoAway handling)
    # instead of the HTTP layer.
    # --memory: 1Gi headroom for hosted extraction (bd 92qe.4, Opus review of
    # PR #282): a run holds the form PDF (up to EXTRACTOR_MAX_PDF_MB) plus an
    # optional instructions PDF in route memory AND as tmpfs copies (/tmp is
    # memory-backed on Cloud Run) while the pipeline child runs -- the 512Mi
    # default risks an opaque OOM kill mid-extraction.
    gcloud run deploy "$BACKEND_SERVICE_NAME" \
        --image "$IMAGE_URL" \
        --region "$REGION" \
        --platform managed \
        --allow-unauthenticated \
        --timeout=3600 \
        --memory=1Gi \
        --project "$POLYGLOT_PROJECT_NAME" \
        --set-env-vars="$BACKEND_ENV" \
        "${SA_FLAG[@]}"
    
    BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE_NAME" --platform managed --region "$REGION" --project "$POLYGLOT_PROJECT_NAME" --format 'value(status.url)')
    log_success "✅ Backend deployed successfully!"
    echo "   URL: $BACKEND_URL"
    echo ""
    
    cd "$SCRIPT_DIR"
fi

# ============================================================================
# FORM KITS DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_FORM_KITS" = true ]; then
    log_info "═══════════════════════════════════════════════════════════"
    log_info "  DEPLOYING FORM KITS TO GCS"
    log_info "═══════════════════════════════════════════════════════════"
    echo ""
    
    # Create bucket if it doesn't exist
    if ! gcloud storage buckets describe "gs://$FORM_KITS_BUCKET" &>/dev/null; then
        log_info "Creating bucket gs://$FORM_KITS_BUCKET..."
        gcloud storage buckets create "gs://$FORM_KITS_BUCKET" \
            --location=us-central1 \
            --uniform-bucket-level-access \
            --project "$POLYGLOT_PROJECT_NAME"
        log_success "Bucket created successfully"
    fi
    
    # Upload all form kits
    log_info "📦 Uploading form kits..."
    for kit_dir in "$FORM_KITS_DIR"/*/; do
        [ -d "$kit_dir" ] || continue
        kit_id=$(basename "$kit_dir")

        # An _-prefixed dir is shared authoring data, not a kit (e.g.
        # form-kits/_translation/, the glossary from bd polyglot-pdf-ch7j).
        # Skip SILENTLY so it does not warn on every full deploy
        # (bd polyglot-pdf-qwex).
        case "$kit_id" in _*) continue ;; esac

        schema_file=$(kit_schema_file "$kit_dir")
        if [ ! -f "$kit_dir/$schema_file" ]; then
            log_warn "Skipping $kit_id - no $schema_file found"
            continue
        fi

        if ! kit_is_complete "$kit_dir"; then
            log_warn "Skipping $kit_id - not status:complete (draft kept local; bd b0pe gate)"
            continue
        fi

        log_info "  Uploading $kit_id..."
        collect_publishable_kit_files kit_files "$kit_dir"
        if [ ${#kit_files[@]} -eq 0 ]; then
            log_warn "Skipping $kit_id - no publishable files"
            continue
        fi
        gcloud storage cp -r "${kit_files[@]}" "gs://$FORM_KITS_BUCKET/$FORM_KITS_PREFIX/$kit_id/" --project "$POLYGLOT_PROJECT_NAME"
    done
    
    # Generate and upload manifest
    log_info "📝 Generating manifest..."
    
    manifest_content='{"generatedAt":"'$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")'","forms":['
    first=true
    
    for kit_dir in "$FORM_KITS_DIR"/*/; do
        [ -d "$kit_dir" ] || continue
        kit_id=$(basename "$kit_dir")

        # An _-prefixed dir is shared authoring data, not a kit (e.g.
        # form-kits/_translation/, the glossary from bd polyglot-pdf-ch7j).
        # Skip SILENTLY so it does not warn on every full deploy
        # (bd polyglot-pdf-qwex).
        case "$kit_id" in _*) continue ;; esac

        schema_file=$(kit_schema_file "$kit_dir")
        if [ ! -f "$kit_dir/$schema_file" ]; then
            continue
        fi

        # Complete-gate: a draft/unmarked kit is uploaded by neither loop, so it
        # is also absent from the manifest the voice app reads (bd b0pe).
        if ! kit_is_complete "$kit_dir"; then
            continue
        fi

        # Label precedence mirrors the store's (metadata.label -> schema title ->
        # kit_id, backend/services/form_kits.py): metadata.json's label is the
        # RENAMEABLE display name (bd 15ic) -- without this, an editor rename
        # would never reach the deployed voice-app manifest.
        label=$(grep -o '"label"[[:space:]]*:[[:space:]]*"[^"]*"' "$kit_dir/metadata.json" 2>/dev/null | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/')
        [ -z "$label" ] && label=$(grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' "$kit_dir/$schema_file" | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/' || echo "$kit_id")
        [ -z "$label" ] && label="$kit_id"
        
        # Find PDF file
        pdf_file="form.pdf"
        if [ ! -f "$kit_dir/form.pdf" ]; then
            pdf_file=$(ls "$kit_dir"/*.pdf 2>/dev/null | head -1 | xargs basename 2>/dev/null || echo "form.pdf")
        fi
        
        if [ "$first" = true ]; then
            first=false
        else
            manifest_content+=','
        fi
        
        manifest_content+='{"id":"'$kit_id'","label":"'$label'","schemaFile":"'$schema_file'","schemaPath":"/'$FORM_KITS_PREFIX'/'$kit_id'/'$schema_file'","pdfFile":"'$pdf_file'","pdfPath":"/'$FORM_KITS_PREFIX'/'$kit_id'/'$pdf_file'"}'
    done
    
    manifest_content+=']}'
    
    # Upload manifest; an invalid manifest aborts the deploy before anything
    # is uploaded (bd polyglot-pdf-4w0l).
    temp_manifest=$(mktemp)
    if ! write_validated_manifest "$manifest_content" "$temp_manifest"; then
        rm -f "$temp_manifest"
        exit 1
    fi
    gcloud storage cp "$temp_manifest" "gs://$FORM_KITS_BUCKET/$FORM_KITS_PREFIX/index.json" --project "$POLYGLOT_PROJECT_NAME"
    rm "$temp_manifest"
    
    log_success "✅ Form kits deployed successfully!"
    echo "   Bucket: gs://$FORM_KITS_BUCKET"
    echo "   Manifest: gs://$FORM_KITS_BUCKET/$FORM_KITS_PREFIX/index.json"
    echo ""
fi

# ============================================================================
# FRONTEND DEPLOYMENT
# ============================================================================
if [ "$DEPLOY_FRONTEND" = true ]; then
    log_info "═══════════════════════════════════════════════════════════"
    log_info "  DEPLOYING FRONTEND TO FIREBASE HOSTING"
    log_info "═══════════════════════════════════════════════════════════"
    echo ""
    
    cd "$FRONTEND_DIR"
    
    # Check if Firebase CLI is installed
    if ! command -v firebase &> /dev/null; then
        log_error "Firebase CLI not found. Install with: npm install -g firebase-tools"
        exit 1
    fi
    
    # Self-heal dependencies. node_modules is git-ignored, so a fresh checkout
    # (or an "npm install" accidentally run from the repo root instead of here)
    # leaves frontend/node_modules empty. The build's prebuild hook then calls
    # tsx, which is not on disk, and fails with "tsx is not recognized". We are
    # already in $FRONTEND_DIR (cd above), so this installs into the right tree
    # no matter where the deploy was launched from. Test the actual binary the
    # build needs -- catches both the empty and the partial-install cases.
    if [ ! -x node_modules/.bin/tsx ]; then
        log_info "Frontend dependencies missing -- installing..."
        if [ -f package-lock.json ]; then
            npm ci
        else
            npm install
        fi
    fi

    # Resolve the LIVE backend URL at deploy time and inject it into the build,
    # instead of trusting a committed VITE_WS_URL literal in .env.<mode> (bd
    # polyglot-pdf-emm7). The Cloud Run auto-URL hash is NOT stable -- it changed
    # (d3mhrrkwfq -> won24rgefq) on a service recreate and silently pointed the
    # deployed frontend at a 404'd backend. A shell VITE_* overrides the .env file
    # (standard Vite precedence; .env.demo documents this), so the .env literals
    # become fallbacks, not load-bearing. Reuse BACKEND_URL if the backend stage
    # set it earlier in THIS process (a bare `deploy-all.sh` / `--all` run);
    # otherwise resolve it fresh -- which is the usual path, since the demo/prod
    # wrappers run the frontend stage as a SEPARATE `deploy-all.sh --frontend`
    # invocation where nothing carries over.
    if [ -z "$BACKEND_URL" ]; then
        BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE_NAME" --platform managed --region "$REGION" --project "$POLYGLOT_PROJECT_NAME" --format 'value(status.url)' 2>/dev/null || true)
    fi
    if [ -n "$BACKEND_URL" ]; then
        # https://host -> wss://host/ws/fill (the app's WS endpoint).
        export VITE_WS_URL="${BACKEND_URL/https:/wss:}/ws/fill"
        log_info "🔌 Injecting live backend URL into build: VITE_WS_URL=$VITE_WS_URL"
    else
        log_warn "Could not resolve live backend URL; build will fall back to VITE_WS_URL in .env.<mode> (may be stale -- bd polyglot-pdf-emm7)"
    fi

    # Build frontend (channel-aware; see FRONTEND_BUILD_CMD above)
    log_info "📦 Building frontend ($FRONTEND_BUILD_CMD)..."
    $FRONTEND_BUILD_CMD
    
    # Deploy to Firebase Hosting
    log_info "🌐 Deploying to Firebase Hosting..."
    # Pinned to the APP target (bd 92qe.4): hosting is now an array of named
    # targets (app = the voice app, editor = the hosted schema editor), and a
    # bare "--only hosting" would deploy BOTH -- including whatever stale build
    # sits in schema-editor/dist. The editor ships via deploy-editor.sh only.
    firebase deploy --only hosting:app --project "$POLYGLOT_PROJECT_NAME"
    
    log_success "✅ Frontend deployed successfully!"
    echo "   URL: https://$POLYGLOT_PROJECT_NAME.web.app"
    echo ""
    
    cd "$SCRIPT_DIR"
fi

# ============================================================================
# DEPLOYMENT SUMMARY
# ============================================================================
echo ""
log_success "╔═══════════════════════════════════════════════════════════╗"
log_success "║         DEPLOYMENT COMPLETED SUCCESSFULLY                 ║"
log_success "╚═══════════════════════════════════════════════════════════╝"
echo ""

if [ "$DEPLOY_BACKEND" = true ]; then
    log_info "🔧 Backend API:"
    echo "   $BACKEND_URL"
    echo ""
fi

if [ "$DEPLOY_FRONTEND" = true ]; then
    log_info "🌐 Frontend URL:"
    echo "   https://$POLYGLOT_PROJECT_NAME.web.app"
    echo ""
fi

if [ "$DEPLOY_FORM_KITS" = true ]; then
    log_info "📦 Form Kits Bucket:"
    echo "   gs://$FORM_KITS_BUCKET/$FORM_KITS_PREFIX"
    echo ""
fi

log_info "💡 Next steps:"
echo "   1. Test the application at the frontend URL"
echo "   2. Verify API routes work through Firebase hosting"
echo "   3. Check form-kits load: /api/form-kits is AUTH-GATED (bd z2is), so a"
echo "      tokenless curl returning 401 is CORRECT. Verify the authed path"
echo "      end-to-end (first deploy exercising Authorization through the"
echo "      Hosting /api/** rewrite):"
echo "        curl -i -H \"Authorization: Bearer <Firebase idToken>\" \\"
echo "          https://<hosting-domain>/api/form-kits   # expect 200"
echo "   4. Confirm the durable confirmation sink writes: run a session, then"
echo "        backend/.venv/Scripts/python.exe scripts/read_confirmations.py \\"
echo "          <form_session_id> --firestore --summary --project $POLYGLOT_PROJECT_NAME"
echo "      (--project pins the queried project; without it your gcloud ADC's"
echo "      default project wins and a record can falsely read as absent."
echo "      The runtime SA needs roles/datastore.user for the backend's WRITES"
echo "      -- setup-gcp-project.sh; this READ runs under YOUR gcloud ADC,"
echo "      which needs its own Firestore read access. Exit 2 = could not"
echo "      query, exit 1 = queried fine but no events.)"
echo "      Quick drift check any time: curl the service /health and read the"
echo "      confirmation_sink field (ok / error / disabled)."
echo ""
