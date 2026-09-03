"""Deploy-script manifest validation must abort on invalid JSON.

bd polyglot-pdf-4w0l: deploy-all.sh and scripts/deploy-form-kit.sh build the
voice-app manifest (index.json) by string concatenation. The old pipeline
validated with `python3 -m json.tool || echo $raw`, so a validation FAILURE
fell back to shipping the RAW invalid JSON to GCS and the deploy reported
success (the voice app then loads no forms, with zero deploy-time signal).
The fix routes both scripts through write_validated_manifest(), which:

  - aborts (nonzero) when the manifest is invalid JSON -- never shipped;
  - falls back python3 -> python -> py so a missing python3 (common on
    Windows Git Bash) still validates instead of skipping validation;
  - aborts when NO interpreter exists at all (unvalidatable != shippable).

The two scripts carry an IDENTICAL copy of the helpers (they already
duplicate the whole manifest-generation block; no shared lib). That identity
is asserted here so a one-sided edit fails CI.

These tests extract the bash functions from the real script text and run
them under bash, so they exercise the shipped code, not a reimplementation.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ALL = REPO_ROOT / "deploy-all.sh"
DEPLOY_KIT = REPO_ROOT / "scripts" / "deploy-form-kit.sh"

BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not on PATH")

FUNC_NAMES = ("find_manifest_python", "write_validated_manifest")


def _extract_function(script_text: str, name: str) -> str:
    """The function block from `name() {` through its closing `}` at col 0."""
    match = re.search(
        r"^" + re.escape(name) + r"\(\) \{\n.*?^\}", script_text, re.S | re.M
    )
    assert match, "{}() not found in script".format(name)
    return match.group(0)


def _validation_functions(script_path: Path) -> str:
    text = script_path.read_text(encoding="utf-8")
    return "\n\n".join(_extract_function(text, n) for n in FUNC_NAMES)


def _run_validator(
    tmp_path: Path, content: str, extra_env: dict[str, str] | None = None
) -> tuple[int, str, Path]:
    """Run write_validated_manifest (as extracted from deploy-form-kit.sh).

    The JSON content goes through a FILE, not argv, and all paths are
    relative to cwd=tmp_path: on Windows, MSYS path conversion at the
    native-python -> Git-Bash boundary mangles argv elements containing
    colons (any JSON with a "key":value), which would corrupt the very
    content under test. (The real scripts build the content inside bash,
    so a file-fed harness is equally faithful.)
    """
    out_file = tmp_path / "index.json"
    (tmp_path / "content.txt").write_text(content, encoding="utf-8", newline="\n")
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "log_error() { echo \"[ERROR] $1\" >&2; }\n"
        + _validation_functions(DEPLOY_KIT)
        + '\nwrite_validated_manifest "$(cat "$1")" "$2"\n',
        encoding="utf-8",
        newline="\n",
    )
    env = dict(os.environ)
    env.update(extra_env or {})
    proc = subprocess.run(
        [BASH, "driver.sh", "content.txt", "index.json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(tmp_path),
        timeout=60,
    )
    return proc.returncode, proc.stderr, out_file


def test_helper_copies_are_identical():
    # The MUST-match-exactly contract between the two scripts' copies.
    assert _validation_functions(DEPLOY_ALL) == _validation_functions(DEPLOY_KIT)


def test_invalid_manifest_aborts_nonzero_with_clear_error(tmp_path):
    rc, stderr, out_file = _run_validator(tmp_path, '{"forms":[')
    assert rc != 0
    assert "INVALID JSON" in stderr
    # Nothing shippable was produced: the out file is empty (json.tool wrote
    # nothing before failing), so even a buggy caller could not upload the
    # raw content -- the raw string never reaches the file.
    assert out_file.read_text(encoding="utf-8") == ""


def test_valid_manifest_passes_and_pretty_prints(tmp_path):
    manifest = '{"generatedAt":"2026-01-01T00:00:00.000Z","forms":[]}'
    rc, stderr, out_file = _run_validator(tmp_path, manifest)
    assert rc == 0, stderr
    assert json.loads(out_file.read_text(encoding="utf-8")) == {
        "generatedAt": "2026-01-01T00:00:00.000Z",
        "forms": [],
    }


def test_missing_python3_falls_back_to_next_candidate(tmp_path):
    # Simulate python3 being absent: the first candidate does not exist, the
    # later ones are the real interpreters (python3 kept for Linux CI, where
    # plain `python` may be the missing one).
    rc, stderr, out_file = _run_validator(
        tmp_path,
        '{"forms": []}',
        extra_env={"MANIFEST_PYTHON_CANDIDATES": "no-such-python-xyz python3 python py"},
    )
    assert rc == 0, stderr
    assert json.loads(out_file.read_text(encoding="utf-8")) == {"forms": []}


def test_no_interpreter_at_all_aborts(tmp_path):
    rc, stderr, _ = _run_validator(
        tmp_path,
        '{"forms": []}',
        extra_env={"MANIFEST_PYTHON_CANDIDATES": "no-such-python-xyz"},
    )
    assert rc != 0
    assert "No python interpreter" in stderr
