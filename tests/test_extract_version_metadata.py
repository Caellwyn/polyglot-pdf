"""Tests for extract_form.py's deterministic version-metadata recovery
(bd polyglot-pdf-s4dp.2).

Forms carry version info in several shapes -- USCIS "Edition MM/DD/YY", IRS
"(Rev. Month Year)", IRS year-only "2025" -- and some carry none. The pure
`extract_version_metadata(page1_text, title)` recovers edition/revision, OMB, and
expiration where present, attaches a `version_confidence` (high for a specific
pattern, low for a generic fallback, 0 for none), and degrades a version-less form
to the sentinel "unknown" (never "draft"/blank/crash).

The synthetic-text cases are the core unit test (no PDF/LLM). The real-PDF cases
re-run the extractor end-to-end against the four repo forms and assert the
probed table; each skips if its PDF is absent in this checkout.

Imports extract_form by file path (repo precedent: test_extract_form_backfill.py).
"""

import importlib.util
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


# --- synthetic text (the core unit test: no PDF, no LLM) -------------------- #

class TestExtractVersionMetadataSynthetic:
    def test_uscis_edition_form(self):
        # I-90/I-589 style: "Edition MM/DD/YY" + OMB + Expires.
        text = (
            "Form I-90   Edition   01/20/25\nPage 1 of 7\n"
            "U.S. Citizenship and Immigration Services\n"
            "OMB No. 1615-0082   Expires 02/28/2027\n"
        )
        out = ef.extract_version_metadata(text, "Form I-90, Application to Replace")
        assert out["form_number"] == "I-90"
        assert out["edition_date"] == "01/20/25"
        assert out["version"] == "01/20/25"
        assert out["version_confidence"] == ef._CONF_HIGH
        assert out["omb_number"] == "1615-0082"
        assert out["expiration_date"] == "02/28/2027"
        assert out["agency"] == "U.S. Citizenship and Immigration Services"

    def test_irs_rev_month_year_form(self):
        # W-7 style: "(Rev. December 2024)", OMB, NO expiration.
        text = (
            "Form  W-7\n(Rev. December 2024)\n"
            "Application for IRS Individual Taxpayer Identification Number\n"
            "Department of the Treasury  Internal Revenue Service\n"
            "OMB No. 1545-0074\n"
        )
        out = ef.extract_version_metadata(text, "Form W-7 (Rev. December 2024)")
        assert out["form_number"] == "W-7"
        assert out["version"] == "December 2024"
        assert out["version_confidence"] == ef._CONF_HIGH
        assert out["omb_number"] == "1545-0074"
        assert "expiration_date" not in out  # W-7 has none
        assert "edition_date" not in out  # no Edition MM/DD/YY
        assert out["agency"] == "Internal Revenue Service"

    def test_irs_year_only_form_is_low_confidence(self):
        # 1040 style: only a bare year "2025" -> low-confidence version.
        text = (
            "Form\n1040\n2025\nU.S. Individual Income Tax Return\n"
            "Department of the Treasury - Internal Revenue Service\n"
            "OMB No. 1545-0074\n"
        )
        out = ef.extract_version_metadata(text, "2025 Form 1040")
        assert out["form_number"] == "1040"
        assert out["version"] == "2025"
        assert out["version_confidence"] == ef._CONF_LOW  # generic fallback
        assert out["omb_number"] == "1545-0074"
        assert "expiration_date" not in out

    def test_versionless_form_degrades_to_unknown(self):
        # A generic blank AcroForm with no recoverable version info.
        text = "Application Form\nName:\nAddress:\nSignature:\n"
        out = ef.extract_version_metadata(text, "")
        assert out["version"] == "unknown"
        assert out["version_confidence"] == ef._CONF_NONE
        assert "edition_date" not in out
        assert "expiration_date" not in out
        assert "omb_number" not in out

    def test_expiration_year_is_not_mistaken_for_version(self):
        # A version-less form whose only 20xx date is an EXPIRATION must NOT have
        # that year promoted to version -- it stays "unknown" (Codex PR #263). An
        # unscoped bare-year fallback would have made version "2027" here.
        text = "Some Application Form\nExpires 02/28/2027\nName:\nSignature:\n"
        out = ef.extract_version_metadata(text, "")
        assert out["version"] == "unknown"
        assert out["expiration_date"] == "02/28/2027"  # still captured as expiration

    def test_year_only_version_requires_a_form_context(self):
        # A bare year adjacent to "Form 1040" on page 1 IS a version (IRS header).
        out = ef.extract_version_metadata("Form 1040\n2025\nIncome Tax Return\n", "")
        assert out["version"] == "2025"
        assert out["version_confidence"] == ef._CONF_LOW

    def test_title_year_must_be_adjacent_to_form_id(self):
        # "2025 Form 1040" -> version 2025 (IRS year-only header convention).
        assert ef.extract_version_metadata("", "2025 Form 1040")["version"] == "2025"
        # A non-version year in the title (e.g. an expiration) must NOT be promoted
        # (Codex PR #263 r2 -- the title fallback must be Form-adjacent too).
        assert ef.extract_version_metadata("Application\nName:\n", "Form X-9 (expires 2027)")["version"] == "unknown"

    def test_loose_omb_bumps_unknown_to_low(self):
        # No version pattern, but a stray NNNN-NNNN -> at least low confidence.
        text = "Some Form\nReference 1234-5678 on file\n"
        out = ef.extract_version_metadata(text, "")
        assert out["version"] == "unknown"
        assert out["omb_number"] == "1234-5678"
        assert out["version_confidence"] == ef._CONF_LOW

    def test_edition_4digit_year_canonicalized_to_2(self):
        out = ef.extract_version_metadata("Edition 01/20/2025\n", "")
        assert out["edition_date"] == "01/20/25"
        assert out["version"] == "01/20/25"

    def test_no_expiration_fallback_even_with_a_stray_date(self):
        # expiration has NO fuzzy fallback -- a wrong expiry is worse than none.
        out = ef.extract_version_metadata("Filed 01/02/2030 by mail\n", "")
        assert "expiration_date" not in out


# --- real PDFs (end-to-end; each skips if its PDF is absent) ---------------- #

_PDFS = {
    "i-90": "schema-editor/public/schemas/i-90/i-90.pdf",
    "w7": "form-kits/w7/form.pdf",
    "f1040": "form-kits/f1040/form.pdf",
    "i-589": "schema-editor/public/schemas/i-589/i-589.pdf",
}


def _meta_for(rel_path: str) -> dict:
    import pymupdf as fitz
    path = _REPO / rel_path
    if not path.exists():
        pytest.skip(f"PDF not present in this checkout: {rel_path}")
    doc = fitz.open(str(path))
    try:
        return ef._extract_version_metadata_from_doc(doc)
    finally:
        doc.close()


class TestExtractVersionMetadataRealPDFs:
    def test_i90(self):
        m = _meta_for(_PDFS["i-90"])
        assert m["form_number"] == "I-90"
        assert m["edition_date"] == "01/20/25"
        assert m["omb_number"] == "1615-0082"
        assert m["expiration_date"] == "02/28/2027"
        assert m["version_confidence"] == ef._CONF_HIGH

    def test_w7(self):
        m = _meta_for(_PDFS["w7"])
        assert m["form_number"] == "W-7"
        assert m["version"] == "December 2024"
        assert m["omb_number"] == "1545-0074"
        assert "expiration_date" not in m
        assert m["version_confidence"] == ef._CONF_HIGH

    def test_f1040(self):
        m = _meta_for(_PDFS["f1040"])
        assert m["form_number"] == "1040"
        assert m["version"] == "2025"
        assert m["omb_number"] == "1545-0074"
        assert m["version_confidence"] == ef._CONF_LOW

    def test_i589(self):
        m = _meta_for(_PDFS["i-589"])
        assert m["form_number"] == "I-589"
        assert m["edition_date"] == "01/20/25"
        assert m["omb_number"] == "1615-0067"
        assert m["expiration_date"] == "09/30/2027"
        assert m["version_confidence"] == ef._CONF_HIGH
