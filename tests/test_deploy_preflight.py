"""scripts/deploy_preflight.sh must refuse a dirty or unpushed tree.

bd polyglot-pdf-1s3ko (Epic 4 of docs/sprint_22_admin-console_plan.md). Every
Cloud Build build runs FROM GIT at an explicit commit, and the build_checks
record vouches for that commit's test run. Both claims are false the moment
the operator's tree does not match the commit they are about to name:

  DIRTY -- a tarball build uploads the LOCAL tree while git rev-parse HEAD
  names a clean commit, so uncommitted code deploys under a SHA the verify
  gate vouched for. The record is not wrong about the commit; it is simply
  about a different tree than the one that shipped.

  UNPUSHED -- a build from the connected GitHub repository can only fetch a
  commit the remote has. Worse, a SHA that exists only on one laptop can never
  be reproduced by the admin console, which triggers builds by SHA.

RUN, NOT READ. These tests EXECUTE the helper under bash against real
temporary git repositories, because the failure mode being guarded is
behavioural. A test that only grepped the script for a git status invocation
would pass with the exit code inverted -- and this repo has paid for exactly
that shape before (a substring guard surviving a whole route revert).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO_ROOT / "scripts" / "deploy_preflight.sh"
WRAPPERS = (REPO_ROOT / "deploy-staging.sh", REPO_ROOT / "deploy-demo.sh")

# shutil.which, never a bare "bash": on Windows a bare name resolves to WSL's
# bash, which cannot see the Git-Bash filesystem (mirrors
# tests/test_deploy_reachability_gate.py).
BASH = shutil.which("bash")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(
    BASH is None or GIT is None, reason="bash and git must both be on PATH"
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [GIT, "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _run_preflight(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, str(PREFLIGHT), str(repo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture
def clean_pushed_repo(tmp_path: Path) -> Path:
    """A real repo with one commit, pushed to a real (bare) remote.

    A bare local remote rather than a fake: the branch -r --contains query is
    the behaviour under test, and it only tells the truth about
    remote-tracking refs that a real push and fetch created.
    """
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run([GIT, "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(
        [GIT, "clone", "-q", str(remote), str(work)],
        check=True,
        capture_output=True,
    )
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test")
    (work / "a.txt").write_text("one\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "initial")
    _git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    _git(work, "fetch", "-q", "origin")
    return work


def test_a_clean_pushed_tree_passes(clean_pushed_repo):
    """The baseline. Without this the refusals could be unconditional.

    A preflight that refused EVERYTHING would satisfy both failure tests below
    while making every deploy impossible, so the passing case is the guard on
    the guards.
    """
    result = _run_preflight(clean_pushed_repo)
    assert result.returncode == 0, (
        f"a clean, pushed tree was refused:\n{result.stdout}\n{result.stderr}"
    )


def test_a_modified_tracked_file_is_refused(clean_pushed_repo):
    """The dirty case that actually happens: an edit you forgot to commit."""
    (clean_pushed_repo / "a.txt").write_text("edited\n", encoding="utf-8")
    result = _run_preflight(clean_pushed_repo)
    assert result.returncode == 1, (
        f"a dirty tree was allowed to deploy:\n{result.stdout}"
    )
    assert "not clean" in result.stderr


def test_an_untracked_file_is_refused(clean_pushed_repo):
    """Untracked counts too.

    A tarball build uploads untracked files (subject to .gcloudignore) while
    the commit does not contain them -- so a porcelain check narrowed to
    tracked changes would miss a whole class of tree/commit mismatch.
    """
    (clean_pushed_repo / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    result = _run_preflight(clean_pushed_repo)
    assert result.returncode == 1, (
        f"an untracked file was allowed to deploy:\n{result.stdout}"
    )
    assert "not clean" in result.stderr


def test_a_staged_but_uncommitted_change_is_refused(clean_pushed_repo):
    """Staged is still uncommitted -- the commit does not contain it."""
    (clean_pushed_repo / "b.txt").write_text("two\n", encoding="utf-8")
    _git(clean_pushed_repo, "add", "-A")
    result = _run_preflight(clean_pushed_repo)
    assert result.returncode == 1
    assert "not clean" in result.stderr


def test_a_clean_but_unpushed_commit_is_refused(clean_pushed_repo):
    """The case a dirty-tree check alone cannot see.

    The tree is spotless and git status is empty; the commit simply does not
    exist on the remote. Cloud Build cannot fetch it, and the admin console
    could never reproduce the deploy.
    """
    (clean_pushed_repo / "c.txt").write_text("three\n", encoding="utf-8")
    _git(clean_pushed_repo, "add", "-A")
    _git(clean_pushed_repo, "commit", "-qm", "unpushed work")

    assert _git(clean_pushed_repo, "status", "--porcelain") == "", (
        "the fixture is not exercising the unpushed case: the tree is dirty, "
        "so the dirty branch would refuse it for the wrong reason"
    )

    result = _run_preflight(clean_pushed_repo)
    assert result.returncode == 1, (
        f"an unpushed commit was allowed to deploy:\n{result.stdout}"
    )
    assert "not on any remote branch" in result.stderr


def test_pushing_that_commit_makes_it_pass(clean_pushed_repo):
    """The refusal must be about the REMOTE, not about having two commits.

    Without this, a preflight that refused any repo with more than one commit
    would pass the test above for entirely the wrong reason.
    """
    (clean_pushed_repo / "c.txt").write_text("three\n", encoding="utf-8")
    _git(clean_pushed_repo, "add", "-A")
    _git(clean_pushed_repo, "commit", "-qm", "work")
    assert _run_preflight(clean_pushed_repo).returncode == 1

    _git(clean_pushed_repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    _git(clean_pushed_repo, "fetch", "-q", "origin")

    result = _run_preflight(clean_pushed_repo)
    assert result.returncode == 0, (
        f"the same commit was still refused after pushing:\n{result.stderr}"
    )


def test_a_commit_on_a_pushed_feature_branch_passes(clean_pushed_repo):
    """Deployable does not mean merged.

    An ancestor test against one branch would refuse a perfectly deployable
    commit on a pushed feature branch -- which is the normal shape of a
    staging deploy. The question is whether the REMOTE has the commit, so the
    check asks which remote branches contain it.
    """
    _git(clean_pushed_repo, "checkout", "-qb", "feature/x")
    (clean_pushed_repo / "d.txt").write_text("four\n", encoding="utf-8")
    _git(clean_pushed_repo, "add", "-A")
    _git(clean_pushed_repo, "commit", "-qm", "feature work")
    _git(clean_pushed_repo, "push", "-q", "origin", "HEAD:refs/heads/feature/x")
    _git(clean_pushed_repo, "fetch", "-q", "origin")

    result = _run_preflight(clean_pushed_repo)
    assert result.returncode == 0, (
        "a commit on a PUSHED feature branch was refused; the check must ask "
        f"whether the remote has it, not whether dev does:\n{result.stderr}"
    )


def test_a_non_git_directory_is_refused(tmp_path: Path):
    """Fail closed on the case the check cannot evaluate."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    result = _run_preflight(plain)
    assert result.returncode == 1
    assert "not a git repository" in result.stderr


def test_the_refusal_names_the_remedy(clean_pushed_repo):
    """The message is read in a terminal by someone mid-deploy.

    A bare non-zero exit sends the operator to read the script. Both refusals
    must say what to do about it.
    """
    (clean_pushed_repo / "a.txt").write_text("edited\n", encoding="utf-8")
    dirty = _run_preflight(clean_pushed_repo).stderr
    assert "Commit" in dirty and "redeploy" in dirty
    # ...and the offending paths, so the operator need not go looking.
    assert "a.txt" in dirty

    _git(clean_pushed_repo, "checkout", "--", "a.txt")
    (clean_pushed_repo / "c.txt").write_text("three\n", encoding="utf-8")
    _git(clean_pushed_repo, "add", "-A")
    _git(clean_pushed_repo, "commit", "-qm", "unpushed")
    unpushed = _run_preflight(clean_pushed_repo).stderr
    assert "git push" in unpushed
    # Stale remote refs produce this SAME message, so the remedy has to name
    # the fetch too -- otherwise an operator whose branch IS pushed pushes
    # again and again.
    assert "git fetch origin" in unpushed


# ---------------------------------------------------------------------------
# THE WIRING: a helper no wrapper calls protects nothing.
# ---------------------------------------------------------------------------


def _live_lines(script: Path) -> list[str]:
    out = []
    for raw in script.read_text(encoding="utf-8").splitlines():
        code: list[str] = []
        quote = None
        for ch in raw:
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#":
                break
            code.append(ch)
        out.append("".join(code))
    return out


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=lambda p: p.name)
def test_each_wrapper_sources_and_calls_the_preflight(wrapper: Path):
    """Sourcing without calling is the classic half-wiring.

    The function would be defined and never run, so every deploy would proceed
    exactly as it did before the check existed -- with the script on disk
    looking like protection.
    """
    lines = _live_lines(wrapper)
    joined = "\n".join(lines)
    assert "scripts/deploy_preflight.sh" in joined, (
        f"{wrapper.name} never sources the preflight helper"
    )
    assert any(
        line.strip().startswith("deploy_preflight ") for line in lines
    ), (
        f"{wrapper.name} sources the preflight helper but never CALLS "
        "deploy_preflight, so nothing is ever checked"
    )


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=lambda p: p.name)
def test_the_preflight_runs_before_any_deploy_work(wrapper: Path):
    """Position is the whole protection.

    A preflight called after the gcloud invocation refuses a deploy that has
    already happened. It must precede every command that touches the cloud.
    """
    lines = _live_lines(wrapper)
    call = next(
        i for i, line in enumerate(lines)
        if line.strip().startswith("deploy_preflight ")
    )
    acting = [
        i for i, line in enumerate(lines)
        if "gcloud " in line or "firebase " in line or "./deploy-all.sh" in line
    ]
    assert acting, (
        f"no cloud-touching command found in {wrapper.name}, so this guard "
        "would pass vacuously"
    )
    assert call < min(acting), (
        f"{wrapper.name} calls deploy_preflight at line {call + 1}, after its "
        f"first cloud command at line {min(acting) + 1}"
    )


def test_the_helper_does_not_swallow_its_own_failure():
    """The wrappers run under set -e, so the refusal must abort them.

    A return 1 from a sourced function under set -e aborts the caller. If the
    helper ever swallowed its own failure, the wrapper would print the refusal
    and deploy anyway.
    """
    text = PREFLIGHT.read_text(encoding="utf-8")
    body = text[text.index("deploy_preflight() {"):]
    assert "|| true" not in body, (
        "deploy_preflight swallows a failure, so a refusal would not abort "
        "the calling wrapper"
    )
