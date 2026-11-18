"""Probe (bd polyglot-pdf-e72on): does INPUT audio transcription add billed
tokens on the Live model?

WHY. Production always requests input_audio_transcription because the idle
watchdog keys on it (backend/adapters/live_ai_gemini.py, on_user_activity), so
any cost it carries is in every deployed session. A text-turn probe on
2026-11-17 measured OUTPUT transcription (about 25-28 TEXT-modality output
tokens per turn on gemini-3.8-live) but could not see INPUT transcription,
because a text turn carries no input audio.

METHOD. Two arms that differ ONLY in input_audio_transcription (present vs
absent), interleaved session by session so drift hits both. Everything else
mirrors deploy: response AUDIO, output_audio_transcription on, the production
TOOL_DECLARATIONS, push-to-talk (automatic activity detection DISABLED, every
utterance bracketed by activity_start / activity_end). Each session plays the
same cached gTTS user clips. Per turn we SUM every usage_metadata event (the
same accounting the adapter bills) by modality: prompt TEXT/AUDIO, response
TEXT/AUDIO, thoughts. The verdict compares per-turn means between arms.

Vertex only (bd rve5). Cost: a few cents per default run.

Usage (from the repo root, backend venv):
  GOOGLE_CLOUD_PROJECT=... python scripts/spikes/probe_input_transcription_cost.py \
      [--model gemini-3.8-live] [--sessions-per-arm 2] [--out path.json]

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
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
_TURN_TIMEOUT_S = 25.0

# Committed English clips from the W-7 plan (16 kHz mono PCM16, keyed by
# sha1(text)[:16]); short, realistic user answers.
CLIP_TEXTS = [
    "I am applying for a new ITIN.",
    "I was born on March 14th, 1990.",
    "My foreign tax I.D. number is 2 4 9 8 1 7 3 6.",
]

SYSTEM_INSTRUCTION = (
    "You are a voice assistant filling a tax form. When the user gives an "
    "answer, acknowledge it in one short sentence and ask them to confirm. "
    "Do not call any tools."
)


def _clip(text: str) -> bytes:
    import hashlib
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    path = _AUDIO_CACHE / f"{key}.pcm"
    if not path.exists():
        raise SystemExit(f"missing cached clip for {text!r} ({path.name})")
    return path.read_bytes()


def _config(input_transcription: bool) -> dict:
    cfg = {
        "response_modalities": ["AUDIO"],
        "system_instruction": SYSTEM_INSTRUCTION,
        "tools": [{"function_declarations": get_settings().TOOL_DECLARATIONS}],
        "output_audio_transcription": {},
        "realtime_input_config": {
            "automatic_activity_detection": {"disabled": True},
        },
    }
    if input_transcription:
        cfg["input_audio_transcription"] = {}
    return cfg


def _add_usage(acc: dict, usage) -> None:
    for d in getattr(usage, "prompt_tokens_details", None) or []:
        key = "in_" + str(getattr(d.modality, "name", d.modality)).lower()
        acc[key] = acc.get(key, 0) + (d.token_count or 0)
    for d in getattr(usage, "response_tokens_details", None) or []:
        key = "out_" + str(getattr(d.modality, "name", d.modality)).lower()
        acc[key] = acc.get(key, 0) + (d.token_count or 0)
    acc["thoughts"] = acc.get("thoughts", 0) + (getattr(usage, "thoughts_token_count", None) or 0)
    acc["usage_events"] = acc.get("usage_events", 0) + 1


async def _turn(session, pcm: bytes) -> dict:
    acc: dict = {"input_transcript_chars": 0, "output_transcript_chars": 0}
    await session.send_realtime_input(activity_start=types.ActivityStart())
    n = int(_RATE * _CHUNK_MS / 1000) * 2
    for i in range(0, len(pcm), n):
        await session.send_realtime_input(
            audio=types.Blob(data=pcm[i:i + n], mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(_CHUNK_MS / 1000.0)
    await session.send_realtime_input(activity_end=types.ActivityEnd())
    t0 = time.monotonic()
    while time.monotonic() - t0 < _TURN_TIMEOUT_S:
        try:
            msg = await asyncio.wait_for(session.receive().__anext__(), timeout=_TURN_TIMEOUT_S)
        except (asyncio.TimeoutError, StopAsyncIteration):
            acc["timeout"] = True
            break
        usage = getattr(msg, "usage_metadata", None)
        if usage is not None:
            _add_usage(acc, usage)
        sc = getattr(msg, "server_content", None)
        if sc is not None:
            it = getattr(sc, "input_transcription", None)
            if it is not None and getattr(it, "text", None):
                acc["input_transcript_chars"] += len(it.text)
            ot = getattr(sc, "output_transcription", None)
            if ot is not None and getattr(ot, "text", None):
                acc["output_transcript_chars"] += len(ot.text)
            if getattr(sc, "turn_complete", False):
                break
    # Late usage_metadata can trail turn_complete by a message; drain briefly.
    end = time.monotonic() + 1.5
    while time.monotonic() < end:
        try:
            msg = await asyncio.wait_for(session.receive().__anext__(), timeout=0.5)
        except (asyncio.TimeoutError, StopAsyncIteration):
            break
        usage = getattr(msg, "usage_metadata", None)
        if usage is not None:
            _add_usage(acc, usage)
    return acc


async def _session(client, model: str, input_transcription: bool) -> list:
    clips = [_clip(t) for t in CLIP_TEXTS]
    out = []
    async with client.aio.live.connect(model=model, config=_config(input_transcription)) as s:
        for pcm in clips:
            out.append(await _turn(s, pcm))
    return out


def _mean(rows: list, key: str) -> float:
    vals = [r.get(key, 0) for r in rows]
    return round(statistics.mean(vals), 2) if vals else 0.0


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="gemini-3.8-live")
    ap.add_argument("--sessions-per-arm", type=int, default=2)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("GOOGLE_CLOUD_PROJECT is required (Vertex only).")
        return 1
    client = genai.Client(vertexai=True, project=project,
                          location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
    arms = {"on": [], "off": []}
    for i in range(args.sessions_per_arm):
        for arm in (("on", "off") if i % 2 == 0 else ("off", "on")):
            rows = await _session(client, args.model, arm == "on")
            for r in rows:
                r["session"] = i
            arms[arm] += rows
            print(f"session {i} arm={arm}: " + json.dumps(rows))
    keys = sorted({k for rows in arms.values() for r in rows for k in r
                   if k not in ("session", "timeout")})
    summary = {"model": args.model, "turns_per_arm": {a: len(r) for a, r in arms.items()},
               "mean_per_turn": {a: {k: _mean(r, k) for k in keys} for a, r in arms.items()}}
    summary["delta_on_minus_off"] = {
        k: round(summary["mean_per_turn"]["on"][k] - summary["mean_per_turn"]["off"][k], 2)
        for k in keys}
    print("SUMMARY " + json.dumps(summary))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "turns": arms}, indent=2),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
