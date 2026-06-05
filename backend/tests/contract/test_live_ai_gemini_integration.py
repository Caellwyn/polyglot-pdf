import asyncio
import os
from typing import Any

import pytest

from backend.adapters.live_ai_gemini import LiveAIGemini

pytestmark = pytest.mark.external


async def _wait_for_audio(session, timeout: float = 30.0) -> bytes | None:
    """Iterate over live responses until we observe inline audio bytes.

    Native audio-to-audio models reply with AUDIO (inline_data on the model
    turn), NOT a TEXT modality — requesting TEXT from them is rejected with a
    1007 close. So the smoke test asserts we get real audio bytes back.
    """

    async def _reader() -> bytes | None:
        async for chunk in session.receive():
            server_content = getattr(chunk, "server_content", None)
            if server_content is None:
                continue
            model_turn = getattr(server_content, "model_turn", None)
            if model_turn is None:
                continue
            for part in getattr(model_turn, "parts", []) or []:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline is not None else None
                if data:
                    return data
        return None

    try:
        return await asyncio.wait_for(_reader(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


@pytest.mark.asyncio
async def test_live_ai_gemini_real_connection():
    """Smoke-test that we can establish a Gemini Live session and receive audio."""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY is not configured")

    # Pins the 2.5 native-audio model. NOTE: this is NO LONGER the app default
    # (default is now 3.1, USE_PREMIUM_MODEL=true) — but 3.1 1007s on this minimal
    # AUDIO-only config, so the test still drives 2.5; reworking it to exercise the
    # 3.1 default via the real adapter config is tracked in bd polyglot-pdf-a7k.
    # (The old gemini-live-2.5-flash-preview string 1008'd — see config.py.)
    model = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")

    # This smoke test drives text via a RAW send_client_content() call (line below),
    # which the 3.1 family rejects with a 1007 (bd polyglot-pdf-1g6). The test is
    # pinned to 2.5; if GEMINI_LIVE_MODEL is overridden to a 3.1 model, skip rather
    # than reproduce that 1007 and look like a regression. The adapter's own text
    # path is model-safe via _send_text_turn; reworking this test to exercise the
    # 3.1 default through the adapter is tracked in bd polyglot-pdf-a7k.
    from backend.config import model_family
    if model_family(model) == "3.1":
        pytest.skip("contract test uses raw send_client_content, which 3.1 1007s; pin 2.5 (bd a7k)")

    adapter = LiveAIGemini(api_key=api_key, model=model)

    # If the runtime lacks an async client surface, bail early with a helpful skip.
    client = getattr(adapter, "_client", None)
    if client is None or not hasattr(client, "aio"):
        pytest.skip("google.genai client does not expose async interface; upgrade google-genai")

    # Native-audio models emit AUDIO only; requesting TEXT here gets a 1007 close.
    config: dict[str, Any] = {
        "response_modalities": ["AUDIO"],
        "system_instruction": "You are a diagnostics bot. When contacted, say the word ACK.",
    }

    async with adapter.connect(model=model, config=config) as session:
        # Some SDK versions expose send_client_content; if absent we cannot provoke a response.
        send_client_content = getattr(session._session, "send_client_content", None)  # type: ignore[attr-defined]
        if send_client_content is None:
            pytest.skip("Gemini session missing send_client_content; update google-genai package")

        await send_client_content(turns={"parts": [{"text": "Please reply."}]})

        audio = await _wait_for_audio(session)
        assert audio, "No audio response received from Gemini within timeout"
