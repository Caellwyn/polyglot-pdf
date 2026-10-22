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
import textwrap
from pathlib import Path

import pymupdf as fitz  # PyMuPDF
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
# THE VALUE IS NEVER REWRITTEN.
#
# An earlier cut of this fix also stripped formatting punctuation so an
# identifier like '123-45-6789' would still fit its comb-9 box. Three review
# rounds each found another input where that strip REORDERED meaning instead of
# reformatting it, and each rewritten value then FIT the cells and printed a
# plausible-looking wrong value. These pin the property that makes the whole
# class unreachable: fit_comb_value changes appearance only.
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


def _stored_value(pdf_bytes: bytes, suffix: str) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        widget, _ = _widget_by_suffix(doc, suffix)
        assert widget is not None, f"widget {suffix} not found"
        return widget.field_value or ""
    finally:
        doc.close()


@pytest.mark.parametrize("value", [
    "1990-03-14",   # ISO -- what <input type="date"> emits for the date-typed fields
    "1990.03.14",   # dotted, year-first
    "14.03.1990",   # dotted, DD.MM.YYYY -- the everyday European/LatAm form
    "03 14 1990",   # space-separated
    "03-14-1990",   # US order with dashes
    "03/14/1990",   # slash-separated
], ids=["iso", "dotted_ymd", "dotted_dmy", "spaced", "dashed_mdy", "slashed"])
@pytest.mark.parametrize("field_id,suffix", [
    (_DOB_FIELD, _DOB_SUFFIX),
    ("date_of_entry_us", "f1_27[0]"),
], ids=["date_typed", "text_typed"])
def test_no_date_format_is_ever_rewritten(field_id, suffix, value):
    """Whatever separator a user (or the model) uses, the digits must not move.

    Every one of these strips to 8 digits, which FITS comb-8 -- so under the old
    strip step each printed as a different, plausible-looking date ('14.03.1990'
    -> '14031990' = month 14). Covers both a schema-declared date and the
    text-typed one, since a type-based guard alone missed the latter.
    """
    filled = _fill({field_id: value})
    assert _stored_value(filled, suffix) == value, "the written value was rewritten"
    printed = _rendered_text(filled, suffix)
    assert value.replace(" ", "") in printed, (
        f"{field_id} printed {printed!r} for input {value!r}"
    )


@pytest.mark.skipif(not (_I90_KIT / "form.pdf").exists(), reason="i-90 kit absent")
def test_dashed_ssn_is_not_rewritten_and_still_prints_in_full():
    """A separator-bearing identifier relaxes rather than being reformatted.

    Losing the one-digit-per-cell look is a cosmetic cost, deliberately accepted
    because rewriting the value is what let three rounds of date corruption
    through. This IS reachable in production -- handleDownloadPDF calls fillPDF
    with no validation -- so the cost is real, not hypothetical; it is simply the
    cheaper failure. Restoring the cell look belongs in input normalization (a
    real 'ssn' digit preset), not in the filler.
    """
    filled = _fill_kit("i-90", _I90_KIT, {"ssn": "123-45-6789"})
    assert _stored_value(filled, "P1_Line16_SSN[0]") == "123-45-6789"
    assert "123-45-6789" in _rendered_text(filled, "P1_Line16_SSN[0]")


@pytest.mark.skipif(not (_F1040_KIT / "form.pdf").exists(), reason="f1040 kit absent")
def test_f1040_dashed_ssn_is_not_rewritten():
    filled = _fill_kit("f1040", _F1040_KIT, {"fld_your_ssn": "123-45-6789"})
    assert _stored_value(filled, "f1_16[0]") == "123-45-6789"
    assert "123-45-6789" in _rendered_text(filled, "f1_16[0]")


@pytest.mark.skipif(not (_I90_KIT / "form.pdf").exists(), reason="i-90 kit absent")
def test_a_number_with_its_letter_prefix_relaxes_rather_than_truncating():
    """'A123456789' is 10 chars in 9 cells, so it relaxes -- and prints in full
    rather than losing its last digit to 'A12345678'."""
    filled = _fill_kit("i-90", _I90_KIT, {"a_number": "A123456789"})
    printed = _rendered_text(filled, "P1_Line1_AlienNumber[0]")
    assert printed.endswith("A123456789"), printed



def test_fit_comb_value_never_raises_on_a_dead_widget():
    """The appearance tweak must never fail a fill (bd polyglot-pdf-l53i).

    PyMuPDF widget refs are weak and go stale, so every attribute read here can
    raise -- including inside the except handler. The handler therefore logs no
    widget attribute at all; restoring a `widget_name=widget.field_name` kwarg to
    it would make this test fail, which is the point of the test.

    Reaches into the route to get the nested helper, since fit_comb_value is
    defined inside fill_pdf (matching the file's other nested helpers).
    """
    class _DeadWidget:
        @property
        def text_maxlen(self):
            raise RuntimeError("weakly-referenced object no longer exists")

        @property
        def field_flags(self):
            raise RuntimeError("weakly-referenced object no longer exists")

        @property
        def field_name(self):
            raise RuntimeError("weakly-referenced object no longer exists")

    import inspect
    import backend.routes.pdf_fill_routes as mod

    src = inspect.getsource(mod.fill_pdf)
    assert "def fit_comb_value" in src, "helper renamed -- update this test"

    # Rebuild just the helper with the module's collaborators in scope.
    ns = {"_log": mod._log, "re": mod.re, "_COMB_FLAG": 1 << 24}
    body = src[src.index("\t\tdef fit_comb_value"):]
    end = body.index("\n\t\tdef ", 1)
    exec(textwrap.dedent(body[:end]), ns)

    out = ns["fit_comb_value"](_DeadWidget(), "03/14/1990")
    assert out == "03/14/1990", "a dead widget must not change or drop the value"


def test_the_never_entered_us_phrase_prints_in_full():
    """bd polyglot-pdf-tmun: the W-7 booklet tells an applicant who has never
    entered the US to write that on line 6d, but the printed box is 64.8pt --
    the booklet's own 31-char wording ('Never entered the United States') clips
    to 'Never entered the' at any font size.

    The kit therefore instructs the 16-char short form, which measures 64.0pt and
    fits with 0.8pt to spare. This pins BOTH halves: the phrase the guidance names
    must be the phrase that fits, so a future reword cannot silently reintroduce a
    clipped value.
    """
    schema = _load_gold_schema()
    field = next(f for f in schema["fields"] if f["id"] == "date_of_entry_us")
    phrase = "Never entered US"

    # The guidance must actually name this phrase -- otherwise the model is free
    # to emit the booklet's longer wording, which does not fit.
    help_obj = field.get("help") or {}
    assert phrase in (help_obj.get("instructions") or ""), (
        "instructions no longer pin the short phrase"
    )
    assert len(phrase) <= field["max_length"], (
        f"max_length {field['max_length']} rejects the phrase the guidance names"
    )

    # The clip rect also picks up the form's own printed '/  /' date separators,
    # so assert containment of the value rather than equality with it.
    printed = _rendered_text(_fill({"date_of_entry_us": phrase}), "f1_27[0]")
    assert phrase.replace(" ", "") in printed, (
        f"printed {printed!r} -- the instructed phrase does not fit the box"
    )
