"""Pins for the tupu.2 spoken-name delivery channels OUTSIDE the guidance
render (bd polyglot-pdf-tupu.2): the direct echo channels in CallbackHandler
(switch success message, candidate lists, secretary fields arrays) and the
next-field-hint substitution, plus the FIELD-NAMES-ALOUD SI rule.

The 6mzi assessment showed English field names reaching non-English users
through channels beyond the guidance block; the adversarial plan review
enumerated these exact sites. Each falls back to English on a miss.
"""
from unittest.mock import MagicMock

from backend.config import Settings
from backend.services.callback_handler import CallbackHandler


def _handler(overrides=None):
    h = MagicMock(spec=CallbackHandler)
    h._get_spoken_name_overrides = (lambda: overrides) if overrides else None
    h._spoken_overrides = lambda: CallbackHandler._spoken_overrides(h)
    return h


def test_translate_spoken_hits_and_misses():
    h = _handler({"family name": "apellido"})
    assert CallbackHandler._translate_spoken(h, "family name") == "apellido"
    assert CallbackHandler._translate_spoken(h, "given name") == "given name"
    assert CallbackHandler._translate_spoken(h, None) is None
    # No getter wired at all: pass-through.
    h2 = _handler(None)
    assert CallbackHandler._translate_spoken(h2, "family name") == "family name"


def test_translate_hint_substitutes_quoted_english_name():
    h = _handler({"current family name": "apellido actual"})
    schema = {"id": "p1_line3a_familyname", "name": "Family Name",
              "spoken_name": "current family name"}
    hint = "Next field to fill is #3: 'Family Name' (type: text)"
    out = CallbackHandler._translate_hint(h, hint, schema)
    assert out == "Next field to fill is #3: 'apellido actual' (type: text)"


def test_translate_hint_miss_or_no_schema_leaves_hint_untouched():
    h = _handler({"something else": "otra cosa"})
    schema = {"id": "f", "name": "Family Name", "spoken_name": "family name"}
    hint = "Next field to fill is #3: 'Family Name'"
    assert CallbackHandler._translate_hint(h, hint, schema) == hint
    assert CallbackHandler._translate_hint(h, hint, None) == hint
    assert CallbackHandler._translate_hint(h, None, schema) is None


# --- Integration: the echo channels through the REAL handler -------------------

import pytest
from unittest.mock import AsyncMock

OVERRIDES = {"first name": "nombre de pila", "family name": "apellido"}


def _real_handler():
    """A real CallbackHandler with the spoken-name override getter wired via
    set_tool_handlers -- so the echo-channel substitutions are exercised at
    the on_tool_call integration level, not just the helper level
    (fresh-eyes round-1 gap, this PR)."""
    coordinator = MagicMock()
    coordinator.request_switch_field = AsyncMock(return_value={
        "found": True, "field_id": "p1_first_name",
        "spoken_name": "first name", "next_field_hint": None})
    handler = CallbackHandler(
        websocket=MagicMock(), session_id="tupu2-test",
        request_coordinator=coordinator,
    )
    handler.set_tool_handlers(
        handle_update_fields=MagicMock(return_value={
            "applied_fields": [], "validation_errors": [],
            "unknown_fields": [], "form_state": {}}),
        handle_switch_section=AsyncMock(return_value={"success": True}),
        request_form_state_from_client=AsyncMock(return_value={}),
        handle_ask_secretary=AsyncMock(return_value={
            "status": "ok", "answer": "they said Jane",
            "sources": [{"field_id": "p1_first_name",
                         "spoken_name": "first name"}]}),
        get_spoken_name_overrides=lambda: OVERRIDES,
    )
    handler.send_form_update = AsyncMock()
    return handler


@pytest.mark.asyncio
async def test_switch_success_message_speaks_translated_name():
    handler = _real_handler()
    resp = await handler.on_tool_call("switch_to_field", {"field": "first name"})
    assert resp.get("success") is True
    assert "nombre de pila" in resp.get("message", "")
    assert "first name" not in resp.get("message", "")


@pytest.mark.asyncio
async def test_ask_secretary_fields_array_carries_translated_names():
    handler = _real_handler()
    resp = await handler.on_tool_call("ask_secretary", {"query": "first name?"})
    fields = resp.get("fields") or []
    assert fields and fields[0]["spoken_name"] == "nombre de pila"
    # The field_id is never translated (tool-call matching).
    assert fields[0]["field_id"] == "p1_first_name"


def test_dti_and_legacy_si_pin_field_names_aloud_rule():
    """Both SIs must tell the model the guidance name is already localized and
    forbid reading English names/labels aloud in a non-English session (bd
    polyglot-pdf-tupu.2)."""
    dti = Settings().DTI_SYSTEM_INSTRUCTION.lower()
    assert "field names aloud" in dti
    assert "already in the session language" in dti
    assert "never call a tool to translate or fetch a field name" in dti
    legacy = Settings().SYSTEM_INSTRUCTION.lower()
    assert "never read an english field name or label aloud" in legacy
