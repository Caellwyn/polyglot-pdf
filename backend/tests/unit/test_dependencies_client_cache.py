"""
Unit tests for the /ws/fill dependency build path (bd polyglot-pdf-4hnyq).

The WS handshake used to block ~9.4s before accept(): three Gemini adapters,
each resolving ADC/endpoint discovery synchronously, built SERIALLY inside the
route's Depends chain -- past the frontend's 10s connect timeout, which made
local voice testing fail on a coin-flip. get_form_filling_service now builds
them concurrently OFF the event loop, with the two STATELESS text clients
process-cached.

These tests pin the properties that keep that safe:
- the LIVE adapter is never shared (callback isolation -- a shared instance
  routes tool calls to the wrong tab);
- the TEXT adapters ARE reused for identical config (the latency win), and
  are NOT reused when the config differs (the aliasing hazard: the cache is
  keyed on config VALUES, never id(settings), because CPython reuses
  addresses and a GC'd Settings could otherwise alias a new one);
- the builds run CONCURRENTLY, not serially (the actual fix);
- construction happens off the event loop (it must not block accept()).

ASCII only.
"""
import asyncio
import time

import pytest

from backend.config import Settings
from backend import dependencies


@pytest.fixture(autouse=True)
def _clear_cache():
    dependencies._TEXT_AI_CACHE.clear()
    yield
    dependencies._TEXT_AI_CACHE.clear()


def _patch_builders(monkeypatch, delay=0.0):
    """Replace the three adapter builders with cheap fakes that record calls."""
    calls = {"live": 0, "text": 0, "pro": 0}

    def fake_live(settings):
        calls["live"] += 1
        if delay:
            time.sleep(delay)
        return ("live", calls["live"])

    def fake_text(settings):
        calls["text"] += 1
        if delay:
            time.sleep(delay)
        return ("text", calls["text"])

    def fake_pro(settings):
        calls["pro"] += 1
        if delay:
            time.sleep(delay)
        return ("pro", calls["pro"])

    monkeypatch.setattr(dependencies, "get_live_ai", fake_live)
    monkeypatch.setattr(dependencies, "get_text_ai", fake_text)
    monkeypatch.setattr(dependencies, "get_text_ai_pro", fake_pro)
    # FormFillingService construction is irrelevant here; keep it trivial.
    import backend.services.form_filling_service as ffs

    class _Svc:
        def __init__(self, live_ai=None, settings=None, text_ai=None, text_ai_pro=None):
            self.live_ai = live_ai
            self.text_ai = text_ai
            self.text_ai_pro = text_ai_pro

    monkeypatch.setattr(ffs, "FormFillingService", _Svc)
    return calls


@pytest.mark.asyncio
async def test_live_adapter_is_fresh_per_connection_text_clients_are_reused(
    monkeypatch,
):
    """The isolation/latency split: a NEW LiveAIGemini every connection
    (callback isolation), the same text clients reused (the 4hnyq win)."""
    calls = _patch_builders(monkeypatch)
    settings = Settings()

    first = await dependencies.get_form_filling_service(settings)
    second = await dependencies.get_form_filling_service(settings)

    # Live: built twice, and the two connections hold DIFFERENT instances.
    assert calls["live"] == 2
    assert first.live_ai != second.live_ai
    # Text: built once, shared.
    assert calls["text"] == 1
    assert calls["pro"] == 1
    assert first.text_ai is second.text_ai
    assert first.text_ai_pro is second.text_ai_pro


@pytest.mark.asyncio
async def test_differing_settings_do_not_share_a_cached_client(monkeypatch):
    """The aliasing guard: the cache is keyed on config VALUES, so a Settings
    with a different model/backend NEVER receives another's client -- even
    though Settings is unhashable and identity keys would be tempting."""
    calls = _patch_builders(monkeypatch)

    a = Settings()
    a.MODEL_LABELING = "gemini-2.5-flash"
    b = Settings()
    b.MODEL_LABELING = "gemini-2.5-flash-lite"

    svc_a = await dependencies.get_form_filling_service(a)
    svc_b = await dependencies.get_form_filling_service(b)

    assert calls["text"] == 2, "a differing config must MISS the cache"
    assert svc_a.text_ai != svc_b.text_ai

    # And an identical-config Settings (a distinct object) HITS it -- which is
    # exactly what an id() key would have gotten wrong in the other direction.
    a2 = Settings()
    a2.MODEL_LABELING = "gemini-2.5-flash"
    svc_a2 = await dependencies.get_form_filling_service(a2)
    assert calls["text"] == 2
    assert svc_a2.text_ai is svc_a.text_ai


@pytest.mark.asyncio
async def test_builds_run_concurrently_not_serially(monkeypatch):
    """The actual fix. With each build sleeping 0.3s, SERIAL construction
    takes >= 0.9s; concurrent takes ~0.3s. Asserting well under the serial
    floor pins the gather (a regression to sequential awaits fails here)."""
    _patch_builders(monkeypatch, delay=0.3)
    settings = Settings()

    t0 = time.perf_counter()
    await dependencies.get_form_filling_service(settings)
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.75, (
        "adapters appear to build serially (%.2fs); the ~9.4s handshake block "
        "was exactly this" % elapsed
    )


@pytest.mark.asyncio
async def test_construction_does_not_block_the_event_loop(monkeypatch):
    """Construction must run OFF the loop: it happens before accept(), so a
    blocking build stalls the handshake (and every other connection)."""
    _patch_builders(monkeypatch, delay=0.4)
    settings = Settings()

    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    try:
        await dependencies.get_form_filling_service(settings)
    finally:
        beat.cancel()

    # A loop blocked for the whole build would tick ~0 times.
    assert ticks > 3, "event loop was blocked during adapter construction"


@pytest.mark.asyncio
async def test_cache_is_bounded(monkeypatch):
    """The bound keeps a pathological caller (many distinct configs) from
    growing the cache without limit."""
    _patch_builders(monkeypatch)
    for i in range(dependencies._TEXT_AI_CACHE_MAX * 2):
        s = Settings()
        s.MODEL_LABELING = "model-%d" % i
        await dependencies.get_form_filling_service(s)

    assert len(dependencies._TEXT_AI_CACHE) <= dependencies._TEXT_AI_CACHE_MAX
