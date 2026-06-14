"""Repro / hypothesis-elimination harness for d24n (bd polyglot-pdf-jnjj.1 / F0).

Drives the REAL CallbackHandler.on_tool_call("update_form_fields", ...) through the
REAL FormFillingService validation path, offline, with no browser or live Gemini.

This script played TWO roles during the d24n investigation:

  1. ARG-SHAPE ELIMINATION (the ARG_SHAPES block). The bug report guessed "a
     signature/arg mismatch." This drove ~14 arg shapes a Live model might emit
     (value=int/None/dict/list/bool, missing value, field_id=None, args-as-list,
     ...) and showed NONE raise the captured TypeError -- DISPROVING the hypothesis
     and narrowing the hunt to the validation-ERROR path. (Note: arg-level raises
     inside the validator are caught by validate_field_updates' own try/except and
     logged as `update_validation_error`, NOT `tool_callback_error`, so they cannot
     be the captured failure either.)

  2. ROOT-CAUSE REPRODUCTION (the DICT_OPTION_CASES block). The real d24n failure:
     a checkbox/select field whose options are {value,label} DICTS, given an INVALID
     value, built a ValidationError carrying the raw dicts as valid_options;
     callback_handler._build_update_fields_response then did
     `", ".join(valid_options[:3])` -> "TypeError: sequence item 0: expected str
     instance, dict found", swallowed by the Live adapter. These cases reproduce
     that exact path. PRE-fix they raise the TypeError; POST-fix they return a clean
     error response. This is the case the ARG_SHAPES block lacked (fresh-eyes PR
     review, jnjj.1).

The live before/after measurement (zero TypeErrors, 18/20 confirmed) is in
scripts/spikes/d24n_dict_option_typeerror_findings.md; the committed regression
test is backend/tests/unit/test_d24n_dict_option_validation.py.

Run: python scripts/spikes/repro_d24n_update_form_fields_typeerror.py
(ASCII-only output; safe on Windows cp1252.)
"""
import asyncio
import os
import sys
import traceback

# Force dev logging ON so the adapter/handler print full tracebacks.
os.environ.setdefault("DEV_LOGGING", "1")

# Ensure the worktree root is importable as the package root.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))  # scripts/spikes -> repo root
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from unittest.mock import AsyncMock, MagicMock
from fastapi import WebSocket

from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import RequestCoordinator
from backend.services.form_filling_service import FormFillingService


# A small but representative schema: text, number, date, select -- the field
# types whose validators differ. Values exercise each branch. The dict-option
# checkbox/select fields (DICT_* below) are the ones that actually reproduce d24n:
# the form-kits store options as {value, label} dicts.
SCHEMA = {
    "fields": [
        {"id": "p1_firstName", "name": "First Name", "type": "text"},
        {"id": "p1_age", "name": "Age", "type": "number", "min": 0, "max": 120},
        {"id": "p1_dob", "name": "Date of Birth", "type": "date",
         "format": "YYYY-MM-DD", "date_constraint": "past_only"},
        {"id": "p1_state", "name": "State", "type": "select",
         "options": ["Iowa", "West Virginia"]},
        {"id": "p1_aliennumber", "name": "Alien Registration Number",
         "type": "text", "format_preset": "a_number", "pattern": r"^\d{7,9}$"},
        # The d24n trigger fields: options are {value, label} DICTS (form-kit shape).
        {"id": "p1_status", "name": "Status", "type": "checkbox",
         "options": [{"value": "lpr", "label": "Lawful Permanent Resident"},
                     {"value": "other", "label": "Other"}]},
        {"id": "p1_kind", "name": "Kind", "type": "select",
         "options": [{"value": "a", "label": "Alpha"},
                     {"value": "b", "label": "Beta"}]},
    ]
}

# The cases that actually REPRODUCE d24n: a dict-option checkbox/select field given
# an INVALID value -> ValidationError with dict-shaped valid_options ->
# ", ".join(dicts) in _build_update_fields_response. PRE-fix these raise the
# captured TypeError; POST-fix they return a clean error response.
DICT_OPTION_CASES = [
    ("checkbox dict-opts, invalid", {"field_id": "p1_status", "value": "bogus"}),
    ("select dict-opts, invalid", {"field_id": "p1_kind", "value": "bogus"}),
    ("checkbox dict-opts, VALID (must not false-reject)",
     {"field_id": "p1_status", "value": "lpr"}),
]

# The arg shapes worth trying -- what a Live model might actually emit for
# update_form_fields. The declared schema is {field_id: str, value: str}, but
# models drift: value as a number, null, a nested dict, a list, missing value, etc.
ARG_SHAPES = [
    ("canonical str", {"field_id": "p1_firstName", "value": "Alice"}),
    ("value=int", {"field_id": "p1_age", "value": 42}),
    ("value=None", {"field_id": "p1_firstName", "value": None}),
    ("value=nested dict", {"field_id": "p1_firstName", "value": {"value": "Alice"}}),
    ("value=list", {"field_id": "p1_state", "value": ["Iowa"]}),
    ("value=bool", {"field_id": "p1_firstName", "value": True}),
    ("missing value key", {"field_id": "p1_firstName"}),
    ("field_id=None", {"field_id": None, "value": "Alice"}),
    ("value=float", {"field_id": "p1_age", "value": 42.5}),
    ("date str", {"field_id": "p1_dob", "value": "1990-01-01"}),
    ("a_number with prefix", {"field_id": "p1_aliennumber", "value": "A1234567"}),
    ("a_number as int", {"field_id": "p1_aliennumber", "value": 1234567}),
    ("whole-args-as-list", [{"field_id": "p1_firstName", "value": "Alice"}]),
    ("args is a str", "p1_firstName=Alice"),
]


def build_handler():
    ws = MagicMock(spec=WebSocket)
    ws.send_json = AsyncMock()
    ws.send_bytes = AsyncMock()

    coordinator = MagicMock(spec=RequestCoordinator)
    coordinator.request_form_state = AsyncMock(return_value={})
    coordinator.request_next_field_hint = AsyncMock(return_value=None)
    coordinator.request_confirm_field = AsyncMock(return_value={"recorded": True})

    handler = CallbackHandler(
        websocket=ws,
        session_id="repro-session",
        request_coordinator=coordinator,
    )

    # Wire the REAL FormFillingService validation path (not a mock) so we exercise
    # handle_update_fields_tool_call -> ValidationHandler -> field_validator.
    svc = FormFillingService.__new__(FormFillingService)
    svc._schema = SCHEMA
    svc._session_id = "repro-session"

    handler.set_tool_handlers(
        handle_update_fields=svc.handle_update_fields_tool_call,
        handle_switch_section=lambda *a, **k: None,
        handle_get_field_value=lambda *a, **k: None,
        request_form_state_from_client=AsyncMock(return_value={}),
        get_next_field_schema_for_jit=lambda *a, **k: None,
    )
    return handler


async def _run_block(handler, title, cases):
    """Drive a list of (label, args) through on_tool_call; collect TypeErrors."""
    print("=" * 78)
    print(title)
    print("=" * 78)
    typeerrors = []
    for label, args in cases:
        try:
            resp = await handler.on_tool_call("update_form_fields", args)
            ok = isinstance(resp, dict)
            applied = resp.get("applied_fields") if isinstance(resp, dict) else None
            print(f"[ ok ] {label:42} -> resp_ok={ok} applied={applied}")
        except TypeError as e:
            typeerrors.append((label, e))
            print(f"[TYPE] {label:42} -> TypeError: {e}")
            traceback.print_exc()
        except Exception as e:  # noqa: BLE001 -- repro wants to see everything
            print(f"[ERR ] {label:42} -> {type(e).__name__}: {e}")
    return typeerrors


async def main():
    handler = build_handler()

    # Block 1: arg-shape elimination -- proves the arg path is NOT the d24n source.
    arg_te = await _run_block(
        handler,
        "Block 1 -- arg-shape elimination (expect NO TypeError; disproves the "
        "arg-mismatch hypothesis)",
        ARG_SHAPES,
    )

    # Block 2: the ACTUAL d24n repro -- dict-option fields with invalid values.
    dict_te = await _run_block(
        handler,
        "Block 2 -- d24n root-cause repro (dict-option checkbox/select, invalid "
        "value). PRE-fix: TypeError; POST-fix: clean error response.",
        DICT_OPTION_CASES,
    )

    print("=" * 78)
    print(f"Block 1 (arg shapes):  {len(arg_te)} TypeError(s)  "
          f"[expected 0 -- arg path is not the bug]")
    print(f"Block 2 (dict options): {len(dict_te)} TypeError(s)  "
          f"[PRE-fix: >0 reproduces d24n; POST-fix: 0 confirms the fix]")
    if dict_te:
        print("\n>>> d24n REPRODUCED (running against UNFIXED code):")
        for label, e in dict_te:
            print(f"  - {label}: {e}")
    else:
        print("\n>>> No TypeError on the dict-option path -- consistent with the fix "
              "in field_validator._option_values / _validate_checkbox.")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
