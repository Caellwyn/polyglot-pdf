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


def _real_gcloud_invocation(stripped: str):
    """Return the invocation text if `stripped` is a REAL, executing
    gcloud call, or None if it is not.

    Two shapes count as real calls: a bare `gcloud ...` command, and a
    command-substitution assignment like `VAR="$(gcloud ...)"` or
    `VAR=$(gcloud ...)` -- both actually run gcloud. An `echo "..."` line
    that merely mentions the word gcloud in a DRY-RUN preview string or an
    [ERROR] usage hint does NOT count: it never executes anything.
    (Fresh-eyes finding, bd polyglot-pdf-p4ale round 2: the old
    `stripped.startswith("gcloud ")` check required gcloud to be the
    line's first token, so the command-substitution shape --
    `PROJECT_NUMBER="$(gcloud projects describe ...)"`, a real, executing
    call sitting in the Pub/Sub block -- was invisible to the gate
    detector. A mutation that pulled that exact line out of its
    `if [ "$DRY_RUN" = false ]` guard produced zero violations.)
    """
    if stripped.startswith("gcloud "):
        return stripped
    match = re.match(r'^[A-Za-z_][A-Za-z0-9_]*="?\$\((gcloud\b.*)', stripped)
    if match:
        return match.group(1)
    return None


def _iam_section_gcloud_gate_violations(iam_section: str):
    """Structurally walk the IAM section's if/else/fi nesting and return
    every real gcloud call (see `_real_gcloud_invocation`) NOT lexically
    inside an active `if [ "$DRY_RUN" = false ]` (or
    `if [ "$DRY_RUN" = true ]` -> else) branch.

    Unlike a fixed-window backward text search, this tracks actual if/fi
    nesting depth with a stack, so a call is only considered "gated" when
    it sits between the governing `if` and its OWN matching `fi` -- a
    gcloud call placed shortly after an unrelated, already-closed guard
    (rather than inside it) is correctly reported as ungated. (Fresh-eyes
    finding, bd polyglot-pdf-p4ale round 1: the old 20-line backward
    lookback matched the Pub/Sub block's already-closed `if` for a mutated
    call inserted right after that block's own `fi`.)

    Frame shape: [dry_run_guard, in_then] where dry_run_guard is
    "false"/"true"/None (None = an ordinary if, e.g. the nested
    `if ! gcloud ... describe` existence check, which inherits its
    enclosing frame's gating rather than gating anything itself) and
    in_then flips to False after an `else` at that nesting depth.
    """
    violations = []
    stack = []  # list of [dry_run_guard, in_then]
    lines = iam_section.splitlines()
    if_re = re.compile(r'^\s*if\b')
    dry_run_false_re = re.compile(r'DRY_RUN"\s*=\s*false')
    dry_run_true_re = re.compile(r'DRY_RUN"\s*=\s*true')
    else_re = re.compile(r'^\s*else\b')
    fi_re = re.compile(r'^\s*fi\b')

    def currently_gated_false():
        for guard, in_then in stack:
            if guard == "false" and in_then:
                return True
            if guard == "true" and not in_then:
                return True
        return False

    for line in lines:
        stripped = line.strip()
        if if_re.match(line):
            if dry_run_false_re.search(line):
                stack.append(["false", True])
            elif dry_run_true_re.search(line):
                stack.append(["true", True])
            else:
                stack.append([None, True])
            continue
        if else_re.match(line) and stack:
            stack[-1][1] = False
            continue
        if fi_re.match(line) and stack:
            stack.pop()
            continue
        invocation = _real_gcloud_invocation(stripped)
        if invocation is not None and not currently_gated_false():
            violations.append(invocation)
    return violations


def test_dry_run_never_calls_gcloud():
    """--dry-run prints every command instead of running it.

    A dry run that still executes gcloud is worthless as a preview and
    dangerous as a default demo -- it would mutate a real project's IAM the
    first time anyone tried to inspect what this script does. Every gcloud
    invocation in the IAM section must be gated behind
    `[ "$DRY_RUN" = false ]` (mirroring the pre-existing trigger loop's own
    gate).

    Mutation: insert an ungated `gcloud ...` call anywhere in the IAM
    section -- including right after an unrelated, already-closed
    `if [ "$DRY_RUN" = false ]; ... fi` block (not just inside one), or as
    an ungated `VAR="$(gcloud ...)"` command-substitution assignment
    (round 2's exact gap: moving the Pub/Sub block's
    `PROJECT_NUMBER="$(gcloud projects describe ...)"` line above its
    guarding `if`) -- red.
    """
    text = _script_text()
    iam_section_start = text.index("THE BUILD IDENTITY: polyglot-cloudbuild-sa")
    iam_section = text[iam_section_start:]
    gcloud_calls = re.findall(r'^\s*gcloud\b[^\n]*', iam_section, re.MULTILINE)
    violations = _iam_section_gcloud_gate_violations(iam_section)
    assert not violations, (
        "gcloud call(s) in the IAM section are not lexically inside an "
        'active `if [ "$DRY_RUN" = false ]` branch: {!r}'.format(violations))
    assert gcloud_calls, (
        "no gcloud calls found in the IAM section -- this test would be "
        "vacuous")
