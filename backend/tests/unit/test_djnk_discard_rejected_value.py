"""Pin the DISCARD instruction on rejected update values (bd polyglot-pdf-djnk).

Observed live (6mzi multilingual assessment, hi run 20260722T174640Z q9-q10):
the model invented field id p1_line6c_unitnumber with value '10'; DTI coercion
snapped it onto the current field where '10' failed options-validation -- but
nothing told the model the value was dead, so it re-used '10' as the fill for
the NEXT field, overriding the user's actual answer ('12'). The response
message for a validation error must explicitly instruct the model to discard
the rejected value and re-ask the user.
"""
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


# --------------------------------------------------------------------------- #
# The RECOVERY half branches on constraint type (bd polyglot-pdf-mq2je).
#
# The anti-leak instruction above is unconditional and must stay so. But the
# RECOVERY it prescribes was also unconditional, and on a FORMAT rejection
# "ask the user again" is the WRONG recovery: the user already gave a usable
# answer and only its shape was wrong. Reshaping is the model's job -- the DTI
# SI's DATES block forbids asking a user to restate a date in another format.
#
# This text is read in the SAME turn as the error, while that SI rule sits
# thousands of characters upstream, so an unconditional re-ask wins on recency.
# Observed live 2026-08-25: the model rejected on format, then asked the
# maintainer to say the date again instead of reshaping it.
# --------------------------------------------------------------------------- #

def _format_error(field_id="date_of_birth", value="1980-10-26"):
    return {
        "field_id": field_id,
        "field_name": "4 Date of birth (month / day / year)",
        "value": value,
        "constraint": "format",
        "constraint_value": "MM/DD/YYYY",
        "message": "Invalid date (expected MM/DD/YYYY)",
    }


def _options_error(field_id="p1_line6c_unitnumber", value="10"):
    return {
        "field_id": field_id,
        "field_name": "Unit type",
        "value": value,
        "constraint": "options",
        "valid_options": ["Apt", "Ste", "Flr"],
        "message": "Invalid option",
    }


def test_format_only_rejection_tells_the_model_to_reshape_not_re_ask():
    """The bug this closes: a pedantic 'say it again differently'."""
    resp = _formatter(validation_errors=[_format_error()])
    msg = resp["message"]
    assert "Re-send the SAME answer corrected to the required format" in msg
    assert "do NOT ask the user to say it again in a different format" in msg
    assert "Ask the user again for the current field" not in msg, (
        "a format rejection must NOT order a re-ask -- the user already gave "
        "the answer, only its shape was wrong")


def test_non_format_rejection_still_orders_a_re_ask():
    """The other branch must survive. An options failure genuinely needs a
    DIFFERENT ANSWER from the user, not a reshaped one."""
    resp = _formatter(validation_errors=[_options_error()])
    msg = resp["message"]
    assert "Ask the user again for the current field" in msg
    assert "Re-send the SAME answer" not in msg


def test_mixed_rejections_fall_back_to_the_re_ask():
    """If ANY error is not a format problem, the safe recovery is the re-ask --
    reshaping cannot fix an out-of-options value."""
    resp = _formatter(validation_errors=[_format_error(), _options_error()])
    msg = resp["message"]
    assert "Ask the user again for the current field" in msg
    assert "Re-send the SAME answer" not in msg


def test_the_anti_leak_instruction_is_unconditional_across_both_branches():
    """bd polyglot-pdf-djnk's guarantee must hold on EVERY rejection, whichever
    recovery is chosen -- that is the half that stops a dead value landing on
    the next field."""
    for errors in ([_format_error()], [_options_error()],
                   [_format_error(), _options_error()]):
        msg = _formatter(validation_errors=errors)["message"]
        assert "DISCARD the rejected value(s) above" in msg
        assert "Never reuse a rejected value" in msg
