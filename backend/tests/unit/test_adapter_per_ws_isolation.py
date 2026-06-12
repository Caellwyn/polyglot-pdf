"""Spec: one LiveAI adapter per WebSocket connection (bd polyglot-pdf-uov.10, T2.3).

Regression guard for polyglot-pdf-1g6: FastAPI dependency caching once let two
WebSocket connections SHARE a single LiveAIGemini instance, so the second
connection's set_callbacks() overwrote the first's on_tool_call -- and tool calls
were routed to the wrong tab. The fix (backend/dependencies.py get_live_ai)
constructs a FRESH adapter per call, and each adapter keeps its callbacks in
per-instance state.

This suite pins that isolation as a CONNECTION-LEVEL property: two adapters are
distinct objects, carry distinct instance_ids, and a callback registered on one
is never visible on the other. It deliberately asserts ONLY on per-connection
adapter instancing -- it does not touch the Gemini session lifecycle or the
section-end reset path, so it stays valid regardless of how (or whether) the
session is restarted at a section boundary.

set_callbacks() has a side effect (it also starts the background session loop via
asyncio.create_task), so the tests run under an event loop and patch
_run_session_loop to a no-op coroutine: we are specifying callback ISOLATION, not
the session machinery, and we do not want a real session spun up.
"""

from unittest.mock import AsyncMock, patch

import pytest

from backend.config import Settings
from backend.dependencies import get_live_ai
from backend.adapters.live_ai_gemini import LiveAIGemini


def _make_settings() -> Settings:
    # A bare Settings() is enough: get_live_ai only reads MODEL_NATIVE,
    # VERTEXAI, and GEMINI_API_KEY off it, and the adapter constructs without
    # authenticating when api_key is absent (the mocked-unit-test default).
    return Settings()


async def _noop_session_loop(self):
    # Stand-in for LiveAIGemini._run_session_loop so set_callbacks() can start
    # its background task without opening a real Gemini session.
    return None


def test_get_live_ai_returns_a_fresh_instance_each_call():
    """get_live_ai must NOT cache: each call yields a distinct adapter object."""
    settings = _make_settings()

    a = get_live_ai(settings=settings)
    b = get_live_ai(settings=settings)

    assert isinstance(a, LiveAIGemini)
    assert isinstance(b, LiveAIGemini)
    # The 1g6 bug WAS a shared instance; the contract is that these are distinct.
    assert a is not b


def test_each_adapter_has_a_distinct_instance_id():
    """Per-instance instance_id is the tag that disambiguates connections in logs."""
    settings = _make_settings()

    a = get_live_ai(settings=settings)
    b = get_live_ai(settings=settings)

    assert a._instance_id != b._instance_id


@pytest.mark.asyncio
async def test_tool_call_callback_does_not_cross_route_between_connections():
    """A tool-call callback set on connection A is never seen by connection B.

    This is the heart of the 1g6 regression: with a shared instance, B's
    set_callbacks() clobbered A's on_tool_call. With per-connection adapters,
    each holds its own on_tool_call and the two never alias.
    """
    settings = _make_settings()

    cb_a = AsyncMock(name="on_tool_call_A")
    cb_b = AsyncMock(name="on_tool_call_B")

    with patch.object(LiveAIGemini, "_run_session_loop", _noop_session_loop):
        conn_a = get_live_ai(settings=settings)
        conn_b = get_live_ai(settings=settings)

        conn_a.set_callbacks(on_tool_call=cb_a)
        conn_b.set_callbacks(on_tool_call=cb_b)

    # Each connection keeps ITS OWN callback -- no overwrite, no aliasing.
    assert conn_a._on_tool_call is cb_a
    assert conn_b._on_tool_call is cb_b
    assert conn_a._on_tool_call is not conn_b._on_tool_call


@pytest.mark.asyncio
async def test_registering_on_b_does_not_mutate_a_after_the_fact():
    """Order-independence: setting B's callbacks LAST must not reach back into A.

    The original bug surfaced specifically because the SECOND connection's
    registration overwrote the first's. Pin that the later registration leaves
    the earlier connection's callback untouched.
    """
    settings = _make_settings()

    cb_a = AsyncMock(name="on_tool_call_A")
    cb_b = AsyncMock(name="on_tool_call_B")

    with patch.object(LiveAIGemini, "_run_session_loop", _noop_session_loop):
        conn_a = get_live_ai(settings=settings)
        conn_b = get_live_ai(settings=settings)

        conn_a.set_callbacks(on_tool_call=cb_a)
        # B registers AFTER A -- the exact sequence that used to clobber A.
        conn_b.set_callbacks(on_tool_call=cb_b)

    assert conn_a._on_tool_call is cb_a  # still A's, not overwritten by B
