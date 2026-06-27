from fastapi import Depends
from typing import Any
from backend.config import Settings, get_settings
from backend.ports.live_ai_port import ILiveAI
from backend.adapters.live_ai_gemini import LiveAIGemini
from backend.ports.text_ai_port import ITextAI
from backend.adapters.text_ai_gemini import TextAIGemini


def get_live_ai(settings: Settings = Depends(get_settings)) -> ILiveAI:
    # CRITICAL: Create a fresh LiveAIGemini instance for EACH WebSocket connection
    # to avoid callback interference between multiple tabs/connections.
    # Each instance maintains its own Gemini session and callback state.
    # 
    # BUG FIX: Previously, FastAPI's dependency caching could cause multiple
    # WebSocket connections to share the same LiveAIGemini instance, leading to
    # callbacks being overwritten when the second connection called set_callbacks().
    # This caused tool calls to be routed to only the most recent connection.
    model_name = settings.MODEL_NATIVE
    vertexai = settings.VERTEXAI
    # Pass both api_key and model to the adapter; the adapter will construct
    # a `genai.Client(api_key=...)` when possible. This matches
    # LabelingAIGemini's constructor convention.
    return LiveAIGemini(api_key=settings.GEMINI_API_KEY, model=model_name, vertexai=vertexai)


def get_text_ai(settings: Settings = Depends(get_settings)) -> ITextAI:
    # Fresh instance per call (consistent with get_live_ai shape).
    # Model: MODEL_LABELING env knob (default gemini-2.5-flash; pin to
    # gemini-2.5-flash-lite in deploy env). Reuse decided in F3 contract
    # (docs/standards/validation-delegation.md, contract 5).
    return TextAIGemini(
        api_key=settings.GEMINI_API_KEY,
        model=settings.MODEL_LABELING,
        vertexai=settings.VERTEXAI,
    )


def get_form_filling_service(
    live_ai: ILiveAI = Depends(get_live_ai),
    settings: Settings = Depends(get_settings),
    text_ai: ITextAI = Depends(get_text_ai),
) -> Any:
    # Lazy import to avoid circular import at module import time
    from backend.services.form_filling_service import FormFillingService

    return FormFillingService(
        live_ai=live_ai,
        settings=settings,
        text_ai=text_ai,
    )

