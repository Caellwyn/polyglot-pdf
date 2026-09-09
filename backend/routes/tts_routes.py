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
from backend.services.auth import require_auth, require_paid_client_work
from backend.services.link_tokens import link_channel
from backend.services.notice_tts import KNOWN_NOTICES, synthesize_notice
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


def _usage_session_ctx(claims: dict) -> dict:
    """This request's usage-event context from the auth dependency's claims
    dict (bd polyglot-pdf-t86oz -- "backend/routes/tts_routes.py has the
    claims dict from its auth dependency").

    No form_session_id: these are ordinary HTTP routes, not a WebSocket
    session -- the usage-event schema allows None here (bd polyglot-pdf-wio6m).

    Two claim SHAPES reach these routes (see backend/services/auth.py):
      - a client-LINK credential: firm_id, link_kit_id, employee_id, jti,
        is_client_link=True;
      - a staff Firebase token: firm_id, uid, no employee_id/jti/link_kit_id.
    Mirrors websocket_routes.py's usage_employee_id derivation (bd
    polyglot-pdf-cjifh): a staff caller still attributes to a PERSON (their
    uid) even though they carry no link_jti.
    """
    if not isinstance(claims, dict):
        return {}
    is_link = bool(claims.get("is_client_link"))
    return {
        "firm_id": claims.get("firm_id"),
        "employee_id": (claims.get("employee_id") if is_link
                        else claims.get("uid")),
        "link_jti": claims.get("jti") if is_link else None,
        "kit_id": claims.get("link_kit_id") if is_link else None,
        "channel": link_channel(),
    }


class SpellbackRequest(BaseModel):
    value: str
    # The session's spoken-language NAME as the frontend holds it ("Spanish").
    # Optional for wire-compat with a client one deploy behind; absent means
    # the en-US fallback frame/voice.
    language: str | None = None


@router.post("/api/tts/spellback")
async def spellback_tts(
    request: SpellbackRequest, user: dict = Depends(require_paid_client_work)
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
            value, settings, language_name=request.language,
            session_ctx=_usage_session_ctx(user),
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
    user: dict = Depends(require_paid_client_work),
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
            request.language, form_number, settings,
            session_ctx=_usage_session_ctx(user),
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


class NoticeRequest(BaseModel):
    """A SAFETY NOTICE the app chose to speak (bd polyglot-pdf-dft1)."""

    # A KEY, never text. The words live server-side; see services/notice_tts.py
    # for why that is what keeps a free route from becoming an open
    # text-to-speech service.
    notice: str
    language: str | None = None


@router.post("/api/tts/notice")
async def notice_tts(
    request: NoticeRequest,
    http_request: Request,
    user: dict = Depends(require_auth),
) -> Response:
    """Speak one of our own safety notices. FREE, deliberately.

    require_auth, NOT require_paid_client_work -- the difference is the whole
    point (maintainer, 2026-08-27). The paid dependency REDEEMS the link, so
    using it here would:
      - answer the budget-exhausted client with silence, when they are exactly
        who needs to hear "save your form now", and
      - BURN a live client's link to deliver a warning we chose to give.

    A client still needs a valid credential to reach it, so this is not an open
    endpoint -- it simply does not charge for our own words. It still emits a
    usage_kind="tts_notice" event (this speech has a real Cloud TTS cost even
    though it is free to the client) -- "FREE" means not billed against the
    client's link/credit, not that it has no telemetry.
    """
    settings = get_settings()

    notice = (request.notice or "").strip()
    if notice not in KNOWN_NOTICES:
        # Refuse BEFORE synthesis: the keyed-route contract.
        raise HTTPException(status_code=400, detail="unknown notice")

    try:
        audio, etag = await synthesize_notice(
            request.language, notice, settings,
            session_ctx=_usage_session_ctx(user),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="unknown notice")
    except Exception as exc:
        # Error TYPE only, consistent with the other two TTS routes.
        _log.error("notice_tts_failed", error_type=type(exc).__name__)
        raise HTTPException(status_code=502, detail="tts synthesis failed")

    # Same manual-revalidation contract as the intro route above (bd
    # polyglot-pdf-see5j): browsers neither cache POST responses nor
    # auto-send If-None-Match on POST, so the client must store this ETag
    # itself and hand-attach If-None-Match on a re-fetch to get the 304
    # instead of re-downloading the clip.
    headers = {"ETag": etag, "Cache-Control": "private, max-age=86400"}
    if http_request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=audio, media_type="audio/mpeg", headers=headers)
