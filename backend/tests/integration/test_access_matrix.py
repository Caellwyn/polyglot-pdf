"""The (method, path, gate) access matrix for the PUBLIC backend, over real
HTTP and the real WebSocket (bd polyglot-pdf-fr20a, sprint 23 workstream C1).

SET-DERIVED, not hand-listed: the HTTP half is built on top of
test_http_route_auth.py's own `_routes_depending_on` helper (imported, not
copied) so this file never drifts from the route table that test already
pins. A route registered on `backend.main.app` with no recognized gate name
fails `test_every_registered_route_is_classified` below.

ACTORS exercised across the matrix (bd's own vocabulary):
  anonymous            -- no credential at all
  firm-A employee      -- Firebase token, firm_id=firm-a, firm_role=employee
  firm-A manager       -- Firebase token, firm_id=firm-a, firm_role=manager
  firm-B manager       -- Firebase token, firm_id=firm-b, firm_role=manager
  client link (firm A) -- a link token naming firm-a's private kit
  client link (firm B) -- a link token naming firm-b's private kit
  editor               -- Firebase token, schema_editor_role=editor (no firm)
  dev-claimless        -- a verified Firebase account with NO claims at all
                          (the maintainer's own pre-enrolment shape)

MUST PROVE (bead text):
  - firm-A cannot read firm-B's private kit/archive.
  - a client link reaches only its own kit + the paid/browse doors.
  - an editor-shaped credential cannot reach the app-admin surface (that
    surface lives on a DIFFERENT app entirely -- see test_access_matrix.py
    in admin_backend/tests/unit/ for the same actor against admin_backend).
  - a Firebase token with no claims at all gets only the browse set.
  - every refusal on an oracle-sensitive door (private kit visibility) is
    the uniform 404, never 401/403 (401/403 would leak existence).

WS cases (bd's own vocabulary):
  1. anonymous is refused BEFORE accept (bad/garbage token -> 1008,
     websocket_connect raises before any accept).
  2. a firm-B link naming a firm-A kit hits the kit-mismatch branch in
     websocket_routes.py and closes 1008.
  3. a staff token naming a kit outside its firm -- see
     test_a_STAFF_token_naming_a_kit_outside_its_firm_is_NOT_refused below:
     this is a REAL GAP, reported per the bead's own "report, don't fix"
     instruction (out of this file's declared surfaces -- production code
     is backend/routes/websocket_routes.py).

Every test here PATCHES THE VERIFIER, never app.dependency_overrides --
matching test_http_route_auth.py and test_websocket_fill_web.py's own
established pattern in this repo (there is no dependency_overrides usage
anywhere in the public-backend suite).

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.routes.form_kit_routes as fkr
import backend.routes.pdf_fill_routes as pfr
import backend.routes.websocket_routes as wsr
from backend.main import app
from backend.services.auth import (
    require_auth,
    require_firm_manager,
    require_paid_client_work,
    require_signin,
)
from backend.services.form_kits import FormKitNotFound
from backend.tests.unit.test_http_route_auth import _routes_depending_on

client = TestClient(app)


# ---------------------------------------------------------------------------
# Actor claims (Firebase-shaped). Synthetic firm ids / kit ids throughout --
# CLAUDE.md scar #10: never a real, named form kit.
# ---------------------------------------------------------------------------

_TOKENS = {
    "tok-anon-claimless": {"uid": "uid-newcomer", "email": "newcomer@x.example"},
    "tok-firm-a-employee": {"uid": "emp-a", "firm_id": "firm-a", "firm_role": "employee"},
    "tok-firm-a-manager": {"uid": "mgr-a", "firm_id": "firm-a", "firm_role": "manager"},
    "tok-firm-b-manager": {"uid": "mgr-b", "firm_id": "firm-b", "firm_role": "manager"},
    "tok-editor": {"uid": "ed-1", "email": "ed@x.example", "schema_editor_role": "editor"},
}


class _AccessMatrixStore:
    """One public + three private kits (two for firm-a, one for firm-b),
    synthetic ids only."""

    def __init__(self):
        self.meta = {
            "pub-kit": {"status": "complete"},
            "kit-a-priv": {
                "status": "complete",
                "visibility": "private",
                "owner_firm_id": "firm-a",
            },
            "kit-b-priv": {
                "status": "complete",
                "visibility": "private",
                "owner_firm_id": "firm-b",
            },
            # A SECOND private firm-a kit, so the client-link cross-kit row
            # reaches the visibility gate instead of 404ing on a kit that
            # does not exist (an unknown id is refused before any gate runs).
            "kit-a-second": {
                "status": "complete",
                "visibility": "private",
                "owner_firm_id": "firm-a",
            },
        }
        self.archive = {
            "kit-a-priv": {"2024-01": {"schema": {"rev": "a"},
                                        "metadata": {"published_at": "2024-01-01T00:00:00+00:00"}}},
            "kit-b-priv": {"2024-01": {"schema": {"rev": "b"},
                                        "metadata": {"published_at": "2024-01-01T00:00:00+00:00"}}},
        }

    async def load_manifest(self, manifest_file: str = "index.json") -> dict:
        from backend.services.form_kits import normalize_manifest
        return normalize_manifest({"forms": [
            {"id": "pub-kit", "label": "Public"},
            {"id": "kit-a-priv", "label": "Firm A private"},
            {"id": "kit-b-priv", "label": "Firm B private"},
            {"id": "kit-a-second", "label": "Firm A private, second"},
        ]})

    async def load_metadata(self, kit_id: str):
        return self.meta.get(kit_id)

    async def load_schema(self, kit_id: str, schema_file: str = "schema.json"):
        return {"kit": kit_id}

    async def list_archived_markers(self, kit_id: str) -> list:
        return list(self.archive.get(kit_id, {}))

    async def load_archived_metadata_or_none(self, kit_id: str, marker: str):
        entry = self.archive.get(kit_id, {}).get(marker)
        return entry.get("metadata") if entry else None

    async def load_archived_revision(self, kit_id: str, marker: str):
        entry = self.archive.get(kit_id, {}).get(marker)
        if entry is None:
            raise FormKitNotFound(f"no archive {kit_id}/{marker}")
        return entry["schema"]

    async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
        # A minimal but VALID pdf (fitz must be able to open it) -- the same
        # trick test_http_route_auth.py's _TwoKitStore uses, needed for any
        # matrix case that reaches the real /api/fill-pdf PyMuPDF render
        # rather than stopping at the auth gate.
        import fitz

        doc = fitz.open()
        doc.new_page()
        data = doc.tobytes()
        doc.close()
        return data


_ALLOWLISTS = {"firm-a": ["kit-a-priv"], "firm-b": ["kit-b-priv"]}


def _fake_verify(token: str, require_enrolment: bool = True, **_kw) -> dict:
    """Stands in for backend.services.auth.verify_token -- SAME SIGNATURE,
    including the real enrolment check, so require_signin (which passes
    require_enrolment=False) and require_auth (which does not) diverge
    exactly as they do in production. Without honoring this flag, a
    claimless/editor token would wrongly pass require_auth's real 403 gate
    here, since the whole point of faking claims is to skip Firebase, not
    to skip the enrolment RULE this matrix is proving."""
    claims = _TOKENS.get(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="bad token")
    claims = dict(claims)
    if require_enrolment and not (claims.get("firm_id") or claims.get("vff_dev")):
        raise HTTPException(status_code=403,
                            detail="This account is not enrolled for the voice application")
    return claims


@pytest.fixture
def matrix_world(monkeypatch):
    """Wire the two-firm store + token->claims map + firm allowlists."""
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    store = _AccessMatrixStore()
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(pfr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr("backend.services.auth.verify_token", _fake_verify)
    monkeypatch.setattr(fkr, "verify_token", _fake_verify)
    monkeypatch.setattr(
        "backend.services.kit_gates.get_allowed_kits",
        lambda firm_id: _ALLOWLISTS.get(firm_id, []),
    )
    return store


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# 1. THE SET PIN -- every registered route classified, derived from the live
#    app, never hand-listed. A route added without a classification (one of
#    the recognized gate dependencies below) fails here.
# ===========================================================================

_KNOWN_GATES = (require_signin, require_auth, require_paid_client_work,
                require_firm_manager)

# Routes with NO auth dependency at all. Each is DELIBERATE and documented
# elsewhere (auth.md): the public-PDF non-gate (vccy), and the two
# out-of-scope surfaces this bead does not touch (dev console log / editor+
# author role-token routes, C4's own workstream; disclaimer-acceptance,
# likewise C4). Websocket routes are handled separately below (WS has no
# `Depends` shape http routes have -- see the WS section).
_DELIBERATELY_UNGATED_HTTP_ROUTES = {
    ("GET", "/api/form-kits/{kit_id}/pdf"),   # public-kit non-gate (vccy)
    ("POST", "/dev/console-log"),             # dev-only, C4 workstream
    ("POST", "/api/disclaimer-acceptance"),   # C4 workstream. Registered
                                               # ONCE: disclaimer_routes.router
                                               # carries prefix="/api" itself
                                               # and main.py includes it bare,
                                               # so there is no un-prefixed
                                               # twin of this path.
    ("POST", "/api/links/open"),              # THE CLIENT. Deliberately
                                               # unauthenticated -- the
                                               # signed link token IS the
                                               # credential (bd ugm6); see
                                               # link_routes.py's own module
                                               # docstring.
}

# The editor/author surface is a SEPARATE credential system
# (backend/services/editor_auth.py) with its own dependency
# (require_editor_actor) -- not one of this bead's four voice-app gates, but
# still a recognized, classified surface. Listed by module prefix so a new
# editor route does not need updating here file-by-file.
_EDITOR_SURFACE_MODULES = ("editor_kit_routes.py", "editor_readiness_routes.py")


def _all_http_routes() -> set:
    """(method, path) for every route on the real app, WS routes excluded."""
    from starlette.routing import WebSocketRoute
    out = set()
    for route in app.routes:
        if isinstance(route, WebSocketRoute):
            continue
        path = getattr(route, "path", None)
        if not path:
            continue
        if path in {"/docs", "/openapi.json", "/redoc",
                    "/docs/oauth2-redirect", "/health", "/version"}:
            continue
        for method in sorted(getattr(route, "methods", None) or []):
            out.add((method, path))
    return out


def _endpoint_module_for(method: str, path: str) -> str:
    for route in app.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or []):
            endpoint = getattr(route, "endpoint", None)
            module = getattr(endpoint, "__module__", "") or ""
            return module.rsplit(".", 1)[-1] + ".py"
    return ""


def test_every_registered_route_is_classified():
    """THE CI FAILSAFE (exit criterion 1). Every HTTP route on the live app
    must be either: (a) wired to one of the four recognized voice-app gates,
    (b) on the editor/author surface (its own credential system), or
    (c) explicitly allowlisted as deliberately ungated.

    Mutation: add a new route with no Depends(require_*) and no allowlist
    entry -- this goes red, naming the offending route.
    """
    gated = set()
    for gate in _KNOWN_GATES:
        gated |= _routes_depending_on(gate)

    all_routes = _all_http_routes()
    unclassified = []
    for route in sorted(all_routes - gated - _DELIBERATELY_UNGATED_HTTP_ROUTES):
        method, path = route
        module = _endpoint_module_for(method, path)
        if module in _EDITOR_SURFACE_MODULES:
            continue
        unclassified.append(route)

    assert not unclassified, (
        "route(s) registered with no recognized gate and no ungated-"
        f"allowlist entry: {unclassified} -- classify them in "
        "test_access_matrix.py (_KNOWN_GATES / "
        "_DELIBERATELY_UNGATED_HTTP_ROUTES / _EDITOR_SURFACE_MODULES)"
    )


def test_removing_a_gate_turns_the_matrix_red(monkeypatch):
    """PROVES the set pin actually catches a real omission (exit criterion
    1's own mutation-test requirement, run permanently rather than by hand):
    register a throwaway ungated route directly on the live app and confirm
    test_every_registered_route_is_classified's own derivation flags it."""
    from fastapi import APIRouter

    throwaway = APIRouter()

    @throwaway.get("/_test_ungated_route_fr20a")
    async def _ungated():  # pragma: no cover -- never invoked
        return {"ok": True}

    before = list(app.routes)
    app.include_router(throwaway)
    try:
        gated = set()
        for gate in _KNOWN_GATES:
            gated |= _routes_depending_on(gate)
        all_routes = _all_http_routes()
        unclassified = all_routes - gated - _DELIBERATELY_UNGATED_HTTP_ROUTES
        assert ("GET", "/_test_ungated_route_fr20a") in unclassified
    finally:
        app.router.routes = before


# ===========================================================================
# 2. HTTP CROSS-TENANT MATRIX -- firm A vs firm B, private kit + archive.
# ===========================================================================

@pytest.mark.parametrize("path", [
    "/api/form-kits/kit-b-priv/schema",
    "/api/form-kits/kit-b-priv/pdf",
    "/api/form-kits/kit-b-priv/archive",
    "/api/form-kits/kit-b-priv/archive/2024-01/schema",
])
def test_firm_A_cannot_read_firm_Bs_private_kit_or_archive(matrix_world, path):
    """Cross-tenant read isolation, the bead's headline requirement. Every
    one of these must be the UNIFORM 404 -- never 401/403, which would leak
    that kit-b-priv exists at all to a firm that cannot see it."""
    resp = client.get(path, headers=_bearer("tok-firm-a-manager"))
    assert resp.status_code == 404, (path, resp.status_code, resp.text)


@pytest.mark.parametrize("path", [
    "/api/form-kits/kit-a-priv/schema",
    "/api/form-kits/kit-a-priv/pdf",
    "/api/form-kits/kit-a-priv/archive",
    "/api/form-kits/kit-a-priv/archive/2024-01/schema",
])
def test_firm_B_cannot_read_firm_As_private_kit_or_archive(matrix_world, path):
    resp = client.get(path, headers=_bearer("tok-firm-b-manager"))
    assert resp.status_code == 404, (path, resp.status_code, resp.text)


def test_firm_A_manager_CAN_read_firm_As_own_private_kit(matrix_world):
    """Positive control: the matrix does not just refuse everything."""
    resp = client.get("/api/form-kits/kit-a-priv/schema",
                      headers=_bearer("tok-firm-a-manager"))
    assert resp.status_code == 200, resp.text


def test_firm_A_employee_can_also_read_firm_As_own_private_kit(matrix_world):
    """Visibility is a FIRM property, not a role property -- an employee
    reads the same kits their manager does (role only matters for the
    retire WRITE path, out of this file's read-focused matrix)."""
    resp = client.get("/api/form-kits/kit-a-priv/schema",
                      headers=_bearer("tok-firm-a-employee"))
    assert resp.status_code == 200, resp.text


def test_firm_B_manager_cannot_retire_firm_As_kit(matrix_world):
    """The one WRITE path in the matrix. 404, not 403 -- z6bk9's own rule."""
    resp = client.post("/api/form-kits/kit-a-priv/retire",
                       headers=_bearer("tok-firm-b-manager"))
    assert resp.status_code == 404, resp.text


def test_a_firm_A_employee_cannot_retire_firm_As_own_kit(matrix_world):
    """Role matters here: an employee is not a manager, so even their OWN
    firm's kit is refused (dmjl5's manager-only write rule). Distinguishing
    from the cross-tenant case above: this is 404 too, because
    _require_firm_owns_private_kit checks manager_firm_id() before
    ownership, and a non-manager gets the identical not-found shape."""
    resp = client.post("/api/form-kits/kit-a-priv/retire",
                       headers=_bearer("tok-firm-a-employee"))
    assert resp.status_code == 404, resp.text


# ===========================================================================
# 3. THE BROWSE SET -- a claimless Firebase account (no firm, no dev claim)
#    reaches ONLY require_signin routes, never require_auth/paid ones.
# ===========================================================================

def test_a_claimless_token_reaches_the_browse_routes(matrix_world):
    for path in ("/api/form-kits", "/api/form-kits/pub-kit/schema"):
        resp = client.get(path, headers=_bearer("tok-anon-claimless"))
        assert resp.status_code == 200, (path, resp.text)


def test_a_claimless_token_is_refused_by_every_gated_route(matrix_world):
    """The other half: browse != act. A claimless account must not reach
    ANY require_auth-gated route -- it authenticates fine (401 would be
    wrong) but is not enrolled (403)."""
    cases = [
        ("GET", "/api/form-kits/pub-kit/archive"),
        ("POST", "/api/form-kits/kit-a-priv/retire"),
        ("POST", "/api/links/mint", {"kit_id": "pub-kit"}),
        ("POST", "/api/fill-pdf", {
            "kit_id": "pub-kit", "pdf_filename": "form.pdf",
            "field_values": {}, "form_schema": {"fields": []},
        }),
        ("POST", "/api/tts/notice", {"key": "x", "language": "English"}),
    ]
    for method, path, *body in cases:
        kwargs = {"headers": _bearer("tok-anon-claimless")}
        if body:
            kwargs["json"] = body[0]
        resp = client.request(method, path, **kwargs)
        assert resp.status_code == 403, (method, path, resp.status_code, resp.text)


def test_anonymous_no_credential_at_all_is_401_on_gated_routes(matrix_world):
    """Truly anonymous (no Authorization header) is a 401 -- distinct from
    the claimless-but-signed-in 403 above. Collapsing the two would mis-
    report "you have no credential" as "you're not enrolled"."""
    resp = client.get("/api/form-kits/pub-kit/archive")
    assert resp.status_code == 401, resp.text
    resp = client.get("/api/form-kits")
    assert resp.status_code == 401, resp.text


# ===========================================================================
# 4. EDITOR CANNOT REACH THE VOICE-APP ENROLLED SET.
#
# An editor-shaped Firebase token (schema_editor_role, no firm_id, no
# vff_dev) is EXACTLY the claimless shape from the voice app's own gate's
# point of view -- editor_auth.py's EDITOR_ROLE_CLAIM is a claim
# require_auth/require_signin never reads (bd polyglot-pdf-lo88's "two
# separate allowlists" decision, auth.py's own docstring). So an editor
# account browses the catalogue like anyone signed in, but is refused by
# every enrolled-only door exactly like a claimless account is.
# ===========================================================================

def test_an_editor_shaped_token_cannot_reach_enrolled_voice_app_routes(matrix_world):
    resp = client.post("/api/fill-pdf", headers=_bearer("tok-editor"), json={
        "kit_id": "pub-kit", "pdf_filename": "form.pdf",
        "field_values": {}, "form_schema": {"fields": []},
    })
    assert resp.status_code == 403, resp.text


def test_an_editor_shaped_token_can_still_browse(matrix_world):
    """It is signed in, so it is not locked out of SELECTING a form -- the
    same 2026-08-25 rule that protects a claimless account (auth.md)."""
    resp = client.get("/api/form-kits", headers=_bearer("tok-editor"))
    assert resp.status_code == 200, resp.text


# ===========================================================================
# 5. CLIENT LINK -- reaches only its own kit + the paid/browse doors.
#    Uses a REAL minted token (not a monkeypatched verifier) so the shape
#    dispatch in require_auth/require_signin is exercised for real.
# ===========================================================================

_LINK_SECRET = "l" * 40


@pytest.fixture
def client_link_world(matrix_world, monkeypatch):
    monkeypatch.setenv("LINK_TOKEN_SECRET", _LINK_SECRET)
    monkeypatch.setenv("LINK_CHANNEL", "demo")

    # Redemption + budget are stubbed hermetically (as the WS suite already
    # does via _stub_link_gates) -- this section is about VISIBILITY
    # scoping, not the money machinery C1's own review covers separately.
    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": 10, "completed_at": None,
        },
    )
    from backend.services import links_store
    monkeypatch.setattr(
        links_store, "get_link",
        lambda jti, channel=None: {"jti": jti, "status": links_store.STATUS_MINTED},
    )
    return None


def _mint(firm_id: str, kit_id: str) -> str:
    from backend.services.link_tokens import mint_link_token
    token, _jti = mint_link_token(firm_id, kit_id, "emp-" + firm_id)
    return token


def test_a_client_link_reaches_its_own_kit(client_link_world):
    token = _mint("firm-a", "kit-a-priv")
    resp = client.get("/api/form-kits/kit-a-priv/schema", headers=_bearer(token))
    assert resp.status_code == 200, resp.text


def test_a_client_link_cannot_reach_a_DIFFERENT_kit_even_in_its_own_firm(client_link_world):
    """firm_allowed_kits() intersects the link's OWN kit with the firm
    allowlist (kit_gates.py) -- a client link is scoped to ONE kit, not to
    its firm's whole allowlist."""
    monkeypatch_extra_kit = _ALLOWLISTS.setdefault("firm-a", [])
    if "kit-a-second" not in monkeypatch_extra_kit:
        monkeypatch_extra_kit.append("kit-a-second")
    try:
        token = _mint("firm-a", "kit-a-priv")
        resp = client.get("/api/form-kits/kit-a-second/schema",
                          headers=_bearer(token))
        assert resp.status_code == 404, resp.text
    finally:
        monkeypatch_extra_kit.remove("kit-a-second")


def test_a_client_link_reaches_the_browse_door_too(client_link_world):
    """Browsing the catalogue must not dead-end the client tier (ugm6)."""
    token = _mint("firm-a", "kit-a-priv")
    resp = client.get("/api/form-kits", headers=_bearer(token))
    assert resp.status_code == 200, resp.text


def test_a_firm_B_client_link_cannot_reach_firm_As_kit(client_link_world):
    token = _mint("firm-b", "kit-a-priv")  # a firm-b link claiming firm-a's kit
    # get_allowed_kits("firm-b") -> ["kit-b-priv"]; kit-a-priv is not in it.
    resp = client.get("/api/form-kits/kit-a-priv/schema", headers=_bearer(token))
    assert resp.status_code == 404, resp.text


def test_a_client_link_cannot_mint_another_link(client_link_world, monkeypatch):
    """Minting needs a uid; a client link's claims carry uid=None (bd
    polyglot-pdf-ugm6 -- see link_routes.mint_link's own check)."""
    import backend.routes.link_routes as lr

    monkeypatch.setattr(lr, "_rc_minting_enabled", lambda: True)
    token = _mint("firm-a", "kit-a-priv")
    resp = client.post("/api/links/mint", headers=_bearer(token),
                       json={"kit_id": "kit-a-priv"})
    assert resp.status_code == 403, resp.text


# ===========================================================================
# 6. THE WEBSOCKET -- real TestClient.websocket_connect, patched verifiers.
# ===========================================================================

_HANDSHAKE = {
    "type": "handshake",
    "schema": {
        "source": "web",
        "form_metadata": {"title": "Contact", "url": "https://example.com"},
        "fields": [{"id": "name", "name": "Full Name", "type": "text"}],
    },
    "current_values": {},
}


def _ws_denial_type_names() -> tuple:
    # Starlette surfaces a pre-accept close as either of these depending on
    # version -- see test_debug_socket_gate.py, this repo's own precedent.
    return ("WebSocketDisconnect", "WebSocketDenialResponse")


def test_ws_anonymous_is_refused_BEFORE_accept(monkeypatch):
    """Case 1 (bead text). A garbage token must never reach accept() -- the
    _verify_ws_credential call happens in a try block strictly before
    `await websocket.accept()` (websocket_routes.py)."""
    with pytest.raises(Exception) as excinfo:
        with client.websocket_connect("/ws/fill?token=not-a-real-token"):
            pass
    assert excinfo.type.__name__ in _ws_denial_type_names(), (
        f"unexpected exception type: {excinfo.type}")


def test_ws_anonymous_refusal_never_calls_accept(monkeypatch):
    """Same case, asserted at the unit level (not just via the ASGI
    exception) so the assertion also demonstrates WHY it fails before
    accept, using the exact route function the WS test suite already drives
    this way (test_websocket_ephemeral.py's own pattern)."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import WebSocket

    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.receive_text = AsyncMock()

    async def _run():
        await wsr.fill_form_from_schema(ws, token="garbage.not-a-real-token-shape",
                                        service=AsyncMock())

    asyncio.run(_run())
    ws.accept.assert_not_awaited()
    ws.close.assert_awaited()
    assert ws.close.await_args.kwargs.get("code") == 1008


def test_ws_firm_B_link_naming_a_firm_A_kit_hits_the_mismatch_branch(monkeypatch):
    """Case 2 (bead text). A firm-B link's handshake names firm-A's kit_id
    -- the token's OWN link_kit_id is firm-B's kit, so this is the
    kit_mismatch branch (websocket_routes.py:1769-1775), not a firm-
    visibility check. Close code 1008, reason token "link_kit_mismatch"."""
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("LINK_TOKEN_SECRET", _LINK_SECRET)
    monkeypatch.setenv("LINK_CHANNEL", "demo")
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-b", "kit-b-priv", "emp-firm-b")

    import time as _clock

    _stamp = int(_clock.time())
    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": _stamp, "completed_at": None,
        },
    )
    from backend.services import links_store
    monkeypatch.setattr(
        links_store, "get_link",
        lambda jti, channel=None: {"jti": jti, "status": links_store.STATUS_MINTED},
    )
    monkeypatch.setattr(wsr, "_handle_fill_session", AsyncMock())

    hostile = dict(_HANDSHAKE)
    hostile["kit_id"] = "kit-a-priv"  # NOT the kit this link names

    with pytest.raises(Exception) as excinfo:
        with client.websocket_connect(f"/ws/fill?token={token}") as ws:
            ws.send_json(hostile)
            ws.receive_json()
    assert excinfo.type.__name__ in _ws_denial_type_names(), (
        f"unexpected exception type: {excinfo.type}")

    # Also assert the DIRECT unit-level mechanism, unambiguous regardless of
    # ASGI transport quirks, and PIN THE REASON TOKEN specifically -- close
    # code 1008 alone is shared with auth_failed/link_redeem_refused, so a
    # bare code assertion here would pass even if enforce_link_redemption
    # (not the kit-mismatch branch) were what actually closed the socket.
    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws2.close = AsyncMock()
    ws2.send_json = AsyncMock()
    ws2.receive_text = AsyncMock(return_value=__import__("json").dumps(hostile))

    seen = {}
    orig_close_ws = wsr._close_ws

    async def _spy_close_ws(websocket, code, reason_token, **kwargs):
        seen["code"] = code
        seen["reason_token"] = reason_token
        return await orig_close_ws(websocket, code, reason_token, **kwargs)

    monkeypatch.setattr(wsr, "_close_ws", _spy_close_ws)

    async def _run():
        await wsr.fill_form_from_schema(ws2, token=token, service=AsyncMock())

    import asyncio

    asyncio.run(_run())
    assert seen == {"code": 1008, "reason_token": "link_kit_mismatch"}


def test_ws_a_STAFF_token_naming_a_kit_outside_its_firm_IS_refused_1008(monkeypatch):
    """Case 3 (bead text): 'a staff token naming a kit outside its firm is
    refused.' CLOSED by sprint 23 C2 (bd polyglot-pdf-bwevj): websocket_routes
    now mirrors the HTTP kit routes' kit_gates.require_visible for a STAFF
    credential, BEFORE any Gemini session -- a private kit outside the
    caller's firm closes 1008 (wire reason "Kit not available"), the same
    uniform shape as the client-link mismatch branch. Before C2 this test
    documented the gap (connect + handshake SUCCEEDED); its assertion is the
    inverse now, so a regression back to the gap has something watching it.
    """
    import asyncio
    import json as _json
    from unittest.mock import AsyncMock, MagicMock
    from backend.services.form_kits import FormKitNotFound
    monkeypatch.setattr(wsr, "verify_token",
                        lambda token, **_kw: {"uid": "mgr-a", "firm_id": "firm-a",
                                              "firm_role": "manager"})
    monkeypatch.setattr(wsr, "_handle_fill_session", AsyncMock())
    # The kit is PRIVATE and not in firm A's allowlist: require_visible refuses.
    monkeypatch.setattr(wsr, "_load_live_metadata", AsyncMock(return_value={"visibility": "private"}))
    monkeypatch.setattr(wsr, "_require_visible", AsyncMock(side_effect=FormKitNotFound("Kit not visible: kit-b-priv")))
    hostile = dict(_HANDSHAKE)
    hostile["kit_id"] = "kit-b-priv"   # firm-A staff naming firm-B's private kit
    ws = MagicMock()
    ws.headers = {}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock(return_value=_json.dumps(hostile))

    async def _run():
        await wsr.fill_form_from_schema(ws, token="tok-firm-a-manager-shape",
                                        service=AsyncMock())
    asyncio.run(_run())
    ws.accept.assert_awaited()
    kit_scoping_close = [c for c in ws.close.await_args_list if c.kwargs.get("code") == 1008]
    assert kit_scoping_close, "the staff kit-scoping refusal is missing again (C2 regression)"
    assert kit_scoping_close[0].kwargs.get("reason") == "Kit not available"
    wsr._handle_fill_session.assert_not_awaited()


def test_ws_a_STAFF_token_naming_a_PUBLIC_or_firm_kit_proceeds(monkeypatch):
    """The other half of the C2 gate: a visible kit passes through to the
    session (require_visible returns), so the gate refuses only what the HTTP
    routes would also 404."""
    import asyncio
    import json as _json
    from unittest.mock import AsyncMock, MagicMock
    monkeypatch.setattr(wsr, "verify_token",
                        lambda token, **_kw: {"uid": "mgr-a", "firm_id": "firm-a",
                                              "firm_role": "manager"})
    monkeypatch.setattr(wsr, "_handle_fill_session", AsyncMock())
    monkeypatch.setattr(wsr, "_load_live_metadata", AsyncMock(return_value={}))
    monkeypatch.setattr(wsr, "_require_published", MagicMock(return_value=None))
    monkeypatch.setattr(wsr, "_require_visible", AsyncMock(return_value=None))
    own = dict(_HANDSHAKE)
    own["kit_id"] = "kit-a-pub"
    ws = MagicMock()
    ws.headers = {}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock(return_value=_json.dumps(own))

    async def _run():
        await wsr.fill_form_from_schema(ws, token="tok-firm-a-manager-shape",
                                        service=AsyncMock())
    asyncio.run(_run())
    assert not [c for c in ws.close.await_args_list if c.kwargs.get("code") == 1008]
    wsr._handle_fill_session.assert_awaited()

def test_ws_client_link_still_hits_kit_mismatch_for_its_own_firm(monkeypatch):
    """Contrast case: a client link (not staff) naming a DIFFERENT kit in
    its OWN firm is still refused -- the kit_mismatch branch is scoped to
    the link's single kit_id, not the firm's whole allowlist (see
    test_a_client_link_cannot_reach_a_DIFFERENT_kit_even_in_its_own_firm's
    HTTP-side twin above). This exists to make the staff-gap test above
    legible as a GAP SPECIFIC TO STAFF TOKENS, not a general WS design
    choice -- the mechanism to refuse this exists for the client-link path
    already; it is simply never invoked for a staff credential."""
    import asyncio
    import json as _json
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("LINK_TOKEN_SECRET", _LINK_SECRET)
    monkeypatch.setenv("LINK_CHANNEL", "demo")
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "kit-a-priv", "emp-a")

    import time as _clock

    _stamp = int(_clock.time())
    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": _stamp, "completed_at": None,
        },
    )
    from backend.services import links_store
    monkeypatch.setattr(
        links_store, "get_link",
        lambda jti, channel=None: {"jti": jti, "status": links_store.STATUS_MINTED},
    )
    monkeypatch.setattr(wsr, "_handle_fill_session", AsyncMock())

    seen = {}
    orig_close_ws = wsr._close_ws

    async def _spy_close_ws(websocket, code, reason_token, **kwargs):
        seen["code"] = code
        seen["reason_token"] = reason_token
        return await orig_close_ws(websocket, code, reason_token, **kwargs)

    monkeypatch.setattr(wsr, "_close_ws", _spy_close_ws)

    hostile = dict(_HANDSHAKE)
    hostile["kit_id"] = "kit-a-second"  # a different kit, same firm

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock(return_value=_json.dumps(hostile))

    async def _run():
        await wsr.fill_form_from_schema(ws, token=token, service=AsyncMock())

    asyncio.run(_run())
    assert seen == {"code": 1008, "reason_token": "link_kit_mismatch"}
