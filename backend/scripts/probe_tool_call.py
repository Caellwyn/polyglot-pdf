"""Probe: does the Live model emit update_form_fields when the user gives a value?

Reproduces the backend's tool-call scenario WITHOUT a microphone (bd polyglot-pdf-kbf):
connect with the REAL system instruction + REAL tool declarations, send the
greeting trigger, then send a text turn standing in for the user's transcribed
answer ("My A-Number is A123456789"), and report EXACTLY what the model emits --
tool calls (name + args), text, audio, or nothing.

This isolates the four hypotheses for "she says trouble saving but no tool call
reaches the backend":
  1. validation block      -> we'd see the call + a validation tool-response
  2. tool-def mismatch      -> call emitted with wrong/empty args
  3. tooling/websocket      -> N/A here (we talk to Gemini directly)
  4. model not following    -> NO update_form_fields call at all

Runs the same scenario on 3.1 and 2.5 for an A/B. Text stands in for transcribed
voice: the backend's tool-call decision is made on the transcript, so this is a
faithful probe of the decision itself (not of the audio path).

Usage:
    GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_tool_call.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from google import genai
from google.genai import types

from backend.config import Settings

# Two A/B-able native-audio Live models.
MODELS = [
    "gemini-3.1-flash-live-preview",
    "gemini-2.5-flash-native-audio-preview-12-2025",
]


def _client() -> genai.Client:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key)  # AI Studio, like the demo backend.


# A realistic single-field section matching the live I-90 session we saw in the
# logs (field #1 = Alien Registration Number, a text field).
FIELDS_TEXT = (
    "[1] id='p1_line1_aliennumber' name='Alien Registration Number (A-Number)' "
    "type=text Filled=False"
)


def _system_instruction() -> str:
    s = Settings()
    return s.SYSTEM_INSTRUCTION.format(
        form_title="Form I-90",
        section_number="1",
        total_sections="16",
        section_label="Part 1 - Information About You: Numbers and Names",
        section_list="[1] Part 1 - Information About You",
        filled_count=0,
        total_fields=9,
        unfilled_count=9,
        fields_json=FIELDS_TEXT,
        fill_language="English",
        previous_spoken_names="(none)",
        confirmation_policy="Confirm every field verbally before moving on.",
        next_field_hint="Alien Registration Number (A-Number) (field_id: p1_line1_aliennumber, type: text)",
    )


def _config(model: str) -> dict:
    s = Settings()
    return {
        "response_modalities": ["AUDIO"],
        "tools": [{"function_declarations": s.TOOL_DECLARATIONS}],
        "realtime_input_config": {"automatic_activity_detection": {}},
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "system_instruction": _system_instruction(),
    }


async def _drain(session, label: str, max_msgs: int = 400, stop_on_tool: bool = True):
    """Read messages, collecting tool calls / text / audio until a tool call or
    the turn completes. Returns (tool_calls, got_audio, got_text, transcript).

    NOTE: a full audio turn is many messages, so max_msgs must be high enough to
    reach turn_complete -- a low cap cuts the turn off mid-stream and contaminates
    the NEXT turn's read."""
    tool_calls = []
    got_audio = False
    got_text = False
    count = 0
    transcript_parts = []
    try:
        async for msg in session.receive():
            count += 1
            if os.environ.get("PROBE_VERBOSE"):
                # Cheap shape dump: which top-level fields are present.
                present = [k for k in ("tool_call", "server_content", "data", "usage_metadata")
                           if getattr(msg, k, None) is not None]
                print(f"    [{label}] msg#{count} fields={present}", flush=True)
            # Tool call via top-level event.tool_call
            tc = getattr(msg, "tool_call", None)
            if tc and getattr(tc, "function_calls", None):
                for fc in tc.function_calls:
                    tool_calls.append({
                        "name": getattr(fc, "name", None),
                        "args": getattr(fc, "args", None) or getattr(fc, "arguments", None),
                    })
            sc = getattr(msg, "server_content", None)
            if sc is not None:
                mt = getattr(sc, "model_turn", None)
                if mt and getattr(mt, "parts", None):
                    for p in mt.parts:
                        # Tool call via model_turn.parts[].function_call
                        pfc = getattr(p, "function_call", None)
                        if pfc:
                            tool_calls.append({
                                "name": getattr(pfc, "name", None),
                                "args": getattr(pfc, "args", None) or getattr(pfc, "arguments", None),
                            })
                        if getattr(p, "inline_data", None) is not None:
                            got_audio = True
                        if getattr(p, "text", None):
                            got_text = True
                ot = getattr(sc, "output_transcription", None)
                if ot and getattr(ot, "text", None):
                    got_text = True
                    transcript_parts.append(ot.text)
                if getattr(sc, "turn_complete", False):
                    if os.environ.get("PROBE_VERBOSE"):
                        print(f"    [{label}] turn_complete at msg#{count}", flush=True)
                    break
            if stop_on_tool and tool_calls:
                break
            if count >= max_msgs:
                print(f"    [{label}] WARNING: hit max_msgs={max_msgs} WITHOUT turn_complete (turn may be truncated)", flush=True)
                break
    except Exception as e:
        print(f"  [{label}] RECEIVE ERROR: {type(e).__name__}: {e}", flush=True)
    return tool_calls, got_audio, got_text, " ".join(transcript_parts).strip()


async def _run(model: str) -> None:
    print(f"\n{'='*70}\n=== MODEL: {model} ===\n{'='*70}", flush=True)
    client = _client()
    try:
        async with client.aio.live.connect(model=model, config=_config(model)) as session:
            print("  connected.", flush=True)

            # Turn 1: trigger the greeting the same way the backend does (an
            # initiating text turn). send_realtime_input(text=) is the 3.1-safe
            # method; 2.5 accepts it too.
            await session.send_realtime_input(
                text="Speak English. Greet the user and ask for the first field."
            )
            tc1, audio1, text1, tr1 = await _drain(session, "greeting", stop_on_tool=False)
            print(f"  [greeting] tool_calls={len(tc1)} audio={audio1} text={text1}", flush=True)
            if tr1:
                print(f"    greeting transcript: {tr1!r}", flush=True)

            # Turn 2: the user answers with their A-Number. THIS is where the
            # backend expects update_form_fields. Text stands in for the
            # transcribed voice.
            await session.send_realtime_input(
                text="My Alien Registration Number is A123456789."
            )
            tc2, audio2, text2, tr2 = await _drain(session, "answer", stop_on_tool=True, max_msgs=400)
            print(f"  [answer] tool_calls={len(tc2)} audio={audio2} text={text2}", flush=True)
            if tr2:
                print(f"    answer transcript: {tr2!r}", flush=True)
            for i, c in enumerate(tc2):
                print(f"    tool_call[{i}]: name={c['name']!r} args={json.dumps(c['args']) if c['args'] is not None else None}", flush=True)

            verdict = "EMITTED update_form_fields" if any(
                c["name"] == "update_form_fields" for c in tc2
            ) else ("emitted OTHER tool: " + ",".join(c["name"] or "?" for c in tc2) if tc2
                    else "NO TOOL CALL (model did not call update_form_fields)")
            print(f"  >>> VERDICT [{model}]: {verdict}", flush=True)
    except Exception as e:
        print(f"  MODEL {model} FAILED: {type(e).__name__}: {e}", flush=True)


async def main():
    only = os.environ.get("PROBE_MODEL")
    models = [only] if only else MODELS
    for m in models:
        await _run(m)


if __name__ == "__main__":
    asyncio.run(main())
