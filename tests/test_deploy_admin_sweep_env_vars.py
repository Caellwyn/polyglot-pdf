"""Every OIDC caller identity an admin route allowlists must be deployed.

bd polyglot-pdf-8vgfh (the original incident) -> bd polyglot-pdf-oqtm7 (moved
onto the channel file when deploy-admin.sh became a thin Cloud Build wrapper).

WHY THIS EXISTS. The admin service's Cloud Run deploy uses `--set-env-vars`,
which REPLACES the service's ENTIRE env block rather than merging into it. A
value set by any other route -- a hand-run `gcloud run services update`, an
older deploy path -- is therefore WIPED by the next deploy. That happened for
real: scripts/setup-admin-service.sh printed a one-time NOTE telling an
operator to set ADMIN_SERVICE_URL and SWEEP_SCHEDULER_SA_EMAIL by hand, and
the very next deploy silently erased them, fail-closing the refund sweep (503)
with no test or alert able to notice. The same shape bit PUBSUB_PUSH_SA_EMAIL,
which no deploy path set at all.

WHAT CHANGED IN 4.6. deploy-admin.sh used to assemble these inline and pass
them as BACKEND_EXTRA_ENV. It is a thin trigger wrapper now, so
deploy/channels/admin.env is the ONE source the build reads -- and a key
missing from that file is a key REMOVED from the running service at the next
deploy, not one left alone.

DERIVED FROM THE ROUTES, NOT HAND-LISTED (CLAUDE.md scar #8). The required set
is every `*_SA_EMAIL` environment variable the admin_backend routes actually
read as an OIDC caller allowlist. A fourth scheduler or push subscription
added later is therefore required here the day its route reads it, rather than
the day someone remembers to widen a typed list -- which is precisely how
MONTHLY_TOPUP_SCHEDULER_SA_EMAIL came to be missing from the channel file
while deploy-admin.sh still injected it.

ASCII only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ADMIN_ENV = REPO_ROOT / "deploy" / "channels" / "admin.env"
ADMIN_ROUTES = REPO_ROOT / "admin_backend" / "routes"

# os.getenv("<NAME>_SA_EMAIL", ...) in a route module.
_SA_EMAIL_READ = re.compile(r'os\.getenv\(\s*"([A-Z0-9_]*_SA_EMAIL)"')


def _parse_section(path: Path, section: str) -> dict[str, str]:
    """The KEY=value pairs of one [SECTION] of a channel file."""
    out: dict[str, str] = {}
    current = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            continue
        if current != section or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key] = value
    return out


def _required_sa_email_vars() -> set[str]:
    """Every *_SA_EMAIL the shipped admin routes read from the environment."""
    found: set[str] = set()
    for path in sorted(ADMIN_ROUTES.glob("*.py")):
        found.update(_SA_EMAIL_READ.findall(path.read_text(encoding="utf-8")))
    return found


def test_the_derivation_finds_something():
    """A regex that matched nothing would make every test below vacuous."""
    assert len(_required_sa_email_vars()) >= 3, _required_sa_email_vars()


@pytest.mark.parametrize(
    "var", sorted(_required_sa_email_vars()), ids=lambda v: v.lower()
)
def test_every_caller_identity_a_route_reads_is_in_the_channel_file(var):
    env = _parse_section(ADMIN_ENV, "SET_ENV_VARS")
    assert var in env, (
        f"an admin route allowlists {var} but deploy/channels/admin.env never "
        "sets it -- --set-env-vars replaces the service's whole env block, so "
        "the deployed value is empty, the allowlist is empty, and that route "
        "fail-closes (503) on every call"
    )
    assert env[var].strip(), f"{var} is present in admin.env but empty"


@pytest.mark.parametrize(
    "var", sorted(_required_sa_email_vars()), ids=lambda v: v.lower()
)
def test_every_caller_identity_is_a_distinct_service_account(var):
    """Never reuse a caller identity across jobs: a Scheduler job or a push
    subscription that can call one route must not thereby be able to call
    another."""
    env = _parse_section(ADMIN_ENV, "SET_ENV_VARS")
    others = [
        env[other]
        for other in _required_sa_email_vars()
        if other != var and other in env
    ]
    assert env[var] not in others, (
        f"{var} shares its service account with another caller identity"
    )


@pytest.mark.parametrize(
    "var", sorted(_required_sa_email_vars()), ids=lambda v: v.lower()
)
def test_every_caller_identity_is_created_by_the_setup_script(var):
    """The value must be a real account someone provisions, not a plausible
    string: scripts/setup-admin-service.sh creates each of these, and its
    names are fixed literals, which is why they are knowable ahead of the
    service's first deploy (unlike ADMIN_SERVICE_URL)."""
    env = _parse_section(ADMIN_ENV, "SET_ENV_VARS")
    local_part = env[var].split("@")[0]
    setup = (REPO_ROOT / "scripts" / "setup-admin-service.sh").read_text(
        encoding="utf-8"
    )
    assert local_part in setup, (
        f"admin.env sets {var} to an account ({local_part}) that "
        "scripts/setup-admin-service.sh never creates"
    )


def test_the_app_module_selector_is_in_the_channel_file():
    """The shared image serves the PUBLIC backend unless APP_MODULE says
    otherwise (the Dockerfile's `CMD uvicorn ${APP_MODULE:-backend.main:app}`),
    so losing this key does not fail -- it silently deploys the wrong app."""
    env = _parse_section(ADMIN_ENV, "SET_ENV_VARS")
    assert env.get("APP_MODULE") == "admin_backend.main:app"


def test_the_runtime_identity_is_not_the_public_backends():
    """The admin service reads and writes firm, credit and audit data the
    voice backend must never be able to touch."""
    sa = _parse_section(ADMIN_ENV, "SERVICE_ACCOUNT").get("SERVICE_ACCOUNT", "")
    assert sa.startswith("admin-backend-sa@"), sa
