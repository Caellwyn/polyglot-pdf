"""Every registered admin-service route carries exactly one of FOUR gates
(bd polyglot-pdf-7w17m).

Cloud Run runs this service with --allow-unauthenticated, so the app-level
gate on every route IS the whole access control -- there is no infrastructure
fallback. Mirrors backend/tests/unit/test_http_route_auth.py's
_routes_depending_on-derived set pins: the set is read off the LIVE app
object, never hand-maintained, so a route added without a gate fails HERE
instead of shipping reachable by anyone with the URL.

The four gates, per the plan ("Admin service" gating section):
  - require_app_admin -- the only one that exists after this bead.
  - require_firm_manager -- ships with its first consuming route
    (backend/services/auth.py; Epic 2 B-track).
  - require_app_admin_or_owning_manager -- the composite for revoke/link
    listing (Epic 2 B5).
  - require_google_oidc(audience, allowed_caller_emails) -- Cloud Scheduler /
    Pub/Sub push callers (Epic 4 4.3).

/health and /version are the deliberate exception (pinned separately in
test_admin_health.py): the unauthenticated liveness/identity probe.
"""
from admin_backend.main import app
from admin_backend.services.admin_auth import require_app_admin

# THREE of the four gates now exist. require_app_admin shipped with
# /admin/whoami (bd polyglot-pdf-7w17m); require_app_admin_or_owning_manager
# ships with the user routes below and require_firm_manager with the retire
# route it moved into backend/services/auth.py (bd polyglot-pdf-dmjl5). Only
# require_google_oidc is still ahead (Epic 2 B5 / Epic 4 4.3), and it stays a
# STRING rather than an import: importing a name that does not exist would
# fail at COLLECTION, which is a worse failure mode than this test failing
# with a clear message the day it is expected to exist.
#
# require_firm_manager appears in the known set even though no route on THIS
# service declares it (its consumer is the public backend's retire route):
# the four names are the vocabulary of legal gates, and dropping one from the
# set would silently make a route carrying it look ungated here.
_FUTURE_GATE_NAMES = (
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
    known_gate_names = {"require_app_admin", *_FUTURE_GATE_NAMES}

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
        known_gate_names = {"require_app_admin", *_FUTURE_GATE_NAMES}
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
