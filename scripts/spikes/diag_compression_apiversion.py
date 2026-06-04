"""Diagnostic (bd polyglot-pdf-l3a.1): is context-window compression inert because our
client uses api_version=v1beta instead of v1alpha?

Lead: the google-genai docs say preview Live features require
http_options=HttpOptions(api_version='v1alpha'). Our adapter builds
genai.Client(api_key=...) with NO http_options -> it defaults to v1beta. The compression
config serializes correctly and the connection succeeds, but eviction never happened in
the 45o sweep. Hypothesis: v1beta silently DROPS the contextWindowCompression field.

This probe drives the SAME short audio session under BOTH api versions with compression
ON (low trigger so it must fire), connecting DIRECTLY via google-genai (no adapter, to
isolate the api_version variable), and reads prompt_token_count per turn. If under
v1alpha the prompt token count PLATEAUS / drops toward the window while under v1beta it
keeps compounding, the api_version is the cause -- and the fix is to set v1alpha on the
production client.

Native-audio model -> AUDIO modality, manual activity signals (VAD disabled).
No PII: fictional prompts. Run from repo root with GEMINI_API_KEY:
    backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_apiversion.py \
        --trigger 1500 --window 800 --turns 8
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

import numpy as np  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

MODEL = "gemini-3.1-flash-live-preview"

PROMPTS = [
    "Hi, I'd like to start filling out the form.",
    "My first name is Alex.",
    "My last name is Rivera.",
    "I was born on January second, nineteen ninety.",
    "I currently live in Austin, Texas.",
    "My phone number is five five five, zero one four two.",
    "I am applying to replace a lost card.",
    "I have lived at my current address for three years.",
    "I do not have a middle name.",
    "Can you read back what you have so far?",
]

_AUDIO_IN_RATE = 16000
_CHUNK_MS = 40
_clip_cache: dict[str, bytes] = {}


def _synth_pcm16(text: str) -> bytes:
    if text in _clip_cache:
        return _clip_cache[text]
    from gtts import gTTS
    import soundfile as sf

    buf = io.BytesIO()
    gTTS(text, lang="en").write_to_fp(buf)
    buf.seek(0)
    y, sr = sf.read(buf, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != _AUDIO_IN_RATE:
        n_out = int(len(y) * _AUDIO_IN_RATE / sr)
        y = np.interp(np.linspace(0, len(y), n_out, endpoint=False),
                      np.arange(len(y)), y).astype("float32")
    pcm = (np.clip(y, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    _clip_cache[text] = pcm
    return pcm


def _pcm_chunks(pcm: bytes) -> list[bytes]:
    bpc = int(_AUDIO_IN_RATE * (_CHUNK_MS / 1000.0)) * 2
    return [pcm[i:i + bpc] for i in range(0, len(pcm), bpc)]


async def _run(api_version: str, trigger: int, window: int, n_turns: int) -> list[int]:
    """Drive n_turns of audio with compression on; return prompt_token_count per turn."""
    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        http_options=types.HttpOptions(api_version=api_version),
    )
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction="You are a form-filling assistant. Keep spoken replies very short.",
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
        ),
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=trigger,
            sliding_window=types.SlidingWindow(target_tokens=window),
        ),
    )

    prompts_seen: list[int] = []
    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            for i in range(n_turns):
                pcm = _synth_pcm16(PROMPTS[i % len(PROMPTS)])
                await session.send_realtime_input(activity_start=types.ActivityStart())
                for chunk in _pcm_chunks(pcm):
                    await session.send_realtime_input(
                        audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
                    await asyncio.sleep(_CHUNK_MS / 1000.0)
                await session.send_realtime_input(activity_end=types.ActivityEnd())

                # Drain until this turn's usage_metadata arrives, then move on.
                got = False
                waited = 0.0
                while not got and waited < 45.0:
                    try:
                        evt = await asyncio.wait_for(session.receive().__anext__(), timeout=2.0)
                    except (asyncio.TimeoutError, StopAsyncIteration):
                        waited += 2.0
                        continue
                    um = getattr(evt, "usage_metadata", None)
                    if um is not None:
                        pt = getattr(um, "prompt_token_count", None)
                        if pt:
                            prompts_seen.append(pt)
                            got = True
                if not got:
                    print(f"  [warn] {api_version} turn {i + 1}: no usage in 45s")
    except Exception as e:  # noqa: BLE001
        print(f"  [error] {api_version}: {type(e).__name__}: {str(e)[:120]}")
    return prompts_seen


async def main_async(args: argparse.Namespace) -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set.")
        return 1
    try:
        for p in PROMPTS[: min(args.turns, len(PROMPTS))]:
            _synth_pcm16(p)
    except Exception as e:  # noqa: BLE001
        print(f"Audio synth failed ({type(e).__name__}: {e}).")
        return 1
    print(f"Model={MODEL}, trigger={args.trigger}, window={args.window}, "
          f"turns={args.turns}\nCompression ON for BOTH; only api_version differs.\n")

    beta = await _run("v1beta", args.trigger, args.window, args.turns)
    alpha = await _run("v1alpha", args.trigger, args.window, args.turns)

    print(f"\n{'=' * 60}")
    print(f"  {'turn':>4} {'v1beta prompt':>15} {'v1alpha prompt':>16}")
    for i in range(max(len(beta), len(alpha))):
        b = beta[i] if i < len(beta) else None
        a = alpha[i] if i < len(alpha) else None
        print(f"  {i + 1:>4} {('-' if b is None else f'{b:,}'):>15} "
              f"{('-' if a is None else f'{a:,}'):>16}")

    def grew(seq):
        return (seq[-1] / seq[0]) if seq else 0.0
    print(f"\n  v1beta  prompt growth: {grew(beta):.1f}x "
          f"({beta[0] if beta else '-'} -> {beta[-1] if beta else '-'})")
    print(f"  v1alpha prompt growth: {grew(alpha):.1f}x "
          f"({alpha[0] if alpha else '-'} -> {alpha[-1] if alpha else '-'})")
    print(f"\n  crossed trigger ({args.trigger})? "
          f"v1beta={'yes' if beta and beta[-1] > args.trigger else 'no'}, "
          f"v1alpha={'yes' if alpha and alpha[-1] > args.trigger else 'no'}")
    print("\n  => If v1alpha PLATEAUS while v1beta COMPOUNDS, the api_version is the cause:\n"
          "     our production client must set HttpOptions(api_version='v1alpha').")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Test compression under v1beta vs v1alpha.")
    ap.add_argument("--trigger", type=int, default=1500)
    ap.add_argument("--window", type=int, default=800)
    ap.add_argument("--turns", type=int, default=8)
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
