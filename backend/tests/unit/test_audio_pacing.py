"""Real-time audio-pacing tests (bd polyglot-pdf-3to5).

The audio sender must forward mic audio to Gemini at EXACTLY real-time cadence
(one WS_CHUNK_MS / 640-byte frame per WS_CHUNK_MS of wall clock), never faster --
the too-fast overrun is what trips a Gemini 1011 "sending data too fast". The old
sender forwarded each bursty client frame immediately AND injected un-paced
gap-fill silence, running ~2.2x real-time. The pacer instead runs a fixed-cadence
tick over a byte accumulator that re-chunks variable-size input to 640-byte output
frames, emits silence only on a genuine underrun tick, and drops the OLDEST
buffered audio beyond AUDIO_MAX_BUFFER_MS to bound latency.

These drive LiveAIGemini._audio_sender_loop directly with a fake session and an
INJECTED clock so "exactly N frames over T seconds" is deterministic without
wall-clock flake. The fake clock advances ONLY when the loop awaits _sleep, so the
test controls the passage of (virtual) time precisely.
"""

import asyncio

import pytest

from backend.adapters.live_ai_gemini import LiveAIGemini


class _RecordingSession:
    """Fake Gemini session that records every realtime-input frame's bytes."""

    def __init__(self):
        self.audio_frames = []  # list[bytes] in send order

    async def send_realtime_input(self, **kwargs):
        blob = kwargs.get("audio")
        data = getattr(blob, "data", blob)
        self.audio_frames.append(bytes(data))


class _FakeClock:
    """Virtual monotonic clock. Time advances ONLY when sleep() is awaited, so a
    paced loop's cadence is fully deterministic: each _sleep(dt) moves the clock by
    dt and yields once to let other tasks (the test's producer) run.
    """

    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    async def sleep(self, dt: float) -> None:
        # Advance virtual time, then yield so a concurrent producer coroutine can run.
        self.t += max(0.0, dt)
        await asyncio.sleep(0)


# One 20ms mono PCM16 frame at 16kHz = 16000 * 0.02 * 2 = 640 bytes.
_FRAME_BYTES = 640


def _make_adapter(monkeypatch, *, max_buffer_ms=200, gapfill=True, native_vad=True):
    """Bare adapter with pacing ON + an injected fake clock/sleep.

    _audio_sender_loop reads get_settings() ONCE at entry, so patching the cached
    settings object before the call is sufficient.
    """
    from backend.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "AUDIO_PACING_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUDIO_GAPFILL_ENABLED", gapfill, raising=False)
    monkeypatch.setattr(settings, "AUDIO_MAX_BUFFER_MS", max_buffer_ms, raising=False)
    monkeypatch.setattr(settings, "WS_CHUNK_MS", 20, raising=False)
    monkeypatch.setattr(settings, "AUDIO_IN_RATE", 16000, raising=False)
    monkeypatch.setattr(settings, "DISABLE_GEMINI_VAD", not native_vad, raising=False)

    adapter = LiveAIGemini(api_key="test_key")
    adapter._audio_queue = asyncio.Queue(maxsize=1000)
    # Inject the fake clock so cadence is virtual + deterministic.
    clock = _FakeClock()
    adapter._clock = clock.now
    adapter._sleep = clock.sleep
    return adapter, clock


@pytest.mark.asyncio
async def test_one_second_of_audio_paces_to_exactly_50_frames(monkeypatch):
    """1s of real audio (32000 bytes) -> exactly 50 output frames of 640B.

    This is the core anti-1011 property: however the input is delivered (here one
    burst + sentinel), the OUTPUT is exactly real-time (50 frames of 640 bytes),
    each emitted on its own paced tick.
    """
    # Buffer cap raised so a one-shot preload of the whole second is NOT dropped by
    # the latency bound -- this test isolates the re-chunk + paced-count property.
    # (The drop-oldest cap is exercised separately in the overrun test.)
    adapter, clock = _make_adapter(monkeypatch, max_buffer_ms=100000)
    session = _RecordingSession()

    # 1 second of audio as 125 x 256-byte client frames.
    for _ in range(125):
        adapter._audio_queue.put_nowait(b"\x11\x22" * 128)  # 256 bytes
    adapter._audio_queue.put_nowait(None)

    await asyncio.wait_for(adapter._audio_sender_loop(session), timeout=2.0)

    # 125 * 256 = 32000 bytes = exactly 50 frames of 640 bytes. No silence, no drops.
    assert len(session.audio_frames) == 50
    assert all(len(f) == _FRAME_BYTES for f in session.audio_frames)
    assert adapter._timing_audio_dropped == 0
    # Paced: 50 frames at 20ms each -> ~49 intervals of virtual time elapsed. (The
    # tail drains paced, one frame per tick -- never faster than real-time.)
    assert clock.now() >= 49 * 0.020 - 1e-9


@pytest.mark.asyncio
async def test_variable_frames_rechunked_to_640(monkeypatch):
    """256-byte client frames are re-chunked to 640-byte output frames, in order."""
    adapter, _clock = _make_adapter(monkeypatch)
    session = _RecordingSession()

    # 5 x 256 = 1280 bytes = exactly 2 output frames of 640, distinct content.
    payload = bytes(range(256)) * 5  # 1280 bytes
    for i in range(5):
        adapter._audio_queue.put_nowait(payload[i * 256:(i + 1) * 256])
    adapter._audio_queue.put_nowait(None)

    await asyncio.wait_for(adapter._audio_sender_loop(session), timeout=2.0)

    assert len(session.audio_frames) == 2
    assert all(len(f) == _FRAME_BYTES for f in session.audio_frames)
    # Output is the ordered concatenation of the input.
    assert b"".join(session.audio_frames) == payload


@pytest.mark.asyncio
async def test_overrun_drops_oldest_bounded_latency(monkeypatch):
    """Input far exceeding the buffer cap drops OLDEST frames; latency stays bounded.

    A single instantaneous burst of ~10 frames with a 40ms cap (2 frames) must cap
    the accumulator and drop the oldest whole frames. Delivered as a preload burst
    THEN sentinel: the drop-oldest cap runs on the first tick (before the sentinel
    flush), so total emitted < total input and _timing_audio_dropped is incremented.
    """
    adapter, _clock = _make_adapter(monkeypatch, max_buffer_ms=40)  # cap = 2 frames
    session = _RecordingSession()

    # 10 output-frames' worth (6400 bytes) delivered as one burst, then stop.
    for _ in range(10):
        adapter._audio_queue.put_nowait(b"\x33\x44" * 320)  # 640 bytes
    adapter._audio_queue.put_nowait(None)

    await asyncio.wait_for(adapter._audio_sender_loop(session), timeout=2.0)

    # Some frames were dropped-oldest to honor the cap; we never emit MORE than input.
    assert adapter._timing_audio_dropped > 0
    assert len(session.audio_frames) < 10
    assert len(session.audio_frames) + adapter._timing_audio_dropped <= 10
    assert all(len(f) == _FRAME_BYTES for f in session.audio_frames)


@pytest.mark.asyncio
async def test_no_silence_before_first_real_chunk(monkeypatch):
    """Silence is never manufactured before any real audio has streamed."""
    adapter, clock = _make_adapter(monkeypatch)
    session = _RecordingSession()

    loop_task = asyncio.create_task(adapter._audio_sender_loop(session))
    # Let the loop reach its pre-first-audio blocking get and idle there.
    for _ in range(5):
        await asyncio.sleep(0)
    assert session.audio_frames == [], "no frames before first real chunk"

    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)
    assert session.audio_frames == []


@pytest.mark.asyncio
async def test_underrun_emits_silence_when_gapfill_enabled(monkeypatch):
    """After real audio, an underrun tick emits a 640-byte silence frame."""
    adapter, clock = _make_adapter(monkeypatch, gapfill=True)
    session = _RecordingSession()

    # One real 640-byte frame, then a long stall (no more input, no sentinel yet).
    adapter._audio_queue.put_nowait(b"\x55\x66" * 320)

    loop_task = asyncio.create_task(adapter._audio_sender_loop(session))
    # Yield enough times for several paced ticks to elapse on the virtual clock.
    for _ in range(30):
        await asyncio.sleep(0)
    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)

    assert session.audio_frames[0] == b"\x55\x66" * 320
    silence = session.audio_frames[1:]
    assert len(silence) >= 1, "expected at least one underrun silence frame"
    assert all(f == bytes(_FRAME_BYTES) for f in silence)


@pytest.mark.asyncio
async def test_no_silence_when_gapfill_disabled(monkeypatch):
    """With gap-fill off (or manual VAD), an underrun emits NOTHING -- only real audio."""
    adapter, clock = _make_adapter(monkeypatch, gapfill=False)
    session = _RecordingSession()

    adapter._audio_queue.put_nowait(b"\x0a\x0b" * 320)
    loop_task = asyncio.create_task(adapter._audio_sender_loop(session))
    for _ in range(30):
        await asyncio.sleep(0)
    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)

    assert session.audio_frames == [b"\x0a\x0b" * 320], "no silence when gap-fill disabled"


@pytest.mark.asyncio
async def test_no_silence_in_manual_vad_mode(monkeypatch):
    """Manual VAD (DISABLE_GEMINI_VAD=true) gates underrun silence OFF even if enabled."""
    adapter, clock = _make_adapter(monkeypatch, gapfill=True, native_vad=False)
    session = _RecordingSession()

    adapter._audio_queue.put_nowait(b"\x0c\x0d" * 320)
    loop_task = asyncio.create_task(adapter._audio_sender_loop(session))
    for _ in range(30):
        await asyncio.sleep(0)
    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)

    assert session.audio_frames == [b"\x0c\x0d" * 320], "manual VAD must not emit silence"


@pytest.mark.asyncio
async def test_no_silence_after_shutdown_flag_set(monkeypatch):
    """Once a graceful shutdown begins, an underrun must NOT manufacture silence."""
    adapter, clock = _make_adapter(monkeypatch, gapfill=True)
    session = _RecordingSession()

    adapter._audio_queue.put_nowait(b"\x77\x00" * 320)
    # Shutdown owns the socket + sentinel now.
    adapter._close_after_flush = True
    adapter._intentional_shutdown = True

    loop_task = asyncio.create_task(adapter._audio_sender_loop(session))
    for _ in range(30):
        await asyncio.sleep(0)
    frames_during = list(session.audio_frames)
    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)

    assert frames_during == [b"\x77\x00" * 320], "no gap-fill silence after shutdown flag set"
    assert session.audio_frames == [b"\x77\x00" * 320]


@pytest.mark.asyncio
async def test_never_sends_faster_than_realtime(monkeypatch):
    """The pacer never advances the virtual clock LESS than one interval per frame.

    A burst of 10 frames + sentinel must still take >= ~9 intervals of virtual time
    to drain -- even the graceful-stop tail is paced one frame per tick, so the
    output cadence is real-time. This is the whole anti-1011 point.
    """
    adapter, clock = _make_adapter(monkeypatch, max_buffer_ms=100000)  # no drops
    session = _RecordingSession()

    for _ in range(10):
        adapter._audio_queue.put_nowait(b"\x01\x02" * 320)  # 640 bytes each
    adapter._audio_queue.put_nowait(None)

    await asyncio.wait_for(adapter._audio_sender_loop(session), timeout=2.0)

    assert len(session.audio_frames) == 10
    # 10 frames paced at 20ms each -> at least ~9 intervals of virtual time elapsed.
    assert clock.now() >= 9 * 0.020 - 1e-9


# ---------------------------------------------------------------------------
# Handshake readiness gate (bd polyglot-pdf-3to5, Part 2): stream_audio must DROP
# audio that arrives before the Gemini session is ready, so no consumerless backlog
# forms in the queue (which would burst on drain -> 1011).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_audio_drops_pre_ready_frames():
    """Before _session_ready, stream_audio drops audio + counts it, never enqueues."""
    adapter = LiveAIGemini(api_key="test_key")
    adapter._audio_queue = asyncio.Queue(maxsize=100)
    adapter._session_ready = False

    await adapter.stream_audio(b"\x11\x22" * 128)
    await adapter.stream_audio(b"\x33\x44" * 128)

    assert adapter._audio_queue.qsize() == 0, "pre-ready audio must NOT be enqueued"
    assert adapter._pre_ready_dropped == 2


@pytest.mark.asyncio
async def test_stream_audio_enqueues_once_ready():
    """Once _session_ready, stream_audio enqueues normally (no pre-ready drop)."""
    adapter = LiveAIGemini(api_key="test_key")
    adapter._audio_queue = asyncio.Queue(maxsize=100)
    adapter._session_ready = True

    await adapter.stream_audio(b"\x55\x66" * 128)

    assert adapter._audio_queue.qsize() == 1
    assert adapter._pre_ready_dropped == 0
