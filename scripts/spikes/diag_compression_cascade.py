"""Diagnostic (bd polyglot-pdf-l3a.1): does context-window compression EVICT on a
CASCADE Live model, when it does not on the native-audio 3.1 model?

Ruled out so far: bad config, API rejection, api_version (v1alpha == v1beta, both
compound). Remaining hypothesis: compression is implemented for cascade Live models but
NOT the native-audio preview (gemini-3.1-flash-live-preview). The genai docs' compression
example uses gemini-live-2.5-flash-preview, a CASCADE model.

Cascade models accept TEXT modality (native-audio rejects it with 1007), so we can drive
turns with cheap TEXT instead of audio. We pad each turn so the context crosses a low
trigger within a few turns, and watch prompt_token_count: if it PLATEAUS near the window
on the cascade model while it COMPOUNDED on 3.1-native, compression works -- just not on
native-audio. That makes it a model-capability gap, not our bug.

If the cascade model won't connect on this key (the docs' string may be unavailable),
the probe reports that too -- itself a useful datum.

No PII: filler text only. Vertex is the DEFAULT (maintainer directive 2026-07-12:
all live-model work runs on Vertex; ADC + GOOGLE_CLOUD_PROJECT):
    GOOGLE_CLOUD_PROJECT=... backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_cascade.py \
        --model gemini-live-2.5-flash-preview --trigger 1200 --window 600 --turns 8
    # deliberate AI Studio run: VERTEXAI=false GEMINI_API_KEY=... <same command>

Converted to Vertex-default for bd polyglot-pdf-rve5; one-shot diagnostic, NOT
re-verified against live Vertex post-conversion. This is a Live-API
(bidiGenerateContent) script -- the Vertex model-id variant may need adjustment
per bd a079.
"""

from __future__ import annotations

import argparse
import asyncio
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

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

# Chunky filler so the context crosses a low trigger within a few turns (no PII).
_PAD = ("Please retain this filler context for the current turn. " * 14).strip()


def _client(http_options=None) -> genai.Client:
    """Vertex by DEFAULT (maintainer directive 2026-07-12: all live-model work
    runs on Vertex so costs land on the tracked billing project). VERTEXAI=true
    (default) -> ADC + GOOGLE_CLOUD_PROJECT; set VERTEXAI=false with GEMINI_API_KEY
    only for a deliberate AI Studio run. Threads http_options (this diagnostic
    varies api_version) through either path.
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
            http_options=http_options,
        )
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("VERTEXAI=false but NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key, http_options=http_options)


async def _run(model: str, api_version: str, trigger: int, window: int,
               n_turns: int) -> tuple[list[int], str]:
    client = _client(http_options=types.HttpOptions(api_version=api_version))
    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction="You are a helpful assistant. Reply with just 'ok'.",
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=trigger,
            sliding_window=types.SlidingWindow(target_tokens=window),
        ),
    )
    prompts: list[int] = []
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            for i in range(n_turns):
                msg = f"Turn {i + 1}. {_PAD} Reply 'ok'."
                await session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part(text=msg)]),
                    turn_complete=True,
                )
                got = False
                async for evt in session.receive():
                    um = getattr(evt, "usage_metadata", None)
                    if um is not None:
                        pt = getattr(um, "prompt_token_count", None)
                        if pt:
                            prompts.append(pt)
                            got = True
                    sc = getattr(evt, "server_content", None)
                    if sc is not None and getattr(sc, "turn_complete", False):
                        break
                if not got:
                    print(f"  [warn] {model} turn {i + 1}: no usage")
        return prompts, "OK"
    except Exception as e:  # noqa: BLE001
        return prompts, f"{type(e).__name__}: {str(e)[:140]}"


async def main_async(args: argparse.Namespace) -> int:
    if os.environ.get("VERTEXAI", "true").lower() != "true" \
            and not os.getenv("GEMINI_API_KEY"):
        print("VERTEXAI=false but GEMINI_API_KEY not set.")
        return 1
    print(f"Model={args.model}, api_version={args.api_version}, "
          f"trigger={args.trigger}, window={args.window}, turns={args.turns}\n")

    prompts, status = await _run(args.model, args.api_version, args.trigger,
                                 args.window, args.turns)
    print(f"connect/run status: {status}")
    if not prompts:
        print("No prompt_token_count captured -- cannot judge eviction.")
        print("(If status shows 1007/1008/NotFound, this cascade model isn't reachable "
              "on this key -- itself evidence about availability.)")
        return 0

    print(f"\n  {'turn':>4} {'prompt_tok':>11}  note")
    prev = 0
    for i, pt in enumerate(prompts, 1):
        note = ""
        if prev and pt < prev:
            note = "<- DROPPED (eviction!)"
        elif pt > args.trigger:
            note = "(over trigger)"
        print(f"  {i:>4} {pt:>11,}  {note}")
        prev = pt

    growth = prompts[-1] / prompts[0] if prompts else 0
    crossed = prompts[-1] > args.trigger
    evicted = any(prompts[i] < prompts[i - 1] for i in range(1, len(prompts)))
    print(f"\n  growth: {growth:.1f}x ({prompts[0]} -> {prompts[-1]}), "
          f"crossed trigger: {'yes' if crossed else 'no'}, "
          f"eviction seen: {'YES' if evicted else 'no'}")
    if crossed and evicted:
        print("  => Compression EVICTS on this cascade model. The native-audio 3.1 model\n"
              "     ignoring it is therefore a MODEL gap, not our config.")
    elif crossed and not evicted:
        print("  => Even this model compounded past the trigger with no eviction --\n"
              "     compression may be broadly inert right now, not just native-audio.")
    else:
        print("  => Prompt never crossed the trigger; lower --trigger or raise --turns.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Test compression eviction on a cascade Live model.")
    ap.add_argument("--model", type=str, default="gemini-live-2.5-flash-preview")
    ap.add_argument("--api-version", dest="api_version", type=str, default="v1beta")
    ap.add_argument("--trigger", type=int, default=1200)
    ap.add_argument("--window", type=int, default=600)
    ap.add_argument("--turns", type=int, default=8)
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
