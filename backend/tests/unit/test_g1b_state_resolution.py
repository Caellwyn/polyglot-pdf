"""option_label resolves a state picker through pdf_on_value (bd polyglot-pdf-bxjck,
landed in g2fpr.4). Separate from test_g1b_answer_key_coherence.py, which is
module-skipped without the retired i-90 kit on disk; this needs no kit.

ASCII only.
"""

from __future__ import annotations

def test_state_option_resolves_through_pdf_on_value_before_the_hand_built_map():
    """bd polyglot-pdf-bxjck / g2fpr.4: since the select migration a state
    picker's option carries its abbreviation in pdf_on_value, which is the
    authoritative reverse map -- including the 12 territories the hand-built
    table never had. The table is only a fallback for a schema without the
    channel."""
    from backend.scripts.g1b_answer_key import option_label
    field = {"id": "mail_state", "type": "select", "options": [
        {"value": "wyoming", "label": "Wyoming (WY)", "pdf_on_value": "WY"},
        {"value": "armed_forces_americas", "label": "Armed Forces Americas (AA)", "pdf_on_value": "AA"},
    ]}
    assert option_label(field, "wyoming") == "WY"
    assert option_label(field, "armed_forces_americas") == "AA"     # not in the table
    assert option_label(field, "TX") == "TX"                         # already a code
    legacy = {"id": "mail_state", "type": "select", "options": [
        {"value": "texas", "label": "Texas"}]}
    assert option_label(legacy, "texas") == "TX"                     # fallback survives
