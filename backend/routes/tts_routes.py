"""
Spell-back TTS route (bd polyglot-pdf-22h1f / 44ywm).

POST /api/tts/spellback -- synthesize the deterministic verification clip
("You said J, O, S, E. Is that correct?" in the SESSION language, regional
voice) for a client-supplied stored field value, for the client to play at
the verification moment INSTEAD of the Live model speaking the spelling
(whose audio head has the measured sticky-first-spelling defect, bd 0rpu).

The client is the only caller: it resolves the current field's stored value
from its own sessionStorage (the backend is stateless and never holds field
values) and posts it here with the session's spoken-language name. The value
is PII -- it is never logged (lengths only) and never persisted; the audio
bytes are returned directly and discarded. The language name is not PII and
maps through the same table as the ASR bias (language_codes.py).

Gated on SPELLBACK_TOOL_ENABLED (503 when off) so the deployment surface does
not expose a general-purpose TTS synthesizer while the feature is dark.

Also home to POST /api/tts/intro (sprint 20, bd polyglot-pdf-s1iex.3): Sol's
scripted intro+disclaimer clip. Keyed route -- the caller sends a bounded
form-number key and a language name; every synthesized word comes from
server-side tables (intro_tts.py), never caller text. Gated on
INTRO_TTS_ENABLED (503 when off).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import structlog

from backend.config import get_settings
from backend.services.auth import require_auth
from backend.services.intro_tts import (
    KNOWN_FORMS,
    resolve_intro_language,
    script_version,
    synthesize_intro,
)
from backend.services.spellback_tts import (
    MAX_SPELLBACK_CHARS,
    synthesize_spellback,
)

_log = structlog.get_logger()

router = APIRouter()


class SpellbackRequest(BaseModel):
    value: str
    # The session's spoken-language NAME as the frontend holds it ("Spanish").
    # Optional for wire-compat with a client one deploy behind; absent means
    # the en-US fallback frame/voice.
    language: str | None = None


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
            value, settings, language_name=request.language
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid value")
    except Exception as exc:
        # Error TYPE only -- the exception text can embed the value (PII), and
        # this reaches Cloud Logging in production (the p84m principle).
        _log.error("spellback_tts_failed", error_type=type(exc).__name__)
        raise HTTPException(status_code=502, detail="tts synthesis failed")

    return Response(content=audio, media_type="audio/mpeg")


class IntroRequest(BaseModel):
    # A key into intro_tts.KNOWN_FORMS ("I-90"), never free text.
    form_number: str
    # The session's spoken-language NAME as the frontend holds it ("Spanish").
    # Optional; absent or unknown falls back to the English script + voice,
    # matching the disclaimer modal's own translation fallback.
    language: str | None = None


@router.post("/api/tts/intro")
async def intro_tts(
    request: IntroRequest,
    http_request: Request,
    _user: dict = Depends(require_auth),
) -> Response:
    settings = get_settings()
    if not getattr(settings, "INTRO_TTS_ENABLED", False):
        raise HTTPException(status_code=503, detail="intro tts disabled")

    form_number = (request.form_number or "").strip()
    if form_number not in KNOWN_FORMS:
        # Reject before anything reaches synthesis -- the keyed-route
        # contract: caller text never becomes spoken audio.
        raise HTTPException(status_code=400, detail="unknown form")

    try:
        audio, etag = await synthesize_intro(
            request.language, form_number, settings
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="unknown form")
    except Exception as exc:
        # Error TYPE only (the p84m principle) -- consistent with the
        # spell-back route above, even though intro inputs are all
        # server-side table values rather than PII.
        _log.error("intro_tts_failed", error_type=type(exc).__name__)
        raise HTTPException(status_code=502, detail="tts synthesis failed")

    # Private: the route is auth-gated, so shared caches must not store it.
    # NOTE the revalidation contract is MANUAL: browsers neither cache POST
    # responses nor auto-send If-None-Match on POST, so the client (bd
    # s1iex.5) must store this ETag itself and hand-attach If-None-Match on
    # a re-fetch to get the 304 instead of re-downloading ~400KB. The
    # Cache-Control header is inert on a POST today and is kept only because
    # the plan specifies it (it activates if this ever becomes a GET).
    # X-Intro-Script-Version: the hash of the exact text this clip speaks, so
    # the client can echo it into the acceptance record (bd
    # polyglot-pdf-s1iex.7). Returned as a HEADER rather than recomputed in the
    # browser on purpose: the backend stays the single source of the hash, so
    # the two can never drift into recording a version the backend never
    # synthesized. Exposed via CORS below.
    headers = {
        "Cache-Control": "private, max-age=3600",
        "ETag": etag,
        "X-Intro-Script-Version": script_version(resolve_intro_language(request.language)),
    }
    if http_request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=audio, media_type="audio/mpeg", headers=headers)
