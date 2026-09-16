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

# No X-Frame-Options: the app site ALSO serves Firebase Auth's reserved
# /__/auth/iframe, which every signInWithPopup on our own pages frames, and
# X-Frame-Options cannot carve out a path. Framing is governed by the CSP's
# frame-ancestors instead: 'none' everywhere, our five sites on /__/auth/**.
REQUIRED_HEADERS = (
    "Content-Security-Policy-Report-Only",
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
)
# The CSP directives every target must carry, and the value each must include.
REQUIRED_CSP = {
    "default-src": "'self'",
    "script-src": "https://apis.google.com",
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
    "https://polyglot-admin-uc.a.run.app",  # the short form frontend/.env.demo names as its fallback
    "https://identitytoolkit.googleapis.com",
    "https://securetoken.googleapis.com",
    "https://firestore.googleapis.com",
    # See the note below on the CDN.
    "https://cdn.jsdelivr.net",
)
# The voice overlay's speech detector (@ricky0123/vad-web) fetches its
# model and audio worklet, and onnxruntime-web its WASM runtime, from
# jsdelivr today; the policy names it so the report-only soak stays
# readable. 'wasm-unsafe-eval' covers WASM compilation ONLY; the ORT
# glue the app currently selects (the jsep variant) also calls
# new Function, which needs 'unsafe-eval' -- deliberately not granted.
# Enforcement waits on bd polyglot-pdf-18o7c: self-host the assets AND
# pick the non-jsep ORT build (no new Function); that removes the CDN from
# REQUIRED_CONNECT below and from firebase.json's script-src + connect-src.
ENV_FILES = ("frontend/.env.demo", "schema-editor/.env.hosted", "admin-console/.env.hosted")
HOSTING_SITES = ("polyglot-demo-aa709", "polyglot-app-staging", "polyglot-editor-demo",
                 "polyglot-admin-demo", "polyglot-admin-candidate")
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
    assert "X-Frame-Options" not in headers, "XFO would deny our own pages the Firebase Auth iframe"
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
    # script-src: our origin, the gapi loader Firebase Auth injects, the CDN
    # the VAD worklet loads from, and WASM compilation (onnxruntime) --
    # nothing else, no inline, no 'unsafe-eval' (see the note on REQUIRED_CSP).
    assert csp["script-src"] == ["'self'", "https://apis.google.com", "https://cdn.jsdelivr.net", "'wasm-unsafe-eval'"], csp["script-src"]


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


def _blocks_for(target: dict, source: str) -> list:
    return [b for b in (target.get("headers") or []) if b.get("source") == source]


@pytest.mark.parametrize("target", _targets(), ids=lambda t: t["target"])
def test_the_auth_iframe_path_lets_only_our_sites_frame_it(target):
    """signInWithPopup on every one of our pages frames
    https://<authDomain>/__/auth/iframe, served by the app site; the
    catch-all's frame-ancestors 'none' would refuse it once enforced, so the
    reserved path carries its own policy naming exactly our five sites (both
    hostnames each)."""
    blocks = _blocks_for(target, "/__/auth/**")
    assert len(blocks) == 1, target["target"]
    hdrs = {h["key"]: h["value"] for h in blocks[0]["headers"]}
    policy = hdrs["Content-Security-Policy-Report-Only"]
    assert policy.startswith("frame-ancestors "), policy
    origins = set(policy.split()[1:])
    expected = set()
    for site in HOSTING_SITES:
        expected |= {"https://%s.web.app" % site, "https://%s.firebaseapp.com" % site}
    assert origins == expected, origins ^ expected
    # The reserved block must come AFTER the catch-all so its value wins.
    sources = [b.get("source") for b in target["headers"]]
    assert sources.index("**") < sources.index("/__/auth/**")


@pytest.mark.parametrize("target", _targets(), ids=lambda t: t["target"])
def test_fonts_are_cached(target):
    blocks = _blocks_for(target, "/fonts/**")
    assert len(blocks) == 1, target["target"]
    hdrs = {h["key"]: h["value"] for h in blocks[0]["headers"]}
    assert "max-age=" in hdrs["Cache-Control"] and "public" in hdrs["Cache-Control"]


def test_every_cloud_run_host_the_apps_are_built_against_is_in_connect_src():
    """The Cloud Run hostname hash is the one value this repo has already
    seen drift (bd polyglot-pdf-emm7): the deploy resolves the live URL and
    injects it into the bundle, but firebase.json cannot. Every a.run.app
    host named in the apps' env files must be in the policy, so a recreate
    that changes the hash fails here before it breaks the voice socket
    under enforcement."""
    csp = _csp(_targets()[0])
    connect = set(csp["connect-src"])
    wanted = set()
    for rel in ENV_FILES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for host in re.findall(r"(?:https|wss)://([a-z0-9.-]+\.a\.run\.app)", text):
            wanted.add(host)
    assert wanted, "no Cloud Run host found in the env files -- scan is vacuous"
    missing = [h for h in sorted(wanted) if "https://" + h not in connect or "wss://" + h not in connect]
    assert not missing, "connect-src lacks (https+wss) for: " + repr(missing)

