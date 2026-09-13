"""scripts/setup-cloud-build.sh: the manual triggers and the build identity
they run as (bead polyglot-pdf-p4ale, E4.5).

This is an OPERATOR script -- no deploy pipeline runs it, and no CI step
executes gcloud -- so the only mechanical guard available is pinning the
SHIPPED SCRIPT TEXT, matching tests/test_setup_monitoring_script.py,
tests/test_setup_telemetry_script.py and
tests/test_setup_admin_service_scheduler.py. The IAM ENVELOPE itself (the
exact role set, the two actAs bindings, the bucket scope) is pinned by
admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py, the sibling
of test_admin_sa_iam_envelope.py -- this file covers the OTHER half of the
bead: every trigger actually names the dedicated build identity, never the
legacy default Cloud Build SA.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup-cloud-build.sh"

EXPECTED_TARGETS = (
    "verify",
    "backend-staging",
    "backend-demo",
    "frontend-staging",
    "frontend-demo",
    "editor",
    "form-kits",
    "firestore-rules",
    "admin-service",
    "admin-console-candidate",
    "admin-console",
    "landing",
)


def _script_text() -> str:
    assert SCRIPT.is_file(), (
        "scripts/setup-cloud-build.sh is missing. It is the script this "
        "whole file asserts against.")
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists_and_starts_with_a_shebang():
    """git tracks these sibling scripts as mode 100644 on this repo and
    Windows stat() never reports S_IXUSR, so the shebang -- not the
    executable bit -- is what actually governs `bash scripts/foo.sh`."""
    assert _script_text().startswith("#!/bin/bash")


def test_script_is_ascii_only():
    """CLAUDE.md scar #6. A .sh is a source file."""
    raw = SCRIPT.read_bytes()
    bad = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not bad, (
        "non-ASCII byte(s) in setup-cloud-build.sh at offsets "
        + repr(bad[:5]))


# ---------------------------------------------------------------------------
# Exit criterion 3: every trigger names polyglot-cloudbuild-sa.
# ---------------------------------------------------------------------------

def test_build_sa_defaults_to_the_dedicated_name_not_the_legacy_default():
    """BUILD_SA is polyglot-cloudbuild-sa by default, not the legacy default
    Cloud Build SA (<project-number>@cloudbuild.gserviceaccount.com), which
    historically holds project Editor -- far wider than a deploy build
    needs. Mutation: revert BUILD_SA_NAME to a literal
    "polyglot-cloudbuild-sa" replaced by anything else -- red.
    """
    text = _script_text()
    assert 'BUILD_SA_NAME="polyglot-cloudbuild-sa"' in text, (
        "setup-cloud-build.sh no longer defaults the build identity to "
        "polyglot-cloudbuild-sa")
    assert re.search(
        r'BUILD_SA="\$\{CLOUD_BUILD_SA:-\$BUILD_SA_NAME@\$PROJECT\.iam\.'
        r'gserviceaccount\.com\}"',
        text,
    ), ("BUILD_SA is not derived from BUILD_SA_NAME -- a trigger could end "
        "up pointed at a different identity than the one this script "
        "actually provisions")


def test_every_trigger_command_names_the_build_sa():
    """The `gcloud builds triggers create manual` call's --service-account
    flag names $BUILD_SA, for every target, not a hand-typed email that
    could drift from the identity actually provisioned above.

    This is exit criterion 3: "Every trigger in the setup script names
    polyglot-cloudbuild-sa as its service account." Mutation: hardcode one
    target's --service-account to a literal email -- red (a trigger bound
    to a different identity than the one the IAM section provisions would
    deploy AS an unpinned, unaudited SA).
    """
    text = _script_text()
    assert re.search(
        r'--service-account="projects/\$PROJECT/serviceAccounts/\$BUILD_SA"',
        text,
    ), (
        "no `gcloud builds triggers create manual` call binds "
        "--service-account to $BUILD_SA")
    # And there is exactly ONE such --service-account flag in the whole
    # script (the one line inside the per-target loop) -- not one per
    # target hand-copied, which would let a future edit change it for only
    # some targets.
    matches = re.findall(r'--service-account="[^"]*"', text)
    assert len(matches) == 1, (
        "expected exactly one --service-account flag (inside the shared "
        "per-target trigger loop), found {}: {}".format(
            len(matches), matches))


def test_no_target_hardcodes_a_different_service_account():
    """No trigger literal ever names a raw *.iam.gserviceaccount.com email
    other than through $BUILD_SA -- catches a target added later with its
    own hand-typed --service-account.
    """
    text = _script_text()
    # Every literal service-account-shaped email in the file must be one of
    # the three declared identities' own variable definitions or comments,
    # never a second hardcoded value used as a --service-account flag.
    triggers_block = re.search(
        r"for entry in \"\$\{TARGETS\[@\]\}\"; do(.*?)\ndone",
        text, re.DOTALL)
    assert triggers_block, "could not find the per-target trigger loop"
    assert "gserviceaccount.com" not in triggers_block.group(1), (
        "the trigger loop hardcodes a service account email instead of "
        "using $BUILD_SA")


def test_every_target_gets_a_trigger():
    """The SET of targets, pinned (CLAUDE.md scar #8).

    Every cloudbuild.yaml target -- including ones not yet implemented --
    gets a trigger, so the console's target list and this script's list
    cannot silently disagree (see the script's own header comment).
    """
    text = _script_text()
    block = re.search(r"^TARGETS=\((.*?)^\)", text, re.MULTILINE | re.DOTALL)
    assert block, "setup-cloud-build.sh has no TARGETS=( ... ) array"
    declared = set(
        entry.split(":")[0]
        for entry in re.findall(r'"([a-z0-9_-]+:[a-z]+)"', block.group(1)))
    assert declared == set(EXPECTED_TARGETS), (
        "the targets setup-cloud-build.sh declares ({}) are not the set "
        "this file pins ({})".format(
            sorted(declared), sorted(EXPECTED_TARGETS)))


@pytest.mark.parametrize("target", EXPECTED_TARGETS)
def test_target_is_declared(target):
    text = _script_text()
    assert re.search(r'"{}:[a-z]+"'.format(re.escape(target)), text), (
        "setup-cloud-build.sh does not declare target " + target)


# ---------------------------------------------------------------------------
# The build identity's own provisioning (creation + role loops actually run)
# ---------------------------------------------------------------------------

def test_build_sa_creation_is_idempotent():
    """describe-then-create, not create-only.

    `gcloud iam service-accounts create` fails on an account that already
    exists, so a create-only script cannot be re-run against an existing
    project. Mutation: delete the `describe` guard -- red (a re-run
    against a provisioned project aborts before granting anything).
    """
    text = _script_text()
    assert "gcloud iam service-accounts describe" in text, (
        "no describe guard before creating polyglot-cloudbuild-sa")
    assert "gcloud iam service-accounts create" in text


def test_project_roles_are_actually_granted_not_just_declared():
    """PROJECT_ROLES is iterated by a real add-iam-policy-binding call.

    A role added to the array but never applied would satisfy every
    text-presence assertion in
    admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py while
    granting nothing. Mutation: delete the `for role in
    "${PROJECT_ROLES[@]}"` loop body's gcloud call -- red.
    """
    text = _script_text()
    assert re.search(r'for role in "\$\{PROJECT_ROLES\[@\]\}"', text), (
        "PROJECT_ROLES is declared but never iterated")
    assert re.search(
        r'gcloud projects add-iam-policy-binding "\$PROJECT"', text), (
        "no project-level add-iam-policy-binding call")


def test_actas_targets_are_actually_granted_not_just_declared():
    """ACTAS_TARGETS is iterated by a real
    service-accounts add-iam-policy-binding call, not merely declared.
    """
    text = _script_text()
    assert re.search(r'for target_sa in "\$\{ACTAS_TARGETS\[@\]\}"', text), (
        "ACTAS_TARGETS is declared but never iterated")
    assert re.search(
        r'gcloud iam service-accounts add-iam-policy-binding "\$target_sa"',
        text,
    ), "no per-target actAs add-iam-policy-binding call"


def test_dry_run_never_calls_gcloud():
    """--dry-run prints every command instead of running it.

    A dry run that still executes gcloud is worthless as a preview and
    dangerous as a default demo -- it would mutate a real project's IAM the
    first time anyone tried to inspect what this script does. Every gcloud
    invocation in the IAM section must be gated behind
    `[ "$DRY_RUN" = false ]` (mirroring the pre-existing trigger loop's own
    gate).
    """
    text = _script_text()
    iam_section_start = text.index("THE BUILD IDENTITY: polyglot-cloudbuild-sa")
    iam_section = text[iam_section_start:]
    gcloud_calls = re.findall(r'^\s*gcloud\b[^\n]*', iam_section, re.MULTILINE)
    # Every real (non-DRY-RUN-echoed) gcloud invocation in the IAM section
    # must appear only inside an `if [ "$DRY_RUN" = false ]` branch. We
    # approximate this by requiring that each such call's nearest preceding
    # "if [ "$DRY_RUN"" line (within 20 lines) says false, not true.
    lines = iam_section.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("gcloud "):
            continue
        # Walk backward for the governing DRY_RUN check.
        guard = None
        for j in range(i - 1, max(-1, i - 20), -1):
            if 'DRY_RUN" = false' in lines[j]:
                guard = "false"
                break
            if 'DRY_RUN" = true' in lines[j]:
                guard = "true"
                break
        assert guard == "false", (
            "a gcloud call in the IAM section is not gated behind "
            '`if [ "$DRY_RUN" = false ]`: {!r}'.format(stripped))
    assert gcloud_calls, (
        "no gcloud calls found in the IAM section -- this test would be "
        "vacuous")
