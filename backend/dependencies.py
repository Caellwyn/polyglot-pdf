import asyncio
import threading

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


def get_text_ai_pro(settings: Settings = Depends(get_settings)) -> ITextAI | None:
    """W6 (bd polyglot-pdf-gbus): the gemini-2.5-pro whole-form validator for the
    end-of-form pro pass. Returns None unless FORM_COMPLETE_PRO_VALIDATOR is on;
    when it is OFF, this returns None and the service's handle_form_complete_pro
    no-ops clean. The flag now DEFAULTS ON (maintainer directive 2026-08-03), so
    this normally returns a wired client; set FORM_COMPLETE_PRO_VALIDATOR=false
    to go back to the dark path.

    Constructed with a BOUNDED thinking budget (W5 config) and an EMPTY fallback
    chain -- falling back to the lite tier would silently defeat the far-pair recall
    the pro pass exists for, so a pro outage must fail-open (clean), never downgrade.
    """
    if not settings.FORM_COMPLETE_PRO_VALIDATOR:
        return None
    return TextAIGemini(
        api_key=settings.GEMINI_API_KEY,
        model=settings.VALIDATOR_PRO_MODEL,
        vertexai=settings.VERTEXAI,
        fallback_models=(),  # no lite-tier fallback; fail-open instead of downgrade
        thinking_budget=settings.VALIDATOR_PRO_THINKING_BUDGET,
    )


# Process-cached TEXT clients (bd polyglot-pdf-4hnyq). Safe to share:
# TextAIGemini is a stateless request/response helper -- no callbacks, no
# session, nothing per-connection -- unlike LiveAIGemini, which MUST stay
# fresh per connection (callback isolation, see get_live_ai).
#
# Keyed on the CONFIG VALUES that determine the client, never on id(settings):
# Settings is unhashable (so lru_cache is out), and an identity key is a live
# footgun -- CPython aggressively reuses addresses, so a GC'd short-lived
# Settings could alias a NEW one and hand back a client built for different
# config (wrong model / vertexai / key). Tests build transient Settings
# constantly, and this repo has already been bitten by an id/cache-aliasing
# bug of this shape (fresh-eyes round 1). Value-keying makes a differing
# Settings miss the cache by construction.
_TEXT_AI_CACHE: dict = {}
_TEXT_AI_CACHE_MAX = 8
_MISSING = object()  # sentinel: distinguishes "no entry" from a falsy/None value
# bd polyglot-pdf-oqqxj / polyglot-pdf-ioe8d: get_form_filling_service fires
# _cached_text_ai and _cached_text_ai_pro CONCURRENTLY via asyncio.gather(
# asyncio.to_thread(...), asyncio.to_thread(...)), so _cache_get_or_build runs
# on real worker threads, not merely interleaved coroutines. This dict is
# guarded by a per-key IN-PROGRESS PLACEHOLDER pattern (see _BuildInProgress
# and _cache_get_or_build below), not spellback_tts.py's simpler
# double-checked `_client`/`_available_voices` lock: that pattern is safe
# there only because those globals are never evicted once built, while
# _TEXT_AI_CACHE supports eviction on overflow -- an eviction racing a
# build's own dict bookkeeping is exactly the hazard the placeholder design
# closes. Holding the lock across the (slow, ~3s) build() call itself would
# also be correct but SERIALIZES unrelated keys (_cached_text_ai and
# _cached_text_ai_pro build concurrently in production; FORM_COMPLETE_PRO_
# VALIDATOR defaults ON), eating into the 9.4s->3.2s cold-start latency win
# bd 4hnyq exists to protect -- so the lock here guards ONLY the dict
# mutations (presence check, eviction, placeholder claim/publish), never the
# build itself.
_TEXT_AI_CACHE_LOCK = threading.Lock()


class _BuildInProgress:
    """Placeholder held in _TEXT_AI_CACHE while a build is running, so a
    concurrent caller for the SAME key waits on the result instead of
    starting a duplicate build (or observing a torn/missing entry)."""

    __slots__ = ("event", "value", "error")

    def __init__(self):
        self.event = threading.Event()
        self.value = None
        self.error = None


def _text_ai_cache_key(kind: str, settings: Settings) -> tuple:
    """The config values a text client is built from (see get_text_ai /
    get_text_ai_pro). Any difference here MUST miss the cache."""
    return (
        kind,
        getattr(settings, "GEMINI_API_KEY", None),
        getattr(settings, "MODEL_LABELING", None),
        getattr(settings, "VERTEXAI", None),
        getattr(settings, "FORM_COMPLETE_PRO_VALIDATOR", None),
        getattr(settings, "VALIDATOR_PRO_MODEL", None),
        getattr(settings, "VALIDATOR_PRO_THINKING_BUDGET", None),
    )


def _cache_get_or_build(kind: str, settings: Settings, build):
    key = _text_ai_cache_key(kind, settings)

    while True:
        with _TEXT_AI_CACHE_LOCK:
            entry = _TEXT_AI_CACHE.get(key, _MISSING)
            if entry is _MISSING:
                # We are the (first) builder for this key: claim it with a
                # placeholder BEFORE releasing the lock, so no other thread
                # starts a duplicate build for the same key.
                if len(_TEXT_AI_CACHE) >= _TEXT_AI_CACHE_MAX:
                    # Evict FINISHED entries only. Wiping an IN-PROGRESS
                    # placeholder here would let a caller for that OTHER key
                    # see _MISSING and start a duplicate build -- exactly the
                    # race this cache exists to prevent -- while that
                    # build's own waiters are still blocked on an Event no
                    # longer reachable through the dict.
                    for k in [
                        k
                        for k, v in _TEXT_AI_CACHE.items()
                        if not isinstance(v, _BuildInProgress)
                    ]:
                        del _TEXT_AI_CACHE[k]
                placeholder = _BuildInProgress()
                _TEXT_AI_CACHE[key] = placeholder
                is_builder = True
            elif isinstance(entry, _BuildInProgress):
                # Someone else is already building this exact key -- wait for
                # them OUTSIDE the lock (below), not here.
                placeholder = entry
                is_builder = False
            else:
                # A real, finished value.
                return entry

        if is_builder:
            try:
                value = build(settings)
            except BaseException as exc:  # noqa: BLE001 - must propagate to every waiter
                with _TEXT_AI_CACHE_LOCK:
                    # Only remove OUR OWN placeholder: an eviction may have
                    # already cleared it (or replaced it with someone else's
                    # retry), and removing THAT would be wrong.
                    if _TEXT_AI_CACHE.get(key) is placeholder:
                        del _TEXT_AI_CACHE[key]
                placeholder.error = exc
                placeholder.event.set()
                raise
            with _TEXT_AI_CACHE_LOCK:
                # Only overwrite if OUR placeholder is still the live entry:
                # a concurrent eviction may have already cleared it (or
                # another builder already replaced it after a clear). Either
                # way, publishing the value we just built is still correct
                # for OUR callers (below) -- we just don't clobber a newer
                # cache state with a stale one.
                if _TEXT_AI_CACHE.get(key) is placeholder:
                    _TEXT_AI_CACHE[key] = value
            placeholder.value = value
            placeholder.event.set()
            return value

        # Not the builder: wait for the in-progress build to finish, then
        # loop back around to fetch (or re-attempt) rather than trusting a
        # value that might have been captured before completion.
        placeholder.event.wait()
        if placeholder.error is not None:
            raise placeholder.error
        return placeholder.value


def _cached_text_ai(settings: Settings) -> ITextAI:
    return _cache_get_or_build("text_ai", settings, get_text_ai)


def _cached_text_ai_pro(settings: Settings) -> ITextAI | None:
    return _cache_get_or_build("text_ai_pro", settings, get_text_ai_pro)


async def get_form_filling_service(
    settings: Settings = Depends(get_settings),
) -> Any:
    """Build the per-connection service OFF the event loop (bd polyglot-pdf-4hnyq).

    The three AI adapters each construct a `genai.Client`, and on the Vertex
    path that resolves ADC + endpoint discovery SYNCHRONOUSLY -- measured ~9.4s
    per connection locally. As plain `def` sub-dependencies of the /ws/fill
    route they ran on the event loop BEFORE `websocket.accept()`, so the
    handshake itself was charged that time and the frontend's 10s connect
    timeout lost a coin-flip (the E2E voice harness failed 0/15 fields with the
    client spraying 'WebSocket not open, readyState:0').

    FastAPI runs a plain `def` dependency in a threadpool, but only when it is
    the DECLARED dependency -- these were nested behind this one, which was
    itself `def`, so the whole chain collapsed onto one blocking call. Making
    THIS one `async` and pushing the construction into `asyncio.to_thread`
    keeps the EVENT LOOP free while it runs, so other sessions are not stalled
    by one connection's setup. Note the win is parallelism + caching, NOT
    overlap with the handshake: FastAPI resolves dependencies BEFORE entering
    the handler, so construction still precedes `websocket.accept()` --
    9.4s -> 3.2s comes from building the three concurrently and reusing the
    cached text clients (Opus cross-surface review corrected an earlier
    claim of overlap here).

    Deliberately builds the adapters here rather than via `Depends`: a fresh
    LiveAIGemini per connection is load-bearing (callback isolation -- a shared
    instance routes tool calls to the wrong tab, see get_live_ai), and routing
    them through Depends is exactly what put them back on the loop.
    """
    # Lazy import to avoid circular import at module import time
    from backend.services.form_filling_service import FormFillingService

    # The TEXT adapters are stateless request/response helpers (secretary,
    # validators) with no per-connection callback state, so their clients are
    # PROCESS-CACHED: only the first connection pays their construction. The
    # LIVE adapter must stay fresh per connection (callback isolation -- a
    # shared instance routes tool calls to the wrong tab, see get_live_ai), so
    # it is built per call, off the loop, concurrently with the (usually
    # cached) text ones.
    live_ai, text_ai, text_ai_pro = await asyncio.gather(
        asyncio.to_thread(get_live_ai, settings),
        asyncio.to_thread(_cached_text_ai, settings),
        asyncio.to_thread(_cached_text_ai_pro, settings),
    )

    return FormFillingService(
        live_ai=live_ai,
        settings=settings,
        text_ai=text_ai,
        text_ai_pro=text_ai_pro,
    )

