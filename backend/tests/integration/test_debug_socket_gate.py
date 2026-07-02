"""Prod gate for the /ws/echo and /ws/audio debug sockets (bd polyglot-pdf-puu8).

The two low-level debug sockets are dev-only: they ride the same
backend/.env.DEV marker gate as the dev console-log route
(DEV_LOGGING_ENABLED). In production the handshake is rejected before
accept; the product socket /ws/fill is NOT gated.

DEV_LOGGING_ENABLED is a module-level constant computed at import time,
so both directions are pinned via monkeypatch -- the test must not depend
on whether the developer's machine has .env.DEV.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import websocket_routes


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("path", ["/ws/echo", "/ws/audio"])
def test_debug_sockets_reject_handshake_in_prod(client, monkeypatch, path):
    monkeypatch.setattr(websocket_routes, "DEV_LOGGING_ENABLED", False)
    with pytest.raises(Exception) as excinfo:
        with client.websocket_connect(path):
            pass
    # Starlette surfaces a pre-accept close as a denial/disconnect, never
    # an accepted session.
    assert excinfo.type.__name__ in (
        "WebSocketDisconnect",
        "WebSocketDenialResponse",
    ), f"unexpected rejection type: {excinfo.type}"


@pytest.mark.parametrize("path", ["/ws/echo", "/ws/audio"])
def test_debug_sockets_accept_in_dev(client, monkeypatch, path):
    monkeypatch.setattr(websocket_routes, "DEV_LOGGING_ENABLED", True)
    # Accepted handshake IS the assertion; close immediately after.
    with client.websocket_connect(path):
        pass
