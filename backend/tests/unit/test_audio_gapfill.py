"""Backend audio-cadence gap-filling tests (bd polyglot-pdf-7f7m).

The audio sender must keep a steady PCM cadence to Gemini even when the client
stutters: on a gap (no real chunk within AUDIO_GAPFILL_INTERVAL_MS) it sends one
synthetic silence frame, so the wire cadence never breaks and Gemini's keepalive
is not starved into a 1011. Silence must NEVER fire before the first real chunk
or once a graceful shutdown has begun; the None sentinel always exits cleanly.

These drive LiveAIGemini._audio_sender_loop directly with a fake session and a
short gap-fill interval, so no real network / Gemini is involved.
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
        # types.Blob exposes .data; be tolerant of a raw-bytes fake too.
        data = getattr(blob, "data", blob)
        self.audio_frames.append(bytes(data))


def _make_adapter(monkeypatch, *, enabled=True, interval_ms=20):
    """Build a bare adapter with gap-fill config forced to test values.

    _audio_sender_loop reads get_settings() ONCE at entry, so patching the
    cached settings object's attributes before the call is sufficient.
    NOTE: gap-fill is now permanently OFF in production (bd polyglot-pdf-v1m8g
    pins _gapfill_enabled=False). These tests still drive the sender plumbing so
    it stays covered until that plumbing is removed (bd polyglot-pdf-ggdpn).
    """
    from backend.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "AUDIO_GAPFILL_ENABLED", enabled, raising=False)
    monkeypatch.setattr(settings, "AUDIO_GAPFILL_INTERVAL_MS", interval_ms, raising=False)
    monkeypatch.setattr(settings, "WS_CHUNK_MS", 20, raising=False)
    monkeypatch.setattr(settings, "AUDIO_IN_RATE", 16000, raising=False)
    # These tests pin the LEGACY (un-paced) gap-fill path (bd polyglot-pdf-7f7m):
    # verbatim pass-through + wall-clock stall -> silence. The real-time pacer (bd
    # polyglot-pdf-3to5) re-chunks + clocks output, so it is covered separately in
    # test_audio_pacing.py; force pacing OFF here so this file keeps exercising the
    # preserved rollback path (AUDIO_PACING_ENABLED=false).
    monkeypatch.setattr(settings, "AUDIO_PACING_ENABLED", False, raising=False)

    adapter = LiveAIGemini(api_key="test_key")
    adapter._audio_queue = asyncio.Queue(maxsize=100)
    return adapter


# One 20ms mono PCM16 frame at 16kHz = 16000 * 0.02 * 2 = 640 bytes.
_SILENCE_LEN = 640


@pytest.mark.asyncio
async def test_real_chunks_pass_through_then_sentinel_exits(monkeypatch):
    """Real chunks are forwarded verbatim; a None sentinel exits the loop."""
    adapter = _make_adapter(monkeypatch, enabled=True)
    session = _RecordingSession()

    real_a = b"\x11\x22" * 320  # 640-byte non-silent frame
    real_b = b"\x33\x44" * 320
    adapter._audio_queue.put_nowait(real_a)
    adapter._audio_queue.put_nowait(real_b)
    adapter._audio_queue.put_nowait(None)

    await asyncio.wait_for(adapter._audio_sender_loop(session), timeout=2.0)

    assert session.audio_frames == [real_a, real_b]


@pytest.mark.asyncio
async def test_gap_produces_silence_frame_while_streaming(monkeypatch):
    """After real audio, a stall longer than the interval yields silence frames.

    Drives _run_legacy_sender DIRECTLY with gapfill_enabled=True. The production
    path can no longer reach this branch -- _audio_sender_loop pins
    _gapfill_enabled=False (bd polyglot-pdf-v1m8g) -- but the machinery is still
    present, and it stays covered until it is removed (bd polyglot-pdf-ggdpn).
    Going through _audio_sender_loop here would test the pin, not the mechanism;
    that is what the sibling `..._even_when_the_setting_is_on` test does.
    """
    adapter = _make_adapter(monkeypatch, enabled=True, interval_ms=20)
    session = _RecordingSession()

    real = b"\x55\x66" * 320
    adapter._audio_queue.put_nowait(real)

    async def _send_frame(data: bytes, *, is_silence: bool):
        session.audio_frames.append(bytes(data))

    loop_task = asyncio.create_task(adapter._run_legacy_sender(
        _send_frame,
        silence_frame=bytes(_SILENCE_LEN),
        gapfill_enabled=True,
        gapfill_timeout_s=0.02,
    ))
    # Let the loop send the real frame, then STALL (no puts) across several
    # gap-fill intervals so silence frames accumulate.
    await asyncio.sleep(0.12)  # ~6 intervals of 20ms
    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)

    # First frame is the real one; the rest are all-zero silence frames.
    assert session.audio_frames[0] == real
    silence = session.audio_frames[1:]
    assert len(silence) >= 2, "expected multiple gap-fill frames during a long stall"
    for frame in silence:
        assert frame == bytes(_SILENCE_LEN), "gap-fill frame must be all-zero PCM16"


@pytest.mark.asyncio
async def test_no_silence_before_first_real_chunk(monkeypatch):
    """Silence must NOT be manufactured before any real audio has streamed."""
    adapter = _make_adapter(monkeypatch, enabled=True, interval_ms=20)
    session = _RecordingSession()

    loop_task = asyncio.create_task(adapter._audio_sender_loop(session))
    # Idle well past several intervals with an EMPTY queue and no real audio yet.
    await asyncio.sleep(0.12)
    assert session.audio_frames == [], "no frames should be sent before first real chunk"

    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)
    assert session.audio_frames == []


@pytest.mark.asyncio
async def test_no_silence_after_shutdown_flag_set(monkeypatch):
    """Once a graceful shutdown begins, a gap must NOT manufacture silence."""
    adapter = _make_adapter(monkeypatch, enabled=True, interval_ms=20)
    session = _RecordingSession()

    real = b"\x77\x00" * 320
    adapter._audio_queue.put_nowait(real)

    # Begin graceful shutdown BEFORE any stall can gap-fill, so we isolate the
    # post-flag behavior: the drain path owns the socket + sentinel now.
    adapter._close_after_flush = True
    adapter._intentional_shutdown = True

    loop_task = asyncio.create_task(adapter._audio_sender_loop(session))
    await asyncio.sleep(0.12)  # a long stall that WOULD gap-fill if the flag were off

    # No silence injected once shutdown is in progress -- only the real frame.
    frames_during_shutdown = list(session.audio_frames)
    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)

    assert frames_during_shutdown == [real], "no gap-fill silence after shutdown flag set"
    assert session.audio_frames == [real]


@pytest.mark.asyncio
async def test_gapfill_disabled_blocks_without_silence(monkeypatch):
    """With gap-fill disabled, a stall produces NO silence (legacy behavior)."""
    adapter = _make_adapter(monkeypatch, enabled=False, interval_ms=20)
    session = _RecordingSession()

    real = b"\x0a\x0b" * 320
    adapter._audio_queue.put_nowait(real)

    loop_task = asyncio.create_task(adapter._audio_sender_loop(session))
    await asyncio.sleep(0.12)  # long stall
    assert session.audio_frames == [real], "disabled gap-fill must not emit silence"

    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)
    assert session.audio_frames == [real]


@pytest.mark.asyncio
async def test_gapfill_off_even_when_the_setting_is_on(monkeypatch):
    """Gap-fill NEVER emits, even with AUDIO_GAPFILL_ENABLED=true.

    It was a native-VAD keepalive: it manufactured a continuous stream so Gemini's
    own detector was not starved of trailing audio. Under push-to-talk (the only
    input mode since bd polyglot-pdf-v1m8g) audio must stay INSIDE the
    activity_start/end brackets, so injecting silence between turns would send
    un-bracketed audio and desync the turn state.

    The production pin is `_gapfill_enabled = False`, deliberately not read from
    the setting -- so this passes the setting as ENABLED to prove the pin, not the
    setting, is what stops it.
    """
    adapter = _make_adapter(monkeypatch, enabled=True, interval_ms=20)
    session = _RecordingSession()

    real = b"\x0c\x0d" * 320
    adapter._audio_queue.put_nowait(real)

    loop_task = asyncio.create_task(adapter._audio_sender_loop(session))
    await asyncio.sleep(0.12)  # long stall that WOULD gap-fill under native VAD
    assert session.audio_frames == [real], "gap-fill must never emit silence"

    adapter._audio_queue.put_nowait(None)
    await asyncio.wait_for(loop_task, timeout=2.0)
    assert session.audio_frames == [real]
