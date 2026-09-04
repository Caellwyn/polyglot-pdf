"""ADMIN_CORS_ORIGINS must list every origin on BOTH its Firebase Hosting
domains (bd polyglot-pdf-3l2vp fresh-eyes fix).

WHY THIS EXISTS. Every Firebase Hosting site is reachable at both
`<site>.web.app` AND `<site>.firebaseapp.com` simultaneously -- platform
behavior, not project config (the codebase's own established convention:
deploy-demo.sh / deploy-staging.sh both list both domains for the
schema-editor's CORS_EXTRA_ORIGINS, and backend/config.py's docstring example
does the same). admin_backend/main.py's CORSMiddleware is a strict
exact-string allowlist with no regex fallback, so a caller served from the
domain missing from the list gets CORS-rejected with no useful error --
exactly what happened to the two app-channel origins here originally: the
admin console origins got both domains, the app-channel origins got only
`.web.app`.

DERIVED FROM THE SCRIPT, never a hand-typed pair list: this test extracts
every `https://<host>` entry ADMIN_CORS_ORIGINS actually contains and asserts
each host's sibling domain (.web.app <-> .firebaseapp.com) is ALSO present --
so it catches the omission for any origin, not just the two that were
missing when this was written (per CLAUDE.md's "enumerate the set" doctrine:
pinning the property, not the instance).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ADMIN = REPO_ROOT / "deploy-admin.sh"


def _live_text(path: Path) -> str:
    """Strip full-line `#` comments so a commented-out assignment can't be
    parsed as the real one (mirrors test_deploy_channel_parity.py's guard)."""
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    ]
    return "\n".join(lines)


def _admin_cors_origins() -> list[str]:
    text = _live_text(DEPLOY_ADMIN)
    match = re.search(r'ADMIN_CORS_ORIGINS="([^"]*)"', text)
    assert match, "no ADMIN_CORS_ORIGINS assignment found in deploy-admin.sh"
    origins = [o for o in match.group(1).split(";") if o]
    assert len(origins) >= 4, (
        f"suspiciously few origins parsed ({origins!r}) -- guard the guard: "
        "a regex that stops matching too early would pass vacuously."
    )
    return origins


def test_extraction_finds_the_assignment():
    """Guard the guard: a match that finds nothing passes every test below
    vacuously."""
    origins = _admin_cors_origins()
    assert any("polyglot-admin-demo" in o for o in origins)
    assert any(o.startswith("https://") for o in origins)


def test_every_origin_has_both_firebase_hosting_domains():
    """For every `https://<host>.web.app` entry, the identical host on
    `.firebaseapp.com` must also be listed, and vice versa -- a Hosting site
    is reachable at both, so listing only one leaves the other's callers
    CORS-rejected."""
    origins = _admin_cors_origins()
    hosts_web_app = {
        o[len("https://"):-len(".web.app")]
        for o in origins
        if o.startswith("https://") and o.endswith(".web.app")
    }
    hosts_firebaseapp = {
        o[len("https://"):-len(".firebaseapp.com")]
        for o in origins
        if o.startswith("https://") and o.endswith(".firebaseapp.com")
    }
    missing_firebaseapp = hosts_web_app - hosts_firebaseapp
    missing_web_app = hosts_firebaseapp - hosts_web_app
    assert not missing_firebaseapp, (
        f"ADMIN_CORS_ORIGINS lists {sorted(missing_firebaseapp)} on "
        ".web.app but not the matching .firebaseapp.com alias -- a caller "
        "served from that domain will be CORS-rejected."
    )
    assert not missing_web_app, (
        f"ADMIN_CORS_ORIGINS lists {sorted(missing_web_app)} on "
        ".firebaseapp.com but not the matching .web.app alias."
    )
