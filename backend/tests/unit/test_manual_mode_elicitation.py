"""Manual mode suppresses the model's proactive speech (bd polyglot-pdf-wurj8).

Manual mode is the sticky half of the two-control voice UI. Its promise is
narrow and load-bearing: while it is on, the model neither speaks nor elicits,
but the SESSION STAYS LIVE and the mic stays usable, so the assistant is
correctly oriented the instant the user wants it.

WHY THE GATE IS AT THE ADAPTER, which is what these tests actually pin. Every
text turn this app sends carries turn_complete=True -- it ASKS the model to
respond. So a client-side speaker mute (the pause() this replaces) leaves the
model talking into a discarded buffer: billed, unheard, and then waiting on an
answer to a question the user never received. Dropping the turn before it
reaches Gemini is the only place that makes manual mode genuinely silent AND
free.

The tests drive LiveAIGemini's two elicitation entry points directly:
  - send_text_message  (queued hints: next-field guidance, manual-edit notices)
  - send_client_content (direct "speak now": disclaimer, initiating message,
                         secretary answers, validator steers)
and assert what must NOT happen (no turn reaches the session/queue) alongside
what must still happen (audio and the user's own turn signals flow, and context
is not LOST -- it is replayed on unmute).
"""

import asyncio

import pytest

from backend.adapters.live_ai_gemini import LiveAIGemini


class _RecordingSession:
    """Fake Gemini session recording the text turns it is asked to send."""

    def __init__(self):
        self.text_turns = []
        self.activity_starts = 0
        self.activity_ends = 0

    async def send_client_content(self, **kwargs):
        turns = kwargs.get("turns") or {}
        for part in turns.get("parts", []):
            self.text_turns.append(part.get("text"))

    async def send_realtime_input(self, **kwargs):
        if "text" in kwargs:
            self.text_turns.append(kwargs["text"])
        if kwargs.get("activity_start") is not None:
            self.activity_starts += 1
        if kwargs.get("activity_end") is not None:
            self.activity_ends += 1


def _make_adapter():
    """An adapter wired far enough to exercise the two elicitation paths."""
    adapter = LiveAIGemini(api_key="test_key")
    adapter._text_queue = asyncio.Queue(maxsize=100)
    adapter._session_ready = True
    adapter._current_session = _RecordingSession()
    return adapter


def _drain(queue):
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


@pytest.mark.asyncio
async def test_voice_mode_lets_both_elicitation_paths_through():
    """Baseline: with manual mode OFF, nothing is suppressed.

    Without this arm the suppression tests below could pass on an adapter that
    never delivers anything at all.
    """
    adapter = _make_adapter()

    await adapter.send_text_message("next field is date of birth")
    delivered = await adapter.send_client_content("say hello")

    assert _drain(adapter._text_queue) == ["next field is date of birth"]
    assert delivered is True
    assert adapter._current_session.text_turns == ["say hello"]


@pytest.mark.asyncio
async def test_manual_mode_holds_queued_hints():
    """send_text_message must not reach the send queue while muted."""
    adapter = _make_adapter()
    adapter.set_voice_muted(True)

    await adapter.send_text_message("next field is date of birth")

    assert _drain(adapter._text_queue) == []


@pytest.mark.asyncio
async def test_manual_mode_holds_direct_speak_turns():
    """send_client_content -- the explicit 'make it talk' path -- is suppressed.

    It must also report NOT-DELIVERED. Callers already treat False as "this was
    never voiced" (a queued or failed send returns False too), and one of them --
    the validator steer -- HOLDS the section on a delivered steer. A held turn
    reported as delivered would trap the user waiting on speech that never came.
    """
    adapter = _make_adapter()
    adapter.set_voice_muted(True)

    delivered = await adapter.send_client_content("say hello")

    assert delivered is False
    assert adapter._current_session.text_turns == []


@pytest.mark.asyncio
async def test_manual_mode_does_not_block_the_users_own_turn():
    """The mic and the user's turn brackets keep working while muted.

    This is the whole difference from the pause() this replaces, which tore the
    mic down and left the user mute as well as deaf.
    """
    adapter = _make_adapter()
    adapter.set_voice_muted(True)

    await adapter.send_activity_start()
    await adapter.send_activity_end()

    session = adapter._current_session
    assert session.activity_starts == 1
    assert session.activity_ends == 1


@pytest.mark.asyncio
async def test_unmuting_replays_the_held_context():
    """Context is HELD, not discarded -- the model comes back oriented."""
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is date of birth")

    adapter.set_voice_muted(False)

    assert _drain(adapter._text_queue) == ["next field is date of birth"]


@pytest.mark.asyncio
async def test_unmute_replays_only_the_newest_context():
    """Only the LATEST held turn is replayed.

    These messages restate whole current state ("the next unfilled field is X"),
    so an older one is not extra information -- it is a stale contradiction, and
    replaying a backlog would bill for every one of them.
    """
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is first name")
    await adapter.send_text_message("next field is last name")
    await adapter.send_client_content("next field is date of birth")

    adapter.set_voice_muted(False)

    assert _drain(adapter._text_queue) == ["next field is date of birth"]


@pytest.mark.asyncio
async def test_unmute_with_nothing_held_sends_nothing():
    """Leaving manual mode does not itself make the model talk."""
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    adapter.set_voice_muted(False)

    assert _drain(adapter._text_queue) == []
    assert adapter._current_session.text_turns == []


@pytest.mark.asyncio
async def test_replayed_context_is_cleared_and_not_sent_twice():
    """A second unmute must not resurrect an already-replayed turn."""
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is date of birth")
    adapter.set_voice_muted(False)
    _drain(adapter._text_queue)

    adapter.set_voice_muted(True)
    adapter.set_voice_muted(False)

    assert _drain(adapter._text_queue) == []


@pytest.mark.asyncio
async def test_elicitation_flows_again_after_unmute():
    """Suppression is not sticky past the mode itself."""
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    adapter.set_voice_muted(False)

    await adapter.send_text_message("next field is date of birth")
    delivered = await adapter.send_client_content("say hello")

    assert _drain(adapter._text_queue) == ["next field is date of birth"]
    assert delivered is True
    assert adapter._current_session.text_turns == ["say hello"]


# ---------------------------------------------------------------------------
# The section-switch replay race (fresh-eyes finding on bd polyglot-pdf-wurj8)
#
# A section switch tears the Gemini session down -- _text_queue goes to None and
# the next connect builds a NEW one. An unmute landing in that window used to
# clear the held context unconditionally, so the re-orientation turn was dropped
# on the floor: silently, because a put on an orphaned queue raises nothing and
# nobody ever drains it. The held turn is now cleared only once it has actually
# reached a live queue.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmuting_with_no_live_queue_keeps_the_context_held():
    """Mid-teardown, the held turn survives instead of being silently dropped."""
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is date of birth")

    # The session-switch teardown: the queue the replay would have targeted is
    # gone, and the replacement does not exist yet.
    adapter._text_queue = None
    adapter.set_voice_muted(False)

    assert adapter._muted_context == "next field is date of birth"


@pytest.mark.asyncio
async def test_a_context_held_through_a_teardown_reaches_the_next_session():
    """...and rides the next turn on the fresh session, so nothing is lost."""
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is date of birth")
    adapter._text_queue = None
    adapter.set_voice_muted(False)

    # The replacement session brings a new queue; the next unmute delivers.
    adapter._text_queue = asyncio.Queue(maxsize=100)
    adapter.set_voice_muted(True)
    adapter.set_voice_muted(False)

    assert _drain(adapter._text_queue) == ["next field is date of birth"]


@pytest.mark.asyncio
async def test_a_deferred_context_still_loses_to_a_newer_one():
    """Deferring must not resurrect a stale turn over fresher state.

    These messages restate whole current state, so the newest-wins rule is what
    keeps the model from being told two contradictory things about where it is.
    """
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is first name")
    adapter._text_queue = None
    adapter.set_voice_muted(False)

    adapter._text_queue = asyncio.Queue(maxsize=100)
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is last name")
    adapter.set_voice_muted(False)

    assert _drain(adapter._text_queue) == ["next field is last name"]
