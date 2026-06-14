"""Repro harness for d24n (bd polyglot-pdf-jnjj.1 / F0).

Goal: force the `tool_callback_error` TypeError that fires 2-3x per 2.5 run on
`update_form_fields`, captured PII-free in scripts/spikes/data/costs_2.5_*.meta.json
(error_type=TypeError, no message -- production strips it). The bug report's
"likely a signature mismatch" was a hypothesis; a full static read of the
update_form_fields chain (on_tool_call -> _handle_update_form_fields_tool ->
handle_update_fields_tool_call -> ValidationHandler.validate_field_updates) found
no static arg-count/await mismatch, and any value-dependent raise inside the
validator is caught by validate_field_updates' own try/except and logged as
`update_validation_error`, NOT `tool_callback_error`. So the TypeError must escape
on a path OUTSIDE that inner catch.

This harness drives the REAL CallbackHandler.on_tool_call("update_form_fields", ...)
through the REAL FormFillingService validation path with a real I-90-style schema,
feeding the arg SHAPES the live model actually emits, with dev logging ON so the
full traceback prints. We try each shape and report which raises.

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
# types whose validators differ. Values exercise each branch.
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
    ]
}

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


async def main():
    handler = build_handler()
    print("=" * 78)
    print("d24n repro: driving update_form_fields with model-realistic arg shapes")
    print("=" * 78)
    typeerrors = []
    for label, args in ARG_SHAPES:
        try:
            resp = await handler.on_tool_call("update_form_fields", args)
            ok = isinstance(resp, dict)
            applied = resp.get("applied_fields") if isinstance(resp, dict) else None
            print(f"[ ok ] {label:24} -> resp_ok={ok} applied={applied}")
        except TypeError as e:
            typeerrors.append((label, e))
            print(f"[TYPE] {label:24} -> TypeError: {e}")
            traceback.print_exc()
        except Exception as e:  # noqa: BLE001 -- repro wants to see everything
            print(f"[ERR ] {label:24} -> {type(e).__name__}: {e}")
    print("=" * 78)
    if typeerrors:
        print(f"REPRODUCED {len(typeerrors)} TypeError shape(s):")
        for label, e in typeerrors:
            print(f"  - {label}: {e}")
    else:
        print("No TypeError raised at the on_tool_call boundary for these shapes.")
        print("Next: the escape may be on the live_ai_gemini event.tool_call path,")
        print("or in confirm_field; widen the harness or capture a dev .jsonl run.")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
