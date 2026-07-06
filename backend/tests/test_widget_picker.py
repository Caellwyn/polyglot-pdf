"""Tests for backend/services/widget_picker.py (bd polyglot-pdf-nivy, P5.3c).

unclaimed_button_widgets returns the dump's checkbox/radio widgets that no
field/option in the schema claims -- the candidates the "Add from PDF widgets"
picker offers. ASCII only.
"""
from __future__ import annotations

from backend.services.widget_picker import unclaimed_button_widgets


def _btn(name, on, tip=None, page=0, ltype="checkbox"):
    w = {"type": ltype, "on_value": on, "rect": {"page": page}}
    if tip:
        w["tu"] = tip
    return {"name": name, "logical_type": ltype, "widgets": [w]}


_DUMP = {
    "fields": [
        _btn("form1[0].reason[0]", "1", "Employment"),
        _btn("form1[0].reason[1]", "2", "Family"),
        _btn("form1[0].reason[2]", "3", "Other"),
        # A text widget is NOT an addable button option.
        {"name": "form1[0].name[0]", "logical_type": "text",
         "widgets": [{"type": "text", "rect": {"page": 0}}]},
    ]
}


def test_returns_button_widgets_no_field_claims():
    # No field claims anything -> all 3 checkboxes are unclaimed (text excluded).
    schema = {"fields": []}
    got = unclaimed_button_widgets(schema, _DUMP)
    assert [w["name"] for w in got] == [
        "form1[0].reason[0]", "form1[0].reason[1]", "form1[0].reason[2]",
    ]
    # Each carries the mint inputs (name / on_value / tooltip / page).
    assert got[0] == {"name": "form1[0].reason[0]", "type": "checkbox",
                      "on_value": "1", "tooltip": "Employment", "page": 0}


def test_excludes_option_claimed_widgets_via_dot_suffix():
    # A schema option claims reason[0] by its LEAF (dot-suffix match, the linter's
    # convention) -> only reason[1], reason[2] remain unclaimed.
    schema = {"fields": [{"id": "reasons", "type": "checkbox_group", "options": [
        {"value": "employment", "pdf_field_name": "form1[0].reason[0]"},
    ]}]}
    got = unclaimed_button_widgets(schema, _DUMP)
    assert [w["name"] for w in got] == [
        "form1[0].reason[1]", "form1[0].reason[2]",
    ]


def test_excludes_field_level_claim():
    # A standalone checkbox field claims reason[1] at field level.
    schema = {"fields": [{"id": "c", "type": "checkbox",
                          "pdf_field_name": "form1[0].reason[1]"}]}
    got = unclaimed_button_widgets(schema, _DUMP)
    assert "form1[0].reason[1]" not in [w["name"] for w in got]


def test_no_dump_returns_empty():
    assert unclaimed_button_widgets({"fields": []}, None) == []
    assert unclaimed_button_widgets({"fields": []}, {}) == []
    assert unclaimed_button_widgets({"fields": []}, {"fields": "oops"}) == []


def test_radio_widgets_are_addable_too():
    dump = {"fields": [_btn("form1[0].sex[0]", "M", "Male", ltype="radio"),
                       _btn("form1[0].sex[1]", "F", "Female", ltype="radio")]}
    got = unclaimed_button_widgets({"fields": []}, dump)
    assert [w["type"] for w in got] == ["radio", "radio"]


def _shared_radio():
    # A TRUE single-name AcroForm radio group: one field name, N kids differing
    # only by on_value (bd nivy fresh-eyes -- the shape widgets[0] used to drop).
    return {"fields": [{
        "name": "form1[0].sex[0]", "logical_type": "radio", "widget_count": 2,
        "widgets": [
            {"type": "radio", "on_value": "M", "tu": "Male", "rect": {"page": 0}},
            {"type": "radio", "on_value": "F", "tu": "Female", "rect": {"page": 0}},
        ],
    }]}


def test_shared_name_radio_surfaces_every_kid():
    got = unclaimed_button_widgets({"fields": []}, _shared_radio())
    # BOTH kids are addable, distinguished by on_value (not just widgets[0]).
    assert [(w["on_value"], w["tooltip"]) for w in got] == [
        ("M", "Male"), ("F", "Female"),
    ]


def test_shared_name_radio_partial_claim_leaves_the_rest():
    # An option claims the Male kid via the field name + pdf_on_value=M; the
    # Female kid must STILL be addable (the whole-name claim must not hide it).
    schema = {"fields": [{"id": "sex", "type": "radio",
                          "pdf_field_name": "form1[0].sex[0]",
                          "options": [{"value": "male", "pdf_on_value": "M"}]}]}
    got = unclaimed_button_widgets(schema, _shared_radio())
    assert [w["on_value"] for w in got] == ["F"]


def test_shared_name_radio_all_kids_claimed_is_empty():
    schema = {"fields": [{"id": "sex", "type": "radio",
                          "pdf_field_name": "form1[0].sex[0]",
                          "options": [{"value": "male", "pdf_on_value": "M"},
                                      {"value": "female", "pdf_on_value": "F"}]}]}
    assert unclaimed_button_widgets(schema, _shared_radio()) == []


def test_option_level_pdf_field_name_claims_whole_name():
    # A per-widget claim (option carries its OWN pdf_field_name) shadows the whole
    # name -- so if a shared-name group were (mis)modeled that way, all kids hide.
    schema = {"fields": [{"id": "sex", "type": "radio", "options": [
        {"value": "male", "pdf_field_name": "form1[0].sex[0]"}]}]}
    assert unclaimed_button_widgets(schema, _shared_radio()) == []


def test_malformed_entries_never_crash():
    dump = {"fields": [None, 7, {"logical_type": "checkbox"},  # no name
                       _btn("form1[0].ok[0]", "1")]}
    got = unclaimed_button_widgets({"fields": [None, "x"]}, dump)
    assert [w["name"] for w in got] == ["form1[0].ok[0]"]
