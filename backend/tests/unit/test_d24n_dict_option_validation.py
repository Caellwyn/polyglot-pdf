"""Regression tests for d24n (bd polyglot-pdf-jnjj.1).

The bug: a select/radio/checkbox field whose options are {value, label} DICTS
(the shape the generated form-kits use) would, on an INVALID value, build a
ValidationError carrying the raw dict options as `valid_options`. The tool-response
formatter then did `", ".join(valid_options[:3])`, which raised
`TypeError: sequence item 0: expected str instance, dict found`. The Live adapter
caught and swallowed that TypeError (logged tool_callback_error, error_type=TypeError),
so every such update_form_fields call silently failed -- the ~2-3 per 20-question
2.5 run captured in scripts/spikes/data/costs_2.5_*.meta.json.

These tests assert:
  1. _validate_checkbox / _validate_select with DICT options on an invalid value
     return `valid_options` as a list of bare STRINGS (never dicts).
  2. The end-to-end formatter (_build_update_fields_response) does NOT raise and
     produces a usable "valid=..." message for that error.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import WebSocket

from backend.utils.field_validator import (
    validate_updates,
    _option_values,
    _validate_checkbox,
    _validate_select,
)
from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import RequestCoordinator


DICT_OPTIONS = [
    {"value": "us_citizen", "label": "U.S. Citizen"},
    {"value": "lpr", "label": "Lawful Permanent Resident"},
    {"value": "other", "label": "Other"},
    {"value": "none", "label": "None of the above"},
]


def test_option_values_extracts_strings_from_dicts():
    assert _option_values(DICT_OPTIONS) == ["us_citizen", "lpr", "other", "none"]


def test_option_values_passes_plain_strings_through():
    assert _option_values(["a", "b"]) == ["a", "b"]


def test_checkbox_invalid_value_returns_string_options_not_dicts():
    """_validate_checkbox with DICT options + an invalid value must not leak dicts."""
    field = {"id": "p1_status", "name": "Status", "type": "checkbox",
             "options": DICT_OPTIONS}
    errors = _validate_checkbox(field, "not_a_real_option", "p1_status", "Status")
    assert len(errors) == 1
    valid_options = errors[0].valid_options
    assert valid_options is not None
    assert all(isinstance(o, str) for o in valid_options), \
        f"valid_options must be all strings, got {valid_options}"
    assert "us_citizen" in valid_options


def test_select_invalid_value_returns_string_options_not_dicts():
    field = {"id": "p1_kind", "name": "Kind", "type": "select",
             "options": DICT_OPTIONS}
    errors = _validate_select(field, "bogus", "p1_kind", "Kind")
    assert len(errors) == 1
    assert all(isinstance(o, str) for o in errors[0].valid_options)


def test_checkbox_valid_dict_option_passes():
    """A valid selection against dict options must validate cleanly (no false error)."""
    field = {"id": "p1_status", "name": "Status", "type": "checkbox",
             "options": DICT_OPTIONS}
    errors = _validate_checkbox(field, "lpr", "p1_status", "Status")
    assert errors == []


@pytest.mark.asyncio
async def test_update_form_fields_dict_options_invalid_does_not_raise_typeerror():
    """End-to-end: the exact d24n path. An invalid value on a dict-option checkbox
    field must produce a clean error response, never a TypeError in the formatter.
    """
    ws = MagicMock(spec=WebSocket)
    ws.send_json = AsyncMock()
    coordinator = MagicMock(spec=RequestCoordinator)
    coordinator.request_next_field_hint = AsyncMock(return_value=None)

    handler = CallbackHandler(
        websocket=ws, session_id="d24n-test", request_coordinator=coordinator,
    )

    # Inject a handle_update_fields that runs the REAL validator over a dict-option
    # checkbox schema -- exactly what FormFillingService does in production.
    schema_fields = [
        {"id": "p1_status", "name": "Status", "type": "checkbox",
         "options": DICT_OPTIONS},
    ]

    def handle_update_fields(session_id, updates, multi_field_call=False):
        # multi_field_call accepted (bd polyglot-pdf-h1bn / Codex PR #264): the
        # callback now passes it so the service can skip DTI coercion on a collapsed
        # multi-field call. This stub ignores it (not under test here).
        return validate_updates(schema_fields, updates)

    handler.set_tool_handlers(
        handle_update_fields=handle_update_fields,
        handle_switch_section=lambda *a, **k: None,
        handle_get_field_value=lambda *a, **k: None,
        request_form_state_from_client=AsyncMock(return_value={}),
    )

    # The invalid value is what made the model's update_form_fields call fail.
    resp = await handler.on_tool_call(
        "update_form_fields", {"field_id": "p1_status", "value": "not_an_option"}
    )

    # Pre-fix this raised TypeError inside _build_update_fields_response and the
    # adapter swallowed it. Post-fix we get a structured error response.
    assert isinstance(resp, dict)
    assert resp.get("success") is False
    # The "valid=..." hint must be present and string-formatted (proves the join
    # over option values did not crash and used the bare values).
    assert "valid=" in resp.get("message", "")
    assert "us_citizen" in resp.get("message", "")
