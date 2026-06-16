#!/usr/bin/env bash
# Functional tests for the kit-gate helpers in deploy-all.sh (bd polyglot-pdf-45x5
# for kit_is_complete; bd polyglot-pdf-snpi for kit_schema_file).
#
# kit_is_complete is the safety-critical gate that keeps DRAFT form-kits out of
# production GCS -- before this, only `bash -n` (a syntax check) guarded it, so a
# regressed grep could silently leak a draft. kit_schema_file resolves a kit's
# (possibly custom) schema filename from metadata.json.
#
# Plain bash + a tiny assert harness rather than bats: bats is not installed in
# this repo/CI and the bead allows "bats or equivalent". Run it directly:
#   bash tests/test_deploy_all_kit_gates.sh
# Exits 0 with all cases listed PASS, non-zero (and prints FAIL) otherwise.

# Source deploy-all.sh for its functions only. The script's sourcing guard returns
# before any deploy flow runs, but its top-level `set -e` DOES leak errexit into
# this harness, which would abort on the first non-zero `kit_is_complete` (the
# EXPECTED "skip" result). The `set +e` below MUST be the very next statement after
# the source -- it is a load-bearing ordering constraint, NOT cosmetic: any
# statement inserted between the source and `set +e` runs under the leaked errexit
# and would abort the harness on its first non-zero return. Keep them adjacent.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/../deploy-all.sh"
set +e  # <-- load-bearing: see the comment above; do not move or precede with code

PASS=0
FAIL=0

# assert_complete <label> <kit_dir> <expect: yes|no>
assert_complete() {
    local label="$1" kit_dir="$2" expect="$3" got
    if kit_is_complete "$kit_dir"; then got="yes"; else got="no"; fi
    if [ "$got" = "$expect" ]; then
        echo "PASS  kit_is_complete: $label (=> $got)"
        PASS=$((PASS + 1))
    else
        echo "FAIL  kit_is_complete: $label (expected $expect, got $got)"
        FAIL=$((FAIL + 1))
    fi
}

# assert_schema <label> <kit_dir> <expected-filename>
assert_schema() {
    local label="$1" kit_dir="$2" expect="$3" got
    got="$(kit_schema_file "$kit_dir")"
    if [ "$got" = "$expect" ]; then
        echo "PASS  kit_schema_file: $label (=> $got)"
        PASS=$((PASS + 1))
    else
        echo "FAIL  kit_schema_file: $label (expected '$expect', got '$got')"
        FAIL=$((FAIL + 1))
    fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- kit_is_complete (bd 45x5): the four required cases ----------------------
mkdir -p "$TMP/complete"
printf '{"status":"complete"}' > "$TMP/complete/metadata.json"
assert_complete "status:complete -> pass" "$TMP/complete" "yes"

mkdir -p "$TMP/draft"
printf '{"status":"draft"}' > "$TMP/draft/metadata.json"
assert_complete "status:draft -> skip" "$TMP/draft" "no"

mkdir -p "$TMP/nostatus"
printf '{"label":"X"}' > "$TMP/nostatus/metadata.json"
assert_complete "missing status field -> skip" "$TMP/nostatus" "no"

mkdir -p "$TMP/nometa"
assert_complete "no metadata.json -> skip" "$TMP/nometa" "no"

# A whitespace-padded status still reads as complete (tolerant grep).
mkdir -p "$TMP/padded"
printf '{ "status" :  "complete" }' > "$TMP/padded/metadata.json"
assert_complete "whitespace-padded status:complete -> pass" "$TMP/padded" "yes"

# --- kit_schema_file (bd snpi): custom / default / multiline / padded --------
mkdir -p "$TMP/custom"
printf '{"schema":"custom.json","status":"complete"}' > "$TMP/custom/metadata.json"
assert_schema "custom filename" "$TMP/custom" "custom.json"

mkdir -p "$TMP/defaultfield"
printf '{"status":"complete"}' > "$TMP/defaultfield/metadata.json"
assert_schema "no schema field -> default" "$TMP/defaultfield" "schema.json"

mkdir -p "$TMP/nometa2"
assert_schema "no metadata.json -> default" "$TMP/nometa2" "schema.json"

mkdir -p "$TMP/multiline"
printf '{\n  "status": "complete",\n  "schema":\n    "multiline.json"\n}' > "$TMP/multiline/metadata.json"
assert_schema "multiline key/value" "$TMP/multiline" "multiline.json"

mkdir -p "$TMP/paddedschema"
printf '{ "schema" : " padded.json " }' > "$TMP/paddedschema/metadata.json"
assert_schema "whitespace-padded value trimmed" "$TMP/paddedschema" "padded.json"

echo ""
echo "----------------------------------------"
echo "kit-gate tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
