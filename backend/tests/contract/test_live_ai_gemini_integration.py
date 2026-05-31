import asyncio
import os
from typing import Any

import pytest

from backend.adapters.live_ai_gemini import LiveAIGemini

pytestmark = pytest.mark.external


async def _wait_for_text(session, timeout: float = 30.0) -> str | None:
    """Iterate over live responses until we observe textual content."""

    async def _reader() -> str | None:
        async for chunk in session.receive():
            # Direct text attribute (common on early chunks)
            text = getattr(chunk, "text", None)
            if text:
                return text

            # server_content.model_turn.parts[0].text/display_text is another shape
            server_content = getattr(chunk, "server_content", None)
            if server_content is not None:
                model_turn = getattr(server_content, "model_turn", None)
                if model_turn is not None:
                    for part in getattr(model_turn, "parts", []) or []:
                        text = getattr(part, "text", None) or getattr(part, "display_text", None)
                        if text:
                            return text

        return None

    try:
        return await asyncio.wait_for(_reader(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


@pytest.mark.asyncio
async def test_live_ai_gemini_real_connection():
    """Smoke-test that we can establish a Gemini Live session and receive text."""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY is not configured")

    # Default to the standard native audio-to-audio model we actually run
    # (the retired half-cascade gemini-live-2.5-flash-preview gets 1008'd).
    model = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")
    adapter = LiveAIGemini(api_key=api_key, model=model)

    # If the runtime lacks an async client surface, bail early with a helpful skip.
    client = getattr(adapter, "_client", None)
    if client is None or not hasattr(client, "aio"):
        pytest.skip("google.genai client does not expose async interface; upgrade google-genai")

    config: dict[str, Any] = {
        "response_modalities": ["TEXT"],
        "system_instruction": "You are a diagnostics bot. Reply with the word ACK when contacted.",
    }

    async with adapter.connect(model=model, config=config) as session:
        # Some SDK versions expose send_client_content; if absent we cannot provoke a response.
        send_client_content = getattr(session._session, "send_client_content", None)  # type: ignore[attr-defined]
        if send_client_content is None:
            pytest.skip("Gemini session missing send_client_content; update google-genai package")

        await send_client_content(turns={"parts": [{"text": "Please reply with ACK."}]})

        text = await _wait_for_text(session)
        assert text is not None, "No textual response received from Gemini within timeout"
        assert "ACK" in text.upper()
