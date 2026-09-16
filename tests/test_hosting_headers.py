"""Every Firebase Hosting target serves the security headers, and the voice
app loads no third-party font host (sprint 23 E2, bd polyglot-pdf-j29z1;
PF-4, PF-15).

Derived from firebase.json itself: a sixth Hosting target added without the
header block fails here, and so does a CSP that loses a directive or gains an
unsafe one.
"""
import json
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIREBASE_JSON = REPO_ROOT / "firebase.json"
INDEX_HTML = REPO_ROOT / "frontend" / "index.html"
FONTS_DIR = REPO_ROOT / "frontend" / "public" / "fonts"

REQUIRED_HEADERS = (
    "Content-Security-Policy-Report-Only",
    "Strict-Transport-Security",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
)
# The CSP directives every target must carry, and the value each must include.
REQUIRED_CSP = {
    "default-src": "'self'",
    "script-src": "'self'",
    "frame-ancestors": "'none'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "font-src": "'self'",
    "worker-src": "'self'",
    "connect-src": "'self'",
}
# The origins the apps actually talk to; a CSP that drops one breaks the app
# silently in report-only mode and loudly once enforced.
REQUIRED_CONNECT = (
    "https://polyglot-backend-won24rgefq-uc.a.run.app",
    "wss://polyglot-backend-won24rgefq-uc.a.run.app",
    "https://polyglot-backend-staging-won24rgefq-uc.a.run.app",
    "wss://polyglot-backend-staging-won24rgefq-uc.a.run.app",
    "https://polyglot-admin-won24rgefq-uc.a.run.app",
    "https://identitytoolkit.googleapis.com",
    "https://securetoken.googleapis.com",
    "https://firestore.googleapis.com",
)
FORBIDDEN_CSP_TOKENS = ("'unsafe-eval'", "http:", "*.googleapis.com", "https://*")


def _targets():
    cfg = json.loads(FIREBASE_JSON.read_text(encoding="utf-8"))
    hosting = cfg["hosting"]
    assert isinstance(hosting, list) and len(hosting) >= 5, "expected the five Hosting targets"
    return hosting


def _headers_for(target: dict) -> dict:
    blocks = target.get("headers") or []
    catch_all = [b for b in blocks if b.get("source") == "**"]
    assert catch_all, "target %r has no catch-all headers block" % target.get("target")
    return {h["key"]: h["value"] for b in catch_all for h in b["headers"]}


def _csp(target: dict) -> dict:
    raw = _headers_for(target)["Content-Security-Policy-Report-Only"]
    out = {}
    for directive in raw.split(";"):
        parts = directive.strip().split()
        if parts:
            out[parts[0]] = parts[1:]
    return out


@pytest.mark.parametrize("target", _targets(), ids=lambda t: t["target"])
def test_every_target_serves_every_security_header(target):
    headers = _headers_for(target)
    missing = [h for h in REQUIRED_HEADERS if h not in headers]
    assert not missing, "target %s lacks %r" % (target["target"], missing)
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    hsts = headers["Strict-Transport-Security"]
    assert "max-age=" in hsts and "includeSubDomains" in hsts and "preload" in hsts, hsts
    pp = headers["Permissions-Policy"]
    assert "microphone=(self)" in pp and "camera=()" in pp, pp


@pytest.mark.parametrize("target", _targets(), ids=lambda t: t["target"])
def test_every_target_csp_carries_the_required_directives(target):
    csp = _csp(target)
    for directive, needed in REQUIRED_CSP.items():
        assert directive in csp, "%s: CSP lacks %s" % (target["target"], directive)
        assert needed in csp[directive], "%s: %s lacks %s" % (target["target"], directive, needed)
    connect = csp["connect-src"]
    missing = [o for o in REQUIRED_CONNECT if o not in connect]
    assert not missing, "%s: connect-src lacks %r" % (target["target"], missing)
    raw = _headers_for(target)["Content-Security-Policy-Report-Only"]
    bad = [t for t in FORBIDDEN_CSP_TOKENS if t in raw]
    assert not bad, "%s: CSP contains %r" % (target["target"], bad)
    # script-src is exactly 'self': no inline, no eval, no CDN.
    assert csp["script-src"] == ["'self'"], csp["script-src"]


def test_all_targets_share_one_csp():
    """One policy for the five sites: a per-site drift would mean one site
    silently allows what another refuses."""
    policies = {_headers_for(t)["Content-Security-Policy-Report-Only"] for t in _targets()}
    assert len(policies) == 1


def test_the_voice_app_loads_no_third_party_font_host():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    assert 'href="/fonts/fonts.css"' in html


def test_every_self_hosted_font_file_exists_and_only_local_urls_are_used():
    css = (FONTS_DIR / "fonts.css").read_text(encoding="utf-8")
    urls = re.findall(r"url\(([^)]+)\)", css)
    assert len(urls) >= 10, "fonts.css lists too few faces: %d" % len(urls)
    for u in urls:
        assert u.startswith("/fonts/"), u
        assert (FONTS_DIR / u.split("/")[-1]).is_file(), "missing font file " + u
    assert "gstatic" not in css and "googleapis" not in css
    families = set(re.findall(r"font-family: '([^']+)'", css))
    assert families == {"Inter", "Outfit"}, families
