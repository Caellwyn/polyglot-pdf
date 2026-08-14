"""Auth gating on the HTTP routes (bd polyglot-pdf-z2is).

/api/fill-pdf renders user-entered field values and /api/form-kits{,/schema}
serve the kit catalogue; all three now require a Firebase ID token via
require_auth. /api/form-kits/{kit_id}/pdf stays DELIBERATELY public (blank
template = public government form, also shipped in the static Hosting bundle)
-- that non-gate is pinned here too so a future blanket-auth sweep can't
silently break the pdfjs viewer path without failing a test.

VFF_DISABLE_AUTH=true (local dev / voice harness) bypasses inside verify_token;
the 401 tests pin the bypass OFF explicitly so a dev .env can't green them.
"""
import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.routes.form_kit_routes as fkr
from backend.main import app
from backend.services.auth import require_auth
from backend.services.form_kits import FormKitNotFound

client = TestClient(app)

# Minimal but schema-valid body so a 401 is unambiguously the auth dependency,
# not a 422 from body validation.
_FILL_BODY = {
    "kit_id": "i-90",
    "pdf_filename": "form.pdf",
    "field_values": {},
    "form_schema": {"fields": []},
}


class _NotFoundStore:
    """Store double whose every read 404s -- keeps route tests hermetic."""

    async def load_manifest(self, manifest_file: str = "index.json") -> dict:
        raise FormKitNotFound("no manifest")

    async def load_metadata(self, kit_id: str):
        raise FormKitNotFound("no metadata")

    async def load_schema(self, kit_id: str, schema_file: str = "schema.json"):
        raise FormKitNotFound("no schema")

    async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
        raise FormKitNotFound("no pdf")


@pytest.fixture
def _auth_on(monkeypatch):
    """Force real auth (bypass OFF) regardless of the dev machine's .env."""
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")


@pytest.fixture
def _auth_bypassed(monkeypatch):
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")


def test_fill_pdf_requires_token(_auth_on):
    resp = client.post("/api/fill-pdf", json=_FILL_BODY)
    assert resp.status_code == 401


def test_fill_pdf_rejects_garbage_token(_auth_on):
    resp = client.post(
        "/api/fill-pdf",
        json=_FILL_BODY,
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_form_kits_list_requires_token(_auth_on):
    resp = client.get("/api/form-kits")
    assert resp.status_code == 401


def test_form_kit_schema_requires_token(_auth_on):
    resp = client.get("/api/form-kits/i-90/schema")
    assert resp.status_code == 401


def test_form_kit_pdf_is_deliberately_public(_auth_on, monkeypatch):
    """The blank-template PDF GET must NOT be auth-gated (see route docstring:
    no frontend consumer loads this route -- the viewer fetches the static
    Hosting copy -- and the same public-form bytes ship in the static bundle
    regardless, so gating protects nothing). Pinned so a future blanket-auth
    sweep is a deliberate decision, not an accident.

    With auth forced on and no token, the route must still reach the store
    (404 from the double), never 401.
    """
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _NotFoundStore())
    resp = client.get("/api/form-kits/i-90/pdf")
    assert resp.status_code == 404


def test_bypass_admits_tokenless_requests(_auth_bypassed, monkeypatch):
    """VFF_DISABLE_AUTH=true keeps local dev / the harness working tokenless."""
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _NotFoundStore())
    resp = client.get("/api/form-kits")
    # Auth passed (bypass); the empty-manifest path returns an empty list.
    assert resp.status_code == 200
    assert resp.json() == {"forms": []}


def test_require_auth_passes_bearer_token_to_verifier(monkeypatch):
    seen = {}

    def _fake_verify(token: str) -> dict:
        seen["token"] = token
        return {"uid": "u1"}

    monkeypatch.setattr("backend.services.auth.verify_token", _fake_verify)
    claims = asyncio.run(require_auth("Bearer abc123"))
    assert claims == {"uid": "u1"}
    assert seen["token"] == "abc123"


def test_require_auth_missing_header_is_401(monkeypatch):
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_auth(None))
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------
# The COMPLETE gated set (bd polyglot-pdf-qs7m6)
# --------------------------------------------------------------------------
#
# Every route above was pinned INDIVIDUALLY, so /api/tts/spellback -- added
# later, and correctly gated in code -- had no test, and two docs
# (components/auth.md, components/config-deployment.md) enumerated only the
# original three. Nothing failed, because nothing asserted the SET.
#
# This derives the gated set from the live app and pins it whole (CLAUDE.md
# scar #7): adding or removing a require_auth dependency now fails HERE, with
# the doc sites named in the message, instead of surfacing as a stale doc a
# reviewer happens to notice.


def _routes_depending_on_require_auth() -> set:
    """(method, path) for every app route wired to the require_auth dependency.

    Reads the actual dependency objects off each route, so it cannot drift the
    way a hand-maintained list does.
    """
    gated = set()
    for route in app.routes:
        for dep in getattr(route, "dependencies", []) or []:
            if getattr(dep, "dependency", None) is require_auth:
                for method in sorted(route.methods or []):
                    gated.add((method, route.path))
        # The common spelling in this repo is a PARAMETER default
        # (`_user: dict = Depends(require_auth)`), which FastAPI flattens into
        # the route's dependant graph rather than route.dependencies.
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            for sub in dependant.dependencies:
                if sub.call is require_auth:
                    for method in sorted(route.methods or []):
                        gated.add((method, route.path))
    return gated


# The four routes that carry user data or gate paid work. Update this list ONLY
# together with the prose enumerations in:
#   docs/components/auth.md            ("HTTP routes (bd polyglot-pdf-z2is)")
#   docs/components/config-deployment.md  (the VFF_DISABLE_AUTH bullet)
_EXPECTED_GATED_ROUTES = {
    ("GET", "/api/form-kits"),
    ("GET", "/api/form-kits/{kit_id}/schema"),
    ("POST", "/api/fill-pdf"),
    ("POST", "/api/tts/spellback"),
}


def test_the_complete_require_auth_route_set_is_pinned():
    actual = _routes_depending_on_require_auth()
    assert actual == _EXPECTED_GATED_ROUTES, (
        "The set of require_auth-gated routes changed.\n"
        f"  added:   {sorted(actual - _EXPECTED_GATED_ROUTES)}\n"
        f"  removed: {sorted(_EXPECTED_GATED_ROUTES - actual)}\n"
        "Update _EXPECTED_GATED_ROUTES *and* both prose enumerations:\n"
        "  docs/components/auth.md\n"
        "  docs/components/config-deployment.md"
    )


def test_spellback_requires_token(_auth_on):
    # The route this bead's doc fix was missing -- gated in code since it was
    # added, but never pinned, so nothing caught the docs falling behind.
    resp = client.post("/api/tts/spellback", json={"text": "A1234"})
    assert resp.status_code == 401
