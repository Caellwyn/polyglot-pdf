"""Spec: _send_text_turn picks the send method by model family (bd polyglot-pdf-uov.11, T2.4).

The 3.1 family REJECTS send_client_content() text turns with close code 1007, so
the adapter routes text turns by model family:
  - 3.1 family        -> session.send_realtime_input(text=...)
  - 3.8 / 2.5 / other -> session.send_client_content(turns=..., turn_complete=True)
(3.8 is the default standard tier; endpoint-verified to accept send_client_content
on Vertex, bd polyglot-pdf-bd1zs.)
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

from backend.config import model_family, MODEL_NATIVE_PREMIUM, MODEL_NATIVE_STANDARD
from backend.adapters.live_ai_gemini import LiveAIGemini


# Use the REAL config model-name constants (the same ones USE_PREMIUM_MODEL
# flips MODEL_NATIVE between), not hardcoded copies -- so if config renames a
# model string, this spec tracks the rename instead of silently exercising a
# stale name. The precondition test then pins that these resolve to the expected
# families.
MODEL_3P1 = MODEL_NATIVE_PREMIUM
MODEL_STANDARD = MODEL_NATIVE_STANDARD
# 2.5 is no longer a tier constant, but an explicit MODEL_NATIVE pin can still
# select it, so its send path stays pinned with a literal id.
MODEL_2P5 = "gemini-live-2.5-flash-native-audio"


def _adapter_for(model_name: str) -> LiveAIGemini:
    # Bare adapter (no api_key) is the mocked-unit-test default; _send_text_turn
    # reads only self._model_name and the passed-in session.
    return LiveAIGemini(api_key=None, model=model_name, vertexai=False)


def test_model_family_mapping_precondition():
    """Guard the assumption the branch rests on: these names map as expected."""
    assert model_family(MODEL_3P1) == "3.1"
    assert model_family(MODEL_STANDARD) == "3.8"
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
async def test_3p8_standard_uses_send_client_content_not_realtime_input():
    """The default 3.8 tier sends text turns via send_client_content (verified on Vertex)."""
    adapter = _adapter_for(MODEL_STANDARD)
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
