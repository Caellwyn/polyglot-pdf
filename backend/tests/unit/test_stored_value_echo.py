"""Spec for the stored-value echo on update_form_fields (bd polyglot-pdf-h7wx).

Live sessions read confirmation values back from the model's own conversational
memory -- which sliding-window compression can have evicted -- so the model
confabulated values that were never in the field (tester 2026-07-16: confirmed
an A-number different from the field's contents; wrote Johanson, read back
Johnson). The fix: a successful update_form_fields response echoes the CANONICAL
stored value (post-normalization), and the DTI SI directs the model to read its
confirmation back from that echo.

These tests pin:
  1. The success response carries stored_values with the CANONICAL value (the
     normalized form the client actually stores, e.g. "A-12345678" -> "12345678"),
     and the message repeats it with the read-THIS-back instruction.
  2. A validation failure carries NO stored_values (nothing was stored).
  3. Production structlog calls never receive the echoed value (PII stays out of
     server logs; the model-facing payload is not a log payload).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import WebSocket

from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import RequestCoordinator
from backend.utils.field_validator import validate_updates


A_NUMBER_FIELD = {
    "id": "p1_line1_aliennumber",
    "name": "Alien Registration Number",
    "type": "text",
    # format_preset drives normalize_value(): the "A-"/"A" prefix is stripped to
    # the canonical digits-only form before storage (bd 0zr / jnjj.40).
    "format_preset": "a_number",
}


def _make_handler(schema_fields):
    ws = MagicMock(spec=WebSocket)
    ws.send_json = AsyncMock()
    coordinator = MagicMock(spec=RequestCoordinator)
    coordinator.request_next_field_hint = AsyncMock(return_value=None)

    handler = CallbackHandler(
        websocket=ws, session_id="h7wx-test", request_coordinator=coordinator,
    )

    def handle_update_fields(session_id, updates, multi_field_call=False):
        # Runs the REAL validator (incl. normalization) and maps its result to
        # the shape FormFillingService hands the callback in production.
        vr = validate_updates(schema_fields, updates)
        return {
            "applied_fields": vr["valid_fields"],
            "unknown_fields": [
                k for k in updates if k not in {f["id"] for f in schema_fields}
            ],
            "validation_errors": vr["validation_errors"],
            "form_state": vr["form_state"],
        }

    handler.set_tool_handlers(
        handle_update_fields=handle_update_fields,
        handle_switch_section=lambda *a, **k: None,
        request_form_state_from_client=AsyncMock(return_value={}),
    )
    return handler


@pytest.mark.asyncio
async def test_success_response_echoes_canonical_stored_value():
    handler = _make_handler([A_NUMBER_FIELD])

    resp = await handler.on_tool_call(
        "update_form_fields",
        {"field_id": "p1_line1_aliennumber", "value": "A-12345678"},
    )

    assert resp.get("success") is True
    # The echo is the CANONICAL (normalized) value, not the raw input: the model
    # must read back exactly what the client stores.
    assert resp.get("stored_values") == {"p1_line1_aliennumber": "12345678"}
    # The message repeats the stored value inline (message text is what the
    # model most reliably attends to) plus the read-THIS-back instruction.
    assert "12345678" in resp.get("message", "")
    assert "Read THIS stored value back" in resp.get("message", "")


@pytest.mark.asyncio
async def test_validation_failure_carries_no_stored_values():
    checkbox_field = {
        "id": "p1_status",
        "name": "Status",
        "type": "select",
        "options": [
            {"value": "us_citizen", "label": "U.S. Citizen"},
            {"value": "lpr", "label": "Lawful Permanent Resident"},
        ],
    }
    handler = _make_handler([checkbox_field])

    resp = await handler.on_tool_call(
        "update_form_fields", {"field_id": "p1_status", "value": "not_an_option"}
    )

    assert resp.get("success") is False
    # Nothing was stored -> nothing to echo.
    assert "stored_values" not in resp


@pytest.mark.asyncio
async def test_collapsed_multi_field_error_carries_no_stored_values():
    """A COLLAPSED multi-field update (two field_ids in one call, first valid)
    lands in the error branch: rejected_fields -> validation_errors is non-empty,
    so the caller sent send_form_update({}, []) and the CLIENT STORED NOTHING --
    yet applied_values still holds the first field's canonical value. The response
    must NOT echo that as stored_values, or the model reads back a value the client
    never stored (bd polyglot-pdf-f7h7).

    The public tool parser caps arguments at a single field, so the collapsed path
    is exercised at its invariant site -- _build_update_fields_response with both
    applied_values populated AND validation_errors present -- which is exactly the
    shape the caller hands it in the collapsed case.
    """
    handler = _make_handler([A_NUMBER_FIELD])

    resp = handler._build_update_fields_response(
        # A collapsed call: first field applied, the rest rejected as
        # single_field_only (mirrors the caller's rejected_fields -> errors path).
        validation_errors=[
            {
                "field_id": "p1_other_field",
                "field_name": "p1_other_field",
                "value": "SOMETHING",
                "constraint": "single_field_only",
                "message": "Rejected - only one field per call allowed",
            }
        ],
        unknown_fields=[],
        applied_fields=["p1_line1_aliennumber"],
        next_field_hint=None,
        rejected_count=1,
        applied_values={"p1_line1_aliennumber": "12345678"},
    )

    assert resp.get("success") is False
    # The first field validated (applied_fields is non-empty), but send_form_update
    # carried nothing to the client on this branch -> no stored_values echo.
    assert "stored_values" not in resp


@pytest.mark.asyncio
async def test_echoed_value_never_reaches_structlog(monkeypatch):
    """PII guard: the echo is model-facing only. The production structlog calls
    around the update path log counts/flags -- the stored value must not appear
    in any structlog event kwargs."""
    import backend.services.callback_handler as cbh

    seen = []

    class _CaptureLog:
        def _record(self, *args, **kwargs):
            seen.append((args, kwargs))

        def __getattr__(self, name):
            # info/warning/error/debug all funnel here.
            return self._record

    monkeypatch.setattr(cbh, "_log", _CaptureLog())

    handler = _make_handler([A_NUMBER_FIELD])
    resp = await handler.on_tool_call(
        "update_form_fields",
        {"field_id": "p1_line1_aliennumber", "value": "A-12345678"},
    )
    assert resp.get("success") is True

    flat = repr(seen)
    assert "12345678" not in flat, (
        "the stored field value leaked into a structlog call: " + flat
    )
