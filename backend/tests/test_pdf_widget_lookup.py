"""Spec: the /fill-pdf widget-lookup edges (bd polyglot-pdf-uov.12, T3.1).

test_pdf_fill_readonly_unlock.py pins two historic CHOICE-field bugs against the
on-disk I-90 kit, but the widget-lookup core -- find_widget's XFA path matching and
fill_widget's weak-ref re-fetch -- has edges that kit cannot exercise on demand
(an exact-vs-endswith collision, a widget on a later page, a name with no widget).
This module specs those edges with SYNTHETIC in-memory PDFs built with PyMuPDF, so
each case is deterministic and present without depending on the real kit:

  1. XFA path matching -- the schema carries a leaf like 'MyField[0]' while an XFA
     PDF widget is 'form1[0].#subform[0].MyField[0]'. find_widget tries EXACT
     across all pages first, then endswith across all pages.
  2. exact-beats-endswith PRECEDENCE -- an exact match on a LATER page must win
     over an endswith-only candidate on an earlier page (the two-pass ordering),
     so a partial path never shadows the real field.
  3. multi-page lookup -- a widget on page 2 (not page 0) is still found.
  4. missing widget -- a schema field whose pdf_field_name matches NO widget is
     skipped gracefully: the route still returns 200 with a valid PDF, it does not
     500 or drop the whole fill.

The synthetic PDFs are driven through the REAL fill_pdf route with the form-kit
store mocked to return the in-memory bytes (the route's only I/O dependency), so
the route's actual find_widget/fill_widget closures run -- not a reimplementation.

ASCII only.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pymupdf as fitz  # PyMuPDF
import pytest

import backend.routes.pdf_fill_routes as pdf_routes
from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf


# --------------------------------------------------------------------------
# Synthetic-PDF helpers
# --------------------------------------------------------------------------
def _make_pdf(pages: list[list[str]]) -> bytes:
    """Build a PDF with one text widget per name, laid out page by page.

    pages[i] is the list of widget field_names on page i. Returns the PDF bytes.
    """
    doc = fitz.open()
    for page_widget_names in pages:
        page = doc.new_page()
        y = 50.0
        for name in page_widget_names:
            widget = fitz.Widget()
            widget.field_name = name
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.rect = fitz.Rect(50, y, 250, y + 20)
            page.add_widget(widget)
            y += 40.0
    out = doc.tobytes()
    doc.close()
    return out


def _widget_values(pdf_bytes: bytes) -> dict[str, str]:
    """field_name -> field_value for every widget in a saved PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        out: dict[str, str] = {}
        for pno in range(doc.page_count):
            for w in doc[pno].widgets() or []:
                out[w.field_name] = w.field_value
        return out
    finally:
        doc.close()


def _text_schema(field_id: str, pdf_field_name: str) -> dict:
    return {"fields": [{"id": field_id, "type": "text", "pdf_field_name": pdf_field_name}]}


@pytest.fixture
def mock_store(monkeypatch):
    """Patch the route's form-kit store so load_pdf_bytes returns OUR synthetic PDF.

    Returns a setter: call set_pdf(bytes) to choose what the route will load.
    """
    store = MagicMock(name="form_kit_store")
    store.load_pdf_bytes = AsyncMock()
    # The fill route now runs the client-tier kit gates (bd polyglot-pdf-
    # vy6id), whose metadata read awaits store.load_metadata. A bare
    # MagicMock AUTO-CREATES that attribute as a non-awaitable mock; make it
    # a real async loader returning None (= no metadata -> public kit), the
    # same contract the real stores honor for absence.
    store.load_metadata = AsyncMock(return_value=None)
    # Same MagicMock trap, second attribute: an auto-created truthy
    # enforce_complete_on_public_reads would arm the publish gate against
    # the None metadata above and 404 every fill. Local-mode semantics.
    store.enforce_complete_on_public_reads = False
    monkeypatch.setattr(pdf_routes, "get_form_kit_store", lambda: store)

    def set_pdf(pdf_bytes: bytes):
        store.load_pdf_bytes.return_value = pdf_bytes

    return set_pdf


def _fill(pdf_field_name_in_schema: str, fill_value: str = "HELLO") -> "Response":
    req = PDFFillRequest(
        kit_id="synthetic",
        pdf_filename="f.pdf",
        field_values={"fid": fill_value},
        form_schema=_text_schema("fid", pdf_field_name_in_schema),
    )
    return asyncio.run(fill_pdf(req))


# --------------------------------------------------------------------------
# 1. XFA path matching -- schema leaf, PDF full path -> endswith resolves it
# --------------------------------------------------------------------------
def test_xfa_full_path_matched_by_endswith(mock_store):
    """The schema carries the leaf 'MyField[0]'; the only widget is the XFA full
    path 'form1[0].#subform[0].MyField[0]'. find_widget's endswith pass resolves
    it and the value lands on that widget."""
    pdf = _make_pdf([["form1[0].#subform[0].MyField[0]"]])
    mock_store(pdf)

    resp = _fill("MyField[0]", "XFA_VALUE")

    assert resp.status_code == 200
    assert _widget_values(resp.body)["form1[0].#subform[0].MyField[0]"] == "XFA_VALUE"


# --------------------------------------------------------------------------
# 2. exact-beats-endswith PRECEDENCE -- exact on a LATER page wins
# --------------------------------------------------------------------------
def test_exact_match_beats_endswith_even_on_a_later_page(mock_store):
    """find_widget does a full EXACT pass across ALL pages before any endswith
    pass. So an exact 'MyField[0]' on page 1 must win over an endswith-only
    'form1[0].sub[0].MyField[0]' on page 0 -- the partial path must not shadow the
    real field just because it sorts earlier."""
    pdf = _make_pdf([
        ["form1[0].sub[0].MyField[0]"],  # page 0: endswith-only candidate
        ["MyField[0]"],                  # page 1: the exact match
    ])
    mock_store(pdf)

    resp = _fill("MyField[0]", "EXACT_WINS")

    values = _widget_values(resp.body)
    assert values["MyField[0]"] == "EXACT_WINS"            # exact got the value
    assert values["form1[0].sub[0].MyField[0]"] == ""       # endswith candidate untouched


# --------------------------------------------------------------------------
# 3. multi-page lookup -- a widget on a non-first page is found
# --------------------------------------------------------------------------
def test_widget_on_a_later_page_is_found(mock_store):
    """find_widget scans every page, so a field whose widget lives on page 2
    (with empty pages before it) is still resolved and filled."""
    pdf = _make_pdf([
        [],                # page 0: no widgets
        [],                # page 1: no widgets
        ["OnPage3[0]"],    # page 2: the target
    ])
    mock_store(pdf)

    resp = _fill("OnPage3[0]", "DEEP_PAGE")

    assert resp.status_code == 200
    assert _widget_values(resp.body)["OnPage3[0]"] == "DEEP_PAGE"


# --------------------------------------------------------------------------
# 4. missing widget -- a name with no widget is skipped, not fatal
# --------------------------------------------------------------------------
def test_missing_widget_is_skipped_not_fatal(mock_store):
    """A schema field whose pdf_field_name matches NO widget must be skipped: the
    route still returns 200 with a valid PDF (it does not 500 or abort the fill),
    and the unrelated widget that IS present is left untouched."""
    pdf = _make_pdf([["RealField[0]"]])
    mock_store(pdf)

    # The schema points at a name that does not exist in the PDF.
    resp = _fill("DoesNotExist[0]", "NOPE")

    assert resp.status_code == 200
    # Valid PDF came back, and the present widget was not somehow filled by the
    # missing one.
    assert _widget_values(resp.body) == {"RealField[0]": ""}


def test_missing_widget_does_not_block_a_sibling_fill(mock_store):
    """A missing widget skips only its own field -- a sibling field whose widget
    DOES exist still fills in the same request (graceful per-field degradation)."""
    pdf = _make_pdf([["Present[0]"]])
    mock_store(pdf)

    req = PDFFillRequest(
        kit_id="synthetic",
        pdf_filename="f.pdf",
        field_values={"missing": "NOPE", "present": "FILLED"},
        form_schema={
            "fields": [
                {"id": "missing", "type": "text", "pdf_field_name": "Absent[0]"},
                {"id": "present", "type": "text", "pdf_field_name": "Present[0]"},
            ]
        },
    )
    resp = asyncio.run(fill_pdf(req))

    assert resp.status_code == 200
    assert _widget_values(resp.body)["Present[0]"] == "FILLED"


# --------------------------------------------------------------------------
# 5. []-alias key resolution (bd polyglot-pdf-h3ac). Gemini inconsistently
#    adds/drops the trailing [] on checkbox-group ids, so a value payload can be
#    keyed under the OTHER bracket variant than the schema id. The lookup +
#    pdf_field_name map now register both variants, so the field fills either way
#    (previously the exact-key miss dropped the value and the widget filled BLANK,
#    exposed once got6 stopped storing a duplicate schema-id-keyed entry).
# --------------------------------------------------------------------------
def test_value_keyed_without_brackets_fills_a_bracketed_schema_id(mock_store):
    # schema id 'x[]', value payload keyed 'x' -> fills.
    pdf = _make_pdf([["W_X[0]"]])
    mock_store(pdf)
    req = PDFFillRequest(
        kit_id="synthetic", pdf_filename="f.pdf",
        field_values={"x": "VAL"},
        form_schema={"fields": [{"id": "x[]", "type": "text", "pdf_field_name": "W_X[0]"}]},
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200
    assert _widget_values(resp.body)["W_X[0]"] == "VAL"


def test_value_keyed_with_brackets_fills_an_unbracketed_schema_id(mock_store):
    # schema id 'x', value payload keyed 'x[]' -> fills (the reverse direction).
    pdf = _make_pdf([["W_X[0]"]])
    mock_store(pdf)
    req = PDFFillRequest(
        kit_id="synthetic", pdf_filename="f.pdf",
        field_values={"x[]": "VAL"},
        form_schema={"fields": [{"id": "x", "type": "text", "pdf_field_name": "W_X[0]"}]},
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200
    assert _widget_values(resp.body)["W_X[0]"] == "VAL"


def test_exact_id_wins_when_both_variants_are_real_distinct_fields(mock_store):
    # Both 'x' and 'x[]' are REAL distinct schema fields -> each resolves to its OWN
    # widget by exact id; the alias registration never clobbers a real exact id.
    pdf = _make_pdf([["W_PLAIN[0]", "W_BRACKET[0]"]])
    mock_store(pdf)
    req = PDFFillRequest(
        kit_id="synthetic", pdf_filename="f.pdf",
        field_values={"x": "PLAIN", "x[]": "BRACKET"},
        form_schema={"fields": [
            {"id": "x", "type": "text", "pdf_field_name": "W_PLAIN[0]"},
            {"id": "x[]", "type": "text", "pdf_field_name": "W_BRACKET[0]"},
        ]},
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200
    vals = _widget_values(resp.body)
    assert vals["W_PLAIN[0]"] == "PLAIN"
    assert vals["W_BRACKET[0]"] == "BRACKET"


def test_mapping_less_exact_field_is_not_filled_by_a_siblings_alias(mock_store):
    """bd polyglot-pdf-eb4z: the field_mappings alias asymmetry.

    Two DISTINCT real fields 'x' (text, NO pdf_field_name) and 'x[]' (text,
    pdf_field_name W_BRACKET). Because 'x' writes no field_mappings entry of its
    own, a naive alias registration would let 'x[]'s alias write
    field_mappings['x'] = W_BRACKET, so a value keyed 'x' would wrongly fill
    x[]'s widget. The exact-wins invariant must hold: field_mappings.get('x')
    stays absent (the alias write is skipped because 'x' is a real schema id), so
    the 'x' value fills NOTHING and W_BRACKET is left untouched."""
    pdf = _make_pdf([["W_BRACKET[0]"]])
    mock_store(pdf)
    req = PDFFillRequest(
        kit_id="synthetic", pdf_filename="f.pdf",
        field_values={"x": "WRONG_TARGET"},
        form_schema={"fields": [
            {"id": "x", "type": "text"},  # real field, NO pdf_field_name
            {"id": "x[]", "type": "text", "pdf_field_name": "W_BRACKET[0]"},
        ]},
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200
    # x[]'s widget must NOT have received x's value.
    assert _widget_values(resp.body)["W_BRACKET[0]"] == ""


def test_mapping_less_exact_field_reverse_bracket_direction(mock_store):
    """The reverse of the case above: the mapping-less exact field is the
    BRACKETED one ('x[]', no pdf_field_name) and its sibling 'x' carries the
    pdf_field_name. A value keyed 'x[]' must not fill x's widget."""
    pdf = _make_pdf([["W_PLAIN[0]"]])
    mock_store(pdf)
    req = PDFFillRequest(
        kit_id="synthetic", pdf_filename="f.pdf",
        field_values={"x[]": "WRONG_TARGET"},
        form_schema={"fields": [
            {"id": "x", "type": "text", "pdf_field_name": "W_PLAIN[0]"},
            {"id": "x[]", "type": "text"},  # real field, NO pdf_field_name
        ]},
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200
    assert _widget_values(resp.body)["W_PLAIN[0]"] == ""
