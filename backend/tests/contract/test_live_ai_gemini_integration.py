import asyncio
import os
from typing import Any

import pytest

from backend.adapters.live_ai_gemini import LiveAIGemini
from backend.config import get_settings, model_family

pytestmark = pytest.mark.external

# 2.5 native-audio is known-flaky on the audio path (bd polyglot-pdf-daa);
# one retry keeps residual flakiness from failing the smoke test outright.
_ATTEMPTS = 2


async def _wait_for_audio(session, timeout: float = 30.0) -> bytes | None:
    """Iterate over live responses until we observe inline audio bytes.

    Native audio-to-audio models reply with AUDIO (inline_data on the model
    turn), NOT a TEXT modality -- requesting TEXT from them is rejected with a
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
    """Smoke-test the DEFAULT model with the adapter's REAL config (bd a7k).

    Resolves the model from settings (MODEL_NATIVE, i.e. whatever
    USE_PREMIUM_MODEL selects) and connects with the same config dict the
    adapter's session loop sends (_build_live_config: tools + VAD +
    transcriptions + system instruction). A hand-rolled minimal config is NOT
    representative: the 3.1 family rejects it with a 1007 close, and the demo
    never ships one. Text is driven through the adapter's model-safe
    _send_text_turn rather than a raw send_client_content call (which 3.1
    also 1007s -- bd polyglot-pdf-1g6).
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY is not configured")

    settings = get_settings()
    model = os.getenv("GEMINI_LIVE_MODEL", settings.MODEL_NATIVE)

    last_failure = None
    for attempt in range(1, _ATTEMPTS + 1):
        adapter = LiveAIGemini(api_key=api_key, model=model)
        adapter._function_declarations = settings.TOOL_DECLARATIONS
        adapter._system_instruction = (
            "You are a diagnostics bot. When contacted, say the word ACK."
        )

        client = getattr(adapter, "_client", None)
        if client is None or not hasattr(client, "aio"):
            pytest.skip("google.genai client does not expose async interface")

        config: dict[str, Any] = adapter._build_live_config(settings)
        assert "tools" in config and "realtime_input_config" in config, (
            "adapter config builder no longer emits the real config shape"
        )

        async with adapter.connect(model=model, config=config) as session:
            await adapter._send_text_turn(session._session, "Please reply.")  # type: ignore[attr-defined]
            audio = await _wait_for_audio(session)
            if audio:
                return
            last_failure = (
                f"attempt {attempt}/{_ATTEMPTS}: no audio from {model} "
                f"(family {model_family(model)}) within timeout"
            )

    pytest.fail(last_failure or "no audio response received")
