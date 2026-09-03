"""A prompt builder may never SILENTLY truncate a dropdown's choice list
(bd polyglot-pdf-hmkas, exit criterion 2).

Both builders render at most 12 choices. That cap is fine -- the full set is
backfilled deterministically from the dump (extract_form._backfill_dropdown_
options) -- but an UNMARKED cut is not: a bare 12-of-63 render reads as the
complete set, and asking a model to emit the other 51 from it invites
hallucination. The i-90 state dropdown showed 12 codes with no marker and came
out of extraction with no options at all.

Pinned over BOTH builders together: they carry the same rendering logic, and a
fix applied to one and not the other is exactly the shape this repo keeps
paying for (CLAUDE.md scar #8 -- enumerate the set).

ASCII only.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_BAKEOFF = _REPO / "scripts" / "bakeoff"
sys.path.insert(0, str(_BAKEOFF))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _BAKEOFF / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


schema_contract = _load("schema_contract")
structural_enrich = _load("structural_enrich")


def _dump(n_choices: int) -> dict:
    """A one-combobox dump whose /Opt list has n_choices entries."""
    return {
        "field_count": 1, "widget_count": 1, "page_count": 1,
        "fields": [{
            "name": "form1[0].P1_Line6e_State[0]",
            "logical_type": "combobox",
            "widget_count": 1,
            "widgets": [{
                "rect": {"page": 0, "x": 1, "y": 2, "width": 36, "height": 18},
                "choices": [{"value": "C%02d" % i, "display": "C%02d" % i}
                            for i in range(n_choices)],
            }],
        }],
    }


# Both builders, rendered the same way, so a fix to one and not the other fails.
_BUILDERS = [
    pytest.param(lambda d: schema_contract.acroform_field_list(d),
                 id="schema_contract.acroform_field_list"),
    pytest.param(lambda d: structural_enrich.enriched_field_list(d),
                 id="structural_enrich.enriched_field_list"),
]


@pytest.mark.parametrize("render", _BUILDERS)
def test_a_truncated_choice_list_says_how_many_were_omitted(render):
    text = render(_dump(63))
    assert "C00" in text and "C11" in text, "the sample itself must render"
    assert "C12" not in text, "still capped at 12"
    # The whole point: the reader can tell the list was cut, and by how much.
    assert "and 51 more" in text, text


@pytest.mark.parametrize("render", _BUILDERS)
@pytest.mark.parametrize("n", [1, 11, 12])
def test_a_COMPLETE_choice_list_carries_no_omission_marker(render, n):
    """No off-by-one: at exactly the cap the list IS complete, so a marker
    would be a lie."""
    text = render(_dump(n))
    assert "more]" not in text
    assert "and 0 more" not in text


@pytest.mark.parametrize("render", _BUILDERS)
def test_one_past_the_cap_is_marked(render):
    """The boundary in the other direction: 13 choices means exactly 1 omitted."""
    text = render(_dump(13))
    assert "and 1 more" in text, text


@pytest.mark.parametrize("render", _BUILDERS)
def test_a_field_with_no_choices_renders_no_choices_clause(render):
    dump = _dump(0)
    dump["fields"][0]["widgets"][0].pop("choices")
    text = render(dump)
    assert "choices=[" not in text


# --- the select contract must be stated CONSISTENTLY everywhere ------------ #


def test_no_rendered_passage_puts_a_selects_export_code_in_its_value():
    """Pins the SET, not the one instance (CLAUDE.md scar #8).

    Until bd polyglot-pdf-g2fpr a select's option.value WAS the PDF export
    code, and this test pinned a carve-out saying so in three places. Now a
    select's value is a SLUG and its export code lives in pdf_on_value (the
    filler writes that -- PR 1), so the invariant inverts: any rendered passage
    that talks about a select's export code must say WHERE it lives. A passage
    that names the code without pdf_on_value is the old contract leaking back
    in -- and the skeleton is what the model imitates first, so one stale
    statement is a contradiction it reads before the rule.

    Scans by SENTENCE, not by line, for the same reason as before: the
    skeleton splits one rule across lines.
    """
    text = schema_contract.SCHEMA_CONTRACT
    chunks = re.split(r"\n\s*\n|(?<=\.)\s", text)
    offenders = []
    for chunk in chunks:
        low = " ".join(chunk.lower().split())
        if not re.search(r"\bselect\b|\bdropdown\b", low):
            continue
        if "export code" not in low:
            continue
        if "pdf_on_value" in low or "never the export code" in low:
            continue
        offenders.append(low[:160])
    assert not offenders, (
        "these rendered passages name a select's export code without saying "
        "it lives in pdf_on_value:\n  " + "\n  ".join(offenders))


@pytest.mark.parametrize("what,needle", [
    # The JSON type skeleton -- what the model imitates first.
    ("skeleton", "its PDF export code in"),
    ("skeleton", "SLUG value minted from its"),
    # CHOICE-FIELD RULES -- the rule itself.
    ("choice-field rule", "each option's value is a"),
    ("choice-field rule", "is stored in option.pdf_on_value"),
    ("choice-field rule", "leave options[] out"),
    # The condition-reference rule -- a show_if on a select names the SLUG.
    ("condition rule", "A condition on a SELECT trigger uses that option's SLUG"),
    # Sits on ONE rendered line; the scan normalizes whitespace, this cannot.
    ("condition rule", 'is referenced as "wyoming"; never'),
])
def test_each_select_statement_is_present(what, needle):
    """Non-vacuity floor for the scan above, ONE STATEMENT PER CASE.

    The scan passes when no passage names a select's export code without its
    home -- which is also true if a statement is simply deleted. Each of the
    three places the contract is stated gets its own needle, keyed on text
    unique to it, so deleting any one of them fails here (the shape that was
    caught by mutation twice on the previous version of this test).
    """
    assert needle in schema_contract.SCHEMA_CONTRACT, (
        "the %s statement is missing; the scan above cannot see its absence, "
        "so this is the only thing pinning it" % what)
