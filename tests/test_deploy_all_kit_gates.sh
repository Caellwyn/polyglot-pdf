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

# --- no-bypass: every deploy path routes form-kits through the gate (bd nr8u) ---
# deploy-demo.sh and deploy-production.sh do NOT upload form-kits themselves --
# they set env/bucket then invoke deploy-all.sh, whose kit_is_complete loop is the
# single gate. Assert neither wrapper has its OWN form-kit upload (a gcloud/gsutil
# copy targeting the form-kits bucket/dir) that would bypass the gate. This is the
# static guarantee behind D2 exit criterion 2 across all three paths; it fails if a
# future edit adds a bypassing upload to a wrapper.
# A "bypass" is ANY storage write of form-kits (cp OR rsync, gcloud OR gsutil)
# in a wrapper that is supposed to delegate. The regex covers cp and rsync so a
# future `gsutil rsync form-kits ...` can't slip past (fresh-eyes finding).
assert_no_bypass() {
    local label="$1" file="$2"
    if [ ! -f "$file" ]; then
        echo "FAIL  no-bypass: $label (missing $file)"
        FAIL=$((FAIL + 1))
        return
    fi
    if grep -Eq '(gcloud storage|gsutil)([[:space:]]+-[^[:space:]]+)*[[:space:]]+(cp|rsync).*form.?kits' "$file"; then
        echo "FAIL  no-bypass: $label has its own form-kit upload (bypasses the gate)"
        FAIL=$((FAIL + 1))
    else
        echo "PASS  no-bypass: $label routes form-kits through deploy-all.sh"
        PASS=$((PASS + 1))
    fi
}

# A "gated" deploy path is one that DOES upload form-kits itself but guards each
# upload with `kit_is_complete`. Assert the actual GUARD CALL is present (the
# `kit_is_complete <dir>` usage as a condition), not merely the function name --
# matching only the name would still PASS if the upload-loop guard were deleted
# while the definition stayed (fresh-eyes finding).
assert_gated() {
    local label="$1" file="$2"
    if [ ! -f "$file" ]; then
        echo "FAIL  gate-present: $label (missing $file)"
        FAIL=$((FAIL + 1))
        return
    fi
    # The guard is invoked as a condition: `if ! kit_is_complete "..."`.
    if grep -Eq 'if[[:space:]]+!?[[:space:]]*kit_is_complete[[:space:]]' "$file"; then
        echo "PASS  gate-present: $label guards uploads with kit_is_complete"
        PASS=$((PASS + 1))
    else
        echo "FAIL  gate-present: $label no longer guards uploads with kit_is_complete"
        FAIL=$((FAIL + 1))
    fi
}

# Wrappers that delegate to deploy-all.sh must NOT upload form-kits themselves.
assert_no_bypass "deploy-demo.sh" "$SCRIPT_DIR/../deploy-demo.sh"
assert_no_bypass "deploy-production.sh" "$SCRIPT_DIR/../deploy-production.sh"

# Paths that DO upload form-kits directly must guard every upload with the gate.
assert_gated "deploy-all.sh" "$SCRIPT_DIR/../deploy-all.sh"
assert_gated "scripts/deploy-form-kit.sh" "$SCRIPT_DIR/../scripts/deploy-form-kit.sh"

# --- collect_publishable_kit_files: underscore dirs never reach the bucket ---
#
# bd polyglot-pdf-06u5o. The upload was `cp -r "$kit_dir"/*`, and the
# `case "$kit_id" in _*)` guard above it filters only the TOP-LEVEL kit id, not
# children INSIDE a kit -- so _archive/ (superseded revisions, bd w3zw) and
# _drafts/ (up to 10 draft snapshots per kit, bd y2l0p) both rode every deploy
# into the bucket. Nothing clears either ring on the status transition.
#
# Note this pins the GENERAL underscore rule, not just _drafts: mutating the
# skip to `_drafts)` alone leaves _archive leaking and MUST redden here.

# NESTED under $TMP, and deliberately NO second trap: bash keeps ONE EXIT
# handler per shell, so `trap ... EXIT` here would have REPLACED the $TMP
# cleanup registered above and leaked that directory on every run.
KIT_ROOT="$TMP/kits"
mkdir -p "$KIT_ROOT"

mkdir -p "$KIT_ROOT/w7/_drafts/1" "$KIT_ROOT/w7/_archive/v1" "$KIT_ROOT/w7/sub"
touch "$KIT_ROOT/w7/schema.json" "$KIT_ROOT/w7/form.pdf" "$KIT_ROOT/w7/metadata.json"
touch "$KIT_ROOT/w7/_drafts/1/schema.json" "$KIT_ROOT/w7/_archive/v1/schema.json"
touch "$KIT_ROOT/w7/sub/nested.txt"

collect_publishable_kit_files _collected "$KIT_ROOT/w7"
_names=$(printf '%s
' "${_collected[@]}" | xargs -n1 basename | sort | tr '
' ' ')

assert_excluded() {
    local what=$1
    if printf '%s
' "${_collected[@]}" | grep -q "/$what\$"; then
        echo "FAIL  publishable: $what was collected for upload"
        FAIL=$((FAIL + 1))
    else
        echo "PASS  publishable: $what excluded from upload"
        PASS=$((PASS + 1))
    fi
}

assert_included() {
    local what=$1
    if printf '%s
' "${_collected[@]}" | grep -q "/$what\$"; then
        echo "PASS  publishable: $what included"
        PASS=$((PASS + 1))
    else
        echo "FAIL  publishable: $what MISSING (collected: $_names)"
        FAIL=$((FAIL + 1))
    fi
}

assert_excluded "_drafts"
assert_excluded "_archive"
# Real content must survive the filter -- an over-broad rule that uploaded
# nothing would pass the two assertions above.
assert_included "schema.json"
assert_included "form.pdf"
assert_included "metadata.json"
assert_included "sub"

# A kit with no publishable children yields an EMPTY array, not the literal
# glob string -- both callers check ${#kit_files[@]} before uploading.
mkdir -p "$KIT_ROOT/onlyunderscore/_drafts"
collect_publishable_kit_files _empty "$KIT_ROOT/onlyunderscore"
if [ "${#_empty[@]}" -eq 0 ]; then
    echo "PASS  publishable: underscore-only kit collects nothing"
    PASS=$((PASS + 1))
else
    echo "FAIL  publishable: underscore-only kit collected ${#_empty[@]} entries"
    FAIL=$((FAIL + 1))
fi

# deploy-form-kit.sh carries its OWN copy of the helper (the scripts are
# independently invocable, so it cannot source deploy-all.sh). Grepping its call
# site proves the CALL, not the FILTER, so extract and RUN that copy.
#
# THREE load-bearing details, each of which cost a green-but-broken run:
#   * unset -f -- the harness sourced deploy-all.sh above, so the same function
#     is already defined in this subshell. Without the unset, `eval` is an
#     optional OVERRIDE, not a binding: if the sed matches nothing the test
#     silently exercises deploy-all.sh's copy and passes while THIS file leaks.
#     Measured: a brace-style reformat + a narrowed filter shipped an _archive
#     leak at 26/26 green.
#   * the empty-source check -- fail loudly when the function moves or is
#     reformatted, rather than skipping in silence.
#   * `|| exit 1` on the eval -- a syntax error inside the extracted body wrote
#     to stderr and still went green.
_dfk_src=$(sed -n '/^collect_publishable_kit_files()[[:space:]]*{\?$/,/^}/p'     "$SCRIPT_DIR/../scripts/deploy-form-kit.sh")
if [ -z "$_dfk_src" ]; then
    echo "FAIL  publishable: could not extract deploy-form-kit.sh's helper (moved or reformatted?)"
    FAIL=$((FAIL + 1))
fi
if (
    unset -f collect_publishable_kit_files
    eval "$_dfk_src" || exit 1
    collect_publishable_kit_files _dfk "$KIT_ROOT/w7"
    printf '%s
' "${_dfk[@]}" > "$KIT_ROOT/dfk_out.txt"
); then
    if [ ! -s "$KIT_ROOT/dfk_out.txt" ]; then
        echo "FAIL  publishable: deploy-form-kit.sh's own helper collected nothing"
        FAIL=$((FAIL + 1))
    elif grep -qE '/_(drafts|archive)$' "$KIT_ROOT/dfk_out.txt"; then
        echo "FAIL  publishable: deploy-form-kit.sh's own helper collected an _ dir"
        FAIL=$((FAIL + 1))
    else
        echo "PASS  publishable: deploy-form-kit.sh's own helper excludes _ dirs"
        PASS=$((PASS + 1))
    fi
    if grep -qE '/schema\.json$' "$KIT_ROOT/dfk_out.txt"; then
        echo "PASS  publishable: deploy-form-kit.sh's own helper keeps real files"
        PASS=$((PASS + 1))
    else
        echo "FAIL  publishable: deploy-form-kit.sh's own helper dropped real files"
        FAIL=$((FAIL + 1))
    fi
else
    echo "FAIL  publishable: deploy-form-kit.sh's helper failed to load"
    FAIL=$((FAIL + 1))
fi

# Both upload sites must go through the helper rather than a raw glob.
for _f in "$SCRIPT_DIR/../deploy-all.sh" "$SCRIPT_DIR/../scripts/deploy-form-kit.sh"; do
    _label=$(basename "$_f")
    # Match any raw-glob upload of the kit dir, not two incidental spellings:
    # ${kit_dir} (brace form) and --recursive (long flag) both reintroduce the
    # leak, and a regex pinned to one shape would stay green (bd
    # polyglot-pdf-j8fe5). Keyed on "cp <flag> <kit_dir-in-any-form>/*".
    if grep -Eq 'gcloud storage cp (-r|--recursive) "?\$\{?kit_dir\}?/?"?/?\*' "$_f"; then
        echo "FAIL  publishable: $_label still uploads a raw \$kit_dir glob"
        FAIL=$((FAIL + 1))
    else
        echo "PASS  publishable: $_label uploads an enumerated file list"
        PASS=$((PASS + 1))
    fi
done

# The harness must register exactly ONE EXIT trap. bash keeps one handler per
# shell, so a second `trap ... EXIT` silently REPLACES the first and orphans
# whatever the first was cleaning -- which is exactly what a second trap added
# here did, leaking $TMP on every run until it was caught in review.
_traps=$(grep -cE '^[[:space:]]*trap( --)? .* (EXIT|0)[[:space:]]*$' "$0")
if [ "$_traps" -eq 1 ]; then
    echo "PASS  cleanup: exactly one EXIT trap registered"
    PASS=$((PASS + 1))
else
    echo "FAIL  cleanup: $_traps EXIT traps -- a later one silently replaces the first"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "----------------------------------------"
echo "kit-gate tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
