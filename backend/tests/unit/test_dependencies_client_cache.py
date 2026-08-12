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
import threading
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


@pytest.mark.asyncio
async def test_concurrent_cache_misses_for_the_same_key_build_exactly_once(
    monkeypatch,
):
    """bd polyglot-pdf-oqqxj / polyglot-pdf-ioe8d: two /ws/fill connections
    racing in on a cold cache must not both pay the ~3s build cost for the
    SAME config. Without the lock, both worker threads pass the
    "key not in cache" check before either writes, and the second build's
    result silently discards the first."""
    calls = {"text": 0}

    def slow_build(settings):
        calls["text"] += 1
        import time as _time

        _time.sleep(0.05)
        return object()

    monkeypatch.setattr(dependencies, "get_text_ai", slow_build)

    settings = Settings()

    results = await asyncio.gather(
        *[
            asyncio.to_thread(dependencies._cached_text_ai, settings)
            for _ in range(8)
        ]
    )

    assert calls["text"] == 1, (
        "concurrent cache misses for the same key built %d times; "
        "expected exactly 1 (the lock should serialize the build)" % calls["text"]
    )
    assert len({id(r) for r in results}) == 1, "every caller must get the SAME client"


def test_concurrent_same_key_hammering_under_forced_eviction_never_raises(
    monkeypatch,
):
    """bd polyglot-pdf-oqqxj / polyglot-pdf-ioe8d, round 2 (Opus cross-surface
    review): an EARLIER single-critical-section fix released the lock between
    the miss-path build/write and the final read-back (in one variant) or
    held the lock across the ENTIRE build() call (in the corrected variant --
    see the round-3 note below). Both of those shapes were tried; this test
    pins the current (round 3) per-key IN-PROGRESS PLACEHOLDER design: many
    threads hammering the SAME key while _TEXT_AI_CACHE_MAX=1 forces constant
    eviction (every miss clears the whole cache first). No caller's read may
    ever raise KeyError or observe a torn value, regardless of interleaving.
    """
    monkeypatch.setattr(dependencies, "_TEXT_AI_CACHE_MAX", 1)

    def fast_build(settings):
        return object()

    monkeypatch.setattr(dependencies, "get_text_ai", fast_build)

    target = Settings()
    target.MODEL_LABELING = "the-target"

    def hammer():
        return dependencies._cached_text_ai(target)

    results = []
    errors = []

    def worker():
        try:
            results.append(hammer())
        except BaseException as exc:  # noqa: BLE001 - want every exception type
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, "concurrent same-key hammering raised: %r" % (errors,)
    assert len(results) == 24


def test_concurrent_different_keys_do_not_serialize_on_each_others_builds(
    monkeypatch,
):
    """bd polyglot-pdf-oqqxj round 2 (Opus cross-surface review): a version
    of the fix that held _TEXT_AI_CACHE_LOCK across the build() call itself
    correctly closed the KeyError race, but SERIALIZED unrelated keys --
    _cached_text_ai and _cached_text_ai_pro are DIFFERENT keys built
    concurrently by get_form_filling_service (asyncio.gather'd
    asyncio.to_thread calls), so a cold instance paid their ~3s builds
    SERIALLY instead of concurrently, eating back part of the 9.4s->3.2s
    latency win bd polyglot-pdf-4hnyq exists to protect (measured directly:
    ~0.85s vs ~0.49s with 0.3s fake builders. holding the lock over build()
    reintroduces exactly this).

    Pin: two DISTINCT keys, each with a 0.3s builder, built concurrently via
    asyncio.to_thread (matching get_form_filling_service's real call shape),
    must complete in well under the SERIAL floor (0.6s) -- proving builds for
    different keys never wait on each other's lock hold."""
    monkeypatch.setattr(dependencies, "_TEXT_AI_CACHE_MAX", 8)

    def slow_build(settings):
        time.sleep(0.3)
        return object()

    monkeypatch.setattr(dependencies, "get_text_ai", slow_build)
    monkeypatch.setattr(dependencies, "get_text_ai_pro", slow_build)

    a = Settings()
    a.MODEL_LABELING = "key-a"
    b = Settings()
    b.MODEL_LABELING = "key-a"  # same MODEL_LABELING, different KIND below
    b.FORM_COMPLETE_PRO_VALIDATOR = True

    async def run():
        t0 = time.perf_counter()
        await asyncio.gather(
            asyncio.to_thread(dependencies._cached_text_ai, a),
            asyncio.to_thread(dependencies._cached_text_ai_pro, b),
        )
        return time.perf_counter() - t0

    elapsed = asyncio.run(run())
    assert elapsed < 0.5, (
        "two DIFFERENT cache keys took %.2fs to build concurrently; expected "
        "well under the 0.6s serial floor (builds for different keys must "
        "never wait on each other's lock hold)" % elapsed
    )


def test_a_cross_key_eviction_does_not_orphan_an_in_flight_same_key_build(
    monkeypatch,
):
    """bd polyglot-pdf-oqqxj, round 3 (fresh-eyes gap): a DIFFERENT key's
    eviction (.clear() on overflow) used to wipe an IN-PROGRESS placeholder
    for a key whose build was still running -- so a THIRD caller for that
    same (still-building) key saw _MISSING and started a duplicate build,
    exactly the pathology this cache exists to prevent, just reopened
    through cross-key eviction instead of the original no-lock-at-all path.

    Deterministic reproduction: hold key A's build in flight (blocked on a
    threading.Event the test controls), then build key B with
    _TEXT_AI_CACHE_MAX=1 (forces overflow eviction), then start a SECOND
    caller for key A while the first A-build is still blocked. Only after
    that must the first A-build be allowed to finish. Assert A's build
    function was invoked exactly once."""
    monkeypatch.setattr(dependencies, "_TEXT_AI_CACHE_MAX", 1)

    calls = {"a": 0}
    a_build_may_finish = threading.Event()
    a_build_started = threading.Event()

    def build_a(settings):
        calls["a"] += 1
        a_build_started.set()
        a_build_may_finish.wait(timeout=5)
        return object()

    def build_b(settings):
        return object()

    a = Settings()
    a.MODEL_LABELING = "key-a"
    b = Settings()
    b.MODEL_LABELING = "key-b"

    results = {}
    errors = []

    def first_a_caller():
        try:
            results["first"] = dependencies._cache_get_or_build("text_ai", a, build_a)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t_first_a = threading.Thread(target=first_a_caller)
    t_first_a.start()
    assert a_build_started.wait(timeout=5), "key A's build never started"

    # While A's build is still in flight, force an eviction via a DIFFERENT
    # key (B) overflowing the MAX=1 cache.
    dependencies._cache_get_or_build("text_ai", b, build_b)

    # Now a SECOND caller for key A arrives while the FIRST A-build is still
    # running. Before the fix, A's in-flight placeholder would have been
    # wiped by B's eviction above, so this second caller would see _MISSING
    # and start a duplicate build.
    def second_a_caller():
        try:
            results["second"] = dependencies._cache_get_or_build("text_ai", a, build_a)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t_second_a = threading.Thread(target=second_a_caller)
    t_second_a.start()

    # Let the (single, if the fix holds) A build complete.
    a_build_may_finish.set()
    t_first_a.join(timeout=5)
    t_second_a.join(timeout=5)

    assert not errors, "unexpected exception: %r" % (errors,)
    assert calls["a"] == 1, (
        "key A's build ran %d times; expected exactly 1 -- a cross-key "
        "eviction must never orphan an in-flight same-key build" % calls["a"]
    )
    assert results["first"] is results["second"], "both callers must get the SAME client"


@pytest.mark.asyncio
async def test_concurrent_eviction_does_not_raise_keyerror_on_the_hit_path(
    monkeypatch,
):
    """bd polyglot-pdf-oqqxj / polyglot-pdf-ioe8d: a thread on the HIT path
    (key already present) must not raise KeyError if another thread's
    eviction .clear() lands between the presence check and the read. Forces
    eviction every call by dropping _TEXT_AI_CACHE_MAX to 1 with many
    distinct configs racing concurrently."""
    monkeypatch.setattr(dependencies, "_TEXT_AI_CACHE_MAX", 1)

    def fast_build(settings):
        return object()

    monkeypatch.setattr(dependencies, "get_text_ai", fast_build)

    settings_list = []
    for i in range(16):
        s = Settings()
        s.MODEL_LABELING = "model-%d" % i
        settings_list.append(s)

    # Fire many distinct keys concurrently so eviction (.clear()) is racing
    # against other threads' hit-path reads of _TEXT_AI_CACHE[key].
    results = await asyncio.gather(
        *[
            asyncio.to_thread(dependencies._cached_text_ai, s)
            for s in settings_list * 4
        ],
        return_exceptions=True,
    )

    errors = [r for r in results if isinstance(r, BaseException)]
    assert not errors, "concurrent eviction raised: %r" % (errors,)
