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
# ABSENT: cloudbuild.builds.editor + iam.serviceAccountUser, run.admin,
# firebasehosting.admin (Epic 4); bigquery.jobUser + bigquery.dataViewer,
# errorreporting.viewer, monitoring.viewer (Epic 3). An unused grant is its
# own risk, so each lands with its first consumer -- pinned by
# test_admin_sa_holds_no_deferred_role_early below.
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

# Roles the plan defers to the epic that first needs them. Granting one early
# widens the blast radius of a compromise for a capability nothing calls.
DEFERRED_ROLES = {
    # Epic 4 (deploy control plane).
    "roles/cloudbuild.builds.editor",
    "roles/iam.serviceAccountUser",
    "roles/run.admin",
    "roles/firebasehosting.admin",
    # Epic 3 (telemetry).
    "roles/bigquery.jobUser",
    "roles/bigquery.dataViewer",
    "roles/errorreporting.viewer",
    "roles/monitoring.viewer",
}


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
    """
    granted = _named_array(_setup_script_text(), "PROJECT_ROLES")
    assert granted == EXPECTED_ADMIN_SA_ROLES, (
        "scripts/setup-admin-service.sh grants a different PROJECT-level role "
        "set than EXPECTED_ADMIN_SA_ROLES pins."
        + chr(10) + "  only in the script: {}".format(
            sorted(granted - EXPECTED_ADMIN_SA_ROLES))
        + chr(10) + "  only in the pin:    {}".format(
            sorted(EXPECTED_ADMIN_SA_ROLES - granted))
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


def test_admin_sa_holds_no_deferred_role_early():
    """Roles the plan defers to Epic 3 / Epic 4 must not be granted yet.

    Pins the DEFERRAL, so adding one early is a decision someone makes in the
    open rather than a line nobody notices in a setup script.
    """
    text = _setup_script_text()
    granted = _named_array(text, "PROJECT_ROLES") | _named_array(
        text, "BUCKET_ROLES")
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
