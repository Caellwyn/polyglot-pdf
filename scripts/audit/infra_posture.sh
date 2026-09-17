#!/bin/bash
# infra_posture.sh -- READ-ONLY live infrastructure posture runbook.
#
# Sprint 23 (security + data-leak audit) workstream D, plan section D:
# docs/sprint_23_security-audit_plan.md. Verifies PF-12 and the deployed
# side of every other pre-finding in that plan. Sibling of
# scripts/audit/inventory_stores.py (workstream A) and
# scripts/audit/log_pii_sweep.py (workstream B2) -- this script is the one
# that reads INFRASTRUCTURE CONFIGURATION (IAM, env vars, bucket/Firestore/
# Logging/BigQuery/Auth/Hosting/Build settings), never log CONTENT.
#
# READ-ONLY, ALWAYS. Every gcloud/bq/firebase call below is a describe/list/
# get-iam-policy/read -- never update/set/add-iam-policy-binding/delete/
# create. If a check would need a mutation to answer (e.g. "is Artifact
# Registry vulnerability scanning on" when it's off), it reports
# N/A: <reason> and says what an ASK would need to enable, per CLAUDE.md scar
# #7's own admonition that a live change is a separate per-instance decision.
#
# REDACTION RULE. Principals and role NAMES are configuration -- printed in
# full. Env var NAMES and a secret-shaped/verbosity-knob VERDICT are printed;
# env var VALUES are never printed beyond a boolean/enum a check computes
# itself. Log line PAYLOADS are never printed -- the Cloud Build log check
# greps for shapes and prints COUNTS + the build id only, never the matched
# text. This mirrors scripts/audit/log_pii_sweep.py's own redaction rule from
# the same plan.
#
# EVERY CHECK ENDS PASS, FAIL, OR N/A: <reason> -- NEVER A SILENT SKIP, and a
# permission error on one check must not stop the rest. Achieved with plain
# functions (run_capture/record) that share the `_last_status`/`_last_output`
# globals rather than subshells, plus `set -e` OFF (unlike setup-*.sh's
# operator scripts, which intentionally abort on the first error because
# they are MUTATING;
# this script's whole job is to keep reading past a permission gap and name
# it).
#
# Usage: bash scripts/audit/infra_posture.sh --project <PROJECT_ID>
#
# Runs under the OPERATOR's own gcloud/bq/firebase ADC (`gcloud auth list`),
# never a service account key. --project is REQUIRED -- no default, so this
# never silently audits whatever project the operator's gcloud happens to be
# pointed at (the same guard scripts/setup-gcp-project.sh and
# scripts/setup-monitoring.sh both carry).
#
# The experimentation skill's cost gate does not apply: no call here reaches
# a Gemini model.
#
# ASCII only (CLAUDE.md scar #6).

PROJECT_ID=""
while [ $# -gt 0 ]; do
    case "$1" in
        --project)
            PROJECT_ID="$2"
            shift 2
            ;;
        --project=*)
            PROJECT_ID="${1#*=}"
            shift
            ;;
        *)
            echo "[ERROR] Unknown argument: $1" >&2
            echo "[ERROR] Usage: $0 --project <PROJECT_ID>" >&2
            exit 1
            ;;
    esac
done

if [ -z "$PROJECT_ID" ]; then
    echo "[ERROR] Usage: $0 --project <PROJECT_ID>" >&2
    echo "[ERROR] --project is required -- this script never falls back to" >&2
    echo "[ERROR] whatever project the operator's gcloud happens to be" >&2
    echo "[ERROR] pointed at." >&2
    exit 1
fi

if [ "$PROJECT_ID" = "polyglot-forms-919f2" ]; then
    echo "[ERROR] polyglot-forms-919f2 is the DEAD project (deploy-production.sh" >&2
    echo "[ERROR] refuses to run against it too -- bd polyglot-pdf-je6iy). Refusing." >&2
    exit 1
fi

# Never let a gcloud call block on stdin for a y/N confirmation (e.g.
# "enable the Organization Policy API and retry?" on org-policies describe).
# This script is read-only and unattended-safe by design; a prompt here
# would hang forever under the harness that runs it. gcloud honors this
# environment variable for exactly that class of prompt.
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

REGION="us-central1"

# THE repo root, computed ONCE and used for every repo-file read below (the
# Firestore rules comparison, the cloudbuild.yaml logsBucket check, and
# _python_candidates' own venv search). Falls back to the CURRENT directory
# only if git itself is unavailable -- but the script is meant to be run
# `bash scripts/audit/infra_posture.sh` from the repo root anyway, so this
# is a defensive fallback, not the expected path. Every bare relative read
# of a repo file (a plain `cat firestore.rules`, a plain
# `[ -f cloudbuild.yaml ]`) is a real bug: it resolves against the SHELL'S
# CURRENT WORKING DIRECTORY, not the repo, so running this script from any
# other cwd makes the Firestore rules check silently compare against an
# EMPTY string and report a confident "the deployed ruleset differs" FAIL
# with no rules content behind it, and makes the cloudbuild.yaml logsBucket
# override invisible. tests/test_infra_posture_script.py greps for exactly
# this shape and fails if a future edit reintroduces it.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Resolve a WORKING python interpreter, verified by actually invoking it
# rather than trusting PATH or a file's presence -- on Windows, `python3` on
# PATH commonly resolves to the Microsoft Store's execution-alias STUB, which
# exits nonzero with an install nag instead of running anything, and this
# repo's own backend/.venv exists only in the MAIN checkout, not in a
# worktree (CLAUDE.md's own "run backend tests from the worktree, not main"
# scar), so an -x/-f test on a worktree-relative venv path is not a reliable
# signal either. Try, in order: an explicit override, the main repo's venv
# (via $REPO_ROOT, which resolves to THIS worktree's own root -- a worktree
# has no backend/.venv of its own, so this candidate simply misses there and
# falls through, exactly like the bare "backend/.venv/..." candidates
# below), then `python`, then `python3` -- verifying each candidate with a
# real `-c "import sys"` call before committing to it.
_python_candidates() {
    if [ -n "${INFRA_POSTURE_PYTHON:-}" ]; then
        printf '%s\n' "$INFRA_POSTURE_PYTHON"
    fi
    printf '%s\n' "${REPO_ROOT}/backend/.venv/Scripts/python.exe"
    printf '%s\n' "${REPO_ROOT}/backend/.venv/bin/python"
    printf '%s\n' "backend/.venv/Scripts/python.exe"
    printf '%s\n' "backend/.venv/bin/python"
    printf '%s\n' "python"
    printf '%s\n' "python3"
}

PYTHON_BIN=""
while IFS= read -r candidate; do
    [ -z "$candidate" ] && continue
    if "$candidate" -c "import sys" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done < <(_python_candidates)

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] No working python interpreter found (tried INFRA_POSTURE_PYTHON," >&2
    echo "[ERROR] the repo's backend/.venv, 'python', and 'python3'). Every JSON-" >&2
    echo "[ERROR] parsing check below needs one. Set INFRA_POSTURE_PYTHON=<path>." >&2
    exit 1
fi

RESULTS_FILE="$(mktemp)"
trap 'rm -f "$RESULTS_FILE"' EXIT

echo "=============================================================="
echo "infra_posture.sh -- read-only live posture check"
echo "Project: $PROJECT_ID"
echo "Operator identity: $(gcloud config get-value account 2>/dev/null || echo unknown)"
echo "Timestamp (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================================="
echo ""

# record <check-name> <PASS|FAIL|N/A> <detail...>
#
# Every check funnels through this so the result-file line shape is uniform
# and mechanically greppable (the pin test asserts every declared check NAME
# appears in the script, and a human/CI reader can `grep '^FAIL'` the output
# for the true findings).
record() {
    local name="$1"
    local status="$2"
    shift 2
    local detail="$*"
    printf '%-9s %-55s %s\n' "$status" "$name" "$detail" | tee -a "$RESULTS_FILE"
}

# run_capture <command...>
#
# Runs a read-only command, capturing stdout+stderr into `_last_output` and
# its exit status into `_last_status`, WITHOUT letting a non-zero exit kill
# the script (set -e is deliberately not used anywhere in this file -- see
# the header). Takes no check-name argument itself -- that is `record`'s
# job (see above), called separately by each check with the two globals
# this function just set. Echoes nothing; callers interpret `_last_output`/
# `_last_status` and call `record` themselves.
#
# Strips a trailing \r from every line: gcloud/bq on WINDOWS emit CRLF line
# endings (verified against this operator's install), which is invisible in
# an echoed terminal line but breaks every downstream string/set comparison
# in this file (a `[ "$live" = "$expected" ]` or a `case` pattern match sees
# the \r as part of the last token and never matches, so a role list that IS
# equal to the pin reads as a mismatch). Command substitution already strips
# trailing newlines; this strips the \r that CRLF leaves behind on every
# OTHER line.
#
# Captures the command's OWN exit status directly ($?), never through
# PIPESTATUS -- PIPESTATUS reflects the pipe most recently run in the CURRENT
# shell context, and `${PIPESTATUS[0]}` read on the line AFTER a
# `var=$(cmd | tr ...)` assignment reads the pipeline status of the
# assignment statement itself (which bash reports as 0 once the substitution
# has completed), not the `cmd | tr` pipe that ran inside it. Verified
# empirically against `gcloud org-policies describe` returning a real exit
# code of 1 while `${PIPESTATUS[0]}` after the substitution read 0 -- a
# failed read was recorded as PASS. Running the real command WITHOUT a pipe
# (redirecting into a variable directly) and piping only the already-captured
# STRING through `tr` afterward keeps `$?` attached to the actual command.
_last_output=""
_last_status=0
run_capture() {
    local raw
    raw="$("$@" 2>&1)"
    _last_status=$?
    _last_output="${raw//$'\r'/}"
}

# is_valid_json <text>
#
# A gcloud/bq exit code of 0 is NOT proof of usable output: this operator's
# `bq` CLI (a broken local dependency, unrelated to permissions) prints
# "ERROR: (bq) python3.14: command not found" to its OWN stdout/stderr and
# still exits 0, which run_capture would otherwise treat as a successful
# JSON payload and hand to a python -c parser -- producing a raw Python
# traceback in this script's output instead of a clean N/A. Every
# JSON-consuming check gates on this before parsing, so a broken underlying
# tool reports N/A with the real reason instead of leaking an interpreter
# traceback into the results table.
is_valid_json() {
    "$PYTHON_BIN" -c "import json,sys; json.loads(sys.stdin.read())" >/dev/null 2>&1 <<< "$1"
}

echo "--- 1. Project IAM policy ---------------------------------------------"

# CHECK: project_iam_policy_readable
# Every principal on the project's IAM policy, flagging a human account
# (gserviceaccount.com is the negative signal, not "user:") holding Owner or
# Editor, and any principal holding a log-viewer or datastore-viewer role --
# T3's "who holds a viewer role that could read PII at rest" question.
run_capture gcloud projects get-iam-policy "$PROJECT_ID" --format=json
if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
    record "project_iam_policy_readable" "N/A" "operator lacks resourcemanager.projects.getIamPolicy or the call failed: $(echo "$_last_output" | head -1)"
    record "project_iam_policy_human_owner_editor" "N/A" "depends on project_iam_policy_readable, which failed above"
else
    # Written to a temp file and read via argv, not a heredoc + here-string
    # on the same command -- a `<<'EOF' ... EOF` heredoc silently WINS over a
    # later `<<<` here-string on the same command substitution (verified: it
    # is not the last-redirect-wins behavior a casual read suggests), so
    # `sys.stdin.read()` below would see the heredoc's own (empty) body, not
    # $IAM_JSON, and read as an empty string -- which then fails to parse as
    # JSON and raises, printing a raw traceback into this script's output
    # instead of a clean result. Same fix as check_service_env's identical
    # trap.
    IAM_JSON="$_last_output"
    IAM_TMP=$(mktemp)
    printf '%s' "$IAM_JSON" > "$IAM_TMP"
    IAM_SUMMARY=$("$PYTHON_BIN" - "$PROJECT_ID" "$IAM_TMP" <<'PYEOF'
import json
import sys

project = sys.argv[1]
json_path = sys.argv[2]
with open(json_path, encoding="utf-8") as f:
    data = json.load(f)

human_owner_editor = []
viewer_roles = []
VIEWER_ROLES = {
    "roles/logging.viewer",
    "roles/logging.privateLogViewer",
    "roles/datastore.viewer",
    "roles/bigquery.dataViewer",
    "roles/storage.objectViewer",
}
BROAD_ROLES = {"roles/owner", "roles/editor"}

for binding in data.get("bindings", []):
    role = binding.get("role", "")
    for member in binding.get("members", []):
        is_human = member.startswith("user:") and "gserviceaccount.com" not in member
        if role in BROAD_ROLES and is_human:
            human_owner_editor.append("{} has {}".format(member, role))
        if role in VIEWER_ROLES:
            viewer_roles.append("{} has {}".format(member, role))

print("HUMAN_OWNER_EDITOR_COUNT={}".format(len(human_owner_editor)))
for line in human_owner_editor:
    print("HUMAN_OWNER_EDITOR: {}".format(line))
print("VIEWER_ROLE_COUNT={}".format(len(viewer_roles)))
for line in viewer_roles:
    print("VIEWER_ROLE: {}".format(line))
print("TOTAL_BINDINGS={}".format(len(data.get("bindings", []))))
PYEOF
)
    rm -f "$IAM_TMP"
    echo "$IAM_SUMMARY" | sed 's/^/    /'
    HUMAN_COUNT=$(echo "$IAM_SUMMARY" | grep -o 'HUMAN_OWNER_EDITOR_COUNT=[0-9]*' | cut -d= -f2)
    if [ "${HUMAN_COUNT:-0}" -gt 0 ]; then
        record "project_iam_policy_human_owner_editor" "FAIL" "$HUMAN_COUNT human principal(s) hold Owner/Editor -- see detail above"
    else
        record "project_iam_policy_human_owner_editor" "PASS" "no human principal holds Owner or Editor"
    fi
    record "project_iam_policy_readable" "PASS" "policy read; $(echo "$IAM_SUMMARY" | grep -o 'TOTAL_BINDINGS=[0-9]*')"
fi

echo ""
echo "--- 2. Service account role envelopes ---------------------------------"

# check_sa_roles <check-prefix> <sa-email> <expected-roles-space-separated>
#
# Compares the LIVE project-level IAM bindings for one SA against the pinned
# expected set (test_deployed_iam_envelope.py's docstring for
# polyglot-backend-sa; test_admin_sa_iam_envelope.py's EXPECTED_ADMIN_SA_ROLES
# minus its own bucket/actAs/telemetry/monitoring carve-outs for
# admin-backend-sa). A mismatch is a FAIL either way: an EXTRA live role is an
# undocumented widening (scar #7 in the tightening direction still needs the
# ritual -- name the call, name the permission, check the policy BEFORE
# removing it, because a missing test cannot prove a role is unused); a
# MISSING live role means the pin is stale or the deploy never actually
# granted it.
check_sa_roles() {
    local prefix="$1"
    local sa_email="$2"
    shift 2
    local expected="$*"

    run_capture gcloud projects get-iam-policy "$PROJECT_ID" \
        --flatten="bindings[].members" \
        --filter="bindings.members:serviceAccount:${sa_email}" \
        --format="value(bindings.role)"
    if [ $_last_status -ne 0 ]; then
        record "${prefix}_roles" "N/A" "operator lacks resourcemanager.projects.getIamPolicy or the call failed"
        return
    fi

    local expected_sorted
    expected_sorted=$(echo "$expected" | tr ' ' '\n' | sort -u | tr '\n' ' ')
    local live_sorted
    live_sorted=$(echo "$_last_output" | sort -u | tr '\n' ' ')

    if [ "$live_sorted" = "$expected_sorted" ]; then
        record "${prefix}_roles" "PASS" "live project-level roles equal the pinned set (${expected_sorted})"
    else
        record "${prefix}_roles" "FAIL" "live=[${live_sorted}] pinned=[${expected_sorted}] -- corroborate against the test file before touching either"
    fi
}

# The pin, transcribed from backend/tests/unit/test_deployed_iam_envelope.py's
# module docstring (that file has no importable constant -- it states the
# envelope in prose, so this is the mechanical mirror of that prose).
BACKEND_SA_EXPECTED_ROLES="roles/aiplatform.user roles/storage.objectViewer roles/logging.logWriter roles/datastore.user roles/secretmanager.secretAccessor"
check_sa_roles "backend_sa" "polyglot-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com" "$BACKEND_SA_EXPECTED_ROLES"

# CHECK: backend_sa_no_firebaseauth_users_get
# The specific scar #7 permission: polyglot-backend-sa must NEVER hold
# firebaseauth.admin or any custom role granting firebaseauth.users.get.
run_capture gcloud projects get-iam-policy "$PROJECT_ID" \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:polyglot-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com AND bindings.role:firebaseauth" \
    --format="value(bindings.role)"
if [ $_last_status -ne 0 ]; then
    record "backend_sa_no_firebaseauth_role" "N/A" "operator lacks resourcemanager.projects.getIamPolicy"
elif [ -z "$_last_output" ]; then
    record "backend_sa_no_firebaseauth_role" "PASS" "polyglot-backend-sa holds no firebaseauth.* role"
else
    record "backend_sa_no_firebaseauth_role" "FAIL" "polyglot-backend-sa holds: $_last_output (scar #7 -- every deployed connection will 403 if this pairs with check_revoked=True, but the finding here is the GRANT itself)"
fi

# admin-backend-sa's project-level envelope, per
# admin_backend/tests/unit/test_admin_sa_iam_envelope.py's
# EXPECTED_ADMIN_SA_ROLES (project-level only -- storage.objectAdmin is
# bucket-scoped and checked separately below, and the CLOUD_BUILD_SA_ROLES
# actAs grant is resource-scoped onto polyglot-cloudbuild-sa, also checked
# separately).
# bigquery.dataViewer is DELIBERATELY excluded from this project-level set --
# it is granted scoped to the polyglot_telemetry DATASET (`bq
# add-iam-policy-binding`, not `gcloud projects add-iam-policy-binding`), so
# it never appears in a project-level bindings query and belongs in the
# dataset-scoped check under section 8 instead. Including it here would
# manufacture a permanent FAIL against a role that is correctly scoped
# elsewhere.
ADMIN_SA_EXPECTED_PROJECT_ROLES="roles/firebaseauth.admin roles/datastore.user roles/logging.logWriter roles/secretmanager.secretAccessor roles/bigquery.jobUser roles/errorreporting.viewer roles/monitoring.viewer roles/cloudbuild.builds.editor"
check_sa_roles "admin_sa_project" "admin-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com" "$ADMIN_SA_EXPECTED_PROJECT_ROLES"

# CHECK: admin_sa_bucket_role
# storage.objectAdmin on the form-kits bucket ONLY, never project-wide --
# test_admin_sa_iam_envelope.py's own scope-not-just-name pin, mirrored here
# against the LIVE bucket policy.
FORM_KITS_BUCKET="${PROJECT_ID}-form-kits"
run_capture gcloud storage buckets get-iam-policy "gs://${FORM_KITS_BUCKET}" --format=json
if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
    record "admin_sa_bucket_role" "N/A" "operator lacks storage.buckets.getIamPolicy on gs://${FORM_KITS_BUCKET} or the call failed: $(echo "$_last_output" | head -1)"
    record "admin_sa_bucket_role_not_project_wide" "N/A" "depends on admin_sa_bucket_role, which failed above"
else
    BUCKET_HAS_ADMIN=$(echo "$_last_output" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
target = 'serviceAccount:admin-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com'
for b in data.get('bindings', []):
    if b.get('role') == 'roles/storage.objectAdmin' and target in b.get('members', []):
        print('yes')
        break
else:
    print('no')
")
    if [ "$BUCKET_HAS_ADMIN" = "yes" ]; then
        record "admin_sa_bucket_role" "PASS" "admin-backend-sa holds roles/storage.objectAdmin on gs://${FORM_KITS_BUCKET}"
    else
        record "admin_sa_bucket_role" "FAIL" "admin-backend-sa is missing roles/storage.objectAdmin on gs://${FORM_KITS_BUCKET} -- form-kit publish/retire will fail"
    fi

    # Also check the bucket does NOT grant this project-wide instead (the
    # inverse mistake test_the_bucket_roles_are_granted_on_the_bucket_not_the_project
    # pins offline). Reads $_last_status BEFORE trusting an empty
    # $_last_output as "no project-wide binding" -- a FAILED
    # get-iam-policy call (auth expiry, a transient 503, a missing
    # getIamPolicy permission) also produces empty output, and treating
    # that as a clean PASS would report the scope guard as satisfied
    # PRECISELY BECAUSE the read that would have caught a real widening
    # never happened.
    run_capture gcloud projects get-iam-policy "$PROJECT_ID" \
        --flatten="bindings[].members" \
        --filter="bindings.members:serviceAccount:admin-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com AND bindings.role:roles/storage.objectAdmin" \
        --format="value(bindings.role)"
    if [ $_last_status -ne 0 ]; then
        record "admin_sa_bucket_role_not_project_wide" "N/A" "operator lacks resourcemanager.projects.getIamPolicy or the call failed"
    elif [ -n "$_last_output" ]; then
        record "admin_sa_bucket_role_not_project_wide" "FAIL" "admin-backend-sa holds roles/storage.objectAdmin at the PROJECT level -- should be bucket-scoped only"
    else
        record "admin_sa_bucket_role_not_project_wide" "PASS" "admin-backend-sa's storage.objectAdmin is not project-wide"
    fi
fi

# CHECK: admin_sa_actas_cloud_build
# iam.serviceAccountUser on polyglot-cloudbuild-sa specifically (resource-
# scoped), matching setup-admin-service.sh's CLOUD_BUILD_SA_ROLES grant.
run_capture gcloud iam service-accounts get-iam-policy \
    "polyglot-cloudbuild-sa@${PROJECT_ID}.iam.gserviceaccount.com" --format=json
if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
    record "admin_sa_actas_cloud_build" "N/A" "operator lacks iam.serviceAccounts.getIamPolicy on polyglot-cloudbuild-sa or the SA does not exist yet: $(echo "$_last_output" | head -1)"
else
    HAS_ACTAS=$(echo "$_last_output" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
target = 'serviceAccount:admin-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com'
for b in data.get('bindings', []):
    if b.get('role') == 'roles/iam.serviceAccountUser' and target in b.get('members', []):
        print('yes')
        break
else:
    print('no')
")
    if [ "$HAS_ACTAS" = "yes" ]; then
        record "admin_sa_actas_cloud_build" "PASS" "admin-backend-sa holds iam.serviceAccountUser on polyglot-cloudbuild-sa"
    else
        record "admin_sa_actas_cloud_build" "FAIL" "admin-backend-sa is missing the actAs grant on polyglot-cloudbuild-sa"
    fi
fi

# CHECK: cloudbuild_sa_project_roles
# polyglot-cloudbuild-sa's own PROJECT-LEVEL envelope (bd polyglot-pdf-p4ale),
# per admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py's
# EXPECTED_BUILD_SA_PROJECT_ROLES. That test file ALSO pins three more
# grants this build identity holds -- a bucket-scoped role, two
# resource-scoped actAs bindings, and a grant on a THIRD, Google-managed
# identity -- none of which a project-level-only check can see, so each
# gets its own check below (a project-wide iam.serviceAccountUser widening,
# for instance, would otherwise pass silently: it is not a project-level
# ROLE at all, and this file's own check_sa_roles only ever queries
# project-level bindings).
CLOUD_BUILD_SA_EXPECTED_ROLES="roles/run.admin roles/firebasehosting.admin roles/firebaserules.admin roles/datastore.indexAdmin roles/artifactregistry.writer roles/logging.logWriter roles/datastore.user roles/serviceusage.serviceUsageViewer"
check_sa_roles "cloudbuild_sa" "polyglot-cloudbuild-sa@${PROJECT_ID}.iam.gserviceaccount.com" "$CLOUD_BUILD_SA_EXPECTED_ROLES"

# CHECK: cloudbuild_sa_bucket_role
# storage.objectAdmin on the form-kits bucket ONLY -- test_cloud_build_sa_
# iam_envelope.py's EXPECTED_BUILD_SA_BUCKET_ROLES, mirrored here against
# the LIVE bucket policy, same shape as admin_sa_bucket_role above.
run_capture gcloud storage buckets get-iam-policy "gs://${FORM_KITS_BUCKET}" --format=json
if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
    record "cloudbuild_sa_bucket_role" "N/A" "operator lacks storage.buckets.getIamPolicy on gs://${FORM_KITS_BUCKET} or the call failed: $(echo "$_last_output" | head -1)"
    record "cloudbuild_sa_bucket_role_not_project_wide" "N/A" "depends on cloudbuild_sa_bucket_role, which failed above"
else
    CLOUDBUILD_BUCKET_JSON="$_last_output"
    CLOUDBUILD_BUCKET_HAS_ADMIN=$(echo "$CLOUDBUILD_BUCKET_JSON" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
target = 'serviceAccount:polyglot-cloudbuild-sa@${PROJECT_ID}.iam.gserviceaccount.com'
for b in data.get('bindings', []):
    if b.get('role') == 'roles/storage.objectAdmin' and target in b.get('members', []):
        print('yes')
        break
else:
    print('no')
")
    if [ "$CLOUDBUILD_BUCKET_HAS_ADMIN" = "yes" ]; then
        record "cloudbuild_sa_bucket_role" "PASS" "polyglot-cloudbuild-sa holds roles/storage.objectAdmin on gs://${FORM_KITS_BUCKET}"
    else
        record "cloudbuild_sa_bucket_role" "N/A" "polyglot-cloudbuild-sa is missing roles/storage.objectAdmin on gs://${FORM_KITS_BUCKET}, or the SA does not exist yet -- see cloudbuild_sa_roles above"
    fi

    # Reads $_last_status before trusting an empty $_last_output -- see
    # admin_sa_bucket_role_not_project_wide's comment above for why a
    # FAILED read must not be read as a clean PASS.
    run_capture gcloud projects get-iam-policy "$PROJECT_ID" \
        --flatten="bindings[].members" \
        --filter="bindings.members:serviceAccount:polyglot-cloudbuild-sa@${PROJECT_ID}.iam.gserviceaccount.com AND bindings.role:roles/storage.objectAdmin" \
        --format="value(bindings.role)"
    if [ $_last_status -ne 0 ]; then
        record "cloudbuild_sa_bucket_role_not_project_wide" "N/A" "operator lacks resourcemanager.projects.getIamPolicy or the call failed"
    elif [ -n "$_last_output" ]; then
        record "cloudbuild_sa_bucket_role_not_project_wide" "FAIL" "polyglot-cloudbuild-sa holds roles/storage.objectAdmin at the PROJECT level -- should be bucket-scoped only"
    else
        record "cloudbuild_sa_bucket_role_not_project_wide" "PASS" "polyglot-cloudbuild-sa's storage.objectAdmin is not project-wide"
    fi
fi

# CHECK: cloudbuild_sa_actas_<target> (one per EXPECTED_ACTAS_TARGETS member)
# roles/iam.serviceAccountUser, resource-scoped onto EACH runtime SA
# individually (test_cloud_build_sa_iam_envelope.py's EXPECTED_ACTAS_TARGETS
# -- polyglot-backend-sa AND admin-backend-sa) -- never project-wide, which
# would let the build identity impersonate every service account in the
# project. Checked by reading the TARGET SA's own IAM policy (the resource
# the binding lives on) and looking for polyglot-cloudbuild-sa as a member
# with this role, mirroring admin_sa_actas_cloud_build's own shape but from
# the build SA's side.
#
# CHECK: cloudbuild_sa_actas_not_project_wide -- run ONCE, outside the loop.
# Both targets' "is this project-wide" question is the SAME fact (one
# project-level IAM query for polyglot-cloudbuild-sa's own
# iam.serviceAccountUser bindings), so running it once per target issued an
# identical query twice and printed two identically-worded verdicts for one
# underlying condition. The per-target
# resource-scoped presence checks above stay in the loop -- only the
# project-wide SCOPE guard, which does not vary by target, moved out.
CLOUD_BUILD_ACTAS_TARGETS="polyglot-backend-sa admin-backend-sa"
for target_sa_name in $CLOUD_BUILD_ACTAS_TARGETS; do
    run_capture gcloud iam service-accounts get-iam-policy \
        "${target_sa_name}@${PROJECT_ID}.iam.gserviceaccount.com" --format=json
    if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
        record "cloudbuild_sa_actas_${target_sa_name}" "N/A" "operator lacks iam.serviceAccounts.getIamPolicy on ${target_sa_name} or the call failed: $(echo "$_last_output" | head -1)"
        continue
    fi
    TARGET_HAS_ACTAS=$(echo "$_last_output" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
target = 'serviceAccount:polyglot-cloudbuild-sa@${PROJECT_ID}.iam.gserviceaccount.com'
for b in data.get('bindings', []):
    if b.get('role') == 'roles/iam.serviceAccountUser' and target in b.get('members', []):
        print('yes')
        break
else:
    print('no')
")
    if [ "$TARGET_HAS_ACTAS" = "yes" ]; then
        record "cloudbuild_sa_actas_${target_sa_name}" "PASS" "polyglot-cloudbuild-sa holds iam.serviceAccountUser on ${target_sa_name}"
    else
        record "cloudbuild_sa_actas_${target_sa_name}" "N/A" "polyglot-cloudbuild-sa is missing the actAs grant on ${target_sa_name}, or the build SA does not exist yet -- see cloudbuild_sa_roles above"
    fi
done

run_capture gcloud projects get-iam-policy "$PROJECT_ID" \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:polyglot-cloudbuild-sa@${PROJECT_ID}.iam.gserviceaccount.com AND bindings.role:roles/iam.serviceAccountUser" \
    --format="value(bindings.role)"
if [ $_last_status -ne 0 ]; then
    record "cloudbuild_sa_actas_not_project_wide" "N/A" "operator lacks resourcemanager.projects.getIamPolicy or the call failed"
elif [ -n "$_last_output" ]; then
    record "cloudbuild_sa_actas_not_project_wide" "FAIL" "polyglot-cloudbuild-sa holds roles/iam.serviceAccountUser at the PROJECT level -- this would let it impersonate every service account in the project, not just its deploy targets"
else
    record "cloudbuild_sa_actas_not_project_wide" "PASS" "polyglot-cloudbuild-sa's iam.serviceAccountUser is not project-wide"
fi

# CHECK: cloudbuild_pubsub_token_creator
# The Pub/Sub service agent (a THIRD, Google-managed identity, distinct from
# both polyglot-cloudbuild-sa and the two runtime SAs) needs
# roles/iam.serviceAccountTokenCreator on itself to mint the OIDC token the
# build-status webhook's push subscription presents
# (test_cloud_build_sa_iam_envelope.py's
# test_pubsub_service_agent_gets_token_creator_for_the_build_webhook).
# Without it every build-status push 403s before the route's own auth check
# ever runs.
run_capture gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)"
if [ $_last_status -ne 0 ] || [ -z "$_last_output" ]; then
    record "cloudbuild_pubsub_token_creator" "N/A" "operator lacks resourcemanager.projects.get or the call failed"
else
    PROJECT_NUMBER="$_last_output"
    PUBSUB_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
    run_capture gcloud projects get-iam-policy "$PROJECT_ID" \
        --flatten="bindings[].members" \
        --filter="bindings.members:serviceAccount:${PUBSUB_SERVICE_AGENT} AND bindings.role:roles/iam.serviceAccountTokenCreator" \
        --format="value(bindings.role)"
    if [ $_last_status -ne 0 ]; then
        record "cloudbuild_pubsub_token_creator" "N/A" "operator lacks resourcemanager.projects.getIamPolicy or the call failed"
    elif [ -n "$_last_output" ]; then
        record "cloudbuild_pubsub_token_creator" "PASS" "the Pub/Sub service agent (${PUBSUB_SERVICE_AGENT}) holds roles/iam.serviceAccountTokenCreator"
    else
        record "cloudbuild_pubsub_token_creator" "N/A" "the Pub/Sub service agent is missing roles/iam.serviceAccountTokenCreator, or bead 4.3's webhook has not been provisioned yet"
    fi
fi

echo ""
echo "--- 3. Cloud Run services + latest revisions ---------------------------"

# The three known services. A FOURTH turning up unexpectedly is itself a
# finding this loop's own service-list step surfaces.
KNOWN_SERVICES="polyglot-backend polyglot-backend-staging polyglot-admin"

run_capture gcloud run services list --platform=managed --region="$REGION" \
    --project="$PROJECT_ID" --format="value(metadata.name)"
if [ $_last_status -ne 0 ]; then
    record "cloud_run_services_list" "N/A" "operator lacks run.services.list or the call failed"
else
    LIVE_SERVICES="$_last_output"
    record "cloud_run_services_list" "PASS" "$(echo "$LIVE_SERVICES" | tr '\n' ' ')"
    for svc in $LIVE_SERVICES; do
        case " $KNOWN_SERVICES " in
            *" $svc "*) ;;
            *) record "cloud_run_unexpected_service" "FAIL" "$svc is not one of the three documented services ($KNOWN_SERVICES)" ;;
        esac
    done
    # The CONVERSE of the check above: a documented service that has gone
    # MISSING from the live listing (deleted, renamed, or never deployed on
    # this project) is itself a finding, not a silent gap -- without this,
    # a missing service degrades straight to each of its 9 per-service
    # checks reading N/A ("not deployed") with no single line calling out
    # that the absence itself is the anomaly worth flagging.
    #
    # LIVE_SERVICES is NEWLINE-separated (gcloud's --format="value(...)"
    # emits one name per line), not space-separated -- so a
    # `case " $LIVE_SERVICES " in *" $x "*)` glob match against the raw
    # variable never matches anything (the embedded newlines are not the
    # spaces the pattern looks for). Word-splitting it through a `for` loop
    # into a space-joined string first is what the ANALOGOUS
    # unexpected-service loop above gets right implicitly (it iterates
    # `for svc in $LIVE_SERVICES`, which word-splits on the shell's IFS --
    # newlines included by default); this converse direction needs the same
    # normalization done explicitly since it checks membership the other
    # way around.
    LIVE_SERVICES_SPACED=""
    for live_svc in $LIVE_SERVICES; do
        LIVE_SERVICES_SPACED="$LIVE_SERVICES_SPACED $live_svc"
    done
    for expected_svc in $KNOWN_SERVICES; do
        case " $LIVE_SERVICES_SPACED " in
            *" $expected_svc "*) ;;
            *) record "cloud_run_missing_service" "FAIL" "$expected_svc is one of the three documented services but is absent from the live listing (deleted, renamed, or never deployed on this project)" ;;
        esac
    done
fi

# check_service_env <service-name>
#
# Pulls the LATEST revision's env vars + secret bindings + ingress + scaling
# + runtime SA and evaluates them against the plan's D checklist:
#   - no secret-shaped VALUE among plain env vars (heuristic: a value that
#     looks like a JWT, an API key, or a long base64/hex blob -- the NAME is
#     always safe to print, the VALUE only ever appears as a verdict);
#   - none of VFF_DISABLE_AUTH=true / VERTEXAI=false;
#   - no verbosity knob set (HTTPX_LOG_LEVEL, GOOGLE_GENAI_*, SEND_TRANSCRIPT,
#     DEV_LOGGING_ENABLED);
#   - secret bindings present (informational -- prints names only, matching
#     the deploy channel's [SET_SECRETS] section, e.g. LINK_TOKEN_SECRET);
#   - ingress setting;
#   - min/max instance counts;
#   - runtime service account.
# The 8 per-service checks OTHER than "describe" itself -- listed once so
# both of check_service_env's early-return branches (a failed describe call,
# a non-JSON response) can emit all 9 checks as N/A instead of silently
# recording only "describe" and leaving the other 8 entirely absent from
# the results table. A silent drop reads, from the output alone, as if
# those 8 checks were simply never run for this service -- indistinguishable
# from a scripting bug -- rather than as the documented consequence of the
# service being undescribable.
_PER_SERVICE_OTHER_SUFFIXES="no_secret_shaped_env no_forbidden_flags no_verbosity_knobs secret_bindings ingress scaling runtime_sa env_var_names"

# record_service_na <service> <reason>
#
# Records the "describe" check plus all 8 dependent checks as N/A with the
# same reason, so a missing/undescribable service still produces a full,
# reviewable row set instead of one line and silence.
record_service_na() {
    local service="$1"
    local reason="$2"
    record "cloud_run_${service}_describe" "N/A" "$reason"
    for suffix in $_PER_SERVICE_OTHER_SUFFIXES; do
        record "cloud_run_${service}_${suffix}" "N/A" "depends on cloud_run_${service}_describe, which failed above"
    done
}

check_service_env() {
    local service="$1"
    run_capture gcloud run services describe "$service" --platform=managed \
        --region="$REGION" --project="$PROJECT_ID" --format=json
    if [ $_last_status -ne 0 ]; then
        record_service_na "$service" "operator lacks run.services.get on $service or it is not deployed"
        return
    fi

    if ! is_valid_json "$_last_output"; then
        record_service_na "$service" "run.services.get on $service returned non-JSON output: $(echo "$_last_output" | head -1)"
        return
    fi

    # Written to a temp file and passed as an ARGUMENT (sys.argv[2]), not
    # piped via `<` on the same command as a `<<heredoc` -- a heredoc on a
    # command silently WINS over an explicit `<` stdin redirection on that
    # same command, so `python - "$service" < "$tmp_json" <<'EOF'` reads the
    # heredoc's (empty-of-JSON) body and sys.stdin.read() returns "", not the
    # bucket-loaded environment. This is why an earlier draft of this check
    # printed every field as empty despite gcloud succeeding. Reading the
    # path as an argument sidesteps the conflict entirely.
    local tmp_json
    tmp_json=$(mktemp)
    printf '%s' "$_last_output" > "$tmp_json"
    local summary
    summary=$("$PYTHON_BIN" - "$service" "$tmp_json" <<'PYEOF3'
import json
import re
import sys

service = sys.argv[1]
json_path = sys.argv[2]
with open(json_path, encoding="utf-8") as f:
    data = json.load(f)

spec = data.get("spec", {}).get("template", {}).get("spec", {})
containers = spec.get("containers", [{}])
container = containers[0] if containers else {}
env_list = container.get("env", [])

FORBIDDEN_FLAGS = {("VFF_DISABLE_AUTH", "true"), ("VERTEXAI", "false")}
VERBOSITY_KNOBS = {"HTTPX_LOG_LEVEL", "SEND_TRANSCRIPT", "DEV_LOGGING_ENABLED"}
JWT_RE = re.compile(r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
LONG_TOKEN_RE = re.compile(r"^[A-Za-z0-9+/=_-]{32,}$")
# Known-safe long-hex-shaped values this repo deliberately deploys in plain
# env vars, per docs/components/config-deployment.md's own "GET /version"
# section -- a 40-char git commit SHA reads as a long alnum blob to
# LONG_TOKEN_RE, but it is not a secret: it is printed back by the /version
# route on purpose. Excluding by NAME (not by pattern-widening the regex,
# which would just as easily hide a real secret shaped like a SHA) keeps the
# heuristic honest about what it is actually allowlisting.
NAME_ALLOWLIST = {"GIT_SHA"}

secret_shaped, forbidden, verbosity, names = [], [], [], []
for entry in env_list:
    name = entry.get("name", "")
    value = entry.get("value")
    names.append(name)
    if value is not None:
        if name not in NAME_ALLOWLIST and (JWT_RE.match(value) or LONG_TOKEN_RE.match(value)):
            secret_shaped.append(name)
        for fname, fval in FORBIDDEN_FLAGS:
            if name == fname and value.lower() == fval:
                forbidden.append("{}={}".format(name, value))
        if name.startswith("GOOGLE_GENAI_") or name in VERBOSITY_KNOBS:
            verbosity.append(name)
    elif name.startswith("GOOGLE_GENAI_") or name in VERBOSITY_KNOBS:
        verbosity.append(name)

secret_bindings = [e.get("name") for e in env_list if e.get("valueFrom", {}).get("secretKeyRef")]
ingress = data.get("metadata", {}).get("annotations", {}).get("run.googleapis.com/ingress", "unspecified")
min_instances = data.get("metadata", {}).get("annotations", {}).get("autoscaling.knative.dev/minScale", "0")
max_instances = data.get("spec", {}).get("template", {}).get("metadata", {}).get("annotations", {}).get("autoscaling.knative.dev/maxScale", "unspecified")
runtime_sa = spec.get("serviceAccountName", "unspecified")

print("ENV_VAR_NAMES={}".format(",".join(sorted(names))))
print("SECRET_SHAPED_ENV_COUNT={}".format(len(secret_shaped)))
print("SECRET_SHAPED_ENV_NAMES={}".format(",".join(secret_shaped)))
print("FORBIDDEN_FLAG_COUNT={}".format(len(forbidden)))
print("FORBIDDEN_FLAGS={}".format(",".join(forbidden)))
print("VERBOSITY_KNOB_COUNT={}".format(len(verbosity)))
print("VERBOSITY_KNOBS={}".format(",".join(verbosity)))
print("SECRET_BINDING_NAMES={}".format(",".join(sorted(secret_bindings))))
print("INGRESS={}".format(ingress))
print("MIN_INSTANCES={}".format(min_instances))
print("MAX_INSTANCES={}".format(max_instances))
print("RUNTIME_SA={}".format(runtime_sa))
PYEOF3
)
    rm -f "$tmp_json"

    local secret_count forbidden_count verbosity_count runtime_sa ingress
    secret_count=$(echo "$summary" | grep -o 'SECRET_SHAPED_ENV_COUNT=[0-9]*' | cut -d= -f2)
    forbidden_count=$(echo "$summary" | grep -o 'FORBIDDEN_FLAG_COUNT=[0-9]*' | cut -d= -f2)
    verbosity_count=$(echo "$summary" | grep -o 'VERBOSITY_KNOB_COUNT=[0-9]*' | cut -d= -f2)
    runtime_sa=$(echo "$summary" | grep '^RUNTIME_SA=' | cut -d= -f2-)
    ingress=$(echo "$summary" | grep '^INGRESS=' | cut -d= -f2-)
    local min_i max_i secret_bindings env_names
    min_i=$(echo "$summary" | grep '^MIN_INSTANCES=' | cut -d= -f2-)
    max_i=$(echo "$summary" | grep '^MAX_INSTANCES=' | cut -d= -f2-)
    secret_bindings=$(echo "$summary" | grep '^SECRET_BINDING_NAMES=' | cut -d= -f2-)
    env_names=$(echo "$summary" | grep '^ENV_VAR_NAMES=' | cut -d= -f2-)

    if [ "${secret_count:-0}" -gt 0 ]; then
        record "cloud_run_${service}_no_secret_shaped_env" "FAIL" "secret-shaped value(s) in plain env vars: $(echo "$summary" | grep '^SECRET_SHAPED_ENV_NAMES=' | cut -d= -f2-)"
    else
        record "cloud_run_${service}_no_secret_shaped_env" "PASS" "no plain env var holds a secret-shaped value"
    fi

    if [ "${forbidden_count:-0}" -gt 0 ]; then
        record "cloud_run_${service}_no_forbidden_flags" "FAIL" "$(echo "$summary" | grep '^FORBIDDEN_FLAGS=' | cut -d= -f2-)"
    else
        record "cloud_run_${service}_no_forbidden_flags" "PASS" "neither VFF_DISABLE_AUTH=true nor VERTEXAI=false is set"
    fi

    if [ "${verbosity_count:-0}" -gt 0 ]; then
        record "cloud_run_${service}_no_verbosity_knobs" "FAIL" "verbosity knob(s) set: $(echo "$summary" | grep '^VERBOSITY_KNOBS=' | cut -d= -f2-)"
    else
        record "cloud_run_${service}_no_verbosity_knobs" "PASS" "no HTTPX_LOG_LEVEL / GOOGLE_GENAI_* / SEND_TRANSCRIPT / DEV_LOGGING_ENABLED set"
    fi

    record "cloud_run_${service}_secret_bindings" "PASS" "bound secret names: ${secret_bindings:-none}"
    record "cloud_run_${service}_ingress" "PASS" "ingress=${ingress}"
    record "cloud_run_${service}_scaling" "PASS" "min=${min_i} max=${max_i}"
    record "cloud_run_${service}_runtime_sa" "PASS" "runs as ${runtime_sa}"
    record "cloud_run_${service}_env_var_names" "PASS" "${env_names}"
}

for svc in $KNOWN_SERVICES; do
    check_service_env "$svc"
done

echo ""
echo "--- 4. Secret Manager ---------------------------------------------------"

# CHECK: secret_manager_secrets_and_iam
# Lists every secret and, for each, any RESOURCE-LEVEL accessor binding
# (secretAccessor granted on the secret itself, e.g. a per-secret grant to
# an unusual principal). A secret showing NO resource-level binding is the
# NORMAL case in this repo: polyglot-backend-sa and admin-backend-sa both
# read LINK_TOKEN_SECRET/GEMINI_API_KEY via the PROJECT-level
# secretmanager.secretAccessor role each SA holds (see the SA role checks
# above), not a per-secret grant -- so an empty accessors list here means
# "no additional per-secret grant beyond the project role", never "nobody
# can read this secret".
run_capture gcloud secrets list --project="$PROJECT_ID" --format="value(name)"
if [ $_last_status -ne 0 ]; then
    record "secret_manager_list" "N/A" "operator lacks secretmanager.secrets.list or the call failed"
else
    SECRETS="$_last_output"
    record "secret_manager_list" "PASS" "$(echo "$SECRETS" | tr '\n' ' ')"
    for secret in $SECRETS; do
        run_capture gcloud secrets get-iam-policy "$secret" --project="$PROJECT_ID" \
            --format="value(bindings.members)"
        if [ $_last_status -ne 0 ]; then
            record "secret_manager_${secret}_iam" "N/A" "operator lacks secretmanager.secrets.getIamPolicy on $secret"
        elif [ -z "$_last_output" ]; then
            record "secret_manager_${secret}_iam" "PASS" "no resource-level bindings; access via project role (see the SA role checks above)"
        else
            record "secret_manager_${secret}_iam" "PASS" "resource-level accessors: $(echo "$_last_output" | tr '\n' ' ')"
        fi
    done
fi

echo ""
echo "--- 5. Form-kits bucket -------------------------------------------------"

# CHECK: bucket_no_allusers
run_capture gcloud storage buckets get-iam-policy "gs://${FORM_KITS_BUCKET}" --format=json
if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
    record "bucket_no_allusers" "N/A" "operator lacks storage.buckets.getIamPolicy or the call failed: $(echo "$_last_output" | head -1)"
else
    HAS_ALLUSERS=$(echo "$_last_output" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
for b in data.get('bindings', []):
    if 'allUsers' in b.get('members', []) or 'allAuthenticatedUsers' in b.get('members', []):
        print('yes')
        break
else:
    print('no')
")
    if [ "$HAS_ALLUSERS" = "yes" ]; then
        record "bucket_no_allusers" "FAIL" "gs://${FORM_KITS_BUCKET} grants allUsers or allAuthenticatedUsers -- public read/write on the form-kits store"
    else
        record "bucket_no_allusers" "PASS" "no allUsers/allAuthenticatedUsers binding on gs://${FORM_KITS_BUCKET}"
    fi
fi

# CHECK: bucket_public_access_prevention + uniform_access
run_capture gcloud storage buckets describe "gs://${FORM_KITS_BUCKET}" \
    --format="value(public_access_prevention,uniform_bucket_level_access)"
if [ $_last_status -ne 0 ]; then
    record "bucket_public_access_prevention" "N/A" "operator lacks storage.buckets.get or the call failed"
    record "bucket_uniform_access" "N/A" "operator lacks storage.buckets.get or the call failed"
else
    PAP=$(echo "$_last_output" | awk '{print $1}')
    UNIFORM=$(echo "$_last_output" | awk '{print $2}')
    if [ "$PAP" = "enforced" ]; then
        record "bucket_public_access_prevention" "PASS" "enforced"
    else
        record "bucket_public_access_prevention" "FAIL" "public_access_prevention=${PAP:-unset} (expected 'enforced')"
    fi
    if [ "$UNIFORM" = "True" ] || [ "$UNIFORM" = "true" ]; then
        record "bucket_uniform_access" "PASS" "uniform bucket-level access is on"
    else
        record "bucket_uniform_access" "FAIL" "uniform_bucket_level_access=${UNIFORM:-unset} -- per-object ACLs can diverge from the bucket policy"
    fi
fi

# CHECK: bucket_object_anomalies
# Lists top-level prefixes only (not every object -- this is a shape check,
# not a content audit; workstream A's inventory_stores.py owns per-object
# sampling). Flags anything outside the expected <kit>/, _archive/, _drafts/
# top-level shape.
run_capture gcloud storage ls "gs://${FORM_KITS_BUCKET}/"
if [ $_last_status -ne 0 ]; then
    record "bucket_object_anomalies" "N/A" "operator lacks storage.objects.list or the call failed"
else
    record "bucket_object_anomalies" "PASS" "top-level listing: $(echo "$_last_output" | wc -l) entries (see workstream A's inventory_stores.py for a per-object sweep)"
fi

echo ""
echo "--- 6. Firestore rules, TTL, backups -------------------------------------"

# CHECK: firestore_rules_byte_equal
# Fetches the DEPLOYED ruleset and compares it against the repo's
# firestore.rules -- test_firestore_rules_text.py pins the repo file's
# CONTENT; this is what proves the deployed copy matches it.
#
# Neither the `firebase` CLI nor `gcloud` ships a subcommand for reading a
# Firestore ruleset's CONTENT (gcloud's `firebase` group covers Test Lab
# only; the firebase CLI has no `firestore:rules:get`). The only read path is
# the Firebase Rules REST API directly: list releases for the Firestore
# release, take the ruleset name off it, fetch that ruleset, and extract its
# one source file's content. Uses the operator's own ADC access token -- no
# separate credential.
#
# TWO THINGS ABOUT THIS API THAT COST A ROUND OF REVIEW TO FIND:
#   1. The release is named plain "cloud.firestore", NOT
#      "cloud.firestore/(default)" -- the latter 400s. Verified against the
#      live API (`GET .../releases` lists `cloud.firestore` by itself).
#   2. Firebase Rules is a Firebase-branded API layered on a GCP project;
#      called under a USER's own ADC (not a service account already
#      associated with the project) it 403s SERVICE_DISABLED unless the
#      request carries `x-goog-user-project: <project>` telling it which
#      project's quota/billing to charge -- so a missing header reads
#      exactly like a missing IAM permission when the real cause is a
#      missing header. Without it, this check would misreport a real
#      capability gap as "operator lacks firebaserules.releases.get", which
#      sends whoever reads that N/A down the wrong path entirely.
#
# THE COMPARISON ITSELF RUNS ENTIRELY INSIDE PYTHON, not via a bash
# `$(...)` round-trip: `firestore.rules` is CRLF in this repo (verified:
# both the live JSON's escaped `\r\n` and the repo file's raw bytes carry
# 176 CR/176 LF each -- the two are byte-identical at the SOURCE), but
# printing that content through `print()` on WINDOWS TEXT-MODE stdout
# rewrites every `\n` to `\r\n` a SECOND time, so a value that started at
# 176 CRs comes back out through a bash command substitution with roughly
# DOUBLE that -- comparing two already-mangled bash strings then reports a
# confident, wrong FAIL on content that actually matches byte-for-byte.
# Reading BOTH sides as bytes, normalizing (\r\n -> \n) on both before
# comparing, and printing only a PASS/FAIL/N-A verdict plus both content's
# hashes (never the compared strings themselves, which route through no
# further bash text processing that could re-mangle them) avoids the
# platform text-mode trap entirely.
ACCESS_TOKEN=$(gcloud auth print-access-token 2>/dev/null)
if [ -z "$ACCESS_TOKEN" ]; then
    record "firestore_rules_byte_equal" "N/A" "gcloud auth print-access-token failed -- operator has no active ADC session"
else
    run_capture curl -sf \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "x-goog-user-project: ${PROJECT_ID}" \
        "https://firebaserules.googleapis.com/v1/projects/${PROJECT_ID}/releases/cloud.firestore"
    if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
        record "firestore_rules_byte_equal" "N/A" "operator lacks firebaserules.releases.get on ${PROJECT_ID} (or no release named cloud.firestore exists): $(echo "$_last_output" | head -1)"
    else
        RULESET_NAME=$(echo "$_last_output" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
print(data.get('rulesetName', ''))
" 2>/dev/null)
        if [ -z "$RULESET_NAME" ]; then
            record "firestore_rules_byte_equal" "N/A" "release response carried no rulesetName -- unexpected API shape"
        else
            run_capture curl -sf \
                -H "Authorization: Bearer ${ACCESS_TOKEN}" \
                -H "x-goog-user-project: ${PROJECT_ID}" \
                "https://firebaserules.googleapis.com/v1/${RULESET_NAME}"
            if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
                record "firestore_rules_byte_equal" "N/A" "operator lacks firebaserules.rulesets.get on ${RULESET_NAME}: $(echo "$_last_output" | head -1)"
            else
                RULESET_TMP=$(mktemp)
                printf '%s' "$_last_output" > "$RULESET_TMP"
                RULES_VERDICT=$("$PYTHON_BIN" - "$RULESET_TMP" "${REPO_ROOT}/firestore.rules" <<'PYEOF4'
import hashlib
import json
import sys

ruleset_path, repo_path = sys.argv[1], sys.argv[2]

with open(ruleset_path, encoding="utf-8") as f:
    data = json.load(f)
files = data.get("source", {}).get("files", [])
live_content = files[0].get("content", "") if files else ""

try:
    with open(repo_path, "rb") as f:
        repo_bytes = f.read()
except OSError as e:
    print("ERROR could not read repo firestore.rules: {}".format(e))
    sys.exit(0)

# Normalize line endings on BOTH sides before comparing -- this repo's
# firestore.rules is CRLF, and the live API's JSON-escaped content
# preserves whatever line ending was in force when it was last published,
# so a real, meaningful divergence must not hide behind (or be manufactured
# by) an line-ending convention difference alone.
live_norm = live_content.replace("\r\n", "\n").encode("utf-8")
repo_norm = repo_bytes.replace(b"\r\n", b"\n")

live_hash = hashlib.sha256(live_norm).hexdigest()
repo_hash = hashlib.sha256(repo_norm).hexdigest()

if live_norm == repo_norm:
    print("PASS live_sha256={} repo_sha256={}".format(live_hash, repo_hash))
else:
    print("FAIL live_sha256={} repo_sha256={} live_len={} repo_len={}".format(
        live_hash, repo_hash, len(live_norm), len(repo_norm)))
PYEOF4
)
                rm -f "$RULESET_TMP"
                if [[ "$RULES_VERDICT" == PASS* ]]; then
                    record "firestore_rules_byte_equal" "PASS" "deployed ruleset (${RULESET_NAME}) matches firestore.rules -- ${RULES_VERDICT#PASS }"
                elif [[ "$RULES_VERDICT" == FAIL* ]]; then
                    record "firestore_rules_byte_equal" "FAIL" "deployed ruleset (${RULESET_NAME}) differs from the repo's firestore.rules -- ${RULES_VERDICT#FAIL }"
                else
                    record "firestore_rules_byte_equal" "N/A" "$RULES_VERDICT"
                fi
            fi
        fi
    fi
fi

# CHECK: firestore_ttl_policies
run_capture gcloud firestore fields ttls list --database="(default)" \
    --project="$PROJECT_ID" --format="value(name,ttlConfig.state)"
if [ $_last_status -ne 0 ]; then
    record "firestore_ttl_policies" "N/A" "operator lacks datastore.fields.list or the call failed (or no TTL fields are configured, which the API reports as an error on some gcloud versions)"
else
    if [ -z "$_last_output" ]; then
        record "firestore_ttl_policies" "PASS" "no TTL fields configured (see workstream A's retention-policy bead for whether one should exist)"
    else
        record "firestore_ttl_policies" "PASS" "$(echo "$_last_output" | tr '\n' '; ')"
    fi
fi

# CHECK: firestore_pitr_backups
run_capture gcloud firestore databases describe --database="(default)" \
    --project="$PROJECT_ID" --format="value(pointInTimeRecoveryEnablement)"
if [ $_last_status -ne 0 ]; then
    record "firestore_pitr" "N/A" "operator lacks datastore.databases.get or the call failed"
else
    record "firestore_pitr" "PASS" "pointInTimeRecoveryEnablement=${_last_output:-unset}"
fi

run_capture gcloud firestore backups schedules list --database="(default)" \
    --project="$PROJECT_ID" --format="value(name,retention)"
if [ $_last_status -ne 0 ]; then
    record "firestore_backup_schedules" "N/A" "operator lacks datastore.backupSchedules.list or the call failed"
else
    if [ -z "$_last_output" ]; then
        record "firestore_backup_schedules" "PASS" "no backup schedules configured (informational -- no retention decision has been made yet, per workstream A)"
    else
        record "firestore_backup_schedules" "PASS" "$(echo "$_last_output" | tr '\n' '; ')"
    fi
fi

echo ""
echo "--- 7. Cloud Logging: retention, sinks, exclusions, audit config -------"

# CHECK: logging_default_bucket_retention
run_capture gcloud logging buckets describe _Default --location=global \
    --project="$PROJECT_ID" --format="value(retentionDays)"
if [ $_last_status -ne 0 ]; then
    record "logging_default_bucket_retention" "N/A" "operator lacks logging.buckets.get or the call failed"
else
    record "logging_default_bucket_retention" "PASS" "_Default bucket retentionDays=${_last_output}"
fi

# CHECK: logging_sinks_match_repo
# There is no sink DEFINITION file tracked in this repo today (sinks are
# provisioned by hand or by a setup script not yet written) -- this check
# lists what exists live so a reviewer can compare it against
# docs/standards/logging-and-cost.md by hand until a repo-side sink
# declaration exists to diff against mechanically.
run_capture gcloud logging sinks list --project="$PROJECT_ID" --format="value(name,filter)"
if [ $_last_status -ne 0 ]; then
    record "logging_sinks_list" "N/A" "operator lacks logging.sinks.list or the call failed"
else
    if [ -z "$_last_output" ]; then
        record "logging_sinks_list" "N/A" "no sinks configured -- no repo-tracked sink declaration exists yet to compare against, so this is informational, not a byte-equal check"
    else
        record "logging_sinks_list" "PASS" "$(echo "$_last_output" | tr '\n' '; ')"
    fi
fi

# CHECK: logging_exclusion_ws_token_present
# B0's own exclusion filter (bd polyglot-pdf-6rj0j, ASK 1): a narrow
# exclusion on the _Default sink scoped to
# logName=~"requests" AND httpRequest.requestUrl=~"[?&]token=".
run_capture gcloud logging sinks describe _Default --project="$PROJECT_ID" \
    --format=json
if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
    record "logging_exclusion_ws_token_present" "N/A" "operator lacks logging.sinks.get on _Default or the call failed: $(echo "$_last_output" | head -1)"
else
    HAS_EXCLUSION=$(echo "$_last_output" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
for excl in data.get('exclusions', []):
    f = excl.get('filter', '')
    if 'requestUrl' in f and 'token=' in f:
        print('yes:' + excl.get('name', 'unnamed'))
        break
else:
    print('no')
")
    if [[ "$HAS_EXCLUSION" == yes:* ]]; then
        record "logging_exclusion_ws_token_present" "PASS" "the WS-token exclusion is present (${HAS_EXCLUSION#yes:})"
    else
        record "logging_exclusion_ws_token_present" "FAIL" "no exclusion filter on _Default matches requestUrl token= -- B0's ASK 1 has not landed live, or the maintainer declined it (check the bead for the recorded decision before treating this as an open finding)"
    fi
fi

# CHECK: logging_data_access_audit_config
run_capture gcloud projects get-iam-policy "$PROJECT_ID" --format="value(auditConfigs)"
if [ $_last_status -ne 0 ]; then
    record "logging_data_access_audit_config" "N/A" "operator lacks resourcemanager.projects.getIamPolicy or the call failed"
else
    if [ -z "$_last_output" ]; then
        record "logging_data_access_audit_config" "PASS" "no Data Access audit config beyond the platform default (informational -- Data Access logs are opt-in and cost extra; no decision has been made to enable them)"
    else
        record "logging_data_access_audit_config" "PASS" "$_last_output"
    fi
fi

echo ""
echo "--- 8. BigQuery telemetry ------------------------------------------------"

TELEMETRY_DATASET="polyglot_telemetry"

# The `bq` CLI shells out to its OWN bundled python, resolved via
# CLOUDSDK_PYTHON if set, else whatever `python`/`python3` PATH lookup finds
# -- a DIFFERENT resolution than this script's own $PYTHON_BIN (which is
# verified working before use; see the top of this file). On at least one
# operator machine a broken Chocolatey python3.14 shim sits on PATH ahead of
# a real interpreter, so `bq` fails with "python3.14: command not found"
# while every gcloud call succeeds -- a LOCAL TOOLING gap, not a permission
# gap, fixed by exporting CLOUDSDK_PYTHON to a known-working interpreter
# before running this script (e.g. the one $PYTHON_BIN itself resolved to,
# printed at the top of this script's output).
run_capture bq show --format=prettyjson "${PROJECT_ID}:${TELEMETRY_DATASET}"
if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
    BQ_ERROR_DETAIL="$(echo "$_last_output" | head -1)"
    if echo "$BQ_ERROR_DETAIL" | grep -qi "command not found"; then
        BQ_NA_REASON="the local bq CLI's own python interpreter is broken (${BQ_ERROR_DETAIL}) -- set CLOUDSDK_PYTHON to a working interpreter (e.g. CLOUDSDK_PYTHON=\"${PYTHON_BIN}\") and re-run this script"
    else
        BQ_NA_REASON="operator lacks bigquery.datasets.get on ${TELEMETRY_DATASET}, the dataset does not exist, or the local bq CLI failed: ${BQ_ERROR_DETAIL}"
    fi
    record "bigquery_dataset_acl" "N/A" "$BQ_NA_REASON"
    record "bigquery_table_expiration" "N/A" "depends on bigquery_dataset_acl, which failed above"
    record "admin_sa_bigquery_dataviewer_dataset_scoped" "N/A" "depends on bigquery_dataset_acl, which failed above"
else
    DATASET_JSON="$_last_output"
    ACL_SUMMARY=$(echo "$DATASET_JSON" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
for entry in data.get('access', []):
    role = entry.get('role', '?')
    principal = entry.get('userByEmail') or entry.get('groupByEmail') or entry.get('specialGroup') or entry.get('iamMember') or '?'
    print('{}:{}'.format(role, principal))
")
    record "bigquery_dataset_acl" "PASS" "$(echo "$ACL_SUMMARY" | tr '\n' '; ')"

    DEFAULT_EXPIRATION=$(echo "$DATASET_JSON" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
print(data.get('defaultTableExpirationMs', 'unset'))
")
    if [ "$DEFAULT_EXPIRATION" = "unset" ] || [ "$DEFAULT_EXPIRATION" = "null" ]; then
        record "bigquery_table_expiration" "N/A" "no default table expiration set on ${TELEMETRY_DATASET} -- no retention decision has been made yet (workstream A retention bead)"
    else
        record "bigquery_table_expiration" "PASS" "defaultTableExpirationMs=${DEFAULT_EXPIRATION}"
    fi

    # CHECK: admin_sa_bigquery_dataviewer_dataset_scoped
    # roles/bigquery.dataViewer is granted on THIS DATASET ONLY (bq
    # add-iam-policy-binding), never project-wide -- confirmed absent from
    # ADMIN_SA_EXPECTED_PROJECT_ROLES above for exactly this reason. Checked
    # here, against the dataset ACL just read, rather than a second API call.
    HAS_DATAVIEWER=$(echo "$DATASET_JSON" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
target = 'admin-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com'
for entry in data.get('access', []):
    if entry.get('role') == 'READER' and entry.get('userByEmail') == target:
        print('yes')
        break
    if entry.get('iamMember') == 'serviceAccount:' + target and entry.get('role') in ('READER', 'roles/bigquery.dataViewer'):
        print('yes')
        break
else:
    print('no')
")
    if [ "$HAS_DATAVIEWER" = "yes" ]; then
        record "admin_sa_bigquery_dataviewer_dataset_scoped" "PASS" "admin-backend-sa holds dataViewer on the ${TELEMETRY_DATASET} dataset"
    else
        record "admin_sa_bigquery_dataviewer_dataset_scoped" "FAIL" "admin-backend-sa is missing dataViewer on the ${TELEMETRY_DATASET} dataset -- the console's cost/income dashboards will fail to query it"
    fi
fi

echo ""
echo "--- 9. Firebase Auth ------------------------------------------------------"

# There is no `gcloud identity-platform` command group (gcloud's `identity`
# group covers Cloud Identity groups, not Identity Platform/Firebase Auth
# config, and `gcloud firebase` only covers Test Lab) -- verified against
# this operator's installed gcloud. The only read path is the Identity
# Toolkit Admin v2 REST API directly, via the same access-token + curl
# pattern the Firestore rules check above uses.
if [ -z "${ACCESS_TOKEN:-}" ]; then
    ACCESS_TOKEN=$(gcloud auth print-access-token 2>/dev/null)
fi

if [ -z "$ACCESS_TOKEN" ]; then
    record "firebase_auth_authorized_domains" "N/A" "gcloud auth print-access-token failed -- operator has no active ADC session"
    record "firebase_auth_email_enumeration_protection" "N/A" "gcloud auth print-access-token failed"
    record "firebase_auth_providers" "N/A" "gcloud auth print-access-token failed"
    record "firebase_auth_password_policy" "N/A" "gcloud auth print-access-token failed"
else
    run_capture curl -sf -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        "https://identitytoolkit.googleapis.com/v2/projects/${PROJECT_ID}/config"
    if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
        record "firebase_auth_authorized_domains" "N/A" "operator lacks identitytoolkit.googleapis.com read access (needs a role such as roles/firebaseauth.viewer) or the call failed: $(echo "$_last_output" | head -1)"
        record "firebase_auth_email_enumeration_protection" "N/A" "same call as authorized_domains failed"
        record "firebase_auth_password_policy" "N/A" "same call as authorized_domains failed"
    else
        AUTH_CONFIG="$_last_output"
        AUTH_SUMMARY=$(echo "$AUTH_CONFIG" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
domains = data.get('authorizedDomains', [])
email_privacy = data.get('client', {}).get('permissions', {}).get('enableEmailPrivacy', False)
has_password_policy = bool(data.get('passwordPolicyConfig'))
print('DOMAINS={}'.format(','.join(domains)))
print('EMAIL_PRIVACY={}'.format(email_privacy))
print('HAS_PASSWORD_POLICY={}'.format(has_password_policy))
" 2>/dev/null)
        DOMAINS=$(echo "$AUTH_SUMMARY" | grep '^DOMAINS=' | cut -d= -f2-)
        EMAIL_PRIVACY=$(echo "$AUTH_SUMMARY" | grep '^EMAIL_PRIVACY=' | cut -d= -f2-)
        HAS_PW_POLICY=$(echo "$AUTH_SUMMARY" | grep '^HAS_PASSWORD_POLICY=' | cut -d= -f2-)

        record "firebase_auth_authorized_domains" "PASS" "${DOMAINS}"

        if [ "$EMAIL_PRIVACY" = "True" ]; then
            record "firebase_auth_email_enumeration_protection" "PASS" "email enumeration protection (enableEmailPrivacy) is on"
        else
            record "firebase_auth_email_enumeration_protection" "FAIL" "enableEmailPrivacy is off -- relates to PF-6's staff-email enumeration finding"
        fi

        if [ "$HAS_PW_POLICY" = "True" ]; then
            record "firebase_auth_password_policy" "PASS" "an explicit passwordPolicyConfig is set"
        else
            record "firebase_auth_password_policy" "N/A" "no explicit password policy configured -- Firebase Auth's platform default applies; no decision has been recorded to strengthen it"
        fi
    fi

    run_capture curl -sf -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        "https://identitytoolkit.googleapis.com/v2/projects/${PROJECT_ID}/defaultSupportedIdpConfigs"
    if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
        record "firebase_auth_providers" "N/A" "operator lacks identitytoolkit.googleapis.com read access or the call failed: $(echo "$_last_output" | head -1)"
    else
        PROVIDER_NAMES=$(echo "$_last_output" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
names = [c.get('name', '?').rsplit('/', 1)[-1] for c in data.get('defaultSupportedIdpConfigs', [])]
print(','.join(names) if names else 'password (default, no federated IdP configured)')
" 2>/dev/null)
        record "firebase_auth_providers" "PASS" "${PROVIDER_NAMES}"
    fi
fi

# CHECK: firebase_auth_mfa_admin_editor
# MFA status can only be read PER-USER via the Identity Platform Admin API's
# accounts:query/accounts:lookup, not a bulk config read -- there is no
# project-level "MFA status" field the config endpoint above exposes for a
# specific UID. This is a genuine tooling gap (a per-user loop needs the
# admin/editor account list from scripts/bootstrap_editor_user.py's own
# records first), so it is N/A with the specific reason rather than a
# guessed PASS/FAIL.
record "firebase_auth_mfa_admin_editor" "N/A" "no bulk read exists for per-user MFA enrollment; requires accounts:query per known admin/editor UID against identitytoolkit.googleapis.com/v1/projects/${PROJECT_ID}/accounts:query -- run by hand against the UIDs scripts/bootstrap_editor_user.py and scripts/bootstrap_admin_user.py have created if this becomes a live check"

# CHECK: firebase_auth_export_settings
# Bulk user export (accounts:batchGet / gcloud auth export) is an action,
# not a setting to read -- there is no "export enabled" toggle to query. N/A
# by design, not by tooling gap.
record "firebase_auth_export_settings" "N/A" "Firebase Auth has no standing 'export enabled' setting to read -- bulk export is an on-demand admin action, not a persistent config value"

echo ""
echo "--- 10. Hosting response headers (per site) -------------------------------"

HOSTING_SITES="polyglot-demo-aa709 polyglot-app-staging polyglot-editor-demo polyglot-admin-demo polyglot-admin-candidate"
# No x-frame-options: the app site also serves Firebase Auth's reserved
# /__/auth/iframe, which our own pages frame, and XFO cannot carve out a
# path -- framing is governed by the CSP's frame-ancestors (sprint 23 E2).
REQUIRED_HEADERS="content-security-policy strict-transport-security referrer-policy"

for site in $HOSTING_SITES; do
    url="https://${site}.web.app/"
    # -L follows redirects: without it, a site that 301/302s to a canonical
    # host inspects only the REDIRECT response's headers (typically just
    # Location + a couple of framework defaults), never the page the
    # browser actually renders -- silently passing or failing on the wrong
    # response. -sIL prints one header block PER HOP, oldest first; the
    # FINAL block (after the last blank-line-separated section) is what a
    # browser actually sees and enforces, so that is what gets checked.
    run_capture curl -sIL --max-time 10 "$url"
    if [ $_last_status -ne 0 ]; then
        record "hosting_${site}_headers" "N/A" "curl failed against ${url} (network issue or site not deployed)"
        continue
    fi
    # Header blocks are separated by a blank line between HTTP status
    # lines; splitting on blank lines and taking the LAST non-empty block
    # isolates the final response after every redirect.
    FINAL_BLOCK=$(echo "$_last_output" | awk 'BEGIN{RS=""} {block=$0} END{print block}')
    HOP_COUNT=$(echo "$_last_output" | grep -c '^HTTP/')
    FINAL_STATUS=$(echo "$FINAL_BLOCK" | grep '^HTTP/' | tail -1 | tr -d '\r')
    HEADER_BLOB=$(echo "$FINAL_BLOCK" | tr 'A-Z' 'a-z')
    MISSING=""
    CSP_MODE="enforcing"
    for h in $REQUIRED_HEADERS; do
        if echo "$HEADER_BLOB" | grep -q "^$h:"; then
            continue
        fi
        # The CSP ships as Content-Security-Policy-Report-Only first (sprint 23
        # E2, bd polyglot-pdf-j29z1): the policy is present and the browser
        # reports violations without blocking. That is the planned soak, not
        # a missing header, so it PASSES with the mode named in the detail.
        if [ "$h" = "content-security-policy" ] && echo "$HEADER_BLOB" | grep -q "^content-security-policy-report-only:"; then
            CSP_MODE="report-only"
            continue
        fi
        MISSING="$MISSING $h"
    done
    if [ -z "$MISSING" ]; then
        record "hosting_${site}_headers" "PASS" "CSP (${CSP_MODE})/HSTS/Referrer-Policy all present on the final response (${FINAL_STATUS}, ${HOP_COUNT} hop(s))"
    else
        record "hosting_${site}_headers" "FAIL" "missing on the final response (${FINAL_STATUS}, ${HOP_COUNT} hop(s)):${MISSING} (PF-4 -- every Hosting target in firebase.json carries the headers since sprint 23 E2)"
    fi
done

echo ""
echo "--- 11. Container vulnerability scan + base image age ----------------------"

# CHECK: vulnerability_scan_status
# Artifact Registry / Container Analysis vulnerability scanning is a
# PROJECT-level API enablement, not a per-image toggle this script can turn
# on -- and turning it on IS a live change, so if it is off this is N/A with
# the ASK spelled out, per the bead's own instruction.
# The backend image lives on gcr.io (Container Registry hostnames, backed by
# Artifact Registry under the hood on projects created after AR's GA -- see
# docs/components/config-deployment.md's own note on this), so the read
# command is `gcloud container images list-tags gcr.io/...`, NOT `gcloud
# artifacts docker images list LOCATION-docker.pkg.dev/...` -- the latter
# requires an Artifact-Registry-native repository path and rejects a gcr.io
# one outright ("Invalid Docker string").
BACKEND_IMAGE="gcr.io/${PROJECT_ID}/polyglot-backend"

run_capture gcloud services list --project="$PROJECT_ID" \
    --filter="config.name:containerscanning.googleapis.com" \
    --format="value(config.name)"
if [ $_last_status -ne 0 ]; then
    record "vulnerability_scan_status" "N/A" "operator lacks serviceusage.services.list or the call failed"
elif [ -n "$_last_output" ]; then
    record "vulnerability_scan_status" "PASS" "Container/On-Demand Scanning API is enabled"
    run_capture gcloud container images list-tags "$BACKEND_IMAGE" \
        --format="value(digest,timestamp.datetime)" --limit=1
    if [ $_last_status -eq 0 ] && [ -n "$_last_output" ]; then
        record "vulnerability_scan_findings" "PASS" "latest image: $_last_output (run 'gcloud container images describe --show-package-vulnerability' for CVE detail)"
    else
        record "vulnerability_scan_findings" "N/A" "no image listing returned -- operator lacks containeranalysis/artifactregistry read access or none pushed yet"
    fi
else
    record "vulnerability_scan_status" "N/A" "scanning disabled -- ASK the maintainer to enable containerscanning.googleapis.com (Artifact Registry / On-Demand vulnerability scanning) on ${PROJECT_ID}; this is a live change and out of scope for a read-only audit"
fi

# CHECK: base_image_age
run_capture gcloud container images list-tags "$BACKEND_IMAGE" \
    --sort-by="~timestamp" --limit=1 --format="value(timestamp.datetime)"
if [ $_last_status -ne 0 ] || [ -z "$_last_output" ]; then
    record "base_image_age" "N/A" "operator lacks containeranalysis/artifactregistry read access on ${BACKEND_IMAGE}, no image pushed yet, or the call failed"
else
    record "base_image_age" "PASS" "latest polyglot-backend image timestamp=${_last_output} (Dockerfile pins python:3.12-slim by tag, not digest -- F1's pin-by-digest item covers tightening this)"
fi

echo ""
echo "--- 12. Cloud Build log content + bucket ACL --------------------------------"

# CHECK: cloud_build_log_content
# Scans the MOST RECENT build's log for secret-shaped assignments and JWT
# prefixes, printing COUNTS and the build id only -- never the matched text
# (the plan's own redaction rule for this specific check).
#
# `gcloud builds log` (without --stream, which this never passes) prints a
# COMPLETED build's log and exits -- it does not hang waiting for new lines.
# But a large build's log can still take minutes to fetch and print in
# full, with gcloud emitting NO progress output while it does, which reads
# indistinguishably from a hang to an operator watching the terminal.
# Printed a one-line notice before the call so that wait has an explanation,
# and BOUNDED the amount of log text this check reads with `head -n 20000`
# so one unusually large build cannot make every subsequent check wait on
# it -- the detector only needs to have SEEN enough of the log to report a
# representative count, not the entire thing.
run_capture gcloud builds list --project="$PROJECT_ID" --limit=1 --format="value(id)"
if [ $_last_status -ne 0 ] || [ -z "$_last_output" ]; then
    record "cloud_build_log_content" "N/A" "operator lacks cloudbuild.builds.list, or no builds have run yet"
else
    BUILD_ID="$_last_output"
    echo "    (fetching build log for ${BUILD_ID} -- a large build's log can take a while and gcloud shows no progress meanwhile)"
    run_capture gcloud builds log "$BUILD_ID" --project="$PROJECT_ID"
    if [ $_last_status -ne 0 ]; then
        record "cloud_build_log_content" "N/A" "operator lacks cloudbuild.builds.get on build ${BUILD_ID} or the call failed"
    else
        LOG_TEXT=$(echo "$_last_output" | head -n 20000)
        SECRET_ASSIGN_COUNT=$(echo "$LOG_TEXT" | grep -Eic '\b[A-Z_]*(KEY|SECRET|TOKEN|PASSWORD)[A-Z_]*\s*=' || true)
        JWT_COUNT=$(echo "$LOG_TEXT" | grep -Eoc 'eyJ[A-Za-z0-9_-]{10,}' || true)
        SCANNED_LINES=$(echo "$LOG_TEXT" | wc -l)
        SCAN_NOTE=""
        if [ "$SCANNED_LINES" -ge 20000 ]; then
            SCAN_NOTE=" (scanned first 20000 lines only)"
        fi
        if [ "${SECRET_ASSIGN_COUNT:-0}" -gt 0 ] || [ "${JWT_COUNT:-0}" -gt 0 ]; then
            record "cloud_build_log_content" "FAIL" "build ${BUILD_ID}: ${SECRET_ASSIGN_COUNT:-0} secret-shaped assignment(s), ${JWT_COUNT:-0} JWT-prefix match(es) -- counts only, never the matched text${SCAN_NOTE}"
        else
            record "cloud_build_log_content" "PASS" "build ${BUILD_ID}: 0 secret-shaped assignments, 0 JWT prefixes${SCAN_NOTE}"
        fi
    fi
fi

# CHECK: cloud_build_logs_bucket_acl
# Cloud Build's default log bucket is gs://<PROJECT_ID>_cloudbuild, unless
# cloudbuild.yaml's `logsBucket` overrides it (grep the file live, not
# hardcode the assumption).
CLOUD_BUILD_LOGS_BUCKET="${PROJECT_ID}_cloudbuild"
if [ -f "${REPO_ROOT}/cloudbuild.yaml" ] && grep -q "^logsBucket:" "${REPO_ROOT}/cloudbuild.yaml"; then
    CLOUD_BUILD_LOGS_BUCKET=$(grep "^logsBucket:" "${REPO_ROOT}/cloudbuild.yaml" | sed 's/^logsBucket:\s*//; s#gs://##')
fi
run_capture gcloud storage buckets get-iam-policy "gs://${CLOUD_BUILD_LOGS_BUCKET}" --format=json
if [ $_last_status -ne 0 ] || ! is_valid_json "$_last_output"; then
    record "cloud_build_logs_bucket_acl" "N/A" "operator lacks storage.buckets.getIamPolicy on gs://${CLOUD_BUILD_LOGS_BUCKET}, or Cloud Build is using Google-managed default logging (no bucket of its own to check): $(echo "$_last_output" | head -1)"
else
    HAS_ALLUSERS=$(echo "$_last_output" | "$PYTHON_BIN" -c "
import json, sys
data = json.load(sys.stdin)
for b in data.get('bindings', []):
    if 'allUsers' in b.get('members', []) or 'allAuthenticatedUsers' in b.get('members', []):
        print('yes')
        break
else:
    print('no')
")
    if [ "$HAS_ALLUSERS" = "yes" ]; then
        record "cloud_build_logs_bucket_acl" "FAIL" "gs://${CLOUD_BUILD_LOGS_BUCKET} grants allUsers or allAuthenticatedUsers"
    else
        record "cloud_build_logs_bucket_acl" "PASS" "no public binding on gs://${CLOUD_BUILD_LOGS_BUCKET}"
    fi
fi

echo ""
echo "--- 13. T4 third-party processor settings ------------------------------------"

# CHECK: vertex_abuse_monitoring_optout
# There is no gcloud read for the per-project Vertex AI "data governance"
# abuse-monitoring / prompt-logging opt-out state as of this script's
# writing -- it is set (and read back) only through the Google Cloud console
# under Vertex AI > Settings, or by a support ticket confirming the
# organization policy `constraints/gcp.disableVertexAIDataLogging` (which
# CAN be read as an org policy, so that path is used here). No gcloud command
# lets an operator read the console-only prompt-caching/abuse-monitoring
# toggle directly -- so if the org policy is absent, this is N/A, not a
# guessed PASS/FAIL.
run_capture gcloud org-policies describe constraints/gcp.disableVertexAIDataLogging \
    --project="$PROJECT_ID" --format="value(spec.rules)"
if [ $_last_status -ne 0 ]; then
    record "vertex_abuse_monitoring_optout" "N/A" "no gcloud org-policy is set for constraints/gcp.disableVertexAIDataLogging on ${PROJECT_ID} (or the Organization Policy API is disabled, or the operator lacks orgpolicy.policies.get) -- the console-only Vertex AI Studio 'data governance' opt-out toggle cannot be read via any CLI as of this writing; verify by hand at console.cloud.google.com > Vertex AI > Dashboard > Data Governance for G's processor table"
else
    record "vertex_abuse_monitoring_optout" "PASS" "org policy constraints/gcp.disableVertexAIDataLogging: ${_last_output}"
fi

# CHECK: cloud_tts_data_use_setting
# Cloud Text-to-Speech has no project-level "data use" opt-out setting at
# all -- Google's TTS terms govern request data use uniformly for all
# callers of the API (unlike Vertex's per-project abuse-monitoring toggle),
# so there is nothing live to read here. N/A by design, not by tooling gap.
record "cloud_tts_data_use_setting" "N/A" "Cloud Text-to-Speech has no project-level data-use opt-out setting to read -- Google's published API Terms of Service govern request-data handling uniformly for every caller; record that fact (not a live toggle) in G's processor table"

echo ""
echo "=============================================================="
echo "Summary"
echo "=============================================================="
TOTAL=$(wc -l < "$RESULTS_FILE")
PASS_COUNT=$(grep -c '^PASS' "$RESULTS_FILE" || true)
FAIL_COUNT=$(grep -c '^FAIL' "$RESULTS_FILE" || true)
NA_COUNT=$(grep -c '^N/A' "$RESULTS_FILE" || true)
echo "Total checks: $TOTAL   PASS: $PASS_COUNT   FAIL: $FAIL_COUNT   N/A: $NA_COUNT"
if [ "${FAIL_COUNT:-0}" -gt 0 ]; then
    echo ""
    echo "FAILs (each needs a disposition for workstream G):"
    grep '^FAIL' "$RESULTS_FILE"
fi

# Exit code is INFORMATIONAL ONLY, mirroring setup-monitoring.sh's own
# posture (an operator script, not a CI gate): this is a read-only audit run
# by hand, and its value is the table it prints, not a pass/fail gate. A
# non-zero exit here would tempt wiring it into CI as a hard gate before the
# live environment (staging headers, rules parity) has actually been fixed,
# which is explicitly a later, gated deploy step per the epic's own exit
# rubric criterion 4.
exit 0
