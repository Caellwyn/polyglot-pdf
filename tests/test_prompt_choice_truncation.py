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


# --- the slug rule must be scoped EVERYWHERE, not just where it is stated --- #

def test_no_rendered_slug_rule_still_claims_to_cover_select():
    """Pins the SET, not the one instance (CLAUDE.md scar #8).

    The prompt states the option-value rule in several places: the JSON type
    skeleton, CHOICE-FIELD RULES, and the condition-reference rule. bd
    polyglot-pdf-hmkas scopes the slug rule to radio/checkbox_group -- a
    select's value is the PDF's own export code -- and fixing only ONE
    statement leaves the model reading a contradiction (the skeleton is what it
    imitates first).

    Scans by SENTENCE, not by line. The skeleton splits one rule across two
    lines ("radio/select/checkbox_group choices" then "option.value is a
    SEMANTIC SLUG"), so a line-by-line scan sees neither half naming BOTH and
    passes while the contradiction stands -- a false negative this test had
    until mutation caught it.
    """
    text = schema_contract.SCHEMA_CONTRACT
    # Blank-line / full-stop windows, so a rule wrapped across lines stays in
    # one chunk.
    chunks = re.split(r"\n\s*\n|(?<=\.)\s", text)
    offenders = []
    for chunk in chunks:
        low = " ".join(chunk.lower().split())
        if "slug" not in low:
            continue
        # The FIELD TYPE, not the English words "selected" / "selection".
        if not re.search(r"\bselect\b|\bdropdown\b", low):
            continue
        if any(k in low for k in ("is different", "does not apply", "not apply",
                                  "no slug", "export code", "omit",
                                  "leave options", "slugify these")):
            continue
        offenders.append(low[:160])
    assert not offenders, (
        "these rendered passages apply the slug rule to select:\n  "
        + "\n  ".join(offenders))


@pytest.mark.parametrize("what,needle", [
    # The JSON type skeleton -- what the model imitates first.
    ("skeleton", "its values are the PDF's own export codes"),
    # CHOICE-FIELD RULES -- the rule itself.
    ("choice-field rule", "For a SELECT (dropdown) this rule does NOT apply"),
    ("choice-field rule", "leave options[] out"),
    # The condition-reference rule -- a show_if on a select names the code.
    ("condition rule", "A condition on a SELECT trigger uses that dropdown's"),
])
def test_each_select_carve_out_statement_is_present(what, needle):
    """Non-vacuity floor for the scan above, ONE STATEMENT PER CASE.

    The scan passes when no passage sweeps select into the slug rule -- which is
    also true if a carve-out is simply deleted. Asserting a shared phrase like
    "export code" appears SOMEWHERE is too weak: three separate statements
    contain it, so deleting any one of them left the assertion green (caught by
    mutation, twice). Each statement therefore gets its own case, keyed on text
    unique to it.
    """
    assert needle in schema_contract.SCHEMA_CONTRACT, (
        "the %s carve-out is missing; the slug-scope scan cannot see its "
        "absence, so this is the only thing pinning it" % what)
