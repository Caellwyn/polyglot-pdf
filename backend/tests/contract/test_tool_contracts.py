"""Tool-call SEQUENCE contract regressions (epic wpw WS-A / bd polyglot-pdf-8k8;
extends the uov.14 tool-contract home).

The standalone probes (backend/scripts/probe_tool_call.py,
probe_confirm_field.py) A/B 2.5 vs 3.1 and tally tool-call PRESENCE + confirm
TIMING, but they never assert the ORDER the tools must fire in. This module
promotes that probe logic into marked-external pytest regressions that assert the
core demo invariant: for a single field, the model emits update_form_fields
(fill) and THEN confirm_field (verify), in that order -- the two-call path the
maintainer's confirm policy keeps separate (no fill_and_confirm collapse).

These are @pytest.mark.external (real Gemini): the default `pytest -m "not
external"` run skips them, and they self-skip when GEMINI_API_KEY is unset --
mirroring test_live_ai_gemini_integration.py. Run on demand with a key:

    GEMINI_API_KEY=... PYTHONPATH=. python -m pytest backend/tests/contract/test_tool_contracts.py -m external

Model A/B: gemini-3.8-live is the demo default. BOTH models now emit both
calls reliably and are gated -- the historic "3.1 skips update_form_fields ~50%"
(bd polyglot-pdf-5oq) was the UNTYPED update_form_fields.value param rejected
under google-genai 2.8.0, not a model regression; typing it "string" fixed 3.1
(bd polyglot-pdf-wpw.4), so 3.1 is no longer xfail'd here.

PII: tool-call args carry the user's field VALUE. As in the probes, we keep
field_id/name for the in-process assertions but NEVER print the value (no-PII
rule, bd polyglot-pdf-oeq).
"""
from __future__ import annotations

import asyncio
import os

import pytest

from backend.config import MODEL_NATIVE_PREMIUM, MODEL_NATIVE_STANDARD, Settings, model_family

pytestmark = pytest.mark.external

# Reuse the I-90 first-field scenario the probes pinned (a single text A-Number
# field in section 1) so this contract test exercises the same path the demo does.
FIELD_ID = "p1_line1_aliennumber"
FIELDS_TEXT = (
    "[1] id='p1_line1_aliennumber' name='Alien Registration Number (A-Number)' "
    "type=text Filled=False"
)


def _require_genai():
    """Import the SDK lazily so a missing dep skips (not errors) the external run."""
    try:
        from google import genai
        from google.genai import types
        return genai, types
    except Exception as exc:  # pragma: no cover - only on a broken external env
        pytest.skip(f"google-genai SDK unavailable: {exc}")


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
        next_field_hint=(
            "Alien Registration Number (A-Number) "
            "(field_id: p1_line1_aliennumber, type: text)"
        ),
    )


def _config(model: str) -> dict:
    s = Settings()
    decls = [dict(d) for d in s.TOOL_DECLARATIONS]
    # Mirror LiveAIGemini._build_live_config: 3.8 defaults tools to NON_BLOCKING,
    # so production sends every declaration BLOCKING on that family (bd
    # polyglot-pdf-bd1zs). Without it this test would gate a config the app never sends.
    if model_family(model) == "3.8":
        for d in decls:
            d["behavior"] = "BLOCKING"
    return {
        "response_modalities": ["AUDIO"],
        "tools": [{"function_declarations": decls}],
        "realtime_input_config": {"automatic_activity_detection": {}},
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "system_instruction": _system_instruction(),
    }


def _calls_in(msg) -> list:
    """Pull function-call (name, id, field_id) dicts off a single live message,
    from BOTH delivery paths (event.tool_call and model_turn.parts). The value is
    deliberately dropped -- never logged (no-PII)."""
    out = []

    def _record(fc):
        args = getattr(fc, "args", None)
        args_dict = dict(args) if args else {}
        out.append({
            "name": getattr(fc, "name", None),
            "id": getattr(fc, "id", None),
            "field_id": args_dict.get("field_id"),
        })

    tc = getattr(msg, "tool_call", None)
    if tc and getattr(tc, "function_calls", None):
        for fc in tc.function_calls:
            _record(fc)
    sc = getattr(msg, "server_content", None)
    if sc is not None:
        mt = getattr(sc, "model_turn", None)
        if mt and getattr(mt, "parts", None):
            for p in mt.parts:
                pfc = getattr(p, "function_call", None)
                if pfc:
                    _record(pfc)
    return out


async def _drain(session, max_msgs: int = 400, turn_timeout: float = 30.0):
    """Drain one turn: collect every tool call until turn_complete or a wall-clock
    timeout. Deadline-bounded because native-audio turns do not always deliver a
    clean turn_complete after a tool response (an unbounded receive would hang).
    The per-turn iterator is closed in a finally so a leaked iterator can't eat the
    next turn's messages (the common path here, since turns routinely time out --
    Codex/fresh-eyes PR #126)."""
    found = []
    count = 0
    it = session.receive().__aiter__()
    try:
        while True:
            try:
                msg = await asyncio.wait_for(it.__anext__(), timeout=turn_timeout)
            except asyncio.TimeoutError:
                break
            except StopAsyncIteration:
                break
            count += 1
            found.extend(_calls_in(msg))
            sc = getattr(msg, "server_content", None)
            if sc is not None and getattr(sc, "turn_complete", False):
                break
            if count >= max_msgs:
                break
    finally:
        try:
            await it.aclose()
        except Exception:
            pass
    return found


async def _send_tool_responses(session, types, calls, payload):
    responses = []
    for c in calls:
        kwargs = {"name": c["name"], "response": payload}
        if c["id"]:
            kwargs["id"] = c["id"]
        responses.append(types.FunctionResponse(**kwargs))
    if responses:
        await session.send_tool_response(function_responses=responses)


async def _drive_fill_then_confirm(model: str) -> dict:
    """Drive greeting -> answer -> verify -> "yes" and return the ORDERED tool-call
    stream plus per-turn breakdown. Mirrors probe_confirm_field._one_run's flow."""
    genai, types = _require_genai()
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    # Ordered (name, field_id) across all turns. Keeping field_id lets the
    # assertions verify the call was for the RIGHT field, not just that SOME
    # update/confirm fired (Codex/fresh-eyes PR #133: a tool call for the wrong
    # field must not satisfy the contract).
    stream = []
    update_calls = []
    confirm_early = []
    confirm_post_yes = []

    def _is(name, c):
        return c["name"] == name and c["field_id"] == FIELD_ID

    async with client.aio.live.connect(model=model, config=_config(model)) as session:
        await session.send_realtime_input(
            text="Speak English. Greet the user and ask for the first field."
        )
        for c in await _drain(session):
            stream.append((c["name"], c["field_id"]))

        await session.send_realtime_input(
            text="My Alien Registration Number is A123456789."
        )
        answer = await _drain(session)
        for c in answer:
            stream.append((c["name"], c["field_id"]))
        update_calls = [c for c in answer if _is("update_form_fields", c)]
        if update_calls:
            await _send_tool_responses(
                session, types, update_calls,
                {"status": "success", "field_id": FIELD_ID,
                 "message": "Field filled. Ask the user to confirm."},
            )

        # 2.5 often confirms PROACTIVELY on the verify turn, before "yes" -- so we
        # look for confirm_field here AND post-yes (order-tolerant, the par finding).
        verify = await _drain(session)
        for c in verify:
            stream.append((c["name"], c["field_id"]))
        confirm_early = [c for c in verify if _is("confirm_field", c)]
        if confirm_early:
            await _send_tool_responses(
                session, types, confirm_early,
                {"status": "success", "field_id": FIELD_ID, "confirmed": True},
            )

        await session.send_realtime_input(text="Yes, that is correct.")
        post_yes = await _drain(session)
        for c in post_yes:
            stream.append((c["name"], c["field_id"]))
        confirm_post_yes = [c for c in post_yes if _is("confirm_field", c)]
        if confirm_post_yes:
            await _send_tool_responses(
                session, types, confirm_post_yes,
                {"status": "success", "field_id": FIELD_ID, "confirmed": True},
            )

    confirm_when = "early" if confirm_early else ("post_yes" if confirm_post_yes else None)
    return {
        "stream": stream,
        "update_called": bool(update_calls),
        "confirm_called": confirm_when is not None,
        "confirm_when": confirm_when,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model",
    [
        MODEL_NATIVE_STANDARD,
        # 3.1 emits update_form_fields reliably as long as the value param is
        # typed "string" (bd polyglot-pdf-wpw.4) -- an untyped value param makes
        # it skip the call ~50% of the time. A real gate for both models.
        MODEL_NATIVE_PREMIUM,
    ],
    ids=["3.8-standard", "3.1-premium"],
)
async def test_update_then_confirm_sequence(model):
    """The demo invariant: the model fills (update_form_fields) and THEN confirms
    (confirm_field) FOR THE SAME FIELD, in that order. Asserts the SEQUENCE the
    probes only tallied: a update_form_fields for FIELD_ID must appear, a
    confirm_field for FIELD_ID must appear, and the first such update must precede
    the first such confirm in the tool-call stream. Filtering on FIELD_ID means a
    tool call for the wrong field cannot satisfy the contract (PR #133)."""
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY is not configured")

    result = await _drive_fill_then_confirm(model)
    stream = result["stream"]  # list of (name, field_id)

    assert result["update_called"], (
        f"model {model} never emitted update_form_fields for {FIELD_ID} on the "
        f"answer turn (tool stream: {stream})"
    )
    assert result["confirm_called"], (
        f"model {model} never emitted confirm_field for {FIELD_ID} on the verify "
        f"or post-yes turn (tool stream: {stream})"
    )

    # Index on the (name, field_id) pair so an update/confirm for ANOTHER field
    # cannot be mistaken for the target's. The guard asserts above guarantee both
    # are present, so .index never raises here.
    first_update = stream.index(("update_form_fields", FIELD_ID))
    first_confirm = stream.index(("confirm_field", FIELD_ID))
    assert first_update < first_confirm, (
        f"update_form_fields must precede confirm_field for {FIELD_ID} (fill "
        f"before verify); got stream {stream} "
        f"(update@{first_update}, confirm@{first_confirm})"
    )
