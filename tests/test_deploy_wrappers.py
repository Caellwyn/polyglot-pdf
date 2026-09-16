"""The deploy-*.sh wrappers are thin Cloud Build triggers, nothing more.

bd polyglot-pdf-oqtm7 (Epic 4 bead 4.6 of docs/sprint_22_admin-console_plan.md).

WHY THIS EXISTS. Deploying used to be a local bash pipeline -- docker build,
gcloud run deploy, npm build, firebase deploy -- run from an operator's
laptop. Every stage moved into cloudbuild.yaml, one target apiece, so the
human path (these wrappers) and the console path (the admin service) drive ONE
engine. That matters because the GATES live in the build: the per-SHA verify
record, the reachability check, the manifest validation and the
staging-before-demo promotion gate all run as build steps, and a wrapper that
still deployed anything itself would be a route around every one of them.

TWO PROPERTIES, PINNED SEPARATELY.

  1. BEHAVIOUR -- each wrapper starts the right triggers, in the right order,
     at the CURRENT commit, and stops at the first failed build. Driven by
     EXECUTING the real scripts under bash against a stubbed `gcloud` in a
     real (clean, pushed) temporary git repo, because the failure mode is
     behavioural: a text assertion cannot tell you that a failed first build
     actually prevents the second, only that both names appear in the file.

  2. THE ENGINE IS GONE -- no wrapper contains `gcloud run deploy`, `firebase
     deploy` or `gcloud builds submit --tag`, and none carries a bash copy of
     the reachability gate. Pinned as a SET over every wrapper (CLAUDE.md scar
     #8), so re-introducing the inline engine in ANY of them fails here rather
     than one review round per script.

ASCII only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# shutil.which, never a bare "bash": on Windows a bare name resolves to WSL's
# bash, which cannot see the Git-Bash filesystem and fails every script with a
# relay error that reads like a syntax error (mirrors
# tests/test_deploy_preflight.py).
BASH = shutil.which("bash")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(
    BASH is None or GIT is None, reason="bash and git must both be on PATH"
)

# Every wrapper this bead made thin. The root scripts plus the one a directory
# down -- deploy-production.sh is excluded because it is DEAD and refuses to
# run (pinned by backend/tests/unit/test_deploy_channel_isolation.py).
WRAPPERS = (
    "deploy-all.sh",
    "deploy-staging.sh",
    "deploy-demo.sh",
    "deploy-editor.sh",
    "deploy-admin.sh",
    "deploy-admin-console.sh",
    "backend/deploy-new.sh",
)

# The three shapes of "this script deploys something itself". Each existed in
# exactly one place before this bead: `gcloud run deploy` in deploy-all.sh and
# backend/deploy-new.sh, `firebase deploy` in deploy-all.sh, deploy-demo.sh,
# deploy-editor.sh and deploy-admin-console.sh, and `gcloud builds submit
# --tag` (the tarball image build) in deploy-all.sh and backend/deploy-new.sh.
INLINE_ENGINE_IDIOMS = (
    "gcloud run deploy",
    "firebase deploy",
    "gcloud builds submit --tag",
)

SUPPORT_FILES = (
    "scripts/deploy_preflight.sh",
    "scripts/deploy_build_targets.sh",
    "scripts/record_build_check.py",
)

# A `gcloud` that records every invocation and answers the four calls the
# wrappers make. Kept minimal on purpose: the point is to observe which
# triggers ran, in what order, with what SHA.
GCLOUD_STUB = """#!/bin/bash
printf '%s\\n' "$*" >> "$GCLOUD_LOG"
if [ "$1 $2" = "config get-value" ]; then
    echo "tester@gmail.com"
    exit 0
fi
if [ "$1 $2 $3" = "builds triggers run" ]; then
    echo "build-$4"
    exit 0
fi
if [ "$1 $2" = "builds describe" ]; then
    if [ "$3" = "build-${GCLOUD_FAIL_TRIGGER:-__no_such_trigger__}" ]; then
        echo "FAILURE"
    else
        echo "SUCCESS"
    fi
    exit 0
fi
exit 0
"""

# A stand-in interpreter for the build_checks probe. `-c pass` must succeed
# (that is deploy_build_python's "can this candidate actually run?" check);
# anything else is the `record_build_check.py require` call, whose EXIT STATUS
# is the only thing the wrapper consumes.
PYTHON_STUB = """#!/bin/bash
if [ "$1" = "-c" ]; then exit 0; fi
exit ${BUILD_CHECK_EXIT:-1}
"""


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


@pytest.fixture
def deploy_repo(tmp_path: Path) -> Path:
    """A clean, pushed temporary repo carrying the real wrapper scripts.

    Clean and pushed because scripts/deploy_preflight.sh refuses anything else
    -- and that refusal is itself part of the wrapper contract, so it runs for
    real here rather than being stubbed out.
    """
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run([GIT, "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(
        [GIT, "clone", "-q", str(remote), str(work)], check=True, capture_output=True
    )
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test")

    for rel in (*WRAPPERS, *SUPPORT_FILES):
        dest = work / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, dest)

    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "wrappers")
    _git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    _git(work, "fetch", "-q", "origin")
    return work


@pytest.fixture
def stub_bin(tmp_path: Path) -> Path:
    """A PATH directory holding the gcloud and python stubs."""
    binned = tmp_path / "bin"
    binned.mkdir()
    for name, body in (("gcloud", GCLOUD_STUB), ("stubpy", PYTHON_STUB)):
        path = binned / name
        path.write_text(body, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    return binned


def _run(
    repo: Path,
    stub_bin: Path,
    script: str,
    *args: str,
    build_check_exit: str = "1",
    fail_trigger: str = "",
) -> tuple[subprocess.CompletedProcess, list[str], str]:
    """Run a wrapper; return (process, gcloud invocations, HEAD sha)."""
    log = repo.parent / "gcloud.log"
    log.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = str(stub_bin) + os.pathsep + env["PATH"]
    env["GCLOUD_LOG"] = str(log)
    env["MANIFEST_PYTHON_CANDIDATES"] = "stubpy"
    env["BUILD_CHECK_EXIT"] = build_check_exit
    env["GCLOUD_FAIL_TRIGGER"] = fail_trigger
    proc = subprocess.run(
        [BASH, str(repo / script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(repo),
    )
    calls = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return proc, calls, _git(repo, "rev-parse", "HEAD")


def _triggers(calls: list[str]) -> list[str]:
    """The trigger names run, in order."""
    out = []
    for call in calls:
        if call.startswith("builds triggers run "):
            out.append(call.split()[3])
    return out


# ---------------------------------------------------------------------------
# 1. Each wrapper runs its own trigger sequence, in order.
# ---------------------------------------------------------------------------

# (script, argv, expected trigger names in order). The build_checks record is
# present for every case here (build_check_exit="0"), so the verify target is
# absent from all of them -- its own two cases are separate, below.
SEQUENCES = [
    ("deploy-staging.sh", (), ["polyglot-backend-staging", "polyglot-frontend-staging"]),
    ("deploy-staging.sh", ("--backend",), ["polyglot-backend-staging"]),
    ("deploy-staging.sh", ("--frontend",), ["polyglot-frontend-staging"]),
    ("deploy-staging.sh", ("--form-kits",), ["polyglot-form-kits"]),
    (
        "deploy-staging.sh",
        ("--all",),
        [
            "polyglot-backend-staging",
            "polyglot-form-kits",
            "polyglot-frontend-staging",
        ],
    ),
    (
        "deploy-demo.sh",
        (),
        [
            "polyglot-backend-demo",
            "polyglot-form-kits",
            "polyglot-firestore-rules",
            "polyglot-frontend-demo",
        ],
    ),
    ("deploy-demo.sh", ("--backend",), ["polyglot-backend-demo"]),
    (
        "deploy-demo.sh",
        ("--frontend",),
        ["polyglot-firestore-rules", "polyglot-frontend-demo"],
    ),
    ("deploy-demo.sh", ("--form-kits",), ["polyglot-form-kits"]),
    ("deploy-editor.sh", (), ["polyglot-editor"]),
    ("deploy-admin.sh", (), ["polyglot-admin-service"]),
    ("deploy-admin-console.sh", (), ["polyglot-admin-console-candidate"]),
    ("deploy-admin-console.sh", ("--live",), ["polyglot-admin-console"]),
    ("backend/deploy-new.sh", (), ["polyglot-backend-demo"]),
    (
        "backend/deploy-new.sh",
        ("polyglot-backend-staging",),
        ["polyglot-backend-staging"],
    ),
    ("backend/deploy-new.sh", ("polyglot-admin",), ["polyglot-admin-service"]),
]


@pytest.mark.parametrize(
    "script,argv,expected",
    SEQUENCES,
    ids=[f"{s}{' ' + ' '.join(a) if a else ''}" for s, a, _ in SEQUENCES],
)
def test_wrapper_runs_its_trigger_sequence(
    deploy_repo, stub_bin, script, argv, expected
):
    proc, calls, _sha = _run(
        deploy_repo, stub_bin, script, *argv, build_check_exit="0"
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _triggers(calls) == expected, (
        f"{script} {' '.join(argv)} ran {_triggers(calls)}; the targets it used "
        f"to perform inline are {expected}"
    )


@pytest.mark.parametrize(
    "script,argv,expected",
    SEQUENCES,
    ids=[f"{s}{' ' + ' '.join(a) if a else ''}" for s, a, _ in SEQUENCES],
)
def test_every_trigger_run_names_the_current_commit(
    deploy_repo, stub_bin, script, argv, expected
):
    """--sha AND _SHA, both the tree's HEAD.

    A build runs from a COMMIT: --sha tells the trigger which revision of the
    connected repository to fetch, and the _SHA substitution is what the
    verify gate writes and every deploy target reads. A wrapper that passed
    one without the other would deploy one commit while vouching for another.
    """
    _proc, calls, sha = _run(
        deploy_repo, stub_bin, script, *argv, build_check_exit="0"
    )
    runs = [c for c in calls if c.startswith("builds triggers run ")]
    assert len(runs) == len(expected)
    for call in runs:
        assert f"--sha={sha}" in call, call
        assert f"--substitutions=_SHA={sha}" in call, call


# ---------------------------------------------------------------------------
# 2. verify runs once per commit, and only when the record is missing.
# ---------------------------------------------------------------------------


def test_staging_runs_verify_first_when_the_commit_has_no_build_checks_record(
    deploy_repo, stub_bin
):
    proc, calls, _sha = _run(
        deploy_repo, stub_bin, "deploy-staging.sh", build_check_exit="1"
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _triggers(calls) == [
        "polyglot-verify",
        "polyglot-backend-staging",
        "polyglot-frontend-staging",
    ]


def test_staging_skips_verify_when_the_commit_is_already_recorded(
    deploy_repo, stub_bin
):
    """Five targets for one commit pay for ONE test run, not five."""
    _proc, calls, _sha = _run(
        deploy_repo, stub_bin, "deploy-staging.sh", build_check_exit="0"
    )
    assert "polyglot-verify" not in _triggers(calls)


# ---------------------------------------------------------------------------
# 3. A failed build stops the sequence.
# ---------------------------------------------------------------------------


def test_a_failed_build_stops_the_remaining_targets(deploy_repo, stub_bin):
    """The demo family deploys the backend before the frontend; a frontend
    built against a backend whose deploy failed is worse than no deploy."""
    proc, calls, _sha = _run(
        deploy_repo,
        stub_bin,
        "deploy-demo.sh",
        build_check_exit="0",
        fail_trigger="polyglot-backend-demo",
    )
    assert proc.returncode != 0, "a failed build must fail the wrapper"
    assert _triggers(calls) == ["polyglot-backend-demo"], (
        "targets after the failed one still ran"
    )


def test_a_failed_build_names_the_target_and_the_build(deploy_repo, stub_bin):
    proc, _calls, _sha = _run(
        deploy_repo,
        stub_bin,
        "deploy-demo.sh",
        build_check_exit="0",
        fail_trigger="polyglot-backend-demo",
    )
    combined = proc.stdout + proc.stderr
    assert "backend-demo" in combined
    assert "FAILURE" in combined


def test_a_middle_failure_stops_the_rest(deploy_repo, stub_bin):
    """Not just the first target: the stop is per-target, not a special case
    for the head of the list."""
    proc, calls, _sha = _run(
        deploy_repo,
        stub_bin,
        "deploy-demo.sh",
        build_check_exit="0",
        fail_trigger="polyglot-form-kits",
    )
    assert proc.returncode != 0
    assert _triggers(calls) == ["polyglot-backend-demo", "polyglot-form-kits"]


def test_a_trigger_that_cannot_start_fails_the_wrapper(deploy_repo, stub_bin, tmp_path):
    """An empty build id means the trigger does not exist (or gcloud failed):
    the wrapper must refuse rather than report a green deploy of nothing."""
    (stub_bin / "gcloud").write_text(
        GCLOUD_STUB.replace('echo "build-$4"', 'echo ""'),
        encoding="utf-8",
        newline="\n",
    )
    proc, _calls, _sha = _run(
        deploy_repo, stub_bin, "deploy-editor.sh", build_check_exit="0"
    )
    assert proc.returncode != 0
    assert "Could not start trigger" in proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# 4. The wrappers still refuse what they always refused.
# ---------------------------------------------------------------------------

UNKNOWN_ARG_SCRIPTS = [
    "deploy-staging.sh",
    "deploy-demo.sh",
    "deploy-admin-console.sh",
]


@pytest.mark.parametrize("script", UNKNOWN_ARG_SCRIPTS)
def test_an_unknown_argument_is_still_fatal(deploy_repo, stub_bin, script):
    """bd polyglot-pdf-7aez9: a typo used to match no arm, deploy NOTHING, and
    still print a success banner. The engine changed; that refusal did not.

    The refusal must NAME the offending argument. Without that assertion this
    test is satisfied by the "nothing selected to deploy" backstop further
    down each wrapper -- which also exits non-zero with no triggers run, so
    deleting the unknown-argument arm entirely would leave it green while the
    operator got a message that never mentions their typo (mutation-verified:
    replacing the arm with a no-op passed until this line existed).
    """
    proc, calls, _sha = _run(
        deploy_repo, stub_bin, script, "--front-end", build_check_exit="0"
    )
    assert proc.returncode != 0
    assert _triggers(calls) == []
    assert "--front-end" in proc.stdout + proc.stderr, (
        f"{script} refused but never told the operator which argument was wrong"
    )


def test_deploy_new_refuses_a_service_it_has_no_target_for(deploy_repo, stub_bin):
    proc, calls, _sha = _run(
        deploy_repo, stub_bin, "backend/deploy-new.sh", "polyglot-nonesuch",
        build_check_exit="0",
    )
    assert proc.returncode != 0
    assert _triggers(calls) == []
    assert "No Cloud Build target" in proc.stdout + proc.stderr


def test_deploy_all_refuses_without_a_channel(deploy_repo, stub_bin):
    """backend-staging vs backend-demo is a CHANNEL choice; defaulting it here
    would default to deploying one of the two, and 'demo' is the protected
    target."""
    proc, calls, _sha = _run(
        deploy_repo, stub_bin, "deploy-all.sh", build_check_exit="0"
    )
    assert proc.returncode != 0
    assert _triggers(calls) == []


@pytest.mark.parametrize(
    "channel,expected",
    [
        (
            "staging",
            [
                "polyglot-backend-staging",
                "polyglot-form-kits",
                "polyglot-frontend-staging",
            ],
        ),
        (
            "demo",
            ["polyglot-backend-demo", "polyglot-form-kits", "polyglot-frontend-demo"],
        ),
    ],
)
def test_deploy_all_runs_the_named_channels_targets(
    deploy_repo, stub_bin, channel, expected
):
    log = deploy_repo.parent / "gcloud.log"
    log.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = str(stub_bin) + os.pathsep + env["PATH"]
    env["GCLOUD_LOG"] = str(log)
    env["MANIFEST_PYTHON_CANDIDATES"] = "stubpy"
    env["BUILD_CHECK_EXIT"] = "0"
    env["GCLOUD_FAIL_TRIGGER"] = ""
    env["DEPLOY_CHANNEL"] = channel
    proc = subprocess.run(
        [BASH, str(deploy_repo / "deploy-all.sh")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(deploy_repo),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert _triggers(calls) == expected


def test_a_dirty_tree_is_still_refused_before_any_trigger(deploy_repo, stub_bin):
    """The preflight is not decorative: a build runs from a COMMIT, and
    build_checks/{sha} vouches for that commit's test run."""
    (deploy_repo / "scratch.txt").write_text("uncommitted\n", encoding="utf-8")
    proc, calls, _sha = _run(
        deploy_repo, stub_bin, "deploy-staging.sh", build_check_exit="0"
    )
    assert proc.returncode != 0
    assert _triggers(calls) == []


# ---------------------------------------------------------------------------
# 5. The inline engine is gone -- pinned as a set over every wrapper.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", WRAPPERS)
@pytest.mark.parametrize("idiom", INLINE_ENGINE_IDIOMS)
def test_no_wrapper_still_deploys_anything_itself(rel, idiom):
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    code = "\n".join(
        ln for ln in body.splitlines() if not ln.lstrip().startswith("#")
    )
    assert idiom not in code, (
        f"{rel} still runs `{idiom}` -- the deploy stages live in "
        "cloudbuild.yaml, and a wrapper that deploys on its own is a route "
        "around the verify, reachability and promotion gates that run as "
        "build steps"
    )


@pytest.mark.parametrize("rel", WRAPPERS)
def test_no_wrapper_carries_a_bash_copy_of_the_reachability_gate(rel):
    """scripts/verify_service_reachable.py is the ONE implementation, and the
    build calls it directly. Four wrappers used to each carry a bash wrapper
    around it because each deployed a service itself; none does now."""
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "verify_service_publicly_reachable()" not in body, (
        f"{rel} defines a bash reachability wrapper again"
    )
    assert "get-iam-policy" not in body, (
        f"{rel} appears to carry its own copy of the IAM-policy check"
    )


@pytest.mark.parametrize("rel", WRAPPERS)
def test_every_wrapper_refuses_a_dirty_or_unpushed_tree(rel):
    """Every wrapper, not just the two the preflight bead shipped with: they
    all name a commit for a build that vouches for it."""
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "deploy_preflight.sh" in body, f"{rel} does not source the preflight"
    assert "deploy_preflight " in body, f"{rel} sources but never calls the preflight"


@pytest.mark.parametrize("rel", WRAPPERS)
def test_every_wrapper_routes_through_the_shared_trigger_runner(rel):
    """One place starts builds, streams logs and reads their final status. A
    wrapper that called `gcloud builds triggers run` itself would be a second
    copy of that logic, and the status check is the half that gets forgotten."""
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "deploy_build_targets.sh" in body
    code = "\n".join(
        ln for ln in body.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "gcloud builds triggers run" not in code, (
        f"{rel} starts a trigger directly instead of via run_build_targets"
    )
