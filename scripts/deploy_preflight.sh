#!/bin/bash
# deploy_preflight.sh -- refuse to deploy a tree that is dirty or unpushed.
#
# WHY (bd polyglot-pdf-1s3ko, sprint-22 plan Epic 4 "Cloud Build layout").
# Every Cloud Build build runs FROM GIT at an explicit commit, and the verify
# gate vouches for a SHA: build_checks/{sha} says "this commit's suites
# passed". Both claims are false the moment the operator's tree does not match
# the commit they are about to name.
#
#   DIRTY TREE -- `gcloud builds submit` uploads the LOCAL tree while
#   `git rev-parse HEAD` names a clean commit, so uncommitted code deploys
#   under a SHA that build_checks vouches for. The record is not wrong about
#   the commit; it is simply about a different tree than the one that shipped.
#
#   UNPUSHED COMMIT -- a build from the connected GitHub repository can only
#   fetch a commit the remote actually has. An unpushed SHA fails the build
#   late and opaquely ("revision not found"), and worse, a LOCAL SHA that
#   exists only here can never be reproduced by the admin console, which
#   triggers builds by SHA against the same repository.
#
# Both failures are silent-ish and land minutes into a deploy, so they are
# checked here, first, before anything else in the wrapper runs.
#
# Usage, from a wrapper:   source scripts/deploy_preflight.sh && deploy_preflight
# Usage, standalone:       bash scripts/deploy_preflight.sh [repo-dir]
#
# Exit 0 = clean and pushed. Exit 1 = refused, with the reason on stderr.

deploy_preflight() {
    local repo="${1:-.}" dirty head remote_branches

    if ! git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
        echo "[ERROR] deploy preflight: $repo is not a git repository." >&2
        return 1
    fi

    # 1. DIRTY TREE. --porcelain covers staged, unstaged and untracked; an
    # untracked file counts because `gcloud builds submit` uploads it (subject
    # to .gcloudignore) while the commit does not contain it.
    dirty=$(git -C "$repo" status --porcelain)
    if [ -n "$dirty" ]; then
        echo "[ERROR] ===========================================================" >&2
        echo "[ERROR]   DEPLOY REFUSED: the working tree is not clean" >&2
        echo "[ERROR] ===========================================================" >&2
        echo "[ERROR] A build runs from a COMMIT, and build_checks/{sha} vouches" >&2
        echo "[ERROR] for that commit's test run. Deploying a dirty tree ships" >&2
        echo "[ERROR] code no verify build ever saw, under a SHA that says it did." >&2
        echo "[ERROR]" >&2
        echo "[ERROR] Uncommitted changes:" >&2
        echo "$dirty" | sed 's/^/[ERROR]   /' >&2
        echo "[ERROR]" >&2
        echo "[ERROR] Commit (or stash) them, push, then redeploy." >&2
        return 1
    fi

    head=$(git -C "$repo" rev-parse HEAD 2>/dev/null)
    if [ -z "$head" ]; then
        echo "[ERROR] deploy preflight: could not resolve HEAD in $repo." >&2
        return 1
    fi

    # 2. UNPUSHED COMMIT. The question is whether the REMOTE has this commit,
    # not whether some local branch does -- so ask which remote-tracking
    # branches contain it. `--contains` is the right test rather than
    # `merge-base --is-ancestor origin/dev HEAD`: a commit on a pushed feature
    # branch is perfectly deployable without having reached dev yet, and an
    # ancestor test against one branch would refuse it.
    remote_branches=$(git -C "$repo" branch -r --contains "$head" 2>/dev/null)
    if [ -z "$remote_branches" ]; then
        echo "[ERROR] ===========================================================" >&2
        echo "[ERROR]   DEPLOY REFUSED: HEAD is not on any remote branch" >&2
        echo "[ERROR] ===========================================================" >&2
        echo "[ERROR] Commit $head exists only in this checkout." >&2
        echo "[ERROR] Cloud Build builds from the connected GitHub repository, so" >&2
        echo "[ERROR] it cannot fetch this SHA -- and the admin console, which" >&2
        echo "[ERROR] triggers builds by SHA against that same repository, could" >&2
        echo "[ERROR] never reproduce this deploy." >&2
        echo "[ERROR]" >&2
        echo "[ERROR] Push the branch, then redeploy:" >&2
        echo "[ERROR]   git push" >&2
        echo "[ERROR]" >&2
        echo "[ERROR] (If the branch IS pushed, your remote refs are stale:" >&2
        echo "[ERROR]  run 'git fetch origin' and try again.)" >&2
        return 1
    fi

    echo "[INFO] Deploy preflight OK: clean tree at $head, present on the remote."
    return 0
}

# Executed directly (not sourced) -> run the check and exit with its status.
# ${BASH_SOURCE[0]} != $0 exactly when this file was sourced.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    deploy_preflight "$@"
    exit $?
fi
