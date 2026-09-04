"""The admin service actually serves (bd polyglot-pdf-pnoik).

Exit criterion 1: `uvicorn admin_backend.main:app` serves GET /health. The
app is otherwise routeless at this stage, so /health is the whole reachable
surface.

These tests are the ONLY coverage /health has. deploy-all.sh's post-deploy
verify_service_publicly_reachable() reads the Cloud Run IAM policy for an
allUsers invoker binding and issues no HTTP request, so a broken /health would
NOT abort a deploy -- do not delete a case here on the theory that the deploy
would catch it.
"""
from fastapi.testclient import TestClient

from admin_backend.main import app, DEFAULT_APP_MODULE


def test_health_answers_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # Names WHICH service answered. Both services are built from one image and
    # both serve /health; without this an operator hitting the wrong URL reads
    # a healthy response from the wrong app.
    assert body["service"] == "polyglot-admin"


def test_health_reports_the_app_module_actually_running(monkeypatch):
    """APP_MODULE is a runtime env var, so a service pointed at the wrong
    module looks perfectly healthy. /health reports which one is live.

    Parametrized by hand over the two states that matter -- set and unset --
    because the default branch is the one every existing deploy takes.
    """
    monkeypatch.setenv("APP_MODULE", "admin_backend.main:app")
    with TestClient(app) as client:
        assert client.get("/health").json()["app_module"] == (
            "admin_backend.main:app")

    monkeypatch.delenv("APP_MODULE", raising=False)
    with TestClient(app) as client:
        assert client.get("/health").json()["app_module"] == DEFAULT_APP_MODULE
        assert DEFAULT_APP_MODULE == "backend.main:app"


def test_health_resolves_an_empty_app_module_the_way_the_container_does(
        monkeypatch):
    """APP_MODULE="" must report the DEFAULT, not an empty string.

    The Dockerfile CMD uses `${APP_MODULE:-backend.main:app}` -- the `:-` form,
    which falls back on unset AND on empty. An operator whose --set-env-vars
    block passes APP_MODULE= therefore gets the public backend, and /health
    must say so. A plain os.getenv(name, default) disagrees here: its default
    fires only when the variable is absent, so it would return '' and the
    field would be blank in exactly the case it exists to diagnose.

    The unset/set cases above pass under BOTH readings, so this is the case
    that actually pins the agreement.
    """
    monkeypatch.setenv("APP_MODULE", "")
    with TestClient(app) as client:
        assert client.get("/health").json()["app_module"] == DEFAULT_APP_MODULE


def test_version_answers():
    with TestClient(app) as client:
        response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": app.version}


def test_the_admin_app_is_a_distinct_asgi_app_from_the_public_backend():
    """Two services, two app objects, one image.

    Importing admin_backend.main must not hand back the public backend's app
    (an `from backend.main import app` re-export would satisfy every assertion
    above while serving the wrong routes on the wide service account).
    """
    from backend.main import app as public_app

    assert app is not public_app
    assert app.title == "Polyglot Admin API"
    assert public_app.title != app.title


def test_the_admin_app_registers_no_unauthenticated_business_route():
    """At the skeleton stage the ONLY app routes are /health and /version.

    Routers land in bd polyglot-pdf-7w17m together with require_app_admin, and
    admin_backend/tests/unit/test_admin_route_auth.py takes over from there.
    Until then this pins that nothing privileged slipped onto a public service
    ahead of its gate.
    """
    paths = {
        route.path for route in app.routes
        if getattr(route, "path", None)
        and route.path not in {
            "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
    }
    assert paths == {"/health", "/version"}, sorted(paths)
