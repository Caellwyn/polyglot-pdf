"""admin-console/.env.hosted's VITE_ADMIN_API_BASE_URL fallback must be a
real Cloud Run auto-URL shape, not a fabricated hostname (bd polyglot-pdf-
o8xmk).

Every real Cloud Run auto-URL in this repo carries a project hash segment
between the service name and the region ("-<hash>-uc.a.run.app"), e.g.
schema-editor/.env.hosted's polyglot-backend-won24rgefq-uc.a.run.app. A
committed value with no hash segment can never resolve to the real service --
deploy-admin-console.sh's live gcloud resolution overrides this line on a
normal deploy, but a gcloud-less local build or a failed resolution falls
through to it, and a fabricated hostname there presents as a network error
with no clue the fallback itself is bogus.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_HOSTED = REPO_ROOT / "admin-console" / ".env.hosted"

_CLOUD_RUN_AUTO_URL = re.compile(
    r"https://[a-z0-9-]+-[a-z0-9]{6,}-[a-z]{2}\.a\.run\.app"
)


def _env_text() -> str:
    return ENV_HOSTED.read_text(encoding="utf-8")


def test_admin_api_base_url_fallback_has_a_hash_segment():
    text = _env_text()
    match = re.search(r"^VITE_ADMIN_API_BASE_URL=(\S+)$", text, re.MULTILINE)
    assert match, "VITE_ADMIN_API_BASE_URL is not set in admin-console/.env.hosted"
    url = match.group(1)
    assert _CLOUD_RUN_AUTO_URL.match(url), (
        "VITE_ADMIN_API_BASE_URL={!r} is not shaped like a real Cloud Run "
        "auto-URL (missing the project hash segment, e.g. "
        "https://polyglot-admin-won24rgefq-uc.a.run.app)".format(url)
    )


def test_admin_api_base_url_fallback_names_the_admin_service():
    text = _env_text()
    match = re.search(r"^VITE_ADMIN_API_BASE_URL=(\S+)$", text, re.MULTILINE)
    assert match
    assert match.group(1).startswith("https://polyglot-admin-"), (
        "the fallback URL must resolve to the polyglot-admin service, not "
        "the public backend or some other service"
    )
