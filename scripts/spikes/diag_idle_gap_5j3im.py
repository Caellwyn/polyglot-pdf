"""Does a live Gemini session survive a long FRAME-FREE gap? (bd polyglot-pdf-5j3im)

## The question

We ship a frame-free idle stream TODAY. Since bd polyglot-pdf-v1m8g retired
Gemini's automatic activity detection, the client sends NOTHING between turns --
not even silence (measured in bd polyglot-pdf-h7atc: 0 silent frames across a
350ms gap, both senders). Backend gap-fill is pinned False.

That was a deliberate, reviewed change. But the premise underneath it is
UNMEASURED: gap-fill originally existed because a starved stream was believed to
trigger 1011 closes (bd polyglot-pdf-7f7m). Reading that bead, its exit criteria
verified the MECHANISM (cadence maintained, silence never fights real audio) --
they never demonstrated that starvation causes a 1011. The stated basis was
"Google-forum analyses", and it was explicitly a NATIVE-VAD claim: "Gemini's
server-side VAD drives turn boundaries and the server clocks keepalive off a
steady cadence of binary frames."

With automatic activity detection DISABLED, turns are bracketed explicitly, so
that reasoning should not apply. Should is not does.

## What this measures

One arm = one live session, deploy-shaped, doing:

    connect -> [turn 1: activity_start, audio, activity_end, await reply]
            -> GAP of N seconds with ZERO bytes sent
            -> [turn 2: same] -> did the second turn get answered?

VERDICT per arm: SURVIVED (turn 2 answered) or DIED (close code + reason).

## Deploy fidelity (mandatory -- bd h04c cost a week of false verdicts)

This drives the REAL adapter, not a hand-rolled config: LiveAIGemini with the
production system instruction and the production tool declarations, connecting
via the adapter's own _build_live_config(). A stripped-down probe config is a
DIFFERENT SYSTEM and its verdicts do not transfer.

Audio is synthetic PCM16 silence-with-tone shaped like a real mic burst. We are
measuring SESSION SURVIVAL across a gap, not transcription accuracy, so the
content does not need to be speech -- but it IS sent inside activity brackets
exactly as PTT does, because un-bracketed audio is a different (and known-bad)
condition.

## Cost

Idle gaps accrue NO tokens -- the cost is wall-clock, not money. Estimated
~$0.0085/arm (deploy SI ~3.8k tok re-sent per billed turn); 6 arms ~= $0.05.
Approved by the maintainer 2026-09-03.

## Run (Vertex only -- all live work bills the tracked project)

    GOOGLE_CLOUD_PROJECT=polyglot-demo-aa709 \
    backend/.venv/Scripts/python.exe scripts/spikes/diag_idle_gap_5j3im.py \
        --gaps 15,60,90 --repeats 2 \
        --json scripts/spikes/data/idle_gap_5j3im.json

No PII: the fixture audio is a tone and the prompts are fictional.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.adapters.live_ai_gemini import LiveAIGemini  # noqa: E402
from backend.config import get_settings  # noqa: E402


def _tone_pcm16(ms: int, rate: int, hz: float = 220.0, amp: float = 0.25) -> bytes:
    """A PCM16 mono tone burst -- stands in for a spoken turn.

    Deliberately NOT silence: we want the server to see a real (non-zero) audio
    payload inside the activity bracket, so the turn is a genuine turn. What the
    model transcribes is irrelevant to session survival.
    """
    n = int(rate * ms / 1000)
    out = bytearray()
    for i in range(n):
        v = int(amp * 32767 * math.sin(2 * math.pi * hz * (i / rate)))
        out += struct.pack("<h", v)
    return bytes(out)


class _ArmResult(dict):
    pass


async def _run_arm(gap_s: float, rep: int, turn_ms: int, verbose: bool) -> _ArmResult:
    """One session: turn, gap, turn. Returns a verdict dict."""
    settings = get_settings()
    started = time.time()
    res = _ArmResult(
        gap_s=gap_s,
        rep=rep,
        model=settings.MODEL_NATIVE,
        vertexai=bool(settings.VERTEXAI),
        turn1_answered=False,
        turn2_answered=False,
        verdict="UNKNOWN",
        close_code=None,
        close_reason=None,
        error=None,
        seconds=None,
    )

    audio_events: List[str] = []
    closed: Dict[str, Any] = {}

    adapter = LiveAIGemini(
        api_key=os.environ.get("GEMINI_API_KEY"),
        model=settings.MODEL_NATIVE,
        vertexai=bool(settings.VERTEXAI),
    )

    async def on_audio(_pcm: bytes) -> None:
        # MUST be async: the adapter awaits this callback
        # (live_ai_gemini.py _handle_session -> `await self._on_audio(...)`).
        # A sync def here raises TypeError inside the receive loop, which the
        # adapter logs and swallows -- so the arm still scored SURVIVED, but on
        # a noisier path than production takes.
        audio_events.append("audio")

    def on_session_dropped(info: Any = None) -> None:
        closed["dropped"] = info

    # Deploy-shaped: the REAL system instruction and the REAL tool declarations.
    from backend.services.form_filling_service import FormFillingService

    svc = FormFillingService.__new__(FormFillingService)
    svc._settings = settings
    try:
        tool_declarations = svc._build_tool_declarations()
    except Exception:
        tool_declarations = None

    adapter.set_callbacks(
        on_form_update=lambda *a, **k: None,
        on_transcript=lambda *a, **k: None,
        on_audio=on_audio,
        on_tool_call=lambda *a, **k: None,
        on_session_dropped=on_session_dropped,
        system_instruction=settings.DTI_SYSTEM_INSTRUCTION,
        tool_declarations=tool_declarations,
    )

    frame = _tone_pcm16(turn_ms, int(getattr(settings, "AUDIO_IN_RATE", 16000)))

    async def one_turn(label: str) -> bool:
        before = len(audio_events)
        await adapter.send_activity_start()
        chunk_ms = int(getattr(settings, "WS_CHUNK_MS", 20))
        rate = int(getattr(settings, "AUDIO_IN_RATE", 16000))
        step = (rate * chunk_ms // 1000) * 2
        for off in range(0, len(frame), step):
            await adapter.stream_audio(frame[off:off + step])
            await asyncio.sleep(chunk_ms / 1000.0)  # real-time pacing, as the mic does
        await adapter.send_activity_end()
        # Wait for ANY reply audio -- that is the proof the session is alive.
        deadline = time.time() + 25.0
        while time.time() < deadline:
            if len(audio_events) > before:
                return True
            if closed:
                return False
            await asyncio.sleep(0.25)
        return False

    try:
        # set_callbacks() above already spawned the session loop (it creates the
        # queues and starts _run_session_loop).
        #
        # Wait on _session_ready, NOT is_session_active(): the latter only reports
        # that the background TASK exists, which is true the instant the task is
        # created and long before the socket is up. A probe that trusted it fired
        # turn 1 into a None session ("ACTIVITY_START called but session is None")
        # and scored a false INCONCLUSIVE. _session_ready is set when the server's
        # setup completes, which is the real thing we need.
        ready_deadline = time.time() + 60
        while time.time() < ready_deadline and not getattr(adapter, "_session_ready", False):
            if closed:
                res["verdict"] = "DIED_BEFORE_TURN1"
                return res
            await asyncio.sleep(0.25)
        if not getattr(adapter, "_session_ready", False):
            res["error"] = "session never became ready"
            res["verdict"] = "ERROR"
            return res
        # Small settle so the first activity bracket is not racing setup_complete.
        await asyncio.sleep(1.0)

        res["turn1_answered"] = await one_turn("turn1")
        if verbose:
            print(f"    turn1 answered={res['turn1_answered']}", flush=True)

        if not res["turn1_answered"]:
            res["verdict"] = "INCONCLUSIVE_TURN1"
            return res

        # THE GAP: send absolutely nothing.
        if verbose:
            print(f"    idling {gap_s}s with ZERO bytes sent...", flush=True)
        gap_deadline = time.time() + gap_s
        while time.time() < gap_deadline:
            if closed:
                res["verdict"] = "DIED_DURING_GAP"
                break
            await asyncio.sleep(0.5)

        if res["verdict"] == "DIED_DURING_GAP":
            return res

        res["turn2_answered"] = await one_turn("turn2")
        res["verdict"] = "SURVIVED" if res["turn2_answered"] else "DIED_AFTER_GAP"
    except asyncio.TimeoutError:
        res["error"] = "timeout establishing session"
        res["verdict"] = "ERROR"
    except Exception as exc:  # pragma: no cover - probe
        res["error"] = f"{type(exc).__name__}: {exc}"
        res["verdict"] = "ERROR"
    finally:
        if closed.get("dropped") is not None:
            res["close_reason"] = str(closed["dropped"])[:300]
        try:
            await asyncio.wait_for(adapter.finalize(), timeout=15)
        except Exception:
            pass
        res["seconds"] = round(time.time() - started, 1)

    return res


async def main_async(args: argparse.Namespace) -> int:
    gaps = [float(g) for g in args.gaps.split(",") if g.strip()]
    results: List[Dict[str, Any]] = []

    print(f"model={get_settings().MODEL_NATIVE} vertexai={get_settings().VERTEXAI}")
    print(f"gaps={gaps} repeats={args.repeats} turn_ms={args.turn_ms}")
    print("Serialized runs (per the experimentation skill) so timings are unconfounded.\n")

    for gap in gaps:
        for rep in range(1, args.repeats + 1):
            print(f"  arm gap={gap}s rep={rep} ...", flush=True)
            r = await _run_arm(gap, rep, args.turn_ms, args.verbose)
            results.append(dict(r))
            print(f"  -> {r['verdict']} ({r['seconds']}s)"
                  + (f" close={r['close_reason']}" if r.get("close_reason") else ""),
                  flush=True)

    print("\n=== SUMMARY ===")
    for gap in gaps:
        arms = [r for r in results if r["gap_s"] == gap]
        verdicts = [a["verdict"] for a in arms]
        survived = sum(1 for v in verdicts if v == "SURVIVED")
        print(f"  gap={gap:>5}s: {survived}/{len(arms)} SURVIVED  {verdicts}")

    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nwrote {p}")

    died = [r for r in results if r["verdict"].startswith("DIED")]
    return 1 if died else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gaps", default="15,60,90",
                    help="comma-separated gap lengths in seconds")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--turn-ms", type=int, default=1200,
                    help="length of each synthetic spoken turn")
    ap.add_argument("--json", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
