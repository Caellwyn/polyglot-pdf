"""The admin app's 422 never echoes the request body (bd polyglot-pdf-wfgjz,
sprint 23 B1a / PF-3). The backend app's twin lives in
backend/tests/test_no_pii_logging.py; this one posts the sentinel through
the credit-adjust body model as an app admin.
"""
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.services.admin_auth import require_app_admin
from admin_backend.tests.unit.test_access_matrix import ADMIN_ACTOR
from backend.utils.validation_errors import validation_error_handler

SENTINEL = "A-098-765-432-PII-SENTINEL"


def test_the_admin_app_installs_the_value_free_422():
    assert app.exception_handlers.get(RequestValidationError) is validation_error_handler


def test_the_admin_app_is_not_in_debug_mode():
    assert app.debug is False


def test_a_malformed_admin_body_never_comes_back_in_the_422():
    """RED without install_validation_error_handler(app) in admin_backend/main.py
    (FastAPI's default carries `input`), green with it."""
    app.dependency_overrides[require_app_admin] = lambda: ADMIN_ACTOR
    try:
        client = TestClient(app)
        resp = client.post("/admin/firms/firm-a/credits/adjust",
                           json={"amount": SENTINEL, "reason": "sentinel test"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422, resp.text
    assert SENTINEL not in resp.text, "the admin 422 echoed the request value: " + resp.text
    detail = resp.json()["detail"]
    assert detail and all(set(e) <= {"loc", "type", "msg"} for e in detail), detail
