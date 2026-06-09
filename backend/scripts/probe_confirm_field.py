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
  - detects confirm_field on BOTH the verify-question turn AND the post-"yes"
    turn, recording WHEN it fired (early vs post_yes) and with what field_id.

FINDING (5/5 runs total, 2.5 native-audio): H1 is REJECTED, H2 is supported.
confirm_field fires RELIABLY (5/5) -- the model is NOT skipping the tool call.
WHEN it fires VARIES run to run: sometimes EARLY, on the verify-question turn,
right after Gemini speaks "Is <value> correct?" and BEFORE the "yes" is injected
(2.5 confirming the value proactively/optimistically); other runs it fires on the
post-"yes" turn (the textbook flow). Either way it DOES fire. So the live g8w
harness reports FLAKY not because confirm_field never fires, but because its
observation window is too narrow: it only watches ssConfirmed AFTER injecting
"yes", so on an EARLY-confirm run it can miss the confirm that already landed (or
the early confirm races its fill/verify waits). The fix is in the HARNESS
observation/timing (watch ssConfirmed from the verify turn onward, not only after
"yes"), NOT in the prompt or model -- filed as bd polyglot-pdf-tfz. SECONDARY
FINDING: native-audio turns after a tool response do NOT reliably deliver a clean
turn_complete here -- drained turns hit the wall-clock timeout; that is why
_drain is deadline-bounded (an unbounded receive hangs) and closes its iterator.

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
    """Pull the id/name/args off a function_call object (mirrors probe_tool_call_id).

    PII: tool-call args carry the user's field VALUE (e.g. update_form_fields
    {value: ...}). Backend print() reaches stdout -> logs, so the no-PII rule
    applies (Codex PR #126; same class as bd polyglot-pdf-oeq). We KEEP args in
    the returned dict (the in-process tally needs field_id), but the PRINTED line
    logs only the safe shape: tool name, id, field_id, and the VALUE's length --
    never the value itself.
    """
    args = getattr(fc, "args", None)
    args_dict = dict(args) if args else {}
    info = {
        "path": path,
        "name": getattr(fc, "name", None),
        "id": getattr(fc, "id", None),
        "args": args_dict,
    }
    value = args_dict.get("value")
    value_len = len(str(value)) if value is not None else 0
    print(
        "  [tool_call] path={path} name={name!r} id={id!r} field_id={fid!r} "
        "value_len={vlen}".format(
            path=path, name=info["name"], id=info["id"],
            fid=args_dict.get("field_id"), vlen=value_len
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
    char_count = 0
    timed_out = False
    # Close the per-turn iterator in a finally (Codex/fresh-eyes PR #126): on a
    # timeout we break out with `it` still open, and a leaked receive iterator can
    # buffer/eat messages destined for the NEXT _drain's fresh iterator -- which,
    # since every turn here times out, is the COMMON path, not an edge case.
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
                    # PII: the output transcript repeats the user's field value
                    # (e.g. "Is A123456789 correct?"). Count chars for the
                    # spoke/length signal -- NEVER store or print the text itself
                    # (Codex PR #126; no-transcript-logging rule).
                    char_count += len(ot.text)
                if getattr(sc, "turn_complete", False):
                    break
            if count >= max_msgs:
                print(f"  [{label}] hit max_msgs without turn_complete", flush=True)
                break
    except Exception as e:
        print(f"  [{label}] RECEIVE ERROR: {type(e).__name__}: {e}", flush=True)
    finally:
        try:
            await it.aclose()
        except Exception:
            pass
    spoke = char_count > 0
    if spoke:
        print(f"  [{label}] spoke a turn ({char_count} transcript chars, redacted)", flush=True)
    return {"calls": found, "timed_out": timed_out, "spoke": spoke}


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
            return {"update_called": False, "confirm_called": False,
                    "confirm_when": None, "verify_spoken": False}

        # Reply to the fill so Gemini proceeds to the verify question.
        await _send_tool_responses(session, update_calls, _update_payload)

        # Gemini's verify-question turn ("Is that correct?"). 2.5 PROACTIVELY
        # calls confirm_field HERE -- during/just after the verify question,
        # BEFORE the "yes" is sent (the whole par finding). So we must look for
        # confirm_field on THIS turn, not only after "yes" (Codex PR #126: a
        # post-yes-only tally reports 0 and contradicts the finding).
        verify = await _drain(session, "verify-question")
        verify_confirm = [c for c in verify["calls"] if c["name"] == "confirm_field"]
        if verify_confirm:
            await _send_tool_responses(session, verify_confirm, _confirm_payload)

        # The user confirms. If 2.5 did NOT confirm early, a well-behaved model
        # confirms HERE; if it already confirmed early, this turn usually just
        # acknowledges/advances. We still drain it and detect any confirm_field.
        await session.send_realtime_input(text="Yes, that is correct.")
        post_yes = await _drain(session, "post-yes")
        post_yes_confirm = [c for c in post_yes["calls"] if c["name"] == "confirm_field"]
        if post_yes_confirm:
            await _send_tool_responses(session, post_yes_confirm, _confirm_payload)

        # Confirm fired if it landed on EITHER turn; record WHEN (early vs post-yes)
        # so the summary can describe the proactive-confirm behavior, not just a
        # boolean. "early" is the par finding; "post_yes" is the textbook flow.
        if verify_confirm:
            confirm_when = "early"
        elif post_yes_confirm:
            confirm_when = "post_yes"
        else:
            confirm_when = None
        first_confirm = (verify_confirm or post_yes_confirm or [None])[0]

        return {
            "update_called": True,
            "confirm_called": confirm_when is not None,
            "confirm_when": confirm_when,
            "confirm_field_id": first_confirm["args"].get("field_id") if first_confirm else None,
            # Did Gemini actually ASK the verify question? If she spoke a verify
            # turn and STILL did not call confirm_field on either turn, that is the
            # cleanest H1 (model-skips-the-tool-call) evidence.
            "verify_spoken": verify["spoke"],
            "post_yes_spoken": post_yes["spoke"],
        }


async def main():
    model = os.environ.get("PROBE_MODEL", MODEL_NATIVE_STANDARD)
    runs = int(os.environ.get("PROBE_RUNS", "1"))
    print(f"\n=== MODEL: {model} (AI Studio) -- {runs} run(s) ===", flush=True)
    client = _client()

    completed = 0  # runs that did not raise
    update_hits = 0
    confirm_hits = 0
    early_hits = 0  # confirm fired on the verify turn (the par finding)
    post_yes_hits = 0  # confirm fired only after "yes" (textbook flow)
    verify_spoken_hits = 0
    for i in range(1, runs + 1):
        try:
            r = await _one_run(client, model, i)
        except Exception as e:
            print(f"  run {i} ERROR: {type(e).__name__}: {e}", flush=True)
            continue
        completed += 1
        if r["update_called"]:
            update_hits += 1
        if r["confirm_called"]:
            confirm_hits += 1
            if r.get("confirm_when") == "early":
                early_hits += 1
            elif r.get("confirm_when") == "post_yes":
                post_yes_hits += 1
        if r.get("verify_spoken"):
            verify_spoken_hits += 1

    print("\n=== SUMMARY ===", flush=True)
    print(f"  runs completed (no error):   {completed}/{runs}", flush=True)
    print(f"  update_form_fields fired:    {update_hits}/{runs}", flush=True)
    print(f"  verify question spoken:      {verify_spoken_hits}/{runs}", flush=True)
    print(f"  CONFIRM_FIELD_CALLED:        {confirm_hits}/{runs}", flush=True)
    print(f"    - early (verify turn):     {early_hits}/{runs}", flush=True)
    print(f"    - post-yes:                {post_yes_hits}/{runs}", flush=True)
    if update_hits == 0:
        # F5 (fresh-eyes PR #126): distinguish a SETUP failure (fill never fires,
        # so there is nothing to confirm) from a real H1 signal. No verdict is
        # possible here -- do not let silence read as "model is clean".
        print("  >>> update_form_fields NEVER fired -- NO VERDICT. The fill path is "
              "the precondition for the confirm probe; check the model name, system "
              "instruction, and key before reading anything into the confirm tally.", flush=True)
    elif confirm_hits == 0:
        print("  >>> Fill works but confirm_field NEVER fired (on EITHER the verify "
              "turn or post-yes) even with clean sequencing -- supports H1 (model "
              "skips the confirm tool call). Same class as "
              "gemini-3p1-skips-update-form-fields.", flush=True)
    elif confirm_hits == update_hits:
        extra = (" -- and it fires EARLY (on the verify turn, before the 'yes'), "
                 "which is the par finding: the live harness only watches AFTER "
                 "injecting 'yes' and misses the early confirm." if early_hits else "")
        print("  >>> confirm_field fires reliably when the turn is cleanly sequenced "
              "-- so the model CAN do it; the live-harness FLAKY points at H2 (the "
              "'yes' injection mis-times the verify turn). Fix lives in the harness."
              + extra, flush=True)
    else:
        print("  >>> mixed/partial -- confirm_field is flaky even with clean "
              "sequencing; capture more runs.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
