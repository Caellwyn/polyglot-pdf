"""Shared pytest fixtures for the backend test suite."""

import os

import pytest

# bd polyglot-pdf-5xhbb: strip K_SERVICE from the process environment as soon
# as conftest.py is imported -- BEFORE pytest collects any test module. A
# per-test autouse fixture (see _isolate_k_service below) runs too late for
# this: several test files import backend.main at module scope (e.g.
# test_http_route_auth.py:20 -> backend/main.py -> backend/routes/
# websocket_routes.py:18's `settings = get_settings()`), so an ambient
# K_SERVICE + VFF_DISABLE_AUTH=true aborts COLLECTION with a pydantic
# ValidationError before any fixture ever runs (reproduced: `K_SERVICE=...
# VFF_DISABLE_AUTH=true pytest backend/tests/unit/test_http_route_auth.py`
# -> "Interrupted: 1 error during collection" even with the fixture present).
# This module-level delenv runs at IMPORT time, ahead of every collection
# import in this session, which is the only point early enough to prevent
# that. The per-test fixture below stays as defense-in-depth for the (rarer)
# case where something re-sets K_SERVICE mid-session outside a test's own
# monkeypatch.
os.environ.pop("K_SERVICE", None)


@pytest.fixture(autouse=True)
def _isolate_confirmation_logs(tmp_path, monkeypatch):
    """Redirect confirmation-audit logs to a per-test tmp dir.

    The confirmation logger writes one JSONL file per form session
    (see backend/utils/confirmation_logger.py). Without this, any test that
    exercises field confirmation (e.g. test_section_switching) would append to
    the repo's real `logs/confirmations/` tree and dirty the working tree on
    every run. Pointing CONFIRMATION_LOG_DIR at tmp_path keeps tests hermetic
    and keeps real confirmation logs out of git.
    """
    monkeypatch.setenv("CONFIRMATION_LOG_DIR", str(tmp_path / "confirmations"))


@pytest.fixture(autouse=True)
def _isolate_k_service(monkeypatch):
    """Strip K_SERVICE so a bare Settings() in a test never inherits a
    deployed-service identity from the ambient shell (bd polyglot-pdf-5xhbb).

    backend/config.py's _resolve_model keys two fail-closed guards off
    os.getenv('K_SERVICE') -- the VERTEXAI guard (bd polyglot-pdf-5e6a) and
    the VFF_DISABLE_AUTH guard (bd polyglot-pdf-knmp). Cloud Run sets this
    var; a local shell normally does not, but nothing pinned that, so a
    containerized/CI-in-Cloud-Run run (or any operator who happens to export
    it) would silently flip guard tests that assume it is absent. Tests that
    deliberately exercise the deployed path still work: they call
    monkeypatch.setenv('K_SERVICE', ...) themselves, which layers over (and
    wins against) this fixture's delenv.

    This is defense-in-depth for TEST-TIME Settings() construction; the
    COLLECTION-time exposure (module-scope get_settings() calls, e.g.
    websocket_routes.py:18) is closed by the module-level os.environ.pop
    above, which runs before this fixture -- or any fixture -- ever could.
    """
    monkeypatch.delenv("K_SERVICE", raising=False)
