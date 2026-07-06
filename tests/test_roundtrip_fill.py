"""Tests for scripts/bakeoff/roundtrip_fill.py's v2 group-shape parity (bd
polyglot-pdf-bvmu).

roundtrip_fill.py is a SEPARATE, self-contained filler used only by the
offline eval/bakeoff harness -- NOT backend/routes/pdf_fill_routes.py (the
production filler). After bd h76m.17 taught production the schema-v2 group
vocabulary (checkbox_group + shared-field radio), this harness diverged and
mis-scored v2 kits: a checkbox_group field fell to the text-like branch
(using the field-level pdf_field_name, which v2 FORBIDS on a group) and a
shared-field radio option (pdf_on_value only, no own pdf_field_name) yielded
no target at all.

These tests exercise the harness's OWN functions directly (_target_widgets_
for_field, run) against two v2 fixtures:
  1. A v2-typed i-90 race group (SYNTHETIC re-type -- the on-disk i-90 gold
     is still v1 checkbox/options; bd h76m.15 hasn't migrated it yet, and
     this bead is about the FILLER logic, not the gold), mirroring the
     re-type helper in backend/tests/test_pdf_fill_v2_group_types.py.
  2. A synthetic shared-field radio PDF (two kid widgets sharing one field
     name, distinguished by /AP on-states), built the same way as that same
     production test file's _synthetic_radio_pdf helper -- PyMuPDF cannot
     author true radio widgets directly, so checkbox-typed kids are renamed
     onto one shared field name and given distinct on-states via xref
     surgery, which presents to page.widgets() exactly like a true-AcroForm
     radio group.

ASCII only.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import fitz  # PyMuPDF
import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))

import roundtrip_fill as rf  # noqa: E402

_I90_ROOT = _REPO / "form-kits" / "i-90"
_RACE_FIELD_ID = "p3_race"

_i90_present = pytest.mark.skipif(
    not (_I90_ROOT / "form.pdf").exists(), reason="i-90 kit not present"
)


# --------------------------------------------------------------------------- #
# Fixture 1: v2-typed checkbox_group (synthetic re-type of the i-90 race group)
# --------------------------------------------------------------------------- #

def _v2_race_field() -> dict:
    """The i-90 gold's race field, re-typed to v2: type=checkbox_group and
    NO field-level pdf_field_name (per-box identity lives on
    options[].pdf_field_name only) -- same re-type bd h76m.17's production
    test applies, kept local here so this test does not depend on the gold
    migration (bd h76m.15, not yet done)."""
    schema = json.loads((_I90_ROOT / "schema.json").read_text(encoding="utf-8"))
    for field in schema["fields"]:
        if field["id"] == _RACE_FIELD_ID:
            field = dict(field)
            field["type"] = "checkbox_group"
            field.pop("pdf_field_name", None)
            return field
    raise AssertionError("race field not found in i-90 schema")


@_i90_present
def test_target_widgets_checkbox_group_returns_per_option_widgets():
    """The v2 checkbox_group regression: pre-fix, type=='checkbox_group' fell
    to the text-like else-branch and used the (forbidden, absent) field-level
    pdf_field_name -- zero targets. Fixed, it must return one 'choice' target
    per option, using each option's OWN pdf_field_name."""
    field = _v2_race_field()
    opts = field.get("options") or []
    assert len(opts) >= 2, "race group fixture needs multiple options"

    targets = rf._target_widgets_for_field(field)

    assert targets, "checkbox_group must produce target widgets (bd bvmu regression)"
    expected_names = {o["pdf_field_name"] for o in opts if o.get("pdf_field_name")}
    got_names = {name for name, kind in targets}
    assert got_names == expected_names
    assert all(kind == "choice" for _, kind in targets)


@_i90_present
def test_roundtrip_run_fills_v2_checkbox_group_options():
    """Full round-trip: run() against the real i-90 PDF with the race group
    re-typed to v2 must mark every option's widget as filled (choice_
    fill_success == 100%), not silently score as unmapped/unfilled."""
    field = _v2_race_field()
    schema = json.loads((_I90_ROOT / "schema.json").read_text(encoding="utf-8"))
    for i, f in enumerate(schema["fields"]):
        if f["id"] == _RACE_FIELD_ID:
            schema["fields"][i] = field
            break

    tmp_schema = _REPO / "tests" / "_tmp_v2_race_schema.json"
    tmp_schema.write_text(json.dumps(schema), encoding="utf-8")
    try:
        result = rf.run(str(tmp_schema), str(_I90_ROOT / "form.pdf"))
    finally:
        tmp_schema.unlink(missing_ok=True)

    choice = result["choice_fill_success"]
    race_failures = [f for f in result["failures"] if f["field_id"] == _RACE_FIELD_ID]
    assert not race_failures, f"race group had unfilled widgets: {race_failures}"
    assert choice["attempted"] > 0
    assert choice["filled"] == choice["attempted"], (
        "some choice widgets (incl. the v2 race group) did not verify filled"
    )


# --------------------------------------------------------------------------- #
# Fixture 2: synthetic shared-field radio (field-level pdf_field_name +
# option.pdf_on_value, no option-level pdf_field_name)
# --------------------------------------------------------------------------- #

def _synthetic_shared_radio_pdf_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """A one-page PDF with a true-AcroForm-style radio group: two kid widgets
    sharing the field name grp[0], distinguished only by their /AP on-states
    ('1' and '2'). Built identically to backend/tests/
    test_pdf_fill_v2_group_types.py's _synthetic_radio_pdf (PyMuPDF cannot
    author standalone radio widgets directly; checkbox-typed kids renamed
    onto one shared field name + given distinct on-states via xref surgery
    reproduce what page.widgets() sees for a true shared-name radio group)."""
    doc = fitz.open()
    page = doc.new_page()
    for idx, rect in enumerate((fitz.Rect(50, 50, 70, 70), fitz.Rect(50, 90, 70, 110))):
        w = fitz.Widget()
        w.field_name = f"tmp_{idx}[0]"
        w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        w.rect = rect
        page.add_widget(w)
    xrefs = [w.xref for w in doc[0].widgets() or []]
    assert len(xrefs) == 2, "synthetic radio kids not created"
    for xref, state in zip(xrefs, ("1", "2")):
        doc.xref_set_key(xref, "T", "(grp[0])")
        doc.xref_set_key(xref, "AP", f"<< /N << /{state} null /Off null >> >>")
    out = tmp_path / "synthetic_shared_radio.pdf"
    doc.save(str(out))
    doc.close()
    return out


_SHARED_RADIO_FIELD = {
    "id": "marital",
    "type": "radio",
    "pdf_field_name": "grp[0]",
    "options": [
        {"value": "single", "label": "Single", "pdf_on_value": "1"},
        {"value": "married", "label": "Married", "pdf_on_value": "2"},
    ],
}


def test_target_widgets_shared_radio_resolves_field_level_name_and_on_value():
    """The shared-field radio regression: pre-fix, an option with no own
    pdf_field_name (only pdf_on_value) yielded NO target at all. Fixed, it
    must resolve using the field-level pdf_field_name + the selected
    option's pdf_on_value (synth_value picks options[0] == 'single' -> on
    state '1')."""
    targets = rf._target_widgets_for_field(_SHARED_RADIO_FIELD)
    assert len(targets) == 1
    marker, kind = targets[0]
    assert kind == "choice_shared"
    shared_field, on_state = marker.split("\x00", 1)
    assert shared_field == "grp[0]"
    assert on_state == "1"  # options[0]'s pdf_on_value ('single')


def test_roundtrip_run_fills_shared_radio_kid_widget(tmp_path):
    """Full round-trip against the synthetic shared-radio PDF: the matching
    kid (on-state '1', for the 'single' option synth_value selects) must
    verify filled, and the harness must not crash or silently skip."""
    pdf_path = _synthetic_shared_radio_pdf_path(tmp_path)
    schema = {"fields": [_SHARED_RADIO_FIELD]}
    schema_path = tmp_path / "shared_radio_schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    result = rf.run(str(schema_path), str(pdf_path), verbose=True)

    assert not result["failures"], f"shared-field radio did not fill: {result['failures']}"
    choice = result["choice_fill_success"]
    assert choice["attempted"] == 1
    assert choice["filled"] == 1, "shared-field radio kid widget was not marked filled"

    # A radio holds ONE value: only the SELECTED option ('single', on-state
    # '1') produces an attempt -- the 'married' sibling ('2') must never be
    # targeted at all (matches production: no Off-pass for deselected kids
    # of a shared-field radio, per pdf_fill_routes.py's comment at line 320).
    attempts = result["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["kind"] == "choice_shared"
    assert attempts[0]["widget"] == "grp[0][on=1]"
    assert attempts[0]["found"] is True


def test_target_widgets_shared_radio_missing_field_level_name_yields_nothing():
    """If neither the option nor the field carries a usable pdf_field_name,
    the harness must yield NO target (never guess/crash) -- mirrors
    production's skip-cleanly behavior for an unresolvable shared radio."""
    field = {
        "id": "marital",
        "type": "radio",
        # no pdf_field_name at the field level
        "options": [{"value": "single", "label": "Single", "pdf_on_value": "1"}],
    }
    assert rf._target_widgets_for_field(field) == []


def test_shared_radio_unsafe_on_state_scores_attempted_but_unfilled(tmp_path):
    """Production (pdf_fill_routes.py _PDF_NAME_UNSAFE, bd h76m.17) REFUSES to
    write a shared-radio on-state carrying PDF-Name-unsafe chars, counting the
    field as skipped/UNFILLED (it stays in the denominator). The harness must
    mirror that SCORING: the unsafe on-state is an ATTEMPTED-but-unfilled write,
    NOT a vanished field. Dropping it from the denominator would inflate the
    fill rate and hide exactly the fill defect the harness exists to surface
    (bd polyglot-pdf-bvmu, fresh-eyes r2). synth_value picks options[0], so its
    unsafe on-value 'has space/slash' is the one under test.

    We drive run() against the same synthetic shared-radio PDF (its kids carry
    on-states '1'/'2', so the unsafe '/'-bearing state resolves to no writable
    kid anyway -- but the POINT is the field must still be counted as an unfilled
    attempt, matching production's skipped accounting)."""
    pdf_path = _synthetic_shared_radio_pdf_path(tmp_path)
    field = {
        "id": "marital",
        "type": "radio",
        "pdf_field_name": "grp[0]",
        "options": [
            {"value": "single", "label": "Single", "pdf_on_value": "has space/slash"},
            {"value": "married", "label": "Married", "pdf_on_value": "2"},
        ],
    }
    schema_path = tmp_path / "unsafe_shared_radio_schema.json"
    schema_path.write_text(json.dumps({"fields": [field]}), encoding="utf-8")

    result = rf.run(str(schema_path), str(pdf_path), verbose=True)

    choice = result["choice_fill_success"]
    # In the denominator (attempted), NOT vanished; and NOT counted filled.
    assert choice["attempted"] == 1
    assert choice["filled"] == 0
    assert choice["pct"] == 0.0
    # Reported as a refusal, matching production's skip -- not silently dropped.
    assert result["failures"]
    assert result["failures"][0]["reason"] == "refused_unsafe_on_state"


def test_target_widgets_shared_radio_unsafe_on_state_still_emits_target():
    """The unsafe on-state must NOT be filtered out at target-selection time
    (that would make the field vanish from scoring). It is emitted here and
    handled as an unfilled attempt in run() -- see the run()-level test above."""
    field = {
        "id": "marital",
        "type": "radio",
        "pdf_field_name": "grp[0]",
        "options": [
            {"value": "single", "label": "Single", "pdf_on_value": "has space/slash"},
        ],
    }
    targets = rf._target_widgets_for_field(field)
    assert len(targets) == 1
    assert targets[0][1] == "choice_shared"


# --------------------------------------------------------------------------- #
# score_value_convention must also recognize checkbox_group
# --------------------------------------------------------------------------- #

def test_value_convention_checks_checkbox_group_options():
    schema = {
        "fields": [
            {
                "id": "grp",
                "type": "checkbox_group",
                "options": [
                    {"value": "P3_checkbox7_White[0]", "pdf_field_name": "P3_checkbox7_White[0]"},
                    {"value": "wrong", "pdf_field_name": "P3_checkbox7_Black[0]"},
                ],
            }
        ]
    }
    result = rf.score_value_convention(schema)
    assert result["total"] == 2
    assert result["conforming"] == 1
    assert len(result["violations"]) == 1
    assert result["violations"][0]["field_id"] == "grp"
