"""Unit tests for FormFillingService.handle_ask_secretary (bd polyglot-pdf-jnjj.45c).

Covers the BLOCKING secretary lookup's guard rails: the asyncio.wait_for timeout
+ fail-open, and the other fail-open paths (no adapter / no schema / values-request
error). The secretary's prose generation itself is tested in
test_text_ai_gemini.py; here we test the orchestration around it.

ASCII only (CLAUDE.md scar #6).
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.config import Settings
from backend.services.form_filling_service import FormFillingService


_SCHEMA = {
    "fields": [
        {"id": "f_first", "spoken_name": "first name", "type": "text"},
        {"id": "f_last", "spoken_name": "last name", "type": "text"},
    ],
    "sections": [{"id": "s1", "label": "Names", "fields": ["f_first", "f_last"]}],
    "parts": [{"id": "p1", "label": "Part 1", "section_ids": ["s1"]}],
}


def _service(text_ai=None, *, schema=_SCHEMA, form_state=None, timeout_s=8.0,
             deadline_s=8.0, live_ai=None):
    """Build a FormFillingService with a stub text_ai + a stubbed client form-state
    round-trip, ready to call handle_ask_secretary().

    deadline_s defaults HIGH (8.0) so a fast stub answer always resolves on the
    synchronous path; the async-deliver tests lower it to force the pending branch.
    """
    settings = Settings()
    settings.SECRETARY_TIMEOUT_S = timeout_s
    settings.SECRETARY_DEADLINE_S = deadline_s
    svc = FormFillingService(live_ai=live_ai, settings=settings, text_ai=text_ai)
    svc._schema = schema
    svc._session_id = "test-123"
    # Stub the client form-state round-trip used to build the values+shown tail.
    svc.request_form_state_from_client = AsyncMock(return_value=form_state or {})
    return svc


@pytest.mark.asyncio
async def test_handle_ask_secretary_happy_path():
    """The handler passes the assembled context to text_ai.ask and returns prose."""
    text_ai = MagicMock()
    text_ai.ask = AsyncMock(return_value="Their first name is Ada.")
    svc = _service(text_ai, form_state={
        "f_first": {"value": "Ada", "confirmed": True, "shown": True},
        "f_last": {"value": None, "confirmed": False, "shown": False},
    })

    out = await svc.handle_ask_secretary("what is their first name?")

    assert out == {"status": "ok", "answer": "Their first name is Ada."}
    # Context carries the schema + the client's form state + a derived shown_map.
    _, kwargs = text_ai.ask.call_args
    ctx = text_ai.ask.call_args.args[1] if len(text_ai.ask.call_args.args) > 1 else kwargs["context"]
    assert ctx["schema"] is _SCHEMA
    assert ctx["shown_map"] == {"f_first": True, "f_last": False}


@pytest.mark.asyncio
async def test_handle_ask_secretary_timeout_fail_open():
    """A lookup slower than the HARD cap (SECRETARY_TIMEOUT_S) that ALSO exceeds the
    deadline resolves to status=failed -- the inner wait_for raises TimeoutError and
    is surfaced on the synchronous path (deadline >= timeout here, so the lookup is
    already done-with-timeout when the race resolves)."""
    async def _slow(query, context):
        await asyncio.sleep(10)
        return "too late"

    text_ai = MagicMock()
    text_ai.ask = _slow
    # deadline >= timeout: the hard-cap TimeoutError fires within the sync race.
    svc = _service(text_ai, timeout_s=0.05, deadline_s=0.2)

    out = await svc.handle_ask_secretary("q")
    assert out == {"status": "failed", "answer": ""}


@pytest.mark.asyncio
async def test_handle_ask_secretary_ask_error_fail_open():
    """An exception from ask() resolves to status=failed."""
    text_ai = MagicMock()
    text_ai.ask = AsyncMock(side_effect=RuntimeError("boom"))
    svc = _service(text_ai)
    assert await svc.handle_ask_secretary("q") == {"status": "failed", "answer": ""}


@pytest.mark.asyncio
async def test_handle_ask_secretary_no_text_ai_fail_open():
    """No secretary adapter wired -> status=failed."""
    svc = _service(text_ai=None)
    assert await svc.handle_ask_secretary("q") == {"status": "failed", "answer": ""}


@pytest.mark.asyncio
async def test_handle_ask_secretary_no_schema_fail_open():
    """No catalog (empty schema) -> status=failed (cannot retrieve)."""
    text_ai = MagicMock()
    text_ai.ask = AsyncMock(return_value="should not be called")
    svc = _service(text_ai, schema={})
    assert await svc.handle_ask_secretary("q") == {"status": "failed", "answer": ""}
    text_ai.ask.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_ask_secretary_shown_defaults_true_without_shown_key():
    """A form_state entry without `shown` leaves the field out of shown_map (the
    renderers default shown=True), not crashing -- covers an older client that omits
    applicability (bd polyglot-pdf-p68s fallback)."""
    text_ai = MagicMock()
    text_ai.ask = AsyncMock(return_value="ok")
    svc = _service(text_ai, form_state={
        "f_first": {"value": "Ada", "confirmed": True},  # no 'shown' key
    })
    out = await svc.handle_ask_secretary("q")
    assert out == {"status": "ok", "answer": "ok"}
    ctx = text_ai.ask.call_args.args[1]
    assert ctx["shown_map"] == {}  # no explicit shown -> renderer defaults True


# --- Full-form catalog wiring (bd polyglot-pdf-p68s / jnjj.45d) -----------------

# A whole-form schema with TWO sections; the per-section schema would carry only
# one section's fields. The secretary must see BOTH.
_FULL_SCHEMA = {
    "fields": [
        {"id": "f_first", "spoken_name": "first name", "type": "text"},
        {"id": "f_last", "spoken_name": "last name", "type": "text"},
        {"id": "f_phone", "spoken_name": "phone", "type": "text"},
    ],
    "sections": [
        {"id": "s1", "label": "Names", "fields": ["f_first", "f_last"]},
        {"id": "s2", "label": "Contact", "fields": ["f_phone"]},
    ],
    "parts": [{"id": "p1", "label": "Part 1", "section_ids": ["s1", "s2"]}],
}


@pytest.mark.asyncio
async def test_handle_ask_secretary_prefers_full_schema_over_section_schema():
    """When the client supplied the full-form catalog at handshake, the handler
    passes the WHOLE form to the secretary, not the current section's schema."""
    text_ai = MagicMock()
    text_ai.ask = AsyncMock(return_value="ok")
    svc = _service(text_ai, schema=_SCHEMA)  # _schema = section-only (2 fields)
    svc._full_schema = _FULL_SCHEMA          # full catalog (3 fields, 2 sections)

    out = await svc.handle_ask_secretary("q")
    assert out == {"status": "ok", "answer": "ok"}
    ctx = text_ai.ask.call_args.args[1]
    assert ctx["schema"] is _FULL_SCHEMA


@pytest.mark.asyncio
async def test_start_session_caches_full_schema_and_preserves_across_switch():
    """start_session(full_schema=...) caches the catalog; a later start_session
    WITHOUT full_schema (the section-switch restart path) preserves it."""
    svc = FormFillingService(live_ai=None, settings=Settings(), text_ai=None)
    ws = AsyncMock()

    # Fresh connect supplies the full catalog.
    await svc.start_session(
        ws, "sess-1", accept_connection=False,
        schema=_SCHEMA, full_schema=_FULL_SCHEMA,
    )
    assert svc._full_schema is _FULL_SCHEMA

    # Section-switch restart calls start_session WITHOUT full_schema -- the cached
    # catalog must survive (the form is unchanged across sections).
    await svc.start_session(
        ws, "sess-1", accept_connection=False,
        schema=_SCHEMA, full_schema=None,
    )
    assert svc._full_schema is _FULL_SCHEMA


# --- Tail-latency guard: deadline + async-deliver (bd polyglot-pdf-jnjj.43) -----


def _live_ai_active():
    """A stub live_ai that reports an active session and records send_client_content."""
    live = MagicMock()
    live.is_session_active = MagicMock(return_value=True)
    live.send_client_content = AsyncMock()
    return live


@pytest.mark.asyncio
async def test_handle_ask_secretary_deadline_returns_pending_then_delivers_async():
    """A lookup slower than SECRETARY_DEADLINE_S (but within the hard cap) returns
    status=pending immediately, and the still-running lookup delivers its answer on a
    follow-up turn via send_client_content (jnjj.43)."""
    async def _slow(query, context):
        await asyncio.sleep(0.2)
        return "Their previous last name was Smith."

    live = _live_ai_active()
    text_ai = MagicMock()
    text_ai.ask = _slow
    # deadline short (so we go pending), hard cap generous (so the lookup completes).
    svc = _service(text_ai, deadline_s=0.05, timeout_s=5.0, live_ai=live)

    out = await svc.handle_ask_secretary("what was their previous last name?")
    # Synchronous path: pending, no answer, principal's turn freed.
    assert out == {"status": "pending", "answer": ""}
    # A deliver task was detached.
    assert len(svc._secretary_deliver_tasks) == 1

    # Let the detached lookup finish + deliver.
    await asyncio.sleep(0.4)

    live.send_client_content.assert_awaited_once()
    delivered = live.send_client_content.await_args.args[0]
    assert "Smith" in delivered  # the late answer was pushed for the principal to voice
    # The task self-removed on completion.
    assert len(svc._secretary_deliver_tasks) == 0


@pytest.mark.asyncio
async def test_async_deliver_drops_when_session_inactive():
    """If the live session went away before the late answer landed, the deliver is
    dropped (no push into a dead session)."""
    async def _slow(query, context):
        await asyncio.sleep(0.2)
        return "too late, nobody home"

    live = _live_ai_active()
    live.is_session_active = MagicMock(return_value=False)  # session gone
    text_ai = MagicMock()
    text_ai.ask = _slow
    svc = _service(text_ai, deadline_s=0.05, timeout_s=5.0, live_ai=live)

    out = await svc.handle_ask_secretary("q")
    assert out == {"status": "pending", "answer": ""}
    await asyncio.sleep(0.4)
    live.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_deliver_drops_empty_answer():
    """A late lookup that returns empty is dropped silently (no apology turn out of
    nowhere -- the user has already moved on)."""
    async def _slow(query, context):
        await asyncio.sleep(0.2)
        return ""

    live = _live_ai_active()
    text_ai = MagicMock()
    text_ai.ask = _slow
    svc = _service(text_ai, deadline_s=0.05, timeout_s=5.0, live_ai=live)

    out = await svc.handle_ask_secretary("q")
    assert out == {"status": "pending", "answer": ""}
    await asyncio.sleep(0.4)
    live.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_end_session_cancels_inflight_secretary_deliver():
    """end_session cancels an in-flight async-deliver so a disconnect never pushes a
    late turn into a session being torn down."""
    started = asyncio.Event()

    async def _slow(query, context):
        started.set()
        await asyncio.sleep(5)  # still running when end_session fires
        return "never delivered"

    live = _live_ai_active()
    live.finalize = AsyncMock()
    text_ai = MagicMock()
    text_ai.ask = _slow
    svc = _service(text_ai, deadline_s=0.05, timeout_s=10.0, live_ai=live)

    out = await svc.handle_ask_secretary("q")
    assert out == {"status": "pending", "answer": ""}
    await started.wait()
    assert len(svc._secretary_deliver_tasks) == 1

    await svc.end_session()
    # The deliver task was cancelled + drained; nothing pushed.
    assert len(svc._secretary_deliver_tasks) == 0
    live.send_client_content.assert_not_awaited()
