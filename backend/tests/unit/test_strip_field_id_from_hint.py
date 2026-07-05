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


def test_strips_when_an_option_value_contains_parens():
    # An option value can itself contain ")" (e.g. "Other (specify)"). The strip
    # must remove the WHOLE trailing group, not stop at the first ")" -- otherwise
    # a fragment like "]" or ")" is left dangling in the spoken text (fresh-eyes
    # + Copilot review of PR #112).
    hint = ("Next field to fill is #2: 'Employment Status' "
            "(field_id: 'p1_employment', type: select, required, options: [Other (specify), None])")
    out = strip_field_id_from_hint(hint)
    assert out == "Next field to fill is #2: 'Employment Status'"
    assert "field_id" not in out and "options" not in out and ")" not in out.split("'")[-1]


def test_strips_when_an_option_value_contains_an_apostrophe():
    # An option value can contain "'" (e.g. "O'Brien"). The field_id VALUE itself
    # never contains "'", but a later option might -- the end-anchored match still
    # removes the whole group.
    hint = ("Next field to fill is #5: 'Surname' "
            "(field_id: 'p1_surname', type: text, options: [O'Brien, Smith])")
    out = strip_field_id_from_hint(hint)
    assert out == "Next field to fill is #5: 'Surname'"
    assert "field_id" not in out


def test_keeps_the_spoken_name_even_when_it_contains_parens():
    # The spoken NAME itself may contain parentheses (e.g. "(A-Number)"). Only the
    # trailing "(field_id: ...)" group is removed, not the name's own parens.
    hint = "Next field to fill is #1: 'Alien Registration Number (A-Number)' (field_id: 'x', type: text)"
    out = strip_field_id_from_hint(hint)
    assert "(A-Number)" in out
    assert "field_id" not in out


def test_strips_field_id_but_keeps_the_bo4m_note_tail():
    # bd polyglot-pdf-bo4m: formatNextFieldHint now appends a fine-print note
    # AFTER the (field_id: ...) group. The strip must remove the id (dx7) but
    # KEEP the note (it is the context the model must speak). Before this fix the
    # end-anchored regex failed to match once a note followed, and the raw
    # field_id was spoken aloud again -- a dx7 regression on every note-bearing
    # field (Opus fallback review of PR #312).
    hint = ("Next field to fill is #4: 'Has Your Name Legally Changed?' "
            "(field_id: 'p1_checkbox4', type: radio). "
            "Context to briefly convey when asking: Indicate if your name has "
            "legally changed since your Permanent Resident Card was issued.")
    out = strip_field_id_from_hint(hint)
    assert "field_id" not in out and "p1_checkbox4" not in out
    assert "Context to briefly convey when asking: Indicate if your name" in out
    assert "  " not in out  # no doubled space where the group was removed
    assert out == ("Next field to fill is #4: 'Has Your Name Legally Changed?'. "
                   "Context to briefly convey when asking: Indicate if your name has "
                   "legally changed since your Permanent Resident Card was issued.")


def test_keeps_a_note_tail_that_itself_contains_parens():
    # The note (help.instructions) can contain its own "()" -- e.g. the A-Number
    # field's "(A-Number)". Peeling the note off by its fixed lead-in (not by the
    # last ")") keeps those parens intact while still stripping the field_id group.
    hint = ("Next field to fill is #1: 'Alien Registration Number' "
            "(field_id: 'p1_line1_aliennumber', type: text). "
            "Context to briefly convey when asking: Your alien registration number "
            "(A-Number) is a 7-9 digit number. It begins with an 'A'.")
    out = strip_field_id_from_hint(hint)
    assert "field_id" not in out
    assert "(A-Number)" in out  # the note's own parens survive
    assert out.endswith("It begins with an 'A'.")


def test_strips_option_parens_group_even_with_a_note_tail():
    # Combine the two hard cases: an option LABEL with ")" inside the field_id
    # group ("Other (specify)") AND a note tail. The group must be removed WHOLE
    # (its inner ")" must not end the strip early) and the note must remain.
    hint = ("Next field to fill is #2: 'Employment Status' "
            "(field_id: 'p1_employment', type: select, required, options: [Other (specify), None]). "
            "Context to briefly convey when asking: Pick the closest match.")
    out = strip_field_id_from_hint(hint)
    assert out == ("Next field to fill is #2: 'Employment Status'. "
                   "Context to briefly convey when asking: Pick the closest match.")
    assert "field_id" not in out and "options" not in out


def test_noop_when_no_field_id_present():
    hint = "Next field to fill is #1: 'First Name'"
    assert strip_field_id_from_hint(hint) == hint


def test_none_and_empty_pass_through():
    assert strip_field_id_from_hint(None) is None
    assert strip_field_id_from_hint("") == ""
