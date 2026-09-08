"""The tagged no-traffic admin deploy flow (bd polyglot-pdf-3l2vp, sprint-22
plan bead 1.3 -- "Staging tier for the admin service").

WHY THIS EXISTS. There is ONE admin service and ONE console site backing BOTH
channels' data (the admin service has no channel of its own), so a bad admin
deploy takes the control plane down for staging AND the demo at once. The plan
requires every admin-service deploy to land as a Cloud Run revision that
receives ZERO traffic, gets its own health check at its OWN stable tag URL,
and ONLY THEN receives traffic -- so a broken revision never serves a single
real request.

WHAT THIS FILE PINS, AND WHY IT RUNS THE SHELL (mirrors
test_deploy_reachability_gate.py's approach, which extracts and executes a
function against synthetic gcloud output rather than asserting on text). Here
the logic is a straight-line block inside deploy-all.sh's backend stage, not
a standalone function, so the driver stubs gcloud/curl/git and executes the
EXTRACTED block directly -- a text assertion could not tell you that a failed
health check actually skips update-traffic, only that both strings appear
somewhere in the file.

Both directions matter and are pinned separately:
  - BACKEND_NO_TRAFFIC_TAG unset (every channel except deploy-admin.sh) must
    produce the EXACT invocation this had before tagged deploys existed --
    no --tag, no --no-traffic, no tag-URL health probe, no update-traffic
    call. A regression here would silently switch every existing channel to
    a no-traffic deploy that never receives its own traffic-shift call.
  - BACKEND_NO_TRAFFIC_TAG set must gate the traffic shift on a REAL /health
    response, not merely on the gcloud deploy exiting 0: a revision that
    deploys cleanly but crash-loops on start (e.g. an APP_MODULE typo
    pointing at a module the image does not contain) must never receive
    traffic.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ALL = REPO_ROOT / "deploy-all.sh"
# shutil.which, never a bare "bash": on Windows a bare name resolves to WSL's
# bash, which cannot see the Git-Bash filesystem (mirrors
# tests/test_deploy_manifest_validation.py and
# tests/test_deploy_reachability_gate.py).
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not on PATH")

BLOCK_START = 'if [ "$DEPLOY_BACKEND" = true ]; then'
BLOCK_END = "\n    cd \"$SCRIPT_DIR\"\nfi\n"


def _backend_block() -> str:
    """The `if [ "$DEPLOY_BACKEND" = true ]; then ... fi` block, verbatim.

    Sliced from the FIRST occurrence of the section banner (the backend
    stage's own header comment, unique in the file) through the first
    `cd "$SCRIPT_DIR"` + `fi` pair that follows it -- the backend stage's own
    close. A byte-range slice (not a re-implementation of the block) is what
    keeps this test honest about testing the REAL script rather than a
    paraphrase of it.
    """
    body = DEPLOY_ALL.read_text(encoding="utf-8")
    start = body.index(BLOCK_START)
    end = body.index(BLOCK_END, start) + len(BLOCK_END)
    return body[start:end]


def test_extraction_finds_the_block():
    """Guard the guard: a slice that finds nothing passes every test vacuously."""
    block = _backend_block()
    assert "gcloud run deploy" in block
    assert "BACKEND_NO_TRAFFIC_TAG" in block
    assert len(block) > 500


def _run_backend_stage(
    tmp_path: Path,
    *,
    no_traffic_tag: str = "",
    health_status: str = "200",
    describe_url: str = "https://polyglot-admin-abc123.a.run.app",
    deploy_rc: int = 0,
) -> tuple[int, str, str]:
    """Execute the extracted backend block against stubbed gcloud/curl/git.

    Stubs are SHELL FUNCTIONS, not files on PATH (same reasoning as the
    reachability gate driver: Python's os.pathsep disagrees with bash's on
    Windows, so a PATH-based stub silently fails to shadow the real binaries).

    `gcloud` fans out on its subcommand so one stub covers `services enable`,
    `builds submit`, `run deploy`, `run services get-iam-policy` (the
    reachability gate, made to always report a healthy binding so this test
    exercises ONLY the tag-flow logic, not the gate covered by
    test_deploy_reachability_gate.py), `run services describe`, and
    `run services update-traffic` -- each recording that it was called via a
    marker file so assertions can check invocation, not just exit code.
    """
    calls_dir = tmp_path / "calls"
    calls_dir.mkdir()

    driver = tmp_path / "driver.sh"
    driver.write_text(
        "set -e\n"
        "log_info() { echo \"[INFO] $1\"; }\n"
        "log_success() { echo \"[SUCCESS] $1\"; }\n"
        "log_warn() { echo \"[WARN] $1\" >&2; }\n"
        "log_error() { echo \"[ERROR] $1\" >&2; }\n"
        # verify_service_publicly_reachable is covered by its own test file;
        # stub it as a no-op success so this driver exercises only the
        # tag-flow logic layered around it.
        "verify_service_publicly_reachable() { return 0; }\n"
        "git() {\n"
        '  if [[ "$1" == "-C" && "$3" == "rev-parse" ]]; then\n'
        '    echo "deadbeef0000000000000000000000000000000000"\n'
        "    return 0\n"
        "  fi\n"
        "}\n"
        "gcloud() {\n"
        f'  echo "$*" >> "{calls_dir.as_posix()}/gcloud_calls"\n'
        '  if [[ "$*" == *"run deploy"* ]]; then\n'
        f"    return {deploy_rc}\n"
        '  elif [[ "$*" == *"describe"* ]]; then\n'
        f'    echo "{describe_url}"\n'
        '  elif [[ "$*" == *"update-traffic"* ]]; then\n'
        f'    touch "{calls_dir.as_posix()}/update_traffic_called"\n'
        "  fi\n"
        "  return 0\n"
        "}\n"
        "curl() {\n"
        f'  echo "$*" >> "{calls_dir.as_posix()}/curl_calls"\n'
        f'  echo -n "{health_status}"\n'
        "}\n"
        f'DEPLOY_BACKEND=true\n'
        f'BACKEND_SERVICE_NAME="polyglot-admin"\n'
        f'REGION="us-central1"\n'
        f'POLYGLOT_PROJECT_NAME="test-project"\n'
        f'FORM_KITS_BUCKET="test-bucket"\n'
        f'FORM_KITS_PREFIX="form-kits"\n'
        f'SCRIPT_DIR="{tmp_path.as_posix()}"\n'
        f'BACKEND_NO_TRAFFIC_TAG="{no_traffic_tag}"\n'
        + _backend_block()
        + '\necho "REACHED_END"\n',
        encoding="utf-8",
        newline="\n",
    )
    proc = subprocess.run(
        [BASH, "driver.sh"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(tmp_path),
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _gcloud_calls(tmp_path: Path) -> str:
    path = tmp_path / "calls" / "gcloud_calls"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ---------------------------------------------------------------------------
# BACKEND_NO_TRAFFIC_TAG unset: every existing channel's invocation must be
# untouched.
# ---------------------------------------------------------------------------


def test_untagged_deploy_passes_no_tag_or_no_traffic_flags(tmp_path):
    rc, out, err = _run_backend_stage(tmp_path, no_traffic_tag="")
    assert rc == 0 and "REACHED_END" in out, err
    calls = _gcloud_calls(tmp_path)
    deploy_call = next(l for l in calls.splitlines() if "run deploy" in l)
    assert "--tag" not in deploy_call, deploy_call
    assert "--no-traffic" not in deploy_call, deploy_call


def test_untagged_deploy_never_probes_a_tag_url_or_shifts_traffic(tmp_path):
    """Without a tag, the whole verify-then-shift sequence must not run."""
    rc, out, err = _run_backend_stage(tmp_path, no_traffic_tag="")
    assert rc == 0, err
    calls_dir = tmp_path / "calls"
    assert not (calls_dir / "curl_calls").exists(), (
        "an untagged deploy must not probe any tag URL's /health"
    )
    assert not (calls_dir / "update_traffic_called").exists(), (
        "an untagged deploy must not call update-traffic -- gcloud run deploy "
        "already shifted 100% of traffic itself"
    )


def test_untagged_deploy_sets_app_module_and_git_sha_runtime_env(tmp_path):
    """Property pinned by this bead: every backend deploy carries both,
    tagged or not -- the reachability gate covers the deploy, this covers
    the runtime env it carries.
    """
    rc, _, err = _run_backend_stage(tmp_path, no_traffic_tag="")
    assert rc == 0, err
    calls = _gcloud_calls(tmp_path)
    deploy_call = next(l for l in calls.splitlines() if "run deploy" in l)
    assert "APP_MODULE=backend.main:app" in deploy_call, deploy_call
    assert "GIT_SHA=deadbeef" in deploy_call, deploy_call


# ---------------------------------------------------------------------------
# BACKEND_NO_TRAFFIC_TAG set: the tagged no-traffic-until-verified flow.
# ---------------------------------------------------------------------------


def test_tagged_deploy_passes_tag_and_no_traffic_flags(tmp_path):
    rc, out, err = _run_backend_stage(tmp_path, no_traffic_tag="candidate")
    assert rc == 0 and "REACHED_END" in out, err
    calls = _gcloud_calls(tmp_path)
    deploy_call = next(l for l in calls.splitlines() if "run deploy" in l)
    assert "--tag candidate" in deploy_call, deploy_call
    assert "--no-traffic" in deploy_call, deploy_call


def test_tagged_deploy_probes_the_tag_url_not_the_base_url(tmp_path):
    """gcloud composes the tag URL as https://<tag>---<service>-<hash>...

    A probe against the BASE url would test the wrong revision entirely --
    the one already serving traffic, not the untagged candidate.
    """
    rc, _, err = _run_backend_stage(
        tmp_path,
        no_traffic_tag="candidate",
        describe_url="https://polyglot-admin-abc123.a.run.app",
    )
    assert rc == 0, err
    curl_calls = (tmp_path / "calls" / "curl_calls").read_text(encoding="utf-8")
    assert (
        "https://candidate---polyglot-admin-abc123.a.run.app/health"
        in curl_calls
    ), curl_calls


def test_healthy_tag_url_shifts_traffic(tmp_path):
    rc, out, err = _run_backend_stage(
        tmp_path, no_traffic_tag="candidate", health_status="200"
    )
    assert rc == 0 and "REACHED_END" in out, err
    assert (tmp_path / "calls" / "update_traffic_called").exists(), (
        "a healthy tagged candidate must have its traffic shifted"
    )
    calls = _gcloud_calls(tmp_path)
    traffic_call = next(l for l in calls.splitlines() if "update-traffic" in l)
    assert "--to-latest" in traffic_call, traffic_call


@pytest.mark.parametrize("status", ["500", "404", "000"], ids=["500", "404", "no-connect"])
def test_unhealthy_tag_url_aborts_without_shifting_traffic(tmp_path, status):
    """THE CASE THIS BEAD EXISTS FOR: a broken candidate must never get traffic.

    000 covers curl's own failure code (connection refused/timeout) -- the
    `|| echo "000"` fallback in deploy-all.sh, exercised here by a curl stub
    that itself returns the sentinel body without needing to fail the process.
    """
    rc, out, err = _run_backend_stage(
        tmp_path, no_traffic_tag="candidate", health_status=status
    )
    assert rc == 1, (
        f"an unhealthy tagged candidate (status {status}) must abort the "
        f"deploy, not exit 0. stdout={out!r} stderr={err!r}"
    )
    assert "REACHED_END" not in out, (
        "the script must exit before reaching the end on a failed health check"
    )
    assert not (tmp_path / "calls" / "update_traffic_called").exists(), (
        "traffic must NOT be shifted when the tagged candidate failed its "
        "health check -- the previous good revision must keep serving"
    )
    assert "did not answer /health" in err
    assert "NOT shifted" in err


def test_tagged_deploy_still_sets_app_module_and_git_sha(tmp_path):
    rc, _, err = _run_backend_stage(tmp_path, no_traffic_tag="candidate")
    assert rc == 0, err
    calls = _gcloud_calls(tmp_path)
    deploy_call = next(l for l in calls.splitlines() if "run deploy" in l)
    assert "APP_MODULE=" in deploy_call, deploy_call
    assert "GIT_SHA=" in deploy_call, deploy_call
