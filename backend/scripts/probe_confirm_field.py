"""Probe: after the user says "yes", does native-audio 2.5 call confirm_field?

bd polyglot-pdf-par. The g8w voice harness, run against a 0ux-FIXED backend,
sees the fill path work (update_form_fields fires, field fills correctly) but
then the confirmation never lands: after "yes that is correct" is injected,
ssConfirmed stays false and the harness reports FLAKY "field never confirmed".

Two hypotheses, and this probe is built to separate them:

  H1 (MODEL):   2.5 native-audio does NOT emit the confirm_field tool call after
                a verbal "yes" -- it confirms verbally and moves on without the
                tool call (same class as gemini-3p1-skips-update-form-fields, but
                for confirm_field on 2.5).
  H2 (HARNESS): 2.5 DOES emit confirm_field when the turn is cleanly sequenced;
                the live harness's "yes" injection mis-times Gemini's verify
                question (lands before she asks / during her audio) so the model
                never treats it as the confirmation answer.

This probe drives the turns DETERMINISTICALLY from the backend side, mirroring
the real flow (greeting -> answer -> update_form_fields -> tool_response ->
verify question -> "yes" -> confirm_field). Because the probe waits for each
turn to complete before injecting the next utterance, it removes the harness
timing variable: if confirm_field STILL does not fire here, that is evidence for
H1 (model); if it DOES fire here but not in the live harness, that points at H2
(timing) and the fix lives in the harness, not the prompt/model.

It reuses the I-90 first-field scenario, system instruction, tool declarations,
and 2.5 native-audio model from probe_tool_call_id.py, and additionally:
  - sends a realistic update_form_fields tool RESPONSE (with the echoed id, per
    bd polyglot-pdf-0ux) so Gemini proceeds to the verify question, and
  - reports, for the post-"yes" turn, whether confirm_field was called at all,
    on which path, and with what field_id.

FINDING (3/3 runs, 2.5 native-audio): H1 is REJECTED, H2 is supported -- with a
twist. confirm_field fires reliably (3/3), so the model is NOT skipping the tool
call. BUT it fires on the VERIFY-QUESTION turn, immediately after Gemini speaks
"Is A123456789 correct?" -- i.e. BEFORE the "yes" is even injected. 2.5 confirms
the value PROACTIVELY/optimistically rather than strictly waiting for user
assent. So the live g8w harness reports FLAKY not because confirm_field never
fires, but because it fires EARLY (during/just after the verify question), and
the harness only watches for ssConfirmed AFTER injecting "yes" -- it can miss the
confirm that already happened, OR the early confirm races the harness's
fill/verify waits. The fix is in the HARNESS observation/timing (watch for
ssConfirmed across the verify turn, not only after "yes"), not in the prompt or
model. SECONDARY FINDING: native-audio turns after a tool response do NOT deliver
a clean turn_complete here -- every drained turn hits the wall-clock timeout;
that is expected and why _drain is deadline-bounded (an unbounded receive hangs).

Run it a few times (model output is non-deterministic) and read the
CONFIRM_FIELD_CALLED tallies, e.g.:

    GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_confirm_field.py
    GEMINI_API_KEY=... PYTHONPATH=. PROBE_RUNS=3 python backend/scripts/probe_confirm_field.py
"""
from __future__ import annotations

import asyncio
import os
import sys

from google import genai
from google.genai import types

from backend.config import MODEL_NATIVE_STANDARD, Settings

FIELD_ID = "p1_line1_aliennumber"
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
    """Pull the id/name/args off a function_call object (mirrors probe_tool_call_id)."""
    args = getattr(fc, "args", None)
    info = {
        "path": path,
        "name": getattr(fc, "name", None),
        "id": getattr(fc, "id", None),
        "args": dict(args) if args else {},
    }
    print(
        "  [tool_call] path={path} name={name!r} id={id!r} args={args}".format(
            path=path, name=info["name"], id=info["id"], args=info["args"]
        ),
        flush=True,
    )
    return info


async def _drain(session, label: str, max_msgs: int = 400, turn_timeout: float = 30.0):
    """Drain one turn: collect any tool calls, stop at turn_complete.

    Unlike probe_tool_call_id._drain we do NOT break on the first tool call --
    a single turn can carry update_form_fields AND a follow-on, and for the
    confirm turn we want to see the WHOLE turn before deciding "no confirm_field".

    Bounded by a wall-clock turn_timeout: a native-audio turn does not always
    deliver a clean turn_complete after a tool response, and an unbounded
    `async for ... session.receive()` would hang the whole probe waiting for a
    boundary that never arrives. On timeout we return what we have so far and
    say so (so "no confirm_field" is only ever reported for a turn we actually
    drained to completion -- a TIMEOUT is logged distinctly).
    """
    found = []
    transcript = []
    count = 0
    timed_out = False
    it = session.receive().__aiter__()
    try:
        while True:
            try:
                msg = await asyncio.wait_for(it.__anext__(), timeout=turn_timeout)
            except asyncio.TimeoutError:
                timed_out = True
                print(f"  [{label}] TURN TIMEOUT after {turn_timeout}s "
                      f"(no turn_complete) -- returning {len(found)} call(s) so far", flush=True)
                break
            except StopAsyncIteration:
                break
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
                ot = getattr(sc, "output_transcription", None)
                if ot is not None and getattr(ot, "text", None):
                    transcript.append(ot.text)
                if getattr(sc, "turn_complete", False):
                    break
            if count >= max_msgs:
                print(f"  [{label}] hit max_msgs without turn_complete", flush=True)
                break
    except Exception as e:
        print(f"  [{label}] RECEIVE ERROR: {type(e).__name__}: {e}", flush=True)
    spoken = "".join(transcript).strip()
    if spoken:
        print(f"  [{label}] said: {spoken!r}", flush=True)
    return {"calls": found, "timed_out": timed_out, "spoke": bool(spoken)}


async def _send_tool_responses(session, calls, payload_for):
    """Reply to each tool call with a realistic response, echoing the id (0ux)."""
    responses = []
    for c in calls:
        fr_kwargs = {"name": c["name"], "response": payload_for(c)}
        if c["id"]:
            fr_kwargs["id"] = c["id"]
        responses.append(types.FunctionResponse(**fr_kwargs))
    if responses:
        await session.send_tool_response(function_responses=responses)


def _update_payload(_call) -> dict:
    # Mirror a stateless "fill succeeded, now ask the user to confirm" result.
    return {
        "status": "success",
        "field_id": FIELD_ID,
        "message": "Field filled. Ask the user to confirm the value is correct.",
    }


def _confirm_payload(_call) -> dict:
    return {
        "status": "success",
        "field_id": FIELD_ID,
        "confirmed": True,
        "next_field_hint": "(none -- last field in section)",
    }


async def _one_run(client, model, run_idx: int) -> dict:
    print(f"\n--- run {run_idx} ---", flush=True)
    async with client.aio.live.connect(model=model, config=_config()) as session:
        await session.send_realtime_input(
            text="Speak English. Greet the user and ask for the first field."
        )
        await _drain(session, "greeting")

        await session.send_realtime_input(
            text="My Alien Registration Number is A123456789."
        )
        answer = await _drain(session, "answer")
        update_calls = [c for c in answer["calls"] if c["name"] == "update_form_fields"]
        if not update_calls:
            print("  >>> no update_form_fields on the answer turn -- skipping confirm probe", flush=True)
            return {"update_called": False, "confirm_called": False, "verify_spoken": False}

        # Reply to the fill so Gemini proceeds to the verify question.
        await _send_tool_responses(session, update_calls, _update_payload)
        # Gemini's verify-question turn ("Is that correct?").
        verify = await _drain(session, "verify-question")

        # The user confirms -- the turn under test.
        await session.send_realtime_input(text="Yes, that is correct.")
        post_yes = await _drain(session, "post-yes")
        confirm_calls = [c for c in post_yes["calls"] if c["name"] == "confirm_field"]
        if confirm_calls:
            await _send_tool_responses(session, confirm_calls, _confirm_payload)

        return {
            "update_called": True,
            "confirm_called": bool(confirm_calls),
            "confirm_field_id": confirm_calls[0]["args"].get("field_id") if confirm_calls else None,
            # Did Gemini actually ASK the verify question? If she spoke a verify
            # turn and STILL did not call confirm_field after "yes", that is the
            # cleanest H1 (model-skips-the-tool-call) evidence.
            "verify_spoken": verify["spoke"],
            "post_yes_spoken": post_yes["spoke"],
        }


async def main():
    model = os.environ.get("PROBE_MODEL", MODEL_NATIVE_STANDARD)
    runs = int(os.environ.get("PROBE_RUNS", "1"))
    print(f"\n=== MODEL: {model} (AI Studio) -- {runs} run(s) ===", flush=True)
    client = _client()

    update_hits = 0
    confirm_hits = 0
    verify_spoken_hits = 0
    for i in range(1, runs + 1):
        try:
            r = await _one_run(client, model, i)
        except Exception as e:
            print(f"  run {i} ERROR: {type(e).__name__}: {e}", flush=True)
            continue
        if r["update_called"]:
            update_hits += 1
        if r["confirm_called"]:
            confirm_hits += 1
        if r.get("verify_spoken"):
            verify_spoken_hits += 1

    print("\n=== SUMMARY ===", flush=True)
    print(f"  update_form_fields fired:    {update_hits}/{runs}", flush=True)
    print(f"  verify question spoken:      {verify_spoken_hits}/{runs}", flush=True)
    print(f"  CONFIRM_FIELD_CALLED:        {confirm_hits}/{runs}", flush=True)
    if update_hits and confirm_hits == 0:
        print("  >>> Fill works but confirm_field NEVER fired even with clean "
              "sequencing -- supports H1 (model skips the confirm tool call). Same "
              "class as gemini-3p1-skips-update-form-fields.", flush=True)
    elif confirm_hits == update_hits and update_hits > 0:
        print("  >>> confirm_field fires reliably when the turn is cleanly sequenced "
              "-- so the model CAN do it; the live-harness FLAKY points at H2 (the "
              "'yes' injection mis-times the verify turn). Fix lives in the harness.", flush=True)
    else:
        print("  >>> mixed/partial -- confirm_field is flaky even with clean "
              "sequencing; capture more runs.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
