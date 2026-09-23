"""scripts/setup-beads-remote.sh's declared bucket and settings (bd
polyglot-pdf-d9f97, epic polyglot-pdf-mlcgn).

This is an OPERATOR script -- no deploy pipeline or CI step runs gcloud -- so
the only mechanical guard is pinning the SHIPPED SCRIPT TEXT, matching the
sibling tests/test_setup_telemetry_script.py pattern.

WHY THE ASSERTIONS ARE SCOPED TO ONE COMMAND BLOCK. The script mentions every
setting three times: in its header comment, in the `create` call, and in the
`update` call. Only the `update` call is load-bearing for idempotency -- it is
the step that runs on EVERY invocation and converges an existing bucket, while
`create` runs once. A whole-file search would stay green if a setting were
deleted from `update` but survived in the comment or in `create`, which is
exactly the regression that matters (a re-run that silently stops enforcing
it). So each setting is looked for inside the parsed `update` block only.

The lifecycle rule is checked by PARSING the heredoc JSON, not by matching
strings: a rule that deleted LIVE objects would be catastrophic for the store,
and only a parse can tell `isLive: false` from `isLive: true` reliably.

ASCII only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup-beads-remote.sh"


def _text() -> str:
    assert SCRIPT.is_file(), "scripts/setup-beads-remote.sh is missing"
    return SCRIPT.read_text(encoding="utf-8")


def _command_block(text: str, prefix: str) -> str:
    """The full (backslash-continued) command starting with `prefix`.

    Returns the command's own lines only -- never surrounding comments -- so
    an assertion against it cannot be satisfied by prose.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith(prefix):
            block = [line]
            j = i
            while lines[j].rstrip().endswith("\\") and j + 1 < len(lines):
                j += 1
                block.append(lines[j])
            return "\n".join(block)
    raise AssertionError(f"no command starting with {prefix!r} in the script")


def _assignment(text: str, name: str) -> str:
    m = re.search(rf'^{name}="([^"]*)"\s*$', text, re.MULTILINE)
    assert m, f"{name}= assignment not found at top level"
    return m.group(1)


# The settings the `update` step must converge on every run. Each is
# parametrized so a mutation removing any ONE of them reddens its own case.
CONVERGED_FLAGS = [
    "--uniform-bucket-level-access",
    "--public-access-prevention",
    "--versioning",
    '--lifecycle-file="$LIFECYCLE_FILE"',
    '--project="$PROJECT_ID"',
]


@pytest.mark.parametrize("flag", CONVERGED_FLAGS)
def test_update_step_converges_each_setting(flag):
    block = _command_block(_text(), 'gcloud storage buckets update "$BUCKET"')
    assert flag in block, (
        f"the always-run `update` step no longer passes {flag}; a re-run would "
        f"stop enforcing it on an existing bucket")


def test_update_step_runs_unconditionally():
    """The converge step must run on EVERY invocation, not only after create.

    Pinned as: the `update` command sits at top level (column 0) AFTER the
    create-if-absent `if ... fi` block closes -- not nested inside a branch.
    """
    text = _text()
    lines = text.splitlines()
    upd = next(i for i, l in enumerate(lines)
               if l.startswith('gcloud storage buckets update "$BUCKET"'))
    last_fi = max(i for i, l in enumerate(lines[:upd]) if l.strip() == "fi")
    create = next(i for i, l in enumerate(lines)
                  if 'gcloud storage buckets create "$BUCKET"' in l)
    assert create < last_fi < upd, (
        "`update` must come after the create-if-absent block closes, at top "
        "level, so it converges an EXISTING bucket too")


def test_create_only_when_absent():
    """`create` lives in the else-branch of a describe-existence check."""
    text = _text()
    m = re.search(
        r'if gcloud storage buckets describe "\$BUCKET".*?\nelse\n(.*?)\nfi\n',
        text, re.DOTALL)
    assert m, "no `if describe ... else ... fi` existence check found"
    assert 'gcloud storage buckets create "$BUCKET"' in m.group(1), (
        "`create` must run only when the describe check fails")


def test_create_sets_location_and_access_controls():
    block = _command_block(_text(), 'gcloud storage buckets create "$BUCKET"')
    for flag in ('--location="$LOCATION"', "--uniform-bucket-level-access",
                 "--public-access-prevention", '--project="$PROJECT_ID"'):
        assert flag in block, f"`create` no longer passes {flag}"


def test_bucket_name_and_location():
    text = _text()
    assert _assignment(text, "BUCKET") == "gs://${PROJECT_ID}-beads"
    assert _assignment(text, "LOCATION") == "us-central1"


def test_lifecycle_deletes_only_noncurrent_versions_after_30_days():
    """Parse the lifecycle JSON; a rule touching LIVE objects would delete
    the store itself, so this is checked structurally, not by substring."""
    text = _text()
    m = re.search(r'cat > "\$LIFECYCLE_FILE" <<EOF\n(.*?)\nEOF\n', text, re.DOTALL)
    assert m, "lifecycle heredoc not found"
    days = _assignment_int(text, "NONCURRENT_DAYS")
    doc = json.loads(m.group(1).replace("${NONCURRENT_DAYS}", str(days)))
    rules = doc["rule"]
    assert len(rules) == 1, f"expected exactly one lifecycle rule, got {rules}"
    rule = rules[0]
    assert rule["action"] == {"type": "Delete"}
    cond = rule["condition"]
    assert cond.get("isLive") is False, (
        "the Delete rule must be scoped to NONCURRENT versions (isLive: false); "
        "without it the rule deletes the live store")
    assert cond.get("daysSinceNoncurrentTime") == 30
    assert set(cond) == {"isLive", "daysSinceNoncurrentTime"}, (
        f"unexpected extra lifecycle conditions: {cond}")


def _assignment_int(text: str, name: str) -> int:
    m = re.search(rf"^{name}=(\d+)\s*$", text, re.MULTILINE)
    assert m, f"{name}=<int> assignment not found"
    return int(m.group(1))


def test_refuses_the_retired_project():
    text = _text()
    m = re.search(r'if \[ "\$PROJECT_ID" = "polyglot-forms-919f2" \]; then\n(.*?)\nfi',
                  text, re.DOTALL)
    assert m, "retired-project refusal missing"
    assert re.search(r"^\s*exit [1-9]", m.group(1), re.MULTILINE), (
        "the retired-project branch must exit non-zero")


def test_strict_mode_and_ascii():
    text = _text()
    assert re.search(r"^set -euo pipefail$", text, re.MULTILINE)
    text.encode("ascii")  # raises on any non-ASCII byte (CLAUDE.md scar #6)
