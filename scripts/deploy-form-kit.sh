#!/bin/bash
# deploy-form-kit.sh - Upload form kit(s) to GCS and regenerate manifest
#
# Usage:
#   ./scripts/deploy-form-kit.sh <kit-id>       # Deploy single kit
#   ./scripts/deploy-form-kit.sh --all          # Deploy all kits
#   ./scripts/deploy-form-kit.sh --manifest     # Regenerate manifest only
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - GCP project set (gcloud config set project <project-id>)
#
# Environment variables (optional):
#   FORM_KITS_BUCKET - GCS bucket name (default: polyglot-demo-aa709-form-kits)
#   FORM_KITS_PREFIX - Path prefix in bucket (default: form-kits)

set -e

# Configuration
# Demo bucket by default (bd polyglot-pdf-d7hy), matching every other bucket-
# default in this repo (schema-editor/vite-plugins/deployKitEndpoint.ts's
# DEFAULT_BUCKET, scripts/pull-form-kits.sh's BUCKET, deploy-all.sh's own
# FORM_KITS_BUCKET default) -- "unset" means demo everywhere, never a silent
# prod upload. The editor's deploy endpoint always passes FORM_KITS_BUCKET
# explicitly (it never relies on this default), so this only matters for a bare
# CLI invocation with no env var; explicitly set FORM_KITS_BUCKET for a real prod
# deploy.
BUCKET_NAME="${FORM_KITS_BUCKET:-polyglot-demo-aa709-form-kits}"
PREFIX="${FORM_KITS_PREFIX:-form-kits}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# Honor FORM_KITS_ROOT (bd polyglot-pdf-ipzh). The editor's deploy button
# validates the kit -- including the status:complete check -- against the root
# the EDITOR is using, and EDITOR_GUIDE.md tells people to point that elsewhere
# with FORM_KITS_ROOT. If this script kept hardcoding the repo tree, that gate
# would check one copy while the upload shipped a different one (or skipped a
# missing kit, still republished the manifest, and reported success for an
# upload that shipped nothing) -- the cross-root trap of bd ball / bd s2bf.
# Unset, the repo tree stays the default, so a plain CLI run is unchanged.
FORM_KITS_DIR="${FORM_KITS_ROOT:-$REPO_ROOT/form-kits}"
MANIFEST_FILE="index.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Resolve a python interpreter for manifest validation. python3 is not
# guaranteed on Windows Git Bash, so fall back to python, then the py
# launcher. Each candidate must actually RUN (-c pass), not merely exist:
# Windows ships a python3 App-Execution-Alias stub that command -v finds but
# that cannot execute, which would misreport every manifest as invalid.
# Candidates are env-overridable for tests. MUST match deploy-all.sh's copy
# exactly.
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
# deploy-all.sh's copy exactly.
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

# Draft-leak gate: only a kit whose metadata.json is status:complete may reach
# GCS / the voice-app manifest (bd b0pe / nr8u). MUST match deploy-all.sh's
# kit_is_complete exactly (same tolerant grep, no jq) -- this script is the
# fourth deploy path and was previously ungated, so a --all run could leak every
# draft (Codex/fresh-eyes finding, bd nr8u). Returns 0 (complete) / non-0 (skip).
kit_is_complete() {
    local meta="$1/metadata.json"
    [ -f "$meta" ] || return 1
    grep -Eq '"status"[[:space:]]*:[[:space:]]*"complete"' "$meta"
}

# Check prerequisites
check_prereqs() {
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI not found. Install from: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi

    # Check if authenticated
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1 | grep -q "@"; then
        log_error "Not authenticated with gcloud. Run: gcloud auth login"
        exit 1
    fi

    # Check project is set
    PROJECT=$(gcloud config get-value project 2>/dev/null)
    if [ -z "$PROJECT" ] || [ "$PROJECT" == "(unset)" ]; then
        log_error "No GCP project set. Run: gcloud config set project <project-id>"
        exit 1
    fi

    log_info "Using GCP project: $PROJECT"
    log_info "Using GCS bucket: gs://$BUCKET_NAME"
}

# Create bucket if it doesn't exist
ensure_bucket() {
    if ! gcloud storage buckets describe "gs://$BUCKET_NAME" &>/dev/null; then
        log_info "Creating bucket gs://$BUCKET_NAME..."
        gcloud storage buckets create "gs://$BUCKET_NAME" \
            --location=us-central1 \
            --uniform-bucket-level-access
        log_info "Bucket created successfully"
    else
        log_info "Bucket gs://$BUCKET_NAME already exists"
    fi
}

# Upload a single form kit
upload_kit() {
    local kit_id="$1"
    local kit_dir="$FORM_KITS_DIR/$kit_id"

    if [ ! -d "$kit_dir" ]; then
        log_error "Form kit directory not found: $kit_dir"
        return 1
    fi

    if [ ! -f "$kit_dir/schema.json" ]; then
        log_error "schema.json not found in $kit_dir"
        return 1
    fi

    # Draft-leak gate: never upload a kit that isn't status:complete.
    if ! kit_is_complete "$kit_dir"; then
        log_warn "Skipping $kit_id - not status:complete (draft kept local; bd b0pe/nr8u gate)"
        return 0
    fi

    log_info "Uploading form kit: $kit_id"

    # Upload all files in the kit directory
    gcloud storage cp -r "$kit_dir/*" "gs://$BUCKET_NAME/$PREFIX/$kit_id/"

    log_info "Uploaded $kit_id successfully"
}

# Generate and upload manifest
generate_manifest() {
    log_info "Generating manifest..."

    local manifest_content='{"generatedAt":"'$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")'","forms":['
    local first=true

    for kit_dir in "$FORM_KITS_DIR"/*/; do
        [ -d "$kit_dir" ] || continue

        local kit_id=$(basename "$kit_dir")

        # An _-prefixed dir is shared authoring data, not a kit (e.g.
        # form-kits/_translation/, the glossary from bd polyglot-pdf-ch7j).
        # Skip SILENTLY -- warning about it on every deploy erodes trust in
        # the deploy log's real warnings (bd polyglot-pdf-qwex).
        case "$kit_id" in _*) continue ;; esac

        # Skip if no schema.json
        if [ ! -f "$kit_dir/schema.json" ]; then
            log_warn "Skipping $kit_id - no schema.json found"
            continue
        fi

        # Draft-leak gate: a draft kit must not appear in the deployed manifest
        # either (the upload is gated above; keep the manifest consistent).
        if ! kit_is_complete "$kit_dir"; then
            log_warn "Skipping $kit_id from manifest - not status:complete"
            continue
        fi

        # Label precedence mirrors the store's (metadata.label -> schema title ->
        # kit_id, backend/services/form_kits.py): metadata.json's label is the
        # RENAMEABLE display name (bd 15ic).
        local label=$(grep -o '"label"[[:space:]]*:[[:space:]]*"[^"]*"' "$kit_dir/metadata.json" 2>/dev/null | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/')
        if [ -z "$label" ]; then
            label=$(grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' "$kit_dir/schema.json" | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/' || echo "$kit_id")
        fi
        if [ -z "$label" ]; then
            label="$kit_id"
        fi

        # Find PDF file (prefer form.pdf, then any .pdf)
        local pdf_file="form.pdf"
        if [ ! -f "$kit_dir/form.pdf" ]; then
            pdf_file=$(ls "$kit_dir"/*.pdf 2>/dev/null | head -1 | xargs basename 2>/dev/null || echo "")
        fi

        if [ -z "$pdf_file" ]; then
            log_warn "No PDF found for $kit_id"
            pdf_file="form.pdf"
        fi

        if [ "$first" = true ]; then
            first=false
        else
            manifest_content+=','
        fi

        manifest_content+='{"id":"'$kit_id'",'
        manifest_content+='"label":"'$label'",'
        manifest_content+='"schemaFile":"schema.json",'
        manifest_content+='"schemaPath":"/'$PREFIX'/'$kit_id'/schema.json",'
        manifest_content+='"pdfFile":"'$pdf_file'",'
        manifest_content+='"pdfPath":"/'$PREFIX'/'$kit_id'/'$pdf_file'"}'
    done

    manifest_content+=']}'

    # Write manifest locally first; an invalid manifest aborts the deploy
    # before anything is uploaded (bd polyglot-pdf-4w0l).
    local temp_manifest=$(mktemp)
    if ! write_validated_manifest "$manifest_content" "$temp_manifest"; then
        rm -f "$temp_manifest"
        exit 1
    fi

    # Upload manifest
    gcloud storage cp "$temp_manifest" "gs://$BUCKET_NAME/$PREFIX/$MANIFEST_FILE"
    rm "$temp_manifest"

    log_info "Manifest uploaded to gs://$BUCKET_NAME/$PREFIX/$MANIFEST_FILE"
}

# Print usage
usage() {
    echo "Usage: $0 <kit-id> | --all | --manifest"
    echo ""
    echo "Commands:"
    echo "  <kit-id>    Deploy a specific form kit (e.g., i-90)"
    echo "  --all       Deploy all form kits in form-kits/"
    echo "  --manifest  Regenerate and upload manifest only"
    echo ""
    echo "Environment variables:"
    echo "  FORM_KITS_BUCKET  GCS bucket name (default: polyglot-demo-aa709-form-kits)"
    echo "  FORM_KITS_PREFIX  Path prefix in bucket (default: form-kits)"
    exit 1
}

# Main
main() {
    if [ $# -eq 0 ]; then
        usage
    fi

    check_prereqs
    ensure_bucket

    case "$1" in
        --all)
            log_info "Deploying all form kits..."
            for kit_dir in "$FORM_KITS_DIR"/*/; do
                [ -d "$kit_dir" ] || continue
                kit_id=$(basename "$kit_dir")
                # Shared authoring data, not a kit -- skip silently (see the
                # matching guard in generate_manifest; bd polyglot-pdf-qwex).
                case "$kit_id" in _*) continue ;; esac
                upload_kit "$kit_id" || log_warn "Failed to upload $kit_id, continuing..."
            done
            generate_manifest
            ;;
        --manifest)
            generate_manifest
            ;;
        --help|-h)
            usage
            ;;
        *)
            upload_kit "$1"
            generate_manifest
            ;;
    esac

    log_info "Done!"
    echo ""
    echo "Next steps:"
    echo "1. Update Cloud Run env vars:"
    echo "   gcloud run services update polyglot-backend \\"
    echo "     --set-env-vars FORM_KITS_MODE=gcs,FORM_KITS_GCS_BUCKET=$BUCKET_NAME,FORM_KITS_REMOTE_PREFIX=$PREFIX"
    echo ""
    echo "2. Test the manifest endpoint:"
    echo "   curl https://your-backend-url/api/form-kits"
}

main "$@"
