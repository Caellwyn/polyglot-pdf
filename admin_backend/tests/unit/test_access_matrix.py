"""The (method, path, gate) access matrix for the ADMIN service, over real
HTTP (bd polyglot-pdf-fr20a, sprint 23 workstream C1). The admin service has
no WebSocket surface -- the WS half of this bead lives in
backend/tests/integration/test_access_matrix.py.

SET-DERIVED, not hand-listed: reuses test_admin_route_auth.py's own
`_business_routes`/`_dependency_names_for` helpers (imported, not copied) so
this file cannot drift from the route table that test already pins.

ACTORS exercised (bd's own vocabulary, mapped onto this service's THREE
composite-gate actor kinds plus the two simple ones):
  anonymous       -- no credential at all
  app admin       -- CompositeActor / AdminActor, is_app_admin=True
  firm-A manager  -- CompositeActor, kind=firm_manager, firm_id=firm-a
  firm-B manager  -- CompositeActor, kind=firm_manager, firm_id=firm-b
  firm-A employee -- CompositeActor, kind=firm_employee, firm_id=firm-a
  editor          -- a Firebase token shaped like the schema-editor's own
                     credential (schema_editor_role claim, no app_admin) --
                     proves the editor cannot reach the admin surface AT ALL,
                     since admin_backend is a SEPARATE FastAPI app/service
                     the editor credential was never designed to reach.
  client link     -- N/A for this service (link tokens are the PUBLIC
                     backend's client credential only; the admin service has
                     no route that accepts one -- see
                     test_no_admin_route_accepts_a_client_link_shaped_token).

MUST PROVE (bead text, this service's share of it):
  - firm-A cannot read firm-B's private links/users/ledger (via the
    firm-scoped composite-gate routes: GET /admin/firms/{firm_id}/links,
    GET /admin/firms/{firm_id}/usage, the /admin/users/* by-uid routes).
  - editor cannot reach admin.
  - every refusal on an oracle-sensitive door (another firm's resource) is
    the uniform 404, never 403 (403 would leak the firm/jti/uid exists).
  - a route added without a classification fails CI
    (test_every_registered_route_is_classified, this file's own copy of
    test_admin_route_auth.py's set pin, kept independent so a change to one
    file's allowlist cannot silently mask a gap the other would have caught).

Dependency faking follows THIS SERVICE's own established pattern
(test_admin_link_routes.py, test_composite_gate.py): `app.dependency_overrides`
for actor-shaped tests that exercise ROUTE BEHAVIOUR, and the module-level
`_fake_firebase` shape for tests of the GATE ITSELF. No app.dependency_overrides
usage exists on the public-backend suite (it patches verify_token instead) --
the two files intentionally follow their OWN app's existing convention rather
than converging on one.

ASCII only.
"""
from __future__ import annotations

import sys
import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.services.admin_auth import (
    ACTOR_KIND_APP_ADMIN,
    ACTOR_KIND_FIRM_EMPLOYEE,
    ACTOR_KIND_FIRM_MANAGER,
    CompositeActor,
    require_app_admin,
    require_app_admin_or_owning_manager,
    require_app_admin_or_owning_manager_or_employee,
)
from admin_backend.tests.unit.test_admin_route_auth import (
    _business_routes,
    _dependency_names_for,
)

client = TestClient(app)


# ===========================================================================
# 1. THE SET PIN -- every registered route classified, derived from the live
#    app. A route added without one of the five recognized gates fails here.
#    (Kept as this file's OWN derivation, independent of
#    test_admin_route_auth.py's, per CLAUDE.md scar #8's "the rule must have
#    ONE home" read the OTHER way: two independent pins of the SAME property
#    catch a bug in either one's bookkeeping, which a single shared pin
#    cannot.)
# ===========================================================================

_KNOWN_GATE_NAMES = {
    "require_app_admin",
    "require_firm_manager",
    "require_app_admin_or_owning_manager",
    "require_google_oidc",
    "require_app_admin_or_owning_manager_or_employee",
}


def test_every_registered_route_is_classified():
    """Exit criterion 1 for this service. Mutation: register a route with no
    Depends(require_*) -- red, naming the offending route."""
    offenders = []
    for route in _business_routes():
        names = _dependency_names_for(route) & _KNOWN_GATE_NAMES
        if len(names) != 1:
            methods = sorted(getattr(route, "methods", None) or [])
            offenders.append(f"{methods} {route.path}: found gates {sorted(names)}")
    assert not offenders, (
        "route(s) on the admin service with no recognized single gate: "
        + "; ".join(offenders)
    )


def test_removing_a_gate_turns_the_matrix_red():
    """PROVES the pin catches a real omission -- exit criterion 1's own
    mutation-test requirement, run permanently. Registers a throwaway
    ungated route directly on the live app and confirms the SAME derivation
    this file's set pin uses flags it, then removes it so no other test's
    view of app.routes is polluted."""
    from fastapi import APIRouter

    throwaway = APIRouter()

    @throwaway.get("/admin/_test_ungated_route_fr20a")
    async def _ungated():  # pragma: no cover -- never invoked
        return {"ok": True}

    before = list(app.routes)
    app.include_router(throwaway)
    try:
        offenders = [
            route.path for route in _business_routes()
            if len(_dependency_names_for(route) & _KNOWN_GATE_NAMES) != 1
        ]
        assert "/admin/_test_ungated_route_fr20a" in offenders
    finally:
        app.router.routes = before


# ===========================================================================
# 2. ANONYMOUS -- every business route refuses a caller with no credential
#    at all. 401 (require_app_admin* gates) or 401/403 (require_google_oidc,
#    which 503s only on its OWN misconfiguration, never admits anonymous).
# ===========================================================================

def _sample_of_every_gate_kind():
    """One representative route per gate name, for the anonymous sweep --
    not every route (that would just repeat the same dependency's own
    already-covered behavior N times), but at least one per DISTINCT gate so
    the anonymous case is proven against each gate shape once."""
    seen_gates = set()
    picked = []
    for route in _business_routes():
        names = _dependency_names_for(route) & _KNOWN_GATE_NAMES
        if len(names) != 1:
            continue
        gate = next(iter(names))
        if gate in seen_gates:
            continue
        seen_gates.add(gate)
        methods = sorted(getattr(route, "methods", None) or [])
        if methods:
            picked.append((methods[0], route.path))
    return picked


def test_anonymous_is_refused_on_every_gate_kind():
    for method, path in _sample_of_every_gate_kind():
        # A path template needs a placeholder value to route at all --
        # any non-empty string reaches the gate (which runs before any
        # path-param validation on every one of these routes).
        concrete = path.format(firm_id="firm-a", uid="u1", jti="j1",
                              kit_id="k1", channel="demo", alert_id="a1")
        resp = client.request(method, concrete)
        # 503 is legitimate ONLY for require_google_oidc's own
        # misconfiguration branch (an empty audience/allowlist fails closed
        # rather than admitting anonymous) -- see admin-service.md's
        # "require_google_oidc" section. No OTHER gate may ever answer 503
        # to a bare anonymous request.
        allowed = (401, 403, 422, 404)
        if "require_google_oidc" in _dependency_names_for(
                next(r for r in _business_routes() if r.path == path)):
            allowed = allowed + (503,)
        assert resp.status_code in allowed, (
            method, concrete, resp.status_code, resp.text)
        assert resp.status_code != 200, (method, concrete, resp.text)


# ===========================================================================
# 3. EDITOR CANNOT REACH ADMIN.
#
# The schema editor's credential (backend/services/editor_auth.py) is a
# Firebase JWT with a `schema_editor_role` claim and NO `app_admin` claim.
# From require_app_admin's point of view that is indistinguishable from any
# other non-admin Firebase account: the editor claim is one this service
# never reads (mirrors auth.md's "two separate allowlists" decision). Proven
# at the GATE level (the fake-Firebase pattern test_composite_gate.py
# already established) rather than over real HTTP, since faking a verified
# Firebase token for a real request needs the same firebase_admin.auth stub
# either way.
# ===========================================================================

def _fake_firebase(monkeypatch, claims=None, raises=None):
    """Same shape as test_composite_gate.py's own helper -- kept here as an
    independent copy rather than imported, so a change to that file's
    fixture cannot silently change what THIS file proves."""
    class _Auth:
        @staticmethod
        def verify_id_token(_tok, check_revoked=False):
            if raises is not None:
                raise raises
            return claims

    mod = types.ModuleType("firebase_admin")
    mod.auth = _Auth
    mod._apps = {"[DEFAULT]": object()}
    mod.initialize_app = lambda *a, **k: None

    monkeypatch.setitem(sys.modules, "firebase_admin", mod)
    monkeypatch.setitem(sys.modules, "firebase_admin.auth", _Auth)
    import admin_backend.services.admin_auth as aa
    monkeypatch.setattr(aa, "_dev_bypass_allowed", lambda: False)


@pytest.mark.asyncio
async def test_an_editor_shaped_token_cannot_reach_require_app_admin(monkeypatch):
    _fake_firebase(monkeypatch, {
        "uid": "ed-1", "email": "ed@x.example",
        "schema_editor_role": "editor",
    })
    with pytest.raises(HTTPException) as exc:
        await require_app_admin("Bearer t")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_an_editor_shaped_token_cannot_reach_the_composite_gate_either(monkeypatch):
    """Not just the strict admin gate -- the widest gate on this service
    (app admin OR manager OR employee) still refuses an editor-shaped
    account, because it carries none of app_admin/firm_role."""
    _fake_firebase(monkeypatch, {
        "uid": "ed-1", "email": "ed@x.example",
        "schema_editor_role": "editor",
    })
    with pytest.raises(HTTPException) as exc:
        await require_app_admin_or_owning_manager_or_employee("Bearer t")
    assert exc.value.status_code == 403


def test_no_admin_route_accepts_a_client_link_shaped_token(monkeypatch):
    """The client-link credential (one dot, HMAC-signed, no Firebase claims
    at all) is not even a WELL-FORMED Firebase JWT -- every admin gate calls
    fb_auth.verify_id_token directly (never the public backend's shape
    dispatcher), so a link token fails Firebase verification outright as a
    malformed token, landing on the SAME 401 a garbage string would. This is
    a real HTTP round trip against the REAL fb_auth.verify_id_token (no fake
    Firebase AUTH) precisely to prove the negative over the actual verifier,
    not a mock of it.

    bd polyglot-pdf-21m1y: verify_admin_token self-inits firebase_admin with
    ADC when no app exists (admin_auth.py's own "OWN the init" comment), so
    this test used to reach a real firebase_admin app -- harmlessly, since a
    malformed token fails LOCAL parsing before any network call, but still a
    real-Firestore-adjacent reach the no-real-Firestore guard now refuses on
    principle. Pre-seed a REAL firebase_admin.App with a STUB credential
    (never asked for a token: verify_id_token rejects the malformed JWT
    during local parsing, before any credential is used) so the app exists
    without touching ADC or the network, and verify_admin_token's own
    self-init is skipped (it only fires when _apps is empty) -- the test
    still exercises the real verify_id_token, just against a harmless app.
    """
    import firebase_admin as fb
    from firebase_admin import credentials

    class _StubCredential(credentials.Base):
        def get_credential(self):  # pragma: no cover -- never reached
            raise AssertionError(
                "a malformed token must fail local parsing before any "
                "credential is used"
            )

    app = fb.App("[DEFAULT]", _StubCredential(), {})
    monkeypatch.setitem(fb._apps, "[DEFAULT]", app)
    try:
        resp = client.get("/admin/whoami",
                          headers={"Authorization": "Bearer not.a.jwt"})
        assert resp.status_code == 401, resp.text
    finally:
        fb._apps.pop("[DEFAULT]", None)


# ===========================================================================
# 4. CROSS-TENANT: firm-A cannot read firm-B's links/usage; firm-A employee
#    scoped identically. Every refusal is the uniform 404 (never 403 --
#    that would leak the OTHER firm's existence).
# ===========================================================================

ADMIN_ACTOR = CompositeActor(uid="admin-1", email="ops@example.com",
                             kind=ACTOR_KIND_APP_ADMIN)
FIRM_A_MANAGER = CompositeActor(uid="mgr-a", email="ada@firm-a.example",
                                kind=ACTOR_KIND_FIRM_MANAGER, firm_id="firm-a")
FIRM_B_MANAGER = CompositeActor(uid="mgr-b", email="bo@firm-b.example",
                                kind=ACTOR_KIND_FIRM_MANAGER, firm_id="firm-b")
FIRM_A_EMPLOYEE = CompositeActor(uid="emp-a", email="al@firm-a.example",
                                 kind=ACTOR_KIND_FIRM_EMPLOYEE,
                                 firm_id="firm-a", employee_id="emp-a")


def _override(actor):
    app.dependency_overrides[require_app_admin_or_owning_manager] = lambda: actor
    app.dependency_overrides[
        require_app_admin_or_owning_manager_or_employee] = lambda: actor


@pytest.fixture
def as_firm_a_manager():
    _override(FIRM_A_MANAGER)
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def as_firm_b_manager():
    _override(FIRM_B_MANAGER)
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def as_firm_a_employee():
    _override(FIRM_A_EMPLOYEE)
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def as_admin():
    _override(ADMIN_ACTOR)
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_firm_A_manager_cannot_read_firm_Bs_link_history(as_firm_a_manager):
    """GET /admin/firms/{firm_id}/links -- the fifth-gate route. Both the
    _require_owning_firm check (link_routes.py) and channel validation run
    before any Firestore touch, so no fake DB is needed for this refusal."""
    resp = client.get("/admin/firms/firm-b/links", params={"channel": "demo"})
    assert resp.status_code == 404, resp.text


def test_firm_A_employee_cannot_read_firm_Bs_link_history(as_firm_a_employee):
    """The SAME 404-not-403 rule extends to the third actor kind (bd
    polyglot-pdf-scaig's own extension of _require_owning_firm)."""
    resp = client.get("/admin/firms/firm-b/links", params={"channel": "demo"})
    assert resp.status_code == 404, resp.text


def test_firm_A_manager_CAN_read_their_own_link_history(as_firm_a_manager, monkeypatch):
    """Positive control, over a minimal fake Firestore -- the matrix does
    not just refuse everything. Only firm-a's OWN links collection needs to
    exist; an empty result set is a perfectly good 200."""
    class _EmptySnap:
        exists = False
        def to_dict(self):
            return None

    class _EmptyQuery:
        def where(self, *a, **k):
            return self
        def stream(self):
            return iter([])

    class _EmptyCollection:
        def document(self, doc_id):
            return _EmptySnap()
        def where(self, *a, **k):
            return _EmptyQuery()
        def stream(self):
            return iter([])

    class _EmptyDb:
        def collection(self, name):
            return _EmptyCollection()

    import admin_backend.routes.link_routes as admin_link_routes
    monkeypatch.setattr(admin_link_routes, "_db", lambda: _EmptyDb())

    resp = client.get("/admin/firms/firm-a/links", params={"channel": "demo"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["links"] == []


def test_firm_B_manager_cannot_read_firm_As_usage(as_firm_a_manager):
    """GET /admin/firms/{firm_id}/usage -- a SEPARATE per-module
    _require_owning_firm copy (usage_routes.py), independently proven here
    so a fix to one module's copy is not mistaken for fixing the other's."""
    resp = client.get("/admin/firms/firm-b/usage",
                      params={"month": "2026-01", "channel": "demo"})
    assert resp.status_code == 404, resp.text


def test_an_app_admin_CAN_read_any_firms_usage(as_admin, monkeypatch):
    """Positive control for the admin actor's unrestricted reach, over a
    minimal fake so the read completes instead of 503ing on a real client."""
    class _ExistingFirmSnap:
        exists = True

    class _EmptyUsageSnap:
        exists = False
        def to_dict(self):
            return None

    class _UsageSubcollection:
        def document(self, doc_id):
            return _EmptyUsageDocRef()

    class _EmptyUsageDocRef:
        def get(self):
            return _EmptyUsageSnap()

    class _FirmDocRef:
        def get(self):
            return _ExistingFirmSnap()
        def collection(self, name):
            return _UsageSubcollection()

    class _FirmsCollection:
        def document(self, firm_id):
            return _FirmDocRef()

    class _EmptyDb:
        def collection(self, name):
            return _FirmsCollection()

    import admin_backend.routes.usage_routes as usage_routes
    monkeypatch.setattr(usage_routes, "_db", lambda: _EmptyDb())

    resp = client.get("/admin/firms/firm-b/usage",
                      params={"month": "2026-01", "channel": "demo"})
    assert resp.status_code == 200, resp.text


# ===========================================================================
# 5. THE /admin/users BY-UID ROUTES -- a manager cannot act on an account
#    outside the resolved firm (also 404-not-403, this rule's own separate
#    home in user_routes.py).
# ===========================================================================

def test_a_firm_A_manager_cannot_disable_an_account_outside_their_firm(
        as_firm_a_manager, monkeypatch):
    """user_routes.py's _require_account_in_firm: a uid is a bearer of
    nothing, so this must be enforced even though the manager names no
    firm_id at all (their own firm is resolved from the token) -- the
    account itself must resolve into that firm before it can be touched."""
    import admin_backend.services.user_admin as user_admin

    monkeypatch.setattr(
        user_admin, "get_user_claims",
        lambda uid: {"firm_id": "firm-b", "firm_role": "employee"},
    )

    resp = client.patch("/admin/users/someone-elses-uid/disable",
                        json={"disabled": True})
    assert resp.status_code == 404, resp.text


def test_an_app_admin_naming_no_firm_on_create_is_422(as_admin):
    """resolve_target_firm's app-admin branch: no firm to fall back to."""
    resp = client.post("/admin/users", json={
        "email": "new@firm.example", "firm_role": "employee",
    })
    assert resp.status_code == 422, resp.text


def test_a_manager_naming_any_firm_on_create_is_403(as_firm_a_manager):
    """resolve_target_firm's manager branch: naming a firm at all -- even
    their OWN -- is refused; their firm comes from the token, never the
    body."""
    resp = client.post("/admin/users", json={
        "email": "new@firm.example", "firm_role": "employee",
        "firm_id": "firm-a",
    })
    assert resp.status_code == 403, resp.text


# ===========================================================================
# 6. THE SWEEP ROUTE (require_google_oidc) -- a human bearer token (of any
#    kind above) is refused; this gate only ever admits a Google-signed
#    service-account token naming an allowlisted caller email, verified
#    elsewhere (test_google_oidc_gate.py). What THIS matrix proves is that
#    the OTHER actors cannot reach it -- a human credential is not even the
#    right SHAPE this gate accepts.
# ===========================================================================

def test_no_human_actor_can_reach_the_sweep_route_by_dependency_override():
    """dependency_overrides only reach the FOUR gates this file's fixtures
    target (require_app_admin / the composite / its employee-widened
    sibling) -- require_google_oidc is a per-route FACTORY closure, not one
    of those functions, so overriding the others proves nothing about it.
    This test instead confirms the real, unoverridden route still requires
    Google OIDC verification for a plain bearer string, over real HTTP."""
    resp = client.post("/admin/links/sweep-expired",
                       headers={"Authorization": "Bearer human-token"})
    assert resp.status_code in (401, 503), resp.text
