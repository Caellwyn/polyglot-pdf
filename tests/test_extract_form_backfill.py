"""Tests for extract_form.py's pdf_position back-fill (bd polyglot-pdf-7a9.18).

The bug: the LLM emits a placeholder pdf_position {x:0,y:0,width:0,height:0}
that is a truthy dict, so the original `if field.get('pdf_position'): continue`
skipped back-fill and left the zeros -- the editor then could not map the field
to the PDF (click-to-jump dead). The fix back-fills when the position is MISSING
*or* DEGENERATE (non-positive width/height) from the deterministic AcroForm dump.

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
    filled = ef._backfill_positions(schema, dump)
    assert filled == 1
    assert schema["fields"][0]["pdf_position"] == {
        "page": 1, "x": 100.0, "y": 200.0, "width": 8.0, "height": 8.0}


def test_backfill_fills_missing_position(tmp_path):
    dump = _write_dump(tmp_path, {
        "fld": {"page": 2, "x": 5, "y": 6, "width": 7, "height": 9}})
    schema = {"fields": [{"id": "a", "pdf_field_name": "fld"}]}  # no pdf_position
    assert ef._backfill_positions(schema, dump) == 1
    assert schema["fields"][0]["pdf_position"]["page"] == 3  # 2 + 1


def test_backfill_preserves_a_usable_position(tmp_path):
    """A field that ALREADY has a real (positive w/h) position is left as-is, even
    if the dump has a different rect for it -- the LLM/human value wins when valid."""
    dump = _write_dump(tmp_path, {
        "fld": {"page": 0, "x": 999, "y": 999, "width": 1, "height": 1}})
    good = {"page": 1, "x": 10, "y": 20, "width": 8, "height": 8}
    schema = {"fields": [{"id": "a", "pdf_field_name": "fld", "pdf_position": dict(good)}]}
    assert ef._backfill_positions(schema, dump) == 0
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
    assert ef._backfill_positions(schema, dump) == 1
    # Full rect, incl. the page +1 (dump page 0 -> schema page 1).
    assert schema["fields"][0]["pdf_position"] == {
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
    assert ef._backfill_positions(schema, dump) == 1
    assert schema["fields"][0]["pdf_position"]["x"] == 10  # top, not opt1


def test_backfill_leaves_degenerate_when_no_dump_match(tmp_path):
    """If a degenerate field's pdf_field_name is absent from the dump, it stays
    degenerate (we can't do better) and is NOT counted as filled."""
    dump = _write_dump(tmp_path, {"other": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}})
    schema = {"fields": [{
        "id": "a", "pdf_field_name": "missing",
        "pdf_position": {"page": 1, "x": 0, "y": 0, "width": 0, "height": 0},
    }]}
    assert ef._backfill_positions(schema, dump) == 0
    assert not ef._has_usable_position(schema["fields"][0]["pdf_position"])


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
    back as a basic field, filed into the section covering its page."""
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
    assert added[0]["section_id"] == "sec1"
    # The section's fields[] list learns about the recovered field too.
    assert added[0]["id"] in schema["sections"][0]["fields"]


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


def test_backfill_creates_a_bucket_section_when_none_exist(tmp_path):
    """No sections at backfill time: a recovered field must NOT be orphaned with
    section_id='' (validates + lints clean but is unreachable). A 'recovered_fields'
    bucket section is created so the field stays navigable."""
    dump = _write_logical_dump(tmp_path, {"orphan[0]": "text"})
    schema = {"fields": []}  # no 'sections' key at all
    assert ef._backfill_unclaimed_widgets(schema, dump) == 1
    f = schema["fields"][0]
    assert f["section_id"] == "recovered_fields"
    buckets = [s for s in schema["sections"] if s["id"] == "recovered_fields"]
    assert len(buckets) == 1
    assert f["id"] in buckets[0]["fields"]


def test_backfilled_fields_always_validate_as_v2(tmp_path):
    """Every backfilled type (checkbox/text) must be VALID under v2 strictness --
    the round-2 fresh-eyes gap: a backfilled radio got 1 option and failed
    FormSchema.model_validate ('radio requires at least 2 options'), and combo/
    list -> select would likewise need options a bare widget can't supply. Pin
    that a mixed dump (checkbox/radio/text/combo/list) yields a valid v2 schema."""
    import warnings
    from backend.models.form_models import FormSchema
    dump = _write_logical_dump(tmp_path, {
        "cb[0]": "checkbox", "rad[0]": "radio", "txt[0]": "text",
        "combo[0]": "combo", "list[0]": "list"})
    schema = {
        "schema_version": "2", "source": "pdf",
        "form_metadata": {"title": "T", "version": "1"},
        "sections": [{"id": "s", "label": "S", "order": 1,
                      "page_numbers": [1], "fields": []}],
        "fields": [],
    }
    assert ef._backfill_unclaimed_widgets(schema, dump) == 5
    # No options-bearing type was minted (all valid with zero options).
    assert {f["type"] for f in schema["fields"]} <= {"checkbox", "text"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        FormSchema.model_validate(schema)  # raises if any field is v2-invalid


def test_backfill_bucket_accumulates_pages_across_orphans(tmp_path):
    """Two orphans on different pages, no sections: one recovered_fields bucket
    whose page_numbers covers BOTH pages (round-2 nit fix)."""
    dump = {"fields": [
        {"name": "a[0]", "logical_type": "text",
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]},
        {"name": "b[0]", "logical_type": "text",
         "widgets": [{"rect": {"page": 2, "x": 1, "y": 2, "width": 8, "height": 8}}]},
    ]}
    p = tmp_path / "d.json"; p.write_text(json.dumps(dump), encoding="utf-8")
    schema = {"fields": []}
    assert ef._backfill_unclaimed_widgets(schema, str(p)) == 2
    buckets = [s for s in schema["sections"] if s["id"] == "recovered_fields"]
    assert len(buckets) == 1
    assert sorted(buckets[0]["page_numbers"]) == [1, 3]  # pages 0+1 -> 1-based 1,3


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
