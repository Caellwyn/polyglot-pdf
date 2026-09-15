"""scripts/audit/infra_posture.sh's shipped check list (sprint 23 workstream
D, bd polyglot-pdf-m1dlv).

This is a READ-ONLY, OPERATOR-RUN script -- no deploy pipeline runs it, and
no CI step executes gcloud/bq/firebase against a live project -- so the only
mechanical guard available is pinning the SHIPPED SCRIPT TEXT, matching
tests/test_setup_monitoring_script.py's own pattern (that file's own
docstring: "the only mechanical guard is pinning the SHIPPED SCRIPT TEXT").

WHY THE CHECK LIST IS PINNED AT ALL. The bead's own contract is "every check
ends PASS, FAIL, or N/A: <reason> -- never a silent skip". A silent skip is
invisible from the OUTPUT alone (nothing prints, nothing is missing that a
casual reader would notice), so the only way to catch a removed check is to
assert its NAME still appears in the script text (CLAUDE.md scar #8:
enumerate the set, then pin the set, not the instance).

WHAT COUNTS AS ONE CHECK. Some checks are declared with a literal `record
"name" ...` call; others are declared with a bash variable that is
INTERPOLATED into the check name at runtime (`record "${prefix}_roles" ...`,
`record "cloud_run_${service}_..." ...`, `record "secret_manager_${secret}_
iam" ...`, `record "hosting_${site}_headers" ...`). For the templated
checks, the PIN is the template string appearing verbatim in the script
(e.g. `cloud_run_${service}_ingress`), not the fully-expanded per-instance
name -- the set of SERVICES/secrets/sites those templates iterate over is
pinned separately, so a check disappearing from EITHER axis (a template
removed, or a member removed from the set a template iterates) is caught.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "audit" / "infra_posture.sh"


def _script_text() -> str:
    assert SCRIPT.is_file(), (
        "scripts/audit/infra_posture.sh is missing. It is the script this "
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
        "non-ASCII byte(s) in infra_posture.sh at offsets " + repr(bad[:5]))


def test_script_requires_a_project_argument():
    """Mutation: drop the PROJECT_ID empty-check / exit 1 -- red.

    Without --project, every gcloud/bq/firebase call below would run against
    whatever project the operator's tool happens to be pointed at.
    """
    text = _script_text()
    assert "--project" in text
    assert re.search(r'if \[ -z "\$PROJECT_ID" \]', text), (
        "no guard on a missing --project")
    assert "exit 1" in text


def test_script_refuses_the_dead_production_project():
    """polyglot-forms-919f2 is unreachable (deploy-production.sh refuses to
    run against it too, bd polyglot-pdf-je6iy) -- auditing it would just
    enumerate permission errors against a project nothing serves."""
    text = _script_text()
    assert "polyglot-forms-919f2" in text
    assert re.search(r'if \[ "\$PROJECT_ID" = "polyglot-forms-919f2" \]', text)


def test_script_never_mutates():
    """Read-only means read-only: none of these gcloud/bq/firebase verbs may
    appear as a COMMAND (not merely as prose in a comment). A regex over
    bare command names is deliberately loose -- false positives (flagging a
    comment) are the safe failure direction for a check whose whole job is
    catching a live-changing call before it ships.
    """
    text = _script_text()
    # Strip comment lines before scanning, so a comment that MENTIONS a
    # forbidden verb (e.g. explaining why a mutation is out of scope) does
    # not itself trip this guard.
    code_lines = [
        line for line in text.splitlines()
        if not line.strip().startswith("#")
    ]
    code_text = "\n".join(code_lines)

    forbidden_patterns = [
        r"\bgcloud\s+\S+\s+\S*\bupdate\b",
        r"\bgcloud\s+\S+\s+\S*\bcreate\b",
        r"\bgcloud\s+\S+\s+\S*\bdelete\b",
        r"add-iam-policy-binding",
        r"remove-iam-policy-binding",
        r"\bbq\s+update\b",
        r"\bbq\s+rm\b",
        r"\bbq\s+mk\b",
        r"firebase\s+deploy\b",
    ]
    offenders = []
    for pattern in forbidden_patterns:
        if re.search(pattern, code_text):
            offenders.append(pattern)
    assert not offenders, (
        "infra_posture.sh contains a MUTATING call, which violates its "
        "read-only contract: " + repr(offenders))


def test_script_disables_interactive_prompts():
    """A gcloud call that would prompt (e.g. org-policies describe offering
    to enable an API) must never block on stdin under an unattended run.
    Mutation: delete this line -- the org-policy check then hangs the first
    time it hits a disabled API, rather than reporting N/A.
    """
    text = _script_text()
    assert "CLOUDSDK_CORE_DISABLE_PROMPTS=1" in text


def test_script_never_lets_pipestatus_read_the_wrong_command():
    """run_capture must read $? directly off the captured command, never
    PIPESTATUS after the fact.

    PIPESTATUS[0] read on the line AFTER a `var=$(cmd | filter)` assignment
    reflects the ASSIGNMENT's own pipeline, not `cmd`'s exit code -- verified
    empirically during this bead's own dry run (`gcloud org-policies
    describe` exits 1 on a disabled API, but a `${PIPESTATUS[0]}` read after
    the substitution read 0, so a real failure was recorded as PASS). This
    guards against reintroducing that exact trap.
    """
    text = _script_text()
    # Comments are allowed to MENTION PIPESTATUS while explaining why it is
    # not used (this script's own run_capture docstring does exactly that);
    # only an actual reference to the bash array (`$PIPESTATUS` / a bare
    # `PIPESTATUS[` subscript) is the trap.
    code_lines = [
        line for line in text.splitlines() if not line.strip().startswith("#")
    ]
    code_text = "\n".join(code_lines)
    assert "PIPESTATUS" not in code_text, (
        "run_capture (or some other capture site) uses PIPESTATUS, which "
        "reads the wrong command's exit status once read outside the "
        "pipeline that produced it -- capture $? directly instead")


def test_run_capture_strips_carriage_returns():
    """gcloud/bq on Windows emit CRLF line endings, which are invisible in
    an echoed line but break every downstream string/set comparison in this
    script. Mutation: delete the \\r stripping -- backend_sa_roles and
    friends go red against a live Windows gcloud despite matching sets.
    """
    text = _script_text()
    assert r"${raw//$'\r'/}" in text or "tr -d '\\r'" in text, (
        "no \\r stripping found in the output-capture path")


def test_script_gates_json_parsing_on_actual_json():
    """A gcloud/bq exit code of 0 is not proof of a JSON payload -- this
    bead's own dry run hit `bq show` exiting 0 while printing
    'ERROR: (bq) python3.14: command not found' to stdout, which a naive
    `if [ $_last_status -ne 0 ]` gate would feed straight to a python -c
    JSON parser and leak a raw traceback into the results table. Every
    python-parsed check must go through the is_valid_json gate.
    """
    text = _script_text()
    assert "is_valid_json()" in text
    assert text.count("is_valid_json") >= 10, (
        "is_valid_json is defined but not used at most JSON-parsing call "
        "sites -- a stray gate omission reintroduces the leaked-traceback "
        "failure mode this function exists to prevent")


# ---------------------------------------------------------------------------
# The full check list -- every literal or templated `record "..."` name.
# ---------------------------------------------------------------------------

# Checks declared with a LITERAL name (record "check_name" ...).
LITERAL_CHECKS = (
    "project_iam_policy_readable",
    "project_iam_policy_human_owner_editor",
    "backend_sa_no_firebaseauth_role",
    "admin_sa_bucket_role",
    "admin_sa_bucket_role_not_project_wide",
    "admin_sa_actas_cloud_build",
    "cloud_run_services_list",
    "cloud_run_unexpected_service",
    "secret_manager_list",
    "bucket_no_allusers",
    "bucket_public_access_prevention",
    "bucket_uniform_access",
    "bucket_object_anomalies",
    "firestore_rules_byte_equal",
    "firestore_ttl_policies",
    "firestore_pitr",
    "firestore_backup_schedules",
    "logging_default_bucket_retention",
    "logging_sinks_list",
    "logging_exclusion_ws_token_present",
    "logging_data_access_audit_config",
    "bigquery_dataset_acl",
    "bigquery_table_expiration",
    "admin_sa_bigquery_dataviewer_dataset_scoped",
    "firebase_auth_authorized_domains",
    "firebase_auth_email_enumeration_protection",
    "firebase_auth_providers",
    "firebase_auth_mfa_admin_editor",
    "firebase_auth_password_policy",
    "firebase_auth_export_settings",
    "vulnerability_scan_status",
    "vulnerability_scan_findings",
    "base_image_age",
    "cloud_build_log_content",
    "cloud_build_logs_bucket_acl",
    "vertex_abuse_monitoring_optout",
    "cloud_tts_data_use_setting",
)

# Checks declared via check_sa_roles(), whose name is "${prefix}_roles" --
# the PIN here is the prefix each call site actually passes.
SA_ROLE_CHECK_PREFIXES = (
    "backend_sa",
    "admin_sa_project",
    "cloudbuild_sa",
)

# Checks declared inside check_service_env(), templated on "${service}".
PER_SERVICE_CHECK_SUFFIXES = (
    "describe",
    "no_secret_shaped_env",
    "no_forbidden_flags",
    "no_verbosity_knobs",
    "secret_bindings",
    "ingress",
    "scaling",
    "runtime_sa",
    "env_var_names",
)

# Checks declared inside the Secret Manager loop, templated on "${secret}".
SECRET_MANAGER_TEMPLATE = 'record "secret_manager_${secret}_iam"'

# Checks declared inside the Hosting headers loop, templated on "${site}".
HOSTING_TEMPLATE = 'record "hosting_${site}_headers"'


@pytest.mark.parametrize("check", LITERAL_CHECKS)
def test_literal_check_is_present(check):
    text = _script_text()
    assert 'record "{}"'.format(check) in text, (
        "infra_posture.sh no longer declares the check " + check)


@pytest.mark.parametrize("prefix", SA_ROLE_CHECK_PREFIXES)
def test_service_account_role_check_is_wired(prefix):
    """Each SA-envelope check is both DEFINED (check_sa_roles is called with
    this prefix) and the check_sa_roles function itself still emits
    "${prefix}_roles" -- two separate things, since a renamed helper
    function that no call site actually reaches would satisfy a naive
    substring check on the CALL alone.
    """
    text = _script_text()
    assert 'check_sa_roles "{}"'.format(prefix) in text, (
        "no check_sa_roles call for prefix " + prefix)
    assert 'record "${prefix}_roles"' in text, (
        "check_sa_roles no longer records ${prefix}_roles")


def test_no_undeclared_sa_role_check_prefixes():
    """The SET of check_sa_roles call sites, pinned (CLAUDE.md scar #8) --
    a fourth SA envelope check added without updating this pin is exactly
    the silent-drift shape scar #8 exists to catch.
    """
    text = _script_text()
    called = re.findall(r'check_sa_roles "([a-zA-Z0-9_]+)"', text)
    assert set(called) == set(SA_ROLE_CHECK_PREFIXES), (
        "the check_sa_roles call sites in infra_posture.sh ({}) are not the "
        "set this test pins ({})".format(
            sorted(called), sorted(SA_ROLE_CHECK_PREFIXES)))


@pytest.mark.parametrize("suffix", PER_SERVICE_CHECK_SUFFIXES)
def test_per_service_check_template_is_present(suffix):
    text = _script_text()
    assert 'record "cloud_run_${{service}}_{}"'.format(suffix) in text, (
        "check_service_env no longer records cloud_run_${{service}}_{}"
        .format(suffix))


def test_no_undeclared_per_service_check_suffixes():
    """The SET of per-Cloud-Run-service checks, pinned."""
    text = _script_text()
    found = set(re.findall(r'record "cloud_run_\$\{service\}_([a-z_]+)"', text))
    assert found == set(PER_SERVICE_CHECK_SUFFIXES), (
        "the cloud_run_${{service}}_* checks in infra_posture.sh ({}) are "
        "not the set this test pins ({})".format(
            sorted(found), sorted(PER_SERVICE_CHECK_SUFFIXES)))


def test_known_services_set_is_pinned():
    """The THREE Cloud Run services check_service_env is actually called
    for -- a fourth service silently added to KNOWN_SERVICES without a
    reviewer noticing is exactly the shape cloud_run_unexpected_service
    exists to catch from the LIVE side; this pins the SCRIPT's own
    declared side.
    """
    text = _script_text()
    match = re.search(r'KNOWN_SERVICES="([^"]+)"', text)
    assert match, "KNOWN_SERVICES is not declared as a literal string"
    services = set(match.group(1).split())
    assert services == {
        "polyglot-backend", "polyglot-backend-staging", "polyglot-admin",
    }


def test_secret_manager_iam_check_is_templated():
    text = _script_text()
    assert SECRET_MANAGER_TEMPLATE in text, (
        "the per-secret IAM check template is missing or renamed")


def test_hosting_headers_check_is_templated():
    text = _script_text()
    assert HOSTING_TEMPLATE in text, (
        "the per-site Hosting headers check template is missing or renamed")


def test_hosting_sites_set_is_pinned():
    """The FIVE Hosting sites this repo actually serves (firebase.json /
    .firebaserc), so a sixth site added to the project without updating
    this script (and this pin) goes unaudited silently.
    """
    text = _script_text()
    match = re.search(r'HOSTING_SITES="([^"]+)"', text)
    assert match, "HOSTING_SITES is not declared as a literal string"
    sites = set(match.group(1).split())
    assert sites == {
        "polyglot-demo-aa709",
        "polyglot-app-staging",
        "polyglot-editor-demo",
        "polyglot-admin-demo",
        "polyglot-admin-candidate",
    }


def test_required_hosting_headers_set_is_pinned():
    """The header NAMES the audit checks for, pinned so a header silently
    dropped from REQUIRED_HEADERS (weakening the check without anyone
    noticing) fails here instead of just producing quieter output.
    """
    text = _script_text()
    match = re.search(r'REQUIRED_HEADERS="([^"]+)"', text)
    assert match, "REQUIRED_HEADERS is not declared as a literal string"
    headers = set(match.group(1).split())
    assert headers == {
        "content-security-policy",
        "strict-transport-security",
        "x-frame-options",
        "referrer-policy",
    }


# ---------------------------------------------------------------------------
# The IAM role pins -- corroborated against the offline envelope tests.
# ---------------------------------------------------------------------------

def test_backend_sa_expected_roles_match_the_offline_envelope_docstring():
    """backend_sa_no_firebaseauth_role and the backend_sa_roles check must
    assert against the SAME role set
    backend/tests/unit/test_deployed_iam_envelope.py's own module docstring
    states for polyglot-backend-sa -- a drift between the two pins is
    exactly the "same rule stated twice, diverges silently" shape CLAUDE.md
    scar #8 warns about.
    """
    script_text = _script_text()
    envelope_text = (
        REPO_ROOT / "backend" / "tests" / "unit"
        / "test_deployed_iam_envelope.py"
    ).read_text(encoding="utf-8")

    match = re.search(r'BACKEND_SA_EXPECTED_ROLES="([^"]+)"', script_text)
    assert match, "BACKEND_SA_EXPECTED_ROLES is not declared as a literal string"
    script_roles = set(match.group(1).split())

    # The docstring's own prose writes the five roles WITHOUT the "roles/"
    # prefix ("...narrow (aiplatform.user, datastore.user, logging.
    # logWriter, secretmanager.secretAccessor, storage.objectViewer)"), so
    # this strips the same prefix off the script's pin before comparing --
    # matching the docstring's own words is the point, not re-deriving a
    # prefix convention the docstring never uses.
    docstring_bare_roles = set(
        re.findall(r"\b[a-zA-Z]+\.[a-zA-Z]+\b", envelope_text))
    script_bare_roles = {r.split("roles/", 1)[-1] for r in script_roles}
    assert script_bare_roles <= docstring_bare_roles, (
        "infra_posture.sh's BACKEND_SA_EXPECTED_ROLES names a role "
        "test_deployed_iam_envelope.py's docstring does not: {}".format(
            sorted(script_bare_roles - docstring_bare_roles)))
    assert script_roles == {
        "roles/aiplatform.user",
        "roles/storage.objectViewer",
        "roles/logging.logWriter",
        "roles/datastore.user",
        "roles/secretmanager.secretAccessor",
    }


def test_admin_sa_project_roles_match_the_offline_envelope_constant():
    """ADMIN_SA_EXPECTED_PROJECT_ROLES must equal the REAL
    admin_backend/tests/unit/test_admin_sa_iam_envelope.py's
    EXPECTED_ADMIN_SA_ROLES constant, minus the two roles that are scoped
    OFF the project level and checked separately in this same script:
    `bigquery.dataViewer` (dataset-scoped -- see
    admin_sa_bigquery_dataviewer_dataset_scoped) and
    `iam.serviceAccountUser` (resource-scoped onto polyglot-cloudbuild-sa --
    see admin_sa_actas_cloud_build).

    Before this test, the pin here was a HAND-TYPED literal with no drift
    guard at all -- the backend list is checked against the envelope
    docstring's own prose (test_backend_sa_expected_roles_match_the_offline_
    envelope_docstring above) and the cloudbuild list is regex-parsed out of
    setup-cloud-build.sh (test_cloudbuild_sa_expected_roles_match_setup_
    cloud_build_script below), but this was the one of the three role lists
    with NO check against its source of truth: a role added to (or removed
    from) EXPECTED_ADMIN_SA_ROLES without a matching edit here would drift
    silently forever. IMPORTS the real constant (a plain Python set, unlike
    setup-cloud-build.sh's bash array, which has no importable form and so
    must be regex-parsed) rather than re-typing it a second time.
    """
    # Imported here rather than at module scope: this is the ONE test in
    # the file that needs admin_backend on sys.path, and importing a test
    # MODULE (not a package __init__) from another suite is unusual enough
    # to want that scoped rather than a standing top-of-file import that
    # every other test in this file would carry for no reason.
    from admin_backend.tests.unit import test_admin_sa_iam_envelope as envelope

    text = _script_text()
    match = re.search(r'ADMIN_SA_EXPECTED_PROJECT_ROLES="([^"]+)"', text)
    assert match, "ADMIN_SA_EXPECTED_PROJECT_ROLES is not declared as a literal string"
    script_roles = set(match.group(1).split())

    assert "roles/bigquery.dataViewer" not in script_roles, (
        "ADMIN_SA_EXPECTED_PROJECT_ROLES includes the dataset-scoped "
        "bigquery.dataViewer role, which a project-level IAM query will "
        "never see -- it belongs in the separate dataset-scoped check")
    assert "roles/iam.serviceAccountUser" not in script_roles, (
        "ADMIN_SA_EXPECTED_PROJECT_ROLES includes the resource-scoped "
        "iam.serviceAccountUser actAs grant, which a project-level IAM "
        "query will never see -- it belongs in the separate "
        "admin_sa_actas_cloud_build check")

    expected = envelope.EXPECTED_ADMIN_SA_ROLES - {
        "roles/bigquery.dataViewer",
        "roles/iam.serviceAccountUser",
    }
    assert script_roles == expected, (
        "infra_posture.sh's ADMIN_SA_EXPECTED_PROJECT_ROLES ({}) does not "
        "match admin_backend/tests/unit/test_admin_sa_iam_envelope.py's "
        "EXPECTED_ADMIN_SA_ROLES minus the dataset/resource-scoped roles "
        "({})".format(sorted(script_roles), sorted(expected)))


def test_cloudbuild_sa_expected_roles_match_setup_cloud_build_script():
    """The CLOUD_BUILD_SA_EXPECTED_ROLES pin here must equal
    scripts/setup-cloud-build.sh's own PROJECT_ROLES array -- the script
    that actually provisions polyglot-cloudbuild-sa.
    """
    script_text = _script_text()
    setup_text = (REPO_ROOT / "scripts" / "setup-cloud-build.sh").read_text(
        encoding="utf-8")

    match = re.search(r'CLOUD_BUILD_SA_EXPECTED_ROLES="([^"]+)"', script_text)
    assert match, "CLOUD_BUILD_SA_EXPECTED_ROLES is not declared as a literal string"
    pinned_roles = set(match.group(1).split())

    setup_block = re.search(
        r"PROJECT_ROLES=\((.*?)^\)", setup_text, re.MULTILINE | re.DOTALL)
    assert setup_block, "setup-cloud-build.sh has no PROJECT_ROLES=( ... ) array"
    setup_roles = set(re.findall(r'"(roles/[^"]+)"', setup_block.group(1)))

    assert pinned_roles == setup_roles, (
        "infra_posture.sh's CLOUD_BUILD_SA_EXPECTED_ROLES ({}) does not "
        "match scripts/setup-cloud-build.sh's PROJECT_ROLES ({})".format(
            sorted(pinned_roles), sorted(setup_roles)))


# ---------------------------------------------------------------------------
# The forbidden-flag / verbosity-knob sets -- pinned against the bead text.
# ---------------------------------------------------------------------------

def test_forbidden_flags_set_is_pinned():
    text = _script_text()
    assert 'FORBIDDEN_FLAGS = {("VFF_DISABLE_AUTH", "true"), ("VERTEXAI", "false")}' in text


def test_verbosity_knobs_set_is_pinned():
    """HTTPX_LOG_LEVEL, GOOGLE_GENAI_* (a prefix, checked separately),
    SEND_TRANSCRIPT, DEV_LOGGING_ENABLED -- the exact set the bead names.
    """
    text = _script_text()
    assert 'VERBOSITY_KNOBS = {"HTTPX_LOG_LEVEL", "SEND_TRANSCRIPT", "DEV_LOGGING_ENABLED"}' in text
    assert 'GOOGLE_GENAI_' in text


def test_git_sha_is_allowlisted_against_the_secret_shaped_heuristic():
    """A 40-char git commit SHA matches the same length/charset heuristic as
    a real secret -- GIT_SHA is deployed in plain env vars ON PURPOSE
    (docs/components/config-deployment.md's GET /version section) and would
    otherwise show up as a permanent false-positive FAIL on every service.
    Mutation: remove GIT_SHA from NAME_ALLOWLIST -- this dry-run's own
    output goes from 3 clean PASSes to 3 FAILs with no underlying change.
    """
    text = _script_text()
    assert 'NAME_ALLOWLIST = {"GIT_SHA"}' in text


# ---------------------------------------------------------------------------
# Mutation-verification harness (scar #9: prove the pin can fail).
# ---------------------------------------------------------------------------

def test_removing_a_check_line_fails_the_literal_check_pin(tmp_path):
    """Prove test_literal_check_is_present can actually go red: delete one
    `record "..."` call from a SCRATCH COPY and confirm the corresponding
    assertion would fail against that mutated text -- never against the
    real, unmutated script (CLAUDE.md scar #9's own "revert the fix and
    watch it fail" rule, applied to a text-pin instead of a code path).
    """
    original = _script_text()
    victim = "bucket_public_access_prevention"
    assert 'record "{}"'.format(victim) in original, (
        "fixture assumption failed: the check this mutation test removes "
        "is not present in the real script")

    mutated = original.replace('record "{}"'.format(victim), 'record "_removed_"')
    assert 'record "{}"'.format(victim) not in mutated, (
        "the mutation did not actually remove the check line")

    # Re-run the exact assertion test_literal_check_is_present makes, but
    # against the MUTATED text -- confirms the check-text pin is capable of
    # catching a removed check, not merely capable of matching the current
    # (unmutated) script by coincidence.
    assert 'record "{}"'.format(victim) not in mutated


def test_removing_the_sa_role_prefix_fails_its_pin():
    """Same mutation-verification shape, for a check_sa_roles call site."""
    original = _script_text()
    victim = 'check_sa_roles "cloudbuild_sa"'
    assert victim in original
    mutated = original.replace(victim, 'check_sa_roles "_removed_"')
    called = set(re.findall(r'check_sa_roles "([a-zA-Z0-9_]+)"', mutated))
    assert called != set(SA_ROLE_CHECK_PREFIXES), (
        "the mutated text still matches the pinned SA role prefix set -- "
        "the pin would not have caught this removal")
