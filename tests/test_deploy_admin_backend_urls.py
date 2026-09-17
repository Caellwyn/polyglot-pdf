"""BACKEND_URLS_JSON's wire format: semicolons, not commas, both ends.

bd polyglot-pdf-mpebj (E3.11a) -> bd polyglot-pdf-oqtm7 (4.6), which moved the
producer.

WHY THIS EXISTS. GET /admin/health (admin_backend/routes/ops_routes.py) fans
out to each channel's public backend /health + /version, and needs that
backend's Cloud Run URL -- unknowable to the admin service itself, which has
no channel of its own. Both URLs are resolved live at deploy time and handed
to the service as one env var.

WHY THE WIRE FORMAT IS "channel=url;channel=url", NOT LITERAL JSON, DESPITE
THE ENV VAR'S NAME. The value rides inside a single comma-separated
`--set-env-vars` string, so a literal JSON object's "," between key/value
pairs would be silently split apart there as a malformed second env-var entry
-- the same reason CORS_EXTRA_ORIGINS is semicolon-separated. This file pins
the SEMICOLON shape on the CONSUMER side and names the producer.

WHO PRODUCES IT NOW. cloudbuild.yaml's admin-service-deploy-tagged step.
deploy-admin.sh used to resolve both URLs itself and fold them into
BACKEND_EXTRA_ENV; it is a thin Cloud Build trigger wrapper as of 4.6, so the
build is the only producer. The RUNTIME proof that the step really passes the
semicolon-joined value through to `gcloud run deploy` lives in
tests/test_cloudbuild_yaml.py::
test_admin_service_deploy_tagged_actually_passes_live_urls_at_runtime, which
drives the real step against a stubbed gcloud -- this file is the cheap
static cross-check that the two SIDES of the contract still agree.

ASCII only.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLOUDBUILD = REPO_ROOT / "cloudbuild.yaml"
OPS_ROUTES = REPO_ROOT / "admin_backend" / "routes" / "ops_routes.py"


def test_the_build_is_the_only_producer_of_backend_urls_json():
    """One producer. A second live copy in a bash wrapper would be the drift
    that moving this config into the build exists to end -- and because
    --set-env-vars REPLACES the whole env block, whichever path ran last would
    silently win."""
    build = CLOUDBUILD.read_text(encoding="utf-8")
    assert "BACKEND_URLS_JSON" in build, (
        "cloudbuild.yaml never assembles BACKEND_URLS_JSON -- GET /admin/health "
        "would read every channel as configured: false on every deploy"
    )
    for wrapper in ("deploy-admin.sh", "deploy-all.sh"):
        text = (REPO_ROOT / wrapper).read_text(encoding="utf-8")
        assert "BACKEND_URLS_JSON" not in text, (
            f"{wrapper} assembles BACKEND_URLS_JSON again -- the build is the "
            "one producer"
        )


def test_the_builds_join_character_is_a_semicolon_not_a_comma():
    """Mutation: change the join to "," -- this goes red. A comma would be
    split apart by the surrounding comma-joined --set-env-vars string,
    corrupting the whole env block rather than just this value."""
    build = CLOUDBUILD.read_text(encoding="utf-8")
    assert 'BACKEND_URLS_PARTS="$$BACKEND_URLS_PARTS;staging=' in build, (
        "cloudbuild.yaml does not join the demo and staging segments of "
        "BACKEND_URLS_PARTS with a semicolon"
    )
    assert "BACKEND_URLS_PARTS,staging=" not in build
    assert "$$BACKEND_URLS_PARTS,staging=" not in build


def test_ops_routes_parses_the_same_semicolon_shape_the_build_produces():
    """The two sides of the contract must agree on the wire format without a
    test importing yaml into Python or vice versa. The other half of this pin
    is admin_backend/tests/unit/test_ops_routes.py's own semicolon-parsing
    test, which exercises the parser directly; this one confirms the PRODUCER
    did not drift to a format the parser never asked for."""
    ops_routes_text = OPS_ROUTES.read_text(encoding="utf-8")
    assert 'raw.split(";")' in ops_routes_text, (
        "admin_backend/routes/ops_routes.py's _backend_urls no longer splits "
        'BACKEND_URLS_JSON on ";" -- re-verify it still agrees with '
        "cloudbuild.yaml's semicolon-joined BACKEND_URLS_PARTS construction"
    )
