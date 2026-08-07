"""
Spell-back TTS route (bd polyglot-pdf-22h1f).

POST /api/tts/spellback -- synthesize a deterministic letter-by-letter clip of
a client-supplied stored field value (Cloud Text-to-Speech), for the client to
play at the verification moment INSTEAD of the Live model speaking the spelling
(whose audio head has the measured sticky-first-spelling defect, bd 0rpu).

The client is the only caller: it resolves the current field's stored value
from its own sessionStorage (the backend is stateless and never holds field
values) and posts it here for synthesis. The value is PII -- it is never
logged (lengths only) and never persisted; the audio bytes are returned
directly and discarded.

Gated on SPELLBACK_TOOL_ENABLED (503 when off) so the deployment surface does
not expose a general-purpose TTS synthesizer while the feature is dark.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

import structlog

from backend.config import get_settings
from backend.services.auth import require_auth
from backend.services.spellback_tts import (
    MAX_SPELLBACK_CHARS,
    synthesize_spellback,
)

_log = structlog.get_logger()

router = APIRouter()


class SpellbackRequest(BaseModel):
    value: str


@router.post("/api/tts/spellback")
async def spellback_tts(
    request: SpellbackRequest, _user: dict = Depends(require_auth)
) -> Response:
    settings = get_settings()
    if not getattr(settings, "SPELLBACK_TOOL_ENABLED", False):
        raise HTTPException(status_code=503, detail="spellback disabled")

    value = request.value or ""
    if not value.strip():
        raise HTTPException(status_code=400, detail="empty value")
    if len(value) > MAX_SPELLBACK_CHARS:
        raise HTTPException(status_code=400, detail="value too long")

    try:
        audio = await synthesize_spellback(
            value, getattr(settings, "SPELLBACK_TTS_VOICE", "")
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid value")
    except Exception as exc:
        # Error TYPE only -- the exception text can embed the value (PII), and
        # this reaches Cloud Logging in production (the p84m principle).
        _log.error("spellback_tts_failed", error_type=type(exc).__name__)
        raise HTTPException(status_code=502, detail="tts synthesis failed")

    return Response(content=audio, media_type="audio/mpeg")
