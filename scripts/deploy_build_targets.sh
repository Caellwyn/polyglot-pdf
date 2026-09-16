#!/bin/bash
# deploy_build_targets.sh -- run cloudbuild.yaml targets from a bash wrapper.
#
# WHY (bd polyglot-pdf-oqtm7, Epic 4 bead 4.6 of
# docs/sprint_22_admin-console_plan.md). Deploying used to be a local bash
# pipeline: docker build, gcloud run deploy, npm build, firebase deploy, all
# on the operator's laptop. Every one of those stages now lives in
# cloudbuild.yaml, selected by the _TARGET substitution, and each target has
# its own manual Cloud Build trigger named polyglot-<target>
# (scripts/setup-cloud-build.sh). The human path (these wrappers) and the
# console path (the admin service, bead 4.3) therefore drive ONE engine
# instead of two that drift -- and the gates that matter (the per-SHA verify
# record, the reachability check, the staging-before-demo promotion gate)
# live in the build, where no wrapper can skip them.
#
# This file is the whole bash side of that: start a trigger at a commit,
# stream its log, and fail the wrapper if the build failed.
#
# Usage, from a wrapper:
#   source "$SCRIPT_DIR/scripts/deploy_build_targets.sh"
#   SHA=$(deploy_build_sha "$SCRIPT_DIR")
#   run_build_targets "$SHA" backend-staging frontend-staging
#
# Every function returns non-zero on failure rather than exiting, so a caller
# running under `set -e` aborts at the first failed target and a caller that
# wants to react can test the status itself.

# The project and region every trigger was created in. --region is REQUIRED
# on `triggers run`: a 2nd-generation repository cannot live in global, so a
# run without it reports the trigger as simply not found
# (scripts/setup-cloud-build.sh's own closing note).
POLYGLOT_PROJECT_NAME="${POLYGLOT_PROJECT_NAME:-polyglot-demo-aa709}"
CLOUD_BUILD_REGION="${CLOUD_BUILD_REGION:-us-central1}"

# Resolve a python interpreter. python3 is not guaranteed on Windows Git
# Bash, and a python3 App-Execution-Alias stub can exist on PATH without
# being able to run -- so each candidate must actually EXECUTE, not merely
# resolve. Same contract (and the same env override, which the tests use) as
# deploy-all.sh's find_manifest_python.
deploy_build_python() {
    local cand
    for cand in ${MANIFEST_PYTHON_CANDIDATES:-python3 python py}; do
        if "$cand" -c "pass" >/dev/null 2>&1; then
            echo "$cand"
            return 0
        fi
    done
    return 1
}

# The commit being deployed. A build runs FROM GIT at an explicit commit, so
# this -- not the working tree -- is what ships; scripts/deploy_preflight.sh
# is what makes the two the same thing.
deploy_build_sha() {
    git -C "${1:-.}" rev-parse HEAD
}

# Has this commit's verify build already run and passed?
#
# Exit 0 = a build_checks/{sha} success record exists, so every deploy target
# for this SHA will pass its own gate step and re-running verify would pay for
# the same three suites twice. ANY other outcome -- no record, a failed
# record, an unreadable Firestore, no interpreter, no client library --
# returns non-zero, and the caller then runs verify. That direction is the
# safe one: a needless verify run costs minutes, while skipping a verify that
# never happened would leave every deploy target for the SHA failing its own
# gate anyway (record_build_check.py's `require` fails closed).
build_check_recorded() {
    local repo="$1" sha="$2" py
    py=$(deploy_build_python) || return 1
    "$py" "$repo/scripts/record_build_check.py" require \
        --sha "$sha" --project "$POLYGLOT_PROJECT_NAME" >/dev/null 2>&1
}

# Run ONE target's trigger at a commit, stream its log, and report its result.
#
# The build id comes back from `triggers run` itself (metadata.build.id)
# rather than from a follow-up list query: two wrappers running concurrently,
# or a console-triggered build for the same target, would make "the most
# recent build for this trigger" the wrong build.
#
# The STATUS is read from `builds describe` after the stream ends, not from
# the streaming command's own exit code: `gcloud builds log --stream` is a log
# reader, and treating "the log was read successfully" as "the build
# succeeded" is exactly the shape of failure this repo has paid for before --
# a green-looking deploy that deployed nothing.
run_build_target() {
    local target="$1" sha="$2"
    local trigger="polyglot-$target"
    local build_id status

    echo "[INFO] Cloud Build: $trigger at $sha"
    build_id=$(gcloud builds triggers run "$trigger" \
        --sha="$sha" \
        --region="$CLOUD_BUILD_REGION" \
        --project="$POLYGLOT_PROJECT_NAME" \
        --substitutions="_SHA=$sha" \
        --format='value(metadata.build.id)')

    if [ -z "$build_id" ]; then
        echo "[ERROR] Could not start trigger $trigger for $sha." >&2
        echo "[ERROR] Check that the trigger exists in region $CLOUD_BUILD_REGION:" >&2
        echo "[ERROR]   gcloud builds triggers list --region=$CLOUD_BUILD_REGION --project=$POLYGLOT_PROJECT_NAME" >&2
        echo "[ERROR] scripts/setup-cloud-build.sh creates one per target." >&2
        return 1
    fi

    echo "[INFO] Build $build_id started; streaming its log..."
    gcloud builds log "$build_id" --stream \
        --region="$CLOUD_BUILD_REGION" \
        --project="$POLYGLOT_PROJECT_NAME" || true

    status=$(gcloud builds describe "$build_id" \
        --region="$CLOUD_BUILD_REGION" \
        --project="$POLYGLOT_PROJECT_NAME" \
        --format='value(status)')

    if [ "$status" != "SUCCESS" ]; then
        echo "[ERROR] Target $target FAILED: build $build_id ended ${status:-UNKNOWN}." >&2
        echo "[ERROR] Full log:" >&2
        echo "[ERROR]   gcloud builds log $build_id --region=$CLOUD_BUILD_REGION --project=$POLYGLOT_PROJECT_NAME" >&2
        return 1
    fi

    echo "[INFO] Target $target succeeded (build $build_id)."
    return 0
}

# Run several targets IN ORDER, stopping at the first failure.
#
# Stopping matters: the demo family deploys the backend before the frontend,
# and a frontend built against a backend whose deploy failed is worse than no
# deploy at all.
run_build_targets() {
    local sha="$1"
    shift
    local target
    for target in "$@"; do
        run_build_target "$target" "$sha" || return 1
    done
    return 0
}
