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
    """A form_state entry without `shown` leaves the field out of shown_map (the
    renderers default shown=True), not crashing -- covers an older client that omits
    applicability (bd polyglot-pdf-p68s fallback)."""
    text_ai = MagicMock()
    text_ai.ask = AsyncMock(return_value="ok")
    svc = _service(text_ai, form_state={
        "f_first": {"value": "Ada", "confirmed": True},  # no 'shown' key
    })
    out = await svc.handle_ask_secretary("q")
    assert out == "ok"
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
    assert out == "ok"
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
