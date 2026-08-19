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
    """The PDF GET must NOT be auth-gated FOR PUBLIC KITS (updated
    DELIBERATELY by bd polyglot-pdf-vccy, which added the private-kit gate:
    the route now parses an OPTIONAL bearer token and 404s private kits for
    non-members -- see the firm-visibility tests below -- while a public
    kit's blank-template bytes ship in the static Hosting bundle regardless,
    so gating the public read still protects nothing). Pinned so a future
    blanket-auth sweep is a deliberate decision, not an accident.

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
# Firm-scoped kit visibility (bd polyglot-pdf-vccy).
#
# One public + one private kit. Identity comes from a patched verify_token
# (tok-a -> firm-a staff, tok-b -> firm-b staff, tok-legacy -> no firm claim);
# the firm allowlist comes from a patched get_allowed_kits (firm-a may see
# priv-kit). The manifest entries carry NO visibility key on purpose: the
# LIVE metadata is the visibility source (the GCS index.json is deploy-time
# stale), so these tests also pin that metadata beats the manifest.
# --------------------------------------------------------------------------

from backend.services.form_kits import normalize_manifest  # noqa: E402

_TOKENS = {
    "tok-a": {"uid": "staff-a", "firm_id": "firm-a", "firm_role": "manager"},
    "tok-b": {"uid": "staff-b", "firm_id": "firm-b", "firm_role": "employee"},
    "tok-legacy": {"uid": "legacy-user"},
}


class _TwoKitStore:
    """One public + one private kit; live metadata is the visibility source."""

    def __init__(self):
        self.meta = {
            "pub-kit": {"status": "complete"},
            "priv-kit": {
                "status": "complete",
                "visibility": "private",
                "owner_firm_id": "firm-a",
            },
        }

    async def load_manifest(self, manifest_file: str = "index.json") -> dict:
        return normalize_manifest({
            "forms": [
                {"id": "pub-kit", "label": "Public Kit"},
                {"id": "priv-kit", "label": "Private Kit", "pdfFile": "intake.pdf"},
            ]
        })

    async def load_metadata(self, kit_id: str):
        return self.meta.get(kit_id)

    async def load_schema(self, kit_id: str, schema_file: str = "schema.json"):
        return {"kit": kit_id}

    async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
        return b"%PDF-" + kit_id.encode("ascii")


@pytest.fixture
def _firm_world(_auth_on, monkeypatch):
    """Wire the two-kit store, the token->claims map, and the firm allowlist."""

    def _fake_verify(token: str) -> dict:
        claims = _TOKENS.get(token)
        if claims is None:
            raise HTTPException(status_code=401, detail="bad token")
        return dict(claims)

    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _TwoKitStore())
    # require_auth (list/schema routes) resolves verify_token inside the auth
    # module; the pdf route uses the copy imported into form_kit_routes.
    monkeypatch.setattr("backend.services.auth.verify_token", _fake_verify)
    monkeypatch.setattr(fkr, "verify_token", _fake_verify)
    monkeypatch.setattr(
        fkr, "get_allowed_kits",
        lambda firm_id: {"firm-a": ["priv-kit"]}.get(firm_id, []),
    )


def _list_ids(resp) -> list:
    return [f["id"] for f in resp.json()["forms"]]


@pytest.mark.parametrize("token", ["tok-b", "tok-legacy"])
def test_private_kit_absent_from_list_for_other_firms_and_legacy(_firm_world, token):
    """Catalogue invisibility (epic 02ye rubric #2, list surface). Mutation:
    drop the visibility filter in list_form_kits -- red."""
    resp = client.get(
        "/api/form-kits", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert _list_ids(resp) == ["pub-kit"]


def test_private_kit_listed_for_own_firm_with_backend_paths(_firm_world):
    """Firm-A sees its private kit, whose paths are REWRITTEN to the
    authenticated backend routes (the static bundle excludes private kits),
    while the public kit keeps its static paths, and BOTH entries carry
    explicit schema_file/pdf_file (the fill path posts the real filename).
    Mutations: drop the rewrite branch -- the path asserts go red; drop the
    schema_file/pdf_file population -- the filename asserts go red."""
    resp = client.get(
        "/api/form-kits", headers={"Authorization": "Bearer tok-a"}
    )
    assert resp.status_code == 200
    forms = {f["id"]: f for f in resp.json()["forms"]}
    assert set(forms) == {"pub-kit", "priv-kit"}
    assert forms["priv-kit"]["schema_path"] == "/api/form-kits/priv-kit/schema"
    assert forms["priv-kit"]["pdf_path"] == "/api/form-kits/priv-kit/pdf"
    assert forms["priv-kit"]["pdf_file"] == "intake.pdf"
    assert forms["pub-kit"]["schema_path"] == "/form-kits/pub-kit/schema.json"
    assert forms["pub-kit"]["pdf_path"] == "/form-kits/pub-kit/form.pdf"
    assert forms["pub-kit"]["schema_file"] == "schema.json"


@pytest.mark.parametrize("token", ["tok-b", "tok-legacy"])
def test_private_schema_is_404_for_other_firms_and_legacy(_firm_world, token):
    """Schema-read invisibility: 404 (existence is the secret), never 403.
    Mutation: drop the _require_visible call in get_form_kit_schema -- red."""
    resp = client.get(
        "/api/form-kits/priv-kit/schema",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_private_schema_loads_for_own_firm(_firm_world):
    """The usability half of rubric #2: firm-A actually READS its kit."""
    resp = client.get(
        "/api/form-kits/priv-kit/schema",
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"kit": "priv-kit"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-real-token"},
        {"Authorization": "Bearer tok-b"},
        {"Authorization": "Bearer tok-legacy"},
    ],
    ids=["anonymous", "invalid-token", "firm-b", "legacy"],
)
def test_private_pdf_is_404_for_everyone_but_the_firm(_firm_world, headers):
    """PDF invisibility, incl. the anonymous + garbage-token paths the public
    route shape makes possible (invalid degrades to anonymous -> 404, not
    401 -- existence is the secret). Mutation: drop the _require_visible call
    in get_form_kit_pdf -- red."""
    resp = client.get("/api/form-kits/priv-kit/pdf", headers=headers)
    assert resp.status_code == 404


def test_private_pdf_loads_for_own_firm(_firm_world):
    resp = client.get(
        "/api/form-kits/priv-kit/pdf",
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert resp.content == b"%PDF-priv-kit"


def test_public_pdf_full_success_path_stays_tokenless(_firm_world):
    """Stronger than the 404 pin above: a PUBLIC kit's pdf serves BYTES with
    no token at all, end to end. Mutation: add a blanket auth dependency to
    the pdf route -- red."""
    resp = client.get("/api/form-kits/pub-kit/pdf")
    assert resp.status_code == 200
    assert resp.content == b"%PDF-pub-kit"


def test_single_kit_routes_read_metadata_exactly_once(_firm_world, monkeypatch):
    """ONE live metadata read serves BOTH single-kit gates (publish +
    visibility): each gate loading independently doubled the GCS read per
    schema/pdf request (vccy fresh-eyes round 2). Mutation: add a second
    _load_live_metadata call to either route -- red."""
    store = _TwoKitStore()
    calls = []
    orig = store.load_metadata

    async def counting(kit_id):
        calls.append(kit_id)
        return await orig(kit_id)

    store.load_metadata = counting
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    resp = client.get(
        "/api/form-kits/priv-kit/schema",
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert calls == ["priv-kit"]

    calls.clear()
    resp = client.get("/api/form-kits/pub-kit/pdf")
    assert resp.status_code == 200
    assert calls == ["pub-kit"]


def test_empty_allowlist_hides_private_even_for_claimed_firm(_firm_world, monkeypatch):
    """FAIL-CLOSED pin: a firms store answering [] (disabled, broken, firm
    suspended) hides the private kit even from a caller whose token CLAIMS
    the owning firm -- an outage narrows visibility, never widens it.
    Mutation: treat an empty allowlist as allow-all in _require_visible
    (`if allowed and kit_id not in allowed`) -- red."""
    monkeypatch.setattr(fkr, "get_allowed_kits", lambda firm_id: [])
    for path in ("/api/form-kits/priv-kit/schema", "/api/form-kits/priv-kit/pdf"):
        resp = client.get(path, headers={"Authorization": "Bearer tok-a"})
        assert resp.status_code == 404, path
    resp = client.get("/api/form-kits", headers={"Authorization": "Bearer tok-a"})
    assert _list_ids(resp) == ["pub-kit"]


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


# The five routes that carry user data or gate paid work. Update this list ONLY
# together with the prose enumerations in:
#   docs/components/auth.md            ("HTTP routes (bd polyglot-pdf-z2is)")
#   docs/components/config-deployment.md  (the VFF_DISABLE_AUTH bullet)
_EXPECTED_GATED_ROUTES = {
    ("GET", "/api/form-kits"),
    ("GET", "/api/form-kits/{kit_id}/schema"),
    ("POST", "/api/fill-pdf"),
    ("POST", "/api/tts/spellback"),
    ("POST", "/api/tts/intro"),
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
    #
    # A schema-VALID body (`value`, per SpellbackRequest) so the 401 is
    # unambiguously require_auth and not a 422 -- same discipline as _FILL_BODY
    # above. require_auth runs ahead of body validation, so a wrong-shaped body
    # would still 401 here and the test would pass for the wrong reason.
    resp = client.post("/api/tts/spellback",
                       json={"value": "A1234", "language": "Spanish"})
    assert resp.status_code == 401
