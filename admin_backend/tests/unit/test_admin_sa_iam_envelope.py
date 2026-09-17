"""What the DEPLOYED ADMIN service may ask Google Cloud for.

THE SIBLING of backend/tests/unit/test_deployed_iam_envelope.py, and the same
scar (CLAUDE.md scar #7): every test stubs the Google SDKs, so a stub happily
answers a call the real service account is FORBIDDEN to make. A mock proves
the code CALLS something; it cannot prove the caller is ALLOWED to.

THE TWO SERVICES ARE MIRROR IMAGES OF EACH OTHER. The public backend runs as
polyglot-backend-sa and is pinned at ZERO privileged Firebase Auth calls. This
service runs as admin-backend-sa and is ALLOWED to make them -- that is the
whole reason it exists. So this file does not re-assert "no privileged calls";
it pins the ENVELOPE instead:

  1. The role list admin-backend-sa actually holds, as a fixture constant kept
     in one-to-one agreement with scripts/setup-admin-service.sh. Offline --
     no token, no deploy, no network -- so it runs in CI on every change.
     Refreshed BY HAND when a role is added, in the same commit that adds it
     to the setup script and to the code that needs it (an unused grant is its
     own risk).
  2. admin_backend/ never imports backend.routes. The two services share
     business LOGIC (backend.services.*, backend.config), not HTTP surface.
     A route import would drag the public app's router registration -- and its
     narrow-SA assumptions -- into the privileged process.

WHY THE ROLE LIST IS PINNED AT ALL. A privileged call added to admin_backend/
whose role is not in this list fails with INSUFFICIENT_PERMISSION on the first
request in production, exactly as check_revoked did on 2026-08-26 -- past a
green suite, green CI, and a cross-surface pass. The list here is what makes
"does the runtime identity have this permission?" a question someone must
answer in the diff instead of after the deploy.
"""
import ast
import pathlib
import re

# The package root (admin_backend/), from this file at
# admin_backend/tests/unit/test_admin_sa_iam_envelope.py.
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent

ADMIN_SA_NAME = "admin-backend-sa"

# THE PIN. Every role admin-backend-sa holds, and the ONE reason each is
# granted. Refreshed by hand, in the same commit that grants it -- this is the
# offline mirror of `gcloud projects get-iam-policy <project>
# --flatten='bindings[].members'
# --filter='bindings.members:admin-backend-sa@...'
# --format='value(bindings.role)'`.
#
# Roles the plan DEFERS to the epic that first needs them are deliberately
# ABSENT: cloudbuild.builds.editor is the one still deferred (Epic 4 bead
# 4.3, admin_backend/services/cloud_build.py, not yet built -- the route
# that actually submits a build). errorreporting.viewer and monitoring.viewer
# were deferred here too until Epic 3 bead 8 (bd polyglot-pdf-e4dt8) shipped
# and moved them OUT of DEFERRED_ROLES into EXPECTED_ADMIN_SA_ROLES below
# (granted by scripts/setup-monitoring.sh, MONITORING_GRANTED_ROLES) -- their
# first real consumer is bd polyglot-pdf-mpebj's GET /admin/errors
# (admin_backend/services/error_stats.py); no route reads monitoring.viewer
# yet. iam.serviceAccountUser moved OUT of DEFERRED_ROLES the same way, into
# CLOUD_BUILD_SA_GRANTED_ROLES below (bead polyglot-pdf-p4ale, E4.5) -- its
# first consumer is the SAME bead-4.3 route, which needs actAs on
# polyglot-cloudbuild-sa to submit a build that runs as that identity even
# before the route itself exists to call it. run.admin and
# firebasehosting.admin are DELETED, not deferred: the admin service never
# deploys anything itself (Cloud Build does), so there is no future epic
# that grants either here. An unused grant is its own risk, so each
# genuinely-deferred role lands with its first consumer -- pinned by
# test_admin_sa_holds_no_deferred_role_early below.
#
# bigquery.jobUser + bigquery.dataViewer landed HERE (Epic 3 bead 6, E3.6):
# they are granted by scripts/setup-telemetry.sh, NOT
# scripts/setup-admin-service.sh's PROJECT_ROLES array (jobUser is
# project-level like the rest of PROJECT_ROLES, but dataViewer is scoped to
# the polyglot_telemetry DATASET, so both are provisioned by the same script
# that creates that dataset in the first place -- see
# test_telemetry_script_grants_admin_sa_bigquery_roles below, which reads
# setup-telemetry.sh directly instead of folding these into the
# PROJECT_ROLES pin test above).
EXPECTED_ADMIN_SA_ROLES = {
    # Create and disable users, and stamp the app_admin / firm_role custom
    # claims. This is the permission the public backend deliberately LACKS.
    "roles/firebaseauth.admin",
    # Firestore reads and writes: firms, the credit ledger, kits, links,
    # admin_audit_log, deployments, app_config.
    "roles/datastore.user",
    # Structured logs to Cloud Logging, same as the public backend.
    "roles/logging.logWriter",
    # Read the email-provider API key (and the link-signing secret) out of
    # Secret Manager.
    "roles/secretmanager.secretAccessor",
    # Run queries against the Epic 3 BigQuery telemetry views (cost/income
    # dashboards). Granted by scripts/setup-telemetry.sh, project-level like
    # a query job itself is not resource-scoped.
    "roles/bigquery.jobUser",
    # Read the polyglot_telemetry dataset ONLY (scripts/setup-telemetry.sh
    # grants this with `bq add-iam-policy-binding` on the dataset, not
    # `gcloud projects add-iam-policy-binding` -- see
    # test_telemetry_script_grants_jobuser_project_wide_and_dataviewer_on_dataset
    # below for why the SCOPE, not just the role name, is pinned).
    "roles/bigquery.dataViewer",
    # Read Cloud Error Reporting groupStats for the console's "errors per
    # channel" view (Epic 3 bead 8, E3.8). VIEWER, not writer or admin:
    # the console READS groups and never resolves or deletes them, and
    # the SERVICES report errors by writing logs (logging.logWriter,
    # which they already hold), not by calling this API. Granted by
    # scripts/setup-monitoring.sh.
    "roles/errorreporting.viewer",
    # Read the log-based metrics, the alert policies' firing state and
    # the uptime-check results for the console's health and alert views
    # (Epic 3 bead 8). Read-only: an operator changes a threshold by
    # re-running scripts/setup-monitoring.sh under their OWN credentials,
    # never through the console with the service's identity.
    "roles/monitoring.viewer",
    # actAs on polyglot-cloudbuild-sa: submit a build that runs AS that
    # identity (bead polyglot-pdf-p4ale, E4.5 -- the admin service's future
    # trigger route, bead 4.3, calls `builds.create`). Granted by
    # scripts/setup-admin-service.sh's CLOUD_BUILD_SA_ROLES array, scoped to
    # that ONE service account -- see
    # test_the_actas_role_is_scoped_to_the_cloud_build_sa_not_the_project below for why
    # the scope, not just the name, is pinned. This is the role CLAUDE.md's
    # scar #7 example is about: a project-wide grant here would let a
    # compromised admin-backend-sa credential impersonate every service
    # account in the project, not just the one build identity it is allowed
    # to submit builds as.
    "roles/iam.serviceAccountUser",
    # Submit/trigger a Cloud Build (bd polyglot-pdf-tb3kp, E4.3 --
    # admin_backend/services/cloud_build.py's run_target(), the FIRST and
    # ONLY caller of CloudBuildClient.run_build_trigger). Moved OUT of
    # DEFERRED_ROLES in this same commit: this is the role's first real
    # consumer, so granting it now (rather than leaving it deferred with no
    # caller) is exactly what "an unused grant is its own risk" argues
    # against continuing to defer.
    "roles/cloudbuild.builds.editor",
}

# Roles granted on ONE RESOURCE rather than project-wide. Kept apart from the
# project-level set above because the setup script grants them with a
# different gcloud command (`gcloud storage buckets add-iam-policy-binding`,
# not `gcloud projects add-iam-policy-binding`), and because the SCOPE is the
# security-relevant half: objectAdmin on the whole project would hand the
# admin service write access to every bucket, not just the kit store.
EXPECTED_ADMIN_SA_BUCKET_ROLES = {
    # Publish and retire form kits in the shared form-kits bucket ONLY. The
    # public backend holds objectViewer on the same bucket.
    "roles/storage.objectAdmin",
}

# The subset of EXPECTED_ADMIN_SA_ROLES granted by scripts/setup-telemetry.sh
# rather than scripts/setup-admin-service.sh's PROJECT_ROLES array. Kept
# separate so test_admin_sa_project_role_pin_matches_the_setup_script (which
# reads ONLY setup-admin-service.sh) can subtract these out instead of
# wrongly demanding that script grant BigQuery roles it does not touch.
# The subset granted by scripts/setup-monitoring.sh (Epic 3 bead 8).
# Named separately from TELEMETRY_GRANTED_ROLES so a reader can tell WHICH
# operator script provisions which role without opening both.
MONITORING_GRANTED_ROLES = {
    "roles/errorreporting.viewer",
    "roles/monitoring.viewer",
}

TELEMETRY_GRANTED_ROLES = {
    "roles/bigquery.jobUser",
    "roles/bigquery.dataViewer",
    # Granted by scripts/setup-monitoring.sh (Epic 3 bead 8), the sibling
    # that provisions the metrics/policies/uptime checks these two roles
    # exist to READ. Same reason as the BigQuery pair above: the role
    # lands with the script that creates the thing it reads, so
    # test_admin_sa_project_role_pin_matches_the_setup_script (which
    # reads ONLY setup-admin-service.sh) must subtract it out.
    "roles/errorreporting.viewer",
    "roles/monitoring.viewer",
}

# The subset of EXPECTED_ADMIN_SA_ROLES granted by setup-admin-service.sh's
# CLOUD_BUILD_SA_ROLES array (resource-scoped to polyglot-cloudbuild-sa),
# not its project-level PROJECT_ROLES array. Subtracted out for the same
# reason as TELEMETRY_GRANTED_ROLES and MONITORING_GRANTED_ROLES above:
# test_admin_sa_project_role_pin_matches_the_setup_script reads ONLY
# PROJECT_ROLES, so a role granted by a different array in the same script
# must be excluded from that comparison rather than wrongly demanded there.
CLOUD_BUILD_SA_GRANTED_ROLES = {
    "roles/iam.serviceAccountUser",
}

# Roles the plan defers to the epic that first needs them. Granting one early
# widens the blast radius of a compromise for a capability nothing calls.
#
# roles/iam.serviceAccountUser, roles/run.admin and roles/firebasehosting.
# admin -- all three DEFERRED here before bead polyglot-pdf-p4ale (E4.5) --
# are gone from this set now, but for two DIFFERENT reasons:
#   - roles/iam.serviceAccountUser is GRANTED (see
#     CLOUD_BUILD_SA_GRANTED_ROLES above): its first consumer, the admin
#     service's future build-trigger route (bead 4.3), needs actAs on
#     polyglot-cloudbuild-sa to submit a build that runs as that identity.
#   - roles/run.admin and roles/firebasehosting.admin are DELETED, not
#     granted: the admin service never deploys anything itself -- Cloud
#     Build does the deploying, as polyglot-cloudbuild-sa (see
#     scripts/setup-cloud-build.sh, which holds both). There is no future
#     epic that grants either to admin-backend-sa, so leaving them deferred
#     would keep a dead expectation this test could never satisfy.
# EMPTY as of bd polyglot-pdf-tb3kp (E4.3): roles/cloudbuild.builds.editor
# was the last deferred role, and it moved into EXPECTED_ADMIN_SA_ROLES
# above the moment its first real caller (cloud_build.py's run_target)
# shipped. Kept as an empty set, not deleted, so a FUTURE epic that defers
# a new role has a home to add it to without re-inventing this pattern --
# see test_admin_sa_holds_no_deferred_role_early below, which iterates
# whatever this set holds.
DEFERRED_ROLES = set()


def _setup_script_text() -> str:
    script = REPO_ROOT / "scripts" / "setup-admin-service.sh"
    assert script.is_file(), (
        "scripts/setup-admin-service.sh is missing. It is the script that "
        "provisions admin-backend-sa; without it this whole file asserts "
        "against nothing.")
    return script.read_text(encoding="utf-8")


def _named_array(text: str, name: str) -> set:
    """The quoted roles/... entries of a `<name>=( ... )` bash array.

    Parsed from the script rather than re-listed in this file, so the pin
    above and the script that actually provisions the SA cannot drift
    (CLAUDE.md scar #8: one rule, one home). The script is the thing an
    operator RUNS; the constants above are what a reviewer READS.
    """
    block = re.search(
        r"^{}=\((.*?)^\)".format(re.escape(name)), text,
        re.MULTILINE | re.DOTALL)
    assert block, (
        "scripts/setup-admin-service.sh has no {}=( ... ) array. That array "
        "is how this test learns what the SA is actually granted.".format(name))
    return set(re.findall(r'"(roles/[^"]+)"', block.group(1)))


def test_admin_sa_project_role_pin_matches_the_setup_script():
    """The hand-refreshed pin and the provisioning script name ONE role set.

    Fails on a role added to either side alone -- the case that otherwise
    ships: a new privileged call, a role quietly added to the setup script to
    make it work, and no reviewer ever asked whether the widening was
    intended.

    TELEMETRY_GRANTED_ROLES is subtracted out: those two roles are granted by
    scripts/setup-telemetry.sh (see
    test_telemetry_script_grants_admin_sa_bigquery_roles below), not by this
    script's PROJECT_ROLES array, so comparing the full envelope against
    setup-admin-service.sh alone would wrongly demand it grant BigQuery
    roles it never touches. CLOUD_BUILD_SA_GRANTED_ROLES is subtracted for
    the identical reason: roles/iam.serviceAccountUser is granted by this
    same script's CLOUD_BUILD_SA_ROLES array (resource-scoped to
    polyglot-cloudbuild-sa), not PROJECT_ROLES -- see
    test_admin_sa_actas_role_pin_matches_the_setup_script below for that
    array's own pin.
    """
    granted = _named_array(_setup_script_text(), "PROJECT_ROLES")
    expected = (
        EXPECTED_ADMIN_SA_ROLES
        - TELEMETRY_GRANTED_ROLES
        - CLOUD_BUILD_SA_GRANTED_ROLES
    )
    assert granted == expected, (
        "scripts/setup-admin-service.sh grants a different PROJECT-level role "
        "set than EXPECTED_ADMIN_SA_ROLES (minus the telemetry-script roles) "
        "pins."
        + chr(10) + "  only in the script: {}".format(
            sorted(granted - expected))
        + chr(10) + "  only in the pin:    {}".format(
            sorted(expected - granted))
        + chr(10) + "Widening admin-backend-sa is a deliberate act: add the "
          "role to BOTH, with the one-line justification saying which call "
          "needs it.")


def test_admin_sa_bucket_role_pin_matches_the_setup_script():
    """The resource-scoped grants, pinned separately from the project ones.

    storage.objectAdmin belongs on the form-kits bucket ONLY. Folding it into
    the project-level array would silently promote it to every bucket in the
    project, which no test keyed on the role NAME alone would notice.
    """
    granted = _named_array(_setup_script_text(), "BUCKET_ROLES")
    assert granted == EXPECTED_ADMIN_SA_BUCKET_ROLES, (
        "scripts/setup-admin-service.sh grants a different BUCKET-scoped role "
        "set than EXPECTED_ADMIN_SA_BUCKET_ROLES pins."
        + chr(10) + "  only in the script: {}".format(
            sorted(granted - EXPECTED_ADMIN_SA_BUCKET_ROLES))
        + chr(10) + "  only in the pin:    {}".format(
            sorted(EXPECTED_ADMIN_SA_BUCKET_ROLES - granted)))


def test_the_bucket_roles_are_granted_on_the_bucket_not_the_project():
    """The SCOPE of the bucket grants, not just their names.

    A role name is half the pin. Moving storage.objectAdmin from
    `gcloud storage buckets add-iam-policy-binding` to
    `gcloud projects add-iam-policy-binding` keeps every name-keyed assertion
    above green while handing the admin service write access to every bucket
    in the project.
    """
    text = _setup_script_text()
    for role in EXPECTED_ADMIN_SA_BUCKET_ROLES:
        # The role must appear in BUCKET_ROLES, and BUCKET_ROLES must be the
        # array the buckets command iterates.
        assert role in _named_array(text, "BUCKET_ROLES"), role
    assert re.search(
        r"BUCKET_ROLES\[@\]", text), (
        "BUCKET_ROLES is never iterated in setup-admin-service.sh -- the "
        "array is pinned by the test above but grants nothing.")
    assert re.search(
        r"gcloud\s+storage\s+buckets\s+add-iam-policy-binding", text), (
        "setup-admin-service.sh has no `gcloud storage buckets "
        "add-iam-policy-binding`, so the bucket-scoped roles are either "
        "ungranted or (worse) granted project-wide.")
    for role in EXPECTED_ADMIN_SA_BUCKET_ROLES:
        assert role not in _named_array(text, "PROJECT_ROLES"), (
            "{} is granted PROJECT-WIDE. It is meant to be scoped to the "
            "form-kits bucket only.".format(role))


def test_admin_sa_actas_role_pin_matches_the_setup_script():
    """The CLOUD_BUILD_SA_ROLES array grants exactly CLOUD_BUILD_SA_GRANTED_ROLES.

    Mirrors test_admin_sa_bucket_role_pin_matches_the_setup_script, but for
    the resource-scoped grant on polyglot-cloudbuild-sa rather than the
    form-kits bucket.
    """
    granted = _named_array(_setup_script_text(), "CLOUD_BUILD_SA_ROLES")
    assert granted == CLOUD_BUILD_SA_GRANTED_ROLES, (
        "scripts/setup-admin-service.sh grants a different actAs role set on "
        "polyglot-cloudbuild-sa than CLOUD_BUILD_SA_GRANTED_ROLES pins."
        + chr(10) + "  only in the script: {}".format(
            sorted(granted - CLOUD_BUILD_SA_GRANTED_ROLES))
        + chr(10) + "  only in the pin:    {}".format(
            sorted(CLOUD_BUILD_SA_GRANTED_ROLES - granted)))


def test_the_actas_role_is_scoped_to_the_cloud_build_sa_not_the_project():
    """The SCOPE of the actAs grant, not just its name.

    roles/iam.serviceAccountUser moved from `gcloud iam service-accounts
    add-iam-policy-binding polyglot-cloudbuild-sa@...` to `gcloud projects
    add-iam-policy-binding` would keep every name-keyed assertion above
    green while handing admin-backend-sa the ability to impersonate EVERY
    service account in the project -- exactly the CLAUDE.md scar #7 shape,
    on the grant side.
    """
    text = _setup_script_text()
    for role in CLOUD_BUILD_SA_GRANTED_ROLES:
        assert role in _named_array(text, "CLOUD_BUILD_SA_ROLES"), role
    assert re.search(
        r"CLOUD_BUILD_SA_ROLES\[@\]", text), (
        "CLOUD_BUILD_SA_ROLES is never iterated in setup-admin-service.sh -- "
        "the array is pinned by the test above but grants nothing.")
    assert re.search(
        r'gcloud\s+iam\s+service-accounts\s+add-iam-policy-binding\s+'
        r'"\$CLOUD_BUILD_SA"', text), (
        "setup-admin-service.sh has no `gcloud iam service-accounts "
        "add-iam-policy-binding \"$CLOUD_BUILD_SA\"` call, so the actAs "
        "role is either ungranted or (worse) granted project-wide.")
    for role in CLOUD_BUILD_SA_GRANTED_ROLES:
        assert role not in _named_array(text, "PROJECT_ROLES"), (
            "{} is granted PROJECT-WIDE. It is meant to be scoped to "
            "polyglot-cloudbuild-sa only.".format(role))


def _telemetry_script_text() -> str:
    script = REPO_ROOT / "scripts" / "setup-telemetry.sh"
    assert script.is_file(), (
        "scripts/setup-telemetry.sh is missing. It is the script that grants "
        "admin-backend-sa the two BigQuery roles this test pins.")
    return script.read_text(encoding="utf-8")


def test_telemetry_script_grants_admin_sa_bigquery_roles():
    """The two BigQuery roles admin-backend-sa needs to query the telemetry
    views (Epic 3 bead 6, E3.6) are actually granted, in
    scripts/setup-telemetry.sh -- not merely pinned as a name in
    EXPECTED_ADMIN_SA_ROLES with nothing on the other side actually granting
    them. Mutation: delete either add-iam-policy-binding call from
    setup-telemetry.sh -- red."""
    text = _telemetry_script_text()
    assert "roles/bigquery.jobUser" in text, (
        "setup-telemetry.sh does not grant roles/bigquery.jobUser to "
        "admin-backend-sa")
    assert "roles/bigquery.dataViewer" in text, (
        "setup-telemetry.sh does not grant roles/bigquery.dataViewer to "
        "admin-backend-sa")
    assert TELEMETRY_GRANTED_ROLES <= EXPECTED_ADMIN_SA_ROLES, (
        "TELEMETRY_GRANTED_ROLES must be a subset of EXPECTED_ADMIN_SA_ROLES "
        "-- a role granted by the telemetry script that the envelope pin "
        "does not expect is exactly the kind of drift this file exists to "
        "catch.")


def test_telemetry_script_grants_jobuser_project_wide_and_dataviewer_on_dataset():
    """The SCOPE of the two BigQuery grants, not just their names.

    jobUser must be granted with `gcloud projects add-iam-policy-binding`
    (running a query job is not a per-dataset action); dataViewer must be
    granted dataset-scoped, on the polyglot_telemetry dataset only, never
    project-wide (which would hand the admin service read access to every
    dataset in the project). bd polyglot-pdf-vzvio moved the dataViewer
    grant from `bq add-iam-policy-binding` to
    scripts/telemetry_bq_setup.py's grant-dataset-role subcommand (the
    BigQuery API's Dataset.access_entries) -- `bq` itself was exiting
    non-zero on at least one maintainer machine. Mutation: swap dataViewer
    onto `gcloud projects add-iam-policy-binding`, or drop the --dataset
    scoping from the grant-dataset-role call -- red."""
    text = _telemetry_script_text()
    assert re.search(
        r'gcloud projects add-iam-policy-binding\b(?:[^\n]*\n){1,5}?\s*'
        r'--role="roles/bigquery\.jobUser"',
        text,
    ), (
        "roles/bigquery.jobUser is not granted via `gcloud projects "
        "add-iam-policy-binding` -- it should be project-level, matching "
        "every other PROJECT_ROLES grant.")
    assert re.search(
        r'telemetry_bq_setup\.py" grant-dataset-role \\(?:[^\n]*\n){0,6}?[^\n]*'
        r'--dataset "\$DATASET"(?:[^\n]*\n){0,6}?[^\n]*'
        r'--role "roles/bigquery\.dataViewer"',
        text,
    ), (
        "roles/bigquery.dataViewer is not granted via telemetry_bq_setup.py "
        'grant-dataset-role with --dataset "$DATASET" -- it should be '
        "scoped to the polyglot_telemetry dataset, not the whole project.")
    # And the negative half: dataViewer must never appear on a
    # `gcloud projects add-iam-policy-binding` invocation, and `bq
    # add-iam-policy-binding` must not be INVOKED anywhere any more (a
    # backtick-quoted mention inside an explanatory comment is fine).
    project_binding_blocks = re.findall(
        r'gcloud projects add-iam-policy-binding.*?(?=\n\n|\Z)', text,
        re.DOTALL)
    for block in project_binding_blocks:
        assert "bigquery.dataViewer" not in block, (
            "roles/bigquery.dataViewer appears in a project-level "
            "add-iam-policy-binding call -- it must be dataset-scoped.")
    invocation_lines = [
        line for line in text.splitlines()
        if line.strip().startswith("bq add-iam-policy-binding")
    ]
    assert not invocation_lines, (
        "scripts/setup-telemetry.sh still INVOKES `bq "
        "add-iam-policy-binding` for a grant this test expects via the "
        "API helper: {}".format(invocation_lines))



def _monitoring_script_text() -> str:
    script = REPO_ROOT / "scripts" / "setup-monitoring.sh"
    assert script.is_file(), (
        "scripts/setup-monitoring.sh is missing. It is the script that grants "
        "admin-backend-sa the two monitoring roles this test pins.")
    return script.read_text(encoding="utf-8")


def test_monitoring_script_grants_admin_sa_the_two_monitoring_roles():
    """The two roles Epic 3 bead 8 moved out of DEFERRED_ROLES are
    actually GRANTED, in scripts/setup-monitoring.sh -- not merely added
    as names to EXPECTED_ADMIN_SA_ROLES with nothing on the other side
    granting them.

    This is the failure the whole file exists to prevent, in its
    least obvious form: moving a role out of the deferred set is the
    cheap half, and a pin that only checks the NAME would go green on
    that alone while the deployed SA still lacked the permission and
    every console call 403'd (CLAUDE.md scar #7). Mutation: delete either
    add-iam-policy-binding call from setup-monitoring.sh -- red.
    """
    text = _monitoring_script_text()
    for role in ("roles/errorreporting.viewer", "roles/monitoring.viewer"):
        assert role in text, (
            "setup-monitoring.sh does not grant {} to admin-backend-sa".format(role))
        # The prefix is NOT .format()ed: it contains a regex repetition
        # `{1,5}` that str.format would read as a field name and blow up on
        # (KeyError: '1,5'). Only the role half is substituted, then the two
        # are concatenated.
        pattern = (
            r'gcloud projects add-iam-policy-binding\b(?:[^\n]*\n){1,5}?\s*'
            + r'--role="' + re.escape(role) + r'"'
        )
        assert re.search(pattern, text), (
            "{} is not granted with `gcloud projects add-iam-policy-binding`. "
            "Error Reporting groups and Monitoring metrics are PROJECT-scoped "
            "resources, so unlike the BigQuery dataViewer grant there is no "
            "narrower scope available -- but the call still has to exist.".format(role))

    assert MONITORING_GRANTED_ROLES <= EXPECTED_ADMIN_SA_ROLES, (
        "MONITORING_GRANTED_ROLES must be a subset of EXPECTED_ADMIN_SA_ROLES.")


def test_monitoring_script_does_not_widen_the_public_backend_sa():
    """polyglot-backend-sa gains NOTHING from the monitoring script.

    It writes logs; it never reads a metric or an error group back.
    Granting it either role would widen the blast radius of a compromise
    for a capability nothing calls -- the exact shape CLAUDE.md scar #7
    is about, on the grant side rather than the call side.
    """
    assert "polyglot-backend-sa@" not in _monitoring_script_text(), (
        "scripts/setup-monitoring.sh references polyglot-backend-sa -- the "
        "public backend's identity must not gain monitoring read roles.")


def test_admin_sa_holds_no_deferred_role_early():
    """Roles the plan defers to Epic 3 / Epic 4 must not be granted yet.

    Pins the DEFERRAL, so adding one early is a decision someone makes in the
    open rather than a line nobody notices in a setup script.
    """
    text = _setup_script_text()
    granted = (
        _named_array(text, "PROJECT_ROLES")
        | _named_array(text, "BUCKET_ROLES")
        | _named_array(text, "CLOUD_BUILD_SA_ROLES")
    )
    granted_early = DEFERRED_ROLES & granted
    assert not granted_early, (
        "scripts/setup-admin-service.sh grants roles the plan defers to the "
        "epic that first needs them: {}. Each is supposed to land WITH its "
        "first consuming call, not ahead of it.".format(sorted(granted_early)))


def _admin_sources():
    """Every .py file the admin Cloud Run service can execute.

    Derived by EXCLUSION, exactly like the public backend's guard, so a NEW
    subpackage under admin_backend/ is covered the day it appears instead of
    the day someone remembers to add it.
    """
    not_deployed = {"tests", ".venv", "__pycache__"}
    for f in sorted(PACKAGE_ROOT.rglob("*.py")):
        rel = f.relative_to(REPO_ROOT)
        if any(part in not_deployed for part in rel.parts):
            continue
        yield f, rel


def _imported_modules(tree) -> set:
    """Every dotted module path this file imports, in both statement shapes.

    `import backend.routes.x`        -> {"backend.routes.x"}
    `from backend.routes import x`   -> {"backend.routes", "backend.routes.x"}

    A `from X import y` binds a name that may be a SUBMODULE or an attribute;
    emitting both the package and the dotted child means an exact-match check
    and a prefix check agree on every shape, instead of one of them silently
    covering less than the other.
    """
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                seen.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # A relative import resolves INSIDE admin_backend/ and can
                # never reach backend.routes.
                continue
            if node.module:
                seen.add(node.module)
                for alias in node.names:
                    if alias.name != "*":
                        seen.add("{}.{}".format(node.module, alias.name))
    return seen


def _reaches_backend_routes(module: str) -> bool:
    """One matching rule, shared by the production guard and its precision
    test below, so the two cannot drift into disagreeing about what counts.

    The dot in the prefix is load-bearing: without it a hypothetical
    `backend.routes_helpers` would be flagged as a route import.
    """
    return module == "backend.routes" or module.startswith("backend.routes.")


def test_admin_backend_never_imports_backend_routes():
    """The two services share business logic, not HTTP surface.

    backend.services.* and backend.config are the sanctioned shared code.
    backend.routes is not: importing a route module executes the public app's
    router construction inside the PRIVILEGED process, binding handlers that
    were written and reviewed against a narrow service account onto a wide one.
    """
    offenders = []
    for f, rel in _admin_sources():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for module in sorted(_imported_modules(tree)):
            if _reaches_backend_routes(module):
                offenders.append("{} imports {}".format(rel.as_posix(), module))

    assert not offenders, (
        "admin_backend/ imports the public backend's ROUTES:"
        + chr(10) + "  " + (chr(10) + "  ").join(sorted(offenders))
        + chr(10) + chr(10)
        + "Share backend.services.* / backend.config instead. If a route's "
          "logic is genuinely needed by both services, lift it into a service "
          "module and import THAT from both.")


def test_the_source_walk_actually_covers_the_admin_package():
    """The guard above is vacuous if _admin_sources() yields nothing.

    A scan that finds no files passes every "no offenders" assertion. Pin that
    it reaches the app module itself and skips this test tree, so a broken
    parents[] index or an over-eager exclusion fails HERE rather than turning
    the import guard into a no-op nobody notices.
    """
    scanned = {rel.as_posix() for _, rel in _admin_sources()}
    assert "admin_backend/main.py" in scanned, sorted(scanned)
    assert not any(part == "tests" for s in scanned for part in s.split("/")), (
        "the walk is picking up admin_backend/tests/, which does not ship")


def test_the_import_guard_matches_both_import_statement_shapes():
    """The matching rule itself, exercised against synthetic sources.

    Without this, a guard narrowed to one statement shape passes the
    production test above purely because no admin file happens to use the
    other shape yet -- and the day one does, the guard is silently absent.
    """
    def hits(src):
        return {m for m in _imported_modules(ast.parse(src))
                if _reaches_backend_routes(m)}

    # Every shape that DOES reach the public routers must be caught.
    assert hits("import backend.routes.link_routes\n")
    assert hits("from backend.routes import link_routes\n")
    assert hits("from backend.routes.link_routes import router\n")
    assert hits("import backend.routes\n")

    # The SANCTIONED shared imports must stay clean...
    assert hits("from backend.services import firms\n") == set()
    assert hits("from backend.config import get_settings\n") == set()
    assert hits("import backend.services.link_tokens\n") == set()
    # ...including a module whose name merely STARTS with the same letters,
    # which a prefix test written without the dot would wrongly flag.
    assert hits("import backend.routes_helpers\n") == set()
    assert hits("from backend.routes_helpers import x\n") == set()

    # A RELATIVE import inside admin_backend/ resolves within this package and
    # must never be misread as reaching the public routes.
    assert hits("from . import routes\n") == set()
    assert hits("from .services import admin_auth\n") == set()
