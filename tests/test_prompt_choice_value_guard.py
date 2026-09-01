"""A prompt builder may never crash on a choice dict missing "value"
(bd polyglot-pdf-r311s).

Both `acroform_field_list` (scripts/bakeoff/schema_contract.py) and
`enriched_field_list` (scripts/bakeoff/structural_enrich.py) render a
widget's /Opt choice sample. Direct dict indexing (`c["value"]`) raised
`KeyError` on any choice dict lacking a "value" key -- a malformed/
hand-edited dump, or a future dump producer with a different choice
shape. Not reachable via the current acroform_dump.py producer (it
always writes value+display), but a latent crash risk on the hot path
every extraction runs through, contradicting the rest of the file's
defensive `.get()` style.

Pinned over BOTH builders together, same reasoning as the sibling
test_prompt_choice_truncation.py (bd hmkas): they carry the same
rendering logic, and a fix applied to one and not the other is exactly
the shape this repo keeps paying for (CLAUDE.md scar #8 -- enumerate
the set).

ASCII only.
"""
from __future__ import annotations

import importlib.util
import pathlib
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


def _dump_with_choices(choices: list) -> dict:
    """A one-combobox dump whose /Opt list is exactly `choices` (verbatim,
    not synthesized) -- so a test can hand it a value-less dict."""
    return {
        "field_count": 1, "widget_count": 1, "page_count": 1,
        "fields": [{
            "name": "form1[0].P1_Line6e_State[0]",
            "logical_type": "combobox",
            "widget_count": 1,
            "widgets": [{
                "rect": {"page": 0, "x": 1, "y": 2, "width": 36, "height": 18},
                "choices": choices,
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
def test_a_choice_dict_missing_value_does_not_crash(render):
    """The bead's own repro: a choice dict with no "value" key must not
    raise KeyError -- it degrades to a skipped sample entry instead."""
    dump = _dump_with_choices([{"display": "x"}])
    text = render(dump)  # must not raise
    assert "choices=[" in text


@pytest.mark.parametrize("render", _BUILDERS)
def test_a_mix_of_valid_and_valueless_choices_renders_only_the_valid_ones(render):
    """A value-less entry is SKIPPED from the sample, not substituted with a
    placeholder that could be mistaken for a real option value."""
    dump = _dump_with_choices([
        {"value": "AL", "display": "Alabama"},
        {"display": "no value here"},
        {"value": "AK", "display": "Alaska"},
    ])
    text = render(dump)
    assert "AL" in text
    assert "AK" in text
    # Exactly two real values rendered, comma-joined with nothing else.
    assert "choices=[AL,AK]" in text, text


@pytest.mark.parametrize("render", _BUILDERS)
def test_all_choices_valueless_renders_an_empty_but_present_choices_clause(render):
    """Degrades gracefully all the way to an empty sample rather than
    crashing, even in the worst case where nothing is usable.

    Asserts the exact empty-bracket form, not merely "contains 'choices='"
    -- that weaker check is satisfied by ANY rendered clause regardless of
    content (caught during review: it would still pass if garbage leaked
    into the brackets)."""
    dump = _dump_with_choices([{"display": "a"}, {"display": "b"}])
    text = render(dump)  # must not raise
    assert "choices=[]" in text, text


@pytest.mark.parametrize("render", _BUILDERS)
def test_a_valueless_choice_within_the_first_12_does_not_undercount_more(render):
    """The "more" count must stay accurate even when a value-less choice
    falls WITHIN the sampled window, not just past it.

    Filtering AFTER slicing to 12 (an earlier version of this fix) would
    shrink the rendered sample below 12 whenever a value-less dict landed
    in the first 12 slots, while "more" still only counted entries past
    index 12 -- silently undercounting how many usable values actually
    exist (shown + more != total usable), exactly the unmarked-truncation
    failure bd hmkas exists to prevent (caught by the Opus cross-surface
    review). 14 usable values plus 1 value-less entry inserted at index 5:
    the sample must still show 12 real values and report "2 more" (14 - 12),
    not 11 shown + a count computed against the wrong denominator."""
    choices = [{"value": "C%02d" % i, "display": "C%02d" % i} for i in range(14)]
    choices.insert(5, {"display": "no value, inserted mid-sample"})
    dump = _dump_with_choices(choices)
    text = render(dump)
    assert "and 2 more" in text, text
    # Exactly 12 real values shown, comma-joined, none of them the
    # value-less placeholder.
    shown = text.split("choices=[")[1].split(",")
    shown_values = [v.strip() for v in shown if v.strip() and "more" not in v and "..." not in v]
    assert len(shown_values) == 12, (len(shown_values), shown_values)


@pytest.mark.parametrize("render", _BUILDERS)
def test_a_non_dict_choice_entry_does_not_crash(render):
    """The guard's isinstance(c, dict) half, pinned separately from its
    "value" in c half: a non-dict entry (a bare string, None) would raise
    TypeError on `"value" in c` for a string, or crash outright on `c["value"]`
    for a bool/None, if only the key-presence check were kept."""
    dump = _dump_with_choices([
        {"value": "AL", "display": "Alabama"},
        "not_a_dict",
        None,
    ])
    text = render(dump)  # must not raise
    assert "choices=[AL]" in text, text
