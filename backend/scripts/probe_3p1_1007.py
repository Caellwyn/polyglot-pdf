"""Isolation probe for the 1007 invalid-argument on gemini-3.1-flash-live-preview.

Replicates what the backend sends AFTER setupComplete, to find which input the
3.1-on-AI-Studio path rejects. Reads the API key from env GEMINI_API_KEY (the
caller injects it from Secret Manager; the key is never printed).

Run staged: each stage connects fresh with the adapter's exact connect-config,
waits for setupComplete, then sends ONE thing and reports whether 1007 fires.

Usage (Vertex is the DEFAULT -- maintainer directive 2026-07-12: all live-model
work runs on Vertex so costs land on the tracked billing project; ADC +
GOOGLE_CLOUD_PROJECT, e.g. via `gcloud auth application-default login`):
    GOOGLE_CLOUD_PROJECT=... python backend/scripts/probe_3p1_1007.py
    # deliberate AI Studio run (billing NOT on the tracked project; this probe
    # is specifically about the AI-Studio-only 1007, so this is likely the
    # relevant escape-hatch run):
    VERTEXAI=false GEMINI_API_KEY=... python backend/scripts/probe_3p1_1007.py

Converted to Vertex-default for bd polyglot-pdf-rve5; one-shot diagnostic, NOT
re-verified against live Vertex post-conversion. NOTE: this probe targets the
AI-Studio-specific 1007 on a Live-API (bidiGenerateContent) model; the Vertex
model-id variant may differ (bd a079) and Vertex may not reproduce this bug at
all -- that is expected, this script's purpose was AI-Studio-only in origin.
"""
from __future__ import annotations

import asyncio
import os
import sys

from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-live-preview"


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


# The adapter's connect-config, trimmed to the fields it actually sets by default
# (proactive audio off, CONTEXT_COMPRESSION off, native VAD => no 'disabled').
BASE_CONFIG = {
    "response_modalities": ["AUDIO"],
    "tools": [
        {
            "function_declarations": [
                {
                    "name": "update_form_fields",
                    "description": "Update one or more form fields.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "field_id": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["field_id", "value"],
                    },
                }
            ]
        }
    ],
    # native VAD mode (DISABLE_GEMINI_VAD=false): empty knobs => Gemini defaults
    "realtime_input_config": {"automatic_activity_detection": {}},
    "input_audio_transcription": {},
    "output_audio_transcription": {},
    "system_instruction": "You are a helpful form-filling assistant. Speak English.",
}


async def _run_stage(name: str, config: dict, after_setup) -> None:
    print(f"\n=== STAGE: {name} ===", flush=True)
    client = _client()
    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("  connected; setupComplete implied by context-manager entry", flush=True)
            if after_setup is not None:
                await after_setup(session)
            # Read a few messages; a 1007 surfaces as an exception here. Report
            # whether any AUDIO data came back (the success signal).
            try:
                count = 0
                got_audio = False
                async for msg in session.receive():
                    count += 1
                    sc = getattr(msg, "server_content", None)
                    if sc is not None:
                        mt = getattr(sc, "model_turn", None)
                        if mt and getattr(mt, "parts", None):
                            for p in mt.parts:
                                if getattr(p, "inline_data", None) is not None:
                                    got_audio = True
                    if count >= 5 or got_audio:
                        break
                print(f"  received {count} msg(s); got_audio={got_audio}", flush=True)
            except Exception as e:
                print(f"  RECEIVE ERROR: {type(e).__name__}: {e}", flush=True)
                return
        print(f"  STAGE {name}: OK (no 1007)", flush=True)
    except Exception as e:
        print(f"  STAGE {name}: FAILED at connect/send: {type(e).__name__}: {e}", flush=True)


async def _send_text(session):
    print("  sending client_content (disclaimer-style text)...", flush=True)
    await session.send_client_content(
        turns={"parts": [{"text": "Please read this disclaimer aloud in English: This is a test."}]},
        turn_complete=True,
    )


async def _send_audio(session):
    print("  sending realtime_input audio frame...", flush=True)
    # 256 bytes of silence as PCM16 @16k, same shape as the backend.
    silence = b"\x00" * 256
    await session.send_realtime_input(
        audio=types.Blob(data=silence, mime_type="audio/pcm;rate=16000")
    )


async def _send_realtime_text(session):
    print("  sending realtime_input TEXT (alternative to client_content)...", flush=True)
    await session.send_realtime_input(
        text="Please read this disclaimer aloud in English: This is a test."
    )


async def main():
    # Stage 0: connect + just receive (does setup alone 1007?)
    await _run_stage("connect-only", BASE_CONFIG, None)
    # Stage 1: connect + send disclaimer text
    await _run_stage("send-client-content-text", BASE_CONFIG, _send_text)
    # Stage 2: connect + send audio frame
    await _run_stage("send-realtime-audio", BASE_CONFIG, _send_audio)
    # Stage 3: minimal config (strip tools/vad/transcription) + text
    minimal = {
        "response_modalities": ["AUDIO"],
        "system_instruction": "You are a helpful assistant.",
    }
    await _run_stage("minimal-config-then-text", minimal, _send_text)
    # Stage 4: minimal + TEXT modality probe (native-audio models 1007 on TEXT)
    text_modality = {"response_modalities": ["TEXT"]}
    await _run_stage("text-modality-probe", text_modality, _send_text)
    # Stage 5: THE FIX HYPOTHESIS -- send text via send_realtime_input(text=...)
    # instead of send_client_content. If this gets AUDIO back, that's the fix.
    await _run_stage("realtime-input-text", BASE_CONFIG, _send_realtime_text)
    # Stage 6: cross-check the fix on the 2.5 native model (USE_PREMIUM_MODEL=false
    # path / what prod-on-Vertex would use) so a blanket swap doesn't regress it.
    global MODEL
    MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
    await _run_stage("2.5-realtime-input-text", BASE_CONFIG, _send_realtime_text)
    await _run_stage("2.5-client-content-text", BASE_CONFIG, _send_text)


if __name__ == "__main__":
    asyncio.run(main())
