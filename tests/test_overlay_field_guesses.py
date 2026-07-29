"""Tests for scripts/authoring/overlay_field_guesses.py (bd polyglot-pdf-3ave).

The overlay is the SECOND review surface for field<->widget assignment. Its
companion, check_line_binding.py, is exact but narrow -- it can only judge a
field that states a line number and claims a widget on a printed marker row, so
it abstains entirely on a form like W-7 that prints no gutter markers. The
overlay covers precisely that gap: it draws the extractor's own guess onto each
widget so a human or vision model can ask the semantic question ("is this
'signature' actually on a phone box?") no numbering scheme can answer.

These pin the mechanics -- what gets drawn, from which fields, and that a
coverage gap is visually distinct from a mislabel. The judgement itself is the
reviewer's; there is no assertion here about a form being 'correct'.

ASCII only.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "authoring" / "overlay_field_guesses.py"
spec = importlib.util.spec_from_file_location("overlay_field_guesses", _SCRIPT)
ov = importlib.util.module_from_spec(spec)
sys.modules["overlay_field_guesses"] = ov
spec.loader.exec_module(ov)

_W7_PDF = _REPO / "form-kits" / "w7" / "form.pdf"
_W7_SCHEMA = _REPO / "form-kits" / "w7" / "schema.json"

needs_w7 = pytest.mark.skipif(not _W7_PDF.exists(), reason="w7 kit not present")
pytest.importorskip("fitz", reason="PyMuPDF required to render the overlay")


# --------------------------------------------------------------------------- #
# Which text gets drawn
# --------------------------------------------------------------------------- #

def test_label_mode_prefers_the_requested_key():
    f = {"id": "fld_x", "name": "Display Label", "spoken_name": "spoken label"}
    assert ov._label_for(f, "spoken") == "spoken label"
    assert ov._label_for(f, "name") == "Display Label"
    assert ov._label_for(f, "id") == "fld_x"


def test_label_falls_back_when_the_preferred_key_is_missing_or_blank():
    # spoken_name is the default mode; a blank one must not draw an empty plate.
    assert ov._label_for({"id": "fld_x", "spoken_name": "   "}, "spoken") == "fld_x"
    assert ov._label_for({"id": "fld_x"}, "spoken") == "fld_x"


def test_option_level_claims_are_drawn_with_their_value():
    """Choice fields carry their real widget identity on OPTIONS, not on the
    field -- if the overlay skipped those, every checkbox would look unclaimed."""
    schema = {"fields": [{
        "id": "reason", "spoken_name": "reason", "options": [
            {"value": "a_treaty", "pdf_field_name": "top.c1_2[0]"},
            {"value": "b_filing", "pdf_field_name": "top.c1_3[0]"},
        ],
    }]}
    claims = ov._claims(schema, "spoken")
    assert claims["top.c1_2[0]"] == "reason=a_treaty"
    assert claims["top.c1_3[0]"] == "reason=b_filing"


def test_claims_walk_nested_parts_and_sections():
    schema = {"parts": [{"sections": [{"fields": [
        {"id": "a", "spoken_name": "alpha", "pdf_field_name": "w1"},
    ]}]}]}
    assert ov._claims(schema, "spoken") == {"w1": "alpha"}


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

@needs_w7
def test_renders_every_widget_and_reports_counts(tmp_path):
    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    out = tmp_path / "review.pdf"
    result = ov.annotate(schema, str(_W7_PDF), str(out), "spoken")
    assert out.exists() and out.stat().st_size > 0
    # The hand-corrected w7 gold deliberately leaves the two "Other" write-in
    # widgets (f1_04, f1_23) unmodeled -- bd ivh9 pins that. They must show as
    # a COVERAGE gap, visually distinct from a mislabelled box.
    assert result["unclaimed"] == 2
    assert result["drawn"] > 0


@needs_w7
def test_an_unclaimed_widget_is_counted_separately_from_a_labelled_one(tmp_path):
    """Dropping a field must move exactly one widget from drawn -> unclaimed:
    a coverage gap and a mislabel are different bugs and must not look alike."""
    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    base = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "a.pdf"), "spoken")

    dropped = None
    for f in list(ov._iter_fields(schema)):
        if isinstance(f.get("pdf_field_name"), str) and f.get("pdf_field_name"):
            dropped = f.pop("pdf_field_name")
            break
    assert dropped is not None
    after = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "b.pdf"), "spoken")
    assert after["unclaimed"] == base["unclaimed"] + 1
    assert after["drawn"] == base["drawn"] - 1


@needs_w7
def test_png_rasterization_is_opt_in(tmp_path):
    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    no_png = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "a.pdf"), "spoken")
    assert no_png["pngs"] == []

    png_dir = tmp_path / "pages"
    with_png = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "b.pdf"),
                           "spoken", str(png_dir))
    assert with_png["pngs"]
    for p in with_png["pngs"]:
        assert pathlib.Path(p).exists()


def test_missing_schema_is_a_usage_error_not_a_crash(tmp_path, capsys):
    rc = ov.main(["--schema", str(tmp_path / "nope.json"),
                  "--pdf", str(_W7_PDF), "--out", str(tmp_path / "o.pdf")])
    capsys.readouterr()
    assert rc == 2
