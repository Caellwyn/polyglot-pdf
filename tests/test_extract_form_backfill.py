"""Tests for extract_form.py's pdf_position back-fill (bd polyglot-pdf-7a9.18,
extended by bd polyglot-pdf-5f41 to also back-fill per-OPTION pdf_position).

The original bug: the LLM emits a placeholder pdf_position {x:0,y:0,width:0,
height:0} that is a truthy dict, so the original `if field.get('pdf_position'):
continue` skipped back-fill and left the zeros -- the editor then could not map
the field to the PDF (click-to-jump dead). The fix back-fills when the position
is MISSING *or* DEGENERATE (non-positive width/height) from the deterministic
AcroForm dump.

bd 5f41 extends the same join to each field's options[]: a radio/checkbox_group
option's own widget rect is resolved the same way (name lookup is suffix-aware,
matching schema_lint._match_dump_names' exact-then-dot-boundary-suffix
convention), disambiguated by pdf_on_value when a name covers several widgets,
or resolved purely by pdf_on_value for the shared-field-name radio/combo-group
shape. `_backfill_positions` now returns
{"fields_filled", "options_filled", "unmatched"} instead of a bare field count.

These tests pin that behavior with synthetic data (no PDF / LLM needed): a
degenerate-zero field and a missing-position field both get the dump rect; a
field that already has a usable position is left untouched.

Imports extract_form by file path (repo precedent: test_bd_safe.py); it adds
scripts/bakeoff to sys.path at import for acroform_dump/arm_llm_native, which is
harmless here since we never call those.
"""

import importlib.util
import json
import pathlib
import sys

import pytest


_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
_SCRIPT = _REPO / "scripts" / "authoring" / "extract_form.py"
spec = importlib.util.spec_from_file_location("extract_form", _SCRIPT)
ef = importlib.util.module_from_spec(spec)
sys.modules["extract_form"] = ef
spec.loader.exec_module(ef)


# --- _has_usable_position --------------------------------------------------- #

@pytest.mark.parametrize("pos,expected", [
    ({"page": 1, "x": 10, "y": 20, "width": 8, "height": 8}, True),
    ({"page": 1, "x": 0, "y": 0, "width": 0, "height": 0}, False),   # the bug case
    ({"page": 1, "x": 10, "y": 20, "width": 0, "height": 8}, False), # zero width
    ({"page": 1, "x": 10, "y": 20, "width": 8, "height": 0}, False), # zero height
    ({"page": 1, "x": 10, "y": 20}, False),                          # missing w/h
    (None, False),
    ("not a dict", False),
    ({"width": "abc", "height": "def"}, False),                     # non-numeric
])
def test_has_usable_position(pos, expected):
    assert ef._has_usable_position(pos) is expected


# --- _backfill_positions ---------------------------------------------------- #

def _write_dump(tmp_path, name_to_rect):
    """Write a minimal acroform-dump JSON: {fields:[{name, widgets:[{rect}]}]}."""
    dump = {"fields": [
        {"name": n, "widgets": [{"rect": r}]} for n, r in name_to_rect.items()
    ]}
    p = tmp_path / "dump.json"
    p.write_text(json.dumps(dump), encoding="utf-8")
    return str(p)


def test_backfill_replaces_degenerate_zero_position(tmp_path):
    """The core bug: a field with an all-zero pdf_position is back-filled from the
    dump rect (page is +1'd: dump pages are 0-based, schema is 1-based)."""
    dump = _write_dump(tmp_path, {
        "topmostSubform[0].Page1[0].f1_47[0]": {
            "page": 0, "x": 100.0, "y": 200.0, "width": 8.0, "height": 8.0},
    })
    schema = {"fields": [{
        "id": "agent_ptin",
        "pdf_field_name": "topmostSubform[0].Page1[0].f1_47[0]",
        "pdf_position": {"page": 1, "x": 0, "y": 0, "width": 0, "height": 0},
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result == {"fields_filled": 1, "options_filled": 0, "unmatched": []}
    assert schema["fields"][0]["pdf_position"] == {
        "page": 1, "x": 100.0, "y": 200.0, "width": 8.0, "height": 8.0}


def test_backfill_fills_missing_position(tmp_path):
    dump = _write_dump(tmp_path, {
        "fld": {"page": 2, "x": 5, "y": 6, "width": 7, "height": 9}})
    schema = {"fields": [{"id": "a", "pdf_field_name": "fld"}]}  # no pdf_position
    result = ef._backfill_positions(schema, dump)
    assert result == {"fields_filled": 1, "options_filled": 0, "unmatched": []}
    assert schema["fields"][0]["pdf_position"]["page"] == 3  # 2 + 1


def test_backfill_preserves_a_usable_position(tmp_path):
    """A field that ALREADY has a real (positive w/h) position is left as-is, even
    if the dump has a different rect for it -- the LLM/human value wins when valid."""
    dump = _write_dump(tmp_path, {
        "fld": {"page": 0, "x": 999, "y": 999, "width": 1, "height": 1}})
    good = {"page": 1, "x": 10, "y": 20, "width": 8, "height": 8}
    schema = {"fields": [{"id": "a", "pdf_field_name": "fld", "pdf_position": dict(good)}]}
    result = ef._backfill_positions(schema, dump)
    assert result == {"fields_filled": 0, "options_filled": 0, "unmatched": []}
    assert schema["fields"][0]["pdf_position"] == good


def test_backfill_uses_first_option_widget_for_consolidated_field(tmp_path):
    """A consolidated options[] field (no top-level pdf_field_name) takes the rect
    of its first option's widget."""
    dump = _write_dump(tmp_path, {
        "opt1": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}})
    schema = {"fields": [{
        "id": "radio",
        "pdf_position": {"page": 1, "x": 0, "y": 0, "width": 0, "height": 0},
        "options": [{"value": "a", "pdf_field_name": "opt1"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # The field's own position AND its single option's position both resolve to
    # the same "opt1" widget rect (one join, both levels backfilled).
    assert result == {"fields_filled": 1, "options_filled": 1, "unmatched": []}
    # Full rect, incl. the page +1 (dump page 0 -> schema page 1).
    assert schema["fields"][0]["pdf_position"] == {
        "page": 1, "x": 1, "y": 2, "width": 8, "height": 8}
    assert schema["fields"][0]["options"][0]["pdf_position"] == {
        "page": 1, "x": 1, "y": 2, "width": 8, "height": 8}


def test_backfill_prefers_top_level_pdf_field_name_over_options(tmp_path):
    """When a field has BOTH a top-level pdf_field_name and options[], the
    top-level name wins (the options branch only runs when pfn is absent)."""
    dump = _write_dump(tmp_path, {
        "top": {"page": 0, "x": 10, "y": 10, "width": 8, "height": 8},
        "opt1": {"page": 0, "x": 99, "y": 99, "width": 8, "height": 8}})
    schema = {"fields": [{
        "id": "f", "pdf_field_name": "top",
        "options": [{"value": "a", "pdf_field_name": "opt1"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # The field resolves via its own "top" name; the option independently
    # resolves via its own "opt1" name -- the two levels don't share a value.
    assert result == {"fields_filled": 1, "options_filled": 1, "unmatched": []}
    assert schema["fields"][0]["pdf_position"]["x"] == 10  # top, not opt1
    assert schema["fields"][0]["options"][0]["pdf_position"]["x"] == 99  # opt1


def test_backfill_leaves_degenerate_when_no_dump_match(tmp_path):
    """If a degenerate field's pdf_field_name is absent from the dump, it stays
    degenerate (we can't do better) and is NOT counted as filled."""
    dump = _write_dump(tmp_path, {"other": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}})
    schema = {"fields": [{
        "id": "a", "pdf_field_name": "missing",
        "pdf_position": {"page": 1, "x": 0, "y": 0, "width": 0, "height": 0},
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result == {"fields_filled": 0, "options_filled": 0, "unmatched": []}
    assert not ef._has_usable_position(schema["fields"][0]["pdf_position"])


# --- option-level pdf_position back-fill (bd polyglot-pdf-5f41) -------------- #

def _write_widget_dump(tmp_path, fields):
    """Write a dump {fields:[{name, widgets:[{rect[, on_value]}, ...]}]}."""
    p = tmp_path / "dump.json"
    p.write_text(json.dumps({"fields": fields}), encoding="utf-8")
    return str(p)


def test_backfill_option_single_widget_via_own_pdf_field_name(tmp_path):
    """A radio option with its own pdf_field_name resolving to exactly ONE
    dump widget takes that widget's rect. Name resolution is suffix-aware
    (schema stores the XFA leaf, dump stores the fully-qualified path)."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "form1[0].#subform[0].P1_checkbox4[0]",
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]},
    ])
    schema = {"fields": [{
        "id": "p1_checkbox4", "type": "radio",
        "options": [{"value": "yes", "pdf_field_name": "P1_checkbox4[0]"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # fields_filled=1: the positionless field ALSO resolves via its first
    # option's widget (the pre-5f41 consolidated-field convention).
    assert result == {"fields_filled": 1, "options_filled": 1, "unmatched": []}
    assert schema["fields"][0]["options"][0]["pdf_position"] == {
        "page": 1, "x": 1, "y": 2, "width": 8, "height": 8}


def test_backfill_option_multi_widget_disambiguated_by_on_value(tmp_path):
    """When an option's pdf_field_name resolves to SEVERAL dump widgets (a
    shared alias), pdf_on_value picks the matching widget's rect."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "shared[0]", "widgets": [
            {"rect": {"page": 0, "x": 1, "y": 1, "width": 8, "height": 8}, "on_value": "1"},
            {"rect": {"page": 0, "x": 2, "y": 2, "width": 8, "height": 8}, "on_value": "2"},
        ]},
    ])
    schema = {"fields": [{
        "id": "f", "type": "radio",
        "options": [{"value": "b", "pdf_field_name": "shared[0]", "pdf_on_value": "2"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # fields_filled=1: the positionless field takes the group's FIRST widget
    # (first-wins field convention); the option picks its on_value match.
    assert result == {"fields_filled": 1, "options_filled": 1, "unmatched": []}
    assert schema["fields"][0]["options"][0]["pdf_position"]["x"] == 2


def test_backfill_shared_field_name_radio_group_by_on_value(tmp_path):
    """The documented shared-name radio-group shape (form_models.py
    FieldOption.pdf_on_value docstring): the option carries NO pdf_field_name of
    its own, only pdf_on_value, and the FIELD's pdf_field_name names the shared
    TOGGLE-widget group (each widget carries an on_value)."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "P3_Line8_HeightFeet[0]", "widgets": [
            {"rect": {"page": 0, "x": 5, "y": 5, "width": 8, "height": 8}, "on_value": "2"},
            {"rect": {"page": 0, "x": 6, "y": 6, "width": 8, "height": 8}, "on_value": "3"},
        ]},
    ])
    schema = {"fields": [{
        "id": "p3_line8_heightfeet", "type": "select",
        "pdf_field_name": "P3_Line8_HeightFeet[0]",
        "options": [
            {"value": "2", "label": "2", "pdf_on_value": "2"},
            {"value": "3", "label": "3", "pdf_on_value": "3"},
        ],
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result["options_filled"] == 2
    assert result["unmatched"] == []
    opts = schema["fields"][0]["options"]
    assert opts[0]["pdf_position"]["x"] == 5
    assert opts[1]["pdf_position"]["x"] == 6


def test_backfill_option_position_idempotent(tmp_path):
    """An option that already carries a USABLE pdf_position is left untouched,
    even though the dump has a different rect for its name (LLM/human value
    wins when valid -- same idempotence contract as the field level)."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "opt1", "widgets": [
            {"rect": {"page": 0, "x": 999, "y": 999, "width": 1, "height": 1}}]},
    ])
    good = {"page": 1, "x": 10, "y": 20, "width": 8, "height": 8}
    schema = {"fields": [{
        "id": "f", "type": "radio",
        "options": [{"value": "a", "pdf_field_name": "opt1", "pdf_position": dict(good)}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # The OPTION is untouched (options_filled=0); the positionless FIELD still
    # back-fills from the option's widget name (pre-5f41 convention), so
    # fields_filled=1 -- option idempotence is what this test pins.
    assert result == {"fields_filled": 1, "options_filled": 0, "unmatched": []}
    assert schema["fields"][0]["options"][0]["pdf_position"] == good


def test_backfill_option_unmatched_bogus_name_is_reported_not_guessed(tmp_path):
    """An option whose pdf_field_name matches NOTHING in the dump is recorded in
    `unmatched` (field id, option value, reason) -- never guessed at (e.g. by
    falling back to some other option's widget)."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "real[0]", "widgets": [
            {"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]},
    ])
    schema = {"fields": [{
        "id": "f", "type": "radio",
        "options": [{"value": "a", "pdf_field_name": "totally_bogus_name[0]"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result["options_filled"] == 0
    assert "pdf_position" not in schema["fields"][0]["options"][0]
    assert result["unmatched"] == [{
        "field_id": "f", "option_value": "a",
        "reason": "pdf_field_name 'totally_bogus_name[0]' not found in dump",
    }]


def test_backfill_dropdown_options_silently_skipped_not_unmatched(tmp_path):
    """A shared-name group whose widgets carry NO on_value is a dropdown
    (combobox/listbox -- real precedent: i-90's P3_Line8_HeightFeet /
    HeightInches selects): its options are choice VALUES of one shared widget,
    not separate printed boxes. They are silently skipped -- no option
    pdf_position, and NOT reported as unmatched (Preview keeps painting the
    selected label at the field-level rect)."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "P3_Line8_HeightFeet[0]", "widgets": [
            {"rect": {"page": 0, "x": 5, "y": 5, "width": 40, "height": 12}}]},
    ])
    schema = {"fields": [{
        "id": "p3_line8_heightfeet", "type": "select",
        "pdf_field_name": "P3_Line8_HeightFeet[0]",
        "options": [
            {"value": "2", "label": "2", "pdf_on_value": "2"},
            {"value": "3", "label": "3", "pdf_on_value": "3"},
        ],
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result["options_filled"] == 0
    assert result["unmatched"] == []
    assert all("pdf_position" not in o for o in schema["fields"][0]["options"])


def test_backfill_shared_field_name_unmatched_on_value_is_reported(tmp_path):
    """Shared-name shape where NO widget in the group carries the option's
    pdf_on_value: reported in `unmatched`, not silently skipped or guessed."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "grp[0]", "widgets": [
            {"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}, "on_value": "1"}]},
    ])
    schema = {"fields": [{
        "id": "f", "type": "select", "pdf_field_name": "grp[0]",
        "options": [{"value": "9", "label": "9", "pdf_on_value": "9"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result["options_filled"] == 0
    assert result["unmatched"] == [{
        "field_id": "f", "option_value": "9",
        "reason": "no widget in 'grp[0]' group with on_value '9'",
    }]


# --- _backfill_unclaimed_widgets (bd polyglot-pdf-w0eq, P6.1c) --------------- #

def _write_logical_dump(tmp_path, name_to_logical):
    """Minimal dump carrying per-widget logical_type + a rect."""
    dump = {"fields": [
        {"name": n, "logical_type": lt,
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]}
        for n, lt in name_to_logical.items()
    ]}
    p = tmp_path / "ldump.json"
    p.write_text(json.dumps(dump), encoding="utf-8")
    return str(p)

def test_backfill_adds_a_field_for_an_unclaimed_widget(tmp_path):
    """The core coverage fix: a fillable dump widget NO field claims is added
    back as a basic field with its dump rect. Section filing is NOT done here
    (bd 6cfu.2): the field carries a placeholder section_id='' and the derived-
    division pass (pipeline step 3e) re-files every field right after."""
    dump = _write_logical_dump(tmp_path, {
        "claimed[0]": "text", "orphan[0]": "text"})
    schema = {
        "fields": [{"id": "a", "type": "text", "pdf_field_name": "claimed[0]"}],
        "sections": [{"id": "sec1", "page_numbers": [1], "fields": ["a"]}],
    }
    assert ef._backfill_unclaimed_widgets(schema, dump) == 1
    added = [f for f in schema["fields"] if f["pdf_field_name"] == "orphan[0]"]
    assert len(added) == 1
    assert added[0]["type"] == "text"
    assert added[0]["section_id"] == ""  # step 3e (derivation) re-files it
    assert added[0]["pdf_position"]["page"] == 1  # the rect derivation needs
    # Pre-existing sections are left alone -- derivation owns them now.
    assert schema["sections"] == [
        {"id": "sec1", "page_numbers": [1], "fields": ["a"]}]


def test_backfill_types_a_checkbox_widget_as_v2_boolean_no_options(tmp_path):
    """A recovered checkbox is a v2 standalone boolean: type=checkbox carrying its
    widget in pdf_field_name, and NO options (options are forbidden on a v2
    checkbox -- a group would be checkbox_group)."""
    dump = _write_logical_dump(tmp_path, {"box[0]": "checkbox"})
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 1
    f = schema["fields"][0]
    assert f["type"] == "checkbox"
    assert f["pdf_field_name"] == "box[0]"
    assert "options" not in f  # a v2 checkbox is a boolean, not an options field


def test_backfill_types_a_lone_radio_widget_as_a_v2_checkbox(tmp_path):
    """A lone recovered radio widget (one dump entry, single toggle) is modeled as
    a v2 boolean checkbox -- NOT a 1-option radio, which v2 rejects (radio needs
    >=2 options). This is the round-2 fresh-eyes fix: the old code minted an
    invalid single-option radio that failed FormSchema.model_validate."""
    dump = _write_logical_dump(tmp_path, {"r[0]": "radio"})
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 1
    f = schema["fields"][0]
    assert f["type"] == "checkbox"
    assert "options" not in f


def test_backfill_excludes_decorative_buttons(tmp_path):
    """A button widget (reset/print) is NOT a coverage defect -- never backfilled."""
    dump = _write_logical_dump(tmp_path, {"btn[0]": "button"})
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 0


def test_acroform_dumper_type_names_cover_every_widget_type():
    """The button exclusion (and every logical_type-keyed rule downstream) only
    works if the REAL dumper NAMES every widget type instead of falling through to
    "unknown(N)" (bd polyglot-pdf-f31h -- PDF_WIDGET_TYPE_BUTTON was the one
    missing, so real buttons became "unknown(1)" and would be backfilled as fake
    text fields). Enumerate fitz's PDF_WIDGET_TYPE_* constants and assert
    _TYPE_NAMES maps every one EXCEPT UNKNOWN -- so a future PyMuPDF widget-type
    addition fails HERE, loudly, instead of silently re-opening the bug class."""
    import sys
    sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
    try:
        import acroform_dump
        import fitz
    except ImportError:
        pytest.skip("acroform_dump / fitz not importable")
    # Buttons specifically (the f31h regression) map to the literal "button".
    assert acroform_dump._TYPE_NAMES.get(fitz.PDF_WIDGET_TYPE_BUTTON) == "button"
    # Completeness: every PDF_WIDGET_TYPE_* constant except UNKNOWN is mapped.
    constants = {
        name: getattr(fitz, name)
        for name in dir(fitz) if name.startswith("PDF_WIDGET_TYPE_")
    }
    missing = [
        name for name, val in constants.items()
        if name != "PDF_WIDGET_TYPE_UNKNOWN" and val not in acroform_dump._TYPE_NAMES
    ]
    assert not missing, (
        "acroform_dump._TYPE_NAMES is missing a mapping for: "
        + ", ".join(sorted(missing))
        + " -- these widgets would become 'unknown(N)' and slip past every "
        "logical_type-keyed rule (bd f31h)"
    )


def test_backfill_recovers_dropdowns_using_real_dumper_strings(tmp_path):
    """The dumper emits "combobox"/"listbox"/"signature" (not "combo"/"list") --
    round-3 fresh-eyes flagged the dict keys were dead. A recovered dropdown /
    signature widget becomes a v2-valid text field."""
    dump = _write_logical_dump(tmp_path, {
        "cmb[0]": "combobox", "lst[0]": "listbox", "sig[0]": "signature"})
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 3
    assert all(f["type"] == "text" for f in schema["fields"])


def test_backfill_excludes_machine_barcodes(tmp_path):
    """A PDF417/QR barcode widget (read-only text, but machine-generated -- name
    carries the marker) is NOT a coverage defect. The bug caught pre-PR: i-90's
    hidden PDF417 barcodes were wrongly backfilled as fake text fields."""
    dump = {"fields": [
        {"name": "form1[0].Page1[0].PDF417BarCode1[0]", "logical_type": "text",
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8},
                      "read_only": True, "tu": "PDF417BarCode1"}]},
    ]}
    p = tmp_path / "bc.json"; p.write_text(json.dumps(dump), encoding="utf-8")
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, str(p)) == 0


def test_backfill_never_touches_sections(tmp_path):
    """The derived world (bd 6cfu.2): backfill neither creates nor edits
    sections -- no 'recovered_fields' bucket, no page_numbers bookkeeping.
    The recovered field carries section_id='' and derive_and_apply (step 3e)
    files it into a derived section (or the 'To review (unplaced)' bucket if
    it somehow has no position), so nothing is orphaned."""
    dump = _write_logical_dump(tmp_path, {"orphan[0]": "text"})
    schema = {"fields": []}  # no 'sections' key at all
    assert ef._backfill_unclaimed_widgets(schema, dump) == 1
    f = schema["fields"][0]
    assert f["section_id"] == ""
    assert "sections" not in schema  # untouched -- derivation owns sections


def test_backfilled_fields_always_validate_as_v2(tmp_path):
    """Every backfilled type (checkbox/text) must be VALID under v2 strictness --
    the round-2 fresh-eyes gap: a backfilled radio got 1 option and failed
    FormSchema.model_validate ('radio requires at least 2 options'), and combo/
    list -> select would likewise need options a bare widget can't supply. Pin
    that a mixed dump yields a valid v2 schema. Uses the REAL dumper logical_type
    strings (combobox/listbox/signature), so it exercises the actual mapping keys."""
    import warnings
    from backend.models.form_models import FormSchema
    dump = _write_logical_dump(tmp_path, {
        "cb[0]": "checkbox", "rad[0]": "radio", "txt[0]": "text",
        "combo[0]": "combobox", "list[0]": "listbox", "sig[0]": "signature"})
    schema = {
        "schema_version": "2", "source": "pdf",
        "form_metadata": {"title": "T", "version": "1"},
        "sections": [{"id": "s", "label": "S", "order": 1,
                      "page_numbers": [1], "fields": []}],
        "fields": [],
    }
    assert ef._backfill_unclaimed_widgets(schema, dump) == 6
    # No options-bearing type was minted (all valid with zero options).
    assert {f["type"] for f in schema["fields"]} <= {"checkbox", "text"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        FormSchema.model_validate(schema)  # raises if any field is v2-invalid


def test_backfill_positions_recovered_fields_one_based(tmp_path):
    """Recovered fields carry 1-based pdf_position pages from the 0-based dump
    rects -- the join key the derived-division pass files them by (bd 6cfu.2)."""
    dump = {"fields": [
        {"name": "a[0]", "logical_type": "text",
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]},
        {"name": "b[0]", "logical_type": "text",
         "widgets": [{"rect": {"page": 2, "x": 1, "y": 2, "width": 8, "height": 8}}]},
    ]}
    p = tmp_path / "d.json"; p.write_text(json.dumps(dump), encoding="utf-8")
    schema = {"fields": []}
    assert ef._backfill_unclaimed_widgets(schema, str(p)) == 2
    assert sorted(f["pdf_position"]["page"] for f in schema["fields"]) == [1, 3]
    assert "sections" not in schema


def test_backfill_degenerate_leaf_falls_back_to_id_for_labels(tmp_path):
    """A widget name whose leaf is empty (ends in '.') still gets non-empty
    name/spoken_name (falls back to the minted id, never blank)."""
    dump = {"fields": [
        {"name": "weird.", "logical_type": "text",
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]},
    ]}
    p = tmp_path / "d.json"; p.write_text(json.dumps(dump), encoding="utf-8")
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, str(p)) == 1
    f = schema["fields"][0]
    assert f["name"] and f["spoken_name"]  # never blank


def test_backfill_is_a_noop_when_all_widgets_claimed(tmp_path):
    dump = _write_logical_dump(tmp_path, {"a[0]": "text"})
    schema = {"fields": [{"id": "a", "type": "text", "pdf_field_name": "a[0]"}],
              "sections": [{"id": "s", "page_numbers": [1], "fields": ["a"]}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 0


def test_backfill_claim_is_suffix_aware(tmp_path):
    """A field claiming the bare leaf 'x[0]' covers the fully-qualified dump name
    'topmostSubform[0].Page1[0].x[0]' -- so it is NOT re-backfilled."""
    dump = {"fields": [{
        "name": "topmostSubform[0].Page1[0].x[0]", "logical_type": "text",
        "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}],
    }]}
    p = tmp_path / "d.json"; p.write_text(json.dumps(dump), encoding="utf-8")
    schema = {"fields": [{"id": "a", "type": "text", "pdf_field_name": "x[0]"}],
              "sections": [{"id": "s", "page_numbers": [1], "fields": ["a"]}]}
    assert ef._backfill_unclaimed_widgets(schema, str(p)) == 0
