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

Run (Vertex is the DEFAULT -- maintainer directive 2026-07-12: all live-model
work runs on Vertex so costs land on the tracked billing project; ADC +
GOOGLE_CLOUD_PROJECT, e.g. via `gcloud auth application-default login`):
    GOOGLE_CLOUD_PROJECT=... backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_connect_boundary.py
    # deliberate AI Studio run (billing NOT on the tracked project):
    VERTEXAI=false GEMINI_API_KEY=... backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_connect_boundary.py

Converted to Vertex-default for bd polyglot-pdf-rve5; one-shot diagnostic, NOT
re-verified against live Vertex post-conversion. NOTE: this is a Live-API
(bidiGenerateContent) script -- the Vertex model-id variant may need adjustment
per bd a079.
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


def _client() -> genai.Client:
    """Vertex by DEFAULT (maintainer directive 2026-07-12: all live-model work
    runs on Vertex so costs land on the tracked billing project). Mirrors the
    production adapter's construction (backend/adapters/text_ai_gemini.py):
    VERTEXAI=true (default) -> ADC + GOOGLE_CLOUD_PROJECT; set VERTEXAI=false
    with GEMINI_API_KEY only for a deliberate AI Studio run.
    """
    if os.environ.get("VERTEXAI", "true").lower() == "true":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            print(
                "VERTEXAI mode but GOOGLE_CLOUD_PROJECT unset; relying on ADC's "
                "default project (gcloud config get-value project).",
                flush=True,
            )
        return genai.Client(
            vertexai=True,
            project=project,
            location=os.environ.get("VERTEX_LOCATION", "us-central1"),
        )
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("VERTEXAI=false but NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key)


async def _probe(trigger, window) -> str:
    client = _client()
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
    if os.environ.get("VERTEXAI", "true").lower() != "true" \
            and not os.getenv("GEMINI_API_KEY"):
        print("VERTEXAI=false but GEMINI_API_KEY not set.")
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
