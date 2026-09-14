"""Every registered admin-service route carries exactly one of FIVE gates
(bd polyglot-pdf-7w17m; the fifth added by bd polyglot-pdf-scaig).

Cloud Run runs this service with --allow-unauthenticated, so the app-level
gate on every route IS the whole access control -- there is no infrastructure
fallback. Mirrors backend/tests/unit/test_http_route_auth.py's
_routes_depending_on-derived set pins: the set is read off the LIVE app
object, never hand-maintained, so a route added without a gate fails HERE
instead of shipping reachable by anyone with the URL.

The FOUR gates the plan itself names ("Admin service" gating section). ALL
FOUR exist (bd polyglot-pdf-8vgfh landed the last one):
  - require_app_admin -- shipped with GET /admin/whoami (bd
    polyglot-pdf-7w17m).
  - require_app_admin_or_owning_manager -- the composite, shipped with the
    four /admin/users routes; also the gate Epic 2 B4's revoke route (POST
    /admin/links/{jti}/revoke) carries (bd polyglot-pdf-jmiys), and carried
    the link-listing route too UNTIL bd polyglot-pdf-scaig (see the fifth
    gate below).
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

A FIFTH gate, ADDED SEPARATELY from the plan's own four (bd
polyglot-pdf-scaig): require_app_admin_or_owning_manager_or_employee,
originally the ONLY gate on GET /admin/firms/{firm_id}/links, WIDENED (bd
polyglot-pdf-62o4d) to two more routes -- GET /admin/firms/{firm_id}/alerts
and PATCH /admin/alerts/{alert_id}/acknowledge -- so a firm manager or
employee can read their own firm's alerts, and a manager can acknowledge
one. An employee-role staff account has no seat in the plan's four-name
vocabulary at all (an employee is neither an app admin nor a firm
manager), so letting an employee reach their own link history (and now
their own alerts) needed a gate the plan's four never described, rather
than silently widening require_app_admin_or_owning_manager (which would
also widen the four /admin/users routes to accept an employee --
test_composite_gate.py pins that as a 403 through that name on purpose).
Acknowledge additionally refuses an employee INSIDE THE ROUTE BODY (see
alert_routes.py's own docstring for why that refusal is not a sixth,
narrower dependency) -- a distinction this file's dependency-only pins
cannot see, so it is pinned instead in test_alert_routes.py. Kept OUT of
_OTHER_GATE_NAMES below and pinned instead on its named routes directly
(test_admin_link_routes.py; test_firm_scoped_alert_routes_carry_the_
fifth_gate_specifically below), exactly as require_google_oidc's specific
route is pinned beyond the generic four-gate set check.

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
# require_app_admin_or_owning_manager_or_employee (bd polyglot-pdf-scaig) is
# DELIBERATELY NOT one of these four -- see the module docstring's "fifth
# gate" section. It carries its own route-specific pin in
# test_admin_link_routes.py instead of joining this generic vocabulary.
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

# The fifth gate (bd polyglot-pdf-scaig), kept OUT of _OTHER_GATE_NAMES
# because that tuple is the plan's own four-name vocabulary (see the module
# docstring's "fifth gate" section) -- but a route carrying it must still
# count as gated exactly once below, so it joins the SET pin's known names
# without joining the plan's four-name list any docstring or error message
# enumerates.
_FIFTH_GATE_NAME = "require_app_admin_or_owning_manager_or_employee"

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
    itself a bug, per CLAUDE.md scar #8: the rule must have ONE home).

    The fifth gate (_FIFTH_GATE_NAME) counts as a legal single gate here too
    -- this test's job is "is there EXACTLY ONE recognized gate", not "is it
    one of the plan's original four" -- but it is EXCLUDED from every OTHER
    route's allowed set below (test_link_listing_route_gate_set below pins
    that it appears on GET /admin/firms/{firm_id}/links alone), so a route
    other than that one growing this gate by mistake still fails as an
    unrecognized-combination offender there rather than silently passing
    here."""
    known_gate_names = {"require_app_admin", *_OTHER_GATE_NAMES,
                        _FIFTH_GATE_NAME}

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
        "of the five gates (require_app_admin, require_firm_manager, "
        "require_app_admin_or_owning_manager, require_google_oidc, "
        "require_app_admin_or_owning_manager_or_employee) -- "
        "Cloud Run runs this service with --allow-unauthenticated, so a "
        "missing or doubled gate is directly reachable:\n  "
        + "\n  ".join(offenders)
    )


def test_only_the_named_routes_carry_the_fifth_gate():
    """The fifth gate (require_app_admin_or_owning_manager_or_employee, bd
    polyglot-pdf-scaig; widened to two more routes by bd polyglot-pdf-62o4d)
    is scoped to a SMALL, NAMED set of routes on purpose -- see that
    function's own docstring for why an employee must not reach any other
    composite route. Mutation: wire it onto a route outside this set (e.g.
    revoke, which deliberately keeps the narrower
    require_app_admin_or_owning_manager) -- red."""
    carriers = {
        route.path for route in _business_routes()
        if _FIFTH_GATE_NAME in _dependency_names_for(route)
    }
    assert carriers == {
        "/admin/firms/{firm_id}/links",
        "/admin/firms/{firm_id}/alerts",
        "/admin/alerts/{alert_id}/acknowledge",
    }


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
        (("PATCH",), "/admin/firms/{firm_id}/plan"),
        (("POST",), "/admin/firms/{firm_id}/credits/grant"),
        (("POST",), "/admin/firms/{firm_id}/credits/adjust"),
        (("POST",), "/admin/credits/monthly-topup"),
        (("POST",), "/admin/links/sweep-expired"),
        (("GET",), "/admin/firms/{firm_id}/links"),
        (("POST",), "/admin/links/{jti}/revoke"),
        (("GET",), "/admin/kits"),
        (("GET",), "/admin/kits/{kit_id}/commercial"),
        (("PUT",), "/admin/kits/{kit_id}/commercial"),
        (("GET",), "/admin/firms/{firm_id}/usage"),
        (("GET",), "/admin/kits/{kit_id}/usage"),
        (("GET",), "/admin/reports/cost"),
        (("GET",), "/admin/reports/income"),
        (("GET",), "/admin/alerts"),
        (("GET",), "/admin/firms/{firm_id}/alerts"),
        (("PATCH",), "/admin/alerts/{alert_id}/acknowledge"),
        (("GET",), "/admin/errors"),
        (("GET",), "/admin/health"),
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


def test_firm_usage_route_is_gated_by_the_composite_gate_specifically():
    """Pins WHICH gate GET /admin/firms/{firm_id}/usage carries (bd
    polyglot-pdf-mpebj, E3.11a): require_app_admin_or_owning_manager, NOT
    require_app_admin -- a firm manager may read their own firm's usage
    (usage_routes.py's own _require_owning_firm), mirroring link_routes.py's
    listing route rather than kit_routes.py's admin-only reasoning.
    Mutation: swap the dependency for require_app_admin on this one route --
    red."""
    route = next(
        r for r in app.routes if r.path == "/admin/firms/{firm_id}/usage")
    assert _dependency_names_for(route) == {
        "require_app_admin_or_owning_manager"}


def test_kit_usage_and_report_and_alert_and_ops_routes_are_gated_by_require_app_admin_specifically():
    """The rest of bd polyglot-pdf-mpebj's new routes all carry the plain
    require_app_admin gate (no firm-manager counterpart -- see each
    module's own docstring for why). Mutation: swap any one of these for a
    different gate -- red."""
    admin_only_paths = (
        "/admin/kits/{kit_id}/usage",
        "/admin/reports/cost",
        "/admin/reports/income",
        "/admin/alerts",
        "/admin/errors",
        "/admin/health",
    )
    for admin_path in admin_only_paths:
        route = next(r for r in app.routes if r.path == admin_path)
        assert _dependency_names_for(route) == {"require_app_admin"}, admin_path


def test_firm_scoped_alert_routes_carry_the_fifth_gate_specifically():
    """GET /admin/firms/{firm_id}/alerts and PATCH /admin/alerts/{alert_id}/
    acknowledge (bd polyglot-pdf-62o4d) carry
    require_app_admin_or_owning_manager_or_employee, NOT the plain
    require_app_admin the OPERATOR-WIDE GET /admin/alerts still carries
    (pinned separately above) -- a firm manager or employee must reach
    their own firm's alerts and (for a manager) acknowledge them; an
    employee's REFUSAL to acknowledge is enforced inside the route body,
    not the dependency (see alert_routes.py's own docstring), so it is NOT
    visible to this dependency-only pin. Mutation: swap either route's
    dependency for require_app_admin -- red."""
    for path in (
        "/admin/firms/{firm_id}/alerts",
        "/admin/alerts/{alert_id}/acknowledge",
    ):
        route = next(r for r in app.routes if r.path == path)
        assert _dependency_names_for(route) == {_FIFTH_GATE_NAME}, path


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


def test_monthly_topup_route_is_gated_by_require_google_oidc_specifically():
    """Pins WHICH gate the monthly plan top-up route carries (bd
    polyglot-pdf-0euzk) -- the SAME shape as
    test_sweep_route_is_gated_by_require_google_oidc_specifically above,
    since both are Cloud Scheduler callers behind require_google_oidc's
    factory-returned closure. Mutation: swap the dependency for
    require_app_admin on this one route -- red."""
    route = next(
        r for r in app.routes if r.path == "/admin/credits/monthly-topup")
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
