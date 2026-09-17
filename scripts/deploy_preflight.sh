#!/bin/bash
# deploy_preflight.sh -- refuse to deploy a tree that is dirty or unpushed.
#
# WHY (bd polyglot-pdf-1s3ko, sprint-22 plan Epic 4 "Cloud Build layout").
# Every Cloud Build build runs FROM GIT at an explicit commit, and the verify
# gate vouches for a SHA: build_checks/{sha} says "this commit's suites
# passed". Both claims are false the moment the operator's tree does not match
# the commit they are about to name.
#
#   DIRTY TRACKED STATE -- a modified-or-staged tracked file means the commit
#   named to the build differs from the tree the operator is looking at, so
#   the commit deployed is not the one they meant to ship.
#
#   UNPUSHED COMMIT -- `gcloud builds triggers run --sha=<sha>` fetches that
#   commit from the connected GitHub repository, which can only ever have a
#   commit the remote actually has. An unpushed SHA fails the build late and
#   opaquely ("revision not found"), and worse, a LOCAL SHA that exists only
#   here can never be reproduced by the admin console, which triggers builds
#   by SHA against the same repository.
#
# Both failures are silent-ish and land minutes into a deploy, so they are
# checked here, first, before anything else in the wrapper runs.
#
# UNTRACKED FILES DO NOT COUNT (bd polyglot-pdf-wobtv). Earlier this also
# refused on any untracked file, on the theory that a local tarball build
# would upload it. That stopped being true when deploy moved onto Cloud Build
# triggers (bd polyglot-pdf-oqtm7): the build fetches ONLY the named commit
# from GitHub, so a file git never committed cannot reach it under any
# circumstances -- there is no tree/commit mismatch for the build to inherit.
# Enforcing it anyway made every real deploy attempt fail: three
# `.firebase/*.cache` files were tracked (untracked now, bd polyglot-pdf-wobtv)
# so every Hosting deploy dirtied the tree, and scratch files other sessions
# leave at the repo root (`Claude outputs/`, `*.bak.py`, `prep-*.txt`) piled on
# top. The check below still lists untracked paths as a NOTE -- an operator
# mid-deploy should still see what is lying around uncommitted -- it just does
# not refuse over them.
#
# Usage, from a wrapper:   source scripts/deploy_preflight.sh && deploy_preflight
# Usage, standalone:       bash scripts/deploy_preflight.sh [repo-dir]
#
# Exit 0 = tracked state clean and pushed (untracked files noted, not fatal).
# Exit 1 = refused, with the reason on stderr.

deploy_preflight() {
    local repo="${1:-.}" dirty untracked head remote_branches

    if ! git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
        echo "[ERROR] deploy preflight: $repo is not a git repository." >&2
        return 1
    fi

    # 1. DIRTY TRACKED STATE. --untracked-files=no limits --porcelain to
    # staged and unstaged changes to TRACKED paths -- exactly the set that
    # would make the deployed commit differ from what is on the operator's
    # screen. Untracked files are handled separately below: they never reach
    # a Cloud Build trigger run (it fetches only the named commit from
    # GitHub), so they are surfaced as a NOTE, not a refusal.
    dirty=$(git -C "$repo" status --porcelain --untracked-files=no)
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

    # Untracked files are noted, never fatal (bd polyglot-pdf-wobtv): the
    # commit named to the build does not contain them either way, so their
    # presence cannot make the build ship something the operator did not see.
    untracked=$(git -C "$repo" ls-files --others --exclude-standard)
    if [ -n "$untracked" ]; then
        echo "[NOTE] Untracked files present (not part of the deployed commit," >&2
        echo "[NOTE] so they do not block this deploy -- shown for awareness):" >&2
        echo "$untracked" | sed 's/^/[NOTE]   /' >&2
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
