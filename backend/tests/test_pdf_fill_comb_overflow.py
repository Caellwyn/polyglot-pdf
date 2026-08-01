"""Regression tests for comb-field truncation on the filled PDF (bd
polyglot-pdf-br7t).

An AcroForm text widget with the Comb flag splits its box into exactly MaxLen
cells and prints ONE glyph per cell. PyMuPDF stores and reads back a longer value
regardless, so the AcroForm VALUE round-trips perfectly while the RENDERED page
silently shows only the first MaxLen characters.

On W-7 that truncated every 4-digit year: date_of_birth, id_document_expiration_
date and date_of_entry_us are all comb-8, so '03/14/1990' printed as '03/14/19'
-- a wrong date of birth on a filed ITIN application, invisible to every
value-level check, every lint, and the whole test suite.

These tests therefore assert on RENDERED text (page.get_text over the widget
rect), not on widget.field_value -- reading the value back is precisely the check
this bug defeats.

Both drive the REAL /fill-pdf route against the on-disk W-7 kit.

ASCII only.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf

_KIT_ROOT = Path(__file__).resolve().parents[2] / "form-kits" / "w7"

_COMB_FLAG = 1 << 24

# Comb-8 date widgets: the value that must print IN FULL.
_DOB_FIELD = "date_of_birth"
_DOB_SUFFIX = "f1_17[0]"
_DOB_VALUE = "03/14/1990"

# Comb digit groups that ALREADY fit their cells -- these must keep the comb
# appearance the form intends (one digit per printed box), so the fix must not
# touch them.
_ITIN_FIELD = "itin_part1"
_ITIN_SUFFIX = "f1_28[0]"
_ITIN_VALUE = "123"

pytestmark = pytest.mark.skipif(
    not (_KIT_ROOT / "form.pdf").exists(), reason="w7 kit not present"
)


def _load_gold_schema() -> dict:
    return json.loads((_KIT_ROOT / "schema.json").read_text(encoding="utf-8"))


def _widget_by_suffix(doc, suffix: str):
    for pno in range(doc.page_count):
        for w in doc[pno].widgets() or []:
            if w.field_name and w.field_name.endswith(suffix):
                return w, doc[pno]
    return None, None


def _rendered_text(pdf_bytes: bytes, suffix: str) -> str:
    """The text actually PRINTED inside the widget's box.

    A comb field renders one glyph per cell with wide gaps, so the raw extraction
    is like '0 3 / 1 4 / 1 9'; whitespace is collapsed so the assertion is about
    which CHARACTERS reached the page, not their spacing.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        widget, page = _widget_by_suffix(doc, suffix)
        assert widget is not None, f"widget {suffix} not found in the filled PDF"
        raw = page.get_text("text", clip=widget.rect)
    finally:
        doc.close()
    return "".join(raw.split())


def _comb_flag(pdf_bytes: bytes, suffix: str) -> bool:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        widget, _ = _widget_by_suffix(doc, suffix)
        assert widget is not None, f"widget {suffix} not found"
        return bool(widget.field_flags & _COMB_FLAG)
    finally:
        doc.close()


def _fill(field_values: dict) -> bytes:
    resp = asyncio.run(fill_pdf(PDFFillRequest(
        kit_id="w7",
        pdf_filename="form.pdf",
        field_values=field_values,
        form_schema=_load_gold_schema(),
    )))
    assert resp.status_code == 200
    return resp.body


def test_source_dob_widget_is_a_comb_that_cannot_hold_the_value():
    """Precondition: without this the test could pass without exercising the fix."""
    doc = fitz.open(str(_KIT_ROOT / "form.pdf"))
    try:
        widget, _ = _widget_by_suffix(doc, _DOB_SUFFIX)
        assert widget is not None
        assert bool(widget.field_flags & _COMB_FLAG), "DOB widget is not a comb field"
        assert widget.text_maxlen == 8
    finally:
        doc.close()
    assert len(_DOB_VALUE) > 8, "test value must overflow the comb cells"


def test_four_digit_year_prints_in_full():
    """The headline bug: '03/14/1990' used to PRINT as '03/14/19'.

    Asserts on rendered text, not widget.field_value -- the value was always
    stored correctly, which is why this went unnoticed.
    """
    printed = _rendered_text(_fill({_DOB_FIELD: _DOB_VALUE}), _DOB_SUFFIX)
    assert _DOB_VALUE.replace("/", "") in printed.replace("/", ""), (
        f"date printed as {printed!r}; the 4-digit year was truncated "
        f"(regression of bd polyglot-pdf-br7t)"
    )
    # Specifically: the last two digits of the year must survive.
    assert printed.endswith("1990"), printed


def test_overflowing_comb_is_relaxed_but_a_fitting_one_is_not():
    """The fix must be surgical.

    The ITIN/IRSN digit groups are comb-3/2/4 and their values always fit; they
    are MEANT to render as separate cells, so relaxing them would visibly change
    a correct form. Only a widget whose value would truncate is relaxed.
    """
    filled = _fill({_DOB_FIELD: _DOB_VALUE, _ITIN_FIELD: _ITIN_VALUE})
    assert _comb_flag(filled, _DOB_SUFFIX) is False, (
        "the overflowing DOB comb was not relaxed"
    )
    assert _comb_flag(filled, _ITIN_SUFFIX) is True, (
        "a comb whose value FITS was relaxed -- the fix is too broad"
    )
    # And the fitting one still prints its digits.
    assert "123" in _rendered_text(filled, _ITIN_SUFFIX)


def test_a_value_that_fits_the_comb_is_untouched():
    """MM/DD/YY exactly fills the 8 cells, so nothing should be relaxed."""
    short = "03/14/90"
    assert len(short) == 8
    filled = _fill({_DOB_FIELD: short})
    assert _comb_flag(filled, _DOB_SUFFIX) is True, (
        "a value that fits triggered the relax path"
    )
    assert "03/14/90" in _rendered_text(filled, _DOB_SUFFIX).replace(" ", "")
