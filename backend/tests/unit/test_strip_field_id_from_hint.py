"""Unit tests for strip_field_id_from_hint (bd polyglot-pdf-dx7).

The frontend's formatNextFieldHint embeds a "(field_id: '...', type: ...)"
parenthetical in the SPOKEN hint; Gemini read it aloud. The backend strips it
before any hint reaches the spoken path. The field_id is still available to
Gemini via the system instruction's FIELDS block, so stripping the spoken hint
does not affect tool-calling.
"""

from backend.services.field_utils import strip_field_id_from_hint


def test_strips_the_real_frontend_hint_shape():
    # The exact shape from frontend/src/navigation.ts formatNextFieldHint.
    hint = ("Next field to fill is #1: 'Alien Registration Number (A-Number)' "
            "(field_id: 'p1_line1_aliennumber', type: text)")
    out = strip_field_id_from_hint(hint)
    assert out == "Next field to fill is #1: 'Alien Registration Number (A-Number)'"
    assert "field_id" not in out
    assert "p1_line1_aliennumber" not in out


def test_strips_with_required_and_options_suffixes():
    hint = ("Next field to fill is #3: 'Eye Color' "
            "(field_id: 'p1_eyecolor', type: select, required, options: [Brown, Blue])")
    out = strip_field_id_from_hint(hint)
    assert out == "Next field to fill is #3: 'Eye Color'"
    assert "field_id" not in out and "options" not in out


def test_keeps_the_spoken_name_even_when_it_contains_parens():
    # The spoken NAME itself may contain parentheses (e.g. "(A-Number)"). Only the
    # trailing "(field_id: ...)" group is removed, not the name's own parens.
    hint = "Next field to fill is #1: 'Alien Registration Number (A-Number)' (field_id: 'x', type: text)"
    out = strip_field_id_from_hint(hint)
    assert "(A-Number)" in out
    assert "field_id" not in out


def test_noop_when_no_field_id_present():
    hint = "Next field to fill is #1: 'First Name'"
    assert strip_field_id_from_hint(hint) == hint


def test_none_and_empty_pass_through():
    assert strip_field_id_from_hint(None) is None
    assert strip_field_id_from_hint("") == ""
