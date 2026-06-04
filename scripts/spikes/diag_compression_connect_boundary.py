"""Diagnostic (bd polyglot-pdf-l3a.1): find the (trigger, window) values the Live API
ACCEPTS vs. REJECTS at connect.

The tiny-window run (trigger=200/window=100) failed with 1007 "Request contains an
invalid argument" on the first frame -- the API REJECTED the compression config. But
triggers 2000/5000 connected fine (they just didn't evict). So the API validates the
config; there's a minimum. This probe connects with several (trigger, window) configs
and reports ACCEPT/REJECT for each, WITHOUT driving full audio turns -- so it's cheap
(a connect handshake, no billed turns).

It connects directly via google-genai (no adapter), sends ONE tiny audio frame +
activity_end to provoke the server to validate + respond, and watches for either a
usage/serverContent event (ACCEPT) or a 1007 close (REJECT). Native-audio model, so
AUDIO modality (TEXT is rejected with a DIFFERENT 1007 -- modality, not argument).

Run: backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_connect_boundary.py
"""

from __future__ import annotations

import asyncio
import io
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

import os  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

MODEL = "gemini-3.1-flash-live-preview"

# (trigger, window) points to probe. None = no compression (control: must ACCEPT).
CONFIGS = [
    (None, None),     # control
    (200, 100),       # the rejected tiny case
    (500, 250),
    (1000, 500),
    (2000, 1000),     # known-accepted region (the sweep used this)
    (4096, 2048),
]


def _one_frame_pcm() -> bytes:
    # 200ms of quiet 16k PCM16 -- enough to be a valid audio frame.
    n = int(16000 * 0.2)
    return (np.zeros(n, dtype="<i2")).tobytes()


async def _probe(trigger, window) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    cfg_kwargs = {
        "response_modalities": ["AUDIO"],
        # VAD off + only {disabled:True} to dodge the p1t 1007 (a DIFFERENT 1007).
        "realtime_input_config": types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
        ),
    }
    if trigger is not None:
        cfg_kwargs["context_window_compression"] = types.ContextWindowCompressionConfig(
            trigger_tokens=trigger,
            sliding_window=types.SlidingWindow(target_tokens=window),
        )
    config = types.LiveConnectConfig(**cfg_kwargs)

    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            # Send one frame + activity end to force the server to validate and respond.
            await session.send_realtime_input(activity_start=types.ActivityStart())
            await session.send_realtime_input(
                audio=types.Blob(data=_one_frame_pcm(), mime_type="audio/pcm;rate=16000"))
            await session.send_realtime_input(activity_end=types.ActivityEnd())
            # Wait briefly for ANY event (accept) or a close (reject).
            try:
                async for _evt in session.receive():
                    return "ACCEPT"  # got a server event => config accepted
            except Exception as e:
                msg = str(e)
                if "1007" in msg or "invalid argument" in msg.lower():
                    return f"REJECT (1007: {msg[:80]})"
                return f"ERROR ({type(e).__name__}: {msg[:80]})"
            return "ACCEPT (no event, clean close)"
    except Exception as e:
        msg = str(e)
        if "1007" in msg or "invalid argument" in msg.lower():
            return f"REJECT (1007: {msg[:80]})"
        return f"ERROR ({type(e).__name__}: {msg[:80]})"


async def main_async() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set.")
        return 1
    print(f"Model: {MODEL}")
    print(f"  {'trigger':>8} {'window':>8}   result")
    for trigger, window in CONFIGS:
        result = await _probe(trigger, window)
        t = "-" if trigger is None else str(trigger)
        w = "-" if window is None else str(window)
        print(f"  {t:>8} {w:>8}   {result}")
        await asyncio.sleep(1.0)
    print("\nReading: the smallest trigger that ACCEPTs marks the API's minimum. "
          "If even\n2000/4096 ACCEPT but the earlier sweep showed no eviction, the floor "
          "is below our\nreal context peak -- so eviction-not-firing is NOT about the trigger value.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
