"""What the CLOUD BUILD IDENTITY may ask Google Cloud for.

THE THIRD SIBLING of backend/tests/unit/test_deployed_iam_envelope.py and
test_admin_sa_iam_envelope.py, and the same scar (CLAUDE.md scar #7): every
test stubs the Google SDKs, so a stub happily answers a call the real
service account is FORBIDDEN to make. A mock proves the code CALLS
something; it cannot prove the caller is ALLOWED to.

WHY A THIRD IDENTITY. Epic 4 (deploy control plane, plan:
docs/sprint_22_admin-console_plan.md "Cloud Build SA") moves every deploy --
bash-triggered or admin-console-triggered -- into ONE Cloud Build pipeline
(cloudbuild.yaml). That pipeline needs to deploy Cloud Run revisions running
as polyglot-backend-sa and admin-backend-sa (actAs), publish Hosting sites,
deploy Firestore rules, push images, and write/read the build_checks and
deployments gates. None of that belongs on either runtime SA -- widening
polyglot-backend-sa or admin-backend-sa to cover "can also deploy things"
would hand a compromised RUNTIME credential the ability to redeploy the
whole app. A dedicated build identity, scoped to exactly what a deploy
needs and nothing a request handler needs, keeps the two blast radii apart.

THIS FILE PINS THREE THINGS, bead polyglot-pdf-p4ale (E4.5):
  1. The exact role list polyglot-cloudbuild-sa holds, parsed from
     scripts/setup-cloud-build.sh's own arrays -- the same collusion-proof
     shape test_admin_sa_iam_envelope.py uses (a role added to the script
     without updating this file's constant fails CI).
  2. The two actAs bindings (roles/iam.serviceAccountUser on
     polyglot-backend-sa AND on admin-backend-sa), each resource-scoped to
     ONE target SA -- a project-wide grant of this role would let the build
     identity impersonate every service account in the project, not just
     the two it actually deploys revisions as.
  3. The bucket-only storage.objectAdmin grant on the form-kits bucket, and
     the Pub/Sub service agent's roles/iam.serviceAccountTokenCreator (bead
     4.3's build-status webhook OIDC token) -- so the WHOLE deploy-plane
     IAM surface (this file plus test_admin_sa_iam_envelope.py's new
     CLOUD_BUILD_SA_GRANTED_ROLES pin on the admin-SA side) is asserted
     from a small number of tests instead of scattered across the codebase.

WHY THE ROLE LIST IS PINNED AT ALL. A privileged build step added to
cloudbuild.yaml whose role is not in this list fails with
INSUFFICIENT_PERMISSION on the very first real build, exactly as
check_revoked did on 2026-08-26 for the public backend -- past a green
suite, green CI, and a cross-surface pass. The list here is what makes
"does the build identity have this permission?" a question someone answers
in the diff instead of after the first Cloud Build run.
"""
import pathlib
import re

# admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py -> repo root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

BUILD_SA_NAME = "polyglot-cloudbuild-sa"

# THE PIN. Every role polyglot-cloudbuild-sa holds, and the ONE class of
# build step that needs it. Refreshed by hand, in the same commit that adds
# a role to scripts/setup-cloud-build.sh's PROJECT_ROLES array.
EXPECTED_BUILD_SA_PROJECT_ROLES = {
    # Deploy Cloud Run revisions: backend-staging, backend-demo, and the
    # admin-service tagged-revision-then-shift target.
    "roles/run.admin",
    # Publish Hosting site targets: frontend-staging, frontend-demo, editor,
    # admin-console-candidate, admin-console.
    "roles/firebasehosting.admin",
    # Deploy the firestore-rules target (`firebase deploy --only
    # firestore:rules`).
    "roles/firebaserules.admin",
    # Push the built backend image before `gcloud run deploy`.
    "roles/artifactregistry.writer",
    # Structured build-step logs to Cloud Logging.
    "roles/logging.logWriter",
    # Write build_checks/{sha} (the verify gate) and deployments/{id}
    # success rows (the staging-before-demo gate's evidence); read
    # deployments/{id} to evaluate that gate for a demo build.
    "roles/datastore.user",
}

# Roles granted on ONE RESOURCE (the form-kits bucket) rather than
# project-wide. Kept apart from the project-level set for the same reason
# test_admin_sa_iam_envelope.py separates EXPECTED_ADMIN_SA_BUCKET_ROLES:
# the setup script grants this with a different gcloud command (`gcloud
# storage buckets add-iam-policy-binding`), and the SCOPE is the
# security-relevant half.
EXPECTED_BUILD_SA_BUCKET_ROLES = {
    # Publish and retire form kits in the shared bucket (the form-kits
    # target). Same role/bucket/scope shape as admin-backend-sa's own grant.
    "roles/storage.objectAdmin",
}

# The two RUNTIME service accounts the build must be able to deploy
# revisions AS. Each needs its own resource-scoped
# roles/iam.serviceAccountUser binding -- granting the role once,
# project-wide, would satisfy a role-name-only test while letting the build
# identity impersonate every service account in the project.
EXPECTED_ACTAS_TARGETS = {
    "polyglot-backend-sa",
    "admin-backend-sa",
}


def _setup_script_text() -> str:
    script = REPO_ROOT / "scripts" / "setup-cloud-build.sh"
    assert script.is_file(), (
        "scripts/setup-cloud-build.sh is missing. It is the script that "
        "provisions polyglot-cloudbuild-sa; without it this whole file "
        "asserts against nothing.")
    return script.read_text(encoding="utf-8")


def _named_array(text: str, name: str) -> set:
    """The quoted roles/... entries of a `<name>=( ... )` bash array.

    Same helper shape as test_admin_sa_iam_envelope.py's -- parsed from the
    script rather than re-listed here, so the pin and the script that
    actually provisions the SA cannot drift (CLAUDE.md scar #8: one rule,
    one home).
    """
    block = re.search(
        r"^{}=\((.*?)^\)".format(re.escape(name)), text,
        re.MULTILINE | re.DOTALL)
    assert block, (
        "scripts/setup-cloud-build.sh has no {}=( ... ) array. That array "
        "is how this test learns what the SA is actually granted.".format(
            name))
    return set(re.findall(r'"(roles/[^"]+)"', block.group(1)))


def _named_array_block(text: str, name: str) -> str:
    """The raw `<name>=( ... )` array body text.

    Unlike `_named_array`, this does not filter to `roles/...` entries --
    used for arrays like ACTAS_TARGETS whose entries are `$VAR` references,
    not role strings.
    """
    block = re.search(
        r"^{}=\((.*?)^\)".format(re.escape(name)), text,
        re.MULTILINE | re.DOTALL)
    assert block, (
        "scripts/setup-cloud-build.sh has no {}=( ... ) array.".format(
            name))
    return block.group(1)


def test_build_sa_project_role_pin_matches_the_setup_script():
    """The hand-refreshed pin and the provisioning script name ONE role set.

    Fails on a role added to either side alone -- a new build step added to
    cloudbuild.yaml, a role quietly added to setup-cloud-build.sh to make it
    work, and no reviewer ever asked whether the widening was intended.
    """
    granted = _named_array(_setup_script_text(), "PROJECT_ROLES")
    assert granted == EXPECTED_BUILD_SA_PROJECT_ROLES, (
        "scripts/setup-cloud-build.sh grants a different PROJECT-level role "
        "set than EXPECTED_BUILD_SA_PROJECT_ROLES pins."
        + chr(10) + "  only in the script: {}".format(
            sorted(granted - EXPECTED_BUILD_SA_PROJECT_ROLES))
        + chr(10) + "  only in the pin:    {}".format(
            sorted(EXPECTED_BUILD_SA_PROJECT_ROLES - granted))
        + chr(10) + "Widening polyglot-cloudbuild-sa is a deliberate act: "
          "add the role to BOTH, with the one-line justification saying "
          "which build step needs it.")


def test_build_sa_bucket_role_pin_matches_the_setup_script():
    """The resource-scoped bucket grant, pinned separately from project ones.

    storage.objectAdmin belongs on the form-kits bucket ONLY. Folding it
    into the project-level array would silently promote it to every bucket
    in the project, which no test keyed on the role NAME alone would
    notice.
    """
    granted = _named_array(_setup_script_text(), "BUCKET_ROLES")
    assert granted == EXPECTED_BUILD_SA_BUCKET_ROLES, (
        "scripts/setup-cloud-build.sh grants a different BUCKET-scoped role "
        "set than EXPECTED_BUILD_SA_BUCKET_ROLES pins."
        + chr(10) + "  only in the script: {}".format(
            sorted(granted - EXPECTED_BUILD_SA_BUCKET_ROLES))
        + chr(10) + "  only in the pin:    {}".format(
            sorted(EXPECTED_BUILD_SA_BUCKET_ROLES - granted)))


def test_the_bucket_role_is_granted_on_the_bucket_not_the_project():
    """The SCOPE of the bucket grant, not just its name.

    Moving storage.objectAdmin from `gcloud storage buckets
    add-iam-policy-binding` to `gcloud projects add-iam-policy-binding`
    keeps every name-keyed assertion above green while handing the build
    identity write access to every bucket in the project.
    """
    text = _setup_script_text()
    for role in EXPECTED_BUILD_SA_BUCKET_ROLES:
        assert role in _named_array(text, "BUCKET_ROLES"), role
    assert re.search(r"BUCKET_ROLES\[@\]", text), (
        "BUCKET_ROLES is never iterated in scripts/setup-cloud-build.sh -- "
        "the array is pinned by the test above but grants nothing.")
    assert re.search(
        r"gcloud\s+storage\s+buckets\s+add-iam-policy-binding", text), (
        "scripts/setup-cloud-build.sh has no `gcloud storage buckets "
        "add-iam-policy-binding`, so the bucket-scoped role is either "
        "ungranted or (worse) granted project-wide.")
    for role in EXPECTED_BUILD_SA_BUCKET_ROLES:
        assert role not in _named_array(text, "PROJECT_ROLES"), (
            "{} is granted PROJECT-WIDE. It is meant to be scoped to the "
            "form-kits bucket only.".format(role))


def test_build_sa_has_actas_bindings_on_both_runtime_sas():
    """roles/iam.serviceAccountUser is granted on BOTH runtime SAs, by name.

    A deploy step running `gcloud run deploy --service-account $RUNTIME_SA`
    fails unless the CALLER (this build identity) holds actAs on that exact
    SA. Missing either binding means one deploy target (backend-* or
    admin-service) fails at deploy time with a permission error that no
    role-count-only test would catch.

    Driven off EXPECTED_ACTAS_TARGETS (not hand-listed here), so a future
    edit to that constant actually changes what this test checks -- before
    this fix the constant was declared and never consulted, which is a
    maintenance trap: an editor updating it would see no test reaction at
    all (fresh-eyes finding, bd polyglot-pdf-p4ale round 1).
    """
    text = _setup_script_text()
    # Each pinned target must be the short-name half of a `<VAR>="<name>@
    # $PROJECT..."` definition, and that VAR must be one of the entries in
    # the ACTAS_TARGETS=( ... ) array -- both halves ("a variable exists
    # for it" and "the array actually uses that variable") must hold for
    # every member of EXPECTED_ACTAS_TARGETS.
    sa_var_by_target = {}
    for target in EXPECTED_ACTAS_TARGETS:
        match = re.search(
            r'^([A-Z_]+)="{}@\$PROJECT'.format(re.escape(target)), text,
            re.MULTILINE)
        assert match, (
            "scripts/setup-cloud-build.sh defines no variable for actAs "
            "target {!r} (pinned in EXPECTED_ACTAS_TARGETS) as "
            '<VAR>="{}@$PROJECT..."'.format(target, target))
        sa_var_by_target[target] = match.group(1)

    actas_targets_block = _named_array_block(text, "ACTAS_TARGETS")
    array_vars = set(re.findall(r'"\$([A-Z_]+)"', actas_targets_block))
    for target, sa_var in sa_var_by_target.items():
        assert sa_var in array_vars, (
            "scripts/setup-cloud-build.sh's ACTAS_TARGETS array does not "
            'include "${}" ({!r}, pinned in EXPECTED_ACTAS_TARGETS) -- '
            "that runtime SA would be missing its actAs binding".format(
                sa_var, target))
    assert array_vars == set(sa_var_by_target.values()), (
        "ACTAS_TARGETS names a variable beyond the ones "
        "EXPECTED_ACTAS_TARGETS pins ({}) -- update the constant to match "
        "scripts/setup-cloud-build.sh, or remove the stray "
        "entry".format(sorted(sa_var_by_target.values())))


def test_the_actas_bindings_are_scoped_to_each_sa_not_the_project():
    """The SCOPE of the actAs grant, not just its name.

    A project-wide roles/iam.serviceAccountUser grant would keep the
    binding-exists assertion above green while letting
    polyglot-cloudbuild-sa impersonate EVERY service account in the
    project, including ones no deploy target ever runs as -- exactly the
    CLAUDE.md scar #7 shape, on the grant side.
    """
    text = _setup_script_text()
    assert re.search(
        r'gcloud\s+iam\s+service-accounts\s+add-iam-policy-binding\s+'
        r'"\$target_sa"', text), (
        "scripts/setup-cloud-build.sh has no `gcloud iam service-accounts "
        "add-iam-policy-binding \"$target_sa\"` loop over ACTAS_TARGETS -- "
        "the actAs role is either ungranted or (worse) granted "
        "project-wide via `gcloud projects add-iam-policy-binding`.")
    assert re.search(
        r'--role="roles/iam\.serviceAccountUser"', text), (
        "scripts/setup-cloud-build.sh's actAs loop does not grant "
        "roles/iam.serviceAccountUser.")
    # And the negative half: this role must never appear on a
    # `gcloud projects add-iam-policy-binding` invocation anywhere in the
    # script (that would be the project-wide leak this test exists to
    # catch).
    project_binding_blocks = re.findall(
        r'gcloud projects add-iam-policy-binding.*?(?=\n\n|\Z)', text,
        re.DOTALL)
    for block in project_binding_blocks:
        assert "iam.serviceAccountUser" not in block, (
            "roles/iam.serviceAccountUser appears in a project-level "
            "add-iam-policy-binding call -- it must be scoped to each "
            "runtime SA individually.")


def test_pubsub_service_agent_gets_token_creator_for_the_build_webhook():
    """The Pub/Sub service agent's OIDC-minting role, so the WHOLE
    deploy-plane IAM (build SA + this one Google-managed agent) is pinned
    from one test, per the bead's own framing.

    Bead 4.3's build-status webhook (POST /api/deploys/webhook) is gated by
    require_google_oidc, which only accepts a push subscription backed by a
    real Google-signed OIDC token -- the Pub/Sub service agent needs
    roles/iam.serviceAccountTokenCreator to mint one. Without this binding
    every build-status push 403s at the PUSH layer, before the route's own
    auth check ever runs, and every build looks stuck at "queued" forever
    with no application-level error to grep for.
    """
    text = _setup_script_text()
    assert "gcp-sa-pubsub.iam.gserviceaccount.com" in text, (
        "scripts/setup-cloud-build.sh does not reference the Pub/Sub "
        "service agent (service-<PROJECT_NUMBER>@gcp-sa-pubsub.iam."
        "gserviceaccount.com).")
    assert re.search(
        r'--role="roles/iam\.serviceAccountTokenCreator"', text), (
        "scripts/setup-cloud-build.sh does not grant "
        "roles/iam.serviceAccountTokenCreator to the Pub/Sub service "
        "agent -- the build-status webhook's OIDC push will 403 before "
        "the route's own auth check ever runs.")
    # Scoped to the agent granting itself the role project-wide is correct
    # here (unlike the build SA's own roles): serviceAccountTokenCreator for
    # minting a token asserting ONE'S OWN identity to a Pub/Sub push
    # subscription is the standard, Google-documented shape, and the
    # service agent itself has no narrower resource to scope it to.
    assert re.search(
        r'--member="serviceAccount:\$PUBSUB_SERVICE_AGENT"', text), (
        "the serviceAccountTokenCreator grant is not made to "
        "$PUBSUB_SERVICE_AGENT.")


def test_every_role_is_used_by_at_least_one_pin():
    """The two arrays this file reads are exhaustive against the pins above.

    Guards against a THIRD array (or a role hand-added outside any named
    array) that would grant a role neither PROJECT_ROLES- nor
    BUCKET_ROLES-shaped test ever sees. A future array needs a
    corresponding pin in this file, not a silent grant.
    """
    text = _setup_script_text()
    all_named = (
        _named_array(text, "PROJECT_ROLES")
        | _named_array(text, "BUCKET_ROLES")
    )
    all_pinned = (
        EXPECTED_BUILD_SA_PROJECT_ROLES | EXPECTED_BUILD_SA_BUCKET_ROLES)
    assert all_named == all_pinned, (
        "scripts/setup-cloud-build.sh's named role arrays and this file's "
        "pinned sets disagree."
        + chr(10) + "  only in the script: {}".format(
            sorted(all_named - all_pinned))
        + chr(10) + "  only in the pin:    {}".format(
            sorted(all_pinned - all_named)))
