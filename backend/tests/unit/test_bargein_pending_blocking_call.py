"""Barge-in while a BLOCKING tool call is pending (bd polyglot-pdf-dakii).

On gemini-3.8-live every declaration is behavior=BLOCKING. When the user presses
push-to-talk while a call is still unanswered, the server sends `interrupted`
and `turn_complete` on ONE message, sends no tool_call_cancellation, and then --
once the barge audio ends -- transcribes it and issues a NEW call for the
corrected value (Vertex, 2026-11-18: scripts/spikes/data/r3ham/dakii/).

google-genai 2.8.0 `AsyncSession.receive()` ENDS its iterator after every
`turn_complete`. A reader that iterates receive() once therefore goes deaf at
the barge's interrupt -- that is exactly what made the r3ham.4 probe report a
"wedged session" 3 of 3 times. The production adapter re-enters receive() per
turn; these tests pin that, with a fake session whose receive() reproduces the
SDK's per-turn iterator shape, so a loop that stops re-entering goes red.

ASCII only (CLAUDE.md scar #6).
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _sc(**fields):
    sc = SimpleNamespace(
        interrupted=False,
        model_turn=None,
        input_transcription=None,
        output_transcription=None,
        turn_complete=False,
        generation_complete=False,
    )
    for k, v in fields.items():
        setattr(sc, k, v)
    return sc


def _tool_call_msg(call_id, name, args):
    fc = SimpleNamespace(name=name, id=call_id, arguments=json.dumps(args))
    return SimpleNamespace(data=None, server_content=None, usage_metadata=None,
                           tool_call=SimpleNamespace(function_calls=[fc]))


def _sc_msg(**fields):
    return SimpleNamespace(data=None, server_content=_sc(**fields), tool_call=None,
                           usage_metadata=None)


class _PerTurnSession:
    """Fake Live session whose receive() mirrors google-genai 2.8.0: each call
    returns a FRESH iterator that yields one turn's messages and STOPS after the
    message carrying turn_complete. Once the scripted turns run out, receive()
    returns an empty iterator (the adapter's no-events exit)."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.sent_responses = []

    async def send_realtime_input(self, **_kwargs):
        return None

    async def send_client_content(self, **_kwargs):
        return None

    async def send_tool_response(self, *, function_responses):
        self.sent_responses.extend(function_responses)

    def receive(self):
        turn = self._turns.pop(0) if self._turns else []

        async def gen():
            for msg in turn:
                sc = getattr(msg, "server_content", None)
                if sc is not None and getattr(sc, "turn_complete", False):
                    yield msg
                    return
                yield msg
        return gen()


class _Ctx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_exc):
        return False


def _barge_turns():
    """The measured 3.8 sequence: call A pending -> barge (interrupted +
    turn_complete together, no cancellation) -> NEW call B with the corrected
    value -> the next turn's confirm_field."""
    return [
        [
            _tool_call_msg("fc-A", "update_form_fields",
                           {"field_id": "foreign_tax_id_number", "value": "AAA"}),
            _sc_msg(interrupted=True, turn_complete=True),
        ],
        [
            _tool_call_msg("fc-B", "update_form_fields",
                           {"field_id": "foreign_tax_id_number", "value": "BBB"}),
            _sc_msg(turn_complete=True),
        ],
        [
            _tool_call_msg("fc-C", "confirm_field",
                           {"field_id": "foreign_tax_id_number",
                            "confirmation_method": "verbal"}),
            _sc_msg(turn_complete=True),
        ],
    ]


async def _run(turns, tool_delay=0.0):
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter._audio_queue = asyncio.Queue()
    adapter._text_queue = asyncio.Queue()

    calls = []
    interrupts = []

    async def on_tool_call(name, args):
        calls.append((name, dict(args)))
        if tool_delay:
            await asyncio.sleep(tool_delay)  # a slow tool (ask_secretary, spell-back)
        return {"success": True}

    async def on_interrupted():
        interrupts.append(True)

    adapter._on_tool_call = on_tool_call
    adapter._on_interrupted = on_interrupted

    session = _PerTurnSession(turns)
    fake_live = MagicMock()
    fake_live.connect.return_value = _Ctx(session)
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    await asyncio.wait_for(adapter._run_session_loop(), timeout=2.0)
    await adapter.finalize()
    return calls, session.sent_responses, interrupts


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_delay", [0.0, 0.05])
async def test_session_keeps_serving_turns_after_barge_during_pending_call(tool_delay):
    calls, responses, interrupts = await _run(_barge_turns(), tool_delay)

    # The barge's interrupt is forwarded once (the client flushes playback).
    assert interrupts == [True]
    # The loop did NOT go deaf at the interrupt's turn_complete: the corrected
    # call AND the next turn's confirm were both dispatched, in order.
    assert [c[0] for c in calls] == [
        "update_form_fields", "update_form_fields", "confirm_field"]
    assert [c[1].get("value") for c in calls[:2]] == ["AAA", "BBB"]
    # Every call id is answered exactly once -- the pending call A included
    # (3.8 sent no cancellation, so it still expects its response).
    assert [r.id for r in responses] == ["fc-A", "fc-B", "fc-C"]


@pytest.mark.asyncio
async def test_last_write_is_the_corrected_value():
    """Field-state consistency: the client applies writes in dispatch order, so
    the value the model reads back (the corrected one) is the last one written."""
    calls, _responses, _ = await _run(_barge_turns())
    writes = [a.get("value") for n, a in calls if n == "update_form_fields"]
    assert writes[-1] == "BBB"
