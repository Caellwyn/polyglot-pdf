"""Tests for extract_form._complete_grouped_families (bd polyglot-pdf-qmxb).

The extractor's LLM pass stochastically drops some option-widgets of a
"select one/all of N checkboxes" question (bd 0nxh: i-90 modeled 1 of 5
P2_checkbox3 widgets). group_candidates mines the dump for the FAMILY; when
exactly one field consolidated SOME-but-not-all of it into options[], the
completer appends the missing members as options of THAT SAME field WITHOUT
changing its type (the widget-type retype that ignored single-vs-multi was
built then removed -- bd w0eq). Every ambiguous case is a SKIP; the downstream
_backfill_unclaimed_widgets still guarantees no widget vanishes.

Tier 1 (synthetic dump, no PDF/LLM) pins the completion + the 3 skip negatives.
Tier 2 uses the real i-90 dump (no LLM) to confirm the real families complete.

Imports extract_form by file path (repo precedent: test_extract_form_backfill.py).
ASCII only.
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


def _write_family_dump(tmp_path, names):
    """A minimal dump of same-leaf-multi-index checkbox widgets (a Family-A group):
    shared leaf base, distinct [n], each a fillable checkbox with a rect."""
    dump = {"fields": [
        {"name": n, "logical_type": "checkbox",
         "widgets": [{"type": "checkbox", "on_value": "1",
                      "rect": {"page": 0, "x": 10, "y": 20 + 10 * i,
                               "width": 8, "height": 8}}]}
        for i, n in enumerate(names)
    ]}
    p = tmp_path / "dump.json"
    p.write_text(json.dumps(dump), encoding="utf-8")
    return str(p)


_FAM = [f"form1[0].#s[0].C[{i}]" for i in range(5)]  # a 5-widget family


def _opt(name, value="v"):
    return {"value": value, "label": "x", "pdf_field_name": name}


# --- Tier 1: completion --------------------------------------------------- #

def test_completes_a_partially_grouped_family_in_place():
    """The 0nxh shape: the LLM modeled the field as a radio but with only 1 of the
    family's 5 option-widgets. The other 4 are appended as options of THAT field."""
    import tempfile, os
    tmp = pathlib.Path(tempfile.mkdtemp())
    dp = _write_family_dump(tmp, _FAM)
    schema = {"fields": [{"id": "reason", "type": "radio",
                          "options": [_opt(_FAM[0], "first")]}]}
    res = ef._complete_grouped_families(schema, dp)
    os.remove(dp)
    f = schema["fields"][0]
    assert res == {"fields_completed": 1, "options_added": 4}
    assert f["type"] == "radio"  # NEVER retyped
    assert [o["pdf_field_name"] for o in f["options"]] == _FAM  # all 5, in order
    # every appended option carries a distinct value (no collision)
    vals = [o["value"] for o in f["options"]]
    assert len(vals) == len(set(vals))


def test_completion_preserves_a_checkbox_group_type():
    """A multi-select group the LLM typed checkbox_group is completed the same way
    -- the type is preserved (the completer never decides single-vs-multi)."""
    import tempfile, os
    tmp = pathlib.Path(tempfile.mkdtemp())
    dp = _write_family_dump(tmp, _FAM)
    schema = {"fields": [{"id": "race", "type": "checkbox_group",
                          "options": [_opt(_FAM[0]), _opt(_FAM[1], "v2")]}]}
    res = ef._complete_grouped_families(schema, dp)
    os.remove(dp)
    assert res == {"fields_completed": 1, "options_added": 3}
    assert schema["fields"][0]["type"] == "checkbox_group"


# --- Tier 1: the 3 skip negatives ----------------------------------------- #

def test_skips_when_family_is_split_across_two_fields():
    """owners > 1: two fields each claim part of the family. Deterministic merge is
    out of scope -- SKIP (backfill still covers any truly-unclaimed member)."""
    import tempfile, os
    tmp = pathlib.Path(tempfile.mkdtemp())
    dp = _write_family_dump(tmp, _FAM)
    schema = {"fields": [
        {"id": "a", "type": "radio", "options": [_opt(_FAM[0], "a")]},
        {"id": "b", "type": "radio", "options": [_opt(_FAM[1], "b")]}]}
    res = ef._complete_grouped_families(schema, dp)
    os.remove(dp)
    assert res == {"fields_completed": 0, "options_added": 0}
    assert len(schema["fields"][0]["options"]) == 1  # untouched


def test_skips_when_no_field_claims_the_family():
    """0 claimed: a false-positive family no field adopted. SKIP -- nothing to
    complete; _backfill_unclaimed_widgets recovers the widgets as loose fields."""
    import tempfile, os
    tmp = pathlib.Path(tempfile.mkdtemp())
    dp = _write_family_dump(tmp, _FAM)
    schema = {"fields": [{"id": "unrelated", "type": "text",
                          "pdf_field_name": "form1[0].#s[0].Other[0]"}]}
    res = ef._complete_grouped_families(schema, dp)
    os.remove(dp)
    assert res == {"fields_completed": 0, "options_added": 0}


def test_skips_when_family_already_complete():
    """all claimed: the LLM already modeled every member. No-op."""
    import tempfile, os
    tmp = pathlib.Path(tempfile.mkdtemp())
    dp = _write_family_dump(tmp, _FAM)
    schema = {"fields": [{"id": "a", "type": "radio",
                          "options": [_opt(n, f"v{i}") for i, n in enumerate(_FAM)]}]}
    res = ef._complete_grouped_families(schema, dp)
    os.remove(dp)
    assert res == {"fields_completed": 0, "options_added": 0}
    assert len(schema["fields"][0]["options"]) == 5


def test_does_not_reappend_a_member_claimed_by_another_fields_field_level_pfn():
    """bd qmxb Opus review: a family member already claimed by a SEPARATE
    standalone field's field-level pdf_field_name must NOT be re-appended as an
    option of the owner -- that would double-claim the widget
    (dump-widget-multiclaim). The owner completes only the truly-unclaimed
    members; the standalone keeps its widget."""
    import tempfile, os
    tmp = pathlib.Path(tempfile.mkdtemp())
    dp = _write_family_dump(tmp, _FAM)
    schema = {"fields": [
        {"id": "owner", "type": "radio", "options": [_opt(_FAM[0], "first")]},
        {"id": "standalone", "type": "checkbox", "pdf_field_name": _FAM[3]}]}
    res = ef._complete_grouped_families(schema, dp)
    os.remove(dp)
    owner_names = [o["pdf_field_name"] for o in schema["fields"][0]["options"]]
    # owner gets 0,1,2,4 (NOT 3 -- the standalone owns it); 3 not double-claimed
    assert res == {"fields_completed": 1, "options_added": 3}
    assert _FAM[3] not in owner_names
    assert set(owner_names) == {_FAM[0], _FAM[1], _FAM[2], _FAM[4]}


def test_no_dump_is_a_safe_noop(tmp_path):
    res = ef._complete_grouped_families({"fields": []}, str(tmp_path / "absent.json"))
    assert res == {"fields_completed": 0, "options_added": 0}


# --- bd polyglot-pdf-pixq: a mixed family (one name repeated via multiple ---
# widget KIDS) must not mint a duplicate option ------------------------------


def _write_mixed_duplicate_family_dump(tmp_path):
    """A Family-B numbered-leaf-run dump reproducing the bead's own repro: ONE
    AcroForm field name (c1_1) with TWO widget kids sharing the same
    on_value at different y-positions (group_candidates._button_widgets
    flattens one entry PER KID, so this field's name enters the flattened
    widget list twice), alongside two ordinary single-kid siblings c1_2 and
    c1_3 -- forming a consecutive numbered run c1_1, c1_1, c1_2, c1_3 that
    passes the >= 2 members guard even discounting the duplicate."""
    dump = {"fields": [
        {"name": "form1[0].P1[0].c1_1[0]", "logical_type": "checkbox", "widgets": [
            {"type": "checkbox", "on_value": "1",
             "rect": {"page": 0, "x": 10, "y": 20, "width": 8, "height": 8}},
            {"type": "checkbox", "on_value": "1",
             "rect": {"page": 0, "x": 10, "y": 40, "width": 8, "height": 8}},
        ]},
        {"name": "form1[0].P1[0].c1_2[0]", "logical_type": "checkbox", "widgets": [
            {"type": "checkbox", "on_value": "1",
             "rect": {"page": 0, "x": 10, "y": 60, "width": 8, "height": 8}},
        ]},
        {"name": "form1[0].P1[0].c1_3[0]", "logical_type": "checkbox", "widgets": [
            {"type": "checkbox", "on_value": "1",
             "rect": {"page": 0, "x": 10, "y": 80, "width": 8, "height": 8}},
        ]},
    ]}
    p = tmp_path / "dump.json"
    p.write_text(json.dumps(dump), encoding="utf-8")
    return str(p)


def test_a_repeated_widget_name_never_yields_two_options_for_one_pdf_field_name():
    """bd polyglot-pdf-pixq, exit criterion 1: a family whose widgets list
    repeats one name (because that field has 2 kids) alongside >=2 distinct
    names must produce a completed field whose option pdf_field_names are
    UNIQUE -- no duplicate option carrying the same name (which would paint
    two options on top of the same rect)."""
    import tempfile, os

    from group_candidates import find_group_candidates  # noqa: E402

    tmp = pathlib.Path(tempfile.mkdtemp())
    dp = _write_mixed_duplicate_family_dump(tmp)

    dump = json.loads(pathlib.Path(dp).read_text(encoding="utf-8"))
    families = find_group_candidates(dump)
    assert families, "fixture assumption changed: no family clustered at all"
    # Confirm the fixture actually reproduces the duplicate-in-widgets shape
    # the bead describes, so this test targets the real bug rather than a
    # family that never carries a repeat.
    fam = families[0]
    assert fam["widgets"].count("form1[0].P1[0].c1_1[0]") == 2, (
        "fixture assumption changed: c1_1 no longer appears twice in the "
        "clustered family's widgets list"
    )

    schema = {"fields": [{
        "id": "reason", "type": "checkbox_group",
        "options": [_opt("form1[0].P1[0].c1_2[0]", "first")],
    }]}
    res = ef._complete_grouped_families(schema, dp)
    os.remove(dp)

    opt_names = [o["pdf_field_name"] for o in schema["fields"][0]["options"]]
    assert len(opt_names) == len(set(opt_names)), (
        f"duplicate pdf_field_name in completed options: {opt_names!r}"
    )
    assert res["options_added"] == len(set(opt_names)) - 1  # minus the pre-existing claim


# --- Tier 2: the real i-90 dump ------------------------------------------- #

_I90_PDF = _REPO / "form-kits" / "i-90" / "form.pdf"


@pytest.mark.skipif(not _I90_PDF.exists(), reason="i-90 PDF not present")
def test_real_i90_p2_checkbox3_family_completes():
    """End-to-end on the REAL i-90 dump (no LLM): simulate the 0nxh drop (1 of 5
    P2_checkbox3 modeled) and confirm the completer recovers all 5 as options of
    the same radio field -- the exact bug bd 0nxh fixed by hand."""
    import tempfile, os, importlib
    sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
    acroform_dump = importlib.import_module("acroform_dump")
    dump = acroform_dump.dump_pdf(str(_I90_PDF))
    fd, dp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(dp, "w", encoding="utf-8") as fh:
        json.dump(dump, fh)
    p0 = "form1[0].#subform[2].P2_checkbox3[0]"
    schema = {"fields": [{"id": "p2_checkbox3", "type": "radio",
                          "options": [_opt(p0, "never_received")]}]}
    res = ef._complete_grouped_families(schema, dp)
    os.remove(dp)
    assert res["fields_completed"] == 1
    assert res["options_added"] == 4
    leaves = sorted(o["pdf_field_name"].split(".")[-1]
                    for o in schema["fields"][0]["options"])
    assert leaves == [f"P2_checkbox3[{i}]" for i in range(5)]
    assert schema["fields"][0]["type"] == "radio"
