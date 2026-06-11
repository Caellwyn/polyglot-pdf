"""Diagnostic (bd polyglot-pdf-4sv7): measure voice-turn registration reliability
per model x VAD mode on the audio path, using the committed harness fixtures.

The live demo drops short answers ("yes") and rarely lands two turns in a row.
Config ground truth (4sv7 comment 2026-06-11): the demo runs NATIVE Gemini VAD
(continuous client streaming) on gemini-2.5-flash-native-audio-preview-12-2025,
with VAD_START_SENSITIVITY=LOW / VAD_END_SENSITIVITY=LOW / 500 ms silence.
Suspects: (a) the 2.5 model on the audio path (bd daa: 1011s), (b) the native
VAD tuning -- START_SENSITIVITY_LOW is the LESS sensitive setting and may miss
short/quiet onsets entirely.

This spike drives REAL AUDIO turns (the committed 16 kHz PCM16 fixtures --
"yes that's correct" is the exact failing case) and measures, per
model x VAD-mode, how many turns REGISTER (any model response: transcription,
audio, tool call, turn_complete, or billing) and the latency to first signal.

Modes:
  manual      -- automatic_activity_detection disabled; bracket each utterance
                 with activity_start/activity_end (no trailing-silence need).
  native-demo -- the demo's shipped knobs: start=LOW, end=LOW, silence=500 ms.
  native-hi   -- start=HIGH (more sensitive), end=LOW, silence=500 ms.

Under native modes the client streams CONTINUOUS silence after each utterance
(the bd 95uy finding: Gemini's VAD needs an unbroken stream to close a turn).

No PII: fixtures are canned digits + "yes that's correct". Run from repo root:
    GEMINI_API_KEY=... python scripts/spikes/diag_turn_reliability_4sv7.py \
        --turns 6 --models both --modes manual,native-demo,native-hi
Writes a JSONL event record next to stdout summary via --out.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
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

MODELS = {
    "2.5": "gemini-2.5-flash-native-audio-preview-12-2025",
    "3.1": "gemini-3.1-flash-live-preview",
}

FIXTURE_DIR = _REPO_ROOT / "frontend" / "public" / "test-fixtures"
# Alternate the short confirm with digits so consecutive turns mix the exact
# failing case ("yes") with longer utterances, like the real demo cadence.
FIXTURES = ["confirm_yes.wav", "digits_1234567.wav", "confirm_yes.wav",
            "digits_12345.wav"]

_RATE = 16000
_CHUNK_MS = 20
_TURN_TIMEOUT_S = 20.0

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


def _vad_config(mode: str) -> dict:
    if mode == "manual":
        return {"disabled": True}
    if mode == "native-demo":
        return {
            "start_of_speech_sensitivity": types.StartSensitivity.START_SENSITIVITY_LOW,
            "end_of_speech_sensitivity": types.EndSensitivity.END_SENSITIVITY_LOW,
            "prefix_padding_ms": 500,
            "silence_duration_ms": 500,
        }
    if mode == "native-hi":
        return {
            "start_of_speech_sensitivity": types.StartSensitivity.START_SENSITIVITY_HIGH,
            "end_of_speech_sensitivity": types.EndSensitivity.END_SENSITIVITY_LOW,
            "prefix_padding_ms": 500,
            "silence_duration_ms": 500,
        }
    raise ValueError(mode)


def _connect_config(mode: str) -> dict:
    # Mirror the adapter's real config family (tools + transcriptions + SI):
    # 3.1 rejects minimal configs with 1007 (bd a7k), and the demo ships all
    # of these, so the probe should too.
    return {
        "response_modalities": ["AUDIO"],
        "system_instruction": SYSTEM_INSTRUCTION,
        "tools": [{"function_declarations": TOOL_DECLARATIONS}],
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "realtime_input_config": {"automatic_activity_detection": _vad_config(mode)},
    }


async def _silence_streamer(session) -> None:
    """Stream zero-filled 20 ms frames at real-time pace until cancelled."""
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


async def _drive_turn(session, pcm: bytes, mode: str, events_out: list[dict]) -> dict:
    """Send one utterance, then wait for the model to register it."""
    turn: dict = {"registered": False, "latency_s": None, "signals": [],
                  "tool_calls": [], "close_code": None}
    t0 = time.monotonic()

    if mode == "manual":
        await session.send_realtime_input(activity_start=types.ActivityStart())
    for ch in _chunks(pcm):
        await session.send_realtime_input(
            audio=types.Blob(data=ch, mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(_CHUNK_MS / 1000.0)
    if mode == "manual":
        await session.send_realtime_input(activity_end=types.ActivityEnd())

    silence_task = None
    if mode != "manual":
        silence_task = asyncio.create_task(_silence_streamer(session))

    sent_at = time.monotonic()
    tool_responses: list[types.FunctionResponse] = []
    try:
        while time.monotonic() - sent_at < _TURN_TIMEOUT_S:
            try:
                evt = await asyncio.wait_for(
                    session.receive().__anext__(),
                    timeout=max(0.5, _TURN_TIMEOUT_S - (time.monotonic() - sent_at)))
            except (asyncio.TimeoutError, StopAsyncIteration):
                break

            now = time.monotonic() - sent_at
            sc = getattr(evt, "server_content", None)
            tc = getattr(evt, "tool_call", None)
            sig = None
            if tc is not None and tc.function_calls:
                for fc in tc.function_calls:
                    turn["tool_calls"].append(
                        {"name": fc.name, "args": dict(fc.args or {})})
                    tool_responses.append(types.FunctionResponse(
                        id=fc.id, name=fc.name, response={"success": True}))
                sig = "tool_call"
            elif sc is not None:
                if getattr(sc, "input_transcription", None) and sc.input_transcription.text:
                    sig = "input_transcription"
                elif getattr(sc, "model_turn", None):
                    sig = "model_turn"
                elif getattr(sc, "turn_complete", False):
                    sig = "turn_complete"
            elif getattr(evt, "usage_metadata", None) is not None:
                sig = "usage"

            if sig:
                if turn["latency_s"] is None:
                    turn["latency_s"] = round(now, 2)
                turn["registered"] = True
                if sig not in turn["signals"]:
                    turn["signals"].append(sig)
                events_out.append({"t": round(now, 2), "signal": sig})
            # A completed model turn (or an answered tool call) ends the wait.
            if tool_responses:
                await session.send_tool_response(function_responses=tool_responses)
                tool_responses = []
            if sc is not None and getattr(sc, "turn_complete", False) and turn["registered"]:
                break
    except _CLOSE_ERRORS as exc:
        turn["close_code"] = getattr(exc, "code", None)
    finally:
        if silence_task is not None:
            silence_task.cancel()
            try:
                await silence_task
            except asyncio.CancelledError:
                pass

    turn["total_s"] = round(time.monotonic() - t0, 2)
    return turn


async def _run_combo(model_key: str, mode: str, n_turns: int) -> dict:
    model = MODELS[model_key]
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    combo = {"model": model_key, "mode": mode, "turns": [], "connect_error": None}
    pcms = [_load_pcm(FIXTURES[i % len(FIXTURES)]) for i in range(n_turns)]
    try:
        async with client.aio.live.connect(
                model=model, config=_connect_config(mode)) as session:
            for i in range(n_turns):
                events: list[dict] = []
                turn = await _drive_turn(session, pcms[i], mode, events)
                turn["fixture"] = FIXTURES[i % len(FIXTURES)]
                combo["turns"].append(turn)
                ok = "ok " if turn["registered"] else "MISS"
                print(f"    [{model_key} {mode}] turn {i+1}: {ok} "
                      f"latency={turn['latency_s']} signals={turn['signals']} "
                      f"tools={[t['name'] for t in turn['tool_calls']]}"
                      + (f" CLOSED code={turn['close_code']}" if turn["close_code"] else ""),
                      flush=True)
                if turn["close_code"] is not None:
                    break  # session is gone
                await asyncio.sleep(1.0)
    except _CLOSE_ERRORS as exc:
        combo["connect_error"] = f"code={getattr(exc, 'code', None)}: {str(exc)[:90]}"
    except Exception as exc:  # noqa: BLE001
        combo["connect_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return combo


async def main_async(args: argparse.Namespace) -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set.")
        return 1
    model_keys = ["2.5", "3.1"] if args.models == "both" else [args.models]
    modes = args.modes.split(",")
    results = []
    for mk in model_keys:
        for mode in modes:
            print(f"\n=== model {mk} / mode {mode} ({args.turns} turns) ===", flush=True)
            results.append(await _run_combo(mk, mode, args.turns))

    if args.out:
        Path(args.out).write_text(
            "\n".join(json.dumps(r) for r in results), encoding="utf-8")

    print(f"\n{'=' * 74}\nSUMMARY -- turn registration per model x VAD mode\n{'=' * 74}")
    print(f"  {'model':<6} {'mode':<12} {'reg/att':>8} {'yes-reg':>8} "
          f"{'med-lat':>8} {'1011s':>6}")
    for r in results:
        if r["connect_error"]:
            print(f"  {r['model']:<6} {r['mode']:<12} CONNECT FAILED: {r['connect_error']}")
            continue
        att = len(r["turns"])
        reg = sum(1 for t in r["turns"] if t["registered"])
        yes_turns = [t for t in r["turns"] if t["fixture"] == "confirm_yes.wav"]
        yes_reg = f"{sum(1 for t in yes_turns if t['registered'])}/{len(yes_turns)}"
        lats = sorted(t["latency_s"] for t in r["turns"] if t["latency_s"] is not None)
        med = lats[len(lats) // 2] if lats else None
        n1011 = sum(1 for t in r["turns"] if t["close_code"] == 1011)
        print(f"  {r['model']:<6} {r['mode']:<12} {reg}/{att:<6} {yes_reg:>8} "
              f"{str(med):>8} {n1011:>6}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--models", choices=["2.5", "3.1", "both"], default="both")
    ap.add_argument("--modes", default="manual,native-demo,native-hi")
    ap.add_argument("--out", default="/tmp/4sv7-turn-reliability.jsonl")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
