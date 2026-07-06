"""Regression tests for two I-90 /fill-pdf choice-field bugs.

bd polyglot-pdf-7a9.16 (read-only unlock): the production filler read the
pdf_field_flag_change unlock descriptor from conditional_behavior, but the I-90
gold schema stores it under conditional_logic -- so read-only fields never
unlocked. apply_field_flag_changes now reads it from EITHER key. PyMuPDF writes
field_value even on a read-only widget, so the observable effect of the unlock is
the read-only FLAG being cleared in the output (a viewer then renders the field
editable instead of locked) -- that is what test_readonly_field_unlocks asserts.

bd polyglot-pdf-7a9.15 (p3_race): the Race checkbox group's option
pdf_field_names dropped the [0] widget index (P3_checkbox7_White vs the real
...White[0]) and used semantic option.values, so the filler's exact-then-endswith
find_widget never matched and Race silently did not fill. The gold was brought
onto the I-90 widget-leaf convention; test_p3_race_options_fill asserts the
selected race widgets get their /AS on-state.

Both tests drive the REAL /fill-pdf route against the on-disk I-90 kit.

ASCII only.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf

# A field that is read-only in form.pdf AND unlocks via conditional_logic.
_READONLY_FIELD_ID = "p1_line5a_familyname"
_READONLY_WIDGET_SUFFIX = "P1_Line5a_FamilyName[0]"
_FILL_VALUE = "RoundtripUnlockTest"

# Repo root is two levels up from backend/tests/; the kit lives at <repo>/form-kits
# (the same default backend/config.py resolves for FORM_KITS_LOCAL_ROOT).
_KIT_ROOT = Path(__file__).resolve().parents[2] / "form-kits" / "i-90"


def _load_gold_schema() -> dict:
    return json.loads((_KIT_ROOT / "schema.json").read_text(encoding="utf-8"))


def _widget_value(pdf_bytes: bytes, suffix: str):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for pno in range(doc.page_count):
            for w in doc[pno].widgets() or []:
                if w.field_name and w.field_name.endswith(suffix):
                    return w.field_value, bool(w.field_flags & 1)
    finally:
        doc.close()
    return None, None


@pytest.mark.skipif(not (_KIT_ROOT / "form.pdf").exists(),
                    reason="i-90 kit not present")
def test_readonly_field_unlocks_and_fills():
    schema = _load_gold_schema()

    # Precondition: the target field is genuinely read-only in the source PDF
    # (otherwise the test would pass without exercising the unlock).
    src = (_KIT_ROOT / "form.pdf").read_bytes()
    _, src_readonly = _widget_value(src, _READONLY_WIDGET_SUFFIX)
    assert src_readonly is True, "target field is not read-only in the source PDF"

    req = PDFFillRequest(
        kit_id="i-90",
        pdf_filename="form.pdf",
        field_values={_READONLY_FIELD_ID: _FILL_VALUE},
        form_schema=schema,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200

    filled_value, out_readonly = _widget_value(resp.body, _READONLY_WIDGET_SUFFIX)
    assert filled_value == _FILL_VALUE, "field did not receive its value"
    # The observable effect of the unlock: the read-only bit is cleared in the
    # output. apply_field_flag_changes only does this if it finds
    # pdf_field_flag_change -- which lives under conditional_logic in the gold.
    # Before bd polyglot-pdf-7a9.16 it read conditional_behavior and never fired,
    # leaving out_readonly True.
    assert out_readonly is False, (
        "read-only bit was NOT cleared -- the unlock did not fire "
        "(regression of bd polyglot-pdf-7a9.16)"
    )


# Race checkbox group: selecting these two options must set exactly their widgets.
# Since the schema-v2 migration (bd polyglot-pdf-c5r8) an option's VALUE is a
# semantic slug (e.g. "white") resolved to its widget via option.pdf_field_name;
# the widget LEAVES are unchanged (only option.value migrated).
_RACE_FIELD_ID = "p3_race"
# Option VALUES (schema-v2 slugs) for White and Black -- what a fill request sends.
_RACE_SELECTED = ["white", "black_or_african_american"]
# The widget leaves those two options resolve to.
_RACE_SELECTED_LEAVES = ["P3_checkbox7_White[0]", "P3_checkbox7_Black[0]"]
_RACE_ALL_LEAVES = [
    "P3_checkbox7_White[0]", "P3_checkbox7_Asian[0]", "P3_checkbox7_Black[0]",
    "P3_checkbox7_Indian[0]", "P3_checkbox7_Hawaiian[0]",
]


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


@pytest.mark.skipif(not (_KIT_ROOT / "form.pdf").exists(),
                    reason="i-90 kit not present")
def test_p3_race_options_fill():
    schema = _load_gold_schema()

    req = PDFFillRequest(
        kit_id="i-90",
        pdf_filename="form.pdf",
        field_values={_RACE_FIELD_ID: _RACE_SELECTED},
        form_schema=schema,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200

    states = _as_states_by_leaf(resp.body, _RACE_ALL_LEAVES)
    # All five race widgets must be present (they were "widget_not_found" before
    # the [0] index was restored to the option pdf_field_names -- bd 7a9.15).
    assert set(states) == set(_RACE_ALL_LEAVES), (
        "not all race widgets resolved -- option pdf_field_names do not match the "
        "PDF (regression of bd polyglot-pdf-7a9.15)"
    )
    # The two selected widgets are ON (non-Off); the other three stay Off.
    for leaf in _RACE_SELECTED_LEAVES:
        assert states[leaf] not in ("/Off", "Off", None), f"{leaf} did not fill"
    for leaf in set(_RACE_ALL_LEAVES) - set(_RACE_SELECTED_LEAVES):
        assert states[leaf] in ("/Off", "Off"), f"{leaf} should not be selected"
