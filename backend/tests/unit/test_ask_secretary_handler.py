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


def _service(text_ai=None, *, schema=_SCHEMA, form_state=None, timeout_s=8.0):
    """Build a FormFillingService with a stub text_ai + a stubbed client form-state
    round-trip, ready to call handle_ask_secretary()."""
    settings = Settings()
    settings.SECRETARY_TIMEOUT_S = timeout_s
    svc = FormFillingService(live_ai=None, settings=settings, text_ai=text_ai)
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

    assert out == "Their first name is Ada."
    # Context carries the schema + the client's form state + a derived shown_map.
    _, kwargs = text_ai.ask.call_args
    ctx = text_ai.ask.call_args.args[1] if len(text_ai.ask.call_args.args) > 1 else kwargs["context"]
    assert ctx["schema"] is _SCHEMA
    assert ctx["shown_map"] == {"f_first": True, "f_last": False}


@pytest.mark.asyncio
async def test_handle_ask_secretary_timeout_fail_open():
    """A lookup slower than SECRETARY_TIMEOUT_S fail-opens to "" so a slow secretary
    cannot hang the conversation (the interim tail-latency guard)."""
    async def _slow(query, context):
        await asyncio.sleep(10)
        return "too late"

    text_ai = MagicMock()
    text_ai.ask = _slow
    svc = _service(text_ai, timeout_s=0.05)

    out = await svc.handle_ask_secretary("q")
    assert out == ""


@pytest.mark.asyncio
async def test_handle_ask_secretary_ask_error_fail_open():
    """An exception from ask() fail-opens to ""."""
    text_ai = MagicMock()
    text_ai.ask = AsyncMock(side_effect=RuntimeError("boom"))
    svc = _service(text_ai)
    assert await svc.handle_ask_secretary("q") == ""


@pytest.mark.asyncio
async def test_handle_ask_secretary_no_text_ai_fail_open():
    """No secretary adapter wired -> fail-open ""."""
    svc = _service(text_ai=None)
    assert await svc.handle_ask_secretary("q") == ""


@pytest.mark.asyncio
async def test_handle_ask_secretary_no_schema_fail_open():
    """No catalog (empty schema) -> fail-open "" (cannot retrieve)."""
    text_ai = MagicMock()
    text_ai.ask = AsyncMock(return_value="should not be called")
    svc = _service(text_ai, schema={})
    assert await svc.handle_ask_secretary("q") == ""
    text_ai.ask.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_ask_secretary_shown_defaults_true_without_shown_key():
    """Until jnjj.45d ships `shown`, a form_state entry without it leaves the field
    out of shown_map (renderers default shown=True), not crashing."""
    text_ai = MagicMock()
    text_ai.ask = AsyncMock(return_value="ok")
    svc = _service(text_ai, form_state={
        "f_first": {"value": "Ada", "confirmed": True},  # no 'shown' key
    })
    out = await svc.handle_ask_secretary("q")
    assert out == "ok"
    ctx = text_ai.ask.call_args.args[1]
    assert ctx["shown_map"] == {}  # no explicit shown -> renderer defaults True
