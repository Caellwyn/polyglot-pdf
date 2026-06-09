"""Probe: does the native-audio tool_call carry an `id`, and on which path?

bd polyglot-pdf-0ux. The backend crashes on AI Studio with 'FunctionResponse
request must have an id field': the SDK's mldev path REQUIRES the id (live.py),
but our receive loop built an id-less FunctionResponse.

This probe isolates the ground truth -- for the SAME I-90 first-field scenario as
the real session, on the SAME 2.5 native-audio model, it reports for EVERY tool
call which path delivered it (event.tool_call vs model_turn.parts) and whether
`.id` is present -- so we know whether the fix is "echo the id we already have" or
"synthesize an id the model never sent".

FINDING (this probe's result): the call arrives via the **event.tool_call** path
WITH a valid id (e.g. id='function-call-...'), and our code DROPPED it -- the
event.tool_call build site omitted the id entirely on a wrong "SDK matches by
order" comment. (The model_turn.parts build site already included the id when it
had one.) So the fix is "echo the id we already have", not "synthesize one". See
_build_function_response in live_ai_gemini.py.

Usage:
    GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_tool_call_id.py
"""
from __future__ import annotations

import asyncio
import os
import sys

from google import genai

from backend.config import MODEL_NATIVE_STANDARD, Settings

FIELDS_TEXT = (
    "[1] id='p1_line1_aliennumber' name='Alien Registration Number (A-Number)' "
    "type=text Filled=False"
)


def _client() -> genai.Client:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key)


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
        fields_json=FIELDS_TEXT,
        fill_language="English",
        previous_spoken_names="(none)",
        confirmation_policy="Confirm every field verbally before moving on.",
        next_field_hint="Alien Registration Number (A-Number) (field_id: p1_line1_aliennumber, type: text)",
    )


def _config() -> dict:
    s = Settings()
    return {
        "response_modalities": ["AUDIO"],
        "tools": [{"function_declarations": s.TOOL_DECLARATIONS}],
        "realtime_input_config": {"automatic_activity_detection": {}},
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "system_instruction": _system_instruction(),
    }


def _report_fc(path: str, fc) -> dict:
    """Pull every plausible id/name attribute off a function_call object."""
    info = {
        "path": path,
        "name": getattr(fc, "name", None),
        "id": getattr(fc, "id", None),
        "has_id_attr": hasattr(fc, "id"),
        # Some SDK shapes nest differently -- dump a few alternates so we don't
        # miss an id that lives under another name.
        "all_attrs": [a for a in dir(fc) if not a.startswith("_")],
    }
    print(
        "  [tool_call] path={path} name={name!r} id={id!r} has_id_attr={has}".format(
            path=path, name=info["name"], id=info["id"], has=info["has_id_attr"]
        ),
        flush=True,
    )
    return info


async def _drain(session, label: str, max_msgs: int = 400):
    found = []
    count = 0
    try:
        async for msg in session.receive():
            count += 1
            tc = getattr(msg, "tool_call", None)
            if tc and getattr(tc, "function_calls", None):
                for fc in tc.function_calls:
                    found.append(_report_fc("event.tool_call", fc))
            sc = getattr(msg, "server_content", None)
            if sc is not None:
                mt = getattr(sc, "model_turn", None)
                if mt and getattr(mt, "parts", None):
                    for p in mt.parts:
                        pfc = getattr(p, "function_call", None)
                        if pfc:
                            found.append(_report_fc("model_turn.parts", pfc))
                if getattr(sc, "turn_complete", False):
                    break
            if found:
                break
            if count >= max_msgs:
                print(f"  [{label}] hit max_msgs without turn_complete", flush=True)
                break
    except Exception as e:
        print(f"  [{label}] RECEIVE ERROR: {type(e).__name__}: {e}", flush=True)
    return found


async def main():
    model = os.environ.get("PROBE_MODEL", MODEL_NATIVE_STANDARD)
    print(f"\n=== MODEL: {model} (AI Studio) ===", flush=True)
    client = _client()
    async with client.aio.live.connect(model=model, config=_config()) as session:
        print("  connected.", flush=True)
        await session.send_realtime_input(
            text="Speak English. Greet the user and ask for the first field."
        )
        await _drain(session, "greeting")
        await session.send_realtime_input(
            text="My Alien Registration Number is A123456789."
        )
        calls = await _drain(session, "answer")
        print(f"\n  >>> {len(calls)} tool call(s) seen", flush=True)
        any_missing = any(c["id"] is None for c in calls)
        update_calls = [c for c in calls if c["name"] == "update_form_fields"]
        print(f"  >>> update_form_fields calls: {len(update_calls)}", flush=True)
        print(f"  >>> ANY call missing id: {any_missing}", flush=True)
        if update_calls:
            print(f"  >>> update_form_fields path(s): {[c['path'] for c in update_calls]}", flush=True)
            print(f"  >>> update_form_fields id(s): {[c['id'] for c in update_calls]}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
