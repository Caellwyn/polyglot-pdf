"""Runtime consumers learn the schema-v2 group vocabulary (bd h76m.17).

Covers the bead's three exit criteria:
1. A v2 checkbox_group field round-trips a REAL PDF fill via /fill-pdf
   (per-option widgets set; the pre-fix behavior printed BLANK because the
   type fell through to the scalar path, which needs the field-level
   pdf_field_name that v2 forbids on groups).
2. A v2 shared-field radio (field-level pdf_field_name + per-option
   pdf_on_value) fills the correct kid widget's state.
3. field_validator rejects an AI update whose value is not in the group's
   option slugs -- for BOTH value shapes (List[str] and the voice-path
   comma string).

The checkbox_group tests drive the real /fill-pdf route against the on-disk
i-90 kit with the race group RE-TYPED to the v2 shape (same harness as
test_pdf_fill_checkbox_group_comma.py). No shipped PDF carries a true
shared-name radio group, so the radio test builds a synthetic PDF (two kids
sharing one field name, distinguished by /AP on-states) and stubs the kit
store.

ASCII only.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

import backend.routes.pdf_fill_routes as pdf_fill_routes
from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf
from backend.utils.field_validator import validate_field_value

_KIT_ROOT = Path(__file__).resolve().parents[2] / "form-kits" / "i-90"

_RACE_FIELD_ID = "race"
# Option VALUES (schema-v2 slugs, bd polyglot-pdf-c5r8) for White and Black --
# what a fill request sends; each resolves to its own widget via
# option.pdf_field_name. The widget LEAVES are unchanged by the migration.
_RACE_SELECTED = ["white", "black_or_african_american"]
_RACE_SELECTED_LEAVES = ["P3_checkbox7_White[0]", "P3_checkbox7_Black[0]"]
_RACE_ALL_LEAVES = [
    "P3_checkbox7_White[0]", "P3_checkbox7_Asian[0]", "P3_checkbox7_Black[0]",
    "P3_checkbox7_Indian[0]", "P3_checkbox7_Hawaiian[0]",
]

_i90_present = pytest.mark.skipif(
    not (_KIT_ROOT / "form.pdf").exists(), reason="i-90 kit not present"
)


def _v2_group_schema() -> dict:
    """The i-90 gold schema with the race group re-typed to schema v2:
    type=checkbox_group and NO field-level pdf_field_name (per-box identity
    lives on options[].pdf_field_name)."""
    schema = json.loads((_KIT_ROOT / "schema.json").read_text(encoding="utf-8"))
    for field in schema["fields"]:
        if field["id"] == _RACE_FIELD_ID:
            field["type"] = "checkbox_group"
            field.pop("pdf_field_name", None)
            break
    else:
        raise AssertionError("race field not found in i-90 schema")
    return schema


def _as_states_by_leaf(pdf_bytes: bytes, leaves: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for pno in range(doc.page_count):
            for w in doc[pno].widgets() or []:
                leaf = (w.field_name or "").split(".")[-1]
                if leaf in leaves:
                    as_key = doc.xref_get_key(w.xref, "AS")
                    out[leaf] = (
                        as_key[1]
                        if isinstance(as_key, (list, tuple)) and len(as_key) > 1
                        else None
                    )
    finally:
        doc.close()
    return out


def _fill(schema: dict, field_values: dict) -> bytes:
    req = PDFFillRequest(
        kit_id="i-90",
        pdf_filename="form.pdf",
        field_values=field_values,
        form_schema=schema,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200
    return resp.body


# ---------------------------------------------------------------------------
# Exit criterion 1: checkbox_group round-trips a real PDF fill
# ---------------------------------------------------------------------------

@_i90_present
def test_checkbox_group_type_fills_per_option_widgets():
    """The blank-print regression: a v2 checkbox_group must fill its selected
    options' widgets exactly (pre-fix it fell to the scalar path and nothing
    was filled)."""
    pdf = _fill(_v2_group_schema(), {_RACE_FIELD_ID: _RACE_SELECTED})

    states = _as_states_by_leaf(pdf, _RACE_ALL_LEAVES)
    assert set(states) == set(_RACE_ALL_LEAVES)
    for leaf in _RACE_SELECTED_LEAVES:
        assert states[leaf] not in ("/Off", "Off", None), (
            f"{leaf} did not fill -- checkbox_group fell out of the group "
            "branch (bd h76m.17 blank-print regression)"
        )
    for leaf in set(_RACE_ALL_LEAVES) - set(_RACE_SELECTED_LEAVES):
        assert states[leaf] in ("/Off", "Off"), f"{leaf} should not be selected"


@_i90_present
def test_checkbox_group_voice_comma_string_round_trips():
    """The voice-path comma string canonicalizes for checkbox_group too."""
    pdf = _fill(_v2_group_schema(), {_RACE_FIELD_ID: ", ".join(_RACE_SELECTED)})
    states = _as_states_by_leaf(pdf, _RACE_ALL_LEAVES)
    for leaf in _RACE_SELECTED_LEAVES:
        assert states[leaf] not in ("/Off", "Off", None)


# ---------------------------------------------------------------------------
# Exit criterion 2: shared-field radio (pdf_field_name + pdf_on_value)
# ---------------------------------------------------------------------------

def _synthetic_radio_pdf() -> bytes:
    """A one-page PDF with a true-AcroForm-style radio group: two kid widgets
    sharing the field name grp[0], distinguished only by their /AP on-states
    ('1' and '2')."""
    doc = fitz.open()
    page = doc.new_page()
    # Create the kids as CHECKBOX widgets under DISTINCT names (PyMuPDF cannot
    # author standalone radio widgets -- its checker demands a Parent/Kids
    # tree), then rename both to ONE shared field name and give each its own
    # /AP on-state via raw xref surgery. That reproduces exactly what a
    # true-AcroForm radio group presents to page.widgets(): same-name button
    # widgets distinguished only by on-state. The fill path treats button
    # widgets uniformly (field_type 2 or CheckBox/RadioButton), so checkbox-
    # typed kids exercise the identical code.
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
    data = doc.tobytes()
    doc.close()
    return data


_SHARED_RADIO_SCHEMA = {
    "fields": [
        {
            "id": "marital",
            "type": "radio",
            "pdf_field_name": "grp[0]",
            "options": [
                {"value": "single", "label": "Single", "pdf_on_value": "1"},
                {"value": "married", "label": "Married", "pdf_on_value": "2"},
            ],
        }
    ]
}


class _StubStore:
    def __init__(self, pdf_bytes: bytes):
        self._pdf = pdf_bytes

    async def load_pdf_bytes(self, kit_id: str, filename: str) -> bytes:
        return self._pdf


def test_shared_field_radio_fills_matching_kid_state(monkeypatch):
    monkeypatch.setattr(
        pdf_fill_routes, "get_form_kit_store", lambda: _StubStore(_synthetic_radio_pdf())
    )
    req = PDFFillRequest(
        kit_id="synthetic",
        pdf_filename="synthetic.pdf",
        field_values={"marital": "married"},
        form_schema=_SHARED_RADIO_SCHEMA,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200

    doc = fitz.open(stream=resp.body, filetype="pdf")
    try:
        # Keep the Page object alive alongside its widgets: PyMuPDF widget
        # wrappers hold a WEAK reference to their page, so `doc[0].widgets()`
        # with a transient page dies nondeterministically under GC.
        page = doc[0]
        widgets = list(page.widgets() or [])
        assert len(widgets) == 2
        # The route is /AS-driven by design: it sets the appearance state and
        # lets the viewer generate appearances (fill_widget skips update();
        # every sibling fill test asserts /AS the same way). The kid whose
        # appearance table carries the selected pdf_on_value must show that
        # state; the OTHER kid must stay Off.
        as_by_states: dict[str, str] = {}
        for w in widgets:
            states = (w.button_states() or {}).get("normal") or []
            as_key = doc.xref_get_key(w.xref, "AS")
            as_val = as_key[1] if isinstance(as_key, (list, tuple)) and len(as_key) > 1 else None
            for state in states:
                if state != "Off":
                    as_by_states[state] = as_val
        assert as_by_states.get("2") == "/2", (
            f"matching kid /AS not set to the pdf_on_value state: {as_by_states}"
        )
        assert as_by_states.get("1") in ("/Off", "Off", None), (
            f"sibling kid should stay Off: {as_by_states}"
        )
    finally:
        doc.close()


def test_shared_field_radio_unknown_value_skips_cleanly(monkeypatch):
    monkeypatch.setattr(
        pdf_fill_routes, "get_form_kit_store", lambda: _StubStore(_synthetic_radio_pdf())
    )
    req = PDFFillRequest(
        kit_id="synthetic",
        pdf_filename="synthetic.pdf",
        field_values={"marital": "divorced"},  # not an option
        form_schema=_SHARED_RADIO_SCHEMA,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200  # skip-and-report, never crash


# ---------------------------------------------------------------------------
# Exit criterion 3: field_validator option membership for checkbox_group
# ---------------------------------------------------------------------------

_GROUP_FIELD = {
    "id": "grp",
    "name": "Reason",
    "type": "checkbox_group",
    "options": [
        {"value": "dependent_spouse", "label": "Dependent spouse"},
        {"value": "other", "label": "Other"},
    ],
}


def test_validator_accepts_in_set_list():
    assert validate_field_value(_GROUP_FIELD, ["other", "dependent_spouse"]) == []


def test_validator_rejects_out_of_set_list():
    errors = validate_field_value(_GROUP_FIELD, ["other", "ghost_slug"])
    assert errors, "out-of-set list member must be rejected"
    assert "ghost_slug" in errors[0].message


def test_validator_accepts_in_set_comma_string():
    assert validate_field_value(_GROUP_FIELD, "dependent_spouse, other") == []


def test_validator_rejects_out_of_set_comma_string():
    errors = validate_field_value(_GROUP_FIELD, "other, ghost_slug")
    assert errors, "out-of-set comma-string member must be rejected"
    assert "ghost_slug" in errors[0].message


def test_validator_standalone_checkbox_unchanged():
    standalone = {"id": "cb", "name": "CB", "type": "checkbox"}
    assert validate_field_value(standalone, True) == []
    assert validate_field_value(standalone, "not-a-bool") != []


# ---------------------------------------------------------------------------
# Fresh-eyes round 1 hardening
# ---------------------------------------------------------------------------

def _synthetic_radio_pdf_broken_sibling() -> bytes:
    """Kid 1 has a MALFORMED appearance table (no /N states); kid 2's real
    on-state is literally 'Yes'. A 'Yes'-defaulting state reader would match
    the broken kid first -- the silent wrong-box hazard."""
    doc = fitz.open()
    page = doc.new_page()
    for idx, rect in enumerate((fitz.Rect(50, 50, 70, 70), fitz.Rect(50, 90, 70, 110))):
        w = fitz.Widget()
        w.field_name = f"tmp_{idx}[0]"
        w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        w.rect = rect
        page.add_widget(w)
    xrefs = [w.xref for w in doc[0].widgets() or []]
    doc.xref_set_key(xrefs[0], "T", "(grp[0])")
    doc.xref_set_key(xrefs[0], "AP", "<< >>")  # malformed: no /N dict
    doc.xref_set_key(xrefs[1], "T", "(grp[0])")
    doc.xref_set_key(xrefs[1], "AP", "<< /N << /Yes null /Off null >> >>")
    data = doc.tobytes()
    doc.close()
    return data


def test_shared_radio_skips_broken_sibling_for_yes_state(monkeypatch):
    monkeypatch.setattr(
        pdf_fill_routes,
        "get_form_kit_store",
        lambda: _StubStore(_synthetic_radio_pdf_broken_sibling()),
    )
    schema = {
        "fields": [{
            "id": "marital", "type": "radio", "pdf_field_name": "grp[0]",
            "options": [{"value": "yes", "label": "Yes", "pdf_on_value": "Yes"},
                        {"value": "no", "label": "No", "pdf_on_value": "2"}],
        }]
    }
    req = PDFFillRequest(
        kit_id="synthetic", pdf_filename="s.pdf",
        field_values={"marital": "yes"}, form_schema=schema,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200

    doc = fitz.open(stream=resp.body, filetype="pdf")
    try:
        page = doc[0]
        for w in page.widgets() or []:
            states = (w.button_states() or {}).get("normal") or []
            as_key = doc.xref_get_key(w.xref, "AS")
            as_val = as_key[1] if isinstance(as_key, (list, tuple)) and len(as_key) > 1 else None
            if "Yes" in states:
                assert as_val == "/Yes", f"intended kid not selected: {as_val}"
            else:
                assert as_val != "/Yes", "the BROKEN sibling was selected (Yes-default regression)"
    finally:
        doc.close()


def test_shared_radio_refuses_pdf_name_unsafe_on_state(monkeypatch):
    monkeypatch.setattr(
        pdf_fill_routes, "get_form_kit_store", lambda: _StubStore(_synthetic_radio_pdf())
    )
    schema = {
        "fields": [{
            "id": "marital", "type": "radio", "pdf_field_name": "grp[0]",
            "options": [{"value": "bad", "label": "Bad", "pdf_on_value": "has space/slash"}],
        }]
    }
    req = PDFFillRequest(
        kit_id="synthetic", pdf_filename="s.pdf",
        field_values={"marital": "bad"}, form_schema=schema,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200  # refused + skipped, never a corrupt write
    # And PROVE nothing was written: both kids stay Off (fresh-eyes round 2 --
    # status-only would not catch a bypassed guard writing the corrupt token).
    doc = fitz.open(stream=resp.body, filetype="pdf")
    try:
        page = doc[0]
        for w in page.widgets() or []:
            as_key = doc.xref_get_key(w.xref, "AS")
            as_val = as_key[1] if isinstance(as_key, (list, tuple)) and len(as_key) > 1 else None
            assert as_val in ("/Off", "Off", None), f"unsafe on-state was written: {as_val}"
    finally:
        doc.close()


@_i90_present
def test_checkbox_group_bool_value_skips_cleanly():
    """Stale client data sending a bare bool to a v2 group must skip with the
    no-pdf-mapping diagnostic (v2 forbids the field-level pdf_field_name the
    bool path needs), never crash or silently succeed."""
    pdf = _fill(_v2_group_schema(), {_RACE_FIELD_ID: True})
    states = _as_states_by_leaf(pdf, _RACE_ALL_LEAVES)
    for leaf in _RACE_ALL_LEAVES:
        assert states[leaf] in ("/Off", "Off", None), f"{leaf} should stay unfilled"
