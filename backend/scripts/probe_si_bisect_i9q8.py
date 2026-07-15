"""Bisect harness for bd polyglot-pdf-wpw.4 (was i9q8): WHICH part of the full
system instruction makes the Live model skip update_form_fields?

OUTCOME (what this harness PROVED, google-genai 2.8.0, 2026-06-11): the SI was a
red herring -- the cause was the UNTYPED update_form_fields.value param. The fix
(typing value "string" in Settings.TOOL_DECLARATIONS) HAS LANDED, so the numbers
below describe the PRE-FIX investigation, NOT current behavior:
  - PRE-FIX: 3.1 + the FULL SI skipped update_form_fields (5/5 NO TOOL CALL); 3.1
    + a SHORT SI ALSO skipped it (0/4) -- so SI length/content was not the
    variable. 2.5 worked either way (4/4).
  - POST-FIX (today): with the typed value param now in the real config, 3.1 emits
    the call on BOTH short and full SI (5/5, 4/4). Re-running any variant here WILL
    succeed -- that is the fix working, not a contradiction.
The `PROBE_TYPED_VALUE` override (below) was the causation A/B; with the param now
typed in the real config it is vestigial (no-op when run without it). Kept as a
forensic record of the bisect.

This harness drives the SAME single fill->answer turn as probe_tool_call.py
(greeting -> "My A-Number is A123456789." -> expect update_form_fields), but the
SYSTEM INSTRUCTION is a swappable VARIANT so we can bisect the full SI down to the
clause(s) that suppress the call. Text stands in for transcribed voice -- the
tool-call decision is made on the transcript, so this is a faithful probe of the
decision (not the audio path), exactly like probe_tool_call.py.

The variants form a ladder from the known-good SHORT control up to the known-bad
FULL SI, plus ablations that remove one suspect block at a time. Run with enough
PROBE_RUNS to see a RATE, not a single sample (the turn is non-deterministic).

Usage (Vertex is the DEFAULT -- maintainer directive 2026-07-12: all live-model
work runs on Vertex so costs land on the tracked billing project; ADC +
GOOGLE_CLOUD_PROJECT, e.g. via `gcloud auth application-default login`):
    GOOGLE_CLOUD_PROJECT=... PYTHONPATH=. python backend/scripts/probe_si_bisect_i9q8.py
    # one variant, more runs:
    PROBE_VARIANT=short PROBE_RUNS=5 PROBE_MODEL=gemini-3.1-flash-live-preview \
        GOOGLE_CLOUD_PROJECT=... PYTHONPATH=. python backend/scripts/probe_si_bisect_i9q8.py
    # list variants:
    PROBE_LIST=1 PYTHONPATH=. python backend/scripts/probe_si_bisect_i9q8.py
    # deliberate AI Studio run (billing NOT on the tracked project):
    VERTEXAI=false GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_si_bisect_i9q8.py

No PII: the only "value" sent is the synthetic A-Number A123456789; tool-call
args are summarized (name + whether field_id/value present), never the value.

Converted to Vertex-default for bd polyglot-pdf-rve5; one-shot diagnostic, NOT
re-verified against live Vertex post-conversion. NOTE: this is a Live-API
(bidiGenerateContent) script -- the Vertex model-id variant may need adjustment
per bd a079.
"""
from __future__ import annotations

import asyncio
import os
import sys

from google import genai

from backend.config import (
    MODEL_NATIVE_PREMIUM,
    MODEL_NATIVE_STANDARD,
    Settings,
)

# Single-field I-90 section, matching probe_tool_call.py so results are comparable.
FIELDS_TEXT = (
    "[1] id='p1_line1_aliennumber' name='Alien Registration Number (A-Number)' "
    "type=text Filled=False"
)
FILL_FORMAT = dict(
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
    next_field_hint=(
        "Alien Registration Number (A-Number) "
        "(field_id: p1_line1_aliennumber, type: text)"
    ),
)


def _full_si() -> str:
    return Settings().SYSTEM_INSTRUCTION.format(**FILL_FORMAT)


# --- Variant ladder -------------------------------------------------------
# Each variant is a function returning the SI string. The KEY question the
# bisect answers: which block, present in `full` but absent in `short`, flips
# update_form_fields from reliable to skipped on 3.1?

# Known-good control: the shortest SI that names the tool + the act-on-answer rule.
SHORT_CONTROL = (
    "You are a helpful form-filling assistant. Speak English.\n"
    "When the user gives you a value for a field, IMMEDIATELY call "
    "update_form_fields with that field_id and value.\n"
    "Current field: id='p1_line1_aliennumber' "
    "name='Alien Registration Number (A-Number)' type=text."
)

# Mid-rung: short control + just the WORKFLOW block from the full SI (numbered
# steps). Tests whether the multi-step workflow narrative (with confirm_field,
# read-back, "wait for verbal confirmation") is what defers the immediate call.
SHORT_PLUS_WORKFLOW = (
    SHORT_CONTROL
    + "\n\nWORKFLOW:\n"
    "1. Ask for ONE field (skip Filled=True)\n"
    "2. User answers -> IMMEDIATELY call update_form_fields with ONE field\n"
    "3. Always read back user provided value and ask 'Is that correct?'\n"
    "4. Wait for verbal confirmation (yes/correct/that's right)\n"
    "5. Call confirm_field tool with confirmation_method='verbal'\n"
    "6. Move to next field (hint provided in confirm_field response)\n"
)

# Ablation A: full SI with the WORKFLOW block removed (does removing the
# confirm-first narrative restore the immediate call?).
def _full_minus_workflow() -> str:
    si = _full_si()
    start = si.find("WORKFLOW:")
    end = si.find("TOOLS:")
    if start == -1 or end == -1:
        raise RuntimeError("could not locate WORKFLOW/TOOLS anchors for ablation")
    return si[:start] + si[end:]


# Ablation B: full SI with the "CRITICAL: ... Never skip confirmation. Never move
# to next field without calling confirm_field." sentence removed -- that line may
# bias the model toward treating confirm_field as the gating action and skipping
# the fill.
def _full_minus_critical() -> str:
    si = _full_si()
    anchor = "CRITICAL: Fields filled by you"
    start = si.find(anchor)
    if start == -1:
        raise RuntimeError("could not locate CRITICAL anchor for ablation")
    end = si.find("\n\n", start)
    if end == -1:
        end = len(si)
    return si[:start] + si[end:]


# Ablation C: full SI but the opening LANGUAGE block stripped (rule out the
# language-detection preamble crowding out the tool directive).
def _full_minus_language() -> str:
    si = _full_si()
    end = si.find("Form assistant:")
    if end == -1:
        raise RuntimeError("could not locate 'Form assistant:' anchor")
    return si[end:]


VARIANTS = {
    "short": lambda: SHORT_CONTROL,
    "short_plus_workflow": lambda: SHORT_PLUS_WORKFLOW,
    "full_minus_workflow": _full_minus_workflow,
    "full_minus_critical": _full_minus_critical,
    "full_minus_language": _full_minus_language,
    "full": _full_si,
}

# Default run order: control first, full last, ablations between (the bisect).
DEFAULT_ORDER = [
    "short",
    "short_plus_workflow",
    "full_minus_workflow",
    "full_minus_critical",
    "full_minus_language",
    "full",
]


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


def _tool_declarations():
    """Return TOOL_DECLARATIONS, optionally OVERRIDING update_form_fields.value's
    type via PROBE_TYPED_VALUE. NOTE: the real config now types `value` "string"
    (the wpw.4 fix has landed), so the default path already carries a typed param
    and PROBE_TYPED_VALUE is a no-op unless you set it to a DIFFERENT type to
    explore. Historically (pre-fix) the live config left `value` UNTYPED, which
    made 3.1 reject the call on google-genai 2.8.0 (it verbalized "I encountered
    an issue processing that value"); this override is how that causation was
    A/B'd. Set PROBE_TYPED_VALUE=string|number|boolean to force a specific type.
    """
    import copy

    decls = copy.deepcopy(Settings().TOOL_DECLARATIONS)
    typed = os.environ.get("PROBE_TYPED_VALUE")
    if typed:
        for d in decls:
            if d["name"] == "update_form_fields":
                d["parameters"]["properties"]["value"]["type"] = typed
    return decls


def _config(si: str) -> dict:
    return {
        "response_modalities": ["AUDIO"],
        "tools": [{"function_declarations": _tool_declarations()}],
        "realtime_input_config": {"automatic_activity_detection": {}},
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "system_instruction": si,
    }


async def _drain(session, stop_on_tool: bool, max_msgs: int = 400):
    """Collect tool calls until a tool call (if stop_on_tool) or turn_complete."""
    tool_calls = []
    count = 0
    try:
        async for msg in session.receive():
            count += 1
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
                        pfc = getattr(p, "function_call", None)
                        if pfc:
                            tool_calls.append({
                                "name": getattr(pfc, "name", None),
                                "args": getattr(pfc, "args", None) or getattr(pfc, "arguments", None),
                            })
                if getattr(sc, "turn_complete", False):
                    break
            if stop_on_tool and tool_calls:
                break
            if count >= max_msgs:
                break
    except Exception as e:
        print(f"    RECEIVE ERROR: {type(e).__name__}: {e}", flush=True)
    return tool_calls


async def _one_run(client, model: str, si: str) -> str:
    """Returns 'update' | 'other:<names>' | 'none' | 'error'."""
    try:
        async with client.aio.live.connect(model=model, config=_config(si)) as session:
            await session.send_realtime_input(
                text="Speak English. Greet the user and ask for the first field."
            )
            await _drain(session, stop_on_tool=False)
            await session.send_realtime_input(
                text="My Alien Registration Number is A123456789."
            )
            calls = await _drain(session, stop_on_tool=True)
            if any(c["name"] == "update_form_fields" for c in calls):
                # Safe shape log: name + which keys present, never the value.
                for c in calls:
                    if c["name"] == "update_form_fields":
                        args = c["args"] or {}
                        keys = sorted(args.keys()) if hasattr(args, "keys") else "?"
                        print(f"      update_form_fields args_keys={keys}", flush=True)
                return "update"
            if calls:
                return "other:" + ",".join(c["name"] or "?" for c in calls)
            return "none"
    except Exception as e:
        print(f"    RUN ERROR: {type(e).__name__}: {e}", flush=True)
        return "error"


async def main():
    if os.environ.get("PROBE_LIST"):
        for name in DEFAULT_ORDER:
            si = VARIANTS[name]()
            print(f"{name:24s} {len(si):5d} chars", flush=True)
        return

    model = os.environ.get("PROBE_MODEL", MODEL_NATIVE_PREMIUM)
    runs = int(os.environ.get("PROBE_RUNS", "3"))
    one = os.environ.get("PROBE_VARIANT")
    order = [one] if one else DEFAULT_ORDER
    client = _client()

    print(f"\n=== SI BISECT (i9q8) model={model} runs={runs} ===", flush=True)
    summary = []
    for name in order:
        if name not in VARIANTS:
            print(f"  unknown variant {name!r}; known: {list(VARIANTS)}", flush=True)
            continue
        si = VARIANTS[name]()
        print(f"\n--- variant '{name}' ({len(si)} chars) ---", flush=True)
        hits = 0
        other = 0
        none = 0
        err = 0
        for i in range(1, runs + 1):
            r = await _one_run(client, model, si)
            print(f"  run {i}: {r}", flush=True)
            if r == "update":
                hits += 1
            elif r == "none":
                none += 1
            elif r == "error":
                err += 1
            else:
                other += 1
        summary.append((name, hits, other, none, err, runs))

    print("\n=== SUMMARY (update_form_fields emission rate) ===", flush=True)
    print(f"  model={model} runs/variant={runs}", flush=True)
    for name, hits, other, none, err, n in summary:
        print(f"  {name:24s} update={hits}/{n}  other={other}  none={none}  err={err}",
              flush=True)


if __name__ == "__main__":
    asyncio.run(main())
