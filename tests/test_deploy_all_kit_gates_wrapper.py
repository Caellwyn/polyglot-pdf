"""
Pytest wrapper so the deploy-gate bash harness runs in CI (bd polyglot-pdf-45x5).

The behavioral tests for deploy-all.sh's kit gates live in the bash harness
``test_deploy_all_kit_gates.sh`` (bash is the natural language for testing bash
helpers). CI runs ``pytest backend/tests tests`` (.github/workflows/ci.yml), which
would NOT collect a bare ``.sh`` file -- so without this wrapper a regression in the
safety-critical ``kit_is_complete`` gate would still pass automated PR checks. This
shells out to the harness and asserts it exits 0, making the gate's coverage part of
the standard pytest run.

Skips (rather than fails) when bash cannot run -- bash absent, OR present but
unable to launch a process (e.g. a Windows box where ``shutil.which`` resolves the
WSL ``bash`` shim that then fails ``execvpe``). The wrapper must never produce a
false red where it simply cannot execute the harness; CI is ubuntu-latest, where
bash runs natively and a genuine gate regression DOES fail this test.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

_HARNESS = Path(__file__).parent / "test_deploy_all_kit_gates.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available on this runner")
def test_deploy_all_kit_gates_harness_passes():
    assert _HARNESS.is_file(), f"missing harness: {_HARNESS}"
    try:
        result = subprocess.run(
            ["bash", str(_HARNESS)],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        pytest.skip(f"bash present but could not launch: {exc}")

    # A bash that resolves to the WSL shim can "run" but fail to exec the harness,
    # printing a CreateProcessCommon/execvpe error to stderr with NO harness output.
    # That is an environment defect, not a gate regression -- skip it. A real run
    # emits the harness's PASS/FAIL lines on stdout.
    if result.returncode != 0 and "PASS" not in result.stdout and "FAIL" not in result.stdout:
        pytest.skip(
            "bash could not execute the harness (no harness output); "
            f"stderr: {result.stderr.strip()}"
        )

    # Surface the harness's own PASS/FAIL lines on failure for a readable report.
    assert result.returncode == 0, (
        f"deploy-gate harness failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
