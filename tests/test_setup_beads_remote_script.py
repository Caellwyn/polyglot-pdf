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


def _allowed_member_patterns() -> list[str]:
    """The `case` arms of is_allowed_member() that `return 0`, as shipped.

    Bash `case` patterns are shell globs; for the characters these patterns
    use (literal text, `*`, `@`, `.`, `-`, `:`) Python's fnmatchcase has the
    same meaning, so the SHIPPED patterns are what get exercised.
    """
    m = re.search(r"^is_allowed_member\(\) \{\n(.*?)\n\}", _text(),
                  re.MULTILINE | re.DOTALL)
    assert m, "is_allowed_member() not found"
    pats = re.findall(r"^\s*(\S+)\) return 0 ;;", m.group(1), re.MULTILINE)
    assert pats, "no allowing case arms found"
    return pats


def _allowed(member: str) -> bool:
    from fnmatch import fnmatchcase
    return any(fnmatchcase(member, p) for p in _allowed_member_patterns())


# Principals that must REFUSE whatever role they hold. The first three are
# exactly what the live check found on polyglot-demo-aa709; the rest are the
# evasions the round-2 review found in the earlier role-blocklist design.
@pytest.mark.parametrize("member", [
    "serviceAccount:polyglot-backend-sa@polyglot-demo-aa709.iam.gserviceaccount.com",
    "serviceAccount:775682479028-compute@developer.gserviceaccount.com",
    "serviceAccount:775682479028@cloudbuild.gserviceaccount.com",
    "serviceAccount:anything@polyglot-beads.iam.gserviceaccount.com",
    "group:admins@caellwynai.com",          # groups can contain service accounts
    "principal://iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p/subject/s",
    "principalSet://iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p/*",
    "deleted:serviceAccount:old@x.iam.gserviceaccount.com?uid=1",
    "allUsers",
    "allAuthenticatedUsers",
    # look-alikes of the allowed Google agents must not slip through
    "serviceAccount:evil@gcp-sa-cloudbuild.iam.gserviceaccount.com",
    "serviceAccount:service-1@my-project.iam.gserviceaccount.com",
    "",
])
def test_non_human_principals_are_refused(member):
    assert not _allowed(member), (
        f"{member!r} would be ALLOWED to hold roles the bucket inherits; any "
        f"role it holds could reach object data")


@pytest.mark.parametrize("member", [
    "user:josh@caellwynai.com",
    "user:caellwyn@gmail.com",
    "domain:caellwynai.com",
    "serviceAccount:service-123@gcp-sa-cloudbuild.iam.gserviceaccount.com",
    "serviceAccount:123@cloudservices.gserviceaccount.com",
    "serviceAccount:service-123@gs-project-accounts.iam.gserviceaccount.com",
])
def test_humans_and_google_agents_are_allowed(member):
    assert _allowed(member), (
        f"{member!r} is a human or a Google-managed agent present on normal "
        f"projects; refusing it would make the script unusable")


def test_guard_reads_ancestors_and_runs_before_create():
    """Reads the ANCESTORS policy (org/folder grants are inherited too), exits
    non-zero on any disallowed principal, is role-agnostic, and runs before
    any bucket work -- a guard after `create` would leave the bucket behind."""
    text = _text()
    lines = text.splitlines()
    guard = next(i for i, l in enumerate(lines)
                 if l.startswith("DISALLOWED=$(gcloud projects "))
    assert "get-ancestors-iam-policy" in lines[guard], (
        "the guard must read the ancestors policy, not the project's alone")
    create = next(i for i, l in enumerate(lines)
                  if 'gcloud storage buckets create "$BUCKET"' in l)
    describe = next(i for i, l in enumerate(lines)
                    if l.startswith('if gcloud storage buckets describe "$BUCKET"'))
    assert guard < describe < create, "the guard must run before any bucket work"
    m = re.search(r'if \[ -n "\$DISALLOWED" \]; then\n(.*?)\nfi', text, re.DOTALL)
    assert m and re.search(r"^\s*exit [1-9]", m.group(1), re.MULTILINE), (
        "a non-empty DISALLOWED list must exit non-zero")
    loop = "\n".join(lines[guard:guard + 12])
    assert 'if ! is_allowed_member "$member"; then' in loop
    assert "$role" not in loop.split("is_allowed_member")[1].split("then")[0], (
        "membership, not role, decides refusal -- the check must stay role-agnostic")


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
