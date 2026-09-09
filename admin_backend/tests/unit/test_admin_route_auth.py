"""Every registered admin-service route carries exactly one of FOUR gates
(bd polyglot-pdf-7w17m).

Cloud Run runs this service with --allow-unauthenticated, so the app-level
gate on every route IS the whole access control -- there is no infrastructure
fallback. Mirrors backend/tests/unit/test_http_route_auth.py's
_routes_depending_on-derived set pins: the set is read off the LIVE app
object, never hand-maintained, so a route added without a gate fails HERE
instead of shipping reachable by anyone with the URL.

The four gates, per the plan ("Admin service" gating section). ALL FOUR now
exist (bd polyglot-pdf-8vgfh lands the last one):
  - require_app_admin -- shipped with GET /admin/whoami (bd
    polyglot-pdf-7w17m).
  - require_app_admin_or_owning_manager -- the composite, shipped with the
    four /admin/users routes; also the gate Epic 2 B4's link listing (GET
    /admin/firms/{firm_id}/links) and revoke (POST /admin/links/{jti}/
    revoke) carry (bd polyglot-pdf-jmiys).
  - require_firm_manager -- exists in backend/services/auth.py over the
    shared rule backend/services/firms.py::manager_firm_id. NO ROUTE
    declares it yet, deliberately: the retire route consumes the RULE
    instead (its refusals must be 404s, not the dependency's 403), and the
    admin user routes need the composite. The name stays in the known set
    below regardless -- these four are the VOCABULARY of legal gates, and
    dropping one would make a route carrying it look ungated here.
  - require_google_oidc(audience, allowed_caller_emails) -- Cloud Scheduler /
    Pub/Sub push callers. Shipped here with its first consuming route, POST
    /admin/links/sweep-expired (bd polyglot-pdf-8vgfh); Epic 4 4.3's Pub/Sub
    push route will be its second.

/health and /version are the deliberate exception (pinned separately in
test_admin_health.py): the unauthenticated liveness/identity probe.
"""
from admin_backend.main import app
from admin_backend.services.admin_auth import require_app_admin

# require_app_admin shipped with /admin/whoami (bd polyglot-pdf-7w17m);
# require_app_admin_or_owning_manager ships with the user routes and
# require_firm_manager with the retire route it moved into
# backend/services/auth.py (bd polyglot-pdf-dmjl5); require_google_oidc
# ships with the sweep route below (bd polyglot-pdf-8vgfh) -- see that
# route's own module for why its FACTORY-returned dependency is named
# "require_google_oidc" rather than an inner closure's own name, which is
# what makes matching on this bare name work identically to the other three.
#
# All four are kept as STRINGS here (not imports) uniformly, even though
# every one is now importable: this file's job is checking WHICH NAME a
# route's dependency graph carries, and importing all four just to compare
# __name__ strings would add nothing test_whoami_is_gated_by_require_app_
# admin_specifically (below) does not already prove for the identity case.
#
# require_firm_manager appears in the known set even though no route on THIS
# service declares it (its consumer is the public backend's retire route):
# the four names are the vocabulary of legal gates, and dropping one from the
# set would silently make a route carrying it look ungated here.
_OTHER_GATE_NAMES = (
    "require_firm_manager",
    "require_app_admin_or_owning_manager",
    "require_google_oidc",
)

_UNGATED_PATHS = {"/health", "/version"}


def _dependency_names_for(route) -> set:
    """The names of every dependency callable FastAPI wired to this route.

    Reads route.dependant.dependencies (FastAPI's flattened dependency
    graph), which is where a `Depends(...)` parameter default lands -- the
    common spelling in this repo -- rather than route.dependencies (only
    populated for router-level `dependencies=[...]`). Mirrors
    test_http_route_auth.py's _routes_depending_on, generalized to collect
    every dependency's name instead of checking membership of one.
    """
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return set()
    return {sub.call.__name__ for sub in dependant.dependencies
            if getattr(sub.call, "__name__", None)}


def _business_routes():
    return [
        route for route in app.routes
        if getattr(route, "path", None)
        and route.path not in _UNGATED_PATHS
        and route.path not in {
            "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
    ]


def test_every_business_route_carries_exactly_one_of_the_four_gates():
    """THE SET PIN. Mutation: register a route with no Depends(require_*) --
    red; register one with two of the four -- red (ambiguous authorization is
    itself a bug, per CLAUDE.md scar #8: the rule must have ONE home)."""
    known_gate_names = {"require_app_admin", *_OTHER_GATE_NAMES}

    offenders = []
    for route in _business_routes():
        names = _dependency_names_for(route) & known_gate_names
        if len(names) != 1:
            methods = sorted(getattr(route, "methods", None) or [])
            offenders.append(
                f"{methods} {route.path}: found gates {sorted(names)}"
            )

    assert not offenders, (
        "every business route on the admin service must carry EXACTLY ONE "
        "of the four gates (require_app_admin, require_firm_manager, "
        "require_app_admin_or_owning_manager, require_google_oidc) -- "
        "Cloud Run runs this service with --allow-unauthenticated, so a "
        "missing or doubled gate is directly reachable:\n  "
        + "\n  ".join(offenders)
    )


def test_the_registered_route_set_is_pinned():
    """The complete route set, derived from the live app -- a new route
    changes this set deliberately, never silently. Mutation: add a route and
    forget to update this set -- red."""
    actual = {
        (tuple(sorted(getattr(r, "methods", None) or [])), r.path)
        for r in _business_routes()
    }
    assert actual == {
        (("GET",), "/admin/whoami"),
        (("GET",), "/admin/config/{channel}"),
        (("PUT",), "/admin/config/{channel}"),
        (("GET",), "/admin/audit"),
        (("POST",), "/admin/users"),
        (("GET",), "/admin/users"),
        (("PATCH",), "/admin/users/{uid}/disable"),
        (("PATCH",), "/admin/users/{uid}/role"),
        (("POST",), "/admin/firms"),
        (("GET",), "/admin/firms"),
        (("GET",), "/admin/firms/{firm_id}"),
        (("PATCH",), "/admin/firms/{firm_id}/status"),
        (("PATCH",), "/admin/firms/{firm_id}/allowed_kits"),
        (("PATCH",), "/admin/firms/{firm_id}/kind"),
        (("POST",), "/admin/firms/{firm_id}/credits/grant"),
        (("POST",), "/admin/firms/{firm_id}/credits/adjust"),
        (("POST",), "/admin/links/sweep-expired"),
        (("GET",), "/admin/firms/{firm_id}/links"),
        (("POST",), "/admin/links/{jti}/revoke"),
        (("GET",), "/admin/kits"),
        (("GET",), "/admin/kits/{kit_id}/commercial"),
        (("PUT",), "/admin/kits/{kit_id}/commercial"),
    }, (
        f"registered admin business routes changed: {sorted(actual)} -- "
        "update this set deliberately, and confirm the new route carries "
        "one of the four gates (see test_every_business_route_carries_"
        "exactly_one_of_the_four_gates)"
    )


def test_whoami_is_gated_by_require_app_admin_specifically():
    """The set pin above only proves ONE of the four names is present; this
    pins WHICH one for the route the gate first shipped with. Mutation: swap
    require_app_admin for a different (even if valid-shaped) dependency on
    the whoami route -- red.

    The config and audit routes (bd polyglot-pdf-li9x0) carry the same gate;
    it is pinned per-route in test_config_routes.py rather than duplicated
    here."""
    route = next(r for r in app.routes if r.path == "/admin/whoami")
    assert _dependency_names_for(route) == {"require_app_admin"}
    dependant = route.dependant
    assert any(sub.call is require_app_admin for sub in dependant.dependencies)


def test_sweep_route_is_gated_by_require_google_oidc_specifically():
    """Pins WHICH gate the sweep route carries (bd polyglot-pdf-8vgfh).

    require_google_oidc is a FACTORY -- the callable FastAPI actually wired
    is the inner closure it returns, not the module-level require_google_
    oidc function object itself, so this cannot assert `sub.call is
    require_google_oidc` the way test_whoami_... does above for a plain
    dependency. What CAN be pinned, and is: the closure's __name__ is
    exactly "require_google_oidc" (the rename that makes the bare-name set
    pin above see it as this gate at all). Mutation: remove the
    `_dependency.__name__ = "require_google_oidc"` line in admin_auth.py --
    this test goes red (the name reverts to the closure's own
    "_dependency"), and so does the set pin above."""
    route = next(
        r for r in app.routes if r.path == "/admin/links/sweep-expired")
    assert _dependency_names_for(route) == {"require_google_oidc"}


def test_a_route_added_without_a_gate_is_caught():
    """PROVES the set pin actually fails on a real omission (exit criterion
    2), rather than trusting the assertion shape by inspection. Registers a
    throwaway route with NO gate directly on the live app object, runs the
    same derivation the two tests above use, and confirms it flags it --
    then removes the route so this test cannot pollute any other test's view
    of app.routes."""
    from fastapi import APIRouter

    throwaway = APIRouter()

    @throwaway.get("/admin/_test_ungated_route_7w17m")
    async def _ungated():  # pragma: no cover -- never actually invoked
        return {"ok": True}

    before = list(app.routes)
    app.include_router(throwaway)
    try:
        known_gate_names = {"require_app_admin", *_OTHER_GATE_NAMES}
        offenders = [
            route.path for route in _business_routes()
            if len(_dependency_names_for(route) & known_gate_names) != 1
        ]
        assert "/admin/_test_ungated_route_7w17m" in offenders, (
            "adding a route with no gate did NOT get flagged -- the set "
            "pin above would not catch a real omission"
        )
    finally:
        app.router.routes = before
