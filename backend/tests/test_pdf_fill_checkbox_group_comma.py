"""Regression test for voice-shaped checkbox-group values in /fill-pdf.

bd polyglot-pdf-h76m.2: the voice path historically stored a checkbox-GROUP
selection as ONE comma-separated string of option values (config.py tells
Gemini "Multiple checkboxes: comma-separated exact values"). The fill route
handled only bool (standalone) and list (group), so a comma string fell to the
unsupported-value branch and the group silently stayed empty on the printed
PDF. The route now canonicalizes a str value on an options-bearing checkbox
field into the list shape before filling.

The frontend splits the same string at the AI ingress now, but sessions
started before that fix (or stale sessionStorage) can still deliver the raw
string -- this backend split is the defensive layer for them.

Drives the REAL /fill-pdf route against the on-disk I-90 kit (same harness as
test_pdf_fill_readonly_unlock.py) and verifies widget /AS on-states -- the
round-trip the bead's exit criterion names.

ASCII only.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf

_KIT_ROOT = Path(__file__).resolve().parents[2] / "form-kits" / "i-90"

# The I-90 Race checkbox group: a real multi-select whose options each map to
# their own PDF widget (the group representation this epic is about).
_RACE_FIELD_ID = "p3_race"
_RACE_SELECTED = ["P3_checkbox7_White[0]", "P3_checkbox7_Black[0]"]
_RACE_ALL_LEAVES = [
    "P3_checkbox7_White[0]", "P3_checkbox7_Asian[0]", "P3_checkbox7_Black[0]",
    "P3_checkbox7_Indian[0]", "P3_checkbox7_Hawaiian[0]",
]

pytestmark = pytest.mark.skipif(
    not (_KIT_ROOT / "form.pdf").exists(), reason="i-90 kit not present"
)


def _load_gold_schema() -> dict:
    return json.loads((_KIT_ROOT / "schema.json").read_text(encoding="utf-8"))


def _as_states_by_leaf(pdf_bytes: bytes, leaves: list[str]) -> dict[str, str]:
    """Map each widget leaf -> its /AS appearance state in the saved PDF."""
    out: dict[str, str] = {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for pno in range(doc.page_count):
            for w in doc[pno].widgets() or []:
                leaf = (w.field_name or "").split(".")[-1]
                if leaf in leaves:
                    as_key = doc.xref_get_key(w.xref, "AS")
                    out[leaf] = as_key[1] if isinstance(as_key, (list, tuple)) and len(as_key) > 1 else None
    finally:
        doc.close()
    return out


def _fill_race(value) -> bytes:
    req = PDFFillRequest(
        kit_id="i-90",
        pdf_filename="form.pdf",
        field_values={_RACE_FIELD_ID: value},
        form_schema=_load_gold_schema(),
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200
    return resp.body


def test_comma_string_group_value_round_trips():
    """A voice-shaped 'a, b' comma string fills exactly the named widgets."""
    pdf = _fill_race(", ".join(_RACE_SELECTED))

    states = _as_states_by_leaf(pdf, _RACE_ALL_LEAVES)
    assert set(states) == set(_RACE_ALL_LEAVES), "not all race widgets resolved"
    for leaf in _RACE_SELECTED:
        assert states[leaf] not in ("/Off", "Off", None), (
            f"{leaf} did not fill -- the comma-string group value was not "
            "canonicalized (regression of bd polyglot-pdf-h76m.2)"
        )
    for leaf in set(_RACE_ALL_LEAVES) - set(_RACE_SELECTED):
        assert states[leaf] in ("/Off", "Off"), f"{leaf} should not be selected"


def test_single_no_comma_string_group_value_fills_one_widget():
    """A single selection arriving as a bare string fills exactly its widget."""
    selected = "P3_checkbox7_Asian[0]"
    pdf = _fill_race(selected)

    states = _as_states_by_leaf(pdf, _RACE_ALL_LEAVES)
    assert states[selected] not in ("/Off", "Off", None), f"{selected} did not fill"
    for leaf in set(_RACE_ALL_LEAVES) - {selected}:
        assert states[leaf] in ("/Off", "Off"), f"{leaf} should not be selected"


def test_list_group_value_still_fills():
    """The canonical list shape is unaffected by the defensive split."""
    pdf = _fill_race(list(_RACE_SELECTED))

    states = _as_states_by_leaf(pdf, _RACE_ALL_LEAVES)
    for leaf in _RACE_SELECTED:
        assert states[leaf] not in ("/Off", "Off", None), f"{leaf} did not fill"
    for leaf in set(_RACE_ALL_LEAVES) - set(_RACE_SELECTED):
        assert states[leaf] in ("/Off", "Off"), f"{leaf} should not be selected"


def test_boolean_intent_string_is_not_split_into_a_selection():
    """A literal "true" on an options-bearing checkbox is boolean intent, not a
    group selection: the split guard excludes it, so it falls through to the
    unsupported-value branch (accurate diagnostic) and fills nothing."""
    pdf = _fill_race("true")

    states = _as_states_by_leaf(pdf, _RACE_ALL_LEAVES)
    for leaf in _RACE_ALL_LEAVES:
        assert states[leaf] in ("/Off", "Off"), f"{leaf} should not be selected"
