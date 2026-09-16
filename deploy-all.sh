#!/bin/bash
# deploy-all.sh - the shared deploy helpers, plus a channel-agnostic Cloud
# Build wrapper.
#
# TWO HALVES, split by the sourcing guard further down.
#
#   SOURCED -- the helper library. cloudbuild.yaml's backend and admin-service
#   targets source this file for read_channel_section / read_channel_value
#   rather than reimplementing deploy/channels/*.env's format in yaml, and the
#   kit-gate harness sources it for kit_is_complete / kit_schema_file /
#   collect_publishable_kit_files (whose twins in scripts/deploy-form-kit.sh
#   are pinned byte-identical by tests/test_deploy_manifest_validation.py).
#
#   EXECUTED -- a thin wrapper over Cloud Build, like every other deploy-*.sh
#   (bd polyglot-pdf-oqtm7, Epic 4 bead 4.6). It runs no docker build, no
#   gcloud run deploy and no firebase deploy: those stages all live in
#   cloudbuild.yaml now, one target apiece, and this script starts the
#   matching triggers at the current commit.
#
# Usage (executed):
#   DEPLOY_CHANNEL=staging ./deploy-all.sh              # backend + frontend + kits
#   DEPLOY_CHANNEL=demo    ./deploy-all.sh --backend    # one target
#
# Prefer deploy-staging.sh / deploy-demo.sh: they name the channel, carry the
# per-channel safety notes, and are what the doctrine refers to.
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

# ---------------------------------------------------------------------------
# CHANNEL FILE PARSER (bd polyglot-pdf-1s3ko)
#
# Per-channel Cloud Run configuration lives in deploy/channels/<channel>.env as
# plain KEY=value data under three section headers, so BOTH this script and
# cloudbuild.yaml read ONE source. Before this existed the env lived only as an
# inline BACKEND_EXTRA_ENV string inside deploy-staging.sh / deploy-demo.sh,
# which a Cloud Build step cannot read without restating it -- and a restated
# config is the drift tests/test_deploy_channel_parity.py exists to catch.
#
# read_channel_section <file> <SECTION>
#   Prints the KEY=value lines of one section, comma-joined for gcloud's
#   --set-env-vars / --set-secrets. Prints nothing for an absent or empty
#   section (admin.env's [SET_SECRETS] is deliberately empty), so the caller's
#   `[ -n "$x" ] &&` guards keep producing a flagless invocation.
#
# A missing FILE is fatal: silently deploying with an empty env block would
# strip every setting off the service, since --set-env-vars REPLACES rather
# than merges.
read_channel_section() {
    local file="$1" want="$2" section="" line key out=""
    if [ ! -f "$file" ]; then
        echo "[ERROR] channel file not found: $file" >&2
        exit 1
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        # Strip a trailing CR so a CRLF-checked-out file still parses (the
        # repo is edited on Windows).
        line="${line%$'\r'}"
        case "$line" in
            \#*|"") continue ;;
            \[*\]) section="${line#[}"; section="${section%]}"; continue ;;
        esac
        [ "$section" = "$want" ] || continue
        key="${line%%=*}"
        # A line inside a section that is not KEY=value is a typo, not data.
        case "$line" in
            *=*) ;;
            *) echo "[ERROR] $file [$want]: not KEY=value: $line" >&2; exit 1 ;;
        esac
        [ -n "$key" ] || { echo "[ERROR] $file [$want]: empty key" >&2; exit 1; }
        if [ -z "$out" ]; then out="$line"; else out="$out,$line"; fi
    done < "$file"
    printf '%s' "$out"
}

# read_channel_value <file> <SECTION> <KEY> -- one value, unwrapped.
read_channel_value() {
    local pairs p
    pairs=$(read_channel_section "$1" "$2")
    # NO pipeline here: a `while read` on the right of a pipe runs in a
    # SUBSHELL, so its printf would be discarded and every caller would see an
    # empty value. Split on commas with IFS in this shell instead.
    local IFS=,
    for p in $pairs; do
        if [ "${p%%=*}" = "$3" ]; then printf '%s' "${p#*=}"; return 0; fi
    done
    return 0
}

# When this file is SOURCED (not executed directly), stop here -- expose only
# the helper functions above and run none of the wrapper flow below.
# cloudbuild.yaml's backend and admin-service targets source this file for
# read_channel_section / read_channel_value rather than reimplementing the
# channel-file format in yaml, and the kit-gate test harness sources it for
# kit_is_complete / collect_publishable_kit_files (bd polyglot-pdf-45x5).
# Direct execution (`./deploy-all.sh ...`) has BASH_SOURCE[0] == $0 and falls
# through.
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    return 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# DEPLOY PREFLIGHT (bd polyglot-pdf-1s3ko): a build runs from a COMMIT and
# build_checks/{sha} vouches for that commit's test run, so a dirty or
# unpushed tree makes both claims false.
source "$SCRIPT_DIR/scripts/deploy_preflight.sh"
deploy_preflight "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/deploy_build_targets.sh"

# Print header
echo ""
log_info "Polyglot PDF Form Filler - Cloud Build deploy"
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

# DEPLOY_CHANNEL selects WHICH channel's targets run. It has no default on
# purpose: the backend and frontend targets are named per channel
# (backend-staging vs backend-demo), so guessing one here would be guessing
# which channel to deploy -- and guessing "demo" would point a bare run at the
# protected target. Use deploy-staging.sh or deploy-demo.sh, which name it.
DEPLOY_CHANNEL="${DEPLOY_CHANNEL:-}"
case "$DEPLOY_CHANNEL" in
    staging|demo) ;;
    *)
        log_error "DEPLOY_CHANNEL must be 'staging' or 'demo' (got '${DEPLOY_CHANNEL}')."
        echo "Deploy a channel through its own wrapper:"
        echo "  ./deploy-staging.sh   (the test deploy)"
        echo "  ./deploy-demo.sh      (the protected demo)"
        exit 1
        ;;
esac

SHA=$(deploy_build_sha "$SCRIPT_DIR")

# form-kits and firestore-rules have NO per-channel split: the kits bucket and
# the Firestore rules are project-wide, so publishing either from the staging
# channel changes what the DEMO serves. deploy-staging.sh is what refuses to
# do so by default; this script honours the flags it is given.
TARGETS=()
[ "$DEPLOY_BACKEND" = true ] && TARGETS+=("backend-$DEPLOY_CHANNEL")
[ "$DEPLOY_FORM_KITS" = true ] && TARGETS+=("form-kits")
[ "$DEPLOY_FRONTEND" = true ] && TARGETS+=("frontend-$DEPLOY_CHANNEL")

log_info "Deploying channel $DEPLOY_CHANNEL at $SHA: ${TARGETS[*]}"

run_build_targets "$SHA" "${TARGETS[@]}"

log_success "Cloud Build deploy complete for channel $DEPLOY_CHANNEL."
