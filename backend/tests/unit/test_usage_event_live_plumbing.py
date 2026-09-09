"""Live-voice usage-event plumbing (bd polyglot-pdf-cjifh, E3.2).

WHAT THIS PINS. websocket_routes._handle_fill_session already receives
kit_id, firm_id, link_jti, link_employee_id as parameters (the claims are
decoded in fill_form_from_schema, a different function). Before this bead it
passed only kit_id + firm_id into FormFillingService.start_session, so a
live-voice usage event (log_gemini_api_response, usage_kind="live_voice")
never carried firm_id, employee_id, link_jti, or channel -- the event
schema (bd polyglot-pdf-wio6m) had the columns, but the live path left them
null even when the session actually had the ids.

TWO LAYERS, because the ids cross two different seams:

  1. THE REAL HANDSHAKE PATH (fill_form_from_schema -> _handle_fill_session ->
     FormFillingService.start_session -> LiveAIGemini.set_session_context) --
     driven for BOTH a link session and a staff session, with genai.Client
     patched at the adapter's own import boundary (the same seam
     test_live_ai_gemini.py's mock_google_ai_client fixture uses) so this is
     the real chain minus the actual live-audio wire.
  2. THE PER-TURN EMIT -- once set_session_context has the ids, does the
     per-turn usage_metadata handler in _run_session_loop actually reach
     log_gemini_api_response with them. Driven directly against the adapter
     (the same _run_session_loop fake-event pattern test_live_ai_gemini.py
     uses), with get_structured_logger mocked at the adapter's own import
     boundary.

MUTATION-VERIFIED (bead exit criterion 1): dropping any one of the six
set_session_context call-site kwargs in form_filling_service.py, or any one
of the six log_gemini_api_response kwargs in live_ai_gemini.py, must fail
this file. Verified by hand for firm_id during authoring (reverted after).

ASCII only.
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket
from google.genai import types

from backend.adapters.live_ai_gemini import LiveAIGemini
from backend.routes.websocket_routes import fill_form_from_schema
from backend.services.form_filling_service import FormFillingService
from backend.services.link_tokens import mint_link_token


# ---------------------------------------------------------------------------
# Layer 1: the real handshake path sets the adapter's context ids
# ---------------------------------------------------------------------------

_HANDSHAKE = {
    "type": "handshake",
    "schema": {
        "source": "web",
        "form_metadata": {"title": "I-90", "form_number": "I-90"},
        "fields": [
            {"id": "name", "name": "Full Name", "type": "text"},
        ],
    },
    "current_values": {},
}


def _make_mock_websocket():
    """A WebSocket double for the TWO DISTINCT receive calls on this path.

    fill_form_from_schema's OWN handshake read is `await
    websocket.receive_text()` (line ~1410) -- called ONCE, before
    _handle_fill_session is ever entered. _handle_fill_session's post-
    handshake control loop is a SEPARATE call, `while True: msg = await
    websocket.receive()` (Starlette's raw-message form, `{"type": ...}` /
    `{"bytes": ...}` / `{"text": ...}`), NOT receive_text() -- conflating the
    two (an earlier version of this fixture only mocked receive_text) leaves
    receive() an unconfigured auto-mock that never produces a real
    "websocket.disconnect" message, so the loop spins forever on a message
    shape nothing in the route recognizes. TestClient.websocket_connect's
    `with` block gets a real disconnect for free on context exit; a bare
    MagicMock does not, so both calls are simulated explicitly here.
    """
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock(return_value=json.dumps(_HANDSHAKE))
    ws.receive = AsyncMock(return_value={"type": "websocket.disconnect"})
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_websocket():
    return _make_mock_websocket()


class _EmptyAsyncIterator:
    """Immediately-stopping async iterator (same shape as
    test_live_ai_gemini.py's helper of the same name)."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def _real_service() -> FormFillingService:
    """A real FormFillingService wrapping a real LiveAIGemini, with
    genai.Client PATCHED at the SDK boundary (bead exit criterion 1: "the
    adapter mocked at the SDK boundary") -- the SAME `genai.Client` symbol
    test_live_ai_gemini.py's mock_google_ai_client fixture patches, and the
    SAME shape: `connect` is an AsyncMock whose return_value is the SESSION
    directly (not a context-manager wrapper). _run_session_loop's connect
    call reads `hasattr(connect_obj, "__aenter__")` on the CALL'S RETURN
    VALUE (a coroutine object, which has no __aenter__) and so takes the
    "awaitable returning a session" branch: `session = await connect_obj`.
    Wrapping the session in an async-context-manager object here (the first
    version of this fixture did that) makes `session` resolve to the
    WRAPPER instead of something with `.receive()`, which raises
    AttributeError every attempt and retries FOREVER at MAX_RECONNECT_ATTEMPTS
    -- discovered by hand as an indefinite hang before this fixture matched
    test_live_ai_gemini.py's proven shape exactly.

    Without the genai.Client patch at all, LiveAIGemini.__init__'s
    vertexai=False + no-api-key branch falls through to a BARE `genai.Client()`
    -- also hangs, for the DNS/ADC-discovery reason its own warning names.

    The receive() iterator yields nothing and stops immediately, so
    _run_session_loop's background task exits cleanly on its own without ever
    needing usage_metadata (Layer 2 below covers that turn-level path
    directly against the adapter, with the SimpleNamespace shape
    test_live_ai_gemini.py's tool-call tests use instead).
    """
    with patch("backend.adapters.live_ai_gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_session = AsyncMock()
        mock_session.receive = MagicMock(return_value=_EmptyAsyncIterator())
        mock_client.aio.live.connect = AsyncMock(return_value=mock_session)
        mock_genai.Client = MagicMock(return_value=mock_client)
        adapter = LiveAIGemini()
    return FormFillingService(live_ai=adapter)


def _stub_open_link(monkeypatch):
    """Every gate before _handle_fill_session must clear to reach it
    (mirrors test_websocket_link_budget.py's helper of the same name)."""
    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": int(time.time()), "completed_at": None,
        },
    )
    monkeypatch.setattr(
        "backend.routes.websocket_routes.check_budget", lambda *a, **k: 10.0
    )


@pytest.mark.asyncio
async def test_link_session_context_carries_all_five_ids_plus_channel(monkeypatch):
    """A client-link session's adapter ends up with firm/employee/link/kit/
    channel all set from the real, signed, verified token -- not from a
    handshake value the client could type (bd polyglot-pdf-xwlt's firm_id
    rule extended to the other four ids here)."""
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    monkeypatch.setenv("LINK_CHANNEL", "staging")
    _stub_open_link(monkeypatch)

    token, jti = mint_link_token("firm-a", "i-90", "emp-7")
    service = _real_service()
    ws = _make_mock_websocket()

    await fill_form_from_schema(ws, service=service, token=token)

    ai = service.live_ai
    assert ai._firm_id == "firm-a"
    assert ai._employee_id == "emp-7"
    assert ai._link_jti == jti
    assert ai._kit_id == "i-90"
    assert ai._channel == "staging"
    # A link session must never be closed by this path -- if any gate had
    # refused, the ids above would just be the adapter's None defaults and
    # this assertion is what catches that silently-vacuous case.
    ws.close.assert_not_called()


@pytest.mark.asyncio
async def test_staff_session_carries_staff_uid_as_employee_id_and_no_link(
    monkeypatch,
):
    """A staff session (no magic link) still attributes the usage event to a
    PERSON -- the staff uid -- with link_jti left None (bd
    polyglot-pdf-cjifh: "Staff sessions carry the staff uid as employee_id
    and link_jti None"). Distinct from log_form_session_start's employee_id,
    which stays None for a staff session on purpose (see that function's
    docstring) -- this test is about the USAGE event's attribution, not the
    confirmation-audit record, and asserts the adapter's context directly so
    it cannot be fooled by conflating the two."""
    monkeypatch.setattr(
        "backend.routes.websocket_routes.verify_token",
        lambda token: {"uid": "staff-uid-42", "firm_id": "firm-b"},
    )
    monkeypatch.setenv("LINK_CHANNEL", "demo")

    service = _real_service()
    ws = _make_mock_websocket()

    await fill_form_from_schema(ws, service=service, token="staff.token.jwt")

    ai = service.live_ai
    assert ai._firm_id == "firm-b"
    assert ai._employee_id == "staff-uid-42"
    assert ai._link_jti is None
    assert ai._channel == "demo"
    ws.close.assert_not_called()


# ---------------------------------------------------------------------------
# Layer 2: the per-turn emit reaches log_gemini_api_response with the ids
# ---------------------------------------------------------------------------

class _DummyContextManager:
    """Async context manager returning the supplied session (same shape as
    test_live_ai_gemini.py's helper of the same name)."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _OneUsageEventSession:
    """Yields exactly one event carrying usage_metadata, then stops."""

    def __init__(self):
        self._generator = None

    async def send_realtime_input(self, **_kwargs):
        return None

    def receive(self):
        if self._generator is None:
            async def gen():
                usage = SimpleNamespace(
                    prompt_token_count=100,
                    response_token_count=20,
                    total_token_count=120,
                    prompt_tokens_details=[
                        types.ModalityTokenCount(
                            modality=types.Modality.TEXT, token_count=60),
                        types.ModalityTokenCount(
                            modality=types.Modality.AUDIO, token_count=40),
                    ],
                    response_tokens_details=[
                        types.ModalityTokenCount(
                            modality=types.Modality.TEXT, token_count=20),
                    ],
                )
                yield SimpleNamespace(
                    usage_metadata=usage,
                    tool_call=None,
                    server_content=None,
                )
            self._generator = gen()
        return self._generator


@pytest.mark.asyncio
async def test_per_turn_emit_carries_all_six_context_keys():
    """set_session_context's ids reach log_gemini_api_response on the very
    next billed turn -- the seam the coverage/schema tests (bd wio6m) cannot
    exercise, because they call the wrapper directly rather than driving the
    adapter's real receive loop.

    MUTATION HOOK: commenting out any one of the six kwargs at the
    log_gemini_api_response call site in live_ai_gemini.py (or any one of the
    five new set_session_context assignments) turns exactly the matching
    assertion below red -- verified by hand for firm_id during authoring.
    """
    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter.set_session_context(
        form_session_id="fs-1",
        form_id="I-90",
        current_section_id="sec-1",
        firm_id="firm-a",
        employee_id="emp-7",
        link_jti="jti-xyz",
        kit_id="i-90",
        channel="staging",
    )
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    session = _OneUsageEventSession()
    fake_live = MagicMock()
    fake_live.connect.return_value = _DummyContextManager(session)
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    with patch("backend.adapters.live_ai_gemini.get_structured_logger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        await asyncio.wait_for(
            adapter._run_session_loop(), timeout=1.0
        )

    mock_logger.log_gemini_api_response.assert_called_once()
    kwargs = mock_logger.log_gemini_api_response.call_args.kwargs
    assert kwargs["form_id"] == "I-90"
    assert kwargs["form_session_id"] == "fs-1"
    assert kwargs["firm_id"] == "firm-a"
    assert kwargs["employee_id"] == "emp-7"
    assert kwargs["link_jti"] == "jti-xyz"
    assert kwargs["kit_id"] == "i-90"
    assert kwargs["channel"] == "staging"
    assert kwargs["model"] == adapter._model_name

    await adapter.finalize()


@pytest.mark.asyncio
async def test_per_turn_emit_leaves_unset_ids_null_not_absent():
    """The complement: a session with NO context ids set (the pre-cjifh
    shape, or a legacy caller) still reaches log_gemini_api_response --
    with every context kwarg explicitly None, matching the v2 envelope's
    "missing key vs null" contract (bd wio6m) rather than omitting the
    kwargs and falling back to _emit_usage's own defaults by accident."""
    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter.set_session_context(form_session_id="fs-2", form_id="I-90")
    adapter._audio_queue = None
    adapter._text_queue = None

    session = _OneUsageEventSession()
    fake_live = MagicMock()
    fake_live.connect.return_value = _DummyContextManager(session)
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    with patch("backend.adapters.live_ai_gemini.get_structured_logger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        await asyncio.wait_for(
            adapter._run_session_loop(), timeout=1.0
        )

    kwargs = mock_logger.log_gemini_api_response.call_args.kwargs
    assert kwargs["firm_id"] is None
    assert kwargs["employee_id"] is None
    assert kwargs["link_jti"] is None
    assert kwargs["kit_id"] is None
    assert kwargs["channel"] is None
    # model is always the adapter's own model name, never null -- it is not
    # session-context-dependent the way the other five are.
    assert kwargs["model"] == adapter._model_name

    await adapter.finalize()
