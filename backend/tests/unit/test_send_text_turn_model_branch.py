"""Spec: _send_text_turn picks the send method by model family (bd polyglot-pdf-uov.11, T2.4).

The 3.1 family REJECTS send_client_content() text turns with close code 1007, so
the adapter routes text turns by model family:
  - 3.1 family  -> session.send_realtime_input(text=...)
  - 2.5 / other -> session.send_client_content(turns=..., turn_complete=True)
(backend/adapters/live_ai_gemini.py _send_text_turn). test_model_selection.py
covers only flag->model NAME resolution, never this send-path branch.

These tests exercise _send_text_turn DIRECTLY with a mocked session and a swapped
model name -- deliberately NOT through send_initiating_message or the
section-switch re-prime path. The model-family branch is a per-TURN decision, not
a per-session-lifecycle one, so testing it directly keeps the spec independent of
the section-end reset path (which may change), while still pinning the exact
contract that matters: 3.1 must never hit send_client_content (the 1007 trap).
"""

from unittest.mock import AsyncMock

import pytest

from backend.config import model_family
from backend.adapters.live_ai_gemini import LiveAIGemini


# Concrete model names whose family must resolve as expected; if these drift,
# the assertion below catches it (and the whole spec rests on the mapping).
MODEL_3P1 = "gemini-3.1-flash-live-preview"
MODEL_2P5 = "gemini-2.5-flash-native-audio-preview-12-2025"


def _adapter_for(model_name: str) -> LiveAIGemini:
    # Bare adapter (no api_key) is the mocked-unit-test default; _send_text_turn
    # reads only self._model_name and the passed-in session.
    return LiveAIGemini(api_key=None, model=model_name, vertexai=False)


def test_model_family_mapping_precondition():
    """Guard the assumption the branch rests on: these names map as expected."""
    assert model_family(MODEL_3P1) == "3.1"
    assert model_family(MODEL_2P5) == "2.5"


@pytest.mark.asyncio
async def test_3p1_uses_send_realtime_input_not_client_content():
    """3.1 family MUST route text via send_realtime_input (send_client_content -> 1007)."""
    adapter = _adapter_for(MODEL_3P1)
    session = AsyncMock()

    await adapter._send_text_turn(session, "hello world")

    session.send_realtime_input.assert_awaited_once_with(text="hello world")
    session.send_client_content.assert_not_called()


@pytest.mark.asyncio
async def test_2p5_uses_send_client_content_not_realtime_input():
    """2.5 family keeps the pre-fix send_client_content shape (turns + turn_complete)."""
    adapter = _adapter_for(MODEL_2P5)
    session = AsyncMock()

    await adapter._send_text_turn(session, "hello world")

    session.send_client_content.assert_awaited_once_with(
        turns={"parts": [{"text": "hello world"}]},
        turn_complete=True,
    )
    session.send_realtime_input.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_model_family_falls_back_to_client_content():
    """A non-3.1 (incl. unrecognized) family takes the send_client_content branch.

    The branch is `if 3.1 -> realtime else -> client_content`, so any model that
    is not the 3.1 family -- including a brand-new preview name model_family()
    does not recognize -- must use the client_content path, never realtime.
    """
    adapter = _adapter_for("gemini-9.9-some-future-preview")
    session = AsyncMock()

    await adapter._send_text_turn(session, "future text")

    session.send_client_content.assert_awaited_once()
    session.send_realtime_input.assert_not_called()


@pytest.mark.asyncio
async def test_branch_follows_the_live_model_name_when_swapped():
    """The branch reads self._model_name at call time, so swapping the model swaps the path.

    This mirrors the real A/B toggle (USE_PREMIUM_MODEL flips MODEL_NATIVE between
    the 2.5 and 3.1 names): the SAME adapter object, re-pointed at a different
    model, must change which send method it uses.
    """
    adapter = _adapter_for(MODEL_2P5)
    session = AsyncMock()

    await adapter._send_text_turn(session, "first")
    session.send_client_content.assert_awaited_once()
    session.send_realtime_input.assert_not_called()

    # Swap to 3.1 and send again -- now the realtime path must be taken.
    adapter._model_name = MODEL_3P1
    await adapter._send_text_turn(session, "second")
    session.send_realtime_input.assert_awaited_once_with(text="second")
