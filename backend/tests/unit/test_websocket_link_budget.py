"""The socket's spend-ceiling PRECEDENCE (bd polyglot-pdf-ah5d3 / A4, closing
polyglot-pdf-4tjt7).

Precedence at `/ws/fill`'s client-link gate is TOKEN `cap_usd` > the global
default, and NOTHING ELSE -- no per-connect kit metadata read. This is the
socket-level half of the change; `test_link_budget.py` pins the resolver
(`cost_ceiling_usd_for_claims`) in isolation and `test_link_tokens.py` pins
the token payload carrying the claim. This file pins that the socket ACTUALLY
calls `check_budget` with the resolved value for a real, signed, verified
token -- the mutation-verified property the bead's exit criterion 1 names.

ASCII only.
"""

from __future__ import annotations

import json
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket

from backend.routes.websocket_routes import fill_form_from_schema
from backend.services.link_tokens import mint_link_token


@pytest.fixture
def mock_websocket():
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_service():
    return MagicMock(name="form_filling_service")


@pytest.fixture
def handshake_message():
    return {
        "type": "handshake",
        "schema": {
            "source": "web",
            "form_metadata": {"title": "Contact Form", "url": "https://example.com"},
            "fields": [
                {"id": "email", "name": "Email", "type": "email", "required": True},
            ],
        },
        "current_values": {},
    }


def _stub_open_link(monkeypatch):
    """Every gate before check_budget must clear for this test to reach it."""
    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": int(time.time()), "completed_at": None,
        },
    )


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_token_WITH_cap_usd_overrides_the_global_at_the_socket(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch,
):
    """THE PRECEDENCE ITSELF (bead exit criterion 1). A token minted with a
    $3 cap must reach check_budget as a $3 ceiling, not the $10 global --
    proven by capturing what check_budget was actually called with, not by
    asserting a side effect that could pass for other reasons.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    monkeypatch.setattr(
        "backend.services.link_budget._rc_link_cost_ceiling_usd", lambda: 10.0
    )
    _stub_open_link(monkeypatch)

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7", cap_usd=3.0)

    captured = {}

    def _spy_check_budget(jti, kit_metadata=None, firm_id=None):
        captured["jti"] = jti
        captured["kit_metadata"] = kit_metadata
        captured["firm_id"] = firm_id
        return 3.0

    monkeypatch.setattr(
        "backend.routes.websocket_routes.check_budget", _spy_check_budget
    )
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    assert captured, "check_budget was never called"
    # The resolved ceiling reaching check_budget must be the TOKEN's $3, not
    # the $10 global -- via whatever key check_budget itself resolves from.
    from backend.services.link_budget import KIT_COST_CEILING_KEY

    assert captured["kit_metadata"] == {KIT_COST_CEILING_KEY: 3.0}
    # bd polyglot-pdf-bo95a: the claim's firm_id must reach check_budget so
    # a refusal's telemetry alert doc can be labelled with the right firm.
    assert captured["firm_id"] == "firm-a"
    mock_fill_session.assert_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_token_WITHOUT_cap_usd_uses_the_global_at_the_socket(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch,
):
    """The other half of the precedence: an uncapped token (minted before A3
    wires cap_usd through, or for a kit with no resolvable ceiling) must
    still get the global default, not zero and not unlimited.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    monkeypatch.setattr(
        "backend.services.link_budget._rc_link_cost_ceiling_usd", lambda: 10.0
    )
    _stub_open_link(monkeypatch)

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")  # no cap_usd

    captured = {}

    def _spy_check_budget(jti, kit_metadata=None, firm_id=None):
        captured["kit_metadata"] = kit_metadata
        captured["firm_id"] = firm_id
        return 10.0

    monkeypatch.setattr(
        "backend.routes.websocket_routes.check_budget", _spy_check_budget
    )
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    from backend.services.link_budget import KIT_COST_CEILING_KEY

    assert captured["kit_metadata"] == {KIT_COST_CEILING_KEY: 10.0}
    assert captured["firm_id"] == "firm-a"
    mock_fill_session.assert_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_the_resolved_ceiling_ACTUALLY_STOPS_A_CAPPED_LINK(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch,
):
    """End-to-end through the REAL check_budget/spend_so_far path (not a
    stub): a link with a $3 token cap that has already spent $3 must be
    refused, even though the $10 global would have allowed it. This is what
    makes the precedence load-bearing rather than cosmetic -- a wiring bug
    that always used the global would pass every isolated resolver test and
    only fail here.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    monkeypatch.setattr(
        "backend.services.link_budget._rc_link_cost_ceiling_usd", lambda: 10.0
    )
    _stub_open_link(monkeypatch)

    token, jti = mint_link_token("firm-a", "i-90", "u-emp-7", cap_usd=3.0)

    # Real spend store, faked at the Firestore-document layer: the link has
    # already spent exactly its $3 token cap (which is UNDER the $10 global,
    # so this only refuses if the token's cap is actually the one enforced).
    class _FakeSnap:
        exists = True

        def to_dict(self):
            return {"spend_usd": 3.0}

    class _FakeDoc:
        def get(self):
            return _FakeSnap()

    class _FakeCollection:
        def document(self, _jti):
            return _FakeDoc()

    monkeypatch.setattr(
        "backend.services.link_spend._enabled", lambda: True
    )
    monkeypatch.setattr(
        "backend.services.link_spend._collection", lambda: _FakeCollection()
    )
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_fill_session.assert_not_awaited()
    mock_websocket.close.assert_awaited()
    kwargs = mock_websocket.close.await_args.kwargs
    assert kwargs.get("code") == 1013
    assert kwargs.get("reason") == "budget_exhausted"


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_ceiling_resolution_runs_OFF_the_event_loop_thread(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch,
):
    """Opus cross-surface finding 1 (bd polyglot-pdf-ah5d3): resolving the
    ceiling is a synchronous call that can hit a blocking Admin-SDK Firestore
    read on a cold runtime_config cache. It must run inside the SAME
    `asyncio.to_thread` call as `check_budget`, never directly on the
    coroutine's own (event-loop) thread -- a synchronous read on the loop
    thread would stall every OTHER concurrent request on this Cloud Run
    instance, in-flight audio included.

    This test captures the thread `cost_ceiling_usd_for_claims` actually runs
    on and asserts it is NOT the thread running this test coroutine. A
    regression that hoists the resolution back onto the event loop (calling
    it directly in `fill_form_from_schema` instead of inside the threaded
    closure) makes this fail, because the coroutine's own thread IS the
    thread pytest-asyncio drives this test from.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    monkeypatch.setattr(
        "backend.services.link_budget._rc_link_cost_ceiling_usd", lambda: 10.0
    )
    _stub_open_link(monkeypatch)

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7", cap_usd=3.0)

    caller_thread_id = threading.get_ident()
    captured = {}

    def _spy_cost_ceiling_usd_for_claims(claims):
        captured["thread_id"] = threading.get_ident()
        return 3.0

    monkeypatch.setattr(
        "backend.routes.websocket_routes.cost_ceiling_usd_for_claims",
        _spy_cost_ceiling_usd_for_claims,
    )
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    assert captured, "cost_ceiling_usd_for_claims was never called"
    assert captured["thread_id"] != caller_thread_id, (
        "cost_ceiling_usd_for_claims ran on the event-loop thread -- a "
        "cold-cache resolution here blocks every concurrent request on "
        "this Cloud Run instance"
    )
    mock_fill_session.assert_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_the_SAME_spend_would_be_ALLOWED_under_the_global_ceiling(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch,
):
    """Control for the test above: without a token cap, $3 of spend against
    the $10 global has headroom and the session proceeds. Proves the refusal
    above is really about the $3 CAP, not some unrelated gate firing.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    monkeypatch.setattr(
        "backend.services.link_budget._rc_link_cost_ceiling_usd", lambda: 10.0
    )
    _stub_open_link(monkeypatch)

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")  # no cap_usd

    class _FakeSnap:
        exists = True

        def to_dict(self):
            return {"spend_usd": 3.0}

    class _FakeDoc:
        def get(self):
            return _FakeSnap()

    class _FakeCollection:
        def document(self, _jti):
            return _FakeDoc()

    monkeypatch.setattr(
        "backend.services.link_spend._enabled", lambda: True
    )
    monkeypatch.setattr(
        "backend.services.link_spend._collection", lambda: _FakeCollection()
    )
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_fill_session.assert_awaited()
    mock_websocket.close.assert_not_awaited()
