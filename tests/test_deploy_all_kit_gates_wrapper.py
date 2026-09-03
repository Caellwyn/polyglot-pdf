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
            encoding="utf-8",
        )
    except OSError as exc:
        pytest.skip(f"bash present but could not launch: {exc}")

    # Skip ONLY the specific local-Windows WSL-shim failures: `shutil.which` can
    # resolve the WSL ``bash`` stub, which then fails one of two ways:
    #   1. it cannot exec the harness (CreateProcessCommon/execvpe/WSL error), OR
    #   2. the WSL VM itself cannot boot -- the System32 shim prints
    #      "...CreateVm/ConfigureGpu/HCS/0x800701b1" ("a device which does not
    #      exist was specified") to STDOUT (bd polyglot-pdf-4nll).
    # We must NOT skip on "any nonzero with no PASS/FAIL output" -- a real
    # regression (a syntax error while sourcing deploy-all.sh, an early abort
    # before the first assertion) has exactly that shape, and skipping it would
    # defeat the CI coverage this wrapper exists to add (Codex review). On Linux CI
    # bash execs natively, so neither shape appears there and a genuine no-output
    # failure falls through to the assert. Check BOTH streams: shape (1) lands on
    # stderr, shape (2) on stdout.
    _WSL_SHIM_MARKERS = (
        "execvpe", "CreateProcessCommon", "WSL (",
        "CreateVm", "ConfigureGpu", "HCS", "0x800701b1",
    )
    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0 and any(m in combined for m in _WSL_SHIM_MARKERS):
        pytest.skip(
            "bash resolved to the WSL shim and could not exec/boot the harness; "
            f"stdout: {result.stdout.strip()} stderr: {result.stderr.strip()}"
        )

    # Surface the harness's own PASS/FAIL lines on failure for a readable report.
    assert result.returncode == 0, (
        f"deploy-gate harness failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
