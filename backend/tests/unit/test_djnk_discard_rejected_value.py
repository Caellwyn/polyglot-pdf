"""Pin the DISCARD instruction on rejected update values (bd polyglot-pdf-djnk).

Observed live (6mzi multilingual assessment, hi run 20260722T174640Z q9-q10):
the model invented field id p1_line6c_unitnumber with value '10'; DTI coercion
snapped it onto the current field where '10' failed options-validation -- but
nothing told the model the value was dead, so it re-used '10' as the fill for
the NEXT field, overriding the user's actual answer ('12'). The response
message for a validation error must explicitly instruct the model to discard
the rejected value and re-ask the user.
"""
import pytest
from unittest.mock import MagicMock

from backend.services.callback_handler import CallbackHandler


def _formatter(**kwargs):
    # _build_update_fields_response reads no instance state; call it unbound on
    # a bare mock so the test needs no full handler construction.
    defaults = dict(
        validation_errors=[],
        unknown_fields=[],
        applied_fields=[],
        next_field_hint=None,
    )
    defaults.update(kwargs)
    return CallbackHandler._build_update_fields_response(MagicMock(), **defaults)


def test_validation_error_message_orders_the_value_discarded():
    resp = _formatter(validation_errors=[{
        "field_id": "p1_unit_type6c_unit", "field_name": "Select Unit Type",
        "value": "10", "constraint": "options", "message": "Invalid option",
        "valid_options": ["suite", "floor", "apartment"],
    }])
    assert resp["success"] is False
    msg = resp["message"]
    assert "DISCARD" in msg
    assert "Never reuse a rejected value" in msg
    assert "Ask the user again" in msg


def test_success_path_carries_no_discard_instruction():
    resp = _formatter(
        applied_fields=["p1_line6c_aptsteflrnumber"],
        applied_values={"p1_line6c_aptsteflrnumber": "12"},
    )
    assert resp["success"] is True
    assert "DISCARD" not in resp["message"]


def test_unknown_field_only_rejection_carries_no_discard_instruction():
    # The discard order is scoped to VALIDATION rejections: an unknown-field
    # rejection has its own recovery text (copy the id / switch_to_field) and
    # the value there may still be the user's real answer for the right field.
    resp = _formatter(unknown_fields=["p1_line6c_unitnumber"])
    assert resp["success"] is False
    assert "DISCARD" not in resp["message"]
    assert "unknown field" in resp["message"]
