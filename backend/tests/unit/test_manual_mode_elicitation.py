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
import textwrap

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


class _FakeSenderTask:
    """Stands in for _current_text_sender_task: the live reader of _text_queue.

    Only `done()` matters to the code under test -- the flush treats a missing or
    finished sender as "nothing will ever read this queue" (see
    _flush_muted_context). Using a fake rather than a real asyncio.Task keeps
    these tests free of a background task that would need a live Gemini session.
    """

    def __init__(self, done: bool = False):
        self._done = done

    def done(self) -> bool:
        return self._done


def _make_adapter():
    """An adapter wired far enough to exercise the two elicitation paths.

    Includes a live sender task: a queue with no reader is treated as no
    pipeline at all, so without this every delivery assertion below would fail
    for the wrong reason.
    """
    adapter = LiveAIGemini(api_key="test_key")
    adapter._text_queue = asyncio.Queue(maxsize=100)
    adapter._current_text_sender_task = _FakeSenderTask()
    adapter._session_ready = True
    adapter._current_session = _RecordingSession()
    return adapter


def _restart_text_pipeline(adapter):
    """Do what a replacement session does when its text sender comes up.

    Mirrors the lines that matter -- a queue, a live reader, then the flush --
    without spawning the real _run_session_loop (which needs a live Gemini
    connection and leaves a pending task behind).
    test_the_sender_start_site_flushes below reads the SHIPPED source and pins
    that the real code really does flush there, so this mirror cannot drift away
    from production and quietly make these tests vacuous.
    """
    adapter._text_queue = asyncio.Queue()
    adapter._current_text_sender_task = _FakeSenderTask()
    adapter._text_pipeline_closing = False
    adapter._flush_muted_context("sender_started")


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


@pytest.mark.asyncio
async def test_a_hint_arriving_DURING_the_teardown_gap_still_wins():
    """The newest hint wins even when it lands while no queue exists.

    The sharp case, and the one worth stating plainly: holding must not depend on
    a queue being present. If it did, a hint arriving in the teardown window would
    return without recording anything, and the deferred replay would then voice an
    OLDER hint as if it were current -- the model confidently naming the wrong
    field, which is worse than saying nothing. So the mute check runs BEFORE the
    queue guard in send_text_message, mirroring send_client_content.
    """
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is first name")

    # Teardown: the queue is gone, and a fresher hint arrives anyway.
    adapter._text_queue = None
    await adapter.send_text_message("next field is last name")

    assert adapter._muted_context == "next field is last name"

    # ...and it is the fresher one that reaches the replacement session.
    adapter._text_queue = asyncio.Queue(maxsize=100)
    adapter.set_voice_muted(False)

    assert _drain(adapter._text_queue) == ["next field is last name"]


@pytest.mark.asyncio
async def test_the_direct_speak_path_holds_the_newest_even_with_no_session():
    """send_client_content records the newest turn regardless of session state.

    The two elicitation paths must agree about what counts as newest, or the rule
    depends on which channel a message happened to arrive on. The session-not-
    ready guard is the one that could plausibly be reordered ahead of the mute
    check here (that is exactly the mistake made on the other path), so the
    not-ready state is what this drives -- setting _text_queue would assert
    nothing, since send_client_content never reads it.
    """
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_client_content("next field is first name")

    adapter._session_ready = False
    adapter._current_session = None
    delivered = await adapter.send_client_content("next field is last name")

    assert delivered is False
    assert adapter._muted_context == "next field is last name"
    # ...and it did NOT fall into the not-ready queue, which would voice it the
    # moment the session came up, defeating the mute.
    assert adapter._pending_client_content == []


@pytest.mark.asyncio
async def test_a_turn_held_through_teardown_flushes_when_the_QUEUE_returns():
    """The other ordering: the unmute itself is what raced the teardown.

    The user unmutes mid-teardown and then never touches the toggle again -- why
    would they? So a flush keyed on the unmute EVENT strands the turn forever.
    Keying it on the CONDITION (not muted AND a queue exists) means whichever of
    the two arrives second does the delivering.
    """
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is date of birth")

    # Teardown, then the ONLY unmute -- no second mute/unmute cycle follows.
    adapter._text_queue = None
    adapter.set_voice_muted(False)
    assert adapter._muted_context == "next field is date of birth"

    # The replacement session builds its queue; that alone must deliver it.
    _restart_text_pipeline(adapter)

    assert _drain(adapter._text_queue) == ["next field is date of birth"]
    assert adapter._muted_context is None


@pytest.mark.asyncio
async def test_queue_creation_does_not_flush_while_still_muted():
    """A new session must not break the silence the user is still asking for."""
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is date of birth")
    adapter._text_queue = None

    _restart_text_pipeline(adapter)

    assert _drain(adapter._text_queue) == []
    assert adapter._muted_context == "next field is date of birth"


def test_the_sender_start_site_flushes():
    """The REAL pipeline-start site calls the flush -- not just the test mirror.

    _restart_text_pipeline above mirrors what production does when a replacement
    session's text sender comes up. A mirror is only worth something if the real
    code does the same thing, so this reads the shipped source and requires the
    flush call to sit right where the sender task is registered. Without it,
    deleting that call would leave every teardown test green while the stranding
    bug was back in production.
    """
    import ast
    import inspect

    from backend.adapters import live_ai_gemini

    src = inspect.getsource(live_ai_gemini.LiveAIGemini)
    tree = ast.parse(textwrap.dedent(src))

    # Find the statement that registers the sender task, then require the flush
    # among its immediate neighbours -- a call somewhere else in the file would
    # not run on the path that matters.
    for parent in ast.walk(tree):
        body = getattr(parent, "body", None)
        if not isinstance(body, list):
            continue
        for i, stmt in enumerate(body):
            registers = (
                isinstance(stmt, ast.Assign)
                and any(
                    isinstance(t, ast.Attribute) and t.attr == "_current_text_sender_task"
                    for t in stmt.targets
                )
                # the teardown also assigns it (to None) -- that one must NOT flush
                and not isinstance(stmt.value, ast.Constant)
            )
            if not registers:
                continue
            after = body[i + 1 : i + 4]
            flushes = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "_flush_muted_context"
                for nxt in after
                for n in ast.walk(nxt)
            )
            if not flushes:
                continue
            # ...and it must ALSO clear the closing flag there, or the flush it
            # just made is a no-op (the flag would still say "tearing down").
            # _restart_text_pipeline mirrors both lines; this is what stops the
            # mirror drifting apart from production.
            reopens = any(
                isinstance(n, ast.Assign)
                and any(
                    isinstance(t, ast.Attribute) and t.attr == "_text_pipeline_closing"
                    for t in n.targets
                )
                and isinstance(n.value, ast.Constant)
                and n.value.value is False
                for nxt in after
                for n in ast.walk(nxt)
            )
            assert reopens, (
                "the text sender is registered and the held turn flushed, but "
                "_text_pipeline_closing is never cleared there -- the flush would "
                "be a no-op and the turn stranded (bd polyglot-pdf-wurj8)"
            )
            return

    raise AssertionError(
        "the text sender is registered without flushing a held manual-mode turn "
        "-- a turn held through a teardown would be stranded whenever the unmute "
        "itself raced the teardown (bd polyglot-pdf-wurj8)"
    )


@pytest.mark.asyncio
async def test_a_queue_whose_reader_is_dying_is_not_treated_as_delivery():
    """The teardown window is not one instant, and the queue lies during it.

    finalize() cancels the sender task and only nulls _text_queue several awaits
    later, so in between there is a real queue that accepts a put -- onto a pipe
    whose reader is already dead. Trusting put_nowait there would log the turn as
    sent, clear it, and then lose it when the queue is dropped. A live CONSUMER
    is the honest signal; the queue object is not.
    """
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is date of birth")

    # Mid-teardown: queue still present, its reader already finished.
    adapter._current_text_sender_task = _FakeSenderTask(done=True)
    adapter.set_voice_muted(False)

    assert adapter._muted_context == "next field is date of birth"
    assert _drain(adapter._text_queue) == []

    # ...and it survives to the replacement pipeline.
    _restart_text_pipeline(adapter)
    assert _drain(adapter._text_queue) == ["next field is date of birth"]


@pytest.mark.asyncio
async def test_a_missing_reader_is_also_not_delivery():
    """Same for a queue with no sender task registered at all."""
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is date of birth")

    adapter._current_text_sender_task = None
    adapter.set_voice_muted(False)

    assert adapter._muted_context == "next field is date of birth"
    assert _drain(adapter._text_queue) == []


@pytest.mark.asyncio
async def test_a_sentinel_already_queued_is_not_a_live_pipeline():
    """The sharpest teardown state: reader alive, but it will never reach us.

    finalize() queues a None SENTINEL that makes the sender loop exit, THEN
    cancels the task, THEN nulls the queue. Between the sentinel and the cancel
    the task is not done() and the queue accepts a put -- yet anything queued
    behind that sentinel is already unreadable. Neither the queue nor the task
    can report this, which is why the adapter tracks the teardown explicitly.
    """
    adapter = _make_adapter()
    adapter.set_voice_muted(True)
    await adapter.send_text_message("next field is date of birth")

    # Exactly the state finalize() creates before it cancels anything.
    adapter._text_queue.put_nowait(None)
    adapter._text_pipeline_closing = True
    adapter.set_voice_muted(False)

    assert adapter._muted_context == "next field is date of birth"
    assert _drain(adapter._text_queue) == [None]

    # ...and it still reaches the replacement pipeline.
    _restart_text_pipeline(adapter)
    assert _drain(adapter._text_queue) == ["next field is date of birth"]


def test_the_teardown_marks_the_pipeline_closing_before_it_queues_the_sentinel():
    """The flag must be set before the sentinel, or it is useless.

    An unmute racing the teardown runs on a DIFFERENT task, so the ordering here
    is what makes the flag meaningful: once the sentinel is queued a put is
    already unreadable, and if the flag were set after it there would be a window
    where nothing says so -- the exact hole this closes.

    Scoped to the ONE function that does the teardown, and matched on the sentinel
    put that targets the TEXT queue specifically: the file has other
    put_nowait(None) calls (the audio pipeline, a restart path) whose line
    numbers are meaningless for this comparison.
    """
    import ast
    import inspect

    from backend.adapters import live_ai_gemini

    src = textwrap.dedent(inspect.getsource(live_ai_gemini.LiveAIGemini))
    tree = ast.parse(src)

    # The function containing the text-queue drain is the subject.
    def _sets_closing_true(node):
        return (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "_text_pipeline_closing"
                for t in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and node.value.value is True
        )

    def _queues_text_sentinel(node):
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "put_nowait"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "_text_queue"
            and any(isinstance(a, ast.Constant) and a.value is None for a in node.args)
        )

    subjects = [
        fn
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_sets_closing_true(n) for n in ast.walk(fn))
        and any(_queues_text_sentinel(n) for n in ast.walk(fn))
    ]
    assert subjects, (
        "no single function both marks the text pipeline closing and queues its "
        "sentinel -- the teardown moved; re-check this guard"
    )

    for fn in subjects:
        flag_line = min(n.lineno for n in ast.walk(fn) if _sets_closing_true(n))
        sentinel_line = min(n.lineno for n in ast.walk(fn) if _queues_text_sentinel(n))
        assert flag_line < sentinel_line, (
            "the pipeline is marked closing AFTER the sentinel is queued in "
            + fn.name
            + "; a concurrent unmute in between would put a turn behind the "
            "sentinel and lose it (bd polyglot-pdf-wurj8)"
        )
