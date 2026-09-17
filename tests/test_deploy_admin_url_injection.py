"""VITE_ADMIN_API_BASE_URL injection into the main-app frontend build.

bd polyglot-pdf-z4ljj (Epic 2 Track C bead C0) -> bd polyglot-pdf-oqtm7 (4.6),
which moved the frontend build into cloudbuild.yaml.

WHY THIS EXISTS. The main app's firm-console pages (frontend/src/console/*)
call the admin service (polyglot-admin) over plain HTTP. Unlike the voice
WebSocket there IS a Hosting rewrite available in principle -- but the admin
service is a SEPARATE Cloud Run service from the voice backend, and
firebase.json's /api/** rewrite points only at the voice backend, so no
rewrite binds the console pages to it either. VITE_ADMIN_API_BASE_URL,
resolved at deploy time from the LIVE polyglot-admin Cloud Run URL, is
therefore the only thing tying a frontend build's firm-console pages to the
admin service -- exactly the role VITE_WS_URL plays for the voice path.

WHY IT MUST ABORT RATHER THAN FALL BACK. The build step exports whatever the
resolve step wrote, UNCONDITIONALLY. An empty export OVERRIDES the committed
frontend/.env.demo fallback rather than deferring to it, so a silent skip
would ship a build whose firm-console calls become relative paths -- routed by
Hosting's /api/** rewrite to the VOICE backend, not the admin service.

READ FROM cloudbuild.yaml. Substitutions are fixed at trigger time, so the
URL cannot be one: it is resolved in an earlier step of the SAME build and
handed forward through the shared /workspace. deploy-all.sh's frontend stage
used to do this; it is a thin Cloud Build trigger wrapper now.

NOT tested here: that a deploy actually works. That needs a real deploy.

ASCII only.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CLOUDBUILD = REPO_ROOT / "cloudbuild.yaml"

ADMIN_SERVICE_NAME = "polyglot-admin"


def _steps() -> dict[str, str]:
    build = yaml.safe_load(CLOUDBUILD.read_text(encoding="utf-8"))
    return {step["id"]: "\n".join(step.get("args", [])) for step in build["steps"]}


@pytest.fixture(scope="module")
def steps() -> dict[str, str]:
    return _steps()


def test_the_frontend_steps_exist(steps):
    """Guard the guard: a renamed step would make every test below vacuous."""
    assert "frontend-resolve-urls" in steps
    assert "frontend-build-deploy" in steps


def test_the_admin_url_is_resolved_live_not_read_from_a_committed_literal(steps):
    """The Cloud Run auto-URL hash is NOT stable -- it changed on a service
    recreate once already (bd polyglot-pdf-emm7), and every client pinned to
    the old literal then hit a 404'd backend that looked like an auth
    failure."""
    body = steps["frontend-resolve-urls"]
    assert f"gcloud run services describe {ADMIN_SERVICE_NAME}" in body, (
        "frontend-resolve-urls does not resolve the admin service's live URL"
    )
    assert "/workspace/.vite_admin_api_base_url" in body, (
        "the resolved admin URL is never handed forward to the build step"
    )


def test_an_unresolvable_admin_url_aborts_the_build(steps):
    """Mutation: drop the guard and let it fall through -- this goes red. See
    the module docstring for why a fallback is worse than a failure here."""
    body = steps["frontend-resolve-urls"]
    marker = 'if [ -z "$$ADMIN_URL" ]; then'
    assert marker in body, (
        "frontend-resolve-urls does not refuse an empty admin service URL"
    )
    lines = body.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == marker)
    end = next(
        i for i in range(start + 1, len(lines)) if lines[i].strip() == "fi"
    )
    branch = lines[start + 1:end]
    assert any(ln.strip() == "exit 1" for ln in branch), (
        "the empty-admin-URL branch does not abort the build: " + repr(branch)
    )


def test_the_build_step_exports_the_resolved_url(steps):
    """Resolving it and never exporting it is exactly as broken as not
    resolving it."""
    body = steps["frontend-build-deploy"]
    assert "/workspace/.vite_admin_api_base_url" in body
    assert "export VITE_ADMIN_API_BASE_URL=" in body, (
        "frontend-build-deploy never exports VITE_ADMIN_API_BASE_URL, so the "
        "firm-console pages fall back to a relative path and Hosting routes "
        "them to the VOICE backend"
    )


def test_the_export_precedes_the_vite_build(steps):
    """Vite reads the environment at build time; an export after `npm run
    build` would bake in the committed fallback instead."""
    body = steps["frontend-build-deploy"]
    assert body.index("export VITE_ADMIN_API_BASE_URL=") < body.index(
        "npm run build:schema:demo"
    )


def test_the_admin_service_name_matches_the_admin_targets(steps):
    """One service name across the frontend's lookup and the admin target's
    own deploy -- a rename on one side only would point every firm-console
    page at a service that does not exist."""
    assert (
        f"gcloud run deploy {ADMIN_SERVICE_NAME}" in steps["admin-service-deploy-tagged"]
    )
    assert (
        f"gcloud run services describe {ADMIN_SERVICE_NAME}"
        in steps["frontend-resolve-urls"]
    )
