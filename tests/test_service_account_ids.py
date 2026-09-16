"""Every `gcloud iam service-accounts create <id>` id declared under
scripts/ must be 6-30 characters -- GCP's own hard limit on a service-
account id (bd polyglot-pdf-l3kqc).

WHY THIS EXISTS. scripts/setup-admin-service.sh once declared
MONTHLY_TOPUP_SCHEDULER_SA_NAME="admin-monthly-topup-scheduler-sa" -- 32
characters, two over the cap -- so `gcloud iam service-accounts create`
failed with INVALID_ARGUMENT the first time an operator actually ran the
script (introduced by bd polyglot-pdf-0euzk, PR #792, and invisible to
every test that mocks the Firebase/gcloud SDK: a mock cannot tell you the
real call is malformed, only that the code attempted it).

ENUMERATED, NOT HAND-LISTED (CLAUDE.md scar #8): this file does not name
scripts/setup-admin-service.sh or any other script by hand. It discovers
every TRACKED shell script under scripts/ via `git ls-files` (mirroring
the form-kits doctrine's "tracked is what CI actually sees" reasoning --
an untracked script is someone's scratch work, invisible in CI either
way), regex-scans each for every `gcloud iam service-accounts create`
invocation, resolves the id variable it references back to that
variable's own literal assignment in the same file, and asserts the
resolved literal's length. A new script introducing a ninth (or
twenty-ninth) over-long id fails this test with no edit here required.

Mutation: lengthen any one resolved literal past 30 characters (or shorten
one below 6) in the script it lives in -- this goes red for that specific
id, naming the file and the id.

ASCII only.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# GCP's own bounds for a service-account id (the part before the trailing
# generated "@<project>.iam.gserviceaccount.com" -- the account id itself,
# not the whole email).
_MIN_ID_LEN = 6
_MAX_ID_LEN = 30

# `gcloud iam service-accounts create "$SOME_VAR"` or, in a printed
# DRY-RUN/NOTE line, the same call with the var reference unquoted --
# both forms appear in scripts/ today (scripts/setup-cloud-build.sh has
# one of each, for the same id). Captures the referenced variable's name.
_CREATE_CALL_RE = re.compile(
    r'gcloud iam service-accounts create\s+"?\$([A-Za-z_][A-Za-z0-9_]*)"?'
)


def _tracked_shell_scripts() -> list[Path]:
    """Every git-tracked *.sh file under scripts/, relative to REPO_ROOT.

    `git ls-files` (not a directory walk) so an untracked, uncommitted
    script -- someone's local scratch work -- cannot silently widen or
    narrow what this test checks; CI sees exactly this same set.
    """
    result = subprocess.run(
        ["git", "ls-files", "scripts/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = [
        REPO_ROOT / line
        for line in result.stdout.splitlines()
        if line.endswith(".sh")
    ]
    assert paths, (
        "git ls-files scripts/ returned no *.sh files -- either the "
        "working tree is wrong or this test's discovery step is broken; "
        "either way it is silently checking nothing"
    )
    return paths


def _resolve_literal(text: str, var_name: str, *, script: Path) -> str:
    """The fixed string literal assigned to `var_name` in `text` (e.g.
    `SA_NAME="admin-backend-sa"`).

    Deliberately excludes `$` from the captured value: a COMPOSED
    assignment like `SA_EMAIL="$SA_NAME@$PROJECT..."` is not a raw id
    literal and must not be mistaken for one.
    """
    match = re.search(
        r'{}="([^"$]+)"'.format(re.escape(var_name)), text
    )
    assert match, (
        "{}: `gcloud iam service-accounts create \"${}\"` references "
        "${} but no `{}=\"<literal>\"` assignment (with no `$` inside "
        "the value) was found in the same file -- either the variable is "
        "only ever composed from other variables (and this test's "
        "resolver needs to follow the chain) or the id is not actually "
        "a fixed literal".format(script, var_name, var_name, var_name)
    )
    return match.group(1)


def _enumerate_service_account_ids() -> list[tuple[Path, str, str]]:
    """(script, variable name, resolved id literal) for every
    `gcloud iam service-accounts create` call under scripts/."""
    entries: list[tuple[Path, str, str]] = []
    for script in _tracked_shell_scripts():
        text = script.read_text(encoding="utf-8")
        for var_match in _CREATE_CALL_RE.finditer(text):
            var_name = var_match.group(1)
            literal = _resolve_literal(text, var_name, script=script)
            entries.append((script, var_name, literal))
    return entries


def test_every_created_service_account_id_is_enumerated_and_non_empty():
    """Sanity check on the enumeration itself: today's scripts/ declares
    at least one `gcloud iam service-accounts create` call. If this ever
    goes to zero, the length assertion below would vacuously pass on
    nothing -- so pin that the discovery step actually finds calls."""
    entries = _enumerate_service_account_ids()
    assert entries, (
        "no `gcloud iam service-accounts create` calls were found under "
        "scripts/ at all -- either every such call was removed, or this "
        "test's regex no longer matches the shape scripts/ uses (in "
        "which case the regex needs updating, not this test relaxing)"
    )


def test_every_created_service_account_id_is_6_to_30_characters():
    """GCP's `gcloud iam service-accounts create` hard-rejects an id
    outside 6-30 characters with INVALID_ARGUMENT -- a failure only a
    live gcloud call surfaces, never a mocked one (bd polyglot-pdf-l3kqc:
    exactly this bug shipped past every test that stubs the SDK).

    Checks every declared id together and reports every violation at
    once, rather than stopping at the first, so a reviewer sees the
    whole set in one failure."""
    entries = _enumerate_service_account_ids()
    violations = [
        "{} ({}=\"{}\", {} chars)".format(script, var_name, literal, len(literal))
        for script, var_name, literal in entries
        if not (_MIN_ID_LEN <= len(literal) <= _MAX_ID_LEN)
    ]
    assert not violations, (
        "service-account id(s) outside GCP's 6-30 character limit:\n  "
        + "\n  ".join(violations)
    )
