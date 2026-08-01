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


@pytest.mark.parametrize("field_id,suffix", [
    (_DOB_FIELD, _DOB_SUFFIX),
    ("id_document_expiration_date", "f1_26[0]"),
    ("date_of_entry_us", "f1_27[0]"),
], ids=["date_of_birth", "id_doc_expiration", "date_of_entry"])
def test_all_three_comb8_date_fields_print_a_full_4_digit_year(field_id, suffix):
    """All three W-7 comb-8 dates, not just DOB.

    f1_26 and f1_27 sit in NARROW 64.8pt boxes (DOB's is 100.8pt), so they are the
    ones most likely to regress if the relax path changes.
    """
    value = "03/14/1990"
    printed = _rendered_text(_fill({field_id: value}), suffix)
    assert printed.endswith("1990"), (
        f"{field_id} printed as {printed!r} -- the 4-digit year was truncated"
    )


# --------------------------------------------------------------------------- #
# Separator stripping keeps the comb on the OTHER kits' identifier boxes.
# The first cut of this fix relaxed any overflowing comb, which silently
# un-combed i-90 / f1040 SSN and A-Number boxes as soon as a user typed the
# punctuation those formats invite ('123-45-6789'). Stripping first keeps the
# one-digit-per-cell rendering the form intends (fresh-eyes review of br7t).
# --------------------------------------------------------------------------- #

_I90_KIT = Path(__file__).resolve().parents[2] / "form-kits" / "i-90"
_F1040_KIT = Path(__file__).resolve().parents[2] / "form-kits" / "f1040"


def _fill_kit(kit_id: str, kit_root: Path, field_values: dict) -> bytes:
    schema = json.loads((kit_root / "schema.json").read_text(encoding="utf-8"))
    resp = asyncio.run(fill_pdf(PDFFillRequest(
        kit_id=kit_id, pdf_filename="form.pdf",
        field_values=field_values, form_schema=schema,
    )))
    assert resp.status_code == 200
    return resp.body


@pytest.mark.skipif(not (_I90_KIT / "form.pdf").exists(), reason="i-90 kit absent")
def test_dashed_ssn_strips_and_keeps_the_i90_comb():
    """'123-45-6789' overflows comb-9 only because of punctuation.

    Stripping makes it fit, so the box keeps its intended one-digit-per-cell
    look; relaxing instead would visibly change a form that was rendering fine.
    """
    filled = _fill_kit("i-90", _I90_KIT, {"p1_line16_ssn": "123-45-6789"})
    printed = _rendered_text(filled, "P1_Line16_SSN[0]")
    assert "123456789" in printed, printed
    assert _comb_flag(filled, "P1_Line16_SSN[0]") is True, (
        "a dashed SSN un-combed the box instead of being stripped to fit"
    )


@pytest.mark.skipif(not (_F1040_KIT / "form.pdf").exists(), reason="f1040 kit absent")
def test_dashed_ssn_strips_and_keeps_the_f1040_comb():
    filled = _fill_kit("f1040", _F1040_KIT, {"fld_your_ssn": "123-45-6789"})
    printed = _rendered_text(filled, "f1_16[0]")
    assert "123456789" in printed, printed
    assert _comb_flag(filled, "f1_16[0]") is True


@pytest.mark.skipif(not (_I90_KIT / "form.pdf").exists(), reason="i-90 kit absent")
def test_a_number_with_its_letter_prefix_relaxes_rather_than_truncating():
    """'A123456789' is 10 chars in 9 cells and the 'A' is MEANINGFUL, so it
    cannot be stripped -- relaxing is correct here, and beats printing
    'A12345678'."""
    filled = _fill_kit("i-90", _I90_KIT, {"p1_line1_aliennumber": "A123456789"})
    printed = _rendered_text(filled, "P1_Line1_AlienNumber[0]")
    assert printed.endswith("A123456789"), printed

