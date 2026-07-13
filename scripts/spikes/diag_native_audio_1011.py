"""Diagnostic (bd polyglot-pdf-daa): measure the code=1011 mid-turn failure rate on the
native-audio Live models, to determine whether polyglot-pdf is affected.

Background: a Google AI Developers Forum report (2026-05-27) said
gemini-2.5-flash-native-audio-preview-12-2025 returns code=1011 ("internal error")
mid-turn at ~80%. Our DEFAULT is now gemini-3.1-flash-live-preview (USE_PREMIUM_MODEL=true);
the 2.5 preview is the opt-in standard tier. So we measure BOTH: confirm the default (3.1)
is clean, and measure the 2.5 preview's actual mid-turn 1011 rate over a sustained run.

Connects DIRECTLY via google-genai (no adapter, to isolate the model), drives N audio
turns per model, and counts: clean turns, mid-turn 1011s, and other close codes. A turn
that bills usage_metadata = clean; a ConnectionClosed with code 1011 during a turn = a hit.

Native-audio -> AUDIO modality + manual activity signals (VAD disabled). No PII (fictional
prompts). Run from repo root (Vertex is the DEFAULT -- maintainer directive
2026-07-12: all live-model work runs on Vertex so costs land on the tracked
billing project; ADC + GOOGLE_CLOUD_PROJECT, e.g. via
`gcloud auth application-default login`):
    GOOGLE_CLOUD_PROJECT=... backend/.venv/Scripts/python.exe scripts/spikes/diag_native_audio_1011.py --turns 15
    # deliberate AI Studio run (billing NOT on the tracked project):
    VERTEXAI=false GEMINI_API_KEY=... backend/.venv/Scripts/python.exe scripts/spikes/diag_native_audio_1011.py --turns 15

Converted to Vertex-default for bd polyglot-pdf-rve5; one-shot diagnostic, NOT
re-verified against live Vertex post-conversion. NOTE: this is a Live-API
(bidiGenerateContent) script -- the Vertex model-id variant may need adjustment
per bd a079.
"""

from __future__ import annotations

import argparse
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
from google.genai import errors as genai_errors  # noqa: E402
from google.genai import types  # noqa: E402
from websockets.exceptions import ConnectionClosed  # noqa: E402

# google-genai >= 2.x converts websocket closures inside receive() into
# errors.APIError (code = the WS close code); sends still raise raw
# ConnectionClosed. Catch both so the 1011 counting survives the cutover
# (bd polyglot-pdf-x52p).
_CLOSE_ERRORS = (ConnectionClosed, genai_errors.APIError)

# Both native-audio models reachable on our key. The 3.1 is our default; the 2.5 preview
# is the one the forum report implicates.
MODELS = [
    "gemini-3.1-flash-live-preview",                       # default (USE_PREMIUM_MODEL=true)
    "gemini-2.5-flash-native-audio-preview-12-2025",       # opt-in standard tier; the suspect
]

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

_RATE = 16000
_CHUNK_MS = 40
_clip_cache: dict[str, bytes] = {}


def _synth(text: str) -> bytes:
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
    if sr != _RATE:
        n = int(len(y) * _RATE / sr)
        y = np.interp(np.linspace(0, len(y), n, endpoint=False), np.arange(len(y)), y).astype("float32")
    pcm = (np.clip(y, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    _clip_cache[text] = pcm
    return pcm


def _chunks(pcm: bytes) -> list[bytes]:
    n = int(_RATE * (_CHUNK_MS / 1000.0)) * 2
    return [pcm[i:i + n] for i in range(0, len(pcm), n)]


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


async def _measure(model: str, n_turns: int) -> dict:
    client = _client()
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction="You are a form-filling assistant. Keep spoken replies very short.",
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
        ),
    )
    result = {"model": model, "turns_attempted": 0, "clean": 0, "code_1011": 0,
              "other_close": 0, "connect_failed": None, "first_failure_turn": None}
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            for i in range(n_turns):
                result["turns_attempted"] += 1
                pcm = _synth(PROMPTS[i % len(PROMPTS)])
                try:
                    await session.send_realtime_input(activity_start=types.ActivityStart())
                    for ch in _chunks(pcm):
                        await session.send_realtime_input(
                            audio=types.Blob(data=ch, mime_type="audio/pcm;rate=16000"))
                        await asyncio.sleep(_CHUNK_MS / 1000.0)
                    await session.send_realtime_input(activity_end=types.ActivityEnd())

                    billed = False
                    waited = 0.0
                    while waited < 30.0:
                        try:
                            evt = await asyncio.wait_for(session.receive().__anext__(), timeout=2.0)
                        except asyncio.TimeoutError:
                            waited += 2.0
                            continue
                        except StopAsyncIteration:
                            break
                        if getattr(evt, "usage_metadata", None) is not None:
                            billed = True
                            break
                    if billed:
                        result["clean"] += 1
                    print(f"    turn {i + 1:>2}: {'clean' if billed else 'no-bill'}")
                except _CLOSE_ERRORS as exc:
                    code = getattr(exc, "code", None) or getattr(getattr(exc, "rcvd", None), "code", None)
                    if code == 1011:
                        result["code_1011"] += 1
                    else:
                        result["other_close"] += 1
                    if result["first_failure_turn"] is None:
                        result["first_failure_turn"] = i + 1
                    print(f"    turn {i + 1:>2}: CLOSED code={code} -- {str(exc)[:70]}")
                    break  # connection is gone; can't continue this session
    except _CLOSE_ERRORS as exc:
        code = getattr(exc, "code", None)
        result["connect_failed"] = f"code={code}: {str(exc)[:80]}"
    except Exception as exc:  # noqa: BLE001
        result["connect_failed"] = f"{type(exc).__name__}: {str(exc)[:80]}"
    return result


async def main_async(args: argparse.Namespace) -> int:
    if os.environ.get("VERTEXAI", "true").lower() != "true" and not os.getenv("GEMINI_API_KEY"):
        print("VERTEXAI=false but GEMINI_API_KEY not set.")
        return 1
    try:
        for p in PROMPTS[: min(args.turns, len(PROMPTS))]:
            _synth(p)
    except Exception as e:  # noqa: BLE001
        print(f"Audio synth failed ({type(e).__name__}: {e}).")
        return 1

    results = []
    for model in MODELS:
        print(f"\n=== {model} ({args.turns} turns) ===")
        results.append(await _measure(model, args.turns))

    print(f"\n{'=' * 70}\nSUMMARY -- code=1011 mid-turn failure rate\n{'=' * 70}")
    print(f"  {'model':<48} {'clean':>6} {'1011':>5} {'other':>6}")
    for r in results:
        if r["connect_failed"]:
            print(f"  {r['model']:<48} CONNECT FAILED: {r['connect_failed']}")
            continue
        att = r["turns_attempted"] or 1
        rate = 100.0 * r["code_1011"] / att
        print(f"  {r['model']:<48} {r['clean']:>6} {r['code_1011']:>5} {r['other_close']:>6}"
              f"   (1011 rate {rate:.0f}%"
              + (f", first fail turn {r['first_failure_turn']}" if r['first_failure_turn'] else "")
              + ")")
    print("\nReading: the ~80% forum report was for the 2.5 preview. If 2.5 shows a high "
          "1011\nrate here -> we'd be affected ONLY on the opt-in standard tier (default is "
          "3.1).\nIf both are clean -> not affected; the upstream issue appears resolved.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure native-audio code=1011 mid-turn failure rate.")
    ap.add_argument("--turns", type=int, default=15, help="audio turns per model")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
