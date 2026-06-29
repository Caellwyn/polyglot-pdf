"""Diagnostic (bd polyglot-pdf-fa4x): does input_transcription fire on the 2.5
native-audio model under the PRODUCTION config (native VAD, START=HIGH)?

fa4x context: the thinking indicator's native-VAD START signal rides
on_user_activity, which fires only on a non-empty server_content.input_transcription.
Two live wpw.5 real-mic tests reported 0 input_transcription events in native mode
(under the OLD START=LOW config). The 4sv7 A/B measured turn REGISTRATION at
START=HIGH as 20/20, but it counted ANY signal (model_turn / audio / turn_complete /
tool_call / input_transcription) -- so it did NOT isolate whether input_transcription
SPECIFICALLY fires. Option 1 of fa4x (cheapest: reuse the existing on_user_activity
trigger with zero new heuristic) lives or dies on that one fact.

This probe drives the committed audio fixtures through the EXACT production config
shape (response AUDIO, complete TOOL_DECLARATIONS per the bd daa 1011 scar,
input_audio_transcription={}, native VAD at START=HIGH, continuous trailing silence)
and records, per turn, whether a NON-EMPTY input_transcription arrived -- and at what
latency relative to the model's other first signals.

Usage (AI Studio, the creds available locally):
    GEMINI_API_KEY=... python scripts/spikes/diag_input_transcription_fa4x.py --turns 6

Vertex (matches the deployed backend id) if ADC is configured:
    GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=... GOOGLE_CLOUD_LOCATION=us-central1 \
        python scripts/spikes/diag_input_transcription_fa4x.py --turns 6 --vertex

It prints a per-turn table and a final verdict line:
  INPUT_TRANSCRIPTION_FIRES=YES/NO  (and the firing rate).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import numpy as np  # noqa: F401  (kept for parity w/ sibling spikes; sf needs it)
import soundfile as sf

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from google import genai  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402
from google.genai import types  # noqa: E402
from websockets.exceptions import ConnectionClosed  # noqa: E402

from backend.config import get_settings  # noqa: E402

TOOL_DECLARATIONS = get_settings().TOOL_DECLARATIONS
_CLOSE_ERRORS = (ConnectionClosed, genai_errors.APIError)

# AI Studio id; the Vertex deployed id is gemini-live-2.5-flash-native-audio
# (same 2.5 native-audio family). --vertex swaps to it.
MODEL_AISTUDIO = "gemini-2.5-flash-native-audio-preview-12-2025"
MODEL_VERTEX = "gemini-live-2.5-flash-native-audio"

FIXTURE_DIR = _REPO_ROOT / "frontend" / "public" / "test-fixtures"
FIXTURES = ["confirm_yes.wav", "digits_1234567.wav", "confirm_yes.wav",
            "digits_12345.wav"]

_RATE = 16000
_CHUNK_MS = 20
_TURN_TIMEOUT_S = 20.0

# Same shape as the 4sv7 probe SI: a real tool-soliciting instruction so the
# native-audio path is exercised the way the app exercises it.
SYSTEM_INSTRUCTION = (
    "You are a voice form-filling assistant for Form I-90. Ask for the user's "
    "A-Number, then ZIP code. When the user gives a value, call "
    "update_form_fields. When the user confirms, call confirm_field for "
    "p1_line1_aliennumber. Keep all spoken replies under one short sentence."
)


def _load_pcm(name: str) -> bytes:
    data, sr = sf.read(FIXTURE_DIR / name, dtype="int16")
    assert sr == _RATE, f"{name}: expected {_RATE} Hz, got {sr}"
    if data.ndim > 1:
        data = data.mean(axis=1).astype("int16")
    return data.tobytes()


def _chunks(pcm: bytes) -> list[bytes]:
    n = int(_RATE * (_CHUNK_MS / 1000.0)) * 2
    return [pcm[i:i + n] for i in range(0, len(pcm), n)]


def _connect_config() -> dict:
    # Production native-VAD config at START=HIGH / END=LOW (backend/config.py
    # defaults), with the COMPLETE tool declarations (bd daa: a name-only
    # declaration 1011s the 2.5 native-audio model).
    return {
        "response_modalities": ["AUDIO"],
        "system_instruction": SYSTEM_INSTRUCTION,
        "tools": [{"function_declarations": TOOL_DECLARATIONS}],
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "realtime_input_config": {
            "automatic_activity_detection": {
                "start_of_speech_sensitivity": types.StartSensitivity.START_SENSITIVITY_HIGH,
                "end_of_speech_sensitivity": types.EndSensitivity.END_SENSITIVITY_LOW,
                "prefix_padding_ms": 500,
                "silence_duration_ms": 500,
            }
        },
    }


async def _silence_streamer(session) -> None:
    silence = b"\x00" * (int(_RATE * (_CHUNK_MS / 1000.0)) * 2)
    try:
        while True:
            await session.send_realtime_input(
                audio=types.Blob(data=silence, mime_type="audio/pcm;rate=16000"))
            await asyncio.sleep(_CHUNK_MS / 1000.0)
    except asyncio.CancelledError:
        raise
    except _CLOSE_ERRORS:
        return


async def _drive_turn(session, pcm: bytes) -> dict:
    """Send one utterance; record whether a non-empty input_transcription fires."""
    turn: dict = {
        "input_transcription": False,
        "input_transcription_latency_s": None,
        "first_signal": None,
        "signals": [],
        "close_code": None,
    }
    for ch in _chunks(pcm):
        await session.send_realtime_input(
            audio=types.Blob(data=ch, mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(_CHUNK_MS / 1000.0)

    silence_task = asyncio.create_task(_silence_streamer(session))
    sent_at = time.monotonic()
    try:
        while time.monotonic() - sent_at < _TURN_TIMEOUT_S:
            try:
                evt = await asyncio.wait_for(
                    session.receive().__anext__(),
                    timeout=max(0.5, _TURN_TIMEOUT_S - (time.monotonic() - sent_at)))
            except (asyncio.TimeoutError, StopAsyncIteration):
                break

            now = round(time.monotonic() - sent_at, 2)
            sc = getattr(evt, "server_content", None)

            # input_transcription is the METRIC -- detect it INDEPENDENTLY of the
            # coarse first-signal classifier below, never gated behind the audio
            # branch. If the SDK ever emits one event carrying BOTH `data` (audio)
            # and `server_content.input_transcription`, an elif chain that checks
            # audio first would silently drop the transcription (fresh-eyes finding
            # on this probe). This unconditional check can't.
            has_input_transcription = (
                sc is not None
                and getattr(sc, "input_transcription", None)
                and getattr(sc.input_transcription, "text", None)
            )
            if has_input_transcription and not turn["input_transcription"]:
                turn["input_transcription"] = True
                turn["input_transcription_latency_s"] = now

            sig = None
            if getattr(evt, "data", None) is not None:
                sig = "audio"
            elif has_input_transcription:
                sig = "input_transcription"
            elif sc is not None and getattr(sc, "output_transcription", None) \
                    and getattr(sc.output_transcription, "text", None):
                sig = "output_transcription"
            elif sc is not None and getattr(sc, "model_turn", None):
                sig = "model_turn"
            elif getattr(evt, "tool_call", None) is not None:
                sig = "tool_call"
            elif sc is not None and getattr(sc, "turn_complete", False):
                sig = "turn_complete"

            if sig is not None:
                if turn["first_signal"] is None:
                    turn["first_signal"] = sig
                if sig not in turn["signals"]:
                    turn["signals"].append(sig)

            # End the wait once the model's turn completes AND we have seen
            # whatever it was going to send (input_transcription typically
            # precedes the model turn).
            if sc is not None and getattr(sc, "turn_complete", False):
                break
    except _CLOSE_ERRORS as exc:
        turn["close_code"] = getattr(exc, "code", None)
    finally:
        silence_task.cancel()
        try:
            await silence_task
        except (asyncio.CancelledError, *_CLOSE_ERRORS):
            pass

    return turn


async def _run(model: str, n_turns: int) -> int:
    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
    client = genai.Client()
    pcms = [_load_pcm(FIXTURES[i % len(FIXTURES)]) for i in range(n_turns)]
    fired = 0
    rows: list[dict] = []
    print(f"model={model} vertex={use_vertex} turns={n_turns} START=HIGH")
    try:
        async with client.aio.live.connect(model=model, config=_connect_config()) as session:
            for i in range(n_turns):
                turn = await _drive_turn(session, pcms[i])
                turn["fixture"] = FIXTURES[i % len(FIXTURES)]
                rows.append(turn)
                if turn["input_transcription"]:
                    fired += 1
                flag = "IT" if turn["input_transcription"] else "--"
                print(f"  turn {i+1}: input_transcription={flag} "
                      f"first={turn['first_signal']} signals={turn['signals']} "
                      f"it_latency={turn['input_transcription_latency_s']}"
                      + (f" CLOSED code={turn['close_code']}" if turn["close_code"] else ""))
                if turn["close_code"] is not None:
                    break
    except _CLOSE_ERRORS as exc:
        print(f"  connect/session closed: code={getattr(exc, 'code', None)} {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        return 1

    n = len(rows)
    verdict = "YES" if fired > 0 else "NO"
    print(f"\nINPUT_TRANSCRIPTION_FIRES={verdict}  rate={fired}/{n}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--vertex", action="store_true",
                    help="use the Vertex deployed model id (needs ADC/project env)")
    args = ap.parse_args()
    model = MODEL_VERTEX if args.vertex else MODEL_AISTUDIO
    return asyncio.run(_run(model, args.turns))


if __name__ == "__main__":
    raise SystemExit(main())
