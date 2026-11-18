"""Probe (bd polyglot-pdf-r3ham.4): what does gemini-3.8-live do when the user
barges in (push-to-talk) while a BLOCKING tool call is still pending?

WHY. On 3.8 the adapter marks every function declaration behavior=BLOCKING
(backend/adapters/live_ai_gemini.py, bd bd1zs). Public reports say new user
input CANCELS a pending blocking call. The adapter has no handler for
LiveServerMessage.tool_call_cancellation, and the frontend applies a fill as
soon as the call arrives -- so a cancelled call could leave a stored value the
model believes it never wrote, and the late tool response would answer an id
the server already cancelled.

METHOD. Per trial: one PTT utterance that should trigger update_form_fields.
  - control arm: answer the call immediately, then wait for the model's turn.
  - barge arm:   on receiving the call, do NOT answer; after --delay seconds
                 send a second PTT utterance (a different answer), record every
                 event for --observe seconds (tool_call_cancellation ids, new
                 tool calls, interrupted, turn_complete, audio), THEN send the
                 late tool response for the original id and record what follows.
Mirrors deploy for the parts under test: response AUDIO, input+output
transcription, production TOOL_DECLARATIONS with behavior=BLOCKING (as the
adapter sets on 3.8), automatic activity detection DISABLED.

Vertex only. Cost: a few cents per default run.

Usage:
  GOOGLE_CLOUD_PROJECT=... python scripts/spikes/probe_bargein_blocking_3p8.py \
      [--trials 3] [--delay 0.3] [--observe 8] [--followup] [--out path.json]

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from backend.config import get_settings  # noqa: E402

_AUDIO_CACHE = Path(__file__).resolve().parent / "fixtures" / "audio_cache"
_RATE = 16000
_CHUNK_MS = 20

FIRST = "My foreign tax I.D. number is 2 4 9 8 1 7 3 6."
BARGE = "My foreign tax I.D. number is 2 4 9 8 1 7 3 8."  # cached 'wrong' variant

SYSTEM_INSTRUCTION = (
    "You are a voice assistant filling a tax form one field at a time. The "
    "current field is foreign_tax_id_number. When the user gives a value, call "
    "update_form_fields with field_id 'foreign_tax_id_number' and that value, "
    "then read the stored value back and ask whether it is correct. If the user "
    "corrects themselves, call update_form_fields again with the corrected value."
)


def _clip(text: str) -> bytes:
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    path = _AUDIO_CACHE / f"{key}.pcm"
    if not path.exists():
        raise SystemExit(f"missing cached clip for {text!r} ({path.name})")
    return path.read_bytes()


def _tools() -> list:
    decls = copy.deepcopy(get_settings().TOOL_DECLARATIONS)
    for d in decls:
        d["behavior"] = "BLOCKING"
    return [{"function_declarations": decls}]


def _config() -> dict:
    return {
        "response_modalities": ["AUDIO"],
        "system_instruction": SYSTEM_INSTRUCTION,
        "tools": _tools(),
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "realtime_input_config": {"automatic_activity_detection": {"disabled": True}},
    }


async def _say(session, pcm: bytes) -> None:
    await session.send_realtime_input(activity_start=types.ActivityStart())
    n = int(_RATE * _CHUNK_MS / 1000) * 2
    for i in range(0, len(pcm), n):
        await session.send_realtime_input(
            audio=types.Blob(data=pcm[i:i + n], mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(_CHUNK_MS / 1000.0)
    await session.send_realtime_input(activity_end=types.ActivityEnd())


class _Rx:
    """Single receive pump; every event is timestamped into self.events."""

    def __init__(self, session):
        self.s = session
        self.t0 = time.monotonic()
        self.events = []
        self.calls = asyncio.Queue()
        self.task = asyncio.create_task(self._pump())

    def _ev(self, kind, **kw):
        self.events.append({"t": round(time.monotonic() - self.t0, 3), "kind": kind, **kw})

    async def _pump(self):
        try:
            async for msg in self.s.receive():
                if msg.tool_call is not None:
                    for fc in msg.tool_call.function_calls or []:
                        self._ev("tool_call", id=fc.id, name=fc.name, args=dict(fc.args or {}))
                        await self.calls.put(fc)
                if msg.tool_call_cancellation is not None:
                    self._ev("tool_call_cancellation", ids=list(msg.tool_call_cancellation.ids or []))
                sc = msg.server_content
                if sc is not None:
                    if sc.interrupted:
                        self._ev("interrupted")
                    if sc.model_turn and any(getattr(p, "inline_data", None) for p in sc.model_turn.parts or []):
                        if not self.events or self.events[-1]["kind"] != "audio":
                            self._ev("audio")
                    if sc.output_transcription is not None and sc.output_transcription.text:
                        self._ev("say", text=sc.output_transcription.text)
                    if sc.input_transcription is not None and sc.input_transcription.text:
                        self._ev("heard", text=sc.input_transcription.text)
                    if sc.turn_complete:
                        self._ev("turn_complete")
                if msg.go_away is not None:
                    self._ev("go_away")
        except Exception as exc:  # session closed
            self._ev("closed", error=f"{type(exc).__name__}: {str(exc)[:160]}")


def _resp(fc, value_note: str):
    return types.FunctionResponse(
        id=fc.id, name=fc.name,
        response={"success": True, "applied_fields": [(fc.args or {}).get("field_id")],
                  "message": f"Fields updated successfully. Stored value: {value_note}"})


async def _trial(client, model: str, barge: bool, delay: float, observe: float,
                 followup: bool = False) -> dict:
    out = {"arm": "barge" if barge else "control"}
    async with client.aio.live.connect(model=model, config=_config()) as s:
        rx = _Rx(s)
        await _say(s, _clip(FIRST))
        try:
            fc = await asyncio.wait_for(rx.calls.get(), timeout=20)
        except asyncio.TimeoutError:
            out["error"] = "no tool call for the first utterance"
            out["events"] = rx.events
            rx.task.cancel()
            return out
        out["first_call"] = {"id": fc.id, "args": dict(fc.args or {})}
        if not barge:
            await s.send_tool_response(function_responses=[_resp(fc, str((fc.args or {}).get("value")))])
            await asyncio.sleep(observe)
        else:
            await asyncio.sleep(delay)
            rx._ev("barge_start")
            await _say(s, _clip(BARGE))
            rx._ev("barge_end")
            await asyncio.sleep(observe)
            rx._ev("late_response_sent", id=fc.id)
            try:
                await s.send_tool_response(function_responses=[_resp(fc, str((fc.args or {}).get("value")))])
            except Exception as exc:
                rx._ev("late_response_error", error=f"{type(exc).__name__}: {str(exc)[:160]}")
            # Answer any further calls so the turn can finish.
            end = time.monotonic() + observe
            while time.monotonic() < end:
                try:
                    fc2 = await asyncio.wait_for(rx.calls.get(), timeout=max(0.2, end - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                await s.send_tool_response(function_responses=[_resp(fc2, str((fc2.args or {}).get("value")))])
            await asyncio.sleep(2.0)
            if followup:
                # Does the session recover on the NEXT user turn?
                rx._ev("followup_start")
                await _say(s, _clip(BARGE))
                rx._ev("followup_end")
                end = time.monotonic() + observe
                while time.monotonic() < end:
                    try:
                        fc3 = await asyncio.wait_for(rx.calls.get(), timeout=max(0.2, end - time.monotonic()))
                    except asyncio.TimeoutError:
                        break
                    await s.send_tool_response(function_responses=[_resp(fc3, str((fc3.args or {}).get("value")))])
                await asyncio.sleep(2.0)
        rx.task.cancel()
        out["events"] = rx.events
    calls = [e for e in out["events"] if e["kind"] == "tool_call"]
    out["n_tool_calls"] = len(calls)
    out["cancelled_ids"] = [i for e in out["events"] if e["kind"] == "tool_call_cancellation" for i in e["ids"]]
    out["first_call_cancelled"] = out["first_call"]["id"] in out["cancelled_ids"]
    out["values_written"] = [c["args"].get("value") for c in calls]
    sigs = [json.dumps(c["args"], sort_keys=True) for c in calls]
    out["duplicate_calls"] = len(sigs) - len(set(sigs))
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="gemini-3.8-live")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--delay", type=float, default=0.3)
    ap.add_argument("--observe", type=float, default=8.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--followup", action="store_true",
                    help="after the late response, send one more utterance to test recovery")
    args = ap.parse_args()
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("GOOGLE_CLOUD_PROJECT is required (Vertex only).")
        return 1
    client = genai.Client(vertexai=True, project=project,
                          location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
    results = [await _trial(client, args.model, False, args.delay, args.observe)]
    for _ in range(args.trials):
        results.append(await _trial(client, args.model, True, args.delay, args.observe, args.followup))
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != "events"}))
        for e in r.get("events", []):
            print("   ", json.dumps(e))
    if args.out:
        Path(args.out).write_text(json.dumps({"model": args.model, "trials": results}, indent=2),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
